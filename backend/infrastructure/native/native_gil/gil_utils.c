/* -*- coding: utf-8 -*-
 * GIL管理工具实现
 *
 * 提供底层的GIL释放/获取接口
 * 阶段11埋点：记录关键GIL操作的参数与返回码，便于排查权限/资源问题
 */

#include <Python.h>
#include <stdio.h>
#include "gil_utils.h"

/* 包含日志桥接头文件 */
#include "../native_log_bridge.h"

#define COMPONENT_GIL_CORE "backend.native.gil.core"

/* 释放GIL，返回线程状态 */
PyThreadState* gil_release(void) {
    /* 阶段11埋点：记录GIL释放操作 */
    NATIVE_LOG_DEBUG(COMPONENT_GIL_CORE, "gil_release", __LINE__, "释放GIL开始");
    PyThreadState *result = PyEval_SaveThread();
    char msg[256];
    sprintf(msg, "GIL释放完成: thread_state=%p, 场景=GIL管理", result);
    NATIVE_LOG_INFO(COMPONENT_GIL_CORE, "gil_release", __LINE__, msg);
    return result;
}

/* 恢复GIL（使用之前的线程状态） */
void gil_restore(PyThreadState *tstate) {
    /* 阶段11埋点：记录GIL恢复操作 */
    char msg[256];
    sprintf(msg, "恢复GIL开始: thread_state=%p, 场景=GIL管理", tstate);
    NATIVE_LOG_DEBUG(COMPONENT_GIL_CORE, "gil_restore", __LINE__, msg);

    if (tstate != NULL) {
        PyEval_RestoreThread(tstate);
        NATIVE_LOG_INFO(COMPONENT_GIL_CORE, "gil_restore", __LINE__, "GIL恢复完成");
    } else {
        NATIVE_LOG_ERROR(COMPONENT_GIL_CORE, "gil_restore", __LINE__, "GIL恢复失败: thread_state=NULL, 场景=GIL管理");
    }
}

/* 创建GIL上下文 */
GilContext* gil_context_enter(void) {
    /* 阶段11埋点：记录GIL上下文创建开始 */
    NATIVE_LOG_DEBUG(COMPONENT_GIL_CORE, "gil_context_enter", __LINE__, "创建GIL上下文开始");

    GilContext *ctx = (GilContext *)malloc(sizeof(GilContext));
    if (ctx == NULL) {
        /* 阶段11埋点：记录GIL上下文创建失败 */
        NATIVE_LOG_ERROR(COMPONENT_GIL_CORE, "gil_context_enter", __LINE__, "GIL上下文创建失败: malloc返回NULL, 场景=GIL上下文管理");
        return NULL;
    }

    ctx->saved_state = gil_release();

    /* 阶段11埋点：记录GIL上下文创建成功 */
    char msg[256];
    sprintf(msg, "GIL上下文创建成功: context=%p, thread_state=%p, 场景=GIL上下文管理", ctx, ctx->saved_state);
    NATIVE_LOG_INFO(COMPONENT_GIL_CORE, "gil_context_enter", __LINE__, msg);

    return ctx;
}

/* 释放GIL上下文 */
void gil_context_exit(GilContext *ctx) {
    if (ctx != NULL) {
        /* 阶段11埋点：记录GIL上下文释放开始 */
        char msg[256];
        sprintf(msg, "释放GIL上下文开始: context=%p, thread_state=%p, 场景=GIL上下文管理", ctx, ctx->saved_state);
        NATIVE_LOG_DEBUG(COMPONENT_GIL_CORE, "gil_context_exit", __LINE__, msg);

        gil_restore(ctx->saved_state);
        free(ctx);

        /* 阶段11埋点：记录GIL上下文释放完成 */
        NATIVE_LOG_INFO(COMPONENT_GIL_CORE, "gil_context_exit", __LINE__, "GIL上下文释放完成");
    } else {
        /* 阶段11埋点：记录GIL上下文释放失败 */
        NATIVE_LOG_WARNING(COMPONENT_GIL_CORE, "gil_context_exit", __LINE__, "GIL上下文释放跳过: context=NULL, 场景=GIL上下文管理");
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

