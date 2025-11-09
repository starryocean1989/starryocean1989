/* -*- coding: utf-8 -*-
 * 零拷贝序列化实现
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "zero_copy_serialize.h"

/*
 * 零拷贝序列化实现
 *
 * 对于已经是bytes/bytearray/memoryview的对象，直接返回新的引用
 * 对于实现了缓冲协议的对象，返回一个memoryview包装，避免额外复制
 * 针对 pandas.DataFrame 等结构化数据，优先利用 Arrow IPC 输出为
 * memoryview，实现跨进程零拷贝传输；其它对象回退到 pickle.dumps
 */

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "zero_copy_serialize.h"

// 日志等级常量（与 Python NativeLogLevel 对应）
enum {
    NATIVE_LOG_DEBUG = 10,
    NATIVE_LOG_INFO = 20,
    NATIVE_LOG_WARNING = 30,
    NATIVE_LOG_ERROR = 40,
    NATIVE_LOG_CRITICAL = 50,
};

static const char* const COMPONENT_CORE = "backend.native.native_serialization.core";

// 日志宏定义
#define NATIVE_LOG_DEBUG(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_DEBUG, component, function, line, message, details)

#define NATIVE_LOG_INFO(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_INFO, component, function, line, message, details)

#define NATIVE_LOG_WARNING(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_WARNING, component, function, line, message, details)

#define NATIVE_LOG_ERROR(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_ERROR, component, function, line, message, details)

#define NATIVE_LOG_CRITICAL(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_CRITICAL, component, function, line, message, details)

// 声明日志桥接函数（在batch_serialize.c中定义）
extern void native_log_from_c(int level, const char* component, const char* function,
                             int line, const char* message, const char* details);

static PyObject *fallback_pickle_dump(PyObject *obj) {
    PyObject *pickle_module = NULL;
    PyObject *dumps_func = NULL;
    PyObject *args_tuple = NULL;
    PyObject *result = NULL;

    pickle_module = PyImport_ImportModule("pickle");
    if (pickle_module == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "fallback_pickle_dump", __LINE__,
                        "Failed to import pickle module - dependency error", NULL);
        return NULL;
    }

    dumps_func = PyObject_GetAttrString(pickle_module, "dumps");
    if (dumps_func == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "fallback_pickle_dump", __LINE__,
                        "Failed to get pickle.dumps function - module error", NULL);
        Py_DECREF(pickle_module);
        return NULL;
    }

    args_tuple = PyTuple_New(1);
    if (args_tuple == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "fallback_pickle_dump", __LINE__,
                        "Failed to create args tuple - memory allocation error", NULL);
        Py_DECREF(dumps_func);
        Py_DECREF(pickle_module);
        return NULL;
    }

    Py_INCREF(obj);
    PyTuple_SET_ITEM(args_tuple, 0, obj);
    result = PyObject_CallObject(dumps_func, args_tuple);

    if (result == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_CORE, "fallback_pickle_dump", __LINE__,
                        "Failed to pickle object - serialization error", NULL);
    } else {
        NATIVE_LOG_INFO(COMPONENT_CORE, "fallback_pickle_dump", __LINE__,
                       "Successfully pickled object using fallback method", NULL);
    }

    Py_DECREF(args_tuple);
    Py_DECREF(dumps_func);
    Py_DECREF(pickle_module);

    return result;
}

static int is_instance_of(PyObject *obj, const char *module_name, const char *type_name, PyObject **cached_type) {
    if (*cached_type == NULL) {
        PyObject *module = PyImport_ImportModule(module_name);
        if (module == NULL) {
            PyErr_Clear();
            return 0;
        }

        PyObject *type_obj = PyObject_GetAttrString(module, type_name);
        Py_DECREF(module);
        if (type_obj == NULL) {
            PyErr_Clear();
            return 0;
        }

        *cached_type = type_obj;
    }

    int result = PyObject_IsInstance(obj, *cached_type);
    if (result == -1) {
        PyErr_Clear();
        return 0;
    }

    return result;
}

static PyObject *serialize_dataframe(PyObject *df) {
    static PyObject *arrow_utils_module = NULL;
    static PyObject *arrow_buffer_func = NULL;

    if (arrow_utils_module == NULL) {
        arrow_utils_module = PyImport_ImportModule("backend.infrastructure.data_module_vnpy.arrow_utils");
        if (arrow_utils_module == NULL) {
            PyErr_Clear();
            return NULL;
        }
    }

    if (arrow_buffer_func == NULL) {
        arrow_buffer_func = PyObject_GetAttrString(arrow_utils_module, "dataframe_to_arrow_buffer");
        if (arrow_buffer_func == NULL) {
            PyErr_Clear();
            return NULL;
        }
    }

    PyObject *args = PyTuple_Pack(1, df);
    if (args == NULL) {
        return NULL;
    }

    PyObject *result = PyObject_CallObject(arrow_buffer_func, args);
    Py_DECREF(args);

    if (result == NULL) {
        PyErr_Clear();
        return NULL;
    }

    if (result == Py_None) {
        Py_DECREF(result);
        return NULL;
    }

    return result;
}

PyObject *zero_copy_serialize_object(PyObject *obj) {
    static PyObject *pandas_dataframe_type = NULL;

    NATIVE_LOG_DEBUG(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                    "Attempting zero-copy serialization", NULL);

    /* 直接返回已有的二进制对象 */
    if (PyBytes_Check(obj) || PyByteArray_Check(obj) || PyMemoryView_Check(obj)) {
        NATIVE_LOG_INFO(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                       "Object is already binary-compatible, returning direct reference", NULL);
        Py_INCREF(obj);
        return obj;
    }

    /* pandas.DataFrame 转换为 Arrow IPC memoryview */
    if (is_instance_of(obj, "pandas", "DataFrame", &pandas_dataframe_type)) {
        NATIVE_LOG_DEBUG(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                        "Detected pandas DataFrame, attempting Arrow serialization", NULL);
        PyObject *arrow_buffer = serialize_dataframe(obj);
        if (arrow_buffer != NULL) {
            NATIVE_LOG_INFO(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                           "Successfully converted DataFrame to Arrow buffer", NULL);
            if (PyMemoryView_Check(arrow_buffer)) {
                Py_buffer *view = PyMemoryView_GET_BUFFER(arrow_buffer);
                if (view != NULL && !view->readonly) {
                    PyObject *readonly_view = PyObject_CallMethod(arrow_buffer, "toreadonly", NULL);
                    if (readonly_view != NULL) {
                        Py_DECREF(arrow_buffer);
                        return readonly_view;
                    }
                    PyErr_Clear();
                }
            }
            return arrow_buffer;
        }
        /* 转换失败时清理错误并回退 */
        NATIVE_LOG_WARNING(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                          "Arrow serialization failed, falling back to other methods", NULL);
        PyErr_Clear();
    }

    /* 针对实现缓冲协议的对象，尝试创建memoryview */
    if (PyObject_CheckBuffer(obj)) {
        NATIVE_LOG_DEBUG(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                        "Object supports buffer protocol, creating memoryview", NULL);
        PyObject *mem = PyMemoryView_FromObject(obj);
        if (mem != NULL) {
            NATIVE_LOG_INFO(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                           "Successfully created memoryview from buffer object", NULL);
            return mem;
        }
        /* 创建失败时清理错误并回退 */
        NATIVE_LOG_WARNING(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                          "Failed to create memoryview from buffer object, falling back to pickle", NULL);
        PyErr_Clear();
    }

    /* 其它情况回退到pickle */
    NATIVE_LOG_DEBUG(COMPONENT_CORE, "zero_copy_serialize_object", __LINE__,
                    "Using pickle fallback for serialization", NULL);
    return fallback_pickle_dump(obj);
}

PyObject *zero_copy_serialize_func(PyObject *self, PyObject *args) {
    PyObject *obj;

    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return NULL;
    }

    return zero_copy_serialize_object(obj);
}

