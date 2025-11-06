/* -*- coding: utf-8 -*-
 * 零拷贝内存操作头文件
 */

#ifndef ZERO_COPY_H
#define ZERO_COPY_H

#include <Python.h>

/* ZeroCopyMemory类型定义 */
typedef struct {
    PyObject_HEAD
    PyObject *data;
    Py_buffer buffer;
    int is_view;  /* 标记是否为视图（非零表示是视图） */
} ZeroCopyMemory;

/* 类型对象声明 */
extern PyTypeObject ZeroCopyMemoryType;

/* 函数声明 */
PyTypeObject* get_ZeroCopyMemoryType(void);

#endif /* ZERO_COPY_H */

