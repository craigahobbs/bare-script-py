// Licensed under the MIT License
// https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

// runtime_c — CPython C extension port of bare_script.runtime
//
// Faithful translation of runtime.py. Public functions exported:
//   execute_script(script, options=None)
//   evaluate_expression(expr, options=None, locals_=None, builtins=True,
//                       script=None, statement=None)

#define PY_SSIZE_T_CLEAN
#include <Python.h>


// ===== Module-level cached objects =====

// Cached imports from bare_script
static PyObject *G_BareScriptRuntimeError = NULL;
static PyObject *G_EXPRESSION_FUNCTIONS = NULL;
static PyObject *G_SCRIPT_FUNCTIONS = NULL;
static PyObject *G_lint_script = NULL;
static PyObject *G_url_file_relative = NULL;
static PyObject *G_parse_script = NULL;
static PyObject *G_value_boolean = NULL;
static PyObject *G_value_compare = NULL;
static PyObject *G_value_normalize_datetime = NULL;
static PyObject *G_value_round_number = NULL;
static PyObject *G_value_string = NULL;
static PyObject *G_ValueArgsError = NULL;
static PyObject *G_functools_partial = NULL;
static PyObject *G_datetime_date = NULL;
static PyObject *G_datetime_timedelta = NULL;

// Cached constants
static PyObject *G_DEFAULT_MAX_STATEMENTS = NULL;            // 1e9 as PyFloat
static PyObject *G_COVERAGE_NAME = NULL;                     // "__barescriptCoverage"
static PyObject *G_INCLUDES_NAME = NULL;                     // "__barescriptIncludes"
static PyObject *G_PY_ZERO = NULL;
static PyObject *G_PY_ONE = NULL;

// Interned key strings
static PyObject *K_globals;
static PyObject *K_statementCount;
static PyObject *K_statements;
static PyObject *K_maxStatements;
static PyObject *K_system;
static PyObject *K_enabled;
static PyObject *K_scripts;
static PyObject *K_scriptName;
static PyObject *K_lineNumber;
static PyObject *K_script;
static PyObject *K_covered;
static PyObject *K_statement;
static PyObject *K_count;
static PyObject *K_expr;
static PyObject *K_name;
static PyObject *K_jump;
static PyObject *K_label;
static PyObject *K_returnK;     // "return"
static PyObject *K_functionK;   // "function"
static PyObject *K_include;
static PyObject *K_includes;
static PyObject *K_url;
static PyObject *K_systemPrefix;
static PyObject *K_fetchFn;
static PyObject *K_logFn;
static PyObject *K_urlFn;
static PyObject *K_debug;
static PyObject *K_number;
static PyObject *K_string;
static PyObject *K_variable;
static PyObject *K_args;
static PyObject *K_binary;
static PyObject *K_op;
static PyObject *K_left;
static PyObject *K_right;
static PyObject *K_unary;
static PyObject *K_group;
static PyObject *K_lastArgArray;
static PyObject *K_null;
static PyObject *K_false;
static PyObject *K_true;
static PyObject *K_ifK;          // "if"
static PyObject *K_milliseconds;
static PyObject *K_return_value;


// Forward declarations
static PyObject *evaluate_expression_c(PyObject *expr, PyObject *options, PyObject *locals_,
                                       int builtins, PyObject *script, PyObject *statement);
static PyObject *execute_script_helper(PyObject *script, PyObject *statements,
                                       PyObject *options, PyObject *locals_);
static int record_statement_coverage(PyObject *script, PyObject *statement,
                                     PyObject *statement_key, PyObject *coverage_global);
static PyObject *script_function_call(PyObject *script, PyObject *function,
                                      PyObject *args, PyObject *options);


// ===== Custom callable type: _ScriptFunc — wraps (script, function_dict) =====

typedef struct {
    PyObject_HEAD
    PyObject *script;
    PyObject *function;
} ScriptFuncObject;

static int
ScriptFunc_init(ScriptFuncObject *self, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    PyObject *script_arg = NULL;
    PyObject *function_arg = NULL;
    if (!PyArg_ParseTuple(args, "OO", &script_arg, &function_arg)) {
        return -1;
    }
    Py_INCREF(script_arg);
    Py_INCREF(function_arg);
    Py_XSETREF(self->script, script_arg);
    Py_XSETREF(self->function, function_arg);
    return 0;
}

static void
ScriptFunc_dealloc(ScriptFuncObject *self)
{
    PyObject_GC_UnTrack(self);
    Py_CLEAR(self->script);
    Py_CLEAR(self->function);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
ScriptFunc_traverse(ScriptFuncObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->script);
    Py_VISIT(self->function);
    return 0;
}

static int
ScriptFunc_clear(ScriptFuncObject *self)
{
    Py_CLEAR(self->script);
    Py_CLEAR(self->function);
    return 0;
}

static PyObject *
ScriptFunc_callobj(ScriptFuncObject *self, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    PyObject *call_args = NULL;
    PyObject *call_options = NULL;
    if (!PyArg_ParseTuple(args, "OO", &call_args, &call_options)) {
        return NULL;
    }
    return script_function_call(self->script, self->function, call_args, call_options);
}

static PyTypeObject ScriptFuncType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c._ScriptFunc",
    .tp_doc = "Callable wrapper for a BareScript user-defined function",
    .tp_basicsize = sizeof(ScriptFuncObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)ScriptFunc_init,
    .tp_dealloc = (destructor)ScriptFunc_dealloc,
    .tp_traverse = (traverseproc)ScriptFunc_traverse,
    .tp_clear = (inquiry)ScriptFunc_clear,
    .tp_call = (ternaryfunc)ScriptFunc_callobj,
};


// ===== Helpers =====

// Raise BareScriptRuntimeError(script, statement, message). Returns NULL.
static PyObject *
raise_runtime_error(PyObject *script, PyObject *statement, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    PyObject *msg = PyUnicode_FromFormatV(fmt, ap);
    va_end(ap);
    if (msg == NULL) {
        return NULL;
    }
    PyObject *args = PyTuple_Pack(3,
                                   script ? script : Py_None,
                                   statement ? statement : Py_None,
                                   msg);
    Py_DECREF(msg);
    if (args == NULL) {
        return NULL;
    }
    PyObject *exc = PyObject_Call(G_BareScriptRuntimeError, args, NULL);
    Py_DECREF(args);
    if (exc == NULL) {
        return NULL;
    }
    PyErr_SetObject(G_BareScriptRuntimeError, exc);
    Py_DECREF(exc);
    return NULL;
}


// Get the single key of a one-key dict. Returns borrowed reference; NULL on error.
static PyObject *
single_dict_key(PyObject *dict)
{
    Py_ssize_t pos = 0;
    PyObject *key = NULL;
    PyObject *value = NULL;
    if (!PyDict_Next(dict, &pos, &key, &value)) {
        PyErr_SetString(PyExc_ValueError, "expected non-empty dict");
        return NULL;
    }
    return key;
}


// Is val a number but not a bool?
static inline int
is_number_not_bool(PyObject *val)
{
    if (val == NULL) return 0;
    if (PyBool_Check(val)) return 0;
    return PyLong_Check(val) || PyFloat_Check(val);
}


// Is val a datetime.date or datetime.datetime?
static inline int
is_date(PyObject *val)
{
    return PyObject_IsInstance(val, G_datetime_date) == 1;
}


// Fast value_boolean: returns 1, 0, or -1 on error.
// Matches value_boolean(): bool→bool, str→nonempty, int/float→nonzero,
// list→nonempty, None→False, anything else non-None→True.
static inline int
fast_value_boolean(PyObject *v)
{
    if (v == Py_None) return 0;
    if (v == Py_True) return 1;
    if (v == Py_False) return 0;
    if (PyLong_CheckExact(v)) {
        return PyObject_IsTrue(v);
    }
    if (PyFloat_CheckExact(v)) {
        return PyFloat_AS_DOUBLE(v) != 0.0;
    }
    if (PyUnicode_CheckExact(v)) {
        return PyUnicode_GET_LENGTH(v) > 0;
    }
    if (PyList_CheckExact(v)) {
        return PyList_GET_SIZE(v) > 0;
    }
    // Subclasses / other types — fall back to Python value_boolean
    PyObject *r = PyObject_CallFunctionObjArgs(G_value_boolean, v, NULL);
    if (r == NULL) return -1;
    int b = (r == Py_True) ? 1 : (r == Py_False ? 0 : PyObject_IsTrue(r));
    Py_DECREF(r);
    return b;
}


// Fast numeric compare for int/float/bool combinations. Returns -1, 0, 1, or -2 on mismatch.
// Caller still needs to handle non-numeric and datetime separately via value_compare.
static inline int
fast_numeric_compare(PyObject *a, PyObject *b)
{
    int a_long = PyLong_CheckExact(a);
    int b_long = PyLong_CheckExact(b);
    int a_float = PyFloat_CheckExact(a);
    int b_float = PyFloat_CheckExact(b);
    if (!(a_long || a_float) || !(b_long || b_float)) return -2;
    if (a_float && b_float) {
        double av = PyFloat_AS_DOUBLE(a);
        double bv = PyFloat_AS_DOUBLE(b);
        return (av < bv) ? -1 : (av > bv ? 1 : 0);
    }
    if (a_long && b_long) {
        int cmp = PyObject_RichCompareBool(a, b, Py_LT);
        if (cmp < 0) return -2;
        if (cmp) return -1;
        cmp = PyObject_RichCompareBool(a, b, Py_EQ);
        if (cmp < 0) return -2;
        return cmp ? 0 : 1;
    }
    // mixed long/float
    double av = a_float ? PyFloat_AS_DOUBLE(a) : PyLong_AsDouble(a);
    if (av == -1 && PyErr_Occurred()) return -2;
    double bv = b_float ? PyFloat_AS_DOUBLE(b) : PyLong_AsDouble(b);
    if (bv == -1 && PyErr_Occurred()) return -2;
    return (av < bv) ? -1 : (av > bv ? 1 : 0);
}


// Borrowed-ref PyDict_GetItem that clears errors. Returns NULL on miss.
static inline PyObject *
dict_get(PyObject *dict, PyObject *key)
{
    if (dict == NULL || !PyDict_Check(dict)) return NULL;
    return PyDict_GetItemWithError(dict, key);
}


// ===== _record_statement_coverage =====

static int
record_statement_coverage(PyObject *script, PyObject *statement,
                          PyObject *statement_key, PyObject *coverage_global)
{
    // Get script name
    PyObject *script_name = dict_get(script, K_scriptName);
    if (PyErr_Occurred()) return -1;
    if (script_name == NULL) return 0;

    // Get the statement details (statement[statement_key])
    PyObject *stmt_details = PyDict_GetItemWithError(statement, statement_key);
    if (stmt_details == NULL) {
        if (PyErr_Occurred()) return -1;
        return 0;
    }
    PyObject *lineno = dict_get(stmt_details, K_lineNumber);
    if (PyErr_Occurred()) return -1;
    if (lineno == NULL) return 0;

    // Get/create scripts
    PyObject *scripts = PyDict_GetItemWithError(coverage_global, K_scripts);
    if (scripts == NULL) {
        if (PyErr_Occurred()) return -1;
        scripts = PyDict_New();
        if (scripts == NULL) return -1;
        if (PyDict_SetItem(coverage_global, K_scripts, scripts) < 0) {
            Py_DECREF(scripts);
            return -1;
        }
        Py_DECREF(scripts);
    }

    // Get/create script_coverage
    PyObject *script_coverage = PyDict_GetItemWithError(scripts, script_name);
    if (script_coverage == NULL) {
        if (PyErr_Occurred()) return -1;
        script_coverage = PyDict_New();
        if (script_coverage == NULL) return -1;
        PyObject *covered = PyDict_New();
        if (covered == NULL) {
            Py_DECREF(script_coverage);
            return -1;
        }
        if (PyDict_SetItem(script_coverage, K_script, script) < 0 ||
            PyDict_SetItem(script_coverage, K_covered, covered) < 0) {
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

    // Increment count at str(lineno)
    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) return -1;

    PyObject *covered_statements = PyDict_GetItemWithError(script_coverage, K_covered);
    if (covered_statements == NULL) {
        Py_DECREF(lineno_str);
        return -1;
    }

    PyObject *covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
    if (covered_statement == NULL) {
        if (PyErr_Occurred()) {
            Py_DECREF(lineno_str);
            return -1;
        }
        covered_statement = PyDict_New();
        if (covered_statement == NULL) {
            Py_DECREF(lineno_str);
            return -1;
        }
        if (PyDict_SetItem(covered_statement, K_statement, statement) < 0 ||
            PyDict_SetItem(covered_statement, K_count, G_PY_ZERO) < 0) {
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        if (PyDict_SetItem(covered_statements, lineno_str, covered_statement) < 0) {
            Py_DECREF(covered_statement);
            Py_DECREF(lineno_str);
            return -1;
        }
        Py_DECREF(covered_statement);
        covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
        if (covered_statement == NULL) {
            Py_DECREF(lineno_str);
            return -1;
        }
    }
    Py_DECREF(lineno_str);

    PyObject *cur = PyDict_GetItemWithError(covered_statement, K_count);
    if (cur == NULL) return -1;
    PyObject *new_count = PyNumber_Add(cur, G_PY_ONE);
    if (new_count == NULL) return -1;
    if (PyDict_SetItem(covered_statement, K_count, new_count) < 0) {
        Py_DECREF(new_count);
        return -1;
    }
    Py_DECREF(new_count);
    return 0;
}


// ===== _script_function =====

static PyObject *
script_function_call(PyObject *script, PyObject *function,
                     PyObject *args, PyObject *options)
{
    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    PyObject *func_args = dict_get(function, K_args);
    if (PyErr_Occurred()) {
        Py_DECREF(func_locals);
        return NULL;
    }
    if (func_args != NULL) {
        if (!PyList_Check(args) && !PyTuple_Check(args)) {
            Py_DECREF(func_locals);
            PyErr_SetString(PyExc_TypeError, "script function args must be a sequence");
            return NULL;
        }
        Py_ssize_t args_length = PySequence_Length(args);
        Py_ssize_t func_args_length = PyList_Check(func_args)
            ? PyList_GET_SIZE(func_args)
            : PySequence_Length(func_args);

        PyObject *last_arg_array = dict_get(function, K_lastArgArray);
        if (PyErr_Occurred()) {
            Py_DECREF(func_locals);
            return NULL;
        }
        Py_ssize_t ix_arg_last = -1;
        if (last_arg_array != NULL && PyObject_IsTrue(last_arg_array)) {
            ix_arg_last = func_args_length - 1;
        }

        for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
            PyObject *arg_name = PyList_Check(func_args)
                ? PyList_GET_ITEM(func_args, ix)
                : PySequence_GetItem(func_args, ix);
            if (arg_name == NULL) {
                Py_DECREF(func_locals);
                return NULL;
            }
            if (!PyList_Check(func_args)) {
                // PySequence_GetItem gave us a new ref; will Py_DECREF below
            } else {
                Py_INCREF(arg_name);
            }

            PyObject *value = NULL;
            int new_ref = 0;
            if (ix < args_length) {
                if (ix != ix_arg_last) {
                    value = PyList_Check(args)
                        ? PyList_GET_ITEM(args, ix)
                        : PySequence_GetItem(args, ix);
                    if (PyList_Check(args)) {
                        // borrowed, will INCREF below
                    } else {
                        new_ref = 1;
                    }
                } else {
                    // Slice args[ix:]
                    value = PySequence_GetSlice(args, ix, args_length);
                    new_ref = 1;
                }
                if (value == NULL) {
                    Py_DECREF(arg_name);
                    Py_DECREF(func_locals);
                    return NULL;
                }
                if (!new_ref) Py_INCREF(value);
            } else {
                if (ix == ix_arg_last) {
                    value = PyList_New(0);
                } else {
                    value = Py_None;
                    Py_INCREF(value);
                }
                if (value == NULL) {
                    Py_DECREF(arg_name);
                    Py_DECREF(func_locals);
                    return NULL;
                }
            }

            if (PyDict_SetItem(func_locals, arg_name, value) < 0) {
                Py_DECREF(value);
                Py_DECREF(arg_name);
                Py_DECREF(func_locals);
                return NULL;
            }
            Py_DECREF(value);
            Py_DECREF(arg_name);
        }
    }

    PyObject *func_statements = PyDict_GetItemWithError(function, K_statements);
    if (func_statements == NULL) {
        Py_DECREF(func_locals);
        return NULL;
    }
    PyObject *result = execute_script_helper(script, func_statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}


// ===== execute_script_helper =====

static PyObject *
execute_script_helper(PyObject *script, PyObject *statements,
                      PyObject *options, PyObject *locals_)
{
    PyObject *globals_ = PyDict_GetItemWithError(options, K_globals);
    if (globals_ == NULL) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_KeyError, "globals");
        }
        return NULL;
    }

    PyObject *label_indexes = NULL;
    Py_ssize_t statements_length = PyList_Check(statements)
        ? PyList_GET_SIZE(statements)
        : PySequence_Length(statements);
    Py_ssize_t ix_statement = 0;

    // Hoist: cache max_statements as a C double once.
    // (Re-reading per statement is wasteful; rarely changes during execution.)
    double max_statements_d = 1e9;
    int max_statements_active = 0;
    {
        PyObject *ms = PyDict_GetItemWithError(options, K_maxStatements);
        if (ms == NULL && PyErr_Occurred()) return NULL;
        if (ms != NULL) {
            if (PyLong_CheckExact(ms)) max_statements_d = (double)PyLong_AsLongLong(ms);
            else if (PyFloat_CheckExact(ms)) max_statements_d = PyFloat_AS_DOUBLE(ms);
            else max_statements_d = PyFloat_AsDouble(ms);
            if (PyErr_Occurred()) return NULL;
        }
        max_statements_active = (max_statements_d > 0.0);
    }

    // Hoist: cache coverage_global / has_coverage.
    // The enabled flag and script.system don't change mid-execution.
    PyObject *coverage_global = PyDict_GetItemWithError(globals_, G_COVERAGE_NAME);
    if (coverage_global == NULL && PyErr_Occurred()) return NULL;
    int has_coverage = 0;
    if (coverage_global != NULL && PyDict_Check(coverage_global)) {
        PyObject *enabled = dict_get(coverage_global, K_enabled);
        if (PyErr_Occurred()) return NULL;
        int enabled_truthy = (enabled != NULL && PyObject_IsTrue(enabled) == 1);
        PyObject *system_flag = dict_get(script, K_system);
        if (PyErr_Occurred()) return NULL;
        int system_truthy = (system_flag != NULL && PyObject_IsTrue(system_flag) == 1);
        has_coverage = enabled_truthy && !system_truthy;
    }

    while (ix_statement < statements_length) {
        PyObject *statement = PyList_Check(statements)
            ? PyList_GET_ITEM(statements, ix_statement)
            : PySequence_GetItem(statements, ix_statement);
        PyObject *statement_owned = NULL;
        if (!PyList_Check(statements)) {
            if (statement == NULL) goto error;
            statement_owned = statement;
        }
        PyObject *statement_key = single_dict_key(statement);
        if (statement_key == NULL) {
            Py_XDECREF(statement_owned);
            goto error;
        }

        // Increment statementCount: read/inc/write via C arithmetic
        PyObject *cur_count = PyDict_GetItemWithError(options, K_statementCount);
        if (cur_count == NULL && PyErr_Occurred()) {
            Py_XDECREF(statement_owned);
            goto error;
        }
        Py_ssize_t cur_count_int = 0;
        if (cur_count != NULL && PyLong_CheckExact(cur_count)) {
            cur_count_int = PyLong_AsSsize_t(cur_count);
            if (cur_count_int == -1 && PyErr_Occurred()) {
                Py_XDECREF(statement_owned);
                goto error;
            }
        }
        Py_ssize_t new_count_int = cur_count_int + 1;
        PyObject *new_count = PyLong_FromSsize_t(new_count_int);
        if (new_count == NULL) {
            Py_XDECREF(statement_owned);
            goto error;
        }
        if (PyDict_SetItem(options, K_statementCount, new_count) < 0) {
            Py_DECREF(new_count);
            Py_XDECREF(statement_owned);
            goto error;
        }
        Py_DECREF(new_count);

        // Check max statements (using cached max_statements_d)
        if (max_statements_active && (double)new_count_int > max_statements_d) {
            char max_buf[64];
            if (max_statements_d == (double)(Py_ssize_t)max_statements_d) {
                snprintf(max_buf, sizeof(max_buf), "%zd", (Py_ssize_t)max_statements_d);
            } else {
                snprintf(max_buf, sizeof(max_buf), "%g", max_statements_d);
            }
            raise_runtime_error(script, statement,
                "Exceeded maximum script statements (%s)", max_buf);
            Py_XDECREF(statement_owned);
            goto error;
        }

        // Coverage (using cached coverage_global / has_coverage)
        if (has_coverage) {
            if (record_statement_coverage(script, statement, statement_key, coverage_global) < 0) {
                Py_XDECREF(statement_owned);
                goto error;
            }
        }

        // Dispatch
        int sk_is_expr = (PyObject_RichCompareBool(statement_key, K_expr, Py_EQ) == 1);
        if (sk_is_expr) {
            PyObject *expr_dict = PyDict_GetItemWithError(statement, K_expr);
            if (expr_dict == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *expr_subexpr = PyDict_GetItemWithError(expr_dict, K_expr);
            if (expr_subexpr == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *expr_value = evaluate_expression_c(expr_subexpr, options, locals_, 0, script, statement);
            if (expr_value == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *expr_name = dict_get(expr_dict, K_name);
            if (PyErr_Occurred()) {
                Py_DECREF(expr_value);
                Py_XDECREF(statement_owned);
                goto error;
            }
            if (expr_name != NULL) {
                PyObject *target = (locals_ != NULL) ? locals_ : globals_;
                if (PyDict_SetItem(target, expr_name, expr_value) < 0) {
                    Py_DECREF(expr_value);
                    Py_XDECREF(statement_owned);
                    goto error;
                }
            }
            Py_DECREF(expr_value);
        }
        else if (PyObject_RichCompareBool(statement_key, K_jump, Py_EQ) == 1) {
            PyObject *jump_dict = PyDict_GetItemWithError(statement, K_jump);
            if (jump_dict == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            // Has expr?
            PyObject *jump_expr = PyDict_GetItemWithError(jump_dict, K_expr);
            int do_jump = 1;
            if (jump_expr == NULL) {
                if (PyErr_Occurred()) PyErr_Clear();
            } else {
                PyObject *cond_value = evaluate_expression_c(jump_expr, options, locals_, 0, script, statement);
                if (cond_value == NULL) {
                    Py_XDECREF(statement_owned);
                    goto error;
                }
                int is_true = fast_value_boolean(cond_value);
                Py_DECREF(cond_value);
                if (is_true < 0) {
                    Py_XDECREF(statement_owned);
                    goto error;
                }
                do_jump = is_true;
            }

            if (do_jump) {
                PyObject *jump_label = PyDict_GetItemWithError(jump_dict, K_label);
                if (jump_label == NULL) {
                    Py_XDECREF(statement_owned);
                    goto error;
                }

                // Look up in label_indexes
                PyObject *cached = NULL;
                if (label_indexes != NULL) {
                    cached = PyDict_GetItemWithError(label_indexes, jump_label);
                    if (cached == NULL && PyErr_Occurred()) {
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                }
                Py_ssize_t ix_label = -1;
                if (cached != NULL) {
                    ix_label = PyLong_AsSsize_t(cached);
                    if (ix_label == -1 && PyErr_Occurred()) {
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                } else {
                    // Linear search
                    for (Py_ssize_t i = 0; i < statements_length; i++) {
                        PyObject *st = PyList_Check(statements) ? PyList_GET_ITEM(statements, i) : PySequence_GetItem(statements, i);
                        PyObject *st_owned = PyList_Check(statements) ? NULL : st;
                        if (st == NULL) {
                            Py_XDECREF(statement_owned);
                            goto error;
                        }
                        if (PyDict_Check(st)) {
                            PyObject *lbl = PyDict_GetItemWithError(st, K_label);
                            if (lbl == NULL) {
                                if (PyErr_Occurred()) {
                                    Py_XDECREF(st_owned);
                                    Py_XDECREF(statement_owned);
                                    goto error;
                                }
                            } else if (PyDict_Check(lbl)) {
                                PyObject *lname = PyDict_GetItemWithError(lbl, K_name);
                                if (lname == NULL) {
                                    if (PyErr_Occurred()) {
                                        Py_XDECREF(st_owned);
                                        Py_XDECREF(statement_owned);
                                        goto error;
                                    }
                                } else {
                                    int eq = PyObject_RichCompareBool(lname, jump_label, Py_EQ);
                                    if (eq < 0) {
                                        Py_XDECREF(st_owned);
                                        Py_XDECREF(statement_owned);
                                        goto error;
                                    }
                                    if (eq) {
                                        ix_label = i;
                                        Py_XDECREF(st_owned);
                                        break;
                                    }
                                }
                            }
                        }
                        Py_XDECREF(st_owned);
                    }
                    if (ix_label == -1) {
                        const char *lstr = PyUnicode_AsUTF8(jump_label);
                        raise_runtime_error(script, statement, "Unknown jump label \"%s\"", lstr ? lstr : "?");
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) {
                            Py_XDECREF(statement_owned);
                            goto error;
                        }
                    }
                    PyObject *ix_obj = PyLong_FromSsize_t(ix_label);
                    if (ix_obj == NULL) {
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    int rc = PyDict_SetItem(label_indexes, jump_label, ix_obj);
                    Py_DECREF(ix_obj);
                    if (rc < 0) {
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                }

                ix_statement = ix_label;

                // Coverage on label statement
                if (has_coverage) {
                    PyObject *label_stmt = PyList_Check(statements) ? PyList_GET_ITEM(statements, ix_statement) : PySequence_GetItem(statements, ix_statement);
                    PyObject *label_stmt_owned = PyList_Check(statements) ? NULL : label_stmt;
                    if (label_stmt == NULL) {
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    PyObject *label_stmt_key = single_dict_key(label_stmt);
                    if (label_stmt_key == NULL) {
                        Py_XDECREF(label_stmt_owned);
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    if (record_statement_coverage(script, label_stmt, label_stmt_key, coverage_global) < 0) {
                        Py_XDECREF(label_stmt_owned);
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    Py_XDECREF(label_stmt_owned);
                }
            }
        }
        else if (PyObject_RichCompareBool(statement_key, K_returnK, Py_EQ) == 1) {
            PyObject *return_dict = PyDict_GetItemWithError(statement, K_returnK);
            if (return_dict == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *ret_expr = PyDict_GetItemWithError(return_dict, K_expr);
            if (ret_expr == NULL) {
                if (PyErr_Occurred()) {
                    Py_XDECREF(statement_owned);
                    goto error;
                }
                Py_XDECREF(statement_owned);
                Py_XDECREF(label_indexes);
                Py_RETURN_NONE;
            }
            PyObject *ret_value = evaluate_expression_c(ret_expr, options, locals_, 0, script, statement);
            Py_XDECREF(statement_owned);
            Py_XDECREF(label_indexes);
            return ret_value;
        }
        else if (PyObject_RichCompareBool(statement_key, K_functionK, Py_EQ) == 1) {
            PyObject *function_dict = PyDict_GetItemWithError(statement, K_functionK);
            if (function_dict == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *fn_name = PyDict_GetItemWithError(function_dict, K_name);
            if (fn_name == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *sf_args = PyTuple_Pack(2, script, function_dict);
            if (sf_args == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *sf = PyObject_CallObject((PyObject *)&ScriptFuncType, sf_args);
            Py_DECREF(sf_args);
            if (sf == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            int rc = PyDict_SetItem(globals_, fn_name, sf);
            Py_DECREF(sf);
            if (rc < 0) {
                Py_XDECREF(statement_owned);
                goto error;
            }
        }
        else if (PyObject_RichCompareBool(statement_key, K_include, Py_EQ) == 1) {
            PyObject *include_dict = PyDict_GetItemWithError(statement, K_include);
            if (include_dict == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            PyObject *system_prefix = dict_get(options, K_systemPrefix);
            if (PyErr_Occurred()) { Py_XDECREF(statement_owned); goto error; }
            PyObject *fetch_fn = dict_get(options, K_fetchFn);
            if (PyErr_Occurred()) { Py_XDECREF(statement_owned); goto error; }
            PyObject *log_fn = dict_get(options, K_logFn);
            if (PyErr_Occurred()) { Py_XDECREF(statement_owned); goto error; }
            PyObject *url_fn = dict_get(options, K_urlFn);
            if (PyErr_Occurred()) { Py_XDECREF(statement_owned); goto error; }

            PyObject *includes_list = PyDict_GetItemWithError(include_dict, K_includes);
            if (includes_list == NULL) {
                Py_XDECREF(statement_owned);
                goto error;
            }
            Py_ssize_t nincludes = PyList_Check(includes_list) ? PyList_GET_SIZE(includes_list) : PySequence_Length(includes_list);
            for (Py_ssize_t inc_i = 0; inc_i < nincludes; inc_i++) {
                PyObject *include = PyList_Check(includes_list)
                    ? PyList_GET_ITEM(includes_list, inc_i)
                    : PySequence_GetItem(includes_list, inc_i);
                PyObject *include_owned = PyList_Check(includes_list) ? NULL : include;
                if (include == NULL) { Py_XDECREF(statement_owned); goto error; }

                PyObject *include_url = PyDict_GetItemWithError(include, K_url);
                if (include_url == NULL) {
                    Py_XDECREF(include_owned);
                    Py_XDECREF(statement_owned);
                    goto error;
                }
                Py_INCREF(include_url);
                PyObject *include_url_owned = include_url; // we now own a ref

                PyObject *system_include = dict_get(include, K_system);
                if (PyErr_Occurred()) {
                    Py_DECREF(include_url_owned);
                    Py_XDECREF(include_owned);
                    Py_XDECREF(statement_owned);
                    goto error;
                }
                int sys_inc_truthy = (system_include != NULL && PyObject_IsTrue(system_include) == 1);
                if (sys_inc_truthy && system_prefix != NULL) {
                    PyObject *fixed = PyObject_CallFunctionObjArgs(G_url_file_relative, system_prefix, include_url_owned, NULL);
                    if (fixed == NULL) {
                        Py_DECREF(include_url_owned);
                        Py_XDECREF(include_owned);
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    Py_DECREF(include_url_owned);
                    include_url_owned = fixed;
                } else if (url_fn != NULL) {
                    PyObject *fixed = PyObject_CallFunctionObjArgs(url_fn, include_url_owned, NULL);
                    if (fixed == NULL) {
                        Py_DECREF(include_url_owned);
                        Py_XDECREF(include_owned);
                        Py_XDECREF(statement_owned);
                        goto error;
                    }
                    Py_DECREF(include_url_owned);
                    include_url_owned = fixed;
                }

                // Already included?
                PyObject *global_includes = dict_get(globals_, G_INCLUDES_NAME);
                if (PyErr_Occurred()) {
                    Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                if (global_includes == NULL || !PyDict_Check(global_includes)) {
                    global_includes = PyDict_New();
                    if (global_includes == NULL) {
                        Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                    }
                    if (PyDict_SetItem(globals_, G_INCLUDES_NAME, global_includes) < 0) {
                        Py_DECREF(global_includes); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                    }
                    Py_DECREF(global_includes);
                    global_includes = PyDict_GetItemWithError(globals_, G_INCLUDES_NAME);
                    if (global_includes == NULL) {
                        Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                    }
                }
                PyObject *already = PyDict_GetItemWithError(global_includes, include_url_owned);
                if (already == NULL && PyErr_Occurred()) {
                    Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                if (already != NULL && PyObject_IsTrue(already) == 1) {
                    Py_DECREF(include_url_owned);
                    Py_XDECREF(include_owned);
                    continue;
                }
                if (PyDict_SetItem(global_includes, include_url_owned, Py_True) < 0) {
                    Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }

                // Fetch
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *fetch_arg = PyDict_New();
                    if (fetch_arg == NULL) {
                        Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                    }
                    if (PyDict_SetItem(fetch_arg, K_url, include_url_owned) < 0) {
                        Py_DECREF(fetch_arg); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
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
                    const char *url_str = PyUnicode_AsUTF8(include_url_owned);
                    raise_runtime_error(script, statement, "Include of \"%s\" failed", url_str ? url_str : "?");
                    Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }

                // Parse
                PyObject *one = PyLong_FromLong(1);
                if (one == NULL) {
                    Py_DECREF(include_text); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                PyObject *include_script = PyObject_CallFunctionObjArgs(G_parse_script, include_text, one, include_url_owned, NULL);
                Py_DECREF(one);
                Py_DECREF(include_text);
                if (include_script == NULL) {
                    Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                if (sys_inc_truthy) {
                    if (PyDict_SetItem(include_script, K_system, Py_True) < 0) {
                        Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                    }
                }

                // Copy options, set urlFn = partial(url_file_relative, include_url)
                PyObject *include_options = PyDict_Copy(options);
                if (include_options == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(G_functools_partial, G_url_file_relative, include_url_owned, NULL);
                if (new_url_fn == NULL) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                if (PyDict_SetItem(include_options, K_urlFn, new_url_fn) < 0) {
                    Py_DECREF(new_url_fn); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                Py_DECREF(new_url_fn);

                PyObject *inc_statements = PyDict_GetItemWithError(include_script, K_statements);
                if (inc_statements == NULL) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                PyObject *exec_result = execute_script_helper(include_script, inc_statements, include_options, NULL);
                if (exec_result == NULL) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                }
                Py_DECREF(exec_result);

                // Lint if log_fn and debug
                if (log_fn != NULL) {
                    PyObject *debug = dict_get(options, K_debug);
                    if (PyErr_Occurred()) {
                        Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                    }
                    int debug_truthy = (debug != NULL && PyObject_IsTrue(debug) == 1);
                    if (debug_truthy) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(G_lint_script, include_script, globals_, NULL);
                        if (warnings == NULL) {
                            Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                        }
                        Py_ssize_t nw = PyObject_Length(warnings);
                        if (nw > 0) {
                            const char *url_str = PyUnicode_AsUTF8(include_url_owned);
                            PyObject *prefix = PyUnicode_FromFormat(
                                "BareScript: Include \"%s\" static analysis... %zd warning%s:",
                                url_str ? url_str : "?", nw, nw > 1 ? "s" : "");
                            if (prefix == NULL) {
                                Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                            }
                            PyObject *r = PyObject_CallFunctionObjArgs(log_fn, prefix, NULL);
                            Py_DECREF(prefix);
                            if (r == NULL) {
                                Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                            }
                            Py_DECREF(r);
                            PyObject *iter = PyObject_GetIter(warnings);
                            if (iter == NULL) {
                                Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                            }
                            PyObject *w;
                            while ((w = PyIter_Next(iter)) != NULL) {
                                PyObject *wmsg = PyUnicode_FromFormat("BareScript: %U", w);
                                Py_DECREF(w);
                                if (wmsg == NULL) {
                                    Py_DECREF(iter); Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                                }
                                PyObject *r2 = PyObject_CallFunctionObjArgs(log_fn, wmsg, NULL);
                                Py_DECREF(wmsg);
                                if (r2 == NULL) {
                                    Py_DECREF(iter); Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                                }
                                Py_DECREF(r2);
                            }
                            Py_DECREF(iter);
                            if (PyErr_Occurred()) {
                                Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url_owned); Py_XDECREF(include_owned); Py_XDECREF(statement_owned); goto error;
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }

                Py_DECREF(include_options);
                Py_DECREF(include_script);
                Py_DECREF(include_url_owned);
                Py_XDECREF(include_owned);
            }
        }

        Py_XDECREF(statement_owned);
        ix_statement++;
    }

    Py_XDECREF(label_indexes);
    Py_RETURN_NONE;

error:
    Py_XDECREF(label_indexes);
    return NULL;
}


// ===== evaluate_expression =====

static PyObject *
evaluate_expression_c(PyObject *expr, PyObject *options, PyObject *locals_,
                      int builtins, PyObject *script, PyObject *statement)
{
    if (!PyDict_Check(expr)) {
        PyErr_SetString(PyExc_TypeError, "expression must be a dict");
        return NULL;
    }
    if (PyDict_GET_SIZE(expr) != 1) {
        PyErr_SetString(PyExc_ValueError, "expression must have exactly one key");
        return NULL;
    }
    PyObject *expr_key = single_dict_key(expr);
    if (expr_key == NULL) return NULL;

    PyObject *globals_ = NULL;
    if (options != NULL && PyDict_Check(options)) {
        globals_ = PyDict_GetItemWithError(options, K_globals);
        if (globals_ == NULL && PyErr_Occurred()) return NULL;
    }

    // Number
    if (PyObject_RichCompareBool(expr_key, K_number, Py_EQ) == 1) {
        PyObject *n = PyDict_GetItemWithError(expr, K_number);
        if (n == NULL) return NULL;
        Py_INCREF(n);
        return n;
    }

    // String
    if (PyObject_RichCompareBool(expr_key, K_string, Py_EQ) == 1) {
        PyObject *s = PyDict_GetItemWithError(expr, K_string);
        if (s == NULL) return NULL;
        Py_INCREF(s);
        return s;
    }

    // Variable
    if (PyObject_RichCompareBool(expr_key, K_variable, Py_EQ) == 1) {
        PyObject *var_name = PyDict_GetItemWithError(expr, K_variable);
        if (var_name == NULL) return NULL;
        // Keywords
        if (PyObject_RichCompareBool(var_name, K_null, Py_EQ) == 1) {
            Py_RETURN_NONE;
        }
        if (PyObject_RichCompareBool(var_name, K_false, Py_EQ) == 1) {
            Py_RETURN_FALSE;
        }
        if (PyObject_RichCompareBool(var_name, K_true, Py_EQ) == 1) {
            Py_RETURN_TRUE;
        }
        if (locals_ != NULL) {
            int has = PyDict_Contains(locals_, var_name);
            if (has < 0) return NULL;
            if (has) {
                PyObject *v = PyDict_GetItemWithError(locals_, var_name);
                if (v == NULL) return NULL;
                Py_INCREF(v);
                return v;
            }
        }
        if (globals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(globals_, var_name);
            if (v == NULL && PyErr_Occurred()) return NULL;
            if (v != NULL) {
                Py_INCREF(v);
                return v;
            }
        }
        Py_RETURN_NONE;
    }

    // Function
    if (PyObject_RichCompareBool(expr_key, K_functionK, Py_EQ) == 1) {
        PyObject *function_dict = PyDict_GetItemWithError(expr, K_functionK);
        if (function_dict == NULL) return NULL;
        PyObject *func_name = PyDict_GetItemWithError(function_dict, K_name);
        if (func_name == NULL) return NULL;

        // "if" built-in
        if (PyObject_RichCompareBool(func_name, K_ifK, Py_EQ) == 1) {
            PyObject *args_expr = dict_get(function_dict, K_args);
            if (PyErr_Occurred()) return NULL;
            Py_ssize_t alen = (args_expr != NULL) ? PyObject_Length(args_expr) : 0;
            PyObject *value_expr = (alen >= 1) ? PySequence_GetItem(args_expr, 0) : NULL;
            if (alen >= 1 && value_expr == NULL) return NULL;
            PyObject *true_expr = (alen >= 2) ? PySequence_GetItem(args_expr, 1) : NULL;
            if (alen >= 2 && true_expr == NULL) { Py_XDECREF(value_expr); return NULL; }
            PyObject *false_expr = (alen >= 3) ? PySequence_GetItem(args_expr, 2) : NULL;
            if (alen >= 3 && false_expr == NULL) { Py_XDECREF(value_expr); Py_XDECREF(true_expr); return NULL; }

            PyObject *value = NULL;
            if (value_expr != NULL) {
                value = evaluate_expression_c(value_expr, options, locals_, builtins, script, statement);
                if (value == NULL) { Py_XDECREF(value_expr); Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
            } else {
                value = Py_False;
                Py_INCREF(value);
            }
            int is_true = fast_value_boolean(value);
            Py_DECREF(value);
            if (is_true < 0) { Py_XDECREF(value_expr); Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
            PyObject *result_expr = is_true ? true_expr : false_expr;
            PyObject *result = NULL;
            if (result_expr != NULL) {
                result = evaluate_expression_c(result_expr, options, locals_, builtins, script, statement);
            } else {
                result = Py_None;
                Py_INCREF(result);
            }
            Py_XDECREF(value_expr); Py_XDECREF(true_expr); Py_XDECREF(false_expr);
            return result;
        }

        // Compute function arguments
        PyObject *func_args = NULL;
        int has_args = PyDict_Contains(function_dict, K_args);
        if (has_args < 0) return NULL;
        if (has_args) {
            PyObject *args_expr = PyDict_GetItemWithError(function_dict, K_args);
            if (args_expr == NULL) return NULL;
            Py_ssize_t alen = PyObject_Length(args_expr);
            if (alen < 0) return NULL;
            func_args = PyList_New(alen);
            if (func_args == NULL) return NULL;
            for (Py_ssize_t i = 0; i < alen; i++) {
                PyObject *a = PySequence_GetItem(args_expr, i);
                if (a == NULL) { Py_DECREF(func_args); return NULL; }
                PyObject *r = evaluate_expression_c(a, options, locals_, builtins, script, statement);
                Py_DECREF(a);
                if (r == NULL) { Py_DECREF(func_args); return NULL; }
                PyList_SET_ITEM(func_args, i, r);
            }
        }

        // Resolve function value
        PyObject *func_value = NULL;
        if (locals_ != NULL) {
            int has = PyDict_Contains(locals_, func_name);
            if (has < 0) { Py_XDECREF(func_args); return NULL; }
            if (has) {
                func_value = PyDict_GetItemWithError(locals_, func_name);
                if (func_value == NULL) { Py_XDECREF(func_args); return NULL; }
            }
        }
        if (func_value == NULL && globals_ != NULL) {
            int has = PyDict_Contains(globals_, func_name);
            if (has < 0) { Py_XDECREF(func_args); return NULL; }
            if (has) {
                func_value = PyDict_GetItemWithError(globals_, func_name);
                if (func_value == NULL) { Py_XDECREF(func_args); return NULL; }
            }
        }
        if (func_value == NULL && builtins) {
            func_value = PyDict_GetItemWithError(G_EXPRESSION_FUNCTIONS, func_name);
            if (func_value == NULL && PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
        }

        if (func_value != NULL && func_value != Py_None) {
            Py_INCREF(func_value);
            PyObject *call_args = func_args;
            if (call_args == NULL) {
                call_args = Py_None;
                Py_INCREF(call_args);
            }
            PyObject *call_options = (options != NULL) ? options : Py_None;
            PyObject *result = PyObject_CallFunctionObjArgs(func_value, call_args, call_options, NULL);
            Py_DECREF(func_value);
            Py_DECREF(call_args);
            if (result == NULL) {
                // Catch ValueArgsError -> return its return_value
                // BareScriptRuntimeError re-raised
                if (PyErr_ExceptionMatches(G_BareScriptRuntimeError)) {
                    return NULL;
                }
                // Log + return None
                PyObject *exc_type, *exc_value, *exc_tb;
                PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
                PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);

                if (options != NULL && PyDict_Check(options)) {
                    PyObject *log_fn = dict_get(options, K_logFn);
                    if (log_fn != NULL) {
                        PyObject *debug = dict_get(options, K_debug);
                        int debug_truthy = (debug != NULL && PyObject_IsTrue(debug) == 1);
                        if (debug_truthy) {
                            PyObject *err_str = (exc_value != NULL) ? PyObject_Str(exc_value) : PyUnicode_FromString("");
                            if (err_str != NULL) {
                                PyObject *msg = PyUnicode_FromFormat(
                                    "BareScript: Function \"%U\" failed with error: %U",
                                    func_name, err_str);
                                if (msg != NULL) {
                                    PyObject *r2 = PyObject_CallFunctionObjArgs(log_fn, msg, NULL);
                                    Py_XDECREF(r2);
                                    Py_DECREF(msg);
                                }
                                Py_DECREF(err_str);
                            }
                            PyErr_Clear();
                        }
                    }
                }

                // Is it ValueArgsError?
                int is_vae = 0;
                if (exc_type != NULL && G_ValueArgsError != NULL) {
                    is_vae = PyObject_IsSubclass(exc_type, G_ValueArgsError) == 1;
                }
                if (is_vae && exc_value != NULL) {
                    PyObject *rv = PyObject_GetAttr(exc_value, K_return_value);
                    Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                    if (rv != NULL) return rv;
                    PyErr_Clear();
                    Py_RETURN_NONE;
                }
                Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                Py_RETURN_NONE;
            }
            return result;
        }
        Py_XDECREF(func_args);

        const char *fn_str = PyUnicode_AsUTF8(func_name);
        raise_runtime_error(script, statement, "Undefined function \"%s\"", fn_str ? fn_str : "?");
        return NULL;
    }

    // Binary
    if (PyObject_RichCompareBool(expr_key, K_binary, Py_EQ) == 1) {
        PyObject *bin = PyDict_GetItemWithError(expr, K_binary);
        if (bin == NULL) return NULL;
        PyObject *op = PyDict_GetItemWithError(bin, K_op);
        if (op == NULL) return NULL;
        PyObject *left_expr = PyDict_GetItemWithError(bin, K_left);
        if (left_expr == NULL) return NULL;
        PyObject *right_expr = PyDict_GetItemWithError(bin, K_right);
        if (right_expr == NULL) return NULL;

        PyObject *left = evaluate_expression_c(left_expr, options, locals_, builtins, script, statement);
        if (left == NULL) return NULL;

        const char *op_str = PyUnicode_AsUTF8(op);
        if (op_str == NULL) { Py_DECREF(left); return NULL; }

        // Short-circuit && / ||
        if (op_str[0] == '&' && op_str[1] == '&' && op_str[2] == 0) {
            int is_true = fast_value_boolean(left);
            if (is_true < 0) { Py_DECREF(left); return NULL; }
            if (!is_true) return left;
            Py_DECREF(left);
            return evaluate_expression_c(right_expr, options, locals_, builtins, script, statement);
        }
        if (op_str[0] == '|' && op_str[1] == '|' && op_str[2] == 0) {
            int is_true = fast_value_boolean(left);
            if (is_true < 0) { Py_DECREF(left); return NULL; }
            if (is_true) return left;
            Py_DECREF(left);
            return evaluate_expression_c(right_expr, options, locals_, builtins, script, statement);
        }

        PyObject *right = evaluate_expression_c(right_expr, options, locals_, builtins, script, statement);
        if (right == NULL) { Py_DECREF(left); return NULL; }

        PyObject *result = NULL;
        // Fast path: both PyFloat exact
        int l_float = PyFloat_CheckExact(left);
        int r_float = PyFloat_CheckExact(right);
        int l_long = PyLong_CheckExact(left) && !PyBool_Check(left);
        int r_long = PyLong_CheckExact(right) && !PyBool_Check(right);
        int ln = l_float || l_long;
        int rn = r_float || r_long;

        // Fast numeric arithmetic
        if (ln && rn && (op_str[1] == 0 || (op_str[0] == '*' && op_str[1] == '*' && op_str[2] == 0))) {
            char op0 = op_str[0];
            if (l_float && r_float) {
                double a = PyFloat_AS_DOUBLE(left);
                double b = PyFloat_AS_DOUBLE(right);
                if (op0 == '+') result = PyFloat_FromDouble(a + b);
                else if (op0 == '-') result = PyFloat_FromDouble(a - b);
                else if (op0 == '*' && op_str[1] == 0) result = PyFloat_FromDouble(a * b);
                else if (op0 == '/') {
                    if (b == 0.0) {
                        result = PyNumber_TrueDivide(left, right); // will raise
                    } else {
                        result = PyFloat_FromDouble(a / b);
                    }
                }
            } else if (l_long && r_long) {
                if (op0 == '+') result = PyNumber_Add(left, right);
                else if (op0 == '-') result = PyNumber_Subtract(left, right);
                else if (op0 == '*' && op_str[1] == 0) result = PyNumber_Multiply(left, right);
                else if (op0 == '/') result = PyNumber_TrueDivide(left, right);
            } else {
                // Mixed long/float
                double a = l_float ? PyFloat_AS_DOUBLE(left) : PyLong_AsDouble(left);
                if (a == -1 && PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                double b = r_float ? PyFloat_AS_DOUBLE(right) : PyLong_AsDouble(right);
                if (b == -1 && PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                if (op0 == '+') result = PyFloat_FromDouble(a + b);
                else if (op0 == '-') result = PyFloat_FromDouble(a - b);
                else if (op0 == '*' && op_str[1] == 0) result = PyFloat_FromDouble(a * b);
                else if (op0 == '/') {
                    if (b == 0.0) {
                        result = PyNumber_TrueDivide(left, right);
                    } else {
                        result = PyFloat_FromDouble(a / b);
                    }
                }
            }
            if (result != NULL) {
                Py_DECREF(left); Py_DECREF(right);
                return result;
            }
            // fall through if op was '**' or similar — handled below
        }

        if (op_str[0] == '+' && op_str[1] == 0) {
            if (ln && rn) {
                result = PyNumber_Add(left, right);
            } else if (PyUnicode_Check(left) && PyUnicode_Check(right)) {
                result = PyUnicode_Concat(left, right);
            } else if (PyUnicode_Check(left)) {
                PyObject *rs = PyObject_CallFunctionObjArgs(G_value_string, right, NULL);
                if (rs == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                result = PyUnicode_Concat(left, rs);
                Py_DECREF(rs);
            } else if (PyUnicode_Check(right)) {
                PyObject *ls = PyObject_CallFunctionObjArgs(G_value_string, left, NULL);
                if (ls == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                result = PyUnicode_Concat(ls, right);
                Py_DECREF(ls);
            } else if (is_date(left) && rn) {
                PyObject *ld = PyObject_CallFunctionObjArgs(G_value_normalize_datetime, left, NULL);
                if (ld == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                PyObject *kwargs = PyDict_New();
                if (kwargs == NULL) { Py_DECREF(ld); Py_DECREF(left); Py_DECREF(right); return NULL; }
                if (PyDict_SetItem(kwargs, K_milliseconds, right) < 0) {
                    Py_DECREF(kwargs); Py_DECREF(ld); Py_DECREF(left); Py_DECREF(right); return NULL;
                }
                PyObject *args0 = PyTuple_New(0);
                PyObject *td = PyObject_Call(G_datetime_timedelta, args0, kwargs);
                Py_DECREF(args0);
                Py_DECREF(kwargs);
                if (td == NULL) { Py_DECREF(ld); Py_DECREF(left); Py_DECREF(right); return NULL; }
                result = PyNumber_Add(ld, td);
                Py_DECREF(ld);
                Py_DECREF(td);
            } else if (ln && is_date(right)) {
                PyObject *rd = PyObject_CallFunctionObjArgs(G_value_normalize_datetime, right, NULL);
                if (rd == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                PyObject *kwargs = PyDict_New();
                if (kwargs == NULL) { Py_DECREF(rd); Py_DECREF(left); Py_DECREF(right); return NULL; }
                if (PyDict_SetItem(kwargs, K_milliseconds, left) < 0) {
                    Py_DECREF(kwargs); Py_DECREF(rd); Py_DECREF(left); Py_DECREF(right); return NULL;
                }
                PyObject *args0 = PyTuple_New(0);
                PyObject *td = PyObject_Call(G_datetime_timedelta, args0, kwargs);
                Py_DECREF(args0);
                Py_DECREF(kwargs);
                if (td == NULL) { Py_DECREF(rd); Py_DECREF(left); Py_DECREF(right); return NULL; }
                result = PyNumber_Add(rd, td);
                Py_DECREF(rd);
                Py_DECREF(td);
            } else {
                Py_INCREF(Py_None);
                result = Py_None;
            }
        }
        else if (op_str[0] == '-' && op_str[1] == 0) {
            if (ln && rn) {
                result = PyNumber_Subtract(left, right);
            } else if (is_date(left) && is_date(right)) {
                PyObject *ld = PyObject_CallFunctionObjArgs(G_value_normalize_datetime, left, NULL);
                if (ld == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                PyObject *rd = PyObject_CallFunctionObjArgs(G_value_normalize_datetime, right, NULL);
                if (rd == NULL) { Py_DECREF(ld); Py_DECREF(left); Py_DECREF(right); return NULL; }
                PyObject *diff = PyNumber_Subtract(ld, rd);
                Py_DECREF(ld); Py_DECREF(rd);
                if (diff == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                Py_DECREF(diff);
                if (secs == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                PyObject *thousand = PyLong_FromLong(1000);
                PyObject *ms = PyNumber_Multiply(secs, thousand);
                Py_DECREF(secs); Py_DECREF(thousand);
                if (ms == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                result = PyObject_CallFunctionObjArgs(G_value_round_number, ms, G_PY_ZERO, NULL);
                Py_DECREF(ms);
            } else {
                Py_INCREF(Py_None);
                result = Py_None;
            }
        }
        else if (op_str[0] == '*' && op_str[1] == 0) {
            if (ln && rn) result = PyNumber_Multiply(left, right);
            else { Py_INCREF(Py_None); result = Py_None; }
        }
        else if (op_str[0] == '/' && op_str[1] == 0) {
            if (ln && rn) result = PyNumber_TrueDivide(left, right);
            else { Py_INCREF(Py_None); result = Py_None; }
        }
        else if ((op_str[0] == '=' && op_str[1] == '=') ||
                 (op_str[0] == '!' && op_str[1] == '=') ||
                 (op_str[0] == '<' && (op_str[1] == 0 || op_str[1] == '=')) ||
                 (op_str[0] == '>' && (op_str[1] == 0 || op_str[1] == '='))) {
            int op_id;
            if (op_str[0] == '=') op_id = Py_EQ;
            else if (op_str[0] == '!') op_id = Py_NE;
            else if (op_str[0] == '<') op_id = (op_str[1] == '=') ? Py_LE : Py_LT;
            else op_id = (op_str[1] == '=') ? Py_GE : Py_GT;
            // Fast path: numeric/numeric
            int cmp_int = fast_numeric_compare(left, right);
            if (cmp_int != -2) {
                int rc;
                switch (op_id) {
                    case Py_EQ: rc = (cmp_int == 0); break;
                    case Py_NE: rc = (cmp_int != 0); break;
                    case Py_LE: rc = (cmp_int <= 0); break;
                    case Py_LT: rc = (cmp_int < 0); break;
                    case Py_GE: rc = (cmp_int >= 0); break;
                    default:    rc = (cmp_int > 0); break;
                }
                result = rc ? Py_True : Py_False;
                Py_INCREF(result);
            } else if (PyErr_Occurred()) {
                Py_DECREF(left); Py_DECREF(right); return NULL;
            } else if (PyUnicode_CheckExact(left) && PyUnicode_CheckExact(right)) {
                int rc = PyUnicode_Compare(left, right);
                if (rc == -1 && PyErr_Occurred()) {
                    Py_DECREF(left); Py_DECREF(right); return NULL;
                }
                int b;
                switch (op_id) {
                    case Py_EQ: b = (rc == 0); break;
                    case Py_NE: b = (rc != 0); break;
                    case Py_LE: b = (rc <= 0); break;
                    case Py_LT: b = (rc < 0); break;
                    case Py_GE: b = (rc >= 0); break;
                    default:    b = (rc > 0); break;
                }
                result = b ? Py_True : Py_False;
                Py_INCREF(result);
            } else if (left == Py_None || right == Py_None) {
                // None handling per value_compare
                int cmp_int2 = (left == Py_None && right == Py_None) ? 0 : (left == Py_None ? -1 : 1);
                int b;
                switch (op_id) {
                    case Py_EQ: b = (cmp_int2 == 0); break;
                    case Py_NE: b = (cmp_int2 != 0); break;
                    case Py_LE: b = (cmp_int2 <= 0); break;
                    case Py_LT: b = (cmp_int2 < 0); break;
                    case Py_GE: b = (cmp_int2 >= 0); break;
                    default:    b = (cmp_int2 > 0); break;
                }
                result = b ? Py_True : Py_False;
                Py_INCREF(result);
            } else {
                PyObject *cmp = PyObject_CallFunctionObjArgs(G_value_compare, left, right, NULL);
                if (cmp == NULL) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                int rc = PyObject_RichCompareBool(cmp, G_PY_ZERO, op_id);
                Py_DECREF(cmp);
                if (rc < 0) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                result = rc ? Py_True : Py_False;
                Py_INCREF(result);
            }
        }
        else if (op_str[0] == '%' && op_str[1] == 0) {
            if (ln && rn) result = PyNumber_Remainder(left, right);
            else { Py_INCREF(Py_None); result = Py_None; }
        }
        else if (op_str[0] == '*' && op_str[1] == '*' && op_str[2] == 0) {
            if (ln && rn) result = PyNumber_Power(left, right, Py_None);
            else { Py_INCREF(Py_None); result = Py_None; }
        }
        else if ((op_str[0] == '&' && op_str[1] == 0) ||
                 (op_str[0] == '|' && op_str[1] == 0) ||
                 (op_str[0] == '^' && op_str[1] == 0) ||
                 (op_str[0] == '<' && op_str[1] == '<') ||
                 (op_str[0] == '>' && op_str[1] == '>')) {
            // Both need to be "int-like" (numeric, and int(v) == v)
            int both_intish = 0;
            PyObject *li = NULL, *ri = NULL;
            if (ln && rn) {
                li = PyNumber_Long(left);
                ri = PyNumber_Long(right);
                if (li != NULL && ri != NULL) {
                    int le = PyObject_RichCompareBool(li, left, Py_EQ);
                    int re = PyObject_RichCompareBool(ri, right, Py_EQ);
                    if (le == 1 && re == 1) both_intish = 1;
                    if (le < 0 || re < 0) {
                        Py_DECREF(li); Py_DECREF(ri); Py_DECREF(left); Py_DECREF(right); return NULL;
                    }
                }
            }
            if (both_intish) {
                char c0 = op_str[0];
                if (c0 == '&') result = PyNumber_And(li, ri);
                else if (c0 == '|') result = PyNumber_Or(li, ri);
                else if (c0 == '^') result = PyNumber_Xor(li, ri);
                else if (c0 == '<') result = PyNumber_Lshift(li, ri);
                else result = PyNumber_Rshift(li, ri);
            } else {
                Py_INCREF(Py_None);
                result = Py_None;
            }
            Py_XDECREF(li);
            Py_XDECREF(ri);
        }
        else {
            Py_INCREF(Py_None);
            result = Py_None;
        }

        Py_DECREF(left);
        Py_DECREF(right);
        if (result == NULL) {
            // If we got here with no result but no error, return None
            if (!PyErr_Occurred()) Py_RETURN_NONE;
            return NULL;
        }
        return result;
    }

    // Unary
    if (PyObject_RichCompareBool(expr_key, K_unary, Py_EQ) == 1) {
        PyObject *un = PyDict_GetItemWithError(expr, K_unary);
        if (un == NULL) return NULL;
        PyObject *op = PyDict_GetItemWithError(un, K_op);
        if (op == NULL) return NULL;
        PyObject *sub = PyDict_GetItemWithError(un, K_expr);
        if (sub == NULL) return NULL;
        PyObject *val = evaluate_expression_c(sub, options, locals_, builtins, script, statement);
        if (val == NULL) return NULL;

        const char *op_str = PyUnicode_AsUTF8(op);
        if (op_str == NULL) { Py_DECREF(val); return NULL; }

        PyObject *result = NULL;
        if (op_str[0] == '!' && op_str[1] == 0) {
            int is_true = fast_value_boolean(val);
            if (is_true < 0) { Py_DECREF(val); return NULL; }
            result = is_true ? Py_False : Py_True;
            Py_INCREF(result);
        } else if (op_str[0] == '-' && op_str[1] == 0) {
            if (is_number_not_bool(val)) {
                result = PyNumber_Negative(val);
            } else {
                Py_INCREF(Py_None); result = Py_None;
            }
        } else { // ~
            if (is_number_not_bool(val)) {
                PyObject *vi = PyNumber_Long(val);
                if (vi == NULL) { Py_DECREF(val); return NULL; }
                int eq = PyObject_RichCompareBool(vi, val, Py_EQ);
                if (eq < 0) { Py_DECREF(vi); Py_DECREF(val); return NULL; }
                if (eq) {
                    result = PyNumber_Invert(vi);
                } else {
                    Py_INCREF(Py_None); result = Py_None;
                }
                Py_DECREF(vi);
            } else {
                Py_INCREF(Py_None); result = Py_None;
            }
        }
        Py_DECREF(val);
        if (result == NULL && !PyErr_Occurred()) Py_RETURN_NONE;
        return result;
    }

    // Group
    if (PyObject_RichCompareBool(expr_key, K_group, Py_EQ) == 1) {
        PyObject *sub = PyDict_GetItemWithError(expr, K_group);
        if (sub == NULL) return NULL;
        return evaluate_expression_c(sub, options, locals_, builtins, script, statement);
    }

    PyErr_Format(PyExc_ValueError, "Unknown expression key");
    return NULL;
}


// ===== Module-level: execute_script wrapper =====

static PyObject *
py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script = NULL;
    PyObject *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &script, &options)) {
        return NULL;
    }
    int options_is_new = 0;
    if (options == Py_None) {
        options = PyDict_New();
        if (options == NULL) return NULL;
        options_is_new = 1;
    } else if (!PyDict_Check(options)) {
        PyErr_SetString(PyExc_TypeError, "options must be a dict or None");
        return NULL;
    } else {
        Py_INCREF(options);
        options_is_new = 1;
    }

    // globals
    PyObject *globals_ = PyDict_GetItemWithError(options, K_globals);
    if (globals_ == NULL && PyErr_Occurred()) {
        Py_DECREF(options);
        return NULL;
    }
    if (globals_ == NULL || globals_ == Py_None) {
        globals_ = PyDict_New();
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, K_globals, globals_) < 0) {
            Py_DECREF(globals_); Py_DECREF(options); return NULL;
        }
        Py_DECREF(globals_);
        globals_ = PyDict_GetItemWithError(options, K_globals);
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
    }

    // Update globals with SCRIPT_FUNCTIONS for missing names
    {
        Py_ssize_t pos = 0;
        PyObject *fname, *fval;
        while (PyDict_Next(G_SCRIPT_FUNCTIONS, &pos, &fname, &fval)) {
            int has = PyDict_Contains(globals_, fname);
            if (has < 0) { Py_DECREF(options); return NULL; }
            if (!has) {
                if (PyDict_SetItem(globals_, fname, fval) < 0) {
                    Py_DECREF(options); return NULL;
                }
            }
        }
    }

    // Reset statementCount
    if (PyDict_SetItem(options, K_statementCount, G_PY_ZERO) < 0) {
        Py_DECREF(options); return NULL;
    }

    // Run
    PyObject *statements = PyDict_GetItemWithError(script, K_statements);
    if (statements == NULL) { Py_DECREF(options); return NULL; }
    PyObject *result = execute_script_helper(script, statements, options, NULL);
    (void)options_is_new;
    Py_DECREF(options);
    return result;
}


// ===== Module-level: evaluate_expression wrapper =====

static PyObject *
py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr = NULL;
    PyObject *options = Py_None;
    PyObject *locals_ = Py_None;
    PyObject *builtins_obj = Py_True;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOOOO", kwlist,
                                     &expr, &options, &locals_, &builtins_obj,
                                     &script, &statement)) {
        return NULL;
    }
    int builtins = PyObject_IsTrue(builtins_obj);
    if (builtins < 0) return NULL;
    PyObject *opt = (options == Py_None) ? NULL : options;
    PyObject *loc = (locals_ == Py_None) ? NULL : locals_;
    PyObject *scr = (script == Py_None) ? NULL : script;
    PyObject *stm = (statement == Py_None) ? NULL : statement;
    return evaluate_expression_c(expr, opt, loc, builtins, scr, stm);
}


// ===== Module init =====

static PyMethodDef RuntimeC_methods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS,
     "Execute a BareScript model"},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS,
     "Evaluate a BareScript expression model"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef RuntimeC_module = {
    PyModuleDef_HEAD_INIT,
    "bare_script.runtime_c",
    "C extension port of bare_script.runtime",
    -1,
    RuntimeC_methods,
    NULL, NULL, NULL, NULL
};

static int
intern_keys(void)
{
#define INTERN(var, lit) do { \
    (var) = PyUnicode_InternFromString(lit); \
    if ((var) == NULL) return -1; \
} while (0)
    INTERN(K_globals, "globals");
    INTERN(K_statementCount, "statementCount");
    INTERN(K_statements, "statements");
    INTERN(K_maxStatements, "maxStatements");
    INTERN(K_system, "system");
    INTERN(K_enabled, "enabled");
    INTERN(K_scripts, "scripts");
    INTERN(K_scriptName, "scriptName");
    INTERN(K_lineNumber, "lineNumber");
    INTERN(K_script, "script");
    INTERN(K_covered, "covered");
    INTERN(K_statement, "statement");
    INTERN(K_count, "count");
    INTERN(K_expr, "expr");
    INTERN(K_name, "name");
    INTERN(K_jump, "jump");
    INTERN(K_label, "label");
    INTERN(K_returnK, "return");
    INTERN(K_functionK, "function");
    INTERN(K_include, "include");
    INTERN(K_includes, "includes");
    INTERN(K_url, "url");
    INTERN(K_systemPrefix, "systemPrefix");
    INTERN(K_fetchFn, "fetchFn");
    INTERN(K_logFn, "logFn");
    INTERN(K_urlFn, "urlFn");
    INTERN(K_debug, "debug");
    INTERN(K_number, "number");
    INTERN(K_string, "string");
    INTERN(K_variable, "variable");
    INTERN(K_args, "args");
    INTERN(K_binary, "binary");
    INTERN(K_op, "op");
    INTERN(K_left, "left");
    INTERN(K_right, "right");
    INTERN(K_unary, "unary");
    INTERN(K_group, "group");
    INTERN(K_lastArgArray, "lastArgArray");
    INTERN(K_null, "null");
    INTERN(K_false, "false");
    INTERN(K_true, "true");
    INTERN(K_ifK, "if");
    INTERN(K_milliseconds, "milliseconds");
    INTERN(K_return_value, "return_value");
#undef INTERN
    return 0;
}

static int
import_symbol(PyObject *module, const char *attr, PyObject **out)
{
    PyObject *sym = PyObject_GetAttrString(module, attr);
    if (sym == NULL) return -1;
    *out = sym;
    return 0;
}

PyMODINIT_FUNC
PyInit_runtime_c(void)
{
    if (PyType_Ready(&ScriptFuncType) < 0) return NULL;

    PyObject *m = PyModule_Create(&RuntimeC_module);
    if (m == NULL) return NULL;

    if (intern_keys() < 0) { Py_DECREF(m); return NULL; }

    G_PY_ZERO = PyLong_FromLong(0);
    if (G_PY_ZERO == NULL) { Py_DECREF(m); return NULL; }
    G_PY_ONE = PyLong_FromLong(1);
    if (G_PY_ONE == NULL) { Py_DECREF(m); return NULL; }
    G_DEFAULT_MAX_STATEMENTS = PyFloat_FromDouble(1e9);
    if (G_DEFAULT_MAX_STATEMENTS == NULL) { Py_DECREF(m); return NULL; }
    G_COVERAGE_NAME = PyUnicode_InternFromString("__barescriptCoverage");
    if (G_COVERAGE_NAME == NULL) { Py_DECREF(m); return NULL; }
    G_INCLUDES_NAME = PyUnicode_InternFromString("__barescriptIncludes");
    if (G_INCLUDES_NAME == NULL) { Py_DECREF(m); return NULL; }

    // bare_script.runtime — BareScriptRuntimeError
    PyObject *mod_runtime = PyImport_ImportModule("bare_script.runtime");
    if (mod_runtime == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_runtime, "BareScriptRuntimeError", &G_BareScriptRuntimeError) < 0) {
        Py_DECREF(mod_runtime); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_runtime);

    // bare_script.library — EXPRESSION_FUNCTIONS, SCRIPT_FUNCTIONS
    PyObject *mod_library = PyImport_ImportModule("bare_script.library");
    if (mod_library == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_library, "EXPRESSION_FUNCTIONS", &G_EXPRESSION_FUNCTIONS) < 0 ||
        import_symbol(mod_library, "SCRIPT_FUNCTIONS", &G_SCRIPT_FUNCTIONS) < 0) {
        Py_DECREF(mod_library); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_library);

    // bare_script.model — lint_script
    PyObject *mod_model = PyImport_ImportModule("bare_script.model");
    if (mod_model == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_model, "lint_script", &G_lint_script) < 0) {
        Py_DECREF(mod_model); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_model);

    // bare_script.options — url_file_relative
    PyObject *mod_options = PyImport_ImportModule("bare_script.options");
    if (mod_options == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_options, "url_file_relative", &G_url_file_relative) < 0) {
        Py_DECREF(mod_options); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_options);

    // bare_script.parser — parse_script
    PyObject *mod_parser = PyImport_ImportModule("bare_script.parser");
    if (mod_parser == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_parser, "parse_script", &G_parse_script) < 0) {
        Py_DECREF(mod_parser); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_parser);

    // bare_script.value — value_boolean, value_compare, value_normalize_datetime,
    //   value_round_number, value_string, ValueArgsError
    PyObject *mod_value = PyImport_ImportModule("bare_script.value");
    if (mod_value == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_value, "value_boolean", &G_value_boolean) < 0 ||
        import_symbol(mod_value, "value_compare", &G_value_compare) < 0 ||
        import_symbol(mod_value, "value_normalize_datetime", &G_value_normalize_datetime) < 0 ||
        import_symbol(mod_value, "value_round_number", &G_value_round_number) < 0 ||
        import_symbol(mod_value, "value_string", &G_value_string) < 0 ||
        import_symbol(mod_value, "ValueArgsError", &G_ValueArgsError) < 0) {
        Py_DECREF(mod_value); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_value);

    // functools.partial
    PyObject *mod_functools = PyImport_ImportModule("functools");
    if (mod_functools == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_functools, "partial", &G_functools_partial) < 0) {
        Py_DECREF(mod_functools); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_functools);

    // datetime.date, datetime.timedelta
    PyObject *mod_datetime = PyImport_ImportModule("datetime");
    if (mod_datetime == NULL) { Py_DECREF(m); return NULL; }
    if (import_symbol(mod_datetime, "date", &G_datetime_date) < 0 ||
        import_symbol(mod_datetime, "timedelta", &G_datetime_timedelta) < 0) {
        Py_DECREF(mod_datetime); Py_DECREF(m); return NULL;
    }
    Py_DECREF(mod_datetime);

    Py_INCREF(&ScriptFuncType);
    if (PyModule_AddObject(m, "_ScriptFunc", (PyObject *)&ScriptFuncType) < 0) {
        Py_DECREF(&ScriptFuncType); Py_DECREF(m); return NULL;
    }

    return m;
}
