// Licensed under the MIT License
// https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

//
// The BareScript runtime C extension
//
// This module is a from-scratch C port of runtime.py, the reference implementation. It implements
// execute_script and evaluate_expression with observably identical behavior: same results, same
// errors, and the same edge cases. The pure-Python implementations of the parser, library, and
// value utilities are reused via imports; only the runtime execution core is implemented in C.
//
// How this file was created
//
// The module began as a direct, statement-for-statement port of runtime.py: a dict-walking
// statement loop and recursive expression evaluator, multi-phase module initialization with the
// Py_mod_gil slot, strong-reference dict access shims for Python 3.10+, and a ScriptFunction
// callable type replacing functools.partial(_script_function, ...). The port was then optimized
// iteratively, with each change measured against a same-session baseline (the Mandelbrot benchmark
// in perf/test.bare plus call-heavy and string-comparison harnesses) and gated on the full Python
// unit test suite and the 10,000+ assertion BareScript include test suite:
//
// 1. Execution context (-10%) - the per-statement options['statementCount'] dict
//    get/increment/set/compare was replaced with a C integer counter in an ExecCtx struct, synced
//    to the options dict only where external code can observe it (around function calls, includes,
//    and at execution exit). The context also caches the globals dict and the maxStatements limit.
// 2. First-key model dispatch (-38%) - valid statement and expression models are single-key dicts,
//    so kinds are dispatched on the dict's first key via interned-pointer identity instead of up
//    to 5-7 hash lookups per node, and inner fields (op/left/right, name/args, ...) are prefetched
//    in a single dict walk with lazy hashed fallback at each exact use point.
// 3. Direct ScriptFunction invocation (-13% call-heavy) - BareScript-to-BareScript calls bypass
//    the generic vectorcall machinery and execute on the caller's execution context.
// 4. Compiled model ASTs (-52%) - statements lists are compiled once into C node trees (see the
//    "Compiled model" section): literals, operator enums, keyword variables, and jump label
//    indexes resolve at compile time, and variable/assignment names are interned so locals/globals
//    dict probes hit on pointer equality. Compiled bodies cache write-once on ScriptFunction
//    objects; anything irregular compiles to a fallback node that defers to the dict-based
//    evaluator, which remains the semantic reference.
// 5. C value comparison fast path (-14% string workloads) - None/string/bool comparisons are
//    handled in C, with value.value_compare as the fallback for all other types.
// 6. Slot-based locals (-21%) - function bodies whose statements all compile cleanly use a C
//    pointer array for locals instead of a dict; local names (declared arguments plus assignment
//    targets, a statically known set) resolve to slot indexes at compile time, so reads are an
//    array load and assignments a pointer swap, with NULL slots mirroring dict misses.
// 7. Bounded-depth guard-free evaluation (-9%) - compiled expression trees are depth-capped at
//    compile time (deeper trees become fallback nodes), removing the per-node recursion guard
//    from compiled evaluation; the statement loop reuses the compiled slot's strong statement
//    reference instead of taking a reference per statement.
// 8. Guarded library intrinsics (-58% math-heavy, -78% accessor-heavy) - 26 trivial library.py
//    functions (math/array/object/string accessors) have C implementations that run only when a
//    compiled call resolves to the original library function object (pointer identity, captured
//    at module init); overrides take the generic path. Handlers replicate each function's
//    value_args_validate model exactly, raising through the Python ValueArgsError class.
//
// Overall, the optimized runtime executes the Mandelbrot benchmark roughly 33x faster than the
// pure-Python runtime. The compiled fast path assumes script models are immutable during
// execution (true of parser output); mutating a model mid-execution is unsupported.
//

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdint.h>

#ifdef Py_GIL_DISABLED
#include <stdatomic.h>
#endif


//
// Python version compatibility shims
//
// These wrap APIs added in newer CPython versions so the same source builds on Python 3.10+ and
// behaves correctly on both the default (GIL) and free-threaded (no-GIL) builds. The _ref variants
// always return strong references - never rely on the GIL to keep a borrowed reference alive.
//


// dict get returning a strong reference: 1 = found, 0 = missing, -1 = error
static inline int dict_get_ref(PyObject *dict, PyObject *key, PyObject **value)
{
#if PY_VERSION_HEX >= 0x030D0000
    return PyDict_GetItemRef(dict, key, value);
#else
    PyObject *borrowed = PyDict_GetItemWithError(dict, key);
    if (borrowed != NULL) {
        Py_INCREF(borrowed);
        *value = borrowed;
        return 1;
    }
    *value = NULL;
    return PyErr_Occurred() ? -1 : 0;
#endif
}


// list item returning a strong reference: 0 = success, -1 = error
static inline int list_get_ref(PyObject *list, Py_ssize_t index, PyObject **value)
{
#if PY_VERSION_HEX >= 0x030D0000
    *value = PyList_GetItemRef(list, index);
    return (*value != NULL) ? 0 : -1;
#else
    PyObject *borrowed = PyList_GetItem(list, index);
    if (borrowed == NULL) {
        *value = NULL;
        return -1;
    }
    Py_INCREF(borrowed);
    *value = borrowed;
    return 0;
#endif
}


// Capture the currently-raised exception as a strong reference to the exception instance
static PyObject *get_raised_exception(void)
{
#if PY_VERSION_HEX >= 0x030C0000
    return PyErr_GetRaisedException();
#else
    PyObject *type, *value, *traceback;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    if (value != NULL && traceback != NULL) {
        PyException_SetTraceback(value, traceback);
    }
    Py_XDECREF(type);
    Py_XDECREF(traceback);
    return value;
#endif
}


//
// Module state
//
// All members are populated once during module exec and are immutable afterwards, so they are safe
// to read concurrently under the free-threaded build (the module is marked as not supporting
// multiple interpreters, so a single initialization is guaranteed per process).
//

typedef struct {
    // Interned key strings
    PyObject *str_globals;
    PyObject *str_maxStatements;
    PyObject *str_statementCount;
    PyObject *str_systemPrefix;
    PyObject *str_fetchFn;
    PyObject *str_logFn;
    PyObject *str_urlFn;
    PyObject *str_debug;
    PyObject *str_statements;
    PyObject *str_scriptName;
    PyObject *str_system;
    PyObject *str_expr;
    PyObject *str_jump;
    PyObject *str_return;
    PyObject *str_function;
    PyObject *str_include;
    PyObject *str_label;
    PyObject *str_name;
    PyObject *str_args;
    PyObject *str_lastArgArray;
    PyObject *str_includes;
    PyObject *str_url;
    PyObject *str_number;
    PyObject *str_string;
    PyObject *str_variable;
    PyObject *str_binary;
    PyObject *str_unary;
    PyObject *str_group;
    PyObject *str_op;
    PyObject *str_left;
    PyObject *str_right;
    PyObject *str_lineNumber;
    PyObject *str_enabled;
    PyObject *str_scripts;
    PyObject *str_script;
    PyObject *str_covered;
    PyObject *str_statement;
    PyObject *str_count;
    PyObject *str_coverage_name;
    PyObject *str_includes_name;
    PyObject *str_return_value;
    PyObject *str_total_seconds;
    PyObject *str_copy;
    PyObject *str_method_upper;
    PyObject *str_method_lower;
    PyObject *str_method_strip;

    // Imported objects
    PyObject *script_functions;
    PyObject *expression_functions;
    PyObject *runtime_error;
    PyObject *value_args_error;
    PyObject *value_string;
    PyObject *value_compare;
    PyObject *value_round_number;
    PyObject *value_normalize_datetime;
    PyObject *url_file_relative;
    PyObject *parse_script;
    PyObject *lint_script;
    PyObject *partial;

    // Constants
    PyObject *default_max_statements;
    PyObject *zero;
    PyObject *one;
} RuntimeState;

static RuntimeState g;


//
// Generic mapping helpers
//
// The runtime's dicts (options, globals, script models) are exact dicts in practice, but these
// helpers fall back to the generic mapping protocol so duck-typed inputs behave like the Python
// reference implementation.
//


// mapping.get(key) semantics: 1 = found (strong reference in *value), 0 = missing, -1 = error
static int obj_get(PyObject *obj, PyObject *key, PyObject **value)
{
    if (PyDict_CheckExact(obj)) {
        return dict_get_ref(obj, key, value);
    }
    *value = PyObject_GetItem(obj, key);
    if (*value != NULL) {
        return 1;
    }
    if (PyErr_ExceptionMatches(PyExc_KeyError)) {
        PyErr_Clear();
        return 0;
    }
    return -1;
}


// mapping[key] semantics (KeyError if missing): 0 = success (strong reference), -1 = error
static int obj_subscript(PyObject *obj, PyObject *key, PyObject **value)
{
    if (PyDict_CheckExact(obj)) {
        int found = dict_get_ref(obj, key, value);
        if (found == 0) {
            PyErr_SetObject(PyExc_KeyError, key);
            return -1;
        }
        return (found < 0) ? -1 : 0;
    }
    *value = PyObject_GetItem(obj, key);
    return (*value != NULL) ? 0 : -1;
}


// mapping[key] = value: 0 = success, -1 = error
static int obj_setitem(PyObject *obj, PyObject *key, PyObject *value)
{
    if (PyDict_CheckExact(obj)) {
        return PyDict_SetItem(obj, key, value);
    }
    return PyObject_SetItem(obj, key, value);
}


//
// Execution context
//
// The reference implementation counts statements by incrementing options['statementCount'] in the
// options dict for every statement. The execution context keeps the counter in a C integer instead
// and syncs it to the options dict only when external code can observe it - before calling any
// Python callable (which may read the count or call back into the runtime) and when execution
// completes. The maxStatements limit and the script globals are read once and cached.
//


// Classification of the maxStatements option value for the fast counting path
typedef enum {
    MAX_KIND_LONG,   // exact int that fits in long long
    MAX_KIND_DOUBLE, // exact float
    MAX_KIND_OBJECT  // anything else - per-statement Python object comparisons
} MaxKind;


typedef struct {
    PyObject *options;   // borrowed - the options mapping or Py_None
    PyObject *globals;   // strong or NULL - the cached options globals
    PyObject *max_obj;   // strong or NULL - the original maxStatements object
    long long max_long;
    double max_double;
    long long count;     // the authoritative statement count when count_in_c
    MaxKind max_kind;
    int max_gt_zero;
    int count_in_c;      // 1 = the C counter is authoritative (the options dict may be stale)
    int is_exec;         // 1 = initialized for execution (globals/limit/counter are set up)
} ExecCtx;


// Counts above this bound fall back to dict-based counting to avoid long long overflow
#define COUNT_IN_C_BOUND (1LL << 62)


// Initialize a context for expression evaluation only (no statement counting). options may be
// Py_None.
static int exec_ctx_init_eval(ExecCtx *ctx, PyObject *options)
{
    ctx->options = options;
    ctx->globals = NULL;
    ctx->max_obj = NULL;
    ctx->count = 0;
    ctx->max_kind = MAX_KIND_OBJECT;
    ctx->max_gt_zero = 0;
    ctx->count_in_c = 0;
    ctx->is_exec = 0;
    if (options != Py_None) {
        if (obj_get(options, g.str_globals, &ctx->globals) < 0) {
            return -1;
        }
        if (ctx->globals == Py_None) {
            Py_CLEAR(ctx->globals);
        }
    }
    return 0;
}


// Initialize a context for script execution - requires options['globals'], reads maxStatements,
// and initializes the statement counter
static int exec_ctx_init_exec(ExecCtx *ctx, PyObject *options)
{
    ctx->options = options;
    ctx->globals = NULL;
    ctx->max_obj = NULL;
    ctx->count = 0;
    ctx->max_kind = MAX_KIND_OBJECT;
    ctx->max_gt_zero = 0;
    ctx->count_in_c = 0;
    ctx->is_exec = 1;

    // Get the script globals
    if (obj_subscript(options, g.str_globals, &ctx->globals) < 0) {
        return -1;
    }

    // Get the maximum statements option
    int found = obj_get(options, g.str_maxStatements, &ctx->max_obj);
    if (found < 0) {
        return -1;
    }
    if (!found) {
        ctx->max_obj = Py_NewRef(g.default_max_statements);
    }
    if (PyLong_CheckExact(ctx->max_obj)) {
        int overflow = 0;
        long long max_long = PyLong_AsLongLongAndOverflow(ctx->max_obj, &overflow);
        if (max_long == -1 && !overflow && PyErr_Occurred()) {
            return -1;
        }
        if (!overflow) {
            ctx->max_kind = MAX_KIND_LONG;
            ctx->max_long = max_long;
            ctx->max_gt_zero = (max_long > 0);
        }
    } else if (PyFloat_CheckExact(ctx->max_obj)) {
        ctx->max_kind = MAX_KIND_DOUBLE;
        ctx->max_double = PyFloat_AS_DOUBLE(ctx->max_obj);
        ctx->max_gt_zero = (ctx->max_double > 0.);
    }
    if (ctx->max_kind == MAX_KIND_OBJECT) {
        int max_gt_zero = PyObject_RichCompareBool(ctx->max_obj, g.zero, Py_GT);
        if (max_gt_zero < 0) {
            return -1;
        }
        ctx->max_gt_zero = max_gt_zero;
    }

    // Initialize the statement counter, if necessary
    if (PyDict_CheckExact(options)) {
#if PY_VERSION_HEX >= 0x030D0000
        PyObject *count_value = NULL;
        if (PyDict_SetDefaultRef(options, g.str_statementCount, g.zero, &count_value) < 0) {
            return -1;
        }
        Py_XDECREF(count_value);
#else
        if (PyDict_SetDefault(options, g.str_statementCount, g.zero) == NULL) {
            return -1;
        }
#endif
    } else {
        PyObject *count_value = NULL;
        found = obj_get(options, g.str_statementCount, &count_value);
        if (found < 0) {
            return -1;
        }
        if (found) {
            Py_DECREF(count_value);
        } else if (obj_setitem(options, g.str_statementCount, g.zero) < 0) {
            return -1;
        }
    }

    // Load the statement counter into C if it (and the maximum) supports fast counting
    PyObject *count_obj;
    if (obj_subscript(options, g.str_statementCount, &count_obj) < 0) {
        return -1;
    }
    if (ctx->max_kind != MAX_KIND_OBJECT && PyLong_CheckExact(count_obj)) {
        int overflow = 0;
        long long count = PyLong_AsLongLongAndOverflow(count_obj, &overflow);
        if (count == -1 && !overflow && PyErr_Occurred()) {
            Py_DECREF(count_obj);
            return -1;
        }
        if (!overflow && count < COUNT_IN_C_BOUND) {
            ctx->count = count;
            ctx->count_in_c = 1;
        }
    }
    Py_DECREF(count_obj);
    return 0;
}


static void exec_ctx_fini(ExecCtx *ctx)
{
    Py_XDECREF(ctx->max_obj);
    Py_XDECREF(ctx->globals);
}


// Write the C statement counter to the options dict (before external code can observe it)
static int exec_ctx_sync_out(ExecCtx *ctx)
{
    if (!ctx->count_in_c) {
        return 0;
    }
    PyObject *count_obj = PyLong_FromLongLong(ctx->count);
    if (count_obj == NULL) {
        return -1;
    }
    int result = obj_setitem(ctx->options, g.str_statementCount, count_obj);
    Py_DECREF(count_obj);
    return result;
}


// Reload the statement counter from the options dict (after external code may have changed it)
static int exec_ctx_sync_in(ExecCtx *ctx)
{
    if (!ctx->count_in_c) {
        return 0;
    }
    PyObject *count_obj;
    if (obj_subscript(ctx->options, g.str_statementCount, &count_obj) < 0) {
        return -1;
    }
    if (PyLong_CheckExact(count_obj)) {
        int overflow = 0;
        long long count = PyLong_AsLongLongAndOverflow(count_obj, &overflow);
        if (count == -1 && !overflow && PyErr_Occurred()) {
            Py_DECREF(count_obj);
            return -1;
        }
        if (!overflow && count < COUNT_IN_C_BOUND) {
            ctx->count = count;
        } else {
            ctx->count_in_c = 0;
        }
    } else {
        // The count was replaced with a non-int - fall back to dict-based counting
        ctx->count_in_c = 0;
    }
    Py_DECREF(count_obj);
    return 0;
}


// Write the C statement counter to the options dict, preserving any pending exception. Used at
// context-owner exit so the options dict is current whether execution succeeded or failed.
static void exec_ctx_sync_out_final(ExecCtx *ctx)
{
    if (!ctx->count_in_c) {
        return;
    }
    PyObject *exc_type;
    PyObject *exc_value;
    PyObject *exc_traceback;
    PyErr_Fetch(&exc_type, &exc_value, &exc_traceback);
    if (exec_ctx_sync_out(ctx) < 0) {
        PyErr_Clear();
    }
    PyErr_Restore(exc_type, exc_value, exc_traceback);
}


// Forward declaration (set_runtime_error is defined below)
static void set_runtime_error(PyObject *script, PyObject *statement, PyObject *message);


// Count a statement and check the maximum statements limit: 0 = success, -1 = error (limit
// exceeded or comparison failure)
static int exec_ctx_count_statement(ExecCtx *ctx, PyObject *script, PyObject *statement)
{
    // Fast path - C integer counting
    if (ctx->count_in_c) {
        ctx->count++;
        if (ctx->max_gt_zero) {
            int over_max = (ctx->max_kind == MAX_KIND_LONG)
                ? (ctx->count > ctx->max_long)
                : ((double)ctx->count > ctx->max_double);
            if (over_max) {
                set_runtime_error(
                    script, statement,
                    PyUnicode_FromFormat("Exceeded maximum script statements (%S)", ctx->max_obj)
                );
                return -1;
            }
        }
        if (ctx->count >= COUNT_IN_C_BOUND) {
            // Avoid long long overflow - fall back to dict-based counting
            if (exec_ctx_sync_out(ctx) < 0) {
                return -1;
            }
            ctx->count_in_c = 0;
        }
        return 0;
    }

    // Slow path - dict-based counting, mirroring the reference implementation directly
    PyObject *count_obj;
    if (obj_subscript(ctx->options, g.str_statementCount, &count_obj) < 0) {
        return -1;
    }
    PyObject *new_count = PyNumber_Add(count_obj, g.one);
    Py_DECREF(count_obj);
    if (new_count == NULL) {
        return -1;
    }
    if (obj_setitem(ctx->options, g.str_statementCount, new_count) < 0) {
        Py_DECREF(new_count);
        return -1;
    }
    if (ctx->max_gt_zero) {
        int over_max = PyObject_RichCompareBool(new_count, ctx->max_obj, Py_GT);
        if (over_max != 0) {
            if (over_max > 0) {
                set_runtime_error(
                    script, statement,
                    PyUnicode_FromFormat("Exceeded maximum script statements (%S)", ctx->max_obj)
                );
            }
            Py_DECREF(new_count);
            return -1;
        }
    }
    Py_DECREF(new_count);
    return 0;
}


//
// Value helpers
//


// Mirror of value.value_boolean - BareScript truthiness (note: unlike Python truthiness, any
// non-null value that is not a bool, string, number, or array is true - including empty objects)
static int value_boolean_c(PyObject *value)
{
    if (value == Py_True) {
        return 1;
    }
    if (value == Py_False || value == Py_None) {
        return 0;
    }
    PyTypeObject *type = Py_TYPE(value);
    if (type == &PyFloat_Type) {
        // NaN != 0 is true, matching the reference implementation
        return PyFloat_AS_DOUBLE(value) != 0.;
    }
    if (type == &PyLong_Type) {
        return PyObject_IsTrue(value);
    }
    if (type == &PyUnicode_Type) {
        return PyUnicode_GetLength(value) != 0;
    }
    if (type == &PyList_Type) {
        return PyList_GET_SIZE(value) != 0;
    }

    // Everything else non-null is true
    return 1;
}


// Is the value an exact int or float (bool is a subclass of int but has its own exact type)?
static inline int is_number(PyObject *value)
{
    return PyLong_CheckExact(value) || PyFloat_CheckExact(value);
}


// Convert an int, or a float with an integral value, to a new int reference. Returns NULL with no
// exception set if the value is not an integral number.
static PyObject *integral_long(PyObject *value)
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


// Compare a unicode object to an ASCII string literal
static inline int unicode_eq_ascii(PyObject *unicode, const char *str, Py_ssize_t length)
{
    if (PyUnicode_GetLength(unicode) != length) {
        return 0;
    }
    return PyUnicode_CompareWithASCIIString(unicode, str) == 0;
}


// Set a BareScriptRuntimeError with the given message (steals nothing; message may be NULL if an
// error is already set from its construction)
static void set_runtime_error(PyObject *script, PyObject *statement, PyObject *message)
{
    if (message == NULL) {
        return;
    }
    PyObject *exc = PyObject_CallFunctionObjArgs(
        g.runtime_error, (script != NULL) ? script : Py_None, (statement != NULL) ? statement : Py_None, message, NULL
    );
    if (exc != NULL) {
        PyErr_SetObject(g.runtime_error, exc);
        Py_DECREF(exc);
    }
    Py_DECREF(message);
}


//
// Binary and unary operator parsing
//


typedef enum {
    BINARY_AND,
    BINARY_OR,
    BINARY_ADD,
    BINARY_SUB,
    BINARY_MUL,
    BINARY_DIV,
    BINARY_LT,
    BINARY_LTE,
    BINARY_GT,
    BINARY_GTE,
    BINARY_EQ,
    BINARY_NEQ,
    BINARY_MOD,
    BINARY_POW,
    BINARY_BIT_AND,
    BINARY_BIT_OR,
    BINARY_BIT_XOR,
    BINARY_SHL,
    BINARY_SHR
} BinaryOp;


// Parse a binary operator string. Unrecognized operators map to BINARY_SHR, mirroring the
// reference implementation's trailing else branch.
static BinaryOp parse_binary_op(PyObject *op)
{
    if (!PyUnicode_Check(op)) {
        return BINARY_SHR;
    }
    Py_ssize_t length = PyUnicode_GetLength(op);
    if (length < 1 || length > 2) {
        return BINARY_SHR;
    }
    Py_UCS4 char0 = PyUnicode_ReadChar(op, 0);
    Py_UCS4 char1 = (length == 2) ? PyUnicode_ReadChar(op, 1) : 0;
    switch (char0) {
    case '&':
        return (length == 2 && char1 == '&') ? BINARY_AND : BINARY_BIT_AND;
    case '|':
        return (length == 2 && char1 == '|') ? BINARY_OR : BINARY_BIT_OR;
    case '+':
        return BINARY_ADD;
    case '-':
        return BINARY_SUB;
    case '*':
        return (length == 2) ? BINARY_POW : BINARY_MUL;
    case '/':
        return BINARY_DIV;
    case '<':
        return (length == 1) ? BINARY_LT : ((char1 == '=') ? BINARY_LTE : BINARY_SHL);
    case '>':
        return (length == 1) ? BINARY_GT : ((char1 == '=') ? BINARY_GTE : BINARY_SHR);
    case '=':
        return BINARY_EQ;
    case '!':
        return BINARY_NEQ;
    case '%':
        return BINARY_MOD;
    case '^':
        return BINARY_BIT_XOR;
    default:
        return BINARY_SHR;
    }
}


typedef enum {
    UNARY_NOT,
    UNARY_NEG,
    UNARY_INVERT
} UnaryOp;


// Parse a unary operator string. Unrecognized operators map to UNARY_INVERT, mirroring the
// reference implementation's trailing else branch.
static UnaryOp parse_unary_op(PyObject *op)
{
    if (PyUnicode_Check(op) && PyUnicode_GetLength(op) == 1) {
        Py_UCS4 char0 = PyUnicode_ReadChar(op, 0);
        if (char0 == '!') {
            return UNARY_NOT;
        }
        if (char0 == '-') {
            return UNARY_NEG;
        }
    }
    return UNARY_INVERT;
}


//
// Library intrinsics
//
// C implementations of hot, trivial library.py functions. An intrinsic runs only when a compiled
// call resolves to the original library function object (pointer identity, captured once at
// module init) - any override or shadowing takes the generic call path, so behavior is
// observably identical to the reference. Handlers replicate their function's
// value.value_args_validate model exactly and raise errors by calling the Python ValueArgsError
// class so messages and error return values match. Intrinsics never touch the options object, so
// no statement-counter sync is required around them. The table is populated once at module exec
// and immutable afterwards (free-threading safe).
//


typedef PyObject *(*IntrinsicHandler)(PyObject *args);

typedef struct {
    const char *name;
    IntrinsicHandler handler;
    PyObject *py_func;  // strong - the original library function, or NULL when unavailable
} IntrinsicDef;


// Raise a ValueArgsError exactly like value.value_args_validate (cold path)
static void intrinsic_args_error(const char *arg_name, PyObject *arg_value, PyObject *return_value)
{
    PyObject *name_obj = (arg_name != NULL) ? PyUnicode_FromString(arg_name) : Py_NewRef(Py_None);
    if (name_obj == NULL) {
        return;
    }
    PyObject *exc = PyObject_CallFunctionObjArgs(
        g.value_args_error, name_obj, (arg_value != NULL) ? arg_value : Py_None,
        (return_value != NULL) ? return_value : Py_None, NULL
    );
    Py_DECREF(name_obj);
    if (exc != NULL) {
        PyErr_SetObject(g.value_args_error, exc);
        Py_DECREF(exc);
    }
}


// Raise the too-many-arguments ValueArgsError (arg_name None, arg_value is the argument count)
static void intrinsic_count_error(Py_ssize_t nargs, PyObject *return_value)
{
    PyObject *nargs_obj = PyLong_FromSsize_t(nargs);
    if (nargs_obj == NULL) {
        return;
    }
    PyObject *exc = PyObject_CallFunctionObjArgs(
        g.value_args_error, Py_None, nargs_obj, (return_value != NULL) ? return_value : Py_None, NULL
    );
    Py_DECREF(nargs_obj);
    if (exc != NULL) {
        PyErr_SetObject(g.value_args_error, exc);
        Py_DECREF(exc);
    }
}


// Validate the single-number-argument model {'name': name, 'type': 'number' [, 'gte'/'gt': 0]}.
// constraint: 0 = none, 1 = gte 0, 2 = gt 0. Returns the argument (borrowed from args) or NULL
// with an exception set.
static PyObject *intrinsic_one_number(PyObject *args, const char *name, int constraint, PyObject *error_return)
{
    PyObject *value = (PyList_GET_SIZE(args) >= 1) ? PyList_GET_ITEM(args, 0) : NULL;
    if (value == NULL || value == Py_None || !is_number(value)) {
        intrinsic_args_error(name, value, error_return);
        return NULL;
    }
    if (constraint != 0) {
        if (PyFloat_CheckExact(value)) {
            // NaN fails both constraints, mirroring the reference's "not (value >= 0)"
            double number = PyFloat_AS_DOUBLE(value);
            if ((constraint == 1) ? !(number >= 0.) : !(number > 0.)) {
                intrinsic_args_error(name, value, error_return);
                return NULL;
            }
        } else {
            // Exact comparison for ints (arbitrary precision)
            int compare = PyObject_RichCompareBool(value, g.zero, (constraint == 1) ? Py_GE : Py_GT);
            if (compare < 0) {
                return NULL;
            }
            if (!compare) {
                intrinsic_args_error(name, value, error_return);
                return NULL;
            }
        }
    }
    if (PyList_GET_SIZE(args) > 1) {
        intrinsic_count_error(PyList_GET_SIZE(args), error_return);
        return NULL;
    }
    return value;
}


// Convert a validated number argument to double (int conversion may raise OverflowError, exactly
// like passing the int to a math-module function). Returns -1. with an exception set on error.
static double intrinsic_number_as_double(PyObject *value)
{
    if (PyFloat_CheckExact(value)) {
        return PyFloat_AS_DOUBLE(value);
    }
    return PyFloat_AsDouble(value);
}


// Validate an exact-typed argument at position ix: 'a' = array (list), 'o' = object (dict),
// 's' = string. Returns the argument (borrowed from args) or NULL with ValueArgsError raised.
static PyObject *intrinsic_typed_arg(PyObject *args, Py_ssize_t ix, char type, const char *name, PyObject *error_return)
{
    PyObject *value = (PyList_GET_SIZE(args) > ix) ? PyList_GET_ITEM(args, ix) : NULL;
    int type_ok = (value != NULL) &&
        ((type == 'a') ? PyList_CheckExact(value) : (type == 'o') ? PyDict_CheckExact(value) : PyUnicode_CheckExact(value));
    if (!type_ok) {
        intrinsic_args_error(name, value, error_return);
        return NULL;
    }
    return value;
}


// Validate an {'type': 'number', 'integer': True, 'gte': 0} argument at position ix. Sets
// *index_out (clamped to PY_SSIZE_T_MAX when numerically larger) and returns 0, or returns -1
// with an exception set. Bounds checking happens separately (after the argument-count check,
// matching the reference's validation order).
static int intrinsic_index_validate(PyObject *args, Py_ssize_t ix, const char *name, Py_ssize_t *index_out)
{
    PyObject *value = (PyList_GET_SIZE(args) > ix) ? PyList_GET_ITEM(args, ix) : NULL;
    if (value == NULL || value == Py_None) {
        intrinsic_args_error(name, value, NULL);
        return -1;
    }
    if (PyLong_CheckExact(value)) {
        int overflow = 0;
        long long index = PyLong_AsLongLongAndOverflow(value, &overflow);
        if (index == -1 && !overflow && PyErr_Occurred()) {
            return -1;
        }
        if (overflow < 0 || (!overflow && index < 0)) {
            intrinsic_args_error(name, value, NULL);
            return -1;
        }
        *index_out = (overflow > 0 || index > (long long)PY_SSIZE_T_MAX) ? PY_SSIZE_T_MAX : (Py_ssize_t)index;
        return 0;
    }
    if (PyFloat_CheckExact(value)) {
        double number = PyFloat_AS_DOUBLE(value);
        // int(value) raises for NaN and infinity, exactly like the reference's integer check
        if (isnan(number)) {
            PyErr_SetString(PyExc_ValueError, "cannot convert float NaN to integer");
            return -1;
        }
        if (isinf(number)) {
            PyErr_SetString(PyExc_OverflowError, "cannot convert float infinity to integer");
            return -1;
        }
        if (floor(number) != number || number < 0.) {
            intrinsic_args_error(name, value, NULL);
            return -1;
        }
        *index_out = (number >= (double)PY_SSIZE_T_MAX) ? PY_SSIZE_T_MAX : (Py_ssize_t)number;
        return 0;
    }
    intrinsic_args_error(name, value, NULL);
    return -1;
}


// Raise the reference's bounds error - ValueArgsError(name, normalized_index)
static void intrinsic_index_bounds_error(PyObject *args, Py_ssize_t ix, const char *name)
{
    PyObject *value = PyList_GET_ITEM(args, ix);
    PyObject *normalized =
        PyLong_CheckExact(value) ? Py_NewRef(value) : PyLong_FromDouble(PyFloat_AS_DOUBLE(value));
    if (normalized != NULL) {
        intrinsic_args_error(name, normalized, NULL);
        Py_DECREF(normalized);
    }
}


// Check the argument count against the model's argument count (no lastArgArray)
static int intrinsic_count_check(PyObject *args, Py_ssize_t count, PyObject *error_return)
{
    if (PyList_GET_SIZE(args) > count) {
        intrinsic_count_error(PyList_GET_SIZE(args), error_return);
        return -1;
    }
    return 0;
}


// mathSqrt(x) - x: number, gte 0. The gte constraint excludes the math-module error paths;
// big-int conversion raises the same OverflowError as math.sqrt.
static PyObject *intrinsic_math_sqrt(PyObject *args)
{
    PyObject *x = intrinsic_one_number(args, "x", 1, NULL);
    if (x == NULL) {
        return NULL;
    }
    double number = intrinsic_number_as_double(x);
    if (number == -1. && PyErr_Occurred()) {
        return NULL;
    }
    return PyFloat_FromDouble(sqrt(number));
}


// mathAbs(x) - abs() preserves int/float type
static PyObject *intrinsic_math_abs(PyObject *args)
{
    PyObject *x = intrinsic_one_number(args, "x", 0, NULL);
    if (x == NULL) {
        return NULL;
    }
    if (PyFloat_CheckExact(x)) {
        return PyFloat_FromDouble(fabs(PyFloat_AS_DOUBLE(x)));
    }
    return PyNumber_Absolute(x);
}


// mathCeil(x) / mathFloor(x) - math.ceil/floor return ints; PyLong_FromDouble raises the same
// errors for NaN and infinity
static PyObject *intrinsic_math_ceil(PyObject *args)
{
    PyObject *x = intrinsic_one_number(args, "x", 0, NULL);
    if (x == NULL) {
        return NULL;
    }
    if (PyFloat_CheckExact(x)) {
        return PyLong_FromDouble(ceil(PyFloat_AS_DOUBLE(x)));
    }
    return Py_NewRef(x);
}


static PyObject *intrinsic_math_floor(PyObject *args)
{
    PyObject *x = intrinsic_one_number(args, "x", 0, NULL);
    if (x == NULL) {
        return NULL;
    }
    if (PyFloat_CheckExact(x)) {
        return PyLong_FromDouble(floor(PyFloat_AS_DOUBLE(x)));
    }
    return Py_NewRef(x);
}


// mathSign(x) - "-1 if x < 0 else (0 if x == 0 else 1)" (NaN yields 1, like the reference)
static PyObject *intrinsic_math_sign(PyObject *args)
{
    PyObject *x = intrinsic_one_number(args, "x", 0, NULL);
    if (x == NULL) {
        return NULL;
    }
    long sign;
    if (PyFloat_CheckExact(x)) {
        double number = PyFloat_AS_DOUBLE(x);
        sign = (number < 0.) ? -1 : ((number == 0.) ? 0 : 1);
    } else {
        int is_negative = PyObject_RichCompareBool(x, g.zero, Py_LT);
        if (is_negative < 0) {
            return NULL;
        }
        if (is_negative) {
            sign = -1;
        } else {
            int is_zero = PyObject_RichCompareBool(x, g.zero, Py_EQ);
            if (is_zero < 0) {
                return NULL;
            }
            sign = is_zero ? 0 : 1;
        }
    }
    return PyLong_FromLong(sign);
}


// arrayNew(values...) - returns the (fresh, per-call) arguments list itself
static PyObject *intrinsic_array_new(PyObject *args)
{
    return Py_NewRef(args);
}


// arrayGet(array, index)
static PyObject *intrinsic_array_get(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", NULL);
    if (array == NULL) {
        return NULL;
    }
    Py_ssize_t index;
    if (intrinsic_index_validate(args, 1, "index", &index) < 0 || intrinsic_count_check(args, 2, NULL) < 0) {
        return NULL;
    }
    if (index >= PyList_GET_SIZE(array)) {
        intrinsic_index_bounds_error(args, 1, "index");
        return NULL;
    }
    return Py_NewRef(PyList_GET_ITEM(array, index));
}


// arraySet(array, index, value) - returns the value
static PyObject *intrinsic_array_set(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", NULL);
    if (array == NULL) {
        return NULL;
    }
    Py_ssize_t index;
    if (intrinsic_index_validate(args, 1, "index", &index) < 0 || intrinsic_count_check(args, 3, NULL) < 0) {
        return NULL;
    }
    if (index >= PyList_GET_SIZE(array)) {
        intrinsic_index_bounds_error(args, 1, "index");
        return NULL;
    }
    PyObject *value = (PyList_GET_SIZE(args) > 2) ? PyList_GET_ITEM(args, 2) : Py_None;
    if (PyList_SetItem(array, index, Py_NewRef(value)) < 0) {
        return NULL;
    }
    return Py_NewRef(value);
}


// arrayLength(array) - error return value 0
static PyObject *intrinsic_array_length(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", g.zero);
    if (array == NULL || intrinsic_count_check(args, 1, g.zero) < 0) {
        return NULL;
    }
    return PyLong_FromSsize_t(PyList_GET_SIZE(array));
}


// arrayPush(array, values...) - extends and returns the array
static PyObject *intrinsic_array_push(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", NULL);
    if (array == NULL) {
        return NULL;
    }
    Py_ssize_t nargs = PyList_GET_SIZE(args);
    for (Py_ssize_t ix = 1; ix < nargs; ix++) {
        if (PyList_Append(array, PyList_GET_ITEM(args, ix)) < 0) {
            return NULL;
        }
    }
    return Py_NewRef(array);
}


// arrayPop(array) - an empty array raises ValueArgsError('array', array)
static PyObject *intrinsic_array_pop(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", NULL);
    if (array == NULL || intrinsic_count_check(args, 1, NULL) < 0) {
        return NULL;
    }
    Py_ssize_t length = PyList_GET_SIZE(array);
    if (length == 0) {
        intrinsic_args_error("array", array, NULL);
        return NULL;
    }
    PyObject *value = Py_NewRef(PyList_GET_ITEM(array, length - 1));
    if (PyList_SetSlice(array, length - 1, length, NULL) < 0) {
        Py_DECREF(value);
        return NULL;
    }
    return value;
}


// arrayCopy(array)
static PyObject *intrinsic_array_copy(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", NULL);
    if (array == NULL || intrinsic_count_check(args, 1, NULL) < 0) {
        return NULL;
    }
    return PyList_GetSlice(array, 0, PyList_GET_SIZE(array));
}


// arrayExtend(array, array2) - extends and returns the first array
static PyObject *intrinsic_array_extend(PyObject *args)
{
    PyObject *array = intrinsic_typed_arg(args, 0, 'a', "array", NULL);
    if (array == NULL) {
        return NULL;
    }
    PyObject *array2 = intrinsic_typed_arg(args, 1, 'a', "array2", NULL);
    if (array2 == NULL || intrinsic_count_check(args, 2, NULL) < 0) {
        return NULL;
    }
    // list.extend semantics (handles array2 is array, like the reference)
    PyObject *extended = PySequence_InPlaceConcat(array, array2);
    if (extended == NULL) {
        return NULL;
    }
    return extended;
}


// objectGet(object, key, defaultValue) - the error return value is the default value argument
static PyObject *intrinsic_object_get(PyObject *args)
{
    PyObject *default_value = (PyList_GET_SIZE(args) >= 3) ? PyList_GET_ITEM(args, 2) : Py_None;
    PyObject *object = intrinsic_typed_arg(args, 0, 'o', "object", default_value);
    if (object == NULL) {
        return NULL;
    }
    PyObject *key = intrinsic_typed_arg(args, 1, 's', "key", default_value);
    if (key == NULL || intrinsic_count_check(args, 3, default_value) < 0) {
        return NULL;
    }
    PyObject *value;
    int found = dict_get_ref(object, key, &value);
    if (found < 0) {
        return NULL;
    }
    return found ? value : Py_NewRef(default_value);
}


// objectSet(object, key, value) - returns the value
static PyObject *intrinsic_object_set(PyObject *args)
{
    PyObject *object = intrinsic_typed_arg(args, 0, 'o', "object", NULL);
    if (object == NULL) {
        return NULL;
    }
    PyObject *key = intrinsic_typed_arg(args, 1, 's', "key", NULL);
    if (key == NULL || intrinsic_count_check(args, 3, NULL) < 0) {
        return NULL;
    }
    PyObject *value = (PyList_GET_SIZE(args) > 2) ? PyList_GET_ITEM(args, 2) : Py_None;
    if (PyDict_SetItem(object, key, value) < 0) {
        return NULL;
    }
    return Py_NewRef(value);
}


// objectHas(object, key) - error return value false
static PyObject *intrinsic_object_has(PyObject *args)
{
    PyObject *object = intrinsic_typed_arg(args, 0, 'o', "object", Py_False);
    if (object == NULL) {
        return NULL;
    }
    PyObject *key = intrinsic_typed_arg(args, 1, 's', "key", Py_False);
    if (key == NULL || intrinsic_count_check(args, 2, Py_False) < 0) {
        return NULL;
    }
    int has_key = PyDict_Contains(object, key);
    if (has_key < 0) {
        return NULL;
    }
    return Py_NewRef(has_key ? Py_True : Py_False);
}


// objectKeys(object)
static PyObject *intrinsic_object_keys(PyObject *args)
{
    PyObject *object = intrinsic_typed_arg(args, 0, 'o', "object", NULL);
    if (object == NULL || intrinsic_count_check(args, 1, NULL) < 0) {
        return NULL;
    }
    return PyDict_Keys(object);
}


// objectDelete(object, key) - returns null
static PyObject *intrinsic_object_delete(PyObject *args)
{
    PyObject *object = intrinsic_typed_arg(args, 0, 'o', "object", NULL);
    if (object == NULL) {
        return NULL;
    }
    PyObject *key = intrinsic_typed_arg(args, 1, 's', "key", NULL);
    if (key == NULL || intrinsic_count_check(args, 2, NULL) < 0) {
        return NULL;
    }
    int has_key = PyDict_Contains(object, key);
    if (has_key < 0) {
        return NULL;
    }
    if (has_key && PyDict_DelItem(object, key) < 0) {
        return NULL;
    }
    Py_RETURN_NONE;
}


// objectCopy(object)
static PyObject *intrinsic_object_copy(PyObject *args)
{
    PyObject *object = intrinsic_typed_arg(args, 0, 'o', "object", NULL);
    if (object == NULL || intrinsic_count_check(args, 1, NULL) < 0) {
        return NULL;
    }
    return PyDict_Copy(object);
}


// stringLength(string) - error return value 0
static PyObject *intrinsic_string_length(PyObject *args)
{
    PyObject *string = intrinsic_typed_arg(args, 0, 's', "string", g.zero);
    if (string == NULL || intrinsic_count_check(args, 1, g.zero) < 0) {
        return NULL;
    }
    return PyLong_FromSsize_t(PyUnicode_GetLength(string));
}


// stringUpper / stringLower / stringTrim - delegate to the str methods for exact Unicode
// case-mapping and whitespace semantics (still avoids the Python frame and validate loop)
static PyObject *intrinsic_string_method(PyObject *args, PyObject *method_name)
{
    PyObject *string = intrinsic_typed_arg(args, 0, 's', "string", NULL);
    if (string == NULL || intrinsic_count_check(args, 1, NULL) < 0) {
        return NULL;
    }
    return PyObject_CallMethodNoArgs(string, method_name);
}


static PyObject *intrinsic_string_upper(PyObject *args)
{
    return intrinsic_string_method(args, g.str_method_upper);
}


static PyObject *intrinsic_string_lower(PyObject *args)
{
    return intrinsic_string_method(args, g.str_method_lower);
}


static PyObject *intrinsic_string_trim(PyObject *args)
{
    return intrinsic_string_method(args, g.str_method_strip);
}


// stringCharCodeAt(string, index)
static PyObject *intrinsic_string_char_code_at(PyObject *args)
{
    PyObject *string = intrinsic_typed_arg(args, 0, 's', "string", NULL);
    if (string == NULL) {
        return NULL;
    }
    Py_ssize_t index;
    if (intrinsic_index_validate(args, 1, "index", &index) < 0 || intrinsic_count_check(args, 2, NULL) < 0) {
        return NULL;
    }
    if (index >= PyUnicode_GetLength(string)) {
        intrinsic_index_bounds_error(args, 1, "index");
        return NULL;
    }
    Py_UCS4 char_code = PyUnicode_ReadChar(string, index);
    if (char_code == (Py_UCS4)-1 && PyErr_Occurred()) {
        return NULL;
    }
    return PyLong_FromUnsignedLong(char_code);
}


// stringFromCharCode(charCodes...) - validates each code is an integral non-negative number;
// chr() range errors raise the same ValueError as the reference
static PyObject *intrinsic_string_from_char_code(PyObject *args)
{
    Py_ssize_t nargs = PyList_GET_SIZE(args);
    Py_UCS4 buffer_stack[32];
    Py_UCS4 *buffer = buffer_stack;
    if (nargs > 32) {
        buffer = PyMem_Malloc((size_t)nargs * sizeof(Py_UCS4));
        if (buffer == NULL) {
            return PyErr_NoMemory();
        }
    }
    PyObject *result = NULL;
    for (Py_ssize_t ix = 0; ix < nargs; ix++) {
        PyObject *code = PyList_GET_ITEM(args, ix);
        double number;
        if (PyFloat_CheckExact(code)) {
            number = PyFloat_AS_DOUBLE(code);
            // The reference's int(code) conversion raises for NaN and infinity (of either sign)
            // before the integral and sign checks
            if (isnan(number)) {
                PyErr_SetString(PyExc_ValueError, "cannot convert float NaN to integer");
                goto done;
            }
            if (isinf(number)) {
                PyErr_SetString(PyExc_OverflowError, "cannot convert float infinity to integer");
                goto done;
            }
            if (floor(number) != number || number < 0.) {
                intrinsic_args_error("char_codes", code, NULL);
                goto done;
            }
        } else if (PyLong_CheckExact(code)) {
            int overflow = 0;
            long long code_ll = PyLong_AsLongLongAndOverflow(code, &overflow);
            if (code_ll == -1 && !overflow && PyErr_Occurred()) {
                goto done;
            }
            if (overflow < 0 || (!overflow && code_ll < 0)) {
                intrinsic_args_error("char_codes", code, NULL);
                goto done;
            }
            number = (overflow > 0) ? 4294967296. : (double)code_ll;
        } else {
            intrinsic_args_error("char_codes", code, NULL);
            goto done;
        }
        if (number > 1114111.) {
            // chr() range error, exactly like the reference
            PyErr_SetString(PyExc_ValueError, "chr() arg not in range(0x110000)");
            goto done;
        }
        buffer[ix] = (Py_UCS4)number;
    }
    result = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, buffer, nargs);

done:
    if (buffer != buffer_stack) {
        PyMem_Free(buffer);
    }
    return result;
}


// The intrinsic table - py_func members are populated once at module exec
static IntrinsicDef g_intrinsics[] = {
    {"mathSqrt", intrinsic_math_sqrt, NULL},
    {"mathAbs", intrinsic_math_abs, NULL},
    {"mathCeil", intrinsic_math_ceil, NULL},
    {"mathFloor", intrinsic_math_floor, NULL},
    {"mathSign", intrinsic_math_sign, NULL},
    {"arrayNew", intrinsic_array_new, NULL},
    {"arrayGet", intrinsic_array_get, NULL},
    {"arraySet", intrinsic_array_set, NULL},
    {"arrayLength", intrinsic_array_length, NULL},
    {"arrayPush", intrinsic_array_push, NULL},
    {"arrayPop", intrinsic_array_pop, NULL},
    {"arrayCopy", intrinsic_array_copy, NULL},
    {"arrayExtend", intrinsic_array_extend, NULL},
    {"objectGet", intrinsic_object_get, NULL},
    {"objectSet", intrinsic_object_set, NULL},
    {"objectHas", intrinsic_object_has, NULL},
    {"objectKeys", intrinsic_object_keys, NULL},
    {"objectDelete", intrinsic_object_delete, NULL},
    {"objectCopy", intrinsic_object_copy, NULL},
    {"stringLength", intrinsic_string_length, NULL},
    {"stringUpper", intrinsic_string_upper, NULL},
    {"stringLower", intrinsic_string_lower, NULL},
    {"stringTrim", intrinsic_string_trim, NULL},
    {"stringCharCodeAt", intrinsic_string_char_code_at, NULL},
    {"stringFromCharCode", intrinsic_string_from_char_code, NULL},
};

#define INTRINSIC_COUNT ((int)(sizeof(g_intrinsics) / sizeof(g_intrinsics[0])))


// Find the intrinsic index for a function name at compile time (-1 if none)
static int intrinsic_lookup(PyObject *name)
{
    if (PyUnicode_Check(name)) {
        for (int ix = 0; ix < INTRINSIC_COUNT; ix++) {
            if (PyUnicode_CompareWithASCIIString(name, g_intrinsics[ix].name) == 0) {
                return ix;
            }
        }
    }
    return -1;
}


//
// Forward declarations
//

static PyObject *evaluate_expression_c(
    PyObject *expr, ExecCtx *ctx, PyObject *locals, int builtins, PyObject *script, PyObject *statement
);
typedef struct CompiledBody CompiledBody;
typedef struct Scope Scope;
static PyObject *execute_script_helper(
    PyObject *script, PyObject *statements, ExecCtx *ctx, Scope *scope, CompiledBody *body
);


//
// Model dict dispatch
//
// Valid statement and expression models are single-key dicts, so the kind is determined from the
// dict's first key with no hash lookups. Keys are matched by interned-pointer identity first with
// a content-comparison fallback for non-interned keys. Inner model fields (e.g. a binary
// expression's op/left/right) are prefetched in a single dict walk; any field not found falls back
// to a hashed subscript at its exact point of use, preserving the reference implementation's
// KeyError and short-circuit edge behavior.
//


// Content comparison of a key against an interned key constant (both unicode means no error)
static int key_eq_content(PyObject *key, PyObject *interned)
{
    return PyUnicode_Check(key) && PyUnicode_Compare(key, interned) == 0;
}


// Compare a key against an interned key constant: identity first, content fallback
static inline int key_eq(PyObject *key, PyObject *interned)
{
    return key == interned || key_eq_content(key, interned);
}


// Prefetch up to three model dict fields in a single dict walk. Each found value is returned as a
// strong reference; missing fields are left NULL.
static void dict_prefetch3(
    PyObject *dict, PyObject *key1, PyObject **value1, PyObject *key2, PyObject **value2, PyObject *key3,
    PyObject **value3
)
{
    Py_ssize_t pos = 0;
    PyObject *key;
    PyObject *value;
    while (PyDict_Next(dict, &pos, &key, &value)) {
        // Interned-pointer identity (the parser's model keys are interned)
        if (key == key1) {
            Py_XSETREF(*value1, Py_NewRef(value));
        } else if (key2 != NULL && key == key2) {
            Py_XSETREF(*value2, Py_NewRef(value));
        } else if (key3 != NULL && key == key3) {
            Py_XSETREF(*value3, Py_NewRef(value));
        } else if (key_eq_content(key, key1)) {
            // Content fallback for non-interned keys
            Py_XSETREF(*value1, Py_NewRef(value));
        } else if (key2 != NULL && key_eq_content(key, key2)) {
            Py_XSETREF(*value2, Py_NewRef(value));
        } else if (key3 != NULL && key_eq_content(key, key3)) {
            Py_XSETREF(*value3, Py_NewRef(value));
        }
    }
}


// Expression model kinds, dispatched on the model dict's first key
typedef enum {
    EXPR_NUMBER,
    EXPR_STRING,
    EXPR_VARIABLE,
    EXPR_FUNCTION,
    EXPR_BINARY,
    EXPR_UNARY,
    EXPR_GROUP,
    EXPR_UNKNOWN
} ExprKind;


static ExprKind expr_kind(PyObject *key)
{
    // Interned-pointer identity (the parser's model keys are interned)
    if (key == g.str_number) {
        return EXPR_NUMBER;
    }
    if (key == g.str_string) {
        return EXPR_STRING;
    }
    if (key == g.str_variable) {
        return EXPR_VARIABLE;
    }
    if (key == g.str_function) {
        return EXPR_FUNCTION;
    }
    if (key == g.str_binary) {
        return EXPR_BINARY;
    }
    if (key == g.str_unary) {
        return EXPR_UNARY;
    }
    if (key == g.str_group) {
        return EXPR_GROUP;
    }

    // Content fallback for non-interned keys
    if (key_eq_content(key, g.str_number)) {
        return EXPR_NUMBER;
    }
    if (key_eq_content(key, g.str_string)) {
        return EXPR_STRING;
    }
    if (key_eq_content(key, g.str_variable)) {
        return EXPR_VARIABLE;
    }
    if (key_eq_content(key, g.str_function)) {
        return EXPR_FUNCTION;
    }
    if (key_eq_content(key, g.str_binary)) {
        return EXPR_BINARY;
    }
    if (key_eq_content(key, g.str_unary)) {
        return EXPR_UNARY;
    }
    if (key_eq_content(key, g.str_group)) {
        return EXPR_GROUP;
    }
    return EXPR_UNKNOWN;
}


//
// Compiled model
//
// Statement and expression models are immutable data produced by the parser, but the dict-based
// evaluator re-walks the model dicts on every execution. The compiler translates a statements list
// into a C node tree once - literals, operator enums, keyword variables, and jump label indexes
// are resolved at compile time, and variable/assignment names are interned so locals/globals dict
// probes hit on pointer equality. Anything irregular (non-dict parts, missing fields, generic
// sequences) compiles to a fallback node that defers to the dict-based evaluator, which remains
// the semantic reference for edge cases. Compilation itself never raises for model shape problems,
// only for memory errors - shape errors must surface at execution time, exactly where the
// reference implementation raises them.
//


typedef enum {
    CEXPR_LITERAL,
    CEXPR_NULL,
    CEXPR_TRUE,
    CEXPR_FALSE,
    CEXPR_VARIABLE,
    CEXPR_IF,
    CEXPR_CALL,
    CEXPR_BINARY,
    CEXPR_UNARY,
    CEXPR_FALLBACK
} CompiledExprKind;


typedef struct CompiledExpr {
    CompiledExprKind kind;
    BinaryOp binary_op;
    UnaryOp unary_op;
    PyObject *value;            // strong or NULL - literal / variable name / function name / fallback expr
    struct CompiledExpr *left;  // owned - binary left / unary operand
    struct CompiledExpr *right; // owned - binary right
    struct CompiledExpr **args; // owned - call arguments / if() value-true-false slots (entries may be NULL)
    Py_ssize_t nargs;           // call argument count, or -1 when the call has no args field
    Py_ssize_t slot;            // variable/call name local slot index, or -1 (not a local)
    int intrinsic;              // call intrinsic table index, or -1
} CompiledExpr;


// Compiled statement kinds. CSTMT_NONE means "execute via the dict-based statement path".
typedef enum {
    CSTMT_NONE,
    CSTMT_NOP,
    CSTMT_EXPR,
    CSTMT_JUMP,
    CSTMT_RETURN,
    CSTMT_FUNCTION
} CompiledStmtKind;


typedef struct {
    CompiledStmtKind kind;
    PyObject *statement;        // strong - the statement dict (identity guard, coverage, errors)
    PyObject *part;             // strong or NULL - the function definition dict (CSTMT_FUNCTION)
    PyObject *name;             // strong or NULL - assignment target / function name / jump label
    CompiledExpr *expr;         // owned or NULL - statement / condition / return expression
    Py_ssize_t jump_index;      // CSTMT_JUMP - the resolved label index, or -1 if unknown
    Py_ssize_t name_slot;       // CSTMT_EXPR - the assignment target local slot index, or -1
} CompiledStmt;


struct CompiledBody {
    PyObject *statements;       // strong - the statements list this body was compiled from
    Py_ssize_t count;
    CompiledStmt *stmts;

    // Slot-based locals model (function bodies whose statements all compiled cleanly).
    // slot_names is NULL when slot-based locals are disabled for this body.
    PyObject *slot_names;       // strong tuple of interned local names, indexed by slot
    Py_ssize_t nslots;
    PyObject *arg_names;        // strong tuple snapshot of the declared argument names, or NULL
    Py_ssize_t *arg_slots;      // owned - declared argument position -> slot index
    Py_ssize_t nargs_decl;
};


// Local variable scope - dict-based (the reference implementation's model) or slot-based (compiled
// function bodies). When slots is non-NULL, entries are strong references; a NULL entry means the
// name is not in the locals (reads fall through to globals, mirroring a dict miss).
struct Scope {
    PyObject *dict;             // dict locals, or Py_None when there are none
    PyObject **slots;           // slot locals, or NULL for dict-based scopes
    PyObject *names;            // borrowed - the body's slot_names tuple (for materialization)
    Py_ssize_t nslots;
};


// Convert a slot-based scope to a dict-based one (used if execution leaves the compiled fast path,
// e.g. after mid-execution mutation of the statements list). The dict is owned by the scope's
// creator, which releases it after execution.
static int scope_materialize(Scope *scope)
{
    PyObject *locals_dict = PyDict_New();
    if (locals_dict == NULL) {
        return -1;
    }
    for (Py_ssize_t ix = 0; ix < scope->nslots; ix++) {
        PyObject *value = scope->slots[ix];
        if (value != NULL && PyDict_SetItem(locals_dict, PyTuple_GET_ITEM(scope->names, ix), value) < 0) {
            Py_DECREF(locals_dict);
            return -1;
        }
    }
    scope->dict = locals_dict;
    scope->slots = NULL;
    return 0;
}


static void compiled_expr_free(CompiledExpr *expr)
{
    if (expr == NULL) {
        return;
    }
    Py_XDECREF(expr->value);
    compiled_expr_free(expr->left);
    compiled_expr_free(expr->right);
    if (expr->args != NULL) {
        Py_ssize_t nargs = (expr->kind == CEXPR_IF) ? 3 : expr->nargs;
        for (Py_ssize_t ix = 0; ix < nargs; ix++) {
            compiled_expr_free(expr->args[ix]);
        }
        PyMem_Free(expr->args);
    }
    PyMem_Free(expr);
}


static void compiled_body_free(CompiledBody *body)
{
    if (body == NULL) {
        return;
    }
    if (body->stmts != NULL) {
        for (Py_ssize_t ix = 0; ix < body->count; ix++) {
            CompiledStmt *stmt = &body->stmts[ix];
            Py_XDECREF(stmt->statement);
            Py_XDECREF(stmt->part);
            Py_XDECREF(stmt->name);
            compiled_expr_free(stmt->expr);
        }
        PyMem_Free(body->stmts);
    }
    Py_XDECREF(body->slot_names);
    Py_XDECREF(body->arg_names);
    PyMem_Free(body->arg_slots);
    Py_XDECREF(body->statements);
    PyMem_Free(body);
}


static int compiled_expr_traverse(CompiledExpr *expr, visitproc visit, void *arg)
{
    if (expr == NULL) {
        return 0;
    }
    Py_VISIT(expr->value);
    int result = compiled_expr_traverse(expr->left, visit, arg);
    if (result != 0) {
        return result;
    }
    result = compiled_expr_traverse(expr->right, visit, arg);
    if (result != 0) {
        return result;
    }
    if (expr->args != NULL) {
        Py_ssize_t nargs = (expr->kind == CEXPR_IF) ? 3 : expr->nargs;
        for (Py_ssize_t ix = 0; ix < nargs; ix++) {
            result = compiled_expr_traverse(expr->args[ix], visit, arg);
            if (result != 0) {
                return result;
            }
        }
    }
    return 0;
}


static int compiled_body_traverse(CompiledBody *body, visitproc visit, void *arg)
{
    if (body == NULL) {
        return 0;
    }
    Py_VISIT(body->statements);
    Py_VISIT(body->slot_names);
    Py_VISIT(body->arg_names);
    for (Py_ssize_t ix = 0; ix < body->count; ix++) {
        CompiledStmt *stmt = &body->stmts[ix];
        Py_VISIT(stmt->statement);
        Py_VISIT(stmt->part);
        Py_VISIT(stmt->name);
        int result = compiled_expr_traverse(stmt->expr, visit, arg);
        if (result != 0) {
            return result;
        }
    }
    return 0;
}


static CompiledExpr *compiled_expr_new(CompiledExprKind kind)
{
    CompiledExpr *expr = PyMem_Calloc(1, sizeof(CompiledExpr));
    if (expr == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    expr->kind = kind;
    expr->slot = -1;
    expr->intrinsic = -1;
    return expr;
}


// Compile to a fallback node that defers to the dict-based evaluator
static CompiledExpr *compile_expr_fallback(PyObject *expr)
{
    CompiledExpr *fallback = compiled_expr_new(CEXPR_FALLBACK);
    if (fallback != NULL) {
        fallback->value = Py_NewRef(expr);
    }
    return fallback;
}


// Intern an exact string in place (a no-op for other objects). Interned names make locals/globals
// dict probes hit on pointer equality. Interning the model's string is semantically invisible.
static void intern_name(PyObject **name)
{
    if (PyUnicode_CheckExact(*name)) {
        PyUnicode_InternInPlace(name);
    }
}


// Look up a name's local slot index in the compile-time local map (-1 if not a local)
static Py_ssize_t local_map_slot(PyObject *local_map, PyObject *name)
{
    if (local_map == NULL || !PyUnicode_CheckExact(name)) {
        return -1;
    }
    PyObject *slot_obj = PyDict_GetItemWithError(local_map, name);
    if (slot_obj == NULL) {
        PyErr_Clear();
        return -1;
    }
    return PyLong_AsSsize_t(slot_obj);
}


// Compile an expression model into a node tree. Returns NULL only on memory error - model shape
// problems compile to fallback nodes so they surface at execution time. local_map maps local
// variable names to slot indexes for slot-based function bodies (NULL otherwise).
static CompiledExpr *compile_expr(PyObject *expr, PyObject *local_map)
{
    CompiledExpr *result = NULL;

    if (!PyDict_CheckExact(expr)) {
        return compile_expr_fallback(expr);
    }

    // Guard compile-time recursion - on overflow, fall back to the (also guarded) dict evaluator
    if (Py_EnterRecursiveCall(" while compiling a BareScript expression")) {
        PyErr_Clear();
        return compile_expr_fallback(expr);
    }

    Py_ssize_t pos = 0;
    PyObject *key;
    PyObject *value;
    if (!PyDict_Next(expr, &pos, &key, &value)) {
        result = compile_expr_fallback(expr);
        goto done;
    }

    switch (expr_kind(key)) {
    case EXPR_NUMBER:
    case EXPR_STRING:
        result = compiled_expr_new(CEXPR_LITERAL);
        if (result != NULL) {
            result->value = Py_NewRef(value);
        }
        break;

    case EXPR_VARIABLE: {
        // Keywords
        if (PyUnicode_Check(value)) {
            Py_ssize_t length = PyUnicode_GetLength(value);
            if (length == 4 && unicode_eq_ascii(value, "null", 4)) {
                result = compiled_expr_new(CEXPR_NULL);
                break;
            }
            if (length == 4 && unicode_eq_ascii(value, "true", 4)) {
                result = compiled_expr_new(CEXPR_TRUE);
                break;
            }
            if (length == 5 && unicode_eq_ascii(value, "false", 5)) {
                result = compiled_expr_new(CEXPR_FALSE);
                break;
            }
        }
        result = compiled_expr_new(CEXPR_VARIABLE);
        if (result != NULL) {
            result->value = Py_NewRef(value);
            intern_name(&result->value);
            result->slot = local_map_slot(local_map, result->value);
        }
        break;
    }

    case EXPR_FUNCTION: {
        if (!PyDict_CheckExact(value)) {
            result = compile_expr_fallback(expr);
            break;
        }
        PyObject *func_name = NULL;
        PyObject *args_expr = NULL;
        dict_prefetch3(value, g.str_name, &func_name, g.str_args, &args_expr, NULL, NULL);
        if (func_name == NULL || (args_expr != NULL && args_expr != Py_None && !PyList_CheckExact(args_expr))) {
            // Missing name (KeyError at evaluation) or a generic args sequence
            Py_XDECREF(func_name);
            Py_XDECREF(args_expr);
            result = compile_expr_fallback(expr);
            break;
        }

        // "if" built-in function?
        if (PyUnicode_Check(func_name) && unicode_eq_ascii(func_name, "if", 2)) {
            Py_DECREF(func_name);
            if (args_expr == Py_None) {
                // len(None) raises at evaluation - defer to the dict evaluator
                Py_DECREF(args_expr);
                result = compile_expr_fallback(expr);
                break;
            }
            result = compiled_expr_new(CEXPR_IF);
            if (result == NULL) {
                Py_XDECREF(args_expr);
                break;
            }
            result->args = PyMem_Calloc(3, sizeof(CompiledExpr *));
            if (result->args == NULL) {
                Py_XDECREF(args_expr);
                PyErr_NoMemory();
                compiled_expr_free(result);
                result = NULL;
                break;
            }
            result->nargs = 3;
            Py_ssize_t args_length = (args_expr != NULL) ? PyList_GET_SIZE(args_expr) : 0;
            for (Py_ssize_t ix_arg = 0; ix_arg < 3 && ix_arg < args_length; ix_arg++) {
                PyObject *arg_expr;
                if (list_get_ref(args_expr, ix_arg, &arg_expr) < 0) {
                    Py_DECREF(args_expr);
                    compiled_expr_free(result);
                    result = NULL;
                    goto done;
                }
                // A None argument is treated as not-provided
                if (arg_expr != Py_None) {
                    result->args[ix_arg] = compile_expr(arg_expr, local_map);
                    if (result->args[ix_arg] == NULL) {
                        Py_DECREF(arg_expr);
                        Py_DECREF(args_expr);
                        compiled_expr_free(result);
                        result = NULL;
                        goto done;
                    }
                }
                Py_DECREF(arg_expr);
            }
            Py_XDECREF(args_expr);
            break;
        }

        // Function call
        result = compiled_expr_new(CEXPR_CALL);
        if (result == NULL) {
            Py_DECREF(func_name);
            Py_XDECREF(args_expr);
            break;
        }
        result->value = func_name;
        intern_name(&result->value);
        result->slot = local_map_slot(local_map, result->value);
        result->intrinsic = intrinsic_lookup(result->value);
        if (args_expr == NULL || args_expr == Py_None) {
            result->nargs = -1;
            Py_XDECREF(args_expr);
        } else {
            Py_ssize_t args_length = PyList_GET_SIZE(args_expr);
            result->nargs = args_length;
            if (args_length > 0) {
                result->args = PyMem_Calloc((size_t)args_length, sizeof(CompiledExpr *));
                if (result->args == NULL) {
                    Py_DECREF(args_expr);
                    PyErr_NoMemory();
                    compiled_expr_free(result);
                    result = NULL;
                    break;
                }
                for (Py_ssize_t ix_arg = 0; ix_arg < args_length; ix_arg++) {
                    PyObject *arg_expr;
                    if (list_get_ref(args_expr, ix_arg, &arg_expr) < 0) {
                        Py_DECREF(args_expr);
                        compiled_expr_free(result);
                        result = NULL;
                        goto done;
                    }
                    result->args[ix_arg] = compile_expr(arg_expr, local_map);
                    Py_DECREF(arg_expr);
                    if (result->args[ix_arg] == NULL) {
                        Py_DECREF(args_expr);
                        compiled_expr_free(result);
                        result = NULL;
                        goto done;
                    }
                }
            }
            Py_DECREF(args_expr);
        }
        break;
    }

    case EXPR_BINARY: {
        if (!PyDict_CheckExact(value)) {
            result = compile_expr_fallback(expr);
            break;
        }
        PyObject *op_obj = NULL;
        PyObject *left_expr = NULL;
        PyObject *right_expr = NULL;
        dict_prefetch3(value, g.str_op, &op_obj, g.str_left, &left_expr, g.str_right, &right_expr);
        if (op_obj == NULL || left_expr == NULL || right_expr == NULL) {
            // Missing fields raise (or short-circuit) at evaluation - defer to the dict evaluator
            Py_XDECREF(op_obj);
            Py_XDECREF(left_expr);
            Py_XDECREF(right_expr);
            result = compile_expr_fallback(expr);
            break;
        }
        result = compiled_expr_new(CEXPR_BINARY);
        if (result == NULL) {
            Py_DECREF(op_obj);
            Py_DECREF(left_expr);
            Py_DECREF(right_expr);
            break;
        }
        result->binary_op = parse_binary_op(op_obj);
        Py_DECREF(op_obj);
        result->left = compile_expr(left_expr, local_map);
        Py_DECREF(left_expr);
        if (result->left == NULL) {
            Py_DECREF(right_expr);
            compiled_expr_free(result);
            result = NULL;
            break;
        }
        result->right = compile_expr(right_expr, local_map);
        Py_DECREF(right_expr);
        if (result->right == NULL) {
            compiled_expr_free(result);
            result = NULL;
        }
        break;
    }

    case EXPR_UNARY: {
        if (!PyDict_CheckExact(value)) {
            result = compile_expr_fallback(expr);
            break;
        }
        PyObject *op_obj = NULL;
        PyObject *sub_expr = NULL;
        dict_prefetch3(value, g.str_op, &op_obj, g.str_expr, &sub_expr, NULL, NULL);
        if (op_obj == NULL || sub_expr == NULL) {
            Py_XDECREF(op_obj);
            Py_XDECREF(sub_expr);
            result = compile_expr_fallback(expr);
            break;
        }
        result = compiled_expr_new(CEXPR_UNARY);
        if (result == NULL) {
            Py_DECREF(op_obj);
            Py_DECREF(sub_expr);
            break;
        }
        result->unary_op = parse_unary_op(op_obj);
        Py_DECREF(op_obj);
        result->left = compile_expr(sub_expr, local_map);
        Py_DECREF(sub_expr);
        if (result->left == NULL) {
            compiled_expr_free(result);
            result = NULL;
        }
        break;
    }

    case EXPR_GROUP:
        // Fold the group - evaluating a group evaluates its inner expression
        result = compile_expr(value, local_map);
        break;

    default: // EXPR_UNKNOWN
        result = compile_expr_fallback(expr);
        break;
    }

done:
    Py_LeaveRecursiveCall();
    return result;
}


// Does a compiled expression tree contain any fallback nodes (which require dict-based locals)?
static int compiled_expr_has_fallback(CompiledExpr *expr)
{
    if (expr == NULL) {
        return 0;
    }
    if (expr->kind == CEXPR_FALLBACK) {
        return 1;
    }
    if (compiled_expr_has_fallback(expr->left) || compiled_expr_has_fallback(expr->right)) {
        return 1;
    }
    if (expr->args != NULL) {
        Py_ssize_t nargs = (expr->kind == CEXPR_IF) ? 3 : expr->nargs;
        for (Py_ssize_t ix = 0; ix < nargs; ix++) {
            if (compiled_expr_has_fallback(expr->args[ix])) {
                return 1;
            }
        }
    }
    return 0;
}


// Maximum compiled expression tree depth - deeper trees compile to fallback nodes so that
// guard-free compiled evaluation has statically bounded C recursion
#define COMPILED_EXPR_MAX_DEPTH 64

static Py_ssize_t compiled_expr_depth(CompiledExpr *expr)
{
    if (expr == NULL) {
        return 0;
    }
    Py_ssize_t depth = compiled_expr_depth(expr->left);
    Py_ssize_t right_depth = compiled_expr_depth(expr->right);
    if (right_depth > depth) {
        depth = right_depth;
    }
    if (expr->args != NULL) {
        Py_ssize_t nargs = (expr->kind == CEXPR_IF) ? 3 : expr->nargs;
        for (Py_ssize_t ix = 0; ix < nargs; ix++) {
            Py_ssize_t arg_depth = compiled_expr_depth(expr->args[ix]);
            if (arg_depth > depth) {
                depth = arg_depth;
            }
        }
    }
    return depth + 1;
}


// Compile a statement's expression, replacing trees deeper than the depth cap with a fallback
// node (evaluated by the guarded dict-based evaluator). Returns NULL only on memory error.
static CompiledExpr *compile_stmt_expr(PyObject *expr, PyObject *local_map)
{
    CompiledExpr *compiled = compile_expr(expr, local_map);
    if (compiled != NULL && compiled_expr_depth(compiled) > COMPILED_EXPR_MAX_DEPTH) {
        compiled_expr_free(compiled);
        compiled = compile_expr_fallback(expr);
    }
    return compiled;
}


// Resolve a jump label to its statement index at compile time, mirroring the reference
// implementation's scan. Returns the index, -1 if not found (the unknown-label error is raised at
// execution), or -2 if the scan itself would raise at execution (defer to the dict path).
static Py_ssize_t compile_jump_index(PyObject *statements, Py_ssize_t count, PyObject *jump_label)
{
    for (Py_ssize_t ix = 0; ix < count; ix++) {
        PyObject *scan_statement = PySequence_Fast_GET_ITEM(statements, ix);
        if (!PyDict_CheckExact(scan_statement)) {
            // The runtime scan would raise here - defer to the dict path
            return -2;
        }
        PyObject *label_part = NULL;
        int found = obj_get(scan_statement, g.str_label, &label_part);
        if (found < 0) {
            PyErr_Clear();
            return -2;
        }
        if (found) {
            PyObject *label_name;
            if (obj_subscript(label_part, g.str_name, &label_name) < 0) {
                PyErr_Clear();
                Py_DECREF(label_part);
                return -2;
            }
            Py_DECREF(label_part);
            int label_eq = PyObject_RichCompareBool(label_name, jump_label, Py_EQ);
            Py_DECREF(label_name);
            if (label_eq < 0) {
                PyErr_Clear();
                return -2;
            }
            if (label_eq) {
                return ix;
            }
        }
    }
    return -1;
}


// Add a local name to the compile-time local map (first occurrence wins). Returns the slot
// index, or -1 on memory error.
static Py_ssize_t local_map_add(PyObject *local_map, PyObject *names_list, PyObject *name)
{
    PyObject *interned = Py_NewRef(name);
    PyUnicode_InternInPlace(&interned);
    PyObject *existing = PyDict_GetItemWithError(local_map, interned);
    if (existing != NULL) {
        Py_ssize_t slot = PyLong_AsSsize_t(existing);
        Py_DECREF(interned);
        return slot;
    }
    if (PyErr_Occurred()) {
        Py_DECREF(interned);
        return -1;
    }
    Py_ssize_t slot = PyList_GET_SIZE(names_list);
    PyObject *slot_obj = PyLong_FromSsize_t(slot);
    if (slot_obj == NULL || PyDict_SetItem(local_map, interned, slot_obj) < 0 ||
        PyList_Append(names_list, interned) < 0) {
        Py_XDECREF(slot_obj);
        Py_DECREF(interned);
        return -1;
    }
    Py_DECREF(slot_obj);
    Py_DECREF(interned);
    return slot;
}


// Compile a statements list (or tuple) into a compiled body. Returns NULL only on memory error.
// arg_names is the function's declared argument names (exact list) or NULL; enable_slots requests
// slot-based locals, granted only when every statement compiles cleanly with no fallback nodes
// and all local names are exact strings.
static CompiledBody *compile_body(PyObject *statements, PyObject *arg_names, int enable_slots)
{
    CompiledBody *body = PyMem_Calloc(1, sizeof(CompiledBody));
    if (body == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    body->statements = Py_NewRef(statements);
    body->count = PySequence_Fast_GET_SIZE(statements);
    if (body->count > 0) {
        body->stmts = PyMem_Calloc((size_t)body->count, sizeof(CompiledStmt));
        if (body->stmts == NULL) {
            PyErr_NoMemory();
            compiled_body_free(body);
            return NULL;
        }
    }

    // Collect the local names (declared arguments and assignment targets) for slot-based locals.
    // The set of possible locals keys is static: the reference implementation only inserts
    // argument names at invocation and assignment targets at execution.
    PyObject *local_map = NULL;
    PyObject *names_list = NULL;
    int slots_ok = 0;
    Py_ssize_t nargs_decl = (arg_names != NULL) ? PyList_GET_SIZE(arg_names) : 0;
    if (enable_slots) {
        slots_ok = 1;
        local_map = PyDict_New();
        names_list = PyList_New(0);
        if (local_map == NULL || names_list == NULL) {
            goto memory_error;
        }
        for (Py_ssize_t ix_arg = 0; slots_ok && ix_arg < nargs_decl; ix_arg++) {
            PyObject *arg_name;
            if (list_get_ref(arg_names, ix_arg, &arg_name) < 0) {
                goto memory_error;
            }
            if (!PyUnicode_CheckExact(arg_name)) {
                slots_ok = 0;
            } else if (local_map_add(local_map, names_list, arg_name) < 0) {
                Py_DECREF(arg_name);
                goto memory_error;
            }
            Py_DECREF(arg_name);
        }
        for (Py_ssize_t ix = 0; slots_ok && ix < body->count; ix++) {
            PyObject *statement = PySequence_Fast_GET_ITEM(statements, ix);
            if (!PyDict_CheckExact(statement)) {
                continue;
            }
            Py_ssize_t pos = 0;
            PyObject *stmt_key;
            PyObject *part;
            if (!PyDict_Next(statement, &pos, &stmt_key, &part) || !key_eq(stmt_key, g.str_expr) ||
                !PyDict_CheckExact(part)) {
                continue;
            }
            PyObject *expr_name = NULL;
            dict_prefetch3(part, g.str_name, &expr_name, NULL, NULL, NULL, NULL);
            if (expr_name != NULL && expr_name != Py_None) {
                if (!PyUnicode_CheckExact(expr_name)) {
                    slots_ok = 0;
                } else if (local_map_add(local_map, names_list, expr_name) < 0) {
                    Py_DECREF(expr_name);
                    goto memory_error;
                }
            }
            Py_XDECREF(expr_name);
        }
    }
    PyObject *compile_map = slots_ok ? local_map : NULL;

    for (Py_ssize_t ix = 0; ix < body->count; ix++) {
        CompiledStmt *stmt = &body->stmts[ix];
        PyObject *statement = PySequence_Fast_GET_ITEM(statements, ix);
        stmt->kind = CSTMT_NONE;
        stmt->jump_index = -1;
        stmt->name_slot = -1;
        stmt->statement = Py_NewRef(statement);

        // Non-dict statements raise at execution - defer to the dict path
        if (!PyDict_CheckExact(statement)) {
            continue;
        }

        // Empty statement dict - no-op
        Py_ssize_t pos = 0;
        PyObject *stmt_key;
        PyObject *part;
        if (!PyDict_Next(statement, &pos, &stmt_key, &part)) {
            stmt->kind = CSTMT_NOP;
            continue;
        }

        // Expression?
        if (key_eq(stmt_key, g.str_expr)) {
            if (!PyDict_CheckExact(part)) {
                continue;
            }
            PyObject *expr_inner = NULL;
            PyObject *expr_name = NULL;
            dict_prefetch3(part, g.str_expr, &expr_inner, g.str_name, &expr_name, NULL, NULL);
            if (expr_inner == NULL) {
                // KeyError at execution - defer to the dict path
                Py_XDECREF(expr_name);
                continue;
            }
            stmt->expr = compile_stmt_expr(expr_inner, compile_map);
            Py_DECREF(expr_inner);
            if (stmt->expr == NULL) {
                Py_XDECREF(expr_name);
                goto memory_error;
            }
            if (expr_name != NULL && expr_name != Py_None) {
                stmt->name = expr_name;
                intern_name(&stmt->name);
                stmt->name_slot = local_map_slot(compile_map, stmt->name);
            } else {
                Py_XDECREF(expr_name);
            }
            stmt->kind = CSTMT_EXPR;
            continue;
        }

        // Jump?
        if (key_eq(stmt_key, g.str_jump)) {
            if (!PyDict_CheckExact(part)) {
                continue;
            }
            PyObject *jump_expr = NULL;
            PyObject *jump_label = NULL;
            dict_prefetch3(part, g.str_expr, &jump_expr, g.str_label, &jump_label, NULL, NULL);
            if (jump_label == NULL) {
                // KeyError at execution - defer to the dict path
                Py_XDECREF(jump_expr);
                continue;
            }
            Py_ssize_t jump_index = compile_jump_index(statements, body->count, jump_label);
            if (jump_index == -2) {
                Py_XDECREF(jump_expr);
                Py_DECREF(jump_label);
                continue;
            }
            if (jump_expr != NULL) {
                stmt->expr = compile_stmt_expr(jump_expr, compile_map);
                Py_DECREF(jump_expr);
                if (stmt->expr == NULL) {
                    Py_DECREF(jump_label);
                    goto memory_error;
                }
            }
            stmt->name = jump_label;
            stmt->jump_index = jump_index;
            stmt->kind = CSTMT_JUMP;
            continue;
        }

        // Return?
        if (key_eq(stmt_key, g.str_return)) {
            if (!PyDict_CheckExact(part)) {
                continue;
            }
            PyObject *return_expr = NULL;
            dict_prefetch3(part, g.str_expr, &return_expr, NULL, NULL, NULL, NULL);
            if (return_expr != NULL) {
                stmt->expr = compile_stmt_expr(return_expr, compile_map);
                Py_DECREF(return_expr);
                if (stmt->expr == NULL) {
                    goto memory_error;
                }
            }
            stmt->kind = CSTMT_RETURN;
            continue;
        }

        // Function?
        if (key_eq(stmt_key, g.str_function)) {
            if (!PyDict_CheckExact(part)) {
                continue;
            }
            PyObject *function_name = NULL;
            dict_prefetch3(part, g.str_name, &function_name, NULL, NULL, NULL, NULL);
            if (function_name == NULL) {
                // KeyError at execution - defer to the dict path
                continue;
            }
            stmt->name = function_name;
            intern_name(&stmt->name);
            stmt->part = Py_NewRef(part);
            stmt->kind = CSTMT_FUNCTION;
            continue;
        }

        // Include - cold path, execute via the dict path
        if (key_eq(stmt_key, g.str_include)) {
            continue;
        }

        // Label statement (or unrecognized) - no-op
        stmt->kind = CSTMT_NOP;
    }

    // Grant slot-based locals only when every statement compiled with no fallback nodes
    if (slots_ok) {
        for (Py_ssize_t ix = 0; ix < body->count; ix++) {
            if (body->stmts[ix].kind == CSTMT_NONE || compiled_expr_has_fallback(body->stmts[ix].expr)) {
                slots_ok = 0;
                break;
            }
        }
    }
    if (slots_ok) {
        body->slot_names = PyList_AsTuple(names_list);
        if (body->slot_names == NULL) {
            goto memory_error;
        }
        body->nslots = PyTuple_GET_SIZE(body->slot_names);
        body->nargs_decl = nargs_decl;
        if (nargs_decl > 0) {
            body->arg_slots = PyMem_Calloc((size_t)nargs_decl, sizeof(Py_ssize_t));
            if (body->arg_slots == NULL) {
                PyErr_NoMemory();
                goto memory_error;
            }
            for (Py_ssize_t ix_arg = 0; ix_arg < nargs_decl; ix_arg++) {
                body->arg_slots[ix_arg] = local_map_slot(local_map, PyList_GET_ITEM(arg_names, ix_arg));
            }
        }
        if (arg_names != NULL) {
            body->arg_names = PyList_AsTuple(arg_names);
            if (body->arg_names == NULL) {
                goto memory_error;
            }
        }
    }
    Py_XDECREF(local_map);
    Py_XDECREF(names_list);
    return body;

memory_error:
    Py_XDECREF(local_map);
    Py_XDECREF(names_list);
    compiled_body_free(body);
    return NULL;
}


//
// Script function callable type
//
// Replaces functools.partial(_script_function, script, function) from the reference
// implementation. Instances are called as fn(args, options). The compiled body is built lazily on
// first invocation and published write-once; if the function dict's statements list is later
// replaced, execution falls back to the dict-based path rather than recompiling.
//

typedef struct {
    PyObject_HEAD
    PyObject *script;
    PyObject *function;
    CompiledBody *compiled;
} ScriptFunctionObject;


// The _script_function locals setup - build the function locals dict from the call arguments
static PyObject *script_function_locals(PyObject *function, PyObject *args)
{
    PyObject *func_locals = NULL;
    PyObject *func_args = NULL;
    PyObject *func_args_fast = NULL;
    PyObject *result = NULL;

    func_locals = PyDict_New();
    if (func_locals == NULL) {
        goto done;
    }

    // func_args = function.get('args')
    int found = obj_get(function, g.str_args, &func_args);
    if (found < 0) {
        goto done;
    }
    if (found && func_args != Py_None) {
        // args_length = len(args) - raises like the reference implementation if args is not a sequence
        Py_ssize_t args_length = PyObject_Length(args);
        if (args_length < 0) {
            goto done;
        }

        func_args_fast = PySequence_Fast(func_args, "function arguments must be a sequence");
        if (func_args_fast == NULL) {
            goto done;
        }
        Py_ssize_t func_args_length = PySequence_Fast_GET_SIZE(func_args_fast);

        // lastArgArray?
        PyObject *last_arg_array_obj = NULL;
        found = obj_get(function, g.str_lastArgArray, &last_arg_array_obj);
        if (found < 0) {
            goto done;
        }
        int last_arg_array = 0;
        if (found) {
            last_arg_array = PyObject_IsTrue(last_arg_array_obj);
            Py_DECREF(last_arg_array_obj);
            if (last_arg_array < 0) {
                goto done;
            }
        }

        int func_args_is_list = PyList_CheckExact(func_args_fast);
        Py_ssize_t ix_arg_last = func_args_length - 1;
        for (Py_ssize_t ix_arg = 0; ix_arg < func_args_length; ix_arg++) {
            PyObject *arg_name;
            if (func_args_is_list) {
                if (list_get_ref(func_args_fast, ix_arg, &arg_name) < 0) {
                    goto done;
                }
            } else {
                arg_name = PyTuple_GetItem(func_args_fast, ix_arg);
                if (arg_name == NULL) {
                    goto done;
                }
                Py_INCREF(arg_name);
            }
            PyObject *arg_value;
            if (ix_arg < args_length) {
                if (last_arg_array && ix_arg == ix_arg_last) {
                    arg_value = PySequence_GetSlice(args, ix_arg, args_length);
                } else {
                    arg_value = PySequence_GetItem(args, ix_arg);
                }
            } else {
                if (last_arg_array && ix_arg == ix_arg_last) {
                    arg_value = PyList_New(0);
                } else {
                    arg_value = Py_NewRef(Py_None);
                }
            }
            if (arg_value == NULL) {
                Py_DECREF(arg_name);
                goto done;
            }
            int set_result = PyDict_SetItem(func_locals, arg_name, arg_value);
            Py_DECREF(arg_name);
            Py_DECREF(arg_value);
            if (set_result < 0) {
                goto done;
            }
        }
    }

    // Success - return the locals dict
    result = func_locals;
    func_locals = NULL;

done:
    Py_XDECREF(func_args_fast);
    Py_XDECREF(func_args);
    Py_XDECREF(func_locals);
    return result;
}


// Get (or lazily build and publish) the compiled body for the function's statements list.
// Returns 0 with *body_out set (NULL when not compilable or stale) or -1 on memory error. The
// body is published write-once - concurrent builders race benignly and the loser is freed.
static int script_function_get_body(ScriptFunctionObject *script_function, PyObject *statements, CompiledBody **body_out)
{
#ifdef Py_GIL_DISABLED
    CompiledBody *body = atomic_load_explicit((_Atomic(CompiledBody *) *)&script_function->compiled, memory_order_acquire);
#else
    CompiledBody *body = script_function->compiled;
#endif
    if (body != NULL) {
        *body_out = (body->statements == statements) ? body : NULL;
        return 0;
    }
    if (!PyList_CheckExact(statements)) {
        *body_out = NULL;
        return 0;
    }

    // Get the declared argument names for slot-based locals (an exact list of names, possibly
    // absent; any other shape disables slots and uses dict-based locals)
    PyObject *args_decl = NULL;
    int enable_slots = 1;
    int found = obj_get(script_function->function, g.str_args, &args_decl);
    if (found < 0) {
        return -1;
    }
    if (args_decl == Py_None) {
        Py_CLEAR(args_decl);
    }
    if (args_decl != NULL && !PyList_CheckExact(args_decl)) {
        enable_slots = 0;
        Py_CLEAR(args_decl);
    }
    CompiledBody *new_body = compile_body(statements, args_decl, enable_slots);
    Py_XDECREF(args_decl);
    if (new_body == NULL) {
        return -1;
    }
#ifdef Py_GIL_DISABLED
    CompiledBody *expected = NULL;
    if (!atomic_compare_exchange_strong_explicit(
            (_Atomic(CompiledBody *) *)&script_function->compiled, &expected, new_body,
            memory_order_acq_rel, memory_order_acquire
        )) {
        compiled_body_free(new_body);
        new_body = expected;
    }
#else
    if (script_function->compiled == NULL) {
        script_function->compiled = new_body;
    } else {
        // A re-entrant build (e.g. via GC during compilation) won - use it
        compiled_body_free(new_body);
        new_body = script_function->compiled;
    }
#endif
    *body_out = (new_body->statements == statements) ? new_body : NULL;
    return 0;
}


// Execute a function body with slot-based locals - bind the arguments into the slot array and
// run the compiled body. Mirrors script_function_locals' argument binding semantics exactly
// (missing arguments bind None, the last-argument array binds a slice or fresh list).
static PyObject *script_function_execute_slots(
    ScriptFunctionObject *script_function, PyObject *statements, CompiledBody *body, PyObject *args, ExecCtx *ctx
)
{
    // args_length = len(args) - raises like the reference implementation if args is not a
    // sequence (only when the function declares arguments)
    Py_ssize_t args_length = 0;
    int last_arg_array = 0;
    if (body->arg_names != NULL) {
        args_length = PyObject_Length(args);
        if (args_length < 0) {
            return NULL;
        }

        // lastArgArray - read per call like the reference implementation
        PyObject *last_arg_array_obj = NULL;
        int found = obj_get(script_function->function, g.str_lastArgArray, &last_arg_array_obj);
        if (found < 0) {
            return NULL;
        }
        if (found) {
            last_arg_array = PyObject_IsTrue(last_arg_array_obj);
            Py_DECREF(last_arg_array_obj);
            if (last_arg_array < 0) {
                return NULL;
            }
        }
    }

    // Allocate the locals slots
    Py_ssize_t nslots = body->nslots;
    PyObject *slots_stack[16];
    PyObject **slots = slots_stack;
    if (nslots > 16) {
        slots = PyMem_Calloc((size_t)nslots, sizeof(PyObject *));
        if (slots == NULL) {
            PyErr_NoMemory();
            return NULL;
        }
    } else {
        memset(slots_stack, 0, sizeof(slots_stack));
    }

    // Bind the arguments
    PyObject *result = NULL;
    Py_ssize_t ix_arg_last = body->nargs_decl - 1;
    for (Py_ssize_t ix_arg = 0; ix_arg < body->nargs_decl; ix_arg++) {
        PyObject *arg_value;
        if (ix_arg < args_length) {
            if (last_arg_array && ix_arg == ix_arg_last) {
                arg_value = PySequence_GetSlice(args, ix_arg, args_length);
            } else {
                arg_value = PySequence_GetItem(args, ix_arg);
            }
        } else {
            arg_value = (last_arg_array && ix_arg == ix_arg_last) ? PyList_New(0) : Py_NewRef(Py_None);
        }
        if (arg_value == NULL) {
            goto done;
        }
        Py_XSETREF(slots[body->arg_slots[ix_arg]], arg_value);
    }

    // Execute the function statements
    {
        Scope scope = {Py_None, slots, body->slot_names, nslots};
        result = execute_script_helper(script_function->script, statements, ctx, &scope, body);
        if (scope.dict != Py_None) {
            // The scope was materialized to a dict after leaving the compiled fast path
            Py_DECREF(scope.dict);
        }
    }

done:
    for (Py_ssize_t ix = 0; ix < nslots; ix++) {
        Py_XDECREF(slots[ix]);
    }
    if (slots != slots_stack) {
        PyMem_Free(slots);
    }
    return result;
}


// Execute a function body on the given execution context, using slot-based locals when the
// compiled body supports them and the declared arguments are unchanged
static PyObject *script_function_execute(
    ScriptFunctionObject *script_function, PyObject *statements, CompiledBody *body, PyObject *args, ExecCtx *ctx
)
{
    // Slot-based locals fast path - the declared argument names must match the compiled
    // binding plan (compared per item, so in-place model mutation falls back to dict locals)
    if (body != NULL && body->slot_names != NULL) {
        PyObject *args_decl = NULL;
        int found = obj_get(script_function->function, g.str_args, &args_decl);
        if (found < 0) {
            return NULL;
        }
        if (args_decl == Py_None) {
            Py_CLEAR(args_decl);
        }
        int args_match;
        if (body->arg_names == NULL) {
            args_match = (args_decl == NULL);
        } else if (args_decl != NULL && PyList_CheckExact(args_decl) &&
                   PyList_GET_SIZE(args_decl) == PyTuple_GET_SIZE(body->arg_names)) {
            args_match = 1;
            for (Py_ssize_t ix_arg = 0; ix_arg < PyTuple_GET_SIZE(body->arg_names); ix_arg++) {
                if (PyList_GET_ITEM(args_decl, ix_arg) != PyTuple_GET_ITEM(body->arg_names, ix_arg)) {
                    args_match = 0;
                    break;
                }
            }
        } else {
            args_match = 0;
        }
        Py_XDECREF(args_decl);
        if (args_match) {
            return script_function_execute_slots(script_function, statements, body, args, ctx);
        }
    }

    // Dict-based locals
    PyObject *func_locals = script_function_locals(script_function->function, args);
    if (func_locals == NULL) {
        return NULL;
    }
    Scope scope = {func_locals, NULL, NULL, 0};
    PyObject *result = execute_script_helper(script_function->script, statements, ctx, &scope, body);
    Py_DECREF(func_locals);
    return result;
}


// Invoke a BareScript function on an existing execution context (the runtime's internal call path)
static PyObject *script_function_invoke_ctx(ScriptFunctionObject *script_function, PyObject *args, ExecCtx *ctx)
{
    PyObject *statements;
    if (obj_subscript(script_function->function, g.str_statements, &statements) < 0) {
        return NULL;
    }
    CompiledBody *body = NULL;
    if (script_function_get_body(script_function, statements, &body) < 0) {
        Py_DECREF(statements);
        return NULL;
    }
    PyObject *result = script_function_execute(script_function, statements, body, args, ctx);
    Py_DECREF(statements);
    return result;
}


// The _script_function logic - execute the function statements on a fresh execution context
// (the Python-visible call path)
static PyObject *script_function_invoke(ScriptFunctionObject *script_function, PyObject *args, PyObject *options)
{
    PyObject *statements = NULL;
    PyObject *result = NULL;
    if (obj_subscript(script_function->function, g.str_statements, &statements) < 0) {
        return NULL;
    }
    CompiledBody *body = NULL;
    if (script_function_get_body(script_function, statements, &body) < 0) {
        Py_DECREF(statements);
        return NULL;
    }
    ExecCtx ctx;
    if (exec_ctx_init_exec(&ctx, options) == 0) {
        result = script_function_execute(script_function, statements, body, args, &ctx);
        exec_ctx_sync_out_final(&ctx);
    }
    exec_ctx_fini(&ctx);
    Py_DECREF(statements);
    return result;
}


static PyObject *script_function_call(PyObject *self, PyObject *args, PyObject *kwargs)
{
    ScriptFunctionObject *script_function = (ScriptFunctionObject *)self;
    PyObject *fn_args;
    PyObject *fn_options;
    if (kwargs != NULL && PyDict_GET_SIZE(kwargs) != 0) {
        PyErr_SetString(PyExc_TypeError, "script function takes no keyword arguments");
        return NULL;
    }
    if (!PyArg_UnpackTuple(args, "script function", 2, 2, &fn_args, &fn_options)) {
        return NULL;
    }
    return script_function_invoke(script_function, fn_args, fn_options);
}


static int script_function_traverse(PyObject *self, visitproc visit, void *arg)
{
    ScriptFunctionObject *script_function = (ScriptFunctionObject *)self;
    Py_VISIT(script_function->script);
    Py_VISIT(script_function->function);
    int result = compiled_body_traverse(script_function->compiled, visit, arg);
    if (result != 0) {
        return result;
    }
    return 0;
}


static int script_function_clear(PyObject *self)
{
    ScriptFunctionObject *script_function = (ScriptFunctionObject *)self;
    Py_CLEAR(script_function->script);
    Py_CLEAR(script_function->function);
    CompiledBody *body = script_function->compiled;
    script_function->compiled = NULL;
    compiled_body_free(body);
    return 0;
}


static void script_function_dealloc(PyObject *self)
{
    PyObject_GC_UnTrack(self);
    script_function_clear(self);
    Py_TYPE(self)->tp_free(self);
}


static PyTypeObject ScriptFunctionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c.ScriptFunction",
    .tp_basicsize = sizeof(ScriptFunctionObject),
    .tp_dealloc = script_function_dealloc,
    .tp_call = script_function_call,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = script_function_traverse,
    .tp_clear = script_function_clear
};


static PyObject *script_function_new(PyObject *script, PyObject *function)
{
    ScriptFunctionObject *script_function = PyObject_GC_New(ScriptFunctionObject, &ScriptFunctionType);
    if (script_function == NULL) {
        return NULL;
    }
    script_function->script = Py_NewRef(script);
    script_function->function = Py_NewRef(function);
    script_function->compiled = NULL;
    PyObject_GC_Track((PyObject *)script_function);
    return (PyObject *)script_function;
}


//
// Statement coverage recording (debug-only path)
//


static int record_statement_coverage(PyObject *script, PyObject *statement, PyObject *coverage_global)
{
    PyObject *script_name = NULL;
    PyObject *lineno = NULL;
    PyObject *scripts = NULL;
    PyObject *script_coverage = NULL;
    PyObject *lineno_str = NULL;
    PyObject *covered = NULL;
    PyObject *covered_statement = NULL;
    PyObject *count = NULL;
    PyObject *new_count = NULL;
    int result = -1;

    // Get the statement's first key's value (the statement model)
    Py_ssize_t pos = 0;
    PyObject *stmt_key_borrowed;
    PyObject *stmt_value_borrowed;
    if (!PyDict_Next(statement, &pos, &stmt_key_borrowed, &stmt_value_borrowed)) {
        return 0;
    }
    PyObject *stmt_value = Py_NewRef(stmt_value_borrowed);

    // Get the script name and statement line number
    int found = obj_get(script, g.str_scriptName, &script_name);
    if (found < 0) {
        goto done;
    }
    if (!found || script_name == Py_None) {
        result = 0;
        goto done;
    }
    found = obj_get(stmt_value, g.str_lineNumber, &lineno);
    if (found < 0) {
        goto done;
    }
    if (!found || lineno == Py_None) {
        result = 0;
        goto done;
    }

    // Get/create the scripts coverage object
    found = obj_get(coverage_global, g.str_scripts, &scripts);
    if (found < 0) {
        goto done;
    }
    if (!found || scripts == Py_None) {
        Py_XDECREF(scripts);
        scripts = PyDict_New();
        if (scripts == NULL || obj_setitem(coverage_global, g.str_scripts, scripts) < 0) {
            goto done;
        }
    }

    // Get/create the script coverage object
    found = obj_get(scripts, script_name, &script_coverage);
    if (found < 0) {
        goto done;
    }
    if (!found || script_coverage == Py_None) {
        Py_XDECREF(script_coverage);
        script_coverage = PyDict_New();
        if (script_coverage == NULL) {
            goto done;
        }
        PyObject *covered_new = PyDict_New();
        if (covered_new == NULL) {
            goto done;
        }
        if (PyDict_SetItem(script_coverage, g.str_script, script) < 0 ||
            PyDict_SetItem(script_coverage, g.str_covered, covered_new) < 0) {
            Py_DECREF(covered_new);
            goto done;
        }
        Py_DECREF(covered_new);
        if (obj_setitem(scripts, script_name, script_coverage) < 0) {
            goto done;
        }
    }

    // Get/create the covered statement object
    lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) {
        goto done;
    }
    if (obj_subscript(script_coverage, g.str_covered, &covered) < 0) {
        goto done;
    }
    found = obj_get(covered, lineno_str, &covered_statement);
    if (found < 0) {
        goto done;
    }
    if (!found || covered_statement == Py_None) {
        Py_XDECREF(covered_statement);
        covered_statement = PyDict_New();
        if (covered_statement == NULL) {
            goto done;
        }
        if (PyDict_SetItem(covered_statement, g.str_statement, statement) < 0 ||
            PyDict_SetItem(covered_statement, g.str_count, g.zero) < 0 ||
            obj_setitem(covered, lineno_str, covered_statement) < 0) {
            goto done;
        }
    }

    // Increment the statement coverage count
    if (obj_subscript(covered_statement, g.str_count, &count) < 0) {
        goto done;
    }
    new_count = PyNumber_Add(count, g.one);
    if (new_count == NULL || obj_setitem(covered_statement, g.str_count, new_count) < 0) {
        goto done;
    }
    result = 0;

done:
    Py_XDECREF(new_count);
    Py_XDECREF(count);
    Py_XDECREF(covered_statement);
    Py_XDECREF(covered);
    Py_XDECREF(lineno_str);
    Py_XDECREF(script_coverage);
    Py_XDECREF(scripts);
    Py_XDECREF(lineno);
    Py_XDECREF(script_name);
    Py_DECREF(stmt_value);
    return result;
}


//
// Expression evaluation
//


// Evaluate a variable expression
static PyObject *eval_variable(PyObject *variable, PyObject *locals, PyObject *globals)
{
    // Keywords
    if (PyUnicode_Check(variable)) {
        Py_ssize_t length = PyUnicode_GetLength(variable);
        if (length == 4) {
            if (unicode_eq_ascii(variable, "null", 4)) {
                Py_RETURN_NONE;
            }
            if (unicode_eq_ascii(variable, "true", 4)) {
                Py_RETURN_TRUE;
            }
        } else if (length == 5 && unicode_eq_ascii(variable, "false", 5)) {
            Py_RETURN_FALSE;
        }
    }

    // Get the local variable value, if any
    if (locals != Py_None) {
        PyObject *value;
        int found = obj_get(locals, variable, &value);
        if (found < 0) {
            return NULL;
        }
        if (found) {
            return value;
        }
    }

    // Get the global variable value or None if undefined
    if (globals != NULL) {
        PyObject *value;
        int found = obj_get(globals, variable, &value);
        if (found < 0) {
            return NULL;
        }
        if (found) {
            return value;
        }
    }
    Py_RETURN_NONE;
}


// Call a resolved function value with evaluated arguments, applying the reference
// implementation's call error handling: BareScriptRuntimeError and BaseException propagate, other
// exceptions are optionally logged and produce None (or the ValueArgsError return value). Returns
// a new reference or NULL with an exception set.
static PyObject *call_function_value(
    PyObject *func_value, PyObject *func_args, PyObject *func_name, ExecCtx *ctx, PyObject *script,
    PyObject *statement, int intrinsic
)
{
    PyObject *result;
    int counter_synced = 0;

    if (intrinsic >= 0 && func_value == g_intrinsics[intrinsic].py_func && PyList_CheckExact(func_args)) {
        // Library intrinsic - the call resolves to the original library function, whose C
        // implementation is observably identical and cannot observe options (no counter sync)
        result = g_intrinsics[intrinsic].handler(func_args);
    } else if (Py_IS_TYPE(func_value, &ScriptFunctionType) && ctx->is_exec) {
        // BareScript function - execute directly on this execution context, skipping the generic
        // call machinery and the per-call context rebuild. Expression-evaluation contexts take
        // the generic path below, which performs the reference implementation's per-call setup
        // (globals subscript, statement counter default) and its error handling.
        ScriptFunctionObject *script_function = (ScriptFunctionObject *)func_value;
        result = script_function_invoke_ctx(script_function, func_args, ctx);
    } else {
        // Call the function - sync the statement counter around the call since the callable can
        // observe and update options['statementCount']
        if (exec_ctx_sync_out(ctx) < 0) {
            return NULL;
        }
        counter_synced = 1;
        PyObject *call_args[2] = {func_args, ctx->options};
        result = PyObject_Vectorcall(func_value, call_args, 2, NULL);
        if (result != NULL && exec_ctx_sync_in(ctx) < 0) {
            Py_CLEAR(result);
        }
    }
    if (result != NULL) {
        return result;
    }

    // BareScriptRuntimeError and BaseException propagate
    if (PyErr_ExceptionMatches(g.runtime_error) || !PyErr_ExceptionMatches(PyExc_Exception)) {
        return NULL;
    }

    // Get the error
    PyObject *error = get_raised_exception();
    if (error == NULL) {
        return NULL;
    }

    // Log and return null
    if (ctx->options != Py_None) {
        PyObject *log_fn = NULL;
        int has_log = obj_get(ctx->options, g.str_logFn, &log_fn);
        if (has_log < 0) {
            Py_DECREF(error);
            return NULL;
        }
        if (has_log) {
            PyObject *debug = NULL;
            int has_debug = obj_get(ctx->options, g.str_debug, &debug);
            if (has_debug < 0) {
                Py_DECREF(log_fn);
                Py_DECREF(error);
                return NULL;
            }
            int is_debug = 0;
            if (has_debug) {
                is_debug = PyObject_IsTrue(debug);
                Py_DECREF(debug);
                if (is_debug < 0) {
                    Py_DECREF(log_fn);
                    Py_DECREF(error);
                    return NULL;
                }
            }
            if (is_debug) {
                PyObject *message = PyUnicode_FromFormat(
                    "BareScript: Function \"%S\" failed with error: %S", func_name, error
                );
                PyObject *error_message = NULL;
                PyObject *error_str = NULL;
                PyObject *log_result = NULL;
                if (message != NULL) {
                    error_message = PyObject_CallFunctionObjArgs(g.runtime_error, script, statement, message, NULL);
                    Py_DECREF(message);
                }
                if (error_message != NULL) {
                    error_str = PyObject_Str(error_message);
                    Py_DECREF(error_message);
                }
                if (error_str != NULL) {
                    log_result = PyObject_CallOneArg(log_fn, error_str);
                    Py_DECREF(error_str);
                }
                if (log_result == NULL) {
                    Py_DECREF(log_fn);
                    Py_DECREF(error);
                    return NULL;
                }
                Py_DECREF(log_result);
            }
            Py_DECREF(log_fn);
        }
    }

    // Function argument error - return the error return value
    int is_args_error = PyObject_IsInstance(error, g.value_args_error);
    if (is_args_error < 0) {
        Py_DECREF(error);
        return NULL;
    }
    if (is_args_error) {
        result = PyObject_GetAttr(error, g.str_return_value);
    } else {
        result = Py_NewRef(Py_None);
    }
    Py_DECREF(error);
    // Reload the counter only when it was synced out before the call - the intrinsic and direct
    // ScriptFunction branches keep the authoritative count in C (the dict may be stale)
    if (counter_synced && result != NULL && exec_ctx_sync_in(ctx) < 0) {
        Py_CLEAR(result);
    }
    return result;
}


// Evaluate a function expression
static PyObject *eval_function(
    PyObject *func, ExecCtx *ctx, PyObject *locals, int builtins, PyObject *script, PyObject *statement
)
{
    PyObject *globals = ctx->globals;
    PyObject *func_name = NULL;
    PyObject *args_expr = NULL;
    PyObject *func_args = NULL;
    PyObject *func_value = NULL;
    PyObject *result = NULL;

    // Prefetch the function expression fields in a single dict walk (args_expr NULL = absent)
    int args_known = 0;
    if (PyDict_CheckExact(func)) {
        dict_prefetch3(func, g.str_name, &func_name, g.str_args, &args_expr, NULL, NULL);
        args_known = 1;
    }
    if (func_name == NULL && obj_subscript(func, g.str_name, &func_name) < 0) {
        Py_XDECREF(args_expr);
        return NULL;
    }

    // "if" built-in function?
    if (PyUnicode_Check(func_name) && unicode_eq_ascii(func_name, "if", 2)) {
        if (!args_known) {
            int found = obj_get(func, g.str_args, &args_expr);
            if (found < 0) {
                goto done;
            }
        }
        Py_ssize_t args_expr_length = 0;
        if (args_expr != NULL) {
            args_expr_length = PyObject_Length(args_expr);
            if (args_expr_length < 0) {
                goto done;
            }
        }

        // Evaluate the value expression (a None expression is treated as not-provided)
        PyObject *cond_value = NULL;
        if (args_expr_length >= 1) {
            PyObject *value_expr = PySequence_GetItem(args_expr, 0);
            if (value_expr == NULL) {
                goto done;
            }
            if (value_expr != Py_None) {
                cond_value = evaluate_expression_c(value_expr, ctx, locals, builtins, script, statement);
                Py_DECREF(value_expr);
                if (cond_value == NULL) {
                    goto done;
                }
            } else {
                Py_DECREF(value_expr);
            }
        }
        if (cond_value == NULL) {
            cond_value = Py_NewRef(Py_False);
        }
        int cond = value_boolean_c(cond_value);
        Py_DECREF(cond_value);

        // Evaluate the true/false expression (a None expression is treated as not-provided)
        Py_ssize_t ix_result = cond ? 1 : 2;
        PyObject *result_expr = NULL;
        if (args_expr_length >= ix_result + 1) {
            result_expr = PySequence_GetItem(args_expr, ix_result);
            if (result_expr == NULL) {
                goto done;
            }
            if (result_expr == Py_None) {
                Py_CLEAR(result_expr);
            }
        }
        if (result_expr != NULL) {
            result = evaluate_expression_c(result_expr, ctx, locals, builtins, script, statement);
            Py_DECREF(result_expr);
        } else {
            result = Py_NewRef(Py_None);
        }
        goto done;
    }

    // Compute the function arguments
    if (!args_known) {
        int found = obj_get(func, g.str_args, &args_expr);
        if (found < 0) {
            goto done;
        }
    }
    if (args_expr == NULL || args_expr == Py_None) {
        func_args = Py_NewRef(Py_None);
    } else if (PyList_CheckExact(args_expr)) {
        Py_ssize_t args_length = PyList_GET_SIZE(args_expr);
        func_args = PyList_New(args_length);
        if (func_args == NULL) {
            goto done;
        }
        for (Py_ssize_t ix_arg = 0; ix_arg < args_length; ix_arg++) {
            PyObject *arg_expr;
            if (list_get_ref(args_expr, ix_arg, &arg_expr) < 0) {
                goto done;
            }
            PyObject *arg_value = evaluate_expression_c(arg_expr, ctx, locals, builtins, script, statement);
            Py_DECREF(arg_expr);
            if (arg_value == NULL) {
                goto done;
            }
            PyList_SET_ITEM(func_args, ix_arg, arg_value);
        }
    } else {
        // Generic sequence of argument expressions
        PyObject *args_fast = PySequence_Fast(args_expr, "function arguments must be a sequence");
        if (args_fast == NULL) {
            goto done;
        }
        Py_ssize_t args_length = PySequence_Fast_GET_SIZE(args_fast);
        func_args = PyList_New(args_length);
        if (func_args == NULL) {
            Py_DECREF(args_fast);
            goto done;
        }
        for (Py_ssize_t ix_arg = 0; ix_arg < args_length; ix_arg++) {
            PyObject *arg_expr = PySequence_Fast_GET_ITEM(args_fast, ix_arg);
            Py_INCREF(arg_expr);
            PyObject *arg_value = evaluate_expression_c(arg_expr, ctx, locals, builtins, script, statement);
            Py_DECREF(arg_expr);
            if (arg_value == NULL) {
                Py_DECREF(args_fast);
                goto done;
            }
            PyList_SET_ITEM(func_args, ix_arg, arg_value);
        }
        Py_DECREF(args_fast);
    }

    // Global/local function?
    int found_value = 0;
    if (locals != Py_None) {
        found_value = obj_get(locals, func_name, &func_value);
        if (found_value < 0) {
            goto done;
        }
    }
    if (!found_value && globals != NULL) {
        found_value = obj_get(globals, func_name, &func_value);
        if (found_value < 0) {
            goto done;
        }
    }
    if (!found_value && builtins) {
        found_value = obj_get(g.expression_functions, func_name, &func_value);
        if (found_value < 0) {
            goto done;
        }
    }

    // A found None value is treated the same as not-found
    if (found_value && func_value == Py_None) {
        Py_CLEAR(func_value);
        found_value = 0;
    }

    if (found_value) {
        result = call_function_value(func_value, func_args, func_name, ctx, script, statement, -1);
        goto done;
    }

    // Undefined function
    set_runtime_error(script, statement, PyUnicode_FromFormat("Undefined function \"%S\"", func_name));

done:
    Py_XDECREF(func_value);
    Py_XDECREF(func_args);
    Py_XDECREF(args_expr);
    Py_XDECREF(func_name);
    return result;
}


// Map a binary comparison operator to a rich comparison opid
static inline int binary_op_to_opid(BinaryOp op)
{
    switch (op) {
    case BINARY_LT:
        return Py_LT;
    case BINARY_LTE:
        return Py_LE;
    case BINARY_GT:
        return Py_GT;
    case BINARY_GTE:
        return Py_GE;
    case BINARY_EQ:
        return Py_EQ;
    default: // BINARY_NEQ
        return Py_NE;
    }
}


// Apply a binary operator to evaluated left and right values (borrowed references). Returns a
// new reference, or NULL with an exception set.
static PyObject *apply_binary_op(BinaryOp op, PyObject *left, PyObject *right)
{
    PyObject *result = NULL;

    // Float fast path
    if (PyFloat_CheckExact(left) && PyFloat_CheckExact(right)) {
        double left_number = PyFloat_AS_DOUBLE(left);
        double right_number = PyFloat_AS_DOUBLE(right);
        switch (op) {
        case BINARY_ADD:
            result = PyFloat_FromDouble(left_number + right_number);
            goto apply_done;
        case BINARY_SUB:
            result = PyFloat_FromDouble(left_number - right_number);
            goto apply_done;
        case BINARY_MUL:
            result = PyFloat_FromDouble(left_number * right_number);
            goto apply_done;
        case BINARY_DIV:
            if (right_number != 0.) {
                result = PyFloat_FromDouble(left_number / right_number);
                goto apply_done;
            }
            break;
        case BINARY_LT:
            result = Py_NewRef((left_number < right_number) ? Py_True : Py_False);
            goto apply_done;
        case BINARY_LTE:
            result = Py_NewRef((left_number <= right_number) ? Py_True : Py_False);
            goto apply_done;
        case BINARY_GT:
            result = Py_NewRef((left_number > right_number) ? Py_True : Py_False);
            goto apply_done;
        case BINARY_GTE:
            result = Py_NewRef((left_number >= right_number) ? Py_True : Py_False);
            goto apply_done;
        case BINARY_EQ:
            result = Py_NewRef((left_number == right_number) ? Py_True : Py_False);
            goto apply_done;
        case BINARY_NEQ:
            result = Py_NewRef((left_number != right_number) ? Py_True : Py_False);
            goto apply_done;
        default:
            break;
        }
    }

    // Generic operator implementations
    switch (op) {
    case BINARY_ADD: {
        if (is_number(left) && is_number(right)) {
            // number + number
            result = PyNumber_Add(left, right);
        } else if (PyUnicode_CheckExact(left) && PyUnicode_CheckExact(right)) {
            // string + string
            result = PyNumber_Add(left, right);
        } else if (PyUnicode_CheckExact(left)) {
            // string + <any>
            PyObject *right_str = PyObject_CallOneArg(g.value_string, right);
            if (right_str != NULL) {
                result = PyNumber_Add(left, right_str);
                Py_DECREF(right_str);
            }
        } else if (PyUnicode_CheckExact(right)) {
            // <any> + string
            PyObject *left_str = PyObject_CallOneArg(g.value_string, left);
            if (left_str != NULL) {
                result = PyNumber_Add(left_str, right);
                Py_DECREF(left_str);
            }
        } else if (PyDate_Check(left) && is_number(right)) {
            // datetime + number
            PyObject *left_dt = PyObject_CallOneArg(g.value_normalize_datetime, left);
            if (left_dt != NULL) {
                PyObject *delta = PyObject_CallFunction((PyObject *)PyDateTimeAPI->DeltaType, "iiiO", 0, 0, 0, right);
                if (delta != NULL) {
                    result = PyNumber_Add(left_dt, delta);
                    Py_DECREF(delta);
                }
                Py_DECREF(left_dt);
            }
        } else if (is_number(left) && PyDate_Check(right)) {
            // number + datetime
            PyObject *right_dt = PyObject_CallOneArg(g.value_normalize_datetime, right);
            if (right_dt != NULL) {
                PyObject *delta = PyObject_CallFunction((PyObject *)PyDateTimeAPI->DeltaType, "iiiO", 0, 0, 0, left);
                if (delta != NULL) {
                    result = PyNumber_Add(right_dt, delta);
                    Py_DECREF(delta);
                }
                Py_DECREF(right_dt);
            }
        } else {
            // Invalid operation values
            result = Py_NewRef(Py_None);
        }
        break;
    }

    case BINARY_SUB: {
        if (is_number(left) && is_number(right)) {
            // number - number
            result = PyNumber_Subtract(left, right);
        } else if (PyDate_Check(left) && PyDate_Check(right)) {
            // datetime - datetime
            PyObject *left_dt = PyObject_CallOneArg(g.value_normalize_datetime, left);
            PyObject *right_dt = (left_dt != NULL) ? PyObject_CallOneArg(g.value_normalize_datetime, right) : NULL;
            PyObject *delta = (right_dt != NULL) ? PyNumber_Subtract(left_dt, right_dt) : NULL;
            PyObject *seconds = (delta != NULL) ? PyObject_CallMethodNoArgs(delta, g.str_total_seconds) : NULL;
            if (seconds != NULL) {
                double milliseconds = PyFloat_AsDouble(seconds) * 1000.;
                if (milliseconds == -1000. && PyErr_Occurred()) {
                    Py_DECREF(seconds);
                    seconds = NULL;
                } else {
                    PyObject *milliseconds_obj = PyFloat_FromDouble(milliseconds);
                    if (milliseconds_obj != NULL) {
                        PyObject *round_args[2] = {milliseconds_obj, g.zero};
                        result = PyObject_Vectorcall(g.value_round_number, round_args, 2, NULL);
                        Py_DECREF(milliseconds_obj);
                    }
                }
            }
            Py_XDECREF(seconds);
            Py_XDECREF(delta);
            Py_XDECREF(right_dt);
            Py_XDECREF(left_dt);
        } else {
            // Invalid operation values
            result = Py_NewRef(Py_None);
        }
        break;
    }

    case BINARY_MUL:
        result = (is_number(left) && is_number(right)) ? PyNumber_Multiply(left, right) : Py_NewRef(Py_None);
        break;

    case BINARY_DIV:
        result = (is_number(left) && is_number(right)) ? PyNumber_TrueDivide(left, right) : Py_NewRef(Py_None);
        break;

    case BINARY_LT:
    case BINARY_LTE:
    case BINARY_GT:
    case BINARY_GTE:
    case BINARY_EQ:
    case BINARY_NEQ: {
        int opid = binary_op_to_opid(op);
        if (is_number(left) && is_number(right)) {
            result = PyObject_RichCompare(left, right, opid);
        } else {
            // Mirror value.value_compare for the common types; call the Python implementation
            // for everything else (datetimes, arrays, objects, mixed types)
            long compare_value;
            int compare_known = 1;
            if (left == Py_None) {
                compare_value = (right == Py_None) ? 0 : -1;
            } else if (right == Py_None) {
                compare_value = 1;
            } else if (PyUnicode_CheckExact(left) && PyUnicode_CheckExact(right)) {
                compare_value = PyUnicode_Compare(left, right);
            } else if (PyBool_Check(left) && PyBool_Check(right)) {
                int left_bool = (left == Py_True);
                int right_bool = (right == Py_True);
                compare_value = (left_bool < right_bool) ? -1 : ((left_bool == right_bool) ? 0 : 1);
            } else {
                compare_known = 0;
                PyObject *compare_args[2] = {left, right};
                PyObject *compare = PyObject_Vectorcall(g.value_compare, compare_args, 2, NULL);
                if (compare != NULL) {
                    compare_value = PyLong_AsLong(compare);
                    Py_DECREF(compare);
                    compare_known = !(compare_value == -1 && PyErr_Occurred());
                }
            }
            if (compare_known) {
                int compare_result;
                switch (opid) {
                case Py_LT:
                    compare_result = compare_value < 0;
                    break;
                case Py_LE:
                    compare_result = compare_value <= 0;
                    break;
                case Py_GT:
                    compare_result = compare_value > 0;
                    break;
                case Py_GE:
                    compare_result = compare_value >= 0;
                    break;
                case Py_EQ:
                    compare_result = compare_value == 0;
                    break;
                default: // Py_NE
                    compare_result = compare_value != 0;
                    break;
                }
                result = Py_NewRef(compare_result ? Py_True : Py_False);
            }
        }
        break;
    }

    case BINARY_MOD:
        result = (is_number(left) && is_number(right)) ? PyNumber_Remainder(left, right) : Py_NewRef(Py_None);
        break;

    case BINARY_POW:
        result = (is_number(left) && is_number(right)) ? PyNumber_Power(left, right, Py_None) : Py_NewRef(Py_None);
        break;

    case BINARY_BIT_AND:
    case BINARY_BIT_OR:
    case BINARY_BIT_XOR:
    case BINARY_SHL:
    case BINARY_SHR: {
        // int <op> int (floats with integral values are converted)
        PyObject *left_int = integral_long(left);
        PyObject *right_int = (left_int != NULL) ? integral_long(right) : NULL;
        if (left_int != NULL && right_int != NULL) {
            switch (op) {
            case BINARY_BIT_AND:
                result = PyNumber_And(left_int, right_int);
                break;
            case BINARY_BIT_OR:
                result = PyNumber_Or(left_int, right_int);
                break;
            case BINARY_BIT_XOR:
                result = PyNumber_Xor(left_int, right_int);
                break;
            case BINARY_SHL:
                result = PyNumber_Lshift(left_int, right_int);
                break;
            default: // BINARY_SHR
                result = PyNumber_Rshift(left_int, right_int);
                break;
            }
        } else if (!PyErr_Occurred()) {
            // Invalid operation values
            result = Py_NewRef(Py_None);
        }
        Py_XDECREF(right_int);
        Py_XDECREF(left_int);
        break;
    }

    default:
        // Unreachable - AND/OR handled above
        result = Py_NewRef(Py_None);
        break;
    }

apply_done:
    return result;
}


// Evaluate a binary expression
static PyObject *eval_binary(
    PyObject *binary, ExecCtx *ctx, PyObject *locals, int builtins, PyObject *script, PyObject *statement
)
{
    PyObject *op_obj = NULL;
    PyObject *left_expr = NULL;
    PyObject *right_expr = NULL;
    PyObject *left = NULL;
    PyObject *right = NULL;
    PyObject *result = NULL;

    // Prefetch the binary expression fields in a single dict walk. A missing field falls back to
    // a subscript at its point of use, preserving the reference implementation's error behavior.
    if (PyDict_CheckExact(binary)) {
        dict_prefetch3(binary, g.str_op, &op_obj, g.str_left, &left_expr, g.str_right, &right_expr);
    }

    // Parse the operator
    if (op_obj == NULL && obj_subscript(binary, g.str_op, &op_obj) < 0) {
        goto fail_exprs;
    }
    BinaryOp op = parse_binary_op(op_obj);
    Py_CLEAR(op_obj);

    // Evaluate the left expression
    if (left_expr == NULL && obj_subscript(binary, g.str_left, &left_expr) < 0) {
        goto fail_exprs;
    }
    left = evaluate_expression_c(left_expr, ctx, locals, builtins, script, statement);
    Py_CLEAR(left_expr);
    if (left == NULL) {
        goto fail_exprs;
    }

    // Short-circuiting "and" and "or" binary operators
    if (op == BINARY_AND || op == BINARY_OR) {
        int left_bool = value_boolean_c(left);
        if ((op == BINARY_AND && !left_bool) || (op == BINARY_OR && left_bool)) {
            Py_XDECREF(right_expr);
            return left;
        }
        Py_DECREF(left);
        if (right_expr == NULL && obj_subscript(binary, g.str_right, &right_expr) < 0) {
            return NULL;
        }
        result = evaluate_expression_c(right_expr, ctx, locals, builtins, script, statement);
        Py_DECREF(right_expr);
        return result;
    }

    // Evaluate the right expression
    if (right_expr == NULL && obj_subscript(binary, g.str_right, &right_expr) < 0) {
        Py_DECREF(left);
        return NULL;
    }
    right = evaluate_expression_c(right_expr, ctx, locals, builtins, script, statement);
    Py_CLEAR(right_expr);
    if (right == NULL) {
        Py_DECREF(left);
        return NULL;
    }

    result = apply_binary_op(op, left, right);
    Py_DECREF(left);
    Py_DECREF(right);
    return result;

fail_exprs:
    Py_XDECREF(op_obj);
    Py_XDECREF(left_expr);
    Py_XDECREF(right_expr);
    return NULL;
}


// Apply a unary operator to an evaluated value (borrowed reference). Returns a new reference, or
// NULL with an exception set.
static PyObject *apply_unary_op(UnaryOp op, PyObject *value)
{
    PyObject *result = NULL;
    if (op == UNARY_NOT) {
        result = Py_NewRef(value_boolean_c(value) ? Py_False : Py_True);
    } else if (op == UNARY_NEG) {
        if (PyFloat_CheckExact(value)) {
            result = PyFloat_FromDouble(-PyFloat_AS_DOUBLE(value));
        } else if (PyLong_CheckExact(value)) {
            result = PyNumber_Negative(value);
        } else {
            // Invalid operation value
            result = Py_NewRef(Py_None);
        }
    } else { // UNARY_INVERT
        PyObject *value_int = integral_long(value);
        if (value_int != NULL) {
            result = PyNumber_Invert(value_int);
            Py_DECREF(value_int);
        } else if (!PyErr_Occurred()) {
            // Invalid operation value
            result = Py_NewRef(Py_None);
        }
    }
    return result;
}


// Evaluate a unary expression
static PyObject *eval_unary(
    PyObject *unary, ExecCtx *ctx, PyObject *locals, int builtins, PyObject *script, PyObject *statement
)
{
    PyObject *op_obj = NULL;
    PyObject *sub_expr = NULL;
    PyObject *value = NULL;
    PyObject *result = NULL;

    // Prefetch the unary expression fields in a single dict walk
    if (PyDict_CheckExact(unary)) {
        dict_prefetch3(unary, g.str_op, &op_obj, g.str_expr, &sub_expr, NULL, NULL);
    }

    // Parse the operator
    if (op_obj == NULL && obj_subscript(unary, g.str_op, &op_obj) < 0) {
        Py_XDECREF(sub_expr);
        return NULL;
    }
    UnaryOp op = parse_unary_op(op_obj);
    Py_CLEAR(op_obj);

    // Evaluate the expression
    if (sub_expr == NULL && obj_subscript(unary, g.str_expr, &sub_expr) < 0) {
        return NULL;
    }
    value = evaluate_expression_c(sub_expr, ctx, locals, builtins, script, statement);
    Py_CLEAR(sub_expr);
    if (value == NULL) {
        return NULL;
    }

    result = apply_unary_op(op, value);
    Py_DECREF(value);
    return result;
}


// Evaluate an expression model. locals, script, and statement are never NULL - Py_None indicates
// "not provided", matching the reference implementation's None defaults. The globals are cached in
// the execution context.
static PyObject *evaluate_expression_c(
    PyObject *expr, ExecCtx *ctx, PyObject *locals, int builtins, PyObject *script, PyObject *statement
)
{
    PyObject *result = NULL;

    if (!PyDict_CheckExact(expr)) {
        PyErr_SetString(PyExc_TypeError, "expression model must be a dict");
        return NULL;
    }

    if (Py_EnterRecursiveCall(" while evaluating a BareScript expression")) {
        return NULL;
    }

    // Dispatch on the expression dict's first (and only, for valid models) key
    Py_ssize_t pos = 0;
    PyObject *key;
    PyObject *value_borrowed;
    if (PyDict_Next(expr, &pos, &key, &value_borrowed)) {
        PyObject *value = Py_NewRef(value_borrowed);
        switch (expr_kind(key)) {
        case EXPR_NUMBER:
        case EXPR_STRING:
            result = value;
            goto done;
        case EXPR_VARIABLE:
            result = eval_variable(value, locals, ctx->globals);
            break;
        case EXPR_FUNCTION:
            result = eval_function(value, ctx, locals, builtins, script, statement);
            break;
        case EXPR_BINARY:
            result = eval_binary(value, ctx, locals, builtins, script, statement);
            break;
        case EXPR_UNARY:
            result = eval_unary(value, ctx, locals, builtins, script, statement);
            break;
        case EXPR_GROUP:
            result = evaluate_expression_c(value, ctx, locals, builtins, script, statement);
            break;
        default: { // EXPR_UNKNOWN
            // Mirror the reference implementation - an unrecognized expression is subscripted as a
            // group (raising KeyError unless a 'group' key exists)
            PyObject *group;
            if (obj_subscript(expr, g.str_group, &group) == 0) {
                result = evaluate_expression_c(group, ctx, locals, builtins, script, statement);
                Py_DECREF(group);
            }
            break;
        }
        }
        Py_DECREF(value);
    } else {
        // Empty expression dict - mirror the reference implementation's expr['group'] KeyError
        PyObject *group;
        if (obj_subscript(expr, g.str_group, &group) == 0) {
            result = evaluate_expression_c(group, ctx, locals, builtins, script, statement);
            Py_DECREF(group);
        }
    }

done:
    Py_LeaveRecursiveCall();
    return result;
}


//
// Script execution
//


// Execute the include statement (cold path)
static int execute_include_statement(PyObject *script, PyObject *statement, PyObject *stmt_include, ExecCtx *ctx)
{
    PyObject *options = ctx->options;
    PyObject *globals = ctx->globals;
    PyObject *system_prefix = NULL;
    PyObject *fetch_fn = NULL;
    PyObject *log_fn = NULL;
    PyObject *url_fn = NULL;
    PyObject *includes = NULL;
    PyObject *includes_fast = NULL;
    int result = -1;

    // Sync the statement counter - the fetch/url/log callables and the options copy below can
    // observe options['statementCount']
    if (exec_ctx_sync_out(ctx) < 0) {
        return -1;
    }

    // Get the include options
    if (obj_get(options, g.str_systemPrefix, &system_prefix) < 0 ||
        obj_get(options, g.str_fetchFn, &fetch_fn) < 0 ||
        obj_get(options, g.str_logFn, &log_fn) < 0 ||
        obj_get(options, g.str_urlFn, &url_fn) < 0) {
        goto done;
    }
    if (system_prefix == Py_None) {
        Py_CLEAR(system_prefix);
    }
    if (fetch_fn == Py_None) {
        Py_CLEAR(fetch_fn);
    }
    if (log_fn == Py_None) {
        Py_CLEAR(log_fn);
    }
    if (url_fn == Py_None) {
        Py_CLEAR(url_fn);
    }

    // Iterate the includes
    if (obj_subscript(stmt_include, g.str_includes, &includes) < 0) {
        goto done;
    }
    includes_fast = PySequence_Fast(includes, "includes must be a sequence");
    if (includes_fast == NULL) {
        goto done;
    }
    Py_ssize_t includes_length = PySequence_Fast_GET_SIZE(includes_fast);
    for (Py_ssize_t ix_include = 0; ix_include < includes_length; ix_include++) {
        PyObject *include = PySequence_Fast_GET_ITEM(includes_fast, ix_include);
        Py_INCREF(include);

        PyObject *include_url = NULL;
        PyObject *system_obj = NULL;
        PyObject *global_includes = NULL;
        PyObject *include_text = NULL;
        PyObject *include_script = NULL;
        PyObject *include_options = NULL;
        int include_ok = 0;

        // Get the include URL
        if (obj_subscript(include, g.str_url, &include_url) < 0) {
            goto include_done;
        }

        // Fixup system include URL
        int system_include = 0;
        int found = obj_get(include, g.str_system, &system_obj);
        if (found < 0) {
            goto include_done;
        }
        if (found) {
            system_include = PyObject_IsTrue(system_obj);
            if (system_include < 0) {
                goto include_done;
            }
        }
        if (system_include && system_prefix != NULL) {
            PyObject *fixup_args[2] = {system_prefix, include_url};
            PyObject *fixed_url = PyObject_Vectorcall(g.url_file_relative, fixup_args, 2, NULL);
            if (fixed_url == NULL) {
                goto include_done;
            }
            Py_SETREF(include_url, fixed_url);
        } else if (url_fn != NULL) {
            PyObject *fixed_url = PyObject_CallOneArg(url_fn, include_url);
            if (fixed_url == NULL) {
                goto include_done;
            }
            Py_SETREF(include_url, fixed_url);
        }

        // Already included?
        found = obj_get(globals, g.str_includes_name, &global_includes);
        if (found < 0) {
            goto include_done;
        }
        if (!found || !PyDict_Check(global_includes)) {
            Py_XDECREF(global_includes);
            global_includes = PyDict_New();
            if (global_includes == NULL || obj_setitem(globals, g.str_includes_name, global_includes) < 0) {
                goto include_done;
            }
        }
        PyObject *already_included = NULL;
        found = obj_get(global_includes, include_url, &already_included);
        if (found < 0) {
            goto include_done;
        }
        if (found) {
            int is_included = PyObject_IsTrue(already_included);
            Py_DECREF(already_included);
            if (is_included < 0) {
                goto include_done;
            }
            if (is_included) {
                include_ok = 1;
                goto include_done;
            }
        }
        if (PyDict_SetItem(global_includes, include_url, Py_True) < 0) {
            goto include_done;
        }

        // Fetch the URL
        if (fetch_fn != NULL) {
            PyObject *request = PyDict_New();
            if (request == NULL) {
                goto include_done;
            }
            if (PyDict_SetItem(request, g.str_url, include_url) < 0) {
                Py_DECREF(request);
                goto include_done;
            }
            include_text = PyObject_CallOneArg(fetch_fn, request);
            Py_DECREF(request);
            if (include_text == NULL) {
                // Bare except in the reference implementation - clear any error
                PyErr_Clear();
            }
        }
        if (include_text == NULL || include_text == Py_None) {
            set_runtime_error(script, statement, PyUnicode_FromFormat("Include of \"%S\" failed", include_url));
            goto include_done;
        }

        // Parse the include script
        include_script = PyObject_CallFunction(g.parse_script, "OiO", include_text, 1, include_url);
        if (include_script == NULL) {
            goto include_done;
        }
        if (system_include) {
            if (obj_setitem(include_script, g.str_system, Py_True) < 0) {
                goto include_done;
            }
        }

        // Execute the include script
        if (PyDict_CheckExact(options)) {
            include_options = PyDict_Copy(options);
        } else {
            include_options = PyObject_CallMethodNoArgs(options, g.str_copy);
        }
        if (include_options == NULL) {
            goto include_done;
        }
        PyObject *partial_args[2] = {g.url_file_relative, include_url};
        PyObject *include_url_fn = PyObject_Vectorcall(g.partial, partial_args, 2, NULL);
        if (include_url_fn == NULL) {
            goto include_done;
        }
        int set_result = obj_setitem(include_options, g.str_urlFn, include_url_fn);
        Py_DECREF(include_url_fn);
        if (set_result < 0) {
            goto include_done;
        }
        PyObject *include_statements;
        if (obj_subscript(include_script, g.str_statements, &include_statements) < 0) {
            goto include_done;
        }
        CompiledBody *include_body = NULL;
        if (PyList_CheckExact(include_statements)) {
            include_body = compile_body(include_statements, NULL, 0);
            if (include_body == NULL) {
                Py_DECREF(include_statements);
                goto include_done;
            }
        }
        ExecCtx include_ctx;
        if (exec_ctx_init_exec(&include_ctx, include_options) < 0) {
            exec_ctx_fini(&include_ctx);
            compiled_body_free(include_body);
            Py_DECREF(include_statements);
            goto include_done;
        }
        Scope include_scope = {Py_None, NULL, NULL, 0};
        PyObject *include_result =
            execute_script_helper(include_script, include_statements, &include_ctx, &include_scope, include_body);
        exec_ctx_sync_out_final(&include_ctx);
        exec_ctx_fini(&include_ctx);
        compiled_body_free(include_body);
        Py_DECREF(include_statements);
        if (include_result == NULL) {
            goto include_done;
        }
        Py_DECREF(include_result);

        // Run the bare-script linter?
        if (log_fn != NULL) {
            PyObject *debug = NULL;
            found = obj_get(options, g.str_debug, &debug);
            if (found < 0) {
                goto include_done;
            }
            int is_debug = 0;
            if (found) {
                is_debug = PyObject_IsTrue(debug);
                Py_DECREF(debug);
                if (is_debug < 0) {
                    goto include_done;
                }
            }
            if (is_debug) {
                PyObject *lint_args[2] = {include_script, globals};
                PyObject *warnings = PyObject_Vectorcall(g.lint_script, lint_args, 2, NULL);
                if (warnings == NULL) {
                    goto include_done;
                }
                int has_warnings = PyObject_IsTrue(warnings);
                if (has_warnings < 0) {
                    Py_DECREF(warnings);
                    goto include_done;
                }
                if (has_warnings) {
                    Py_ssize_t warnings_length = PyObject_Length(warnings);
                    PyObject *prefix_message = (warnings_length >= 0) ? PyUnicode_FromFormat(
                        "BareScript: Include \"%S\" static analysis... %zd warning%s:",
                        include_url, warnings_length, (warnings_length > 1) ? "s" : ""
                    ) : NULL;
                    if (prefix_message == NULL) {
                        Py_DECREF(warnings);
                        goto include_done;
                    }
                    PyObject *log_result = PyObject_CallOneArg(log_fn, prefix_message);
                    Py_DECREF(prefix_message);
                    if (log_result == NULL) {
                        Py_DECREF(warnings);
                        goto include_done;
                    }
                    Py_DECREF(log_result);

                    PyObject *warnings_fast = PySequence_Fast(warnings, "lint warnings must be a sequence");
                    Py_DECREF(warnings);
                    if (warnings_fast == NULL) {
                        goto include_done;
                    }
                    Py_ssize_t warnings_count = PySequence_Fast_GET_SIZE(warnings_fast);
                    for (Py_ssize_t ix_warning = 0; ix_warning < warnings_count; ix_warning++) {
                        PyObject *warning = PySequence_Fast_GET_ITEM(warnings_fast, ix_warning);
                        PyObject *warning_message = PyUnicode_FromFormat("BareScript: %S", warning);
                        if (warning_message == NULL) {
                            Py_DECREF(warnings_fast);
                            goto include_done;
                        }
                        log_result = PyObject_CallOneArg(log_fn, warning_message);
                        Py_DECREF(warning_message);
                        if (log_result == NULL) {
                            Py_DECREF(warnings_fast);
                            goto include_done;
                        }
                        Py_DECREF(log_result);
                    }
                    Py_DECREF(warnings_fast);
                } else {
                    Py_DECREF(warnings);
                }
            }
        }
        include_ok = 1;

    include_done:
        Py_XDECREF(include_options);
        Py_XDECREF(include_script);
        Py_XDECREF(include_text);
        Py_XDECREF(global_includes);
        Py_XDECREF(system_obj);
        Py_XDECREF(include_url);
        Py_DECREF(include);
        if (!include_ok) {
            goto done;
        }
    }
    result = 0;

done:
    Py_XDECREF(includes_fast);
    Py_XDECREF(includes);
    Py_XDECREF(url_fn);
    Py_XDECREF(log_fn);
    Py_XDECREF(fetch_fn);
    Py_XDECREF(system_prefix);

    // Reload the statement counter - the external callables may have changed it
    if (result == 0 && exec_ctx_sync_in(ctx) < 0) {
        result = -1;
    }
    return result;
}


// Evaluate a compiled expression node. Mirrors evaluate_expression_c over the compiled tree.
static PyObject *eval_compiled(
    CompiledExpr *expr, ExecCtx *ctx, Scope *scope, PyObject *script, PyObject *statement
)
{
    PyObject *result = NULL;

    switch (expr->kind) {
    case CEXPR_LITERAL:
        return Py_NewRef(expr->value);
    case CEXPR_NULL:
        Py_RETURN_NONE;
    case CEXPR_TRUE:
        Py_RETURN_TRUE;
    case CEXPR_FALSE:
        Py_RETURN_FALSE;

    case CEXPR_VARIABLE: {
        // Get the local variable value, if any (a NULL slot mirrors a locals dict miss)
        if (scope->slots != NULL) {
            if (expr->slot >= 0) {
                PyObject *value = scope->slots[expr->slot];
                if (value != NULL) {
                    return Py_NewRef(value);
                }
            }
        } else if (scope->dict != Py_None) {
            PyObject *value;
            int found = obj_get(scope->dict, expr->value, &value);
            if (found != 0) {
                return (found < 0) ? NULL : value;
            }
        }

        // Get the global variable value or None if undefined
        if (ctx->globals != NULL) {
            PyObject *value;
            int found = obj_get(ctx->globals, expr->value, &value);
            if (found != 0) {
                return (found < 0) ? NULL : value;
            }
        }
        Py_RETURN_NONE;
    }
    default:
        break;
    }

    // No recursion guard - compiled tree depth is bounded at compile time
    // (COMPILED_EXPR_MAX_DEPTH); function-call nesting is guarded in execute_script_helper
    switch (expr->kind) {
    case CEXPR_BINARY: {
        PyObject *left = eval_compiled(expr->left, ctx, scope, script, statement);
        if (left == NULL) {
            break;
        }

        // Short-circuiting "and" and "or" binary operators
        BinaryOp op = expr->binary_op;
        if (op == BINARY_AND || op == BINARY_OR) {
            int left_bool = value_boolean_c(left);
            if ((op == BINARY_AND && !left_bool) || (op == BINARY_OR && left_bool)) {
                result = left;
                break;
            }
            Py_DECREF(left);
            result = eval_compiled(expr->right, ctx, scope, script, statement);
            break;
        }

        PyObject *right = eval_compiled(expr->right, ctx, scope, script, statement);
        if (right == NULL) {
            Py_DECREF(left);
            break;
        }
        result = apply_binary_op(op, left, right);
        Py_DECREF(left);
        Py_DECREF(right);
        break;
    }

    case CEXPR_UNARY: {
        PyObject *value = eval_compiled(expr->left, ctx, scope, script, statement);
        if (value == NULL) {
            break;
        }
        result = apply_unary_op(expr->unary_op, value);
        Py_DECREF(value);
        break;
    }

    case CEXPR_IF: {
        // Evaluate the value expression
        int cond = 0;
        if (expr->args[0] != NULL) {
            PyObject *cond_value = eval_compiled(expr->args[0], ctx, scope, script, statement);
            if (cond_value == NULL) {
                break;
            }
            cond = value_boolean_c(cond_value);
            Py_DECREF(cond_value);
        }

        // Evaluate the true/false expression
        CompiledExpr *result_expr = cond ? expr->args[1] : expr->args[2];
        result = (result_expr != NULL)
            ? eval_compiled(result_expr, ctx, scope, script, statement)
            : Py_NewRef(Py_None);
        break;
    }

    case CEXPR_CALL: {
        // Compute the function arguments
        PyObject *func_args;
        if (expr->nargs < 0) {
            func_args = Py_NewRef(Py_None);
        } else {
            func_args = PyList_New(expr->nargs);
            if (func_args == NULL) {
                break;
            }
            for (Py_ssize_t ix_arg = 0; ix_arg < expr->nargs; ix_arg++) {
                PyObject *arg_value = eval_compiled(expr->args[ix_arg], ctx, scope, script, statement);
                if (arg_value == NULL) {
                    Py_CLEAR(func_args);
                    break;
                }
                PyList_SET_ITEM(func_args, ix_arg, arg_value);
            }
            if (func_args == NULL) {
                break;
            }
        }

        // Global/local function? (builtins are never included in script execution)
        PyObject *func_value = NULL;
        int found_value = 0;
        if (scope->slots != NULL) {
            if (expr->slot >= 0 && scope->slots[expr->slot] != NULL) {
                func_value = Py_NewRef(scope->slots[expr->slot]);
                found_value = 1;
            }
        } else if (scope->dict != Py_None) {
            found_value = obj_get(scope->dict, expr->value, &func_value);
            if (found_value < 0) {
                Py_DECREF(func_args);
                break;
            }
        }
        if (!found_value && ctx->globals != NULL) {
            found_value = obj_get(ctx->globals, expr->value, &func_value);
            if (found_value < 0) {
                Py_DECREF(func_args);
                break;
            }
        }
        if (found_value && func_value == Py_None) {
            Py_CLEAR(func_value);
            found_value = 0;
        }

        if (found_value) {
            result = call_function_value(func_value, func_args, expr->value, ctx, script, statement, expr->intrinsic);
            Py_DECREF(func_value);
        } else {
            // Undefined function
            set_runtime_error(script, statement, PyUnicode_FromFormat("Undefined function \"%S\"", expr->value));
        }
        Py_DECREF(func_args);
        break;
    }

    default: // CEXPR_FALLBACK - defer to the dict-based evaluator
        if (scope->slots != NULL && scope_materialize(scope) < 0) {
            break;
        }
        result = evaluate_expression_c(expr->value, ctx, scope->dict, 0, script, statement);
        break;
    }

    return result;
}


// Execute a script's statements. Returns a new reference (the script return value) or NULL on
// error. locals is Py_None or a dict. The execution context (globals, maximum statements, and the
// statement counter) is initialized by the caller. body is the compiled form of statements (or
// NULL); compiled statement slots are used when their statement identity matches, with the
// dict-based statement path as the fallback.
static PyObject *execute_script_helper(
    PyObject *script, PyObject *statements, ExecCtx *ctx, Scope *scope, CompiledBody *body
)
{
    PyObject *globals = ctx->globals;
    PyObject *coverage_global = NULL;
    PyObject *label_indexes = NULL;
    PyObject *statements_fast = NULL;
    PyObject *result = NULL;
    int has_coverage = 0;
    int found;

    if (Py_EnterRecursiveCall(" while executing a BareScript script")) {
        return NULL;
    }

    // Coverage configuration is invariant across this helper invocation
    found = obj_get(globals, g.str_coverage_name, &coverage_global);
    if (found < 0) {
        goto done;
    }
    if (found && coverage_global != Py_None && PyDict_Check(coverage_global)) {
        PyObject *enabled = NULL;
        found = obj_get(coverage_global, g.str_enabled, &enabled);
        if (found < 0) {
            goto done;
        }
        int is_enabled = 0;
        if (found) {
            is_enabled = PyObject_IsTrue(enabled);
            Py_DECREF(enabled);
            if (is_enabled < 0) {
                goto done;
            }
        }
        if (is_enabled) {
            PyObject *system_obj = NULL;
            found = obj_get(script, g.str_system, &system_obj);
            if (found < 0) {
                goto done;
            }
            int is_system = 0;
            if (found) {
                is_system = PyObject_IsTrue(system_obj);
                Py_DECREF(system_obj);
                if (is_system < 0) {
                    goto done;
                }
            }
            has_coverage = !is_system;
        }
    }

    // Get the statements sequence
    statements_fast = PySequence_Fast(statements, "statements must be a sequence");
    if (statements_fast == NULL) {
        goto done;
    }
    int statements_is_list = PyList_CheckExact(statements_fast);
    Py_ssize_t statements_length = PySequence_Fast_GET_SIZE(statements_fast);

    // Iterate each script statement
    Py_ssize_t ix_statement = 0;
    while (ix_statement < statements_length) {
        // Fetch the statement. When the compiled slot's identity matches, the slot's strong
        // reference (kept alive by the body) is used with no refcount traffic - the borrowed
        // peek is only ever compared by pointer. Otherwise take a strong reference.
        CompiledStmt *cstmt = NULL;
        PyObject *statement;
        int statement_owned;
        PyObject *statement_peek = PySequence_Fast_GET_ITEM(statements_fast, ix_statement);
        if (body != NULL && ix_statement < body->count && body->stmts[ix_statement].statement == statement_peek &&
            body->stmts[ix_statement].kind != CSTMT_NONE) {
            cstmt = &body->stmts[ix_statement];
            statement = cstmt->statement;
            statement_owned = 0;
        } else if (statements_is_list) {
            if (list_get_ref(statements_fast, ix_statement, &statement) < 0) {
                goto done;
            }
            statement_owned = 1;
        } else {
            statement = PyTuple_GetItem(statements_fast, ix_statement);
            if (statement == NULL) {
                goto done;
            }
            Py_INCREF(statement);
            statement_owned = 1;
        }

        // Increment the statement counter
        if (exec_ctx_count_statement(ctx, script, statement) < 0) {
            if (statement_owned) {
                Py_DECREF(statement);
            }
            goto done;
        }

        // Record the statement coverage
        if (has_coverage && PyDict_CheckExact(statement)) {
            if (record_statement_coverage(script, statement, coverage_global) < 0) {
                if (statement_owned) {
                    Py_DECREF(statement);
                }
                goto done;
            }
        }

        // Compiled statement fast path (statement is the slot's reference - not owned here)
        if (cstmt != NULL) {
            {
                switch (cstmt->kind) {
                case CSTMT_EXPR: {
                    PyObject *expr_value = eval_compiled(cstmt->expr, ctx, scope, script, statement);
                    if (expr_value == NULL) {
                        goto done;
                    }
                    if (cstmt->name != NULL) {
                        if (cstmt->name_slot >= 0 && scope->slots != NULL) {
                            // Transfer the value into the local slot
                            Py_XSETREF(scope->slots[cstmt->name_slot], expr_value);
                            break;
                        }
                        PyObject *target = (scope->dict != Py_None) ? scope->dict : globals;
                        if (obj_setitem(target, cstmt->name, expr_value) < 0) {
                            Py_DECREF(expr_value);
                                goto done;
                        }
                    }
                    Py_DECREF(expr_value);
                    break;
                }

                case CSTMT_JUMP: {
                    // Evaluate the expression (if any)
                    int do_jump = 1;
                    if (cstmt->expr != NULL) {
                        PyObject *jump_value = eval_compiled(cstmt->expr, ctx, scope, script, statement);
                        if (jump_value == NULL) {
                                goto done;
                        }
                        do_jump = value_boolean_c(jump_value);
                        Py_DECREF(jump_value);
                    }
                    if (do_jump) {
                        if (cstmt->jump_index < 0) {
                            set_runtime_error(
                                script, statement, PyUnicode_FromFormat("Unknown jump label \"%S\"", cstmt->name)
                            );
                                goto done;
                        }
                        ix_statement = cstmt->jump_index;

                        // Record the label statement coverage
                        if (has_coverage && ix_statement < statements_length) {
                            PyObject *label_statement = PySequence_Fast_GET_ITEM(statements_fast, ix_statement);
                            Py_INCREF(label_statement);
                            if (PyDict_CheckExact(label_statement) &&
                                record_statement_coverage(script, label_statement, coverage_global) < 0) {
                                Py_DECREF(label_statement);
                                        goto done;
                            }
                            Py_DECREF(label_statement);
                        }
                    }
                    break;
                }

                case CSTMT_RETURN:
                    result = (cstmt->expr != NULL)
                        ? eval_compiled(cstmt->expr, ctx, scope, script, statement)
                        : Py_NewRef(Py_None);
                    goto done;

                case CSTMT_FUNCTION: {
                    PyObject *function_value = script_function_new(script, cstmt->part);
                    if (function_value == NULL) {
                        goto done;
                    }
                    int set_result = obj_setitem(globals, cstmt->name, function_value);
                    Py_DECREF(function_value);
                    if (set_result < 0) {
                        goto done;
                    }
                    break;
                }

                default: // CSTMT_NOP
                    break;
                }
                ix_statement++;
                continue;
            }
        }

        // Dict-based statement path - convert a slot scope to a dict scope first (only
        // reachable when the statements list was mutated after compilation)
        if (scope->slots != NULL && scope_materialize(scope) < 0) {
            Py_DECREF(statement);
            goto done;
        }

        // Dispatch on the statement dict's first (and only, for valid models) key
        if (!PyDict_CheckExact(statement)) {
            PyErr_SetString(PyExc_TypeError, "statement model must be a dict");
            Py_DECREF(statement);
            goto done;
        }
        Py_ssize_t stmt_pos = 0;
        PyObject *stmt_key;
        PyObject *stmt_value_borrowed;
        if (!PyDict_Next(statement, &stmt_pos, &stmt_key, &stmt_value_borrowed)) {
            // Empty statement dict - no-op
            Py_DECREF(statement);
            ix_statement++;
            continue;
        }
        PyObject *part = Py_NewRef(stmt_value_borrowed);

        // Expression?
        if (key_eq(stmt_key, g.str_expr)) {
            PyObject *stmt_expr = part;

            // Prefetch the expression statement fields in a single dict walk
            PyObject *expr_inner = NULL;
            PyObject *expr_name = NULL;
            int name_known = 0;
            if (PyDict_CheckExact(stmt_expr)) {
                dict_prefetch3(stmt_expr, g.str_expr, &expr_inner, g.str_name, &expr_name, NULL, NULL);
                name_known = 1;
            }
            if (expr_inner == NULL && obj_subscript(stmt_expr, g.str_expr, &expr_inner) < 0) {
                Py_XDECREF(expr_name);
                Py_DECREF(stmt_expr);
                Py_DECREF(statement);
                goto done;
            }
            PyObject *expr_value = evaluate_expression_c(expr_inner, ctx, scope->dict, 0, script, statement);
            Py_DECREF(expr_inner);
            if (expr_value == NULL) {
                Py_XDECREF(expr_name);
                Py_DECREF(stmt_expr);
                Py_DECREF(statement);
                goto done;
            }
            if (!name_known) {
                found = obj_get(stmt_expr, g.str_name, &expr_name);
                if (found < 0) {
                    Py_DECREF(expr_value);
                    Py_DECREF(stmt_expr);
                    Py_DECREF(statement);
                    goto done;
                }
            }
            Py_DECREF(stmt_expr);
            if (expr_name != NULL && expr_name != Py_None) {
                PyObject *target = (scope->dict != Py_None) ? scope->dict : globals;
                int set_result = obj_setitem(target, expr_name, expr_value);
                if (set_result < 0) {
                    Py_DECREF(expr_name);
                    Py_DECREF(expr_value);
                    Py_DECREF(statement);
                    goto done;
                }
            }
            Py_XDECREF(expr_name);
            Py_DECREF(expr_value);
            Py_DECREF(statement);
            ix_statement++;
            continue;
        }

        // Jump?
        if (key_eq(stmt_key, g.str_jump)) {
            PyObject *stmt_jump = part;

            // Prefetch the jump statement fields in a single dict walk (jump_expr NULL = absent)
            PyObject *jump_expr = NULL;
            PyObject *jump_label_pf = NULL;
            if (PyDict_CheckExact(stmt_jump)) {
                dict_prefetch3(stmt_jump, g.str_expr, &jump_expr, g.str_label, &jump_label_pf, NULL, NULL);
            } else {
                found = obj_get(stmt_jump, g.str_expr, &jump_expr);
                if (found < 0) {
                    Py_DECREF(stmt_jump);
                    Py_DECREF(statement);
                    goto done;
                }
            }

            // Evaluate the expression (if any)
            int do_jump = 1;
            if (jump_expr != NULL) {
                PyObject *jump_value = evaluate_expression_c(jump_expr, ctx, scope->dict, 0, script, statement);
                Py_DECREF(jump_expr);
                if (jump_value == NULL) {
                    Py_XDECREF(jump_label_pf);
                    Py_DECREF(stmt_jump);
                    Py_DECREF(statement);
                    goto done;
                }
                do_jump = value_boolean_c(jump_value);
                Py_DECREF(jump_value);
            }

            if (do_jump) {
                // Find the label
                PyObject *jump_label = jump_label_pf;
                jump_label_pf = NULL;
                if (jump_label == NULL && obj_subscript(stmt_jump, g.str_label, &jump_label) < 0) {
                    Py_DECREF(stmt_jump);
                    Py_DECREF(statement);
                    goto done;
                }
                PyObject *cached_index = NULL;
                if (label_indexes != NULL) {
                    if (dict_get_ref(label_indexes, jump_label, &cached_index) < 0) {
                        Py_DECREF(jump_label);
                        Py_DECREF(stmt_jump);
                        Py_DECREF(statement);
                        goto done;
                    }
                }
                if (cached_index != NULL) {
                    Py_ssize_t ix_label = PyLong_AsSsize_t(cached_index);
                    Py_DECREF(cached_index);
                    Py_DECREF(jump_label);
                    if (ix_label == -1 && PyErr_Occurred()) {
                        Py_DECREF(stmt_jump);
                        Py_DECREF(statement);
                        goto done;
                    }
                    ix_statement = ix_label;
                } else {
                    // Scan the statements for the label
                    Py_ssize_t ix_label = -1;
                    for (Py_ssize_t ix_scan = 0; ix_scan < statements_length; ix_scan++) {
                        PyObject *scan_statement = PySequence_Fast_GET_ITEM(statements_fast, ix_scan);
                        Py_INCREF(scan_statement);
                        PyObject *label_part = NULL;
                        int scan_found = obj_get(scan_statement, g.str_label, &label_part);
                        Py_DECREF(scan_statement);
                        if (scan_found < 0) {
                            Py_DECREF(jump_label);
                            Py_DECREF(stmt_jump);
                            Py_DECREF(statement);
                            goto done;
                        }
                        if (scan_found) {
                            PyObject *label_name;
                            int sub_result = obj_subscript(label_part, g.str_name, &label_name);
                            Py_DECREF(label_part);
                            if (sub_result < 0) {
                                Py_DECREF(jump_label);
                                Py_DECREF(stmt_jump);
                                Py_DECREF(statement);
                                goto done;
                            }
                            int label_eq = PyObject_RichCompareBool(label_name, jump_label, Py_EQ);
                            Py_DECREF(label_name);
                            if (label_eq < 0) {
                                Py_DECREF(jump_label);
                                Py_DECREF(stmt_jump);
                                Py_DECREF(statement);
                                goto done;
                            }
                            if (label_eq) {
                                ix_label = ix_scan;
                                break;
                            }
                        }
                    }
                    if (ix_label == -1) {
                        set_runtime_error(
                            script, statement, PyUnicode_FromFormat("Unknown jump label \"%S\"", jump_label)
                        );
                        Py_DECREF(jump_label);
                        Py_DECREF(stmt_jump);
                        Py_DECREF(statement);
                        goto done;
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) {
                            Py_DECREF(jump_label);
                            Py_DECREF(stmt_jump);
                            Py_DECREF(statement);
                            goto done;
                        }
                    }
                    PyObject *index_obj = PyLong_FromSsize_t(ix_label);
                    if (index_obj == NULL || PyDict_SetItem(label_indexes, jump_label, index_obj) < 0) {
                        Py_XDECREF(index_obj);
                        Py_DECREF(jump_label);
                        Py_DECREF(stmt_jump);
                        Py_DECREF(statement);
                        goto done;
                    }
                    Py_DECREF(index_obj);
                    Py_DECREF(jump_label);
                    ix_statement = ix_label;
                }

                // Record the label statement coverage
                if (has_coverage) {
                    PyObject *label_statement = PySequence_Fast_GET_ITEM(statements_fast, ix_statement);
                    Py_INCREF(label_statement);
                    if (PyDict_CheckExact(label_statement) &&
                        record_statement_coverage(script, label_statement, coverage_global) < 0) {
                        Py_DECREF(label_statement);
                        Py_DECREF(stmt_jump);
                        Py_DECREF(statement);
                        goto done;
                    }
                    Py_DECREF(label_statement);
                }
            }
            Py_XDECREF(jump_label_pf);
            Py_DECREF(stmt_jump);
            Py_DECREF(statement);
            ix_statement++;
            continue;
        }

        // Return?
        if (key_eq(stmt_key, g.str_return)) {
            PyObject *stmt_return = part;
            PyObject *return_expr = NULL;
            if (PyDict_CheckExact(stmt_return)) {
                dict_prefetch3(stmt_return, g.str_expr, &return_expr, NULL, NULL, NULL, NULL);
            } else {
                found = obj_get(stmt_return, g.str_expr, &return_expr);
                if (found < 0) {
                    Py_DECREF(stmt_return);
                    Py_DECREF(statement);
                    goto done;
                }
            }
            Py_DECREF(stmt_return);
            if (return_expr != NULL) {
                result = evaluate_expression_c(return_expr, ctx, scope->dict, 0, script, statement);
                Py_DECREF(return_expr);
            } else {
                result = Py_NewRef(Py_None);
            }
            Py_DECREF(statement);
            goto done;
        }

        // Function?
        if (key_eq(stmt_key, g.str_function)) {
            PyObject *stmt_function = part;
            PyObject *function_name;
            if (obj_subscript(stmt_function, g.str_name, &function_name) < 0) {
                Py_DECREF(stmt_function);
                Py_DECREF(statement);
                goto done;
            }
            PyObject *function_value = script_function_new(script, stmt_function);
            Py_DECREF(stmt_function);
            if (function_value == NULL) {
                Py_DECREF(function_name);
                Py_DECREF(statement);
                goto done;
            }
            int set_result = obj_setitem(globals, function_name, function_value);
            Py_DECREF(function_value);
            Py_DECREF(function_name);
            if (set_result < 0) {
                Py_DECREF(statement);
                goto done;
            }
            Py_DECREF(statement);
            ix_statement++;
            continue;
        }

        // Include?
        if (key_eq(stmt_key, g.str_include)) {
            int include_result = execute_include_statement(script, statement, part, ctx);
            Py_DECREF(part);
            Py_DECREF(statement);
            if (include_result < 0) {
                goto done;
            }
            ix_statement++;
            continue;
        }

        // Label statement (or unrecognized) - no-op
        Py_DECREF(part);
        Py_DECREF(statement);
        ix_statement++;
    }

    // Script complete
    result = Py_NewRef(Py_None);

done:
    Py_XDECREF(statements_fast);
    Py_XDECREF(label_indexes);
    Py_XDECREF(coverage_global);
    Py_LeaveRecursiveCall();
    return result;
}


//
// Module functions
//


PyDoc_STRVAR(
    execute_script_doc,
    "execute_script(script, options=None)\n"
    "\n"
    "Execute a BareScript model"
);

static PyObject *runtime_execute_script(PyObject *module, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script;
    PyObject *options_arg = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:execute_script", kwlist, &script, &options_arg)) {
        return NULL;
    }

    PyObject *options = NULL;
    PyObject *globals = NULL;
    PyObject *script_functions = NULL;
    PyObject *statements = NULL;
    PyObject *result = NULL;

    // Create the options object, if necessary
    if (options_arg == Py_None) {
        options = PyDict_New();
        if (options == NULL) {
            return NULL;
        }
    } else {
        options = Py_NewRef(options_arg);
    }

    // Create the global variable object, if necessary
    int found = obj_get(options, g.str_globals, &globals);
    if (found < 0) {
        goto done;
    }
    if (!found || globals == Py_None) {
        Py_XDECREF(globals);
        globals = PyDict_New();
        if (globals == NULL || obj_setitem(options, g.str_globals, globals) < 0) {
            goto done;
        }
    }

    // Set the script function globals variables (snapshot the dict so concurrent mutation of
    // SCRIPT_FUNCTIONS cannot break iteration under the free-threaded build)
    script_functions = PyDict_Copy(g.script_functions);
    if (script_functions == NULL) {
        goto done;
    }
    Py_ssize_t pos = 0;
    PyObject *fn_name;
    PyObject *fn_value;
    int globals_is_dict = PyDict_CheckExact(globals);
    while (PyDict_Next(script_functions, &pos, &fn_name, &fn_value)) {
        int has_name = globals_is_dict ? PyDict_Contains(globals, fn_name) : PySequence_Contains(globals, fn_name);
        if (has_name < 0) {
            goto done;
        }
        if (!has_name && obj_setitem(globals, fn_name, fn_value) < 0) {
            goto done;
        }
    }

    // Execute the script
    if (obj_setitem(options, g.str_statementCount, g.zero) < 0) {
        goto done;
    }
    if (obj_subscript(script, g.str_statements, &statements) < 0) {
        goto done;
    }
    {
        CompiledBody *body = NULL;
        if (PyList_CheckExact(statements)) {
            body = compile_body(statements, NULL, 0);
            if (body == NULL) {
                goto done;
            }
        }
        ExecCtx ctx;
        if (exec_ctx_init_exec(&ctx, options) < 0) {
            exec_ctx_fini(&ctx);
            compiled_body_free(body);
            goto done;
        }
        Scope scope = {Py_None, NULL, NULL, 0};
        result = execute_script_helper(script, statements, &ctx, &scope, body);
        exec_ctx_sync_out_final(&ctx);
        exec_ctx_fini(&ctx);
        compiled_body_free(body);
    }

done:
    Py_XDECREF(statements);
    Py_XDECREF(script_functions);
    Py_XDECREF(globals);
    Py_XDECREF(options);
    return result;
}


PyDoc_STRVAR(
    evaluate_expression_doc,
    "evaluate_expression(expr, options=None, locals_=None, builtins=True, script=None, statement=None)\n"
    "\n"
    "Evaluate an expression model"
);

static PyObject *runtime_evaluate_expression(PyObject *module, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr;
    PyObject *options = Py_None;
    PyObject *locals = Py_None;
    int builtins = 1;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs, "O|OOpOO:evaluate_expression", kwlist, &expr, &options, &locals, &builtins, &script, &statement
        )) {
        return NULL;
    }

    ExecCtx ctx;
    if (exec_ctx_init_eval(&ctx, options) < 0) {
        exec_ctx_fini(&ctx);
        return NULL;
    }
    PyObject *result = evaluate_expression_c(expr, &ctx, locals, builtins, script, statement);
    exec_ctx_fini(&ctx);
    return result;
}


static PyMethodDef runtime_c_methods[] = {
    {"execute_script", (PyCFunction)(void (*)(void))runtime_execute_script, METH_VARARGS | METH_KEYWORDS, execute_script_doc},
    {"evaluate_expression", (PyCFunction)(void (*)(void))runtime_evaluate_expression, METH_VARARGS | METH_KEYWORDS,
     evaluate_expression_doc},
    {NULL, NULL, 0, NULL}
};


//
// Module initialization
//


// Intern a string constant into a state member
static int intern_string(PyObject **member, const char *str)
{
    if (*member == NULL) {
        *member = PyUnicode_InternFromString(str);
        if (*member == NULL) {
            return -1;
        }
    }
    return 0;
}


// Import a module attribute into a state member
static int import_member(PyObject **member, PyObject *module, const char *name)
{
    if (*member == NULL) {
        *member = PyObject_GetAttrString(module, name);
        if (*member == NULL) {
            return -1;
        }
    }
    return 0;
}


static int runtime_c_exec(PyObject *module)
{
    // Idempotency guard - state is populated once and immutable afterwards
    if (g.one != NULL) {
        return 0;
    }

    PyDateTime_IMPORT;
    if (PyDateTimeAPI == NULL) {
        return -1;
    }

    // Intern the key strings
    if (intern_string(&g.str_globals, "globals") < 0 ||
        intern_string(&g.str_maxStatements, "maxStatements") < 0 ||
        intern_string(&g.str_statementCount, "statementCount") < 0 ||
        intern_string(&g.str_systemPrefix, "systemPrefix") < 0 ||
        intern_string(&g.str_fetchFn, "fetchFn") < 0 ||
        intern_string(&g.str_logFn, "logFn") < 0 ||
        intern_string(&g.str_urlFn, "urlFn") < 0 ||
        intern_string(&g.str_debug, "debug") < 0 ||
        intern_string(&g.str_statements, "statements") < 0 ||
        intern_string(&g.str_scriptName, "scriptName") < 0 ||
        intern_string(&g.str_system, "system") < 0 ||
        intern_string(&g.str_expr, "expr") < 0 ||
        intern_string(&g.str_jump, "jump") < 0 ||
        intern_string(&g.str_return, "return") < 0 ||
        intern_string(&g.str_function, "function") < 0 ||
        intern_string(&g.str_include, "include") < 0 ||
        intern_string(&g.str_label, "label") < 0 ||
        intern_string(&g.str_name, "name") < 0 ||
        intern_string(&g.str_args, "args") < 0 ||
        intern_string(&g.str_lastArgArray, "lastArgArray") < 0 ||
        intern_string(&g.str_includes, "includes") < 0 ||
        intern_string(&g.str_url, "url") < 0 ||
        intern_string(&g.str_number, "number") < 0 ||
        intern_string(&g.str_string, "string") < 0 ||
        intern_string(&g.str_variable, "variable") < 0 ||
        intern_string(&g.str_binary, "binary") < 0 ||
        intern_string(&g.str_unary, "unary") < 0 ||
        intern_string(&g.str_group, "group") < 0 ||
        intern_string(&g.str_op, "op") < 0 ||
        intern_string(&g.str_left, "left") < 0 ||
        intern_string(&g.str_right, "right") < 0 ||
        intern_string(&g.str_lineNumber, "lineNumber") < 0 ||
        intern_string(&g.str_enabled, "enabled") < 0 ||
        intern_string(&g.str_scripts, "scripts") < 0 ||
        intern_string(&g.str_script, "script") < 0 ||
        intern_string(&g.str_covered, "covered") < 0 ||
        intern_string(&g.str_statement, "statement") < 0 ||
        intern_string(&g.str_count, "count") < 0 ||
        intern_string(&g.str_coverage_name, "__barescriptCoverage") < 0 ||
        intern_string(&g.str_includes_name, "__barescriptIncludes") < 0 ||
        intern_string(&g.str_return_value, "return_value") < 0 ||
        intern_string(&g.str_total_seconds, "total_seconds") < 0 ||
        intern_string(&g.str_copy, "copy") < 0 ||
        intern_string(&g.str_method_upper, "upper") < 0 ||
        intern_string(&g.str_method_lower, "lower") < 0 ||
        intern_string(&g.str_method_strip, "strip") < 0) {
        return -1;
    }

    // Import the Python implementation modules
    PyObject *library_module = PyImport_ImportModule("bare_script.library");
    if (library_module == NULL) {
        return -1;
    }
    int import_ok = import_member(&g.script_functions, library_module, "SCRIPT_FUNCTIONS") == 0 &&
        import_member(&g.expression_functions, library_module, "EXPRESSION_FUNCTIONS") == 0;
    Py_DECREF(library_module);
    if (!import_ok) {
        return -1;
    }

    // Capture the original library function objects for the intrinsic table (a missing name
    // leaves the intrinsic disabled)
    for (int ix_intrinsic = 0; ix_intrinsic < INTRINSIC_COUNT; ix_intrinsic++) {
        PyObject *intrinsic_name = PyUnicode_FromString(g_intrinsics[ix_intrinsic].name);
        if (intrinsic_name == NULL) {
            return -1;
        }
        int found_intrinsic = dict_get_ref(g.script_functions, intrinsic_name, &g_intrinsics[ix_intrinsic].py_func);
        Py_DECREF(intrinsic_name);
        if (found_intrinsic < 0) {
            return -1;
        }
    }

    PyObject *runtime_module = PyImport_ImportModule("bare_script.runtime");
    if (runtime_module == NULL) {
        return -1;
    }
    import_ok = import_member(&g.runtime_error, runtime_module, "BareScriptRuntimeError") == 0;
    Py_DECREF(runtime_module);
    if (!import_ok) {
        return -1;
    }

    PyObject *value_module = PyImport_ImportModule("bare_script.value");
    if (value_module == NULL) {
        return -1;
    }
    import_ok = import_member(&g.value_args_error, value_module, "ValueArgsError") == 0 &&
        import_member(&g.value_string, value_module, "value_string") == 0 &&
        import_member(&g.value_compare, value_module, "value_compare") == 0 &&
        import_member(&g.value_round_number, value_module, "value_round_number") == 0 &&
        import_member(&g.value_normalize_datetime, value_module, "value_normalize_datetime") == 0;
    Py_DECREF(value_module);
    if (!import_ok) {
        return -1;
    }

    PyObject *options_module = PyImport_ImportModule("bare_script.options");
    if (options_module == NULL) {
        return -1;
    }
    import_ok = import_member(&g.url_file_relative, options_module, "url_file_relative") == 0;
    Py_DECREF(options_module);
    if (!import_ok) {
        return -1;
    }

    PyObject *parser_module = PyImport_ImportModule("bare_script.parser");
    if (parser_module == NULL) {
        return -1;
    }
    import_ok = import_member(&g.parse_script, parser_module, "parse_script") == 0;
    Py_DECREF(parser_module);
    if (!import_ok) {
        return -1;
    }

    PyObject *model_module = PyImport_ImportModule("bare_script.model");
    if (model_module == NULL) {
        return -1;
    }
    import_ok = import_member(&g.lint_script, model_module, "lint_script") == 0;
    Py_DECREF(model_module);
    if (!import_ok) {
        return -1;
    }

    PyObject *functools_module = PyImport_ImportModule("functools");
    if (functools_module == NULL) {
        return -1;
    }
    import_ok = import_member(&g.partial, functools_module, "partial") == 0;
    Py_DECREF(functools_module);
    if (!import_ok) {
        return -1;
    }

    // Ready the script function type
    if (PyType_Ready(&ScriptFunctionType) < 0) {
        return -1;
    }

    // Create the constants (g.one last - it is the idempotency guard)
    g.default_max_statements = PyFloat_FromDouble(1e9);
    if (g.default_max_statements == NULL) {
        return -1;
    }
    g.zero = PyLong_FromLong(0);
    if (g.zero == NULL) {
        return -1;
    }
    g.one = PyLong_FromLong(1);
    if (g.one == NULL) {
        return -1;
    }

    return 0;
}


static PyModuleDef_Slot runtime_c_slots[] = {
    {Py_mod_exec, (void *)runtime_c_exec},
#if PY_VERSION_HEX >= 0x030C0000
    {Py_mod_multiple_interpreters, Py_MOD_MULTIPLE_INTERPRETERS_NOT_SUPPORTED},
#endif
#if PY_VERSION_HEX >= 0x030D0000
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL}
};


static struct PyModuleDef runtime_c_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "runtime_c",
    .m_doc = "The BareScript runtime C extension",
    .m_size = 0,
    .m_methods = runtime_c_methods,
    .m_slots = runtime_c_slots
};


PyMODINIT_FUNC PyInit_runtime_c(void)
{
    return PyModuleDef_Init(&runtime_c_module);
}
