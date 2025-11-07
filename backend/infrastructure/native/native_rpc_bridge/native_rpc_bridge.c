// -*- coding: utf-8 -*-
/*
 * native_rpc_bridge.c - Python绑定层
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "rpc_bridge.h"

// Python函数：get_method_id
static PyObject* py_get_method_id(PyObject* self, PyObject* args) {
    const char* method_name;
    
    if (!PyArg_ParseTuple(args, "s", &method_name)) {
        return NULL;
    }
    
    uint32_t method_id = get_method_id(method_name);
    return PyLong_FromUnsignedLong(method_id);
}

// Python函数：get_method_name
static PyObject* py_get_method_name(PyObject* self, PyObject* args) {
    unsigned long method_id;
    
    if (!PyArg_ParseTuple(args, "k", &method_id)) {
        return NULL;
    }
    
    const char* method_name = get_method_name((uint32_t)method_id);
    if (method_name) {
        return PyUnicode_FromString(method_name);
    }
    
    Py_RETURN_NONE;
}

// Python函数：create_request_header
static PyObject* py_create_request_header(PyObject* self, PyObject* args) {
    unsigned long method_id;
    unsigned long payload_size;
    
    if (!PyArg_ParseTuple(args, "kk", &method_id, &payload_size)) {
        return NULL;
    }
    
    RPCMessageHeader* header = create_rpc_header((uint32_t)method_id, (uint32_t)payload_size);
    if (!header) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to create RPC header");
        return NULL;
    }
    
    // 返回字典格式
    PyObject* result = PyDict_New();
    PyDict_SetItemString(result, "method_id", PyLong_FromUnsignedLong(header->method_id));
    PyDict_SetItemString(result, "payload_size", PyLong_FromUnsignedLong(header->payload_size));
    PyDict_SetItemString(result, "request_id", PyLong_FromUnsignedLong(header->request_id));
    PyDict_SetItemString(result, "flags", PyLong_FromUnsignedLong(header->flags));
    
    free_rpc_header(header);
    
    return result;
}

// Python函数：serialize_request（简化版，使用orjson在Python层处理）
static PyObject* py_serialize_request(PyObject* self, PyObject* args) {
    unsigned long method_id;
    PyObject* payload_obj;
    
    if (!PyArg_ParseTuple(args, "kO", &method_id, &payload_obj)) {
        return NULL;
    }
    
    // 简化实现：返回method_id，让Python层处理序列化
    PyObject* result = PyDict_New();
    PyDict_SetItemString(result, "method_id", PyLong_FromUnsignedLong(method_id));
    PyDict_SetItemString(result, "payload", payload_obj);
    Py_INCREF(payload_obj);
    
    return result;
}

// 方法定义表
static PyMethodDef RPCBridgeMethods[] = {
    {"get_method_id", py_get_method_id, METH_VARARGS,
     "Get method ID from method name"},
    {"get_method_name", py_get_method_name, METH_VARARGS,
     "Get method name from method ID"},
    {"create_request_header", py_create_request_header, METH_VARARGS,
     "Create RPC request header"},
    {"serialize_request", py_serialize_request, METH_VARARGS,
     "Serialize RPC request (simplified)"},
    {NULL, NULL, 0, NULL}
};

// 模块定义
static struct PyModuleDef rpc_bridge_module = {
    PyModuleDef_HEAD_INIT,
    "native_rpc_bridge",
    "Native RPC bridge for zero-copy IPC communication",
    -1,
    RPCBridgeMethods
};

// 模块初始化
PyMODINIT_FUNC PyInit_native_rpc_bridge(void) {
    PyObject* module = PyModule_Create(&rpc_bridge_module);
    if (module == NULL) {
        return NULL;
    }
    
    // 添加常量
    PyModule_AddIntConstant(module, "RPC_BRIDGE_AVAILABLE", 1);
    PyModule_AddStringConstant(module, "VERSION", "1.0.0");
    
    // 添加方法ID常量
    PyModule_AddIntConstant(module, "METHOD_GET_KLINE_DATA", METHOD_GET_KLINE_DATA);
    PyModule_AddIntConstant(module, "METHOD_GET_STOCK_LIST", METHOD_GET_STOCK_LIST);
    PyModule_AddIntConstant(module, "METHOD_GET_CACHE_STATUS", METHOD_GET_CACHE_STATUS);
    PyModule_AddIntConstant(module, "METHOD_CALCULATE_INDICATORS", METHOD_CALCULATE_INDICATORS);
    PyModule_AddIntConstant(module, "METHOD_SCAN_DATA_QUALITY", METHOD_SCAN_DATA_QUALITY);
    
    return module;
}
