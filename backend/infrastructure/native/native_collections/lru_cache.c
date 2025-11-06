/* -*- coding: utf-8 -*-
 * 高性能LRU缓存实现
 *
 * 使用C实现LRU缓存，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>
#include "lru_cache.h"

/* 使用头文件中定义的HighPerfLRUCache结构 */

/* LRU节点结构 */
typedef struct _LRUNode {
    PyObject *key;
    PyObject *value;
    struct _LRUNode *prev;
    struct _LRUNode *next;
} LRUNode;

/* 方法声明 */
static PyObject* HighPerfLRUCache_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void HighPerfLRUCache_dealloc(HighPerfLRUCache *self);
static PyObject* HighPerfLRUCache_get(HighPerfLRUCache *self, PyObject *args);
static PyObject* HighPerfLRUCache_set(HighPerfLRUCache *self, PyObject *args);
static PyObject* HighPerfLRUCache_size(HighPerfLRUCache *self, PyObject *args);

/* 方法定义 */
static PyMethodDef HighPerfLRUCache_methods[] = {
    {"get", (PyCFunction)HighPerfLRUCache_get, METH_VARARGS, "Get value by key"},
    {"set", (PyCFunction)HighPerfLRUCache_set, METH_VARARGS, "Set key-value pair"},
    {"size", (PyCFunction)HighPerfLRUCache_size, METH_NOARGS, "Get cache size"},
    {NULL, NULL, 0, NULL}
};

/* 类型定义 */
PyTypeObject HighPerfLRUCacheType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_collections.HighPerfLRUCache",
    .tp_doc = "High-performance LRU cache",
    .tp_basicsize = sizeof(HighPerfLRUCache),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = HighPerfLRUCache_new,
    .tp_dealloc = (destructor)HighPerfLRUCache_dealloc,
    .tp_methods = HighPerfLRUCache_methods,
};

/* 初始化LRU缓存 */
static PyObject* HighPerfLRUCache_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    HighPerfLRUCache *self;
    Py_ssize_t maxsize = 128;

    if (!PyArg_ParseTuple(args, "|n", &maxsize)) {
        return NULL;
    }

    if (maxsize <= 0) {
        maxsize = 128;
    }

    self = (HighPerfLRUCache *)type->tp_alloc(type, 0);
    if (self != NULL) {
        InitializeCriticalSection(&self->lock);
        self->maxsize = maxsize;
        self->size = 0;
        self->head = NULL;
        self->tail = NULL;
        self->cache = PyDict_New();
        if (self->cache == NULL) {
            DeleteCriticalSection(&self->lock);
            Py_DECREF(self);
            return NULL;
        }
    }
    return (PyObject *)self;
}

/* 清理LRU缓存 */
static void HighPerfLRUCache_dealloc(HighPerfLRUCache *self) {
    EnterCriticalSection(&self->lock);

    /* 释放所有节点 */
    LRUNode *node = self->head;
    while (node != NULL) {
        LRUNode *next = node->next;
        Py_XDECREF(node->key);
        Py_XDECREF(node->value);
        free(node);
        node = next;
    }

    Py_XDECREF(self->cache);
    LeaveCriticalSection(&self->lock);
    DeleteCriticalSection(&self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 获取值 */
static PyObject* HighPerfLRUCache_get(HighPerfLRUCache *self, PyObject *args) {
    PyObject *key;
    PyObject *node_obj = NULL;
    LRUNode *node = NULL;
    PyObject *value = NULL;

    if (!PyArg_ParseTuple(args, "O", &key)) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);

    node_obj = PyDict_GetItem(self->cache, key);
    if (node_obj == NULL) {
        LeaveCriticalSection(&self->lock);
        PyErr_SetString(PyExc_KeyError, "Key not found");
        return NULL;
    }

    /* 获取节点 */
    node = (LRUNode *)PyLong_AsVoidPtr(node_obj);
    value = node->value;
    Py_INCREF(value);

    /* 移动到头部 */
    if (node != self->head) {
        if (node->prev != NULL) {
            node->prev->next = node->next;
        }
        if (node->next != NULL) {
            node->next->prev = node->prev;
        }
        if (node == self->tail) {
            self->tail = node->prev;
        }

        node->prev = NULL;
        node->next = self->head;
        if (self->head != NULL) {
            self->head->prev = node;
        }
        self->head = node;
    }

    LeaveCriticalSection(&self->lock);

    return value;
}

/* 设置值 */
static PyObject* HighPerfLRUCache_set(HighPerfLRUCache *self, PyObject *args) {
    PyObject *key, *value;
    PyObject *node_obj = NULL;
    LRUNode *node = NULL;

    if (!PyArg_ParseTuple(args, "OO", &key, &value)) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);

    node_obj = PyDict_GetItem(self->cache, key);
    if (node_obj != NULL) {
        /* 更新现有节点 */
        node = (LRUNode *)PyLong_AsVoidPtr(node_obj);
        Py_XDECREF(node->value);
        Py_INCREF(value);
        node->value = value;

        /* 移动到头部 */
        if (node != self->head) {
            if (node->prev != NULL) {
                node->prev->next = node->next;
            }
            if (node->next != NULL) {
                node->next->prev = node->prev;
            }
            if (node == self->tail) {
                self->tail = node->prev;
            }

            node->prev = NULL;
            node->next = self->head;
            if (self->head != NULL) {
                self->head->prev = node;
            }
            self->head = node;
        }
    } else {
        /* 创建新节点 */
        node = (LRUNode *)malloc(sizeof(LRUNode));
        if (node == NULL) {
            LeaveCriticalSection(&self->lock);
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate LRU node");
            return NULL;
        }

        Py_INCREF(key);
        Py_INCREF(value);
        node->key = key;
        node->value = value;
        node->prev = NULL;
        node->next = self->head;

        if (self->head != NULL) {
            self->head->prev = node;
        }
        self->head = node;

        if (self->tail == NULL) {
            self->tail = node;
        }

        /* 添加到字典 */
        node_obj = PyLong_FromVoidPtr(node);
        if (PyDict_SetItem(self->cache, key, node_obj) < 0) {
            Py_DECREF(node_obj);
            LeaveCriticalSection(&self->lock);
            return NULL;
        }
        Py_DECREF(node_obj);

        self->size++;

        /* 检查是否需要删除最旧的节点 */
        if (self->size > self->maxsize) {
            LRUNode *oldest = self->tail;
            if (oldest != NULL) {
                self->tail = oldest->prev;
                if (self->tail != NULL) {
                    self->tail->next = NULL;
                }

                PyDict_DelItem(self->cache, oldest->key);
                Py_XDECREF(oldest->key);
                Py_XDECREF(oldest->value);
                free(oldest);
                self->size--;
            }
        }
    }

    LeaveCriticalSection(&self->lock);
    Py_RETURN_NONE;
}

/* 获取大小 */
static PyObject* HighPerfLRUCache_size(HighPerfLRUCache *self, PyObject *args) {
    Py_ssize_t size;

    EnterCriticalSection(&self->lock);
    size = self->size;
    LeaveCriticalSection(&self->lock);

    return PyLong_FromSsize_t(size);
}

/* 获取类型对象 */
PyTypeObject* get_LRUCacheType(void) {
    return &HighPerfLRUCacheType;
}

