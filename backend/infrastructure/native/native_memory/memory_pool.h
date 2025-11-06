/* -*- coding: utf-8 -*-
 * 内存池头文件
 */

#ifndef MEMORY_POOL_H
#define MEMORY_POOL_H

#include <Python.h>
#include <Windows.h>

/* MemoryPool类型定义 */
typedef struct {
    PyObject_HEAD
    CRITICAL_SECTION lock;
    PyObject **pool;
    Py_ssize_t size;
    Py_ssize_t capacity;
    Py_ssize_t obj_size;
} MemoryPool;

/* 类型对象声明 */
extern PyTypeObject MemoryPoolType;

/* 函数声明 */
PyTypeObject* get_MemoryPoolType(void);

#endif /* MEMORY_POOL_H */

