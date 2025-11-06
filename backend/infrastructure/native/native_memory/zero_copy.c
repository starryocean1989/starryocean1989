/* -*- coding: utf-8 -*-
 * 零拷贝内存操作实现
 *
 * 使用Py_buffer实现零拷贝内存视图
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include "zero_copy.h"

/* 方法声明 */
static PyObject* ZeroCopyMemory_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void ZeroCopyMemory_dealloc(ZeroCopyMemory *self);
static PyObject* ZeroCopyMemory_view(ZeroCopyMemory *self, PyObject *args);
static PyObject* ZeroCopyMemory_copy(ZeroCopyMemory *self, PyObject *args);
static PyObject* ZeroCopyMemory_get_size(ZeroCopyMemory *self, PyObject *args);

/* 方法定义 */
static PyMethodDef ZeroCopyMemory_methods[] = {
    {"view", (PyCFunction)ZeroCopyMemory_view, METH_NOARGS, "Get zero-copy memory view"},
    {"copy", (PyCFunction)ZeroCopyMemory_copy, METH_NOARGS, "Create a copy of the memory"},
    {"get_size", (PyCFunction)ZeroCopyMemory_get_size, METH_NOARGS, "Get memory size"},
    {NULL, NULL, 0, NULL}
};

/* ZeroCopyMemory类型定义 */
PyTypeObject ZeroCopyMemoryType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_memory.ZeroCopyMemory",
    .tp_doc = "Zero-copy memory view",
    .tp_basicsize = sizeof(ZeroCopyMemory),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = ZeroCopyMemory_new,
    .tp_dealloc = (destructor)ZeroCopyMemory_dealloc,
    .tp_methods = ZeroCopyMemory_methods,
};

/* 初始化ZeroCopyMemory */
static PyObject* ZeroCopyMemory_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    ZeroCopyMemory *self;
    PyObject *data;

    if (!PyArg_ParseTuple(args, "O", &data)) {
        return NULL;
    }

    self = (ZeroCopyMemory *)type->tp_alloc(type, 0);
    if (self != NULL) {
        /* 获取缓冲区视图（零拷贝） */
        if (PyObject_GetBuffer(data, &self->buffer, PyBUF_ANY_CONTIGUOUS) < 0) {
            Py_DECREF(self);
            return NULL;
        }

        Py_INCREF(data);
        self->data = data;
        self->is_view = 1;
    }
    return (PyObject *)self;
}

/* 清理ZeroCopyMemory */
static void ZeroCopyMemory_dealloc(ZeroCopyMemory *self) {
    if (self->is_view && self->buffer.obj != NULL) {
        PyBuffer_Release(&self->buffer);
    }
    Py_XDECREF(self->data);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 获取零拷贝视图 */
static PyObject* ZeroCopyMemory_view(ZeroCopyMemory *self, PyObject *args) {
    /* 返回memoryview对象（零拷贝） */
    return PyMemoryView_FromObject((PyObject *)self->data);
}

/* 创建副本 */
static PyObject* ZeroCopyMemory_copy(ZeroCopyMemory *self, PyObject *args) {
    /* 创建字节数组副本 */
    return PyBytes_FromStringAndSize((const char *)self->buffer.buf, self->buffer.len);
}

/* 获取大小 */
static PyObject* ZeroCopyMemory_get_size(ZeroCopyMemory *self, PyObject *args) {
    return PyLong_FromSsize_t(self->buffer.len);
}

/* 获取类型对象 */
PyTypeObject* get_ZeroCopyMemoryType(void) {
    return &ZeroCopyMemoryType;
}

