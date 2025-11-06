#ifndef BATCH_STRING_H
#define BATCH_STRING_H

#include <Python.h>

/* 函数声明 */
PyObject* batch_encode_func(PyObject *self, PyObject *args);
PyObject* batch_decode_func(PyObject *self, PyObject *args);

#endif /* BATCH_STRING_H */

