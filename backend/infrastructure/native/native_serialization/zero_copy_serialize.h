#ifndef ZERO_COPY_SERIALIZE_H
#define ZERO_COPY_SERIALIZE_H

#include <Python.h>

/* 核心零拷贝序列化实现（返回新的引用） */
PyObject *zero_copy_serialize_object(PyObject *obj);

/* Python可调用包装函数 */
PyObject *zero_copy_serialize_func(PyObject *self, PyObject *args);

#endif /* ZERO_COPY_SERIALIZE_H */

