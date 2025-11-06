/* -*- coding: utf-8 -*-
 * 线程安全数据结构头文件
 * 
 * 提供线程安全的队列、计数器等数据结构
 */

#ifndef THREAD_SAFE_H
#define THREAD_SAFE_H

#include <Python.h>
#include <Windows.h>
#include <structmember.h>

/* 线程安全队列 */
typedef struct {
    PyObject_HEAD
    CRITICAL_SECTION lock;
    PyObject **items;
    Py_ssize_t size;
    Py_ssize_t capacity;
    Py_ssize_t head;
    Py_ssize_t tail;
} ThreadSafeQueue;

/* 线程安全计数器 */
typedef struct {
    PyObject_HEAD
    CRITICAL_SECTION lock;
    Py_ssize_t value;
} ThreadSafeCounter;

/* 类型对象声明 */
extern PyTypeObject ThreadSafeQueueType;
extern PyTypeObject ThreadSafeCounterType;

/* ThreadSafeQueue方法 */
static PyObject* ThreadSafeQueue_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void ThreadSafeQueue_dealloc(ThreadSafeQueue *self);
static PyObject* ThreadSafeQueue_put(ThreadSafeQueue *self, PyObject *args);
static PyObject* ThreadSafeQueue_get(ThreadSafeQueue *self, PyObject *args);
static PyObject* ThreadSafeQueue_size(ThreadSafeQueue *self, PyObject *args);
static PyObject* ThreadSafeQueue_empty(ThreadSafeQueue *self, PyObject *args);

/* ThreadSafeCounter方法 */
static PyObject* ThreadSafeCounter_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void ThreadSafeCounter_dealloc(ThreadSafeCounter *self);
static PyObject* ThreadSafeCounter_increment(ThreadSafeCounter *self, PyObject *args);
static PyObject* ThreadSafeCounter_decrement(ThreadSafeCounter *self, PyObject *args);
static PyObject* ThreadSafeCounter_get(ThreadSafeCounter *self, PyObject *args);
static PyObject* ThreadSafeCounter_set(ThreadSafeCounter *self, PyObject *args);

/* 导出函数 */
PyTypeObject* get_ThreadSafeQueueType(void);
PyTypeObject* get_ThreadSafeCounterType(void);
int init_thread_safe_types(void);

#endif /* THREAD_SAFE_H */

