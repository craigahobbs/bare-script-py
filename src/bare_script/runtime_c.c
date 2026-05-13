/*
 * runtime_c.c - C port of bare_script/runtime.py for Python 3.13+
 *
 * Faithful port of runtime.py. See claude-runtime-c-log.md for the
 * optimization history.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stddef.h>


/* ---------- module-level state (cached Python objects) ---------- */

static PyObject *g_BareScriptRuntimeError = NULL;     /* runtime.BareScriptRuntimeError */
static PyObject *g_SCRIPT_FUNCTIONS = NULL;           /* library.SCRIPT_FUNCTIONS */
static PyObject *g_EXPRESSION_FUNCTIONS = NULL;       /* library.EXPRESSION_FUNCTIONS */
static PyObject *g_lint_script = NULL;                /* model.lint_script */
static PyObject *g_url_file_relative = NULL;          /* options.url_file_relative */
static PyObject *g_parse_script = NULL;               /* parser.parse_script */
static PyObject *g_ValueArgsError = NULL;             /* value.ValueArgsError */
static PyObject *g_value_boolean = NULL;
static PyObject *g_value_compare = NULL;
static PyObject *g_value_normalize_datetime = NULL;
static PyObject *g_value_round_number = NULL;
static PyObject *g_value_string = NULL;
static PyObject *g_datetime_date = NULL;              /* datetime.date */
static PyObject *g_datetime_timedelta = NULL;         /* datetime.timedelta */
static PyObject *g_functools_partial = NULL;

/* Module-level constants */
#define DEFAULT_MAX_STATEMENTS 1000000000LL
static PyObject *g_DEFAULT_MAX_STATEMENTS = NULL;
static PyObject *g_SYSTEM_GLOBAL_COVERAGE_NAME = NULL; /* "__barescriptCoverage" */
static PyObject *g_SYSTEM_GLOBAL_INCLUDES_NAME = NULL; /* "__barescriptIncludes" */

/* Interned string keys */
static PyObject *KS_expr = NULL;
static PyObject *KS_jump = NULL;
static PyObject *KS_return = NULL;
static PyObject *KS_function = NULL;
static PyObject *KS_include = NULL;
static PyObject *KS_label = NULL;
static PyObject *KS_name = NULL;
static PyObject *KS_args = NULL;
static PyObject *KS_globals = NULL;
static PyObject *KS_statementCount = NULL;
static PyObject *KS_maxStatements = NULL;
static PyObject *KS_statements = NULL;
static PyObject *KS_systemPrefix = NULL;
static PyObject *KS_fetchFn = NULL;
static PyObject *KS_logFn = NULL;
static PyObject *KS_urlFn = NULL;
static PyObject *KS_url = NULL;
static PyObject *KS_system = NULL;
static PyObject *KS_includes = NULL;
static PyObject *KS_debug = NULL;
static PyObject *KS_scripts = NULL;
static PyObject *KS_covered = NULL;
static PyObject *KS_count = NULL;
static PyObject *KS_enabled = NULL;
static PyObject *KS_script = NULL;
static PyObject *KS_statement = NULL;
static PyObject *KS_scriptName = NULL;
static PyObject *KS_lineNumber = NULL;
static PyObject *KS_lastArgArray = NULL;
static PyObject *KS_binary = NULL;
static PyObject *KS_unary = NULL;
static PyObject *KS_variable = NULL;
static PyObject *KS_number = NULL;
static PyObject *KS_string = NULL;
static PyObject *KS_group = NULL;
static PyObject *KS_left = NULL;
static PyObject *KS_right = NULL;
static PyObject *KS_op = NULL;
static PyObject *KS_null = NULL;     /* "null" */
static PyObject *KS_true = NULL;     /* "true" */
static PyObject *KS_false = NULL;    /* "false" */
static PyObject *KS_if = NULL;       /* "if" */
static PyObject *KS_op_amp = NULL;       /* "&&" */
static PyObject *KS_op_pipe = NULL;      /* "||" */
static PyObject *KS_op_plus = NULL;      /* "+" */
static PyObject *KS_op_minus = NULL;     /* "-" */
static PyObject *KS_op_star = NULL;      /* "*" */
static PyObject *KS_op_slash = NULL;     /* "/" */
static PyObject *KS_op_eq = NULL;        /* "==" */
static PyObject *KS_op_ne = NULL;        /* "!=" */
static PyObject *KS_op_le = NULL;        /* "<=" */
static PyObject *KS_op_lt = NULL;        /* "<" */
static PyObject *KS_op_ge = NULL;        /* ">=" */
static PyObject *KS_op_gt = NULL;        /* ">" */
static PyObject *KS_op_pct = NULL;       /* "%" */
static PyObject *KS_op_pow = NULL;       /* "**" */
static PyObject *KS_op_band = NULL;      /* "&" */
static PyObject *KS_op_bor = NULL;       /* "|" */
static PyObject *KS_op_bxor = NULL;      /* "^" */
static PyObject *KS_op_shl = NULL;       /* "<<" */
static PyObject *KS_op_shr = NULL;       /* ">>" */
static PyObject *KS_op_not = NULL;       /* "!" */
static PyObject *KS_op_tilde = NULL;     /* "~" */
static PyObject *KS_return_value = NULL; /* "return_value" */

/* Booleans interned for speed */
#define PY_TRUE Py_True
#define PY_FALSE Py_False


/* ---------- forward declarations ---------- */

static PyObject *evaluate_expression(
    PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
    PyObject *script, PyObject *statement);

static PyObject *execute_script_helper(
    PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_);

static PyObject *resolve_covered_dict(PyObject *script, PyObject *coverage_global);
static int record_coverage_fast(PyObject **covered_dict_ptr, PyObject *script,
                                PyObject *coverage_global, PyObject *statement, PyObject *statement_key);


/* ---------- helpers ---------- */

/* Raise BareScriptRuntimeError(script, statement, message). Returns NULL. */
static PyObject *raise_runtime_error(PyObject *script, PyObject *statement, const char *message)
{
    PyObject *msg = PyUnicode_FromString(message);
    if (msg == NULL) return NULL;
    PyObject *args = PyTuple_Pack(3, script ? script : Py_None,
                                  statement ? statement : Py_None, msg);
    Py_DECREF(msg);
    if (args == NULL) return NULL;
    PyObject *exc = PyObject_CallObject(g_BareScriptRuntimeError, args);
    Py_DECREF(args);
    if (exc == NULL) return NULL;
    PyErr_SetObject(g_BareScriptRuntimeError, exc);
    Py_DECREF(exc);
    return NULL;
}

static PyObject *raise_runtime_error_fmt(PyObject *script, PyObject *statement, const char *fmt, ...)
{
    char buf[512];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    return raise_runtime_error(script, statement, buf);
}

/* Inlined value_boolean for common BareScript types. Returns -1 on error. */
static inline int fast_value_boolean(PyObject *v)
{
    if (v == Py_None) return 0;
    if (v == Py_True) return 1;
    if (v == Py_False) return 0;
    PyTypeObject *t = Py_TYPE(v);
    if (t == &PyLong_Type) return PyObject_IsTrue(v);
    if (t == &PyFloat_Type) return PyFloat_AS_DOUBLE(v) != 0.0;
    if (t == &PyUnicode_Type) return PyUnicode_GET_LENGTH(v) != 0;
    if (t == &PyList_Type) return PyList_GET_SIZE(v) != 0;
    /* Other non-None (dict, datetime, function, regex, etc.) -> true */
    return 1;
}
#define call_value_boolean(v) fast_value_boolean(v)

/* Pointer-identity-first key compare. Both sides expected to be interned. */
#define KS_EQ(k, ks) ((k) == (ks) || (PyUnicode_Check(k) && PyUnicode_Compare((k), (ks)) == 0))

/* Call value_compare(a, b) and return its long int. Returns LONG_MIN on error. */
static long call_value_compare(PyObject *a, PyObject *b)
{
    PyObject *args[2] = {a, b};
    PyObject *result = PyObject_Vectorcall(g_value_compare, args, 2, NULL);
    if (result == NULL) return -2147483647L; /* sentinel; caller must check PyErr */
    long r = PyLong_AsLong(result);
    Py_DECREF(result);
    if (r == -1 && PyErr_Occurred()) return -2147483647L;
    return r;
}

/* Return 1 if value is a "number" (int or float) but NOT a bool. */
static int is_number(PyObject *v)
{
    if (PyBool_Check(v)) return 0;
    return PyLong_Check(v) || PyFloat_Check(v);
}

/* Return 1 if value is an int after coercion (i.e., int(v) == v). */
static int is_integer_valued(PyObject *v)
{
    if (PyBool_Check(v)) return 0;
    if (PyLong_Check(v)) return 1;
    if (PyFloat_Check(v)) {
        double d = PyFloat_AS_DOUBLE(v);
        if (d != d) return 0; /* NaN */
        if (d == (double)(long long)d) return 1;
        /* Compare with int(v) using Python semantics for large floats */
        PyObject *as_int = PyNumber_Long(v);
        if (as_int == NULL) { PyErr_Clear(); return 0; }
        PyObject *as_float = PyNumber_Float(as_int);
        Py_DECREF(as_int);
        if (as_float == NULL) { PyErr_Clear(); return 0; }
        int eq = (PyFloat_AS_DOUBLE(as_float) == d);
        Py_DECREF(as_float);
        return eq;
    }
    return 0;
}

/* Coerce PyObject number to PyLongObject (new ref) for bitwise ops. */
static PyObject *to_pylong(PyObject *v)
{
    if (PyLong_Check(v)) {
        Py_INCREF(v);
        return v;
    }
    return PyNumber_Long(v);
}

/* dict.get with default fallback. Returns new ref, or NULL on error (default is borrowed). */
static PyObject *dict_get_new(PyObject *dict, PyObject *key, PyObject *def)
{
    PyObject *value = PyDict_GetItemWithError(dict, key);
    if (value != NULL) {
        Py_INCREF(value);
        return value;
    }
    if (PyErr_Occurred()) return NULL;
    if (def == NULL) Py_RETURN_NONE;
    Py_INCREF(def);
    return def;
}

/* Get next dict key (the first key in iteration order). Returns borrowed reference or NULL on error/empty. */
static PyObject *dict_first_key(PyObject *dict)
{
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    if (PyDict_Next(dict, &pos, &key, &value)) {
        return key;
    }
    return NULL;
}

/* Get first (key, value) pair. Returns 1 on success, 0 on empty dict. Both borrowed. */
static inline int dict_first_pair(PyObject *dict, PyObject **out_key, PyObject **out_value)
{
    Py_ssize_t pos = 0;
    return PyDict_Next(dict, &pos, out_key, out_value);
}

/* Fast inline evaluation for number/string/variable expressions only.
   Returns: new ref on success (status: 1), NULL on error (status: -1),
   or NULL with status=0 if expression isn't a simple leaf (caller must fallback). */
static inline PyObject *eval_simple(PyObject *expr, PyObject *locals_, PyObject *globals_, int *status)
{
    if (!PyDict_Check(expr)) { *status = 0; return NULL; }
    PyObject *k, *v;
    if (!dict_first_pair(expr, &k, &v)) { *status = 0; return NULL; }
    if (k == KS_number || k == KS_string) {
        *status = 1;
        Py_INCREF(v);
        return v;
    }
    if (k == KS_variable) {
        *status = 1;
        if (PyUnicode_Check(v)) {
            if (v == KS_null || PyUnicode_Compare(v, KS_null) == 0) Py_RETURN_NONE;
            if (v == KS_false || PyUnicode_Compare(v, KS_false) == 0) return Py_NewRef(Py_False);
            if (v == KS_true || PyUnicode_Compare(v, KS_true) == 0) return Py_NewRef(Py_True);
        }
        if (locals_ != NULL && locals_ != Py_None) {
            PyObject *r = PyDict_GetItemWithError(locals_, v);
            if (r != NULL) { Py_INCREF(r); return r; }
            if (PyErr_Occurred()) { *status = -1; return NULL; }
        }
        if (globals_ != NULL) {
            PyObject *r = PyDict_GetItemWithError(globals_, v);
            if (r != NULL) { Py_INCREF(r); return r; }
            if (PyErr_Occurred()) { *status = -1; return NULL; }
        }
        Py_RETURN_NONE;
    }
    *status = 0;
    return NULL;
}


/* ---------- ScriptFunction callable type ---------- */

typedef struct {
    PyObject_HEAD
    vectorcallfunc vectorcall;
    PyObject *script;
    PyObject *function;
} ScriptFunctionObject;

static PyObject *ScriptFunction_vectorcall(
    PyObject *callable, PyObject *const *args, size_t nargsf, PyObject *kwnames);

static int ScriptFunction_traverse(ScriptFunctionObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->script);
    Py_VISIT(self->function);
    return 0;
}

static int ScriptFunction_clear(ScriptFunctionObject *self)
{
    Py_CLEAR(self->script);
    Py_CLEAR(self->function);
    return 0;
}

static void ScriptFunction_dealloc(ScriptFunctionObject *self)
{
    PyObject_GC_UnTrack(self);
    ScriptFunction_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* Shared body: takes call_args and options. Returns new ref or NULL. */
static PyObject *ScriptFunction_call_body(ScriptFunctionObject *self, PyObject *call_args, PyObject *options)
{
    PyObject *function = self->function;
    PyObject *script = self->script;
    PyObject *func_locals = PyDict_New();
    if (func_locals == NULL) return NULL;

    PyObject *func_args = PyDict_GetItemWithError(function, KS_args);
    if (func_args == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
    if (func_args != NULL) {
        Py_ssize_t args_length = PyObject_Length(call_args);
        if (args_length < 0) { Py_DECREF(func_locals); return NULL; }
        Py_ssize_t func_args_length = PyList_Check(func_args) ? PyList_GET_SIZE(func_args) : PyObject_Length(func_args);
        if (func_args_length < 0) { Py_DECREF(func_locals); return NULL; }

        Py_ssize_t ix_arg_last = -1;
        PyObject *last_arg_array = PyDict_GetItemWithError(function, KS_lastArgArray);
        if (last_arg_array == NULL && PyErr_Occurred()) { Py_DECREF(func_locals); return NULL; }
        if (last_arg_array != NULL) {
            int b = PyObject_IsTrue(last_arg_array);
            if (b < 0) { Py_DECREF(func_locals); return NULL; }
            if (b) ix_arg_last = func_args_length - 1;
        }

        for (Py_ssize_t ix = 0; ix < func_args_length; ix++) {
            PyObject *arg_name = PyList_Check(func_args) ?
                PyList_GET_ITEM(func_args, ix) : PySequence_GetItem(func_args, ix);
            if (arg_name == NULL) { Py_DECREF(func_locals); return NULL; }
            if (!PyList_Check(func_args)) {
                /* PySequence_GetItem returns new ref; we'll DECREF after use */
            }

            PyObject *value = NULL;
            if (ix < args_length) {
                if (ix != ix_arg_last) {
                    if (PyList_Check(call_args)) {
                        value = PyList_GET_ITEM(call_args, ix);
                        Py_INCREF(value);
                    } else {
                        value = PySequence_GetItem(call_args, ix);
                    }
                } else {
                    value = PySequence_GetSlice(call_args, ix, args_length);
                }
            } else {
                if (ix == ix_arg_last) {
                    value = PyList_New(0);
                } else {
                    Py_INCREF(Py_None);
                    value = Py_None;
                }
            }
            if (value == NULL) {
                if (!PyList_Check(func_args)) Py_DECREF(arg_name);
                Py_DECREF(func_locals);
                return NULL;
            }
            int rc = PyDict_SetItem(func_locals, arg_name, value);
            Py_DECREF(value);
            if (!PyList_Check(func_args)) Py_DECREF(arg_name);
            if (rc < 0) { Py_DECREF(func_locals); return NULL; }
        }
    }

    PyObject *statements = PyDict_GetItemWithError(function, KS_statements);
    if (statements == NULL) {
        Py_DECREF(func_locals);
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }
    PyObject *result = execute_script_helper(script, statements, options, func_locals);
    Py_DECREF(func_locals);
    return result;
}

/* tp_call shim (rarely used; vectorcall is the fast path) */
static PyObject *ScriptFunction_call(ScriptFunctionObject *self, PyObject *args, PyObject *kwargs)
{
    PyObject *call_args = NULL;
    PyObject *options = NULL;
    if (!PyArg_ParseTuple(args, "OO", &call_args, &options)) return NULL;
    return ScriptFunction_call_body(self, call_args, options);
}

/* Vectorcall: skips tuple packing for the call. */
static PyObject *ScriptFunction_vectorcall(
    PyObject *callable, PyObject *const *args, size_t nargsf, PyObject *kwnames)
{
    Py_ssize_t nargs = PyVectorcall_NARGS(nargsf);
    if (kwnames != NULL && PyTuple_GET_SIZE(kwnames) > 0) {
        PyErr_SetString(PyExc_TypeError, "ScriptFunction does not accept keyword arguments");
        return NULL;
    }
    if (nargs != 2) {
        PyErr_Format(PyExc_TypeError, "ScriptFunction expects 2 arguments, got %zd", nargs);
        return NULL;
    }
    return ScriptFunction_call_body((ScriptFunctionObject *)callable, args[0], args[1]);
}

static PyTypeObject ScriptFunctionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "bare_script.runtime_c.ScriptFunction",
    sizeof(ScriptFunctionObject),
    0,
    (destructor)ScriptFunction_dealloc,
    offsetof(ScriptFunctionObject, vectorcall),  /* tp_vectorcall_offset */
    0, 0, 0, 0, 0, 0, 0, 0,
    (ternaryfunc)ScriptFunction_call,
    0, 0, 0, 0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_HAVE_VECTORCALL,
    "BareScript script function callable",
    (traverseproc)ScriptFunction_traverse,
    (inquiry)ScriptFunction_clear,
};

static PyObject *new_script_function(PyObject *script, PyObject *function)
{
    ScriptFunctionObject *self = PyObject_GC_New(ScriptFunctionObject, &ScriptFunctionType);
    if (self == NULL) return NULL;
    self->vectorcall = ScriptFunction_vectorcall;
    Py_INCREF(script);
    Py_INCREF(function);
    self->script = script;
    self->function = function;
    PyObject_GC_Track(self);
    return (PyObject *)self;
}


/* ---------- record_statement_coverage ---------- */

/* Resolve covered_statements dict once per script. Returns borrowed ref or NULL.
   If script has no scriptName, returns NULL with no error set. */
static PyObject *resolve_covered_dict(PyObject *script, PyObject *coverage_global)
{
    PyObject *script_name = PyDict_GetItemWithError(script, KS_scriptName);
    if (script_name == NULL) return NULL; /* either error or missing — caller handles */

    PyObject *scripts = PyDict_GetItemWithError(coverage_global, KS_scripts);
    if (scripts == NULL) {
        if (PyErr_Occurred()) return NULL;
        scripts = PyDict_New();
        if (scripts == NULL) return NULL;
        if (PyDict_SetItem(coverage_global, KS_scripts, scripts) < 0) { Py_DECREF(scripts); return NULL; }
        Py_DECREF(scripts);
        scripts = PyDict_GetItemWithError(coverage_global, KS_scripts);
        if (scripts == NULL) return NULL;
    }

    PyObject *script_coverage = PyDict_GetItemWithError(scripts, script_name);
    if (script_coverage == NULL) {
        if (PyErr_Occurred()) return NULL;
        script_coverage = PyDict_New();
        if (script_coverage == NULL) return NULL;
        PyObject *covered = PyDict_New();
        if (covered == NULL) { Py_DECREF(script_coverage); return NULL; }
        if (PyDict_SetItem(script_coverage, KS_script, script) < 0 ||
            PyDict_SetItem(script_coverage, KS_covered, covered) < 0) {
            Py_DECREF(covered); Py_DECREF(script_coverage); return NULL;
        }
        Py_DECREF(covered);
        if (PyDict_SetItem(scripts, script_name, script_coverage) < 0) {
            Py_DECREF(script_coverage); return NULL;
        }
        Py_DECREF(script_coverage);
        script_coverage = PyDict_GetItemWithError(scripts, script_name);
        if (script_coverage == NULL) return NULL;
    }
    return PyDict_GetItemWithError(script_coverage, KS_covered);
}

/* Record coverage. covered_dict_ptr is lazily resolved on first eligible statement.
   Lazy resolution preserves the runtime.py contract that an entry is created in
   coverage_global['scripts'] only after a statement with a lineNumber is seen. */
static int record_coverage_fast(PyObject **covered_dict_ptr, PyObject *script,
                                PyObject *coverage_global, PyObject *statement, PyObject *statement_key)
{
    PyObject *stmt_body = PyDict_GetItemWithError(statement, statement_key);
    if (stmt_body == NULL) return PyErr_Occurred() ? -1 : 0;
    PyObject *lineno = PyDict_GetItemWithError(stmt_body, KS_lineNumber);
    if (lineno == NULL) return PyErr_Occurred() ? -1 : 0;

    PyObject *covered_statements = *covered_dict_ptr;
    if (covered_statements == NULL) {
        covered_statements = resolve_covered_dict(script, coverage_global);
        if (covered_statements == NULL) return PyErr_Occurred() ? -1 : 0;
        *covered_dict_ptr = covered_statements;
    }

    PyObject *lineno_str = PyObject_Str(lineno);
    if (lineno_str == NULL) return -1;

    PyObject *covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
    if (covered_statement == NULL) {
        if (PyErr_Occurred()) { Py_DECREF(lineno_str); return -1; }
        covered_statement = PyDict_New();
        if (covered_statement == NULL) { Py_DECREF(lineno_str); return -1; }
        PyObject *zero = PyLong_FromLong(0);
        if (zero == NULL) { Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1; }
        if (PyDict_SetItem(covered_statement, KS_statement, statement) < 0 ||
            PyDict_SetItem(covered_statement, KS_count, zero) < 0 ||
            PyDict_SetItem(covered_statements, lineno_str, covered_statement) < 0) {
            Py_DECREF(zero); Py_DECREF(covered_statement); Py_DECREF(lineno_str); return -1;
        }
        Py_DECREF(zero);
        Py_DECREF(covered_statement);
        covered_statement = PyDict_GetItemWithError(covered_statements, lineno_str);
        if (covered_statement == NULL) { Py_DECREF(lineno_str); return -1; }
    }
    Py_DECREF(lineno_str);

    PyObject *cur = PyDict_GetItemWithError(covered_statement, KS_count);
    if (cur == NULL) return PyErr_Occurred() ? -1 : 0;
    PyObject *one = PyLong_FromLong(1);
    if (one == NULL) return -1;
    PyObject *new_count = PyNumber_Add(cur, one);
    Py_DECREF(one);
    if (new_count == NULL) return -1;
    int rc = PyDict_SetItem(covered_statement, KS_count, new_count);
    Py_DECREF(new_count);
    return rc < 0 ? -1 : 0;
}


/* ---------- evaluate_expression ---------- */

static PyObject *evaluate_expression(
    PyObject *expr, PyObject *options, PyObject *locals_, int builtins,
    PyObject *script, PyObject *statement)
{
    if (!PyDict_Check(expr)) {
        PyErr_SetString(PyExc_TypeError, "expression must be a dict");
        return NULL;
    }
    PyObject *expr_key, *expr_value;
    if (!dict_first_pair(expr, &expr_key, &expr_value)) {
        PyErr_SetString(PyExc_TypeError, "empty expression");
        return NULL;
    }

    PyObject *globals_ = NULL;
    if (options != NULL && options != Py_None && PyDict_Check(options)) {
        globals_ = PyDict_GetItemWithError(options, KS_globals);
        if (globals_ == NULL && PyErr_Occurred()) return NULL;
    }

    /* Number / String — fast paths */
    if (KS_EQ(expr_key, KS_number)) {
        Py_INCREF(expr_value);
        return expr_value;
    }
    if (KS_EQ(expr_key, KS_string)) {
        Py_INCREF(expr_value);
        return expr_value;
    }

    /* Variable */
    if (KS_EQ(expr_key, KS_variable)) {
        PyObject *name = expr_value;
        if (PyUnicode_Check(name)) {
            if (KS_EQ(name, KS_null)) Py_RETURN_NONE;
            if (KS_EQ(name, KS_false)) { Py_INCREF(PY_FALSE); return PY_FALSE; }
            if (KS_EQ(name, KS_true)) { Py_INCREF(PY_TRUE); return PY_TRUE; }
        }
        if (locals_ != NULL && locals_ != Py_None) {
            PyObject *v = NULL;
            int rc = PyDict_GetItemRef(locals_, name, &v);
            if (rc < 0) return NULL;
            if (rc > 0) return v;
        }
        if (globals_ != NULL) {
            PyObject *v = NULL;
            int rc = PyDict_GetItemRef(globals_, name, &v);
            if (rc < 0) return NULL;
            if (rc > 0) return v;
        }
        Py_RETURN_NONE;
    }

    /* Function */
    if (KS_EQ(expr_key, KS_function)) {
        PyObject *fn = expr_value;
        PyObject *func_name = PyDict_GetItemWithError(fn, KS_name);
        if (func_name == NULL) return PyErr_Occurred() ? NULL : Py_NewRef(Py_None);

        /* "if" builtin */
        if (KS_EQ(func_name, KS_if)) {
            PyObject *args_expr = PyDict_GetItemWithError(fn, KS_args);
            if (args_expr == NULL && PyErr_Occurred()) return NULL;
            Py_ssize_t alen = 0;
            if (args_expr != NULL) {
                alen = PyObject_Length(args_expr);
                if (alen < 0) return NULL;
            }
            PyObject *value_expr = (alen >= 1) ? PySequence_GetItem(args_expr, 0) : NULL;
            PyObject *true_expr = (alen >= 2) ? PySequence_GetItem(args_expr, 1) : NULL;
            PyObject *false_expr = (alen >= 3) ? PySequence_GetItem(args_expr, 2) : NULL;
            PyObject *value = NULL;
            if (value_expr != NULL) {
                value = evaluate_expression(value_expr, options, locals_, builtins, script, statement);
                if (value == NULL) { Py_XDECREF(value_expr); Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
            } else {
                Py_INCREF(Py_False); value = Py_False;
            }
            int bv = call_value_boolean(value);
            Py_DECREF(value);
            if (bv < 0) { Py_XDECREF(value_expr); Py_XDECREF(true_expr); Py_XDECREF(false_expr); return NULL; }
            PyObject *chosen = bv ? true_expr : false_expr;
            PyObject *result;
            if (chosen != NULL) {
                result = evaluate_expression(chosen, options, locals_, builtins, script, statement);
            } else {
                Py_INCREF(Py_None); result = Py_None;
            }
            Py_XDECREF(value_expr); Py_XDECREF(true_expr); Py_XDECREF(false_expr);
            return result;
        }

        /* Evaluate args */
        PyObject *args_list = PyDict_GetItemWithError(fn, KS_args);
        if (args_list == NULL && PyErr_Occurred()) return NULL;
        PyObject *func_args = NULL;
        if (args_list != NULL) {
            Py_ssize_t alen = PyObject_Length(args_list);
            if (alen < 0) return NULL;
            func_args = PyList_New(alen);
            if (func_args == NULL) return NULL;
            for (Py_ssize_t i = 0; i < alen; i++) {
                PyObject *arg;
                if (PyList_Check(args_list)) {
                    arg = PyList_GET_ITEM(args_list, i);
                    Py_INCREF(arg);
                } else {
                    arg = PySequence_GetItem(args_list, i);
                    if (arg == NULL) { Py_DECREF(func_args); return NULL; }
                }
                PyObject *v = evaluate_expression(arg, options, locals_, builtins, script, statement);
                Py_DECREF(arg);
                if (v == NULL) { Py_DECREF(func_args); return NULL; }
                PyList_SET_ITEM(func_args, i, v);
            }
        }

        /* Resolve function value */
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
        if (func_value != NULL && func_value != Py_None) {
            PyObject *call_args = func_args ? func_args : Py_None;
            Py_INCREF(call_args);
            PyObject *call_options = options ? options : Py_None;
            PyObject *vc_args[2] = {call_args, call_options};
            PyObject *result = PyObject_Vectorcall(func_value, vc_args, 2, NULL);
            Py_DECREF(call_args);
            Py_XDECREF(func_args);
            if (result != NULL) return result;

            /* Exception path. Re-raise BareScriptRuntimeError. */
            if (PyErr_ExceptionMatches(g_BareScriptRuntimeError)) return NULL;

            /* Catch other exceptions, log if debug, return value */
            PyObject *exc_type, *exc_value, *exc_tb;
            PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
            PyErr_NormalizeException(&exc_type, &exc_value, &exc_tb);

            if (options != NULL && options != Py_None) {
                PyObject *log_fn = PyDict_GetItemWithError(options, KS_logFn);
                if (log_fn == NULL && PyErr_Occurred()) {
                    PyErr_Restore(exc_type, exc_value, exc_tb); return NULL;
                }
                PyObject *debug = PyDict_GetItemWithError(options, KS_debug);
                if (debug == NULL && PyErr_Occurred()) {
                    PyErr_Restore(exc_type, exc_value, exc_tb); return NULL;
                }
                int dbg = (debug != NULL) ? PyObject_IsTrue(debug) : 0;
                if (dbg < 0) {
                    PyErr_Restore(exc_type, exc_value, exc_tb); return NULL;
                }
                if (log_fn != NULL && dbg) {
                    PyObject *err_str = PyObject_Str(exc_value ? exc_value : Py_None);
                    if (err_str != NULL) {
                        PyObject *msg = PyUnicode_FromFormat(
                            "BareScript: Function \"%U\" failed with error: %U",
                            func_name, err_str);
                        if (msg != NULL) {
                            PyObject *r = PyObject_CallOneArg(log_fn, msg);
                            Py_XDECREF(r);
                            Py_DECREF(msg);
                        }
                        Py_DECREF(err_str);
                    }
                    PyErr_Clear();
                }
            }

            /* If ValueArgsError, return its return_value */
            if (exc_value != NULL && PyObject_IsInstance(exc_value, g_ValueArgsError)) {
                PyObject *rv = PyObject_GetAttr(exc_value, KS_return_value);
                Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
                if (rv == NULL) { PyErr_Clear(); Py_RETURN_NONE; }
                return rv;
            }
            Py_XDECREF(exc_type); Py_XDECREF(exc_value); Py_XDECREF(exc_tb);
            Py_RETURN_NONE;
        }
        Py_XDECREF(func_args);

        /* Undefined function */
        const char *name_utf8 = PyUnicode_AsUTF8(func_name);
        return raise_runtime_error_fmt(script, statement, "Undefined function \"%s\"",
                                       name_utf8 ? name_utf8 : "");
    }

    /* Binary */
    if (KS_EQ(expr_key, KS_binary)) {
        PyObject *bin = expr_value;
        PyObject *bin_op = PyDict_GetItemWithError(bin, KS_op);
        PyObject *left_expr = PyDict_GetItemWithError(bin, KS_left);
        PyObject *right_expr = PyDict_GetItemWithError(bin, KS_right);
        if (PyErr_Occurred()) return NULL;
        if (bin_op == NULL || left_expr == NULL) Py_RETURN_NONE;

        int s = 0;
        PyObject *left = eval_simple(left_expr, locals_, globals_, &s);
        if (s == 0) {
            left = evaluate_expression(left_expr, options, locals_, builtins, script, statement);
        }
        if (left == NULL) return NULL;

        /* && / || short-circuit */
        if (KS_EQ(bin_op, KS_op_amp)) {
            int b = call_value_boolean(left);
            if (b < 0) { Py_DECREF(left); return NULL; }
            if (!b) return left;
            Py_DECREF(left);
            return evaluate_expression(right_expr, options, locals_, builtins, script, statement);
        }
        if (KS_EQ(bin_op, KS_op_pipe)) {
            int b = call_value_boolean(left);
            if (b < 0) { Py_DECREF(left); return NULL; }
            if (b) return left;
            Py_DECREF(left);
            return evaluate_expression(right_expr, options, locals_, builtins, script, statement);
        }

        if (right_expr == NULL) { Py_DECREF(left); Py_RETURN_NONE; }
        s = 0;
        PyObject *right = eval_simple(right_expr, locals_, globals_, &s);
        if (s == 0) {
            right = evaluate_expression(right_expr, options, locals_, builtins, script, statement);
        }
        if (right == NULL) { Py_DECREF(left); return NULL; }

        /* Numeric fast path: both operands are non-bool int/float.
           Py_TYPE(true) is &PyBool_Type, not &PyLong_Type, so this excludes bools. */
        {
            PyTypeObject *lt = Py_TYPE(left), *rt = Py_TYPE(right);
            int l_num = (lt == &PyFloat_Type || lt == &PyLong_Type);
            int r_num = (rt == &PyFloat_Type || rt == &PyLong_Type);
            if (l_num && r_num) {
                Py_ssize_t op_len = PyUnicode_GET_LENGTH(bin_op);
                Py_UCS4 c0 = PyUnicode_READ_CHAR(bin_op, 0);
                PyObject *fp = NULL;
                int cmp_kind = 0; /* 0=none, 1=<, 2=<=, 3=>, 4=>=, 5===, 6=!= */
                /* Double-only fast path: inline + - * to avoid PyNumber dispatch. */
                int both_float = (lt == &PyFloat_Type && rt == &PyFloat_Type);
                if (op_len == 1) {
                    if (both_float && (c0 == '+' || c0 == '-' || c0 == '*')) {
                        double a = PyFloat_AS_DOUBLE(left);
                        double b = PyFloat_AS_DOUBLE(right);
                        double r;
                        switch (c0) {
                        case '+': r = a + b; break;
                        case '-': r = a - b; break;
                        case '*': default: r = a * b; break;
                        }
                        fp = PyFloat_FromDouble(r);
                    } else {
                        switch (c0) {
                        case '+': fp = PyNumber_Add(left, right); break;
                        case '-': fp = PyNumber_Subtract(left, right); break;
                        case '*': fp = PyNumber_Multiply(left, right); break;
                        case '/': fp = PyNumber_TrueDivide(left, right); break;
                        case '%': fp = PyNumber_Remainder(left, right); break;
                        case '<': cmp_kind = 1; break;
                        case '>': cmp_kind = 3; break;
                        }
                    }
                } else if (op_len == 2) {
                    Py_UCS4 c1 = PyUnicode_READ_CHAR(bin_op, 1);
                    if (c1 == '=') {
                        switch (c0) {
                        case '<': cmp_kind = 2; break;
                        case '>': cmp_kind = 4; break;
                        case '=': cmp_kind = 5; break;
                        case '!': cmp_kind = 6; break;
                        }
                    } else if (c0 == '*' && c1 == '*') {
                        fp = PyNumber_Power(left, right, Py_None);
                    }
                }
                if (cmp_kind != 0) {
                    /* Inline numeric comparison matching value_compare semantics:
                       value_compare(a,b) = -1 if a<b else 0 if a==b else 1.
                       For NaN, a<b and a==b are both false, so result is 1.
                       Thus value_compare(a,b) > 0 corresponds to !(a <= b). */
                    double a = (lt == &PyFloat_Type) ? PyFloat_AS_DOUBLE(left) : (double)PyLong_AsLongLong(left);
                    double b = (rt == &PyFloat_Type) ? PyFloat_AS_DOUBLE(right) : (double)PyLong_AsLongLong(right);
                    if (PyErr_Occurred()) {
                        /* long overflow — fall back to call_value_compare */
                        PyErr_Clear();
                        long cv = call_value_compare(left, right);
                        if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
                        int r;
                        switch (cmp_kind) {
                        case 1: r = (cv < 0); break;
                        case 2: r = (cv <= 0); break;
                        case 3: r = (cv > 0); break;
                        case 4: r = (cv >= 0); break;
                        case 5: r = (cv == 0); break;
                        case 6: default: r = (cv != 0); break;
                        }
                        fp = r ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
                    } else {
                        int r;
                        switch (cmp_kind) {
                        case 1: r = (a < b); break;
                        case 2: r = (a <= b); break;
                        case 3: r = !(a <= b); break;  /* matches value_compare > 0 incl NaN */
                        case 4: r = !(a < b); break;
                        case 5: r = (a == b); break;
                        case 6: default: r = !(a == b); break;
                        }
                        fp = r ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
                    }
                }
                if (fp != NULL) {
                    Py_DECREF(left); Py_DECREF(right);
                    return fp;
                }
                if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            }
        }

        PyObject *result = NULL;
        int op_handled = 0;

        if (KS_EQ(bin_op, KS_op_plus)) {
            op_handled = 1;
            if (is_number(left) && is_number(right)) {
                result = PyNumber_Add(left, right);
            } else if (PyUnicode_Check(left) && PyUnicode_Check(right)) {
                result = PyNumber_Add(left, right);
            } else if (PyUnicode_Check(left)) {
                PyObject *rs = PyObject_CallOneArg(g_value_string, right);
                if (rs != NULL) { result = PyUnicode_Concat(left, rs); Py_DECREF(rs); }
            } else if (PyUnicode_Check(right)) {
                PyObject *ls = PyObject_CallOneArg(g_value_string, left);
                if (ls != NULL) { result = PyUnicode_Concat(ls, right); Py_DECREF(ls); }
            } else if (PyObject_IsInstance(left, g_datetime_date) && is_number(right)) {
                PyObject *ldt = PyObject_CallOneArg(g_value_normalize_datetime, left);
                if (ldt != NULL) {
                    PyObject *td_kwargs = PyDict_New();
                    PyObject *args_empty = PyTuple_New(0);
                    if (td_kwargs && args_empty) {
                        if (PyDict_SetItemString(td_kwargs, "milliseconds", right) == 0) {
                            PyObject *td = PyObject_Call(g_datetime_timedelta, args_empty, td_kwargs);
                            if (td != NULL) {
                                result = PyNumber_Add(ldt, td);
                                Py_DECREF(td);
                            }
                        }
                    }
                    Py_XDECREF(td_kwargs); Py_XDECREF(args_empty);
                    Py_DECREF(ldt);
                }
            } else if (is_number(left) && PyObject_IsInstance(right, g_datetime_date)) {
                PyObject *rdt = PyObject_CallOneArg(g_value_normalize_datetime, right);
                if (rdt != NULL) {
                    PyObject *td_kwargs = PyDict_New();
                    PyObject *args_empty = PyTuple_New(0);
                    if (td_kwargs && args_empty) {
                        if (PyDict_SetItemString(td_kwargs, "milliseconds", left) == 0) {
                            PyObject *td = PyObject_Call(g_datetime_timedelta, args_empty, td_kwargs);
                            if (td != NULL) {
                                result = PyNumber_Add(rdt, td);
                                Py_DECREF(td);
                            }
                        }
                    }
                    Py_XDECREF(td_kwargs); Py_XDECREF(args_empty);
                    Py_DECREF(rdt);
                }
            }
        } else if (KS_EQ(bin_op, KS_op_minus)) {
            op_handled = 1;
            if (is_number(left) && is_number(right)) {
                result = PyNumber_Subtract(left, right);
            } else if (PyObject_IsInstance(left, g_datetime_date) && PyObject_IsInstance(right, g_datetime_date)) {
                PyObject *ldt = PyObject_CallOneArg(g_value_normalize_datetime, left);
                PyObject *rdt = (ldt != NULL) ? PyObject_CallOneArg(g_value_normalize_datetime, right) : NULL;
                if (ldt && rdt) {
                    PyObject *diff = PyNumber_Subtract(ldt, rdt);
                    if (diff != NULL) {
                        PyObject *secs = PyObject_CallMethod(diff, "total_seconds", NULL);
                        if (secs != NULL) {
                            PyObject *thousand = PyFloat_FromDouble(1000.0);
                            PyObject *ms = thousand ? PyNumber_Multiply(secs, thousand) : NULL;
                            Py_XDECREF(thousand);
                            if (ms != NULL) {
                                PyObject *zero = PyLong_FromLong(0);
                                PyObject *vc_args[2] = {ms, zero};
                                result = PyObject_Vectorcall(g_value_round_number, vc_args, 2, NULL);
                                Py_DECREF(zero); Py_DECREF(ms);
                            }
                            Py_DECREF(secs);
                        }
                        Py_DECREF(diff);
                    }
                }
                Py_XDECREF(ldt); Py_XDECREF(rdt);
            }
        } else if (KS_EQ(bin_op, KS_op_star)) {
            op_handled = 1;
            if (is_number(left) && is_number(right)) result = PyNumber_Multiply(left, right);
        } else if (KS_EQ(bin_op, KS_op_slash)) {
            op_handled = 1;
            if (is_number(left) && is_number(right)) result = PyNumber_TrueDivide(left, right);
        } else if (KS_EQ(bin_op, KS_op_eq)) {
            op_handled = 1;
            long c = call_value_compare(left, right);
            if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            result = (c == 0) ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
        } else if (KS_EQ(bin_op, KS_op_ne)) {
            op_handled = 1;
            long c = call_value_compare(left, right);
            if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            result = (c != 0) ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
        } else if (KS_EQ(bin_op, KS_op_le)) {
            op_handled = 1;
            long c = call_value_compare(left, right);
            if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            result = (c <= 0) ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
        } else if (KS_EQ(bin_op, KS_op_lt)) {
            op_handled = 1;
            long c = call_value_compare(left, right);
            if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            result = (c < 0) ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
        } else if (KS_EQ(bin_op, KS_op_ge)) {
            op_handled = 1;
            long c = call_value_compare(left, right);
            if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            result = (c >= 0) ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
        } else if (KS_EQ(bin_op, KS_op_gt)) {
            op_handled = 1;
            long c = call_value_compare(left, right);
            if (PyErr_Occurred()) { Py_DECREF(left); Py_DECREF(right); return NULL; }
            result = (c > 0) ? Py_NewRef(Py_True) : Py_NewRef(Py_False);
        } else if (KS_EQ(bin_op, KS_op_pct)) {
            op_handled = 1;
            if (is_number(left) && is_number(right)) result = PyNumber_Remainder(left, right);
        } else if (KS_EQ(bin_op, KS_op_pow)) {
            op_handled = 1;
            if (is_number(left) && is_number(right)) result = PyNumber_Power(left, right, Py_None);
        } else if (KS_EQ(bin_op, KS_op_band)) {
            op_handled = 1;
            if (is_number(left) && is_integer_valued(left) && is_number(right) && is_integer_valued(right)) {
                PyObject *ll = to_pylong(left); PyObject *rr = to_pylong(right);
                if (ll && rr) result = PyNumber_And(ll, rr);
                Py_XDECREF(ll); Py_XDECREF(rr);
            }
        } else if (KS_EQ(bin_op, KS_op_bor)) {
            op_handled = 1;
            if (is_number(left) && is_integer_valued(left) && is_number(right) && is_integer_valued(right)) {
                PyObject *ll = to_pylong(left); PyObject *rr = to_pylong(right);
                if (ll && rr) result = PyNumber_Or(ll, rr);
                Py_XDECREF(ll); Py_XDECREF(rr);
            }
        } else if (KS_EQ(bin_op, KS_op_bxor)) {
            op_handled = 1;
            if (is_number(left) && is_integer_valued(left) && is_number(right) && is_integer_valued(right)) {
                PyObject *ll = to_pylong(left); PyObject *rr = to_pylong(right);
                if (ll && rr) result = PyNumber_Xor(ll, rr);
                Py_XDECREF(ll); Py_XDECREF(rr);
            }
        } else if (KS_EQ(bin_op, KS_op_shl)) {
            op_handled = 1;
            if (is_number(left) && is_integer_valued(left) && is_number(right) && is_integer_valued(right)) {
                PyObject *ll = to_pylong(left); PyObject *rr = to_pylong(right);
                if (ll && rr) result = PyNumber_Lshift(ll, rr);
                Py_XDECREF(ll); Py_XDECREF(rr);
            }
        } else {
            /* default: >> */
            op_handled = 1;
            if (is_number(left) && is_integer_valued(left) && is_number(right) && is_integer_valued(right)) {
                PyObject *ll = to_pylong(left); PyObject *rr = to_pylong(right);
                if (ll && rr) result = PyNumber_Rshift(ll, rr);
                Py_XDECREF(ll); Py_XDECREF(rr);
            }
        }

        Py_DECREF(left); Py_DECREF(right);
        if (result != NULL) return result;
        if (PyErr_Occurred()) return NULL;
        (void)op_handled;
        Py_RETURN_NONE;
    }

    /* Unary */
    if (KS_EQ(expr_key, KS_unary)) {
        PyObject *un = expr_value;
        PyObject *un_op = PyDict_GetItemWithError(un, KS_op);
        PyObject *sub_expr = PyDict_GetItemWithError(un, KS_expr);
        if (PyErr_Occurred()) return NULL;
        if (un_op == NULL || sub_expr == NULL) Py_RETURN_NONE;
        PyObject *value = evaluate_expression(sub_expr, options, locals_, builtins, script, statement);
        if (value == NULL) return NULL;

        if (KS_EQ(un_op, KS_op_not)) {
            int b = call_value_boolean(value);
            Py_DECREF(value);
            if (b < 0) return NULL;
            if (b) Py_RETURN_FALSE;
            Py_RETURN_TRUE;
        }
        if (KS_EQ(un_op, KS_op_minus)) {
            PyObject *result = NULL;
            if (is_number(value)) result = PyNumber_Negative(value);
            Py_DECREF(value);
            if (result != NULL) return result;
            if (PyErr_Occurred()) return NULL;
            Py_RETURN_NONE;
        }
        /* ~ */
        PyObject *result = NULL;
        if (is_number(value) && is_integer_valued(value)) {
            PyObject *ll = to_pylong(value);
            if (ll != NULL) { result = PyNumber_Invert(ll); Py_DECREF(ll); }
        }
        Py_DECREF(value);
        if (result != NULL) return result;
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }

    /* Group */
    return evaluate_expression(expr_value, options, locals_, builtins, script, statement);
}


/* ---------- execute_script_helper ---------- */

static PyObject *execute_script_helper(
    PyObject *script, PyObject *statements, PyObject *options, PyObject *locals_)
{
    PyObject *globals_ = PyDict_GetItemWithError(options, KS_globals);
    if (globals_ == NULL) return PyErr_Occurred() ? NULL : Py_NewRef(Py_None);

    PyObject *label_indexes = NULL;
    Py_ssize_t statements_length = PyList_Check(statements) ? PyList_GET_SIZE(statements) : PyObject_Length(statements);
    if (statements_length < 0) return NULL;

    /* Hoist invariants out of the statement loop:
       - max_statements: not expected to change mid-execution.
       - coverage_global / has_coverage: coverage object pointer stable per
         execute_script call.
       - script_system: stable per script.
     */
    long long max_statements = DEFAULT_MAX_STATEMENTS;
    {
        PyObject *max_obj = PyDict_GetItemWithError(options, KS_maxStatements);
        if (max_obj == NULL && PyErr_Occurred()) return NULL;
        if (max_obj != NULL) {
            long long mv = PyLong_AsLongLong(max_obj);
            if (mv == -1 && PyErr_Occurred()) {
                PyErr_Clear();
                double dv = PyFloat_AsDouble(max_obj);
                if (dv == -1.0 && PyErr_Occurred()) return NULL;
                mv = (long long)dv;
            }
            max_statements = mv;
        }
    }

    int has_coverage = 0;
    PyObject *covered_dict = NULL;  /* borrowed; set when has_coverage */
    PyObject *coverage_global = PyDict_GetItemWithError(globals_, g_SYSTEM_GLOBAL_COVERAGE_NAME);
    if (coverage_global == NULL && PyErr_Occurred()) return NULL;
    if (coverage_global != NULL && PyDict_Check(coverage_global)) {
        PyObject *enabled = PyDict_GetItemWithError(coverage_global, KS_enabled);
        if (enabled == NULL && PyErr_Occurred()) return NULL;
        int en = (enabled != NULL) ? PyObject_IsTrue(enabled) : 0;
        if (en < 0) return NULL;
        PyObject *sys_flag = PyDict_GetItemWithError(script, KS_system);
        if (sys_flag == NULL && PyErr_Occurred()) return NULL;
        int sys_is = (sys_flag != NULL) ? PyObject_IsTrue(sys_flag) : 0;
        if (sys_is < 0) return NULL;
        has_coverage = en && !sys_is;
        if (has_coverage) {
            /* If script has no scriptName, no statement would ever record. Short-circuit. */
            PyObject *script_name = PyDict_GetItemWithError(script, KS_scriptName);
            if (script_name == NULL) {
                if (PyErr_Occurred()) return NULL;
                has_coverage = 0;
            }
        }
    }

    Py_ssize_t ix_statement = 0;
    while (ix_statement < statements_length) {
        PyObject *statement;
        if (PyList_Check(statements)) {
            statement = PyList_GET_ITEM(statements, ix_statement);
            Py_INCREF(statement);
        } else {
            statement = PySequence_GetItem(statements, ix_statement);
            if (statement == NULL) { Py_XDECREF(label_indexes); return NULL; }
        }
        PyObject *statement_key, *statement_body;
        if (!dict_first_pair(statement, &statement_key, &statement_body)) {
            Py_DECREF(statement);
            Py_XDECREF(label_indexes);
            PyErr_SetString(PyExc_RuntimeError, "empty statement dict");
            return NULL;
        }

        /* Increment statement count */
        PyObject *count_obj = PyDict_GetItemWithError(options, KS_statementCount);
        long long stmt_count;
        if (count_obj == NULL) {
            if (PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            stmt_count = 1;
        } else {
            stmt_count = PyLong_AsLongLong(count_obj);
            if (stmt_count == -1 && PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            stmt_count += 1;
        }
        PyObject *new_count = PyLong_FromLongLong(stmt_count);
        if (new_count == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
        if (PyDict_SetItem(options, KS_statementCount, new_count) < 0) {
            Py_DECREF(new_count); Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
        }
        Py_DECREF(new_count);

        if (max_statements > 0 && stmt_count > max_statements) {
            char buf[128];
            snprintf(buf, sizeof(buf), "Exceeded maximum script statements (%lld)", max_statements);
            raise_runtime_error(script, statement, buf);
            Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
        }

        if (has_coverage) {
            if (record_coverage_fast(&covered_dict, script, coverage_global, statement, statement_key) < 0) {
                Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
            }
        }

        /* Dispatch */
        if (KS_EQ(statement_key, KS_expr)) {
            PyObject *expr_dict = statement_body;
            PyObject *inner = PyDict_GetItemWithError(expr_dict, KS_expr);
            if (inner == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return PyErr_Occurred() ? NULL : Py_NewRef(Py_None); }
            PyObject *value = evaluate_expression(inner, options, locals_, 0, script, statement);
            if (value == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            PyObject *name = PyDict_GetItemWithError(expr_dict, KS_name);
            if (name == NULL && PyErr_Occurred()) { Py_DECREF(value); Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            if (name != NULL) {
                PyObject *target = (locals_ != NULL && locals_ != Py_None) ? locals_ : globals_;
                if (PyDict_SetItem(target, name, value) < 0) {
                    Py_DECREF(value); Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
                }
            }
            Py_DECREF(value);
        } else if (KS_EQ(statement_key, KS_jump)) {
            PyObject *jump_dict = statement_body;
            PyObject *jump_expr = PyDict_GetItemWithError(jump_dict, KS_expr);
            if (jump_expr == NULL && PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            int do_jump = 1;
            if (jump_expr != NULL) {
                PyObject *v = evaluate_expression(jump_expr, options, locals_, 0, script, statement);
                if (v == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
                do_jump = call_value_boolean(v);
                Py_DECREF(v);
                if (do_jump < 0) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            }
            if (do_jump) {
                PyObject *jump_label = PyDict_GetItemWithError(jump_dict, KS_label);
                if (jump_label == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return PyErr_Occurred() ? NULL : Py_NewRef(Py_None); }
                Py_ssize_t ix_label = -1;
                if (label_indexes != NULL) {
                    PyObject *cached = PyDict_GetItemWithError(label_indexes, jump_label);
                    if (cached == NULL && PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
                    if (cached != NULL) {
                        ix_label = PyLong_AsSsize_t(cached);
                        if (ix_label == -1 && PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
                    }
                }
                if (ix_label < 0) {
                    /* Scan for label */
                    for (Py_ssize_t i = 0; i < statements_length; i++) {
                        PyObject *st = PyList_Check(statements) ?
                            PyList_GET_ITEM(statements, i) : PySequence_GetItem(statements, i);
                        if (st == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
                        PyObject *lab = PyDict_GetItemWithError(st, KS_label);
                        if (!PyList_Check(statements)) Py_DECREF(st);
                        if (lab == NULL) {
                            if (PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
                            continue;
                        }
                        PyObject *lab_name = PyDict_GetItemWithError(lab, KS_name);
                        if (lab_name == NULL) { if (PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; } continue; }
                        if (PyObject_RichCompareBool(lab_name, jump_label, Py_EQ) == 1) {
                            ix_label = i;
                            break;
                        }
                    }
                    if (ix_label < 0) {
                        const char *lab_s = PyUnicode_AsUTF8(jump_label);
                        raise_runtime_error_fmt(script, statement, "Unknown jump label \"%s\"", lab_s ? lab_s : "");
                        Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
                    }
                    if (label_indexes == NULL) {
                        label_indexes = PyDict_New();
                        if (label_indexes == NULL) { Py_DECREF(statement); return NULL; }
                    }
                    PyObject *ix_obj = PyLong_FromSsize_t(ix_label);
                    if (ix_obj == NULL || PyDict_SetItem(label_indexes, jump_label, ix_obj) < 0) {
                        Py_XDECREF(ix_obj); Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
                    }
                    Py_DECREF(ix_obj);
                }
                ix_statement = ix_label;

                /* Record label statement coverage */
                if (has_coverage) {
                    PyObject *lst = PyList_Check(statements) ?
                        PyList_GET_ITEM(statements, ix_statement) : PySequence_GetItem(statements, ix_statement);
                    if (lst == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
                    if (!PyList_Check(statements)) {
                        /* lst new ref */
                    } else {
                        Py_INCREF(lst);
                    }
                    PyObject *lst_key = dict_first_key(lst);
                    if (lst_key != NULL) {
                        if (record_coverage_fast(&covered_dict, script, coverage_global, lst, lst_key) < 0) {
                            Py_DECREF(lst); Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
                        }
                    }
                    Py_DECREF(lst);
                }
            }
        } else if (KS_EQ(statement_key, KS_return)) {
            PyObject *ret = statement_body;
            PyObject *ret_expr = PyDict_GetItemWithError(ret, KS_expr);
            if (ret_expr == NULL && PyErr_Occurred()) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            PyObject *result;
            if (ret_expr != NULL) {
                result = evaluate_expression(ret_expr, options, locals_, 0, script, statement);
            } else {
                Py_INCREF(Py_None); result = Py_None;
            }
            Py_DECREF(statement); Py_XDECREF(label_indexes);
            return result;
        } else if (KS_EQ(statement_key, KS_function)) {
            PyObject *fn = statement_body;
            PyObject *fn_name = PyDict_GetItemWithError(fn, KS_name);
            if (fn_name == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return PyErr_Occurred() ? NULL : Py_NewRef(Py_None); }
            PyObject *sf = new_script_function(script, fn);
            if (sf == NULL) { Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL; }
            if (PyDict_SetItem(globals_, fn_name, sf) < 0) {
                Py_DECREF(sf); Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
            }
            Py_DECREF(sf);
        } else if (KS_EQ(statement_key, KS_include)) {
            PyObject *inc = statement_body;
            PyObject *system_prefix = PyDict_GetItemWithError(options, KS_systemPrefix);
            if (system_prefix == NULL && PyErr_Occurred()) goto include_err;
            PyObject *fetch_fn = PyDict_GetItemWithError(options, KS_fetchFn);
            if (fetch_fn == NULL && PyErr_Occurred()) goto include_err;
            PyObject *log_fn = PyDict_GetItemWithError(options, KS_logFn);
            if (log_fn == NULL && PyErr_Occurred()) goto include_err;
            PyObject *url_fn = PyDict_GetItemWithError(options, KS_urlFn);
            if (url_fn == NULL && PyErr_Occurred()) goto include_err;
            PyObject *includes_list = PyDict_GetItemWithError(inc, KS_includes);
            if (includes_list == NULL) { if (PyErr_Occurred()) goto include_err; goto include_end; }

            Py_ssize_t ilen = PyObject_Length(includes_list);
            if (ilen < 0) goto include_err;
            for (Py_ssize_t i = 0; i < ilen; i++) {
                PyObject *include;
                if (PyList_Check(includes_list)) {
                    include = PyList_GET_ITEM(includes_list, i);
                    Py_INCREF(include);
                } else {
                    include = PySequence_GetItem(includes_list, i);
                    if (include == NULL) goto include_err;
                }
                PyObject *include_url = PyDict_GetItemWithError(include, KS_url);
                if (include_url == NULL) { Py_DECREF(include); if (PyErr_Occurred()) goto include_err; continue; }
                Py_INCREF(include_url);

                PyObject *system_include = PyDict_GetItemWithError(include, KS_system);
                if (system_include == NULL && PyErr_Occurred()) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                int is_sys = (system_include != NULL) ? PyObject_IsTrue(system_include) : 0;
                if (is_sys < 0) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }

                if (is_sys && system_prefix != NULL) {
                    PyObject *vc_args[2] = {system_prefix, include_url};
                    PyObject *new_url = PyObject_Vectorcall(g_url_file_relative, vc_args, 2, NULL);
                    if (new_url == NULL) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                    Py_DECREF(include_url); include_url = new_url;
                } else if (url_fn != NULL) {
                    PyObject *new_url = PyObject_CallOneArg(url_fn, include_url);
                    if (new_url == NULL) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                    Py_DECREF(include_url); include_url = new_url;
                }

                /* global_includes */
                PyObject *global_includes = PyDict_GetItemWithError(globals_, g_SYSTEM_GLOBAL_INCLUDES_NAME);
                if (global_includes == NULL && PyErr_Occurred()) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                if (global_includes == NULL || !PyDict_Check(global_includes)) {
                    global_includes = PyDict_New();
                    if (global_includes == NULL) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                    if (PyDict_SetItem(globals_, g_SYSTEM_GLOBAL_INCLUDES_NAME, global_includes) < 0) {
                        Py_DECREF(global_includes); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                    }
                    Py_DECREF(global_includes);
                    global_includes = PyDict_GetItemWithError(globals_, g_SYSTEM_GLOBAL_INCLUDES_NAME);
                    if (global_includes == NULL) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                }
                PyObject *already = PyDict_GetItemWithError(global_includes, include_url);
                if (already == NULL && PyErr_Occurred()) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                if (already != NULL && PyObject_IsTrue(already)) {
                    Py_DECREF(include_url); Py_DECREF(include); continue;
                }
                if (PyDict_SetItem(global_includes, include_url, Py_True) < 0) {
                    Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                }

                /* Fetch */
                PyObject *include_text = NULL;
                if (fetch_fn != NULL) {
                    PyObject *fetch_arg = PyDict_New();
                    if (fetch_arg == NULL) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                    if (PyDict_SetItem(fetch_arg, KS_url, include_url) < 0) {
                        Py_DECREF(fetch_arg); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                    }
                    include_text = PyObject_CallOneArg(fetch_fn, fetch_arg);
                    Py_DECREF(fetch_arg);
                    if (include_text == NULL) {
                        PyErr_Clear();
                    }
                }
                if (include_text == NULL || include_text == Py_None) {
                    Py_XDECREF(include_text);
                    const char *url_s = PyUnicode_AsUTF8(include_url);
                    raise_runtime_error_fmt(script, statement, "Include of \"%s\" failed", url_s ? url_s : "");
                    Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                }

                /* Parse */
                PyObject *one = PyLong_FromLong(1);
                if (one == NULL) { Py_DECREF(include_text); Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                PyObject *vc_args[3] = {include_text, one, include_url};
                PyObject *include_script = PyObject_Vectorcall(g_parse_script, vc_args, 3, NULL);
                Py_DECREF(one); Py_DECREF(include_text);
                if (include_script == NULL) { Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                if (is_sys) {
                    if (PyDict_SetItem(include_script, KS_system, Py_True) < 0) {
                        Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                    }
                }

                /* Execute */
                PyObject *include_options = PyDict_Copy(options);
                if (include_options == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                }
                PyObject *new_url_fn = PyObject_CallFunctionObjArgs(g_functools_partial, g_url_file_relative, include_url, NULL);
                if (new_url_fn == NULL || PyDict_SetItem(include_options, KS_urlFn, new_url_fn) < 0) {
                    Py_XDECREF(new_url_fn); Py_DECREF(include_options); Py_DECREF(include_script);
                    Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                }
                Py_DECREF(new_url_fn);

                PyObject *inc_statements = PyDict_GetItemWithError(include_script, KS_statements);
                if (inc_statements == NULL) {
                    if (PyErr_Occurred()) { Py_DECREF(include_options); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                    inc_statements = Py_None;
                }
                PyObject *exec_result = execute_script_helper(include_script, inc_statements, include_options, NULL);
                Py_DECREF(include_options);
                if (exec_result == NULL) {
                    Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                }
                Py_DECREF(exec_result);

                /* Lint */
                if (log_fn != NULL) {
                    PyObject *debug = PyDict_GetItemWithError(options, KS_debug);
                    if (debug == NULL && PyErr_Occurred()) {
                        Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                    }
                    int dbg = (debug != NULL) ? PyObject_IsTrue(debug) : 0;
                    if (dbg < 0) {
                        Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                    }
                    if (dbg) {
                        PyObject *vc_args2[2] = {include_script, globals_};
                        PyObject *warnings = PyObject_Vectorcall(g_lint_script, vc_args2, 2, NULL);
                        if (warnings == NULL) {
                            Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err;
                        }
                        Py_ssize_t wlen = PyObject_Length(warnings);
                        if (wlen > 0) {
                            const char *plural = wlen > 1 ? "s" : "";
                            PyObject *header = PyUnicode_FromFormat(
                                "BareScript: Include \"%U\" static analysis... %zd warning%s:",
                                include_url, wlen, plural);
                            if (header != NULL) {
                                PyObject *r = PyObject_CallOneArg(log_fn, header);
                                Py_XDECREF(r);
                                Py_DECREF(header);
                            }
                            for (Py_ssize_t wi = 0; wi < wlen; wi++) {
                                PyObject *w = PySequence_GetItem(warnings, wi);
                                if (w == NULL) { Py_DECREF(warnings); Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include); goto include_err; }
                                PyObject *msg = PyUnicode_FromFormat("BareScript: %U", w);
                                Py_DECREF(w);
                                if (msg != NULL) {
                                    PyObject *r = PyObject_CallOneArg(log_fn, msg);
                                    Py_XDECREF(r);
                                    Py_DECREF(msg);
                                }
                            }
                        }
                        Py_DECREF(warnings);
                    }
                }
                Py_DECREF(include_script); Py_DECREF(include_url); Py_DECREF(include);
            }
include_end:
            (void)0;
            goto include_done;
include_err:
            Py_DECREF(statement); Py_XDECREF(label_indexes); return NULL;
include_done:
            (void)0;
        }
        /* else: label statement — no action */

        Py_DECREF(statement);
        ix_statement += 1;
    }
    Py_XDECREF(label_indexes);
    Py_RETURN_NONE;
}


/* ---------- public: execute_script(script, options=None) ---------- */

static PyObject *py_execute_script(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"script", "options", NULL};
    PyObject *script = NULL;
    PyObject *options = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &script, &options)) return NULL;

    if (options == Py_None) {
        options = PyDict_New();
        if (options == NULL) return NULL;
    } else {
        if (!PyDict_Check(options)) {
            PyErr_SetString(PyExc_TypeError, "options must be a dict");
            return NULL;
        }
        Py_INCREF(options);
    }

    /* Create globals if absent */
    PyObject *globals_ = PyDict_GetItemWithError(options, KS_globals);
    if (globals_ == NULL) {
        if (PyErr_Occurred()) { Py_DECREF(options); return NULL; }
        globals_ = PyDict_New();
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
        if (PyDict_SetItem(options, KS_globals, globals_) < 0) {
            Py_DECREF(globals_); Py_DECREF(options); return NULL;
        }
        Py_DECREF(globals_);
        globals_ = PyDict_GetItemWithError(options, KS_globals);
        if (globals_ == NULL) { Py_DECREF(options); return NULL; }
    }

    /* Update globals with SCRIPT_FUNCTIONS (only items not already in globals) */
    {
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        while (PyDict_Next(g_SCRIPT_FUNCTIONS, &pos, &key, &value)) {
            int contains = PyDict_Contains(globals_, key);
            if (contains < 0) { Py_DECREF(options); return NULL; }
            if (!contains) {
                if (PyDict_SetItem(globals_, key, value) < 0) { Py_DECREF(options); return NULL; }
            }
        }
    }

    /* statementCount = 0 */
    PyObject *zero = PyLong_FromLong(0);
    if (zero == NULL || PyDict_SetItem(options, KS_statementCount, zero) < 0) {
        Py_XDECREF(zero); Py_DECREF(options); return NULL;
    }
    Py_DECREF(zero);

    PyObject *statements = PyDict_GetItemWithError(script, KS_statements);
    if (statements == NULL) {
        Py_DECREF(options);
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }
    PyObject *result = execute_script_helper(script, statements, options, NULL);
    Py_DECREF(options);
    return result;
}


/* ---------- public: evaluate_expression ---------- */

static PyObject *py_evaluate_expression(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"expr", "options", "locals_", "builtins", "script", "statement", NULL};
    PyObject *expr = NULL;
    PyObject *options = Py_None;
    PyObject *locals_ = Py_None;
    PyObject *builtins_obj = Py_True;
    PyObject *script = Py_None;
    PyObject *statement = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OOOOO", kwlist,
                                     &expr, &options, &locals_, &builtins_obj, &script, &statement))
        return NULL;
    int builtins = PyObject_IsTrue(builtins_obj);
    if (builtins < 0) return NULL;
    return evaluate_expression(expr, options, locals_, builtins, script, statement);
}


/* ---------- module init ---------- */

static PyMethodDef runtime_c_methods[] = {
    {"execute_script", (PyCFunction)py_execute_script, METH_VARARGS | METH_KEYWORDS,
     "Execute a BareScript model."},
    {"evaluate_expression", (PyCFunction)py_evaluate_expression, METH_VARARGS | METH_KEYWORDS,
     "Evaluate a BareScript expression model."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef runtime_c_module = {
    PyModuleDef_HEAD_INIT,
    "runtime_c",
    "BareScript runtime, C implementation",
    -1,
    runtime_c_methods,
};

/* Helper: import attr `name` from module `mod_name`. Returns new ref or NULL. */
static PyObject *import_attr(const char *mod_name, const char *attr_name)
{
    PyObject *mod = PyImport_ImportModule(mod_name);
    if (mod == NULL) return NULL;
    PyObject *attr = PyObject_GetAttrString(mod, attr_name);
    Py_DECREF(mod);
    return attr;
}

#define INTERN_KS(var, str) do { \
    var = PyUnicode_InternFromString(str); \
    if (var == NULL) return NULL; \
} while (0)

PyMODINIT_FUNC PyInit_runtime_c(void)
{
    if (PyType_Ready(&ScriptFunctionType) < 0) return NULL;

    PyObject *m = PyModule_Create(&runtime_c_module);
    if (m == NULL) return NULL;

    /* Imports */
    g_BareScriptRuntimeError = import_attr("bare_script.runtime", "BareScriptRuntimeError");
    if (g_BareScriptRuntimeError == NULL) return NULL;
    g_SCRIPT_FUNCTIONS = import_attr("bare_script.library", "SCRIPT_FUNCTIONS");
    if (g_SCRIPT_FUNCTIONS == NULL) return NULL;
    g_EXPRESSION_FUNCTIONS = import_attr("bare_script.library", "EXPRESSION_FUNCTIONS");
    if (g_EXPRESSION_FUNCTIONS == NULL) return NULL;
    g_lint_script = import_attr("bare_script.model", "lint_script");
    if (g_lint_script == NULL) return NULL;
    g_url_file_relative = import_attr("bare_script.options", "url_file_relative");
    if (g_url_file_relative == NULL) return NULL;
    g_parse_script = import_attr("bare_script.parser", "parse_script");
    if (g_parse_script == NULL) return NULL;
    g_ValueArgsError = import_attr("bare_script.value", "ValueArgsError");
    if (g_ValueArgsError == NULL) return NULL;
    g_value_boolean = import_attr("bare_script.value", "value_boolean");
    g_value_compare = import_attr("bare_script.value", "value_compare");
    g_value_normalize_datetime = import_attr("bare_script.value", "value_normalize_datetime");
    g_value_round_number = import_attr("bare_script.value", "value_round_number");
    g_value_string = import_attr("bare_script.value", "value_string");
    if (!g_value_boolean || !g_value_compare || !g_value_normalize_datetime ||
        !g_value_round_number || !g_value_string) return NULL;
    g_datetime_date = import_attr("datetime", "date");
    g_datetime_timedelta = import_attr("datetime", "timedelta");
    if (!g_datetime_date || !g_datetime_timedelta) return NULL;
    g_functools_partial = import_attr("functools", "partial");
    if (g_functools_partial == NULL) return NULL;

    g_DEFAULT_MAX_STATEMENTS = PyFloat_FromDouble(1e9);
    if (g_DEFAULT_MAX_STATEMENTS == NULL) return NULL;
    if (PyModule_AddObject(m, "DEFAULT_MAX_STATEMENTS",
                           Py_NewRef(g_DEFAULT_MAX_STATEMENTS)) < 0) return NULL;
    g_SYSTEM_GLOBAL_COVERAGE_NAME = PyUnicode_InternFromString("__barescriptCoverage");
    g_SYSTEM_GLOBAL_INCLUDES_NAME = PyUnicode_InternFromString("__barescriptIncludes");
    if (!g_SYSTEM_GLOBAL_COVERAGE_NAME || !g_SYSTEM_GLOBAL_INCLUDES_NAME) return NULL;
    if (PyModule_AddObject(m, "SYSTEM_GLOBAL_COVERAGE_NAME",
                           Py_NewRef(g_SYSTEM_GLOBAL_COVERAGE_NAME)) < 0) return NULL;
    if (PyModule_AddObject(m, "SYSTEM_GLOBAL_INCLUDES_NAME",
                           Py_NewRef(g_SYSTEM_GLOBAL_INCLUDES_NAME)) < 0) return NULL;

    /* Intern keys */
    INTERN_KS(KS_expr, "expr");
    INTERN_KS(KS_jump, "jump");
    INTERN_KS(KS_return, "return");
    INTERN_KS(KS_function, "function");
    INTERN_KS(KS_include, "include");
    INTERN_KS(KS_label, "label");
    INTERN_KS(KS_name, "name");
    INTERN_KS(KS_args, "args");
    INTERN_KS(KS_globals, "globals");
    INTERN_KS(KS_statementCount, "statementCount");
    INTERN_KS(KS_maxStatements, "maxStatements");
    INTERN_KS(KS_statements, "statements");
    INTERN_KS(KS_systemPrefix, "systemPrefix");
    INTERN_KS(KS_fetchFn, "fetchFn");
    INTERN_KS(KS_logFn, "logFn");
    INTERN_KS(KS_urlFn, "urlFn");
    INTERN_KS(KS_url, "url");
    INTERN_KS(KS_system, "system");
    INTERN_KS(KS_includes, "includes");
    INTERN_KS(KS_debug, "debug");
    INTERN_KS(KS_scripts, "scripts");
    INTERN_KS(KS_covered, "covered");
    INTERN_KS(KS_count, "count");
    INTERN_KS(KS_enabled, "enabled");
    INTERN_KS(KS_script, "script");
    INTERN_KS(KS_statement, "statement");
    INTERN_KS(KS_scriptName, "scriptName");
    INTERN_KS(KS_lineNumber, "lineNumber");
    INTERN_KS(KS_lastArgArray, "lastArgArray");
    INTERN_KS(KS_binary, "binary");
    INTERN_KS(KS_unary, "unary");
    INTERN_KS(KS_variable, "variable");
    INTERN_KS(KS_number, "number");
    INTERN_KS(KS_string, "string");
    INTERN_KS(KS_group, "group");
    INTERN_KS(KS_left, "left");
    INTERN_KS(KS_right, "right");
    INTERN_KS(KS_op, "op");
    INTERN_KS(KS_null, "null");
    INTERN_KS(KS_true, "true");
    INTERN_KS(KS_false, "false");
    INTERN_KS(KS_if, "if");
    INTERN_KS(KS_op_amp, "&&");
    INTERN_KS(KS_op_pipe, "||");
    INTERN_KS(KS_op_plus, "+");
    INTERN_KS(KS_op_minus, "-");
    INTERN_KS(KS_op_star, "*");
    INTERN_KS(KS_op_slash, "/");
    INTERN_KS(KS_op_eq, "==");
    INTERN_KS(KS_op_ne, "!=");
    INTERN_KS(KS_op_le, "<=");
    INTERN_KS(KS_op_lt, "<");
    INTERN_KS(KS_op_ge, ">=");
    INTERN_KS(KS_op_gt, ">");
    INTERN_KS(KS_op_pct, "%");
    INTERN_KS(KS_op_pow, "**");
    INTERN_KS(KS_op_band, "&");
    INTERN_KS(KS_op_bor, "|");
    INTERN_KS(KS_op_bxor, "^");
    INTERN_KS(KS_op_shl, "<<");
    INTERN_KS(KS_op_shr, ">>");
    INTERN_KS(KS_op_not, "!");
    INTERN_KS(KS_op_tilde, "~");
    INTERN_KS(KS_return_value, "return_value");

    Py_INCREF((PyObject *)&ScriptFunctionType);
    if (PyModule_AddObject(m, "ScriptFunction", (PyObject *)&ScriptFunctionType) < 0) {
        Py_DECREF((PyObject *)&ScriptFunctionType);
        return NULL;
    }

    return m;
}
