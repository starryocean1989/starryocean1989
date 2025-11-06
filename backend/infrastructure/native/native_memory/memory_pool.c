/* -*- coding: utf-8 -*-
 * 内存池实现
 *
 * 使用Windows临界区实现线程安全的内存池
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <Windows.h>
#include "memory_pool.h"

/* 方法声明 */
static PyObject* MemoryPool_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void MemoryPool_dealloc(MemoryPool *self);
static PyObject* MemoryPool_alloc(MemoryPool *self, PyObject *args);
static PyObject* MemoryPool_free(MemoryPool *self, PyObject *args);
static PyObject* MemoryPool_size(MemoryPool *self, PyObject *args);
static PyObject* MemoryPool_capacity(MemoryPool *self, PyObject *args);

/* 方法定义 */
static PyMethodDef MemoryPool_methods[] = {
    {"alloc", (PyCFunction)MemoryPool_alloc, METH_NOARGS, "Allocate memory from pool"},
    {"free", (PyCFunction)MemoryPool_free, METH_VARARGS, "Free memory back to pool"},
    {"size", (PyCFunction)MemoryPool_size, METH_NOARGS, "Get pool size"},
    {"capacity", (PyCFunction)MemoryPool_capacity, METH_NOARGS, "Get pool capacity"},
    {NULL, NULL, 0, NULL}
};

/* MemoryPool类型定义 */
PyTypeObject MemoryPoolType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_memory.MemoryPool",
    .tp_doc = "Memory pool for efficient allocation/deallocation",
    .tp_basicsize = sizeof(MemoryPool),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = MemoryPool_new,
    .tp_dealloc = (destructor)MemoryPool_dealloc,
    .tp_methods = MemoryPool_methods,
};

/* 初始化内存池 */
static PyObject* MemoryPool_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    MemoryPool *self;
    Py_ssize_t size = 1024;
    Py_ssize_t count = 100;

    if (!PyArg_ParseTuple(args, "|nn", &size, &count)) {
        return NULL;
    }

    if (size <= 0) size = 1024;
    if (count <= 0) count = 100;

    self = (MemoryPool *)type->tp_alloc(type, 0);
    if (self != NULL) {
        InitializeCriticalSection(&self->lock);

        self->pool = (PyObject **)calloc(count, sizeof(PyObject *));
        if (self->pool == NULL) {
            DeleteCriticalSection(&self->lock);
            Py_DECREF(self);
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate memory pool");
            return NULL;
        }

        self->size = 0;
        self->capacity = count;
        self->obj_size = size;

        /* 预分配对象 */
        for (Py_ssize_t i = 0; i < count; i++) {
            PyObject *obj = PyBytes_FromStringAndSize(NULL, size);
            if (obj == NULL) {
                /* 清理已分配的对象 */
                for (Py_ssize_t j = 0; j < i; j++) {
                    Py_DECREF(self->pool[j]);
                }
                free(self->pool);
                DeleteCriticalSection(&self->lock);
                Py_DECREF(self);
                return NULL;
            }
            self->pool[i] = obj;
            self->size++;
        }
    }
    return (PyObject *)self;
}

/* 清理内存池 */
static void MemoryPool_dealloc(MemoryPool *self) {
    EnterCriticalSection(&self->lock);

    /* 释放所有对象 */
    for (Py_ssize_t i = 0; i < self->size; i++) {
        Py_XDECREF(self->pool[i]);
    }

    free(self->pool);
    LeaveCriticalSection(&self->lock);
    DeleteCriticalSection(&self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 分配内存 */
static PyObject* MemoryPool_alloc(MemoryPool *self, PyObject *args) {
    PyObject *obj = NULL;

    EnterCriticalSection(&self->lock);

    if (self->size > 0) {
        /* 从池中取出一个对象 */
        self->size--;
        obj = self->pool[self->size];
        self->pool[self->size] = NULL;
        Py_INCREF(obj);
    } else {
        /* 池为空，创建新对象 */
        obj = PyBytes_FromStringAndSize(NULL, self->obj_size);
    }

    LeaveCriticalSection(&self->lock);

    if (obj == NULL) {
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate memory from pool");
        return NULL;
    }

    return obj;
}

/* 释放内存 */
static PyObject* MemoryPool_free(MemoryPool *self, PyObject *args) {
    PyObject *obj;

    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);

    if (self->size < self->capacity) {
        /* 归还到池中 */
        Py_INCREF(obj);
        self->pool[self->size] = obj;
        self->size++;
        LeaveCriticalSection(&self->lock);
        Py_RETURN_NONE;
    } else {
        /* 池已满，直接释放 */
        LeaveCriticalSection(&self->lock);
        Py_RETURN_NONE;
    }
}

/* 获取池大小 */
static PyObject* MemoryPool_size(MemoryPool *self, PyObject *args) {
    Py_ssize_t size;

    EnterCriticalSection(&self->lock);
    size = self->size;
    LeaveCriticalSection(&self->lock);

    return PyLong_FromSsize_t(size);
}

/* 获取池容量 */
static PyObject* MemoryPool_capacity(MemoryPool *self, PyObject *args) {
    return PyLong_FromSsize_t(self->capacity);
}

/* 获取类型对象 */
PyTypeObject* get_MemoryPoolType(void) {
    return &MemoryPoolType;
}

