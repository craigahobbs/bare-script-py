// Licensed under the MIT License
// https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

/*
 * The BareScript C runtime - a CPython extension port of runtime.py's execute_script and
 * evaluate_expression
 *
 * runtime.py is the reference implementation: this module is observably identical to it - the same
 * results, errors, log messages, and statement counts. Script models compile to a flat register
 * bytecode, a function body lazily on its first call. A model the compiler cannot represent exactly
 * (a hand-built model the parser never produces) runs on runtime.py itself. Two behaviors are
 * implementation-defined: changing a model during execution (a function's compiled body is reused until
 * its model's keys or list lengths change), and recursion depth (nested BareScript calls are limited by
 * the C stack rather than by Python's recursion limit).
 *
 * How it was made
 *
 * Claude (Opus) ported runtime.py to this file from scratch, then alternated two loops until a full
 * round of both kept nothing: a profile-guided optimization loop, keeping a change only when it moved
 * instructions, cycles, wall time, or memory beyond noise with the other axes flat, and a
 * simplification loop for less code at flat performance. Every change passed the full "make commit"
 * gate, the four include and unit suites byte-for-byte against runtime.py, and differential fuzzing,
 * on GIL and free-threaded builds. An independent adversarial review then found four divergences,
 * each fixed with a regression test in test_runtime.py; its other two findings, an in-place model edit
 * going unseen and a deeper recursion limit, are the implementation-defined behaviors above.
 *
 * The kept optimizations, in order, with their effect when made:
 *
 *   - Definite assignment: locals definitely assigned on every path read as direct register
 *     operands (mandelbrot -5%, call -3%)
 *   - Float results reuse a float only their register holds, in place (mandelbrot -16%)
 *   - objectNew in C, and a call's own intrinsic checked first (markdownElements -23%)
 *   - Include scripts parse with the parser running on this runtime (include suite -45%)
 *   - "!" and comparisons fold into conditional jumps (mandelbrot -7%, schemaValidate -2%)
 *   - A dict watcher epoch checks a function against its model (call -24%)
 *   - runtime.py's per-call setup reads cached on the execution context (call -25%)
 *   - Library function replicas - exact-type happy paths that defer to the library otherwise - in
 *     three batches (accessor -78%, urlDecode -52%, schemaParse -42%, strcmp -62%, qrcode -31%)
 *   - Global call resolutions cached on the execution context (accessor -14%, schemaValidate -8%)
 *   - value_compare in C for exact types (schemaValidate -19%, schemaParse -10%)
 *   - Resident registers for a function called more than once (call -3%)
 *   - Intrinsic call sites' common shapes run inline on the cached function (schemaValidate -4%)
 *   - A float copy into a float only its register holds, in place (mandelbrot -3%)
 *   - jsonParse and jsonStringify through the library's own JSON coders (qrcode -11%)
 *   - regexReplace group-number replacements translated in C (qrcode -3%)
 *
 * Tried and rejected: block-level statement counting (exactness needed a second code copy), frames
 * borrowing the context's setup references, an arraySort replica, objectSet and objectNew call-site
 * shapes, an in-place mathSqrt result, and a call cache shared across execution contexts.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <datetime.h>

#include <float.h>
#include <limits.h>
#include <stddef.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#ifdef Py_GIL_DISABLED
#include <stdatomic.h>
#endif


//
// Python version compatibility
//


// Get a dict item as a new reference - 1 found, 0 absent, -1 error
#if PY_VERSION_HEX >= 0x030D0000
#define bs_dict_get PyDict_GetItemRef
#else
static int bs_dict_get(PyObject *dict, PyObject *key, PyObject **result)
{
    PyObject *value = PyDict_GetItemWithError(dict, key);
    *result = Py_XNewRef(value);
    return value != NULL ? 1 : (PyErr_Occurred() ? -1 : 0);
}
#endif


// Get a list item as a new reference, or NULL with IndexError
#if PY_VERSION_HEX >= 0x030D0000
#define bs_list_get PyList_GetItemRef
#else
static PyObject *bs_list_get(PyObject *list, Py_ssize_t index)
{
    return Py_XNewRef(PyList_GetItem(list, index));
}
#endif


// Critical sections exist from 3.13 - before that there is no free-threaded build to need them
#if PY_VERSION_HEX < 0x030D0000
#define Py_BEGIN_CRITICAL_SECTION(object) {
#define Py_END_CRITICAL_SECTION() }
#endif


// Fetch the raised exception (a new reference), clearing it
static PyObject *bs_err_fetch(void)
{
#if PY_VERSION_HEX >= 0x030C0000
    return PyErr_GetRaisedException();
#else
    PyObject *type, *value, *traceback;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    if (traceback != NULL) {
        PyException_SetTraceback(value, traceback);
    }
    Py_XDECREF(type);
    Py_XDECREF(traceback);
    return value;
#endif
}


// Re-raise an exception fetched by bs_err_fetch (steals the reference)
static void bs_err_restore(PyObject *exc)
{
#if PY_VERSION_HEX >= 0x030C0000
    PyErr_SetRaisedException(exc);
#else
    PyErr_Restore(Py_NewRef((PyObject *)Py_TYPE(exc)), exc, PyException_GetTraceback(exc));
#endif
}


// Keep a function out of line - a cold path, or one the interpreter loop must not grow by
#if defined(__GNUC__) || defined(__clang__)
#define BS_NOINLINE __attribute__((noinline))
#define BS_INLINE inline __attribute__((always_inline))
#else
#define BS_NOINLINE
#define BS_INLINE inline
#endif


// A pointer published once, lazily - an atomic compare-and-swap on the free-threaded build, where two
// threads can race to publish; the losing builder frees its copy
#ifdef Py_GIL_DISABLED
#define BS_ATOMIC_PTR(type) _Atomic(type *)
#define bs_atomic_load(ptr) atomic_load_explicit((ptr), memory_order_acquire)
#define bs_atomic_publish(ptr, expected, value) atomic_compare_exchange_strong((ptr), (expected), (value))
#define BS_ATOMIC_U64 _Atomic uint64_t
#define BS_ATOMIC_INT _Atomic int
#define bs_atomic_claim(ptr) atomic_exchange_explicit((ptr), 1, memory_order_acquire) == 0
#define bs_atomic_add(ptr) atomic_fetch_add_explicit((ptr), 1, memory_order_release)
#define bs_atomic_store(ptr, value) atomic_store_explicit((ptr), (value), memory_order_release)
#else
#define BS_ATOMIC_PTR(type) type *
#define BS_ATOMIC_U64 uint64_t
#define BS_ATOMIC_INT int
#define bs_atomic_claim(ptr) (*(ptr) == 0 ? (*(ptr) = 1) : 0)
#define bs_atomic_add(ptr) ((*(ptr))++)
#define bs_atomic_store(ptr, value) (*(ptr) = (value))
#define bs_atomic_load(ptr) (*(ptr))
#define bs_atomic_publish(ptr, expected, value) \
    (*(ptr) == *(expected) ? (*(ptr) = (value), 1) : (*(expected) = *(ptr), 0))
#endif


//
// Module state - populated once at module execution and immutable thereafter
//


// Interned strings
static PyObject *S_args, *S_binary, *S_coverage, *S_debug, *S_empty, *S_enabled, *S_expr, *S_false,
    *S_fetchFn, *S_function, *S_get, *S_globals, *S_group, *S_include, *S_includes, *S_jump, *S_label,
    *S_lastArgArray, *S_left, *S_lineNumber, *S_logFn, *S_maxStatements, *S_milliseconds, *S_name, *S_null,
    *S_number, *S_op, *S_return, *S_return_value, *S_right, *S_scriptName, *S_scripts, *S_covered, *S_count,
    *S_startswith, *S_brace, *S_dollar, *S_backslash, *S_statementCount, *S_statements, *S_string, *S_system,
    *S_total_seconds, *S_true, *S_unary, *S_url, *S_urlFn, *S_variable, *S_search, *S_finditer, *S_groups,
    *S_groupdict, *S_start, *S_index, *S_input, *S_lower, *S_upper, *S_sub, *S_unknown;

// The value type names
static PyObject *S_t_array, *S_t_boolean, *S_t_datetime, *S_t_function, *S_t_null, *S_t_number, *S_t_object,
    *S_t_regex, *S_t_string;

// Python objects from the pure-Python implementation
static PyObject *g_runtime;                  // the bare_script.runtime module - cold paths look up its names at use
static PyObject *g_BareScriptRuntimeError;
static PyObject *g_ValueArgsError;
static PyObject *g_SCRIPT_FUNCTIONS;
static PyObject *g_EXPRESSION_FUNCTIONS;
static PyObject *g_INTRINSICS;
static PyObject *g_value_string;
static PyObject *g_value_compare;
static PyObject *g_value_normalize_datetime;
static PyObject *g_value_round_number;
static PyObject *g_REGEX_TYPE;
static PyObject *g_json_loads;
static PyObject *g_json_encode;              // value._JSON_ENCODER_DEFAULT.encode
static PyObject *g_json_decode;              // library jsonParse's decoder, with Python's integer parsing
static PyObject *g_re_escape;
static PyObject *g_group_keys[10];          // the regex match group keys '0' to '9'
static PyObject *g_partial;
static PyObject *g_url_file_relative;
static PyObject *g_timedelta;
static PyObject *g_default_max_statements;   // runtime.DEFAULT_MAX_STATEMENTS
static PyObject *g_zero;                     // 0
static PyObject *g_one;                      // 1
static PyObject *g_thousand;                 // 1000
static PyObject *g_dbl_max;                  // sys.float_info.max
static PyObject *g_dbl_max_neg;              // -sys.float_info.max


// The library intrinsics - the library functions runtime.py runs inline when called by their own names, then the
// library functions replicated here, run when the call resolves to the library function itself
#define BS_INTRINSICS(X) \
    X(ARRAY_NEW, "arrayNew") X(OBJECT_GET, "objectGet") X(OBJECT_HAS, "objectHas") X(ARRAY_GET, "arrayGet") \
    X(ARRAY_LENGTH, "arrayLength") X(ARRAY_PUSH, "arrayPush") X(OBJECT_SET, "objectSet") \
    X(STRING_LENGTH, "stringLength") X(SYSTEM_TYPE, "systemType") X(OBJECT_KEYS, "objectKeys") \
    X(ARRAY_SET, "arraySet") X(MATH_SQRT, "mathSqrt") \
    X(OBJECT_NEW, "objectNew") X(STRING_SLICE, "stringSlice") X(STRING_INDEX_OF, "stringIndexOf") \
    X(STRING_STARTS_WITH, "stringStartsWith") X(STRING_TRIM, "stringTrim") X(STRING_CHAR_CODE_AT, "stringCharCodeAt") \
    X(MATH_FLOOR, "mathFloor") X(MATH_MIN, "mathMin") X(MATH_MAX, "mathMax") X(ARRAY_JOIN, "arrayJoin") \
    X(ARRAY_EXTEND, "arrayExtend") X(REGEX_MATCH, "regexMatch") X(REGEX_MATCH_ALL, "regexMatchAll") \
    X(NUMBER_PARSE_INT, "numberParseInt") X(NUMBER_PARSE_FLOAT, "numberParseFloat") X(STRING_SPLIT, "stringSplit") \
    X(STRING_ENCODE, "stringEncode") X(STRING_DECODE, "stringDecode") X(STRING_REPLACE, "stringReplace") \
    X(STRING_LOWER, "stringLower") X(STRING_UPPER, "stringUpper") X(STRING_ENDS_WITH, "stringEndsWith") \
    X(STRING_CHAR_AT, "stringCharAt") X(STRING_NEW, "stringNew") X(ARRAY_REVERSE, "arrayReverse") \
    X(ARRAY_SLICE, "arraySlice") X(ARRAY_COPY, "arrayCopy") X(OBJECT_DELETE, "objectDelete") \
    X(OBJECT_ASSIGN, "objectAssign") X(OBJECT_COPY, "objectCopy") X(SYSTEM_BOOLEAN, "systemBoolean") \
    X(MATH_ABS, "mathAbs") X(MATH_CEIL, "mathCeil") X(SYSTEM_GLOBAL_GET, "systemGlobalGet") \
    X(SYSTEM_GLOBAL_SET, "systemGlobalSet") X(REGEX_REPLACE, "regexReplace") X(REGEX_ESCAPE, "regexEscape") \
    X(ARRAY_NEW_SIZE, "arrayNewSize") X(NUMBER_TO_STRING, "numberToString") X(JSON_PARSE, "jsonParse") \
    X(JSON_STRINGIFY, "jsonStringify")

#define BS_INTRINSIC_ENUM(id, name) IN_##id,
enum { IN_NONE = 0, BS_INTRINSICS(BS_INTRINSIC_ENUM) IN_COUNT };

// The first library function replica
#define IN_LIBRARY IN_OBJECT_NEW

#define BS_INTRINSIC_NAME(id, name) name,
static const char *const intrinsic_names[] = { NULL, BS_INTRINSICS(BS_INTRINSIC_NAME) };

static PyObject *g_intrinsic_names[IN_COUNT];   // interned
static PyObject *g_intrinsic_fns[IN_COUNT];     // the library function objects


// Is a function one of runtime.py's library intrinsic functions?
static int is_intrinsic_fn(PyObject *func)
{
    for (int id = 1; id < IN_LIBRARY; id++) {
        if (func == g_intrinsic_fns[id]) {
            return 1;
        }
    }
    return 0;
}


// Get an attribute of the runtime module (a new reference)
static PyObject *runtime_attr(const char *name)
{
    return PyObject_GetAttrString(g_runtime, name);
}


// Call a runtime module function with its arguments (a NULL-terminated list) - a new reference
static PyObject *runtime_call(const char *name, ...)
{
    PyObject *func = runtime_attr(name);
    if (func == NULL) {
        return NULL;
    }
    PyObject *args[6];
    size_t nargs = 0;
    va_list vargs;
    va_start(vargs, name);
    for (PyObject *arg = va_arg(vargs, PyObject *); arg != NULL && nargs < 6; arg = va_arg(vargs, PyObject *)) {
        args[nargs++] = arg;
    }
    va_end(vargs);
    PyObject *result = PyObject_Vectorcall(func, args, nargs, NULL);
    Py_DECREF(func);
    return result;
}


// Get a mapping value as the Python "value.get(key)" - a new reference to the value, or to None if absent
static PyObject *object_get(PyObject *object, PyObject *key)
{
    if (PyDict_CheckExact(object)) {
        PyObject *value;
        int found = bs_dict_get(object, key, &value);
        return found < 0 ? NULL : (found ? value : Py_NewRef(Py_None));
    }
    return PyObject_CallMethodObjArgs(object, S_get, key, NULL);
}


// Create a list from an argument array
static PyObject *list_new(PyObject *const *items, Py_ssize_t count)
{
    PyObject *list = PyList_New(count);
    if (list != NULL) {
        for (Py_ssize_t ix = 0; ix < count; ix++) {
            PyList_SET_ITEM(list, ix, Py_NewRef(items[ix]));
        }
    }
    return list;
}


//
// Errors
//


// Raise a BareScriptRuntimeError for a script statement (steals the message reference)
static void raise_runtime_error(PyObject *script, PyObject *statement, PyObject *message)
{
    if (message == NULL) {
        return;
    }
    PyObject *exc = PyObject_CallFunctionObjArgs(g_BareScriptRuntimeError, script != NULL ? script : Py_None,
                                                 statement != NULL ? statement : Py_None, message, NULL);
    Py_DECREF(message);
    if (exc != NULL) {
        PyErr_SetObject((PyObject *)Py_TYPE(exc), exc);
        Py_DECREF(exc);
    }
}


//
// Value helpers - value.py's value_boolean, value_string, value_compare, and value_type
//


// value_boolean - 1 true, 0 false, -1 error
static int value_boolean(PyObject *value)
{
    if (value == Py_True) {
        return 1;
    }
    if (value == Py_False || value == Py_None) {
        return 0;
    }
    if (PyUnicode_CheckExact(value)) {
        return PyUnicode_GET_LENGTH(value) != 0;
    }
    if (PyFloat_CheckExact(value)) {
        return PyFloat_AS_DOUBLE(value) != 0.0;
    }
    if (PyLong_CheckExact(value)) {
        return PyObject_IsTrue(value);
    }
    if (PyUnicode_Check(value)) {
        return PyObject_RichCompareBool(value, S_empty, Py_NE);
    }
    if (PyLong_Check(value) || PyFloat_Check(value)) {
        return PyObject_RichCompareBool(value, g_zero, Py_NE);
    }
    if (PyList_Check(value)) {
        Py_ssize_t length = PyObject_Length(value);
        return length < 0 ? -1 : length != 0;
    }
    return 1;
}


// An integer's digits in a radix (2 to 36), as a string
static PyObject *digits_string(unsigned long long magnitude, int negative, int radix)
{
    static const char digits[] = "0123456789abcdefghijklmnopqrstuvwxyz";
    char text[72];
    int ix = (int)sizeof(text);
    do {
        text[--ix] = digits[magnitude % (unsigned)radix];
        magnitude /= (unsigned)radix;
    } while (magnitude > 0);
    if (negative) {
        text[--ix] = '-';
    }
    return PyUnicode_FromStringAndSize(text + ix, (Py_ssize_t)sizeof(text) - ix);
}


// value_string - a new reference
static PyObject *value_string(PyObject *value)
{
    if (PyUnicode_CheckExact(value)) {
        return Py_NewRef(value);
    }
    if (value == Py_None) {
        return Py_NewRef(S_null);
    }
    if (value == Py_True) {
        return Py_NewRef(S_true);
    }
    if (value == Py_False) {
        return Py_NewRef(S_false);
    }
    if (PyLong_CheckExact(value)) {
        return PyObject_Str(value);
    }
    if (PyFloat_CheckExact(value)) {
        // An integral float a double represents with every smaller integer formats as the integer
        double number = PyFloat_AS_DOUBLE(value);
        if (floor(number) == number && fabs(number) < 9007199254740992.0) {
            return digits_string((unsigned long long)fabs(number), number < 0, 10);
        }
    }
    return PyObject_CallOneArg(g_value_string, value);
}


// value_type - a borrowed reference to the type name, or None for an unknown type
static PyObject *value_type(PyObject *value)
{
    if (value == Py_None) {
        return S_t_null;
    }
    if (PyUnicode_Check(value)) {
        return S_t_string;
    }
    if (PyBool_Check(value)) {
        return S_t_boolean;
    }
    if (PyLong_Check(value) || PyFloat_Check(value)) {
        return S_t_number;
    }
    if (PyDate_Check(value)) {
        return S_t_datetime;
    }
    if (PyDict_Check(value)) {
        return S_t_object;
    }
    if (PyList_Check(value)) {
        return S_t_array;
    }
    if (PyCallable_Check(value)) {
        return S_t_function;
    }
    if (PyObject_TypeCheck(value, (PyTypeObject *)g_REGEX_TYPE)) {
        return S_t_regex;
    }
    return Py_None;
}


//
// Operators - runtime.py's binary and unary expression semantics
//


// Is the value a number to the operators - an exact int or float (bool and subclasses are not)?
#define IS_NUMBER(value) (PyFloat_CheckExact(value) || PyLong_CheckExact(value))

// The largest integer magnitude every smaller integer of which a double represents exactly
#define BS_EXACT_INT_MAX 9007199254740992LL


// Get an exact int's value - 1 if it fits in a long long, 0 otherwise
static inline int small_int(PyObject *value, long long *result)
{
    int overflow;
    *result = PyLong_AsLongLongAndOverflow(value, &overflow);
    return !overflow;
}


// A number operand as a double (an exact int or float) - -1 on error (an int too large for a float)
static inline int number_double(PyObject *value, double *result)
{
    if (PyFloat_CheckExact(value)) {
        *result = PyFloat_AS_DOUBLE(value);
        return 0;
    }
    *result = PyLong_AsDouble(value);
    return *result == -1.0 && PyErr_Occurred() ? -1 : 0;
}


// runtime.py's _arithmetic_result - non-finite numbers (including out-of-double-range integers and complex
// results) are invalid operation values. Steals the result reference.
static PyObject *arithmetic_result(PyObject *result)
{
    if (result == NULL) {
        return NULL;
    }
    if (PyFloat_CheckExact(result)) {
        if (isfinite(PyFloat_AS_DOUBLE(result))) {
            return result;
        }
    } else if (PyLong_CheckExact(result)) {
        long long small;
        if (small_int(result, &small)) {
            return result;
        }
        int in_range = PyObject_RichCompareBool(result, g_dbl_max, Py_LE);
        if (in_range > 0) {
            in_range = PyObject_RichCompareBool(result, g_dbl_max_neg, Py_GE);
        }
        if (in_range < 0) {
            Py_DECREF(result);
            return NULL;
        }
        if (in_range) {
            return result;
        }
    }
    Py_DECREF(result);
    return Py_NewRef(Py_None);
}


// A finite double as a float, or None
static inline PyObject *float_result(double value)
{
    return isfinite(value) ? PyFloat_FromDouble(value) : Py_NewRef(Py_None);
}


// Numeric +, -, and * of two number operands
static PyObject *number_arith(int op, PyObject *left, PyObject *right)
{
    if (PyLong_CheckExact(left) && PyLong_CheckExact(right)) {
        long long left_int, right_int, result;
        if (small_int(left, &left_int) && small_int(right, &right_int)) {
            int overflow = op == '+' ? __builtin_add_overflow(left_int, right_int, &result) :
                (op == '-' ? __builtin_sub_overflow(left_int, right_int, &result) :
                 __builtin_mul_overflow(left_int, right_int, &result));
            if (!overflow) {
                return PyLong_FromLongLong(result);
            }
        }
        return arithmetic_result(op == '+' ? PyNumber_Add(left, right) :
                                 (op == '-' ? PyNumber_Subtract(left, right) : PyNumber_Multiply(left, right)));
    }
    double left_num, right_num;
    if (number_double(left, &left_num) < 0 || number_double(right, &right_num) < 0) {
        return NULL;
    }
    return float_result(op == '+' ? left_num + right_num : (op == '-' ? left_num - right_num : left_num * right_num));
}


// Datetime + number (milliseconds) - None on overflow
static PyObject *datetime_add(PyObject *datetime_value, PyObject *milliseconds)
{
    PyObject *datetime_norm = PyObject_CallOneArg(g_value_normalize_datetime, datetime_value);
    if (datetime_norm == NULL) {
        return NULL;
    }
    PyObject *result = NULL;
    PyObject *args = PyTuple_New(0);
    PyObject *kwargs = Py_BuildValue("{OO}", S_milliseconds, milliseconds);
    if (args != NULL && kwargs != NULL) {
        PyObject *delta = PyObject_Call(g_timedelta, args, kwargs);
        if (delta != NULL) {
            result = PyNumber_Add(datetime_norm, delta);
            Py_DECREF(delta);
        }
        if (result == NULL && PyErr_ExceptionMatches(PyExc_OverflowError)) {
            PyErr_Clear();
            result = Py_NewRef(Py_None);
        }
    }
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    Py_DECREF(datetime_norm);
    return result;
}


// Datetime - datetime (milliseconds)
static PyObject *datetime_sub(PyObject *left, PyObject *right)
{
    PyObject *left_dt = PyObject_CallOneArg(g_value_normalize_datetime, left);
    PyObject *right_dt = left_dt != NULL ? PyObject_CallOneArg(g_value_normalize_datetime, right) : NULL;
    PyObject *delta = right_dt != NULL ? PyNumber_Subtract(left_dt, right_dt) : NULL;
    PyObject *seconds = delta != NULL ? PyObject_CallMethodNoArgs(delta, S_total_seconds) : NULL;
    PyObject *ms = seconds != NULL ? PyNumber_Multiply(seconds, g_thousand) : NULL;
    PyObject *result = ms != NULL ? PyObject_CallFunctionObjArgs(g_value_round_number, ms, g_zero, NULL) : NULL;
    Py_XDECREF(left_dt);
    Py_XDECREF(right_dt);
    Py_XDECREF(delta);
    Py_XDECREF(seconds);
    Py_XDECREF(ms);
    return result;
}


// Binary +
static PyObject *op_add(PyObject *left, PyObject *right)
{
    int left_number = IS_NUMBER(left), right_number = IS_NUMBER(right);
    if (left_number && right_number) {
        return number_arith('+', left, right);
    }
    int left_string = PyUnicode_CheckExact(left), right_string = PyUnicode_CheckExact(right);
    if (left_string && right_string) {
        return PyUnicode_Concat(left, right);
    }
    if (left_string || right_string) {
        PyObject *string = value_string(left_string ? right : left);
        if (string == NULL) {
            return NULL;
        }
        PyObject *result = left_string ? PyNumber_Add(left, string) : PyNumber_Add(string, right);
        Py_DECREF(string);
        return result;
    }
    if (right_number && PyDate_Check(left)) {
        return datetime_add(left, right);
    }
    if (left_number && PyDate_Check(right)) {
        return datetime_add(right, left);
    }
    return Py_NewRef(Py_None);
}


// Binary -
static PyObject *op_sub(PyObject *left, PyObject *right)
{
    if (IS_NUMBER(left) && IS_NUMBER(right)) {
        return number_arith('-', left, right);
    }
    if (PyDate_Check(left) && PyDate_Check(right)) {
        return datetime_sub(left, right);
    }
    return Py_NewRef(Py_None);
}


// Binary *
static PyObject *op_mul(PyObject *left, PyObject *right)
{
    return IS_NUMBER(left) && IS_NUMBER(right) ? number_arith('*', left, right) : Py_NewRef(Py_None);
}


// Binary / - None on division by zero
static PyObject *op_div(PyObject *left, PyObject *right)
{
    if (!IS_NUMBER(left) || !IS_NUMBER(right)) {
        return Py_NewRef(Py_None);
    }
    if (PyLong_CheckExact(left) && PyLong_CheckExact(right)) {
        // Integers a double represents exactly divide as doubles, as Python's int true division does
        long long left_int, right_int;
        if (small_int(left, &left_int) && small_int(right, &right_int) &&
            left_int <= BS_EXACT_INT_MAX && left_int >= -BS_EXACT_INT_MAX &&
            right_int <= BS_EXACT_INT_MAX && right_int >= -BS_EXACT_INT_MAX) {
            return right_int != 0 ? float_result((double)left_int / (double)right_int) : Py_NewRef(Py_None);
        }
        PyObject *result = PyNumber_TrueDivide(left, right);
        if (result == NULL && PyErr_ExceptionMatches(PyExc_ZeroDivisionError)) {
            PyErr_Clear();
            return Py_NewRef(Py_None);
        }
        return arithmetic_result(result);
    }
    double left_num, right_num;
    if (number_double(left, &left_num) < 0 || number_double(right, &right_num) < 0) {
        return NULL;
    }
    return right_num != 0.0 ? float_result(left_num / right_num) : Py_NewRef(Py_None);
}


// Binary % - the remainder has the dividend's sign (math.fmod), as in JavaScript
static PyObject *op_mod(PyObject *left, PyObject *right)
{
    if (!IS_NUMBER(left) || !IS_NUMBER(right)) {
        return Py_NewRef(Py_None);
    }
    double left_num, right_num;
    if (number_double(left, &left_num) < 0 || number_double(right, &right_num) < 0) {
        if (PyErr_ExceptionMatches(PyExc_OverflowError)) {
            PyErr_Clear();
            return Py_NewRef(Py_None);
        }
        return NULL;
    }

    // math.fmod - fmod(x, +/-inf) is x for finite x; a NaN result from non-NaN operands is a domain error
    double result;
    if (isinf(right_num) && isfinite(left_num)) {
        result = left_num;
    } else {
        result = fmod(left_num, right_num);
        if (isnan(result) && !isnan(left_num) && !isnan(right_num)) {
            return Py_NewRef(Py_None);
        }
    }

    // Adding zero turns fmod's negative zero (a negative dividend's zero remainder) into zero
    result = result + 0.0;
    if (PyLong_CheckExact(left) && PyLong_CheckExact(right)) {
        return arithmetic_result(PyLong_FromDouble(result));
    }
    return float_result(result);
}


// Binary ** - None on overflow and division by zero
static PyObject *op_pow(PyObject *left, PyObject *right)
{
    if (!IS_NUMBER(left) || !IS_NUMBER(right)) {
        return Py_NewRef(Py_None);
    }
    PyObject *result = PyNumber_Power(left, right, Py_None);
    if (result == NULL && (PyErr_ExceptionMatches(PyExc_OverflowError) ||
                           PyErr_ExceptionMatches(PyExc_ZeroDivisionError))) {
        PyErr_Clear();
        return Py_NewRef(Py_None);
    }
    return arithmetic_result(result);
}


// Compare two number operands with a Python rich comparison - 1 true, 0 false, -1 error
static int number_compare(PyObject *left, PyObject *right, int op)
{
    double left_num, right_num;
    long long left_int, right_int;
    int left_exact, right_exact;
    if (PyFloat_CheckExact(left)) {
        left_num = PyFloat_AS_DOUBLE(left);
        left_exact = 1;
    } else {
        left_exact = small_int(left, &left_int);
        left_num = (double)left_int;
        if (left_exact && PyLong_CheckExact(right) && small_int(right, &right_int)) {
            switch (op) {
            case Py_LT: return left_int < right_int;
            case Py_LE: return left_int <= right_int;
            case Py_GT: return left_int > right_int;
            case Py_GE: return left_int >= right_int;
            case Py_EQ: return left_int == right_int;
            default: return left_int != right_int;
            }
        }
        left_exact = left_exact && left_int <= BS_EXACT_INT_MAX && left_int >= -BS_EXACT_INT_MAX;
    }
    if (PyFloat_CheckExact(right)) {
        right_num = PyFloat_AS_DOUBLE(right);
        right_exact = 1;
    } else {
        right_exact = small_int(right, &right_int) && right_int <= BS_EXACT_INT_MAX && right_int >= -BS_EXACT_INT_MAX;
        right_num = (double)right_int;
    }
    if (!left_exact || !right_exact) {
        return PyObject_RichCompareBool(left, right, op);
    }
    switch (op) {
    case Py_LT: return left_num < right_num;
    case Py_LE: return left_num <= right_num;
    case Py_GT: return left_num > right_num;
    case Py_GE: return left_num >= right_num;
    case Py_EQ: return left_num == right_num;
    default: return left_num != right_num;
    }
}


// value.py's value_compare - sets *result to -1, 0, or 1; returns -1 on error. Exact types compare here; subclasses,
// datetimes, and objects compare with value.py's.
enum { KIND_STRING, KIND_BOOLEAN, KIND_NUMBER, KIND_DATETIME, KIND_ARRAY, KIND_OBJECT, KIND_OTHER };

static int value_kind(PyObject *value)
{
    return PyUnicode_Check(value) ? KIND_STRING : (PyBool_Check(value) ? KIND_BOOLEAN :
        (PyLong_Check(value) || PyFloat_Check(value) ? KIND_NUMBER : (PyDate_Check(value) ? KIND_DATETIME :
        (PyList_Check(value) ? KIND_ARRAY : (PyDict_Check(value) ? KIND_OBJECT : KIND_OTHER)))));
}

static int value_compare(PyObject *left, PyObject *right, int *result)
{
    if (left == Py_None || right == Py_None) {
        *result = left == right ? 0 : (left == Py_None ? -1 : 1);
        return 0;
    }
    int kind = value_kind(left), cmp;
    if (kind != value_kind(right) || kind == KIND_OTHER) {
        // Invalid comparison - compare by type name
        PyObject *left_type = value_type(left), *right_type = value_type(right);
        cmp = PyUnicode_Compare(left_type != Py_None ? left_type : S_unknown, right_type != Py_None ? right_type : S_unknown);
    } else if (kind == KIND_BOOLEAN) {
        cmp = (left == Py_True) - (right == Py_True);
    } else if (kind == KIND_STRING && PyUnicode_CheckExact(left) && PyUnicode_CheckExact(right)) {
        cmp = left == right ? 0 : PyUnicode_Compare(left, right);
    } else if (kind == KIND_NUMBER && IS_NUMBER(left) && IS_NUMBER(right)) {
        int less = number_compare(left, right, Py_LT);
        int equal = less == 0 ? number_compare(left, right, Py_EQ) : 0;
        if (less < 0 || equal < 0) {
            return -1;
        }
        cmp = less ? -1 : !equal;
    } else if (kind == KIND_ARRAY && PyList_CheckExact(left) && PyList_CheckExact(right)) {
        Py_ssize_t count = Py_MIN(PyList_GET_SIZE(left), PyList_GET_SIZE(right));
        if (Py_EnterRecursiveCall(" in comparison") < 0) {
            return -1;
        }
        cmp = 0;
        for (Py_ssize_t ix = 0; cmp == 0 && ix < count; ix++) {
            PyObject *left_item = bs_list_get(left, ix);
            PyObject *right_item = left_item != NULL ? bs_list_get(right, ix) : NULL;
            int rc = right_item != NULL ? value_compare(left_item, right_item, &cmp) : -1;
            Py_XDECREF(left_item);
            Py_XDECREF(right_item);
            if (rc < 0) {
                Py_LeaveRecursiveCall();
                return -1;
            }
        }
        Py_LeaveRecursiveCall();
        if (cmp == 0) {
            Py_ssize_t left_size = PyList_GET_SIZE(left), right_size = PyList_GET_SIZE(right);
            cmp = left_size < right_size ? -1 : (left_size == right_size ? 0 : 1);
        }
    } else {
        PyObject *value = PyObject_CallFunctionObjArgs(g_value_compare, left, right, NULL);
        long number = value != NULL ? PyLong_AsLong(value) : -1;
        Py_XDECREF(value);
        if (number == -1 && PyErr_Occurred()) {
            return -1;
        }
        cmp = (int)number;
    }
    if (cmp == -1 && PyErr_Occurred()) {
        return -1;
    }
    *result = cmp < 0 ? -1 : (cmp > 0 ? 1 : 0);
    return 0;
}


// Compare two values for a comparison operator - 1 true, 0 false, -1 error. Numbers compare as Python numbers,
// strings for == and != as strings, and anything else with value_compare.
static int compare_truth(int op, PyObject *left, PyObject *right)
{
    if (IS_NUMBER(left) && IS_NUMBER(right)) {
        return number_compare(left, right, op);
    }
    if ((op == Py_EQ || op == Py_NE) && PyUnicode_CheckExact(left) && PyUnicode_CheckExact(right)) {
        return PyObject_RichCompareBool(left, right, op);
    }
    int cmp;
    if (value_compare(left, right, &cmp) < 0) {
        return -1;
    }
    switch (op) {
    case Py_LT: return cmp < 0;
    case Py_LE: return cmp <= 0;
    case Py_GT: return cmp > 0;
    case Py_GE: return cmp >= 0;
    case Py_EQ: return cmp == 0;
    default: return cmp != 0;
    }
}


// Binary <, <=, >, >=, ==, and !=
static PyObject *op_compare(int op, PyObject *left, PyObject *right)
{
    int truth = compare_truth(op, left, right);
    return truth < 0 ? NULL : PyBool_FromLong(truth);
}


// A bitwise operand's integer - an exact int, or an exact integral float, as a new int reference; NULL with no
// error for any other value
static PyObject *bitwise_int(PyObject *value)
{
    if (PyLong_CheckExact(value)) {
        return Py_NewRef(value);
    }
    if (PyFloat_CheckExact(value)) {
        double number = PyFloat_AS_DOUBLE(value);
        if (isfinite(number) && floor(number) == number) {
            return PyLong_FromDouble(number);
        }
    }
    return NULL;
}


// Binary &, |, ^, <<, and >> (the op is the operator's first character, '>' for >>)
static PyObject *op_bitwise(int op, PyObject *left, PyObject *right)
{
    long long left_int, right_int;
    if (PyLong_CheckExact(left) && PyLong_CheckExact(right) && small_int(left, &left_int) &&
        small_int(right, &right_int)) {
        switch (op) {
        case '&': return PyLong_FromLongLong(left_int & right_int);
        case '|': return PyLong_FromLongLong(left_int | right_int);
        case '^': return PyLong_FromLongLong(left_int ^ right_int);
        case '<':
            if (right_int >= 0 && right_int < 63 &&
                (left_int >= 0 ? left_int <= (LLONG_MAX >> right_int) : left_int >= (LLONG_MIN >> right_int))) {
                return PyLong_FromLongLong(left_int * (1LL << right_int));
            }
            break;
        default:
            if (right_int >= 0) {
                return PyLong_FromLongLong(left_int >> (right_int < 63 ? right_int : 63));
            }
            break;
        }
    }
    PyObject *left_value = bitwise_int(left);
    if (left_value == NULL) {
        return PyErr_Occurred() ? NULL : Py_NewRef(Py_None);
    }
    PyObject *right_value = bitwise_int(right);
    if (right_value == NULL) {
        Py_DECREF(left_value);
        return PyErr_Occurred() ? NULL : Py_NewRef(Py_None);
    }
    PyObject *result;
    switch (op) {
    case '&': result = PyNumber_And(left_value, right_value); break;
    case '|': result = PyNumber_Or(left_value, right_value); break;
    case '^': result = PyNumber_Xor(left_value, right_value); break;
    case '<': result = PyNumber_Lshift(left_value, right_value); break;
    default: result = PyNumber_Rshift(left_value, right_value); break;
    }
    Py_DECREF(left_value);
    Py_DECREF(right_value);
    return result;
}


// Unary -
static PyObject *op_neg(PyObject *value)
{
    if (PyFloat_CheckExact(value)) {
        return PyFloat_FromDouble(-PyFloat_AS_DOUBLE(value));
    }
    return PyLong_CheckExact(value) ? PyNumber_Negative(value) : Py_NewRef(Py_None);
}


// Unary ~
static PyObject *op_bnot(PyObject *value)
{
    PyObject *int_value = bitwise_int(value);
    if (int_value == NULL) {
        return PyErr_Occurred() ? NULL : Py_NewRef(Py_None);
    }
    PyObject *result = PyNumber_Invert(int_value);
    Py_DECREF(int_value);
    return result;
}


//
// Bytecode
//


// The instructions - a is the destination register (or an index), b and c are operand registers (or indexes),
// w (overlaying b and c) is a jump target or a statement index
#define BS_OPS(X) \
    X(STMT)     /* statement w begins - count it against the limit, and record its coverage */ \
    X(MOVE)     /* a = b */ \
    X(LOADG)    /* a = the global named b */ \
    X(LOADS)    /* a = slot b, or the global of its name if the slot is unassigned */ \
    X(LOADN)    /* a = the local (evaluate_expression's locals) or global named b */ \
    X(STOREG)   /* the global named a = b */ \
    X(JMP)      /* jump to w - a label jump when x is set */ \
    X(JF)       /* jump to w if a is false */ \
    X(JT)       /* jump to w if a is true - a label jump when x is set */ \
    X(JUNDEF)   /* the unknown jump label error for the label named a */ \
    X(RET)      /* return a */ \
    X(RETNONE)  /* return None */ \
    X(ADD) X(SUB) X(MUL) X(DIV) X(MOD) X(POW) X(EQ) X(NE) X(LT) X(LE) X(GT) X(GE) \
    X(BAND) X(BOR) X(BXOR) X(SHL) X(SHR)   /* a = b op c */ \
    X(NOT) X(NEG) X(BNOT)                  /* a = op b */ \
    X(CALLG)    /* a = the global function named b called with the c (ARGS_NONE for none) arguments in the DATA words that follow; x is the name's intrinsic */ \
    X(CALLS)    /* the same, calling the function in slot b, or the global of its name if the slot is unassigned */ \
    X(CALLN)    /* the same, calling the local, global, or built-in function named b */ \
    X(FUNC)     /* define the script function model b as the global named a */ \
    X(JEQ) X(JNE) X(JLT) X(JLE) X(JGT) X(JGE)   /* jump to the JTARGET word's w if a op b (if not, when x has JUMP_NOT) - EQ's order */ \
    X(JTARGET)  /* a compare-and-jump's target - never dispatched */ \
    X(INCLUDE)  /* run statement w's includes */ \
    X(DATA)     /* call argument registers a, b, and c - never dispatched */

#define BS_OP_ENUM(name) OP_##name,
enum { BS_OPS(BS_OP_ENUM) OP_COUNT };

typedef struct {
    uint8_t op;
    uint8_t x;
    uint16_t a;
    union {
        struct {
            uint16_t b;
            uint16_t c;
        };
        uint32_t w;
    };
} Inst;

// The register operand fields of each instruction
enum { RA = 1, RB = 2, RC = 4 };

static int op_registers(int op)
{
    switch (op) {
    case OP_MOVE: case OP_LOADS: case OP_NOT: case OP_NEG: case OP_BNOT: case OP_CALLS:
    case OP_JEQ: case OP_JNE: case OP_JLT: case OP_JLE: case OP_JGT: case OP_JGE:
        return RA | RB;
    case OP_LOADG: case OP_LOADN: case OP_JF: case OP_JT: case OP_RET: case OP_CALLG: case OP_CALLN:
        return RA;
    case OP_STOREG: case OP_FUNC:
        return RB;
    case OP_STMT: case OP_JMP: case OP_JUNDEF: case OP_RETNONE: case OP_INCLUDE: case OP_JTARGET:
        return 0;
    default:
        return RA | RB | RC;
    }
}

// Jump instruction flags - a label jump (recording the label's coverage), and a compare-and-jump on false
#define JUMP_LABEL 1
#define JUMP_NOT 2

// The call argument count of a call without arguments (the model's "args" absent or null)
#define ARGS_NONE 0xFFFF

// The number of DATA words following a call instruction
#define CALL_DATA(count) ((count) == ARGS_NONE ? 0 : ((count) + 2) / 3)


// A compiled statement list or expression. Its registers are the slots (a function's local variables), then the
// temporaries, then the constants.
typedef struct {
    Inst *code;
    uint32_t *pcstmt;           // each instruction's statement index
    PyObject **consts;
    PyObject **names;           // interned global names
    PyObject **slot_names;      // interned local variable names
    uint16_t *arg_slots;        // each declared argument's slot
    PyObject **arg_items;       // the function model's "args" items when compiled
    PyObject *args;             // the function model's "args" list when compiled, or NULL
    PyObject *statements;       // the statements list (NULL for an expression)
    PyObject *script;           // the script model (NULL for an expression)
    Py_ssize_t nstatements;
    int nconsts;
    int nnames;
    int nslots;
    int nowned;                 // the slots and temporaries - the registers a frame owns
    int nargs;
    int last_arg_array;
    int last_arg_array_plain;   // the model's lastArgArray is absent, None, or a bool - its truth can't change
    int irregular;              // the model is not compiled - run it on runtime.py
    int model_watched;          // the function model dict is watched (model_epoch is valid)
    BS_ATOMIC_U64 model_epoch;  // the model epoch when the function model dict was last known current
    BS_ATOMIC_PTR(PyObject *) resident; // a function's resident registers, from its second call
    BS_ATOMIC_INT resident_busy;        // a call is using the resident registers
    BS_ATOMIC_INT called;       // the function has been called
} Chunk;


// Release an array of references (some possibly NULL) and free it
static void references_free(PyObject **items, int count)
{
    for (int ix = 0; ix < count; ix++) {
        Py_XDECREF(items[ix]);
    }
    PyMem_Free(items);
}


static void chunk_free(Chunk *chunk)
{
    if (chunk == NULL) {
        return;
    }
    references_free(chunk->consts, chunk->nconsts);
    references_free(chunk->names, chunk->nnames);
    references_free(chunk->slot_names, chunk->nslots);
    references_free(chunk->arg_items, chunk->nargs);
    Py_XDECREF(chunk->args);
    Py_XDECREF(chunk->statements);
    Py_XDECREF(chunk->script);
    PyMem_Free(bs_atomic_load(&chunk->resident));
    PyMem_Free(chunk->code);
    PyMem_Free(chunk->pcstmt);
    PyMem_Free(chunk->arg_slots);
    PyMem_Free(chunk);
}


//
// The compiler
//


enum { MODE_TOP, MODE_FUNC, MODE_EXPR };

// Register operand tags while compiling - the temporaries and constants are numbered once all are counted
#define REG_TEMP 0x4000
#define REG_CONST 0x8000
#define REG_MAX 0x3FFF

// The maximum expression nesting compiled - deeper expressions run on runtime.py
#define DEPTH_MAX 200


typedef struct {
    int mode;
    Inst *code;
    uint32_t *pcstmt;
    int ncode;
    int capcode;
    PyObject *consts;           // list
    PyObject *names;            // list
    PyObject *name_index;       // dict of name to index in names
    PyObject *slots;            // dict of local variable name to slot (MODE_FUNC)
    PyObject *slot_names;       // list
    int nargslots;              // the leading slots that are arguments - always assigned
    uint64_t *definite;         // the slots definitely assigned when the statement being compiled begins
    PyObject *labels;           // dict of label name to statement index
    PyObject *keep;             // list of the model objects read, kept alive while compiling
    int *fixups;                // label jump fixups - (pc, label statement index) pairs
    int nfixups;
    int capfixups;
    int tmp;
    int tmpmax;
    uint32_t stmt;
    int depth;
    int result_pc;              // the instruction computing the last expression's result, or -1
    int reg_none;
    int reg_false;
    int reg_true;
} Compiler;


static int c_irregular(Compiler *c)
{
    (void)c;
    return -1;
}


// Get a model dict's value (kept alive by the compiler) - 1 found, 0 absent, -1 error
static int c_get(Compiler *c, PyObject *dict, PyObject *key, PyObject **value)
{
    int found = bs_dict_get(dict, key, value);
    if (found > 0) {
        int rc = PyList_Append(c->keep, *value);
        Py_DECREF(*value);
        if (rc < 0) {
            return -1;
        }
    }
    return found;
}


// Get a model list's item (kept alive by the compiler)
static PyObject *c_item(Compiler *c, PyObject *list, Py_ssize_t index)
{
    PyObject *item = bs_list_get(list, index);
    if (item != NULL) {
        int rc = PyList_Append(c->keep, item);
        Py_DECREF(item);
        if (rc < 0) {
            return NULL;
        }
    }
    return item;
}


static int c_emit(Compiler *c, int op, int a, int b, int cc)
{
    if (c->ncode == c->capcode) {
        int capcode = c->capcode ? c->capcode * 2 : 64;
        Inst *code = PyMem_Realloc(c->code, capcode * sizeof(Inst));
        if (code != NULL) {
            c->code = code;
        }
        uint32_t *pcstmt = code != NULL ? PyMem_Realloc(c->pcstmt, capcode * sizeof(uint32_t)) : NULL;
        if (pcstmt == NULL) {
            PyErr_NoMemory();
            return -1;
        }
        c->pcstmt = pcstmt;
        c->capcode = capcode;
    }
    Inst *inst = &c->code[c->ncode];
    inst->op = (uint8_t)op;
    inst->x = 0;
    inst->a = (uint16_t)a;
    inst->b = (uint16_t)b;
    inst->c = (uint16_t)cc;
    c->pcstmt[c->ncode] = c->stmt;
    return c->ncode++;
}


static int c_temp(Compiler *c)
{
    if (c->tmp > REG_MAX) {
        return c_irregular(c);
    }
    int reg = REG_TEMP | c->tmp++;
    if (c->tmp > c->tmpmax) {
        c->tmpmax = c->tmp;
    }
    return reg;
}


// Emit an instruction computing a new temporary, the temporaries first reset to a mark - the temporary, or -1
static int c_emit_temp(Compiler *c, int mark, int op, int b, int cc)
{
    c->tmp = mark;
    int reg = c_temp(c);
    int pc = reg >= 0 ? c_emit(c, op, reg, b, cc) : -1;
    if (pc < 0) {
        return -1;
    }
    c->result_pc = pc;
    return reg;
}


// Reset the temporaries to those below a register (if it's a temporary) and itself
static void c_temp_reset(Compiler *c, int reg)
{
    c->tmp = (reg & REG_TEMP) ? (reg & REG_MAX) + 1 : 0;
}


static int c_const(Compiler *c, PyObject *value)
{
    Py_ssize_t index = PyList_GET_SIZE(c->consts);
    if (index > REG_MAX) {
        return c_irregular(c);
    }
    if (PyList_Append(c->consts, value) < 0) {
        return -1;
    }
    return REG_CONST | (int)index;
}


static int c_keyword(Compiler *c, PyObject *value)
{
    int *reg = value == Py_None ? &c->reg_none : (value == Py_False ? &c->reg_false : &c->reg_true);
    if (*reg < 0) {
        *reg = c_const(c, value);
    }
    return *reg;
}


// Get a name's index in a name table - a list and its dict of name to index - adding it (interned) if necessary
static int c_table_index(Compiler *c, PyObject *names, PyObject *indexes, PyObject *name, Py_ssize_t max)
{
    PyObject *index = PyDict_GetItemWithError(indexes, name);
    if (index != NULL) {
        return (int)PyLong_AsLong(index);
    }
    if (PyErr_Occurred()) {
        return -1;
    }
    Py_ssize_t count = PyList_GET_SIZE(names);
    if (count > max) {
        return c_irregular(c);
    }
    PyObject *interned = Py_NewRef(name);
    PyUnicode_InternInPlace(&interned);
    PyObject *index_obj = PyLong_FromSsize_t(count);
    int rc = index_obj != NULL && PyList_Append(names, interned) == 0 &&
        PyDict_SetItem(indexes, interned, index_obj) == 0 ? 0 : -1;
    Py_DECREF(interned);
    Py_XDECREF(index_obj);
    return rc < 0 ? -1 : (int)count;
}


// Get a global name's index in the names table, adding it if necessary
static int c_name(Compiler *c, PyObject *name)
{
    return c_table_index(c, c->names, c->name_index, name, 0xFFFF);
}


// Get a local variable's slot - -1 if not a local variable
static int c_slot(Compiler *c, PyObject *name)
{
    if (c->mode != MODE_FUNC) {
        return -1;
    }
    PyObject *slot = PyDict_GetItemWithError(c->slots, name);
    return slot != NULL ? (int)PyLong_AsLong(slot) : -1;
}


// Get a local variable's slot, adding it if necessary
static int c_slot_add(Compiler *c, PyObject *name)
{
    return c_table_index(c, c->slot_names, c->slots, name, REG_MAX);
}


// Get a name's intrinsic
static int c_intrinsic(PyObject *name)
{
    for (int id = 1; id < IN_COUNT; id++) {
        if (PyUnicode_Compare(name, g_intrinsic_names[id]) == 0) {
            return id;
        }
    }
    return IN_NONE;
}


static int c_expr(Compiler *c, PyObject *expr);


static int c_variable(Compiler *c, PyObject *name)
{
    if (!PyUnicode_CheckExact(name)) {
        return c_irregular(c);
    }
    if (PyUnicode_CompareWithASCIIString(name, "null") == 0) {
        return c_keyword(c, Py_None);
    }
    if (PyUnicode_CompareWithASCIIString(name, "false") == 0) {
        return c_keyword(c, Py_False);
    }
    if (PyUnicode_CompareWithASCIIString(name, "true") == 0) {
        return c_keyword(c, Py_True);
    }
    int slot = c_slot(c, name);
    if (slot >= 0 && (slot < c->nargslots || (c->definite != NULL && ((c->definite[slot / 64] >> (slot % 64)) & 1)))) {
        return slot;
    }
    int index = slot >= 0 ? slot : (PyErr_Occurred() ? -1 : c_name(c, name));
    int op = slot >= 0 ? OP_LOADS : (c->mode == MODE_EXPR ? OP_LOADN : OP_LOADG);
    return index < 0 ? -1 : c_emit_temp(c, c->tmp, op, index, 0);
}


// The "if" built-in function - value, true, and false expressions, evaluated as conditional jumps
static int c_if(Compiler *c, PyObject *func)
{
    PyObject *args;
    int found = c_get(c, func, S_args, &args);
    if (found < 0) {
        return -1;
    }
    Py_ssize_t count = 0;
    if (found) {
        if (!PyList_CheckExact(args)) {
            return c_irregular(c);
        }
        count = PyList_GET_SIZE(args);
    }
    if (count == 0) {
        return c_keyword(c, Py_None);
    }

    int mark = c->tmp;
    PyObject *value_expr = c_item(c, args, 0);
    int value_reg = value_expr != NULL ? c_expr(c, value_expr) : -1;
    if (value_reg < 0) {
        return -1;
    }
    c->tmp = mark;
    int reg = c_temp(c);
    int jump_false = reg >= 0 ? c_emit(c, OP_JF, value_reg, 0, 0) : -1;
    if (jump_false < 0) {
        return -1;
    }

    // The true and false expressions
    int jump_done = -1;
    for (int ix = 1; ix <= 2; ix++) {
        int result_reg;
        if (count > ix) {
            PyObject *result_expr = c_item(c, args, ix);
            result_reg = result_expr != NULL ? c_expr(c, result_expr) : -1;
        } else {
            result_reg = c_keyword(c, Py_None);
        }
        if (result_reg < 0 || (result_reg != reg && c_emit(c, OP_MOVE, reg, result_reg, 0) < 0)) {
            return -1;
        }
        c_temp_reset(c, reg);
        if (ix == 1) {
            jump_done = c_emit(c, OP_JMP, 0, 0, 0);
            if (jump_done < 0) {
                return -1;
            }
            c->code[jump_false].w = (uint32_t)c->ncode;
        }
    }
    c->code[jump_done].w = (uint32_t)c->ncode;
    c->result_pc = -1;
    return reg;
}


static int c_call(Compiler *c, PyObject *func)
{
    if (!PyDict_CheckExact(func)) {
        return c_irregular(c);
    }
    PyObject *name, *args;
    int found = c_get(c, func, S_name, &name);
    if (found <= 0 || !PyUnicode_CheckExact(name)) {
        return found < 0 ? -1 : c_irregular(c);
    }
    if (PyUnicode_CompareWithASCIIString(name, "if") == 0) {
        return c_if(c, func);
    }

    // Compile the arguments
    found = c_get(c, func, S_args, &args);
    if (found < 0) {
        return -1;
    }
    int args_none = !found || args == Py_None;
    if (!args_none && !PyList_CheckExact(args)) {
        return c_irregular(c);
    }
    Py_ssize_t argc = args_none ? 0 : PyList_GET_SIZE(args);
    if (argc > REG_MAX) {
        return c_irregular(c);
    }
    int regs_small[16];
    int *regs = argc <= 16 ? regs_small : PyMem_Malloc(argc * sizeof(int));
    if (regs == NULL) {
        PyErr_NoMemory();
        return -1;
    }
    int mark = c->tmp, result = -1;
    for (Py_ssize_t ix = 0; ix < argc; ix++) {
        PyObject *arg = c_item(c, args, ix);
        regs[ix] = arg != NULL ? c_expr(c, arg) : -1;
        if (regs[ix] < 0) {
            goto done;
        }
    }
    c->tmp = mark;
    int reg = c_temp(c);
    if (reg < 0) {
        goto done;
    }

    // Emit the call and its argument DATA words
    int slot = c_slot(c, name);
    int op = slot >= 0 ? OP_CALLS : (c->mode == MODE_EXPR ? OP_CALLN : OP_CALLG);
    int index = slot >= 0 ? slot : (PyErr_Occurred() ? -1 : c_name(c, name));
    int pc = index >= 0 ? c_emit(c, op, reg, index, args_none ? ARGS_NONE : (int)argc) : -1;
    if (pc < 0) {
        goto done;
    }
    c->code[pc].x = (uint8_t)c_intrinsic(name);
    for (Py_ssize_t ix = 0; ix < argc; ix += 3) {
        if (c_emit(c, OP_DATA, regs[ix], ix + 1 < argc ? regs[ix + 1] : 0, ix + 2 < argc ? regs[ix + 2] : 0) < 0) {
            goto done;
        }
    }
    c->result_pc = pc;
    result = reg;

done:
    if (regs != regs_small) {
        PyMem_Free(regs);
    }
    return result;
}


// Map a binary operator string to its instruction - runtime.py treats any other operator as ">>"
#define OP_AND (OP_COUNT + 1)
#define OP_OR (OP_COUNT + 2)

static int c_binary_op(Compiler *c, PyObject *op)
{
    static const struct {
        const char *name;
        int op;
    } ops[] = {
        {"&&", OP_AND}, {"||", OP_OR}, {"+", OP_ADD}, {"-", OP_SUB}, {"*", OP_MUL}, {"/", OP_DIV},
        {"<", OP_LT}, {"<=", OP_LE}, {">", OP_GT}, {">=", OP_GE}, {"==", OP_EQ}, {"!=", OP_NE}, {"%", OP_MOD},
        {"**", OP_POW}, {"&", OP_BAND}, {"|", OP_BOR}, {"^", OP_BXOR}, {"<<", OP_SHL}
    };
    if (PyUnicode_CheckExact(op)) {
        for (size_t ix = 0; ix < sizeof(ops) / sizeof(ops[0]); ix++) {
            if (PyUnicode_CompareWithASCIIString(op, ops[ix].name) == 0) {
                return ops[ix].op;
            }
        }
    } else if (PyUnicode_Check(op)) {
        return c_irregular(c);
    }
    return OP_SHR;
}


static int c_binary(Compiler *c, PyObject *binary)
{
    PyObject *op_obj, *left, *right;
    int found = PyDict_CheckExact(binary) ? c_get(c, binary, S_op, &op_obj) : 0;
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }
    int op = c_binary_op(c, op_obj);
    found = op >= 0 ? c_get(c, binary, S_left, &left) : -1;
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }

    // Short-circuiting "and" and "or" - the left value is the result unless it decides otherwise
    int mark = c->tmp;
    if (op == OP_AND || op == OP_OR) {
        int left_reg = c_expr(c, left);
        if (left_reg < 0) {
            return -1;
        }
        c->tmp = mark;
        int reg = c_temp(c);
        if (reg < 0 || (left_reg != reg && c_emit(c, OP_MOVE, reg, left_reg, 0) < 0)) {
            return -1;
        }
        int jump = c_emit(c, op == OP_AND ? OP_JF : OP_JT, reg, 0, 0);
        found = jump >= 0 ? c_get(c, binary, S_right, &right) : -1;
        if (found <= 0) {
            return found < 0 ? -1 : c_irregular(c);
        }
        int right_reg = c_expr(c, right);
        if (right_reg < 0 || (right_reg != reg && c_emit(c, OP_MOVE, reg, right_reg, 0) < 0)) {
            return -1;
        }
        c->code[jump].w = (uint32_t)c->ncode;
        c_temp_reset(c, reg);
        c->result_pc = -1;
        return reg;
    }

    found = c_get(c, binary, S_right, &right);
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }
    int left_reg = c_expr(c, left);
    int right_reg = left_reg >= 0 ? c_expr(c, right) : -1;
    return right_reg < 0 ? -1 : c_emit_temp(c, mark, op, left_reg, right_reg);
}


static int c_unary(Compiler *c, PyObject *unary)
{
    PyObject *op_obj, *expr;
    int found = PyDict_CheckExact(unary) ? c_get(c, unary, S_op, &op_obj) : 0;
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }
    int op = OP_BNOT;
    if (PyUnicode_CheckExact(op_obj)) {
        if (PyUnicode_CompareWithASCIIString(op_obj, "!") == 0) {
            op = OP_NOT;
        } else if (PyUnicode_CompareWithASCIIString(op_obj, "-") == 0) {
            op = OP_NEG;
        }
    } else if (PyUnicode_Check(op_obj)) {
        return c_irregular(c);
    }
    found = c_get(c, unary, S_expr, &expr);
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }
    int mark = c->tmp;
    int value_reg = c_expr(c, expr);
    return value_reg < 0 ? -1 : c_emit_temp(c, mark, op, value_reg, 0);
}


// The expression key runtime.py dispatches an expression model on (borrowed), or NULL with its value unset if
// none (an error is set if the lookup failed)
static PyObject *c_expr_key(Compiler *c, PyObject *expr, PyObject **value)
{
    PyObject *keys[] = {S_number, S_string, S_variable, S_function, S_binary, S_unary, S_group};
    for (size_t ix = 0; ix < sizeof(keys) / sizeof(keys[0]); ix++) {
        int found = c_get(c, expr, keys[ix], value);
        if (found != 0) {
            return found > 0 ? keys[ix] : NULL;
        }
    }
    return NULL;
}


// Compile an expression - returns its operand register, or -1 (a Python error, or the irregular flag)
static int c_expr(Compiler *c, PyObject *expr)
{
    PyObject *value;
    PyObject *key = PyDict_CheckExact(expr) && c->depth < DEPTH_MAX ? c_expr_key(c, expr, &value) : NULL;
    if (key == NULL) {
        return PyErr_Occurred() ? -1 : c_irregular(c);
    }
    c->depth++;
    c->result_pc = -1;
    int reg = key == S_number || key == S_string ? c_const(c, value) :
        (key == S_variable ? c_variable(c, value) :
         (key == S_function ? c_call(c, value) :
          (key == S_binary ? c_binary(c, value) : (key == S_unary ? c_unary(c, value) : c_expr(c, value)))));
    c->depth--;
    return reg;
}


// Compute a statements list's label indexes (checking it is compilable) - 0 success, -1 failure
static int c_labels(Compiler *c, PyObject *statements, PyObject *labels)
{
    if (!PyList_CheckExact(statements)) {
        return c_irregular(c);
    }
    Py_ssize_t count = PyList_GET_SIZE(statements);
    for (Py_ssize_t ix = 0; ix < count; ix++) {
        PyObject *statement = c_item(c, statements, ix), *label, *name;
        if (statement == NULL) {
            return -1;
        }
        if (!PyDict_CheckExact(statement)) {
            return c_irregular(c);
        }
        int found = c_get(c, statement, S_label, &label);
        if (found < 0) {
            return -1;
        }
        if (found) {
            found = PyDict_CheckExact(label) ? c_get(c, label, S_name, &name) : 0;
            if (found <= 0 || !PyUnicode_CheckExact(name)) {
                return found < 0 ? -1 : c_irregular(c);
            }
            PyObject *index = PyLong_FromSsize_t(ix);
            int rc = labels != NULL && index != NULL ? PyDict_SetItem(labels, name, index) : 0;
            Py_XDECREF(index);
            if (index == NULL || rc < 0) {
                return -1;
            }
        }
    }
    return 0;
}


static int c_statement_expr(Compiler *c, PyObject *statement)
{
    PyObject *expr, *name;
    int found = PyDict_CheckExact(statement) ? c_get(c, statement, S_expr, &expr) : 0;
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }
    int reg = c_expr(c, expr);
    found = reg >= 0 ? c_get(c, statement, S_name, &name) : -1;
    if (found <= 0 || name == Py_None) {
        return found < 0 ? -1 : 0;
    }
    if (!PyUnicode_CheckExact(name)) {
        return c_irregular(c);
    }
    if (c->mode == MODE_FUNC) {
        // Retarget a single instruction computing the value into a temporary to the local variable slot
        int slot = c_slot(c, name);
        if (slot < 0) {
            return -1;
        }
        if (c->result_pc >= 0 && c->code[c->result_pc].a == reg && (reg & REG_TEMP)) {
            c->code[c->result_pc].a = (uint16_t)slot;
            return 0;
        }
        return c_emit(c, OP_MOVE, slot, reg, 0) < 0 ? -1 : 0;
    }
    int index = c_name(c, name);
    return index < 0 || c_emit(c, OP_STOREG, index, reg, 0) < 0 ? -1 : 0;
}


// Compile a label jump on a condition - a leading "!" inverts the jump, and a comparison compiles to a
// compare-and-jump. Returns the pc of the instruction holding the jump target, or -1.
static int c_jump_condition(Compiler *c, PyObject *expr)
{
    int on_true = 1;
    for (;;) {
        PyObject *value, *op, *operand, *right;
        PyObject *key = PyDict_CheckExact(expr) ? c_expr_key(c, expr, &value) : NULL;
        if (PyErr_Occurred()) {
            return -1;
        }
        if (key == S_group) {
            expr = value;
            continue;
        }
        if ((key != S_unary && key != S_binary) || !PyDict_CheckExact(value)) {
            break;
        }
        int found = c_get(c, value, S_op, &op);
        if (found > 0) {
            found = c_get(c, value, key == S_unary ? S_expr : S_left, &operand);
        }
        if (found < 0) {
            return -1;
        }
        if (found == 0 || !PyUnicode_CheckExact(op)) {
            break;
        }

        // "!" - jump on the operand's falsity
        if (key == S_unary) {
            if (PyUnicode_CompareWithASCIIString(op, "!") != 0) {
                break;
            }
            on_true = !on_true;
            expr = operand;
            continue;
        }

        // A comparison - a compare-and-jump
        int compare = c_binary_op(c, op);
        if (compare < OP_EQ || compare > OP_GE) {
            break;
        }
        found = c_get(c, value, S_right, &right);
        if (found <= 0) {
            return found < 0 ? -1 : c_irregular(c);
        }
        int mark = c->tmp;
        int left_reg = c_expr(c, operand);
        int right_reg = left_reg >= 0 ? c_expr(c, right) : -1;
        int pc = right_reg >= 0 ? c_emit(c, OP_JEQ + (compare - OP_EQ), left_reg, right_reg, 0) : -1;
        if (pc < 0 || c_emit(c, OP_JTARGET, 0, 0, 0) < 0) {
            return -1;
        }
        c->tmp = mark;
        c->code[pc].x = JUMP_LABEL | (on_true ? 0 : JUMP_NOT);
        return pc + 1;
    }
    int reg = c_expr(c, expr);
    int pc = reg >= 0 ? c_emit(c, on_true ? OP_JT : OP_JF, reg, 0, 0) : -1;
    if (pc >= 0) {
        c->code[pc].x = JUMP_LABEL;
    }
    return pc;
}


static int c_statement_jump(Compiler *c, PyObject *statement)
{
    PyObject *expr, *label;
    int has_expr = PyDict_CheckExact(statement) ? c_get(c, statement, S_expr, &expr) : -2;
    int found = has_expr >= 0 ? c_get(c, statement, S_label, &label) : has_expr;
    if (found <= 0 || !PyUnicode_CheckExact(label)) {
        return found == -1 ? -1 : c_irregular(c);
    }

    // Known label?
    PyObject *label_index = PyDict_GetItemWithError(c->labels, label);
    if (label_index != NULL) {
        int pc;
        if (has_expr) {
            pc = c_jump_condition(c, expr);
        } else if ((pc = c_emit(c, OP_JMP, 0, 0, 0)) >= 0) {
            c->code[pc].x = JUMP_LABEL;
        }
        if (pc < 0) {
            return -1;
        }
        if (c->nfixups == c->capfixups) {
            int capfixups = c->capfixups ? c->capfixups * 2 : 32;
            int *fixups = PyMem_Realloc(c->fixups, capfixups * 2 * sizeof(int));
            if (fixups == NULL) {
                PyErr_NoMemory();
                return -1;
            }
            c->fixups = fixups;
            c->capfixups = capfixups;
        }
        c->fixups[c->nfixups * 2] = pc;
        c->fixups[c->nfixups * 2 + 1] = (int)PyLong_AsLong(label_index);
        c->nfixups++;
        return 0;
    }
    if (PyErr_Occurred()) {
        return -1;
    }

    // Unknown label - an error when the jump is taken
    int reg = has_expr ? c_expr(c, expr) : 0;
    int index = reg >= 0 ? c_name(c, label) : -1;
    int jump = has_expr && index >= 0 ? c_emit(c, OP_JF, reg, 0, 0) : 0;
    if (index < 0 || jump < 0 || c_emit(c, OP_JUNDEF, index, 0, 0) < 0) {
        return -1;
    }
    if (has_expr) {
        c->code[jump].w = (uint32_t)c->ncode;
    }
    return 0;
}


static int c_statement_return(Compiler *c, PyObject *statement)
{
    PyObject *expr;
    int found = PyDict_CheckExact(statement) ? c_get(c, statement, S_expr, &expr) : -2;
    if (found < 0) {
        return found == -1 ? -1 : c_irregular(c);
    }
    if (!found) {
        return c_emit(c, OP_RETNONE, 0, 0, 0) < 0 ? -1 : 0;
    }
    int reg = c_expr(c, expr);
    return reg < 0 || c_emit(c, OP_RET, reg, 0, 0) < 0 ? -1 : 0;
}


static int c_statement_function(Compiler *c, PyObject *statement)
{
    PyObject *name, *statements;
    int found = PyDict_CheckExact(statement) ? c_get(c, statement, S_name, &name) : 0;
    if (found <= 0 || !PyUnicode_CheckExact(name)) {
        return found < 0 ? -1 : c_irregular(c);
    }
    found = c_get(c, statement, S_statements, &statements);
    if (found <= 0) {
        return found < 0 ? -1 : c_irregular(c);
    }

    // The function's label indexes are computed when it's defined - check they can be
    if (c_labels(c, statements, NULL) < 0) {
        return -1;
    }
    int index = c_name(c, name);
    int reg = index >= 0 ? c_const(c, statement) : -1;
    return reg < 0 || c_emit(c, OP_FUNC, index, reg, 0) < 0 ? -1 : 0;
}


static int c_statement(Compiler *c, PyObject *statement)
{
    c->tmp = 0;
    int pc = c_emit(c, OP_STMT, 0, 0, 0);
    if (pc < 0) {
        return -1;
    }
    c->code[pc].w = c->stmt;
    PyObject *value;
    int found;
    if ((found = c_get(c, statement, S_expr, &value)) != 0) {
        return found < 0 ? -1 : c_statement_expr(c, value);
    }
    if ((found = c_get(c, statement, S_jump, &value)) != 0) {
        return found < 0 ? -1 : c_statement_jump(c, value);
    }
    if ((found = c_get(c, statement, S_return, &value)) != 0) {
        return found < 0 ? -1 : c_statement_return(c, value);
    }
    if ((found = c_get(c, statement, S_function, &value)) != 0) {
        return found < 0 ? -1 : c_statement_function(c, value);
    }
    if ((found = c_get(c, statement, S_include, &value)) != 0) {
        if (found < 0 || (pc = c_emit(c, OP_INCLUDE, 0, 0, 0)) < 0) {
            return -1;
        }
        c->code[pc].w = c->stmt;
    }
    return 0;
}


// A statement's control flow, for the definite assignment analysis
typedef struct {
    int assign;     // the slot the statement assigns, or -1
    int target;     // the statement a label jump continues with, or -1
    int next;       // the statement can continue with the next statement
} Flow;


// Definite assignment - the slots assigned on every path to each statement, a forward must-analysis over the
// statements' fall-through and label jump edges. A local variable read where its slot is definitely assigned
// reads the slot directly; elsewhere it reads the global of its name if the slot is unassigned. Returns each
// statement's slot bit set (words per statement); an unreached statement's set is every slot.
static uint64_t *c_definite(Compiler *c, Flow *flow, Py_ssize_t count, int words)
{
    uint64_t *sets = PyMem_Malloc((count * words + 1) * sizeof(uint64_t));
    Py_ssize_t *work = PyMem_Malloc((count + 1) * sizeof(Py_ssize_t));
    char *queued = PyMem_Calloc(count + 1, 1), *reached = PyMem_Calloc(count + 1, 1);
    if (sets == NULL || work == NULL || queued == NULL || reached == NULL) {
        PyMem_Free(sets);
        PyMem_Free(work);
        PyMem_Free(queued);
        PyMem_Free(reached);
        PyErr_NoMemory();
        return NULL;
    }
    memset(sets, 0xFF, count * words * sizeof(uint64_t));

    // The arguments are assigned on entry
    Py_ssize_t nwork = 0;
    if (count > 0) {
        memset(sets, 0, words * sizeof(uint64_t));
        for (int slot = 0; slot < c->nargslots; slot++) {
            sets[slot / 64] |= (uint64_t)1 << (slot % 64);
        }
        reached[0] = queued[0] = 1;
        work[nwork++] = 0;
    }
    while (nwork > 0) {
        Py_ssize_t ix = work[--nwork];
        queued[ix] = 0;
        Py_ssize_t succs[2] = {flow[ix].next ? ix + 1 : -1, flow[ix].target};
        for (int ix_succ = 0; ix_succ < 2; ix_succ++) {
            Py_ssize_t succ = succs[ix_succ];
            if (succ < 0 || succ >= count) {
                continue;
            }
            uint64_t *in = sets + ix * words, *succ_in = sets + succ * words;
            int changed = !reached[succ];
            for (int word = 0; word < words; word++) {
                uint64_t out = in[word];
                if (flow[ix].assign >= 0 && flow[ix].assign / 64 == word) {
                    out |= (uint64_t)1 << (flow[ix].assign % 64);
                }
                uint64_t value = reached[succ] ? succ_in[word] & out : out;
                changed = changed || value != succ_in[word];
                succ_in[word] = value;
            }
            reached[succ] = 1;
            if (changed && !queued[succ]) {
                queued[succ] = 1;
                work[nwork++] = succ;
            }
        }
    }
    PyMem_Free(work);
    PyMem_Free(queued);
    PyMem_Free(reached);
    return sets;
}


// Compile a statements list
static int c_statements(Compiler *c, PyObject *statements)
{
    if (c_labels(c, statements, c->labels) < 0) {
        return -1;
    }
    Py_ssize_t count = PyList_GET_SIZE(statements);

    // A function's local variables are its arguments (already added) and its assignment targets
    Flow *flow = NULL;
    uint64_t *definite = NULL;
    int words = 0;
    if (c->mode == MODE_FUNC) {
        flow = PyMem_Calloc(count + 1, sizeof(Flow));
        if (flow == NULL) {
            PyErr_NoMemory();
            return -1;
        }
        for (Py_ssize_t ix = 0; ix < count; ix++) {
            PyObject *statement = c_item(c, statements, ix), *value, *name;
            int found = statement != NULL ? c_get(c, statement, S_expr, &value) : -1;
            flow[ix].assign = -1;
            flow[ix].target = -1;
            flow[ix].next = 1;
            if (found > 0) {
                if (PyDict_CheckExact(value)) {
                    found = c_get(c, value, S_name, &name);
                    if (found > 0 && PyUnicode_CheckExact(name)) {
                        found = flow[ix].assign = c_slot_add(c, name);
                    }
                }
            } else if (found == 0 && (found = c_get(c, statement, S_jump, &value)) > 0) {
                if (PyDict_CheckExact(value)) {
                    PyObject *label, *label_index;
                    found = c_get(c, value, S_label, &label);
                    if (found > 0 && PyUnicode_CheckExact(label) &&
                        (label_index = PyDict_GetItemWithError(c->labels, label)) != NULL) {
                        flow[ix].target = (int)PyLong_AsLong(label_index) + 1;
                    }
                    found = found < 0 || PyErr_Occurred() ? -1 : PyDict_Contains(value, S_expr);
                    flow[ix].next = found > 0;
                }
            } else if (found == 0 && (found = c_get(c, statement, S_return, &value)) > 0) {
                flow[ix].next = 0;
            }
            if (found < 0) {
                PyMem_Free(flow);
                return -1;
            }
        }
        words = ((int)PyList_GET_SIZE(c->slot_names) + 63) / 64;
        definite = c_definite(c, flow, count, words);
        PyMem_Free(flow);
        if (definite == NULL) {
            return -1;
        }
    }

    // Compile the statements, noting where each begins for the label jumps
    int *starts = PyMem_Malloc((count + 1) * sizeof(int));
    if (starts == NULL) {
        PyMem_Free(definite);
        PyErr_NoMemory();
        return -1;
    }
    int rc = -1;
    for (Py_ssize_t ix = 0; ix < count; ix++) {
        PyObject *statement = c_item(c, statements, ix);
        c->stmt = (uint32_t)ix;
        c->definite = definite != NULL ? definite + ix * words : NULL;
        starts[ix] = c->ncode;
        if (statement == NULL || c_statement(c, statement) < 0) {
            goto done;
        }
    }
    c->stmt = (uint32_t)count;
    starts[count] = c_emit(c, OP_RETNONE, 0, 0, 0);
    if (starts[count] < 0) {
        goto done;
    }

    // A jump to a label continues with the statement after it
    for (int ix = 0; ix < c->nfixups; ix++) {
        c->code[c->fixups[ix * 2]].w = (uint32_t)starts[c->fixups[ix * 2 + 1] + 1];
    }
    rc = 0;

done:
    c->definite = NULL;
    PyMem_Free(definite);
    PyMem_Free(starts);
    return rc;
}


// Finish a compile - number the registers and build the chunk
static Chunk *c_finish(Compiler *c, Chunk *chunk)
{
    int nslots = (int)PyList_GET_SIZE(c->slot_names);
    int ntemps = c->tmpmax;
    for (int pc = 0; pc < c->ncode; pc++) {
        Inst *inst = &c->code[pc];
        int regs = op_registers(inst->op);
        uint16_t *fields[3] = {&inst->a, &inst->b, &inst->c};
        for (int ix = 0; ix < 3; ix++) {
            if (regs & (1 << ix)) {
                uint16_t reg = *fields[ix];
                *fields[ix] = (reg & REG_CONST) ? (uint16_t)(nslots + ntemps + (reg & REG_MAX)) :
                    ((reg & REG_TEMP) ? (uint16_t)(nslots + (reg & REG_MAX)) : reg);
            }
        }
    }

    chunk->code = c->code;
    chunk->pcstmt = c->pcstmt;
    c->code = NULL;
    c->pcstmt = NULL;
    chunk->nslots = nslots;
    chunk->nowned = nslots + ntemps;
    chunk->nconsts = (int)PyList_GET_SIZE(c->consts);
    chunk->nnames = (int)PyList_GET_SIZE(c->names);
    chunk->consts = PyMem_Calloc(chunk->nconsts + 1, sizeof(PyObject *));
    chunk->names = PyMem_Calloc(chunk->nnames + 1, sizeof(PyObject *));
    chunk->slot_names = PyMem_Calloc(nslots + 1, sizeof(PyObject *));
    if (chunk->consts == NULL || chunk->names == NULL || chunk->slot_names == NULL) {
        chunk->nconsts = chunk->nnames = chunk->nslots = 0;
        chunk_free(chunk);
        PyErr_NoMemory();
        return NULL;
    }
    for (int ix = 0; ix < chunk->nconsts; ix++) {
        chunk->consts[ix] = Py_NewRef(PyList_GET_ITEM(c->consts, ix));
    }
    for (int ix = 0; ix < chunk->nnames; ix++) {
        chunk->names[ix] = Py_NewRef(PyList_GET_ITEM(c->names, ix));
    }
    for (int ix = 0; ix < nslots; ix++) {
        chunk->slot_names[ix] = Py_NewRef(PyList_GET_ITEM(c->slot_names, ix));
    }
    return chunk;
}


// Compile a statements list or expression. Returns NULL on error; the chunk's irregular flag is set for a
// model that is not compiled.
static Chunk *compile(int mode, PyObject *script, PyObject *model, PyObject *function)
{
    Chunk *chunk = PyMem_Calloc(1, sizeof(Chunk));
    if (chunk == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    Compiler compiler = {0}, *c = &compiler;
    c->mode = mode;
    c->result_pc = -1;
    c->reg_none = c->reg_false = c->reg_true = -1;
    c->consts = PyList_New(0);
    c->names = PyList_New(0);
    c->name_index = PyDict_New();
    c->slots = PyDict_New();
    c->slot_names = PyList_New(0);
    c->labels = PyDict_New();
    c->keep = PyList_New(0);
    int rc = -1;
    if (c->consts == NULL || c->names == NULL || c->name_index == NULL || c->slots == NULL ||
        c->slot_names == NULL || c->labels == NULL || c->keep == NULL) {
        goto done;
    }

    if (mode == MODE_EXPR) {
        int reg = c_expr(c, model);
        rc = reg < 0 || c_emit(c, OP_RET, reg, 0, 0) < 0 ? -1 : 0;
    } else {
        chunk->script = Py_NewRef(script);
        chunk->statements = Py_NewRef(model);
        chunk->nstatements = PyList_Check(model) ? PyList_GET_SIZE(model) : 0;

        // A function's arguments are its leading local variable slots
        if (mode == MODE_FUNC) {
            PyObject *args, *last_arg_array;
            int found = c_get(c, function, S_args, &args);
            if (found > 0 && args != Py_None) {
                if (!PyList_CheckExact(args)) {
                    rc = c_irregular(c);
                    goto done;
                }
                chunk->args = Py_NewRef(args);
                chunk->nargs = (int)PyList_GET_SIZE(args);
                chunk->arg_slots = PyMem_Calloc(chunk->nargs + 1, sizeof(uint16_t));
                chunk->arg_items = PyMem_Calloc(chunk->nargs + 1, sizeof(PyObject *));
                if (chunk->arg_slots == NULL || chunk->arg_items == NULL) {
                    chunk->nargs = 0;
                    PyErr_NoMemory();
                    goto done;
                }
                for (int ix = 0; ix < chunk->nargs; ix++) {
                    PyObject *arg = bs_list_get(args, ix);
                    chunk->arg_items[ix] = arg;
                    if (arg == NULL) {
                        goto done;
                    }
                    if (!PyUnicode_CheckExact(arg)) {
                        rc = c_irregular(c);
                        goto done;
                    }
                    int slot = c_slot_add(c, arg);
                    if (slot < 0) {
                        goto done;
                    }
                    chunk->arg_slots[ix] = (uint16_t)slot;
                }
                c->nargslots = (int)PyList_GET_SIZE(c->slot_names);
                found = c_get(c, function, S_lastArgArray, &last_arg_array);
                chunk->last_arg_array = found > 0 ? PyObject_IsTrue(last_arg_array) : found;
                chunk->last_arg_array_plain = found == 0 || last_arg_array == Py_None || PyBool_Check(last_arg_array);
                if (chunk->last_arg_array < 0) {
                    goto done;
                }
            } else if (found < 0) {
                goto done;
            }
        }
        rc = c_statements(c, model);
    }

done:
    if (rc < 0 && !PyErr_Occurred()) {
        chunk->irregular = 1;
    }
    Chunk *result = NULL;
    if (rc == 0) {
        result = c_finish(c, chunk);
    } else if (chunk->irregular) {
        result = chunk;
    } else {
        chunk_free(chunk);
    }
    PyMem_Free(c->code);
    PyMem_Free(c->pcstmt);
    PyMem_Free(c->fixups);
    Py_XDECREF(c->consts);
    Py_XDECREF(c->names);
    Py_XDECREF(c->name_index);
    Py_XDECREF(c->slots);
    Py_XDECREF(c->slot_names);
    Py_XDECREF(c->labels);
    Py_XDECREF(c->keep);
    return result;
}


//
// The execution context and frames
//


// A global call resolution (GIL builds) - a call name's value in the globals, valid while the globals epoch stands
// still. The epoch advances whenever a globals dict might change: Python code running, an include, a global
// assignment or function definition, or a library function setting a key of the globals. A context's frames all
// share its globals, which change only when Python code runs. The free-threaded build resolves every call - another
// thread's Python code could change the globals without advancing the epoch.
#define CALL_CACHE_SIZE 128
#ifndef Py_GIL_DISABLED
#define BS_CALL_CACHE 1
static uint64_t g_globals_epoch = 1;
#define globals_changed() (g_globals_epoch++)
#else
#define globals_changed() ((void)0)
#endif

typedef struct CallCache {
    PyObject *name;             // the interned call name (a reference)
    PyObject *func;             // its value in the globals (a reference)
    PyObject *globals;          // the globals (a reference)
    uint64_t epoch;
} CallCache;


// An execution context - one per entry from Python, shared by the script function calls it makes directly.
// The statement count is kept here and synchronized with options['statementCount'] whenever Python code might
// read or write it. runtime.py's per-call setup reads - the globals, the statement limit, and the coverage
// global - are cached here too, and dropped whenever anything could have changed them: Python code running, or
// this runtime assigning the coverage global or setting a key of the coverage, globals, or options dict.
// The statement count while options['statementCount'] is runtime.py's - above every frame's limit, so that each
// statement counts with count_python
#define COUNT_PYTHON (LLONG_MAX - 1)

typedef struct {
    PyObject *options;          // borrowed - the caller holds it
    long long count;
    long long synced;           // the count when last synchronized
    PyObject *synced_obj;       // options['statementCount'] when last synchronized - NULL until the count is loaded
    int count_python;           // options['statementCount'] isn't an int this runtime can count (see count_python)
    PyObject *setup_globals;    // options['globals'] - NULL until the setup reads are cached
    PyObject *setup_max;        // options.get('maxStatements', DEFAULT_MAX_STATEMENTS)
    long long setup_limit;      // a statement count above this exceeds maxStatements
    PyObject *setup_coverage;   // globals['__barescriptCoverage'] if it's a dict, or NULL
    int setup_enabled;          // its "enabled" truth, or -1 to read it on each call
    struct CallCache *call_cache; // global call resolutions (GIL builds), allocated on first use
} Ctx;


// Drop the cached setup reads
static void ctx_invalidate(Ctx *ctx)
{
    Py_CLEAR(ctx->setup_globals);
    Py_CLEAR(ctx->setup_max);
    Py_CLEAR(ctx->setup_coverage);
}


// A dict this runtime changed - drop the cached setup reads if it's the options, globals, or coverage dict
static void ctx_dict_changed(Ctx *ctx, PyObject *dict)
{
    if (dict == ctx->setup_coverage || dict == ctx->setup_globals || dict == ctx->options) {
        ctx_invalidate(ctx);
    }
}


// Write the statement count to the options
static int ctx_sync_out(Ctx *ctx)
{
    if (ctx->synced_obj == NULL || ctx->count_python || ctx->count == ctx->synced) {
        return 0;
    }
    PyObject *count = PyLong_FromLongLong(ctx->count);
    if (count == NULL || PyDict_SetItem(ctx->options, S_statementCount, count) < 0) {
        Py_XDECREF(count);
        return -1;
    }
    Py_XSETREF(ctx->synced_obj, count);
    ctx->synced = ctx->count;
    return 0;
}


// Read the statement count back from the options, after Python code may have changed it
static void ctx_sync_in(Ctx *ctx)
{
    ctx_invalidate(ctx);
    globals_changed();
    if (ctx->synced_obj == NULL) {
        return;
    }
    PyObject *count;
    int found = bs_dict_get(ctx->options, S_statementCount, &count);
    if (found < 0) {
        PyErr_Clear();
    }
    long long value;
    if (found > 0 && count == ctx->synced_obj) {
        Py_DECREF(count);
    } else if (found > 0 && PyLong_CheckExact(count) && small_int(count, &value)) {
        ctx->count = ctx->synced = value;
        ctx->count_python = 0;
        Py_XSETREF(ctx->synced_obj, count);
    } else {
        // A count this runtime can't keep - each statement updates options['statementCount'] as runtime.py does
        ctx->count = COUNT_PYTHON;
        ctx->count_python = 1;
        Py_XDECREF(count);
    }
}


// Exit the context - write the statement count to the options, preserving any raised exception
static void ctx_exit(Ctx *ctx)
{
    PyObject *exc = PyErr_Occurred() ? bs_err_fetch() : NULL;
    if (ctx_sync_out(ctx) < 0) {
        PyErr_Clear();
    }
    if (exc != NULL) {
        bs_err_restore(exc);
    }
    Py_CLEAR(ctx->synced_obj);
    ctx_invalidate(ctx);
    if (ctx->call_cache != NULL) {
        for (int ix = 0; ix < CALL_CACHE_SIZE; ix++) {
            Py_XDECREF(ctx->call_cache[ix].name);
            Py_XDECREF(ctx->call_cache[ix].func);
            Py_XDECREF(ctx->call_cache[ix].globals);
        }
        PyMem_Free(ctx->call_cache);
    }
}


// A running chunk
typedef struct {
    Ctx *ctx;
    Chunk *chunk;
    PyObject **regs;
    PyObject *globals;          // a new reference, or NULL (evaluate_expression without globals)
    PyObject *locals;           // evaluate_expression's locals dict (borrowed), or NULL
    PyObject *coverage;         // a new reference to the coverage global when recording coverage, or NULL
    PyObject *max_statements;   // a new reference to the maxStatements option
    long long limit;            // a statement count above this takes the STMT slow path
    long long max_limit;        // a statement count above this exceeds maxStatements
    PyObject *script;           // the script for error messages (borrowed)
    PyObject *statement;        // evaluate_expression's statement for error messages (borrowed)
    int builtins;
} Frame;


// Read and cache runtime.py's per-call setup - returns 1, 0 if the options are not supported here (run
// runtime.py), or -1 on error
static int ctx_setup(Ctx *ctx)
{
    PyObject *options = ctx->options, *globals, *max = NULL, *coverage = NULL;
    int found = bs_dict_get(options, S_globals, &globals);
    if (found <= 0 || !PyDict_CheckExact(globals)) {
        Py_XDECREF(globals);
        return found < 0 ? -1 : 0;
    }

    // The statement limit - a count greater than a positive maxStatements
    int rc = 0;
    long long limit = COUNT_PYTHON - 1, max_int;
    found = bs_dict_get(options, S_maxStatements, &max);
    if (found == 0) {
        max = Py_NewRef(g_default_max_statements);
    }
    if (found < 0) {
        rc = -1;
    } else if (PyFloat_CheckExact(max)) {
        double max_float = PyFloat_AS_DOUBLE(max);
        if (max_float > 0 && max_float < 9e18) {
            limit = (long long)max_float;
        }
        rc = 1;
    } else if (PyLong_CheckExact(max) || PyBool_Check(max)) {
        if (small_int(max, &max_int) && max_int > 0) {
            limit = max_int < COUNT_PYTHON ? max_int : COUNT_PYTHON - 1;
        }
        rc = 1;
    }

    // The coverage global - its "enabled" value is read on each call unless it's a bool or None
    int enabled = 0;
    if (rc > 0 && (found = bs_dict_get(globals, S_coverage, &coverage)) != 0) {
        if (found < 0) {
            rc = -1;
        } else if (!PyDict_Check(coverage)) {
            Py_CLEAR(coverage);
        } else if (!PyDict_CheckExact(coverage)) {
            enabled = -1;
        } else {
            PyObject *value;
            found = bs_dict_get(coverage, S_enabled, &value);
            if (found < 0) {
                rc = -1;
            } else {
                enabled = found && value != Py_None && !PyBool_Check(value) ? -1 : value == Py_True;
                Py_XDECREF(value);
            }
        }
    }
    if (rc <= 0) {
        Py_DECREF(globals);
        Py_XDECREF(max);
        Py_XDECREF(coverage);
        return rc;
    }
    ctx->setup_globals = globals;
    ctx->setup_max = max;
    ctx->setup_limit = limit;
    ctx->setup_coverage = coverage;
    ctx->setup_enabled = enabled;
    return 1;
}


// Begin a statements frame - runtime.py's _execute_script_helper preamble. Returns 1, 0 if the options are
// not supported here (run runtime.py), or -1 on error.
static int frame_begin(Frame *f, Ctx *ctx, Chunk *chunk, PyObject *script)
{
    f->ctx = ctx;
    f->chunk = chunk;
    f->script = script;
    if (ctx->setup_globals == NULL) {
        int rc = ctx_setup(ctx);
        if (rc <= 0) {
            return rc;
        }
    }
    f->globals = Py_NewRef(ctx->setup_globals);
    f->max_statements = Py_NewRef(ctx->setup_max);
    f->max_limit = ctx->setup_limit;

    // options.setdefault('statementCount', 0)
    if (ctx->synced_obj == NULL) {
        PyObject *count;
        int found = bs_dict_get(ctx->options, S_statementCount, &count);
        if (found < 0) {
            return -1;
        }
        if (!found) {
            count = Py_NewRef(g_zero);
            if (PyDict_SetItem(ctx->options, S_statementCount, count) < 0) {
                Py_DECREF(count);
                return -1;
            }
        }
        if (!PyLong_CheckExact(count) || !small_int(count, &ctx->count)) {
            Py_DECREF(count);
            return 0;
        }
        ctx->synced = ctx->count;
        ctx->synced_obj = count;
    }

    // Recording coverage?
    int truth = ctx->setup_enabled;
    if (truth < 0) {
        PyObject *enabled = object_get(ctx->setup_coverage, S_enabled);
        truth = enabled != NULL ? PyObject_IsTrue(enabled) : -1;
        Py_XDECREF(enabled);
    }
    if (truth > 0) {
        PyObject *system = object_get(script, S_system);
        truth = system != NULL ? PyObject_IsTrue(system) : -1;
        Py_XDECREF(system);
        if (truth == 0) {
            f->coverage = Py_NewRef(ctx->setup_coverage);
        }
    }
    f->limit = f->coverage != NULL ? LLONG_MIN : f->max_limit;
    return truth < 0 ? -1 : 1;
}


static void frame_end(Frame *f)
{
    Py_CLEAR(f->globals);
    Py_CLEAR(f->coverage);
    Py_CLEAR(f->max_statements);
}


// The registers a frame gets on the C stack before it needs the heap
#define REGS_SMALL 32


static PyObject **regs_alloc(Chunk *chunk, PyObject **small)
{
    int nowned = chunk->nowned, count = nowned + chunk->nconsts;
    PyObject **regs = count <= REGS_SMALL ? small : PyMem_Malloc(count * sizeof(PyObject *));
    if (regs == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    memset(regs, 0, nowned * sizeof(PyObject *));
    memcpy(regs + nowned, chunk->consts, chunk->nconsts * sizeof(PyObject *));
    return regs;
}


static void regs_free(Chunk *chunk, PyObject **regs, PyObject **small)
{
    int nowned = chunk->nowned;
    for (int ix = 0; ix < nowned; ix++) {
        Py_XDECREF(regs[ix]);
    }
    if (regs != small) {
        PyMem_Free(regs);
    }
}


// Claim a function's resident registers - its owned registers are null (they're released when a call finishes)
// and its constants in place. A function gets resident registers on its second call; a call finding them in use
// (recursion, or another thread) uses registers of its own. Returns NULL if not claimed.
static PyObject **regs_claim(Chunk *chunk)
{
    PyObject **regs = bs_atomic_load(&chunk->resident);
    if (regs == NULL) {
        if (bs_atomic_claim(&chunk->called)) {
            return NULL;
        }
        int nowned = chunk->nowned;
        regs = PyMem_Calloc(nowned + chunk->nconsts + 1, sizeof(PyObject *));
        if (regs == NULL) {
            return NULL;
        }
        memcpy(regs + nowned, chunk->consts, chunk->nconsts * sizeof(PyObject *));
        PyObject **expected = NULL;
        if (!bs_atomic_publish(&chunk->resident, &expected, regs)) {
            PyMem_Free(regs);
            regs = expected;
        }
    }
    return bs_atomic_claim(&chunk->resident_busy) ? regs : NULL;
}


// Release a function's resident registers
static void regs_release(Chunk *chunk, PyObject **regs)
{
    int nowned = chunk->nowned;
    for (int ix = 0; ix < nowned; ix++) {
        PyObject *value = regs[ix];
        regs[ix] = NULL;
        Py_XDECREF(value);
    }
    bs_atomic_store(&chunk->resident_busy, 0);
}


// The statement at a statement index (a new reference) - None past the end
static PyObject *chunk_statement(Chunk *chunk, uint32_t index)
{
    PyObject *statement = chunk->statements != NULL ? bs_list_get(chunk->statements, index) : NULL;
    if (statement == NULL) {
        PyErr_Clear();
        statement = Py_NewRef(Py_None);
    }
    return statement;
}


// The error-message statement of an instruction (a new reference)
static PyObject *frame_statement(Frame *f, const Inst *inst)
{
    if (f->chunk->statements == NULL) {
        return Py_NewRef(f->statement != NULL ? f->statement : Py_None);
    }
    return chunk_statement(f->chunk, f->chunk->pcstmt[inst - f->chunk->code]);
}


//
// Coverage
//


// runtime.py's _record_statement_coverage
static int coverage_record(PyObject *script, PyObject *statement, PyObject *coverage)
{
    // The statement's first key
    PyObject *keys = PyDict_Keys(statement);
    if (keys == NULL) {
        return -1;
    }
    if (PyList_GET_SIZE(keys) == 0) {
        Py_DECREF(keys);
        PyErr_SetNone(PyExc_StopIteration);
        return -1;
    }
    PyObject *key = Py_NewRef(PyList_GET_ITEM(keys, 0));
    Py_DECREF(keys);

    // Exact dicts are recorded here, anything else by runtime.py
    int rc = -1;
    PyObject *script_name = NULL, *statement_value = NULL, *lineno = NULL, *scripts = NULL, *script_coverage = NULL,
        *lineno_str = NULL, *covered = NULL, *covered_statement = NULL, *count = NULL;
    script_name = object_get(script, S_scriptName);
    if (script_name == NULL || bs_dict_get(statement, key, &statement_value) < 0) {
        goto done;
    }
    if (statement_value == NULL || !PyDict_CheckExact(statement_value) || !PyDict_CheckExact(coverage)) {
        goto python;
    }
    lineno = object_get(statement_value, S_lineNumber);
    if (lineno == NULL) {
        goto done;
    }
    if (script_name == Py_None || lineno == Py_None) {
        rc = 0;
        goto done;
    }
    if ((scripts = object_get(coverage, S_scripts)) == NULL) {
        goto done;
    }
    if (scripts == Py_None) {
        Py_SETREF(scripts, PyDict_New());
        if (scripts == NULL || PyDict_SetItem(coverage, S_scripts, scripts) < 0) {
            goto done;
        }
    }
    if (!PyDict_CheckExact(scripts)) {
        goto python;
    }
    if ((script_coverage = object_get(scripts, script_name)) == NULL) {
        goto done;
    }
    if (script_coverage == Py_None) {
        PyObject *covered_new = PyDict_New();
        Py_SETREF(script_coverage, covered_new != NULL ? Py_BuildValue("{sOsO}", "script", script, "covered", covered_new) : NULL);
        Py_XDECREF(covered_new);
        if (script_coverage == NULL || PyDict_SetItem(scripts, script_name, script_coverage) < 0) {
            goto done;
        }
    }
    if (!PyDict_CheckExact(script_coverage)) {
        goto python;
    }
    if ((lineno_str = PyObject_Str(lineno)) == NULL) {
        goto done;
    }
    covered = PyObject_GetItem(script_coverage, S_covered);
    if (covered == NULL) {
        goto done;
    }
    if (!PyDict_CheckExact(covered)) {
        goto python;
    }
    if ((covered_statement = object_get(covered, lineno_str)) == NULL) {
        goto done;
    }
    if (covered_statement == Py_None) {
        Py_SETREF(covered_statement, Py_BuildValue("{sOsO}", "statement", statement, "count", g_zero));
        if (covered_statement == NULL || PyDict_SetItem(covered, lineno_str, covered_statement) < 0) {
            goto done;
        }
    }
    if (!PyDict_CheckExact(covered_statement)) {
        goto python;
    }
    count = PyObject_GetItem(covered_statement, S_count);
    if (count == NULL) {
        goto done;
    }
    Py_SETREF(count, PyNumber_Add(count, g_one));
    rc = count != NULL ? PyDict_SetItem(covered_statement, S_count, count) : -1;
    goto done;

python:
    {
        PyObject *result = runtime_call("_record_statement_coverage", script, statement, key, coverage, NULL);
        rc = result != NULL ? 0 : -1;
        Py_XDECREF(result);
    }

done:
    Py_DECREF(key);
    Py_XDECREF(script_name);
    Py_XDECREF(statement_value);
    Py_XDECREF(lineno);
    Py_XDECREF(scripts);
    Py_XDECREF(script_coverage);
    Py_XDECREF(lineno_str);
    Py_XDECREF(covered);
    Py_XDECREF(covered_statement);
    Py_XDECREF(count);
    return rc;
}


// Record the coverage of the statement at an index
static int frame_coverage(Frame *f, uint32_t index)
{
    PyObject *statement = chunk_statement(f->chunk, index);
    int rc = coverage_record(f->script, statement, f->coverage);
    Py_DECREF(statement);
    return rc;
}


//
// Script functions
//


// The function model dict watcher (Python 3.12+) - runtime.py reads a function model's statements and arguments
// on each call, so a compiled body is checked against its model on each call. A watched model dict's changes
// advance the model epoch; while it stands still, only the model's lists can have changed.
#if PY_VERSION_HEX >= 0x030C0000
#define BS_MODEL_WATCH 1
static int g_model_watcher = -1;
static BS_ATOMIC_U64 g_model_epoch;


static int model_watch_callback(PyDict_WatchEvent event, PyObject *dict, PyObject *key, PyObject *new_value)
{
    (void)dict;
    (void)key;
    (void)new_value;
    if (event != PyDict_EVENT_DEALLOCATED) {
        bs_atomic_add(&g_model_epoch);
    }
    return 0;
}
#endif


// A script function - a function statement's model and its script, called as a Python function (args, options)
typedef struct {
    PyObject_HEAD
    vectorcallfunc vectorcall;
    PyObject *script;
    PyObject *function;
    BS_ATOMIC_PTR(Chunk) chunk;   // compiled on first call
} ScriptFunction;

static PyTypeObject ScriptFunction_Type;


static PyObject *script_function_vectorcall(PyObject *self, PyObject *const *args, size_t nargsf, PyObject *kwnames);


static PyObject *script_function_new(PyObject *script, PyObject *function)
{
    ScriptFunction *fn = PyObject_GC_New(ScriptFunction, &ScriptFunction_Type);
    if (fn == NULL) {
        return NULL;
    }
    fn->vectorcall = script_function_vectorcall;
    fn->script = Py_NewRef(script);
    fn->function = Py_NewRef(function);
    fn->chunk = NULL;
    PyObject_GC_Track((PyObject *)fn);
    return (PyObject *)fn;
}


static int script_function_traverse(PyObject *self, visitproc visit, void *arg)
{
    ScriptFunction *fn = (ScriptFunction *)self;
    Py_VISIT(fn->script);
    Py_VISIT(fn->function);
    Chunk *chunk = bs_atomic_load(&fn->chunk);
    if (chunk != NULL) {
        for (int ix = 0; ix < chunk->nconsts; ix++) {
            Py_VISIT(chunk->consts[ix]);
        }
        Py_VISIT(chunk->statements);
        Py_VISIT(chunk->script);
        Py_VISIT(chunk->args);
    }
    return 0;
}


static int script_function_clear(PyObject *self)
{
    ScriptFunction *fn = (ScriptFunction *)self;
    Py_CLEAR(fn->script);
    Py_CLEAR(fn->function);
    Chunk *chunk = bs_atomic_load(&fn->chunk);
    fn->chunk = NULL;
    chunk_free(chunk);
    return 0;
}


static void script_function_dealloc(PyObject *self)
{
    PyObject_GC_UnTrack(self);
    script_function_clear(self);
    PyObject_GC_Del(self);
}


static PyTypeObject ScriptFunction_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c.ScriptFunction",
    .tp_basicsize = sizeof(ScriptFunction),
    .tp_dealloc = script_function_dealloc,
    .tp_vectorcall_offset = offsetof(ScriptFunction, vectorcall),
    .tp_call = PyVectorcall_Call,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_HAVE_VECTORCALL,
    .tp_traverse = script_function_traverse,
    .tp_clear = script_function_clear,
};


// Get a script function's compiled body, compiling it on first call
static Chunk *script_function_chunk(ScriptFunction *fn)
{
    Chunk *chunk = bs_atomic_load(&fn->chunk);
    if (chunk != NULL) {
        return chunk;
    }
    // Watch the model dict before reading it
    int watched = 0;
    uint64_t epoch = 0;
#ifdef BS_MODEL_WATCH
    if (g_model_watcher >= 0) {
        if (PyDict_Watch(g_model_watcher, fn->function) < 0) {
            return NULL;
        }
        watched = 1;
        epoch = bs_atomic_load(&g_model_epoch);
    }
#endif
    PyObject *statements;
    int found = bs_dict_get(fn->function, S_statements, &statements);
    if (found < 0) {
        return NULL;
    }
    chunk = compile(MODE_FUNC, fn->script, found ? statements : Py_None, fn->function);
    Py_XDECREF(statements);
    if (chunk == NULL) {
        return NULL;
    }
    chunk->model_watched = watched && (chunk->args == NULL || chunk->last_arg_array_plain);
    bs_atomic_store(&chunk->model_epoch, epoch);
    Chunk *expected = NULL;
    if (!bs_atomic_publish(&fn->chunk, &expected, chunk)) {
        chunk_free(chunk);
        return expected;
    }
    return chunk;
}


// Are a compiled function body's model lists unchanged in place?
static int script_function_lists_current(Chunk *chunk)
{
    int current = PyList_GET_SIZE(chunk->statements) == chunk->nstatements;
    if (current && chunk->args != NULL) {
        Py_BEGIN_CRITICAL_SECTION(chunk->args);
        current = PyList_GET_SIZE(chunk->args) == chunk->nargs;
        for (int ix = 0; current && ix < chunk->nargs; ix++) {
            current = PyList_GET_ITEM(chunk->args, ix) == chunk->arg_items[ix];
        }
        Py_END_CRITICAL_SECTION();
    }
    return current;
}


// Is a function's compiled body still its model? runtime.py reads the function's statements and arguments on
// each call. Returns 1 current, 0 changed, -1 error.
static int script_function_current(ScriptFunction *fn, Chunk *chunk)
{
#ifdef BS_MODEL_WATCH
    uint64_t epoch = bs_atomic_load(&g_model_epoch);
    if (chunk->model_watched && bs_atomic_load(&chunk->model_epoch) == epoch) {
        return script_function_lists_current(chunk);
    }
#endif
    PyObject *statements, *args;
    int found = bs_dict_get(fn->function, S_statements, &statements);
    if (found <= 0) {
        return found;
    }
    int current = statements == chunk->statements;
    Py_DECREF(statements);
    found = current ? bs_dict_get(fn->function, S_args, &args) : 0;
    if (found < 0) {
        return -1;
    }
    if (current) {
        current = (!found || args == Py_None) ? chunk->args == NULL : args == chunk->args;
        Py_XDECREF(args);
    }
    if (current && chunk->args != NULL) {
        PyObject *last_arg_array = NULL;
        found = bs_dict_get(fn->function, S_lastArgArray, &last_arg_array);
        int truth = found > 0 ? PyObject_IsTrue(last_arg_array) : found;
        Py_XDECREF(last_arg_array);
        current = truth < 0 ? -1 : truth == chunk->last_arg_array;
    }
    if (current > 0) {
        current = script_function_lists_current(chunk);
#ifdef BS_MODEL_WATCH
        if (current && chunk->model_watched) {
            bs_atomic_store(&chunk->model_epoch, epoch);
        }
#endif
    }
    return current;
}


static PyObject *vm_run(Frame *f);


// Call a script function on runtime.py (its _script_function), for what the compiled body does not support
static PyObject *script_function_python(Ctx *ctx, ScriptFunction *fn, PyObject *args)
{
    PyObject *statements = PyObject_GetItem(fn->function, S_statements);
    PyObject *labels = statements != NULL ? runtime_call("_compute_label_indexes", statements, NULL) : NULL;
    Py_XDECREF(statements);
    if (labels == NULL || ctx_sync_out(ctx) < 0) {
        Py_XDECREF(labels);
        return NULL;
    }
    PyObject *result = runtime_call("_script_function", fn->script, fn->function, labels, args, ctx->options, NULL);
    Py_DECREF(labels);
    ctx_sync_in(ctx);
    return result;
}


// Call a script function - runtime.py's _script_function
static PyObject *script_function_call(Ctx *ctx, ScriptFunction *fn, PyObject *const *argv, Py_ssize_t argc,
                                      int args_none)
{
    Chunk *chunk = script_function_chunk(fn);
    if (chunk == NULL) {
        return NULL;
    }
    int current = !chunk->irregular && PyDict_CheckExact(ctx->options) ? script_function_current(fn, chunk) : 0;
    if (current < 0) {
        return NULL;
    }
    Frame frame = {0}, *f = &frame;
    int begin = current && !(args_none && chunk->args != NULL) ? frame_begin(f, ctx, chunk, fn->script) : 0;
    if (begin <= 0) {
        frame_end(f);
        if (begin < 0) {
            return NULL;
        }
        PyObject *args = args_none ? Py_NewRef(Py_None) : list_new(argv, argc);
        PyObject *result = args != NULL ? script_function_python(ctx, fn, args) : NULL;
        Py_XDECREF(args);
        return result;
    }

    // Bind the arguments - runtime.py's _script_function_locals
    PyObject *small[REGS_SMALL];
    PyObject **resident = regs_claim(chunk);
    PyObject **regs = resident != NULL ? resident : regs_alloc(chunk, small);
    PyObject *result = NULL;
    if (regs == NULL) {
        frame_end(f);
        return NULL;
    }
    int last = chunk->last_arg_array ? chunk->nargs - 1 : -1;
    for (int ix = 0; ix < chunk->nargs; ix++) {
        PyObject *value;
        if (ix == last) {
            value = list_new(argv + ix, ix < argc ? argc - ix : 0);
            if (value == NULL) {
                goto done;
            }
        } else {
            value = Py_NewRef(ix < argc ? argv[ix] : Py_None);
        }
        Py_XSETREF(regs[chunk->arg_slots[ix]], value);
    }

    f->regs = regs;
    if (Py_EnterRecursiveCall(" while calling a BareScript function") == 0) {
        result = vm_run(f);
        Py_LeaveRecursiveCall();
    }

done:
    if (resident != NULL) {
        regs_release(chunk, regs);
    } else {
        regs_free(chunk, regs, small);
    }
    frame_end(f);
    return result;
}


// Execute a script's statements on runtime.py (its _execute_script_helper)
static PyObject *execute_script_python(Ctx *ctx, PyObject *script)
{
    if (ctx_sync_out(ctx) < 0) {
        return NULL;
    }
    PyObject *statements = PyObject_GetItem(script, S_statements);
    PyObject *statements_labels = statements != NULL ? PyObject_GetItem(script, S_statements) : NULL;
    PyObject *labels = statements_labels != NULL ? runtime_call("_compute_label_indexes", statements_labels, NULL) : NULL;
    PyObject *result = labels != NULL ?
        runtime_call("_execute_script_helper", script, statements, ctx->options, Py_None, labels, NULL) : NULL;
    Py_XDECREF(statements);
    Py_XDECREF(statements_labels);
    Py_XDECREF(labels);
    ctx_sync_in(ctx);
    return result;
}


// Execute a script's top-level statements - runtime.py's _execute_script_helper without locals
static PyObject *execute_script_statements(Ctx *ctx, PyObject *script)
{
    Chunk *chunk = NULL;
    if (PyDict_CheckExact(script) && PyDict_CheckExact(ctx->options)) {
        PyObject *statements;
        int found = bs_dict_get(script, S_statements, &statements);
        if (found < 0) {
            return NULL;
        }
        if (found) {
            chunk = compile(MODE_TOP, script, statements, NULL);
            Py_DECREF(statements);
            if (chunk == NULL) {
                return NULL;
            }
        }
    }
    Frame frame = {0}, *f = &frame;
    int begin = chunk != NULL && !chunk->irregular ? frame_begin(f, ctx, chunk, script) : 0;
    PyObject *result = NULL;
    if (begin == 0) {
        result = execute_script_python(ctx, script);
    } else if (begin > 0) {
        PyObject *small[REGS_SMALL];
        PyObject **regs = regs_alloc(chunk, small);
        if (regs != NULL) {
            f->regs = regs;
            if (Py_EnterRecursiveCall(" while executing a BareScript script") == 0) {
                result = vm_run(f);
                Py_LeaveRecursiveCall();
            }
            regs_free(chunk, regs, small);
        }
    }
    frame_end(f);
    chunk_free(chunk);
    return result;
}


// Call a Python function object as a script function would be, from Python - (args, options)
static PyObject *script_function_vectorcall(PyObject *self, PyObject *const *args, size_t nargsf, PyObject *kwnames)
{
    ScriptFunction *fn = (ScriptFunction *)self;
    Py_ssize_t nargs = PyVectorcall_NARGS(nargsf);
    PyObject *result;
    if (kwnames != NULL || nargs != 2 || (args[0] != Py_None && !PyList_CheckExact(args[0]))) {
        // Anything else is runtime.py's function - functools.partial(_script_function, script, function, labels)
        PyObject *statements = PyObject_GetItem(fn->function, S_statements);
        PyObject *labels = statements != NULL ? runtime_call("_compute_label_indexes", statements, NULL) : NULL;
        PyObject *script_function = labels != NULL ? runtime_attr("_script_function") : NULL;
        PyObject *partial = script_function != NULL ?
            PyObject_CallFunctionObjArgs(g_partial, script_function, fn->script, fn->function, labels, NULL) : NULL;
        result = partial != NULL ? PyObject_Vectorcall(partial, args, nargsf, kwnames) : NULL;
        Py_XDECREF(statements);
        Py_XDECREF(labels);
        Py_XDECREF(script_function);
        Py_XDECREF(partial);
        return result;
    }

    Ctx ctx = {.options = args[1]};
    if (args[0] == Py_None) {
        result = script_function_call(&ctx, fn, NULL, 0, 1);
    } else {
#ifdef Py_GIL_DISABLED
        // Another thread could change the list - bind a snapshot
        PyObject *items = PyList_AsTuple(args[0]);
        result = items != NULL ?
            script_function_call(&ctx, fn, &PyTuple_GET_ITEM(items, 0), PyTuple_GET_SIZE(items), 0) : NULL;
        Py_XDECREF(items);
#else
        result = script_function_call(&ctx, fn, PySequence_Fast_ITEMS(args[0]), PyList_GET_SIZE(args[0]), 0);
#endif
    }
    ctx_exit(&ctx);
    return result;
}


//
// Function calls
//


// Handle a function call's exception - runtime.py's except clause: log it and return null, or the argument
// error's return value. Steals the exception reference.
static PyObject *call_error(Frame *f, const Inst *inst, PyObject *name, PyObject *exc)
{
    PyObject *options = f->ctx->options, *result = NULL;
    int log = 0;
    if (options != Py_None) {
        log = PyDict_CheckExact(options) ? PyDict_Contains(options, S_logFn) : PySequence_Contains(options, S_logFn);
        if (log > 0) {
            PyObject *debug = object_get(options, S_debug);
            log = debug != NULL ? PyObject_IsTrue(debug) : -1;
            Py_XDECREF(debug);
        }
    }
    if (log > 0) {
        PyObject *message = PyUnicode_FromFormat("BareScript: Function \"%U\" failed with error: %S", name, exc);
        PyObject *statement = message != NULL ? frame_statement(f, inst) : NULL;
        PyObject *error = statement != NULL ? PyObject_CallFunctionObjArgs(
            g_BareScriptRuntimeError, f->script != NULL ? f->script : Py_None, statement, message, NULL) : NULL;
        PyObject *error_str = error != NULL ? PyObject_Str(error) : NULL;
        PyObject *log_fn = error_str != NULL ? PyObject_GetItem(options, S_logFn) : NULL;
        PyObject *log_result = NULL;
        if (log_fn != NULL && ctx_sync_out(f->ctx) == 0) {
            log_result = PyObject_CallOneArg(log_fn, error_str);
            ctx_sync_in(f->ctx);
        }
        log = log_result != NULL ? 0 : -1;
        Py_XDECREF(message);
        Py_XDECREF(statement);
        Py_XDECREF(error);
        Py_XDECREF(error_str);
        Py_XDECREF(log_fn);
        Py_XDECREF(log_result);
    }
    if (log == 0) {
        int is_args_error = PyObject_IsInstance(exc, g_ValueArgsError);
        result = is_args_error > 0 ? PyObject_GetAttr(exc, S_return_value) :
            (is_args_error == 0 ? Py_NewRef(Py_None) : NULL);
    }
    Py_DECREF(exc);
    return result;
}


// Handle a function call's raised exception - BareScriptRuntimeError and non-Exception exceptions propagate
static PyObject *call_failed(Frame *f, const Inst *inst, PyObject *name)
{
    if (!PyErr_ExceptionMatches(PyExc_Exception) || PyErr_ExceptionMatches(g_BareScriptRuntimeError)) {
        return NULL;
    }
    return call_error(f, inst, name, bs_err_fetch());
}


// A library function replica's result when it does not handle the arguments - the library function is called
static PyObject call_deferred;
#define DEFER (&call_deferred)


// A string index argument on a replica's happy path - an exact int or integral float, 0 to a limit. Returns 1 and
// the index, or 0.
static int replica_index(PyObject *value, Py_ssize_t limit, Py_ssize_t *index)
{
    if (PyLong_CheckExact(value)) {
        long long number;
        if (!small_int(value, &number) || number < 0 || number > limit) {
            return 0;
        }
        *index = (Py_ssize_t)number;
        return 1;
    }
    if (PyFloat_CheckExact(value)) {
        double number = PyFloat_AS_DOUBLE(value);
        if (!(number >= 0 && number <= (double)limit && number < 9223372036854775808.0) || floor(number) != number) {
            return 0;
        }
        *index = (Py_ssize_t)number;
        return 1;
    }
    return 0;
}


// Run a library intrinsic inline - runtime.py's intrinsic fast path, for exact-type arguments of a valid shape. Other
// arguments return DEFER, for the intrinsic's library function, whose results and errors match the fast path's.
static PyObject *call_intrinsic(Frame *f, const Inst *inst, PyObject *name, PyObject *const *argv, Py_ssize_t argc,
                                int args_none)
{
    if (inst->x == IN_ARRAY_NEW) {
        return args_none ? Py_NewRef(Py_None) : list_new(argv, argc);
    }
    if (args_none) {
        // len(None)
        PyObject_Length(Py_None);
        return call_failed(f, inst, name);
    }

    PyObject *arg0 = argc >= 1 ? argv[0] : NULL, *arg1 = argc >= 2 ? argv[1] : NULL, *result = DEFER;
    Py_ssize_t index;
    long long number;

    switch (inst->x) {
    case IN_OBJECT_GET:
        if (argc >= 2 && argc <= 3 && PyDict_CheckExact(arg0) && PyUnicode_CheckExact(arg1)) {
            int found = bs_dict_get(arg0, arg1, &result);
            result = found == 0 ? Py_NewRef(argc == 3 ? argv[2] : Py_None) : result;
        }
        break;
    case IN_OBJECT_HAS:
        if (argc == 2 && PyDict_CheckExact(arg0) && PyUnicode_CheckExact(arg1)) {
            int has = PyDict_Contains(arg0, arg1);
            result = has < 0 ? NULL : PyBool_FromLong(has);
        }
        break;
    case IN_ARRAY_GET:
        if (argc == 2 && PyList_CheckExact(arg0) && replica_index(arg1, PyList_GET_SIZE(arg0) - 1, &index)) {
            result = bs_list_get(arg0, index);
        }
        break;
    case IN_ARRAY_SET:
        if (argc >= 2 && argc <= 3 && PyList_CheckExact(arg0) && replica_index(arg1, PyList_GET_SIZE(arg0) - 1, &index)) {
            PyObject *value = argc == 3 ? argv[2] : Py_None;
            result = PyList_SetItem(arg0, index, Py_NewRef(value)) < 0 ? NULL : Py_NewRef(value);
        }
        break;
    case IN_ARRAY_LENGTH:
        if (argc == 1 && PyList_CheckExact(arg0)) {
            result = PyLong_FromSsize_t(PyList_GET_SIZE(arg0));
        }
        break;
    case IN_ARRAY_PUSH:
        if (argc == 2 && PyList_CheckExact(arg0)) {
            result = PyList_Append(arg0, arg1) < 0 ? NULL : Py_NewRef(arg0);
        } else if (argc >= 1 && PyList_CheckExact(arg0)) {
            PyObject *items = list_new(argv + 1, argc - 1);
            int rc = items != NULL ? PyList_SetSlice(arg0, PY_SSIZE_T_MAX, PY_SSIZE_T_MAX, items) : -1;
            Py_XDECREF(items);
            result = rc < 0 ? NULL : Py_NewRef(arg0);
        }
        break;
    case IN_OBJECT_SET:
        if (argc >= 2 && argc <= 3 && PyDict_CheckExact(arg0) && PyUnicode_CheckExact(arg1)) {
            PyObject *value = argc == 3 ? argv[2] : Py_None;
            result = PyDict_SetItem(arg0, arg1, value) < 0 ? NULL : Py_NewRef(value);
            ctx_dict_changed(f->ctx, arg0);
            if (arg0 == f->globals) {
                globals_changed();
            }
        }
        break;
    case IN_STRING_LENGTH:
        if (argc == 1 && PyUnicode_CheckExact(arg0)) {
            result = PyLong_FromSsize_t(PyUnicode_GET_LENGTH(arg0));
        }
        break;
    case IN_SYSTEM_TYPE:
        if (argc <= 1) {
            result = Py_NewRef(value_type(argc == 1 ? arg0 : Py_None));
        }
        break;
    case IN_OBJECT_KEYS:
        if (argc == 1 && PyDict_CheckExact(arg0)) {
            result = PyDict_Keys(arg0);
        }
        break;
    default: // IN_MATH_SQRT
        if (argc == 1 && PyFloat_CheckExact(arg0) && PyFloat_AS_DOUBLE(arg0) >= 0) {
            result = PyFloat_FromDouble(sqrt(PyFloat_AS_DOUBLE(arg0)));
        } else if (argc == 1 && PyLong_CheckExact(arg0) && small_int(arg0, &number) && number >= 0) {
            result = PyFloat_FromDouble(sqrt((double)number));
        }
        break;
    }
    return result != NULL ? result : call_failed(f, inst, name);
}


// The library's _regex_match_groups - a regex match object's model
static PyObject *regex_match_groups(PyObject *match)
{
    PyObject *groups = PyDict_New(), *match_text = NULL, *group_texts = NULL, *group_dict = NULL, *index = NULL,
        *input = NULL, *result = NULL;
    if (groups == NULL || (match_text = PyObject_GetItem(match, g_zero)) == NULL ||
        PyDict_SetItem(groups, g_group_keys[0], match_text) < 0 ||
        (group_texts = PyObject_CallMethodNoArgs(match, S_groups)) == NULL) {
        goto done;
    }
    for (Py_ssize_t ix = 0; ix < PyTuple_GET_SIZE(group_texts); ix++) {
        PyObject *key = ix < 9 ? Py_NewRef(g_group_keys[ix + 1]) : digits_string((unsigned long long)ix + 1, 0, 10);
        int rc = key != NULL ? PyDict_SetItem(groups, key, PyTuple_GET_ITEM(group_texts, ix)) : -1;
        Py_XDECREF(key);
        if (rc < 0) {
            goto done;
        }
    }
    if ((group_dict = PyObject_CallMethodNoArgs(match, S_groupdict)) == NULL || PyDict_Update(groups, group_dict) < 0 ||
        (index = PyObject_CallMethodNoArgs(match, S_start)) == NULL ||
        (input = PyObject_GetAttr(match, S_string)) == NULL) {
        goto done;
    }
    if ((result = PyDict_New()) == NULL || PyDict_SetItem(result, S_index, index) < 0 ||
        PyDict_SetItem(result, S_input, input) < 0 || PyDict_SetItem(result, S_groups, groups) < 0) {
        Py_CLEAR(result);
    }

done:
    Py_XDECREF(groups);
    Py_XDECREF(match_text);
    Py_XDECREF(group_texts);
    Py_XDECREF(group_dict);
    Py_XDECREF(index);
    Py_XDECREF(input);
    return result;
}


// Match a number string - value.py's R_NUMBER (radix 0) or a VALUE_PARSE_INTEGER_REGEX_MAP integer regex
static int number_text_match(PyObject *text, int radix)
{
    int kind = PyUnicode_KIND(text);
    const void *data = PyUnicode_DATA(text);
    Py_ssize_t length = PyUnicode_GET_LENGTH(text), ix = 0, digits = 0;
#define TEXT_CHAR() (ix < length ? PyUnicode_READ(kind, data, ix) : 0)
#define TEXT_DIGITS() \
    for (; ix < length && TEXT_CHAR() >= '0' && TEXT_CHAR() <= '9'; ix++) { \
        digits++; \
    }
    while (ix < length && Py_UNICODE_ISSPACE(TEXT_CHAR())) {
        ix++;
    }
    if (TEXT_CHAR() == '-' || TEXT_CHAR() == '+') {
        ix++;
    }
    if (radix == 0) {
        TEXT_DIGITS()
        if (TEXT_CHAR() == '.') {
            ix++;
            Py_ssize_t int_digits = digits;
            TEXT_DIGITS()
            if (int_digits == 0 && digits == 0) {
                return 0;
            }
        }
        if (digits == 0) {
            return 0;
        }
        if (TEXT_CHAR() == 'e' || TEXT_CHAR() == 'E') {
            ix++;
            if (TEXT_CHAR() == '-' || TEXT_CHAR() == '+') {
                ix++;
            }
            digits = 0;
            TEXT_DIGITS()
            if (digits == 0) {
                return 0;
            }
        }
    } else {
        for (; ix < length; ix++, digits++) {
            Py_UCS4 ch = TEXT_CHAR();
            int digit = ch >= '0' && ch <= '9' ? (int)(ch - '0') : (ch >= 'A' && ch <= 'Z' ? (int)(ch - 'A' + 10) :
                (ch >= 'a' && ch <= 'z' ? (int)(ch - 'a' + 10) : 99));
            if (digit >= radix) {
                break;
            }
        }
        if (digits == 0) {
            return 0;
        }
    }
    while (ix < length && Py_UNICODE_ISSPACE(TEXT_CHAR())) {
        ix++;
    }
    return ix == length;
#undef TEXT_CHAR
#undef TEXT_DIGITS
}


// Run a library function replica - the library function's result for the exact types and valid arguments of its
// happy path; DEFER for anything else, which calls the library function itself
// A value as library jsonStringify normalizes it for encoding - an integral float is an integer and a non-finite
// float null - or DEFER for a small float (which it formats separately), a non-JSON value, or nesting past 64
static PyObject *json_normalize(PyObject *value, int depth)
{
    if (PyFloat_CheckExact(value)) {
        double number = PyFloat_AS_DOUBLE(value);
        if (!isfinite(number)) {
            return Py_NewRef(Py_None);
        }
        if (floor(number) == number && fabs(number) < 1e21) {
            return PyLong_FromDouble(number);
        }
        return fabs(number) < 1e-4 ? DEFER : Py_NewRef(value);
    }
    if (PyUnicode_CheckExact(value) || PyLong_CheckExact(value) || PyBool_Check(value) || value == Py_None) {
        return Py_NewRef(value);
    }
    if (depth >= 64 || !(PyList_CheckExact(value) || PyDict_CheckExact(value))) {
        return DEFER;
    }
    PyObject *result;
    Py_BEGIN_CRITICAL_SECTION(value);
    if (PyList_CheckExact(value)) {
        result = PyList_New(PyList_GET_SIZE(value));
        for (Py_ssize_t ix = 0; result != NULL && result != DEFER && ix < PyList_GET_SIZE(value); ix++) {
            PyObject *item = json_normalize(PyList_GET_ITEM(value, ix), depth + 1);
            if (item == NULL || item == DEFER) {
                Py_DECREF(result);
                result = item;
            } else {
                PyList_SET_ITEM(result, ix, item);
            }
        }
    } else {
        result = PyDict_New();
        Py_ssize_t pos = 0;
        PyObject *key, *item;
        while (result != NULL && result != DEFER && PyDict_Next(value, &pos, &key, &item)) {
            PyObject *normal = json_normalize(item, depth + 1);
            if (normal == NULL || normal == DEFER || PyDict_SetItem(result, key, normal) < 0) {
                Py_DECREF(result);
                result = normal == DEFER ? DEFER : NULL;
            }
            if (normal != DEFER) {
                Py_XDECREF(normal);
            }
        }
    }
    Py_END_CRITICAL_SECTION();
    return result;
}


// Does a string have a run of 309 or more digits - an integer past the double range, which library jsonParse nulls?
static int json_long_digits(PyObject *text)
{
    int kind = PyUnicode_KIND(text);
    const void *data = PyUnicode_DATA(text);
    Py_ssize_t length = PyUnicode_GET_LENGTH(text), run = 0;
    for (Py_ssize_t ix = 0; ix < length; ix++) {
        Py_UCS4 ch = PyUnicode_READ(kind, data, ix);
        run = ch >= '0' && ch <= '9' ? run + 1 : 0;
        if (run >= 309) {
            return 1;
        }
    }
    return 0;
}


static PyObject *call_library(Ctx *ctx, int id, PyObject *const *argv, Py_ssize_t argc, int args_none)
{
    if (args_none) {
        return DEFER;
    }
    PyObject *arg0 = argc >= 1 ? argv[0] : NULL, *arg1 = argc >= 2 ? argv[1] : NULL;
    Py_ssize_t start, end;
    switch (id) {
    case IN_JSON_PARSE:
    case IN_JSON_STRINGIFY: {
        // The library's own JSON coders - jsonParse without its per-integer hook, which only nulls integers past the
        // double range, and jsonStringify of the library's normalized value. An error defers, so the library raises it.
        PyObject *value;
        if (id == IN_JSON_PARSE) {
            value = argc == 1 && PyUnicode_CheckExact(arg0) && !json_long_digits(arg0) ? Py_NewRef(arg0) : DEFER;
        } else {
            value = argc >= 1 && argc <= 2 && (argc == 1 || arg1 == Py_None) ? json_normalize(arg0, 0) : DEFER;
        }
        if (value == NULL || value == DEFER) {
            return value;
        }
        PyObject *result = PyObject_CallOneArg(id == IN_JSON_PARSE ? g_json_decode : g_json_encode, value);
        Py_DECREF(value);
        if (result == NULL) {
            PyErr_Clear();
            return DEFER;
        }
        return result;
    }
    case IN_OBJECT_NEW: {
        for (Py_ssize_t ix = 0; ix < argc; ix += 2) {
            if (!PyUnicode_CheckExact(argv[ix])) {
                return DEFER;
            }
        }
        PyObject *object = PyDict_New();
        for (Py_ssize_t ix = 0; object != NULL && ix < argc; ix += 2) {
            if (PyDict_SetItem(object, argv[ix], ix + 1 < argc ? argv[ix + 1] : Py_None) < 0) {
                Py_CLEAR(object);
            }
        }
        return object;
    }
    case IN_STRING_SLICE:
    case IN_ARRAY_SLICE: {
        // A string's or list's slice - a start index and an optional end index, each 0 to its length
        int is_string = id == IN_STRING_SLICE;
        if (argc < 2 || argc > 3 || !(is_string ? PyUnicode_CheckExact(arg0) : PyList_CheckExact(arg0))) {
            return DEFER;
        }
        Py_ssize_t length = is_string ? PyUnicode_GET_LENGTH(arg0) : PyList_GET_SIZE(arg0);
        end = length;
        if (!replica_index(arg1, length, &start) ||
            (argc == 3 && argv[2] != Py_None && !replica_index(argv[2], length, &end))) {
            return DEFER;
        }
        return is_string ? PyUnicode_Substring(arg0, start, end) : PyList_GetSlice(arg0, start, end);
    }
    case IN_STRING_INDEX_OF:
        if (argc < 2 || argc > 3 || !PyUnicode_CheckExact(arg0) || !PyUnicode_CheckExact(arg1)) {
            return DEFER;
        }
        start = 0;
        if (argc == 3 && !replica_index(argv[2], PyUnicode_GET_LENGTH(arg0), &start)) {
            return DEFER;
        }
        end = PyUnicode_Find(arg0, arg1, start, PY_SSIZE_T_MAX, 1);
        return end < -1 ? NULL : PyLong_FromSsize_t(end);
    case IN_STRING_STARTS_WITH:
    case IN_STRING_ENDS_WITH: {
        if (argc != 2 || !PyUnicode_CheckExact(arg0) || !PyUnicode_CheckExact(arg1)) {
            return DEFER;
        }
        Py_ssize_t match = PyUnicode_Tailmatch(arg0, arg1, 0, PY_SSIZE_T_MAX, id == IN_STRING_STARTS_WITH ? -1 : 1);
        return match < 0 ? NULL : PyBool_FromLong(match);
    }
    case IN_STRING_TRIM: {
        if (argc != 1 || !PyUnicode_CheckExact(arg0)) {
            return DEFER;
        }
        int kind = PyUnicode_KIND(arg0);
        const void *data = PyUnicode_DATA(arg0);
        start = 0;
        end = PyUnicode_GET_LENGTH(arg0);
        while (start < end && Py_UNICODE_ISSPACE(PyUnicode_READ(kind, data, start))) {
            start++;
        }
        while (end > start && Py_UNICODE_ISSPACE(PyUnicode_READ(kind, data, end - 1))) {
            end--;
        }
        return PyUnicode_Substring(arg0, start, end);
    }
    case IN_STRING_CHAR_AT:
    case IN_STRING_CHAR_CODE_AT:
        if (argc != 2 || !PyUnicode_CheckExact(arg0) || PyUnicode_GET_LENGTH(arg0) == 0 ||
            !replica_index(arg1, PyUnicode_GET_LENGTH(arg0) - 1, &start)) {
            return DEFER;
        }
        return id == IN_STRING_CHAR_AT ? PySequence_GetItem(arg0, start) :
            PyLong_FromLong((long)PyUnicode_READ_CHAR(arg0, start));
    case IN_MATH_MIN:
    case IN_MATH_MAX: {
        // The first value, replaced by each value comparing less (greater) - value_compare of numbers
        PyObject *result = Py_None;
        for (Py_ssize_t ix = 0; ix < argc; ix++) {
            if (!IS_NUMBER(argv[ix])) {
                return DEFER;
            }
            if (ix == 0) {
                result = argv[ix];
                continue;
            }
            int less = number_compare(argv[ix], result, Py_LT);
            int equal = less == 0 ? number_compare(argv[ix], result, Py_EQ) : 0;
            if (less < 0 || equal < 0) {
                return NULL;
            }
            if (id == IN_MATH_MIN ? less : !less && !equal) {
                result = argv[ix];
            }
        }
        return Py_NewRef(result);
    }
    case IN_ARRAY_JOIN: {
        // separator.join(value_string(value) for value in array)
        if (argc != 2 || !PyList_CheckExact(arg0) || !PyUnicode_CheckExact(arg1)) {
            return DEFER;
        }
        PyObject *strings = PySequence_List(arg0);
        for (Py_ssize_t ix = 0; strings != NULL && ix < PyList_GET_SIZE(strings); ix++) {
            PyObject *string = value_string(PyList_GET_ITEM(strings, ix));
            if (string == NULL) {
                Py_CLEAR(strings);
            } else {
                Py_SETREF(PyList_GET_ITEM(strings, ix), string);
            }
        }
        PyObject *result = strings != NULL ? PyUnicode_Join(arg1, strings) : NULL;
        Py_XDECREF(strings);
        return result;
    }
    case IN_ARRAY_EXTEND:
        if (argc != 2 || !PyList_CheckExact(arg0) || !PyList_CheckExact(arg1)) {
            return DEFER;
        }
        return PyList_SetSlice(arg0, PY_SSIZE_T_MAX, PY_SSIZE_T_MAX, arg1) < 0 ? NULL : Py_NewRef(arg0);
    case IN_REGEX_MATCH:
    case IN_REGEX_MATCH_ALL: {
        if (argc != 2 || !Py_IS_TYPE(arg0, (PyTypeObject *)g_REGEX_TYPE) || !PyUnicode_CheckExact(arg1)) {
            return DEFER;
        }
        if (id == IN_REGEX_MATCH) {
            PyObject *match = PyObject_CallMethodOneArg(arg0, S_search, arg1);
            PyObject *result = match != NULL && match != Py_None ? regex_match_groups(match) : Py_XNewRef(match);
            Py_XDECREF(match);
            return result;
        }
        PyObject *matches = PyObject_CallMethodOneArg(arg0, S_finditer, arg1), *match;
        PyObject *result = matches != NULL ? PyList_New(0) : NULL;
        while (result != NULL && (match = PyIter_Next(matches)) != NULL) {
            PyObject *groups = regex_match_groups(match);
            if (groups == NULL || PyList_Append(result, groups) < 0) {
                Py_CLEAR(result);
            }
            Py_XDECREF(groups);
            Py_DECREF(match);
        }
        if (PyErr_Occurred()) {
            Py_CLEAR(result);
        }
        Py_XDECREF(matches);
        return result;
    }
    case IN_NUMBER_PARSE_INT:
    case IN_NUMBER_PARSE_FLOAT: {
        // value.py's value_parse_integer and value_parse_number
        Py_ssize_t radix = 10;
        if (argc < 1 || argc > (id == IN_NUMBER_PARSE_INT ? 2 : 1) || !PyUnicode_CheckExact(arg0) ||
            (argc == 2 && (!replica_index(arg1, 36, &radix) || radix < 2))) {
            return DEFER;
        }
        if (!number_text_match(arg0, id == IN_NUMBER_PARSE_INT ? (int)radix : 0)) {
            return Py_NewRef(Py_None);
        }
        if (id == IN_NUMBER_PARSE_FLOAT) {
            PyObject *value = PyFloat_FromString(arg0);
            return value == NULL || isfinite(PyFloat_AS_DOUBLE(value)) ? value : (Py_DECREF(value), Py_NewRef(Py_None));
        }
        return arithmetic_result(PyLong_FromUnicodeObject(arg0, (int)radix));
    }
    case IN_STRING_SPLIT:
        if (argc != 2 || !PyUnicode_CheckExact(arg0) || !PyUnicode_CheckExact(arg1)) {
            return DEFER;
        }
        return PyUnicode_GET_LENGTH(arg1) == 0 ? PySequence_List(arg0) : PyUnicode_Split(arg0, arg1, -1);
    case IN_STRING_ENCODE: {
        if (argc != 1 || !PyUnicode_CheckExact(arg0)) {
            return DEFER;
        }
        // A string with unpaired surrogates defers to the library function
        PyObject *encoded = PyUnicode_AsUTF8String(arg0);
        if (encoded == NULL) {
            PyErr_Clear();
            return DEFER;
        }
        PyObject *result = PyList_New(PyBytes_GET_SIZE(encoded));
        for (Py_ssize_t ix = 0; result != NULL && ix < PyBytes_GET_SIZE(encoded); ix++) {
            PyObject *byte = PyLong_FromLong((unsigned char)PyBytes_AS_STRING(encoded)[ix]);
            if (byte == NULL) {
                Py_CLEAR(result);
            } else {
                PyList_SET_ITEM(result, ix, byte);
            }
        }
        Py_XDECREF(encoded);
        return result;
    }
    case IN_STRING_DECODE: {
        if (argc != 1 || !PyList_CheckExact(arg0)) {
            return DEFER;
        }
        PyObject *items = PySequence_Tuple(arg0);
        if (items == NULL) {
            return NULL;
        }
        Py_ssize_t count = PyTuple_GET_SIZE(items);
        char *bytes = PyMem_Malloc(count + 1);
        int bytes_ok = bytes != NULL;
        for (Py_ssize_t ix = 0; bytes_ok && ix < count; ix++) {
            long byte;
            PyObject *item = PyTuple_GET_ITEM(items, ix);
            bytes_ok = PyLong_CheckExact(item) && (byte = PyLong_AsLong(item)) >= 0 && byte <= 255;
            if (bytes_ok) {
                bytes[ix] = (char)byte;
            }
        }
        PyObject *result = DEFER;
        if (bytes == NULL) {
            result = PyErr_NoMemory();
        } else if (bytes_ok) {
            result = PyUnicode_DecodeUTF8(bytes, count, NULL);
            if (result == NULL && PyErr_ExceptionMatches(PyExc_ValueError)) {
                PyErr_Clear();
                result = Py_NewRef(Py_None);
            }
        } else {
            // An int too large for a long
            PyErr_Clear();
        }
        PyMem_Free(bytes);
        Py_DECREF(items);
        return result;
    }
    case IN_STRING_REPLACE:
        if (argc != 3 || !PyUnicode_CheckExact(arg0) || !PyUnicode_CheckExact(arg1) || !PyUnicode_CheckExact(argv[2])) {
            return DEFER;
        }
        return PyUnicode_Replace(arg0, arg1, argv[2], -1);
    case IN_STRING_LOWER:
    case IN_STRING_UPPER:
        if (argc != 1 || !PyUnicode_CheckExact(arg0)) {
            return DEFER;
        }
        return PyObject_CallMethodNoArgs(arg0, id == IN_STRING_LOWER ? S_lower : S_upper);
    case IN_STRING_NEW:
        return argc <= 1 ? value_string(argc == 1 ? arg0 : Py_None) : DEFER;
    case IN_ARRAY_REVERSE:
        if (argc != 1 || !PyList_CheckExact(arg0)) {
            return DEFER;
        }
        return PyList_Reverse(arg0) < 0 ? NULL : Py_NewRef(arg0);
    case IN_ARRAY_COPY:
        return argc == 1 && PyList_CheckExact(arg0) ? PyList_GetSlice(arg0, 0, PY_SSIZE_T_MAX) : DEFER;
    case IN_OBJECT_DELETE: {
        if (argc != 2 || !PyDict_CheckExact(arg0) || !PyUnicode_CheckExact(arg1)) {
            return DEFER;
        }
        int has = PyDict_Contains(arg0, arg1);
        globals_changed();
        ctx_dict_changed(ctx, arg0);
        return has < 0 || (has && PyDict_DelItem(arg0, arg1) < 0) ? NULL : Py_NewRef(Py_None);
    }
    case IN_OBJECT_ASSIGN:
        if (argc != 2 || !PyDict_CheckExact(arg0) || !PyDict_CheckExact(arg1)) {
            return DEFER;
        }
        globals_changed();
        ctx_dict_changed(ctx, arg0);
        return PyDict_Update(arg0, arg1) < 0 ? NULL : Py_NewRef(arg0);
    case IN_OBJECT_COPY:
        return argc == 1 && PyDict_CheckExact(arg0) ? PyDict_Copy(arg0) : DEFER;
    case IN_SYSTEM_BOOLEAN: {
        if (argc > 1) {
            return DEFER;
        }
        int truth = value_boolean(argc == 1 ? arg0 : Py_None);
        return truth < 0 ? NULL : PyBool_FromLong(truth);
    }
    case IN_MATH_ABS:
    case IN_MATH_CEIL:
    case IN_MATH_FLOOR: {
        if (argc != 1 || !IS_NUMBER(arg0)) {
            return DEFER;
        }
        if (PyLong_CheckExact(arg0)) {
            return id == IN_MATH_ABS ? PyNumber_Absolute(arg0) : Py_NewRef(arg0);
        }
        if (id == IN_MATH_ABS) {
            return PyFloat_FromDouble(fabs(PyFloat_AS_DOUBLE(arg0)));
        }
        double number = PyFloat_AS_DOUBLE(arg0);
        return isfinite(number) ? PyLong_FromDouble(id == IN_MATH_CEIL ? ceil(number) : floor(number)) : DEFER;
    }
    case IN_REGEX_REPLACE: {
        // The library's JavaScript-to-Python replacement translation, for a replacement without "\\" whose every "$"
        // starts a group number ("$1") - each "$" becomes "\\"
        if (argc != 3 || !Py_IS_TYPE(arg0, (PyTypeObject *)g_REGEX_TYPE) || !PyUnicode_CheckExact(arg1) ||
            !PyUnicode_CheckExact(argv[2])) {
            return DEFER;
        }
        PyObject *replacement = argv[2];
        int kind = PyUnicode_KIND(replacement), dollars = 0;
        const void *data = PyUnicode_DATA(replacement);
        Py_ssize_t length = PyUnicode_GET_LENGTH(replacement);
        for (Py_ssize_t ix = 0; ix < length; ix++) {
            Py_UCS4 ch = PyUnicode_READ(kind, data, ix);
            if (ch == '\\') {
                return DEFER;
            }
            if (ch == '$') {
                Py_UCS4 next = ix + 1 < length ? PyUnicode_READ(kind, data, ix + 1) : 0;
                if (next < '0' || next > '9') {
                    return DEFER;
                }
                dollars = 1;
            }
        }
        replacement = dollars ? PyUnicode_Replace(replacement, S_dollar, S_backslash, -1) : Py_NewRef(replacement);
        PyObject *result = replacement != NULL ? PyObject_CallMethodObjArgs(arg0, S_sub, replacement, arg1, NULL) : NULL;
        Py_XDECREF(replacement);
        return result;
    }
    case IN_REGEX_ESCAPE:
        return argc == 1 && PyUnicode_CheckExact(arg0) ? PyObject_CallOneArg(g_re_escape, arg0) : DEFER;
    case IN_ARRAY_NEW_SIZE: {
        Py_ssize_t size = 0;
        if (argc > 2 || (argc >= 1 && !replica_index(arg0, PY_SSIZE_T_MAX / 16, &size))) {
            return DEFER;
        }
        PyObject *value = argc == 2 ? arg1 : g_zero, *result = PyList_New(size);
        for (Py_ssize_t ix = 0; result != NULL && ix < size; ix++) {
            PyList_SET_ITEM(result, ix, Py_NewRef(value));
        }
        return result;
    }
    case IN_NUMBER_TO_STRING: {
        // The digits of a non-negative integer in a radix
        Py_ssize_t value, radix = 10;
        if (argc < 1 || argc > 2 || !replica_index(arg0, PY_SSIZE_T_MAX, &value) ||
            (argc == 2 && (!replica_index(arg1, 36, &radix) || radix < 2))) {
            return DEFER;
        }
        return digits_string((unsigned long long)value, 0, (int)radix);
    }
    default: { // IN_SYSTEM_GLOBAL_GET, IN_SYSTEM_GLOBAL_SET
        // The globals - options.get('globals')
        PyObject *globals = NULL, *result = DEFER;
        if (argc < 1 || argc > 2 || !PyUnicode_CheckExact(arg0) || !PyDict_CheckExact(ctx->options)) {
            return DEFER;
        }
        if (bs_dict_get(ctx->options, S_globals, &globals) < 0) {
            return NULL;
        }
        PyObject *value = argc == 2 ? arg1 : Py_None;
        if (globals == NULL || globals == Py_None) {
            result = Py_NewRef(value);
        } else if (PyDict_CheckExact(globals)) {
            if (id == IN_SYSTEM_GLOBAL_GET) {
                int found = bs_dict_get(globals, arg0, &result);
                if (found == 0) {
                    result = Py_NewRef(value);
                }
            } else {
                result = PyDict_SetItem(globals, arg0, value) < 0 ? NULL : Py_NewRef(value);
                ctx_invalidate(ctx);
                globals_changed();
            }
        }
        Py_XDECREF(globals);
        return result;
    }
    }
}


// Call a function value
static BS_INLINE PyObject *call_function(Frame *f, const Inst *inst, PyObject *name, PyObject *func, PyObject *const *argv,
                               Py_ssize_t argc, int args_none)
{
    // An intrinsic call site - runtime.py's intrinsic by the call's name, or a library function replica
    if (inst->x != IN_NONE) {
        if (inst->x < IN_LIBRARY) {
            if (func == g_intrinsic_fns[inst->x] || is_intrinsic_fn(func)) {
                PyObject *result = call_intrinsic(f, inst, name, argv, argc, args_none);
                if (result != DEFER) {
                    return result;
                }
                func = g_intrinsic_fns[inst->x];
            }
        } else if (func == g_intrinsic_fns[inst->x]) {
            PyObject *result = call_library(f->ctx, inst->x, argv, argc, args_none);
            if (result != DEFER) {
                return result != NULL ? result : call_failed(f, inst, name);
            }
        }
    }
    if (Py_IS_TYPE(func, &ScriptFunction_Type)) {
        PyObject *result = script_function_call(f->ctx, (ScriptFunction *)func, argv, argc, args_none);
        return result != NULL ? result : call_failed(f, inst, name);
    }
    if (is_intrinsic_fn(func)) {
        // runtime.py's intrinsic fast path takes the argument count (len(None)) whatever the call's name
        if (args_none) {
            return call_intrinsic(f, inst, name, argv, argc, args_none);
        }
    } else if (PySet_Contains(g_INTRINSICS, func) < 0) {
        // runtime.py's intrinsic set membership test raises for an unhashable value
        return call_failed(f, inst, name);
    }

    // Call the function with the argument list and the options
    PyObject *args = args_none ? Py_NewRef(Py_None) : list_new(argv, argc);
    if (args == NULL || ctx_sync_out(f->ctx) < 0) {
        Py_XDECREF(args);
        return NULL;
    }
    PyObject *call_args[2] = {args, f->ctx->options};
    PyObject *result = PyObject_Vectorcall(func, call_args, 2, NULL);
    Py_DECREF(args);
    ctx_sync_in(f->ctx);
    return result != NULL ? result : call_failed(f, inst, name);
}


// The number of call arguments gathered on the C stack before the heap
#define ARGV_SMALL 16


#ifdef BS_CALL_CACHE
// A call name's entry in a context's call cache
static inline CallCache *call_cache_entry(Ctx *ctx, PyObject *name)
{
    uintptr_t hash = (uintptr_t)name >> 4;
    return &ctx->call_cache[(hash ^ (hash >> 7)) & (CALL_CACHE_SIZE - 1)];
}
#endif


// Gather a call instruction's arguments - argv is argv_small, or a new array, or NULL on error
static PyObject **vm_call_args(Frame *f, const Inst *inst, PyObject **argv_small)
{
    Py_ssize_t argc = inst->c == ARGS_NONE ? 0 : inst->c;
    PyObject **argv = argc > ARGV_SMALL ? PyMem_Malloc(argc * sizeof(PyObject *)) : argv_small;
    if (argv == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    const Inst *data = inst + 1;
    for (Py_ssize_t ix = 0; ix < argc; ix += 3, data++) {
        argv[ix] = f->regs[data->a];
        if (ix + 1 < argc) {
            argv[ix + 1] = f->regs[data->b];
        }
        if (ix + 2 < argc) {
            argv[ix + 2] = f->regs[data->c];
        }
    }
    return argv;
}


// The intrinsic call fast path - an intrinsic call site whose function the context's call cache resolves runs its
// common argument shapes on exact types here, and anything else as the intrinsic. Returns DEFER for the general
// call.
static BS_NOINLINE PyObject *vm_call_intrinsic(Frame *f, const Inst *inst)
{
#ifdef BS_CALL_CACHE
    Ctx *ctx = f->ctx;
    if (ctx->call_cache == NULL) {
        return DEFER;
    }
    PyObject *name = f->chunk->names[inst->b];
    CallCache *cache = call_cache_entry(ctx, name);
    PyObject *func = cache->func;
    if (cache->name != name || cache->globals != f->globals || cache->epoch != g_globals_epoch ||
        (inst->x < IN_LIBRARY ? func != g_intrinsic_fns[inst->x] && !is_intrinsic_fn(func) :
         func != g_intrinsic_fns[inst->x])) {
        return DEFER;
    }
    PyObject **regs = f->regs;
    const Inst *data = inst + 1;
    PyObject *arg0 = regs[data->a], *arg1 = regs[data->b], *value;
    Py_ssize_t index;
    switch (inst->x * 4 + (inst->c == ARGS_NONE ? 3 : (inst->c > 3 ? 3 : inst->c))) {
    case IN_OBJECT_GET * 4 + 2:
        if (PyDict_CheckExact(arg0) && PyUnicode_CheckExact(arg1)) {
            int found = bs_dict_get(arg0, arg1, &value);
            return found < 0 ? NULL : (found ? value : Py_NewRef(Py_None));
        }
        break;
    case IN_OBJECT_HAS * 4 + 2:
        if (PyDict_CheckExact(arg0) && PyUnicode_CheckExact(arg1)) {
            int has = PyDict_Contains(arg0, arg1);
            return has < 0 ? NULL : PyBool_FromLong(has);
        }
        break;
    case IN_ARRAY_GET * 4 + 2:
        if (PyList_CheckExact(arg0) && replica_index(arg1, PyList_GET_SIZE(arg0) - 1, &index)) {
            return bs_list_get(arg0, index);
        }
        break;
    case IN_ARRAY_SET * 4 + 3:
        if (PyList_CheckExact(arg0) && replica_index(arg1, PyList_GET_SIZE(arg0) - 1, &index)) {
            value = regs[data->c];
            return PyList_SetItem(arg0, index, Py_NewRef(value)) < 0 ? NULL : Py_NewRef(value);
        }
        break;
    case IN_ARRAY_LENGTH * 4 + 1:
        if (PyList_CheckExact(arg0)) {
            return PyLong_FromSsize_t(PyList_GET_SIZE(arg0));
        }
        break;
    case IN_STRING_LENGTH * 4 + 1:
        if (PyUnicode_CheckExact(arg0)) {
            return PyLong_FromSsize_t(PyUnicode_GET_LENGTH(arg0));
        }
        break;
    case IN_SYSTEM_TYPE * 4 + 1:
        return Py_NewRef(value_type(arg0));
    case IN_ARRAY_PUSH * 4 + 2:
        if (PyList_CheckExact(arg0)) {
            return PyList_Append(arg0, arg1) < 0 ? NULL : Py_NewRef(arg0);
        }
        break;
    case IN_MATH_SQRT * 4 + 1:
        if (PyFloat_CheckExact(arg0) && PyFloat_AS_DOUBLE(arg0) >= 0) {
            return PyFloat_FromDouble(sqrt(PyFloat_AS_DOUBLE(arg0)));
        }
        break;
    case IN_OBJECT_KEYS * 4 + 1:
        if (PyDict_CheckExact(arg0)) {
            return PyDict_Keys(arg0);
        }
        break;
    case IN_ARRAY_NEW * 4 + 0:
        return PyList_New(0);
    case IN_OBJECT_NEW * 4 + 0:
        return PyDict_New();
    default:
        break;
    }

    // Any other shape - runtime.py's intrinsic, or the library replica (which may defer to the general call)
    int args_none = inst->c == ARGS_NONE;
    Py_ssize_t argc = args_none ? 0 : inst->c;
    PyObject *argv_small[ARGV_SMALL], **argv = vm_call_args(f, inst, argv_small);
    if (argv == NULL) {
        return NULL;
    }
    if (inst->x < IN_LIBRARY) {
        value = call_intrinsic(f, inst, name, argv, argc, args_none);
    } else if ((value = call_library(ctx, inst->x, argv, argc, args_none)) == NULL) {
        value = call_failed(f, inst, name);
    }
    if (argv != argv_small) {
        PyMem_Free(argv);
    }
    return value;
#else
    (void)f;
    (void)inst;
    return DEFER;
#endif
}


// Execute a call instruction
static BS_INLINE PyObject *vm_call(Frame *f, const Inst *inst)
{
    Chunk *chunk = f->chunk;
    PyObject **regs = f->regs;
    int args_none = inst->c == ARGS_NONE;
    Py_ssize_t argc = args_none ? 0 : inst->c;
    PyObject *argv_small[ARGV_SMALL], **argv = vm_call_args(f, inst, argv_small);
    if (argv == NULL) {
        return NULL;
    }

    // Resolve the function - a local, a global, or a built-in expression function
    PyObject *name, *func = NULL, *result = NULL;
    int found = 0;
    if (inst->op == OP_CALLS) {
        name = chunk->slot_names[inst->b];
        func = Py_XNewRef(regs[inst->b]);
        found = func != NULL;
    } else {
        name = chunk->names[inst->b];
        if (f->locals != NULL) {
            found = bs_dict_get(f->locals, name, &func);
        }
    }
#ifdef BS_CALL_CACHE
    if (inst->op == OP_CALLG && f->ctx->call_cache == NULL) {
        f->ctx->call_cache = PyMem_Calloc(CALL_CACHE_SIZE, sizeof(CallCache));
    }
    if (inst->op == OP_CALLG && f->ctx->call_cache != NULL) {
        CallCache *cache = call_cache_entry(f->ctx, name);
        if (cache->name == name && cache->globals == f->globals && cache->epoch == g_globals_epoch) {
            func = Py_NewRef(cache->func);
            found = 1;
        } else if ((found = bs_dict_get(f->globals, name, &func)) > 0) {
            Py_XSETREF(cache->name, Py_NewRef(name));
            Py_XSETREF(cache->func, Py_NewRef(func));
            Py_XSETREF(cache->globals, Py_NewRef(f->globals));
            cache->epoch = g_globals_epoch;
        }
    }
#endif
    if (found == 0 && f->globals != NULL) {
        found = bs_dict_get(f->globals, name, &func);
    }
    if (found == 0 && f->builtins) {
        found = bs_dict_get(g_EXPRESSION_FUNCTIONS, name, &func);
    }
    if (found >= 0) {
        if (func == NULL || func == Py_None) {
            PyObject *statement = frame_statement(f, inst);
            raise_runtime_error(f->script, statement, PyUnicode_FromFormat("Undefined function \"%U\"", name));
            Py_DECREF(statement);
        } else {
            result = call_function(f, inst, name, func, argv, argc, args_none);
        }
    }
    Py_XDECREF(func);
    if (argv != argv_small) {
        PyMem_Free(argv);
    }
    return result;
}


//
// Includes
//


// Execute an include statement's includes
static int vm_include(Frame *f, uint32_t index)
{
    Ctx *ctx = f->ctx;
    PyObject *options = ctx->options;
    PyObject *statement = chunk_statement(f->chunk, index);
    PyObject *fetch_fn = NULL, *url_fn = NULL, *include_statement = NULL, *includes = NULL, *iter = NULL,
        *include = NULL, *url = NULL, *system = NULL, *key = NULL, *global_includes = NULL, *text = NULL,
        *include_script = NULL, *include_options = NULL, *result = NULL;
    int rc = -1;
    if ((fetch_fn = object_get(options, S_fetchFn)) == NULL || (url_fn = object_get(options, S_urlFn)) == NULL ||
        (include_statement = PyObject_GetItem(statement, S_include)) == NULL ||
        (includes = PyObject_GetItem(include_statement, S_includes)) == NULL ||
        (iter = PyObject_GetIter(includes)) == NULL) {
        goto done;
    }
    while ((include = PyIter_Next(iter)) != NULL) {
        // Fixup the non-system include URL
        if ((url = PyObject_GetItem(include, S_url)) == NULL || (system = object_get(include, S_system)) == NULL) {
            goto done;
        }
        int is_system = PyObject_IsTrue(system);
        if (is_system < 0) {
            goto done;
        }
        if (!is_system && url_fn != Py_None) {
            if (ctx_sync_out(ctx) < 0) {
                goto done;
            }
            Py_SETREF(url, PyObject_CallOneArg(url_fn, url));
            ctx_sync_in(ctx);
            if (url == NULL) {
                goto done;
            }
        }

        // Already included? System include keys are bracketed so they can't collide with local include URLs.
        if (is_system) {
            PyObject *url_format = PyObject_Format(url, S_empty);
            key = url_format != NULL ? PyUnicode_FromFormat("<%U>", url_format) : NULL;
            Py_XDECREF(url_format);
        } else {
            key = Py_NewRef(url);
        }
        if (key == NULL || (global_includes = runtime_call("_system_global_includes", f->globals, NULL)) == NULL) {
            goto done;
        }
        PyObject *included = object_get(global_includes, key);
        int is_included = included != NULL ? PyObject_IsTrue(included) : -1;
        Py_XDECREF(included);
        if (is_included < 0) {
            goto done;
        }
        if (!is_included) {
            if (PyObject_SetItem(global_includes, key, Py_True) < 0) {
                goto done;
            }

            // Get the include script text - system includes from the system include map, otherwise fetch
            if (is_system) {
                PyObject *system_includes = runtime_attr("SYSTEM_INCLUDES");
                text = system_includes != NULL ? object_get(system_includes, url) : NULL;
                Py_XDECREF(system_includes);
                if (text == NULL) {
                    goto done;
                }
            } else if (fetch_fn != Py_None) {
                if (ctx_sync_out(ctx) < 0) {
                    goto done;
                }
                PyObject *request = Py_BuildValue("{OO}", S_url, url);
                text = request != NULL ? PyObject_CallOneArg(fetch_fn, request) : NULL;
                Py_XDECREF(request);
                ctx_sync_in(ctx);
                if (text == NULL) {
                    PyErr_Clear();
                    text = Py_NewRef(Py_None);
                }
            } else {
                text = Py_NewRef(Py_None);
            }
            if (text == Py_None) {
                PyObject *url_format = PyObject_Format(url, S_empty);
                raise_runtime_error(f->script, statement, url_format != NULL ?
                                    PyUnicode_FromFormat("Include of \"%U\" failed", url_format) : NULL);
                Py_XDECREF(url_format);
                goto done;
            }

            // Parse the include script. A system include starting with "{" is the parser-compiled JSON script model.
            int is_json = 0;
            if (is_system) {
                if (PyUnicode_CheckExact(text)) {
                    is_json = PyUnicode_GET_LENGTH(text) > 0 && PyUnicode_READ_CHAR(text, 0) == '{';
                } else {
                    PyObject *starts = PyObject_CallMethodObjArgs(text, S_startswith, S_brace, NULL);
                    is_json = starts != NULL ? PyObject_IsTrue(starts) : -1;
                    Py_XDECREF(starts);
                    if (is_json < 0) {
                        goto done;
                    }
                }
            }
            if (is_json) {
                include_script = PyObject_CallOneArg(g_json_loads, text);
            } else {
                include_script = runtime_call("barescript_parse_script", text, g_one, url, NULL);
            }
            if (include_script == NULL || (is_system && PyObject_SetItem(include_script, S_system, Py_True) < 0)) {
                goto done;
            }

            // Execute the include script
            if (ctx_sync_out(ctx) < 0 || (include_options = PyDict_Copy(options)) == NULL) {
                goto done;
            }
            PyObject *include_url_fn = PyObject_CallFunctionObjArgs(g_partial, g_url_file_relative, url, NULL);
            int set = include_url_fn != NULL ? PyDict_SetItem(include_options, S_urlFn, include_url_fn) : -1;
            Py_XDECREF(include_url_fn);
            if (set < 0) {
                goto done;
            }
            Ctx include_ctx = {.options = include_options};
            result = execute_script_statements(&include_ctx, include_script);
            ctx_exit(&include_ctx);
            if (result == NULL) {
                goto done;
            }
            Py_CLEAR(result);

            // Run the bare-script linter?
            if ((result = runtime_call("_lint_include", options, include_script, url, NULL)) == NULL) {
                goto done;
            }
            Py_CLEAR(result);
        }
        Py_CLEAR(include);
        Py_CLEAR(url);
        Py_CLEAR(system);
        Py_CLEAR(key);
        Py_CLEAR(global_includes);
        Py_CLEAR(text);
        Py_CLEAR(include_script);
        Py_CLEAR(include_options);
    }
    rc = PyErr_Occurred() ? -1 : 0;

done:
    Py_DECREF(statement);
    Py_XDECREF(fetch_fn);
    Py_XDECREF(url_fn);
    Py_XDECREF(include_statement);
    Py_XDECREF(includes);
    Py_XDECREF(iter);
    Py_XDECREF(include);
    Py_XDECREF(url);
    Py_XDECREF(system);
    Py_XDECREF(key);
    Py_XDECREF(global_includes);
    Py_XDECREF(text);
    Py_XDECREF(include_script);
    Py_XDECREF(include_options);
    Py_XDECREF(result);
    return rc;
}


//
// The interpreter
//


// The STMT slow path - the statement limit exceeded, or coverage recording
// runtime.py's statement count, for a count this runtime can't keep: options['statementCount'] + 1, stored and
// compared with maxStatements. A count that's an int this runtime can keep goes back to its own count. Returns 1 if
// the count exceeds maxStatements, 0 if not, or -1 on error.
static int count_python(Frame *f)
{
    Ctx *ctx = f->ctx;
    ctx->count = COUNT_PYTHON;
    PyObject *count = PyObject_GetItem(ctx->options, S_statementCount);
    PyObject *next = count != NULL ? PyNumber_Add(count, g_one) : NULL;
    Py_XDECREF(count);
    if (next == NULL || PyDict_SetItem(ctx->options, S_statementCount, next) < 0) {
        Py_XDECREF(next);
        return -1;
    }

    // statement_count > max_statements > 0
    int exceeded = PyObject_RichCompareBool(next, f->max_statements, Py_GT);
    if (exceeded > 0) {
        exceeded = PyObject_RichCompareBool(f->max_statements, g_zero, Py_GT);
    }
    long long value;
    if (exceeded == 0 && PyLong_CheckExact(next) && small_int(next, &value)) {
        ctx->count = ctx->synced = value;
        ctx->count_python = 0;
        Py_XSETREF(ctx->synced_obj, next);
    } else {
        Py_DECREF(next);
    }
    return exceeded;
}


static int vm_statement(Frame *f, uint32_t index)
{
    int exceeded = f->ctx->count_python ? count_python(f) : f->ctx->count > f->max_limit;
    if (exceeded < 0) {
        return -1;
    }
    if (exceeded) {
        PyObject *statement = chunk_statement(f->chunk, index);
        raise_runtime_error(f->script, statement,
                            PyUnicode_FromFormat("Exceeded maximum script statements (%S)", f->max_statements));
        Py_DECREF(statement);
        return -1;
    }
    return f->coverage != NULL ? frame_coverage(f, index) : 0;
}


// Load a local (evaluate_expression's locals) or global variable - a new reference
static PyObject *vm_load_name(Frame *f, PyObject *name)
{
    PyObject *value = NULL;
    int found = f->locals != NULL ? bs_dict_get(f->locals, name, &value) : 0;
    if (found == 0 && f->globals != NULL) {
        found = bs_dict_get(f->globals, name, &value);
    }
    return found < 0 ? NULL : (found ? value : Py_NewRef(Py_None));
}


// Raise the unknown jump label error
static void vm_jump_undefined(Frame *f, const Inst *inst)
{
    PyObject *statement = frame_statement(f, inst);
    raise_runtime_error(f->script, statement,
                        PyUnicode_FromFormat("Unknown jump label \"%U\"", f->chunk->names[inst->a]));
    Py_DECREF(statement);
}


// Record a label jump's label statement coverage - the label statement precedes the jump target's statement
static int vm_jump_coverage(Frame *f, uint32_t target)
{
    return frame_coverage(f, f->chunk->pcstmt[target] - 1);
}


static inline int vm_truth(PyObject *value)
{
    return value == Py_True ? 1 : (value == Py_False ? 0 : value_boolean(value));
}


// Is an object referenced only by the caller, so its value can be replaced in place?
static inline int is_unique(PyObject *object)
{
#ifdef Py_GIL_DISABLED
#if PY_VERSION_HEX >= 0x030E0000
    return PyUnstable_Object_IsUniquelyReferenced(object);
#else
    return 0;
#endif
#else
    return Py_REFCNT(object) == 1;
#endif
}


// Store an arithmetic result in a register - None if it's not finite. A float only the register holds is
// reused in place rather than replaced by a new float.
static inline int vm_store_float(PyObject **reg, double value)
{
    PyObject *old = *reg;
    if (!isfinite(value)) {
        *reg = Py_NewRef(Py_None);
    } else if (old != NULL && PyFloat_CheckExact(old) && is_unique(old)) {
        ((PyFloatObject *)old)->ob_fval = value;
        return 0;
    } else {
        *reg = PyFloat_FromDouble(value);
        if (*reg == NULL) {
            *reg = old;
            return -1;
        }
    }
    Py_XDECREF(old);
    return 0;
}


#if defined(__GNUC__) || defined(__clang__)
#define BS_THREADED_DISPATCH 1
#endif


// Run a frame's chunk. Returns a new reference, or NULL on error.
static PyObject *vm_run(Frame *f)
{
    Ctx *ctx = f->ctx;
    Chunk *chunk = f->chunk;
    PyObject **regs = f->regs;
    const Inst *code = chunk->code, *inst = code;
    PyObject *result = NULL;

#define SETREG(reg, value) \
    do { \
        PyObject *old_ = regs[reg]; \
        regs[reg] = (value); \
        Py_XDECREF(old_); \
    } while (0)

#ifdef BS_THREADED_DISPATCH
#define BS_OP_LABEL(name) &&L_##name,
    static const void *const dispatch[] = { BS_OPS(BS_OP_LABEL) };
#define CASE(name) L_##name:
#define DISPATCH() goto *dispatch[inst->op]
#else
#define CASE(name) case OP_##name:
#define DISPATCH() goto dispatch
#endif
#define NEXT() \
    do { \
        inst++; \
        DISPATCH(); \
    } while (0)

#define BINARY(name, fast, slow) \
    CASE(name) { \
        PyObject *left = regs[inst->b], *right = regs[inst->c], *value; \
        if (PyFloat_CheckExact(left) && PyFloat_CheckExact(right)) { \
            double x = PyFloat_AS_DOUBLE(left), y = PyFloat_AS_DOUBLE(right); \
            value = (fast); \
        } else { \
            value = (slow); \
        } \
        if (value == NULL) { \
            goto error; \
        } \
        SETREG(inst->a, value); \
        NEXT(); \
    }

#define ARITHMETIC(name, fast, slow) \
    CASE(name) { \
        PyObject *left = regs[inst->b], *right = regs[inst->c]; \
        if (PyFloat_CheckExact(left) && PyFloat_CheckExact(right)) { \
            double x = PyFloat_AS_DOUBLE(left), y = PyFloat_AS_DOUBLE(right); \
            if (vm_store_float(&regs[inst->a], (fast)) < 0) { \
                goto error; \
            } \
        } else { \
            PyObject *value = (slow); \
            if (value == NULL) { \
                goto error; \
            } \
            SETREG(inst->a, value); \
        } \
        NEXT(); \
    }

// Jump to an instruction, recording a label's coverage
#define JUMP(target) \
    do { \
        uint32_t target_ = (target); \
        if ((inst->x & JUMP_LABEL) && f->coverage != NULL && vm_jump_coverage(f, target_) < 0) { \
            goto error; \
        } \
        inst = code + target_; \
        DISPATCH(); \
    } while (0)

#define JUMP_TRUTH(name, on_true) \
    CASE(name) { \
        int truth = vm_truth(regs[inst->a]); \
        if (truth < 0) { \
            goto error; \
        } \
        if (truth == (on_true)) { \
            JUMP(inst->w); \
        } \
        NEXT(); \
    }

#define JUMP_COMPARE(name, op, fast) \
    CASE(name) { \
        PyObject *left = regs[inst->a], *right = regs[inst->b]; \
        int truth; \
        if (PyFloat_CheckExact(left) && PyFloat_CheckExact(right)) { \
            double x = PyFloat_AS_DOUBLE(left), y = PyFloat_AS_DOUBLE(right); \
            truth = (fast); \
        } else if ((truth = compare_truth(op, left, right)) < 0) { \
            goto error; \
        } \
        if (truth != ((inst->x & JUMP_NOT) != 0)) { \
            JUMP(inst[1].w); \
        } \
        inst += 2; \
        DISPATCH(); \
    }

#define BINARY_SLOW(name, slow) \
    CASE(name) { \
        PyObject *value = (slow); \
        if (value == NULL) { \
            goto error; \
        } \
        SETREG(inst->a, value); \
        NEXT(); \
    }

#ifdef BS_THREADED_DISPATCH
    DISPATCH();
#else
dispatch:
    switch (inst->op) {
#endif

    CASE(STMT)
        if (++ctx->count > f->limit && vm_statement(f, inst->w) < 0) {
            goto error;
        }
        NEXT();

    CASE(MOVE) {
        // A float copies into a float only the register holds - float identity isn't observable
        PyObject *value = regs[inst->b], *old = regs[inst->a];
        if (PyFloat_CheckExact(value) && old != NULL && PyFloat_CheckExact(old) && is_unique(old)) {
            ((PyFloatObject *)old)->ob_fval = PyFloat_AS_DOUBLE(value);
            NEXT();
        }
        SETREG(inst->a, Py_NewRef(value));
        NEXT();
    }

    CASE(LOADG) {
        PyObject *value;
        int found = bs_dict_get(f->globals, chunk->names[inst->b], &value);
        if (found < 0) {
            goto error;
        }
        SETREG(inst->a, found ? value : Py_NewRef(Py_None));
        NEXT();
    }

    CASE(LOADS) {
        PyObject *value = regs[inst->b];
        if (value != NULL) {
            Py_INCREF(value);
        } else {
            int found = bs_dict_get(f->globals, chunk->slot_names[inst->b], &value);
            if (found < 0) {
                goto error;
            }
            if (!found) {
                value = Py_NewRef(Py_None);
            }
        }
        SETREG(inst->a, value);
        NEXT();
    }

    CASE(LOADN) {
        PyObject *value = vm_load_name(f, chunk->names[inst->b]);
        if (value == NULL) {
            goto error;
        }
        SETREG(inst->a, value);
        NEXT();
    }

    CASE(STOREG)
        if (PyDict_SetItem(f->globals, chunk->names[inst->a], regs[inst->b]) < 0) {
            goto error;
        }
        globals_changed();
        if (chunk->names[inst->a] == S_coverage) {
            ctx_invalidate(ctx);
        }
        NEXT();

    CASE(JMP)
        JUMP(inst->w);

    JUMP_TRUTH(JF, 0)
    JUMP_TRUTH(JT, 1)

    JUMP_COMPARE(JLT, Py_LT, x < y)
    JUMP_COMPARE(JLE, Py_LE, x <= y)
    JUMP_COMPARE(JGT, Py_GT, x > y)
    JUMP_COMPARE(JGE, Py_GE, x >= y)
    JUMP_COMPARE(JEQ, Py_EQ, x == y)
    JUMP_COMPARE(JNE, Py_NE, x != y)

    CASE(JUNDEF)
        vm_jump_undefined(f, inst);
        goto error;

    CASE(RET)
        result = Py_NewRef(regs[inst->a]);
        goto done;

    CASE(RETNONE)
        result = Py_NewRef(Py_None);
        goto done;

    ARITHMETIC(ADD, x + y, op_add(left, right))
    ARITHMETIC(SUB, x - y, op_sub(left, right))
    ARITHMETIC(MUL, x * y, op_mul(left, right))
    ARITHMETIC(DIV, y != 0.0 ? x / y : NAN, op_div(left, right))
    BINARY_SLOW(MOD, op_mod(regs[inst->b], regs[inst->c]))
    BINARY_SLOW(POW, op_pow(regs[inst->b], regs[inst->c]))
    BINARY(EQ, PyBool_FromLong(x == y), op_compare(Py_EQ, left, right))
    BINARY(NE, PyBool_FromLong(x != y), op_compare(Py_NE, left, right))
    BINARY(LT, PyBool_FromLong(x < y), op_compare(Py_LT, left, right))
    BINARY(LE, PyBool_FromLong(x <= y), op_compare(Py_LE, left, right))
    BINARY(GT, PyBool_FromLong(x > y), op_compare(Py_GT, left, right))
    BINARY(GE, PyBool_FromLong(x >= y), op_compare(Py_GE, left, right))
    BINARY_SLOW(BAND, op_bitwise('&', regs[inst->b], regs[inst->c]))
    BINARY_SLOW(BOR, op_bitwise('|', regs[inst->b], regs[inst->c]))
    BINARY_SLOW(BXOR, op_bitwise('^', regs[inst->b], regs[inst->c]))
    BINARY_SLOW(SHL, op_bitwise('<', regs[inst->b], regs[inst->c]))
    BINARY_SLOW(SHR, op_bitwise('>', regs[inst->b], regs[inst->c]))

    CASE(NOT) {
        int truth = vm_truth(regs[inst->b]);
        if (truth < 0) {
            goto error;
        }
        SETREG(inst->a, PyBool_FromLong(!truth));
        NEXT();
    }

    BINARY_SLOW(NEG, op_neg(regs[inst->b]))
    BINARY_SLOW(BNOT, op_bnot(regs[inst->b]))

    CASE(CALLG) {
        PyObject *value = inst->x != IN_NONE ? vm_call_intrinsic(f, inst) : DEFER;
        if (value == DEFER) {
            value = vm_call(f, inst);
        }
        if (value == NULL) {
            goto error;
        }
        SETREG(inst->a, value);
        inst += 1 + CALL_DATA(inst->c);
        DISPATCH();
    }

    CASE(CALLS)
    CASE(CALLN) {
        PyObject *value = vm_call(f, inst);
        if (value == NULL) {
            goto error;
        }
        SETREG(inst->a, value);
        inst += 1 + CALL_DATA(inst->c);
        DISPATCH();
    }

    CASE(FUNC) {
        PyObject *fn = script_function_new(chunk->script, regs[inst->b]);
        int rc = fn != NULL ? PyDict_SetItem(f->globals, chunk->names[inst->a], fn) : -1;
        Py_XDECREF(fn);
        globals_changed();
        if (rc < 0) {
            goto error;
        }
        if (chunk->names[inst->a] == S_coverage) {
            ctx_invalidate(ctx);
        }
        NEXT();
    }

    CASE(INCLUDE) {
        int rc = vm_include(f, inst->w);
        ctx_invalidate(ctx);
        globals_changed();
        if (rc < 0) {
            goto error;
        }
        NEXT();
    }

    CASE(DATA)
    CASE(JTARGET)
        Py_UNREACHABLE();

#ifndef BS_THREADED_DISPATCH
    }
#endif

error:
    result = NULL;
done:
    return result;

#undef SETREG
#undef CASE
#undef DISPATCH
#undef NEXT
#undef BINARY
#undef BINARY_SLOW
#undef ARITHMETIC
#undef JUMP
#undef JUMP_TRUTH
#undef JUMP_COMPARE
}


//
// The module functions
//


static PyObject *execute_script(PyObject *module, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script, *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:execute_script", kwlist, &script, &options)) {
        return NULL;
    }
    options = options == Py_None ? PyDict_New() : Py_NewRef(options);
    if (options == NULL) {
        return NULL;
    }
    PyObject *result = NULL, *globals = NULL, *init = NULL;
    if (!PyDict_CheckExact(options)) {
        goto python;
    }

    // runtime.py's _execute_script_init - the globals dict, its built-in script functions, and a zero statement count
    if ((init = runtime_call("_execute_script_init", options, NULL)) == NULL) {
        goto done;
    }
    int found = bs_dict_get(options, S_globals, &globals);
    if (found < 0) {
        goto done;
    }
    if (!found || !PyDict_CheckExact(globals)) {
        goto python;
    }

    // Execute the script
    Ctx ctx = {.options = options, .synced_obj = Py_NewRef(g_zero)};
    result = execute_script_statements(&ctx, script);
    ctx_exit(&ctx);
    goto done;

python:
    result = runtime_call("execute_script", script, options, NULL);

done:
    Py_DECREF(options);
    Py_XDECREF(globals);
    Py_XDECREF(init);
    return result;
}


static PyObject *evaluate_expression(PyObject *module, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr, *options = Py_None, *locals = Py_None, *builtins = Py_True, *script = Py_None,
        *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOOOO:evaluate_expression", kwlist, &expr, &options, &locals,
                                     &builtins, &script, &statement)) {
        return NULL;
    }
    PyObject *globals = NULL, *result = NULL;
    Chunk *chunk = NULL;
    if ((options != Py_None && !PyDict_CheckExact(options)) || (locals != Py_None && !PyDict_CheckExact(locals)) ||
        !PyBool_Check(builtins)) {
        goto python;
    }
    if (options != Py_None) {
        if (bs_dict_get(options, S_globals, &globals) < 0) {
            return NULL;
        }
        if (globals == Py_None) {
            Py_CLEAR(globals);
        }
        if (globals != NULL && !PyDict_CheckExact(globals)) {
            goto python;
        }
    }
    if ((chunk = compile(MODE_EXPR, NULL, expr, NULL)) == NULL) {
        goto done;
    }
    if (chunk->irregular) {
        goto python;
    }

    // Evaluate the expression
    Ctx ctx = {.options = options};
    Frame frame = {0}, *f = &frame;
    f->ctx = &ctx;
    f->chunk = chunk;
    f->globals = globals;
    f->locals = locals != Py_None ? locals : NULL;
    f->script = script;
    f->statement = statement;
    f->builtins = builtins == Py_True;
    f->limit = f->max_limit = LLONG_MAX;
    PyObject *small[REGS_SMALL];
    f->regs = regs_alloc(chunk, small);
    if (f->regs != NULL) {
        result = vm_run(f);
        regs_free(chunk, f->regs, small);
    }
    ctx_exit(&ctx);
    goto done;

python:
    result = runtime_call("evaluate_expression", expr, options, locals, builtins, script, statement, NULL);

done:
    Py_XDECREF(globals);
    chunk_free(chunk);
    return result;
}


//
// Module initialization
//


static PyObject *import_attr(const char *module_name, const char *name)
{
    PyObject *module = PyImport_ImportModule(module_name);
    if (module == NULL) {
        return NULL;
    }
    PyObject *attr = PyObject_GetAttrString(module, name);
    Py_DECREF(module);
    return attr;
}


static int intern(PyObject **str, const char *value)
{
    *str = PyUnicode_InternFromString(value);
    return *str != NULL ? 0 : -1;
}


// Populate the module state, once
static int module_init(void)
{
    static const struct {
        PyObject **str;
        const char *value;
    } strings[] = {
        {&S_args, "args"}, {&S_binary, "binary"}, {&S_coverage, "__barescriptCoverage"}, {&S_debug, "debug"},
        {&S_empty, ""}, {&S_enabled, "enabled"}, {&S_expr, "expr"}, {&S_false, "false"},
        {&S_fetchFn, "fetchFn"}, {&S_function, "function"}, {&S_get, "get"}, {&S_globals, "globals"},
        {&S_group, "group"}, {&S_include, "include"}, {&S_includes, "includes"}, {&S_jump, "jump"},
        {&S_label, "label"}, {&S_lastArgArray, "lastArgArray"}, {&S_left, "left"},
        {&S_lineNumber, "lineNumber"}, {&S_logFn, "logFn"}, {&S_maxStatements, "maxStatements"},
        {&S_milliseconds, "milliseconds"}, {&S_name, "name"}, {&S_null, "null"}, {&S_number, "number"},
        {&S_op, "op"}, {&S_return, "return"}, {&S_return_value, "return_value"}, {&S_right, "right"},
        {&S_scriptName, "scriptName"}, {&S_scripts, "scripts"}, {&S_covered, "covered"}, {&S_count, "count"},
 {&S_startswith, "startswith"}, {&S_brace, "{"}, {&S_dollar, "$"}, {&S_backslash, "\\"},
        {&S_statementCount, "statementCount"}, {&S_statements, "statements"}, {&S_string, "string"},
        {&S_system, "system"}, {&S_total_seconds, "total_seconds"}, {&S_true, "true"}, {&S_unary, "unary"},
        {&S_url, "url"}, {&S_urlFn, "urlFn"}, {&S_variable, "variable"}, {&S_search, "search"},
        {&S_finditer, "finditer"}, {&S_groups, "groups"}, {&S_groupdict, "groupdict"}, {&S_start, "start"},
        {&S_index, "index"}, {&S_input, "input"}, {&S_lower, "lower"}, {&S_upper, "upper"}, {&S_sub, "sub"}, {&S_unknown, "unknown"},
        {&S_t_array, "array"}, {&S_t_boolean, "boolean"}, {&S_t_datetime, "datetime"},
        {&S_t_function, "function"}, {&S_t_null, "null"}, {&S_t_number, "number"}, {&S_t_object, "object"},
        {&S_t_regex, "regex"}, {&S_t_string, "string"}
    };
    for (size_t ix = 0; ix < sizeof(strings) / sizeof(strings[0]); ix++) {
        if (intern(strings[ix].str, strings[ix].value) < 0) {
            return -1;
        }
    }

    PyDateTime_IMPORT;
    if (PyDateTimeAPI == NULL) {
        return -1;
    }

    PyObject *runtime = PyImport_ImportModule("bare_script.runtime");
    if (runtime == NULL ||
        (g_BareScriptRuntimeError = PyObject_GetAttrString(runtime, "BareScriptRuntimeError")) == NULL ||
        (g_ValueArgsError = PyObject_GetAttrString(runtime, "ValueArgsError")) == NULL ||
        (g_SCRIPT_FUNCTIONS = PyObject_GetAttrString(runtime, "SCRIPT_FUNCTIONS")) == NULL ||
        (g_EXPRESSION_FUNCTIONS = PyObject_GetAttrString(runtime, "EXPRESSION_FUNCTIONS")) == NULL ||
        (g_INTRINSICS = PyObject_GetAttrString(runtime, "INTRINSICS")) == NULL ||
        (g_value_string = PyObject_GetAttrString(runtime, "value_string")) == NULL ||
        (g_value_compare = PyObject_GetAttrString(runtime, "value_compare")) == NULL ||
        (g_value_normalize_datetime = PyObject_GetAttrString(runtime, "value_normalize_datetime")) == NULL ||
        (g_value_round_number = PyObject_GetAttrString(runtime, "value_round_number")) == NULL ||
        (g_url_file_relative = PyObject_GetAttrString(runtime, "url_file_relative")) == NULL ||
        (g_default_max_statements = PyObject_GetAttrString(runtime, "DEFAULT_MAX_STATEMENTS")) == NULL ||
        (g_REGEX_TYPE = import_attr("bare_script.value", "REGEX_TYPE")) == NULL ||
        (g_json_loads = import_attr("json", "loads")) == NULL ||
        (g_re_escape = import_attr("re", "escape")) == NULL ||
        (g_partial = import_attr("functools", "partial")) == NULL ||
        (g_timedelta = import_attr("datetime", "timedelta")) == NULL ||
        (g_zero = PyLong_FromLong(0)) == NULL ||
        (g_one = PyLong_FromLong(1)) == NULL ||
        (g_thousand = PyLong_FromLong(1000)) == NULL ||
        (g_dbl_max = PyFloat_FromDouble(DBL_MAX)) == NULL ||
        (g_dbl_max_neg = PyFloat_FromDouble(-DBL_MAX)) == NULL) {
        Py_XDECREF(runtime);
        return -1;
    }

    // The JSON replicas' coders - the library's, and its decoder's hooks but for the integer hook
    PyObject *encoder = import_attr("bare_script.value", "_JSON_ENCODER_DEFAULT");
    PyObject *library_decoder = import_attr("bare_script.library", "_JSON_DECODER");
    PyObject *decoder_type = import_attr("json", "JSONDecoder"), *decoder = NULL, *kwargs = NULL;
    if (encoder != NULL && library_decoder != NULL && decoder_type != NULL &&
        (g_json_encode = PyObject_GetAttrString(encoder, "encode")) != NULL && (kwargs = PyDict_New()) != NULL) {
        PyObject *parse_float = PyObject_GetAttrString(library_decoder, "parse_float");
        PyObject *parse_constant = PyObject_GetAttrString(library_decoder, "parse_constant");
        if (parse_float != NULL && parse_constant != NULL && PyDict_SetItemString(kwargs, "parse_float", parse_float) == 0 &&
            PyDict_SetItemString(kwargs, "parse_constant", parse_constant) == 0 &&
            (decoder = PyObject_VectorcallDict(decoder_type, NULL, 0, kwargs)) != NULL) {
            g_json_decode = PyObject_GetAttrString(decoder, "decode");
        }
        Py_XDECREF(parse_float);
        Py_XDECREF(parse_constant);
    }
    Py_XDECREF(encoder);
    Py_XDECREF(library_decoder);
    Py_XDECREF(decoder_type);
    Py_XDECREF(decoder);
    Py_XDECREF(kwargs);
    if (g_json_decode == NULL) {
        Py_XDECREF(runtime);
        return -1;
    }
    for (int ix = 0; ix < 10; ix++) {
        char key[2] = {(char)('0' + ix), 0};
        if (intern(&g_group_keys[ix], key) < 0) {
            Py_DECREF(runtime);
            return -1;
        }
    }
    for (int id = 1; id < IN_COUNT; id++) {
        if (intern(&g_intrinsic_names[id], intrinsic_names[id]) < 0 ||
            (g_intrinsic_fns[id] = PyObject_GetItem(g_SCRIPT_FUNCTIONS, g_intrinsic_names[id])) == NULL) {
            Py_DECREF(runtime);
            return -1;
        }
    }
    if (PyType_Ready(&ScriptFunction_Type) < 0) {
        Py_DECREF(runtime);
        return -1;
    }
#ifdef BS_MODEL_WATCH
    // Without a free dict watcher, function models are checked by lookup on each call
    g_model_watcher = PyDict_AddWatcher(model_watch_callback);
    if (g_model_watcher < 0) {
        PyErr_Clear();
    }
#endif
    g_runtime = runtime;
    return 0;
}


static int module_exec(PyObject *module)
{
    (void)module;
    return g_runtime != NULL || module_init() == 0 ? 0 : -1;
}


static PyMethodDef module_methods[] = {
    {"execute_script", (PyCFunction)(void (*)(void))execute_script, METH_VARARGS | METH_KEYWORDS,
     "Execute a BareScript model"},
    {"evaluate_expression", (PyCFunction)(void (*)(void))evaluate_expression, METH_VARARGS | METH_KEYWORDS,
     "Evaluate an expression model"},
    {NULL, NULL, 0, NULL}
};


static PyModuleDef_Slot module_slots[] = {
    {Py_mod_exec, module_exec},
#if PY_VERSION_HEX >= 0x030C0000
    {Py_mod_multiple_interpreters, Py_MOD_MULTIPLE_INTERPRETERS_NOT_SUPPORTED},
#endif
#if PY_VERSION_HEX >= 0x030D0000
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL}
};


static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "bare_script.runtime_c",
    .m_doc = "The BareScript C runtime",
    .m_size = 0,
    .m_methods = module_methods,
    .m_slots = module_slots,
};


PyMODINIT_FUNC PyInit_runtime_c(void)
{
    return PyModuleDef_Init(&module_def);
}
