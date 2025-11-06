/* -*- coding: utf-8 -*-
 * native_collections主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "lru_cache.h"
#include "priority_queue.h"

/* 前向声明 */
extern PyTypeObject* get_LRUCacheType(void);
extern PyTypeObject* get_PriorityQueueType(void);

static struct PyModuleDef native_collectionsmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_collections",
    .m_doc = "High-performance LRU cache and priority queue for Windows",
    .m_size = -1,
    .m_methods = NULL,
};

PyMODINIT_FUNC PyInit_native_collections(void) {
    PyObject *m = PyModule_Create(&native_collectionsmodule);
    if (m == NULL) return NULL;

    /* 添加HighPerfLRUCache类型 */
    if (PyType_Ready(get_LRUCacheType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_LRUCacheType());
    if (PyModule_AddObject(m, "HighPerfLRUCache", (PyObject *)get_LRUCacheType()) < 0) {
        Py_DECREF(get_LRUCacheType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加HighPerfPriorityQueue类型 */
    if (PyType_Ready(get_PriorityQueueType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_PriorityQueueType());
    if (PyModule_AddObject(m, "HighPerfPriorityQueue", (PyObject *)get_PriorityQueueType()) < 0) {
        Py_DECREF(get_PriorityQueueType());
        Py_DECREF(m);
        return NULL;
    }

    return m;
}

