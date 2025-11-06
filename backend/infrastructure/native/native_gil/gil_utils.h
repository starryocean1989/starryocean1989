/* -*- coding: utf-8 -*-
 * GIL管理工具头文件
 * 
 * 提供底层的GIL释放/获取接口，供其他C扩展使用
 */

#ifndef GIL_UTILS_H
#define GIL_UTILS_H

#include <Python.h>

/* GIL上下文结构 */
typedef struct {
    PyThreadState *saved_state;
} GilContext;

/* 释放GIL，返回线程状态 */
PyThreadState* gil_release(void);

/* 恢复GIL（使用之前的线程状态） */
void gil_restore(PyThreadState *tstate);

/* 创建GIL上下文 */
GilContext* gil_context_enter(void);

/* 释放GIL上下文 */
void gil_context_exit(GilContext *ctx);

/* 执行CPU密集型任务（自动释放/恢复GIL） */
PyObject* gil_execute_cpu_task(
    PyObject *callable, 
    PyObject *args, 
    PyObject *kwargs
);

/* Python可调用的函数声明 */
PyObject* gil_release_gil(PyObject *self, PyObject *args);
PyObject* gil_restore_gil(PyObject *self, PyObject *args);
PyObject* gil_execute_cpu_task_func(PyObject *self, PyObject *args, PyObject *kwargs);

#endif /* GIL_UTILS_H */

