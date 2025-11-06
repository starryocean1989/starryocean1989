/* -*- coding: utf-8 -*-
 * native_memory主模块
 *
 * 统一导出所有功能，提供Python模块接口
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>

/* 前向声明 */
extern PyTypeObject* get_ZeroCopyMemoryType(void);
extern PyTypeObject* get_MemoryPoolType(void);

/* 批量操作函数声明 */
static PyObject* batch_alloc_func(PyObject *self, PyObject *args);
static PyObject* batch_free_func(PyObject *self, PyObject *args);

/* 方法定义 */
static PyMethodDef MemoryMethods[] = {
    {"batch_alloc", batch_alloc_func, METH_VARARGS, "Batch allocate memory objects"},
    {"batch_free", batch_free_func, METH_VARARGS, "Batch free memory objects"},
    {NULL, NULL, 0, NULL}
};

/* 模块初始化 */
static struct PyModuleDef native_memorymodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_memory",
    .m_doc = "Native memory operations (zero-copy and memory pool) for Windows",
    .m_size = -1,
    .m_methods = MemoryMethods,
};

PyMODINIT_FUNC PyInit_native_memory(void) {
    PyObject *m;

    /* 创建模块 */
    m = PyModule_Create(&native_memorymodule);
    if (m == NULL) {
        return NULL;
    }

    /* 添加ZeroCopyMemory类型 */
    if (PyType_Ready(get_ZeroCopyMemoryType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_ZeroCopyMemoryType());
    if (PyModule_AddObject(m, "ZeroCopyMemory", (PyObject *)get_ZeroCopyMemoryType()) < 0) {
        Py_DECREF(get_ZeroCopyMemoryType());
        Py_DECREF(m);
        return NULL;
    }

    /* 添加MemoryPool类型 */
    if (PyType_Ready(get_MemoryPoolType()) < 0) {
        return NULL;
    }
    Py_INCREF(get_MemoryPoolType());
    if (PyModule_AddObject(m, "MemoryPool", (PyObject *)get_MemoryPoolType()) < 0) {
        Py_DECREF(get_MemoryPoolType());
        Py_DECREF(m);
        return NULL;
    }

    return m;
}

/* 批量分配函数 */
static PyObject* batch_alloc_func(PyObject *self, PyObject *args) {
    Py_ssize_t count, size;
    PyObject *result;

    if (!PyArg_ParseTuple(args, "nn", &count, &size)) {
        return NULL;
    }

    if (count <= 0 || size <= 0) {
        PyErr_SetString(PyExc_ValueError, "count and size must be positive");
        return NULL;
    }

    result = PyList_New(count);
    if (result == NULL) {
        return NULL;
    }

    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *obj = PyBytes_FromStringAndSize(NULL, size);
        if (obj == NULL) {
            Py_DECREF(result);
            return NULL;
        }
        PyList_SET_ITEM(result, i, obj);
    }

    return result;
}

/* 批量释放函数 */
static PyObject* batch_free_func(PyObject *self, PyObject *args) {
    PyObject *objects;

    if (!PyArg_ParseTuple(args, "O", &objects)) {
        return NULL;
    }

    if (!PyList_Check(objects)) {
        PyErr_SetString(PyExc_TypeError, "objects must be a list");
        return NULL;
    }

    Py_ssize_t count = PyList_Size(objects);
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *obj = PyList_GET_ITEM(objects, i);
        Py_XDECREF(obj);
    }

    Py_RETURN_NONE;
}

