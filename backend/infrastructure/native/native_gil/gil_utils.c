/* -*- coding: utf-8 -*-
 * GIL管理工具实现
 * 
 * 提供底层的GIL释放/获取接口
 */

#include <Python.h>
#include "gil_utils.h"

/* 释放GIL，返回线程状态 */
PyThreadState* gil_release(void) {
    return PyEval_SaveThread();
}

/* 恢复GIL（使用之前的线程状态） */
void gil_restore(PyThreadState *tstate) {
    if (tstate != NULL) {
        PyEval_RestoreThread(tstate);
    }
}

/* 创建GIL上下文 */
GilContext* gil_context_enter(void) {
    GilContext *ctx = (GilContext *)malloc(sizeof(GilContext));
    if (ctx == NULL) {
        return NULL;
    }
    ctx->saved_state = gil_release();
    return ctx;
}

/* 释放GIL上下文 */
void gil_context_exit(GilContext *ctx) {
    if (ctx != NULL) {
        gil_restore(ctx->saved_state);
        free(ctx);
    }
}

/* 执行CPU密集型任务（自动释放/恢复GIL） */
PyObject* gil_execute_cpu_task(
    PyObject *callable, 
    PyObject *args, 
    PyObject *kwargs
) {
    if (callable == NULL || !PyCallable_Check(callable)) {
        PyErr_SetString(PyExc_TypeError, "callable must be callable");
        return NULL;
    }

    /* 释放GIL */
    PyThreadState *tstate = gil_release();
    
    /* 注意：在无GIL状态下，不能调用Python C API
     * 这里需要调用Python函数，所以必须先恢复GIL
     * 实际应用中，CPU密集型任务应该在C扩展中实现
     */
    gil_restore(tstate);
    
    /* 调用Python函数 */
    PyObject *result = PyObject_Call(callable, args, kwargs);
    
    return result;
}

/* Python函数：释放GIL */
PyObject* gil_release_gil(PyObject *self, PyObject *args) {
    PyThreadState *tstate = gil_release();
    /* 返回线程状态对象（作为整数指针） */
    return PyLong_FromVoidPtr((void *)tstate);
}

/* Python函数：恢复GIL */
PyObject* gil_restore_gil(PyObject *self, PyObject *args) {
    PyObject *tstate_obj;
    if (!PyArg_ParseTuple(args, "O", &tstate_obj)) {
        return NULL;
    }
    
    PyThreadState *tstate = (PyThreadState *)PyLong_AsVoidPtr(tstate_obj);
    if (PyErr_Occurred()) {
        return NULL;
    }
    
    gil_restore(tstate);
    Py_RETURN_NONE;
}

/* Python函数：执行CPU密集型任务 */
PyObject* gil_execute_cpu_task_func(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *callable;
    PyObject *task_args = NULL;
    
    if (!PyArg_ParseTuple(args, "O|O", &callable, &task_args)) {
        return NULL;
    }
    
    if (task_args == NULL) {
        task_args = PyTuple_New(0);
    }
    
    return gil_execute_cpu_task(callable, task_args, kwargs);
}

