/* -*- coding: utf-8 -*-
 * IOCP批量文件操作模块
 *
 * 提供批量文件操作和目录遍历功能
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>

/* Native Log Bridge */
#include "../native_log_bridge.h"
#include "batch_file.h"
#include "dir_traversal.h"

/* 方法定义 */
static PyMethodDef BatchFileMethods[] = {
    {"batch_file_exists", batch_file_exists, METH_VARARGS, "Batch check if files exist"},
    {"batch_file_delete", batch_file_delete, METH_VARARGS, "Batch delete files"},
    {"batch_file_stat", batch_file_stat, METH_VARARGS, "Batch get file statistics"},
    {"fast_dir_walk", fast_dir_walk, METH_VARARGS, "Fast directory traversal"},
    {"fast_dir_list", fast_dir_list, METH_VARARGS, "Fast directory listing"},
    {NULL, NULL, 0, NULL}
};

/* 模块初始化 */
static struct PyModuleDef iocp_batchmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "iocp_batch",
    .m_doc = "IOCP batch file operations and directory traversal for Windows",
    .m_size = -1,
    .m_methods = BatchFileMethods,
};

PyMODINIT_FUNC PyInit_iocp_batch(void) {
    return PyModule_Create(&iocp_batchmodule);
}

