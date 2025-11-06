/* -*- coding: utf-8 -*-
 * 高性能事件/条件变量头文件
 */

#ifndef HIGH_PERF_EVENT_H
#define HIGH_PERF_EVENT_H

#include <Python.h>
#include <Windows.h>

/* 高性能事件类型定义 */
typedef struct {
    PyObject_HEAD
    HANDLE hEvent;
    volatile LONG state;
} HighPerfEvent;

/* 高性能条件变量类型定义 */
typedef struct {
    PyObject_HEAD
    HANDLE hEvent;
    CRITICAL_SECTION lock;
    volatile LONG waiters;
} HighPerfCondition;

/* 类型对象声明 */
extern PyTypeObject HighPerfEventType;
extern PyTypeObject HighPerfConditionType;

/* 函数声明 */
PyTypeObject* get_HighPerfEventType(void);
PyTypeObject* get_HighPerfConditionType(void);

#endif /* HIGH_PERF_EVENT_H */

