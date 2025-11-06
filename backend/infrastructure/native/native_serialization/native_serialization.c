/* -*- coding: utf-8 -*-
 * native_serialization主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_serialize.h"

/* 前向声明 */
extern PyObject* batch_serialize_func(PyObject *self, PyObject *args);
extern PyObject* batch_deserialize_func(PyObject *self, PyObject *args);

/* 零拷贝序列化函数（简化实现） */
static PyObject* zero_copy_serialize_func(PyObject *self, PyObject *args) {
    PyObject *obj;
    PyObject *pickle_module = NULL;
    PyObject *dumps_func = NULL;
    PyObject *result = NULL;

    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return NULL;
    }

    /* 导入pickle模块 */
    pickle_module = PyImport_ImportModule("pickle");
    if (pickle_module == NULL) {
        return NULL;
    }

    dumps_func = PyObject_GetAttrString(pickle_module, "dumps");
    if (dumps_func == NULL) {
        Py_DECREF(pickle_module);
        return NULL;
    }

    /* 序列化对象 */
    PyObject *args_tuple = PyTuple_New(1);
    if (args_tuple == NULL) {
        Py_DECREF(dumps_func);
        Py_DECREF(pickle_module);
        return NULL;
    }

    Py_INCREF(obj);
    PyTuple_SET_ITEM(args_tuple, 0, obj);

    result = PyObject_CallObject(dumps_func, args_tuple);
    Py_DECREF(args_tuple);
    Py_DECREF(dumps_func);
    Py_DECREF(pickle_module);

    return result;
}

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

