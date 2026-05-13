/*
 * BareScript runtime - C extension
 *
 * Mirrors src/bare_script/runtime.py. runtime.py is the source of truth.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <datetime.h>


/* ---------------- Cached module references ---------------- */

static PyObject *g_BareScriptRuntimeError;
static PyObject *g_ValueArgsError;
static PyObject *g_SCRIPT_FUNCTIONS;
static PyObject *g_EXPRESSION_FUNCTIONS;
static PyObject *g_value_boolean;
static PyObject *g_value_compare;
static PyObject *g_value_normalize_datetime;
static PyObject *g_value_round_number;
static PyObject *g_value_string;
static PyObject *g_url_file_relative;
static PyObject *g_parse_script;
static PyObject *g_lint_script;
static PyObject *g_functools_partial;
static PyObject *g_default_max_statements; /* 1e9 (float) */

/* ---------------- Cached interned key strings ---------------- */

#define KEY(name) static PyObject *k_##name
KEY(expr); KEY(jump); KEY(return_); KEY(function); KEY(include); KEY(label);
KEY(name); KEY(args); KEY(statements); KEY(lastArgArray);
KEY(number); KEY(string); KEY(variable); KEY(binary); KEY(unary); KEY(group);
KEY(left); KEY(right); KEY(op);
KEY(url); KEY(includes); KEY(system);
KEY(globals); KEY(statementCount); KEY(maxStatements);
KEY(systemPrefix); KEY(fetchFn); KEY(logFn); KEY(urlFn); KEY(debug);
KEY(scriptName); KEY(lineNumber);
KEY(enabled); KEY(scripts); KEY(covered); KEY(script_field); KEY(count_field); KEY(statement_field);
KEY(null_str); KEY(false_str); KEY(true_str); KEY(if_str);
KEY(coverage_global_name);
KEY(includes_global_name);
#undef KEY

static PyObject *g_empty_tuple;

/* ---------------- Helpers ---------------- */

/* Return 1 if value is a "number" by BareScript semantics: int or float, NOT bool */
static inline int is_number(PyObject *v) {
    return (PyLong_Check(v) || PyFloat_Check(v)) && !PyBool_Check(v);
}

/* Check whether v is int-valued (int, or float with int(v) == v) and not bool */
static inline int is_intish(PyObject *v) {
    if (PyBool_Check(v)) return 0;
    if (PyLong_Check(v)) return 1;
    if (PyFloat_Check(v)) {
        double d = PyFloat_AS_DOUBLE(v);
        double t = (double)(long long)d;
        return t == d;
    }
    return 0;
}

/* Convert int-valued number to long (caller already ensured is_intish) */
static long long intish_to_ll(PyObject *v) {
    if (PyLong_Check(v)) return PyLong_AsLongLong(v);
    return (long long)PyFloat_AS_DOUBLE(v);
}

/* Call Python's value_boolean(v) and return as int (-1 on error). Returns 0/1. */
static int call_value_boolean(PyObject *v) {
    if (v == Py_None) return 0;
    if (PyBool_Check(v)) return v == Py_True;
    if (PyLong_Check(v)) {
        int z = PyObject_IsTrue(v);
        return z;
    }
    if (PyFloat_Check(v)) {
        double d = PyFloat_AS_DOUBLE(v);
        return d != 0.0;
    }
    if (PyUnicode_Check(v)) return PyUnicode_GetLength(v) != 0;
    if (PyList_Check(v)) return PyList_GET_SIZE(v) != 0;
    return 1; /* everything else non-null is true */
}

/* Wrapper to call ValueErr - returns NULL after setting BareScriptRuntimeError */
static PyObject *raise_runtime_error(PyObject *script, PyObject *statement, const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    PyObject *msg = PyUnicode_FromString(buf);
    if (!msg) return NULL;
    PyObject *exc = PyObject_CallFunctionObjArgs(g_BareScriptRuntimeError, script ? script : Py_None,
                                                 statement ? statement : Py_None, msg, NULL);
    Py_DECREF(msg);
    if (!exc) return NULL;
    PyErr_SetObject(g_BareScriptRuntimeError, exc);
    Py_DECREF(exc);
    return NULL;
}

/* ---------------- ScriptFunction custom type ---------------- */

/*
 * Wraps a (script, function) BareScript model pair as a Python callable.
 * When called with (args, options), invokes execute_script_helper with new locals.
 */
typedef struct {
    PyObject_HEAD
    PyObject *script;
    PyObject *function;
} ScriptFunctionObject;

static PyObject *execute_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_);
static PyObject *evaluate_expression_inner(PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
                                           PyObject *script, PyObject *statement);

static int ScriptFunction_traverse(ScriptFunctionObject *self, visitproc visit, void *arg) {
    Py_VISIT(self->script);
    Py_VISIT(self->function);
    return 0;
}

static int ScriptFunction_clear(ScriptFunctionObject *self) {
    Py_CLEAR(self->script);
    Py_CLEAR(self->function);
    return 0;
}

static void ScriptFunction_dealloc(ScriptFunctionObject *self) {
    PyObject_GC_UnTrack(self);
    ScriptFunction_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *ScriptFunction_call(ScriptFunctionObject *self, PyObject *args, PyObject *kwds) {
    PyObject *fn_args, *options;
    if (!PyArg_UnpackTuple(args, "ScriptFunction", 2, 2, &fn_args, &options)) return NULL;

    /* Build locals_ from function args */
    PyObject *func_locals = PyDict_New();
    if (!func_locals) return NULL;

    PyObject *func_args = PyDict_GetItemWithError(self->function, k_args);
    if (!func_args && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
    if (func_args && func_args != Py_None) {
        Py_ssize_t args_length = PyList_Check(fn_args) ? PyList_GET_SIZE(fn_args)
                                                       : PyObject_Length(fn_args);
        if (args_length < 0) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t func_args_length = PyList_GET_SIZE(func_args);
        PyObject *last_arg_array_obj = PyDict_GetItemWithError(self->function, k_lastArgArray);
        if (!last_arg_array_obj && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
        int has_last_arg_array = (last_arg_array_obj != NULL && PyObject_IsTrue(last_arg_array_obj));
        Py_ssize_t ix_arg_last = has_last_arg_array ? (func_args_length - 1) : -1;

        for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
            PyObject *arg_name = PyList_GET_ITEM(func_args, ix);
            PyObject *value;
            if (ix < args_length) {
                if (ix == ix_arg_last) {
                    /* args[ix:] */
                    value = PyObject_GetItem(fn_args, PySlice_New(PyLong_FromSsize_t(ix), Py_None, NULL));
                    /* Construct slice properly */
                    PyObject *start = PyLong_FromSsize_t(ix);
                    PyObject *slice = PySlice_New(start, Py_None, NULL);
                    Py_DECREF(start);
                    if (!slice) { Py_DECREF(func_locals); return NULL; }
                    Py_XDECREF(value);
                    value = PyObject_GetItem(fn_args, slice);
                    Py_DECREF(slice);
                    if (!value) { Py_DECREF(func_locals); return NULL; }
                } else {
                    if (PyList_Check(fn_args)) {
                        value = PyList_GET_ITEM(fn_args, ix);
                        Py_INCREF(value);
                    } else {
                        value = PySequence_GetItem(fn_args, ix);
                        if (!value) { Py_DECREF(func_locals); return NULL; }
                    }
                }
            } else {
                if (ix == ix_arg_last) {
                    value = PyList_New(0);
                    if (!value) { Py_DECREF(func_locals); return NULL; }
                } else {
                    value = Py_None;
                    Py_INCREF(value);
                }
            }
            if (PyDict_SetItem(func_locals, arg_name, value) < 0) {
                Py_DECREF(value);
                Py_DECREF(func_locals);
                return NULL;
            }
            Py_DECREF(value);
        }
    }

    PyObject *statements = PyDict_GetItemWithError(self->function, k_statements);
    if (!statements) { Py_DECREF(func_locals); if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements"); return NULL; }
    PyObject *result = execute_script_helper(self->script, statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}

static PyTypeObject ScriptFunctionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c.ScriptFunction",
    .tp_basicsize = sizeof(ScriptFunctionObject),
    .tp_dealloc = (destructor)ScriptFunction_dealloc,
    .tp_call = (ternaryfunc)ScriptFunction_call,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)ScriptFunction_traverse,
    .tp_clear = (inquiry)ScriptFunction_clear,
};

static PyObject *new_script_function(PyObject *script, PyObject *function) {
    ScriptFunctionObject *obj = PyObject_GC_New(ScriptFunctionObject, &ScriptFunctionType);
    if (!obj) return NULL;
    Py_INCREF(script);
    Py_INCREF(function);
    obj->script = script;
    obj->function = function;
    PyObject_GC_Track(obj);
    return (PyObject *)obj;
}

/* ---------------- Coverage helper ---------------- */

static int record_statement_coverage(PyObject *script, PyObject *statement, PyObject *statement_key,
                                     PyObject *coverage_global) {
    PyObject *script_name = PyDict_GetItemWithError(script, k_scriptName);
    if (!script_name && PyErr_Occurred()) return -1;
    if (!script_name) return 0;

    PyObject *stmt_inner = PyDict_GetItemWithError(statement, statement_key);
    if (!stmt_inner) { if (PyErr_Occurred()) return -1; return 0; }
    PyObject *lineno = PyDict_GetItemWithError(stmt_inner, k_lineNumber);
    if (!lineno && PyErr_Occurred()) return -1;
    if (!lineno) return 0;

    PyObject *scripts = PyDict_GetItemWithError(coverage_global, k_scripts);
    if (!scripts && PyErr_Occurred()) return -1;
    if (!scripts) {
        scripts = PyDict_New();
        if (!scripts) return -1;
        if (PyDict_SetItem(coverage_global, k_scripts, scripts) < 0) { Py_DECREF(scripts); return -1; }
        Py_DECREF(scripts);
        scripts = PyDict_GetItem(coverage_global, k_scripts);
    }

    PyObject *script_coverage = PyDict_GetItemWithError(scripts, script_name);
    if (!script_coverage && PyErr_Occurred()) return -1;
    if (!script_coverage) {
        script_coverage = PyDict_New();
        if (!script_coverage) return -1;
        PyObject *covered = PyDict_New();
        if (!covered) { Py_DECREF(script_coverage); return -1; }
        if (PyDict_SetItem(script_coverage, k_script_field, script) < 0 ||
            PyDict_SetItem(script_coverage, k_covered, covered) < 0) {
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
        script_coverage = PyDict_GetItem(scripts, script_name);
    }

    PyObject *covered = PyDict_GetItemWithError(script_coverage, k_covered);
    if (!covered) { if (PyErr_Occurred()) return -1; return 0; }

    PyObject *lineno_str = PyObject_Str(lineno);
    if (!lineno_str) return -1;

    PyObject *covered_statement = PyDict_GetItemWithError(covered, lineno_str);
    if (!covered_statement && PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
    if (!covered_statement) {
        covered_statement = PyDict_New();
        if (!covered_statement) { Py_DECREF(lineno_str); return -1; }
        PyObject *zero = PyLong_FromLong(0);
        if (!zero ||
            PyDict_SetItem(covered_statement, k_statement_field, statement) < 0 ||
            PyDict_SetItem(covered_statement, k_count_field, zero) < 0) {
            Py_XDECREF(zero);
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
        covered_statement = PyDict_GetItem(covered, lineno_str);
    }
    Py_DECREF(lineno_str);

    PyObject *current_count = PyDict_GetItemWithError(covered_statement, k_count_field);
    if (!current_count) { if (PyErr_Occurred()) return -1; return 0; }
    PyObject *one = PyLong_FromLong(1);
    if (!one) return -1;
    PyObject *new_count = PyNumber_Add(current_count, one);
    Py_DECREF(one);
    if (!new_count) return -1;
    int rc = PyDict_SetItem(covered_statement, k_count_field, new_count);
    Py_DECREF(new_count);
    return rc;
}

/* ---------------- Expression evaluator ---------------- */

static PyObject *evaluate_expression_inner(PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
                                           PyObject *script, PyObject *statement) {
    if (!PyDict_Check(expr)) {
        PyErr_SetString(PyExc_TypeError, "expression must be a dict");
        return NULL;
    }

    PyObject *globals_ = NULL;
    if (options != NULL && options != Py_None) {
        globals_ = PyDict_GetItemWithError(options, k_globals);
        if (!globals_ && PyErr_Occurred()) return NULL;
    }

    /* Get the (single) key */
    PyObject *expr_key = NULL;
    PyObject *expr_value = NULL;
    Py_ssize_t pos = 0;
    if (!PyDict_Next(expr, &pos, &expr_key, &expr_value)) {
        PyErr_SetString(PyExc_ValueError, "expression dict is empty");
        return NULL;
    }

    /* number */
    if (expr_key == k_number || PyObject_RichCompareBool(expr_key, k_number, Py_EQ) == 1) {
        Py_INCREF(expr_value);
        return expr_value;
    }

    /* string */
    if (expr_key == k_string || PyObject_RichCompareBool(expr_key, k_string, Py_EQ) == 1) {
        Py_INCREF(expr_value);
        return expr_value;
    }

    /* variable */
    if (expr_key == k_variable || PyObject_RichCompareBool(expr_key, k_variable, Py_EQ) == 1) {
        /* expr_value is the variable name string */
        if (PyUnicode_Check(expr_value)) {
            if (PyUnicode_CompareWithASCIIString(expr_value, "null") == 0) { Py_RETURN_NONE; }
            if (PyUnicode_CompareWithASCIIString(expr_value, "false") == 0) { Py_RETURN_FALSE; }
            if (PyUnicode_CompareWithASCIIString(expr_value, "true") == 0) { Py_RETURN_TRUE; }
        }
        if (locals_ != NULL && locals_ != Py_None) {
            PyObject *v = PyDict_GetItemWithError(locals_, expr_value);
            if (v) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        if (globals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(globals_, expr_value);
            if (v) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        Py_RETURN_NONE;
    }

    /* function */
    if (expr_key == k_function || PyObject_RichCompareBool(expr_key, k_function, Py_EQ) == 1) {
        PyObject *func_dict = expr_value;
        PyObject *func_name = PyDict_GetItemWithError(func_dict, k_name);
        if (!func_name) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "name"); return NULL; }

        /* "if" built-in */
        if (PyUnicode_Check(func_name) && PyUnicode_CompareWithASCIIString(func_name, "if") == 0) {
            PyObject *args_expr = PyDict_GetItemWithError(func_dict, k_args);
            if (!args_expr && PyErr_Occurred()) return NULL;
            Py_ssize_t alen = 0;
            if (args_expr) alen = PyObject_Length(args_expr);
            PyObject *value_expr = (alen >= 1) ? PySequence_GetItem(args_expr, 0) : NULL;
            PyObject *true_expr  = (alen >= 2) ? PySequence_GetItem(args_expr, 1) : NULL;
            PyObject *false_expr = (alen >= 3) ? PySequence_GetItem(args_expr, 2) : NULL;
            PyObject *value;
            if (value_expr) {
                value = evaluate_expression_inner(value_expr, options, locals_, builtins, script, statement);
                Py_DECREF(value_expr);
                if (!value) { Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
            } else {
                value = Py_False; Py_INCREF(value);
            }
            int truthy = call_value_boolean(value);
            Py_DECREF(value);
            PyObject *result_expr = truthy ? true_expr : false_expr;
            PyObject *other = truthy ? false_expr : true_expr;
            Py_XDECREF(other);
            if (!result_expr) { Py_RETURN_NONE; }
            PyObject *r = evaluate_expression_inner(result_expr, options, locals_, builtins, script, statement);
            Py_DECREF(result_expr);
            return r;
        }

        /* Compute func_args (list) */
        PyObject *func_args_list = NULL;
        PyObject *args_expr = PyDict_GetItemWithError(func_dict, k_args);
        if (!args_expr && PyErr_Occurred()) return NULL;
        if (args_expr) {
            Py_ssize_t n = PyObject_Length(args_expr);
            if (n < 0) return NULL;
            func_args_list = PyList_New(n);
            if (!func_args_list) return NULL;
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *arg_expr = PySequence_GetItem(args_expr, i);
                if (!arg_expr) { Py_DECREF(func_args_list); return NULL; }
                PyObject *v = evaluate_expression_inner(arg_expr, options, locals_, builtins, script, statement);
                Py_DECREF(arg_expr);
                if (!v) { Py_DECREF(func_args_list); return NULL; }
                PyList_SET_ITEM(func_args_list, i, v);
            }
        }

        /* Look up func_value */
        PyObject *func_value = NULL;
        if (locals_ != NULL && locals_ != Py_None) {
            func_value = PyDict_GetItemWithError(locals_, func_name);
            if (!func_value && PyErr_Occurred()) { Py_XDECREF(func_args_list); return NULL; }
        }
        if (!func_value && globals_ != NULL) {
            func_value = PyDict_GetItemWithError(globals_, func_name);
            if (!func_value && PyErr_Occurred()) { Py_XDECREF(func_args_list); return NULL; }
        }
        if (!func_value && builtins) {
            func_value = PyDict_GetItemWithError(g_EXPRESSION_FUNCTIONS, func_name);
            if (!func_value && PyErr_Occurred()) { Py_XDECREF(func_args_list); return NULL; }
        }

        if (func_value != NULL && func_value != Py_None) {
            PyObject *call_args = func_args_list ? func_args_list : PyList_New(0);
            if (!call_args) { return NULL; }
            PyObject *opt = options ? options : Py_None;
            PyObject *result = PyObject_CallFunctionObjArgs(func_value, call_args, opt, NULL);
            Py_DECREF(call_args);
            if (result) return result;

            /* Exception path */
            if (PyErr_ExceptionMatches(g_BareScriptRuntimeError)) {
                return NULL;
            }
            /* Get the exception value to extract error info */
            PyObject *exc_type, *exc_value, *exc_tb;
            PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
            PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);

            /* Log if debug and logFn */
            if (options != NULL && options != Py_None) {
                PyObject *log_fn = PyDict_GetItemWithError(options, k_logFn);
                if (!log_fn && PyErr_Occurred()) { Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb); return NULL; }
                PyObject *debug = PyDict_GetItemWithError(options, k_debug);
                if (!debug && PyErr_Occurred()) { Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb); return NULL; }
                if (log_fn && debug && PyObject_IsTrue(debug)) {
                    PyObject *error_str = exc_value ? PyObject_Str(exc_value) : PyUnicode_FromString("");
                    if (error_str) {
                        PyObject *msg = PyUnicode_FromFormat("BareScript: Function \"%U\" failed with error: %U",
                                                             func_name, error_str);
                        Py_DECREF(error_str);
                        if (msg) {
                            PyObject *log_res = PyObject_CallOneArg(log_fn, msg);
                            Py_DECREF(msg);
                            Py_XDECREF(log_res);
                        }
                    }
                }
            }

            /* If ValueArgsError, return its return_value */
            if (exc_value && PyObject_IsInstance(exc_value, g_ValueArgsError)) {
                PyObject *rv = PyObject_GetAttrString(exc_value, "return_value");
                Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                if (!rv) return NULL;
                return rv;
            }
            Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
            Py_RETURN_NONE;
        }

        Py_XDECREF(func_args_list);
        PyObject *name_str = PyObject_Str(func_name);
        const char *ns = name_str ? PyUnicode_AsUTF8(name_str) : "?";
        raise_runtime_error(script, statement, "Undefined function \"%s\"", ns);
        Py_XDECREF(name_str);
        return NULL;
    }

    /* binary */
    if (expr_key == k_binary || PyObject_RichCompareBool(expr_key, k_binary, Py_EQ) == 1) {
        PyObject *bin = expr_value;
        PyObject *bin_op = PyDict_GetItemWithError(bin, k_op);
        if (!bin_op) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "op"); return NULL; }
        PyObject *left_expr = PyDict_GetItemWithError(bin, k_left);
        if (!left_expr) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "left"); return NULL; }
        PyObject *left_value = evaluate_expression_inner(left_expr, options, locals_, builtins, script, statement);
        if (!left_value) return NULL;

        const char *op = PyUnicode_AsUTF8(bin_op);
        if (!op) { Py_DECREF(left_value); return NULL; }

        /* short-circuit && */
        if (op[0] == '&' && op[1] == '&' && op[2] == 0) {
            int t = call_value_boolean(left_value);
            if (!t) return left_value;
            Py_DECREF(left_value);
            PyObject *right_expr = PyDict_GetItemWithError(bin, k_right);
            if (!right_expr) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "right"); return NULL; }
            return evaluate_expression_inner(right_expr, options, locals_, builtins, script, statement);
        }
        /* short-circuit || */
        if (op[0] == '|' && op[1] == '|' && op[2] == 0) {
            int t = call_value_boolean(left_value);
            if (t) return left_value;
            Py_DECREF(left_value);
            PyObject *right_expr = PyDict_GetItemWithError(bin, k_right);
            if (!right_expr) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "right"); return NULL; }
            return evaluate_expression_inner(right_expr, options, locals_, builtins, script, statement);
        }

        PyObject *right_expr = PyDict_GetItemWithError(bin, k_right);
        if (!right_expr) { Py_DECREF(left_value); if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "right"); return NULL; }
        PyObject *right_value = evaluate_expression_inner(right_expr, options, locals_, builtins, script, statement);
        if (!right_value) { Py_DECREF(left_value); return NULL; }

        PyObject *result = NULL;
        if (op[0] == '+' && op[1] == 0) {
            if (is_number(left_value) && is_number(right_value)) {
                result = PyNumber_Add(left_value, right_value);
            } else if (PyUnicode_Check(left_value) && PyUnicode_Check(right_value)) {
                result = PyUnicode_Concat(left_value, right_value);
            } else if (PyUnicode_Check(left_value)) {
                PyObject *rs = PyObject_CallOneArg(g_value_string, right_value);
                if (rs) { result = PyUnicode_Concat(left_value, rs); Py_DECREF(rs); }
            } else if (PyUnicode_Check(right_value)) {
                PyObject *ls = PyObject_CallOneArg(g_value_string, left_value);
                if (ls) { result = PyUnicode_Concat(ls, right_value); Py_DECREF(ls); }
            } else if (PyDateTime_Check(left_value) || PyDate_Check(left_value)) {
                if (is_number(right_value)) {
                    PyObject *left_dt = PyObject_CallOneArg(g_value_normalize_datetime, left_value);
                    if (left_dt) {
                        double ms = PyFloat_AsDouble(right_value);
                        if (PyErr_Occurred()) { Py_DECREF(left_dt); }
                        else {
                            PyObject *td = PyObject_CallFunction((PyObject*)PyDateTimeAPI->DeltaType, "iii", 0, 0, 0);
                            Py_XDECREF(td);
                            /* Use proper construction with milliseconds: timedelta(milliseconds=ms) */
                            PyObject *kwargs = Py_BuildValue("{s:d}", "milliseconds", ms);
                            if (kwargs) {
                                PyObject *empty = PyTuple_New(0);
                                PyObject *delta = PyObject_Call((PyObject *)PyDateTimeAPI->DeltaType, empty, kwargs);
                                Py_DECREF(empty); Py_DECREF(kwargs);
                                if (delta) {
                                    result = PyNumber_Add(left_dt, delta);
                                    Py_DECREF(delta);
                                }
                            }
                            Py_DECREF(left_dt);
                        }
                    }
                }
            } else if (is_number(left_value) && (PyDateTime_Check(right_value) || PyDate_Check(right_value))) {
                PyObject *right_dt = PyObject_CallOneArg(g_value_normalize_datetime, right_value);
                if (right_dt) {
                    double ms = PyFloat_AsDouble(left_value);
                    if (PyErr_Occurred()) { Py_DECREF(right_dt); }
                    else {
                        PyObject *kwargs = Py_BuildValue("{s:d}", "milliseconds", ms);
                        if (kwargs) {
                            PyObject *empty = PyTuple_New(0);
                            PyObject *delta = PyObject_Call((PyObject *)PyDateTimeAPI->DeltaType, empty, kwargs);
                            Py_DECREF(empty); Py_DECREF(kwargs);
                            if (delta) {
                                result = PyNumber_Add(right_dt, delta);
                                Py_DECREF(delta);
                            }
                        }
                        Py_DECREF(right_dt);
                    }
                }
            }
        } else if (op[0] == '-' && op[1] == 0) {
            if (is_number(left_value) && is_number(right_value)) {
                result = PyNumber_Subtract(left_value, right_value);
            } else if ((PyDateTime_Check(left_value) || PyDate_Check(left_value)) &&
                       (PyDateTime_Check(right_value) || PyDate_Check(right_value))) {
                PyObject *ldt = PyObject_CallOneArg(g_value_normalize_datetime, left_value);
                PyObject *rdt = ldt ? PyObject_CallOneArg(g_value_normalize_datetime, right_value) : NULL;
                if (ldt && rdt) {
                    PyObject *delta = PyNumber_Subtract(ldt, rdt);
                    if (delta) {
                        PyObject *secs = PyObject_CallMethod(delta, "total_seconds", NULL);
                        Py_DECREF(delta);
                        if (secs) {
                            double s = PyFloat_AsDouble(secs);
                            Py_DECREF(secs);
                            if (!PyErr_Occurred()) {
                                PyObject *ms_arg = PyFloat_FromDouble(s * 1000.0);
                                PyObject *digits = PyLong_FromLong(0);
                                if (ms_arg && digits) {
                                    result = PyObject_CallFunctionObjArgs(g_value_round_number, ms_arg, digits, NULL);
                                }
                                Py_XDECREF(ms_arg); Py_XDECREF(digits);
                            }
                        }
                    }
                }
                Py_XDECREF(ldt); Py_XDECREF(rdt);
            }
        } else if (op[0] == '*' && op[1] == 0) {
            if (is_number(left_value) && is_number(right_value)) {
                result = PyNumber_Multiply(left_value, right_value);
            }
        } else if (op[0] == '/' && op[1] == 0) {
            if (is_number(left_value) && is_number(right_value)) {
                result = PyNumber_TrueDivide(left_value, right_value);
            }
        } else if (op[0] == '=' && op[1] == '=' && op[2] == 0) {
            PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left_value, right_value, NULL);
            if (r) {
                long c = PyLong_AsLong(r);
                Py_DECREF(r);
                if (c == 0 && PyErr_Occurred()) {}
                else { result = c == 0 ? Py_True : Py_False; Py_INCREF(result); }
            }
        } else if (op[0] == '!' && op[1] == '=' && op[2] == 0) {
            PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left_value, right_value, NULL);
            if (r) {
                long c = PyLong_AsLong(r);
                Py_DECREF(r);
                if (!(c == 0 && PyErr_Occurred())) { result = c != 0 ? Py_True : Py_False; Py_INCREF(result); }
            }
        } else if (op[0] == '<' && op[1] == '=' && op[2] == 0) {
            PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left_value, right_value, NULL);
            if (r) {
                long c = PyLong_AsLong(r);
                Py_DECREF(r);
                if (!(c == 0 && PyErr_Occurred())) { result = c <= 0 ? Py_True : Py_False; Py_INCREF(result); }
            }
        } else if (op[0] == '<' && op[1] == 0) {
            PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left_value, right_value, NULL);
            if (r) {
                long c = PyLong_AsLong(r);
                Py_DECREF(r);
                if (!(c == 0 && PyErr_Occurred())) { result = c < 0 ? Py_True : Py_False; Py_INCREF(result); }
            }
        } else if (op[0] == '>' && op[1] == '=' && op[2] == 0) {
            PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left_value, right_value, NULL);
            if (r) {
                long c = PyLong_AsLong(r);
                Py_DECREF(r);
                if (!(c == 0 && PyErr_Occurred())) { result = c >= 0 ? Py_True : Py_False; Py_INCREF(result); }
            }
        } else if (op[0] == '>' && op[1] == 0) {
            PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left_value, right_value, NULL);
            if (r) {
                long c = PyLong_AsLong(r);
                Py_DECREF(r);
                if (!(c == 0 && PyErr_Occurred())) { result = c > 0 ? Py_True : Py_False; Py_INCREF(result); }
            }
        } else if (op[0] == '%' && op[1] == 0) {
            if (is_number(left_value) && is_number(right_value)) {
                /* BareScript % uses Python % semantics but only on numbers - match Python's modulo */
                result = PyNumber_Remainder(left_value, right_value);
            }
        } else if (op[0] == '*' && op[1] == '*' && op[2] == 0) {
            if (is_number(left_value) && is_number(right_value)) {
                result = PyNumber_Power(left_value, right_value, Py_None);
            }
        } else if (op[0] == '&' && op[1] == 0) {
            if (is_intish(left_value) && is_intish(right_value)) {
                long long a = intish_to_ll(left_value), b = intish_to_ll(right_value);
                result = PyLong_FromLongLong(a & b);
            }
        } else if (op[0] == '|' && op[1] == 0) {
            if (is_intish(left_value) && is_intish(right_value)) {
                long long a = intish_to_ll(left_value), b = intish_to_ll(right_value);
                result = PyLong_FromLongLong(a | b);
            }
        } else if (op[0] == '^' && op[1] == 0) {
            if (is_intish(left_value) && is_intish(right_value)) {
                long long a = intish_to_ll(left_value), b = intish_to_ll(right_value);
                result = PyLong_FromLongLong(a ^ b);
            }
        } else if (op[0] == '<' && op[1] == '<' && op[2] == 0) {
            if (is_intish(left_value) && is_intish(right_value)) {
                long long a = intish_to_ll(left_value), b = intish_to_ll(right_value);
                result = PyLong_FromLongLong(a << b);
            }
        } else if (op[0] == '>' && op[1] == '>' && op[2] == 0) {
            if (is_intish(left_value) && is_intish(right_value)) {
                long long a = intish_to_ll(left_value), b = intish_to_ll(right_value);
                result = PyLong_FromLongLong(a >> b);
            }
        }

        Py_DECREF(left_value);
        Py_DECREF(right_value);
        if (result) return result;
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }

    /* unary */
    if (expr_key == k_unary || PyObject_RichCompareBool(expr_key, k_unary, Py_EQ) == 1) {
        PyObject *un = expr_value;
        PyObject *unary_op = PyDict_GetItemWithError(un, k_op);
        if (!unary_op) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "op"); return NULL; }
        PyObject *inner_expr = PyDict_GetItemWithError(un, k_expr);
        if (!inner_expr) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "expr"); return NULL; }
        PyObject *value = evaluate_expression_inner(inner_expr, options, locals_, builtins, script, statement);
        if (!value) return NULL;
        const char *op = PyUnicode_AsUTF8(unary_op);
        if (!op) { Py_DECREF(value); return NULL; }
        PyObject *result = NULL;
        if (op[0] == '!') {
            int t = call_value_boolean(value);
            result = t ? Py_False : Py_True;
            Py_INCREF(result);
        } else if (op[0] == '-') {
            if (is_number(value)) result = PyNumber_Negative(value);
        } else { /* '~' */
            if (is_intish(value)) {
                long long a = intish_to_ll(value);
                result = PyLong_FromLongLong(~a);
            }
        }
        Py_DECREF(value);
        if (result) return result;
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }

    /* group */
    return evaluate_expression_inner(expr_value, options, locals_, builtins, script, statement);
}

/* ---------------- Script executor ---------------- */

static PyObject *execute_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_) {
    PyObject *globals_ = PyDict_GetItemWithError(options, k_globals);
    if (!globals_) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "globals"); return NULL; }

    PyObject *label_indexes = NULL;
    Py_ssize_t statements_length;
    if (PyList_Check(statements)) statements_length = PyList_GET_SIZE(statements);
    else { statements_length = PyObject_Length(statements); if (statements_length < 0) return NULL; }
    Py_ssize_t ix_statement = 0;

    PyObject *result = NULL;

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_Check(statements)
            ? PyList_GET_ITEM(statements, ix_statement)
            : PySequence_GetItem(statements, ix_statement);
        if (!statement) goto error;
        if (!PyList_Check(statements)) {
            /* PySequence_GetItem returned a new ref; we want a borrowed-style ref */
            Py_DECREF(statement); /* but we still need it */
            statement = PyList_Check(statements) ? PyList_GET_ITEM(statements, ix_statement)
                                                 : PySequence_GetItem(statements, ix_statement);
            if (!statement) goto error;
        }
        /* statement is borrowed in list case, owned in sequence case - normalize: only support list */

        PyObject *statement_key = NULL, *statement_value = NULL;
        Py_ssize_t pos = 0;
        if (!PyDict_Next(statement, &pos, &statement_key, &statement_value)) {
            PyErr_SetString(PyExc_ValueError, "empty statement");
            goto error;
        }

        /* Increment statementCount */
        PyObject *count_obj = PyDict_GetItemWithError(options, k_statementCount);
        if (!count_obj && PyErr_Occurred()) goto error;
        long long count = 0;
        if (count_obj) {
            count = PyLong_AsLongLong(count_obj);
            if (count == -1 && PyErr_Occurred()) { PyErr_Clear(); count = 0; }
        }
        count++;
        PyObject *new_count = PyLong_FromLongLong(count);
        if (!new_count) goto error;
        if (PyDict_SetItem(options, k_statementCount, new_count) < 0) { Py_DECREF(new_count); goto error; }
        Py_DECREF(new_count);

        /* maxStatements check */
        PyObject *max_obj = PyDict_GetItemWithError(options, k_maxStatements);
        if (!max_obj && PyErr_Occurred()) goto error;
        if (!max_obj) max_obj = g_default_max_statements;
        double max_val = PyFloat_AsDouble(max_obj);
        if (max_val == -1.0 && PyErr_Occurred()) { PyErr_Clear(); max_val = 1e9; }
        if (max_val > 0 && (double)count > max_val) {
            char msg[128];
            if (max_val == (double)(long long)max_val) {
                snprintf(msg, sizeof(msg), "Exceeded maximum script statements (%lld)", (long long)max_val);
            } else {
                snprintf(msg, sizeof(msg), "Exceeded maximum script statements (%g)", max_val);
            }
            raise_runtime_error(script, statement, "%s", msg);
            goto error;
        }

        /* Coverage */
        PyObject *coverage_global = PyDict_GetItemWithError(globals_, k_coverage_global_name);
        if (!coverage_global && PyErr_Occurred()) goto error;
        int has_coverage = 0;
        if (coverage_global && PyDict_Check(coverage_global)) {
            PyObject *enabled = PyDict_GetItemWithError(coverage_global, k_enabled);
            if (!enabled && PyErr_Occurred()) goto error;
            int is_system = 0;
            PyObject *sysv = PyDict_GetItemWithError(script, k_system);
            if (!sysv && PyErr_Occurred()) goto error;
            if (sysv) is_system = PyObject_IsTrue(sysv);
            if (enabled && PyObject_IsTrue(enabled) && !is_system) {
                has_coverage = 1;
                if (record_statement_coverage(script, statement, statement_key, coverage_global) < 0) goto error;
            }
        }

        /* Dispatch */
        int eq;

        eq = (statement_key == k_expr) || PyObject_RichCompareBool(statement_key, k_expr, Py_EQ) == 1;
        if (eq) {
            PyObject *inner_expr = PyDict_GetItemWithError(statement_value, k_expr);
            if (!inner_expr) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "expr"); goto error; }
            PyObject *expr_value = evaluate_expression_inner(inner_expr, options, locals_, 0, script, statement);
            if (!expr_value) goto error;
            PyObject *expr_name = PyDict_GetItemWithError(statement_value, k_name);
            if (!expr_name && PyErr_Occurred()) { Py_DECREF(expr_value); goto error; }
            if (expr_name) {
                PyObject *target = (locals_ != NULL && locals_ != Py_None) ? locals_ : globals_;
                if (PyDict_SetItem(target, expr_name, expr_value) < 0) { Py_DECREF(expr_value); goto error; }
            }
            Py_DECREF(expr_value);
            ix_statement++;
            continue;
        }

        eq = (statement_key == k_jump) || PyObject_RichCompareBool(statement_key, k_jump, Py_EQ) == 1;
        if (eq) {
            PyObject *jump = statement_value;
            int do_jump = 1;
            PyObject *cond_expr = PyDict_GetItemWithError(jump, k_expr);
            if (!cond_expr && PyErr_Occurred()) goto error;
            if (cond_expr) {
                PyObject *cv = evaluate_expression_inner(cond_expr, options, locals_, 0, script, statement);
                if (!cv) goto error;
                do_jump = call_value_boolean(cv);
                Py_DECREF(cv);
            }
            if (do_jump) {
                PyObject *jump_label = PyDict_GetItemWithError(jump, k_label);
                if (!jump_label) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "label"); goto error; }
                Py_ssize_t ix_label = -1;
                if (label_indexes) {
                    PyObject *ixobj = PyDict_GetItemWithError(label_indexes, jump_label);
                    if (!ixobj && PyErr_Occurred()) goto error;
                    if (ixobj) ix_label = PyLong_AsSsize_t(ixobj);
                }
                if (ix_label < 0) {
                    /* Search statements for label */
                    for (Py_ssize_t i = 0; i < statements_length; i++) {
                        PyObject *st = PyList_GET_ITEM(statements, i);
                        PyObject *stk = NULL, *stv = NULL;
                        Py_ssize_t spos = 0;
                        if (!PyDict_Next(st, &spos, &stk, &stv)) continue;
                        int is_label = (stk == k_label) || PyObject_RichCompareBool(stk, k_label, Py_EQ) == 1;
                        if (!is_label) continue;
                        PyObject *lname = PyDict_GetItemWithError(stv, k_name);
                        if (!lname && PyErr_Occurred()) goto error;
                        if (lname && PyObject_RichCompareBool(lname, jump_label, Py_EQ) == 1) {
                            ix_label = i;
                            break;
                        }
                    }
                    if (ix_label < 0) {
                        PyObject *lstr = PyObject_Str(jump_label);
                        const char *ls = lstr ? PyUnicode_AsUTF8(lstr) : "?";
                        raise_runtime_error(script, statement, "Unknown jump label \"%s\"", ls);
                        Py_XDECREF(lstr);
                        goto error;
                    }
                    if (!label_indexes) {
                        label_indexes = PyDict_New();
                        if (!label_indexes) goto error;
                    }
                    PyObject *ixobj = PyLong_FromSsize_t(ix_label);
                    if (!ixobj) goto error;
                    int sr = PyDict_SetItem(label_indexes, jump_label, ixobj);
                    Py_DECREF(ixobj);
                    if (sr < 0) goto error;
                }
                ix_statement = ix_label;

                /* Record label statement coverage */
                if (has_coverage && coverage_global) {
                    PyObject *label_statement = PyList_GET_ITEM(statements, ix_statement);
                    PyObject *lstk = NULL, *lstv = NULL;
                    Py_ssize_t lspos = 0;
                    if (PyDict_Next(label_statement, &lspos, &lstk, &lstv)) {
                        if (record_statement_coverage(script, label_statement, lstk, coverage_global) < 0) goto error;
                    }
                }
            }
            ix_statement++;
            continue;
        }

        eq = (statement_key == k_return_) || PyObject_RichCompareBool(statement_key, k_return_, Py_EQ) == 1;
        if (eq) {
            PyObject *ret = statement_value;
            PyObject *cond_expr = PyDict_GetItemWithError(ret, k_expr);
            if (!cond_expr && PyErr_Occurred()) goto error;
            if (cond_expr) {
                result = evaluate_expression_inner(cond_expr, options, locals_, 0, script, statement);
                if (!result) goto error;
                goto cleanup;
            }
            result = Py_None; Py_INCREF(result);
            goto cleanup;
        }

        eq = (statement_key == k_function) || PyObject_RichCompareBool(statement_key, k_function, Py_EQ) == 1;
        if (eq) {
            PyObject *fn = statement_value;
            PyObject *fn_name = PyDict_GetItemWithError(fn, k_name);
            if (!fn_name) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "name"); goto error; }
            PyObject *sf = new_script_function(script, fn);
            if (!sf) goto error;
            if (PyDict_SetItem(globals_, fn_name, sf) < 0) { Py_DECREF(sf); goto error; }
            Py_DECREF(sf);
            ix_statement++;
            continue;
        }

        eq = (statement_key == k_include) || PyObject_RichCompareBool(statement_key, k_include, Py_EQ) == 1;
        if (eq) {
            PyObject *include = statement_value;
            PyObject *system_prefix = PyDict_GetItemWithError(options, k_systemPrefix);
            if (!system_prefix && PyErr_Occurred()) goto error;
            PyObject *fetch_fn = PyDict_GetItemWithError(options, k_fetchFn);
            if (!fetch_fn && PyErr_Occurred()) goto error;
            PyObject *log_fn = PyDict_GetItemWithError(options, k_logFn);
            if (!log_fn && PyErr_Occurred()) goto error;
            PyObject *url_fn = PyDict_GetItemWithError(options, k_urlFn);
            if (!url_fn && PyErr_Occurred()) goto error;

            PyObject *includes_list = PyDict_GetItemWithError(include, k_includes);
            if (!includes_list) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "includes"); goto error; }

            Py_ssize_t n_includes = PyList_Check(includes_list) ? PyList_GET_SIZE(includes_list)
                                                                 : PyObject_Length(includes_list);
            for (Py_ssize_t ii = 0; ii < n_includes; ii++) {
                PyObject *inc = PyList_Check(includes_list) ? PyList_GET_ITEM(includes_list, ii)
                                                            : PySequence_GetItem(includes_list, ii);
                if (!inc) goto error;
                PyObject *inc_url = PyDict_GetItemWithError(inc, k_url);
                if (!inc_url) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "url"); goto error; }
                Py_INCREF(inc_url);

                PyObject *sys_flag = PyDict_GetItemWithError(inc, k_system);
                if (!sys_flag && PyErr_Occurred()) { Py_DECREF(inc_url); goto error; }
                int is_sys = sys_flag && PyObject_IsTrue(sys_flag);
                if (is_sys && system_prefix && system_prefix != Py_None) {
                    PyObject *nu = PyObject_CallFunctionObjArgs(g_url_file_relative, system_prefix, inc_url, NULL);
                    Py_DECREF(inc_url);
                    if (!nu) goto error;
                    inc_url = nu;
                } else if (url_fn && url_fn != Py_None) {
                    PyObject *nu = PyObject_CallOneArg(url_fn, inc_url);
                    Py_DECREF(inc_url);
                    if (!nu) goto error;
                    inc_url = nu;
                }

                /* Already included? */
                PyObject *gincs = PyDict_GetItemWithError(globals_, k_includes_global_name);
                if (!gincs && PyErr_Occurred()) { Py_DECREF(inc_url); goto error; }
                if (!gincs || !PyDict_Check(gincs)) {
                    gincs = PyDict_New();
                    if (!gincs) { Py_DECREF(inc_url); goto error; }
                    if (PyDict_SetItem(globals_, k_includes_global_name, gincs) < 0) {
                        Py_DECREF(gincs); Py_DECREF(inc_url); goto error;
                    }
                    Py_DECREF(gincs);
                    gincs = PyDict_GetItem(globals_, k_includes_global_name);
                }
                PyObject *seen = PyDict_GetItemWithError(gincs, inc_url);
                if (!seen && PyErr_Occurred()) { Py_DECREF(inc_url); goto error; }
                if (seen && PyObject_IsTrue(seen)) { Py_DECREF(inc_url); continue; }
                if (PyDict_SetItem(gincs, inc_url, Py_True) < 0) { Py_DECREF(inc_url); goto error; }

                /* Fetch */
                PyObject *include_text = NULL;
                if (fetch_fn && fetch_fn != Py_None) {
                    PyObject *req = Py_BuildValue("{s:O}", "url", inc_url);
                    if (!req) { Py_DECREF(inc_url); goto error; }
                    include_text = PyObject_CallOneArg(fetch_fn, req);
                    Py_DECREF(req);
                    if (!include_text) { PyErr_Clear(); include_text = NULL; }
                }
                if (!include_text || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    PyObject *us = PyObject_Str(inc_url);
                    const char *uss = us ? PyUnicode_AsUTF8(us) : "?";
                    raise_runtime_error(script, statement, "Include of \"%s\" failed", uss);
                    Py_XDECREF(us);
                    Py_DECREF(inc_url);
                    goto error;
                }

                /* parse_script(text, 1, url) */
                PyObject *one = PyLong_FromLong(1);
                PyObject *include_script = PyObject_CallFunctionObjArgs(g_parse_script, include_text, one, inc_url, NULL);
                Py_DECREF(one);
                Py_DECREF(include_text);
                if (!include_script) { Py_DECREF(inc_url); goto error; }

                if (is_sys) {
                    if (PyDict_SetItem(include_script, k_system, Py_True) < 0) {
                        Py_DECREF(include_script); Py_DECREF(inc_url); goto error;
                    }
                }

                /* include_options = options.copy(); urlFn = partial(url_file_relative, include_url) */
                PyObject *include_options = PyDict_Copy(options);
                if (!include_options) { Py_DECREF(include_script); Py_DECREF(inc_url); goto error; }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, inc_url, NULL);
                if (!new_url_fn) { Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(inc_url); goto error; }
                if (PyDict_SetItem(include_options, k_urlFn, new_url_fn) < 0) {
                    Py_DECREF(new_url_fn); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(inc_url); goto error;
                }
                Py_DECREF(new_url_fn);

                PyObject *inc_statements = PyDict_GetItemWithError(include_script, k_statements);
                if (!inc_statements) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(inc_url); goto error; }
                PyObject *exec_result = execute_script_helper(include_script, inc_statements, include_options, NULL);
                Py_DECREF(include_options);
                if (!exec_result) { Py_DECREF(include_script); Py_DECREF(inc_url); goto error; }
                Py_DECREF(exec_result);

                /* Lint */
                if (log_fn && log_fn != Py_None) {
                    PyObject *debug = PyDict_GetItemWithError(options, k_debug);
                    if (!debug && PyErr_Occurred()) { Py_DECREF(include_script); Py_DECREF(inc_url); goto error; }
                    if (debug && PyObject_IsTrue(debug)) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(g_lint_script, include_script, globals_, NULL);
                        if (!warnings) { Py_DECREF(include_script); Py_DECREF(inc_url); goto error; }
                        Py_ssize_t nw = PyObject_Length(warnings);
                        if (nw > 0) {
                            PyObject *prefix = PyUnicode_FromFormat("BareScript: Include \"%U\" static analysis... %zd warning%s:",
                                inc_url, nw, nw > 1 ? "s" : "");
                            if (prefix) { PyObject *r = PyObject_CallOneArg(log_fn, prefix); Py_DECREF(prefix); Py_XDECREF(r); }
                            for (Py_ssize_t wi = 0; wi < nw; wi++) {
                                PyObject *w = PySequence_GetItem(warnings, wi);
                                if (!w) break;
                                PyObject *m = PyUnicode_FromFormat("BareScript: %U", w);
                                Py_DECREF(w);
                                if (m) { PyObject *r = PyObject_CallOneArg(log_fn, m); Py_DECREF(m); Py_XDECREF(r); }
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }

                Py_DECREF(include_script);
                Py_DECREF(inc_url);
            }
            ix_statement++;
            continue;
        }

        /* label - just advance */
        ix_statement++;
    }

    result = Py_None; Py_INCREF(result);

cleanup:
    Py_XDECREF(label_indexes);
    return result;

error:
    Py_XDECREF(label_indexes);
    return NULL;
}

/* ---------------- Module entry: execute_script ---------------- */

static PyObject *py_execute_script(PyObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script, *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|O", kwlist, &script, &options)) return NULL;

    if (options == Py_None || options == NULL) {
        options = PyDict_New();
        if (!options) return NULL;
    } else {
        Py_INCREF(options);
    }

    PyObject *globals_ = PyDict_GetItemWithError(options, k_globals);
    if (!globals_ && PyErr_Occurred()) { Py_DECREF(options); return NULL; }
    if (!globals_) {
        globals_ = PyDict_New();
        if (!globals_) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, k_globals, globals_) < 0) { Py_DECREF(globals_); Py_DECREF(options); return NULL; }
        Py_DECREF(globals_);
        globals_ = PyDict_GetItem(options, k_globals);
    }

    /* Set the script function globals variables (only if not already present) */
    Py_ssize_t pos = 0;
    PyObject *fn_name, *fn_obj;
    while (PyDict_Next(g_SCRIPT_FUNCTIONS, &pos, &fn_name, &fn_obj)) {
        if (PyDict_Contains(globals_, fn_name) == 0) {
            if (PyDict_SetItem(globals_, fn_name, fn_obj) < 0) { Py_DECREF(options); return NULL; }
        }
    }

    /* statementCount = 0 */
    PyObject *zero = PyLong_FromLong(0);
    if (!zero || PyDict_SetItem(options, k_statementCount, zero) < 0) { Py_XDECREF(zero); Py_DECREF(options); return NULL; }
    Py_DECREF(zero);

    PyObject *statements = PyDict_GetItemWithError(script, k_statements);
    if (!statements) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements"); Py_DECREF(options); return NULL; }

    PyObject *result = execute_script_helper(script, statements, options, NULL);
    Py_DECREF(options);
    return result;
}

/* ---------------- Module entry: evaluate_expression ---------------- */

static PyObject *py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr, *options = Py_None, *locals_ = Py_None, *script = Py_None, *statement = Py_None;
    int builtins = 1;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|OOpOO", kwlist, &expr, &options, &locals_, &builtins, &script, &statement))
        return NULL;
    return evaluate_expression_inner(expr,
        (options == Py_None) ? NULL : options,
        (locals_ == Py_None) ? NULL : locals_,
        builtins,
        (script == Py_None) ? NULL : script,
        (statement == Py_None) ? NULL : statement);
}

/* ---------------- Module init ---------------- */

static PyMethodDef module_methods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS, "Execute a script"},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS, "Evaluate an expression"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "runtime_c", NULL, -1, module_methods,
};

#define INTERN_KEY(var, str) do { var = PyUnicode_InternFromString(str); if (!var) return NULL; } while (0)

PyMODINIT_FUNC PyInit_runtime_c(void) {
    PyDateTime_IMPORT;

    if (PyType_Ready(&ScriptFunctionType) < 0) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    INTERN_KEY(k_expr, "expr");
    INTERN_KEY(k_jump, "jump");
    INTERN_KEY(k_return_, "return");
    INTERN_KEY(k_function, "function");
    INTERN_KEY(k_include, "include");
    INTERN_KEY(k_label, "label");
    INTERN_KEY(k_name, "name");
    INTERN_KEY(k_args, "args");
    INTERN_KEY(k_statements, "statements");
    INTERN_KEY(k_lastArgArray, "lastArgArray");
    INTERN_KEY(k_number, "number");
    INTERN_KEY(k_string, "string");
    INTERN_KEY(k_variable, "variable");
    INTERN_KEY(k_binary, "binary");
    INTERN_KEY(k_unary, "unary");
    INTERN_KEY(k_group, "group");
    INTERN_KEY(k_left, "left");
    INTERN_KEY(k_right, "right");
    INTERN_KEY(k_op, "op");
    INTERN_KEY(k_url, "url");
    INTERN_KEY(k_includes, "includes");
    INTERN_KEY(k_system, "system");
    INTERN_KEY(k_globals, "globals");
    INTERN_KEY(k_statementCount, "statementCount");
    INTERN_KEY(k_maxStatements, "maxStatements");
    INTERN_KEY(k_systemPrefix, "systemPrefix");
    INTERN_KEY(k_fetchFn, "fetchFn");
    INTERN_KEY(k_logFn, "logFn");
    INTERN_KEY(k_urlFn, "urlFn");
    INTERN_KEY(k_debug, "debug");
    INTERN_KEY(k_scriptName, "scriptName");
    INTERN_KEY(k_lineNumber, "lineNumber");
    INTERN_KEY(k_enabled, "enabled");
    INTERN_KEY(k_scripts, "scripts");
    INTERN_KEY(k_covered, "covered");
    INTERN_KEY(k_script_field, "script");
    INTERN_KEY(k_count_field, "count");
    INTERN_KEY(k_statement_field, "statement");
    INTERN_KEY(k_null_str, "null");
    INTERN_KEY(k_false_str, "false");
    INTERN_KEY(k_true_str, "true");
    INTERN_KEY(k_if_str, "if");
    INTERN_KEY(k_coverage_global_name, "__barescriptCoverage");
    INTERN_KEY(k_includes_global_name, "__barescriptIncludes");

    g_empty_tuple = PyTuple_New(0);

    /* Import sibling modules */
    PyObject *runtime_mod = PyImport_ImportModule("bare_script.runtime");
    if (!runtime_mod) return NULL;
    g_BareScriptRuntimeError = PyObject_GetAttrString(runtime_mod, "BareScriptRuntimeError");
    Py_DECREF(runtime_mod);
    if (!g_BareScriptRuntimeError) return NULL;

    PyObject *value_mod = PyImport_ImportModule("bare_script.value");
    if (!value_mod) return NULL;
    g_ValueArgsError = PyObject_GetAttrString(value_mod, "ValueArgsError");
    g_value_boolean = PyObject_GetAttrString(value_mod, "value_boolean");
    g_value_compare = PyObject_GetAttrString(value_mod, "value_compare");
    g_value_normalize_datetime = PyObject_GetAttrString(value_mod, "value_normalize_datetime");
    g_value_round_number = PyObject_GetAttrString(value_mod, "value_round_number");
    g_value_string = PyObject_GetAttrString(value_mod, "value_string");
    Py_DECREF(value_mod);
    if (!g_ValueArgsError || !g_value_boolean || !g_value_compare || !g_value_normalize_datetime ||
        !g_value_round_number || !g_value_string) return NULL;

    PyObject *lib_mod = PyImport_ImportModule("bare_script.library");
    if (!lib_mod) return NULL;
    g_SCRIPT_FUNCTIONS = PyObject_GetAttrString(lib_mod, "SCRIPT_FUNCTIONS");
    g_EXPRESSION_FUNCTIONS = PyObject_GetAttrString(lib_mod, "EXPRESSION_FUNCTIONS");
    Py_DECREF(lib_mod);
    if (!g_SCRIPT_FUNCTIONS || !g_EXPRESSION_FUNCTIONS) return NULL;

    PyObject *options_mod = PyImport_ImportModule("bare_script.options");
    if (!options_mod) return NULL;
    g_url_file_relative = PyObject_GetAttrString(options_mod, "url_file_relative");
    Py_DECREF(options_mod);
    if (!g_url_file_relative) return NULL;

    PyObject *parser_mod = PyImport_ImportModule("bare_script.parser");
    if (!parser_mod) return NULL;
    g_parse_script = PyObject_GetAttrString(parser_mod, "parse_script");
    Py_DECREF(parser_mod);
    if (!g_parse_script) return NULL;

    PyObject *model_mod = PyImport_ImportModule("bare_script.model");
    if (!model_mod) return NULL;
    g_lint_script = PyObject_GetAttrString(model_mod, "lint_script");
    Py_DECREF(model_mod);
    if (!g_lint_script) return NULL;

    PyObject *ft_mod = PyImport_ImportModule("functools");
    if (!ft_mod) return NULL;
    g_functools_partial = PyObject_GetAttrString(ft_mod, "partial");
    Py_DECREF(ft_mod);
    if (!g_functools_partial) return NULL;

    g_default_max_statements = PyFloat_FromDouble(1e9);
    if (!g_default_max_statements) return NULL;

    return m;
}
