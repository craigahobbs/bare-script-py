/*
 * Licensed under the MIT License
 * https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE
 *
 * bare_script.runtime_c - C port of bare_script/runtime.py
 *
 * Implements execute_script() and evaluate_expression() in C for performance.
 * The pure-Python implementation in runtime.py is the source of truth.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* ----- Module-level interned strings (set during init) -------------------- */

static PyObject *S_expr;
static PyObject *S_jump;
static PyObject *S_return;
static PyObject *S_function;
static PyObject *S_include;
static PyObject *S_label;
static PyObject *S_name;
static PyObject *S_globals;
static PyObject *S_statementCount;
static PyObject *S_maxStatements;
static PyObject *S_statements;
static PyObject *S_lineNumber;
static PyObject *S_scriptName;
static PyObject *S_scripts;
static PyObject *S_covered;
static PyObject *S_count;
static PyObject *S_statement;
static PyObject *S_script;
static PyObject *S_enabled;
static PyObject *S_system;
static PyObject *S_includes;
static PyObject *S_systemPrefix;
static PyObject *S_fetchFn;
static PyObject *S_logFn;
static PyObject *S_urlFn;
static PyObject *S_url;
static PyObject *S_debug;
static PyObject *S_args;
static PyObject *S_lastArgArray;
static PyObject *S_variable;
static PyObject *S_number;
static PyObject *S_string;
static PyObject *S_binary;
static PyObject *S_unary;
static PyObject *S_group;
static PyObject *S_left;
static PyObject *S_right;
static PyObject *S_op;
static PyObject *S_null;
static PyObject *S_true;
static PyObject *S_false;
static PyObject *S_if;

/* Binary/unary op interned strings */
static PyObject *S_op_and;
static PyObject *S_op_or;
static PyObject *S_op_add;
static PyObject *S_op_sub;
static PyObject *S_op_mul;
static PyObject *S_op_div;
static PyObject *S_op_eq;
static PyObject *S_op_ne;
static PyObject *S_op_lte;
static PyObject *S_op_lt;
static PyObject *S_op_gte;
static PyObject *S_op_gt;
static PyObject *S_op_mod;
static PyObject *S_op_pow;
static PyObject *S_op_band;
static PyObject *S_op_bor;
static PyObject *S_op_bxor;
static PyObject *S_op_shl;
static PyObject *S_op_shr;
static PyObject *S_op_unot;
static PyObject *S_op_uneg;
static PyObject *S_op_uinv;

/* Globals/markers used by Python runtime */
static PyObject *S_COVERAGE_GLOBAL; /* "__barescriptCoverage" */
static PyObject *S_INCLUDES_GLOBAL; /* "__barescriptIncludes" */

/* Imported helpers (from .library, .model, .options, .parser, .value) */
static PyObject *PY_SCRIPT_FUNCTIONS;     /* dict */
static PyObject *PY_EXPRESSION_FUNCTIONS; /* dict */
static PyObject *PY_lint_script;
static PyObject *PY_url_file_relative;
static PyObject *PY_parse_script;
static PyObject *PY_value_boolean;
static PyObject *PY_value_compare;
static PyObject *PY_value_string;
static PyObject *PY_value_normalize_datetime;
static PyObject *PY_value_round_number;
static PyObject *PY_ValueArgsError;
static PyObject *PY_BareScriptRuntimeError;
static PyObject *PY_datetime_date;
static PyObject *PY_datetime_timedelta;
static PyObject *PY_functools_partial;

/* Default max statements: 1e9 */
static PyObject *PY_DEFAULT_MAX_STATEMENTS;

/* ----- Forward declarations ---------------------------------------------- */

static PyObject *execute_script_helper(PyObject *script, PyObject *statements,
                                       PyObject *options, PyObject *locals_);
static PyObject *eval_expression(PyObject *expr, PyObject *options,
                                 PyObject *locals_, int builtins,
                                 PyObject *script, PyObject *statement);
static PyObject *script_function_call(PyObject *self, PyObject *args);
static void record_statement_coverage(PyObject *script, PyObject *statement,
                                      PyObject *statement_key, PyObject *coverage_global);
static int raise_runtime_error(PyObject *script, PyObject *statement, const char *fmt, PyObject *arg);

/* ----- Helper utilities -------------------------------------------------- */

/* Get the only key of a one-key dict (the "kind" tag, e.g. 'expr'/'jump'). */
static inline PyObject *get_only_key(PyObject *dict)
{
    /* Use PyDict_Next for speed (no list materialization). */
    Py_ssize_t pos = 0;
    PyObject *key = NULL, *value = NULL;
    if (PyDict_Next(dict, &pos, &key, &value)) {
        return key; /* borrowed */
    }
    PyErr_SetString(PyExc_RuntimeError, "expected non-empty dict");
    return NULL;
}

/* Check if value is a "real" number (int or float but not bool). */
static inline int is_number(PyObject *o)
{
    if (PyBool_Check(o)) return 0;
    return PyLong_Check(o) || PyFloat_Check(o);
}

/* Call value_boolean(value) and return 0/1, or -1 on error. */
static inline int call_value_boolean(PyObject *value)
{
    /* Fast paths for common types */
    if (value == Py_None) return 0;
    if (value == Py_True) return 1;
    if (value == Py_False) return 0;
    if (PyUnicode_Check(value)) {
        return PyUnicode_GET_LENGTH(value) != 0;
    }
    if (PyLong_Check(value)) {
        return !_PyLong_IsZero((PyLongObject *)value);
    }
    if (PyFloat_Check(value)) {
        double d = PyFloat_AS_DOUBLE(value);
        return d != 0.0;
    }
    if (PyList_Check(value)) {
        return PyList_GET_SIZE(value) != 0;
    }
    /* Fallback to Python helper */
    PyObject *res = PyObject_CallOneArg(PY_value_boolean, value);
    if (res == NULL) return -1;
    int truth = PyObject_IsTrue(res);
    Py_DECREF(res);
    return truth;
}

/* Compare two values per value_compare. Returns -2 on error, else -1/0/1. */
static inline int call_value_compare(PyObject *left, PyObject *right)
{
    PyObject *res = PyObject_CallFunctionObjArgs(PY_value_compare, left, right, NULL);
    if (res == NULL) return -2;
    long c = PyLong_AsLong(res);
    Py_DECREF(res);
    if (c < 0) return -1;
    if (c > 0) return 1;
    return 0;
}

/* Coerce two integral numeric values to long. Returns 0 on success, -1 on failure. */
static int as_long_long(PyObject *o, long long *out)
{
    if (PyLong_Check(o) && !PyBool_Check(o)) {
        *out = PyLong_AsLongLong(o);
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    if (PyFloat_Check(o)) {
        double d = PyFloat_AS_DOUBLE(o);
        long long v = (long long)d;
        if ((double)v != d) return -1;
        *out = v;
        return 0;
    }
    return -1;
}

/* Convert any number to double. Returns 0 on success, -1 on failure (not number). */
static int as_double(PyObject *o, double *out)
{
    if (PyBool_Check(o)) return -1;
    if (PyFloat_Check(o)) {
        *out = PyFloat_AS_DOUBLE(o);
        return 0;
    }
    if (PyLong_Check(o)) {
        double d = PyLong_AsDouble(o);
        if (d == -1.0 && PyErr_Occurred()) return -1;
        *out = d;
        return 0;
    }
    return -1;
}

/* Raise BareScriptRuntimeError(script, statement, message). Returns -1. */
static int raise_runtime_error(PyObject *script, PyObject *statement,
                               const char *fmt, PyObject *arg)
{
    PyObject *message;
    if (arg != NULL) {
        message = PyUnicode_FromFormat(fmt, arg);
    } else {
        message = PyUnicode_FromString(fmt);
    }
    if (message == NULL) return -1;
    PyObject *err = PyObject_CallFunctionObjArgs(
        PY_BareScriptRuntimeError,
        script ? script : Py_None,
        statement ? statement : Py_None,
        message,
        NULL);
    Py_DECREF(message);
    if (err == NULL) return -1;
    PyErr_SetObject(PY_BareScriptRuntimeError, err);
    Py_DECREF(err);
    return -1;
}

/* ----- Coverage --------------------------------------------------------- */

static void record_statement_coverage(PyObject *script, PyObject *statement,
                                      PyObject *statement_key, PyObject *coverage_global)
{
    /* script_name = script.get('scriptName'); */
    PyObject *script_name = PyDict_GetItemWithError(script, S_scriptName);
    if (script_name == NULL && PyErr_Occurred()) { PyErr_Clear(); return; }
    if (script_name == NULL || script_name == Py_None) return;

    /* lineno = statement[statement_key].get('lineNumber') */
    PyObject *body = PyDict_GetItemWithError(statement, statement_key);
    if (body == NULL || !PyDict_Check(body)) { if (PyErr_Occurred()) PyErr_Clear(); return; }
    PyObject *lineno = PyDict_GetItemWithError(body, S_lineNumber);
    if (lineno == NULL || lineno == Py_None) { if (PyErr_Occurred()) PyErr_Clear(); return; }

    /* scripts = coverage_global.get('scripts') or new dict */
    PyObject *scripts = PyDict_GetItemWithError(coverage_global, S_scripts);
    if (scripts == NULL && PyErr_Occurred()) { PyErr_Clear(); return; }
    if (scripts == NULL) {
        scripts = PyDict_New();
        if (scripts == NULL) { PyErr_Clear(); return; }
        PyDict_SetItem(coverage_global, S_scripts, scripts);
        Py_DECREF(scripts);
        scripts = PyDict_GetItem(coverage_global, S_scripts);
    }

    /* script_coverage = scripts.get(script_name) or {'script': script, 'covered': {}} */
    PyObject *script_coverage = PyDict_GetItemWithError(scripts, script_name);
    if (script_coverage == NULL && PyErr_Occurred()) { PyErr_Clear(); return; }
    if (script_coverage == NULL) {
        script_coverage = PyDict_New();
        if (script_coverage == NULL) { PyErr_Clear(); return; }
        PyObject *covered = PyDict_New();
        if (covered == NULL) { Py_DECREF(script_coverage); PyErr_Clear(); return; }
        PyDict_SetItem(script_coverage, S_script, script);
        PyDict_SetItem(script_coverage, S_covered, covered);
        Py_DECREF(covered);
        PyDict_SetItem(scripts, script_name, script_coverage);
        Py_DECREF(script_coverage);
        script_coverage = PyDict_GetItem(scripts, script_name);
    }

    /* lineno_str = str(lineno) */
    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) { PyErr_Clear(); return; }

    /* covered_statements = script_coverage['covered'] */
    PyObject *covered_statements = PyDict_GetItemWithError(script_coverage, S_covered);
    if (covered_statements == NULL) { Py_DECREF(lineno_str); if (PyErr_Occurred()) PyErr_Clear(); return; }

    PyObject *covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
    if (covered_statement == NULL && PyErr_Occurred()) { Py_DECREF(lineno_str); PyErr_Clear(); return; }
    if (covered_statement == NULL) {
        covered_statement = PyDict_New();
        if (covered_statement == NULL) { Py_DECREF(lineno_str); PyErr_Clear(); return; }
        PyObject *zero = PyLong_FromLong(0);
        PyDict_SetItem(covered_statement, S_statement, statement);
        PyDict_SetItem(covered_statement, S_count, zero);
        Py_DECREF(zero);
        PyDict_SetItem(covered_statements, lineno_str, covered_statement);
        Py_DECREF(covered_statement);
        covered_statement = PyDict_GetItem(covered_statements, lineno_str);
    }
    Py_DECREF(lineno_str);

    /* covered_statement['count'] += 1 */
    PyObject *cnt = PyDict_GetItemWithError(covered_statement, S_count);
    if (cnt == NULL) { if (PyErr_Occurred()) PyErr_Clear(); return; }
    long n = PyLong_AsLong(cnt);
    if (n == -1 && PyErr_Occurred()) { PyErr_Clear(); return; }
    PyObject *new_cnt = PyLong_FromLong(n + 1);
    if (new_cnt == NULL) { PyErr_Clear(); return; }
    PyDict_SetItem(covered_statement, S_count, new_cnt);
    Py_DECREF(new_cnt);
}

/* ----- Expression evaluation -------------------------------------------- */

static PyObject *eval_function(PyObject *fn_dict, PyObject *options,
                               PyObject *locals_, int builtins,
                               PyObject *script, PyObject *statement)
{
    PyObject *globals_ = options != NULL ? PyDict_GetItemWithError(options, S_globals) : NULL;
    if (globals_ == NULL && PyErr_Occurred()) PyErr_Clear();

    PyObject *func_name = PyDict_GetItemWithError(fn_dict, S_name);
    if (func_name == NULL) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_KeyError, "function missing 'name'");
        return NULL;
    }

    /* "if" built-in function? */
    int is_if = PyUnicode_Check(func_name) && PyUnicode_CompareWithASCIIString(func_name, "if") == 0;
    if (is_if) {
        PyObject *args_expr = PyDict_GetItemWithError(fn_dict, S_args);
        if (args_expr == NULL && PyErr_Occurred()) PyErr_Clear();
        Py_ssize_t alen = (args_expr != NULL && PyList_Check(args_expr)) ? PyList_GET_SIZE(args_expr) : 0;
        PyObject *value_expr = alen >= 1 ? PyList_GET_ITEM(args_expr, 0) : NULL;
        PyObject *true_expr = alen >= 2 ? PyList_GET_ITEM(args_expr, 1) : NULL;
        PyObject *false_expr = alen >= 3 ? PyList_GET_ITEM(args_expr, 2) : NULL;
        PyObject *value;
        if (value_expr != NULL) {
            value = eval_expression(value_expr, options, locals_, builtins, script, statement);
            if (value == NULL) return NULL;
        } else {
            Py_INCREF(Py_False); value = Py_False;
        }
        int truth = call_value_boolean(value);
        Py_DECREF(value);
        if (truth < 0) return NULL;
        PyObject *result_expr = truth ? true_expr : false_expr;
        if (result_expr == NULL) Py_RETURN_NONE;
        return eval_expression(result_expr, options, locals_, builtins, script, statement);
    }

    /* Compute function arguments */
    PyObject *args_expr = PyDict_GetItemWithError(fn_dict, S_args);
    if (args_expr == NULL && PyErr_Occurred()) PyErr_Clear();
    PyObject *func_args;
    if (args_expr != NULL && PyList_Check(args_expr)) {
        Py_ssize_t alen = PyList_GET_SIZE(args_expr);
        func_args = PyList_New(alen);
        if (func_args == NULL) return NULL;
        for (Py_ssize_t i = 0; i < alen; i++) {
            PyObject *arg_expr = PyList_GET_ITEM(args_expr, i);
            PyObject *v = eval_expression(arg_expr, options, locals_, builtins, script, statement);
            if (v == NULL) { Py_DECREF(func_args); return NULL; }
            PyList_SET_ITEM(func_args, i, v);
        }
    } else {
        func_args = Py_None;
        Py_INCREF(func_args);
    }

    /* Lookup function value: locals_ then globals_ then EXPRESSION_FUNCTIONS */
    PyObject *func_value = NULL;
    if (locals_ != NULL) {
        func_value = PyDict_GetItemWithError(locals_, func_name);
        if (func_value == NULL && PyErr_Occurred()) { Py_DECREF(func_args); return NULL; }
    }
    if (func_value == NULL && globals_ != NULL) {
        func_value = PyDict_GetItemWithError(globals_, func_name);
        if (func_value == NULL && PyErr_Occurred()) { Py_DECREF(func_args); return NULL; }
    }
    if (func_value == NULL && builtins) {
        func_value = PyDict_GetItemWithError(PY_EXPRESSION_FUNCTIONS, func_name);
        if (func_value == NULL && PyErr_Occurred()) { Py_DECREF(func_args); return NULL; }
    }
    if (func_value != NULL) {
        PyObject *call_args[2] = { func_args, options ? options : Py_None };
        PyObject *result = PyObject_Vectorcall(func_value, call_args, 2, NULL);
        Py_DECREF(func_args);
        if (result == NULL) {
            /* Check whether exception is BareScriptRuntimeError */
            if (PyErr_ExceptionMatches(PY_BareScriptRuntimeError)) return NULL;

            /* Capture the active exception */
            PyObject *exc_type, *exc_value, *exc_tb;
            PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
            PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);

            /* Logging on debug */
            if (options != NULL) {
                PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
                if (log_fn == NULL && PyErr_Occurred()) PyErr_Clear();
                PyObject *debug = PyDict_GetItemWithError(options, S_debug);
                if (debug == NULL && PyErr_Occurred()) PyErr_Clear();
                int do_log = log_fn != NULL && debug != NULL && PyObject_IsTrue(debug) == 1;
                if (do_log) {
                    PyObject *msg = PyUnicode_FromFormat(
                        "BareScript: Function \"%S\" failed with error: %S",
                        func_name, exc_value);
                    if (msg != NULL) {
                        PyObject *r = PyObject_CallOneArg(log_fn, msg);
                        Py_XDECREF(r);
                        Py_DECREF(msg);
                        if (PyErr_Occurred()) PyErr_Clear();
                    }
                }
            }

            /* If ValueArgsError, return its return_value */
            if (exc_value != NULL && PyObject_IsInstance(exc_value, PY_ValueArgsError) == 1) {
                PyObject *rv = PyObject_GetAttrString(exc_value, "return_value");
                Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                if (rv == NULL) return NULL;
                return rv;
            }
            Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
            Py_RETURN_NONE;
        }
        return result;
    }

    Py_DECREF(func_args);
    raise_runtime_error(script, statement, "Undefined function \"%S\"", func_name);
    return NULL;
}

static PyObject *eval_binary(PyObject *bin_dict, PyObject *options,
                             PyObject *locals_, int builtins,
                             PyObject *script, PyObject *statement)
{
    PyObject *op = PyDict_GetItemWithError(bin_dict, S_op);
    if (op == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "binary missing 'op'");
        return NULL;
    }
    PyObject *left_expr = PyDict_GetItemWithError(bin_dict, S_left);
    PyObject *right_expr = PyDict_GetItemWithError(bin_dict, S_right);
    if (left_expr == NULL || right_expr == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "binary missing operand");
        return NULL;
    }

    PyObject *left = eval_expression(left_expr, options, locals_, builtins, script, statement);
    if (left == NULL) return NULL;

    /* Short-circuiting and/or */
    if (op == S_op_and || PyUnicode_Compare(op, S_op_and) == 0) {
        int truth = call_value_boolean(left);
        if (truth < 0) { Py_DECREF(left); return NULL; }
        if (!truth) return left;
        Py_DECREF(left);
        return eval_expression(right_expr, options, locals_, builtins, script, statement);
    }
    if (op == S_op_or || PyUnicode_Compare(op, S_op_or) == 0) {
        int truth = call_value_boolean(left);
        if (truth < 0) { Py_DECREF(left); return NULL; }
        if (truth) return left;
        Py_DECREF(left);
        return eval_expression(right_expr, options, locals_, builtins, script, statement);
    }

    PyObject *right = eval_expression(right_expr, options, locals_, builtins, script, statement);
    if (right == NULL) { Py_DECREF(left); return NULL; }

    PyObject *result = NULL;

    if (op == S_op_add || PyUnicode_Compare(op, S_op_add) == 0) {
        int ln = is_number(left), rn = is_number(right);
        if (ln && rn) {
            result = PyNumber_Add(left, right);
        } else if (PyUnicode_Check(left) && PyUnicode_Check(right)) {
            result = PyUnicode_Concat(left, right);
        } else if (PyUnicode_Check(left)) {
            PyObject *rs = PyObject_CallOneArg(PY_value_string, right);
            if (rs != NULL) {
                result = PyUnicode_Concat(left, rs);
                Py_DECREF(rs);
            }
        } else if (PyUnicode_Check(right)) {
            PyObject *ls = PyObject_CallOneArg(PY_value_string, left);
            if (ls != NULL) {
                result = PyUnicode_Concat(ls, right);
                Py_DECREF(ls);
            }
        } else {
            int left_dt = PyObject_IsInstance(left, PY_datetime_date);
            int right_dt = PyObject_IsInstance(right, PY_datetime_date);
            if (left_dt < 0 || right_dt < 0) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            if (left_dt && rn) {
                PyObject *ldt = PyObject_CallOneArg(PY_value_normalize_datetime, left);
                if (ldt != NULL) {
                    PyObject *td = PyObject_CallFunction(PY_datetime_timedelta, "OO", PyLong_FromLong(0), PyLong_FromLong(0));
                    Py_XDECREF(td);
                    PyObject *kwargs = PyDict_New();
                    if (kwargs != NULL) {
                        PyDict_SetItemString(kwargs, "milliseconds", right);
                        PyObject *empty_args = PyTuple_New(0);
                        td = PyObject_Call(PY_datetime_timedelta, empty_args, kwargs);
                        Py_DECREF(empty_args);
                        Py_DECREF(kwargs);
                        if (td != NULL) {
                            result = PyNumber_Add(ldt, td);
                            Py_DECREF(td);
                        }
                    }
                    Py_DECREF(ldt);
                }
            } else if (ln && right_dt) {
                PyObject *rdt = PyObject_CallOneArg(PY_value_normalize_datetime, right);
                if (rdt != NULL) {
                    PyObject *kwargs = PyDict_New();
                    if (kwargs != NULL) {
                        PyDict_SetItemString(kwargs, "milliseconds", left);
                        PyObject *empty_args = PyTuple_New(0);
                        PyObject *td = PyObject_Call(PY_datetime_timedelta, empty_args, kwargs);
                        Py_DECREF(empty_args);
                        Py_DECREF(kwargs);
                        if (td != NULL) {
                            result = PyNumber_Add(rdt, td);
                            Py_DECREF(td);
                        }
                    }
                    Py_DECREF(rdt);
                }
            }
        }
    } else if (op == S_op_sub || PyUnicode_Compare(op, S_op_sub) == 0) {
        int ln = is_number(left), rn = is_number(right);
        if (ln && rn) {
            result = PyNumber_Subtract(left, right);
        } else {
            int left_dt = PyObject_IsInstance(left, PY_datetime_date);
            int right_dt = PyObject_IsInstance(right, PY_datetime_date);
            if (left_dt < 0 || right_dt < 0) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            if (left_dt && right_dt) {
                PyObject *ldt = PyObject_CallOneArg(PY_value_normalize_datetime, left);
                PyObject *rdt = ldt ? PyObject_CallOneArg(PY_value_normalize_datetime, right) : NULL;
                if (ldt && rdt) {
                    PyObject *diff = PyNumber_Subtract(ldt, rdt);
                    if (diff != NULL) {
                        PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                        if (secs != NULL) {
                            PyObject *thousand = PyFloat_FromDouble(1000.0);
                            PyObject *ms = PyNumber_Multiply(secs, thousand);
                            Py_DECREF(thousand); Py_DECREF(secs);
                            if (ms != NULL) {
                                PyObject *zero = PyLong_FromLong(0);
                                result = PyObject_CallFunctionObjArgs(PY_value_round_number, ms, zero, NULL);
                                Py_DECREF(zero); Py_DECREF(ms);
                            }
                        }
                        Py_DECREF(diff);
                    }
                }
                Py_XDECREF(ldt); Py_XDECREF(rdt);
            }
        }
    } else if (op == S_op_mul || PyUnicode_Compare(op, S_op_mul) == 0) {
        if (is_number(left) && is_number(right)) result = PyNumber_Multiply(left, right);
    } else if (op == S_op_div || PyUnicode_Compare(op, S_op_div) == 0) {
        if (is_number(left) && is_number(right)) result = PyNumber_TrueDivide(left, right);
    } else if (op == S_op_eq || PyUnicode_Compare(op, S_op_eq) == 0) {
        int c = call_value_compare(left, right);
        if (c == -2) { Py_DECREF(left); Py_DECREF(right); return NULL; }
        result = (c == 0) ? Py_True : Py_False;
        Py_INCREF(result);
    } else if (op == S_op_ne || PyUnicode_Compare(op, S_op_ne) == 0) {
        int c = call_value_compare(left, right);
        if (c == -2) { Py_DECREF(left); Py_DECREF(right); return NULL; }
        result = (c != 0) ? Py_True : Py_False;
        Py_INCREF(result);
    } else if (op == S_op_lte || PyUnicode_Compare(op, S_op_lte) == 0) {
        int c = call_value_compare(left, right);
        if (c == -2) { Py_DECREF(left); Py_DECREF(right); return NULL; }
        result = (c <= 0) ? Py_True : Py_False;
        Py_INCREF(result);
    } else if (op == S_op_lt || PyUnicode_Compare(op, S_op_lt) == 0) {
        int c = call_value_compare(left, right);
        if (c == -2) { Py_DECREF(left); Py_DECREF(right); return NULL; }
        result = (c < 0) ? Py_True : Py_False;
        Py_INCREF(result);
    } else if (op == S_op_gte || PyUnicode_Compare(op, S_op_gte) == 0) {
        int c = call_value_compare(left, right);
        if (c == -2) { Py_DECREF(left); Py_DECREF(right); return NULL; }
        result = (c >= 0) ? Py_True : Py_False;
        Py_INCREF(result);
    } else if (op == S_op_gt || PyUnicode_Compare(op, S_op_gt) == 0) {
        int c = call_value_compare(left, right);
        if (c == -2) { Py_DECREF(left); Py_DECREF(right); return NULL; }
        result = (c > 0) ? Py_True : Py_False;
        Py_INCREF(result);
    } else if (op == S_op_mod || PyUnicode_Compare(op, S_op_mod) == 0) {
        if (is_number(left) && is_number(right)) result = PyNumber_Remainder(left, right);
    } else if (op == S_op_pow || PyUnicode_Compare(op, S_op_pow) == 0) {
        if (is_number(left) && is_number(right)) result = PyNumber_Power(left, right, Py_None);
    } else if (op == S_op_band || op == S_op_bor || op == S_op_bxor
            || op == S_op_shl || op == S_op_shr
            || PyUnicode_Compare(op, S_op_band) == 0
            || PyUnicode_Compare(op, S_op_bor) == 0
            || PyUnicode_Compare(op, S_op_bxor) == 0
            || PyUnicode_Compare(op, S_op_shl) == 0
            || PyUnicode_Compare(op, S_op_shr) == 0) {
        long long li, ri;
        if (is_number(left) && is_number(right) &&
            as_long_long(left, &li) == 0 && as_long_long(right, &ri) == 0) {
            PyObject *li_o = PyLong_FromLongLong(li);
            PyObject *ri_o = PyLong_FromLongLong(ri);
            if (li_o != NULL && ri_o != NULL) {
                if (op == S_op_band || PyUnicode_Compare(op, S_op_band) == 0) result = PyNumber_And(li_o, ri_o);
                else if (op == S_op_bor || PyUnicode_Compare(op, S_op_bor) == 0) result = PyNumber_Or(li_o, ri_o);
                else if (op == S_op_bxor || PyUnicode_Compare(op, S_op_bxor) == 0) result = PyNumber_Xor(li_o, ri_o);
                else if (op == S_op_shl || PyUnicode_Compare(op, S_op_shl) == 0) result = PyNumber_Lshift(li_o, ri_o);
                else result = PyNumber_Rshift(li_o, ri_o);
            }
            Py_XDECREF(li_o); Py_XDECREF(ri_o);
        }
    }

    Py_DECREF(left);
    Py_DECREF(right);
    if (result == NULL && !PyErr_Occurred()) Py_RETURN_NONE;
    return result;
}

static PyObject *eval_unary(PyObject *un_dict, PyObject *options,
                            PyObject *locals_, int builtins,
                            PyObject *script, PyObject *statement)
{
    PyObject *op = PyDict_GetItemWithError(un_dict, S_op);
    PyObject *expr = PyDict_GetItemWithError(un_dict, S_expr);
    if (op == NULL || expr == NULL) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "unary missing");
        return NULL;
    }
    PyObject *value = eval_expression(expr, options, locals_, builtins, script, statement);
    if (value == NULL) return NULL;

    if (op == S_op_unot || PyUnicode_Compare(op, S_op_unot) == 0) {
        int t = call_value_boolean(value);
        Py_DECREF(value);
        if (t < 0) return NULL;
        PyObject *r = t ? Py_False : Py_True;
        Py_INCREF(r);
        return r;
    }
    if (op == S_op_uneg || PyUnicode_Compare(op, S_op_uneg) == 0) {
        if (is_number(value)) {
            PyObject *r = PyNumber_Negative(value);
            Py_DECREF(value);
            return r;
        }
        Py_DECREF(value);
        Py_RETURN_NONE;
    }
    /* '~' */
    if (is_number(value)) {
        long long iv;
        if (as_long_long(value, &iv) == 0) {
            Py_DECREF(value);
            PyObject *iv_o = PyLong_FromLongLong(iv);
            if (iv_o == NULL) return NULL;
            PyObject *r = PyNumber_Invert(iv_o);
            Py_DECREF(iv_o);
            return r;
        }
    }
    Py_DECREF(value);
    Py_RETURN_NONE;
}

static PyObject *eval_expression(PyObject *expr, PyObject *options,
                                 PyObject *locals_, int builtins,
                                 PyObject *script, PyObject *statement)
{
    if (!PyDict_Check(expr)) {
        PyErr_SetString(PyExc_TypeError, "expression must be a dict");
        return NULL;
    }
    PyObject *key = get_only_key(expr);
    if (key == NULL) return NULL;
    PyObject *value;

    /* Pointer-identity fast path then equality fallback */
    if (key == S_number || PyUnicode_Compare(key, S_number) == 0) {
        value = PyDict_GetItemWithError(expr, S_number);
        if (value == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "number"); return NULL; }
        Py_INCREF(value);
        return value;
    }
    if (key == S_string || PyUnicode_Compare(key, S_string) == 0) {
        value = PyDict_GetItemWithError(expr, S_string);
        if (value == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "string"); return NULL; }
        Py_INCREF(value);
        return value;
    }
    if (key == S_variable || PyUnicode_Compare(key, S_variable) == 0) {
        PyObject *var_name = PyDict_GetItemWithError(expr, S_variable);
        if (var_name == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "variable"); return NULL; }
        /* Keywords */
        if (PyUnicode_Check(var_name)) {
            if (PyUnicode_Compare(var_name, S_null) == 0) Py_RETURN_NONE;
            if (PyUnicode_Compare(var_name, S_false) == 0) { Py_INCREF(Py_False); return Py_False; }
            if (PyUnicode_Compare(var_name, S_true) == 0) { Py_INCREF(Py_True); return Py_True; }
        }
        if (locals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(locals_, var_name);
            if (v != NULL) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        if (options != NULL) {
            PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
            if (globals_ == NULL && PyErr_Occurred()) { PyErr_Clear(); }
            if (globals_ != NULL) {
                PyObject *v = PyDict_GetItemWithError(globals_, var_name);
                if (v != NULL) { Py_INCREF(v); return v; }
                if (PyErr_Occurred()) return NULL;
            }
        }
        Py_RETURN_NONE;
    }
    if (key == S_function || PyUnicode_Compare(key, S_function) == 0) {
        PyObject *fn = PyDict_GetItemWithError(expr, S_function);
        if (fn == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "function"); return NULL; }
        return eval_function(fn, options, locals_, builtins, script, statement);
    }
    if (key == S_binary || PyUnicode_Compare(key, S_binary) == 0) {
        PyObject *bn = PyDict_GetItemWithError(expr, S_binary);
        if (bn == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "binary"); return NULL; }
        return eval_binary(bn, options, locals_, builtins, script, statement);
    }
    if (key == S_unary || PyUnicode_Compare(key, S_unary) == 0) {
        PyObject *un = PyDict_GetItemWithError(expr, S_unary);
        if (un == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "unary"); return NULL; }
        return eval_unary(un, options, locals_, builtins, script, statement);
    }
    /* group */
    PyObject *grp = PyDict_GetItemWithError(expr, S_group);
    if (grp == NULL) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "group"); return NULL; }
    return eval_expression(grp, options, locals_, builtins, script, statement);
}

/* ----- Script function (functools.partial replacement) ------------------ */

/*
 * We mirror runtime.py's `functools.partial(_script_function, script, function)`
 * by creating a partial via functools at function-definition time.
 *
 * Defined functions go into globals_ as a callable taking (args, options).
 */

static PyObject *py_script_function(PyObject *self, PyObject *args)
{
    PyObject *script, *function, *call_args, *options;
    if (!PyArg_UnpackTuple(args, "_script_function", 4, 4, &script, &function, &call_args, &options))
        return NULL;

    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    PyObject *func_args = PyDict_GetItemWithError(function, S_args);
    if (func_args == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
    if (func_args != NULL && func_args != Py_None && PyList_Check(func_args)) {
        Py_ssize_t args_length = PyList_Check(call_args) ? PyList_GET_SIZE(call_args) : 0;
        Py_ssize_t func_args_length = PyList_GET_SIZE(func_args);
        PyObject *last_arg_array = PyDict_GetItemWithError(function, S_lastArgArray);
        if (last_arg_array == NULL && PyErr_Occurred()) PyErr_Clear();
        int has_last_arg = last_arg_array != NULL && PyObject_IsTrue(last_arg_array) == 1;
        Py_ssize_t ix_arg_last = has_last_arg ? (func_args_length - 1) : -1;
        for (Py_ssize_t i = 0; i < func_args_length; i++) {
            PyObject *arg_name = PyList_GET_ITEM(func_args, i);
            PyObject *v;
            if (i < args_length) {
                if (i != ix_arg_last) {
                    v = PyList_GET_ITEM(call_args, i);
                    Py_INCREF(v);
                } else {
                    /* args[ix_arg:] */
                    v = PyList_GetSlice(call_args, i, args_length);
                    if (v == NULL) { Py_DECREF(func_locals); return NULL; }
                }
            } else {
                if (i == ix_arg_last) {
                    v = PyList_New(0);
                    if (v == NULL) { Py_DECREF(func_locals); return NULL; }
                } else {
                    Py_INCREF(Py_None);
                    v = Py_None;
                }
            }
            if (PyDict_SetItem(func_locals, arg_name, v) < 0) {
                Py_DECREF(v); Py_DECREF(func_locals); return NULL;
            }
            Py_DECREF(v);
        }
    }

    PyObject *statements = PyDict_GetItemWithError(function, S_statements);
    if (statements == NULL) {
        Py_DECREF(func_locals);
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "function 'statements'");
        return NULL;
    }
    PyObject *result = execute_script_helper(script, statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}

static PyMethodDef ScriptFunctionMethod = {
    "_script_function", py_script_function, METH_VARARGS, NULL
};

/* ----- execute_script_helper -------------------------------------------- */

static PyObject *execute_script_helper(PyObject *script, PyObject *statements,
                                       PyObject *options, PyObject *locals_)
{
    if (!PyList_Check(statements)) {
        PyErr_SetString(PyExc_TypeError, "statements must be a list");
        return NULL;
    }

    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL && PyErr_Occurred()) PyErr_Clear();

    PyObject *label_indexes = NULL; /* dict, only on first jump */
    Py_ssize_t statements_length = PyList_GET_SIZE(statements);
    Py_ssize_t ix_statement = 0;

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_GET_ITEM(statements, ix_statement);
        PyObject *statement_key = get_only_key(statement);
        if (statement_key == NULL) { Py_XDECREF(label_indexes); return NULL; }

        /* Increment the statement counter */
        PyObject *count_obj = PyDict_GetItemWithError(options, S_statementCount);
        if (count_obj == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
        long long count = count_obj != NULL ? PyLong_AsLongLong(count_obj) : 0;
        if (count == -1 && PyErr_Occurred()) PyErr_Clear();
        count += 1;
        PyObject *new_count = PyLong_FromLongLong(count);
        if (new_count == NULL) { Py_XDECREF(label_indexes); return NULL; }
        if (PyDict_SetItem(options, S_statementCount, new_count) < 0) {
            Py_DECREF(new_count); Py_XDECREF(label_indexes); return NULL;
        }
        Py_DECREF(new_count);

        PyObject *max_statements_obj = PyDict_GetItemWithError(options, S_maxStatements);
        if (max_statements_obj == NULL && PyErr_Occurred()) PyErr_Clear();
        if (max_statements_obj == NULL) max_statements_obj = PY_DEFAULT_MAX_STATEMENTS;
        double max_stmts = 0.0;
        if (as_double(max_statements_obj, &max_stmts) != 0) {
            PyErr_Clear();
            max_stmts = (double)PyLong_AsLongLong(max_statements_obj);
            if (PyErr_Occurred()) PyErr_Clear();
        }
        if (max_stmts > 0 && (double)count > max_stmts) {
            PyObject *m = PyUnicode_FromFormat("Exceeded maximum script statements (%S)", max_statements_obj);
            PyObject *err = PyObject_CallFunctionObjArgs(
                PY_BareScriptRuntimeError,
                script ? script : Py_None,
                statement,
                m,
                NULL);
            Py_XDECREF(m);
            if (err != NULL) {
                PyErr_SetObject(PY_BareScriptRuntimeError, err);
                Py_DECREF(err);
            }
            Py_XDECREF(label_indexes);
            return NULL;
        }

        /* Coverage */
        PyObject *coverage_global = NULL;
        int has_coverage = 0;
        if (globals_ != NULL) {
            coverage_global = PyDict_GetItemWithError(globals_, S_COVERAGE_GLOBAL);
            if (coverage_global == NULL && PyErr_Occurred()) PyErr_Clear();
            if (coverage_global != NULL && PyDict_Check(coverage_global)) {
                PyObject *enabled = PyDict_GetItemWithError(coverage_global, S_enabled);
                if (enabled == NULL && PyErr_Occurred()) PyErr_Clear();
                PyObject *sys = script != NULL ? PyDict_GetItemWithError(script, S_system) : NULL;
                if (sys == NULL && PyErr_Occurred()) PyErr_Clear();
                int e = enabled != NULL && PyObject_IsTrue(enabled) == 1;
                int s = sys != NULL && PyObject_IsTrue(sys) == 1;
                if (e && !s) has_coverage = 1;
            }
        }
        if (has_coverage) {
            record_statement_coverage(script, statement, statement_key, coverage_global);
        }

        /* Statement dispatch */
        if (statement_key == S_expr || PyUnicode_Compare(statement_key, S_expr) == 0) {
            PyObject *body = PyDict_GetItem(statement, S_expr);
            PyObject *expr_field = PyDict_GetItem(body, S_expr);
            PyObject *expr_value = eval_expression(expr_field, options, locals_, 0, script, statement);
            if (expr_value == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *expr_name = PyDict_GetItemWithError(body, S_name);
            if (expr_name == NULL && PyErr_Occurred()) {
                Py_DECREF(expr_value); Py_XDECREF(label_indexes); return NULL;
            }
            if (expr_name != NULL) {
                if (locals_ != NULL) {
                    if (PyDict_SetItem(locals_, expr_name, expr_value) < 0) {
                        Py_DECREF(expr_value); Py_XDECREF(label_indexes); return NULL;
                    }
                } else if (globals_ != NULL) {
                    if (PyDict_SetItem(globals_, expr_name, expr_value) < 0) {
                        Py_DECREF(expr_value); Py_XDECREF(label_indexes); return NULL;
                    }
                }
            }
            Py_DECREF(expr_value);
        } else if (statement_key == S_jump || PyUnicode_Compare(statement_key, S_jump) == 0) {
            PyObject *jump = PyDict_GetItem(statement, S_jump);
            PyObject *jump_expr = PyDict_GetItemWithError(jump, S_expr);
            if (jump_expr == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            int do_jump;
            if (jump_expr == NULL) {
                do_jump = 1;
            } else {
                PyObject *v = eval_expression(jump_expr, options, locals_, 0, script, statement);
                if (v == NULL) { Py_XDECREF(label_indexes); return NULL; }
                int t = call_value_boolean(v);
                Py_DECREF(v);
                if (t < 0) { Py_XDECREF(label_indexes); return NULL; }
                do_jump = t;
            }
            if (do_jump) {
                PyObject *label_name = PyDict_GetItem(jump, S_label);
                PyObject *cached = NULL;
                if (label_indexes != NULL) {
                    cached = PyDict_GetItemWithError(label_indexes, label_name);
                    if (cached == NULL && PyErr_Occurred()) PyErr_Clear();
                }
                Py_ssize_t ix_label = -1;
                if (cached != NULL) {
                    ix_label = PyLong_AsSsize_t(cached);
                } else {
                    /* Search for the label */
                    for (Py_ssize_t i = 0; i < statements_length; i++) {
                        PyObject *stmt = PyList_GET_ITEM(statements, i);
                        PyObject *lbl = PyDict_GetItemWithError(stmt, S_label);
                        if (lbl == NULL) { if (PyErr_Occurred()) PyErr_Clear(); continue; }
                        PyObject *nm = PyDict_GetItemWithError(lbl, S_name);
                        if (nm == NULL) { if (PyErr_Occurred()) PyErr_Clear(); continue; }
                        if (PyUnicode_Compare(nm, label_name) == 0) {
                            ix_label = i;
                            break;
                        }
                    }
                    if (ix_label == -1) {
                        raise_runtime_error(script, statement, "Unknown jump label \"%S\"", label_name);
                        Py_XDECREF(label_indexes);
                        return NULL;
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) return NULL;
                    }
                    PyObject *ix_o = PyLong_FromSsize_t(ix_label);
                    PyDict_SetItem(label_indexes, label_name, ix_o);
                    Py_DECREF(ix_o);
                }
                ix_statement = ix_label;

                if (has_coverage) {
                    PyObject *label_statement = PyList_GET_ITEM(statements, ix_statement);
                    PyObject *label_key = get_only_key(label_statement);
                    if (label_key != NULL) {
                        record_statement_coverage(script, label_statement, label_key, coverage_global);
                    }
                }
            }
        } else if (statement_key == S_return || PyUnicode_Compare(statement_key, S_return) == 0) {
            PyObject *ret = PyDict_GetItem(statement, S_return);
            PyObject *ret_expr = PyDict_GetItemWithError(ret, S_expr);
            if (ret_expr == NULL && PyErr_Occurred()) { Py_XDECREF(label_indexes); return NULL; }
            Py_XDECREF(label_indexes);
            if (ret_expr != NULL) {
                return eval_expression(ret_expr, options, locals_, 0, script, statement);
            }
            Py_RETURN_NONE;
        } else if (statement_key == S_function || PyUnicode_Compare(statement_key, S_function) == 0) {
            PyObject *fn = PyDict_GetItem(statement, S_function);
            PyObject *fn_name = PyDict_GetItem(fn, S_name);
            PyObject *sf_callable = PyCFunction_New(&ScriptFunctionMethod, NULL);
            if (sf_callable == NULL) { Py_XDECREF(label_indexes); return NULL; }
            PyObject *partial = PyObject_CallFunctionObjArgs(
                PY_functools_partial, sf_callable, script, fn, NULL);
            Py_DECREF(sf_callable);
            if (partial == NULL) { Py_XDECREF(label_indexes); return NULL; }
            if (globals_ != NULL) PyDict_SetItem(globals_, fn_name, partial);
            Py_DECREF(partial);
        } else if (statement_key == S_include || PyUnicode_Compare(statement_key, S_include) == 0) {
            PyObject *inc = PyDict_GetItem(statement, S_include);
            PyObject *system_prefix = PyDict_GetItemWithError(options, S_systemPrefix);
            if (system_prefix == NULL && PyErr_Occurred()) PyErr_Clear();
            PyObject *fetch_fn = PyDict_GetItemWithError(options, S_fetchFn);
            if (fetch_fn == NULL && PyErr_Occurred()) PyErr_Clear();
            PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
            if (log_fn == NULL && PyErr_Occurred()) PyErr_Clear();
            PyObject *url_fn = PyDict_GetItemWithError(options, S_urlFn);
            if (url_fn == NULL && PyErr_Occurred()) PyErr_Clear();
            PyObject *includes_list = PyDict_GetItem(inc, S_includes);
            if (!PyList_Check(includes_list)) {
                PyErr_SetString(PyExc_TypeError, "include 'includes' must be a list");
                Py_XDECREF(label_indexes); return NULL;
            }
            for (Py_ssize_t ii = 0; ii < PyList_GET_SIZE(includes_list); ii++) {
                PyObject *include = PyList_GET_ITEM(includes_list, ii);
                PyObject *include_url = PyDict_GetItem(include, S_url);
                Py_INCREF(include_url);
                PyObject *system_include = PyDict_GetItemWithError(include, S_system);
                if (system_include == NULL && PyErr_Occurred()) PyErr_Clear();
                int is_system = system_include != NULL && PyObject_IsTrue(system_include) == 1;
                if (is_system && system_prefix != NULL) {
                    PyObject *new_url = PyObject_CallFunctionObjArgs(PY_url_file_relative, system_prefix, include_url, NULL);
                    Py_DECREF(include_url);
                    if (new_url == NULL) { Py_XDECREF(label_indexes); return NULL; }
                    include_url = new_url;
                } else if (url_fn != NULL) {
                    PyObject *new_url = PyObject_CallOneArg(url_fn, include_url);
                    Py_DECREF(include_url);
                    if (new_url == NULL) { Py_XDECREF(label_indexes); return NULL; }
                    include_url = new_url;
                }

                /* global_includes */
                PyObject *global_includes = globals_ != NULL ? PyDict_GetItemWithError(globals_, S_INCLUDES_GLOBAL) : NULL;
                if (global_includes == NULL && PyErr_Occurred()) PyErr_Clear();
                if (global_includes == NULL || !PyDict_Check(global_includes)) {
                    global_includes = PyDict_New();
                    if (globals_ != NULL) PyDict_SetItem(globals_, S_INCLUDES_GLOBAL, global_includes);
                    Py_DECREF(global_includes);
                    global_includes = globals_ != NULL ? PyDict_GetItem(globals_, S_INCLUDES_GLOBAL) : NULL;
                }
                PyObject *already = global_includes != NULL ? PyDict_GetItemWithError(global_includes, include_url) : NULL;
                if (already == NULL && PyErr_Occurred()) PyErr_Clear();
                if (already != NULL && PyObject_IsTrue(already) == 1) {
                    Py_DECREF(include_url);
                    continue;
                }
                if (global_includes != NULL)
                    PyDict_SetItem(global_includes, include_url, Py_True);

                /* Fetch */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *req = PyDict_New();
                    PyDict_SetItem(req, S_url, include_url);
                    include_text = PyObject_CallOneArg(fetch_fn, req);
                    Py_DECREF(req);
                    if (include_text == NULL) { PyErr_Clear(); include_text = NULL; }
                }
                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    PyObject *m = PyUnicode_FromFormat("Include of \"%S\" failed", include_url);
                    PyObject *err = PyObject_CallFunctionObjArgs(
                        PY_BareScriptRuntimeError,
                        script ? script : Py_None,
                        statement, m, NULL);
                    Py_XDECREF(m);
                    if (err != NULL) {
                        PyErr_SetObject(PY_BareScriptRuntimeError, err);
                        Py_DECREF(err);
                    }
                    Py_DECREF(include_url);
                    Py_XDECREF(label_indexes);
                    return NULL;
                }

                /* parse_script(include_text, 1, include_url) */
                PyObject *one = PyLong_FromLong(1);
                PyObject *include_script = PyObject_CallFunctionObjArgs(
                    PY_parse_script, include_text, one, include_url, NULL);
                Py_DECREF(one);
                Py_DECREF(include_text);
                if (include_script == NULL) {
                    Py_DECREF(include_url); Py_XDECREF(label_indexes); return NULL;
                }
                if (is_system) {
                    PyDict_SetItem(include_script, S_system, Py_True);
                }

                /* include_options = options.copy() */
                PyObject *include_options = PyDict_Copy(options);
                if (include_options == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); Py_XDECREF(label_indexes); return NULL;
                }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(
                    PY_functools_partial, PY_url_file_relative, include_url, NULL);
                if (new_url_fn != NULL) {
                    PyDict_SetItem(include_options, S_urlFn, new_url_fn);
                    Py_DECREF(new_url_fn);
                }

                /* Execute include */
                PyObject *include_statements = PyDict_GetItem(include_script, S_statements);
                PyObject *r = execute_script_helper(include_script, include_statements, include_options, NULL);
                Py_DECREF(include_options);
                Py_XDECREF(r);
                if (r == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); Py_XDECREF(label_indexes); return NULL;
                }

                /* lint */
                if (log_fn != NULL) {
                    PyObject *dbg = PyDict_GetItemWithError(options, S_debug);
                    if (dbg == NULL && PyErr_Occurred()) PyErr_Clear();
                    if (dbg != NULL && PyObject_IsTrue(dbg) == 1) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(
                            PY_lint_script, include_script, globals_, NULL);
                        if (warnings != NULL) {
                            Py_ssize_t wlen = PyList_Check(warnings) ? PyList_GET_SIZE(warnings) : 0;
                            if (wlen > 0) {
                                const char *plural = wlen > 1 ? "s" : "";
                                PyObject *hdr = PyUnicode_FromFormat(
                                    "BareScript: Include \"%S\" static analysis... %zd warning%s:",
                                    include_url, wlen, plural);
                                if (hdr != NULL) {
                                    PyObject *r2 = PyObject_CallOneArg(log_fn, hdr);
                                    Py_XDECREF(r2);
                                    Py_DECREF(hdr);
                                }
                                for (Py_ssize_t wi = 0; wi < wlen; wi++) {
                                    PyObject *warning = PyList_GET_ITEM(warnings, wi);
                                    PyObject *m = PyUnicode_FromFormat("BareScript: %S", warning);
                                    if (m != NULL) {
                                        PyObject *r3 = PyObject_CallOneArg(log_fn, m);
                                        Py_XDECREF(r3);
                                        Py_DECREF(m);
                                    }
                                }
                            }
                            Py_DECREF(warnings);
                        } else {
                            PyErr_Clear();
                        }
                    }
                }
                Py_DECREF(include_script);
                Py_DECREF(include_url);
            }
        }
        /* labels: no action */

        ix_statement++;
    }

    Py_XDECREF(label_indexes);
    Py_RETURN_NONE;
}

/* ----- Public functions: execute_script and evaluate_expression --------- */

static PyObject *py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script;
    PyObject *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &script, &options))
        return NULL;

    if (options == Py_None) {
        options = PyDict_New();
        if (options == NULL) return NULL;
    } else {
        Py_INCREF(options);
    }

    /* Ensure 'globals' */
    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL && PyErr_Occurred()) { Py_DECREF(options); return NULL; }
    if (globals_ == NULL) {
        globals_ = PyDict_New();
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
        PyDict_SetItem(options, S_globals, globals_);
        Py_DECREF(globals_);
        globals_ = PyDict_GetItem(options, S_globals);
    }

    /* Set script function globals where not overridden */
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(PY_SCRIPT_FUNCTIONS, &pos, &key, &value)) {
        int contains = PyDict_Contains(globals_, key);
        if (contains < 0) { Py_DECREF(options); return NULL; }
        if (!contains) PyDict_SetItem(globals_, key, value);
    }

    /* statementCount = 0 */
    PyObject *zero = PyLong_FromLong(0);
    PyDict_SetItem(options, S_statementCount, zero);
    Py_DECREF(zero);

    PyObject *statements = PyDict_GetItem(script, S_statements);
    if (statements == NULL) {
        PyErr_SetString(PyExc_KeyError, "script 'statements'");
        Py_DECREF(options);
        return NULL;
    }
    PyObject *result = execute_script_helper(script, statements, options, NULL);
    Py_DECREF(options);
    return result;
}

static PyObject *py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr;
    PyObject *options = Py_None;
    PyObject *locals_ = Py_None;
    int builtins = 1;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOpOO", kwlist,
                                     &expr, &options, &locals_, &builtins, &script, &statement))
        return NULL;
    return eval_expression(expr,
                           options == Py_None ? NULL : options,
                           locals_ == Py_None ? NULL : locals_,
                           builtins,
                           script == Py_None ? NULL : script,
                           statement == Py_None ? NULL : statement);
}

/* ----- Module initialization ------------------------------------------- */

static PyMethodDef ModuleMethods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS,
     "Execute a BareScript model."},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS,
     "Evaluate an expression model."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef ModuleDef = {
    PyModuleDef_HEAD_INIT, "runtime_c", "BareScript runtime (C implementation)",
    -1, ModuleMethods, NULL, NULL, NULL, NULL
};

static int intern(PyObject **out, const char *s) {
    PyObject *o = PyUnicode_InternFromString(s);
    if (o == NULL) return -1;
    *out = o;
    return 0;
}

#define INTERN(var, s) do { if (intern(&(var), (s)) < 0) return NULL; } while (0)

PyMODINIT_FUNC PyInit_runtime_c(void)
{
    /* Intern strings */
    INTERN(S_expr, "expr");
    INTERN(S_jump, "jump");
    INTERN(S_return, "return");
    INTERN(S_function, "function");
    INTERN(S_include, "include");
    INTERN(S_label, "label");
    INTERN(S_name, "name");
    INTERN(S_globals, "globals");
    INTERN(S_statementCount, "statementCount");
    INTERN(S_maxStatements, "maxStatements");
    INTERN(S_statements, "statements");
    INTERN(S_lineNumber, "lineNumber");
    INTERN(S_scriptName, "scriptName");
    INTERN(S_scripts, "scripts");
    INTERN(S_covered, "covered");
    INTERN(S_count, "count");
    INTERN(S_statement, "statement");
    INTERN(S_script, "script");
    INTERN(S_enabled, "enabled");
    INTERN(S_system, "system");
    INTERN(S_includes, "includes");
    INTERN(S_systemPrefix, "systemPrefix");
    INTERN(S_fetchFn, "fetchFn");
    INTERN(S_logFn, "logFn");
    INTERN(S_urlFn, "urlFn");
    INTERN(S_url, "url");
    INTERN(S_debug, "debug");
    INTERN(S_args, "args");
    INTERN(S_lastArgArray, "lastArgArray");
    INTERN(S_variable, "variable");
    INTERN(S_number, "number");
    INTERN(S_string, "string");
    INTERN(S_binary, "binary");
    INTERN(S_unary, "unary");
    INTERN(S_group, "group");
    INTERN(S_left, "left");
    INTERN(S_right, "right");
    INTERN(S_op, "op");
    INTERN(S_null, "null");
    INTERN(S_true, "true");
    INTERN(S_false, "false");
    INTERN(S_if, "if");

    INTERN(S_op_and, "&&");
    INTERN(S_op_or, "||");
    INTERN(S_op_add, "+");
    INTERN(S_op_sub, "-");
    INTERN(S_op_mul, "*");
    INTERN(S_op_div, "/");
    INTERN(S_op_eq, "==");
    INTERN(S_op_ne, "!=");
    INTERN(S_op_lte, "<=");
    INTERN(S_op_lt, "<");
    INTERN(S_op_gte, ">=");
    INTERN(S_op_gt, ">");
    INTERN(S_op_mod, "%");
    INTERN(S_op_pow, "**");
    INTERN(S_op_band, "&");
    INTERN(S_op_bor, "|");
    INTERN(S_op_bxor, "^");
    INTERN(S_op_shl, "<<");
    INTERN(S_op_shr, ">>");
    INTERN(S_op_unot, "!");
    INTERN(S_op_uneg, "-");
    INTERN(S_op_uinv, "~");

    INTERN(S_COVERAGE_GLOBAL, "__barescriptCoverage");
    INTERN(S_INCLUDES_GLOBAL, "__barescriptIncludes");

    /* Import library/value/parser/options/model/datetime modules */
    PyObject *m;

    m = PyImport_ImportModule("bare_script.library");
    if (m == NULL) return NULL;
    PY_SCRIPT_FUNCTIONS = PyObject_GetAttrString(m, "SCRIPT_FUNCTIONS");
    PY_EXPRESSION_FUNCTIONS = PyObject_GetAttrString(m, "EXPRESSION_FUNCTIONS");
    Py_DECREF(m);
    if (PY_SCRIPT_FUNCTIONS == NULL || PY_EXPRESSION_FUNCTIONS == NULL) return NULL;

    m = PyImport_ImportModule("bare_script.model");
    if (m == NULL) return NULL;
    PY_lint_script = PyObject_GetAttrString(m, "lint_script");
    Py_DECREF(m);
    if (PY_lint_script == NULL) return NULL;

    m = PyImport_ImportModule("bare_script.options");
    if (m == NULL) return NULL;
    PY_url_file_relative = PyObject_GetAttrString(m, "url_file_relative");
    Py_DECREF(m);
    if (PY_url_file_relative == NULL) return NULL;

    m = PyImport_ImportModule("bare_script.parser");
    if (m == NULL) return NULL;
    PY_parse_script = PyObject_GetAttrString(m, "parse_script");
    Py_DECREF(m);
    if (PY_parse_script == NULL) return NULL;

    m = PyImport_ImportModule("bare_script.value");
    if (m == NULL) return NULL;
    PY_value_boolean = PyObject_GetAttrString(m, "value_boolean");
    PY_value_compare = PyObject_GetAttrString(m, "value_compare");
    PY_value_string = PyObject_GetAttrString(m, "value_string");
    PY_value_normalize_datetime = PyObject_GetAttrString(m, "value_normalize_datetime");
    PY_value_round_number = PyObject_GetAttrString(m, "value_round_number");
    PY_ValueArgsError = PyObject_GetAttrString(m, "ValueArgsError");
    Py_DECREF(m);
    if (PY_value_boolean == NULL || PY_value_compare == NULL || PY_value_string == NULL
        || PY_value_normalize_datetime == NULL || PY_value_round_number == NULL
        || PY_ValueArgsError == NULL) return NULL;

    m = PyImport_ImportModule("bare_script.runtime");
    if (m == NULL) return NULL;
    PY_BareScriptRuntimeError = PyObject_GetAttrString(m, "BareScriptRuntimeError");
    Py_DECREF(m);
    if (PY_BareScriptRuntimeError == NULL) return NULL;

    m = PyImport_ImportModule("datetime");
    if (m == NULL) return NULL;
    PY_datetime_date = PyObject_GetAttrString(m, "date");
    PY_datetime_timedelta = PyObject_GetAttrString(m, "timedelta");
    Py_DECREF(m);
    if (PY_datetime_date == NULL || PY_datetime_timedelta == NULL) return NULL;

    m = PyImport_ImportModule("functools");
    if (m == NULL) return NULL;
    PY_functools_partial = PyObject_GetAttrString(m, "partial");
    Py_DECREF(m);
    if (PY_functools_partial == NULL) return NULL;

    PY_DEFAULT_MAX_STATEMENTS = PyFloat_FromDouble(1e9);
    if (PY_DEFAULT_MAX_STATEMENTS == NULL) return NULL;

    /* Create module */
    PyObject *module = PyModule_Create(&ModuleDef);
    if (module == NULL) return NULL;
    PyModule_AddObject(module, "BareScriptRuntimeError",
                       (Py_INCREF(PY_BareScriptRuntimeError), PY_BareScriptRuntimeError));
    return module;
}
