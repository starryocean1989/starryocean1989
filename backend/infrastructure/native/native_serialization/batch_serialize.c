/* -*- coding: utf-8 -*-
 * 批量序列化实现
 *
 * 使用Python pickle模块实现批量序列化，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_serialize.h"

/* 批量序列化函数 */
PyObject* batch_serialize_func(PyObject *self, PyObject *args) {
    PyObject *objects, *format = NULL;
    PyObject *pickle_module = NULL;
    PyObject *dumps_func = NULL;
    PyObject *result = NULL;
    Py_ssize_t count;

    if (!PyArg_ParseTuple(args, "O|O", &objects, &format)) {
        return NULL;
    }

    if (!PyList_Check(objects)) {
        PyErr_SetString(PyExc_TypeError, "objects must be a list");
        return NULL;
    }

    count = PyList_Size(objects);
    if (count == 0) {
        return PyList_New(0);
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

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        Py_DECREF(dumps_func);
        Py_DECREF(pickle_module);
        return NULL;
    }

    /* 批量序列化 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *obj = PyList_GET_ITEM(objects, i);
        PyObject *args_tuple = PyTuple_New(1);
        PyObject *serialized = NULL;

        if (args_tuple == NULL) {
            Py_DECREF(result);
            Py_DECREF(dumps_func);
            Py_DECREF(pickle_module);
            return NULL;
        }

        Py_INCREF(obj);
        PyTuple_SET_ITEM(args_tuple, 0, obj);

        serialized = PyObject_CallObject(dumps_func, args_tuple);
        Py_DECREF(args_tuple);

        if (serialized == NULL) {
            Py_DECREF(result);
            Py_DECREF(dumps_func);
            Py_DECREF(pickle_module);
            return NULL;
        }

        PyList_SET_ITEM(result, i, serialized);
    }

    Py_DECREF(dumps_func);
    Py_DECREF(pickle_module);

    return result;
}

/* 批量反序列化函数 */
PyObject* batch_deserialize_func(PyObject *self, PyObject *args) {
    PyObject *data_list;
    PyObject *pickle_module = NULL;
    PyObject *loads_func = NULL;
    PyObject *result = NULL;
    Py_ssize_t count;

    if (!PyArg_ParseTuple(args, "O", &data_list)) {
        return NULL;
    }

    if (!PyList_Check(data_list)) {
        PyErr_SetString(PyExc_TypeError, "data_list must be a list");
        return NULL;
    }

    count = PyList_Size(data_list);
    if (count == 0) {
        return PyList_New(0);
    }

    /* 导入pickle模块 */
    pickle_module = PyImport_ImportModule("pickle");
    if (pickle_module == NULL) {
        return NULL;
    }

    loads_func = PyObject_GetAttrString(pickle_module, "loads");
    if (loads_func == NULL) {
        Py_DECREF(pickle_module);
        return NULL;
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        Py_DECREF(loads_func);
        Py_DECREF(pickle_module);
        return NULL;
    }

    /* 批量反序列化 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *data = PyList_GET_ITEM(data_list, i);
        PyObject *args_tuple = PyTuple_New(1);
        PyObject *deserialized = NULL;

        if (args_tuple == NULL) {
            Py_DECREF(result);
            Py_DECREF(loads_func);
            Py_DECREF(pickle_module);
            return NULL;
        }

        Py_INCREF(data);
        PyTuple_SET_ITEM(args_tuple, 0, data);

        deserialized = PyObject_CallObject(loads_func, args_tuple);
        Py_DECREF(args_tuple);

        if (deserialized == NULL) {
            Py_DECREF(result);
            Py_DECREF(loads_func);
            Py_DECREF(pickle_module);
            return NULL;
        }

        PyList_SET_ITEM(result, i, deserialized);
    }

    Py_DECREF(loads_func);
    Py_DECREF(pickle_module);

    return result;
}

