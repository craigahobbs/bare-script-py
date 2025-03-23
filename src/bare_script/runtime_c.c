#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyObject* parse_script(PyObject* self, PyObject* args) {
    const char* script;
    Py_ssize_t length;

    if (!PyArg_ParseTuple(args, "s", &script)) {
        return NULL;  // Failed to parse arguments
    }

    // Duplicate runtime.py's functionality (example: return length)
    length = strlen(script);
    return PyLong_FromSsize_t(length);
}

static PyMethodDef RuntimeMethods[] = {
    {"parse_script", parse_script, METH_VARARGS, "Parse a script and return its length."},
    {NULL, NULL, 0, NULL}  // Sentinel
};

static struct PyModuleDef runtimemodule = {
    PyModuleDef_HEAD_INIT,
    "runtime_c",  // Module name with _c suffix
    NULL,         // Module documentation
    -1,           // Size of per-interpreter state
    RuntimeMethods
};

PyMODINIT_FUNC PyInit_runtime_c(void) {
    return PyModule_Create(&runtimemodule);
}
