/* -*- coding: utf-8 -*-
 * 高性能目录遍历头文件
 */

#ifndef DIR_TRAVERSAL_H
#define DIR_TRAVERSAL_H

#include <Python.h>
#include <Windows.h>

/* 目录遍历函数声明 */
PyObject* fast_dir_walk(PyObject *self, PyObject *args);
PyObject* fast_dir_list(PyObject *self, PyObject *args);

#endif /* DIR_TRAVERSAL_H */

