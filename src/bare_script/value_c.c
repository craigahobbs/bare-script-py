/* Licensed under the MIT License */
/* https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE */

/*
 * BareScript value utilities — C accelerated implementations of the helper
 * functions in bare_script.value. The pure-Python implementations stay in
 * value.py and are used as the fallback when this extension fails to build.
 *
 * Where the BareScript semantics require regex / JSON / datetime / schema
 * features beyond what's reasonable to recreate in C, the C function calls
 * back into a cached helper exposed by value.py (typically a "_*_py" private
 * symbol). The boundary is chosen so the C side handles the common-case fast
 * paths (numbers, strings, booleans, None, simple compares) and only delegates
 * to Python for full-fidelity edge cases.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stddef.h>


/* Cached references resolved at module init from value.py and stdlib */
static PyObject *g_re_compile = NULL;
static PyObject *g_re_pattern_type = NULL;
static PyObject *g_datetime_date_type = NULL;
static PyObject *g_datetime_datetime_type = NULL;
static PyObject *g_uuid_type = NULL;
static PyObject *g_json_dumps = NULL;
static PyObject *g_value_json_py = NULL;              /* pure-Python value_json fallback */
static PyObject *g_value_string_py = NULL;            /* pure-Python value_string fallback */
static PyObject *g_value_compare_py = NULL;           /* pure-Python value_compare fallback */
static PyObject *g_value_parse_datetime_py = NULL;    /* pure-Python value_parse_datetime fallback */
static PyObject *g_r_number_cleanup_sub = NULL;       /* re.compile(r'\.0*$').sub */

/* Frequently-used interned strings */
static PyObject *g_str_null = NULL;
static PyObject *g_str_true = NULL;
static PyObject *g_str_false = NULL;
static PyObject *g_str_string = NULL;
static PyObject *g_str_boolean = NULL;
static PyObject *g_str_number = NULL;
static PyObject *g_str_datetime = NULL;
static PyObject *g_str_object = NULL;
static PyObject *g_str_array = NULL;
static PyObject *g_str_function = NULL;
static PyObject *g_str_regex = NULL;
static PyObject *g_str_function_disp = NULL;          /* "<function>" */
static PyObject *g_str_regex_disp = NULL;             /* "<regex>" */
static PyObject *g_str_unknown_disp = NULL;           /* "<unknown>" */
static PyObject *g_str_empty = NULL;                  /* "" */


/* ---- helpers ---- */

/* Lazy-resolve a private symbol from bare_script.value. value.py imports
 * value_c at its top, so during PyInit_value_c the value.py module body
 * hasn't run yet — these symbols only become reachable after the first
 * value_c function call. Caches into *slot on success. */
static int
ensure_value_py_fallback(PyObject **slot, const char *attr)
{
    if (*slot != NULL) return 0;
    PyObject *vmod = PyImport_ImportModule("bare_script.value");
    if (vmod == NULL) return -1;
    PyObject *fn = PyObject_GetAttrString(vmod, attr);
    Py_DECREF(vmod);
    if (fn == NULL) return -1;
    *slot = fn;
    return 0;
}

static inline int
is_plain_int(PyObject *value)
{
    /* int but not bool */
    return PyLong_Check(value) && !PyBool_Check(value);
}

static inline int
is_plain_number(PyObject *value)
{
    if (PyBool_Check(value)) return 0;
    return PyLong_Check(value) || PyFloat_Check(value);
}

static int
is_regex(PyObject *value)
{
    if (g_re_pattern_type == NULL) return 0;
    int r = PyObject_IsInstance(value, g_re_pattern_type);
    return r == 1;
}

static int
is_datetime_any(PyObject *value)
{
    if (g_datetime_date_type == NULL) return 0;
    int r = PyObject_IsInstance(value, g_datetime_date_type);
    return r == 1;
}


/* ---- value_type ---- */

static PyObject *
c_value_type_impl(PyObject *value)
{
    if (value == Py_None) {
        Py_INCREF(g_str_null);
        return g_str_null;
    }
    if (PyUnicode_Check(value)) {
        Py_INCREF(g_str_string);
        return g_str_string;
    }
    if (PyBool_Check(value)) {
        Py_INCREF(g_str_boolean);
        return g_str_boolean;
    }
    if (PyLong_Check(value) || PyFloat_Check(value)) {
        Py_INCREF(g_str_number);
        return g_str_number;
    }
    if (is_datetime_any(value)) {
        Py_INCREF(g_str_datetime);
        return g_str_datetime;
    }
    if (PyDict_Check(value)) {
        Py_INCREF(g_str_object);
        return g_str_object;
    }
    if (PyList_Check(value)) {
        Py_INCREF(g_str_array);
        return g_str_array;
    }
    if (PyCallable_Check(value)) {
        Py_INCREF(g_str_function);
        return g_str_function;
    }
    if (is_regex(value)) {
        Py_INCREF(g_str_regex);
        return g_str_regex;
    }
    Py_RETURN_NONE;
}

static PyObject *
c_value_type(PyObject *self, PyObject *value)
{
    (void)self;
    return c_value_type_impl(value);
}


/* ---- value_boolean ---- */

static int
c_value_boolean_impl(PyObject *value)
{
    if (value == Py_None) return 0;
    if (value == Py_True) return 1;
    if (value == Py_False) return 0;
    if (PyBool_Check(value)) return PyObject_IsTrue(value);
    if (PyUnicode_Check(value)) return PyUnicode_GET_LENGTH(value) != 0;
    if (PyLong_Check(value)) return PyObject_IsTrue(value);
    if (PyFloat_Check(value)) return PyFloat_AS_DOUBLE(value) != 0.0;
    if (PyList_Check(value)) return PyList_GET_SIZE(value) != 0;
    /* dict, datetime, regex, callable, etc — non-null is True */
    return 1;
}

static PyObject *
c_value_boolean(PyObject *self, PyObject *value)
{
    (void)self;
    int b = c_value_boolean_impl(value);
    if (b < 0) return NULL;
    return PyBool_FromLong(b);
}


/* ---- value_is ---- */

static PyObject *
c_value_is(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *v1, *v2;
    if (!PyArg_ParseTuple(args, "OO", &v1, &v2)) return NULL;

    /* Numbers compare by value (matching the Python semantics). */
    if (is_plain_number(v1) && is_plain_number(v2)) {
        int eq = PyObject_RichCompareBool(v1, v2, Py_EQ);
        if (eq < 0) return NULL;
        return PyBool_FromLong(eq);
    }
    return PyBool_FromLong(v1 == v2);
}


/* ---- value_compare ---- */

static long c_value_compare_long(PyObject *left, PyObject *right);

/* Returns a new tuple-of-(key,value) sorted-list. Pure C path so we don't
 * depend on Python sorted() each call. */
static PyObject *
sorted_dict_items(PyObject *d)
{
    PyObject *items = PyDict_Items(d);
    if (items == NULL) return NULL;
    if (PyList_Sort(items) < 0) {
        Py_DECREF(items);
        return NULL;
    }
    return items;
}

static long
c_value_compare_long(PyObject *left, PyObject *right)
{
    /* None */
    if (left == Py_None) return (right == Py_None) ? 0 : -1;
    if (right == Py_None) return 1;

    /* str-vs-str */
    if (PyUnicode_Check(left) && PyUnicode_Check(right)) {
        int c = PyUnicode_Compare(left, right);
        if (c == -1 && PyErr_Occurred()) return -2;
        return (c < 0) ? -1 : (c > 0 ? 1 : 0);
    }

    /* bool-vs-bool */
    if (PyBool_Check(left) && PyBool_Check(right)) {
        return (left == right) ? 0 : (left == Py_False ? -1 : 1);
    }

    /* number-vs-number (excluding bool) */
    if (is_plain_number(left) && is_plain_number(right)) {
        int lt = PyObject_RichCompareBool(left, right, Py_LT);
        if (lt < 0) return -2;
        if (lt) return -1;
        int eq = PyObject_RichCompareBool(left, right, Py_EQ);
        if (eq < 0) return -2;
        return eq ? 0 : 1;
    }

    /* datetime-vs-datetime: normalize then compare */
    if (is_datetime_any(left) && is_datetime_any(right)) {
        /* Delegate to Python value_compare for full-fidelity normalization
         * (timezone awareness is non-trivial to replicate). */
        if (ensure_value_py_fallback(&g_value_compare_py, "_value_compare_py") < 0) return -2;
        PyObject *r = PyObject_CallFunctionObjArgs(g_value_compare_py, left, right, NULL);
        if (r == NULL) return -2;
        long v = PyLong_AsLong(r);
        Py_DECREF(r);
        if (v == -1 && PyErr_Occurred()) return -2;
        return v;
    }

    /* list-vs-list: lexicographic */
    if (PyList_Check(left) && PyList_Check(right)) {
        Py_ssize_t llen = PyList_GET_SIZE(left);
        Py_ssize_t rlen = PyList_GET_SIZE(right);
        Py_ssize_t n = llen < rlen ? llen : rlen;
        for (Py_ssize_t i = 0; i < n; i++) {
            long c = c_value_compare_long(PyList_GET_ITEM(left, i),
                                          PyList_GET_ITEM(right, i));
            if (c == -2) return -2;
            if (c != 0) return c;
        }
        if (llen < rlen) return -1;
        if (llen > rlen) return 1;
        return 0;
    }

    /* dict-vs-dict: sort items, lexicographic */
    if (PyDict_Check(left) && PyDict_Check(right)) {
        PyObject *li = sorted_dict_items(left);
        if (li == NULL) return -2;
        PyObject *ri = sorted_dict_items(right);
        if (ri == NULL) {
            Py_DECREF(li);
            return -2;
        }
        Py_ssize_t llen = PyList_GET_SIZE(li);
        Py_ssize_t rlen = PyList_GET_SIZE(ri);
        Py_ssize_t n = llen < rlen ? llen : rlen;
        long result = 0;
        for (Py_ssize_t i = 0; i < n && result == 0; i++) {
            PyObject *l_pair = PyList_GET_ITEM(li, i);
            PyObject *r_pair = PyList_GET_ITEM(ri, i);
            long kc = c_value_compare_long(PyTuple_GET_ITEM(l_pair, 0),
                                           PyTuple_GET_ITEM(r_pair, 0));
            if (kc == -2) { Py_DECREF(li); Py_DECREF(ri); return -2; }
            if (kc != 0) { result = kc; break; }
            long vc = c_value_compare_long(PyTuple_GET_ITEM(l_pair, 1),
                                           PyTuple_GET_ITEM(r_pair, 1));
            if (vc == -2) { Py_DECREF(li); Py_DECREF(ri); return -2; }
            if (vc != 0) { result = vc; break; }
        }
        Py_DECREF(li);
        Py_DECREF(ri);
        if (result != 0) return result;
        if (llen < rlen) return -1;
        if (llen > rlen) return 1;
        return 0;
    }

    /* Fall back to type-name comparison (matches Python value_compare's
     * "invalid comparison" branch). */
    PyObject *t1 = c_value_type_impl(left);
    if (t1 == NULL) return -2;
    if (t1 == Py_None) {
        Py_DECREF(t1);
        t1 = PyUnicode_FromString("unknown");
        if (t1 == NULL) return -2;
    }
    PyObject *t2 = c_value_type_impl(right);
    if (t2 == NULL) { Py_DECREF(t1); return -2; }
    if (t2 == Py_None) {
        Py_DECREF(t2);
        t2 = PyUnicode_FromString("unknown");
        if (t2 == NULL) { Py_DECREF(t1); return -2; }
    }
    int c = PyUnicode_Compare(t1, t2);
    Py_DECREF(t1);
    Py_DECREF(t2);
    if (c == -1 && PyErr_Occurred()) return -2;
    return (c < 0) ? -1 : (c > 0 ? 1 : 0);
}

static PyObject *
c_value_compare(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *left, *right;
    if (!PyArg_ParseTuple(args, "OO", &left, &right)) return NULL;
    long r = c_value_compare_long(left, right);
    if (r == -2) return NULL;
    return PyLong_FromLong(r);
}


/* ---- value_string ---- */

static PyObject *
c_value_string_impl(PyObject *value)
{
    if (value == Py_None) {
        Py_INCREF(g_str_null);
        return g_str_null;
    }
    if (PyUnicode_Check(value)) {
        Py_INCREF(value);
        return value;
    }
    if (value == Py_True) {
        Py_INCREF(g_str_true);
        return g_str_true;
    }
    if (value == Py_False) {
        Py_INCREF(g_str_false);
        return g_str_false;
    }
    if (PyBool_Check(value)) {
        /* Py_True / Py_False are handled via pointer-compare above; this only
         * fires for bool subclasses (uncommon). */
        int t = PyObject_IsTrue(value);
        if (t < 0) return NULL;
        PyObject *r = t ? g_str_true : g_str_false;
        Py_INCREF(r);
        return r;
    }
    if (is_plain_int(value)) {
        return PyObject_Str(value);
    }
    if (PyFloat_Check(value)) {
        /* str(float) then strip trailing ".0*". Use the cached re.sub bound
         * method for the cleanup so semantics match the Python implementation. */
        PyObject *s = PyObject_Str(value);
        if (s == NULL) return NULL;
        PyObject *cleaned = PyObject_CallFunctionObjArgs(g_r_number_cleanup_sub,
                                                          g_str_empty, s, NULL);
        Py_DECREF(s);
        return cleaned;
    }
    if (is_datetime_any(value)) {
        /* Datetime formatting is intricate (timezone normalization +
         * microsecond → millisecond truncation + suffix scrubbing). Defer
         * to the Python implementation. */
        if (ensure_value_py_fallback(&g_value_string_py, "_value_string_py") < 0) return NULL;
        return PyObject_CallOneArg(g_value_string_py, value);
    }
    if (PyDict_Check(value) || PyList_Check(value)) {
        if (ensure_value_py_fallback(&g_value_json_py, "_value_json_py") < 0) return NULL;
        return PyObject_CallOneArg(g_value_json_py, value);
    }
    if (PyCallable_Check(value)) {
        Py_INCREF(g_str_function_disp);
        return g_str_function_disp;
    }
    if (is_regex(value)) {
        Py_INCREF(g_str_regex_disp);
        return g_str_regex_disp;
    }
    if (g_uuid_type != NULL) {
        int u = PyObject_IsInstance(value, g_uuid_type);
        if (u < 0) return NULL;
        if (u == 1) return PyObject_Str(value);
    }
    Py_INCREF(g_str_unknown_disp);
    return g_str_unknown_disp;
}

static PyObject *
c_value_string(PyObject *self, PyObject *value)
{
    (void)self;
    return c_value_string_impl(value);
}


/* ---- value_json ---- */

static PyObject *
c_value_json(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    /* Minimal wrapper: the JSON encoding details (sort_keys, separators,
     * trailing-zero cleanup, _JSONEncoder.default for datetime/callable) are
     * intricate enough that we delegate to the Python implementation. */
    if (ensure_value_py_fallback(&g_value_json_py, "_value_json_py") < 0) return NULL;
    return PyObject_Call(g_value_json_py, args, kwargs);
}


/* ---- value_round_number ---- */

static PyObject *
c_value_round_number(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *value;
    PyObject *digits;
    if (!PyArg_ParseTuple(args, "OO", &value, &digits)) return NULL;
    if (!is_plain_number(value)) {
        PyErr_SetString(PyExc_TypeError, "value must be int or float");
        return NULL;
    }
    /* digits can be int or float (matching `10 ** digits` semantics). */
    double d_double;
    if (PyFloat_Check(digits)) {
        d_double = PyFloat_AS_DOUBLE(digits);
    } else if (PyLong_Check(digits) && !PyBool_Check(digits)) {
        d_double = (double)PyLong_AsLongLong(digits);
        if (PyErr_Occurred()) return NULL;
    } else {
        PyErr_SetString(PyExc_TypeError, "digits must be int or float");
        return NULL;
    }

    double v = PyFloat_Check(value) ? PyFloat_AS_DOUBLE(value)
                                    : (double)PyLong_AsLongLong(value);
    if (PyErr_Occurred()) return NULL;

    /* multiplier = 10 ** digits — use pow() for non-integer digits */
    double mult;
    if (d_double == (double)(long long)d_double) {
        long long d_int = (long long)d_double;
        mult = 1.0;
        if (d_int >= 0) {
            for (long long i = 0; i < d_int; i++) mult *= 10.0;
        } else {
            for (long long i = 0; i < -d_int; i++) mult /= 10.0;
        }
    } else {
        /* Match Python's `10 ** digits` for non-integer digits. Use pow(). */
        PyObject *ten = PyLong_FromLong(10);
        if (ten == NULL) return NULL;
        PyObject *mult_obj = PyNumber_Power(ten, digits, Py_None);
        Py_DECREF(ten);
        if (mult_obj == NULL) return NULL;
        mult = PyFloat_AsDouble(mult_obj);
        Py_DECREF(mult_obj);
        if (mult == -1.0 && PyErr_Occurred()) return NULL;
    }
    double scaled = v * mult + (v >= 0 ? 0.5 : -0.5);
    /* Match `int(value * multiplier + (0.5 if value >= 0 else -0.5)) / multiplier`. */
    long long truncated = (long long)scaled;
    double result = (double)truncated / mult;
    return PyFloat_FromDouble(result);
}


/* ---- value_parse_number ---- */

static PyObject *
c_value_parse_number(PyObject *self, PyObject *text)
{
    (void)self;
    if (!PyUnicode_Check(text)) {
        PyErr_SetString(PyExc_TypeError, "text must be str");
        return NULL;
    }
    /* Use Python float() to match semantics including subnormal handling. */
    PyObject *f = PyFloat_FromString(text);
    if (f == NULL) {
        PyErr_Clear();
        Py_RETURN_NONE;
    }
    double d = PyFloat_AS_DOUBLE(f);
    /* Reject NaN and infinities (matches the Python implementation). */
    if (d != d || (d == d * 0.5 && d != 0.0)) {
        Py_DECREF(f);
        Py_RETURN_NONE;
    }
    return f;
}


/* ---- value_parse_integer ---- */

static PyObject *
c_value_parse_integer(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *text;
    PyObject *radix = NULL;
    if (!PyArg_ParseTuple(args, "O|O", &text, &radix)) return NULL;
    if (radix == NULL) {
        radix = PyLong_FromLong(10);
        if (radix == NULL) return NULL;
    } else {
        Py_INCREF(radix);
    }
    PyObject *result = PyObject_CallFunctionObjArgs((PyObject *)&PyLong_Type, text, radix, NULL);
    Py_DECREF(radix);
    if (result == NULL) {
        PyErr_Clear();
        Py_RETURN_NONE;
    }
    return result;
}


/* ---- value_parse_datetime ---- */

static PyObject *
c_value_parse_datetime(PyObject *self, PyObject *text)
{
    (void)self;
    /* The regex / fromisoformat / timezone pipeline is intricate; delegate
     * to the Python fallback for full fidelity. */
    if (ensure_value_py_fallback(&g_value_parse_datetime_py, "_value_parse_datetime_py") < 0) return NULL;
    return PyObject_CallOneArg(g_value_parse_datetime_py, text);
}


/* ---- value_normalize_datetime ---- */

static PyObject *
c_value_normalize_datetime(PyObject *self, PyObject *value)
{
    (void)self;
    if (g_datetime_datetime_type == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "datetime types not initialized");
        return NULL;
    }
    int is_dt = PyObject_IsInstance(value, g_datetime_datetime_type);
    if (is_dt < 0) return NULL;
    if (is_dt == 1) {
        PyObject *tzinfo = PyObject_GetAttrString(value, "tzinfo");
        if (tzinfo == NULL) return NULL;
        int tz_set = (tzinfo != Py_None);
        Py_DECREF(tzinfo);
        if (!tz_set) {
            Py_INCREF(value);
            return value;
        }
        /* tz-aware: convert to local then strip tzinfo via .replace(tzinfo=None) */
        PyObject *local_dt = PyObject_CallMethod(value, "astimezone", NULL);
        if (local_dt == NULL) return NULL;
        PyObject *empty_args = PyTuple_New(0);
        PyObject *kw = PyDict_New();
        if (empty_args == NULL || kw == NULL) {
            Py_XDECREF(empty_args); Py_XDECREF(kw); Py_DECREF(local_dt);
            return NULL;
        }
        if (PyDict_SetItemString(kw, "tzinfo", Py_None) < 0) {
            Py_DECREF(empty_args); Py_DECREF(kw); Py_DECREF(local_dt);
            return NULL;
        }
        PyObject *replace = PyObject_GetAttrString(local_dt, "replace");
        Py_DECREF(local_dt);
        if (replace == NULL) { Py_DECREF(empty_args); Py_DECREF(kw); return NULL; }
        PyObject *result = PyObject_Call(replace, empty_args, kw);
        Py_DECREF(replace);
        Py_DECREF(empty_args);
        Py_DECREF(kw);
        return result;
    }
    /* date (not datetime): build datetime(value.year, value.month, value.day) */
    PyObject *year = PyObject_GetAttrString(value, "year");
    if (year == NULL) return NULL;
    PyObject *month = PyObject_GetAttrString(value, "month");
    if (month == NULL) { Py_DECREF(year); return NULL; }
    PyObject *day = PyObject_GetAttrString(value, "day");
    if (day == NULL) { Py_DECREF(year); Py_DECREF(month); return NULL; }
    PyObject *result = PyObject_CallFunctionObjArgs(g_datetime_datetime_type, year, month, day, NULL);
    Py_DECREF(year);
    Py_DECREF(month);
    Py_DECREF(day);
    return result;
}


/* ---- module setup ---- */

static PyMethodDef ValueCMethods[] = {
    {"value_type", c_value_type, METH_O, "Get a value's type string"},
    {"value_boolean", c_value_boolean, METH_O, "Interpret value as boolean"},
    {"value_is", c_value_is, METH_VARARGS, "Test value identity (numbers compare by value)"},
    {"value_compare", c_value_compare, METH_VARARGS, "Compare two values"},
    {"value_string", c_value_string, METH_O, "Get a value's string representation"},
    {"value_json", (PyCFunction)(void(*)(void))c_value_json, METH_VARARGS | METH_KEYWORDS, "Get a value's JSON string representation"},
    {"value_round_number", c_value_round_number, METH_VARARGS, "Round a number"},
    {"value_parse_number", c_value_parse_number, METH_O, "Parse a number string"},
    {"value_parse_integer", c_value_parse_integer, METH_VARARGS, "Parse an integer string"},
    {"value_parse_datetime", c_value_parse_datetime, METH_O, "Parse a datetime string"},
    {"value_normalize_datetime", c_value_normalize_datetime, METH_O, "Normalize a datetime value"},
    {NULL, NULL, 0, NULL}
};


static struct PyModuleDef value_c_module = {
    PyModuleDef_HEAD_INIT,
    "bare_script.value_c",
    "BareScript value utilities (C extension)",
    -1,
    ValueCMethods,
    NULL, NULL, NULL, NULL
};


static int
init_string(PyObject **dest, const char *str)
{
    *dest = PyUnicode_InternFromString(str);
    return *dest == NULL ? -1 : 0;
}


PyMODINIT_FUNC
PyInit_value_c(void)
{
    PyObject *module = PyModule_Create(&value_c_module);
    if (module == NULL) return NULL;

    /* Cached display strings */
    if (init_string(&g_str_null, "null") < 0) goto error;
    if (init_string(&g_str_true, "true") < 0) goto error;
    if (init_string(&g_str_false, "false") < 0) goto error;
    if (init_string(&g_str_string, "string") < 0) goto error;
    if (init_string(&g_str_boolean, "boolean") < 0) goto error;
    if (init_string(&g_str_number, "number") < 0) goto error;
    if (init_string(&g_str_datetime, "datetime") < 0) goto error;
    if (init_string(&g_str_object, "object") < 0) goto error;
    if (init_string(&g_str_array, "array") < 0) goto error;
    if (init_string(&g_str_function, "function") < 0) goto error;
    if (init_string(&g_str_regex, "regex") < 0) goto error;
    if (init_string(&g_str_function_disp, "<function>") < 0) goto error;
    if (init_string(&g_str_regex_disp, "<regex>") < 0) goto error;
    if (init_string(&g_str_unknown_disp, "<unknown>") < 0) goto error;
    if (init_string(&g_str_empty, "") < 0) goto error;

    /* re module */
    PyObject *re_mod = PyImport_ImportModule("re");
    if (re_mod == NULL) goto error;
    g_re_compile = PyObject_GetAttrString(re_mod, "compile");
    PyObject *empty_pattern = PyObject_CallFunction(g_re_compile, "s", "");
    Py_DECREF(re_mod);
    if (g_re_compile == NULL || empty_pattern == NULL) {
        Py_XDECREF(empty_pattern);
        goto error;
    }
    g_re_pattern_type = (PyObject *)Py_TYPE(empty_pattern);
    Py_INCREF(g_re_pattern_type);
    Py_DECREF(empty_pattern);

    /* Compile R_NUMBER_CLEANUP and bind its .sub method */
    PyObject *r_cleanup = PyObject_CallFunction(g_re_compile, "s", "\\.0*$");
    if (r_cleanup == NULL) goto error;
    g_r_number_cleanup_sub = PyObject_GetAttrString(r_cleanup, "sub");
    Py_DECREF(r_cleanup);
    if (g_r_number_cleanup_sub == NULL) goto error;

    /* datetime module */
    PyObject *dt_mod = PyImport_ImportModule("datetime");
    if (dt_mod == NULL) goto error;
    g_datetime_date_type = PyObject_GetAttrString(dt_mod, "date");
    g_datetime_datetime_type = PyObject_GetAttrString(dt_mod, "datetime");
    Py_DECREF(dt_mod);
    if (g_datetime_date_type == NULL || g_datetime_datetime_type == NULL) goto error;

    /* uuid module */
    PyObject *uuid_mod = PyImport_ImportModule("uuid");
    if (uuid_mod == NULL) {
        PyErr_Clear();
    } else {
        g_uuid_type = PyObject_GetAttrString(uuid_mod, "UUID");
        Py_DECREF(uuid_mod);
        if (g_uuid_type == NULL) PyErr_Clear();
    }

    /* json module */
    PyObject *json_mod = PyImport_ImportModule("json");
    if (json_mod == NULL) goto error;
    g_json_dumps = PyObject_GetAttrString(json_mod, "dumps");
    Py_DECREF(json_mod);
    if (g_json_dumps == NULL) goto error;

    /* Pure-Python fallbacks from value.py are resolved lazily on first use
     * to break the import cycle (value.py imports value_c at its top, so
     * value.py's symbols don't exist yet during PyInit_value_c). See
     * ensure_value_py_fallback below. */

    return module;

error:
    Py_DECREF(module);
    return NULL;
}
