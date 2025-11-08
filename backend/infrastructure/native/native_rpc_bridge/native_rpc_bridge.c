// -*- coding: utf-8 -*-
/*
 * native_rpc_bridge.c - Python绑定层
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "rpc_bridge.h"

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
    
    return module;
}
