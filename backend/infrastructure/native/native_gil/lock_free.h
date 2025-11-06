/* -*- coding: utf-8 -*-
 * 无锁数据结构头文件
 */

#ifndef LOCK_FREE_H
#define LOCK_FREE_H

#include <Python.h>
#include <Windows.h>

/* 无锁队列类型定义 */
typedef struct {
    PyObject_HEAD
    volatile PyObject **items;
    volatile LONG64 head;  /* 使用LONG64类型以便原子操作 */
    volatile LONG64 tail;  /* 使用LONG64类型以便原子操作 */
    Py_ssize_t capacity;
} LockFreeQueue;

/* 无锁哈希表类型定义 */
typedef struct {
    PyObject_HEAD
    volatile PyObject **buckets;
    Py_ssize_t bucket_count;
} LockFreeHashMap;

/* 类型对象声明 */
extern PyTypeObject LockFreeQueueType;
extern PyTypeObject LockFreeHashMapType;

/* 函数声明 */
PyTypeObject* get_LockFreeQueueType(void);
PyTypeObject* get_LockFreeHashMapType(void);

#endif /* LOCK_FREE_H */

