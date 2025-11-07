/* -*- coding: utf-8 -*-
 * native_compute主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_compute.h"
#include "batch_hash.h"
#include "batch_date.h"

/* 前向声明 */
extern PyObject* batch_compute_func(PyObject *self, PyObject *args);
extern PyObject* batch_hash_func(PyObject *self, PyObject *args);
extern PyObject* batch_get_price_func(PyObject *self, PyObject *args);
extern PyObject* batch_validate_iso_dates(PyObject *self, PyObject *args);
extern PyObject* batch_compare_dates(PyObject *self, PyObject *args);
extern PyObject* prefix_sum_scale_func(PyObject *self, PyObject *args);

static PyMethodDef ComputeMethods[] = {
    {"batch_compute", batch_compute_func, METH_VARARGS, "Batch numerical operations"},
    {"batch_hash", batch_hash_func, METH_VARARGS, "Batch hash computation"},
    {"batch_get_price", batch_get_price_func, METH_VARARGS, "Batch get_price parsing for TDX"},
    {"batch_validate_iso_dates", batch_validate_iso_dates, METH_VARARGS, "Batch validate ISO date strings"},
    {"batch_compare_dates", batch_compare_dates, METH_VARARGS, "Batch compare dates with reference"},
    {"prefix_sum_scale", prefix_sum_scale_func, METH_VARARGS, "Prefix sum with scaling for price diffs"},
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

