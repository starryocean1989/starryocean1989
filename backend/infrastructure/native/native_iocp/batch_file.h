/* -*- coding: utf-8 -*-
 * 批量文件操作头文件
 */

#ifndef BATCH_FILE_H
#define BATCH_FILE_H

#include <Python.h>
#include <Windows.h>

/* 批量文件操作函数声明 */
PyObject* batch_file_exists(PyObject *self, PyObject *args);
PyObject* batch_file_delete(PyObject *self, PyObject *args);
PyObject* batch_file_stat(PyObject *self, PyObject *args);

#endif /* BATCH_FILE_H */

