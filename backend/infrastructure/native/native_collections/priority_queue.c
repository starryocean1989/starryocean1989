/* -*- coding: utf-8 -*-
 * 高性能优先级队列实现
 *
 * 使用C实现优先级队列，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>
#include "priority_queue.h"

/* 使用头文件中定义的HighPerfPriorityQueue结构 */

/* 优先级队列节点结构 */
typedef struct _PriorityNode {
    PyObject *item;
    long priority;
    struct _PriorityNode *next;
} PriorityNode;

/* 方法声明 */
static PyObject* HighPerfPriorityQueue_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void HighPerfPriorityQueue_dealloc(HighPerfPriorityQueue *self);
static PyObject* HighPerfPriorityQueue_put(HighPerfPriorityQueue *self, PyObject *args);
static PyObject* HighPerfPriorityQueue_get(HighPerfPriorityQueue *self, PyObject *args);
static PyObject* HighPerfPriorityQueue_size(HighPerfPriorityQueue *self, PyObject *args);

/* 方法定义 */
static PyMethodDef HighPerfPriorityQueue_methods[] = {
    {"put", (PyCFunction)HighPerfPriorityQueue_put, METH_VARARGS, "Put item with priority"},
    {"get", (PyCFunction)HighPerfPriorityQueue_get, METH_NOARGS, "Get item with highest priority"},
    {"size", (PyCFunction)HighPerfPriorityQueue_size, METH_NOARGS, "Get queue size"},
    {NULL, NULL, 0, NULL}
};

/* 类型定义 */
PyTypeObject HighPerfPriorityQueueType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_collections.HighPerfPriorityQueue",
    .tp_doc = "High-performance priority queue",
    .tp_basicsize = sizeof(HighPerfPriorityQueue),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = HighPerfPriorityQueue_new,
    .tp_dealloc = (destructor)HighPerfPriorityQueue_dealloc,
    .tp_methods = HighPerfPriorityQueue_methods,
};

/* 初始化优先级队列 */
static PyObject* HighPerfPriorityQueue_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    HighPerfPriorityQueue *self;

    self = (HighPerfPriorityQueue *)type->tp_alloc(type, 0);
    if (self != NULL) {
        InitializeCriticalSection(&self->lock);
        self->head = NULL;
        self->size = 0;
    }
    return (PyObject *)self;
}

/* 清理优先级队列 */
static void HighPerfPriorityQueue_dealloc(HighPerfPriorityQueue *self) {
    EnterCriticalSection(&self->lock);

    /* 释放所有节点 */
    PriorityNode *node = self->head;
    while (node != NULL) {
        PriorityNode *next = node->next;
        Py_XDECREF(node->item);
        free(node);
        node = next;
    }

    LeaveCriticalSection(&self->lock);
    DeleteCriticalSection(&self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 放入元素 */
static PyObject* HighPerfPriorityQueue_put(HighPerfPriorityQueue *self, PyObject *args) {
    PyObject *item;
    long priority = 0;
    PriorityNode *node = NULL;
    PriorityNode *current = NULL;
    PriorityNode *prev = NULL;

    if (!PyArg_ParseTuple(args, "Ol", &item, &priority)) {
        return NULL;
    }

    /* 创建节点 */
    node = (PriorityNode *)malloc(sizeof(PriorityNode));
    if (node == NULL) {
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate priority node");
        return NULL;
    }

    Py_INCREF(item);
    node->item = item;
    node->priority = priority;
    node->next = NULL;

    EnterCriticalSection(&self->lock);

    /* 插入到合适的位置（按优先级降序） */
    current = self->head;
    while (current != NULL && current->priority >= priority) {
        prev = current;
        current = current->next;
    }

    if (prev == NULL) {
        /* 插入到头部 */
        node->next = self->head;
        self->head = node;
    } else {
        /* 插入到中间或尾部 */
        node->next = prev->next;
        prev->next = node;
    }

    self->size++;
    LeaveCriticalSection(&self->lock);

    Py_RETURN_NONE;
}

/* 获取元素 */
static PyObject* HighPerfPriorityQueue_get(HighPerfPriorityQueue *self, PyObject *args) {
    PriorityNode *node = NULL;
    PyObject *item = NULL;

    EnterCriticalSection(&self->lock);

    if (self->head == NULL) {
        LeaveCriticalSection(&self->lock);
        PyErr_SetString(PyExc_IndexError, "Queue is empty");
        return NULL;
    }

    /* 获取头部节点（最高优先级） */
    node = self->head;
    self->head = node->next;
    self->size--;

    item = node->item;
    Py_INCREF(item);
    free(node);

    LeaveCriticalSection(&self->lock);

    return item;
}

/* 获取大小 */
static PyObject* HighPerfPriorityQueue_size(HighPerfPriorityQueue *self, PyObject *args) {
    Py_ssize_t size;

    EnterCriticalSection(&self->lock);
    size = self->size;
    LeaveCriticalSection(&self->lock);

    return PyLong_FromSsize_t(size);
}

/* 获取类型对象 */
PyTypeObject* get_PriorityQueueType(void) {
    return &HighPerfPriorityQueueType;
}

