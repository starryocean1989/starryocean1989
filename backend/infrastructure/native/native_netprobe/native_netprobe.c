// -*- coding: utf-8 -*-
/*
 * native_netprobe.c - Python绑定层
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "netprobe.h"
#include "../native_log_bridge.h"
#include <stdio.h>

#define NETPROBE_WRAPPER_COMPONENT "backend.native.netprobe.wrapper"

static void netprobe_wrapper_log(
    int level,
    const char *function,
    int line,
    const char *message,
    const char *details
) {
    native_log_bridge_log(level, NETPROBE_WRAPPER_COMPONENT, function, line, message, details);
}

static void netprobe_wrapper_log_warning(const char *function, int line, const char *message, const char *details) {
    netprobe_wrapper_log(NATIVE_LOG_LEVEL_WARNING, function, line, message, details);
}

static void netprobe_wrapper_log_error(const char *function, int line, const char *message, const char *details) {
    netprobe_wrapper_log(NATIVE_LOG_LEVEL_ERROR, function, line, message, details);
}

static void netprobe_wrapper_log_info(const char *function, int line, const char *message, const char *details) {
    netprobe_wrapper_log(NATIVE_LOG_LEVEL_INFO, function, line, message, details);
}

// Python函数：test_connection
static PyObject* py_test_connection(PyObject* self, PyObject* args, PyObject* kwargs) {
    const char* host;
    int port;
    double timeout = 3.0;
    
    static char* kwlist[] = {"host", "port", "timeout", NULL};
    
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "si|d", kwlist, &host, &port, &timeout)) {
        netprobe_wrapper_log_warning(__FUNCTION__, __LINE__, "Invalid arguments for test_connection", NULL);
        return NULL;
    }
    
    ConnectionResult* result = test_connection(host, port, timeout);
    if (!result) {
        char details[128];
        snprintf(details, sizeof(details), "host=%s;port=%d;timeout=%.2f", host, port, timeout);
        netprobe_wrapper_log_error(__FUNCTION__, __LINE__, "test_connection returned NULL", details);
        PyErr_SetString(PyExc_RuntimeError, "Connection test failed");
        return NULL;
    }
    
    PyObject* result_dict = PyDict_New();
    PyDict_SetItemString(result_dict, "host", PyUnicode_FromString(result->host));
    PyDict_SetItemString(result_dict, "port", PyLong_FromLong(result->port));
    PyDict_SetItemString(result_dict, "status", PyLong_FromLong(result->status));
    PyDict_SetItemString(result_dict, "latency_ms", PyFloat_FromDouble(result->latency_ms));
    
    if (result->error_message) {
        PyDict_SetItemString(result_dict, "error", PyUnicode_FromString(result->error_message));
    } else {
        Py_INCREF(Py_None);
        PyDict_SetItemString(result_dict, "error", Py_None);
    }
    
    free_connection_result(result);
    netprobe_wrapper_log_info(__FUNCTION__, __LINE__, "test_connection succeeded", NULL);
    
    return result_dict;
}

// Python函数：batch_test_connections
static PyObject* py_batch_test_connections(PyObject* self, PyObject* args, PyObject* kwargs) {
    PyObject* servers_list;
    double timeout = 3.0;
    int max_concurrent = 10;
    
    static char* kwlist[] = {"servers", "timeout", "max_concurrent", NULL};
    
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|di", kwlist, 
                                     &servers_list, &timeout, &max_concurrent)) {
        netprobe_wrapper_log_warning(__FUNCTION__, __LINE__, "Invalid arguments for batch_test_connections", NULL);
        return NULL;
    }
    
    if (!PyList_Check(servers_list)) {
        netprobe_wrapper_log_warning(__FUNCTION__, __LINE__, "Servers argument must be list", NULL);
        PyErr_SetString(PyExc_TypeError, "servers must be a list");
        return NULL;
    }
    
    Py_ssize_t count = PyList_Size(servers_list);
    if (count == 0) {
        return PyList_New(0);
    }
    
    // 准备数据
    const char** hosts = (const char**)malloc(sizeof(char*) * count);
    int* ports = (int*)malloc(sizeof(int) * count);
    
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject* item = PyList_GetItem(servers_list, i);
        if (!PyTuple_Check(item) || PyTuple_Size(item) != 2) {
            free(hosts);
            free(ports);
            PyErr_SetString(PyExc_TypeError, "Each server must be a (host, port) tuple");
            return NULL;
        }
        
        PyObject* host_obj = PyTuple_GetItem(item, 0);
        PyObject* port_obj = PyTuple_GetItem(item, 1);
        
        hosts[i] = PyUnicode_AsUTF8(host_obj);
        ports[i] = (int)PyLong_AsLong(port_obj);
    }
    
    // 执行批量测试
    BatchTestResult* batch_result = batch_test_connections(hosts, ports, (size_t)count, timeout, max_concurrent);
    
    free(hosts);
    free(ports);
    
    if (!batch_result) {
        netprobe_wrapper_log_error(__FUNCTION__, __LINE__, "batch_test_connections returned NULL", NULL);
        PyErr_SetString(PyExc_RuntimeError, "Batch test failed");
        return NULL;
    }
    
    // 转换结果
    PyObject* results_list = PyList_New(batch_result->count);
    for (size_t i = 0; i < batch_result->count; i++) {
        PyObject* result_dict = PyDict_New();
        PyDict_SetItemString(result_dict, "host", PyUnicode_FromString(batch_result->results[i].host));
        PyDict_SetItemString(result_dict, "port", PyLong_FromLong(batch_result->results[i].port));
        PyDict_SetItemString(result_dict, "status", PyLong_FromLong(batch_result->results[i].status));
        PyDict_SetItemString(result_dict, "latency_ms", PyFloat_FromDouble(batch_result->results[i].latency_ms));
        
        if (batch_result->results[i].error_message) {
            PyDict_SetItemString(result_dict, "error", PyUnicode_FromString(batch_result->results[i].error_message));
        } else {
            Py_INCREF(Py_None);
            PyDict_SetItemString(result_dict, "error", Py_None);
        }
        
        PyList_SetItem(results_list, i, result_dict);
    }
    
    free_batch_test_result(batch_result);
    netprobe_wrapper_log_info(__FUNCTION__, __LINE__, "batch_test_connections completed", NULL);
    return results_list;
}

// 方法定义表
static PyMethodDef NetProbeMethods[] = {
    {"test_connection", (PyCFunction)py_test_connection, METH_VARARGS | METH_KEYWORDS,
     "Test single connection to a host:port"},
    {"batch_test_connections", (PyCFunction)py_batch_test_connections, METH_VARARGS | METH_KEYWORDS,
     "Batch test connections to multiple servers"},
    {NULL, NULL, 0, NULL}
};

// 模块定义
static struct PyModuleDef netprobe_module = {
    PyModuleDef_HEAD_INIT,
    "native_netprobe",
    "Native network probe for fast batch connectivity testing",
    -1,
    NetProbeMethods
};

// 模块初始化
PyMODINIT_FUNC PyInit_native_netprobe(void) {
    PyObject* module = PyModule_Create(&netprobe_module);
    if (module == NULL) {
        return NULL;
    }
    
    PyModule_AddIntConstant(module, "NETPROBE_AVAILABLE", 1);
    PyModule_AddStringConstant(module, "VERSION", "1.0.0");
    
    return module;
}
