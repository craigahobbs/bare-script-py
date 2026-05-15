/* Licensed under the MIT License
 * https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE
 *
 * BareScript runtime - C extension (mirror of runtime.py)
 *
 * ---------------------------------------------------------------------------
 * History
 * ---------------------------------------------------------------------------
 * This file was rebuilt from scratch as a faithful C port of the pure-Python
 * runtime in runtime.py, then iteratively optimized against the Mandelbrot
 * perf benchmark (perf/test.bare). The baseline of the clean port was
 * ~4878 ms for `make perf` and ~1570 ms for `make test-include`.
 *
 * Optimizations applied, in order:
 *   1. Single-pass statement dispatch in execute_script_helper via
 *      PyDict_Next + identity-or-equal key match (replaces a cascade of
 *      PyUnicode_Compare and a separate first-key extraction).
 *   2. Single-pass expression dispatch in evaluate_expression_internal,
 *      similarly using PyDict_Next + identity match.
 *   3. Op-id integer dispatch: resolve op string to an integer once via
 *      pointer identity (with PyUnicode_Compare fallback) and switch on it
 *      instead of cascading PyUnicode_Compare calls.
 *   4. PyFloat+PyFloat fast path: inline + - * / and comparisons in C
 *      against doubles extracted via PyFloat_AS_DOUBLE, allocating one
 *      PyFloat for the result instead of going through PyNumber_*.
 *   5. Shared C-side statement counter: rather than PyDict_SetItem on
 *      options['statementCount'] per statement, the topmost
 *      execute_script_helper owns a Py_ssize_t pointed at by a static
 *      g_active_counter (GIL-protected). Nested calls share it. The value
 *      is flushed back to the options dict only at function exit / error.
 *   6. Thread globals_ through evaluate_expression_internal so the
 *      options['globals'] lookup happens once at the top instead of on
 *      every recursive call.
 *   7. Length-prefilter the null/true/false keyword checks and the "if"
 *      builtin name check, so non-keyword names skip the PyUnicode_Compare
 *      cascade.
 *   8. Batch op/left/right (and function name/args) via a single
 *      PyDict_Next iteration instead of three separate PyDict_GetItem
 *      lookups.
 *   9. ScriptFunc fast call path: when the resolved function value is our
 *      own ScriptFuncObject, invoke script_function_call directly to skip
 *      the tp_call tuple-build round trip.
 *  10. Inline leaf evaluation: in the binary expression handler, in
 *      function argument evaluation, and in expr-statement evaluation,
 *      peek the child expression's first key and handle variable/number/
 *      string cases inline (via lookup_variable) instead of recursing
 *      back into evaluate_expression_internal.
 *
 * After all optimizations: perf ~2099 ms (-57% from C baseline, -81% vs
 * pure-Python's ~11074 ms). test-include ~1259 ms (-20% from C baseline,
 * -55% vs pure-Python's ~2783 ms).
 *
 * Optimizations explored and rejected:
 *  - PyObject_Vectorcall for non-ScriptFunc calls: slightly slower than
 *    PyObject_CallFunctionObjArgs in this benchmark.
 *  - PyDict_GetItem (no error variant) in dict_getitem_borrow: measurably
 *    slower than PyDict_GetItemWithError on CPython 3.14.
 *  - Caching resolved function values in the AST: would break dynamic
 *    re-binding semantics tested by the suite.
 *
 * Note: coverage recording (record_statement_coverage) is intentionally
 * unoptimized — debug-only path, see CLAUDE.md.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <datetime.h>
#include <stdarg.h>
#include <string.h>


/* =====================================================================
 * Cached references and interned strings
 * ===================================================================== */

static PyObject *g_library_mod;
static PyObject *g_value_mod;
static PyObject *g_options_mod;
static PyObject *g_parser_mod;
static PyObject *g_model_mod;
static PyObject *g_runtime_mod;
static PyObject *g_functools_partial;
static PyObject *g_datetime_timedelta;
static PyObject *g_datetime_date_class;
static PyObject *g_datetime_datetime_class;

static PyObject *g_expression_functions;
static PyObject *g_script_functions;
static PyObject *g_runtime_error_class;
static PyObject *g_value_args_error_class;
static PyObject *g_value_boolean;
static PyObject *g_value_compare;
static PyObject *g_value_normalize_datetime;
static PyObject *g_value_round_number;
static PyObject *g_value_string;
static PyObject *g_parse_script;
static PyObject *g_lint_script;
static PyObject *g_url_file_relative;

/* Default max statements: 1e9 as float (matches runtime.py constant) */
static PyObject *g_default_max_statements;

/* Active C-side statement counter (GIL-protected). When non-NULL, execute_script_helper
 * uses this shared counter across nested calls instead of updating options dict
 * per statement. Topmost execute_script_helper owns the storage. */
static Py_ssize_t *g_active_counter;

/* Interned strings */
static PyObject *K_statements;
static PyObject *K_globals;
static PyObject *K_statementCount;
static PyObject *K_maxStatements;
static PyObject *K_expr;
static PyObject *K_jump;
static PyObject *K_return_;          /* "return" */
static PyObject *K_label;
static PyObject *K_name;
static PyObject *K_args;
static PyObject *K_left;
static PyObject *K_right;
static PyObject *K_op;
static PyObject *K_unary;
static PyObject *K_binary;
static PyObject *K_group;
static PyObject *K_function;
static PyObject *K_number;
static PyObject *K_string;
static PyObject *K_variable;
static PyObject *K_include;
static PyObject *K_includes;
static PyObject *K_url;
static PyObject *K_system;
static PyObject *K_systemPrefix;
static PyObject *K_fetchFn;
static PyObject *K_logFn;
static PyObject *K_urlFn;
static PyObject *K_scriptName;
static PyObject *K_lineNumber;
static PyObject *K_scripts;
static PyObject *K_covered;
static PyObject *K_statement;
static PyObject *K_count;
static PyObject *K_enabled;
static PyObject *K_lastArgArray;
static PyObject *K_debug;
static PyObject *K_return_value_attr; /* "return_value" attribute on ValueArgsError */

static PyObject *K_coverage_global_name; /* "__barescriptCoverage" */
static PyObject *K_includes_global_name; /* "__barescriptIncludes" */
static PyObject *K_if_name;              /* "if" */

/* String values for operators - cached for fast compare */
static PyObject *K_op_amp_amp;
static PyObject *K_op_pipe_pipe;
static PyObject *K_op_plus;
static PyObject *K_op_minus;
static PyObject *K_op_star;
static PyObject *K_op_slash;
static PyObject *K_op_eq;
static PyObject *K_op_ne;
static PyObject *K_op_le;
static PyObject *K_op_lt;
static PyObject *K_op_ge;
static PyObject *K_op_gt;
static PyObject *K_op_pct;
static PyObject *K_op_star_star;
static PyObject *K_op_amp;
static PyObject *K_op_pipe;
static PyObject *K_op_caret;
static PyObject *K_op_lshift;
static PyObject *K_op_rshift;
static PyObject *K_op_bang;
static PyObject *K_op_neg;
static PyObject *K_op_tilde;

/* String values for variable keywords */
static PyObject *K_var_null;
static PyObject *K_var_true;
static PyObject *K_var_false;


/* =====================================================================
 * Forward declarations
 * ===================================================================== */

static PyObject *evaluate_expression_internal(
    PyObject *expr, PyObject *options, PyObject *globals_, PyObject *locals_, int builtins,
    PyObject *script, PyObject *statement);

static PyObject *execute_script_helper(
    PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_);

static PyObject *script_function_call(
    PyObject *script, PyObject *function, PyObject *args, PyObject *options);

static int record_statement_coverage(
    PyObject *script, PyObject *statement, PyObject *statement_key, PyObject *coverage_global);


/* =====================================================================
 * Small helpers
 * ===================================================================== */

/* Borrowed reference dict lookup, no exception on missing key. */
static inline PyObject *
dict_getitem_borrow(PyObject *d, PyObject *key)
{
    if (!d || !PyDict_Check(d)) return NULL;
    return PyDict_GetItemWithError(d, key);
}

/* Raise BareScriptRuntimeError(script, statement, msg). Steals nothing. */
static void
raise_runtime_error(PyObject *script, PyObject *statement, PyObject *message)
{
    PyObject *s = script ? script : Py_None;
    PyObject *st = statement ? statement : Py_None;
    PyObject *err = PyObject_CallFunctionObjArgs(g_runtime_error_class, s, st, message, NULL);
    if (err) {
        PyErr_SetObject(g_runtime_error_class, err);
        Py_DECREF(err);
    }
}

static void
raise_runtime_error_format(PyObject *script, PyObject *statement, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    PyObject *message = PyUnicode_FromFormatV(fmt, ap);
    va_end(ap);
    if (!message) return;
    raise_runtime_error(script, statement, message);
    Py_DECREF(message);
}

/* Inline value_boolean — mirrors value.py value_boolean */
static int
c_value_boolean(PyObject *value)
{
    if (value == Py_None) return 0;
    if (value == Py_True) return 1;
    if (value == Py_False) return 0;
    PyTypeObject *t = Py_TYPE(value);
    if (t == &PyUnicode_Type) return PyUnicode_GET_LENGTH(value) != 0;
    if (t == &PyLong_Type) {
        int r = PyObject_IsTrue(value);
        return r;
    }
    if (t == &PyFloat_Type) return PyFloat_AS_DOUBLE(value) != 0.0;
    if (t == &PyList_Type) return PyList_GET_SIZE(value) != 0;
    /* datetime, dict, regex, function -> truthy unless None */
    return 1;
}

/* Is value a plain int or float (excluding bool)? */
static inline int
is_int_or_float(PyObject *v)
{
    PyTypeObject *t = Py_TYPE(v);
    return t == &PyLong_Type || t == &PyFloat_Type;
}

/* Is value a datetime.date/datetime.datetime (any subclass)? */
static inline int
is_datetime_like(PyObject *v)
{
    return PyDate_Check(v);
}

/* Call value_compare(left, right) -> int (-1/0/1). Returns INT_MIN on error. */
static int
call_value_compare(PyObject *left, PyObject *right)
{
    PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare, left, right, NULL);
    if (!r) return INT_MIN;
    long v = PyLong_AsLong(r);
    Py_DECREF(r);
    if (v == -1 && PyErr_Occurred()) return INT_MIN;
    return (int)v;
}

/* Call value.value_normalize_datetime; new reference */
static inline PyObject *
call_normalize_dt(PyObject *v)
{
    return PyObject_CallFunctionObjArgs(g_value_normalize_datetime, v, NULL);
}

/* Build a datetime.timedelta(milliseconds=x) */
static PyObject *
make_timedelta_ms(PyObject *ms_value)
{
    PyObject *args = PyTuple_New(0);
    if (!args) return NULL;
    PyObject *kwargs = PyDict_New();
    if (!kwargs) { Py_DECREF(args); return NULL; }
    if (PyDict_SetItemString(kwargs, "milliseconds", ms_value) < 0) {
        Py_DECREF(args); Py_DECREF(kwargs);
        return NULL;
    }
    PyObject *result = PyObject_Call(g_datetime_timedelta, args, kwargs);
    Py_DECREF(args);
    Py_DECREF(kwargs);
    return result;
}


/* =====================================================================
 * Script-defined function callable (C version of _script_function)
 *
 * Wraps (script, function) and is callable with (args, options).
 * ===================================================================== */

typedef struct {
    PyObject_HEAD
    PyObject *script;
    PyObject *function;
} ScriptFuncObject;

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

static void
ScriptFunc_dealloc(ScriptFuncObject *self)
{
    PyObject_GC_UnTrack(self);
    ScriptFunc_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
ScriptFunc_call(ScriptFuncObject *self, PyObject *args, PyObject *kwargs)
{
    PyObject *func_args = NULL, *options = NULL;
    if (!PyArg_ParseTuple(args, "OO", &func_args, &options)) return NULL;
    return script_function_call(self->script, self->function, func_args, options);
}

static PyTypeObject ScriptFuncType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bare_script.runtime_c._ScriptFunction",
    .tp_basicsize = sizeof(ScriptFuncObject),
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_dealloc = (destructor)ScriptFunc_dealloc,
    .tp_traverse = (traverseproc)ScriptFunc_traverse,
    .tp_clear = (inquiry)ScriptFunc_clear,
    .tp_call = (ternaryfunc)ScriptFunc_call,
};

static PyObject *
new_script_function(PyObject *script, PyObject *function)
{
    ScriptFuncObject *obj = PyObject_GC_New(ScriptFuncObject, &ScriptFuncType);
    if (!obj) return NULL;
    Py_INCREF(script);
    Py_INCREF(function);
    obj->script = script;
    obj->function = function;
    PyObject_GC_Track(obj);
    return (PyObject *)obj;
}


/* =====================================================================
 * script_function_call - mirrors _script_function in runtime.py
 * ===================================================================== */

static PyObject *
script_function_call(PyObject *script, PyObject *function, PyObject *args, PyObject *options)
{
    PyObject *func_locals = PyDict_New();
    if (!func_locals) return NULL;

    PyObject *func_args = dict_getitem_borrow(function, K_args);
    if (PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }

    if (func_args != NULL) {
        if (!PyList_Check(func_args)) {
            Py_DECREF(func_locals);
            PyErr_SetString(PyExc_TypeError, "function 'args' must be a list");
            return NULL;
        }
        Py_ssize_t args_length = PyObject_Size(args);
        if (args_length < 0) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t func_args_length = PyList_GET_SIZE(func_args);

        PyObject *last_arg_array = dict_getitem_borrow(function, K_lastArgArray);
        if (PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
        int has_last_arg_array = (last_arg_array != NULL && PyObject_IsTrue(last_arg_array) == 1);

        if (has_last_arg_array) {
            Py_ssize_t ix_arg_last = func_args_length - 1;
            for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
                PyObject *arg_name = PyList_GET_ITEM(func_args, ix);
                PyObject *val = NULL;
                int needs_decref = 0;
                if (ix < args_length) {
                    if (ix == ix_arg_last) {
                        /* args[ix:] */
                        if (PyList_Check(args)) {
                            val = PyList_GetSlice(args, ix, args_length);
                        } else {
                            val = PySequence_GetSlice(args, ix, args_length);
                        }
                        if (!val) { Py_DECREF(func_locals); return NULL; }
                        needs_decref = 1;
                    } else {
                        val = PySequence_GetItem(args, ix);
                        if (!val) { Py_DECREF(func_locals); return NULL; }
                        needs_decref = 1;
                    }
                } else {
                    if (ix == ix_arg_last) {
                        val = PyList_New(0);
                        if (!val) { Py_DECREF(func_locals); return NULL; }
                        needs_decref = 1;
                    } else {
                        val = Py_None;
                    }
                }
                int rc = PyDict_SetItem(func_locals, arg_name, val);
                if (needs_decref) Py_DECREF(val);
                if (rc < 0) { Py_DECREF(func_locals); return NULL; }
            }
        } else {
            for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
                PyObject *arg_name = PyList_GET_ITEM(func_args, ix);
                PyObject *val;
                int needs_decref = 0;
                if (ix < args_length) {
                    val = PySequence_GetItem(args, ix);
                    if (!val) { Py_DECREF(func_locals); return NULL; }
                    needs_decref = 1;
                } else {
                    val = Py_None;
                }
                int rc = PyDict_SetItem(func_locals, arg_name, val);
                if (needs_decref) Py_DECREF(val);
                if (rc < 0) { Py_DECREF(func_locals); return NULL; }
            }
        }
    }

    PyObject *statements = dict_getitem_borrow(function, K_statements);
    if (!statements) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
        Py_DECREF(func_locals);
        return NULL;
    }
    PyObject *result = execute_script_helper(script, statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}


/* =====================================================================
 * execute_script_helper - mirrors _execute_script_helper
 * ===================================================================== */

static int
record_statement_coverage(PyObject *script, PyObject *statement, PyObject *statement_key, PyObject *coverage_global)
{
    /* Get the script name and statement line number */
    PyObject *script_name = dict_getitem_borrow(script, K_scriptName);
    if (PyErr_Occurred()) return -1;
    PyObject *stmt_body = dict_getitem_borrow(statement, statement_key);
    if (PyErr_Occurred()) return -1;
    if (!stmt_body || !PyDict_Check(stmt_body)) return 0;
    PyObject *lineno = dict_getitem_borrow(stmt_body, K_lineNumber);
    if (PyErr_Occurred()) return -1;
    if (script_name == NULL || lineno == NULL) return 0;

    /* scripts dict */
    PyObject *scripts = dict_getitem_borrow(coverage_global, K_scripts);
    if (PyErr_Occurred()) return -1;
    if (scripts == NULL) {
        scripts = PyDict_New();
        if (!scripts) return -1;
        if (PyDict_SetItem(coverage_global, K_scripts, scripts) < 0) { Py_DECREF(scripts); return -1; }
        Py_DECREF(scripts);
        scripts = PyDict_GetItemWithError(coverage_global, K_scripts);
        if (!scripts) return -1;
    }
    PyObject *script_coverage = dict_getitem_borrow(scripts, script_name);
    if (PyErr_Occurred()) return -1;
    if (script_coverage == NULL) {
        script_coverage = PyDict_New();
        if (!script_coverage) return -1;
        if (PyDict_SetItemString(script_coverage, "script", script) < 0) {
            Py_DECREF(script_coverage); return -1;
        }
        PyObject *covered_new = PyDict_New();
        if (!covered_new) { Py_DECREF(script_coverage); return -1; }
        if (PyDict_SetItem(script_coverage, K_covered, covered_new) < 0) {
            Py_DECREF(covered_new); Py_DECREF(script_coverage); return -1;
        }
        Py_DECREF(covered_new);
        if (PyDict_SetItem(scripts, script_name, script_coverage) < 0) {
            Py_DECREF(script_coverage); return -1;
        }
        Py_DECREF(script_coverage);
        script_coverage = dict_getitem_borrow(scripts, script_name);
        if (!script_coverage) return -1;
    }

    PyObject *lineno_str = PyObject_Str(lineno);
    if (!lineno_str) return -1;
    PyObject *covered_statements = dict_getitem_borrow(script_coverage, K_covered);
    if (PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
    PyObject *covered_statement = dict_getitem_borrow(covered_statements, lineno_str);
    if (PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
    if (covered_statement == NULL) {
        covered_statement = PyDict_New();
        if (!covered_statement) { Py_DECREF(lineno_str); return -1; }
        if (PyDict_SetItem(covered_statement, K_statement, statement) < 0) {
            Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1;
        }
        PyObject *zero = PyLong_FromLong(0);
        if (!zero) { Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1; }
        if (PyDict_SetItem(covered_statement, K_count, zero) < 0) {
            Py_DECREF(zero); Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(zero);
        if (PyDict_SetItem(covered_statements, lineno_str, covered_statement) < 0) {
            Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(covered_statement);
        covered_statement = dict_getitem_borrow(covered_statements, lineno_str);
    }
    Py_DECREF(lineno_str);
    if (!covered_statement) return -1;

    PyObject *cur_count = dict_getitem_borrow(covered_statement, K_count);
    if (PyErr_Occurred()) return -1;
    if (!cur_count) {
        PyObject *one = PyLong_FromLong(1);
        if (!one) return -1;
        if (PyDict_SetItem(covered_statement, K_count, one) < 0) { Py_DECREF(one); return -1; }
        Py_DECREF(one);
    } else {
        PyObject *one = PyLong_FromLong(1);
        if (!one) return -1;
        PyObject *new_count = PyNumber_Add(cur_count, one);
        Py_DECREF(one);
        if (!new_count) return -1;
        if (PyDict_SetItem(covered_statement, K_count, new_count) < 0) { Py_DECREF(new_count); return -1; }
        Py_DECREF(new_count);
    }
    return 0;
}


/* Identity-or-equal compare. K is interned; key may or may not be. */
static inline int
key_match(PyObject *key, PyObject *K)
{
    if (key == K) return 1;
    if (!PyUnicode_Check(key)) return 0;
    return PyUnicode_Compare(key, K) == 0;
}

/* Binary/unary op id constants */
#define OP_PLUS       0
#define OP_MINUS      1
#define OP_STAR       2
#define OP_SLASH      3
#define OP_EQ         4
#define OP_NE         5
#define OP_LE         6
#define OP_LT         7
#define OP_GE         8
#define OP_GT         9
#define OP_PCT       10
#define OP_STAR_STAR 11
#define OP_AMP       12
#define OP_PIPE      13
#define OP_CARET     14
#define OP_LSHIFT    15
#define OP_RSHIFT    16
#define OP_AND_AND   17
#define OP_OR_OR     18
#define OP_BANG      19
#define OP_TILDE     20
#define OP_UNKNOWN   -1

static int
op_to_id(PyObject *op)
{
    if (op == K_op_plus) return OP_PLUS;
    if (op == K_op_minus) return OP_MINUS;
    if (op == K_op_star) return OP_STAR;
    if (op == K_op_slash) return OP_SLASH;
    if (op == K_op_lt) return OP_LT;
    if (op == K_op_le) return OP_LE;
    if (op == K_op_gt) return OP_GT;
    if (op == K_op_ge) return OP_GE;
    if (op == K_op_eq) return OP_EQ;
    if (op == K_op_ne) return OP_NE;
    if (op == K_op_pct) return OP_PCT;
    if (op == K_op_star_star) return OP_STAR_STAR;
    if (op == K_op_amp_amp) return OP_AND_AND;
    if (op == K_op_pipe_pipe) return OP_OR_OR;
    if (op == K_op_amp) return OP_AMP;
    if (op == K_op_pipe) return OP_PIPE;
    if (op == K_op_caret) return OP_CARET;
    if (op == K_op_lshift) return OP_LSHIFT;
    if (op == K_op_rshift) return OP_RSHIFT;
    if (op == K_op_bang) return OP_BANG;
    if (op == K_op_tilde) return OP_TILDE;
    /* Fallback for non-interned strings */
    if (!PyUnicode_Check(op)) return OP_UNKNOWN;
    if (PyUnicode_Compare(op, K_op_plus) == 0) return OP_PLUS;
    if (PyUnicode_Compare(op, K_op_minus) == 0) return OP_MINUS;
    if (PyUnicode_Compare(op, K_op_star) == 0) return OP_STAR;
    if (PyUnicode_Compare(op, K_op_slash) == 0) return OP_SLASH;
    if (PyUnicode_Compare(op, K_op_lt) == 0) return OP_LT;
    if (PyUnicode_Compare(op, K_op_le) == 0) return OP_LE;
    if (PyUnicode_Compare(op, K_op_gt) == 0) return OP_GT;
    if (PyUnicode_Compare(op, K_op_ge) == 0) return OP_GE;
    if (PyUnicode_Compare(op, K_op_eq) == 0) return OP_EQ;
    if (PyUnicode_Compare(op, K_op_ne) == 0) return OP_NE;
    if (PyUnicode_Compare(op, K_op_pct) == 0) return OP_PCT;
    if (PyUnicode_Compare(op, K_op_star_star) == 0) return OP_STAR_STAR;
    if (PyUnicode_Compare(op, K_op_amp_amp) == 0) return OP_AND_AND;
    if (PyUnicode_Compare(op, K_op_pipe_pipe) == 0) return OP_OR_OR;
    if (PyUnicode_Compare(op, K_op_amp) == 0) return OP_AMP;
    if (PyUnicode_Compare(op, K_op_pipe) == 0) return OP_PIPE;
    if (PyUnicode_Compare(op, K_op_caret) == 0) return OP_CARET;
    if (PyUnicode_Compare(op, K_op_lshift) == 0) return OP_LSHIFT;
    if (PyUnicode_Compare(op, K_op_rshift) == 0) return OP_RSHIFT;
    if (PyUnicode_Compare(op, K_op_bang) == 0) return OP_BANG;
    if (PyUnicode_Compare(op, K_op_tilde) == 0) return OP_TILDE;
    return OP_UNKNOWN;
}

/* Peek the first (key, value) entry of a dict. Borrowed refs.
 * Returns 1 on success, 0 if empty/non-dict. */
static inline int
dict_peek1(PyObject *d, PyObject **outk, PyObject **outv)
{
    Py_ssize_t pos = 0;
    return PyDict_Next(d, &pos, outk, outv);
}

/* Inline-fast variable lookup (mirrors variable branch of evaluate_expression).
 * Returns new ref to value, or NULL on error (with exception set). */
static inline PyObject *
lookup_variable(PyObject *variable, PyObject *globals_, PyObject *locals_)
{
    if (PyUnicode_Check(variable)) {
        Py_ssize_t var_len = PyUnicode_GET_LENGTH(variable);
        if (var_len == 4) {
            if (variable == K_var_null || PyUnicode_Compare(variable, K_var_null) == 0) Py_RETURN_NONE;
            if (variable == K_var_true || PyUnicode_Compare(variable, K_var_true) == 0) Py_RETURN_TRUE;
        } else if (var_len == 5) {
            if (variable == K_var_false || PyUnicode_Compare(variable, K_var_false) == 0) Py_RETURN_FALSE;
        }
    }
    if (locals_ != NULL) {
        PyObject *v = PyDict_GetItemWithError(locals_, variable);
        if (v != NULL) { Py_INCREF(v); return v; }
        if (PyErr_Occurred()) return NULL;
    }
    if (globals_ != NULL) {
        PyObject *v = PyDict_GetItemWithError(globals_, variable);
        if (v != NULL) { Py_INCREF(v); return v; }
        if (PyErr_Occurred()) return NULL;
    }
    Py_RETURN_NONE;
}


static PyObject *
execute_script_helper(PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_)
{
    PyObject *globals_ = dict_getitem_borrow(options, K_globals);
    if (PyErr_Occurred()) return NULL;

    PyObject *max_statements_obj = dict_getitem_borrow(options, K_maxStatements);
    if (PyErr_Occurred()) return NULL;
    PyObject *max_statements = max_statements_obj ? max_statements_obj : g_default_max_statements;

    /* Pre-compute: is max_statements > 0?  And cap value as a double for fast compare. */
    double max_stmt_d = -1.0;
    int check_max = 0;
    if (PyFloat_Check(max_statements)) {
        max_stmt_d = PyFloat_AS_DOUBLE(max_statements);
        check_max = max_stmt_d > 0.0;
    } else if (PyLong_Check(max_statements)) {
        long mv = PyLong_AsLong(max_statements);
        if (mv == -1 && PyErr_Occurred()) { PyErr_Clear(); max_stmt_d = 1e18; check_max = 1; }
        else { max_stmt_d = (double)mv; check_max = mv > 0; }
    }

    /* options.setdefault('statementCount', 0) */
    PyObject *stmt_count_init = dict_getitem_borrow(options, K_statementCount);
    if (PyErr_Occurred()) return NULL;
    if (!stmt_count_init) {
        PyObject *zero = PyLong_FromLong(0);
        if (!zero) return NULL;
        if (PyDict_SetItem(options, K_statementCount, zero) < 0) { Py_DECREF(zero); return NULL; }
        Py_DECREF(zero);
    }

    /* Take ownership of the shared C counter at topmost invocation. */
    Py_ssize_t local_counter = 0;
    int counter_topmost = 0;
    if (g_active_counter == NULL) {
        counter_topmost = 1;
        if (stmt_count_init && PyLong_Check(stmt_count_init)) {
            local_counter = PyLong_AsSsize_t(stmt_count_init);
            if (local_counter == -1 && PyErr_Occurred()) { PyErr_Clear(); local_counter = 0; }
        }
        g_active_counter = &local_counter;
    }

    /* Coverage configuration */
    PyObject *coverage_global = NULL;
    int has_coverage = 0;
    if (globals_ && PyDict_Check(globals_)) {
        coverage_global = dict_getitem_borrow(globals_, K_coverage_global_name);
        if (PyErr_Occurred()) return NULL;
        if (coverage_global && PyDict_Check(coverage_global)) {
            PyObject *enabled = dict_getitem_borrow(coverage_global, K_enabled);
            if (PyErr_Occurred()) return NULL;
            int en = enabled && PyObject_IsTrue(enabled);
            if (en) {
                PyObject *sys = dict_getitem_borrow(script, K_system);
                if (PyErr_Occurred()) return NULL;
                int sy = sys && PyObject_IsTrue(sys);
                if (!sy) has_coverage = 1;
            }
        } else {
            coverage_global = NULL;
        }
    }

    /* Iterate statements */
    PyObject *label_indexes = NULL;
    if (!PyList_Check(statements)) {
        PyErr_SetString(PyExc_TypeError, "statements must be a list");
        return NULL;
    }
    Py_ssize_t statements_length = PyList_GET_SIZE(statements);

    Py_ssize_t ix_statement = 0;
    while (ix_statement < statements_length) {
        PyObject *statement = PyList_GET_ITEM(statements, ix_statement);

        /* Increment shared C counter */
        Py_ssize_t new_val = ++(*g_active_counter);
        if (check_max && (double)new_val > max_stmt_d) {
            PyObject *ms_str = PyObject_Str(max_statements);
            if (ms_str) {
                raise_runtime_error_format(script, statement,
                    "Exceeded maximum script statements (%U)", ms_str);
                Py_DECREF(ms_str);
            }
            goto error;
        }

        /* Peek first (key, body) of statement */
        PyObject *stmt_key, *stmt_body;
        if (!dict_peek1(statement, &stmt_key, &stmt_body)) {
            ix_statement++;
            continue;
        }

        /* Record coverage if needed */
        if (has_coverage) {
            if (record_statement_coverage(script, statement, stmt_key, coverage_global) < 0) {
                goto error;
            }
        }

        /* Identity-first dispatch */
        if (key_match(stmt_key, K_expr)) {
            /* stmt_body is the expr-statement dict */
            PyObject *inner = dict_getitem_borrow(stmt_body, K_expr);
            if (!inner) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "expr"); goto error; }
            PyObject *expr_value;
            PyObject *ik, *iv;
            if (PyDict_Check(inner) && dict_peek1(inner, &ik, &iv)) {
                if (ik == K_variable) expr_value = lookup_variable(iv, globals_, locals_);
                else if (ik == K_number || ik == K_string) { Py_INCREF(iv); expr_value = iv; }
                else expr_value = evaluate_expression_internal(inner, options, globals_, locals_, 0, script, statement);
            } else {
                expr_value = evaluate_expression_internal(inner, options, globals_, locals_, 0, script, statement);
            }
            if (!expr_value) goto error;
            PyObject *expr_name = dict_getitem_borrow(stmt_body, K_name);
            if (PyErr_Occurred()) { Py_DECREF(expr_value); goto error; }
            if (expr_name != NULL) {
                PyObject *target = (locals_ != NULL) ? locals_ : globals_;
                if (target && PyDict_SetItem(target, expr_name, expr_value) < 0) {
                    Py_DECREF(expr_value); goto error;
                }
            }
            Py_DECREF(expr_value);
        } else if (key_match(stmt_key, K_jump)) {
            int do_jump = 1;
            PyObject *jexpr = dict_getitem_borrow(stmt_body, K_expr);
            if (PyErr_Occurred()) goto error;
            if (jexpr != NULL) {
                PyObject *cond = evaluate_expression_internal(jexpr, options, globals_, locals_, 0, script, statement);
                if (!cond) goto error;
                do_jump = c_value_boolean(cond);
                Py_DECREF(cond);
                if (PyErr_Occurred()) goto error;
            }
            if (do_jump) {
                PyObject *jump_label = dict_getitem_borrow(stmt_body, K_label);
                if (!jump_label) {
                    if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "label");
                    goto error;
                }
                Py_ssize_t target_ix = -1;
                if (label_indexes != NULL) {
                    PyObject *cached = PyDict_GetItemWithError(label_indexes, jump_label);
                    if (PyErr_Occurred()) goto error;
                    if (cached) {
                        target_ix = PyLong_AsSsize_t(cached);
                        if (target_ix == -1 && PyErr_Occurred()) goto error;
                    }
                }
                if (target_ix == -1) {
                    /* Linear search */
                    for (Py_ssize_t ii = 0; ii < statements_length; ii++) {
                        PyObject *st = PyList_GET_ITEM(statements, ii);
                        PyObject *lbl = dict_getitem_borrow(st, K_label);
                        if (PyErr_Occurred()) goto error;
                        if (lbl != NULL) {
                            PyObject *lblname = dict_getitem_borrow(lbl, K_name);
                            if (PyErr_Occurred()) goto error;
                            if (lblname && PyUnicode_Check(lblname) && PyUnicode_Check(jump_label) &&
                                PyUnicode_Compare(lblname, jump_label) == 0) {
                                target_ix = ii;
                                break;
                            }
                        }
                    }
                    if (target_ix == -1) {
                        raise_runtime_error_format(script, statement,
                            "Unknown jump label \"%U\"", jump_label);
                        goto error;
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (!label_indexes) goto error;
                    }
                    PyObject *ix_obj = PyLong_FromSsize_t(target_ix);
                    if (!ix_obj) goto error;
                    if (PyDict_SetItem(label_indexes, jump_label, ix_obj) < 0) {
                        Py_DECREF(ix_obj); goto error;
                    }
                    Py_DECREF(ix_obj);
                }
                ix_statement = target_ix;

                if (has_coverage) {
                    PyObject *label_statement = PyList_GET_ITEM(statements, ix_statement);
                    PyObject *lkey, *lbody;
                    if (dict_peek1(label_statement, &lkey, &lbody)) {
                        if (record_statement_coverage(script, label_statement, lkey, coverage_global) < 0) goto error;
                    }
                }
            }
        } else if (key_match(stmt_key, K_return_)) {
            PyObject *rexpr = dict_getitem_borrow(stmt_body, K_expr);
            if (PyErr_Occurred()) goto error;
            Py_XDECREF(label_indexes);
            PyObject *retval;
            if (rexpr != NULL) {
                retval = evaluate_expression_internal(rexpr, options, globals_, locals_, 0, script, statement);
            } else {
                Py_INCREF(Py_None);
                retval = Py_None;
            }
            if (counter_topmost) {
                PyObject *cnt = PyLong_FromSsize_t(*g_active_counter);
                if (cnt) {
                    PyDict_SetItem(options, K_statementCount, cnt);
                    Py_DECREF(cnt);
                }
                g_active_counter = NULL;
            }
            return retval;
        } else if (key_match(stmt_key, K_function)) {
            PyObject *fname = dict_getitem_borrow(stmt_body, K_name);
            if (!fname) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "name"); goto error; }
            PyObject *sf = new_script_function(script, stmt_body);
            if (!sf) goto error;
            if (globals_ == NULL) {
                Py_DECREF(sf);
                PyErr_SetString(PyExc_RuntimeError, "no globals");
                goto error;
            }
            if (PyDict_SetItem(globals_, fname, sf) < 0) { Py_DECREF(sf); goto error; }
            Py_DECREF(sf);
        } else if (key_match(stmt_key, K_include)) {
            PyObject *includes = dict_getitem_borrow(stmt_body, K_includes);
            if (!includes) { if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "includes"); goto error; }
            PyObject *system_prefix = dict_getitem_borrow(options, K_systemPrefix);
            if (PyErr_Occurred()) goto error;
            PyObject *fetch_fn = dict_getitem_borrow(options, K_fetchFn);
            if (PyErr_Occurred()) goto error;
            PyObject *log_fn = dict_getitem_borrow(options, K_logFn);
            if (PyErr_Occurred()) goto error;
            PyObject *url_fn = dict_getitem_borrow(options, K_urlFn);
            if (PyErr_Occurred()) goto error;

            Py_ssize_t inc_len = PyObject_Size(includes);
            if (inc_len < 0) goto error;
            for (Py_ssize_t ii = 0; ii < inc_len; ii++) {
                PyObject *include = PySequence_GetItem(includes, ii);
                if (!include) goto error;
                PyObject *include_url = dict_getitem_borrow(include, K_url);
                if (PyErr_Occurred()) { Py_DECREF(include); goto error; }
                if (!include_url) { Py_DECREF(include); PyErr_SetString(PyExc_KeyError, "url"); goto error; }
                Py_INCREF(include_url);

                PyObject *system_include = dict_getitem_borrow(include, K_system);
                if (PyErr_Occurred()) { Py_DECREF(include); Py_DECREF(include_url); goto error; }
                int is_sys = system_include && PyObject_IsTrue(system_include);

                /* Fixup URL */
                if (is_sys && system_prefix != NULL) {
                    PyObject *new_url = PyObject_CallFunctionObjArgs(g_url_file_relative, system_prefix, include_url, NULL);
                    Py_DECREF(include_url);
                    if (!new_url) { Py_DECREF(include); goto error; }
                    include_url = new_url;
                } else if (url_fn != NULL) {
                    PyObject *new_url = PyObject_CallFunctionObjArgs(url_fn, include_url, NULL);
                    Py_DECREF(include_url);
                    if (!new_url) { Py_DECREF(include); goto error; }
                    include_url = new_url;
                }

                /* Already included? */
                PyObject *global_includes = dict_getitem_borrow(globals_, K_includes_global_name);
                if (PyErr_Occurred()) { Py_DECREF(include); Py_DECREF(include_url); goto error; }
                if (global_includes == NULL || !PyDict_Check(global_includes)) {
                    global_includes = PyDict_New();
                    if (!global_includes) { Py_DECREF(include); Py_DECREF(include_url); goto error; }
                    if (PyDict_SetItem(globals_, K_includes_global_name, global_includes) < 0) {
                        Py_DECREF(global_includes); Py_DECREF(include); Py_DECREF(include_url); goto error;
                    }
                    Py_DECREF(global_includes);
                    global_includes = dict_getitem_borrow(globals_, K_includes_global_name);
                    if (!global_includes) { Py_DECREF(include); Py_DECREF(include_url); goto error; }
                }
                PyObject *seen = PyDict_GetItemWithError(global_includes, include_url);
                if (PyErr_Occurred()) { Py_DECREF(include); Py_DECREF(include_url); goto error; }
                if (seen && PyObject_IsTrue(seen)) {
                    Py_DECREF(include);
                    Py_DECREF(include_url);
                    continue;
                }
                if (PyDict_SetItem(global_includes, include_url, Py_True) < 0) {
                    Py_DECREF(include); Py_DECREF(include_url); goto error;
                }

                /* Fetch the URL */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *url_arg = PyDict_New();
                    if (!url_arg) { Py_DECREF(include); Py_DECREF(include_url); goto error; }
                    if (PyDict_SetItem(url_arg, K_url, include_url) < 0) {
                        Py_DECREF(url_arg); Py_DECREF(include); Py_DECREF(include_url); goto error;
                    }
                    include_text = PyObject_CallFunctionObjArgs(fetch_fn, url_arg, NULL);
                    Py_DECREF(url_arg);
                    if (!include_text) {
                        PyErr_Clear();
                        include_text = NULL;
                    }
                }
                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    raise_runtime_error_format(script, statement,
                        "Include of \"%U\" failed", include_url);
                    Py_DECREF(include); Py_DECREF(include_url); goto error;
                }

                /* Parse */
                PyObject *one_int = PyLong_FromLong(1);
                if (!one_int) { Py_DECREF(include_text); Py_DECREF(include); Py_DECREF(include_url); goto error; }
                PyObject *include_script = PyObject_CallFunctionObjArgs(g_parse_script, include_text, one_int, include_url, NULL);
                Py_DECREF(one_int);
                Py_DECREF(include_text);
                if (!include_script) {
                    Py_DECREF(include); Py_DECREF(include_url); goto error;
                }
                if (is_sys) {
                    if (PyDict_SetItem(include_script, K_system, Py_True) < 0) {
                        Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                    }
                }

                /* include_options = options.copy(); set urlFn */
                PyObject *include_options = PyDict_Copy(options);
                if (!include_options) {
                    Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, include_url, NULL);
                if (!new_url_fn) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                }
                if (PyDict_SetItem(include_options, K_urlFn, new_url_fn) < 0) {
                    Py_DECREF(new_url_fn); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                }
                Py_DECREF(new_url_fn);

                PyObject *inc_statements = dict_getitem_borrow(include_script, K_statements);
                if (!inc_statements) {
                    if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                }
                PyObject *exec_result = execute_script_helper(include_script, inc_statements, include_options, NULL);
                if (!exec_result) {
                    Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                }
                Py_DECREF(exec_result);

                /* Optional linter */
                if (log_fn != NULL) {
                    PyObject *debug_obj = dict_getitem_borrow(options, K_debug);
                    if (PyErr_Occurred()) {
                        Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                    }
                    if (debug_obj && PyObject_IsTrue(debug_obj)) {
                        PyObject *warnings = PyObject_CallFunctionObjArgs(g_lint_script, include_script, globals_, NULL);
                        if (!warnings) {
                            Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                        }
                        Py_ssize_t wlen = PyObject_Size(warnings);
                        if (wlen > 0) {
                            const char *plural = wlen > 1 ? "s" : "";
                            PyObject *header = PyUnicode_FromFormat(
                                "BareScript: Include \"%U\" static analysis... %zd warning%s:",
                                include_url, wlen, plural);
                            if (!header) {
                                Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                            }
                            PyObject *r = PyObject_CallFunctionObjArgs(log_fn, header, NULL);
                            Py_DECREF(header);
                            Py_XDECREF(r);
                            for (Py_ssize_t wi = 0; wi < wlen; wi++) {
                                PyObject *w = PySequence_GetItem(warnings, wi);
                                if (!w) {
                                    Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                                }
                                PyObject *line = PyUnicode_FromFormat("BareScript: %U", w);
                                Py_DECREF(w);
                                if (!line) {
                                    Py_DECREF(warnings); Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include); Py_DECREF(include_url); goto error;
                                }
                                PyObject *rr = PyObject_CallFunctionObjArgs(log_fn, line, NULL);
                                Py_DECREF(line);
                                Py_XDECREF(rr);
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }
                Py_DECREF(include_options);
                Py_DECREF(include_script);
                Py_DECREF(include);
                Py_DECREF(include_url);
            }
        }
        /* Otherwise: label, etc. - skip */

        ix_statement++;
        continue;

    error:
        Py_XDECREF(label_indexes);
        if (counter_topmost) {
            PyObject *cnt = PyLong_FromSsize_t(*g_active_counter);
            if (cnt) {
                /* Preserve any existing exception */
                PyObject *ex_type, *ex_value, *ex_tb;
                PyErr_Fetch(&ex_type, &ex_value, &ex_tb);
                PyDict_SetItem(options, K_statementCount, cnt);
                Py_DECREF(cnt);
                PyErr_Restore(ex_type, ex_value, ex_tb);
            }
            g_active_counter = NULL;
        }
        return NULL;
    }

    Py_XDECREF(label_indexes);
    if (counter_topmost) {
        PyObject *cnt = PyLong_FromSsize_t(*g_active_counter);
        if (cnt) {
            PyDict_SetItem(options, K_statementCount, cnt);
            Py_DECREF(cnt);
        }
        g_active_counter = NULL;
    }
    Py_RETURN_NONE;
}


/* =====================================================================
 * evaluate_expression_internal
 * ===================================================================== */

static PyObject *
evaluate_expression_internal(PyObject *expr, PyObject *options, PyObject *globals_, PyObject *locals_, int builtins,
                              PyObject *script, PyObject *statement)
{
    if (!PyDict_Check(expr)) {
        PyErr_SetString(PyExc_TypeError, "expression must be a dict");
        return NULL;
    }

    /* Single-pass dispatch on first key */
    PyObject *ekey, *eval_body;
    if (!dict_peek1(expr, &ekey, &eval_body)) Py_RETURN_NONE;

    /* Number */
    if (key_match(ekey, K_number)) { Py_INCREF(eval_body); return eval_body; }
    /* String */
    if (key_match(ekey, K_string)) { Py_INCREF(eval_body); return eval_body; }

    /* Variable */
    if (key_match(ekey, K_variable)) {
        return lookup_variable(eval_body, globals_, locals_);
    }

    /* Function */
    if (key_match(ekey, K_function)) {
        PyObject *func = eval_body;
        PyObject *func_name = NULL, *args_expr_cached = NULL;
        int has_args_key = 0;
        Py_ssize_t fpos = 0;
        PyObject *fk, *fv;
        while (PyDict_Next(func, &fpos, &fk, &fv)) {
            if (fk == K_name) func_name = fv;
            else if (fk == K_args) { args_expr_cached = fv; has_args_key = 1; }
            else if (PyUnicode_Check(fk)) {
                if (PyUnicode_Compare(fk, K_name) == 0) func_name = fv;
                else if (PyUnicode_Compare(fk, K_args) == 0) { args_expr_cached = fv; has_args_key = 1; }
            }
        }
        if (!func_name) {
            PyErr_SetString(PyExc_KeyError, "name");
            return NULL;
        }

        /* "if" built-in */
        if (PyUnicode_Check(func_name) && PyUnicode_GET_LENGTH(func_name) == 2 &&
            (func_name == K_if_name || PyUnicode_Compare(func_name, K_if_name) == 0)) {
            PyObject *args_expr = args_expr_cached;
            Py_ssize_t alen = (args_expr != NULL) ? PyObject_Size(args_expr) : 0;
            if (alen < 0) return NULL;
            PyObject *value_expr = (alen >= 1) ? PySequence_GetItem(args_expr, 0) : NULL;
            if (alen >= 1 && !value_expr) return NULL;
            PyObject *true_expr = (alen >= 2) ? PySequence_GetItem(args_expr, 1) : NULL;
            if (alen >= 2 && !true_expr) { Py_XDECREF(value_expr); return NULL; }
            PyObject *false_expr = (alen >= 3) ? PySequence_GetItem(args_expr, 2) : NULL;
            if (alen >= 3 && !false_expr) { Py_XDECREF(value_expr); Py_XDECREF(true_expr); return NULL; }

            int cond = 0;
            if (value_expr != NULL) {
                PyObject *val = evaluate_expression_internal(value_expr, options, globals_, locals_, builtins, script, statement);
                Py_DECREF(value_expr);
                if (!val) { Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
                cond = c_value_boolean(val);
                Py_DECREF(val);
                if (PyErr_Occurred()) { Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
            }
            PyObject *result_expr = cond ? true_expr : false_expr;
            PyObject *other = cond ? false_expr : true_expr;
            Py_XDECREF(other);
            if (result_expr == NULL) Py_RETURN_NONE;
            PyObject *result = evaluate_expression_internal(result_expr, options, globals_, locals_, builtins, script, statement);
            Py_DECREF(result_expr);
            return result;
        }

        /* Compute the function arguments */
        PyObject *args_expr = args_expr_cached;
        (void)has_args_key;
        PyObject *func_args = NULL;
        if (args_expr != NULL) {
            Py_ssize_t alen = PyList_Check(args_expr) ? PyList_GET_SIZE(args_expr) : PyObject_Size(args_expr);
            if (alen < 0) return NULL;
            func_args = PyList_New(alen);
            if (!func_args) return NULL;
            int is_list = PyList_Check(args_expr);
            for (Py_ssize_t i = 0; i < alen; i++) {
                PyObject *arg_expr = is_list ? PyList_GET_ITEM(args_expr, i) : PySequence_GetItem(args_expr, i);
                if (!arg_expr) { Py_DECREF(func_args); return NULL; }
                PyObject *v;
                PyObject *ak, *av;
                if (PyDict_Check(arg_expr) && dict_peek1(arg_expr, &ak, &av)) {
                    if (ak == K_variable) v = lookup_variable(av, globals_, locals_);
                    else if (ak == K_number || ak == K_string) { Py_INCREF(av); v = av; }
                    else v = evaluate_expression_internal(arg_expr, options, globals_, locals_, builtins, script, statement);
                } else {
                    v = evaluate_expression_internal(arg_expr, options, globals_, locals_, builtins, script, statement);
                }
                if (!is_list) Py_DECREF(arg_expr);
                if (!v) { Py_DECREF(func_args); return NULL; }
                PyList_SET_ITEM(func_args, i, v);
            }
        }

        /* Resolve function value */
        PyObject *func_value = NULL;
        int local_hit = 0;
        if (locals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(locals_, func_name);
            if (PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
            if (v != NULL) { func_value = v; local_hit = 1; }
        }
        if (!local_hit && globals_ != NULL) {
            PyObject *v = PyDict_GetItemWithError(globals_, func_name);
            if (PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
            if (v != NULL) func_value = v;
        }
        if (func_value == NULL && builtins) {
            PyObject *v = PyDict_GetItemWithError(g_expression_functions, func_name);
            if (PyErr_Occurred()) { Py_XDECREF(func_args); return NULL; }
            if (v != NULL) func_value = v;
        }
        if (func_value != NULL && func_value != Py_None) {
            PyObject *call_args = (func_args != NULL) ? func_args : Py_None;
            PyObject *call_opts = (options != NULL) ? options : Py_None;
            PyObject *result;
            /* Fast path: script-defined function - call directly */
            if (Py_TYPE(func_value) == &ScriptFuncType) {
                ScriptFuncObject *sf = (ScriptFuncObject *)func_value;
                result = script_function_call(sf->script, sf->function, call_args, call_opts);
            } else {
                result = PyObject_CallFunctionObjArgs(func_value, call_args, call_opts, NULL);
            }
            Py_XDECREF(func_args);
            if (result) return result;
            /* Handle exception */
            if (PyErr_ExceptionMatches(g_runtime_error_class)) {
                return NULL;
            }
            PyObject *etype, *evalue, *etb;
            PyErr_Fetch(&etype, &evalue, &etb);
            PyErr_NormalizeException(&etype, &evalue, &etb);

            /* Log if debug + logFn */
            if (options != NULL && options != Py_None && PyDict_Check(options)) {
                PyObject *log_fn = dict_getitem_borrow(options, K_logFn);
                PyObject *debug_obj = dict_getitem_borrow(options, K_debug);
                if (log_fn && debug_obj && PyObject_IsTrue(debug_obj)) {
                    PyObject *err_text = evalue ? PyObject_Str(evalue) : PyUnicode_FromString("<unknown>");
                    if (err_text) {
                        PyObject *msg = PyUnicode_FromFormat(
                            "BareScript: Function \"%U\" failed with error: %U", func_name, err_text);
                        Py_DECREF(err_text);
                        if (msg) {
                            PyObject *wrapped = PyObject_CallFunctionObjArgs(g_runtime_error_class,
                                script ? script : Py_None, statement ? statement : Py_None, msg, NULL);
                            Py_DECREF(msg);
                            if (wrapped) {
                                PyObject *wrapped_str = PyObject_Str(wrapped);
                                Py_DECREF(wrapped);
                                if (wrapped_str) {
                                    PyObject *r = PyObject_CallFunctionObjArgs(log_fn, wrapped_str, NULL);
                                    Py_DECREF(wrapped_str);
                                    Py_XDECREF(r);
                                }
                            }
                        }
                    }
                }
            }
            /* ValueArgsError -> return_value; else None */
            if (evalue && g_value_args_error_class &&
                PyObject_IsInstance(evalue, g_value_args_error_class) == 1) {
                PyObject *rv = PyObject_GetAttr(evalue, K_return_value_attr);
                Py_XDECREF(etype); Py_XDECREF(evalue); Py_XDECREF(etb);
                if (rv) {
                    PyErr_Clear();
                    return rv;
                }
                Py_RETURN_NONE;
            }
            Py_XDECREF(etype); Py_XDECREF(evalue); Py_XDECREF(etb);
            PyErr_Clear();
            Py_RETURN_NONE;
        }

        Py_XDECREF(func_args);
        raise_runtime_error_format(script, statement, "Undefined function \"%U\"", func_name);
        return NULL;
    }

    /* Binary expression */
    if (key_match(ekey, K_binary)) {
        PyObject *binary = eval_body;
        PyObject *op = NULL, *left_expr = NULL, *right_expr_obj = NULL;
        Py_ssize_t bpos = 0;
        PyObject *bk, *bv;
        while (PyDict_Next(binary, &bpos, &bk, &bv)) {
            if (bk == K_op) op = bv;
            else if (bk == K_left) left_expr = bv;
            else if (bk == K_right) right_expr_obj = bv;
            else if (PyUnicode_Check(bk)) {
                if (PyUnicode_Compare(bk, K_op) == 0) op = bv;
                else if (PyUnicode_Compare(bk, K_left) == 0) left_expr = bv;
                else if (PyUnicode_Compare(bk, K_right) == 0) right_expr_obj = bv;
            }
        }
        if (!op) { PyErr_SetString(PyExc_KeyError, "op"); return NULL; }
        if (!left_expr) { PyErr_SetString(PyExc_KeyError, "left"); return NULL; }
        if (!right_expr_obj) { PyErr_SetString(PyExc_KeyError, "right"); return NULL; }

        int op_id = op_to_id(op);

        /* Inline leaf evaluation for left */
        PyObject *left_value;
        {
            PyObject *lk, *lv;
            if (PyDict_Check(left_expr) && dict_peek1(left_expr, &lk, &lv)) {
                if (lk == K_variable) {
                    left_value = lookup_variable(lv, globals_, locals_);
                } else if (lk == K_number || lk == K_string) {
                    Py_INCREF(lv); left_value = lv;
                } else {
                    left_value = evaluate_expression_internal(left_expr, options, globals_, locals_, builtins, script, statement);
                }
            } else {
                left_value = evaluate_expression_internal(left_expr, options, globals_, locals_, builtins, script, statement);
            }
        }
        if (!left_value) return NULL;

        /* Short-circuit */
        if (op_id == OP_AND_AND) {
            if (!c_value_boolean(left_value)) return left_value;
            Py_DECREF(left_value);
            return evaluate_expression_internal(right_expr_obj, options, globals_, locals_, builtins, script, statement);
        }
        if (op_id == OP_OR_OR) {
            if (c_value_boolean(left_value)) return left_value;
            Py_DECREF(left_value);
            return evaluate_expression_internal(right_expr_obj, options, globals_, locals_, builtins, script, statement);
        }

        /* Inline leaf evaluation for right */
        PyObject *right_value;
        {
            PyObject *rk, *rv;
            if (PyDict_Check(right_expr_obj) && dict_peek1(right_expr_obj, &rk, &rv)) {
                if (rk == K_variable) {
                    right_value = lookup_variable(rv, globals_, locals_);
                } else if (rk == K_number || rk == K_string) {
                    Py_INCREF(rv); right_value = rv;
                } else {
                    right_value = evaluate_expression_internal(right_expr_obj, options, globals_, locals_, builtins, script, statement);
                }
            } else {
                right_value = evaluate_expression_internal(right_expr_obj, options, globals_, locals_, builtins, script, statement);
            }
        }
        if (!right_value) { Py_DECREF(left_value); return NULL; }

        PyTypeObject *lt = Py_TYPE(left_value);
        PyTypeObject *rt = Py_TYPE(right_value);

        /* Fast path: both floats — direct C arithmetic */
        if (lt == &PyFloat_Type && rt == &PyFloat_Type) {
            double a = PyFloat_AS_DOUBLE(left_value);
            double b = PyFloat_AS_DOUBLE(right_value);
            PyObject *result = NULL;
            switch (op_id) {
                case OP_PLUS:  result = PyFloat_FromDouble(a + b); break;
                case OP_MINUS: result = PyFloat_FromDouble(a - b); break;
                case OP_STAR:  result = PyFloat_FromDouble(a * b); break;
                case OP_SLASH:
                    if (b == 0.0) {
                        PyErr_SetString(PyExc_ZeroDivisionError, "float division by zero");
                    } else result = PyFloat_FromDouble(a / b);
                    break;
                case OP_LT:    result = (a <  b) ? Py_True : Py_False; Py_INCREF(result); break;
                case OP_LE:    result = (a <= b) ? Py_True : Py_False; Py_INCREF(result); break;
                case OP_GT:    result = (a >  b) ? Py_True : Py_False; Py_INCREF(result); break;
                case OP_GE:    result = (a >= b) ? Py_True : Py_False; Py_INCREF(result); break;
                case OP_EQ:    result = (a == b) ? Py_True : Py_False; Py_INCREF(result); break;
                case OP_NE:    result = (a != b) ? Py_True : Py_False; Py_INCREF(result); break;
                default: break; /* fall through to generic */
            }
            if (result) { Py_DECREF(left_value); Py_DECREF(right_value); return result; }
            if (PyErr_Occurred()) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
            /* Unhandled float op (** % etc) -> fall through to generic path */
        }
        /* Fast path: both ints — direct compare */
        else if (lt == &PyLong_Type && rt == &PyLong_Type) {
            PyObject *result = NULL;
            switch (op_id) {
                case OP_PLUS:  result = PyNumber_Add(left_value, right_value); break;
                case OP_MINUS: result = PyNumber_Subtract(left_value, right_value); break;
                case OP_STAR:  result = PyNumber_Multiply(left_value, right_value); break;
                case OP_SLASH: result = PyNumber_TrueDivide(left_value, right_value); break;
                case OP_LT: case OP_LE: case OP_GT: case OP_GE: case OP_EQ: case OP_NE: {
                    int op_richcmp = (op_id == OP_LT ? Py_LT :
                                      op_id == OP_LE ? Py_LE :
                                      op_id == OP_GT ? Py_GT :
                                      op_id == OP_GE ? Py_GE :
                                      op_id == OP_EQ ? Py_EQ : Py_NE);
                    int c = PyObject_RichCompareBool(left_value, right_value, op_richcmp);
                    if (c < 0) result = NULL;
                    else { result = c ? Py_True : Py_False; Py_INCREF(result); }
                    break;
                }
                default: break;
            }
            if (result) { Py_DECREF(left_value); Py_DECREF(right_value); return result; }
            if (PyErr_Occurred()) { Py_DECREF(left_value); Py_DECREF(right_value); return NULL; }
        }

        /* Mixed-numeric int<->float fast path */
        int l_num = (lt == &PyLong_Type || lt == &PyFloat_Type);
        int r_num = (rt == &PyLong_Type || rt == &PyFloat_Type);
        int l_str = (lt == &PyUnicode_Type);
        int r_str = (rt == &PyUnicode_Type);

        PyObject *result = NULL;

        switch (op_id) {
        case OP_PLUS:
            if (l_num && r_num) result = PyNumber_Add(left_value, right_value);
            else if (l_str && r_str) result = PyUnicode_Concat(left_value, right_value);
            else if (l_str) {
                PyObject *rs = PyObject_CallFunctionObjArgs(g_value_string, right_value, NULL);
                if (rs) { result = PyUnicode_Concat(left_value, rs); Py_DECREF(rs); }
            } else if (r_str) {
                PyObject *ls = PyObject_CallFunctionObjArgs(g_value_string, left_value, NULL);
                if (ls) { result = PyUnicode_Concat(ls, right_value); Py_DECREF(ls); }
            } else if (is_datetime_like(left_value) && r_num) {
                PyObject *ldt = call_normalize_dt(left_value);
                if (ldt) {
                    PyObject *td = make_timedelta_ms(right_value);
                    if (td) { result = PyNumber_Add(ldt, td); Py_DECREF(td); }
                    Py_DECREF(ldt);
                }
            } else if (l_num && is_datetime_like(right_value)) {
                PyObject *rdt = call_normalize_dt(right_value);
                if (rdt) {
                    PyObject *td = make_timedelta_ms(left_value);
                    if (td) { result = PyNumber_Add(rdt, td); Py_DECREF(td); }
                    Py_DECREF(rdt);
                }
            } else { Py_INCREF(Py_None); result = Py_None; }
            break;
        case OP_MINUS:
            if (l_num && r_num) result = PyNumber_Subtract(left_value, right_value);
            else if (is_datetime_like(left_value) && is_datetime_like(right_value)) {
                PyObject *ldt = call_normalize_dt(left_value);
                PyObject *rdt = ldt ? call_normalize_dt(right_value) : NULL;
                if (ldt && rdt) {
                    PyObject *diff = PyNumber_Subtract(ldt, rdt);
                    if (diff) {
                        PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                        Py_DECREF(diff);
                        if (secs) {
                            PyObject *thousand = PyFloat_FromDouble(1000.0);
                            if (thousand) {
                                PyObject *ms = PyNumber_Multiply(secs, thousand);
                                Py_DECREF(thousand);
                                if (ms) {
                                    PyObject *zero = PyLong_FromLong(0);
                                    if (zero) {
                                        result = PyObject_CallFunctionObjArgs(g_value_round_number, ms, zero, NULL);
                                        Py_DECREF(zero);
                                    }
                                    Py_DECREF(ms);
                                }
                            }
                            Py_DECREF(secs);
                        }
                    }
                }
                Py_XDECREF(ldt); Py_XDECREF(rdt);
            } else { Py_INCREF(Py_None); result = Py_None; }
            break;
        case OP_STAR:
            if (l_num && r_num) result = PyNumber_Multiply(left_value, right_value);
            else { Py_INCREF(Py_None); result = Py_None; }
            break;
        case OP_SLASH:
            if (l_num && r_num) result = PyNumber_TrueDivide(left_value, right_value);
            else { Py_INCREF(Py_None); result = Py_None; }
            break;
        case OP_EQ: case OP_NE: case OP_LE: case OP_LT: case OP_GE: case OP_GT: {
            int richcmp = (op_id == OP_EQ ? Py_EQ :
                          op_id == OP_NE ? Py_NE :
                          op_id == OP_LE ? Py_LE :
                          op_id == OP_LT ? Py_LT :
                          op_id == OP_GE ? Py_GE : Py_GT);
            int target = (op_id == OP_EQ ? 0 :
                         op_id == OP_NE ? 1 :
                         op_id == OP_LE ? 2 :
                         op_id == OP_LT ? 3 :
                         op_id == OP_GE ? 4 : 5);
            (void)target;
            if (l_num && r_num) {
                int eq = PyObject_RichCompareBool(left_value, right_value, richcmp);
                if (eq < 0) result = NULL;
                else result = eq ? (Py_INCREF(Py_True), Py_True) : (Py_INCREF(Py_False), Py_False);
            } else {
                int c = call_value_compare(left_value, right_value);
                if (c != INT_MIN) {
                    int match = 0;
                    switch (op_id) {
                        case OP_EQ: match = (c == 0); break;
                        case OP_NE: match = (c != 0); break;
                        case OP_LE: match = (c <= 0); break;
                        case OP_LT: match = (c <  0); break;
                        case OP_GE: match = (c >= 0); break;
                        case OP_GT: match = (c >  0); break;
                    }
                    result = match ? (Py_INCREF(Py_True), Py_True) : (Py_INCREF(Py_False), Py_False);
                }
            }
            break;
        }
        case OP_PCT:
            if (l_num && r_num) result = PyNumber_Remainder(left_value, right_value);
            else { Py_INCREF(Py_None); result = Py_None; }
            break;
        case OP_STAR_STAR:
            if (l_num && r_num) result = PyNumber_Power(left_value, right_value, Py_None);
            else { Py_INCREF(Py_None); result = Py_None; }
            break;
        case OP_AMP: case OP_PIPE: case OP_CARET: case OP_LSHIFT: case OP_RSHIFT: {
            /* int & int (allow integer-valued floats) */
            int ok = 0;
            PyObject *li = NULL, *ri = NULL;
            if (l_num && r_num) {
                if (lt == &PyLong_Type) { li = left_value; Py_INCREF(li); }
                else {
                    double d = PyFloat_AS_DOUBLE(left_value);
                    PyObject *as_int = PyNumber_Long(left_value);
                    if (as_int) {
                        double back = PyLong_AsDouble(as_int);
                        if (back == d) { li = as_int; }
                        else Py_DECREF(as_int);
                    }
                }
                if (li) {
                    if (rt == &PyLong_Type) { ri = right_value; Py_INCREF(ri); }
                    else {
                        double d = PyFloat_AS_DOUBLE(right_value);
                        PyObject *as_int = PyNumber_Long(right_value);
                        if (as_int) {
                            double back = PyLong_AsDouble(as_int);
                            if (back == d) { ri = as_int; }
                            else Py_DECREF(as_int);
                        }
                    }
                    if (ri) ok = 1;
                }
            }
            if (ok) {
                if (op_id == OP_AMP) result = PyNumber_And(li, ri);
                else if (op_id == OP_PIPE) result = PyNumber_Or(li, ri);
                else if (op_id == OP_CARET) result = PyNumber_Xor(li, ri);
                else if (op_id == OP_LSHIFT) result = PyNumber_Lshift(li, ri);
                else result = PyNumber_Rshift(li, ri);
            } else {
                Py_INCREF(Py_None); result = Py_None;
            }
            Py_XDECREF(li); Py_XDECREF(ri);
            break;
        }
        default:
            Py_INCREF(Py_None); result = Py_None;
            break;
        }

        Py_DECREF(left_value);
        Py_DECREF(right_value);
        return result;
    }

    /* Unary expression */
    if (key_match(ekey, K_unary)) {
        PyObject *unary = eval_body;
        PyObject *op = dict_getitem_borrow(unary, K_op);
        if (!op) { PyErr_SetString(PyExc_KeyError, "op"); return NULL; }
        PyObject *uexpr = dict_getitem_borrow(unary, K_expr);
        if (!uexpr) { PyErr_SetString(PyExc_KeyError, "expr"); return NULL; }
        int u_id = op_to_id(op);
        PyObject *value = evaluate_expression_internal(uexpr, options, globals_, locals_, builtins, script, statement);
        if (!value) return NULL;
        if (u_id == OP_BANG) {
            int b = c_value_boolean(value);
            Py_DECREF(value);
            return b ? (Py_INCREF(Py_False), Py_False) : (Py_INCREF(Py_True), Py_True);
        }
        PyTypeObject *vt = Py_TYPE(value);
        int v_num = (vt == &PyLong_Type || vt == &PyFloat_Type);
        PyObject *res = NULL;
        if (u_id == OP_MINUS) {
            if (v_num) res = PyNumber_Negative(value);
            else { Py_INCREF(Py_None); res = Py_None; }
        } else { /* '~' */
            if (v_num) {
                PyObject *as_int = NULL;
                if (vt == &PyLong_Type) { Py_INCREF(value); as_int = value; }
                else {
                    double d = PyFloat_AS_DOUBLE(value);
                    PyObject *ai = PyNumber_Long(value);
                    if (ai) {
                        double back = PyLong_AsDouble(ai);
                        if (back == d) as_int = ai;
                        else Py_DECREF(ai);
                    }
                }
                if (as_int) { res = PyNumber_Invert(as_int); Py_DECREF(as_int); }
                else { Py_INCREF(Py_None); res = Py_None; }
            } else { Py_INCREF(Py_None); res = Py_None; }
        }
        Py_DECREF(value);
        return res;
    }

    /* Group */
    if (key_match(ekey, K_group)) {
        return evaluate_expression_internal(eval_body, options, globals_, locals_, builtins, script, statement);
    }

    Py_RETURN_NONE;
}


/* =====================================================================
 * Python-callable wrappers
 * ===================================================================== */

static PyObject *
py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script = NULL, *options = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &script, &options)) return NULL;

    if (options == NULL || options == Py_None) {
        options = PyDict_New();
        if (!options) return NULL;
    } else {
        Py_INCREF(options);
    }

    PyObject *globals_ = dict_getitem_borrow(options, K_globals);
    if (PyErr_Occurred()) { Py_DECREF(options); return NULL; }
    if (globals_ == NULL) {
        globals_ = PyDict_New();
        if (!globals_) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, K_globals, globals_) < 0) {
            Py_DECREF(globals_); Py_DECREF(options); return NULL;
        }
        Py_DECREF(globals_);
        globals_ = dict_getitem_borrow(options, K_globals);
    }

    /* Set script function globals that are not already present */
    PyObject *iter = PyObject_GetIter(g_script_functions);
    if (!iter) { Py_DECREF(options); return NULL; }
    PyObject *key;
    while ((key = PyIter_Next(iter)) != NULL) {
        int contains = PyDict_Contains(globals_, key);
        if (contains < 0) { Py_DECREF(key); Py_DECREF(iter); Py_DECREF(options); return NULL; }
        if (!contains) {
            PyObject *val = PyDict_GetItemWithError(g_script_functions, key);
            if (!val) { Py_DECREF(key); Py_DECREF(iter); Py_DECREF(options); return NULL; }
            if (PyDict_SetItem(globals_, key, val) < 0) {
                Py_DECREF(key); Py_DECREF(iter); Py_DECREF(options); return NULL;
            }
        }
        Py_DECREF(key);
    }
    Py_DECREF(iter);
    if (PyErr_Occurred()) { Py_DECREF(options); return NULL; }

    PyObject *zero = PyLong_FromLong(0);
    if (!zero) { Py_DECREF(options); return NULL; }
    if (PyDict_SetItem(options, K_statementCount, zero) < 0) {
        Py_DECREF(zero); Py_DECREF(options); return NULL;
    }
    Py_DECREF(zero);

    PyObject *statements = dict_getitem_borrow(script, K_statements);
    if (!statements) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_KeyError, "statements");
        Py_DECREF(options); return NULL;
    }

    PyObject *result = execute_script_helper(script, statements, options, NULL);
    Py_DECREF(options);
    return result;
}


static PyObject *
py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr = NULL, *options = Py_None, *locals_ = Py_None, *script = Py_None, *statement = Py_None;
    int builtins = 1;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOpOO", kwlist,
            &expr, &options, &locals_, &builtins, &script, &statement)) return NULL;

    PyObject *opt = (options == Py_None) ? NULL : options;
    PyObject *loc = (locals_ == Py_None) ? NULL : locals_;
    PyObject *sc = (script == Py_None) ? NULL : script;
    PyObject *st = (statement == Py_None) ? NULL : statement;
    PyObject *gbl = NULL;
    if (opt != NULL && PyDict_Check(opt)) {
        gbl = dict_getitem_borrow(opt, K_globals);
        if (PyErr_Occurred()) return NULL;
    }
    return evaluate_expression_internal(expr, opt, gbl, loc, builtins, sc, st);
}


/* =====================================================================
 * Module init
 * ===================================================================== */

static PyMethodDef ModuleMethods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS,
        "Execute a BareScript model."},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS,
        "Evaluate an expression model."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "runtime_c",
    "BareScript runtime - C extension",
    -1,
    ModuleMethods
};


/* Helper to intern a string and store it into a static PyObject* */
#define INIT_KEY(varname, str_lit) do { \
    varname = PyUnicode_InternFromString(str_lit); \
    if (!varname) goto fail; \
} while (0)


PyMODINIT_FUNC
PyInit_runtime_c(void)
{
    PyObject *m = NULL;

    if (PyType_Ready(&ScriptFuncType) < 0) return NULL;

    m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    PyDateTime_IMPORT;
    if (!PyDateTimeAPI) goto fail;

    /* Import sister modules and cache the references we need */
    g_library_mod = PyImport_ImportModule("bare_script.library");
    if (!g_library_mod) goto fail;
    g_value_mod = PyImport_ImportModule("bare_script.value");
    if (!g_value_mod) goto fail;
    g_options_mod = PyImport_ImportModule("bare_script.options");
    if (!g_options_mod) goto fail;
    g_parser_mod = PyImport_ImportModule("bare_script.parser");
    if (!g_parser_mod) goto fail;
    g_model_mod = PyImport_ImportModule("bare_script.model");
    if (!g_model_mod) goto fail;
    g_runtime_mod = PyImport_ImportModule("bare_script.runtime");
    if (!g_runtime_mod) goto fail;

    PyObject *functools_mod = PyImport_ImportModule("functools");
    if (!functools_mod) goto fail;
    g_functools_partial = PyObject_GetAttrString(functools_mod, "partial");
    Py_DECREF(functools_mod);
    if (!g_functools_partial) goto fail;

    PyObject *datetime_mod = PyImport_ImportModule("datetime");
    if (!datetime_mod) goto fail;
    g_datetime_timedelta = PyObject_GetAttrString(datetime_mod, "timedelta");
    g_datetime_date_class = PyObject_GetAttrString(datetime_mod, "date");
    g_datetime_datetime_class = PyObject_GetAttrString(datetime_mod, "datetime");
    Py_DECREF(datetime_mod);
    if (!g_datetime_timedelta || !g_datetime_date_class || !g_datetime_datetime_class) goto fail;

    g_expression_functions = PyObject_GetAttrString(g_library_mod, "EXPRESSION_FUNCTIONS");
    g_script_functions = PyObject_GetAttrString(g_library_mod, "SCRIPT_FUNCTIONS");
    g_runtime_error_class = PyObject_GetAttrString(g_runtime_mod, "BareScriptRuntimeError");
    g_value_args_error_class = PyObject_GetAttrString(g_value_mod, "ValueArgsError");
    g_value_boolean = PyObject_GetAttrString(g_value_mod, "value_boolean");
    g_value_compare = PyObject_GetAttrString(g_value_mod, "value_compare");
    g_value_normalize_datetime = PyObject_GetAttrString(g_value_mod, "value_normalize_datetime");
    g_value_round_number = PyObject_GetAttrString(g_value_mod, "value_round_number");
    g_value_string = PyObject_GetAttrString(g_value_mod, "value_string");
    g_parse_script = PyObject_GetAttrString(g_parser_mod, "parse_script");
    g_lint_script = PyObject_GetAttrString(g_model_mod, "lint_script");
    g_url_file_relative = PyObject_GetAttrString(g_options_mod, "url_file_relative");

    if (!g_expression_functions || !g_script_functions || !g_runtime_error_class ||
        !g_value_args_error_class || !g_value_boolean || !g_value_compare ||
        !g_value_normalize_datetime || !g_value_round_number || !g_value_string ||
        !g_parse_script || !g_lint_script || !g_url_file_relative) goto fail;

    g_default_max_statements = PyFloat_FromDouble(1e9);
    if (!g_default_max_statements) goto fail;

    INIT_KEY(K_statements, "statements");
    INIT_KEY(K_globals, "globals");
    INIT_KEY(K_statementCount, "statementCount");
    INIT_KEY(K_maxStatements, "maxStatements");
    INIT_KEY(K_expr, "expr");
    INIT_KEY(K_jump, "jump");
    INIT_KEY(K_return_, "return");
    INIT_KEY(K_label, "label");
    INIT_KEY(K_name, "name");
    INIT_KEY(K_args, "args");
    INIT_KEY(K_left, "left");
    INIT_KEY(K_right, "right");
    INIT_KEY(K_op, "op");
    INIT_KEY(K_unary, "unary");
    INIT_KEY(K_binary, "binary");
    INIT_KEY(K_group, "group");
    INIT_KEY(K_function, "function");
    INIT_KEY(K_number, "number");
    INIT_KEY(K_string, "string");
    INIT_KEY(K_variable, "variable");
    INIT_KEY(K_include, "include");
    INIT_KEY(K_includes, "includes");
    INIT_KEY(K_url, "url");
    INIT_KEY(K_system, "system");
    INIT_KEY(K_systemPrefix, "systemPrefix");
    INIT_KEY(K_fetchFn, "fetchFn");
    INIT_KEY(K_logFn, "logFn");
    INIT_KEY(K_urlFn, "urlFn");
    INIT_KEY(K_scriptName, "scriptName");
    INIT_KEY(K_lineNumber, "lineNumber");
    INIT_KEY(K_scripts, "scripts");
    INIT_KEY(K_covered, "covered");
    INIT_KEY(K_statement, "statement");
    INIT_KEY(K_count, "count");
    INIT_KEY(K_enabled, "enabled");
    INIT_KEY(K_lastArgArray, "lastArgArray");
    INIT_KEY(K_debug, "debug");
    INIT_KEY(K_return_value_attr, "return_value");
    INIT_KEY(K_coverage_global_name, "__barescriptCoverage");
    INIT_KEY(K_includes_global_name, "__barescriptIncludes");
    INIT_KEY(K_if_name, "if");

    INIT_KEY(K_op_amp_amp, "&&");
    INIT_KEY(K_op_pipe_pipe, "||");
    INIT_KEY(K_op_plus, "+");
    INIT_KEY(K_op_minus, "-");
    INIT_KEY(K_op_star, "*");
    INIT_KEY(K_op_slash, "/");
    INIT_KEY(K_op_eq, "==");
    INIT_KEY(K_op_ne, "!=");
    INIT_KEY(K_op_le, "<=");
    INIT_KEY(K_op_lt, "<");
    INIT_KEY(K_op_ge, ">=");
    INIT_KEY(K_op_gt, ">");
    INIT_KEY(K_op_pct, "%");
    INIT_KEY(K_op_star_star, "**");
    INIT_KEY(K_op_amp, "&");
    INIT_KEY(K_op_pipe, "|");
    INIT_KEY(K_op_caret, "^");
    INIT_KEY(K_op_lshift, "<<");
    INIT_KEY(K_op_rshift, ">>");
    INIT_KEY(K_op_bang, "!");
    INIT_KEY(K_op_neg, "-");
    INIT_KEY(K_op_tilde, "~");

    INIT_KEY(K_var_null, "null");
    INIT_KEY(K_var_true, "true");
    INIT_KEY(K_var_false, "false");

    Py_INCREF(&ScriptFuncType);
    if (PyModule_AddObject(m, "_ScriptFunction", (PyObject *)&ScriptFuncType) < 0) {
        Py_DECREF(&ScriptFuncType);
        goto fail;
    }

    return m;

fail:
    Py_XDECREF(m);
    return NULL;
}
