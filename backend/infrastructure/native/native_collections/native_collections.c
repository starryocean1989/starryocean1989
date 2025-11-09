/* -*- coding: utf-8 -*-
 * native_collections主模块
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "lru_cache.h"
#include "priority_queue.h"
#include "match_cache.h"
#include "../native_log_bridge.h"

#define COLLECTIONS_MODULE_COMPONENT "backend.native.collections.module"
#define COLLECTIONS_CORE_COMPONENT "backend.native.collections.core"

#define COLLECTIONS_LOG(level, message, details) \
    native_log_bridge_log(level, COLLECTIONS_MODULE_COMPONENT, __FUNCTION__, __LINE__, message, details)

/* 前向声明 */
extern PyTypeObject* get_LRUCacheType(void);
extern PyTypeObject* get_PriorityQueueType(void);
extern PyTypeObject* get_MatchCacheType(void);

static struct PyModuleDef native_collectionsmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_collections",
    .m_doc = "High-performance LRU cache and priority queue for Windows",
    .m_size = -1,
    .m_methods = NULL,
};

PyMODINIT_FUNC PyInit_native_collections(void) {
    PyObject *m = PyModule_Create(&native_collectionsmodule);
    if (m == NULL) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "failed to create native_collections module", NULL);
        return NULL;
    }

    /* 添加HighPerfLRUCache类型 */
    if (PyType_Ready(get_LRUCacheType()) < 0) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "HighPerfLRUCache type initialization failed", NULL);
        return NULL;
    }
    Py_INCREF(get_LRUCacheType());
    if (PyModule_AddObject(m, "HighPerfLRUCache", (PyObject *)get_LRUCacheType()) < 0) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "failed to add HighPerfLRUCache to module", NULL);
        Py_DECREF(get_LRUCacheType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加HighPerfPriorityQueue类型 */
    if (PyType_Ready(get_PriorityQueueType()) < 0) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "HighPerfPriorityQueue type initialization failed", NULL);
        return NULL;
    }
    Py_INCREF(get_PriorityQueueType());
    if (PyModule_AddObject(m, "HighPerfPriorityQueue", (PyObject *)get_PriorityQueueType()) < 0) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "failed to add HighPerfPriorityQueue to module", NULL);
        Py_DECREF(get_PriorityQueueType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加HighPerfMatchCache类型 */
    if (PyType_Ready(get_MatchCacheType()) < 0) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "HighPerfMatchCache type initialization failed", NULL);
        return NULL;
    }
    Py_INCREF(get_MatchCacheType());
    if (PyModule_AddObject(m, "HighPerfMatchCache", (PyObject *)get_MatchCacheType()) < 0) {
        COLLECTIONS_LOG(NATIVE_LOG_LEVEL_ERROR, "failed to add HighPerfMatchCache to module", NULL);
        Py_DECREF(get_MatchCacheType());
        Py_DECREF(m);
        return NULL;
    }

    COLLECTIONS_LOG(NATIVE_LOG_LEVEL_INFO, "native_collections module loaded", NULL);

    return m;
}

