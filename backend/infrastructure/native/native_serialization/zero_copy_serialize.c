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
#include "zero_copy_serialize.h"

static PyObject *fallback_pickle_dump(PyObject *obj) {
    PyObject *pickle_module = NULL;
    PyObject *dumps_func = NULL;
    PyObject *args_tuple = NULL;
    PyObject *result = NULL;

    pickle_module = PyImport_ImportModule("pickle");
    if (pickle_module == NULL) {
        return NULL;
    }

    dumps_func = PyObject_GetAttrString(pickle_module, "dumps");
    if (dumps_func == NULL) {
        Py_DECREF(pickle_module);
        return NULL;
    }

    args_tuple = PyTuple_New(1);
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

    /* 直接返回已有的二进制对象 */
    if (PyBytes_Check(obj) || PyByteArray_Check(obj) || PyMemoryView_Check(obj)) {
        Py_INCREF(obj);
        return obj;
    }

    /* pandas.DataFrame 转换为 Arrow IPC memoryview */
    if (is_instance_of(obj, "pandas", "DataFrame", &pandas_dataframe_type)) {
        PyObject *arrow_buffer = serialize_dataframe(obj);
        if (arrow_buffer != NULL) {
            return arrow_buffer;
        }
        /* 转换失败时清理错误并回退 */
        PyErr_Clear();
    }

    /* 针对实现缓冲协议的对象，尝试创建memoryview */
    if (PyObject_CheckBuffer(obj)) {
        PyObject *mem = PyMemoryView_FromObject(obj);
        if (mem != NULL) {
            return mem;
        }
        /* 创建失败时清理错误并回退 */
        PyErr_Clear();
    }

    /* 其它情况回退到pickle */
    return fallback_pickle_dump(obj);
}

PyObject *zero_copy_serialize_func(PyObject *self, PyObject *args) {
    PyObject *obj;

    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return NULL;
    }

    return zero_copy_serialize_object(obj);
}

