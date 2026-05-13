/*
 * Licensed under the MIT License
 * https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE
 *
 * BareScript runtime - C extension implementation.
 *
 * This file mirrors src/bare_script/runtime.py. runtime.py is the source of
 * truth - keep them in sync. See CLAUDE.md for details.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>


/* ---------------------------------------------------------------------------
 * Module-level cached references
 * ------------------------------------------------------------------------- */

static PyObject *g_value_compare = NULL;
static PyObject *g_value_normalize_datetime = NULL;
static PyObject *g_value_round_number = NULL;
static PyObject *g_value_string = NULL;
static PyObject *g_value_args_error = NULL;

static PyObject *g_script_functions = NULL;     /* SCRIPT_FUNCTIONS dict */
static PyObject *g_expression_functions = NULL; /* EXPRESSION_FUNCTIONS dict */
static PyObject *g_lint_script = NULL;
static PyObject *g_url_file_relative = NULL;
static PyObject *g_parse_script = NULL;
static PyObject *g_runtime_error = NULL;
static PyObject *g_functools_partial = NULL;
static PyObject *g_datetime_date = NULL;
static PyObject *g_datetime_datetime = NULL;
static PyObject *g_datetime_timedelta = NULL;

/* Cached interned strings */
static PyObject *S_expr = NULL;
static PyObject *S_name = NULL;
static PyObject *S_args = NULL;
static PyObject *S_function = NULL;
static PyObject *S_variable = NULL;
static PyObject *S_number = NULL;
static PyObject *S_string = NULL;
static PyObject *S_binary = NULL;
static PyObject *S_unary = NULL;
static PyObject *S_group = NULL;
static PyObject *S_op = NULL;
static PyObject *S_left = NULL;
static PyObject *S_right = NULL;
static PyObject *S_label = NULL;
static PyObject *S_jump = NULL;
static PyObject *S_return = NULL;
static PyObject *S_include = NULL;
static PyObject *S_includes = NULL;
static PyObject *S_url = NULL;
static PyObject *S_system = NULL;
static PyObject *S_lineNumber = NULL;
static PyObject *S_scriptName = NULL;
static PyObject *S_statements = NULL;
static PyObject *S_lastArgArray = NULL;

static PyObject *S_globals = NULL;
static PyObject *S_statementCount = NULL;
static PyObject *S_maxStatements = NULL;
static PyObject *S_fetchFn = NULL;
static PyObject *S_logFn = NULL;
static PyObject *S_urlFn = NULL;
static PyObject *S_systemPrefix = NULL;
static PyObject *S_debug = NULL;
static PyObject *S_enabled = NULL;
static PyObject *S_scripts = NULL;
static PyObject *S_covered = NULL;
static PyObject *S_statement = NULL;
static PyObject *S_count = NULL;
static PyObject *S_script = NULL;
static PyObject *S_null = NULL;
static PyObject *S_false = NULL;
static PyObject *S_true = NULL;
static PyObject *S_if = NULL;
static PyObject *S_return_value = NULL;

static PyObject *S_cov_global = NULL;     /* __barescriptCoverage */
static PyObject *S_includes_global = NULL; /* __barescriptIncludes */

/* Default max statements: 1e9 */
static double g_default_max_statements = 1e9;

/* Thread-local statement counter. Sync'd to options['statementCount'] only at
 * top-level entry/exit boundaries (when helper_depth transitions 0 <-> 1).
 * Inside the loop we use the bare long, avoiding a dict update per statement. */
static __thread long g_stmt_counter = 0;
static __thread int g_helper_depth = 0;


/* ---------------------------------------------------------------------------
 * Forward declarations
 * ------------------------------------------------------------------------- */

static PyObject *exec_script_helper(PyObject *script, PyObject *statements,
                                    PyObject *options, PyObject *locals_);
static PyObject *eval_expression(PyObject *expr, PyObject *options, PyObject *locals_,
                                 int builtins, PyObject *script, PyObject *statement);


/* ---------------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------------- */

/* Set BareScriptRuntimeError(script, statement, message) and return NULL */
static PyObject *
raise_runtime_error(PyObject *script, PyObject *statement, const char *message_fmt, PyObject *fmt_arg)
{
    PyObject *msg;
    if (fmt_arg != NULL) {
        msg = PyUnicode_FromFormat(message_fmt, fmt_arg);
    } else {
        msg = PyUnicode_FromString(message_fmt);
    }
    if (msg == NULL) {
        return NULL;
    }
    PyObject *script_arg = (script == NULL) ? Py_None : script;
    PyObject *statement_arg = (statement == NULL) ? Py_None : statement;
    PyObject *exc = PyObject_CallFunctionObjArgs(g_runtime_error, script_arg, statement_arg, msg, NULL);
    Py_DECREF(msg);
    if (exc == NULL) {
        return NULL;
    }
    PyErr_SetObject(g_runtime_error, exc);
    Py_DECREF(exc);
    return NULL;
}


/* Fast C value_boolean - mirrors value.value_boolean */
static int
value_boolean_c(PyObject *v)
{
    if (v == Py_None) return 0;
    if (PyBool_Check(v)) return v == Py_True;
    if (PyUnicode_Check(v)) return PyUnicode_GET_LENGTH(v) != 0;
    if (PyLong_Check(v)) return PyObject_IsTrue(v);
    if (PyFloat_Check(v)) return PyFloat_AS_DOUBLE(v) != 0.0;
    if (PyList_Check(v)) return PyList_GET_SIZE(v) != 0;
    return 1;
}


/* Helper: is value a "number" in BareScript sense (int or float, not bool) */
static inline int
is_number(PyObject *v)
{
    if (PyBool_Check(v)) return 0;
    return PyLong_Check(v) || PyFloat_Check(v);
}


/* Fast arithmetic for number/number. op_code: 0=+ 1=- 2=* 3=/.
 * Returns NULL on error (exc set) or a result. Caller must have already
 * checked is_number(l) && is_number(r). */
static PyObject *
fast_arith(PyObject *l, PyObject *r, int op_code)
{
    /* float + float / mixed: do as double */
    if (PyFloat_Check(l) || PyFloat_Check(r)) {
        double a, b;
        if (PyFloat_Check(l)) a = PyFloat_AS_DOUBLE(l);
        else {
            a = PyLong_AsDouble(l);
            if (a == -1.0 && PyErr_Occurred()) return NULL;
        }
        if (PyFloat_Check(r)) b = PyFloat_AS_DOUBLE(r);
        else {
            b = PyLong_AsDouble(r);
            if (b == -1.0 && PyErr_Occurred()) return NULL;
        }
        double d;
        switch (op_code) {
            case 0: d = a + b; break;
            case 1: d = a - b; break;
            case 2: d = a * b; break;
            case 3:
                if (b == 0.0) {
                    PyErr_SetString(PyExc_ZeroDivisionError, "float division by zero");
                    return NULL;
                }
                d = a / b; break;
            default: d = 0.0;
        }
        return PyFloat_FromDouble(d);
    }
    /* int op int — fall back to PyNumber for big-int correctness */
    switch (op_code) {
        case 0: return PyNumber_Add(l, r);
        case 1: return PyNumber_Subtract(l, r);
        case 2: return PyNumber_Multiply(l, r);
        case 3: return PyNumber_TrueDivide(l, r);
    }
    Py_RETURN_NONE;
}


/* Returns 1 if the number value is integral (no fractional part) */
static int
number_is_integral(PyObject *v)
{
    if (PyLong_Check(v)) return 1;
    if (PyFloat_Check(v)) {
        double d = PyFloat_AS_DOUBLE(v);
        if (d != d) return 0; /* NaN */
        if (d == (double)(long long)d) return 1;
        return 0;
    }
    return 0;
}


/* Get next dict key (single-key dict). Returns borrowed reference (or NULL). */
static PyObject *
dict_first_key(PyObject *d)
{
    Py_ssize_t pos = 0;
    PyObject *key = NULL, *value = NULL;
    if (PyDict_Next(d, &pos, &key, &value)) {
        return key;
    }
    return NULL;
}

/* Get first key+value of a dict (single-entry tagged dict). Borrowed refs. */
static int
dict_first_kv(PyObject *d, PyObject **key, PyObject **value)
{
    Py_ssize_t pos = 0;
    return PyDict_Next(d, &pos, key, value);
}


/* Returns 1 if isinstance(v, datetime.date) - uses cached class */
static int
is_datetime(PyObject *v)
{
    int r = PyObject_IsInstance(v, g_datetime_date);
    return r > 0;
}


/* ---------------------------------------------------------------------------
 * Coverage recording (matches _record_statement_coverage)
 * ------------------------------------------------------------------------- */

static int
record_statement_coverage(PyObject *script, PyObject *statement, PyObject *statement_key, PyObject *coverage_global)
{
    PyObject *script_name = PyDict_GetItemWithError(script, S_scriptName);
    if (script_name == NULL && PyErr_Occurred()) return -1;

    PyObject *stmt_inner = PyDict_GetItemWithError(statement, statement_key);
    if (stmt_inner == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    PyObject *lineno = PyDict_GetItemWithError(stmt_inner, S_lineNumber);
    if (lineno == NULL && PyErr_Occurred()) return -1;
    if (script_name == NULL || lineno == NULL) return 0;

    /* scripts dict */
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

    /* per-script entry */
    PyObject *script_coverage = PyDict_GetItemWithError(scripts, script_name);
    if (script_coverage == NULL) {
        if (PyErr_Occurred()) return -1;
        script_coverage = PyDict_New();
        if (script_coverage == NULL) return -1;
        PyObject *covered = PyDict_New();
        if (covered == NULL) { Py_DECREF(script_coverage); return -1; }
        if (PyDict_SetItem(script_coverage, S_script, script) < 0 ||
            PyDict_SetItem(script_coverage, S_covered, covered) < 0) {
            Py_DECREF(covered); Py_DECREF(script_coverage); return -1;
        }
        Py_DECREF(covered);
        if (PyDict_SetItem(scripts, script_name, script_coverage) < 0) {
            Py_DECREF(script_coverage);
            return -1;
        }
        Py_DECREF(script_coverage);
        script_coverage = PyDict_GetItemWithError(scripts, script_name);
        if (script_coverage == NULL) return -1;
    }

    PyObject *covered_dict = PyDict_GetItemWithError(script_coverage, S_covered);
    if (covered_dict == NULL) return -1;

    /* lineno_str = str(lineno) */
    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) return -1;

    PyObject *covered_statement = PyDict_GetItemWithError(covered_dict, lineno_str);
    if (covered_statement == NULL) {
        if (PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
        covered_statement = PyDict_New();
        if (covered_statement == NULL) { Py_DECREF(lineno_str); return -1; }
        PyObject *zero = PyLong_FromLong(0);
        if (zero == NULL ||
            PyDict_SetItem(covered_statement, S_statement, statement) < 0 ||
            PyDict_SetItem(covered_statement, S_count, zero) < 0) {
            Py_XDECREF(zero); Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(zero);
        if (PyDict_SetItem(covered_dict, lineno_str, covered_statement) < 0) {
            Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(covered_statement);
        covered_statement = PyDict_GetItemWithError(covered_dict, lineno_str);
        if (covered_statement == NULL) { Py_DECREF(lineno_str); return -1; }
    }
    Py_DECREF(lineno_str);

    /* count += 1 */
    PyObject *cur = PyDict_GetItemWithError(covered_statement, S_count);
    if (cur == NULL) return -1;
    PyObject *one = PyLong_FromLong(1);
    if (one == NULL) return -1;
    PyObject *new_count = PyNumber_Add(cur, one);
    Py_DECREF(one);
    if (new_count == NULL) return -1;
    int rc = PyDict_SetItem(covered_statement, S_count, new_count);
    Py_DECREF(new_count);
    return rc;
}


/* ---------------------------------------------------------------------------
 * Script function callable - mirrors functools.partial(_script_function, script, function)
 * Implementation: simple C type that owns (script, function) and is callable as f(args, options)
 * ------------------------------------------------------------------------- */

typedef struct {
    PyObject_HEAD
    PyObject *script;
    PyObject *function;
} ScriptFunctionObject;

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
    ScriptFunction_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* call: args=(args_list, options) */
static PyObject *
ScriptFunction_call(ScriptFunctionObject *self, PyObject *args, PyObject *kwargs)
{
    PyObject *call_args, *options;
    if (!PyArg_UnpackTuple(args, "ScriptFunction", 2, 2, &call_args, &options)) {
        return NULL;
    }

    PyObject *function = self->function;
    PyObject *script = self->script;

    /* func_locals = {} */
    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    /* func_args = function.get('args') */
    PyObject *func_args = PyDict_GetItemWithError(function, S_args);
    if (func_args == NULL && PyErr_Occurred()) {
        Py_DECREF(func_locals); return NULL;
    }
    if (func_args != NULL) {
        if (!PyList_Check(call_args)) {
            /* Convert to list to allow slicing */
        }
        Py_ssize_t args_length = PySequence_Size(call_args);
        if (args_length < 0) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t func_args_length = PyList_GET_SIZE(func_args);

        /* lastArgArray flag */
        PyObject *last_arg_array_flag = PyDict_GetItemWithError(function, S_lastArgArray);
        if (last_arg_array_flag == NULL && PyErr_Occurred()) {
            Py_DECREF(func_locals); return NULL;
        }
        Py_ssize_t ix_arg_last = -1;
        if (last_arg_array_flag != NULL && PyObject_IsTrue(last_arg_array_flag)) {
            ix_arg_last = func_args_length - 1;
        }

        for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
            PyObject *arg_name = PyList_GET_ITEM(func_args, ix);
            PyObject *value;
            if (ix < args_length) {
                if (ix == ix_arg_last) {
                    /* slice [ix:] */
                    value = PySequence_GetSlice(call_args, ix, args_length);
                    if (value == NULL) { Py_DECREF(func_locals); return NULL; }
                } else {
                    value = PySequence_GetItem(call_args, ix);
                    if (value == NULL) { Py_DECREF(func_locals); return NULL; }
                }
            } else {
                if (ix == ix_arg_last) {
                    value = PyList_New(0);
                    if (value == NULL) { Py_DECREF(func_locals); return NULL; }
                } else {
                    value = Py_None; Py_INCREF(value);
                }
            }
            if (PyDict_SetItem(func_locals, arg_name, value) < 0) {
                Py_DECREF(value); Py_DECREF(func_locals); return NULL;
            }
            Py_DECREF(value);
        }
    }

    /* statements = function['statements'] */
    PyObject *fn_statements = PyDict_GetItemWithError(function, S_statements);
    if (fn_statements == NULL) {
        Py_DECREF(func_locals);
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_KeyError, "statements");
        }
        return NULL;
    }

    PyObject *result = exec_script_helper(script, fn_statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}

static PyTypeObject ScriptFunctionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c.ScriptFunction",
    .tp_basicsize = sizeof(ScriptFunctionObject),
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_call = (ternaryfunc)ScriptFunction_call,
    .tp_dealloc = (destructor)ScriptFunction_dealloc,
    .tp_traverse = (traverseproc)ScriptFunction_traverse,
    .tp_clear = (inquiry)ScriptFunction_clear,
};

static PyObject *
ScriptFunction_new(PyObject *script, PyObject *function)
{
    ScriptFunctionObject *self = PyObject_GC_New(ScriptFunctionObject, &ScriptFunctionType);
    if (self == NULL) return NULL;
    Py_INCREF(script); self->script = script;
    Py_INCREF(function); self->function = function;
    PyObject_GC_Track(self);
    return (PyObject *)self;
}


/* ---------------------------------------------------------------------------
 * Execute statements
 * ------------------------------------------------------------------------- */

static PyObject *
exec_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_)
{
    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL) return NULL;

    /* Top-level entry: read counter from options. Nested calls share the
     * thread-local counter directly. */
    int outer_depth = g_helper_depth++;
    if (outer_depth == 0) {
        PyObject *cur = PyDict_GetItemWithError(options, S_statementCount);
        if (cur != NULL) {
            long v = PyLong_AsLong(cur);
            if (v == -1 && PyErr_Occurred()) { g_helper_depth--; return NULL; }
            g_stmt_counter = v;
        } else {
            if (PyErr_Occurred()) { g_helper_depth--; return NULL; }
            g_stmt_counter = 0;
        }
    }

    /* Cache max_statements once - constant across the run */
    PyObject *max_stmt_obj = PyDict_GetItemWithError(options, S_maxStatements);
    if (max_stmt_obj == NULL && PyErr_Occurred()) return NULL;
    double max_statements_d = g_default_max_statements;
    if (max_stmt_obj != NULL) {
        if (PyLong_Check(max_stmt_obj)) {
            max_statements_d = (double)PyLong_AsLongLong(max_stmt_obj);
        } else if (PyFloat_Check(max_stmt_obj)) {
            max_statements_d = PyFloat_AS_DOUBLE(max_stmt_obj);
        } else {
            max_statements_d = PyFloat_AsDouble(max_stmt_obj);
            if (max_statements_d == -1 && PyErr_Occurred()) return NULL;
        }
    }

    /* Cache coverage state once - script's system flag and coverage_global don't change */
    PyObject *coverage_global = PyDict_GetItemWithError(globals_, S_cov_global);
    if (coverage_global == NULL && PyErr_Occurred()) return NULL;
    int coverage_active = 0;
    if (coverage_global != NULL && PyDict_Check(coverage_global)) {
        PyObject *enabled = PyDict_GetItemWithError(coverage_global, S_enabled);
        if (enabled == NULL && PyErr_Occurred()) return NULL;
        if (enabled != NULL && PyObject_IsTrue(enabled)) {
            PyObject *system_flag = PyDict_GetItemWithError(script, S_system);
            if (system_flag == NULL && PyErr_Occurred()) return NULL;
            if (system_flag == NULL || !PyObject_IsTrue(system_flag)) {
                coverage_active = 1;
            }
        }
    }

    PyObject *label_indexes = NULL;
    PyObject *ret = NULL;
    Py_ssize_t statements_length = PyList_GET_SIZE(statements);
    Py_ssize_t ix_statement = 0;

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_GET_ITEM(statements, ix_statement);
        PyObject *statement_key = NULL;
        PyObject *statement_inner = NULL;
        if (!dict_first_kv(statement, &statement_key, &statement_inner)) {
            PyErr_SetString(PyExc_ValueError, "empty statement");
            goto error;
        }

        /* Increment thread-local statement counter (synced to options at top boundaries) */
        g_stmt_counter++;
        long count_val = g_stmt_counter;

        if (max_statements_d > 0 && (double)count_val > max_statements_d) {
            char buf[128];
            snprintf(buf, sizeof(buf), "Exceeded maximum script statements (%ld)", (long)max_statements_d);
            PyObject *fmt_arg = PyUnicode_FromString(buf);
            if (fmt_arg == NULL) goto error;
            raise_runtime_error(script, statement, "%S", fmt_arg);
            Py_DECREF(fmt_arg);
            goto error;
        }

        if (coverage_active) {
            if (record_statement_coverage(script, statement, statement_key, coverage_global) < 0) goto error;
        }

        /* Dispatch on first character of statement_key */
        const char *kc = PyUnicode_AsUTF8(statement_key);
        if (kc == NULL) goto error;
        char k0 = kc[0];

        /* expr */
        if (k0 == 'e') {
            PyObject *expr_dict = statement_inner;
            PyObject *inner_expr = PyDict_GetItemWithError(expr_dict, S_expr);
            if (inner_expr == NULL) goto error;
            PyObject *expr_value = eval_expression(inner_expr, options, locals_, 0, script, statement);
            if (expr_value == NULL) goto error;
            PyObject *expr_name = PyDict_GetItemWithError(expr_dict, S_name);
            if (expr_name == NULL && PyErr_Occurred()) {
                Py_DECREF(expr_value); goto error;
            }
            if (expr_name != NULL) {
                PyObject *target = (locals_ != NULL) ? locals_ : globals_;
                if (PyDict_SetItem(target, expr_name, expr_value) < 0) {
                    Py_DECREF(expr_value); goto error;
                }
            }
            Py_DECREF(expr_value);
            ix_statement++;
            continue;
        }

        /* jump */
        if (k0 == 'j') {
            PyObject *jump_dict = statement_inner;
            int do_jump = 1;
            PyObject *jump_expr = PyDict_GetItemWithError(jump_dict, S_expr);
            if (jump_expr == NULL && PyErr_Occurred()) goto error;
            if (jump_expr != NULL) {
                PyObject *cond = eval_expression(jump_expr, options, locals_, 0, script, statement);
                if (cond == NULL) goto error;
                do_jump = value_boolean_c(cond);
                Py_DECREF(cond);
            }
            if (do_jump) {
                PyObject *jump_label = PyDict_GetItemWithError(jump_dict, S_label);
                if (jump_label == NULL) goto error;

                Py_ssize_t ix_label = -1;
                if (label_indexes != NULL) {
                    PyObject *cached = PyDict_GetItemWithError(label_indexes, jump_label);
                    if (cached == NULL && PyErr_Occurred()) goto error;
                    if (cached != NULL) {
                        ix_label = PyLong_AsSsize_t(cached);
                        if (ix_label == -1 && PyErr_Occurred()) goto error;
                    }
                }
                if (ix_label == -1) {
                    Py_ssize_t i;
                    for (i = 0; i < statements_length; i++) {
                        PyObject *st = PyList_GET_ITEM(statements, i);
                        PyObject *lbl = PyDict_GetItemWithError(st, S_label);
                        if (lbl == NULL && PyErr_Occurred()) goto error;
                        if (lbl != NULL) {
                            PyObject *lbl_name = PyDict_GetItemWithError(lbl, S_name);
                            if (lbl_name == NULL && PyErr_Occurred()) goto error;
                            if (lbl_name != NULL && PyUnicode_Compare(lbl_name, jump_label) == 0) {
                                ix_label = i; break;
                            }
                            if (PyErr_Occurred()) goto error;
                        }
                    }
                    if (ix_label == -1) {
                        PyObject *fmt_arg = jump_label;
                        Py_INCREF(fmt_arg);
                        raise_runtime_error(script, statement, "Unknown jump label \"%S\"", fmt_arg);
                        Py_DECREF(fmt_arg);
                        goto error;
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) goto error;
                    }
                    PyObject *idx_obj = PyLong_FromSsize_t(ix_label);
                    if (idx_obj == NULL) goto error;
                    if (PyDict_SetItem(label_indexes, jump_label, idx_obj) < 0) {
                        Py_DECREF(idx_obj); goto error;
                    }
                    Py_DECREF(idx_obj);
                }
                ix_statement = ix_label;

                if (coverage_active) {
                    PyObject *label_statement = PyList_GET_ITEM(statements, ix_statement);
                    PyObject *label_statement_key = dict_first_key(label_statement);
                    if (label_statement_key != NULL) {
                        if (record_statement_coverage(script, label_statement, label_statement_key, coverage_global) < 0) goto error;
                    }
                }
            }
            ix_statement++;
            continue;
        }

        /* return */
        if (k0 == 'r') {
            PyObject *return_dict = statement_inner;
            PyObject *return_expr = PyDict_GetItemWithError(return_dict, S_expr);
            if (return_expr == NULL && PyErr_Occurred()) goto error;
            if (return_expr != NULL) {
                ret = eval_expression(return_expr, options, locals_, 0, script, statement);
            } else {
                ret = Py_None; Py_INCREF(Py_None);
            }
            goto done;
        }

        /* function */
        if (k0 == 'f') {
            PyObject *fn_dict = statement_inner;
            PyObject *fn_name = PyDict_GetItemWithError(fn_dict, S_name);
            if (fn_name == NULL) goto error;
            PyObject *callable = ScriptFunction_new(script, fn_dict);
            if (callable == NULL) goto error;
            if (PyDict_SetItem(globals_, fn_name, callable) < 0) {
                Py_DECREF(callable); goto error;
            }
            Py_DECREF(callable);
            ix_statement++;
            continue;
        }

        /* include */
        if (k0 == 'i') {
            PyObject *inc_dict = statement_inner;
            PyObject *system_prefix = PyDict_GetItemWithError(options, S_systemPrefix);
            if (system_prefix == NULL && PyErr_Occurred()) goto error;
            PyObject *fetch_fn = PyDict_GetItemWithError(options, S_fetchFn);
            if (fetch_fn == NULL && PyErr_Occurred()) goto error;
            PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
            if (log_fn == NULL && PyErr_Occurred()) goto error;
            PyObject *url_fn = PyDict_GetItemWithError(options, S_urlFn);
            if (url_fn == NULL && PyErr_Occurred()) goto error;
            PyObject *includes_list = PyDict_GetItemWithError(inc_dict, S_includes);
            if (includes_list == NULL) goto error;

            Py_ssize_t inc_count = PyList_GET_SIZE(includes_list);
            for (Py_ssize_t i = 0; i < inc_count; i++) {
                PyObject *include = PyList_GET_ITEM(includes_list, i);
                PyObject *url0 = PyDict_GetItemWithError(include, S_url);
                if (url0 == NULL) goto error;

                PyObject *include_url = NULL;
                PyObject *system_inc = PyDict_GetItemWithError(include, S_system);
                if (system_inc == NULL && PyErr_Occurred()) goto error;
                int sys_truthy = system_inc != NULL && PyObject_IsTrue(system_inc);
                if (sys_truthy && system_prefix != NULL) {
                    include_url = PyObject_CallFunctionObjArgs(g_url_file_relative, system_prefix, url0, NULL);
                    if (include_url == NULL) goto error;
                } else if (url_fn != NULL) {
                    include_url = PyObject_CallFunctionObjArgs(url_fn, url0, NULL);
                    if (include_url == NULL) goto error;
                } else {
                    include_url = url0; Py_INCREF(include_url);
                }

                /* global_includes */
                PyObject *global_includes = PyDict_GetItemWithError(globals_, S_includes_global);
                if (global_includes == NULL && PyErr_Occurred()) {
                    Py_DECREF(include_url); goto error;
                }
                if (global_includes == NULL || !PyDict_Check(global_includes)) {
                    global_includes = PyDict_New();
                    if (global_includes == NULL) { Py_DECREF(include_url); goto error; }
                    if (PyDict_SetItem(globals_, S_includes_global, global_includes) < 0) {
                        Py_DECREF(global_includes); Py_DECREF(include_url); goto error;
                    }
                    Py_DECREF(global_includes);
                    global_includes = PyDict_GetItemWithError(globals_, S_includes_global);
                    if (global_includes == NULL) { Py_DECREF(include_url); goto error; }
                }
                PyObject *already = PyDict_GetItemWithError(global_includes, include_url);
                if (already == NULL && PyErr_Occurred()) { Py_DECREF(include_url); goto error; }
                if (already != NULL && PyObject_IsTrue(already)) {
                    Py_DECREF(include_url); continue;
                }
                if (PyDict_SetItem(global_includes, include_url, Py_True) < 0) {
                    Py_DECREF(include_url); goto error;
                }

                /* Fetch */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *fetch_arg = PyDict_New();
                    if (fetch_arg == NULL) { Py_DECREF(include_url); goto error; }
                    if (PyDict_SetItem(fetch_arg, S_url, include_url) < 0) {
                        Py_DECREF(fetch_arg); Py_DECREF(include_url); goto error;
                    }
                    include_text = PyObject_CallFunctionObjArgs(fetch_fn, fetch_arg, NULL);
                    Py_DECREF(fetch_arg);
                    if (include_text == NULL) {
                        PyErr_Clear();
                        include_text = NULL;
                    }
                }
                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    PyObject *url_copy = include_url;
                    Py_INCREF(url_copy);
                    raise_runtime_error(script, statement, "Include of \"%S\" failed", url_copy);
                    Py_DECREF(url_copy);
                    Py_DECREF(include_url); goto error;
                }

                /* Parse the include script: parse_script(include_text, 1, include_url) */
                PyObject *one = PyLong_FromLong(1);
                if (one == NULL) { Py_DECREF(include_text); Py_DECREF(include_url); goto error; }
                PyObject *include_script = PyObject_CallFunctionObjArgs(g_parse_script, include_text, one, include_url, NULL);
                Py_DECREF(one);
                Py_DECREF(include_text);
                if (include_script == NULL) { Py_DECREF(include_url); goto error; }

                if (sys_truthy) {
                    if (PyDict_SetItem(include_script, S_system, Py_True) < 0) {
                        Py_DECREF(include_script); Py_DECREF(include_url); goto error;
                    }
                }

                /* include_options = options.copy(); urlFn = partial(url_file_relative, include_url) */
                PyObject *include_options = PyDict_Copy(options);
                if (include_options == NULL) { Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, include_url, NULL);
                if (new_url_fn == NULL) { Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                if (PyDict_SetItem(include_options, S_urlFn, new_url_fn) < 0) {
                    Py_DECREF(new_url_fn); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); goto error;
                }
                Py_DECREF(new_url_fn);

                PyObject *inc_statements = PyDict_GetItemWithError(include_script, S_statements);
                if (inc_statements == NULL) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); goto error;
                }
                PyObject *inc_result = exec_script_helper(include_script, inc_statements, include_options, NULL);
                Py_DECREF(include_options);
                if (inc_result == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); goto error;
                }
                Py_DECREF(inc_result);

                /* Lint pass if log_fn and debug */
                if (log_fn != NULL) {
                    PyObject *debug = PyDict_GetItemWithError(options, S_debug);
                    if (debug == NULL && PyErr_Occurred()) {
                        Py_DECREF(include_script); Py_DECREF(include_url); goto error;
                    }
                    if (debug != NULL && PyObject_IsTrue(debug)) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(g_lint_script, include_script, globals_, NULL);
                        if (warnings == NULL) {
                            Py_DECREF(include_script); Py_DECREF(include_url); goto error;
                        }
                        Py_ssize_t w_len = PyObject_Length(warnings);
                        if (w_len < 0) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                        if (w_len > 0) {
                            const char *plural = (w_len > 1) ? "s" : "";
                            PyObject *prefix_msg = PyUnicode_FromFormat(
                                "BareScript: Include \"%S\" static analysis... %zd warning%s:",
                                include_url, w_len, plural);
                            if (prefix_msg == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                            PyObject *call_res = PyObject_CallFunctionObjArgs(log_fn, prefix_msg, NULL);
                            Py_DECREF(prefix_msg);
                            if (call_res == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                            Py_DECREF(call_res);
                            for (Py_ssize_t wi = 0; wi < w_len; wi++) {
                                PyObject *w = PySequence_GetItem(warnings, wi);
                                if (w == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                                PyObject *wmsg = PyUnicode_FromFormat("BareScript: %S", w);
                                Py_DECREF(w);
                                if (wmsg == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                                PyObject *r2 = PyObject_CallFunctionObjArgs(log_fn, wmsg, NULL);
                                Py_DECREF(wmsg);
                                if (r2 == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); goto error; }
                                Py_DECREF(r2);
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }

                Py_DECREF(include_script);
                Py_DECREF(include_url);
            }
            ix_statement++;
            continue;
        }

        /* label or unknown - just advance */
        ix_statement++;
    }

    ret = Py_None; Py_INCREF(Py_None);
    goto done;

error:
    ret = NULL;
done:
    Py_XDECREF(label_indexes);
    /* Sync counter to options at top-level exit */
    int new_depth = --g_helper_depth;
    if (new_depth == 0) {
        PyObject *exc_type = NULL, *exc_val = NULL, *exc_tb = NULL;
        if (ret == NULL) PyErr_Fetch(&exc_type, &exc_val, &exc_tb);
        PyObject *final_count = PyLong_FromLong(g_stmt_counter);
        if (final_count != NULL) {
            if (PyDict_SetItem(options, S_statementCount, final_count) < 0) {
                PyErr_Clear();
            }
            Py_DECREF(final_count);
        } else {
            PyErr_Clear();
        }
        if (ret == NULL) PyErr_Restore(exc_type, exc_val, exc_tb);
    }
    return ret;
}


/* ---------------------------------------------------------------------------
 * Evaluate expression
 * ------------------------------------------------------------------------- */

/* Direct call into a ScriptFunction without going through tp_call/PyArg_UnpackTuple.
 * Returns NULL with exception on error, or a new reference on success. */
static PyObject *
script_function_call_direct(ScriptFunctionObject *sf, PyObject *call_args, PyObject *options)
{
    PyObject *function = sf->function;
    PyObject *script = sf->script;
    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    PyObject *func_args = PyDict_GetItemWithError(function, S_args);
    if (func_args == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
    if (func_args != NULL) {
        Py_ssize_t args_length = (call_args == NULL || call_args == Py_None) ? 0 : PyList_GET_SIZE(call_args);
        Py_ssize_t func_args_length = PyList_GET_SIZE(func_args);

        PyObject *last_arg_array_flag = PyDict_GetItemWithError(function, S_lastArgArray);
        if (last_arg_array_flag == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t ix_arg_last = -1;
        if (last_arg_array_flag != NULL && PyObject_IsTrue(last_arg_array_flag)) {
            ix_arg_last = func_args_length - 1;
        }

        for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
            PyObject *arg_name = PyList_GET_ITEM(func_args, ix);
            PyObject *value;
            if (ix < args_length) {
                if (ix == ix_arg_last) {
                    value = PyList_GetSlice(call_args, ix, args_length);
                    if (value == NULL) { Py_DECREF(func_locals); return NULL; }
                } else {
                    value = PyList_GET_ITEM(call_args, ix);
                    Py_INCREF(value);
                }
            } else if (ix == ix_arg_last) {
                value = PyList_New(0);
                if (value == NULL) { Py_DECREF(func_locals); return NULL; }
            } else {
                value = Py_None; Py_INCREF(value);
            }
            if (PyDict_SetItem(func_locals, arg_name, value) < 0) {
                Py_DECREF(value); Py_DECREF(func_locals); return NULL;
            }
            Py_DECREF(value);
        }
    }

    PyObject *fn_statements = PyDict_GetItemWithError(function, S_statements);
    if (fn_statements == NULL) {
        Py_DECREF(func_locals);
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
        return NULL;
    }

    PyObject *result = exec_script_helper(script, fn_statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}


static PyObject *
do_function_call(PyObject *func_value, PyObject *func_name, PyObject *func_args_list,
                 PyObject *options, PyObject *script, PyObject *statement)
{
    PyObject *args_arg = (func_args_list == NULL) ? Py_None : func_args_list;
    PyObject *opts_arg = (options == NULL) ? Py_None : options;

    PyObject *result;
    if (Py_TYPE(func_value) == &ScriptFunctionType) {
        result = script_function_call_direct((ScriptFunctionObject *)func_value, args_arg, opts_arg);
    } else {
        result = PyObject_CallFunctionObjArgs(func_value, args_arg, opts_arg, NULL);
    }
    if (result != NULL) return result;

    /* Exception path */
    if (PyErr_ExceptionMatches(g_runtime_error)) {
        return NULL; /* propagate */
    }

    /* Other exception: log if debug, return error.return_value if ValueArgsError, else None */
    PyObject *exc_type, *exc_val, *exc_tb;
    PyErr_Fetch(&exc_type, &exc_val, &exc_tb);
    PyErr_NormalizeException(&exc_type, &exc_val, &exc_tb);

    if (options != NULL && options != Py_None) {
        PyObject *log_fn = PyDict_GetItemWithError(options, S_logFn);
        if (log_fn == NULL && PyErr_Occurred()) PyErr_Clear();
        PyObject *debug = PyDict_GetItemWithError(options, S_debug);
        if (debug == NULL && PyErr_Occurred()) PyErr_Clear();
        if (log_fn != NULL && debug != NULL && PyObject_IsTrue(debug)) {
            PyObject *err_msg = PyUnicode_FromFormat(
                "BareScript: Function \"%S\" failed with error: %S", func_name, exc_val);
            if (err_msg != NULL) {
                PyObject *r = PyObject_CallFunctionObjArgs(log_fn, err_msg, NULL);
                Py_XDECREF(r);
                Py_DECREF(err_msg);
                if (PyErr_Occurred()) PyErr_Clear();
            } else {
                PyErr_Clear();
            }
        }
    }

    PyObject *out = NULL;
    if (g_value_args_error != NULL && PyObject_IsInstance(exc_val, g_value_args_error) > 0) {
        out = PyObject_GetAttr(exc_val, S_return_value);
        if (out == NULL) {
            PyErr_Clear();
            out = Py_None; Py_INCREF(out);
        }
    } else {
        out = Py_None; Py_INCREF(out);
    }
    Py_XDECREF(exc_type);
    Py_XDECREF(exc_val);
    Py_XDECREF(exc_tb);
    return out;
}


static PyObject *
eval_expression(PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
                PyObject *script, PyObject *statement)
{
    PyObject *expr_key = NULL;
    PyObject *expr_inner = NULL;
    if (!dict_first_kv(expr, &expr_key, &expr_inner)) {
        PyErr_SetString(PyExc_ValueError, "empty expression");
        return NULL;
    }
    PyObject *globals_ = NULL;
    if (options != NULL && options != Py_None) {
        globals_ = PyDict_GetItemWithError(options, S_globals);
        if (globals_ == NULL && PyErr_Occurred()) return NULL;
    }

    const char *kc = PyUnicode_AsUTF8(expr_key);
    if (kc == NULL) return NULL;
    char k0 = kc[0];

    /* number */
    if (k0 == 'n') {
        Py_INCREF(expr_inner); return expr_inner;
    }

    /* string */
    if (k0 == 's') {
        Py_INCREF(expr_inner); return expr_inner;
    }

    /* variable */
    if (k0 == 'v') {
        PyObject *vname = expr_inner;
        /* Keywords: null, false, true (length 4 or 5) */
        Py_ssize_t vlen = PyUnicode_GET_LENGTH(vname);
        if (vlen == 4 || vlen == 5) {
            const char *vc = PyUnicode_AsUTF8(vname);
            if (vc == NULL) return NULL;
            if (vlen == 4 && vc[0] == 'n' && vc[1] == 'u' && vc[2] == 'l' && vc[3] == 'l') Py_RETURN_NONE;
            if (vlen == 4 && vc[0] == 't' && vc[1] == 'r' && vc[2] == 'u' && vc[3] == 'e') Py_RETURN_TRUE;
            if (vlen == 5 && vc[0] == 'f' && vc[1] == 'a' && vc[2] == 'l' && vc[3] == 's' && vc[4] == 'e') Py_RETURN_FALSE;
        }

        if (locals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(locals_, vname);
            if (v != NULL) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        if (globals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(globals_, vname);
            if (v != NULL) { Py_INCREF(v); return v; }
            if (PyErr_Occurred()) return NULL;
        }
        Py_RETURN_NONE;
    }

    /* function */
    if (k0 == 'f') {
        PyObject *fn_dict = expr_inner;
        PyObject *func_name = PyDict_GetItemWithError(fn_dict, S_name);
        if (func_name == NULL) return NULL;

        /* "if" built-in */
        if (PyUnicode_Compare(func_name, S_if) == 0) {
            PyObject *args_expr = PyDict_GetItemWithError(fn_dict, S_args);
            if (args_expr == NULL && PyErr_Occurred()) return NULL;
            PyObject *value_expr = NULL, *true_expr = NULL, *false_expr = NULL;
            if (args_expr != NULL) {
                Py_ssize_t a_len = PyList_GET_SIZE(args_expr);
                if (a_len >= 1) value_expr = PyList_GET_ITEM(args_expr, 0);
                if (a_len >= 2) true_expr = PyList_GET_ITEM(args_expr, 1);
                if (a_len >= 3) false_expr = PyList_GET_ITEM(args_expr, 2);
            }
            int cond = 0;
            if (value_expr != NULL) {
                PyObject *cv = eval_expression(value_expr, options, locals_, builtins, script, statement);
                if (cv == NULL) return NULL;
                cond = value_boolean_c(cv);
                Py_DECREF(cv);
            }
            PyObject *result_expr = cond ? true_expr : false_expr;
            if (result_expr != NULL) {
                return eval_expression(result_expr, options, locals_, builtins, script, statement);
            }
            Py_RETURN_NONE;
        }
        if (PyErr_Occurred()) return NULL;

        /* compute args */
        PyObject *func_args_list = NULL;
        PyObject *args_expr = PyDict_GetItemWithError(fn_dict, S_args);
        if (args_expr == NULL && PyErr_Occurred()) return NULL;
        if (args_expr != NULL) {
            Py_ssize_t a_len = PyList_GET_SIZE(args_expr);
            func_args_list = PyList_New(a_len);
            if (func_args_list == NULL) return NULL;
            for (Py_ssize_t i = 0; i < a_len; i++) {
                PyObject *a = PyList_GET_ITEM(args_expr, i);
                PyObject *v = eval_expression(a, options, locals_, builtins, script, statement);
                if (v == NULL) { Py_DECREF(func_args_list); return NULL; }
                PyList_SET_ITEM(func_args_list, i, v);
            }
        }

        /* lookup function: locals_ takes priority even if value is None */
        PyObject *func_value = NULL;
        int found = 0;
        if (locals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(locals_, func_name);
            if (v == NULL && PyErr_Occurred()) { Py_XDECREF(func_args_list); return NULL; }
            if (v != NULL || PyDict_Contains(locals_, func_name) == 1) {
                func_value = v;
                found = 1;
            }
        }
        if (!found && globals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(globals_, func_name);
            if (v == NULL && PyErr_Occurred()) { Py_XDECREF(func_args_list); return NULL; }
            if (v != NULL || PyDict_Contains(globals_, func_name) == 1) {
                func_value = v;
                found = 1;
            }
        }
        if (!found && builtins) {
            PyObject *v = PyDict_GetItemWithError(g_expression_functions, func_name);
            if (v == NULL && PyErr_Occurred()) { Py_XDECREF(func_args_list); return NULL; }
            if (v != NULL) func_value = v;
        }
        if (func_value == NULL || func_value == Py_None) {
            PyObject *fn_copy = func_name; Py_INCREF(fn_copy);
            raise_runtime_error(script, statement, "Undefined function \"%S\"", fn_copy);
            Py_DECREF(fn_copy);
            Py_XDECREF(func_args_list);
            return NULL;
        }

        PyObject *result = do_function_call(func_value, func_name, func_args_list, options, script, statement);
        Py_XDECREF(func_args_list);
        return result;
    }
    /* binary */
    if (k0 == 'b') {
        PyObject *bin = expr_inner;
        PyObject *op = PyDict_GetItemWithError(bin, S_op);
        if (op == NULL) return NULL;
        PyObject *left_expr = PyDict_GetItemWithError(bin, S_left);
        if (left_expr == NULL) return NULL;
        PyObject *left = eval_expression(left_expr, options, locals_, builtins, script, statement);
        if (left == NULL) return NULL;

        const char *opcs = PyUnicode_AsUTF8(op);
        if (opcs == NULL) { Py_DECREF(left); return NULL; }

        /* Short-circuit && */
        if (opcs[0] == '&' && opcs[1] == '&' && opcs[2] == 0) {
            if (!value_boolean_c(left)) return left;
            Py_DECREF(left);
            PyObject *right_expr = PyDict_GetItemWithError(bin, S_right);
            if (right_expr == NULL) return NULL;
            return eval_expression(right_expr, options, locals_, builtins, script, statement);
        }
        /* Short-circuit || */
        if (opcs[0] == '|' && opcs[1] == '|' && opcs[2] == 0) {
            if (value_boolean_c(left)) return left;
            Py_DECREF(left);
            PyObject *right_expr = PyDict_GetItemWithError(bin, S_right);
            if (right_expr == NULL) return NULL;
            return eval_expression(right_expr, options, locals_, builtins, script, statement);
        }

        PyObject *right_expr = PyDict_GetItemWithError(bin, S_right);
        if (right_expr == NULL) { Py_DECREF(left); return NULL; }
        PyObject *right = eval_expression(right_expr, options, locals_, builtins, script, statement);
        if (right == NULL) { Py_DECREF(left); return NULL; }

        PyObject *result = NULL;

        if (opcs[0] == '+' && opcs[1] == 0) {
            int ln = is_number(left), rn = is_number(right);
            if (ln && rn) {
                result = fast_arith(left, right, 0);
            } else if (PyUnicode_Check(left) && PyUnicode_Check(right)) {
                result = PyUnicode_Concat(left, right);
            } else if (PyUnicode_Check(left)) {
                PyObject *r2 = PyObject_CallFunctionObjArgs(g_value_string, right, NULL);
                if (r2 != NULL) { result = PyUnicode_Concat(left, r2); Py_DECREF(r2); }
            } else if (PyUnicode_Check(right)) {
                PyObject *l2 = PyObject_CallFunctionObjArgs(g_value_string, left, NULL);
                if (l2 != NULL) { result = PyUnicode_Concat(l2, right); Py_DECREF(l2); }
            } else {
                int l_dt = is_datetime(left);
                int r_dt = is_datetime(right);
                if (l_dt && rn) {
                    PyObject *ldt = PyObject_CallFunctionObjArgs(g_value_normalize_datetime, left, NULL);
                    if (ldt != NULL) {
                        PyObject *empty = PyTuple_New(0);
                        PyObject *kw = PyDict_New();
                        if (empty != NULL && kw != NULL && PyDict_SetItemString(kw, "milliseconds", right) == 0) {
                            PyObject *delta = PyObject_Call(g_datetime_timedelta, empty, kw);
                            if (delta != NULL) {
                                result = PyNumber_Add(ldt, delta);
                                Py_DECREF(delta);
                            }
                        }
                        Py_XDECREF(empty);
                        Py_XDECREF(kw);
                        Py_DECREF(ldt);
                    }
                } else if (ln && r_dt) {
                    PyObject *rdt = PyObject_CallFunctionObjArgs(g_value_normalize_datetime, right, NULL);
                    if (rdt != NULL) {
                        PyObject *empty = PyTuple_New(0);
                        PyObject *kw = PyDict_New();
                        if (empty != NULL && kw != NULL && PyDict_SetItemString(kw, "milliseconds", left) == 0) {
                            PyObject *delta = PyObject_Call(g_datetime_timedelta, empty, kw);
                            if (delta != NULL) {
                                result = PyNumber_Add(rdt, delta);
                                Py_DECREF(delta);
                            }
                        }
                        Py_XDECREF(empty);
                        Py_XDECREF(kw);
                        Py_DECREF(rdt);
                    }
                }
            }
        } else if (opcs[0] == '-' && opcs[1] == 0) {
            int ln = is_number(left), rn = is_number(right);
            if (ln && rn) {
                result = fast_arith(left, right, 1);
            } else {
                int l_dt = is_datetime(left), r_dt = is_datetime(right);
                if (l_dt && r_dt) {
                    PyObject *ldt = PyObject_CallFunctionObjArgs(g_value_normalize_datetime, left, NULL);
                    PyObject *rdt = ldt ? PyObject_CallFunctionObjArgs(g_value_normalize_datetime, right, NULL) : NULL;
                    if (ldt != NULL && rdt != NULL) {
                        PyObject *diff = PyNumber_Subtract(ldt, rdt);
                        if (diff != NULL) {
                            PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                            Py_DECREF(diff);
                            if (secs != NULL) {
                                PyObject *thousand = PyFloat_FromDouble(1000.0);
                                PyObject *ms = PyNumber_Multiply(secs, thousand);
                                Py_DECREF(secs); Py_DECREF(thousand);
                                if (ms != NULL) {
                                    PyObject *zero = PyLong_FromLong(0);
                                    if (zero != NULL) {
                                        result = PyObject_CallFunctionObjArgs(g_value_round_number, ms, zero, NULL);
                                        Py_DECREF(zero);
                                    }
                                    Py_DECREF(ms);
                                }
                            }
                        }
                    }
                    Py_XDECREF(ldt); Py_XDECREF(rdt);
                }
            }
        } else if (opcs[0] == '*' && opcs[1] == '*' && opcs[2] == 0) {
            if (is_number(left) && is_number(right)) {
                result = PyNumber_Power(left, right, Py_None);
            }
        } else if (opcs[0] == '*' && opcs[1] == 0) {
            if (is_number(left) && is_number(right)) {
                result = fast_arith(left, right, 2);
            }
        } else if (opcs[0] == '/' && opcs[1] == 0) {
            if (is_number(left) && is_number(right)) {
                result = fast_arith(left, right, 3);
            }
        } else if (opcs[0] == '%' && opcs[1] == 0) {
            if (is_number(left) && is_number(right)) {
                result = PyNumber_Remainder(left, right);
            }
        } else if ((opcs[0] == '=' && opcs[1] == '=' && opcs[2] == 0) ||
                   (opcs[0] == '!' && opcs[1] == '=' && opcs[2] == 0) ||
                   (opcs[0] == '<' && opcs[1] == '=' && opcs[2] == 0) ||
                   (opcs[0] == '<' && opcs[1] == 0) ||
                   (opcs[0] == '>' && opcs[1] == '=' && opcs[2] == 0) ||
                   (opcs[0] == '>' && opcs[1] == 0)) {
            /* Map op to Py_* comparison code */
            int py_op = -1;
            if (opcs[0] == '=' && opcs[1] == '=') py_op = Py_EQ;
            else if (opcs[0] == '!' && opcs[1] == '=') py_op = Py_NE;
            else if (opcs[0] == '<' && opcs[1] == '=') py_op = Py_LE;
            else if (opcs[0] == '<') py_op = Py_LT;
            else if (opcs[0] == '>' && opcs[1] == '=') py_op = Py_GE;
            else if (opcs[0] == '>') py_op = Py_GT;

            /* Fast path: matching compatible types use PyObject_RichCompareBool
             * (semantics match value_compare for these types). */
            int ln = is_number(left), rn = is_number(right);
            int fast = (ln && rn) ||
                       (PyUnicode_Check(left) && PyUnicode_Check(right)) ||
                       (PyBool_Check(left) && PyBool_Check(right));
            if (fast) {
                int b = PyObject_RichCompareBool(left, right, py_op);
                if (b < 0) goto cmp_err;
                result = b ? Py_True : Py_False;
                Py_INCREF(result);
            } else {
                PyObject *cmp = PyObject_CallFunctionObjArgs(g_value_compare, left, right, NULL);
                if (cmp == NULL) goto cmp_err;
                long c = PyLong_AsLong(cmp);
                Py_DECREF(cmp);
                if (c == -1 && PyErr_Occurred()) goto cmp_err;
                int b = 0;
                switch (py_op) {
                    case Py_EQ: b = (c == 0); break;
                    case Py_NE: b = (c != 0); break;
                    case Py_LE: b = (c <= 0); break;
                    case Py_LT: b = (c < 0);  break;
                    case Py_GE: b = (c >= 0); break;
                    case Py_GT: b = (c > 0);  break;
                }
                result = b ? Py_True : Py_False;
                Py_INCREF(result);
            }
            cmp_err: ;
        } else if (opcs[0] == '&' && opcs[1] == 0) {
            if (is_number(left) && is_number(right) && number_is_integral(left) && number_is_integral(right)) {
                PyObject *li = PyNumber_Long(left);
                PyObject *ri = li ? PyNumber_Long(right) : NULL;
                if (li && ri) result = PyNumber_And(li, ri);
                Py_XDECREF(li); Py_XDECREF(ri);
            }
        } else if (opcs[0] == '|' && opcs[1] == 0) {
            if (is_number(left) && is_number(right) && number_is_integral(left) && number_is_integral(right)) {
                PyObject *li = PyNumber_Long(left);
                PyObject *ri = li ? PyNumber_Long(right) : NULL;
                if (li && ri) result = PyNumber_Or(li, ri);
                Py_XDECREF(li); Py_XDECREF(ri);
            }
        } else if (opcs[0] == '^' && opcs[1] == 0) {
            if (is_number(left) && is_number(right) && number_is_integral(left) && number_is_integral(right)) {
                PyObject *li = PyNumber_Long(left);
                PyObject *ri = li ? PyNumber_Long(right) : NULL;
                if (li && ri) result = PyNumber_Xor(li, ri);
                Py_XDECREF(li); Py_XDECREF(ri);
            }
        } else if (opcs[0] == '<' && opcs[1] == '<' && opcs[2] == 0) {
            if (is_number(left) && is_number(right) && number_is_integral(left) && number_is_integral(right)) {
                PyObject *li = PyNumber_Long(left);
                PyObject *ri = li ? PyNumber_Long(right) : NULL;
                if (li && ri) result = PyNumber_Lshift(li, ri);
                Py_XDECREF(li); Py_XDECREF(ri);
            }
        } else if (opcs[0] == '>' && opcs[1] == '>' && opcs[2] == 0) {
            if (is_number(left) && is_number(right) && number_is_integral(left) && number_is_integral(right)) {
                PyObject *li = PyNumber_Long(left);
                PyObject *ri = li ? PyNumber_Long(right) : NULL;
                if (li && ri) result = PyNumber_Rshift(li, ri);
                Py_XDECREF(li); Py_XDECREF(ri);
            }
        }

        Py_DECREF(left); Py_DECREF(right);
        if (result == NULL && !PyErr_Occurred()) Py_RETURN_NONE;
        return result;
    }
    /* unary */
    if (k0 == 'u') {
        PyObject *u = expr_inner;
        PyObject *op = PyDict_GetItemWithError(u, S_op);
        if (op == NULL) return NULL;
        PyObject *u_expr = PyDict_GetItemWithError(u, S_expr);
        if (u_expr == NULL) return NULL;
        PyObject *value = eval_expression(u_expr, options, locals_, builtins, script, statement);
        if (value == NULL) return NULL;
        const char *opcs = PyUnicode_AsUTF8(op);
        if (opcs == NULL) { Py_DECREF(value); return NULL; }
        PyObject *result = NULL;
        if (opcs[0] == '!' && opcs[1] == 0) {
            int b = !value_boolean_c(value);
            result = b ? Py_True : Py_False; Py_INCREF(result);
        } else if (opcs[0] == '-' && opcs[1] == 0) {
            if (is_number(value)) result = PyNumber_Negative(value);
        } else if (opcs[0] == '~' && opcs[1] == 0) {
            if (is_number(value) && number_is_integral(value)) {
                PyObject *li = PyNumber_Long(value);
                if (li != NULL) { result = PyNumber_Invert(li); Py_DECREF(li); }
            }
        }
        Py_DECREF(value);
        if (result == NULL && !PyErr_Occurred()) Py_RETURN_NONE;
        return result;
    }
    /* group */
    if (k0 == 'g') {
        return eval_expression(expr_inner, options, locals_, builtins, script, statement);
    }

    Py_RETURN_NONE;
}


/* ---------------------------------------------------------------------------
 * Module-level functions
 * ------------------------------------------------------------------------- */

static PyObject *
py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script = NULL;
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

    /* globals = options.get('globals') or new dict */
    PyObject *globals_ = PyDict_GetItemWithError(options, S_globals);
    if (globals_ == NULL && PyErr_Occurred()) { Py_DECREF(options); return NULL; }
    if (globals_ == NULL) {
        globals_ = PyDict_New();
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, S_globals, globals_) < 0) {
            Py_DECREF(globals_); Py_DECREF(options); return NULL;
        }
        Py_DECREF(globals_);
        globals_ = PyDict_GetItemWithError(options, S_globals);
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
    }

    /* Update with SCRIPT_FUNCTIONS not already in globals */
    Py_ssize_t pos = 0;
    PyObject *k, *v;
    while (PyDict_Next(g_script_functions, &pos, &k, &v)) {
        int contains = PyDict_Contains(globals_, k);
        if (contains < 0) { Py_DECREF(options); return NULL; }
        if (!contains) {
            if (PyDict_SetItem(globals_, k, v) < 0) { Py_DECREF(options); return NULL; }
        }
    }

    /* statementCount = 0 (visible to Python; runtime uses g_stmt_counter) */
    PyObject *zero = PyLong_FromLong(0);
    if (zero == NULL) { Py_DECREF(options); return NULL; }
    if (PyDict_SetItem(options, S_statementCount, zero) < 0) {
        Py_DECREF(zero); Py_DECREF(options); return NULL;
    }
    Py_DECREF(zero);

    PyObject *statements = PyDict_GetItemWithError(script, S_statements);
    if (statements == NULL) { Py_DECREF(options); return NULL; }

    PyObject *result = exec_script_helper(script, statements, options, NULL);
    Py_DECREF(options);
    return result;
}


static PyObject *
py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr = NULL;
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
    PyObject *stm = (statement == Py_None) ? NULL : statement;
    return eval_expression(expr, opts, locs, builtins ? 1 : 0, scr, stm);
}


/* ---------------------------------------------------------------------------
 * Module init
 * ------------------------------------------------------------------------- */

static PyMethodDef ModuleMethods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS, "Execute a BareScript model"},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS, "Evaluate an expression"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef ModuleDef = {
    PyModuleDef_HEAD_INIT, "bare_script.runtime_c", NULL, -1, ModuleMethods,
    NULL, NULL, NULL, NULL
};


#define INTERN_OR_FAIL(var, str) \
    do { var = PyUnicode_InternFromString(str); if (var == NULL) return NULL; } while (0)


PyMODINIT_FUNC
PyInit_runtime_c(void)
{
    if (PyType_Ready(&ScriptFunctionType) < 0) return NULL;

    PyObject *m = PyModule_Create(&ModuleDef);
    if (m == NULL) return NULL;

    /* Intern strings */
    INTERN_OR_FAIL(S_expr, "expr");
    INTERN_OR_FAIL(S_name, "name");
    INTERN_OR_FAIL(S_args, "args");
    INTERN_OR_FAIL(S_function, "function");
    INTERN_OR_FAIL(S_variable, "variable");
    INTERN_OR_FAIL(S_number, "number");
    INTERN_OR_FAIL(S_string, "string");
    INTERN_OR_FAIL(S_binary, "binary");
    INTERN_OR_FAIL(S_unary, "unary");
    INTERN_OR_FAIL(S_group, "group");
    INTERN_OR_FAIL(S_op, "op");
    INTERN_OR_FAIL(S_left, "left");
    INTERN_OR_FAIL(S_right, "right");
    INTERN_OR_FAIL(S_label, "label");
    INTERN_OR_FAIL(S_jump, "jump");
    INTERN_OR_FAIL(S_return, "return");
    INTERN_OR_FAIL(S_include, "include");
    INTERN_OR_FAIL(S_includes, "includes");
    INTERN_OR_FAIL(S_url, "url");
    INTERN_OR_FAIL(S_system, "system");
    INTERN_OR_FAIL(S_lineNumber, "lineNumber");
    INTERN_OR_FAIL(S_scriptName, "scriptName");
    INTERN_OR_FAIL(S_statements, "statements");
    INTERN_OR_FAIL(S_lastArgArray, "lastArgArray");
    INTERN_OR_FAIL(S_globals, "globals");
    INTERN_OR_FAIL(S_statementCount, "statementCount");
    INTERN_OR_FAIL(S_maxStatements, "maxStatements");
    INTERN_OR_FAIL(S_fetchFn, "fetchFn");
    INTERN_OR_FAIL(S_logFn, "logFn");
    INTERN_OR_FAIL(S_urlFn, "urlFn");
    INTERN_OR_FAIL(S_systemPrefix, "systemPrefix");
    INTERN_OR_FAIL(S_debug, "debug");
    INTERN_OR_FAIL(S_enabled, "enabled");
    INTERN_OR_FAIL(S_scripts, "scripts");
    INTERN_OR_FAIL(S_covered, "covered");
    INTERN_OR_FAIL(S_statement, "statement");
    INTERN_OR_FAIL(S_count, "count");
    INTERN_OR_FAIL(S_script, "script");
    INTERN_OR_FAIL(S_null, "null");
    INTERN_OR_FAIL(S_false, "false");
    INTERN_OR_FAIL(S_true, "true");
    INTERN_OR_FAIL(S_if, "if");
    INTERN_OR_FAIL(S_return_value, "return_value");
    INTERN_OR_FAIL(S_cov_global, "__barescriptCoverage");
    INTERN_OR_FAIL(S_includes_global, "__barescriptIncludes");

    /* Import value module */
    PyObject *value_mod = PyImport_ImportModule("bare_script.value");
    if (value_mod == NULL) return NULL;
    g_value_compare = PyObject_GetAttrString(value_mod, "value_compare");
    g_value_normalize_datetime = PyObject_GetAttrString(value_mod, "value_normalize_datetime");
    g_value_round_number = PyObject_GetAttrString(value_mod, "value_round_number");
    g_value_string = PyObject_GetAttrString(value_mod, "value_string");
    g_value_args_error = PyObject_GetAttrString(value_mod, "ValueArgsError");
    Py_DECREF(value_mod);
    if (!g_value_compare || !g_value_normalize_datetime || !g_value_round_number ||
        !g_value_string || !g_value_args_error) return NULL;

    /* Import library module */
    PyObject *library_mod = PyImport_ImportModule("bare_script.library");
    if (library_mod == NULL) return NULL;
    g_script_functions = PyObject_GetAttrString(library_mod, "SCRIPT_FUNCTIONS");
    g_expression_functions = PyObject_GetAttrString(library_mod, "EXPRESSION_FUNCTIONS");
    Py_DECREF(library_mod);
    if (!g_script_functions || !g_expression_functions) return NULL;

    /* Import model.lint_script */
    PyObject *model_mod = PyImport_ImportModule("bare_script.model");
    if (model_mod == NULL) return NULL;
    g_lint_script = PyObject_GetAttrString(model_mod, "lint_script");
    Py_DECREF(model_mod);
    if (!g_lint_script) return NULL;

    /* Import options.url_file_relative */
    PyObject *options_mod = PyImport_ImportModule("bare_script.options");
    if (options_mod == NULL) return NULL;
    g_url_file_relative = PyObject_GetAttrString(options_mod, "url_file_relative");
    Py_DECREF(options_mod);
    if (!g_url_file_relative) return NULL;

    /* Import parser.parse_script */
    PyObject *parser_mod = PyImport_ImportModule("bare_script.parser");
    if (parser_mod == NULL) return NULL;
    g_parse_script = PyObject_GetAttrString(parser_mod, "parse_script");
    Py_DECREF(parser_mod);
    if (!g_parse_script) return NULL;

    /* Import runtime.BareScriptRuntimeError */
    PyObject *runtime_mod = PyImport_ImportModule("bare_script.runtime");
    if (runtime_mod == NULL) return NULL;
    g_runtime_error = PyObject_GetAttrString(runtime_mod, "BareScriptRuntimeError");
    Py_DECREF(runtime_mod);
    if (!g_runtime_error) return NULL;

    /* Import functools.partial */
    PyObject *functools_mod = PyImport_ImportModule("functools");
    if (functools_mod == NULL) return NULL;
    g_functools_partial = PyObject_GetAttrString(functools_mod, "partial");
    Py_DECREF(functools_mod);
    if (!g_functools_partial) return NULL;

    /* Import datetime types */
    PyObject *dt_mod = PyImport_ImportModule("datetime");
    if (dt_mod == NULL) return NULL;
    g_datetime_date = PyObject_GetAttrString(dt_mod, "date");
    g_datetime_datetime = PyObject_GetAttrString(dt_mod, "datetime");
    g_datetime_timedelta = PyObject_GetAttrString(dt_mod, "timedelta");
    Py_DECREF(dt_mod);
    if (!g_datetime_date || !g_datetime_datetime || !g_datetime_timedelta) return NULL;

    return m;
}
