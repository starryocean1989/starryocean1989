#ifndef LRU_CACHE_H
#define LRU_CACHE_H

#include <Python.h>
#include <Windows.h>

/* 前向声明 */
struct _LRUNode;
typedef struct _LRUNode LRUNode;

/* 类型声明 */
typedef struct {
    PyObject_HEAD
    CRITICAL_SECTION lock;
    Py_ssize_t maxsize;
    Py_ssize_t size;
    LRUNode *head;
    LRUNode *tail;
    PyObject *cache;
} HighPerfLRUCache;

/* 类型对象声明 */
extern PyTypeObject HighPerfLRUCacheType;

/* 函数声明 */
PyTypeObject* get_LRUCacheType(void);

#endif /* LRU_CACHE_H */

