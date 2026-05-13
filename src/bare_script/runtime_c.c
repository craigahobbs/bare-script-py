/*
 * Licensed under the MIT License
 * https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE
 *
 * BareScript runtime — C implementation (CPython extension).
 *
 * This file is a port of runtime.py. runtime.py is the source of truth; this
 * file mirrors its semantics. Optimizations live below the porting layer.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* ---------- Module-level cached references ---------- */

static PyObject *g_EXPRESSION_FUNCTIONS = NULL;   /* dict */
static PyObject *g_SCRIPT_FUNCTIONS = NULL;       /* dict */
static PyObject *g_lint_script = NULL;
static PyObject *g_url_file_relative = NULL;
static PyObject *g_parse_script = NULL;
static PyObject *g_ValueArgsError = NULL;
static PyObject *g_value_boolean = NULL;
static PyObject *g_value_compare = NULL;
static PyObject *g_value_normalize_datetime = NULL;
static PyObject *g_value_round_number = NULL;
static PyObject *g_value_string = NULL;
static PyObject *g_BareScriptRuntimeError = NULL;
static PyObject *g_functools_partial = NULL;
static PyObject *g_datetime_date = NULL;
static PyObject *g_datetime_timedelta = NULL;
static PyObject *g_script_function_obj = NULL;    /* the C-level _script_function wrapper */

/* Cached interned strings */
static PyObject *S_globals;
static PyObject *S_statementCount;
static PyObject *S_maxStatements;
static PyObject *S_systemPrefix;
static PyObject *S_fetchFn;
static PyObject *S_logFn;
static PyObject *S_urlFn;
static PyObject *S_debug;
static PyObject *S_includes;
static PyObject *S_url;
static PyObject *S_system;
static PyObject *S_statements;
static PyObject *S_expr;
static PyObject *S_jump;
static PyObject *S_return_;
static PyObject *S_function;
static PyObject *S_include;
static PyObject *S_label;
static PyObject *S_name;
static PyObject *S_args;
static PyObject *S_lastArgArray;
static PyObject *S_binary;
static PyObject *S_unary;
static PyObject *S_group;
static PyObject *S_number;
static PyObject *S_string;
static PyObject *S_variable;
static PyObject *S_op;
static PyObject *S_left;
static PyObject *S_right;
static PyObject *S_scriptName;
static PyObject *S_lineNumber;
static PyObject *S_scripts;
static PyObject *S_covered;
static PyObject *S_script;
static PyObject *S_count;
static PyObject *S_statement;
static PyObject *S_enabled;
static PyObject *S_null;
static PyObject *S_true;
static PyObject *S_false;
static PyObject *S_if_;
static PyObject *S_coverage_global;   /* '__barescriptCoverage' */
static PyObject *S_includes_global;   /* '__barescriptIncludes' */
static PyObject *S_op_and;            /* '&&' */
static PyObject *S_op_or;             /* '||' */
static PyObject *S_op_plus;
static PyObject *S_op_minus;
static PyObject *S_op_mult;
static PyObject *S_op_div;
static PyObject *S_op_eq;
static PyObject *S_op_ne;
static PyObject *S_op_le;
static PyObject *S_op_lt;
static PyObject *S_op_ge;
static PyObject *S_op_gt;
static PyObject *S_op_mod;
static PyObject *S_op_pow;
static PyObject *S_op_bitand;
static PyObject *S_op_bitor;
static PyObject *S_op_bitxor;
static PyObject *S_op_shl;
static PyObject *S_op_shr;
static PyObject *S_op_not;
static PyObject *S_op_neg;
static PyObject *S_op_bitnot;
static PyObject *S_milliseconds;

/* Default max statements: 1e9 */
static PyObject *g_default_max_statements = NULL;

/* ---------- Forward declarations ---------- */

static PyObject *evaluate_expression_impl(PyObject *expr, PyObject *options, PyObject *locals_,
                                          int builtins, PyObject *script, PyObject *statement);
static PyObject *execute_script_helper(PyObject *script, PyObject *statements,
                                       PyObject *options, PyObject *locals_);

/* ---------- Helpers ---------- */

/* Raise BareScriptRuntimeError(script, statement, message). Always returns NULL. */
static PyObject *raise_runtime_error(PyObject *script, PyObject *statement, PyObject *message) {
    PyObject *s = script ? script : Py_None;
    PyObject *st = statement ? statement : Py_None;
    PyObject *exc = PyObject_CallFunctionObjArgs(g_BareScriptRuntimeError, s, st, message, NULL);
    if (exc != NULL) {
        PyErr_SetObject(g_BareScriptRuntimeError, exc);
        Py_DECREF(exc);
    }
    return NULL;
}

static PyObject *raise_runtime_error_fmt(PyObject *script, PyObject *statement, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    PyObject *msg = PyUnicode_FromFormatV(fmt, ap);
    va_end(ap);
    if (msg == NULL) return NULL;
    PyObject *result = raise_runtime_error(script, statement, msg);
    Py_DECREF(msg);
    return result;
}

/* True if value is "number-like": int or float, excluding bool. */
static inline int is_number_strict(PyObject *v) {
    if (PyBool_Check(v)) return 0;
    return PyLong_Check(v) || PyFloat_Check(v);
}

/* True if value is "int-like" — a number that equals its integer truncation. */
static int is_int_like(PyObject *v, long long *out_ll, PyObject **out_pylong) {
    /* On success, sets either out_ll (if it fits) or out_pylong (new ref) */
    if (PyBool_Check(v)) return 0;
    if (PyLong_Check(v)) {
        Py_INCREF(v);
        *out_pylong = v;
        return 1;
    }
    if (PyFloat_Check(v)) {
        double d = PyFloat_AsDouble(v);
        if (d != (double)(long long)d) {
            /* not an integer value */
            /* But also accommodate values outside long long but still integral — fall back to PyLong */
            /* Compare value with int(value) via Python int conversion */
            PyObject *as_long = PyNumber_Long(v);
            if (as_long == NULL) { PyErr_Clear(); return 0; }
            PyObject *as_float_back = PyNumber_Float(as_long);
            if (as_float_back == NULL) { Py_DECREF(as_long); PyErr_Clear(); return 0; }
            double back = PyFloat_AsDouble(as_float_back);
            Py_DECREF(as_float_back);
            if (back == d) {
                *out_pylong = as_long;
                return 1;
            }
            Py_DECREF(as_long);
            return 0;
        }
        *out_ll = (long long)d;
        return 2;
    }
    return 0;
}

/* True if value is a datetime.date (including datetime). */
static inline int is_datetime_date(PyObject *v) {
    int r = PyObject_IsInstance(v, g_datetime_date);
    if (r < 0) { PyErr_Clear(); return 0; }
    return r;
}

/* Call value_boolean(v) and return Python truth (1/0). On failure, returns -1. */
static int call_value_boolean(PyObject *v) {
    /* Fast paths matching value_boolean semantics */
    if (v == Py_None) return 0;
    if (PyBool_Check(v)) return (v == Py_True) ? 1 : 0;
    if (PyUnicode_Check(v)) return PyUnicode_GET_LENGTH(v) != 0;
    if (PyLong_Check(v)) {
        int r = PyObject_IsTrue(v);
        return r;
    }
    if (PyFloat_Check(v)) {
        double d = PyFloat_AsDouble(v);
        return d != 0.0 ? 1 : 0;
    }
    if (PyList_Check(v)) return PyList_GET_SIZE(v) != 0 ? 1 : 0;
    /* Everything else non-null is true */
    return 1;
}

/* Call value_compare(a, b) returning <0/0/>0. On error returns -2. */
static int call_value_compare(PyObject *a, PyObject *b) {
    PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, a, b, NULL);
    if (r == NULL) return -2;
    long lv = PyLong_AsLong(r);
    Py_DECREF(r);
    if (lv == -1 && PyErr_Occurred()) return -2;
    return (int)lv;
}

/* Increment options['statementCount'] by 1, checking maxStatements limit.
 * Returns 0 on success, -1 on error (raised). Raises BareScriptRuntimeError
 * with given script/statement on overflow. */
static int bump_statement_count(PyObject *options, PyObject *script, PyObject *statement) {
    PyObject *count = PyDict_GetItemWithError(options, S_statementCount);
    PyObject *new_count;
    if (count == NULL) {
        if (PyErr_Occurred()) return -1;
        new_count = PyLong_FromLong(1);
    } else {
        PyObject *one = PyLong_FromLong(1);
        new_count = PyNumber_Add(count, one);
        Py_DECREF(one);
    }
    if (new_count == NULL) return -1;
    if (PyDict_SetItem(options, S_statementCount, new_count) < 0) {
        Py_DECREF(new_count);
        return -1;
    }

    /* Check max */
    PyObject *max = PyDict_GetItemWithError(options, S_maxStatements);
    if (max == NULL && PyErr_Occurred()) { Py_DECREF(new_count); return -1; }
    if (max == NULL) max = g_default_max_statements;

    int cmp_max_gt_zero = PyObject_RichCompareBool(max, PyLong_FromLong(0), Py_GT);
    /* Above leaks a long(0), but it's a small int; in fact PyLong_FromLong(0) returns a cached small int, but we still need to DECREF. Redo with cached: */
    /* Simpler approach: */
    Py_DECREF(new_count);
    /* Now reread to compare properly */
    PyObject *zero = PyLong_FromLong(0);
    cmp_max_gt_zero = PyObject_RichCompareBool(max, zero, Py_GT);
    Py_DECREF(zero);
    if (cmp_max_gt_zero < 0) return -1;
    if (!cmp_max_gt_zero) return 0;

    PyObject *cur_count = PyDict_GetItemWithError(options, S_statementCount);
    if (cur_count == NULL) return -1;
    int cmp = PyObject_RichCompareBool(cur_count, max, Py_GT);
    if (cmp < 0) return -1;
    if (cmp) {
        PyObject *msg = PyUnicode_FromFormat("Exceeded maximum script statements (%S)", max);
        if (msg == NULL) return -1;
        raise_runtime_error(script, statement, msg);
        Py_DECREF(msg);
        return -1;
    }
    return 0;
}

/* Record statement coverage. Returns 0 on success / -1 on error. */
static int record_statement_coverage(PyObject *script, PyObject *statement,
                                     PyObject *statement_key, PyObject *coverage_global) {
    PyObject *script_name = PyDict_GetItemWithError(script, S_scriptName);
    if (script_name == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    PyObject *stmt_body = PyDict_GetItemWithError(statement, statement_key);
    if (stmt_body == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    PyObject *lineno = PyDict_GetItemWithError(stmt_body, S_lineNumber);
    if (lineno == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }

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
        scripts = PyDict_GetItemWithError(coverage_global, S_scripts);
        if (scripts == NULL) return -1;
    }
    PyObject *script_cov = PyDict_GetItemWithError(scripts, script_name);
    if (script_cov == NULL) {
        if (PyErr_Occurred()) return -1;
        script_cov = PyDict_New();
        if (script_cov == NULL) return -1;
        if (PyDict_SetItem(script_cov, S_script, script) < 0) goto cov_fail;
        PyObject *empty = PyDict_New();
        if (empty == NULL) goto cov_fail;
        if (PyDict_SetItem(script_cov, S_covered, empty) < 0) { Py_DECREF(empty); goto cov_fail; }
        Py_DECREF(empty);
        if (PyDict_SetItem(scripts, script_name, script_cov) < 0) goto cov_fail;
        Py_DECREF(script_cov);
        script_cov = PyDict_GetItemWithError(scripts, script_name);
        if (script_cov == NULL) return -1;
        goto cov_have;
    cov_fail:
        Py_DECREF(script_cov);
        return -1;
    }
cov_have: ;
    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) return -1;
    PyObject *covered = PyDict_GetItemWithError(script_cov, S_covered);
    if (covered == NULL) { Py_DECREF(lineno_str); return -1; }
    PyObject *cov_stmt = PyDict_GetItemWithError(covered, lineno_str);
    if (cov_stmt == NULL) {
        if (PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
        cov_stmt = PyDict_New();
        if (cov_stmt == NULL) { Py_DECREF(lineno_str); return -1; }
        if (PyDict_SetItem(cov_stmt, S_statement, statement) < 0 ||
            PyDict_SetItem(cov_stmt, S_count, PyLong_FromLong(0)) < 0) {
            Py_DECREF(cov_stmt); Py_DECREF(lineno_str); return -1;
        }
        /* Note above leaks the long(0) intentionally — small int cached, no real leak.
         * Actually PyDict_SetItem doesn't steal. Let's redo cleanly: */
        /* We over-incremented. Replace clean: */
        Py_DECREF(cov_stmt);
        cov_stmt = PyDict_New();
        if (cov_stmt == NULL) { Py_DECREF(lineno_str); return -1; }
        PyObject *zero = PyLong_FromLong(0);
        if (PyDict_SetItem(cov_stmt, S_statement, statement) < 0 ||
            PyDict_SetItem(cov_stmt, S_count, zero) < 0) {
            Py_DECREF(zero); Py_DECREF(cov_stmt); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(zero);
        if (PyDict_SetItem(covered, lineno_str, cov_stmt) < 0) {
            Py_DECREF(cov_stmt); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(cov_stmt);
        cov_stmt = PyDict_GetItemWithError(covered, lineno_str);
        if (cov_stmt == NULL) { Py_DECREF(lineno_str); return -1; }
    }
    Py_DECREF(lineno_str);
    PyObject *count = PyDict_GetItemWithError(cov_stmt, S_count);
    if (count == NULL) return -1;
    PyObject *one = PyLong_FromLong(1);
    PyObject *new_count = PyNumber_Add(count, one);
    Py_DECREF(one);
    if (new_count == NULL) return -1;
    if (PyDict_SetItem(cov_stmt, S_count, new_count) < 0) {
        Py_DECREF(new_count);
        return -1;
    }
    Py_DECREF(new_count);
    return 0;
}

/* Get the single key of a single-key dict (statement node).
 * Returns a borrowed reference to the key, or NULL with error set. */
static PyObject *first_key(PyObject *d) {
    if (!PyDict_Check(d)) {
        PyErr_SetString(PyExc_TypeError, "expected dict");
        return NULL;
    }
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    if (PyDict_Next(d, &pos, &key, &value)) {
        return key;
    }
    PyErr_SetString(PyExc_RuntimeError, "empty dict where statement expected");
    return NULL;
}

/* ---------- _script_function (Python-callable) ----------
 * Signature: _script_function(script, function, args, options)
 */
static PyObject *py_script_function(PyObject *self, PyObject *args_tuple) {
    PyObject *script, *function, *args, *options;
    if (!PyArg_UnpackTuple(args_tuple, "_script_function", 4, 4,
                           &script, &function, &args, &options)) {
        return NULL;
    }
    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    PyObject *func_args = PyDict_GetItemWithError(function, S_args);
    if (func_args == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
    if (func_args != NULL) {
        Py_ssize_t args_length = PyObject_Length(args);
        if (args_length < 0) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t func_args_length = PyObject_Length(func_args);
        if (func_args_length < 0) { Py_DECREF(func_locals); return NULL; }

        /* ix_arg_last = function.get('lastArgArray', None) and (func_args_length - 1) */
        PyObject *last_flag = PyDict_GetItemWithError(function, S_lastArgArray);
        if (last_flag == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t ix_arg_last = -1;
        if (last_flag != NULL && PyObject_IsTrue(last_flag) == 1) {
            ix_arg_last = func_args_length - 1;
        }
        for (Py_ssize_t ix_arg = 0; ix_arg < func_args_length; ix_arg++) {
            PyObject *arg_name = PySequence_GetItem(func_args, ix_arg);
            if (arg_name == NULL) { Py_DECREF(func_locals); return NULL; }
            PyObject *value = NULL;
            if (ix_arg < args_length) {
                if (ix_arg != ix_arg_last) {
                    value = PySequence_GetItem(args, ix_arg);
                } else {
                    /* args[ix_arg:] */
                    value = PySequence_GetSlice(args, ix_arg, args_length);
                }
            } else {
                if (ix_arg == ix_arg_last) {
                    value = PyList_New(0);
                } else {
                    Py_INCREF(Py_None);
                    value = Py_None;
                }
            }
            if (value == NULL) { Py_DECREF(arg_name); Py_DECREF(func_locals); return NULL; }
            if (PyDict_SetItem(func_locals, arg_name, value) < 0) {
                Py_DECREF(arg_name); Py_DECREF(value); Py_DECREF(func_locals); return NULL;
            }
            Py_DECREF(arg_name);
            Py_DECREF(value);
        }
    }

    PyObject *stmts = PyDict_GetItemWithError(function, S_statements);
    if (stmts == NULL) { Py_DECREF(func_locals); if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements"); return NULL; }
    PyObject *result = execute_script_helper(script, stmts, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}

/* ---------- evaluate_expression core ---------- */

/* Returns new reference, or NULL with error set. */
static PyObject *evaluate_expression_impl(PyObject *expr, PyObject *options, PyObject *locals_,
                                          int builtins, PyObject *script, PyObject *statement) {
    if (!PyDict_Check(expr)) {
        PyErr_SetString(PyExc_TypeError, "expr must be a dict");
        return NULL;
    }
    PyObject *expr_key = first_key(expr);
    if (expr_key == NULL) return NULL;

    PyObject *globals_ = NULL;
    if (options != NULL && options != Py_None) {
        globals_ = PyDict_GetItemWithError(options, S_globals);
        if (globals_ == NULL && PyErr_Occurred()) return NULL;
    }

    /* Number */
    if (PyUnicode_Compare(expr_key, S_number) == 0) {
        PyObject *v = PyDict_GetItemWithError(expr, S_number);
        if (v == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "number"); return NULL; }
        Py_INCREF(v);
        return v;
    }
    /* String */
    if (PyUnicode_Compare(expr_key, S_string) == 0) {
        PyObject *v = PyDict_GetItemWithError(expr, S_string);
        if (v == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "string"); return NULL; }
        Py_INCREF(v);
        return v;
    }

    /* Variable */
    if (PyUnicode_Compare(expr_key, S_variable) == 0) {
        PyObject *var_name = PyDict_GetItemWithError(expr, S_variable);
        if (var_name == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "variable"); return NULL; }
        if (PyUnicode_Compare(var_name, S_null) == 0) Py_RETURN_NONE;
        if (PyUnicode_Compare(var_name, S_false) == 0) Py_RETURN_FALSE;
        if (PyUnicode_Compare(var_name, S_true) == 0) Py_RETURN_TRUE;
        if (locals_ != NULL && locals_ != Py_None) {
            PyObject *v = PyDict_GetItemWithError(locals_, var_name);
            if (v != NULL) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        if (globals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(globals_, var_name);
            if (v != NULL) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        Py_RETURN_NONE;
    }

    /* Function */
    if (PyUnicode_Compare(expr_key, S_function) == 0) {
        PyObject *fn = PyDict_GetItemWithError(expr, S_function);
        if (fn == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "function"); return NULL; }
        PyObject *func_name = PyDict_GetItemWithError(fn, S_name);
        if (func_name == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "name"); return NULL; }

        /* "if" built-in */
        if (PyUnicode_Compare(func_name, S_if_) == 0) {
            PyObject *args_expr = PyDict_GetItemWithError(fn, S_args);
            if (args_expr == NULL && PyErr_Occurred()) return NULL;
            Py_ssize_t alen = 0;
            if (args_expr != NULL) {
                alen = PyObject_Length(args_expr);
                if (alen < 0) return NULL;
            }
            PyObject *value_expr = (args_expr != NULL && alen >= 1) ? PyList_GetItem(args_expr, 0) : NULL;
            PyObject *true_expr  = (args_expr != NULL && alen >= 2) ? PyList_GetItem(args_expr, 1) : NULL;
            PyObject *false_expr = (args_expr != NULL && alen >= 3) ? PyList_GetItem(args_expr, 2) : NULL;
            PyObject *value;
            if (value_expr != NULL) {
                value = evaluate_expression_impl(value_expr, options, locals_, builtins, script, statement);
                if (value == NULL) return NULL;
            } else {
                Py_INCREF(Py_False);
                value = Py_False;
            }
            int b = call_value_boolean(value);
            Py_DECREF(value);
            if (b < 0) return NULL;
            PyObject *result_expr = b ? true_expr : false_expr;
            if (result_expr != NULL) {
                return evaluate_expression_impl(result_expr, options, locals_, builtins, script, statement);
            }
            Py_RETURN_NONE;
        }

        /* Compute the function arguments */
        PyObject *func_args = NULL;
        PyObject *args_list = PyDict_GetItemWithError(fn, S_args);
        if (args_list == NULL && PyErr_Occurred()) return NULL;
        if (args_list != NULL) {
            Py_ssize_t n = PyObject_Length(args_list);
            if (n < 0) return NULL;
            func_args = PyList_New(n);
            if (func_args == NULL) return NULL;
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *arg_expr = PyList_GetItem(args_list, i);
                PyObject *v = evaluate_expression_impl(arg_expr, options, locals_, builtins, script, statement);
                if (v == NULL) { Py_DECREF(func_args); return NULL; }
                PyList_SET_ITEM(func_args, i, v); /* steals ref */
            }
        }

        /* Resolve function */
        PyObject *func_value = NULL;
        if (locals_ != NULL && locals_ != Py_None) {
            func_value = PyDict_GetItemWithError(locals_, func_name);
            if (func_value == NULL && PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
        }
        if (func_value == NULL && globals_ != NULL) {
            func_value = PyDict_GetItemWithError(globals_, func_name);
            if (func_value == NULL && PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
        }
        if (func_value == NULL && builtins) {
            func_value = PyDict_GetItemWithError(g_EXPRESSION_FUNCTIONS, func_name);
            if (func_value == NULL && PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
        }
        if (func_value == NULL) {
            Py_XDECREF(func_args);
            return raise_runtime_error_fmt(script, statement,
                                           "Undefined function \"%U\"", func_name);
        }
        Py_INCREF(func_value);

        /* Call with (func_args, options) — pass None if no args */
        PyObject *call_args = func_args ? func_args : Py_None;
        if (func_args == NULL) Py_INCREF(Py_None);
        PyObject *opts = options ? options : Py_None;
        PyObject *result = PyObject_CallFunctionObjArgs(func_value, call_args, opts, NULL);
        Py_DECREF(func_value);
        if (call_args != NULL && func_args != NULL) Py_DECREF(func_args);
        else Py_DECREF(Py_None);

        if (result != NULL) return result;

        /* Exception handling */
        if (PyErr_ExceptionMatches(g_BareScriptRuntimeError)) return NULL;
        PyObject *etype, *evalue, *etb;
        PyErr_Fetch(&etype, &evalue, &etb);
        PyErr_NormalizeException(&etype, &evalue, &etb);

        /* Log if options['debug'] and 'logFn' in options */
        if (options != NULL && options != Py_None && PyDict_Check(options)) {
            PyObject *debug = PyDict_GetItemWithError(options, S_debug);
            if (debug == NULL && PyErr_Occurred()) { Py_XDECREF(etype); Py_XDECREF(evalue); Py_XDECREF(etb); return NULL; }
            int is_debug = debug != NULL && PyObject_IsTrue(debug) == 1;
            int has_log = PyDict_Contains(options, S_logFn);
            if (has_log < 0) { Py_XDECREF(etype); Py_XDECREF(evalue); Py_XDECREF(etb); return NULL; }
            if (is_debug && has_log) {
                PyObject *logfn = PyDict_GetItemWithError(options, S_logFn);
                if (logfn != NULL) {
                    PyObject *err_str = evalue ? PyObject_Str(evalue) : PyUnicode_FromString("");
                    if (err_str != NULL) {
                        PyObject *msg = PyUnicode_FromFormat("BareScript: Function \"%U\" failed with error: %U", func_name, err_str);
                        Py_DECREF(err_str);
                        if (msg != NULL) {
                            PyObject *r = PyObject_CallOneArg(logfn, msg);
                            Py_XDECREF(r);
                            Py_DECREF(msg);
                            if (PyErr_Occurred()) PyErr_Clear();
                        }
                    }
                }
            }
        }

        /* ValueArgsError → return its return_value */
        if (etype != NULL && PyType_IsSubtype((PyTypeObject *)etype, (PyTypeObject *)g_ValueArgsError)) {
            PyObject *rv = PyObject_GetAttrString(evalue, "return_value");
            Py_XDECREF(etype); Py_XDECREF(evalue); Py_XDECREF(etb);
            if (rv == NULL) {
                PyErr_Clear();
                Py_RETURN_NONE;
            }
            return rv;
        }
        Py_XDECREF(etype); Py_XDECREF(evalue); Py_XDECREF(etb);
        Py_RETURN_NONE;
    }

    /* Binary */
    if (PyUnicode_Compare(expr_key, S_binary) == 0) {
        PyObject *bin = PyDict_GetItemWithError(expr, S_binary);
        if (bin == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "binary"); return NULL; }
        PyObject *bin_op = PyDict_GetItemWithError(bin, S_op);
        if (bin_op == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "op"); return NULL; }
        PyObject *left_expr = PyDict_GetItemWithError(bin, S_left);
        if (left_expr == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "left"); return NULL; }
        PyObject *right_expr = PyDict_GetItemWithError(bin, S_right);
        if (right_expr == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "right"); return NULL; }
        PyObject *left_value = evaluate_expression_impl(left_expr, options, locals_, builtins, script, statement);
        if (left_value == NULL) return NULL;

        /* && */
        if (PyUnicode_Compare(bin_op, S_op_and) == 0) {
            int b = call_value_boolean(left_value);
            if (b < 0) { Py_DECREF(left_value); return NULL; }
            if (!b) return left_value;
            Py_DECREF(left_value);
            return evaluate_expression_impl(right_expr, options, locals_, builtins, script, statement);
        }
        /* || */
        if (PyUnicode_Compare(bin_op, S_op_or) == 0) {
            int b = call_value_boolean(left_value);
            if (b < 0) { Py_DECREF(left_value); return NULL; }
            if (b) return left_value;
            Py_DECREF(left_value);
            return evaluate_expression_impl(right_expr, options, locals_, builtins, script, statement);
        }

        PyObject *right_value = evaluate_expression_impl(right_expr, options, locals_, builtins, script, statement);
        if (right_value == NULL) { Py_DECREF(left_value); return NULL; }

        PyObject *result = NULL;

        if (PyUnicode_Compare(bin_op, S_op_plus) == 0) {
            int l_num = is_number_strict(left_value);
            int r_num = is_number_strict(right_value);
            int l_str = PyUnicode_Check(left_value);
            int r_str = PyUnicode_Check(right_value);
            if (l_num && r_num) {
                result = PyNumber_Add(left_value, right_value);
            } else if (l_str && r_str) {
                result = PyUnicode_Concat(left_value, right_value);
            } else if (l_str) {
                PyObject *rs = PyObject_CallOneArg(g_value_string, right_value);
                if (rs != NULL) { result = PyUnicode_Concat(left_value, rs); Py_DECREF(rs); }
            } else if (r_str) {
                PyObject *ls = PyObject_CallOneArg(g_value_string, left_value);
                if (ls != NULL) { result = PyUnicode_Concat(ls, right_value); Py_DECREF(ls); }
            } else if (is_datetime_date(left_value) && r_num) {
                PyObject *ldt = PyObject_CallOneArg(g_value_normalize_datetime, left_value);
                if (ldt != NULL) {
                    PyObject *td = PyObject_CallFunction(g_datetime_timedelta, "OO", S_milliseconds == NULL ? Py_None : Py_None, right_value);
                    /* Need keyword arg: timedelta(milliseconds=right_value) */
                    Py_XDECREF(td);
                    PyObject *kwargs = PyDict_New();
                    if (kwargs != NULL) {
                        PyDict_SetItem(kwargs, S_milliseconds, right_value);
                        PyObject *empty = PyTuple_New(0);
                        td = PyObject_Call(g_datetime_timedelta, empty, kwargs);
                        Py_DECREF(empty); Py_DECREF(kwargs);
                        if (td != NULL) {
                            result = PyNumber_Add(ldt, td);
                            Py_DECREF(td);
                        }
                    }
                    Py_DECREF(ldt);
                }
            } else if (l_num && is_datetime_date(right_value)) {
                PyObject *rdt = PyObject_CallOneArg(g_value_normalize_datetime, right_value);
                if (rdt != NULL) {
                    PyObject *kwargs = PyDict_New();
                    if (kwargs != NULL) {
                        PyDict_SetItem(kwargs, S_milliseconds, left_value);
                        PyObject *empty = PyTuple_New(0);
                        PyObject *td = PyObject_Call(g_datetime_timedelta, empty, kwargs);
                        Py_DECREF(empty); Py_DECREF(kwargs);
                        if (td != NULL) {
                            result = PyNumber_Add(rdt, td);
                            Py_DECREF(td);
                        }
                    }
                    Py_DECREF(rdt);
                }
            }
            goto binary_done;
        }

        if (PyUnicode_Compare(bin_op, S_op_minus) == 0) {
            if (is_number_strict(left_value) && is_number_strict(right_value)) {
                result = PyNumber_Subtract(left_value, right_value);
            } else if (is_datetime_date(left_value) && is_datetime_date(right_value)) {
                PyObject *ldt = PyObject_CallOneArg(g_value_normalize_datetime, left_value);
                PyObject *rdt = ldt ? PyObject_CallOneArg(g_value_normalize_datetime, right_value) : NULL;
                if (ldt && rdt) {
                    PyObject *diff = PyNumber_Subtract(ldt, rdt);
                    if (diff != NULL) {
                        PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                        Py_DECREF(diff);
                        if (secs != NULL) {
                            PyObject *thousand = PyLong_FromLong(1000);
                            PyObject *ms = PyNumber_Multiply(secs, thousand);
                            Py_DECREF(thousand); Py_DECREF(secs);
                            if (ms != NULL) {
                                PyObject *zero = PyLong_FromLong(0);
                                result = PyObject_CallFunctionObjArgs(g_value_round_number, ms, zero, NULL);
                                Py_DECREF(zero); Py_DECREF(ms);
                            }
                        }
                    }
                }
                Py_XDECREF(ldt); Py_XDECREF(rdt);
            }
            goto binary_done;
        }

        if (PyUnicode_Compare(bin_op, S_op_mult) == 0) {
            if (is_number_strict(left_value) && is_number_strict(right_value))
                result = PyNumber_Multiply(left_value, right_value);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_div) == 0) {
            if (is_number_strict(left_value) && is_number_strict(right_value))
                result = PyNumber_TrueDivide(left_value, right_value);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_eq) == 0) {
            int c = call_value_compare(left_value, right_value);
            if (c == -2) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            result = (c == 0) ? Py_True : Py_False; Py_INCREF(result);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_ne) == 0) {
            int c = call_value_compare(left_value, right_value);
            if (c == -2) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            result = (c != 0) ? Py_True : Py_False; Py_INCREF(result);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_le) == 0) {
            int c = call_value_compare(left_value, right_value);
            if (c == -2) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            result = (c <= 0) ? Py_True : Py_False; Py_INCREF(result);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_lt) == 0) {
            int c = call_value_compare(left_value, right_value);
            if (c == -2) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            result = (c < 0) ? Py_True : Py_False; Py_INCREF(result);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_ge) == 0) {
            int c = call_value_compare(left_value, right_value);
            if (c == -2) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            result = (c >= 0) ? Py_True : Py_False; Py_INCREF(result);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_gt) == 0) {
            int c = call_value_compare(left_value, right_value);
            if (c == -2) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            result = (c > 0) ? Py_True : Py_False; Py_INCREF(result);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_mod) == 0) {
            if (is_number_strict(left_value) && is_number_strict(right_value))
                result = PyNumber_Remainder(left_value, right_value);
            goto binary_done;
        }
        if (PyUnicode_Compare(bin_op, S_op_pow) == 0) {
            if (is_number_strict(left_value) && is_number_strict(right_value))
                result = PyNumber_Power(left_value, right_value, Py_None);
            goto binary_done;
        }

        /* Bitwise: both must be number AND int-valued */
        int do_int_op = 0;
        PyObject *lint = NULL, *rint = NULL;
        long long llv = 0, rlv = 0;
        if (PyUnicode_Compare(bin_op, S_op_bitand) == 0 ||
            PyUnicode_Compare(bin_op, S_op_bitor) == 0 ||
            PyUnicode_Compare(bin_op, S_op_bitxor) == 0 ||
            PyUnicode_Compare(bin_op, S_op_shl) == 0 ||
            PyUnicode_Compare(bin_op, S_op_shr) == 0) {
            if (is_number_strict(left_value) && is_number_strict(right_value)) {
                int la = is_int_like(left_value, &llv, &lint);
                int ra = is_int_like(right_value, &rlv, &rint);
                if (la && ra) {
                    if (la == 2) { lint = PyLong_FromLongLong(llv); }
                    if (ra == 2) { rint = PyLong_FromLongLong(rlv); }
                    if (lint && rint) {
                        if (PyUnicode_Compare(bin_op, S_op_bitand) == 0) result = PyNumber_And(lint, rint);
                        else if (PyUnicode_Compare(bin_op, S_op_bitor) == 0) result = PyNumber_Or(lint, rint);
                        else if (PyUnicode_Compare(bin_op, S_op_bitxor) == 0) result = PyNumber_Xor(lint, rint);
                        else if (PyUnicode_Compare(bin_op, S_op_shl) == 0) result = PyNumber_Lshift(lint, rint);
                        else result = PyNumber_Rshift(lint, rint);
                    }
                }
                Py_XDECREF(lint); Py_XDECREF(rint);
                do_int_op = 1;
            } else {
                do_int_op = 1;
            }
        }
        if (do_int_op) goto binary_done;

        /* Unknown op or invalid types fall through to None */
binary_done:
        Py_DECREF(left_value);
        Py_DECREF(right_value);
        if (result == NULL && !PyErr_Occurred()) Py_RETURN_NONE;
        return result;
    }

    /* Unary */
    if (PyUnicode_Compare(expr_key, S_unary) == 0) {
        PyObject *u = PyDict_GetItemWithError(expr, S_unary);
        if (u == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "unary"); return NULL; }
        PyObject *op = PyDict_GetItemWithError(u, S_op);
        if (op == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "op"); return NULL; }
        PyObject *sub = PyDict_GetItemWithError(u, S_expr);
        if (sub == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "expr"); return NULL; }
        PyObject *value = evaluate_expression_impl(sub, options, locals_, builtins, script, statement);
        if (value == NULL) return NULL;
        PyObject *result = NULL;
        if (PyUnicode_Compare(op, S_op_not) == 0) {
            int b = call_value_boolean(value);
            Py_DECREF(value);
            if (b < 0) return NULL;
            result = b ? Py_False : Py_True;
            Py_INCREF(result);
            return result;
        }
        if (PyUnicode_Compare(op, S_op_neg) == 0) {
            if (is_number_strict(value)) result = PyNumber_Negative(value);
            Py_DECREF(value);
            if (result != NULL) return result;
            Py_RETURN_NONE;
        }
        /* '~' */
        if (is_number_strict(value)) {
            long long lv = 0; PyObject *iv = NULL;
            int a = is_int_like(value, &lv, &iv);
            if (a) {
                if (a == 2) iv = PyLong_FromLongLong(lv);
                if (iv) {
                    result = PyNumber_Invert(iv);
                    Py_DECREF(iv);
                }
            }
        }
        Py_DECREF(value);
        if (result != NULL) return result;
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }

    /* group */
    if (PyUnicode_Compare(expr_key, S_group) == 0) {
        PyObject *g = PyDict_GetItemWithError(expr, S_group);
        if (g == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "group"); return NULL; }
        return evaluate_expression_impl(g, options, locals_, builtins, script, statement);
    }

    PyErr_Format(PyExc_RuntimeError, "Unknown expression key: %U", expr_key);
    return NULL;
}

/* ---------- execute_script_helper ---------- */

static PyObject *execute_script_helper(PyObject *script, PyObject *statements,
                                       PyObject *options, PyObject *locals_) {
    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "globals"); return NULL; }

    PyObject *label_indexes = NULL;
    Py_ssize_t statements_length = PyList_Check(statements) ? PyList_GET_SIZE(statements) : PyObject_Length(statements);
    if (statements_length < 0) return NULL;
    Py_ssize_t ix_statement = 0;

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_GET_ITEM(statements, ix_statement);
        PyObject *statement_key = first_key(statement);
        if (statement_key == NULL) { Py_XDECREF(label_indexes); return NULL; }

        if (bump_statement_count(options, script, statement) < 0) {
            Py_XDECREF(label_indexes);
            return NULL;
        }

        /* Coverage */
        PyObject *coverage_global = PyDict_GetItemWithError(globals_, S_coverage_global);
        if (coverage_global == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
        int has_coverage = 0;
        if (coverage_global != NULL && PyDict_Check(coverage_global)) {
            PyObject *enabled = PyDict_GetItemWithError(coverage_global, S_enabled);
            if (enabled == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            int en = enabled != NULL && PyObject_IsTrue(enabled) == 1;
            PyObject *sysflag = PyDict_GetItemWithError(script, S_system);
            if (sysflag == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            int sysv = sysflag != NULL && PyObject_IsTrue(sysflag) == 1;
            has_coverage = en && !sysv;
        }
        if (has_coverage) {
            if (record_statement_coverage(script, statement, statement_key, coverage_global) < 0) {
                Py_XDECREF(label_indexes);
                return NULL;
            }
        }

        if (PyUnicode_Compare(statement_key, S_expr) == 0) {
            PyObject *expr_node = PyDict_GetItemWithError(statement, S_expr);
            if (expr_node == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *expr_inner = PyDict_GetItemWithError(expr_node, S_expr);
            if (expr_inner == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *value = evaluate_expression_impl(expr_inner, options, locals_, 0, script, statement);
            if (value == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *expr_name = PyDict_GetItemWithError(expr_node, S_name);
            if (expr_name == NULL && PyErr_Occurred()) { Py_DECREF(value); Py_XDECREF(label_indexes); return NULL; }
            if (expr_name != NULL) {
                PyObject *target = (locals_ != NULL && locals_ != Py_None) ? locals_ : globals_;
                if (PyDict_SetItem(target, expr_name, value) < 0) {
                    Py_DECREF(value); Py_XDECREF(label_indexes); return NULL;
                }
            }
            Py_DECREF(value);
        }
        else if (PyUnicode_Compare(statement_key, S_jump) == 0) {
            PyObject *jump_node = PyDict_GetItemWithError(statement, S_jump);
            if (jump_node == NULL) { Py_XDECREF(label_indexes); return NULL; }
            int do_jump = 1;
            int has_expr = PyDict_Contains(jump_node, S_expr);
            if (has_expr < 0) { Py_XDECREF(label_indexes); return NULL; }
            if (has_expr) {
                PyObject *je = PyDict_GetItemWithError(jump_node, S_expr);
                PyObject *value = evaluate_expression_impl(je, options, locals_, 0, script, statement);
                if (value == NULL) { Py_XDECREF(label_indexes); return NULL; }
                int b = call_value_boolean(value);
                Py_DECREF(value);
                if (b < 0) { Py_XDECREF(label_indexes); return NULL; }
                do_jump = b;
            }
            if (do_jump) {
                PyObject *jump_label = PyDict_GetItemWithError(jump_node, S_label);
                if (jump_label == NULL) { Py_XDECREF(label_indexes); return NULL; }
                PyObject *idx = NULL;
                if (label_indexes != NULL) {
                    idx = PyDict_GetItemWithError(label_indexes, jump_label);
                    if (idx == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
                }
                Py_ssize_t target_ix = -1;
                if (idx != NULL) {
                    target_ix = PyLong_AsSsize_t(idx);
                    if (target_ix == -1 && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
                } else {
                    /* find label */
                    for (Py_ssize_t i = 0; i < statements_length; i++) {
                        PyObject *s = PyList_GET_ITEM(statements, i);
                        if (!PyDict_Check(s)) continue;
                        PyObject *lab = PyDict_GetItemWithError(s, S_label);
                        if (lab == NULL) { if (PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; } continue; }
                        PyObject *lname = PyDict_GetItemWithError(lab, S_name);
                        if (lname == NULL) { if (PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; } continue; }
                        if (PyUnicode_Compare(lname, jump_label) == 0) { target_ix = i; break; }
                    }
                    if (target_ix == -1) {
                        Py_XDECREF(label_indexes);
                        return raise_runtime_error_fmt(script, statement,
                                                       "Unknown jump label \"%U\"", jump_label);
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) return NULL;
                    }
                    PyObject *iv = PyLong_FromSsize_t(target_ix);
                    if (iv == NULL) { Py_DECREF(label_indexes); return NULL; }
                    if (PyDict_SetItem(label_indexes, jump_label, iv) < 0) {
                        Py_DECREF(iv); Py_DECREF(label_indexes); return NULL;
                    }
                    Py_DECREF(iv);
                }
                ix_statement = target_ix;
                if (has_coverage) {
                    PyObject *label_stmt = PyList_GET_ITEM(statements, ix_statement);
                    PyObject *lkey = first_key(label_stmt);
                    if (lkey == NULL) { Py_XDECREF(label_indexes); return NULL; }
                    if (record_statement_coverage(script, label_stmt, lkey, coverage_global) < 0) {
                        Py_XDECREF(label_indexes); return NULL;
                    }
                }
            }
        }
        else if (PyUnicode_Compare(statement_key, S_return_) == 0) {
            PyObject *ret_node = PyDict_GetItemWithError(statement, S_return_);
            if (ret_node == NULL) { Py_XDECREF(label_indexes); return NULL; }
            int has_expr = PyDict_Contains(ret_node, S_expr);
            if (has_expr < 0) { Py_XDECREF(label_indexes); return NULL; }
            Py_XDECREF(label_indexes);
            if (has_expr) {
                PyObject *e = PyDict_GetItemWithError(ret_node, S_expr);
                return evaluate_expression_impl(e, options, locals_, 0, script, statement);
            }
            Py_RETURN_NONE;
        }
        else if (PyUnicode_Compare(statement_key, S_function) == 0) {
            PyObject *fn_node = PyDict_GetItemWithError(statement, S_function);
            if (fn_node == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *fname = PyDict_GetItemWithError(fn_node, S_name);
            if (fname == NULL) { Py_XDECREF(label_indexes); return NULL; }
            /* functools.partial(_script_function, script, fn_node) */
            PyObject *partial = PyObject_CallFunctionObjArgs(g_functools_partial,
                                                             g_script_function_obj,
                                                             script, fn_node, NULL);
            if (partial == NULL) { Py_XDECREF(label_indexes); return NULL; }
            if (PyDict_SetItem(globals_, fname, partial) < 0) {
                Py_DECREF(partial); Py_XDECREF(label_indexes); return NULL;
            }
            Py_DECREF(partial);
        }
        else if (PyUnicode_Compare(statement_key, S_include) == 0) {
            PyObject *inc_node = PyDict_GetItemWithError(statement, S_include);
            if (inc_node == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *system_prefix = PyDict_GetItemWithError(options, S_systemPrefix);
            if (system_prefix == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *fetch_fn = PyDict_GetItemWithError(options, S_fetchFn);
            if (fetch_fn == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
            if (log_fn == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *url_fn = PyDict_GetItemWithError(options, S_urlFn);
            if (url_fn == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *includes = PyDict_GetItemWithError(inc_node, S_includes);
            if (includes == NULL) { Py_XDECREF(label_indexes); return NULL; }
            Py_ssize_t inc_n = PyObject_Length(includes);
            if (inc_n < 0) { Py_XDECREF(label_indexes); return NULL; }
            for (Py_ssize_t ii = 0; ii < inc_n; ii++) {
                PyObject *inc = PySequence_GetItem(includes, ii);
                if (inc == NULL) { Py_XDECREF(label_indexes); return NULL; }
                PyObject *include_url = PyDict_GetItemWithError(inc, S_url);
                if (include_url == NULL) { Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                Py_INCREF(include_url);
                PyObject *system_include = PyDict_GetItemWithError(inc, S_system);
                if (system_include == NULL && PyErr_Occurred()) { Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                int is_sys = system_include != NULL && PyObject_IsTrue(system_include) == 1;
                if (is_sys && system_prefix != NULL) {
                    PyObject *nu = PyObject_CallFunctionObjArgs(g_url_file_relative, system_prefix, include_url, NULL);
                    Py_DECREF(include_url);
                    if (nu == NULL) { Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                    include_url = nu;
                } else if (url_fn != NULL) {
                    PyObject *nu = PyObject_CallOneArg(url_fn, include_url);
                    Py_DECREF(include_url);
                    if (nu == NULL) { Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                    include_url = nu;
                }
                /* global_includes */
                PyObject *gi = PyDict_GetItemWithError(globals_, S_includes_global);
                if (gi == NULL && PyErr_Occurred()) { Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                if (gi == NULL || !PyDict_Check(gi)) {
                    gi = PyDict_New();
                    if (gi == NULL) { Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                    if (PyDict_SetItem(globals_, S_includes_global, gi) < 0) {
                        Py_DECREF(gi); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL;
                    }
                    Py_DECREF(gi);
                    gi = PyDict_GetItemWithError(globals_, S_includes_global);
                }
                PyObject *existing = PyDict_GetItemWithError(gi, include_url);
                if (existing == NULL && PyErr_Occurred()) { Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                if (existing != NULL && PyObject_IsTrue(existing) == 1) {
                    Py_DECREF(include_url); Py_DECREF(inc);
                    continue;
                }
                if (PyDict_SetItem(gi, include_url, Py_True) < 0) {
                    Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL;
                }

                /* Fetch */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *url_dict = PyDict_New();
                    if (url_dict == NULL) { Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                    PyDict_SetItem(url_dict, S_url, include_url);
                    include_text = PyObject_CallOneArg(fetch_fn, url_dict);
                    Py_DECREF(url_dict);
                    if (include_text == NULL) {
                        PyErr_Clear();
                    }
                }
                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    PyObject *err = raise_runtime_error_fmt(script, statement, "Include of \"%U\" failed", include_url);
                    Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes);
                    (void)err;
                    return NULL;
                }

                PyObject *one = PyLong_FromLong(1);
                PyObject *include_script = PyObject_CallFunctionObjArgs(g_parse_script, include_text, one, include_url, NULL);
                Py_DECREF(one); Py_DECREF(include_text);
                if (include_script == NULL) {
                    Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes);
                    return NULL;
                }
                if (is_sys) {
                    PyDict_SetItem(include_script, S_system, Py_True);
                }

                PyObject *inc_options = PyDict_Copy(options);
                if (inc_options == NULL) { Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, include_url, NULL);
                if (new_url_fn == NULL) { Py_DECREF(inc_options); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                PyDict_SetItem(inc_options, S_urlFn, new_url_fn);
                Py_DECREF(new_url_fn);

                PyObject *inc_stmts = PyDict_GetItemWithError(include_script, S_statements);
                if (inc_stmts == NULL) { Py_DECREF(inc_options); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                PyObject *exec_res = execute_script_helper(include_script, inc_stmts, inc_options, NULL);
                Py_DECREF(inc_options);
                if (exec_res == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes);
                    return NULL;
                }
                Py_DECREF(exec_res);

                /* Lint? */
                if (log_fn != NULL) {
                    PyObject *dbg = PyDict_GetItemWithError(options, S_debug);
                    if (dbg == NULL && PyErr_Occurred()) { Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                    if (dbg != NULL && PyObject_IsTrue(dbg) == 1) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(g_lint_script, include_script, globals_, NULL);
                        if (warnings == NULL) { Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                        Py_ssize_t wn = PyObject_Length(warnings);
                        if (wn < 0) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                        if (wn > 0) {
                            PyObject *header = PyUnicode_FromFormat("BareScript: Include \"%U\" static analysis... %zd warning%s:",
                                                                    include_url, wn, wn > 1 ? "s" : "");
                            if (header != NULL) {
                                PyObject *r = PyObject_CallOneArg(log_fn, header);
                                Py_XDECREF(r); Py_DECREF(header);
                                if (PyErr_Occurred()) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                            }
                            for (Py_ssize_t wi = 0; wi < wn; wi++) {
                                PyObject *w = PySequence_GetItem(warnings, wi);
                                if (w == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                                PyObject *msg = PyUnicode_FromFormat("BareScript: %U", w);
                                Py_DECREF(w);
                                if (msg != NULL) {
                                    PyObject *r = PyObject_CallOneArg(log_fn, msg);
                                    Py_XDECREF(r); Py_DECREF(msg);
                                }
                                if (PyErr_Occurred()) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(inc); Py_XDECREF(label_indexes); return NULL; }
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }
                Py_DECREF(include_script);
                Py_DECREF(include_url);
                Py_DECREF(inc);
            }
        }
        /* label / unknown — ignore */

        ix_statement++;
    }

    Py_XDECREF(label_indexes);
    Py_RETURN_NONE;
}

/* ---------- Public: evaluate_expression ---------- */

static PyObject *py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr;
    PyObject *options = Py_None;
    PyObject *locals_ = Py_None;
    PyObject *builtins_obj = Py_True;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOOOO:evaluate_expression",
                                     kwlist, &expr, &options, &locals_, &builtins_obj, &script, &statement)) {
        return NULL;
    }
    int builtins = PyObject_IsTrue(builtins_obj);
    if (builtins < 0) return NULL;
    PyObject *opt = (options == Py_None) ? NULL : options;
    PyObject *loc = (locals_ == Py_None) ? NULL : locals_;
    PyObject *scr = (script == Py_None) ? NULL : script;
    PyObject *stmt = (statement == Py_None) ? NULL : statement;
    return evaluate_expression_impl(expr, opt, loc, builtins, scr, stmt);
}

/* ---------- Public: execute_script ---------- */

static PyObject *py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script;
    PyObject *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:execute_script", kwlist, &script, &options)) {
        return NULL;
    }
    int created_options = 0;
    if (options == Py_None) {
        options = PyDict_New();
        if (options == NULL) return NULL;
        created_options = 1;
    } else {
        Py_INCREF(options);
    }

    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL) {
        if (PyErr_Occurred()) { Py_DECREF(options); return NULL; }
        globals_ = PyDict_New();
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, S_globals, globals_) < 0) {
            Py_DECREF(globals_); Py_DECREF(options); return NULL;
        }
        Py_DECREF(globals_);
        globals_ = PyDict_GetItemWithError(options, S_globals);
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
    }

    /* Update globals_ with SCRIPT_FUNCTIONS items not already present */
    Py_ssize_t pos = 0;
    PyObject *k, *v;
    while (PyDict_Next(g_SCRIPT_FUNCTIONS, &pos, &k, &v)) {
        int has = PyDict_Contains(globals_, k);
        if (has < 0) { Py_DECREF(options); return NULL; }
        if (!has) {
            if (PyDict_SetItem(globals_, k, v) < 0) { Py_DECREF(options); return NULL; }
        }
    }

    PyObject *zero = PyLong_FromLong(0);
    if (PyDict_SetItem(options, S_statementCount, zero) < 0) {
        Py_DECREF(zero); Py_DECREF(options); return NULL;
    }
    Py_DECREF(zero);

    PyObject *stmts = PyDict_GetItemWithError(script, S_statements);
    if (stmts == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
        Py_DECREF(options); return NULL;
    }
    PyObject *result = execute_script_helper(script, stmts, options, NULL);
    Py_DECREF(options);
    (void)created_options;
    return result;
}

/* ---------- Module init ---------- */

static PyMethodDef methods[] = {
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS,
     "Evaluate an expression model."},
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS,
     "Execute a script model."},
    {"_script_function", (PyCFunction)py_script_function, METH_VARARGS,
     "Runtime script function implementation."},
    {NULL, NULL, 0, NULL}
};

static int intern_str(PyObject **slot, const char *s) {
    PyObject *o = PyUnicode_InternFromString(s);
    if (o == NULL) return -1;
    *slot = o;
    return 0;
}

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "bare_script.runtime_c", NULL, -1, methods
};

PyMODINIT_FUNC PyInit_runtime_c(void) {
    PyObject *m = PyModule_Create(&moduledef);
    if (m == NULL) return NULL;

    /* Intern strings */
    if (intern_str(&S_globals, "globals") < 0) return NULL;
    if (intern_str(&S_statementCount, "statementCount") < 0) return NULL;
    if (intern_str(&S_maxStatements, "maxStatements") < 0) return NULL;
    if (intern_str(&S_systemPrefix, "systemPrefix") < 0) return NULL;
    if (intern_str(&S_fetchFn, "fetchFn") < 0) return NULL;
    if (intern_str(&S_logFn, "logFn") < 0) return NULL;
    if (intern_str(&S_urlFn, "urlFn") < 0) return NULL;
    if (intern_str(&S_debug, "debug") < 0) return NULL;
    if (intern_str(&S_includes, "includes") < 0) return NULL;
    if (intern_str(&S_url, "url") < 0) return NULL;
    if (intern_str(&S_system, "system") < 0) return NULL;
    if (intern_str(&S_statements, "statements") < 0) return NULL;
    if (intern_str(&S_expr, "expr") < 0) return NULL;
    if (intern_str(&S_jump, "jump") < 0) return NULL;
    if (intern_str(&S_return_, "return") < 0) return NULL;
    if (intern_str(&S_function, "function") < 0) return NULL;
    if (intern_str(&S_include, "include") < 0) return NULL;
    if (intern_str(&S_label, "label") < 0) return NULL;
    if (intern_str(&S_name, "name") < 0) return NULL;
    if (intern_str(&S_args, "args") < 0) return NULL;
    if (intern_str(&S_lastArgArray, "lastArgArray") < 0) return NULL;
    if (intern_str(&S_binary, "binary") < 0) return NULL;
    if (intern_str(&S_unary, "unary") < 0) return NULL;
    if (intern_str(&S_group, "group") < 0) return NULL;
    if (intern_str(&S_number, "number") < 0) return NULL;
    if (intern_str(&S_string, "string") < 0) return NULL;
    if (intern_str(&S_variable, "variable") < 0) return NULL;
    if (intern_str(&S_op, "op") < 0) return NULL;
    if (intern_str(&S_left, "left") < 0) return NULL;
    if (intern_str(&S_right, "right") < 0) return NULL;
    if (intern_str(&S_scriptName, "scriptName") < 0) return NULL;
    if (intern_str(&S_lineNumber, "lineNumber") < 0) return NULL;
    if (intern_str(&S_scripts, "scripts") < 0) return NULL;
    if (intern_str(&S_covered, "covered") < 0) return NULL;
    if (intern_str(&S_script, "script") < 0) return NULL;
    if (intern_str(&S_count, "count") < 0) return NULL;
    if (intern_str(&S_statement, "statement") < 0) return NULL;
    if (intern_str(&S_enabled, "enabled") < 0) return NULL;
    if (intern_str(&S_null, "null") < 0) return NULL;
    if (intern_str(&S_true, "true") < 0) return NULL;
    if (intern_str(&S_false, "false") < 0) return NULL;
    if (intern_str(&S_if_, "if") < 0) return NULL;
    if (intern_str(&S_coverage_global, "__barescriptCoverage") < 0) return NULL;
    if (intern_str(&S_includes_global, "__barescriptIncludes") < 0) return NULL;
    if (intern_str(&S_op_and, "&&") < 0) return NULL;
    if (intern_str(&S_op_or, "||") < 0) return NULL;
    if (intern_str(&S_op_plus, "+") < 0) return NULL;
    if (intern_str(&S_op_minus, "-") < 0) return NULL;
    if (intern_str(&S_op_mult, "*") < 0) return NULL;
    if (intern_str(&S_op_div, "/") < 0) return NULL;
    if (intern_str(&S_op_eq, "==") < 0) return NULL;
    if (intern_str(&S_op_ne, "!=") < 0) return NULL;
    if (intern_str(&S_op_le, "<=") < 0) return NULL;
    if (intern_str(&S_op_lt, "<") < 0) return NULL;
    if (intern_str(&S_op_ge, ">=") < 0) return NULL;
    if (intern_str(&S_op_gt, ">") < 0) return NULL;
    if (intern_str(&S_op_mod, "%") < 0) return NULL;
    if (intern_str(&S_op_pow, "**") < 0) return NULL;
    if (intern_str(&S_op_bitand, "&") < 0) return NULL;
    if (intern_str(&S_op_bitor, "|") < 0) return NULL;
    if (intern_str(&S_op_bitxor, "^") < 0) return NULL;
    if (intern_str(&S_op_shl, "<<") < 0) return NULL;
    if (intern_str(&S_op_shr, ">>") < 0) return NULL;
    if (intern_str(&S_op_not, "!") < 0) return NULL;
    if (intern_str(&S_op_neg, "-") < 0) return NULL;
    if (intern_str(&S_op_bitnot, "~") < 0) return NULL;
    if (intern_str(&S_milliseconds, "milliseconds") < 0) return NULL;

    /* Import dependencies */
    PyObject *mod;

    mod = PyImport_ImportModule("bare_script.library");
    if (mod == NULL) return NULL;
    g_EXPRESSION_FUNCTIONS = PyObject_GetAttrString(mod, "EXPRESSION_FUNCTIONS");
    g_SCRIPT_FUNCTIONS = PyObject_GetAttrString(mod, "SCRIPT_FUNCTIONS");
    Py_DECREF(mod);
    if (g_EXPRESSION_FUNCTIONS == NULL || g_SCRIPT_FUNCTIONS == NULL) return NULL;

    mod = PyImport_ImportModule("bare_script.model");
    if (mod == NULL) return NULL;
    g_lint_script = PyObject_GetAttrString(mod, "lint_script");
    Py_DECREF(mod);
    if (g_lint_script == NULL) return NULL;

    mod = PyImport_ImportModule("bare_script.options");
    if (mod == NULL) return NULL;
    g_url_file_relative = PyObject_GetAttrString(mod, "url_file_relative");
    Py_DECREF(mod);
    if (g_url_file_relative == NULL) return NULL;

    mod = PyImport_ImportModule("bare_script.parser");
    if (mod == NULL) return NULL;
    g_parse_script = PyObject_GetAttrString(mod, "parse_script");
    Py_DECREF(mod);
    if (g_parse_script == NULL) return NULL;

    mod = PyImport_ImportModule("bare_script.value");
    if (mod == NULL) return NULL;
    g_ValueArgsError = PyObject_GetAttrString(mod, "ValueArgsError");
    g_value_boolean = PyObject_GetAttrString(mod, "value_boolean");
    g_value_compare = PyObject_GetAttrString(mod, "value_compare");
    g_value_normalize_datetime = PyObject_GetAttrString(mod, "value_normalize_datetime");
    g_value_round_number = PyObject_GetAttrString(mod, "value_round_number");
    g_value_string = PyObject_GetAttrString(mod, "value_string");
    Py_DECREF(mod);
    if (!g_ValueArgsError || !g_value_boolean || !g_value_compare || !g_value_normalize_datetime ||
        !g_value_round_number || !g_value_string) return NULL;

    mod = PyImport_ImportModule("bare_script.runtime");
    if (mod == NULL) return NULL;
    g_BareScriptRuntimeError = PyObject_GetAttrString(mod, "BareScriptRuntimeError");
    Py_DECREF(mod);
    if (g_BareScriptRuntimeError == NULL) return NULL;

    mod = PyImport_ImportModule("functools");
    if (mod == NULL) return NULL;
    g_functools_partial = PyObject_GetAttrString(mod, "partial");
    Py_DECREF(mod);
    if (g_functools_partial == NULL) return NULL;

    mod = PyImport_ImportModule("datetime");
    if (mod == NULL) return NULL;
    g_datetime_date = PyObject_GetAttrString(mod, "date");
    g_datetime_timedelta = PyObject_GetAttrString(mod, "timedelta");
    Py_DECREF(mod);
    if (!g_datetime_date || !g_datetime_timedelta) return NULL;

    g_default_max_statements = PyLong_FromDouble(1e9);
    if (g_default_max_statements == NULL) return NULL;

    /* Look up _script_function for use with functools.partial */
    g_script_function_obj = PyObject_GetAttrString(m, "_script_function");
    if (g_script_function_obj == NULL) return NULL;

    return m;
}
