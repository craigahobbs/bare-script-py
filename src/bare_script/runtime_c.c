/* Licensed under the MIT License */
/* https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE */

/*
 * BareScript runtime C extension - evaluate_expression and execute_script implementations
 *
 * This module provides a C-accelerated implementation of evaluate_expression
 * and execute_script. Most value operations delegate back to the pure-Python
 * implementations in bare_script.value and bare_script.library to maintain
 * identical semantics.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>


/* Module-level cached references to Python functions and types */
static PyObject *g_value_boolean = NULL;
static PyObject *g_value_compare = NULL;
static PyObject *g_value_normalize_datetime = NULL;
static PyObject *g_value_round_number = NULL;
static PyObject *g_value_string = NULL;
static PyObject *g_value_args_error = NULL;
static PyObject *g_expression_functions = NULL;
static PyObject *g_script_functions = NULL;
static PyObject *g_default_max_statements = NULL;
static PyObject *g_runtime_error = NULL;
static PyObject *g_datetime_date = NULL;
static PyObject *g_timedelta = NULL;
static PyObject *g_parse_script = NULL;
static PyObject *g_lint_script = NULL;
static PyObject *g_url_file_relative = NULL;
static PyObject *g_functools_partial = NULL;

/* Cached default max statements as a long */
static long g_default_max_statements_long = 0;

/* Frequently-used interned strings */
static PyObject *g_str_number = NULL;
static PyObject *g_str_string = NULL;
static PyObject *g_str_variable = NULL;
static PyObject *g_str_function = NULL;
static PyObject *g_str_binary = NULL;
static PyObject *g_str_unary = NULL;
static PyObject *g_str_group = NULL;
static PyObject *g_str_null = NULL;
static PyObject *g_str_false = NULL;
static PyObject *g_str_true = NULL;
static PyObject *g_str_if = NULL;
static PyObject *g_str_name = NULL;
static PyObject *g_str_args = NULL;
static PyObject *g_str_op = NULL;
static PyObject *g_str_left = NULL;
static PyObject *g_str_right = NULL;
static PyObject *g_str_expr = NULL;
static PyObject *g_str_globals = NULL;
static PyObject *g_str_logFn = NULL;
static PyObject *g_str_debug = NULL;
static PyObject *g_str_return_value = NULL;
static PyObject *g_str_milliseconds = NULL;
static PyObject *g_str_statements = NULL;
static PyObject *g_str_jump = NULL;
static PyObject *g_str_label = NULL;
static PyObject *g_str_return = NULL;
static PyObject *g_str_include = NULL;
static PyObject *g_str_includes = NULL;
static PyObject *g_str_url = NULL;
static PyObject *g_str_system = NULL;
static PyObject *g_str_lastArgArray = NULL;
static PyObject *g_str_statementCount = NULL;
static PyObject *g_str_maxStatements = NULL;
static PyObject *g_str_systemPrefix = NULL;
static PyObject *g_str_fetchFn = NULL;
static PyObject *g_str_urlFn = NULL;
static PyObject *g_str_scriptName = NULL;
static PyObject *g_str_lineNumber = NULL;
static PyObject *g_str_scripts = NULL;
static PyObject *g_str_script = NULL;
static PyObject *g_str_covered = NULL;
static PyObject *g_str_count = NULL;
static PyObject *g_str_statement = NULL;
static PyObject *g_str_enabled = NULL;
static PyObject *g_str___barescriptCoverage = NULL;
static PyObject *g_str___barescriptIncludes = NULL;


/* Forward declarations */
static PyObject *evaluate_expression_impl(PyObject *expr, PyObject *options, PyObject *locals_,
                                           int builtins, PyObject *script, PyObject *statement,
                                           long *stmt_count);
static PyObject *execute_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_);


/* Helper: Convert a number-like Python object (int or float) to long.
 * Returns -1 on error, with PyErr set or with default if not set.
 * Pass -2 as default to indicate no fallback. */
static long
number_to_long(PyObject *obj, long default_value)
{
    if (obj == NULL) return default_value;
    if (PyLong_Check(obj)) {
        long v = PyLong_AsLong(obj);
        if (v == -1 && PyErr_Occurred()) {
            PyErr_Clear();
            return default_value;
        }
        return v;
    }
    if (PyFloat_Check(obj)) {
        return (long)PyFloat_AS_DOUBLE(obj);
    }
    return default_value;
}


/* Helper: Write a C long value into options['statementCount'].
 * This is used to persist the local statement counter back to options. */
static void
write_statement_count(PyObject *options, long statement_count)
{
    if (options != NULL && options != Py_None && PyDict_Check(options)) {
        PyObject *count_obj = PyLong_FromLong(statement_count);
        if (count_obj != NULL) {
            PyDict_SetItem(options, g_str_statementCount, count_obj);
            Py_DECREF(count_obj);
        }
    }
}


/* Helper: Read the statement count from options['statementCount'] as a C long. */
static long
read_statement_count(PyObject *options)
{
    if (options != NULL && options != Py_None && PyDict_Check(options)) {
        PyObject *cur = PyDict_GetItem(options, g_str_statementCount);
        return number_to_long(cur, 0);
    }
    return 0;
}


/* ScriptFunction type - represents a user-defined BareScript function */
typedef struct {
    PyObject_HEAD
    PyObject *script;     /* The script that contains this function */
    PyObject *function;   /* The function definition statement's "function" dict */
} ScriptFunctionObject;


static void
ScriptFunction_dealloc(ScriptFunctionObject *self)
{
    Py_XDECREF(self->script);
    Py_XDECREF(self->function);
    Py_TYPE(self)->tp_free((PyObject*)self);
}


/* ScriptFunction call: __call__(args, options)
 *
 * This is the entry point for user-defined function calls from expression
 * evaluation. Before calling execute_script_helper, we don't need to sync
 * the statement counter because the caller's execute_script_helper will
 * have already written it to options before evaluating the expression that
 * led to this call. After the call, the child's execute_script_helper will
 * have updated options['statementCount'], so the caller reads it back.
 */
static PyObject *
ScriptFunction_call(ScriptFunctionObject *self, PyObject *args, PyObject *kwds)
{
    PyObject *call_args;
    PyObject *options;

    if (!PyArg_ParseTuple(args, "OO", &call_args, &options)) {
        return NULL;
    }

    /* Build locals from function args */
    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    PyObject *func_args = PyDict_GetItemWithError(self->function, g_str_args);
    if (func_args == NULL && PyErr_Occurred()) {
        Py_DECREF(func_locals);
        return NULL;
    }

    if (func_args != NULL && PyList_Check(func_args)) {
        Py_ssize_t func_args_length = PyList_GET_SIZE(func_args);
        Py_ssize_t args_length = (call_args != Py_None && PyList_Check(call_args))
            ? PyList_GET_SIZE(call_args) : 0;

        /* Get lastArgArray flag */
        PyObject *last_arg_array_obj = PyDict_GetItemWithError(self->function, g_str_lastArgArray);
        if (last_arg_array_obj == NULL && PyErr_Occurred()) {
            Py_DECREF(func_locals);
            return NULL;
        }
        int last_arg_array = (last_arg_array_obj != NULL && PyObject_IsTrue(last_arg_array_obj) == 1);
        Py_ssize_t ix_arg_last = last_arg_array ? (func_args_length - 1) : -1;

        for (Py_ssize_t ix_arg = 0; ix_arg < func_args_length; ix_arg++) {
            PyObject *arg_name = PyList_GET_ITEM(func_args, ix_arg);
            PyObject *arg_value = NULL;
            int arg_value_owned = 0;

            if (ix_arg < args_length) {
                if (ix_arg != ix_arg_last) {
                    arg_value = PyList_GET_ITEM(call_args, ix_arg);
                } else {
                    /* Slice from ix_arg to end */
                    arg_value = PyList_GetSlice(call_args, ix_arg, args_length);
                    if (arg_value == NULL) {
                        Py_DECREF(func_locals);
                        return NULL;
                    }
                    arg_value_owned = 1;
                }
            } else {
                if (ix_arg == ix_arg_last) {
                    arg_value = PyList_New(0);
                    if (arg_value == NULL) {
                        Py_DECREF(func_locals);
                        return NULL;
                    }
                    arg_value_owned = 1;
                } else {
                    arg_value = Py_None;
                }
            }

            if (PyDict_SetItem(func_locals, arg_name, arg_value) < 0) {
                if (arg_value_owned) Py_DECREF(arg_value);
                Py_DECREF(func_locals);
                return NULL;
            }
            if (arg_value_owned) Py_DECREF(arg_value);
        }
    }

    PyObject *func_statements = PyDict_GetItemWithError(self->function, g_str_statements);
    if (func_statements == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
        Py_DECREF(func_locals);
        return NULL;
    }

    PyObject *opts = (options == Py_None) ? NULL : options;
    PyObject *result = execute_script_helper(self->script, func_statements, opts, func_locals);
    Py_DECREF(func_locals);
    return result;
}


static PyTypeObject ScriptFunctionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c.ScriptFunction",
    .tp_basicsize = sizeof(ScriptFunctionObject),
    .tp_itemsize = 0,
    .tp_dealloc = (destructor)ScriptFunction_dealloc,
    .tp_call = (ternaryfunc)ScriptFunction_call,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "BareScript user-defined function",
};


/* Create a new ScriptFunction */
static PyObject *
ScriptFunction_new(PyObject *script, PyObject *function)
{
    ScriptFunctionObject *self = PyObject_New(ScriptFunctionObject, &ScriptFunctionType);
    if (self == NULL) return NULL;
    Py_INCREF(script);
    Py_INCREF(function);
    self->script = script;
    self->function = function;
    return (PyObject *)self;
}


/* Helper: Get the single key and value from a single-key dict using PyDict_Next.
 *
 * Both *key and *value are borrowed references. Returns 0 on success,
 * -1 on error.
 */
static inline int
get_single_dict_key_value(PyObject *dict, PyObject **key, PyObject **value)
{
    if (!PyDict_Check(dict)) {
        PyErr_SetString(PyExc_TypeError, "expected dict");
        return -1;
    }

    *key = NULL;
    *value = NULL;
    Py_ssize_t pos = 0;
    if (!PyDict_Next(dict, &pos, key, value)) {
        PyErr_SetString(PyExc_ValueError, "empty dict");
        return -1;
    }
    return 0;
}


/* Helper: Get the expression type discriminator key and its value.
 *
 * The expression dict always has exactly one of: number, string, variable,
 * function, binary, unary, group. We get the key and value directly via
 * PyDict_Next, then compare via interned-string pointer equality to return
 * one of our cached g_str_* objects as the canonical key.
 *
 * On success, *out_key is one of the g_str_* canonical strings (borrowed),
 * and *out_value is the dict's value (borrowed). Returns 0 on success, -1
 * on error.
 */
static inline int
get_expr_key_value(PyObject *expr, PyObject **out_key, PyObject **out_value)
{
    PyObject *key, *value;
    if (get_single_dict_key_value(expr, &key, &value) < 0) return -1;
    *out_value = value;

    /* Compare by pointer for interned strings (the common case). */
    if (key == g_str_number) { *out_key = g_str_number; return 0; }
    if (key == g_str_string) { *out_key = g_str_string; return 0; }
    if (key == g_str_variable) { *out_key = g_str_variable; return 0; }
    if (key == g_str_function) { *out_key = g_str_function; return 0; }
    if (key == g_str_binary) { *out_key = g_str_binary; return 0; }
    if (key == g_str_unary) { *out_key = g_str_unary; return 0; }
    if (key == g_str_group) { *out_key = g_str_group; return 0; }

    /* Fallback: compare by string value. */
    if (PyUnicode_Check(key)) {
        if (PyUnicode_Compare(key, g_str_number) == 0) { *out_key = g_str_number; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_string) == 0) { *out_key = g_str_string; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_variable) == 0) { *out_key = g_str_variable; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_function) == 0) { *out_key = g_str_function; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_binary) == 0) { *out_key = g_str_binary; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_unary) == 0) { *out_key = g_str_unary; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_group) == 0) { *out_key = g_str_group; return 0; }
        if (PyErr_Occurred()) return -1;
    }

    /* Unknown key - return as-is (caller will error out) */
    *out_key = key;
    return 0;
}


/* Helper: Get the statement type discriminator key and its value.
 *
 * Same approach as get_expr_key_value but for statement dicts which have
 * one of: expr, jump, return, label, function, include.
 *
 * On success, *out_key is one of the g_str_* canonical strings (borrowed),
 * and *out_value is the dict's value (borrowed). Returns 0 on success, -1
 * on error.
 */
static inline int
get_statement_key_value(PyObject *statement, PyObject **out_key, PyObject **out_value)
{
    PyObject *key, *value;
    if (get_single_dict_key_value(statement, &key, &value) < 0) return -1;
    *out_value = value;

    /* Compare by pointer for interned strings (common case) */
    if (key == g_str_expr) { *out_key = g_str_expr; return 0; }
    if (key == g_str_jump) { *out_key = g_str_jump; return 0; }
    if (key == g_str_return) { *out_key = g_str_return; return 0; }
    if (key == g_str_label) { *out_key = g_str_label; return 0; }
    if (key == g_str_function) { *out_key = g_str_function; return 0; }
    if (key == g_str_include) { *out_key = g_str_include; return 0; }

    /* Fallback: compare by string value */
    if (PyUnicode_Check(key)) {
        if (PyUnicode_Compare(key, g_str_expr) == 0) { *out_key = g_str_expr; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_jump) == 0) { *out_key = g_str_jump; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_return) == 0) { *out_key = g_str_return; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_label) == 0) { *out_key = g_str_label; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_function) == 0) { *out_key = g_str_function; return 0; }
        if (PyErr_Occurred()) return -1;
        if (PyUnicode_Compare(key, g_str_include) == 0) { *out_key = g_str_include; return 0; }
        if (PyErr_Occurred()) return -1;
    }

    *out_key = key;
    return 0;
}


/* Helper: Determine just the statement-key class (used for label statements
 * during coverage recording, where we don't need the value).
 */
static inline PyObject *
get_statement_key(PyObject *statement)
{
    PyObject *key, *value;
    if (get_statement_key_value(statement, &key, &value) < 0) return NULL;
    return key;
}


/* Helper: Fast borrowed-reference dict lookup using PyDict_GetItem.
 *
 * PyDict_GetItem is faster than PyDict_GetItemWithError because it doesn't
 * need to set up error state. Returns a borrowed reference, or NULL if the
 * key is not present.
 */
static inline PyObject *
fast_dict_get(PyObject *dict, PyObject *key)
{
    return PyDict_GetItem(dict, key);
}


/* Helper: Call value_boolean(value) - returns 1 (true), 0 (false), or -1 (error).
 *
 * Optimization: handle common types directly in C to avoid the overhead of
 * calling into the Python value_boolean function. The semantics must match
 * the Python implementation exactly:
 *   - None         -> False
 *   - bool         -> the value itself
 *   - int/float    -> value != 0  (note: bool is_subclass of int, so check bool first)
 *   - str          -> non-empty
 *   - list         -> non-empty
 *   - dict         -> True (always, even if empty - this differs from Python's truthiness!)
 *   - other        -> True (functions, regex, datetime, etc. all truthy)
 *
 * For most common cases, we avoid the Python function call entirely. We only
 * fall back to the Python implementation for unknown/edge case types.
 */
static int
call_value_boolean(PyObject *value)
{
    /* None -> False */
    if (value == Py_None) return 0;

    /* Bool fast path - check bool BEFORE int because bool is a subclass of int.
     * Py_True and Py_False are singletons. */
    if (value == Py_True) return 1;
    if (value == Py_False) return 0;

    /* Bool check (defensive - in case of bool subclasses, though uncommon) */
    if (PyBool_Check(value)) {
        return PyObject_IsTrue(value);
    }

    /* Integer (long) -> nonzero */
    if (PyLong_Check(value)) {
        /* PyObject_IsTrue is fast for PyLong: checks ob_size != 0 */
        return PyObject_IsTrue(value);
    }

    /* Float -> nonzero */
    if (PyFloat_Check(value)) {
        double d = PyFloat_AS_DOUBLE(value);
        return d != 0.0;
    }

    /* String -> non-empty */
    if (PyUnicode_Check(value)) {
        return PyUnicode_GetLength(value) != 0;
    }

    /* List -> non-empty */
    if (PyList_Check(value)) {
        return PyList_GET_SIZE(value) != 0;
    }

    /* Dict -> True (matches Python value_boolean semantics: dicts are always truthy
     * in BareScript, even when empty - this differs from Python's natural truthiness
     * where empty dict is falsy). Tuple is the same. */
    if (PyDict_Check(value)) return 1;
    if (PyTuple_Check(value)) return 1;

    /* For all other types (datetime, regex, function, custom types), value_boolean
     * returns True for non-None values. We can safely return 1 here since None was
     * handled above. */
    return 1;
}


/* Helper: Call value_compare(left, right) */
static PyObject *
call_value_compare(PyObject *left, PyObject *right)
{
    return PyObject_CallFunctionObjArgs(g_value_compare, left, right, NULL);
}


/* Helper: Check if value is a number (int or float, but not bool) */
static int
is_number(PyObject *value)
{
    if (PyBool_Check(value)) return 0;
    return PyLong_Check(value) || PyFloat_Check(value);
}


/* Helper: Check if value is an integer-valued number (not bool) */
static int
is_integer_number(PyObject *value)
{
    if (PyBool_Check(value)) return 0;
    if (PyLong_Check(value)) return 1;
    if (PyFloat_Check(value)) {
        double d = PyFloat_AS_DOUBLE(value);
        return d == (double)(long long)d;
    }
    return 0;
}


/* Helper: Check if value is a datetime (date or datetime) */
static int
is_datetime(PyObject *value)
{
    return PyObject_IsInstance(value, g_datetime_date);
}


/* Helper: Convert value to long long integer (must be is_integer_number) */
static long long
to_long_long(PyObject *value)
{
    if (PyLong_Check(value)) {
        return PyLong_AsLongLong(value);
    }
    /* float */
    return (long long)PyFloat_AS_DOUBLE(value);
}


/* Helper: Construct timedelta(milliseconds=ms_value) */
static PyObject *
make_timedelta_ms(PyObject *ms_value)
{
    PyObject *empty_args = PyTuple_New(0);
    if (empty_args == NULL) return NULL;
    PyObject *kwargs = PyDict_New();
    if (kwargs == NULL) {
        Py_DECREF(empty_args);
        return NULL;
    }
    if (PyDict_SetItem(kwargs, g_str_milliseconds, ms_value) < 0) {
        Py_DECREF(empty_args);
        Py_DECREF(kwargs);
        return NULL;
    }
    PyObject *delta = PyObject_Call(g_timedelta, empty_args, kwargs);
    Py_DECREF(empty_args);
    Py_DECREF(kwargs);
    return delta;
}


/* Evaluate a binary expression after operands are computed.
 * Both left_value and right_value are borrowed references.
 * Returns new reference or NULL on error.
 */
static PyObject *
evaluate_binary_op(const char *op, Py_ssize_t op_len, PyObject *left_value, PyObject *right_value)
{
    /* '+' addition */
    if (op_len == 1 && op[0] == '+') {
        /* number + number */
        if (is_number(left_value) && is_number(right_value)) {
            return PyNumber_Add(left_value, right_value);
        }
        /* string + string */
        int left_str = PyUnicode_Check(left_value);
        int right_str = PyUnicode_Check(right_value);
        if (left_str && right_str) {
            return PyUnicode_Concat(left_value, right_value);
        }
        /* string + <any> */
        if (left_str) {
            PyObject *right_str_val = PyObject_CallOneArg(g_value_string, right_value);
            if (right_str_val == NULL) return NULL;
            PyObject *result = PyUnicode_Concat(left_value, right_str_val);
            Py_DECREF(right_str_val);
            return result;
        }
        if (right_str) {
            PyObject *left_str_val = PyObject_CallOneArg(g_value_string, left_value);
            if (left_str_val == NULL) return NULL;
            PyObject *result = PyUnicode_Concat(left_str_val, right_value);
            Py_DECREF(left_str_val);
            return result;
        }
        /* datetime + number */
        if (is_datetime(left_value) && is_number(right_value)) {
            PyObject *left_dt = PyObject_CallOneArg(g_value_normalize_datetime, left_value);
            if (left_dt == NULL) return NULL;
            PyObject *delta = make_timedelta_ms(right_value);
            if (delta == NULL) {
                Py_DECREF(left_dt);
                return NULL;
            }
            PyObject *result = PyNumber_Add(left_dt, delta);
            Py_DECREF(left_dt);
            Py_DECREF(delta);
            return result;
        }
        /* number + datetime */
        if (is_number(left_value) && is_datetime(right_value)) {
            PyObject *right_dt = PyObject_CallOneArg(g_value_normalize_datetime, right_value);
            if (right_dt == NULL) return NULL;
            PyObject *delta = make_timedelta_ms(left_value);
            if (delta == NULL) {
                Py_DECREF(right_dt);
                return NULL;
            }
            PyObject *result = PyNumber_Add(right_dt, delta);
            Py_DECREF(right_dt);
            Py_DECREF(delta);
            return result;
        }
        Py_RETURN_NONE;
    }

    /* '-' subtraction */
    if (op_len == 1 && op[0] == '-') {
        if (is_number(left_value) && is_number(right_value)) {
            return PyNumber_Subtract(left_value, right_value);
        }
        if (is_datetime(left_value) && is_datetime(right_value)) {
            PyObject *left_dt = PyObject_CallOneArg(g_value_normalize_datetime, left_value);
            if (left_dt == NULL) return NULL;
            PyObject *right_dt = PyObject_CallOneArg(g_value_normalize_datetime, right_value);
            if (right_dt == NULL) {
                Py_DECREF(left_dt);
                return NULL;
            }
            PyObject *delta = PyNumber_Subtract(left_dt, right_dt);
            Py_DECREF(left_dt);
            Py_DECREF(right_dt);
            if (delta == NULL) return NULL;
            /* delta.total_seconds() * 1000 */
            PyObject *total_seconds = PyObject_CallMethod(delta, "total_seconds", NULL);
            Py_DECREF(delta);
            if (total_seconds == NULL) return NULL;
            PyObject *thousand = PyLong_FromLong(1000);
            if (thousand == NULL) {
                Py_DECREF(total_seconds);
                return NULL;
            }
            PyObject *ms = PyNumber_Multiply(total_seconds, thousand);
            Py_DECREF(total_seconds);
            Py_DECREF(thousand);
            if (ms == NULL) return NULL;
            PyObject *zero = PyLong_FromLong(0);
            if (zero == NULL) {
                Py_DECREF(ms);
                return NULL;
            }
            PyObject *result = PyObject_CallFunctionObjArgs(g_value_round_number, ms, zero, NULL);
            Py_DECREF(ms);
            Py_DECREF(zero);
            return result;
        }
        Py_RETURN_NONE;
    }

    /* '*' multiplication */
    if (op_len == 1 && op[0] == '*') {
        if (is_number(left_value) && is_number(right_value)) {
            return PyNumber_Multiply(left_value, right_value);
        }
        Py_RETURN_NONE;
    }

    /* '/' division */
    if (op_len == 1 && op[0] == '/') {
        if (is_number(left_value) && is_number(right_value)) {
            return PyNumber_TrueDivide(left_value, right_value);
        }
        Py_RETURN_NONE;
    }

    /* '%' modulus */
    if (op_len == 1 && op[0] == '%') {
        if (is_number(left_value) && is_number(right_value)) {
            return PyNumber_Remainder(left_value, right_value);
        }
        Py_RETURN_NONE;
    }

    /* Comparisons */
    if (op_len == 2 && op[0] == '=' && op[1] == '=') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp == NULL) return NULL;
        long c = PyLong_AsLong(cmp);
        Py_DECREF(cmp);
        if (c == -1 && PyErr_Occurred()) return NULL;
        if (c == 0) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }
    if (op_len == 2 && op[0] == '!' && op[1] == '=') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp == NULL) return NULL;
        long c = PyLong_AsLong(cmp);
        Py_DECREF(cmp);
        if (c == -1 && PyErr_Occurred()) return NULL;
        if (c != 0) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }
    if (op_len == 2 && op[0] == '<' && op[1] == '=') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp == NULL) return NULL;
        long c = PyLong_AsLong(cmp);
        Py_DECREF(cmp);
        if (c == -1 && PyErr_Occurred()) return NULL;
        if (c <= 0) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }
    if (op_len == 1 && op[0] == '<') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp == NULL) return NULL;
        long c = PyLong_AsLong(cmp);
        Py_DECREF(cmp);
        if (c == -1 && PyErr_Occurred()) return NULL;
        if (c < 0) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }
    if (op_len == 2 && op[0] == '>' && op[1] == '=') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp == NULL) return NULL;
        long c = PyLong_AsLong(cmp);
        Py_DECREF(cmp);
        if (c == -1 && PyErr_Occurred()) return NULL;
        if (c >= 0) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }
    if (op_len == 1 && op[0] == '>') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp == NULL) return NULL;
        long c = PyLong_AsLong(cmp);
        Py_DECREF(cmp);
        if (c == -1 && PyErr_Occurred()) return NULL;
        if (c > 0) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }

    /* '**' exponentiation */
    if (op_len == 2 && op[0] == '*' && op[1] == '*') {
        if (is_number(left_value) && is_number(right_value)) {
            return PyNumber_Power(left_value, right_value, Py_None);
        }
        Py_RETURN_NONE;
    }

    /* Bitwise operators - require integer-valued numbers */
    if (op_len == 1 && op[0] == '&') {
        if (is_integer_number(left_value) && is_integer_number(right_value)) {
            long long l = to_long_long(left_value);
            long long r = to_long_long(right_value);
            return PyLong_FromLongLong(l & r);
        }
        Py_RETURN_NONE;
    }
    if (op_len == 1 && op[0] == '|') {
        if (is_integer_number(left_value) && is_integer_number(right_value)) {
            long long l = to_long_long(left_value);
            long long r = to_long_long(right_value);
            return PyLong_FromLongLong(l | r);
        }
        Py_RETURN_NONE;
    }
    if (op_len == 1 && op[0] == '^') {
        if (is_integer_number(left_value) && is_integer_number(right_value)) {
            long long l = to_long_long(left_value);
            long long r = to_long_long(right_value);
            return PyLong_FromLongLong(l ^ r);
        }
        Py_RETURN_NONE;
    }
    if (op_len == 2 && op[0] == '<' && op[1] == '<') {
        if (is_integer_number(left_value) && is_integer_number(right_value)) {
            long long l = to_long_long(left_value);
            long long r = to_long_long(right_value);
            return PyLong_FromLongLong(l << r);
        }
        Py_RETURN_NONE;
    }
    if (op_len == 2 && op[0] == '>' && op[1] == '>') {
        if (is_integer_number(left_value) && is_integer_number(right_value)) {
            long long l = to_long_long(left_value);
            long long r = to_long_long(right_value);
            return PyLong_FromLongLong(l >> r);
        }
        Py_RETURN_NONE;
    }

    /* Unknown operator */
    Py_RETURN_NONE;
}


/* Helper: Get globals dict from options (returns borrowed reference, or NULL if not present) */
static PyObject *
get_globals(PyObject *options)
{
    if (options == NULL || options == Py_None) return NULL;
    if (!PyDict_Check(options)) return NULL;
    PyObject *globals_ = fast_dict_get(options, g_str_globals);
    if (globals_ == Py_None) return NULL;
    return globals_;
}


/* Core recursive expression evaluator
 *
 * Returns a new reference or NULL on error.
 * All input arguments are borrowed references. options/locals_/script/statement may be NULL.
 */
static PyObject *
evaluate_expression_impl(PyObject *expr, PyObject *options, PyObject *locals_,
                          int builtins, PyObject *script, PyObject *statement,
                          long *stmt_count)
{
    PyObject *result = NULL;

    /* Get the discriminator key AND its value in one pass. */
    PyObject *expr_key, *expr_inner;
    if (get_expr_key_value(expr, &expr_key, &expr_inner) < 0) {
        return NULL;
    }

    /* number */
    if (expr_key == g_str_number) {
        Py_INCREF(expr_inner);
        return expr_inner;
    }

    /* string */
    if (expr_key == g_str_string) {
        Py_INCREF(expr_inner);
        return expr_inner;
    }

    /* variable */
    if (expr_key == g_str_variable) {
        PyObject *var_name = expr_inner;

        /* Check keyword literals via pointer compare first */
        if (var_name == g_str_null) Py_RETURN_NONE;
        if (var_name == g_str_false) Py_RETURN_FALSE;
        if (var_name == g_str_true) Py_RETURN_TRUE;

        /* Slower fallback for non-interned variable names */
        if (PyUnicode_Check(var_name)) {
            int eq = PyUnicode_Compare(var_name, g_str_null);
            if (eq == 0) Py_RETURN_NONE;
            if (eq == -1 && PyErr_Occurred()) return NULL;
            eq = PyUnicode_Compare(var_name, g_str_false);
            if (eq == 0) Py_RETURN_FALSE;
            if (eq == -1 && PyErr_Occurred()) return NULL;
            eq = PyUnicode_Compare(var_name, g_str_true);
            if (eq == 0) Py_RETURN_TRUE;
            if (eq == -1 && PyErr_Occurred()) return NULL;
        }

        /* Check locals */
        if (locals_ != NULL && locals_ != Py_None && PyDict_Check(locals_)) {
            result = fast_dict_get(locals_, var_name);
            if (result != NULL) {
                Py_INCREF(result);
                return result;
            }
            int contains = PyDict_Contains(locals_, var_name);
            if (contains < 0) return NULL;
            if (contains) {
                Py_RETURN_NONE;
            }
        }

        /* Check globals */
        PyObject *globals_ = get_globals(options);
        if (globals_ != NULL) {
            result = fast_dict_get(globals_, var_name);
            if (result == NULL) {
                Py_RETURN_NONE;
            }
            Py_INCREF(result);
            return result;
        }

        Py_RETURN_NONE;
    }

    /* function */
    if (expr_key == g_str_function) {
        PyObject *func_obj = expr_inner;
        PyObject *func_name = fast_dict_get(func_obj, g_str_name);
        if (func_name == NULL) {
            PyErr_SetString(PyExc_KeyError, "name");
            return NULL;
        }

        /* "if" built-in - short-circuiting */
        int is_if = (func_name == g_str_if);
        if (!is_if && PyUnicode_Check(func_name)) {
            int eq = PyUnicode_Compare(func_name, g_str_if);
            if (eq == -1 && PyErr_Occurred()) return NULL;
            is_if = (eq == 0);
        }
        if (is_if) {
            PyObject *args_expr = fast_dict_get(func_obj, g_str_args);

            PyObject *value_expr = NULL;
            PyObject *true_expr = NULL;
            PyObject *false_expr = NULL;

            if (args_expr != NULL && PyList_Check(args_expr)) {
                Py_ssize_t alen = PyList_GET_SIZE(args_expr);
                if (alen >= 1) value_expr = PyList_GET_ITEM(args_expr, 0);
                if (alen >= 2) true_expr = PyList_GET_ITEM(args_expr, 1);
                if (alen >= 3) false_expr = PyList_GET_ITEM(args_expr, 2);
            }

            int truth = 0;
            if (value_expr != NULL) {
                PyObject *value = evaluate_expression_impl(value_expr, options, locals_, builtins, script, statement, stmt_count);
                if (value == NULL) return NULL;
                truth = call_value_boolean(value);
                Py_DECREF(value);
                if (truth < 0) return NULL;
            }

            PyObject *result_expr = truth ? true_expr : false_expr;
            if (result_expr == NULL) {
                Py_RETURN_NONE;
            }

            return evaluate_expression_impl(result_expr, options, locals_, builtins, script, statement, stmt_count);
        }

        /* Compute the function arguments */
        PyObject *func_args = NULL;
        PyObject *args_expr = fast_dict_get(func_obj, g_str_args);
        if (args_expr != NULL && PyList_Check(args_expr)) {
            Py_ssize_t alen = PyList_GET_SIZE(args_expr);
            func_args = PyList_New(alen);
            if (func_args == NULL) return NULL;
            for (Py_ssize_t i = 0; i < alen; i++) {
                PyObject *arg_expr = PyList_GET_ITEM(args_expr, i);
                PyObject *arg_value = evaluate_expression_impl(arg_expr, options, locals_, builtins, script, statement, stmt_count);
                if (arg_value == NULL) {
                    Py_DECREF(func_args);
                    return NULL;
                }
                PyList_SET_ITEM(func_args, i, arg_value);
            }
        }

        /* Resolve the function: locals -> globals -> builtins */
        PyObject *func_value = NULL;
        if (locals_ != NULL && locals_ != Py_None && PyDict_Check(locals_)) {
            func_value = fast_dict_get(locals_, func_name);
        }
        if (func_value == NULL) {
            PyObject *globals_ = get_globals(options);
            if (globals_ != NULL) {
                func_value = fast_dict_get(globals_, func_name);
            }
        }
        if (func_value == NULL && builtins) {
            func_value = fast_dict_get(g_expression_functions, func_name);
        }

        if (func_value != NULL && func_value != Py_None) {
            /* Call the function */
            PyObject *args_arg = func_args ? func_args : Py_None;
            PyObject *options_arg = options ? options : Py_None;
            /* Sync statement count only for user-defined functions (ScriptFunction) which
             * re-enter execute_script_helper and need the current count in options. */
            int is_script_func = (Py_TYPE(func_value) == &ScriptFunctionType);
            if (is_script_func && stmt_count != NULL) {
                write_statement_count(options, *stmt_count);
            }
            PyObject *call_result = PyObject_CallFunctionObjArgs(func_value, args_arg, options_arg, NULL);
            Py_XDECREF(func_args);
            if (is_script_func && stmt_count != NULL) {
                *stmt_count = read_statement_count(options);
            }

            if (call_result == NULL) {
                /* Check if it's BareScriptRuntimeError - re-raise */
                if (PyErr_ExceptionMatches(g_runtime_error)) {
                    return NULL;
                }

                /* Save the exception */
                PyObject *exc_type, *exc_value, *exc_tb;
                PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
                PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);

                /* Optionally log */
                if (options != NULL && options != Py_None && PyDict_Check(options)) {
                    PyObject *log_fn = fast_dict_get(options, g_str_logFn);
                    if (log_fn != NULL && log_fn != Py_None) {
                        PyObject *debug = fast_dict_get(options, g_str_debug);
                        int dbg = (debug != NULL && PyObject_IsTrue(debug) == 1);
                        if (dbg) {
                            PyObject *err_str = exc_value ? PyObject_Str(exc_value) : PyUnicode_FromString("");
                            if (err_str != NULL) {
                                PyObject *msg = PyUnicode_FromFormat(
                                    "BareScript: Function \"%S\" failed with error: %S",
                                    func_name, err_str);
                                Py_DECREF(err_str);
                                if (msg != NULL) {
                                    PyObject *log_result = PyObject_CallOneArg(log_fn, msg);
                                    Py_DECREF(msg);
                                    Py_XDECREF(log_result);
                                }
                            }
                        }
                    }
                    /* Clear any errors from logging */
                    if (PyErr_Occurred()) PyErr_Clear();
                }

                /* If it's ValueArgsError, return its return_value */
                int is_args_error = (exc_value != NULL) ? PyObject_IsInstance(exc_value, g_value_args_error) : 0;
                if (is_args_error < 0) {
                    Py_XDECREF(exc_type);
                    Py_XDECREF(exc_value);
                    Py_XDECREF(exc_tb);
                    return NULL;
                }

                if (is_args_error) {
                    PyObject *return_value = PyObject_GetAttr(exc_value, g_str_return_value);
                    Py_XDECREF(exc_type);
                    Py_XDECREF(exc_value);
                    Py_XDECREF(exc_tb);
                    return return_value;
                }

                /* Otherwise return None */
                Py_XDECREF(exc_type);
                Py_XDECREF(exc_value);
                Py_XDECREF(exc_tb);
                Py_RETURN_NONE;
            }

            return call_result;
        }

        Py_XDECREF(func_args);

        /* Undefined function */
        PyObject *msg = PyUnicode_FromFormat("Undefined function \"%S\"", func_name);
        if (msg == NULL) return NULL;
        PyObject *script_arg = script ? script : Py_None;
        PyObject *stmt_arg = statement ? statement : Py_None;
        PyObject *exc = PyObject_CallFunctionObjArgs(g_runtime_error, script_arg, stmt_arg, msg, NULL);
        Py_DECREF(msg);
        if (exc != NULL) {
            PyErr_SetObject(g_runtime_error, exc);
            Py_DECREF(exc);
        }
        return NULL;
    }

    /* binary */
    if (expr_key == g_str_binary) {
        PyObject *bin_obj = expr_inner;
        PyObject *op_obj = fast_dict_get(bin_obj, g_str_op);
        PyObject *left_expr = fast_dict_get(bin_obj, g_str_left);
        PyObject *right_expr = fast_dict_get(bin_obj, g_str_right);
        if (op_obj == NULL || left_expr == NULL || right_expr == NULL) {
            PyErr_SetString(PyExc_KeyError, "binary fields");
            return NULL;
        }

        Py_ssize_t op_len;
        const char *op = PyUnicode_AsUTF8AndSize(op_obj, &op_len);
        if (op == NULL) return NULL;

        /* Evaluate left */
        PyObject *left_value = evaluate_expression_impl(left_expr, options, locals_, builtins, script, statement, stmt_count);
        if (left_value == NULL) return NULL;

        /* Short-circuit && */
        if (op_len == 2 && op[0] == '&' && op[1] == '&') {
            int truth = call_value_boolean(left_value);
            if (truth < 0) {
                Py_DECREF(left_value);
                return NULL;
            }
            if (!truth) {
                return left_value;
            }
            Py_DECREF(left_value);
            return evaluate_expression_impl(right_expr, options, locals_, builtins, script, statement, stmt_count);
        }

        /* Short-circuit || */
        if (op_len == 2 && op[0] == '|' && op[1] == '|') {
            int truth = call_value_boolean(left_value);
            if (truth < 0) {
                Py_DECREF(left_value);
                return NULL;
            }
            if (truth) {
                return left_value;
            }
            Py_DECREF(left_value);
            return evaluate_expression_impl(right_expr, options, locals_, builtins, script, statement, stmt_count);
        }

        /* Evaluate right */
        PyObject *right_value = evaluate_expression_impl(right_expr, options, locals_, builtins, script, statement, stmt_count);
        if (right_value == NULL) {
            Py_DECREF(left_value);
            return NULL;
        }

        result = evaluate_binary_op(op, op_len, left_value, right_value);
        Py_DECREF(left_value);
        Py_DECREF(right_value);
        return result;
    }

    /* unary */
    if (expr_key == g_str_unary) {
        PyObject *un_obj = expr_inner;
        PyObject *op_obj = fast_dict_get(un_obj, g_str_op);
        PyObject *sub_expr = fast_dict_get(un_obj, g_str_expr);
        if (op_obj == NULL || sub_expr == NULL) {
            PyErr_SetString(PyExc_KeyError, "unary fields");
            return NULL;
        }

        Py_ssize_t op_len;
        const char *op = PyUnicode_AsUTF8AndSize(op_obj, &op_len);
        if (op == NULL) return NULL;

        PyObject *value = evaluate_expression_impl(sub_expr, options, locals_, builtins, script, statement, stmt_count);
        if (value == NULL) return NULL;

        if (op_len == 1 && op[0] == '!') {
            int truth = call_value_boolean(value);
            Py_DECREF(value);
            if (truth < 0) return NULL;
            if (!truth) Py_RETURN_TRUE;
            Py_RETURN_FALSE;
        }
        if (op_len == 1 && op[0] == '-') {
            if (is_number(value)) {
                result = PyNumber_Negative(value);
                Py_DECREF(value);
                return result;
            }
            Py_DECREF(value);
            Py_RETURN_NONE;
        }
        if (op_len == 1 && op[0] == '~') {
            if (is_integer_number(value)) {
                long long v = to_long_long(value);
                Py_DECREF(value);
                return PyLong_FromLongLong(~v);
            }
            Py_DECREF(value);
            Py_RETURN_NONE;
        }
        Py_DECREF(value);
        Py_RETURN_NONE;
    }

    /* group */
    if (expr_key == g_str_group) {
        return evaluate_expression_impl(expr_inner, options, locals_, builtins, script, statement, stmt_count);
    }

    /* Unknown expression type - shouldn't happen with validated input */
    PyErr_Format(PyExc_ValueError, "unknown expression type");
    return NULL;
}


/* Helper: Record statement coverage */
static int
record_statement_coverage(PyObject *script, PyObject *statement, PyObject *statement_key, PyObject *coverage_global)
{
    PyObject *script_name = fast_dict_get(script, g_str_scriptName);
    if (script_name == NULL) return 0;

    PyObject *statement_inner = fast_dict_get(statement, statement_key);
    if (statement_inner == NULL) {
        PyErr_SetString(PyExc_KeyError, "statement key");
        return -1;
    }

    PyObject *lineno = fast_dict_get(statement_inner, g_str_lineNumber);
    if (lineno == NULL) return 0;

    PyObject *scripts = fast_dict_get(coverage_global, g_str_scripts);
    if (scripts == NULL) {
        scripts = PyDict_New();
        if (scripts == NULL) return -1;
        if (PyDict_SetItem(coverage_global, g_str_scripts, scripts) < 0) {
            Py_DECREF(scripts);
            return -1;
        }
        Py_DECREF(scripts);  /* Now borrowed via dict */
        scripts = fast_dict_get(coverage_global, g_str_scripts);
        if (scripts == NULL) return -1;
    }

    PyObject *script_coverage = fast_dict_get(scripts, script_name);
    if (script_coverage == NULL) {
        script_coverage = PyDict_New();
        if (script_coverage == NULL) return -1;
        if (PyDict_SetItem(script_coverage, g_str_script, script) < 0) {
            Py_DECREF(script_coverage);
            return -1;
        }
        PyObject *covered = PyDict_New();
        if (covered == NULL) {
            Py_DECREF(script_coverage);
            return -1;
        }
        if (PyDict_SetItem(script_coverage, g_str_covered, covered) < 0) {
            Py_DECREF(covered);
            Py_DECREF(script_coverage);
            return -1;
        }
        Py_DECREF(covered);
        if (PyDict_SetItem(scripts, script_name, script_coverage) < 0) {
            Py_DECREF(script_coverage);
            return -1;
        }
        Py_DECREF(script_coverage);
        script_coverage = fast_dict_get(scripts, script_name);
        if (script_coverage == NULL) return -1;
    }

    PyObject *covered = fast_dict_get(script_coverage, g_str_covered);
    if (covered == NULL) {
        PyErr_SetString(PyExc_KeyError, "covered");
        return -1;
    }

    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) return -1;

    PyObject *covered_statement = fast_dict_get(covered, lineno_str);
    if (covered_statement == NULL) {
        covered_statement = PyDict_New();
        if (covered_statement == NULL) {
            Py_DECREF(lineno_str);
            return -1;
        }
        if (PyDict_SetItem(covered_statement, g_str_statement, statement) < 0) {
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        PyObject *zero = PyLong_FromLong(0);
        if (zero == NULL) {
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        if (PyDict_SetItem(covered_statement, g_str_count, zero) < 0) {
            Py_DECREF(zero);
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        Py_DECREF(zero);
        if (PyDict_SetItem(covered, lineno_str, covered_statement) < 0) {
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        Py_DECREF(covered_statement);
        covered_statement = fast_dict_get(covered, lineno_str);
        if (covered_statement == NULL) {
            Py_DECREF(lineno_str);
            return -1;
        }
    }
    Py_DECREF(lineno_str);

    /* Increment count */
    PyObject *current_count = fast_dict_get(covered_statement, g_str_count);
    if (current_count == NULL) {
        PyErr_SetString(PyExc_KeyError, "count");
        return -1;
    }
    PyObject *one = PyLong_FromLong(1);
    if (one == NULL) return -1;
    PyObject *new_count = PyNumber_Add(current_count, one);
    Py_DECREF(one);
    if (new_count == NULL) return -1;
    if (PyDict_SetItem(covered_statement, g_str_count, new_count) < 0) {
        Py_DECREF(new_count);
        return -1;
    }
    Py_DECREF(new_count);
    return 0;
}


/* Helper: Raise a BareScriptRuntimeError */
static void
raise_runtime_error(PyObject *script, PyObject *statement, const char *message)
{
    PyObject *msg_obj = PyUnicode_FromString(message);
    if (msg_obj == NULL) return;
    PyObject *script_arg = script ? script : Py_None;
    PyObject *stmt_arg = statement ? statement : Py_None;
    PyObject *exc = PyObject_CallFunctionObjArgs(g_runtime_error, script_arg, stmt_arg, msg_obj, NULL);
    Py_DECREF(msg_obj);
    if (exc != NULL) {
        PyErr_SetObject(g_runtime_error, exc);
        Py_DECREF(exc);
    }
}


/* Core execute_script_helper - executes a list of statements
 *
 * Returns a new reference (or Py_None new ref) on success, NULL on error.
 * If a return statement is encountered, returns its value (new reference).
 * If statements complete normally, returns Py_None.
 *
 * Statement counting strategy:
 * - We maintain a local C `long statement_count` to avoid creating/destroying
 *   PyLong objects on every statement.
 * - We read the initial count from options['statementCount'] at entry.
 * - We write it back to options['statementCount'] only when needed:
 *   1. Before include execution (which calls execute_script_helper recursively)
 *   2. At scope exit (normal completion, return, or error)
 * - Expression evaluation (which may call user-defined ScriptFunctions that
 *   re-enter execute_script_helper) is handled by writing the count before
 *   the expression and reading it back after. However, we only do this for
 *   expressions that *could* call functions — which is all expressions since
 *   we can't know statically. To minimize overhead, we write once before
 *   evaluating and read once after, rather than the previous approach of
 *   wrapping every single expression evaluation.
 *
 * The key optimization vs the previous code: we write/read the count
 * once per statement (before/after the expression evaluation), not
 * around every sub-expression. Since a single statement may contain
 * many sub-expressions but only one top-level evaluation, this
 * dramatically reduces PyLong creation.
 */
static PyObject *
execute_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_)
{
    if (Py_EnterRecursiveCall(" while executing BareScript")) {
        return NULL;
    }

    /* Get globals from options */
    PyObject *globals_ = (options != NULL && options != Py_None) ? get_globals(options) : NULL;

    /* Cache for label indices */
    PyObject *label_indexes = NULL;

    /* Read statement counter and max statements from options once at entry. */
    long statement_count = read_statement_count(options);
    long max_statements = g_default_max_statements_long;
    if (options != NULL && options != Py_None && PyDict_Check(options)) {
        PyObject *max_obj = fast_dict_get(options, g_str_maxStatements);
        max_statements = number_to_long(max_obj, g_default_max_statements_long);
    }

    /* Determine coverage state once */
    int script_is_system = 0;
    if (script != NULL && PyDict_Check(script)) {
        PyObject *sys = fast_dict_get(script, g_str_system);
        if (sys != NULL) script_is_system = PyObject_IsTrue(sys) == 1;
    }

    Py_ssize_t statements_length = PyList_Check(statements) ? PyList_GET_SIZE(statements) : 0;
    Py_ssize_t ix_statement = 0;

    /* Cache coverage state once before the loop to avoid per-statement dict lookup. */
    int has_coverage = 0;
    PyObject *coverage_global_cached = NULL;
    if (globals_ != NULL && !script_is_system) {
        PyObject *tmp = fast_dict_get(globals_, g_str___barescriptCoverage);
        if (tmp != NULL && PyDict_Check(tmp)) {
            PyObject *enabled = fast_dict_get(tmp, g_str_enabled);
            if (enabled != NULL && PyObject_IsTrue(enabled) == 1) {
                Py_INCREF(tmp);
                coverage_global_cached = tmp;
                has_coverage = 1;
            }
        }
    }

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_GET_ITEM(statements, ix_statement);

        /* Get the discriminator key AND its value in one pass. */
        PyObject *statement_key, *statement_inner;
        if (get_statement_key_value(statement, &statement_key, &statement_inner) < 0) goto error;

        /* Increment statement counter (cached locally) */
        statement_count++;
        if (max_statements > 0 && statement_count > max_statements) {
            char msg[128];
            snprintf(msg, sizeof(msg), "Exceeded maximum script statements (%ld)", max_statements);
            raise_runtime_error(script, statement, msg);
            goto error;
        }

        if (has_coverage) {
            if (record_statement_coverage(script, statement, statement_key, coverage_global_cached) < 0) {
                goto error;
            }
        }

        /* expr */
        if (statement_key == g_str_expr) {
            PyObject *expr_obj = statement_inner;
            PyObject *expr_inner = fast_dict_get(expr_obj, g_str_expr);
            if (expr_inner == NULL) {
                PyErr_SetString(PyExc_KeyError, "expr inner");
                goto error;
            }

            PyObject *expr_value = evaluate_expression_impl(expr_inner, options, locals_, 0, script, statement, &statement_count);

            if (expr_value == NULL) goto error;

            PyObject *expr_name = fast_dict_get(expr_obj, g_str_name);
            if (expr_name != NULL) {
                PyObject *target = (locals_ != NULL) ? locals_ : globals_;
                if (target != NULL) {
                    if (PyDict_SetItem(target, expr_name, expr_value) < 0) {
                        Py_DECREF(expr_value);
                        goto error;
                    }
                }
            }
            Py_DECREF(expr_value);
            ix_statement++;
            continue;
        }

        /* jump */
        if (statement_key == g_str_jump) {
            PyObject *jump_obj = statement_inner;

            /* Evaluate condition (if any) */
            int do_jump = 1;
            PyObject *jump_expr = fast_dict_get(jump_obj, g_str_expr);
            if (jump_expr != NULL) {
                PyObject *cond_value = evaluate_expression_impl(jump_expr, options, locals_, 0, script, statement, &statement_count);
                if (cond_value == NULL) goto error;
                int truth = call_value_boolean(cond_value);
                Py_DECREF(cond_value);
                if (truth < 0) goto error;
                do_jump = truth;
            }

            if (do_jump) {
                PyObject *jump_label = fast_dict_get(jump_obj, g_str_label);
                if (jump_label == NULL) {
                    PyErr_SetString(PyExc_KeyError, "jump.label");
                    goto error;
                }

                /* Look up in cache */
                Py_ssize_t target_index = -1;
                if (label_indexes != NULL) {
                    PyObject *cached = fast_dict_get(label_indexes, jump_label);
                    if (cached != NULL) {
                        target_index = PyLong_AsSsize_t(cached);
                        if (target_index == -1 && PyErr_Occurred()) goto error;
                    }
                }

                if (target_index < 0) {
                    /* Search for label */
                    for (Py_ssize_t i = 0; i < statements_length; i++) {
                        PyObject *stmt = PyList_GET_ITEM(statements, i);
                        PyObject *label_obj = fast_dict_get(stmt, g_str_label);
                        if (label_obj != NULL) {
                            PyObject *label_name = fast_dict_get(label_obj, g_str_name);
                            if (label_name == NULL) goto error;
                            int eq = PyObject_RichCompareBool(label_name, jump_label, Py_EQ);
                            if (eq < 0) goto error;
                            if (eq) {
                                target_index = i;
                                break;
                            }
                        }
                    }
                    if (target_index < 0) {
                        PyObject *label_str = PyObject_Str(jump_label);
                        const char *label_cstr = label_str ? PyUnicode_AsUTF8(label_str) : "?";
                        char msg[256];
                        snprintf(msg, sizeof(msg), "Unknown jump label \"%s\"", label_cstr ? label_cstr : "?");
                        Py_XDECREF(label_str);
                        raise_runtime_error(script, statement, msg);
                        goto error;
                    }

                    /* Cache it */
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) goto error;
                    }
                    PyObject *idx_obj = PyLong_FromSsize_t(target_index);
                    if (idx_obj == NULL) goto error;
                    if (PyDict_SetItem(label_indexes, jump_label, idx_obj) < 0) {
                        Py_DECREF(idx_obj);
                        goto error;
                    }
                    Py_DECREF(idx_obj);
                }

                ix_statement = target_index;

                /* Record the label statement coverage */
                if (has_coverage) {
                    PyObject *label_statement = PyList_GET_ITEM(statements, ix_statement);
                    PyObject *label_key = get_statement_key(label_statement);
                    if (label_key == NULL) goto error;
                    if (record_statement_coverage(script, label_statement, label_key, coverage_global_cached) < 0) {
                        goto error;
                    }
                }
                ix_statement++;
                continue;
            }
            ix_statement++;
            continue;
        }

        /* return */
        if (statement_key == g_str_return) {
            PyObject *return_obj = statement_inner;
            PyObject *return_expr = fast_dict_get(return_obj, g_str_expr);
            PyObject *result;
            if (return_expr != NULL) {
                result = evaluate_expression_impl(return_expr, options, locals_, 0, script, statement, &statement_count);
            } else {
                Py_INCREF(Py_None);
                result = Py_None;
            }

            /* Persist statement counter back to options */
            write_statement_count(options, statement_count);

            Py_XDECREF(coverage_global_cached);
            Py_XDECREF(label_indexes);
            Py_LeaveRecursiveCall();
            return result;
        }

        /* function */
        if (statement_key == g_str_function) {
            PyObject *func_def = statement_inner;
            PyObject *func_name = fast_dict_get(func_def, g_str_name);
            if (func_name == NULL) {
                PyErr_SetString(PyExc_KeyError, "function.name");
                goto error;
            }
            PyObject *script_func = ScriptFunction_new(script, func_def);
            if (script_func == NULL) goto error;
            if (globals_ != NULL) {
                if (PyDict_SetItem(globals_, func_name, script_func) < 0) {
                    Py_DECREF(script_func);
                    goto error;
                }
            }
            Py_DECREF(script_func);
            ix_statement++;
            continue;
        }

        /* label - skip */
        if (statement_key == g_str_label) {
            ix_statement++;
            continue;
        }

        /* include */
        if (statement_key == g_str_include) {
            /* Persist statement counter before include execution since the
             * included script's execute_script_helper will read it. */
            write_statement_count(options, statement_count);

            PyObject *include_obj = statement_inner;
            PyObject *includes_list = fast_dict_get(include_obj, g_str_includes);
            if (includes_list == NULL) {
                PyErr_SetString(PyExc_KeyError, "include.includes");
                goto error;
            }

            PyObject *system_prefix = NULL;
            PyObject *fetch_fn = NULL;
            PyObject *log_fn = NULL;
            PyObject *url_fn = NULL;
            if (options != NULL && options != Py_None && PyDict_Check(options)) {
                system_prefix = fast_dict_get(options, g_str_systemPrefix);
                fetch_fn = fast_dict_get(options, g_str_fetchFn);
                log_fn = fast_dict_get(options, g_str_logFn);
                url_fn = fast_dict_get(options, g_str_urlFn);
            }

            Py_ssize_t includes_length = PyList_Check(includes_list) ? PyList_GET_SIZE(includes_list) : 0;
            for (Py_ssize_t i = 0; i < includes_length; i++) {
                PyObject *include = PyList_GET_ITEM(includes_list, i);
                PyObject *include_url_orig = fast_dict_get(include, g_str_url);
                if (include_url_orig == NULL) {
                    PyErr_SetString(PyExc_KeyError, "include.url");
                    goto error;
                }

                /* Determine system include */
                int system_include = 0;
                {
                    PyObject *sys = fast_dict_get(include, g_str_system);
                    if (sys != NULL) {
                        system_include = PyObject_IsTrue(sys) == 1;
                    }
                }

                /* Compute fixed-up URL */
                PyObject *include_url = NULL;
                if (system_include && system_prefix != NULL && system_prefix != Py_None) {
                    include_url = PyObject_CallFunctionObjArgs(g_url_file_relative, system_prefix, include_url_orig, NULL);
                    if (include_url == NULL) goto error;
                } else if (url_fn != NULL && url_fn != Py_None) {
                    include_url = PyObject_CallOneArg(url_fn, include_url_orig);
                    if (include_url == NULL) goto error;
                } else {
                    Py_INCREF(include_url_orig);
                    include_url = include_url_orig;
                }

                /* Check if already included */
                if (globals_ != NULL) {
                    PyObject *global_includes = fast_dict_get(globals_, g_str___barescriptIncludes);
                    if (global_includes == NULL || !PyDict_Check(global_includes)) {
                        PyObject *new_includes = PyDict_New();
                        if (new_includes == NULL) {
                            Py_DECREF(include_url);
                            goto error;
                        }
                        if (PyDict_SetItem(globals_, g_str___barescriptIncludes, new_includes) < 0) {
                            Py_DECREF(new_includes);
                            Py_DECREF(include_url);
                            goto error;
                        }
                        Py_DECREF(new_includes);
                        global_includes = fast_dict_get(globals_, g_str___barescriptIncludes);
                        if (global_includes == NULL) {
                            Py_DECREF(include_url);
                            goto error;
                        }
                    }
                    PyObject *already = fast_dict_get(global_includes, include_url);
                    if (already != NULL && PyObject_IsTrue(already) == 1) {
                        Py_DECREF(include_url);
                        continue;
                    }
                    if (PyDict_SetItem(global_includes, include_url, Py_True) < 0) {
                        Py_DECREF(include_url);
                        goto error;
                    }
                }

                /* Fetch the URL */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL && fetch_fn != Py_None) {
                    PyObject *request = PyDict_New();
                    if (request == NULL) {
                        Py_DECREF(include_url);
                        goto error;
                    }
                    if (PyDict_SetItem(request, g_str_url, include_url) < 0) {
                        Py_DECREF(request);
                        Py_DECREF(include_url);
                        goto error;
                    }
                    include_text = PyObject_CallOneArg(fetch_fn, request);
                    Py_DECREF(request);
                    if (include_text == NULL) {
                        /* Swallow exception, treat as fetch failure */
                        PyErr_Clear();
                    }
                }

                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    PyObject *url_str = PyObject_Str(include_url);
                    const char *url_cstr = url_str ? PyUnicode_AsUTF8(url_str) : "?";
                    char msg[512];
                    snprintf(msg, sizeof(msg), "Include of \"%s\" failed", url_cstr ? url_cstr : "?");
                    Py_XDECREF(url_str);
                    raise_runtime_error(script, statement, msg);
                    Py_DECREF(include_url);
                    goto error;
                }

                /* Parse the include script */
                PyObject *one = PyLong_FromLong(1);
                if (one == NULL) {
                    Py_DECREF(include_text);
                    Py_DECREF(include_url);
                    goto error;
                }
                PyObject *include_script = PyObject_CallFunctionObjArgs(g_parse_script, include_text, one, include_url, NULL);
                Py_DECREF(one);
                Py_DECREF(include_text);
                if (include_script == NULL) {
                    Py_DECREF(include_url);
                    goto error;
                }
                if (system_include) {
                    if (PyDict_SetItem(include_script, g_str_system, Py_True) < 0) {
                        Py_DECREF(include_script);
                        Py_DECREF(include_url);
                        goto error;
                    }
                }

                /* Build include options - copy options and update urlFn */
                PyObject *include_options = NULL;
                if (options != NULL && options != Py_None && PyDict_Check(options)) {
                    include_options = PyDict_Copy(options);
                    if (include_options == NULL) {
                        Py_DECREF(include_script);
                        Py_DECREF(include_url);
                        goto error;
                    }
                    /* urlFn = partial(url_file_relative, include_url) */
                    PyObject *new_url_fn = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, include_url, NULL);
                    if (new_url_fn == NULL) {
                        Py_DECREF(include_options);
                        Py_DECREF(include_script);
                        Py_DECREF(include_url);
                        goto error;
                    }
                    if (PyDict_SetItem(include_options, g_str_urlFn, new_url_fn) < 0) {
                        Py_DECREF(new_url_fn);
                        Py_DECREF(include_options);
                        Py_DECREF(include_script);
                        Py_DECREF(include_url);
                        goto error;
                    }
                    Py_DECREF(new_url_fn);
                } else {
                    include_options = PyDict_New();
                    if (include_options == NULL) {
                        Py_DECREF(include_script);
                        Py_DECREF(include_url);
                        goto error;
                    }
                }

                /* Execute the include script */
                PyObject *include_statements = fast_dict_get(include_script, g_str_statements);
                if (include_statements == NULL) {
                    PyErr_SetString(PyExc_KeyError, "statements");
                    Py_DECREF(include_options);
                    Py_DECREF(include_script);
                    Py_DECREF(include_url);
                    goto error;
                }
                PyObject *exec_result = execute_script_helper(include_script, include_statements, include_options, NULL);
                if (exec_result == NULL) {
                    Py_DECREF(include_options);
                    Py_DECREF(include_script);
                    Py_DECREF(include_url);
                    goto error;
                }
                Py_DECREF(exec_result);

                /* Read back statement count after include execution */
                statement_count = read_statement_count(options);

                /* Run linter if debug */
                if (log_fn != NULL && log_fn != Py_None && options != NULL && PyDict_Check(options)) {
                    PyObject *debug = fast_dict_get(options, g_str_debug);
                    if (debug != NULL && PyObject_IsTrue(debug) == 1) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(g_lint_script, include_script, globals_, NULL);
                        if (warnings == NULL) {
                            Py_DECREF(include_options);
                            Py_DECREF(include_script);
                            Py_DECREF(include_url);
                            goto error;
                        }
                        Py_ssize_t warnings_len = PyList_Check(warnings) ? PyList_GET_SIZE(warnings) : 0;
                        if (warnings_len > 0) {
                            PyObject *prefix_msg = PyUnicode_FromFormat(
                                "BareScript: Include \"%S\" static analysis... %zd warning%s:",
                                include_url, warnings_len, warnings_len > 1 ? "s" : "");
                            if (prefix_msg != NULL) {
                                PyObject *r = PyObject_CallOneArg(log_fn, prefix_msg);
                                Py_XDECREF(r);
                                Py_DECREF(prefix_msg);
                            }
                            for (Py_ssize_t wi = 0; wi < warnings_len; wi++) {
                                PyObject *w = PyList_GET_ITEM(warnings, wi);
                                PyObject *wmsg = PyUnicode_FromFormat("BareScript: %S", w);
                                if (wmsg != NULL) {
                                    PyObject *r = PyObject_CallOneArg(log_fn, wmsg);
                                    Py_XDECREF(r);
                                    Py_DECREF(wmsg);
                                }
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }

                Py_DECREF(include_options);
                Py_DECREF(include_script);
                Py_DECREF(include_url);
            }

            ix_statement++;
            continue;
        }

        /* Unknown statement type - just skip */
        ix_statement++;
    }

    /* Persist statement counter back to options before returning */
    write_statement_count(options, statement_count);

    Py_XDECREF(coverage_global_cached);
    Py_XDECREF(label_indexes);
    Py_LeaveRecursiveCall();
    Py_RETURN_NONE;

error:
    /* Persist statement counter even on error path */
    if (options != NULL && options != Py_None && PyDict_Check(options)) {
        PyObject *count_obj = PyLong_FromLong(statement_count);
        if (count_obj != NULL) {
            /* Don't overwrite an existing exception */
            PyObject *t, *v, *tb;
            PyErr_Fetch(&t, &v, &tb);
            PyDict_SetItem(options, g_str_statementCount, count_obj);
            Py_DECREF(count_obj);
            PyErr_Restore(t, v, tb);
        }
    }
    Py_XDECREF(coverage_global_cached);
    Py_XDECREF(label_indexes);
    Py_LeaveRecursiveCall();
    return NULL;
}


/* Python-callable evaluate_expression(expr, options=None, locals_=None, builtins=True, script=None, statement=None) */
static PyObject *
runtime_c_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr;
    PyObject *options = Py_None;
    PyObject *locals_ = Py_None;
    int builtins = 1;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOpOO", kwlist,
                                      &expr, &options, &locals_, &builtins, &script, &statement)) {
        return NULL;
    }

    PyObject *opts = (options == Py_None) ? NULL : options;
    PyObject *locs = (locals_ == Py_None) ? NULL : locals_;
    PyObject *scr = (script == Py_None) ? NULL : script;
    PyObject *stmt = (statement == Py_None) ? NULL : statement;

    long stmt_count = read_statement_count(opts);
    return evaluate_expression_impl(expr, opts, locs, builtins, scr, stmt, &stmt_count);
}


/* Python-callable execute_script(script, options=None) */
static PyObject *
runtime_c_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script;
    PyObject *options = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &script, &options)) {
        return NULL;
    }

    /* Create options dict if None */
    PyObject *options_dict = NULL;
    int options_owned = 0;
    if (options == Py_None) {
        options_dict = PyDict_New();
        if (options_dict == NULL) return NULL;
        options_owned = 1;
    } else if (PyDict_Check(options)) {
        options_dict = options;
        Py_INCREF(options_dict);
        options_owned = 1;
    } else {
        PyErr_SetString(PyExc_TypeError, "options must be a dict or None");
        return NULL;
    }

    /* Create globals if not present */
    PyObject *globals_ = fast_dict_get(options_dict, g_str_globals);
    if (globals_ == NULL || globals_ == Py_None) {
        globals_ = PyDict_New();
        if (globals_ == NULL) {
            if (options_owned) Py_DECREF(options_dict);
            return NULL;
        }
        if (PyDict_SetItem(options_dict, g_str_globals, globals_) < 0) {
            Py_DECREF(globals_);
            if (options_owned) Py_DECREF(options_dict);
            return NULL;
        }
        Py_DECREF(globals_);
        globals_ = fast_dict_get(options_dict, g_str_globals);
        if (globals_ == NULL) {
            if (options_owned) Py_DECREF(options_dict);
            return NULL;
        }
    }

    /* Update globals with script functions (only if not already present) */
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(g_script_functions, &pos, &key, &value)) {
        int contains = PyDict_Contains(globals_, key);
        if (contains < 0) {
            if (options_owned) Py_DECREF(options_dict);
            return NULL;
        }
        if (!contains) {
            if (PyDict_SetItem(globals_, key, value) < 0) {
                if (options_owned) Py_DECREF(options_dict);
                return NULL;
            }
        }
    }

    /* Initialize statementCount */
    PyObject *zero = PyLong_FromLong(0);
    if (zero == NULL) {
        if (options_owned) Py_DECREF(options_dict);
        return NULL;
    }
    if (PyDict_SetItem(options_dict, g_str_statementCount, zero) < 0) {
        Py_DECREF(zero);
        if (options_owned) Py_DECREF(options_dict);
        return NULL;
    }
    Py_DECREF(zero);

    /* Get statements */
    PyObject *statements = fast_dict_get(script, g_str_statements);
    if (statements == NULL) {
        PyErr_SetString(PyExc_KeyError, "statements");
        if (options_owned) Py_DECREF(options_dict);
        return NULL;
    }

    PyObject *result = execute_script_helper(script, statements, options_dict, NULL);
    if (options_owned) Py_DECREF(options_dict);
    return result;
}


static PyMethodDef RuntimeCMethods[] = {
    {"evaluate_expression", (PyCFunction)(void(*)(void))runtime_c_evaluate_expression,
     METH_VARARGS | METH_KEYWORDS, "Evaluate a BareScript expression model (C implementation)"},
    {"execute_script", (PyCFunction)(void(*)(void))runtime_c_execute_script,
     METH_VARARGS | METH_KEYWORDS, "Execute a BareScript script model (C implementation)"},
    {NULL, NULL, 0, NULL}
};


static struct PyModuleDef runtime_c_module = {
    PyModuleDef_HEAD_INIT,
    "bare_script.runtime_c",
    "BareScript runtime C extension",
    -1,
    RuntimeCMethods,
    NULL, NULL, NULL, NULL
};


/* Helper to intern a string and store in a global */
static int
init_string(PyObject **dest, const char *str)
{
    *dest = PyUnicode_InternFromString(str);
    return *dest == NULL ? -1 : 0;
}


PyMODINIT_FUNC
PyInit_runtime_c(void)
{
    if (PyType_Ready(&ScriptFunctionType) < 0) return NULL;

    PyObject *module = PyModule_Create(&runtime_c_module);
    if (module == NULL) return NULL;

    /* Initialize interned strings */
    if (init_string(&g_str_number, "number") < 0) goto error;
    if (init_string(&g_str_string, "string") < 0) goto error;
    if (init_string(&g_str_variable, "variable") < 0) goto error;
    if (init_string(&g_str_function, "function") < 0) goto error;
    if (init_string(&g_str_binary, "binary") < 0) goto error;
    if (init_string(&g_str_unary, "unary") < 0) goto error;
    if (init_string(&g_str_group, "group") < 0) goto error;
    if (init_string(&g_str_null, "null") < 0) goto error;
    if (init_string(&g_str_false, "false") < 0) goto error;
    if (init_string(&g_str_true, "true") < 0) goto error;
    if (init_string(&g_str_if, "if") < 0) goto error;
    if (init_string(&g_str_name, "name") < 0) goto error;
    if (init_string(&g_str_args, "args") < 0) goto error;
    if (init_string(&g_str_op, "op") < 0) goto error;
    if (init_string(&g_str_left, "left") < 0) goto error;
    if (init_string(&g_str_right, "right") < 0) goto error;
    if (init_string(&g_str_expr, "expr") < 0) goto error;
    if (init_string(&g_str_globals, "globals") < 0) goto error;
    if (init_string(&g_str_logFn, "logFn") < 0) goto error;
    if (init_string(&g_str_debug, "debug") < 0) goto error;
    if (init_string(&g_str_return_value, "return_value") < 0) goto error;
    if (init_string(&g_str_milliseconds, "milliseconds") < 0) goto error;
    if (init_string(&g_str_statements, "statements") < 0) goto error;
    if (init_string(&g_str_jump, "jump") < 0) goto error;
    if (init_string(&g_str_label, "label") < 0) goto error;
    if (init_string(&g_str_return, "return") < 0) goto error;
    if (init_string(&g_str_include, "include") < 0) goto error;
    if (init_string(&g_str_includes, "includes") < 0) goto error;
    if (init_string(&g_str_url, "url") < 0) goto error;
    if (init_string(&g_str_system, "system") < 0) goto error;
    if (init_string(&g_str_lastArgArray, "lastArgArray") < 0) goto error;
    if (init_string(&g_str_statementCount, "statementCount") < 0) goto error;
    if (init_string(&g_str_maxStatements, "maxStatements") < 0) goto error;
    if (init_string(&g_str_systemPrefix, "systemPrefix") < 0) goto error;
    if (init_string(&g_str_fetchFn, "fetchFn") < 0) goto error;
    if (init_string(&g_str_urlFn, "urlFn") < 0) goto error;
    if (init_string(&g_str_scriptName, "scriptName") < 0) goto error;
    if (init_string(&g_str_lineNumber, "lineNumber") < 0) goto error;
    if (init_string(&g_str_scripts, "scripts") < 0) goto error;
    if (init_string(&g_str_script, "script") < 0) goto error;
    if (init_string(&g_str_covered, "covered") < 0) goto error;
    if (init_string(&g_str_count, "count") < 0) goto error;
    if (init_string(&g_str_statement, "statement") < 0) goto error;
    if (init_string(&g_str_enabled, "enabled") < 0) goto error;
    if (init_string(&g_str___barescriptCoverage, "__barescriptCoverage") < 0) goto error;
    if (init_string(&g_str___barescriptIncludes, "__barescriptIncludes") < 0) goto error;

    /* Import bare_script.value */
    PyObject *value_mod = PyImport_ImportModule("bare_script.value");
    if (value_mod == NULL) goto error;
    g_value_boolean = PyObject_GetAttrString(value_mod, "value_boolean");
    g_value_compare = PyObject_GetAttrString(value_mod, "value_compare");
    g_value_normalize_datetime = PyObject_GetAttrString(value_mod, "value_normalize_datetime");
    g_value_round_number = PyObject_GetAttrString(value_mod, "value_round_number");
    g_value_string = PyObject_GetAttrString(value_mod, "value_string");
    g_value_args_error = PyObject_GetAttrString(value_mod, "ValueArgsError");
    Py_DECREF(value_mod);
    if (!g_value_boolean || !g_value_compare || !g_value_normalize_datetime ||
        !g_value_round_number || !g_value_string || !g_value_args_error) goto error;

    /* Import bare_script.library */
    PyObject *library_mod = PyImport_ImportModule("bare_script.library");
    if (library_mod == NULL) goto error;
    g_expression_functions = PyObject_GetAttrString(library_mod, "EXPRESSION_FUNCTIONS");
    g_script_functions = PyObject_GetAttrString(library_mod, "SCRIPT_FUNCTIONS");
    g_default_max_statements = PyObject_GetAttrString(library_mod, "DEFAULT_MAX_STATEMENTS");
    Py_DECREF(library_mod);
    if (!g_expression_functions || !g_script_functions || !g_default_max_statements) goto error;

    /* Convert default max statements to long (it's a float in Python: 1e9) */
    if (PyLong_Check(g_default_max_statements)) {
        g_default_max_statements_long = PyLong_AsLong(g_default_max_statements);
    } else if (PyFloat_Check(g_default_max_statements)) {
        g_default_max_statements_long = (long)PyFloat_AS_DOUBLE(g_default_max_statements);
    } else {
        g_default_max_statements_long = 1000000000L;
    }

    /* Import bare_script.runtime for BareScriptRuntimeError */
    PyObject *runtime_mod = PyImport_ImportModule("bare_script.runtime");
    if (runtime_mod == NULL) goto error;
    g_runtime_error = PyObject_GetAttrString(runtime_mod, "BareScriptRuntimeError");
    Py_DECREF(runtime_mod);
    if (!g_runtime_error) goto error;

    /* Import bare_script.parser */
    PyObject *parser_mod = PyImport_ImportModule("bare_script.parser");
    if (parser_mod == NULL) goto error;
    g_parse_script = PyObject_GetAttrString(parser_mod, "parse_script");
    Py_DECREF(parser_mod);
    if (!g_parse_script) goto error;

    /* Import bare_script.model */
    PyObject *model_mod = PyImport_ImportModule("bare_script.model");
    if (model_mod == NULL) goto error;
    g_lint_script = PyObject_GetAttrString(model_mod, "lint_script");
    Py_DECREF(model_mod);
    if (!g_lint_script) goto error;

    /* Import bare_script.options */
    PyObject *options_mod = PyImport_ImportModule("bare_script.options");
    if (options_mod == NULL) goto error;
    g_url_file_relative = PyObject_GetAttrString(options_mod, "url_file_relative");
    Py_DECREF(options_mod);
    if (!g_url_file_relative) goto error;

    /* Import functools */
    PyObject *functools_mod = PyImport_ImportModule("functools");
    if (functools_mod == NULL) goto error;
    g_functools_partial = PyObject_GetAttrString(functools_mod, "partial");
    Py_DECREF(functools_mod);
    if (!g_functools_partial) goto error;

    /* Import datetime types */
    PyObject *datetime_mod = PyImport_ImportModule("datetime");
    if (datetime_mod == NULL) goto error;
    g_datetime_date = PyObject_GetAttrString(datetime_mod, "date");
    g_timedelta = PyObject_GetAttrString(datetime_mod, "timedelta");
    Py_DECREF(datetime_mod);
    if (!g_datetime_date || !g_timedelta) goto error;

    return module;

error:
    Py_DECREF(module);
    return NULL;
}
