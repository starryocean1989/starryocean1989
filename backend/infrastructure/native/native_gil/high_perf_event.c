/* -*- coding: utf-8 -*-
 * 高性能事件/条件变量实现
 *
 * 使用Windows Event对象实现高性能同步原语
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>
#include "high_perf_event.h"

/* ==================== HighPerfEvent 实现 ==================== */

/* 方法声明 */
static PyObject* HighPerfEvent_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void HighPerfEvent_dealloc(HighPerfEvent *self);
static PyObject* HighPerfEvent_set(HighPerfEvent *self, PyObject *args);
static PyObject* HighPerfEvent_clear(HighPerfEvent *self, PyObject *args);
static PyObject* HighPerfEvent_wait(HighPerfEvent *self, PyObject *args);
static PyObject* HighPerfEvent_is_set(HighPerfEvent *self, PyObject *args);

/* 方法定义 */
static PyMethodDef HighPerfEvent_methods[] = {
    {"set", (PyCFunction)HighPerfEvent_set, METH_NOARGS, "Set event"},
    {"clear", (PyCFunction)HighPerfEvent_clear, METH_NOARGS, "Clear event"},
    {"wait", (PyCFunction)HighPerfEvent_wait, METH_VARARGS, "Wait for event"},
    {"is_set", (PyCFunction)HighPerfEvent_is_set, METH_NOARGS, "Check if event is set"},
    {NULL, NULL, 0, NULL}
};

/* HighPerfEvent类型定义 */
PyTypeObject HighPerfEventType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_gil.HighPerfEvent",
    .tp_doc = "High-performance event for Windows",
    .tp_basicsize = sizeof(HighPerfEvent),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = HighPerfEvent_new,
    .tp_dealloc = (destructor)HighPerfEvent_dealloc,
    .tp_methods = HighPerfEvent_methods,
};

/* 初始化事件 */
static PyObject* HighPerfEvent_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    HighPerfEvent *self;

    self = (HighPerfEvent *)type->tp_alloc(type, 0);
    if (self != NULL) {
        /* 创建Windows事件对象（自动重置事件） */
        self->hEvent = CreateEventA(
            NULL,  /* 默认安全属性 */
            FALSE, /* 自动重置 */
            FALSE, /* 初始状态为未设置 */
            NULL   /* 匿名事件 */
        );

        if (self->hEvent == NULL) {
            Py_DECREF(self);
            PyErr_SetFromWindowsErr(0);
            return NULL;
        }

        self->state = 0;
    }
    return (PyObject *)self;
}

/* 清理事件 */
static void HighPerfEvent_dealloc(HighPerfEvent *self) {
    if (self->hEvent != NULL) {
        CloseHandle(self->hEvent);
        self->hEvent = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 设置事件 */
static PyObject* HighPerfEvent_set(HighPerfEvent *self, PyObject *args) {
    if (SetEvent(self->hEvent) == 0) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    InterlockedExchange(&self->state, 1);
    Py_RETURN_NONE;
}

/* 清除事件 */
static PyObject* HighPerfEvent_clear(HighPerfEvent *self, PyObject *args) {
    if (ResetEvent(self->hEvent) == 0) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    InterlockedExchange(&self->state, 0);
    Py_RETURN_NONE;
}

/* 等待事件 */
static PyObject* HighPerfEvent_wait(HighPerfEvent *self, PyObject *args) {
    DWORD timeout = INFINITE;

    if (!PyArg_ParseTuple(args, "|k", &timeout)) {
        return NULL;
    }

    DWORD result = WaitForSingleObject(self->hEvent, timeout);

    if (result == WAIT_OBJECT_0) {
        Py_RETURN_TRUE;
    } else if (result == WAIT_TIMEOUT) {
        Py_RETURN_FALSE;
    } else {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
}

/* 检查事件是否已设置 */
static PyObject* HighPerfEvent_is_set(HighPerfEvent *self, PyObject *args) {
    DWORD result = WaitForSingleObject(self->hEvent, 0);

    if (result == WAIT_OBJECT_0) {
        /* 事件已设置，需要重置（因为这是自动重置事件） */
        SetEvent(self->hEvent);
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

/* ==================== HighPerfCondition 实现 ==================== */

/* 方法声明 */
static PyObject* HighPerfCondition_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void HighPerfCondition_dealloc(HighPerfCondition *self);
static PyObject* HighPerfCondition_wait(HighPerfCondition *self, PyObject *args);
static PyObject* HighPerfCondition_notify(HighPerfCondition *self, PyObject *args);
static PyObject* HighPerfCondition_notify_all(HighPerfCondition *self, PyObject *args);

/* 方法定义 */
static PyMethodDef HighPerfCondition_methods[] = {
    {"wait", (PyCFunction)HighPerfCondition_wait, METH_VARARGS, "Wait for condition"},
    {"notify", (PyCFunction)HighPerfCondition_notify, METH_NOARGS, "Notify one waiter"},
    {"notify_all", (PyCFunction)HighPerfCondition_notify_all, METH_NOARGS, "Notify all waiters"},
    {NULL, NULL, 0, NULL}
};

/* HighPerfCondition类型定义 */
PyTypeObject HighPerfConditionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_gil.HighPerfCondition",
    .tp_doc = "High-performance condition variable for Windows",
    .tp_basicsize = sizeof(HighPerfCondition),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = HighPerfCondition_new,
    .tp_dealloc = (destructor)HighPerfCondition_dealloc,
    .tp_methods = HighPerfCondition_methods,
};

/* 初始化条件变量 */
static PyObject* HighPerfCondition_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    HighPerfCondition *self;

    self = (HighPerfCondition *)type->tp_alloc(type, 0);
    if (self != NULL) {
        /* 初始化临界区 */
        InitializeCriticalSection(&self->lock);

        /* 创建Windows事件对象 */
        self->hEvent = CreateEventA(
            NULL,  /* 默认安全属性 */
            TRUE,  /* 手动重置 */
            FALSE, /* 初始状态为未设置 */
            NULL   /* 匿名事件 */
        );

        if (self->hEvent == NULL) {
            DeleteCriticalSection(&self->lock);
            Py_DECREF(self);
            PyErr_SetFromWindowsErr(0);
            return NULL;
        }

        self->waiters = 0;
    }
    return (PyObject *)self;
}

/* 清理条件变量 */
static void HighPerfCondition_dealloc(HighPerfCondition *self) {
    if (self->hEvent != NULL) {
        CloseHandle(self->hEvent);
        self->hEvent = NULL;
    }
    DeleteCriticalSection(&self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 等待条件 */
static PyObject* HighPerfCondition_wait(HighPerfCondition *self, PyObject *args) {
    DWORD timeout = INFINITE;

    if (!PyArg_ParseTuple(args, "|k", &timeout)) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);
    InterlockedIncrement(&self->waiters);
    LeaveCriticalSection(&self->lock);

    DWORD result = WaitForSingleObject(self->hEvent, timeout);

    EnterCriticalSection(&self->lock);
    InterlockedDecrement(&self->waiters);
    LeaveCriticalSection(&self->lock);

    if (result == WAIT_OBJECT_0) {
        Py_RETURN_TRUE;
    } else if (result == WAIT_TIMEOUT) {
        Py_RETURN_FALSE;
    } else {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
}

/* 通知一个等待者 */
static PyObject* HighPerfCondition_notify(HighPerfCondition *self, PyObject *args) {
    EnterCriticalSection(&self->lock);

    if (self->waiters > 0) {
        SetEvent(self->hEvent);
        ResetEvent(self->hEvent);
    }

    LeaveCriticalSection(&self->lock);
    Py_RETURN_NONE;
}

/* 通知所有等待者 */
static PyObject* HighPerfCondition_notify_all(HighPerfCondition *self, PyObject *args) {
    EnterCriticalSection(&self->lock);

    if (self->waiters > 0) {
        SetEvent(self->hEvent);
        ResetEvent(self->hEvent);
    }

    LeaveCriticalSection(&self->lock);
    Py_RETURN_NONE;
}

/* 获取类型对象 */
PyTypeObject* get_HighPerfEventType(void) {
    return &HighPerfEventType;
}

PyTypeObject* get_HighPerfConditionType(void) {
    return &HighPerfConditionType;
}

