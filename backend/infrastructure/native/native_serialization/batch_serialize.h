#ifndef BATCH_SERIALIZE_H
#define BATCH_SERIALIZE_H

#include <Python.h>

/* 函数声明 */
PyObject* batch_serialize_func(PyObject *self, PyObject *args);
PyObject* batch_deserialize_func(PyObject *self, PyObject *args);

#endif /* BATCH_SERIALIZE_H */

