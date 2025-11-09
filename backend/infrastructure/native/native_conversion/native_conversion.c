/* -*- coding: utf-8 -*-
 * native_conversion主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_convert.h"
#include "batch_string.h"
/* 日志桥接宏 */
#include "../native_log_bridge.h"

/* 前向声明 */
extern PyObject* batch_convert_func(PyObject *self, PyObject *args);
extern PyObject* batch_encode_func(PyObject *self, PyObject *args);
extern PyObject* batch_decode_func(PyObject *self, PyObject *args);

static PyMethodDef ConversionMethods[] = {
    {"batch_convert", batch_convert_func, METH_VARARGS, "Batch convert types"},
    {"batch_encode", batch_encode_func, METH_VARARGS, "Batch encode strings"},
    {"batch_decode", batch_decode_func, METH_VARARGS, "Batch decode strings"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_conversionmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_conversion",
    .m_doc = "Native batch type conversion and string operations for Windows",
    .m_size = -1,
    .m_methods = ConversionMethods,
};

PyMODINIT_FUNC PyInit_native_conversion(void) {
    PyObject *m = PyModule_Create(&native_conversionmodule);
    if (m) {
        NATIVE_LOG_INFO("backend.native.conversion.module", "PyInit_native_conversion", __LINE__, "native_conversion module loaded");
    } else {
        NATIVE_LOG_ERROR("backend.native.conversion.module", "PyInit_native_conversion", __LINE__, "failed to create native_conversion module");
    }
    return m;
}

