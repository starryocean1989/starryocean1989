/* -*- coding: utf-8 -*-
 * 线程安全数据结构实现
 * 
 * 提供线程安全的队列、计数器等数据结构
 */

#include <Python.h>
#include <Windows.h>
#include <structmember.h>
#include "thread_safe.h"

/* ==================== ThreadSafeQueue ==================== */

/* ThreadSafeQueue类型定义 */
static PyTypeObject ThreadSafeQueueType;

/* 初始化队列 */
static PyObject* ThreadSafeQueue_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    ThreadSafeQueue *self;
    self = (ThreadSafeQueue *)type->tp_alloc(type, 0);
    if (self != NULL) {
        InitializeCriticalSection(&self->lock);
        self->capacity = 16;  /* 初始容量 */
        self->size = 0;
        self->head = 0;
        self->tail = 0;
        self->items = (PyObject **)malloc(sizeof(PyObject *) * self->capacity);
        if (self->items == NULL) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate queue items");
            return NULL;
        }
    }
    return (PyObject *)self;
}

/* 清理队列 */
static void ThreadSafeQueue_dealloc(ThreadSafeQueue *self) {
    EnterCriticalSection(&self->lock);
    
    /* 释放所有Python对象引用 */
    for (Py_ssize_t i = 0; i < self->size; i++) {
        Py_ssize_t index = (self->head + i) % self->capacity;
        Py_XDECREF(self->items[index]);
    }
    
    free(self->items);
    LeaveCriticalSection(&self->lock);
    DeleteCriticalSection(&self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 放入元素 */
static PyObject* ThreadSafeQueue_put(ThreadSafeQueue *self, PyObject *args) {
    PyObject *item;
    if (!PyArg_ParseTuple(args, "O", &item)) {
        return NULL;
    }
    
    EnterCriticalSection(&self->lock);
    
    /* 检查是否需要扩容 */
    if (self->size >= self->capacity) {
        Py_ssize_t new_capacity = self->capacity * 2;
        PyObject **new_items = (PyObject **)realloc(self->items, sizeof(PyObject *) * new_capacity);
        if (new_items == NULL) {
            LeaveCriticalSection(&self->lock);
            PyErr_SetString(PyExc_MemoryError, "Failed to resize queue");
            return NULL;
        }
        
        /* 重新排列元素 */
        if (self->head > self->tail) {
            /* 需要移动元素 */
            Py_ssize_t move_count = self->capacity - self->head;
            memmove(new_items + new_capacity - move_count, new_items + self->head, 
                    sizeof(PyObject *) * move_count);
            self->head = new_capacity - move_count;
        }
        
        self->items = new_items;
        self->capacity = new_capacity;
    }
    
    /* 放入元素 */
    Py_INCREF(item);
    self->items[self->tail] = item;
    self->tail = (self->tail + 1) % self->capacity;
    self->size++;
    
    LeaveCriticalSection(&self->lock);
    
    Py_RETURN_NONE;
}

/* 获取元素 */
static PyObject* ThreadSafeQueue_get(ThreadSafeQueue *self, PyObject *args) {
    PyObject *item = NULL;
    
    EnterCriticalSection(&self->lock);
    
    if (self->size == 0) {
        LeaveCriticalSection(&self->lock);
        PyErr_SetString(PyExc_IndexError, "Queue is empty");
        return NULL;
    }
    
    item = self->items[self->head];
    self->items[self->head] = NULL;
    self->head = (self->head + 1) % self->capacity;
    self->size--;
    
    LeaveCriticalSection(&self->lock);
    
    return item;
}

/* 获取队列大小 */
static PyObject* ThreadSafeQueue_size(ThreadSafeQueue *self, PyObject *args) {
    EnterCriticalSection(&self->lock);
    Py_ssize_t size = self->size;
    LeaveCriticalSection(&self->lock);
    
    return PyLong_FromSsize_t(size);
}

/* 检查队列是否为空 */
static PyObject* ThreadSafeQueue_empty(ThreadSafeQueue *self, PyObject *args) {
    EnterCriticalSection(&self->lock);
    int is_empty = (self->size == 0);
    LeaveCriticalSection(&self->lock);
    
    if (is_empty) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

/* ThreadSafeQueue方法定义 */
static PyMethodDef ThreadSafeQueue_methods[] = {
    {"put", (PyCFunction)ThreadSafeQueue_put, METH_VARARGS, "Put item into queue"},
    {"get", (PyCFunction)ThreadSafeQueue_get, METH_VARARGS, "Get item from queue"},
    {"size", (PyCFunction)ThreadSafeQueue_size, METH_NOARGS, "Get queue size"},
    {"empty", (PyCFunction)ThreadSafeQueue_empty, METH_NOARGS, "Check if queue is empty"},
    {NULL, NULL, 0, NULL}
};

PyTypeObject ThreadSafeQueueType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_gil.ThreadSafeQueue",
    .tp_doc = "Thread-safe queue",
    .tp_basicsize = sizeof(ThreadSafeQueue),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = ThreadSafeQueue_new,
    .tp_dealloc = (destructor)ThreadSafeQueue_dealloc,
    .tp_methods = ThreadSafeQueue_methods,
};

/* ==================== ThreadSafeCounter ==================== */

/* ThreadSafeCounter类型定义 */
static PyTypeObject ThreadSafeCounterType;

/* 初始化计数器 */
static PyObject* ThreadSafeCounter_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    ThreadSafeCounter *self;
    Py_ssize_t initial_value = 0;
    
    if (!PyArg_ParseTuple(args, "|n", &initial_value)) {
        return NULL;
    }
    
    self = (ThreadSafeCounter *)type->tp_alloc(type, 0);
    if (self != NULL) {
        InitializeCriticalSection(&self->lock);
        self->value = initial_value;
    }
    return (PyObject *)self;
}

/* 清理计数器 */
static void ThreadSafeCounter_dealloc(ThreadSafeCounter *self) {
    DeleteCriticalSection(&self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 增加计数 */
static PyObject* ThreadSafeCounter_increment(ThreadSafeCounter *self, PyObject *args) {
    Py_ssize_t amount = 1;
    
    if (!PyArg_ParseTuple(args, "|n", &amount)) {
        return NULL;
    }
    
    EnterCriticalSection(&self->lock);
    self->value += amount;
    Py_ssize_t result = self->value;
    LeaveCriticalSection(&self->lock);
    
    return PyLong_FromSsize_t(result);
}

/* 减少计数 */
static PyObject* ThreadSafeCounter_decrement(ThreadSafeCounter *self, PyObject *args) {
    Py_ssize_t amount = 1;
    
    if (!PyArg_ParseTuple(args, "|n", &amount)) {
        return NULL;
    }
    
    EnterCriticalSection(&self->lock);
    self->value -= amount;
    Py_ssize_t result = self->value;
    LeaveCriticalSection(&self->lock);
    
    return PyLong_FromSsize_t(result);
}

/* 获取当前值 */
static PyObject* ThreadSafeCounter_get(ThreadSafeCounter *self, PyObject *args) {
    EnterCriticalSection(&self->lock);
    Py_ssize_t value = self->value;
    LeaveCriticalSection(&self->lock);
    
    return PyLong_FromSsize_t(value);
}

/* 设置值 */
static PyObject* ThreadSafeCounter_set(ThreadSafeCounter *self, PyObject *args) {
    Py_ssize_t value;
    
    if (!PyArg_ParseTuple(args, "n", &value)) {
        return NULL;
    }
    
    EnterCriticalSection(&self->lock);
    self->value = value;
    LeaveCriticalSection(&self->lock);
    
    Py_RETURN_NONE;
}

/* ThreadSafeCounter方法定义 */
static PyMethodDef ThreadSafeCounter_methods[] = {
    {"increment", (PyCFunction)ThreadSafeCounter_increment, METH_VARARGS, "Increment counter"},
    {"decrement", (PyCFunction)ThreadSafeCounter_decrement, METH_VARARGS, "Decrement counter"},
    {"get", (PyCFunction)ThreadSafeCounter_get, METH_NOARGS, "Get current value"},
    {"set", (PyCFunction)ThreadSafeCounter_set, METH_VARARGS, "Set value"},
    {NULL, NULL, 0, NULL}
};

PyTypeObject ThreadSafeCounterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_gil.ThreadSafeCounter",
    .tp_doc = "Thread-safe counter",
    .tp_basicsize = sizeof(ThreadSafeCounter),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = ThreadSafeCounter_new,
    .tp_dealloc = (destructor)ThreadSafeCounter_dealloc,
    .tp_methods = ThreadSafeCounter_methods,
};

/* 导出类型 */
PyTypeObject* get_ThreadSafeQueueType(void) {
    return &ThreadSafeQueueType;
}

PyTypeObject* get_ThreadSafeCounterType(void) {
    return &ThreadSafeCounterType;
}

/* 初始化类型 */
int init_thread_safe_types(void) {
    if (PyType_Ready(&ThreadSafeQueueType) < 0) {
        return -1;
    }
    if (PyType_Ready(&ThreadSafeCounterType) < 0) {
        return -1;
    }
    return 0;
}

