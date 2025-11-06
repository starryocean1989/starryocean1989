/* -*- coding: utf-8 -*-
 * native_compute主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_compute.h"
#include "batch_hash.h"

/* 前向声明 */
extern PyObject* batch_compute_func(PyObject *self, PyObject *args);
extern PyObject* batch_hash_func(PyObject *self, PyObject *args);
extern PyObject* batch_get_price_func(PyObject *self, PyObject *args);

static PyMethodDef ComputeMethods[] = {
    {"batch_compute", batch_compute_func, METH_VARARGS, "Batch numerical operations"},
    {"batch_hash", batch_hash_func, METH_VARARGS, "Batch hash computation"},
    {"batch_get_price", batch_get_price_func, METH_VARARGS, "Batch get_price parsing for TDX"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_computemodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_compute",
    .m_doc = "Batch numerical operations and hash computation for Windows",
    .m_size = -1,
    .m_methods = ComputeMethods,
};

PyMODINIT_FUNC PyInit_native_compute(void) {
    return PyModule_Create(&native_computemodule);
}

