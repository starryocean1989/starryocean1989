/* -*- coding: utf-8 -*-
 * 批量哈希计算实现
 *
 * 批量计算哈希值，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>
#include "batch_hash.h"
/* 日志桥接宏 */
#include "../native_log_bridge.h"

/* 批量哈希计算函数 */
PyObject* batch_hash_func(PyObject *self, PyObject *args) {
    PyObject *data, *algorithm = NULL;
    PyObject *result = NULL;
    PyObject *hashlib_module = NULL;
    PyObject *hash_func = NULL;
    Py_ssize_t count;
    const char *algo = "md5";

    /* 解析参数：data 列表，algorithm 可选的字符串对象 */
    if (!PyArg_ParseTuple(args, "O|O", &data, &algorithm)) {
        NATIVE_LOG_ERROR("backend.native.compute.core", "batch_hash", __LINE__, "invalid arguments to batch_hash");
        return NULL;
    }

    if (!PyList_Check(data)) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.compute.core", "batch_hash", __LINE__, "data must be a list", NULL);
        PyErr_SetString(PyExc_TypeError, "data must be a list");
        return NULL;
    }

    if (algorithm != NULL) {
        if (!PyUnicode_Check(algorithm)) {
            NATIVE_LOG_ERROR_DETAILS("backend.native.compute.core", "batch_hash", __LINE__, "algorithm must be a string", NULL);
            PyErr_SetString(PyExc_TypeError, "algorithm must be a string");
            return NULL;
        }
        algo = PyUnicode_AsUTF8(algorithm);
        if (algo == NULL) {
            NATIVE_LOG_ERROR("backend.native.compute.core", "batch_hash", __LINE__, "failed to parse algorithm string");
            return NULL;
        }
    }

    count = PyList_Size(data);
    if (count == 0) {
        return PyList_New(0);
    }

    /* 导入hashlib模块 */
    hashlib_module = PyImport_ImportModule("hashlib");
    if (hashlib_module == NULL) {
        NATIVE_LOG_ERROR("backend.native.compute.core", "batch_hash", __LINE__, "failed to import hashlib");
        return NULL;
    }

    /* 获取哈希函数 */
    hash_func = PyObject_GetAttrString(hashlib_module, algo);
    if (hash_func == NULL) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.compute.core", "batch_hash", __LINE__, "unsupported hash algorithm", algo);
        Py_DECREF(hashlib_module);
        return NULL;
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        NATIVE_LOG_CRITICAL("backend.native.compute.core", "batch_hash", __LINE__, "failed to allocate result list");
        Py_DECREF(hash_func);
        Py_DECREF(hashlib_module);
        return NULL;
    }

    /* 批量计算哈希 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *item = PyList_GET_ITEM(data, i);
        PyObject *args_tuple = NULL;
        PyObject *hash_obj = NULL;
        PyObject *hashed = NULL;

        /* 创建哈希对象 */
        args_tuple = PyTuple_New(0);
        if (args_tuple == NULL) {
            NATIVE_LOG_ERROR("backend.native.compute.core", "batch_hash", __LINE__, "failed to create args tuple");
            Py_DECREF(result);
            Py_DECREF(hash_func);
            Py_DECREF(hashlib_module);
            return NULL;
        }

        hash_obj = PyObject_CallObject(hash_func, args_tuple);
        Py_DECREF(args_tuple);

        if (hash_obj == NULL) {
            NATIVE_LOG_ERROR("backend.native.compute.core", "batch_hash", __LINE__, "failed to create hash object");
            Py_DECREF(result);
            Py_DECREF(hash_func);
            Py_DECREF(hashlib_module);
            return NULL;
        }

        /* 更新哈希值 */
        PyObject *update_func = PyObject_GetAttrString(hash_obj, "update");
        if (update_func != NULL) {
            PyObject *update_args = PyTuple_New(1);
            if (update_args != NULL) {
                Py_INCREF(item);
                PyTuple_SET_ITEM(update_args, 0, item);
                PyObject_CallObject(update_func, update_args);
                Py_DECREF(update_args);
            }
            Py_DECREF(update_func);
        }

        /* 获取哈希值 */
        PyObject *hexdigest_func = PyObject_GetAttrString(hash_obj, "hexdigest");
        if (hexdigest_func != NULL) {
            hashed = PyObject_CallObject(hexdigest_func, NULL);
            Py_DECREF(hexdigest_func);
        }

        Py_DECREF(hash_obj);

        if (hashed == NULL) {
            NATIVE_LOG_ERROR("backend.native.compute.core", "batch_hash", __LINE__, "failed to compute hexdigest");
            Py_DECREF(result);
            Py_DECREF(hash_func);
            Py_DECREF(hashlib_module);
            return NULL;
        }

        PyList_SET_ITEM(result, i, hashed);
    }

    Py_DECREF(hash_func);
    Py_DECREF(hashlib_module);

    return result;
}

