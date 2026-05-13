/*
 * Licensed under the MIT License
 * https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE
 *
 * BareScript runtime - C implementation
 *
 * A faithful port of src/bare_script/runtime.py optimized for CPython 3.10+.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>


/* The default maximum statements for executeScript */
#define DEFAULT_MAX_STATEMENTS 1000000000LL


/* ---------------------------------------------------------------------- */
/* Module-level cached references                                          */
/* ---------------------------------------------------------------------- */

static PyObject *g_EXPRESSION_FUNCTIONS = NULL;
static PyObject *g_SCRIPT_FUNCTIONS = NULL;
static PyObject *g_BareScriptRuntimeError = NULL;
static PyObject *g_ValueArgsError = NULL;
static PyObject *g_value_boolean = NULL;
static PyObject *g_value_compare = NULL;
static PyObject *g_value_normalize_datetime = NULL;
static PyObject *g_value_round_number = NULL;
static PyObject *g_value_string = NULL;
static PyObject *g_lint_script = NULL;
static PyObject *g_url_file_relative = NULL;
static PyObject *g_parse_script = NULL;
static PyObject *g_datetime_date_type = NULL;
static PyObject *g_datetime_timedelta_type = NULL;
static PyObject *g_functools_partial = NULL;

/* Interned string keys */
static PyObject *S_globals;
static PyObject *S_statementCount;
static PyObject *S_maxStatements;
static PyObject *S_statements;
static PyObject *S_expr;
static PyObject *S_jump;
static PyObject *S_return;
static PyObject *S_function;
static PyObject *S_include;
static PyObject *S_label;
static PyObject *S_name;
static PyObject *S_args;
static PyObject *S_op;
static PyObject *S_left;
static PyObject *S_right;
static PyObject *S_number;
static PyObject *S_string;
static PyObject *S_variable;
static PyObject *S_binary;
static PyObject *S_unary;
static PyObject *S_group;
static PyObject *S_system;
static PyObject *S_url;
static PyObject *S_includes;
static PyObject *S_systemPrefix;
static PyObject *S_fetchFn;
static PyObject *S_logFn;
static PyObject *S_urlFn;
static PyObject *S_debug;
static PyObject *S_scriptName;
static PyObject *S_lineNumber;
static PyObject *S_scripts;
static PyObject *S_script;
static PyObject *S_covered;
static PyObject *S_count;
static PyObject *S_statement;
static PyObject *S_enabled;
static PyObject *S_lastArgArray;
static PyObject *S_null_str;
static PyObject *S_false_str;
static PyObject *S_true_str;
static PyObject *S_if_str;
static PyObject *S_SYSTEM_GLOBAL_COVERAGE;
static PyObject *S_SYSTEM_GLOBAL_INCLUDES;


/* ---------------------------------------------------------------------- */
/* ScriptFunction type — wraps (script, function) as a callable.           */
/* Replaces functools.partial(_script_function, script, function).         */
/* ---------------------------------------------------------------------- */

typedef struct {
    PyObject_HEAD
    PyObject *script;
    PyObject *function;
} ScriptFunctionObject;


static PyObject *exec_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_);


static int
ScriptFunction_traverse(ScriptFunctionObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->script);
    Py_VISIT(self->function);
    return 0;
}


static int
ScriptFunction_clear(ScriptFunctionObject *self)
{
    Py_CLEAR(self->script);
    Py_CLEAR(self->function);
    return 0;
}


static void
ScriptFunction_dealloc(ScriptFunctionObject *self)
{
    PyObject_GC_UnTrack(self);
    (void)ScriptFunction_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}


static PyObject *
ScriptFunction_call(PyObject *self_obj, PyObject *args, PyObject *kwargs)
{
    ScriptFunctionObject *self = (ScriptFunctionObject *)self_obj;
    if (kwargs != NULL && PyDict_GET_SIZE(kwargs) != 0) {
        PyErr_SetString(PyExc_TypeError, "script function takes no keyword arguments");
        return NULL;
    }
    if (PyTuple_GET_SIZE(args) != 2) {
        PyErr_SetString(PyExc_TypeError, "script function takes exactly 2 positional arguments");
        return NULL;
    }
    PyObject *func_args = PyTuple_GET_ITEM(args, 0);
    PyObject *options = PyTuple_GET_ITEM(args, 1);

    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) {
        return NULL;
    }

    PyObject *fn_args_list = PyDict_GetItemWithError(self->function, S_args);
    if (fn_args_list == NULL && PyErr_Occurred()) {
        Py_DECREF(func_locals);
        return NULL;
    }
    if (fn_args_list != NULL) {
        Py_ssize_t func_args_length = PyList_GET_SIZE(fn_args_list);
        Py_ssize_t args_length;
        if (PyList_Check(func_args)) {
            args_length = PyList_GET_SIZE(func_args);
        } else {
            args_length = PyObject_Length(func_args);
            if (args_length < 0) {
                Py_DECREF(func_locals);
                return NULL;
            }
        }

        Py_ssize_t ix_arg_last = -1;
        PyObject *last_arg_array = PyDict_GetItemWithError(self->function, S_lastArgArray);
        if (last_arg_array == NULL && PyErr_Occurred()) {
            Py_DECREF(func_locals);
            return NULL;
        }
        if (last_arg_array != NULL && PyObject_IsTrue(last_arg_array) == 1) {
            ix_arg_last = func_args_length - 1;
        }

        for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
            PyObject *arg_name = PyList_GET_ITEM(fn_args_list, ix);
            PyObject *value = NULL;
            if (ix < args_length) {
                if (ix != ix_arg_last) {
                    if (PyList_Check(func_args)) {
                        value = PyList_GET_ITEM(func_args, ix);
                        Py_INCREF(value);
                    } else {
                        value = PySequence_GetItem(func_args, ix);
                    }
                } else {
                    value = PySequence_GetSlice(func_args, ix, args_length);
                }
            } else {
                if (ix == ix_arg_last) {
                    value = PyList_New(0);
                } else {
                    value = Py_None;
                    Py_INCREF(value);
                }
            }
            if (value == NULL) {
                Py_DECREF(func_locals);
                return NULL;
            }
            if (PyDict_SetItem(func_locals, arg_name, value) < 0) {
                Py_DECREF(value);
                Py_DECREF(func_locals);
                return NULL;
            }
            Py_DECREF(value);
        }
    }

    PyObject *fn_statements = PyDict_GetItemWithError(self->function, S_statements);
    if (fn_statements == NULL) {
        Py_DECREF(func_locals);
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_KeyError, "statements");
        }
        return NULL;
    }
    PyObject *result = exec_script_helper(self->script, fn_statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}


static PyTypeObject ScriptFunctionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c.ScriptFunction",
    .tp_basicsize = sizeof(ScriptFunctionObject),
    .tp_itemsize = 0,
    .tp_dealloc = (destructor)ScriptFunction_dealloc,
    .tp_call = ScriptFunction_call,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)ScriptFunction_traverse,
    .tp_clear = (inquiry)ScriptFunction_clear,
};


static PyObject *
make_script_function(PyObject *script, PyObject *function)
{
    ScriptFunctionObject *sf = PyObject_GC_New(ScriptFunctionObject, &ScriptFunctionType);
    if (sf == NULL) {
        return NULL;
    }
    Py_INCREF(script);
    Py_INCREF(function);
    sf->script = script;
    sf->function = function;
    PyObject_GC_Track(sf);
    return (PyObject *)sf;
}


/* ---------------------------------------------------------------------- */
/* Value helpers                                                           */
/* ---------------------------------------------------------------------- */

/* C version of value_boolean: returns 1/0, or -1 on error. */
static int
c_value_boolean(PyObject *value)
{
    if (value == Py_None) return 0;
    if (value == Py_True) return 1;
    if (value == Py_False) return 0;
    if (PyUnicode_Check(value)) return PyUnicode_GetLength(value) != 0;
    if (PyLong_Check(value)) {
        int z = PyObject_Not(value);
        if (z < 0) return -1;
        return !z;
    }
    if (PyFloat_Check(value)) return PyFloat_AS_DOUBLE(value) != 0.0;
    if (PyList_Check(value)) return PyList_GET_SIZE(value) != 0;
    return 1;
}


/* Check value is a number (int or float) but not a bool */
static inline int
is_number(PyObject *value)
{
    if (value == Py_True || value == Py_False) return 0;
    return PyLong_Check(value) || PyFloat_Check(value);
}


static inline int
is_int_value(PyObject *value)
{
    if (value == Py_True || value == Py_False) return 0;
    if (PyLong_Check(value)) return 1;
    if (PyFloat_Check(value)) {
        double d = PyFloat_AS_DOUBLE(value);
        return d == (double)(long long)d;
    }
    return 0;
}


static PyObject *
to_pylong(PyObject *value)
{
    if (PyLong_Check(value)) {
        Py_INCREF(value);
        return value;
    }
    /* float -> int */
    return PyNumber_Long(value);
}


/* Raise BareScriptRuntimeError(script, statement, message) */
static void
set_runtime_error(PyObject *script, PyObject *statement, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    PyObject *message = PyUnicode_FromFormatV(fmt, ap);
    va_end(ap);
    if (message == NULL) return;

    PyObject *script_obj = script ? script : Py_None;
    PyObject *stmt_obj = statement ? statement : Py_None;
    PyObject *exc = PyObject_CallFunctionObjArgs(g_BareScriptRuntimeError, script_obj, stmt_obj, message, NULL);
    Py_DECREF(message);
    if (exc == NULL) return;
    PyErr_SetObject(g_BareScriptRuntimeError, exc);
    Py_DECREF(exc);
}


/* ---------------------------------------------------------------------- */
/* Statement coverage                                                      */
/* ---------------------------------------------------------------------- */

static int
record_statement_coverage(PyObject *script, PyObject *statement, PyObject *statement_key, PyObject *coverage_global)
{
    /* script_name = script.get('scriptName') */
    PyObject *script_name = PyDict_GetItemWithError(script, S_scriptName);
    if (script_name == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    if (script_name == Py_None) return 0;

    /* lineno = statement[statement_key].get('lineNumber') */
    PyObject *inner = PyDict_GetItemWithError(statement, statement_key);
    if (inner == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    if (!PyDict_Check(inner)) return 0;
    PyObject *lineno = PyDict_GetItemWithError(inner, S_lineNumber);
    if (lineno == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    if (lineno == Py_None) return 0;

    /* scripts = coverage_global.get('scripts') */
    PyObject *scripts = PyDict_GetItemWithError(coverage_global, S_scripts);
    if (scripts == NULL) {
        if (PyErr_Occurred()) return -1;
        scripts = PyDict_New();
        if (scripts == NULL) return -1;
        if (PyDict_SetItem(coverage_global, S_scripts, scripts) < 0) {
            Py_DECREF(scripts);
            return -1;
        }
        Py_DECREF(scripts);
    }

    /* script_coverage = scripts.get(script_name) */
    PyObject *script_coverage = PyDict_GetItemWithError(scripts, script_name);
    if (script_coverage == NULL) {
        if (PyErr_Occurred()) return -1;
        script_coverage = PyDict_New();
        if (script_coverage == NULL) return -1;
        PyObject *covered = PyDict_New();
        if (covered == NULL) { Py_DECREF(script_coverage); return -1; }
        if (PyDict_SetItem(script_coverage, S_script, script) < 0 ||
            PyDict_SetItem(script_coverage, S_covered, covered) < 0) {
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
    }

    /* lineno_str = str(lineno) */
    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) return -1;
    PyObject *covered_statements = PyDict_GetItemWithError(script_coverage, S_covered);
    if (covered_statements == NULL) { Py_DECREF(lineno_str); return -1; }

    PyObject *covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
    if (covered_statement == NULL) {
        if (PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
        covered_statement = PyDict_New();
        if (covered_statement == NULL) { Py_DECREF(lineno_str); return -1; }
        PyObject *zero = PyLong_FromLong(0);
        if (zero == NULL ||
            PyDict_SetItem(covered_statement, S_statement, statement) < 0 ||
            PyDict_SetItem(covered_statement, S_count, zero) < 0) {
            Py_XDECREF(zero);
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        Py_DECREF(zero);
        if (PyDict_SetItem(covered_statements, lineno_str, covered_statement) < 0) {
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        Py_DECREF(covered_statement);
        covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
        if (covered_statement == NULL) { Py_DECREF(lineno_str); return -1; }
    }
    Py_DECREF(lineno_str);

    /* covered_statement['count'] += 1 */
    PyObject *cur_count = PyDict_GetItemWithError(covered_statement, S_count);
    if (cur_count == NULL) return -1;
    PyObject *one = PyLong_FromLong(1);
    if (one == NULL) return -1;
    PyObject *new_count = PyNumber_Add(cur_count, one);
    Py_DECREF(one);
    if (new_count == NULL) return -1;
    int rv = PyDict_SetItem(covered_statement, S_count, new_count);
    Py_DECREF(new_count);
    return rv;
}


/* ---------------------------------------------------------------------- */
/* evaluate_expression                                                     */
/* ---------------------------------------------------------------------- */

static PyObject *
c_evaluate_expression(PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
                      PyObject *script, PyObject *statement);


/* Get globals_ from options dict, NULL if options is None/NULL or no globals */
static inline PyObject *
get_globals(PyObject *options)
{
    if (options == NULL || options == Py_None) return NULL;
    return PyDict_GetItemWithError(options, S_globals);
}


/* For binary operators that work on int values, return new ref to PyLong of arg as int.
 * Returns NULL on error AND sets the error. Returns NULL also if value isn't a valid int-value (no err set). */
static PyObject *
ensure_int(PyObject *value)
{
    if (value == Py_True || value == Py_False) return NULL;
    if (PyLong_Check(value)) {
        Py_INCREF(value);
        return value;
    }
    if (PyFloat_Check(value)) {
        double d = PyFloat_AS_DOUBLE(value);
        long long l = (long long)d;
        if ((double)l != d) return NULL;
        return PyLong_FromLongLong(l);
    }
    return NULL;
}


static int
is_datetime(PyObject *value)
{
    return PyObject_IsInstance(value, g_datetime_date_type) == 1;
}


static PyObject *
make_timedelta_ms(double ms)
{
    /* datetime.timedelta(milliseconds=ms) */
    PyObject *kwargs = Py_BuildValue("{s:d}", "milliseconds", ms);
    if (kwargs == NULL) return NULL;
    PyObject *args = PyTuple_New(0);
    if (args == NULL) { Py_DECREF(kwargs); return NULL; }
    PyObject *td = PyObject_Call(g_datetime_timedelta_type, args, kwargs);
    Py_DECREF(args);
    Py_DECREF(kwargs);
    return td;
}


static PyObject *
call_value_string(PyObject *v)
{
    return PyObject_CallOneArg(g_value_string, v);
}


static PyObject *
call_value_compare(PyObject *l, PyObject *r)
{
    return PyObject_CallFunctionObjArgs(g_value_compare, l, r, NULL);
}


static PyObject *
call_value_normalize_datetime(PyObject *v)
{
    return PyObject_CallOneArg(g_value_normalize_datetime, v);
}


static PyObject *
call_value_round_number(PyObject *v, long digits)
{
    PyObject *d = PyLong_FromLong(digits);
    if (d == NULL) return NULL;
    PyObject *r = PyObject_CallFunctionObjArgs(g_value_round_number, v, d, NULL);
    Py_DECREF(d);
    return r;
}


static PyObject *
eval_binary(PyObject *expr_binary, PyObject *options, PyObject *locals_, int builtins,
            PyObject *script, PyObject *statement)
{
    PyObject *bin_op = PyDict_GetItemWithError(expr_binary, S_op);
    if (bin_op == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "op");
        return NULL;
    }
    PyObject *left_expr = PyDict_GetItemWithError(expr_binary, S_left);
    if (left_expr == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "left");
        return NULL;
    }
    PyObject *left_value = c_evaluate_expression(left_expr, options, locals_, builtins, script, statement);
    if (left_value == NULL) return NULL;

    /* Get the op string */
    const char *op = PyUnicode_AsUTF8(bin_op);
    if (op == NULL) { Py_DECREF(left_value); return NULL; }

    /* Short-circuit && and || */
    if (op[0] == '&' && op[1] == '&' && op[2] == '\0') {
        int b = c_value_boolean(left_value);
        if (b < 0) { Py_DECREF(left_value); return NULL; }
        if (!b) return left_value;
        Py_DECREF(left_value);
        PyObject *right_expr = PyDict_GetItemWithError(expr_binary, S_right);
        if (right_expr == NULL) return NULL;
        return c_evaluate_expression(right_expr, options, locals_, builtins, script, statement);
    }
    if (op[0] == '|' && op[1] == '|' && op[2] == '\0') {
        int b = c_value_boolean(left_value);
        if (b < 0) { Py_DECREF(left_value); return NULL; }
        if (b) return left_value;
        Py_DECREF(left_value);
        PyObject *right_expr = PyDict_GetItemWithError(expr_binary, S_right);
        if (right_expr == NULL) return NULL;
        return c_evaluate_expression(right_expr, options, locals_, builtins, script, statement);
    }

    PyObject *right_expr = PyDict_GetItemWithError(expr_binary, S_right);
    if (right_expr == NULL) { Py_DECREF(left_value); return NULL; }
    PyObject *right_value = c_evaluate_expression(right_expr, options, locals_, builtins, script, statement);
    if (right_value == NULL) { Py_DECREF(left_value); return NULL; }

    PyObject *result = NULL;

    if (op[0] == '+' && op[1] == '\0') {
        int ln = is_number(left_value), rn = is_number(right_value);
        if (ln && rn) {
            result = PyNumber_Add(left_value, right_value);
        } else if (PyUnicode_Check(left_value) && PyUnicode_Check(right_value)) {
            result = PyUnicode_Concat(left_value, right_value);
        } else if (PyUnicode_Check(left_value)) {
            PyObject *rs = call_value_string(right_value);
            if (rs != NULL) {
                result = PyUnicode_Concat(left_value, rs);
                Py_DECREF(rs);
            }
        } else if (PyUnicode_Check(right_value)) {
            PyObject *ls = call_value_string(left_value);
            if (ls != NULL) {
                result = PyUnicode_Concat(ls, right_value);
                Py_DECREF(ls);
            }
        } else if (is_datetime(left_value) && rn) {
            PyObject *ldt = call_value_normalize_datetime(left_value);
            if (ldt != NULL) {
                double ms = PyFloat_Check(right_value) ? PyFloat_AS_DOUBLE(right_value) : (double)PyLong_AsLongLong(right_value);
                PyObject *td = make_timedelta_ms(ms);
                if (td != NULL) {
                    result = PyNumber_Add(ldt, td);
                    Py_DECREF(td);
                }
                Py_DECREF(ldt);
            }
        } else if (ln && is_datetime(right_value)) {
            PyObject *rdt = call_value_normalize_datetime(right_value);
            if (rdt != NULL) {
                double ms = PyFloat_Check(left_value) ? PyFloat_AS_DOUBLE(left_value) : (double)PyLong_AsLongLong(left_value);
                PyObject *td = make_timedelta_ms(ms);
                if (td != NULL) {
                    result = PyNumber_Add(rdt, td);
                    Py_DECREF(td);
                }
                Py_DECREF(rdt);
            }
        }
    } else if (op[0] == '-' && op[1] == '\0') {
        int ln = is_number(left_value), rn = is_number(right_value);
        if (ln && rn) {
            result = PyNumber_Subtract(left_value, right_value);
        } else if (is_datetime(left_value) && is_datetime(right_value)) {
            PyObject *ldt = call_value_normalize_datetime(left_value);
            PyObject *rdt = ldt ? call_value_normalize_datetime(right_value) : NULL;
            if (ldt && rdt) {
                PyObject *diff = PyNumber_Subtract(ldt, rdt);
                if (diff != NULL) {
                    PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                    Py_DECREF(diff);
                    if (secs != NULL) {
                        double sd = PyFloat_AsDouble(secs);
                        Py_DECREF(secs);
                        if (!PyErr_Occurred()) {
                            PyObject *ms = PyFloat_FromDouble(sd * 1000.0);
                            if (ms != NULL) {
                                result = call_value_round_number(ms, 0);
                                Py_DECREF(ms);
                            }
                        }
                    }
                }
            }
            Py_XDECREF(ldt);
            Py_XDECREF(rdt);
        }
    } else if (op[0] == '*' && op[1] == '\0') {
        if (is_number(left_value) && is_number(right_value)) {
            result = PyNumber_Multiply(left_value, right_value);
        }
    } else if (op[0] == '/' && op[1] == '\0') {
        if (is_number(left_value) && is_number(right_value)) {
            result = PyNumber_TrueDivide(left_value, right_value);
        }
    } else if (op[0] == '=' && op[1] == '=' && op[2] == '\0') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp != NULL) {
            long c = PyLong_AsLong(cmp);
            Py_DECREF(cmp);
            if (c != -1 || !PyErr_Occurred()) {
                result = c == 0 ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
    } else if (op[0] == '!' && op[1] == '=' && op[2] == '\0') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp != NULL) {
            long c = PyLong_AsLong(cmp);
            Py_DECREF(cmp);
            if (c != -1 || !PyErr_Occurred()) {
                result = c != 0 ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
    } else if (op[0] == '<' && op[1] == '=' && op[2] == '\0') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp != NULL) {
            long c = PyLong_AsLong(cmp);
            Py_DECREF(cmp);
            if (c != -1 || !PyErr_Occurred()) {
                result = c <= 0 ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
    } else if (op[0] == '<' && op[1] == '\0') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp != NULL) {
            long c = PyLong_AsLong(cmp);
            Py_DECREF(cmp);
            if (c != -1 || !PyErr_Occurred()) {
                result = c < 0 ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
    } else if (op[0] == '>' && op[1] == '=' && op[2] == '\0') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp != NULL) {
            long c = PyLong_AsLong(cmp);
            Py_DECREF(cmp);
            if (c != -1 || !PyErr_Occurred()) {
                result = c >= 0 ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
    } else if (op[0] == '>' && op[1] == '\0') {
        PyObject *cmp = call_value_compare(left_value, right_value);
        if (cmp != NULL) {
            long c = PyLong_AsLong(cmp);
            Py_DECREF(cmp);
            if (c != -1 || !PyErr_Occurred()) {
                result = c > 0 ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
    } else if (op[0] == '%' && op[1] == '\0') {
        if (is_number(left_value) && is_number(right_value)) {
            result = PyNumber_Remainder(left_value, right_value);
        }
    } else if (op[0] == '*' && op[1] == '*' && op[2] == '\0') {
        if (is_number(left_value) && is_number(right_value)) {
            result = PyNumber_Power(left_value, right_value, Py_None);
        }
    } else if (op[0] == '&' && op[1] == '\0') {
        PyObject *li = ensure_int(left_value), *ri = li ? ensure_int(right_value) : NULL;
        if (li && ri) result = PyNumber_And(li, ri);
        Py_XDECREF(li); Py_XDECREF(ri);
    } else if (op[0] == '|' && op[1] == '\0') {
        PyObject *li = ensure_int(left_value), *ri = li ? ensure_int(right_value) : NULL;
        if (li && ri) result = PyNumber_Or(li, ri);
        Py_XDECREF(li); Py_XDECREF(ri);
    } else if (op[0] == '^' && op[1] == '\0') {
        PyObject *li = ensure_int(left_value), *ri = li ? ensure_int(right_value) : NULL;
        if (li && ri) result = PyNumber_Xor(li, ri);
        Py_XDECREF(li); Py_XDECREF(ri);
    } else if (op[0] == '<' && op[1] == '<' && op[2] == '\0') {
        PyObject *li = ensure_int(left_value), *ri = li ? ensure_int(right_value) : NULL;
        if (li && ri) result = PyNumber_Lshift(li, ri);
        Py_XDECREF(li); Py_XDECREF(ri);
    } else if (op[0] == '>' && op[1] == '>' && op[2] == '\0') {
        PyObject *li = ensure_int(left_value), *ri = li ? ensure_int(right_value) : NULL;
        if (li && ri) result = PyNumber_Rshift(li, ri);
        Py_XDECREF(li); Py_XDECREF(ri);
    }

    Py_DECREF(left_value);
    Py_DECREF(right_value);

    if (result == NULL && !PyErr_Occurred()) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return result;
}


static PyObject *
eval_unary(PyObject *expr_unary, PyObject *options, PyObject *locals_, int builtins,
           PyObject *script, PyObject *statement)
{
    PyObject *unary_op = PyDict_GetItemWithError(expr_unary, S_op);
    if (unary_op == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "op");
        return NULL;
    }
    PyObject *value_expr = PyDict_GetItemWithError(expr_unary, S_expr);
    if (value_expr == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "expr");
        return NULL;
    }
    PyObject *value = c_evaluate_expression(value_expr, options, locals_, builtins, script, statement);
    if (value == NULL) return NULL;

    const char *op = PyUnicode_AsUTF8(unary_op);
    if (op == NULL) { Py_DECREF(value); return NULL; }

    PyObject *result = NULL;
    if (op[0] == '!' && op[1] == '\0') {
        int b = c_value_boolean(value);
        if (b >= 0) {
            result = b ? Py_False : Py_True;
            Py_INCREF(result);
        }
    } else if (op[0] == '-' && op[1] == '\0') {
        if (is_number(value)) {
            result = PyNumber_Negative(value);
        }
    } else { /* '~' */
        PyObject *iv = ensure_int(value);
        if (iv != NULL) {
            result = PyNumber_Invert(iv);
            Py_DECREF(iv);
        }
    }

    Py_DECREF(value);
    if (result == NULL && !PyErr_Occurred()) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return result;
}


static PyObject *
eval_function(PyObject *expr_function, PyObject *options, PyObject *locals_, int builtins,
              PyObject *script, PyObject *statement)
{
    PyObject *globals_ = get_globals(options);

    PyObject *func_name = PyDict_GetItemWithError(expr_function, S_name);
    if (func_name == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "name");
        return NULL;
    }

    /* "if" built-in */
    if (PyUnicode_Check(func_name) && PyUnicode_Compare(func_name, S_if_str) == 0) {
        PyObject *args_expr = PyDict_GetItemWithError(expr_function, S_args);
        if (args_expr == NULL && PyErr_Occurred()) return NULL;
        PyObject *value_expr = NULL, *true_expr = NULL, *false_expr = NULL;
        if (args_expr != NULL && PyList_Check(args_expr)) {
            Py_ssize_t n = PyList_GET_SIZE(args_expr);
            if (n >= 1) value_expr = PyList_GET_ITEM(args_expr, 0);
            if (n >= 2) true_expr = PyList_GET_ITEM(args_expr, 1);
            if (n >= 3) false_expr = PyList_GET_ITEM(args_expr, 2);
        }
        PyObject *value;
        if (value_expr != NULL) {
            value = c_evaluate_expression(value_expr, options, locals_, builtins, script, statement);
            if (value == NULL) return NULL;
        } else {
            value = Py_False;
            Py_INCREF(value);
        }
        int b = c_value_boolean(value);
        Py_DECREF(value);
        if (b < 0) return NULL;
        PyObject *result_expr = b ? true_expr : false_expr;
        if (result_expr == NULL) {
            Py_INCREF(Py_None);
            return Py_None;
        }
        return c_evaluate_expression(result_expr, options, locals_, builtins, script, statement);
    }

    /* Compute the function arguments */
    PyObject *func_args = NULL;
    int has_args = PyDict_Contains(expr_function, S_args);
    if (has_args < 0) return NULL;
    if (has_args) {
        PyObject *args_expr = PyDict_GetItemWithError(expr_function, S_args);
        if (args_expr == NULL) return NULL;
        Py_ssize_t n = PyList_Check(args_expr) ? PyList_GET_SIZE(args_expr) : PyObject_Length(args_expr);
        if (n < 0) return NULL;
        func_args = PyList_New(n);
        if (func_args == NULL) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *arg_expr = PyList_Check(args_expr) ? PyList_GET_ITEM(args_expr, i) : PySequence_GetItem(args_expr, i);
            PyObject *arg_value = c_evaluate_expression(arg_expr, options, locals_, builtins, script, statement);
            if (!PyList_Check(args_expr)) Py_DECREF(arg_expr);
            if (arg_value == NULL) {
                Py_DECREF(func_args);
                return NULL;
            }
            PyList_SET_ITEM(func_args, i, arg_value);
        }
    }

    /* Find the function value */
    PyObject *func_value = NULL;
    if (locals_ != NULL && locals_ != Py_None) {
        func_value = PyDict_GetItemWithError(locals_, func_name);
        if (func_value == NULL && PyErr_Occurred()) {
            Py_XDECREF(func_args);
            return NULL;
        }
    }
    if (func_value == NULL && globals_ != NULL) {
        func_value = PyDict_GetItemWithError(globals_, func_name);
        if (func_value == NULL && PyErr_Occurred()) {
            Py_XDECREF(func_args);
            return NULL;
        }
    }
    if (func_value == NULL && builtins) {
        func_value = PyDict_GetItemWithError(g_EXPRESSION_FUNCTIONS, func_name);
        if (func_value == NULL && PyErr_Occurred()) {
            Py_XDECREF(func_args);
            return NULL;
        }
    }

    if (func_value != NULL) {
        Py_INCREF(func_value);
        if (func_args == NULL) {
            Py_INCREF(Py_None);
            func_args = Py_None;
        }
        PyObject *options_arg = options ? options : Py_None;
        PyObject *result = PyObject_CallFunctionObjArgs(func_value, func_args, options_arg, NULL);
        Py_DECREF(func_value);
        Py_DECREF(func_args);
        if (result != NULL) return result;

        /* Handle exception */
        PyObject *exc_type, *exc_value, *exc_tb;
        PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
        PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);
        if (exc_type != NULL && PyErr_GivenExceptionMatches(exc_type, g_BareScriptRuntimeError)) {
            PyErr_Restore(exc_type, exc_value, exc_tb);
            return NULL;
        }
        /* Optionally log */
        if (options != NULL && options != Py_None) {
            PyObject *debug = PyDict_GetItemWithError(options, S_debug);
            if (debug == NULL && PyErr_Occurred()) {
                Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                return NULL;
            }
            int dbg = debug ? PyObject_IsTrue(debug) : 0;
            if (dbg > 0) {
                PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
                if (log_fn == NULL && PyErr_Occurred()) {
                    Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                    return NULL;
                }
                if (log_fn != NULL) {
                    PyObject *msg = PyUnicode_FromFormat("BareScript: Function \"%U\" failed with error: %S",
                                                        func_name, exc_value ? exc_value : Py_None);
                    if (msg != NULL) {
                        PyObject *log_result = PyObject_CallOneArg(log_fn, msg);
                        Py_XDECREF(log_result);
                        Py_DECREF(msg);
                    }
                }
            }
        }
        /* Check ValueArgsError */
        if (exc_type != NULL && g_ValueArgsError != NULL &&
            PyErr_GivenExceptionMatches(exc_type, g_ValueArgsError)) {
            PyObject *rv = PyObject_GetAttrString(exc_value, "return_value");
            Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
            return rv;
        }
        Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
        Py_INCREF(Py_None);
        return Py_None;
    }

    Py_XDECREF(func_args);
    set_runtime_error(script, statement, "Undefined function \"%U\"", func_name);
    return NULL;
}


static PyObject *
c_evaluate_expression(PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
                      PyObject *script, PyObject *statement)
{
    /* Probe each AST key directly; the dict has exactly one. Ordered by frequency. */
    PyObject *v;

    /* variable */
    v = PyDict_GetItemWithError(expr, S_variable);
    if (v != NULL) {
        /* Keywords (parser interns short ASCII strings so identity usually matches) */
        if (v == S_null_str) { Py_INCREF(Py_None); return Py_None; }
        if (v == S_false_str) { Py_INCREF(Py_False); return Py_False; }
        if (v == S_true_str) { Py_INCREF(Py_True); return Py_True; }
        if (PyUnicode_Check(v) && PyUnicode_GET_LENGTH(v) <= 5) {
            if (PyUnicode_Compare(v, S_null_str) == 0) { Py_INCREF(Py_None); return Py_None; }
            if (PyErr_Occurred()) return NULL;
            if (PyUnicode_Compare(v, S_false_str) == 0) { Py_INCREF(Py_False); return Py_False; }
            if (PyErr_Occurred()) return NULL;
            if (PyUnicode_Compare(v, S_true_str) == 0) { Py_INCREF(Py_True); return Py_True; }
            if (PyErr_Occurred()) return NULL;
        }
        if (locals_ != NULL) {
            PyObject *lv = PyDict_GetItemWithError(locals_, v);
            if (lv != NULL) { Py_INCREF(lv); return lv; }
            if (PyErr_Occurred()) return NULL;
        }
        PyObject *globals_ = get_globals(options);
        if (globals_ != NULL) {
            PyObject *gv = PyDict_GetItemWithError(globals_, v);
            if (gv != NULL) { Py_INCREF(gv); return gv; }
            if (PyErr_Occurred()) return NULL;
        }
        Py_INCREF(Py_None);
        return Py_None;
    }
    if (PyErr_Occurred()) return NULL;

    /* function */
    v = PyDict_GetItemWithError(expr, S_function);
    if (v != NULL) {
        return eval_function(v, options, locals_, builtins, script, statement);
    }
    if (PyErr_Occurred()) return NULL;

    /* binary */
    v = PyDict_GetItemWithError(expr, S_binary);
    if (v != NULL) {
        return eval_binary(v, options, locals_, builtins, script, statement);
    }
    if (PyErr_Occurred()) return NULL;

    /* number */
    v = PyDict_GetItemWithError(expr, S_number);
    if (v != NULL) {
        Py_INCREF(v);
        return v;
    }
    if (PyErr_Occurred()) return NULL;

    /* string */
    v = PyDict_GetItemWithError(expr, S_string);
    if (v != NULL) {
        Py_INCREF(v);
        return v;
    }
    if (PyErr_Occurred()) return NULL;

    /* unary */
    v = PyDict_GetItemWithError(expr, S_unary);
    if (v != NULL) {
        return eval_unary(v, options, locals_, builtins, script, statement);
    }
    if (PyErr_Occurred()) return NULL;

    /* group */
    v = PyDict_GetItemWithError(expr, S_group);
    if (v != NULL) {
        return c_evaluate_expression(v, options, locals_, builtins, script, statement);
    }
    if (PyErr_Occurred()) return NULL;

    PyErr_SetString(PyExc_ValueError, "unknown expression kind");
    return NULL;
}


/* ---------------------------------------------------------------------- */
/* execute_script helper                                                   */
/* ---------------------------------------------------------------------- */

static PyObject *
exec_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_)
{
    if (!PyList_Check(statements)) {
        PyErr_SetString(PyExc_TypeError, "statements must be a list");
        return NULL;
    }
    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "globals");
        return NULL;
    }

    /* Hoist statementCount and maxStatements into C locals; sync back when needed. */
    long long count_val;
    {
        PyObject *cur_count = PyDict_GetItemWithError(options, S_statementCount);
        if (cur_count == NULL) {
            if (PyErr_Occurred()) return NULL;
            count_val = 0;
        } else {
            count_val = PyLong_AsLongLong(cur_count);
            if (count_val == -1 && PyErr_Occurred()) return NULL;
        }
    }
    long long max_stmts;
    {
        PyObject *max_obj = PyDict_GetItemWithError(options, S_maxStatements);
        if (max_obj == NULL) {
            if (PyErr_Occurred()) return NULL;
            max_stmts = DEFAULT_MAX_STATEMENTS;
        } else if (PyLong_Check(max_obj)) {
            max_stmts = PyLong_AsLongLong(max_obj);
            if (max_stmts == -1 && PyErr_Occurred()) return NULL;
        } else {
            double d = PyFloat_AsDouble(max_obj);
            if (d == -1.0 && PyErr_Occurred()) return NULL;
            max_stmts = (long long)d;
        }
    }

    /* Coverage cache. Recompute when execute_script enters/leaves or after include. */
    PyObject *coverage_global = PyDict_GetItemWithError(globals_, S_SYSTEM_GLOBAL_COVERAGE);
    if (coverage_global == NULL && PyErr_Occurred()) return NULL;
    int has_coverage = 0;
    if (coverage_global != NULL && coverage_global != Py_None && PyDict_Check(coverage_global)) {
        PyObject *enabled = PyDict_GetItemWithError(coverage_global, S_enabled);
        if (enabled == NULL && PyErr_Occurred()) return NULL;
        int en = enabled ? PyObject_IsTrue(enabled) : 0;
        if (en < 0) return NULL;
        if (en) {
            PyObject *system_v = PyDict_GetItemWithError(script, S_system);
            if (system_v == NULL && PyErr_Occurred()) return NULL;
            int sys_v = system_v ? PyObject_IsTrue(system_v) : 0;
            if (sys_v < 0) return NULL;
            has_coverage = !sys_v;
        }
    }

    PyObject *label_indexes = NULL;
    Py_ssize_t statements_length = PyList_GET_SIZE(statements);
    Py_ssize_t ix_statement = 0;
    PyObject *result = NULL;

#define CLEANUP_AND_RETURN(val) do { \
    PyObject *_v = PyLong_FromLongLong(count_val); \
    if (_v != NULL) { PyDict_SetItem(options, S_statementCount, _v); Py_DECREF(_v); } \
    Py_XDECREF(label_indexes); \
    result = (val); \
    goto done; \
} while (0)

#define ABORT() do { \
    PyObject *_v = PyLong_FromLongLong(count_val); \
    if (_v != NULL) { PyDict_SetItem(options, S_statementCount, _v); Py_DECREF(_v); } \
    Py_XDECREF(label_indexes); \
    return NULL; \
} while (0)

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_GET_ITEM(statements, ix_statement);

        /* Increment + check */
        count_val++;
        if (max_stmts > 0 && count_val > max_stmts) {
            /* Write back before raising */
            PyObject *cv = PyLong_FromLongLong(count_val);
            if (cv != NULL) { PyDict_SetItem(options, S_statementCount, cv); Py_DECREF(cv); }
            set_runtime_error(script, statement, "Exceeded maximum script statements (%lld)", max_stmts);
            Py_XDECREF(label_indexes);
            return NULL;
        }

        /* Dispatch by probing keys directly. Most common: expr, jump, label */
        PyObject *expr_obj = PyDict_GetItemWithError(statement, S_expr);
        if (expr_obj != NULL) {
            if (has_coverage) {
                if (record_statement_coverage(script, statement, S_expr, coverage_global) < 0) ABORT();
            }
            PyObject *inner_expr = PyDict_GetItemWithError(expr_obj, S_expr);
            if (inner_expr == NULL) {
                if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "expr");
                ABORT();
            }
            PyObject *value = c_evaluate_expression(inner_expr, options, locals_, 0, script, statement);
            if (value == NULL) ABORT();
            PyObject *name = PyDict_GetItemWithError(expr_obj, S_name);
            if (name == NULL && PyErr_Occurred()) { Py_DECREF(value); ABORT(); }
            if (name != NULL) {
                PyObject *target = (locals_ != NULL) ? locals_ : globals_;
                if (PyDict_SetItem(target, name, value) < 0) { Py_DECREF(value); ABORT(); }
            }
            Py_DECREF(value);
            ix_statement++;
            continue;
        }
        if (PyErr_Occurred()) ABORT();

        /* jump */
        {
            PyObject *jump_obj = PyDict_GetItemWithError(statement, S_jump);
            if (jump_obj != NULL) {
                if (has_coverage) {
                    if (record_statement_coverage(script, statement, S_jump, coverage_global) < 0) ABORT();
                }
                int do_jump = 1;
                PyObject *cond_expr = PyDict_GetItemWithError(jump_obj, S_expr);
                if (cond_expr == NULL && PyErr_Occurred()) ABORT();
                if (cond_expr != NULL) {
                    PyObject *cond_val = c_evaluate_expression(cond_expr, options, locals_, 0, script, statement);
                    if (cond_val == NULL) ABORT();
                    int b = c_value_boolean(cond_val);
                    Py_DECREF(cond_val);
                    if (b < 0) ABORT();
                    do_jump = b;
                }
                if (do_jump) {
                    PyObject *label_name = PyDict_GetItemWithError(jump_obj, S_label);
                    if (label_name == NULL) {
                        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "label");
                        ABORT();
                    }
                    Py_ssize_t ix_label = -1;
                    if (label_indexes != NULL) {
                        PyObject *cached = PyDict_GetItemWithError(label_indexes, label_name);
                        if (cached == NULL && PyErr_Occurred()) ABORT();
                        if (cached != NULL) {
                            ix_label = PyLong_AsSsize_t(cached);
                            if (ix_label == -1 && PyErr_Occurred()) ABORT();
                        }
                    }
                    if (ix_label == -1) {
                        for (Py_ssize_t i = 0; i < statements_length; i++) {
                            PyObject *st = PyList_GET_ITEM(statements, i);
                            PyObject *lbl_obj = PyDict_GetItemWithError(st, S_label);
                            if (lbl_obj == NULL) {
                                if (PyErr_Occurred()) ABORT();
                                continue;
                            }
                            PyObject *lbl_name = PyDict_GetItemWithError(lbl_obj, S_name);
                            if (lbl_name == NULL) {
                                if (PyErr_Occurred()) ABORT();
                                continue;
                            }
                            if (PyObject_RichCompareBool(lbl_name, label_name, Py_EQ) == 1) {
                                ix_label = i;
                                break;
                            }
                        }
                        if (ix_label == -1) {
                            set_runtime_error(script, statement, "Unknown jump label \"%U\"", label_name);
                            ABORT();
                        }
                        if (label_indexes == NULL) {
                            label_indexes = PyDict_New();
                            if (label_indexes == NULL) ABORT();
                        }
                        PyObject *ix_obj = PyLong_FromSsize_t(ix_label);
                        if (ix_obj == NULL) ABORT();
                        if (PyDict_SetItem(label_indexes, label_name, ix_obj) < 0) {
                            Py_DECREF(ix_obj); ABORT();
                        }
                        Py_DECREF(ix_obj);
                    }
                    ix_statement = ix_label;
                    if (has_coverage) {
                        PyObject *label_statement = PyList_GET_ITEM(statements, ix_statement);
                        /* Determine which key the label statement has and record it */
                        PyObject *probe;
                        probe = PyDict_GetItemWithError(label_statement, S_label);
                        if (probe != NULL) {
                            if (record_statement_coverage(script, label_statement, S_label, coverage_global) < 0) ABORT();
                        } else if (PyErr_Occurred()) {
                            ABORT();
                        } else {
                            probe = PyDict_GetItemWithError(label_statement, S_expr);
                            if (probe != NULL) {
                                if (record_statement_coverage(script, label_statement, S_expr, coverage_global) < 0) ABORT();
                            } else if (PyErr_Occurred()) {
                                ABORT();
                            } else {
                                probe = PyDict_GetItemWithError(label_statement, S_jump);
                                if (probe != NULL) {
                                    if (record_statement_coverage(script, label_statement, S_jump, coverage_global) < 0) ABORT();
                                } else if (PyErr_Occurred()) {
                                    ABORT();
                                }
                            }
                        }
                    }
                }
                ix_statement++;
                continue;
            }
            if (PyErr_Occurred()) ABORT();
        }

        /* label */
        {
            PyObject *label_obj = PyDict_GetItemWithError(statement, S_label);
            if (label_obj != NULL) {
                if (has_coverage) {
                    if (record_statement_coverage(script, statement, S_label, coverage_global) < 0) ABORT();
                }
                ix_statement++;
                continue;
            }
            if (PyErr_Occurred()) ABORT();
        }

        /* return */
        {
            PyObject *ret_obj = PyDict_GetItemWithError(statement, S_return);
            if (ret_obj != NULL) {
                if (has_coverage) {
                    if (record_statement_coverage(script, statement, S_return, coverage_global) < 0) ABORT();
                }
                /* sync count_val back */
                PyObject *cv = PyLong_FromLongLong(count_val);
                if (cv != NULL) { PyDict_SetItem(options, S_statementCount, cv); Py_DECREF(cv); }
                Py_XDECREF(label_indexes);
                PyObject *e = PyDict_GetItemWithError(ret_obj, S_expr);
                if (e == NULL && PyErr_Occurred()) return NULL;
                if (e != NULL) {
                    return c_evaluate_expression(e, options, locals_, 0, script, statement);
                }
                Py_INCREF(Py_None);
                return Py_None;
            }
            if (PyErr_Occurred()) ABORT();
        }

        /* function */
        {
            PyObject *fn_obj = PyDict_GetItemWithError(statement, S_function);
            if (fn_obj != NULL) {
                if (has_coverage) {
                    if (record_statement_coverage(script, statement, S_function, coverage_global) < 0) ABORT();
                }
                PyObject *name = PyDict_GetItemWithError(fn_obj, S_name);
                if (name == NULL) {
                    if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "name");
                    ABORT();
                }
                PyObject *sf = make_script_function(script, fn_obj);
                if (sf == NULL) ABORT();
                if (PyDict_SetItem(globals_, name, sf) < 0) { Py_DECREF(sf); ABORT(); }
                Py_DECREF(sf);
                ix_statement++;
                continue;
            }
            if (PyErr_Occurred()) ABORT();
        }

        /* include */
        {
            PyObject *inc_obj = PyDict_GetItemWithError(statement, S_include);
            if (inc_obj == NULL) {
                if (PyErr_Occurred()) ABORT();
                /* Unknown key — skip */
                ix_statement++;
                continue;
            }
            if (has_coverage) {
                if (record_statement_coverage(script, statement, S_include, coverage_global) < 0) ABORT();
            }
            PyObject *system_prefix = PyDict_GetItemWithError(options, S_systemPrefix);
            if (system_prefix == NULL && PyErr_Occurred()) ABORT();
            PyObject *fetch_fn = PyDict_GetItemWithError(options, S_fetchFn);
            if (fetch_fn == NULL && PyErr_Occurred()) ABORT();
            PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
            if (log_fn == NULL && PyErr_Occurred()) ABORT();
            PyObject *url_fn = PyDict_GetItemWithError(options, S_urlFn);
            if (url_fn == NULL && PyErr_Occurred()) ABORT();

            PyObject *includes_list = PyDict_GetItemWithError(inc_obj, S_includes);
            if (includes_list == NULL) {
                if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "includes");
                ABORT();
            }
            Py_ssize_t ninc = PyList_GET_SIZE(includes_list);
            for (Py_ssize_t i = 0; i < ninc; i++) {
                PyObject *include = PyList_GET_ITEM(includes_list, i);
                PyObject *include_url = PyDict_GetItemWithError(include, S_url);
                if (include_url == NULL) {
                    if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "url");
                    ABORT();
                }
                Py_INCREF(include_url);

                PyObject *system_include = PyDict_GetItemWithError(include, S_system);
                if (system_include == NULL && PyErr_Occurred()) {
                    Py_DECREF(include_url); ABORT();
                }
                int sys_v = system_include ? PyObject_IsTrue(system_include) : 0;
                if (sys_v < 0) { Py_DECREF(include_url); ABORT(); }

                if (sys_v && system_prefix != NULL) {
                    PyObject *new_url = PyObject_CallFunctionObjArgs(g_url_file_relative, system_prefix, include_url, NULL);
                    Py_DECREF(include_url);
                    if (new_url == NULL) ABORT();
                    include_url = new_url;
                } else if (url_fn != NULL) {
                    PyObject *new_url = PyObject_CallOneArg(url_fn, include_url);
                    Py_DECREF(include_url);
                    if (new_url == NULL) ABORT();
                    include_url = new_url;
                }

                /* global_includes management */
                PyObject *global_includes = PyDict_GetItemWithError(globals_, S_SYSTEM_GLOBAL_INCLUDES);
                if (global_includes == NULL && PyErr_Occurred()) { Py_DECREF(include_url); ABORT(); }
                if (global_includes == NULL || !PyDict_Check(global_includes)) {
                    global_includes = PyDict_New();
                    if (global_includes == NULL) { Py_DECREF(include_url); ABORT(); }
                    if (PyDict_SetItem(globals_, S_SYSTEM_GLOBAL_INCLUDES, global_includes) < 0) {
                        Py_DECREF(global_includes); Py_DECREF(include_url); ABORT();
                    }
                    Py_DECREF(global_includes);
                    global_includes = PyDict_GetItemWithError(globals_, S_SYSTEM_GLOBAL_INCLUDES);
                }

                PyObject *already = PyDict_GetItemWithError(global_includes, include_url);
                if (already == NULL && PyErr_Occurred()) { Py_DECREF(include_url); ABORT(); }
                int already_v = already ? PyObject_IsTrue(already) : 0;
                if (already_v) {
                    Py_DECREF(include_url);
                    continue;
                }
                if (PyDict_SetItem(global_includes, include_url, Py_True) < 0) {
                    Py_DECREF(include_url); ABORT();
                }

                /* Fetch */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *req = PyDict_New();
                    if (req == NULL) { Py_DECREF(include_url); ABORT(); }
                    if (PyDict_SetItem(req, S_url, include_url) < 0) {
                        Py_DECREF(req); Py_DECREF(include_url); ABORT();
                    }
                    include_text = PyObject_CallOneArg(fetch_fn, req);
                    Py_DECREF(req);
                    if (include_text == NULL) {
                        PyErr_Clear();
                    }
                }
                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    set_runtime_error(script, statement, "Include of \"%U\" failed", include_url);
                    Py_DECREF(include_url); ABORT();
                }

                /* parse_script(include_text, 1, include_url) */
                PyObject *one_obj = PyLong_FromLong(1);
                PyObject *include_script = PyObject_CallFunctionObjArgs(g_parse_script, include_text, one_obj, include_url, NULL);
                Py_XDECREF(one_obj);
                Py_DECREF(include_text);
                if (include_script == NULL) { Py_DECREF(include_url); ABORT(); }
                if (sys_v) {
                    if (PyDict_SetItem(include_script, S_system, Py_True) < 0) {
                        Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                    }
                }

                /* Build include_options = options.copy(); urlFn = partial(url_file_relative, include_url) */
                PyObject *include_options = PyDict_Copy(options);
                if (include_options == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                }
                PyObject *partial = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, include_url, NULL);
                if (partial == NULL) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                }
                if (PyDict_SetItem(include_options, S_urlFn, partial) < 0) {
                    Py_DECREF(partial); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                }
                Py_DECREF(partial);

                /* Execute include script */
                PyObject *inc_stmts = PyDict_GetItemWithError(include_script, S_statements);
                if (inc_stmts == NULL) {
                    if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                }
                PyObject *inc_result = exec_script_helper(include_script, inc_stmts, include_options, NULL);
                if (inc_result == NULL) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                }
                Py_DECREF(inc_result);

                /* Lint if debug */
                if (log_fn != NULL) {
                    PyObject *debug = PyDict_GetItemWithError(options, S_debug);
                    if (debug == NULL && PyErr_Occurred()) {
                        Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                    }
                    int dbg = debug ? PyObject_IsTrue(debug) : 0;
                    if (dbg > 0) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(g_lint_script, include_script, globals_, NULL);
                        if (warnings == NULL) {
                            Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); ABORT();
                        }
                        Py_ssize_t nw = PyObject_Length(warnings);
                        if (nw > 0) {
                            PyObject *prefix_msg = PyUnicode_FromFormat(
                                "BareScript: Include \"%U\" static analysis... %zd warning%s:",
                                include_url, nw, nw > 1 ? "s" : "");
                            if (prefix_msg != NULL) {
                                PyObject *r1 = PyObject_CallOneArg(log_fn, prefix_msg);
                                Py_XDECREF(r1);
                                Py_DECREF(prefix_msg);
                            }
                            PyObject *iter = PyObject_GetIter(warnings);
                            if (iter != NULL) {
                                PyObject *w;
                                while ((w = PyIter_Next(iter)) != NULL) {
                                    PyObject *m = PyUnicode_FromFormat("BareScript: %S", w);
                                    if (m != NULL) {
                                        PyObject *r2 = PyObject_CallOneArg(log_fn, m);
                                        Py_XDECREF(r2);
                                        Py_DECREF(m);
                                    }
                                    Py_DECREF(w);
                                }
                                Py_DECREF(iter);
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }

                Py_DECREF(include_options);
                Py_DECREF(include_script);
                Py_DECREF(include_url);
            }

            /* Recompute coverage cache; included script may have modified globals/script.system. */
            coverage_global = PyDict_GetItemWithError(globals_, S_SYSTEM_GLOBAL_COVERAGE);
            if (coverage_global == NULL && PyErr_Occurred()) ABORT();
            has_coverage = 0;
            if (coverage_global != NULL && coverage_global != Py_None && PyDict_Check(coverage_global)) {
                PyObject *enabled = PyDict_GetItemWithError(coverage_global, S_enabled);
                if (enabled == NULL && PyErr_Occurred()) ABORT();
                int en = enabled ? PyObject_IsTrue(enabled) : 0;
                if (en < 0) ABORT();
                if (en) {
                    PyObject *system_v = PyDict_GetItemWithError(script, S_system);
                    if (system_v == NULL && PyErr_Occurred()) ABORT();
                    int sys_v = system_v ? PyObject_IsTrue(system_v) : 0;
                    if (sys_v < 0) ABORT();
                    has_coverage = !sys_v;
                }
            }
        }

        ix_statement++;
    }

    Py_INCREF(Py_None);
    result = Py_None;
    goto done;

done:
    {
        PyObject *cv = PyLong_FromLongLong(count_val);
        if (cv != NULL) { PyDict_SetItem(options, S_statementCount, cv); Py_DECREF(cv); }
    }
    Py_XDECREF(label_indexes);
    return result;

#undef ABORT
#undef CLEANUP_AND_RETURN
}


/* ---------------------------------------------------------------------- */
/* Public API                                                              */
/* ---------------------------------------------------------------------- */

static PyObject *
py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script;
    PyObject *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &script, &options)) {
        return NULL;
    }
    if (options == Py_None) {
        options = PyDict_New();
        if (options == NULL) return NULL;
    } else {
        Py_INCREF(options);
    }
    /* Ensure 'globals' */
    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL && PyErr_Occurred()) { Py_DECREF(options); return NULL; }
    if (globals_ == NULL || globals_ == Py_None) {
        globals_ = PyDict_New();
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, S_globals, globals_) < 0) {
            Py_DECREF(globals_); Py_DECREF(options); return NULL;
        }
        Py_DECREF(globals_);
        globals_ = PyDict_GetItemWithError(options, S_globals);
    }

    /* globals_.update(name_func for name_func in SCRIPT_FUNCTIONS.items() if name_func[0] not in globals_) */
    Py_ssize_t pos = 0;
    PyObject *key, *value;
    while (PyDict_Next(g_SCRIPT_FUNCTIONS, &pos, &key, &value)) {
        int has = PyDict_Contains(globals_, key);
        if (has < 0) { Py_DECREF(options); return NULL; }
        if (!has) {
            if (PyDict_SetItem(globals_, key, value) < 0) {
                Py_DECREF(options); return NULL;
            }
        }
    }

    /* statementCount = 0 */
    PyObject *zero = PyLong_FromLong(0);
    if (zero == NULL) { Py_DECREF(options); return NULL; }
    if (PyDict_SetItem(options, S_statementCount, zero) < 0) {
        Py_DECREF(zero); Py_DECREF(options); return NULL;
    }
    Py_DECREF(zero);

    PyObject *statements = PyDict_GetItemWithError(script, S_statements);
    if (statements == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
        Py_DECREF(options);
        return NULL;
    }
    PyObject *result = exec_script_helper(script, statements, options, NULL);
    Py_DECREF(options);
    return result;
}


static PyObject *
py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr;
    PyObject *options = Py_None;
    PyObject *locals_ = Py_None;
    PyObject *builtins_obj = Py_True;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOOOO", kwlist,
                                     &expr, &options, &locals_, &builtins_obj, &script, &statement)) {
        return NULL;
    }
    int builtins = PyObject_IsTrue(builtins_obj);
    if (builtins < 0) return NULL;
    PyObject *opts = (options == Py_None) ? NULL : options;
    PyObject *locs = (locals_ == Py_None) ? NULL : locals_;
    PyObject *scr = (script == Py_None) ? NULL : script;
    PyObject *stm = (statement == Py_None) ? NULL : statement;
    return c_evaluate_expression(expr, opts, locs, builtins, scr, stm);
}


/* ---------------------------------------------------------------------- */
/* Module init                                                             */
/* ---------------------------------------------------------------------- */

static PyMethodDef methods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS, "Execute a BareScript model"},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS, "Evaluate an expression model"},
    {NULL, NULL, 0, NULL}
};


static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "bare_script.runtime_c",
    NULL,
    -1,
    methods,
};


#define INTERN(var, s) do { var = PyUnicode_InternFromString(s); if (var == NULL) return NULL; } while (0)


static PyObject *
import_attr(const char *module_name, const char *attr_name)
{
    PyObject *mod = PyImport_ImportModule(module_name);
    if (mod == NULL) return NULL;
    PyObject *attr = PyObject_GetAttrString(mod, attr_name);
    Py_DECREF(mod);
    return attr;
}


PyMODINIT_FUNC
PyInit_runtime_c(void)
{
    if (PyType_Ready(&ScriptFunctionType) < 0) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (m == NULL) return NULL;

    /* Cache module references */
    g_EXPRESSION_FUNCTIONS = import_attr("bare_script.library", "EXPRESSION_FUNCTIONS");
    if (g_EXPRESSION_FUNCTIONS == NULL) return NULL;
    g_SCRIPT_FUNCTIONS = import_attr("bare_script.library", "SCRIPT_FUNCTIONS");
    if (g_SCRIPT_FUNCTIONS == NULL) return NULL;
    g_BareScriptRuntimeError = import_attr("bare_script.runtime", "BareScriptRuntimeError");
    if (g_BareScriptRuntimeError == NULL) return NULL;
    g_ValueArgsError = import_attr("bare_script.value", "ValueArgsError");
    if (g_ValueArgsError == NULL) return NULL;
    g_value_boolean = import_attr("bare_script.value", "value_boolean");
    if (g_value_boolean == NULL) return NULL;
    g_value_compare = import_attr("bare_script.value", "value_compare");
    if (g_value_compare == NULL) return NULL;
    g_value_normalize_datetime = import_attr("bare_script.value", "value_normalize_datetime");
    if (g_value_normalize_datetime == NULL) return NULL;
    g_value_round_number = import_attr("bare_script.value", "value_round_number");
    if (g_value_round_number == NULL) return NULL;
    g_value_string = import_attr("bare_script.value", "value_string");
    if (g_value_string == NULL) return NULL;
    g_lint_script = import_attr("bare_script.model", "lint_script");
    if (g_lint_script == NULL) return NULL;
    g_url_file_relative = import_attr("bare_script.options", "url_file_relative");
    if (g_url_file_relative == NULL) return NULL;
    g_parse_script = import_attr("bare_script.parser", "parse_script");
    if (g_parse_script == NULL) return NULL;
    g_datetime_date_type = import_attr("datetime", "date");
    if (g_datetime_date_type == NULL) return NULL;
    g_datetime_timedelta_type = import_attr("datetime", "timedelta");
    if (g_datetime_timedelta_type == NULL) return NULL;
    g_functools_partial = import_attr("functools", "partial");
    if (g_functools_partial == NULL) return NULL;

    /* Intern strings */
    INTERN(S_globals, "globals");
    INTERN(S_statementCount, "statementCount");
    INTERN(S_maxStatements, "maxStatements");
    INTERN(S_statements, "statements");
    INTERN(S_expr, "expr");
    INTERN(S_jump, "jump");
    INTERN(S_return, "return");
    INTERN(S_function, "function");
    INTERN(S_include, "include");
    INTERN(S_label, "label");
    INTERN(S_name, "name");
    INTERN(S_args, "args");
    INTERN(S_op, "op");
    INTERN(S_left, "left");
    INTERN(S_right, "right");
    INTERN(S_number, "number");
    INTERN(S_string, "string");
    INTERN(S_variable, "variable");
    INTERN(S_binary, "binary");
    INTERN(S_unary, "unary");
    INTERN(S_group, "group");
    INTERN(S_system, "system");
    INTERN(S_url, "url");
    INTERN(S_includes, "includes");
    INTERN(S_systemPrefix, "systemPrefix");
    INTERN(S_fetchFn, "fetchFn");
    INTERN(S_logFn, "logFn");
    INTERN(S_urlFn, "urlFn");
    INTERN(S_debug, "debug");
    INTERN(S_scriptName, "scriptName");
    INTERN(S_lineNumber, "lineNumber");
    INTERN(S_scripts, "scripts");
    INTERN(S_script, "script");
    INTERN(S_covered, "covered");
    INTERN(S_count, "count");
    INTERN(S_statement, "statement");
    INTERN(S_enabled, "enabled");
    INTERN(S_lastArgArray, "lastArgArray");
    INTERN(S_null_str, "null");
    INTERN(S_false_str, "false");
    INTERN(S_true_str, "true");
    INTERN(S_if_str, "if");
    INTERN(S_SYSTEM_GLOBAL_COVERAGE, "__barescriptCoverage");
    INTERN(S_SYSTEM_GLOBAL_INCLUDES, "__barescriptIncludes");

    /* Export constants */
    if (PyModule_AddObject(m, "DEFAULT_MAX_STATEMENTS", PyLong_FromLongLong(DEFAULT_MAX_STATEMENTS)) < 0) return NULL;

    return m;
}
