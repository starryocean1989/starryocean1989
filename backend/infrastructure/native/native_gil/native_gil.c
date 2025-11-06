/* -*- coding: utf-8 -*-
 * native_gil主模块
 *
 * 统一导出所有功能，提供Python模块接口
 */

#include <Python.h>
#include "gil_utils.h"
#include "task_executor.h"
#include "thread_safe.h"
#include "lock_free.h"
#include "high_perf_event.h"

/* 声明外部函数 */
extern PyTypeObject* get_ThreadSafeQueueType(void);
extern PyTypeObject* get_ThreadSafeCounterType(void);
extern PyTypeObject* get_LockFreeQueueType(void);
extern PyTypeObject* get_LockFreeHashMapType(void);
extern PyTypeObject* get_HighPerfEventType(void);
extern PyTypeObject* get_HighPerfConditionType(void);
extern int init_thread_safe_types(void);

/* GIL管理函数 */
static PyMethodDef GilMethods[] = {
    {"release_gil", gil_release_gil, METH_NOARGS, "Release GIL and return thread state"},
    {"restore_gil", gil_restore_gil, METH_VARARGS, "Restore GIL using thread state"},
    {"execute_cpu_task", (PyCFunction)gil_execute_cpu_task_func, METH_VARARGS | METH_KEYWORDS,
     "Execute CPU-intensive task with GIL released"},
    {NULL, NULL, 0, NULL}
};

/* 模块初始化 */
static struct PyModuleDef native_gilmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_gil",
    .m_doc = "Native GIL management and thread-safe utilities for Windows",
    .m_size = -1,
    .m_methods = GilMethods,
};

PyMODINIT_FUNC PyInit_native_gil(void) {
    PyObject *m;

    /* 初始化线程安全类型 */
    if (init_thread_safe_types() < 0) {
        return NULL;
    }

    /* 创建模块 */
    m = PyModule_Create(&native_gilmodule);
    if (m == NULL) {
        return NULL;
    }

    /* 添加ThreadSafeQueue类型 */
    Py_INCREF(get_ThreadSafeQueueType());
    if (PyModule_AddObject(m, "ThreadSafeQueue", (PyObject *)get_ThreadSafeQueueType()) < 0) {
        Py_DECREF(get_ThreadSafeQueueType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加ThreadSafeCounter类型 */
    Py_INCREF(get_ThreadSafeCounterType());
    if (PyModule_AddObject(m, "ThreadSafeCounter", (PyObject *)get_ThreadSafeCounterType()) < 0) {
        Py_DECREF(get_ThreadSafeCounterType());
        Py_DECREF(get_ThreadSafeQueueType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加LockFreeQueue类型 */
    if (PyType_Ready(get_LockFreeQueueType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_LockFreeQueueType());
    if (PyModule_AddObject(m, "LockFreeQueue", (PyObject *)get_LockFreeQueueType()) < 0) {
        Py_DECREF(get_LockFreeQueueType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加LockFreeHashMap类型 */
    if (PyType_Ready(get_LockFreeHashMapType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_LockFreeHashMapType());
    if (PyModule_AddObject(m, "LockFreeHashMap", (PyObject *)get_LockFreeHashMapType()) < 0) {
        Py_DECREF(get_LockFreeHashMapType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加HighPerfEvent类型 */
    if (PyType_Ready(get_HighPerfEventType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_HighPerfEventType());
    if (PyModule_AddObject(m, "HighPerfEvent", (PyObject *)get_HighPerfEventType()) < 0) {
        Py_DECREF(get_HighPerfEventType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加HighPerfCondition类型 */
    if (PyType_Ready(get_HighPerfConditionType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_HighPerfConditionType());
    if (PyModule_AddObject(m, "HighPerfCondition", (PyObject *)get_HighPerfConditionType()) < 0) {
        Py_DECREF(get_HighPerfConditionType());
        Py_DECREF(m);
        return NULL;
    }

    return m;
}

