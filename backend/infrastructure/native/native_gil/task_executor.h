/* -*- coding: utf-8 -*-
 * CPU密集型任务执行器头文件
 * 
 * 提供多线程并行执行CPU密集型任务的能力
 */

#ifndef TASK_EXECUTOR_H
#define TASK_EXECUTOR_H

#include <Python.h>
#include <Windows.h>

/* 任务回调函数类型 */
typedef PyObject* (*TaskCallback)(void *data, Py_ssize_t task_id);

/* 任务上下文结构 */
typedef struct {
    TaskCallback callback;
    void *data;
    Py_ssize_t task_id;
    PyObject *result;
    PyObject *error;
    HANDLE thread_handle;
    DWORD thread_id;
} TaskContext;

/* 执行单个CPU密集型任务 */
PyObject* execute_cpu_task(
    TaskCallback callback,
    void *data,
    Py_ssize_t task_id
);

/* 批量执行CPU密集型任务（并行） */
PyObject* execute_cpu_tasks_parallel(
    TaskCallback callback,
    void **data_array,
    Py_ssize_t task_count,
    Py_ssize_t max_threads
);

/* 线程入口函数 */
DWORD WINAPI task_thread_proc(LPVOID lpParam);

/* Python可调用的函数声明 */
static PyObject* task_execute_single(PyObject *self, PyObject *args);
static PyObject* task_execute_parallel(PyObject *self, PyObject *args);

#endif /* TASK_EXECUTOR_H */

