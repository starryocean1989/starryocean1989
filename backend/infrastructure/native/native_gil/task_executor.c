/* -*- coding: utf-8 -*-
 * CPU密集型任务执行器实现
 * 
 * 提供多线程并行执行CPU密集型任务的能力
 */

#include <Python.h>
#include <Windows.h>
#include <process.h>
#include "task_executor.h"
#include "gil_utils.h"

/* 线程入口函数 */
DWORD WINAPI task_thread_proc(LPVOID lpParam) {
    TaskContext *ctx = (TaskContext *)lpParam;
    
    /* 在新线程中，需要初始化Python线程状态 */
    /* 注意：新线程没有Python线程状态，需要从主线程传递interp，这里简化处理 */
    /* 实际应用中，应该从TaskContext中传递interp指针 */
    PyInterpreterState *interp = NULL;
    
    /* 尝试从主线程获取解释器状态（需要GIL） */
    /* 注意：这里假设主线程已经设置了线程状态 */
    PyGILState_STATE gstate = PyGILState_Ensure();
    
    /* 获取当前解释器状态 */
    PyThreadState *main_tstate = PyThreadState_Get();
    if (main_tstate != NULL) {
        interp = main_tstate->interp;
    }
    
    if (interp == NULL) {
        /* 无法获取解释器状态 */
        PyGILState_Release(gstate);
        ctx->error = NULL;
        return 1;
    }
    
    /* 创建新线程的线程状态 */
    PyThreadState *tstate = PyThreadState_New(interp);
    if (tstate == NULL) {
        PyGILState_Release(gstate);
        ctx->error = NULL;
        return 1;
    }
    
    /* 切换到新线程状态 */
    PyThreadState_Swap(tstate);
    PyGILState_Release(gstate);
    
    /* 释放GIL（每个线程独立） */
    PyThreadState *saved_tstate = gil_release();
    
    /* 执行任务（在无GIL状态下） */
    /* 注意：在无GIL状态下，不能调用Python C API
     * 实际应用中，回调函数应该是纯C函数，不涉及Python对象
     * 这里为了示例，我们假设回调函数会恢复GIL后再调用
     */
    gil_restore(saved_tstate);
    
    /* 调用回调函数（此时有GIL） */
    ctx->result = ctx->callback(ctx->data, ctx->task_id);
    
    if (ctx->result == NULL) {
        /* 回调函数返回NULL，可能有异常 */
        if (PyErr_Occurred()) {
            ctx->error = NULL;  /* 异常已在PyErr中 */
        } else {
            ctx->error = NULL;  /* 无异常，结果为空 */
        }
        /* 不清除异常，让调用者处理 */
    }
    
    /* 保存线程状态并清理 */
    saved_tstate = gil_release();
    gil_restore(saved_tstate);  /* 恢复GIL以便清理 */
    PyThreadState_Clear(tstate);
    PyThreadState_Delete(tstate);
    
    return 0;
}

/* 执行单个CPU密集型任务 */
PyObject* execute_cpu_task(
    TaskCallback callback,
    void *data,
    Py_ssize_t task_id
) {
    TaskContext ctx;
    ctx.callback = callback;
    ctx.data = data;
    ctx.task_id = task_id;
    ctx.result = NULL;
    ctx.error = NULL;
    
    /* 创建线程 */
    ctx.thread_handle = CreateThread(
        NULL,
        0,
        task_thread_proc,
        &ctx,
        0,
        &ctx.thread_id
    );
    
    if (ctx.thread_handle == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to create thread");
        return NULL;
    }
    
    /* 等待线程完成 */
    WaitForSingleObject(ctx.thread_handle, INFINITE);
    CloseHandle(ctx.thread_handle);
    
    /* 检查错误 */
    if (ctx.error != NULL) {
        PyErr_SetObject(PyExc_RuntimeError, ctx.error);
        Py_XDECREF(ctx.error);
        return NULL;
    }
    
    if (ctx.result == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Task returned NULL");
        return NULL;
    }
    
    return ctx.result;
}

/* 批量执行CPU密集型任务（并行） */
PyObject* execute_cpu_tasks_parallel(
    TaskCallback callback,
    void **data_array,
    Py_ssize_t task_count,
    Py_ssize_t max_threads
) {
    if (task_count <= 0) {
        return PyList_New(0);
    }
    
    if (max_threads <= 0) {
        max_threads = 4;  /* 默认4个线程 */
    }
    
    if (max_threads > task_count) {
        max_threads = task_count;
    }
    
    /* 创建任务上下文数组 */
    TaskContext *contexts = (TaskContext *)malloc(sizeof(TaskContext) * task_count);
    if (contexts == NULL) {
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate task contexts");
        return NULL;
    }
    
    /* 初始化所有任务上下文 */
    for (Py_ssize_t i = 0; i < task_count; i++) {
        contexts[i].callback = callback;
        contexts[i].data = data_array[i];
        contexts[i].task_id = i;
        contexts[i].result = NULL;
        contexts[i].error = NULL;
        contexts[i].thread_handle = NULL;
    }
    
    /* 创建线程执行任务 */
    Py_ssize_t active_threads = 0;
    Py_ssize_t next_task = 0;
    HANDLE *thread_handles = (HANDLE *)malloc(sizeof(HANDLE) * max_threads);
    if (thread_handles == NULL) {
        free(contexts);
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate thread handles");
        return NULL;
    }
    
    /* 启动初始批次线程 */
    while (active_threads < max_threads && next_task < task_count) {
        contexts[next_task].thread_handle = CreateThread(
            NULL,
            0,
            task_thread_proc,
            &contexts[next_task],
            0,
            &contexts[next_task].thread_id
        );
        
        if (contexts[next_task].thread_handle != NULL) {
            thread_handles[active_threads] = contexts[next_task].thread_handle;
            active_threads++;
            next_task++;
        } else {
            break;
        }
    }
    
    /* 等待线程完成并启动新任务 */
    while (active_threads > 0) {
        DWORD wait_result = WaitForMultipleObjects(active_threads, thread_handles, FALSE, INFINITE);
        if (wait_result >= WAIT_OBJECT_0 && wait_result < WAIT_OBJECT_0 + active_threads) {
            DWORD completed_index = wait_result - WAIT_OBJECT_0;
            CloseHandle(thread_handles[completed_index]);
            
            /* 移除已完成的线程 */
            for (DWORD i = completed_index; i < (DWORD)(active_threads - 1); i++) {
                thread_handles[i] = thread_handles[i + 1];
            }
            active_threads--;
            
            /* 启动新任务 */
            if (next_task < task_count) {
                contexts[next_task].thread_handle = CreateThread(
                    NULL,
                    0,
                    task_thread_proc,
                    &contexts[next_task],
                    0,
                    &contexts[next_task].thread_id
                );
                
                if (contexts[next_task].thread_handle != NULL) {
                    thread_handles[active_threads] = contexts[next_task].thread_handle;
                    active_threads++;
                    next_task++;
                }
            }
        }
    }
    
    free(thread_handles);
    
    /* 收集结果 */
    PyObject *results = PyList_New(task_count);
    if (results == NULL) {
        free(contexts);
        return NULL;
    }
    
    for (Py_ssize_t i = 0; i < task_count; i++) {
        if (contexts[i].error != NULL) {
            PyList_SetItem(results, i, Py_None);
            Py_INCREF(Py_None);
            Py_XDECREF(contexts[i].error);
        } else if (contexts[i].result != NULL) {
            PyList_SetItem(results, i, contexts[i].result);
        } else {
            PyList_SetItem(results, i, Py_None);
            Py_INCREF(Py_None);
        }
    }
    
    free(contexts);
    return results;
}

/* Python函数：执行单个任务 */
static PyObject* task_execute_single(PyObject *self, PyObject *args) {
    /* 这个函数需要Python回调，但C扩展中不能直接调用Python函数
     * 实际应用中，应该使用C函数作为回调
     * 这里仅作为示例接口
     */
    PyErr_SetString(PyExc_NotImplementedError, 
                    "Direct Python callable execution not supported. Use C callbacks.");
    return NULL;
}

/* Python函数：执行并行任务 */
static PyObject* task_execute_parallel(PyObject *self, PyObject *args) {
    /* 同上，需要C回调函数 */
    PyErr_SetString(PyExc_NotImplementedError, 
                    "Direct Python callable execution not supported. Use C callbacks.");
    return NULL;
}

