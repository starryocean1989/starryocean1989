/* -*- coding: utf-8 -*-
 * native_serialization主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_serialize.h"
#include "zero_copy_serialize.h"

/* 前向声明 */
extern PyObject* batch_serialize_func(PyObject *self, PyObject *args);
extern PyObject* batch_deserialize_func(PyObject *self, PyObject *args);
extern PyObject* zero_copy_serialize_func(PyObject *self, PyObject *args);

static PyMethodDef SerializationMethods[] = {
    {"batch_serialize", batch_serialize_func, METH_VARARGS, "Batch serialize objects"},
    {"batch_deserialize", batch_deserialize_func, METH_VARARGS, "Batch deserialize objects"},
    {"zero_copy_serialize", zero_copy_serialize_func, METH_VARARGS, "Zero-copy serialize object"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_serializationmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_serialization",
    .m_doc = "Native batch and zero-copy serialization for Windows",
    .m_size = -1,
    .m_methods = SerializationMethods,
};

PyMODINIT_FUNC PyInit_native_serialization(void) {
    return PyModule_Create(&native_serializationmodule);
}

