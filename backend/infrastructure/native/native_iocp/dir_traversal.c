/* -*- coding: utf-8 -*-
 * 高性能目录遍历实现
 *
 * 使用Windows FindFirstFile/FindNextFile API实现高性能目录遍历
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <string.h>
#include "dir_traversal.h"

/* Native Log Bridge */
#include "../native_log_bridge.h"

/* 快速目录遍历 */
PyObject* fast_dir_walk(PyObject *self, PyObject *args) {
    const char *root_path;
    PyObject *result = NULL;
    PyObject *dirs_list = NULL;
    PyObject *files_list = NULL;

    if (!PyArg_ParseTuple(args, "s", &root_path)) {
        return NULL;
    }

    result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }

    dirs_list = PyList_New(0);
    files_list = PyList_New(0);
    if (dirs_list == NULL || files_list == NULL) {
        Py_DECREF(result);
        Py_XDECREF(dirs_list);
        Py_XDECREF(files_list);
        return NULL;
    }

    /* 构建搜索路径 */
    char search_path[MAX_PATH];
    size_t root_len = strlen(root_path);

    if (root_len >= MAX_PATH - 3) {
        PyErr_SetString(PyExc_ValueError, "Path too long");
        Py_DECREF(result);
        Py_DECREF(dirs_list);
        Py_DECREF(files_list);
        return NULL;
    }

    strncpy_s(search_path, MAX_PATH, root_path, _TRUNCATE);
    if (search_path[root_len - 1] != '\\' && search_path[root_len - 1] != '/') {
        strcat_s(search_path, MAX_PATH, "\\");
        root_len++;
    }
    strcat_s(search_path, MAX_PATH, "*");

    /* 使用FindFirstFile遍历目录 */
    WIN32_FIND_DATAA find_data;
    HANDLE find_handle = FindFirstFileA(search_path, &find_data);

    if (find_handle != INVALID_HANDLE_VALUE) {
        do {
            /* 跳过.和.. */
            if (strcmp(find_data.cFileName, ".") == 0 ||
                strcmp(find_data.cFileName, "..") == 0) {
                continue;
            }

            /* 构建完整路径 */
            char full_path[MAX_PATH];
            strncpy_s(full_path, MAX_PATH, root_path, _TRUNCATE);
            if (full_path[strlen(full_path) - 1] != '\\' &&
                full_path[strlen(full_path) - 1] != '/') {
                strcat_s(full_path, MAX_PATH, "\\");
            }
            strcat_s(full_path, MAX_PATH, find_data.cFileName);

            PyObject *path_obj = PyUnicode_FromString(full_path);

            if (find_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                /* 目录 */
                PyList_Append(dirs_list, path_obj);
            } else {
                /* 文件 */
                PyList_Append(files_list, path_obj);
            }

            Py_XDECREF(path_obj);
        } while (FindNextFileA(find_handle, &find_data));

        FindClose(find_handle);
    } else {
        char warning_message[256];
        snprintf(warning_message, sizeof(warning_message),
                 "Failed to find first file in: %s, error code: %ld", root_path, GetLastError());
        PyErr_WarnEx(PyExc_RuntimeWarning, warning_message, 1);
    }

    /* 构建结果元组 */
    PyObject *tuple = PyTuple_New(3);
    if (tuple != NULL) {
        PyObject *root_obj = PyUnicode_FromString(root_path);
        PyTuple_SET_ITEM(tuple, 0, root_obj);
        PyTuple_SET_ITEM(tuple, 1, dirs_list);
        PyTuple_SET_ITEM(tuple, 2, files_list);
        PyList_Append(result, tuple);
        Py_DECREF(tuple);
    } else {
        Py_DECREF(dirs_list);
        Py_DECREF(files_list);
    }

    return result;
}

/* 快速目录列表 */
PyObject* fast_dir_list(PyObject *self, PyObject *args) {
    const char *dir_path;
    PyObject *result = NULL;

    if (!PyArg_ParseTuple(args, "s", &dir_path)) {
        return NULL;
    }

    result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }

    /* 构建搜索路径 */
    char search_path[MAX_PATH];
    size_t dir_len = strlen(dir_path);

    if (dir_len >= MAX_PATH - 3) {
        PyErr_SetString(PyExc_ValueError, "Path too long");
        Py_DECREF(result);
        return NULL;
    }

    strncpy_s(search_path, MAX_PATH, dir_path, _TRUNCATE);
    if (search_path[dir_len - 1] != '\\' && search_path[dir_len - 1] != '/') {
        strcat_s(search_path, MAX_PATH, "\\");
    }
    strcat_s(search_path, MAX_PATH, "*");

    /* 使用FindFirstFile遍历目录 */
    WIN32_FIND_DATAA find_data;
    HANDLE find_handle = FindFirstFileA(search_path, &find_data);

    if (find_handle != INVALID_HANDLE_VALUE) {
        do {
            /* 跳过.和.. */
            if (strcmp(find_data.cFileName, ".") == 0 ||
                strcmp(find_data.cFileName, "..") == 0) {
                continue;
            }

            /* 构建完整路径 */
            char full_path[MAX_PATH];
            strncpy_s(full_path, MAX_PATH, dir_path, _TRUNCATE);
            if (full_path[strlen(full_path) - 1] != '\\' &&
                full_path[strlen(full_path) - 1] != '/') {
                strcat_s(full_path, MAX_PATH, "\\");
            }
            strcat_s(full_path, MAX_PATH, find_data.cFileName);

            PyObject *path_obj = PyUnicode_FromString(full_path);
            PyList_Append(result, path_obj);
            Py_XDECREF(path_obj);
        } while (FindNextFileA(find_handle, &find_data));

        FindClose(find_handle);
    } else {
        char warning_message[256];
        snprintf(warning_message, sizeof(warning_message),
                 "Failed to find first file in: %s, error code: %ld", dir_path, GetLastError());
        PyErr_WarnEx(PyExc_RuntimeWarning, warning_message, 1);
    }

    return result;
}

