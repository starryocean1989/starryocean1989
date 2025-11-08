/* -*- coding: utf-8 -*-
 * 批量文件操作实现
 *
 * 使用Windows API实现批量文件操作，减少系统调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <stdio.h>
#include "batch_file.h"

/* 批量检查文件是否存在 */
PyObject* batch_file_exists(PyObject *self, PyObject *args) {
    PyObject *file_list;
    PyObject *result = NULL;
    Py_ssize_t count;

    if (!PyArg_ParseTuple(args, "O", &file_list)) {
        return NULL;
    }

    if (!PyList_Check(file_list)) {
        PyErr_SetString(PyExc_TypeError, "file_list must be a list");
        return NULL;
    }

    count = PyList_Size(file_list);
    if (count == 0) {
        return PyList_New(0);
    }

    result = PyList_New(count);
    if (result == NULL) {
        return NULL;
    }

    /* 批量检查文件是否存在 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *file_path_obj = PyList_GET_ITEM(file_list, i);
        const char *file_path;
        DWORD attributes;
        PyObject *exists = NULL;

        if (PyUnicode_Check(file_path_obj)) {
            file_path = PyUnicode_AsUTF8(file_path_obj);
            if (file_path == NULL) {
                Py_DECREF(result);
                return NULL;
            }
        } else {
            PyErr_SetString(PyExc_TypeError, "file paths must be strings");
            Py_DECREF(result);
            return NULL;
        }

        /* 使用Windows API检查文件是否存在 */
        attributes = GetFileAttributesA(file_path);
        exists = PyBool_FromLong(attributes != INVALID_FILE_ATTRIBUTES &&
                                !(attributes & FILE_ATTRIBUTE_DIRECTORY));

        PyList_SET_ITEM(result, i, exists);
    }

    return result;
}

/* 批量删除文件 */
PyObject* batch_file_delete(PyObject *self, PyObject *args) {
    PyObject *file_list;
    PyObject *result = NULL;
    Py_ssize_t count;
    Py_ssize_t success_count = 0;

    if (!PyArg_ParseTuple(args, "O", &file_list)) {
        return NULL;
    }

    if (!PyList_Check(file_list)) {
        PyErr_SetString(PyExc_TypeError, "file_list must be a list");
        return NULL;
    }

    count = PyList_Size(file_list);
    if (count == 0) {
        return PyLong_FromSsize_t(0);
    }

    /* 批量删除文件 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *file_path_obj = PyList_GET_ITEM(file_list, i);
        const char *file_path;
        BOOL success;

        if (PyUnicode_Check(file_path_obj)) {
            file_path = PyUnicode_AsUTF8(file_path_obj);
            if (file_path == NULL) {
                continue;
            }
        } else {
            continue;
        }

        /* 使用Windows API删除文件 */
        success = DeleteFileA(file_path);
        if (success) {
            success_count++;
        } else {
            char warning_message[256];
            snprintf(warning_message, sizeof(warning_message),
                     "Failed to delete file: %s, error code: %ld", file_path, GetLastError());
            PyErr_WarnEx(PyExc_RuntimeWarning, warning_message, 1);
        }
    }

    return PyLong_FromSsize_t(success_count);
}

/* 批量获取文件统计信息 */
PyObject* batch_file_stat(PyObject *self, PyObject *args) {
    PyObject *file_list;
    PyObject *result = NULL;
    Py_ssize_t count;

    if (!PyArg_ParseTuple(args, "O", &file_list)) {
        return NULL;
    }

    if (!PyList_Check(file_list)) {
        PyErr_SetString(PyExc_TypeError, "file_list must be a list");
        return NULL;
    }

    count = PyList_Size(file_list);
    if (count == 0) {
        return PyList_New(0);
    }

    result = PyList_New(count);
    if (result == NULL) {
        return NULL;
    }

    /* 批量获取文件统计信息 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *file_path_obj = PyList_GET_ITEM(file_list, i);
        const char *file_path;
        WIN32_FILE_ATTRIBUTE_DATA file_data;
        PyObject *stat_dict = NULL;

        if (PyUnicode_Check(file_path_obj)) {
            file_path = PyUnicode_AsUTF8(file_path_obj);
            if (file_path == NULL) {
                Py_INCREF(Py_None);
                PyList_SET_ITEM(result, i, Py_None);
                continue;
            }
        } else {
            Py_INCREF(Py_None);
            PyList_SET_ITEM(result, i, Py_None);
            continue;
        }

        /* 使用Windows API获取文件属性 */
        if (GetFileAttributesExA(file_path, GetFileExInfoStandard, &file_data)) {
            stat_dict = PyDict_New();
            if (stat_dict != NULL) {
                PyObject *size = PyLong_FromLongLong(
                    ((LONGLONG)file_data.nFileSizeHigh << 32) | file_data.nFileSizeLow
                );
                PyObject *mtime = PyLong_FromLongLong(
                    ((LONGLONG)file_data.ftLastWriteTime.dwHighDateTime << 32) |
                    file_data.ftLastWriteTime.dwLowDateTime
                );

                if (size != NULL) PyDict_SetItemString(stat_dict, "size", size);
                if (mtime != NULL) PyDict_SetItemString(stat_dict, "mtime", mtime);

                Py_XDECREF(size);
                Py_XDECREF(mtime);
            }
        } else {
            char warning_message[256];
            snprintf(warning_message, sizeof(warning_message),
                     "Failed to get stat for file: %s, error code: %ld", file_path, GetLastError());
            PyErr_WarnEx(PyExc_RuntimeWarning, warning_message, 1);
        }

        if (stat_dict == NULL) {
            Py_INCREF(Py_None);
            stat_dict = Py_None;
        }

        PyList_SET_ITEM(result, i, stat_dict);
    }

    return result;
}
