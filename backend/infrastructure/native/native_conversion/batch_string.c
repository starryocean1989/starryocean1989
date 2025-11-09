/* -*- coding: utf-8 -*-
 * 批量字符串操作实现
 *
 * 批量进行字符串编码/解码操作，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_string.h"
/* 日志桥接宏 */
#include "../native_log_bridge.h"

/* 批量编码函数 */
PyObject* batch_encode_func(PyObject *self, PyObject *args) {
    PyObject *strings;
    PyObject *result = NULL;
    Py_ssize_t count;
    const char *enc = "utf-8";

    if (!PyArg_ParseTuple(args, "O|s", &strings, &enc)) {
        NATIVE_LOG_ERROR("backend.native.conversion.core", "batch_encode", __LINE__, "invalid arguments to batch_encode");
        return NULL;
    }

    if (!PyList_Check(strings)) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.conversion.core", "batch_encode", __LINE__, "strings must be a list", NULL);
        PyErr_SetString(PyExc_TypeError, "strings must be a list");
        return NULL;
    }

    count = PyList_Size(strings);
    if (count == 0) {
        return PyList_New(0);
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        NATIVE_LOG_CRITICAL("backend.native.conversion.core", "batch_encode", __LINE__, "failed to allocate result list");
        return NULL;
    }

    /* 批量编码 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *str_obj = PyList_GET_ITEM(strings, i);
        PyObject *encoded = NULL;

        if (PyUnicode_Check(str_obj)) {
            encoded = PyUnicode_AsEncodedString(str_obj, enc, "strict");
        } else if (PyBytes_Check(str_obj)) {
            Py_INCREF(str_obj);
            encoded = str_obj;
        } else {
            PyObject *str_converted = PyObject_Str(str_obj);
            if (str_converted != NULL) {
                encoded = PyUnicode_AsEncodedString(str_converted, enc, "strict");
                Py_DECREF(str_converted);
            }
        }

        if (encoded == NULL) {
            NATIVE_LOG_ERROR("backend.native.conversion.core", "batch_encode", __LINE__, "failed to encode string");
            Py_DECREF(result);
            return NULL;
        }

        PyList_SET_ITEM(result, i, encoded);
    }

    return result;
}

/* 批量解码函数 */
PyObject* batch_decode_func(PyObject *self, PyObject *args) {
    PyObject *bytes_list;
    PyObject *result = NULL;
    Py_ssize_t count;
    const char *enc = "utf-8";

    if (!PyArg_ParseTuple(args, "O|s", &bytes_list, &enc)) {
        NATIVE_LOG_ERROR("backend.native.conversion.core", "batch_decode", __LINE__, "invalid arguments to batch_decode");
        return NULL;
    }

    if (!PyList_Check(bytes_list)) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.conversion.core", "batch_decode", __LINE__, "bytes_list must be a list", NULL);
        PyErr_SetString(PyExc_TypeError, "bytes_list must be a list");
        return NULL;
    }

    count = PyList_Size(bytes_list);
    if (count == 0) {
        return PyList_New(0);
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        NATIVE_LOG_CRITICAL("backend.native.conversion.core", "batch_decode", __LINE__, "failed to allocate result list");
        return NULL;
    }

    /* 批量解码 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *bytes_obj = PyList_GET_ITEM(bytes_list, i);
        PyObject *decoded = NULL;

        if (PyBytes_Check(bytes_obj)) {
            decoded = PyUnicode_FromEncodedObject(bytes_obj, enc, "strict");
        } else if (PyUnicode_Check(bytes_obj)) {
            Py_INCREF(bytes_obj);
            decoded = bytes_obj;
        } else {
            NATIVE_LOG_ERROR_DETAILS("backend.native.conversion.core", "batch_decode", __LINE__, "items must be bytes", NULL);
            PyErr_SetString(PyExc_TypeError, "items must be bytes");
            Py_DECREF(result);
            return NULL;
        }

        if (decoded == NULL) {
            NATIVE_LOG_ERROR("backend.native.conversion.core", "batch_decode", __LINE__, "failed to decode item");
            Py_DECREF(result);
            return NULL;
        }

        PyList_SET_ITEM(result, i, decoded);
    }

    return result;
}

