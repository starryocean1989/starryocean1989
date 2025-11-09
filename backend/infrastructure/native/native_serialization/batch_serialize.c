/* -*- coding: utf-8 -*-
 * 批量序列化实现
 *
 * 使用Python pickle模块实现批量序列化，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_serialize.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static PyObject* g_log_func = NULL;
static const char* const COMPONENT_CORE = "backend.native.native_serialization.core";

static int
ensure_log_bridge(void) {
    if (g_log_func != NULL) {
        return 0;
    }

    PyObject* logging_module = PyImport_ImportModule("backend.infrastructure.native.logging_bridge");
    if (logging_module == NULL) {
        return -1;
    }

    g_log_func = PyObject_GetAttrString(logging_module, "log_from_native");
    Py_DECREF(logging_module);

    if (g_log_func == NULL) {
        return -1;
    }

    return 0;
}

void native_log_from_c(int level, const char* component, const char* function,
                      int line, const char* message, const char* details) {
    if (ensure_log_bridge() != 0) {
        // 日志桥接初始化失败，回退到stderr输出
        fprintf(stderr, "[NATIVE_LOG:%d] %s:%s:%d: %s",
                level, component, function, line, message);
        if (details) {
            fprintf(stderr, " (%s)", details);
        }
        fprintf(stderr, "\n");
        return;
    }

    PyObject* result = PyObject_CallFunction(g_log_func, "isssiz",
                                           level, component, function, line, message,
                                           details ? details : Py_None);
    if (result == NULL) {
        PyErr_Clear();  // 忽略日志调用本身的异常
    } else {
        Py_DECREF(result);
    }
}

/* 批量序列化函数 */
PyObject* batch_serialize_func(PyObject *self, PyObject *args) {
    PyObject *objects, *format = NULL;
    PyObject *pickle_module = NULL;
    PyObject *dumps_func = NULL;
    PyObject *result = NULL;
    Py_ssize_t count;

    if (!PyArg_ParseTuple(args, "O|O", &objects, &format)) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                        "Failed to parse arguments", NULL);
        return NULL;
    }

    if (!PyList_Check(objects)) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                        "Input objects must be a list - type error", NULL);
        PyErr_SetString(PyExc_TypeError, "objects must be a list");
        return NULL;
    }

    count = PyList_Size(objects);
    char details[128];
    snprintf(details, sizeof(details), "object_count=%zd", count);
    NATIVE_LOG_INFO(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                   "Starting batch serialization", details);

    if (count == 0) {
        NATIVE_LOG_DEBUG(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                        "Empty input list, returning empty result", NULL);
        return PyList_New(0);
    }

    /* 导入pickle模块 */
    pickle_module = PyImport_ImportModule("pickle");
    if (pickle_module == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                        "Failed to import pickle module - dependency error", NULL);
        return NULL;
    }

    dumps_func = PyObject_GetAttrString(pickle_module, "dumps");
    if (dumps_func == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                        "Failed to get pickle.dumps function - module error", NULL);
        Py_DECREF(pickle_module);
        return NULL;
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                        "Failed to create result list - memory allocation error", NULL);
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
            NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                            "Failed to create args tuple - memory allocation error", NULL);
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
            char error_details[256];
            snprintf(error_details, sizeof(error_details), "object_index=%zd", i);
            NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                            "Failed to serialize object - pickle error", error_details);
            Py_DECREF(result);
            Py_DECREF(dumps_func);
            Py_DECREF(pickle_module);
            return NULL;
        }

        PyList_SET_ITEM(result, i, serialized);
    }

    Py_DECREF(dumps_func);
    Py_DECREF(pickle_module);

    char success_details[128];
    snprintf(success_details, sizeof(success_details), "serialized_count=%zd", count);
    NATIVE_LOG_INFO(COMPONENT_CORE, "batch_serialize_func", __LINE__,
                   "Batch serialization completed successfully", success_details);

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
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                        "Failed to parse arguments", NULL);
        return NULL;
    }

    if (!PyList_Check(data_list)) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                        "Input data_list must be a list - type error", NULL);
        PyErr_SetString(PyExc_TypeError, "data_list must be a list");
        return NULL;
    }

    count = PyList_Size(data_list);
    char details[128];
    snprintf(details, sizeof(details), "data_count=%zd", count);
    NATIVE_LOG_INFO(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                   "Starting batch deserialization", details);

    if (count == 0) {
        NATIVE_LOG_DEBUG(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                        "Empty input list, returning empty result", NULL);
        return PyList_New(0);
    }

    /* 导入pickle模块 */
    pickle_module = PyImport_ImportModule("pickle");
    if (pickle_module == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                        "Failed to import pickle module - dependency error", NULL);
        return NULL;
    }

    loads_func = PyObject_GetAttrString(pickle_module, "loads");
    if (loads_func == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                        "Failed to get pickle.loads function - module error", NULL);
        Py_DECREF(pickle_module);
        return NULL;
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                        "Failed to create result list - memory allocation error", NULL);
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
            NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                            "Failed to create args tuple - memory allocation error", NULL);
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
            char error_details[256];
            snprintf(error_details, sizeof(error_details), "data_index=%zd", i);
            NATIVE_LOG_ERROR(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                            "Failed to deserialize data - pickle error", error_details);
            Py_DECREF(result);
            Py_DECREF(loads_func);
            Py_DECREF(pickle_module);
            return NULL;
        }

        PyList_SET_ITEM(result, i, deserialized);
    }

    Py_DECREF(loads_func);
    Py_DECREF(pickle_module);

    char success_details[128];
    snprintf(success_details, sizeof(success_details), "deserialized_count=%zd", count);
    NATIVE_LOG_INFO(COMPONENT_CORE, "batch_deserialize_func", __LINE__,
                   "Batch deserialization completed successfully", success_details);

    return result;
}

