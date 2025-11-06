/* -*- coding: utf-8 -*-
 * 批量类型转换实现
 *
 * 批量转换Python对象类型，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_convert.h"

/* 批量类型转换函数 */
PyObject* batch_convert_func(PyObject *self, PyObject *args) {
    PyObject *objects, *target_type;
    PyObject *result = NULL;
    Py_ssize_t count;
    const char *type_name = NULL;

    if (!PyArg_ParseTuple(args, "OO", &objects, &target_type)) {
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

    /* 获取目标类型名称 */
    if (PyUnicode_Check(target_type)) {
        type_name = PyUnicode_AsUTF8(target_type);
    } else if (PyType_Check(target_type)) {
        PyObject *type_name_obj = PyObject_GetAttrString(target_type, "__name__");
        if (type_name_obj != NULL) {
            type_name = PyUnicode_AsUTF8(type_name_obj);
            Py_DECREF(type_name_obj);
        }
    } else {
        PyErr_SetString(PyExc_TypeError, "target_type must be a type or string");
        return NULL;
    }

    if (type_name == NULL) {
        return NULL;
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        return NULL;
    }

    /* 批量转换 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *obj = PyList_GET_ITEM(objects, i);
        PyObject *converted = NULL;

        /* 根据类型名称进行转换 */
        if (strcmp(type_name, "int") == 0) {
            converted = PyNumber_Long(obj);
        } else if (strcmp(type_name, "float") == 0) {
            converted = PyNumber_Float(obj);
        } else if (strcmp(type_name, "str") == 0) {
            converted = PyObject_Str(obj);
        } else if (strcmp(type_name, "bytes") == 0) {
            if (PyUnicode_Check(obj)) {
                converted = PyUnicode_AsEncodedString(obj, "utf-8", "strict");
            } else if (PyBytes_Check(obj)) {
                Py_INCREF(obj);
                converted = obj;
            } else {
                converted = PyBytes_FromObject(obj);
            }
        } else {
            /* 尝试调用目标类型 */
            if (PyType_Check(target_type)) {
                PyObject *args_tuple = PyTuple_New(1);
                if (args_tuple != NULL) {
                    Py_INCREF(obj);
                    PyTuple_SET_ITEM(args_tuple, 0, obj);
                    converted = PyObject_CallObject(target_type, args_tuple);
                    Py_DECREF(args_tuple);
                }
            } else {
                PyErr_SetString(PyExc_TypeError, "Unsupported target type");
                Py_DECREF(result);
                return NULL;
            }
        }

        if (converted == NULL) {
            Py_DECREF(result);
            return NULL;
        }

        PyList_SET_ITEM(result, i, converted);
    }

    return result;
}

