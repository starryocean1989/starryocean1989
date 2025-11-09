/* -*- coding: utf-8 -*-
 * 批量日期处理实现
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "batch_date.h"
#include <string.h>
#include <ctype.h>
/* 日志桥接宏 */
#include "../native_log_bridge.h"

/* 验证单个ISO日期字符串格式 (YYYY-MM-DD)
 * 返回: 1=有效, 0=无效
 */
static int validate_iso_date_format(const char* date_str) {
    if (!date_str || strlen(date_str) != 10) {
        return 0;
    }
    
    /* 检查格式: YYYY-MM-DD */
    if (date_str[4] != '-' || date_str[7] != '-') {
        return 0;
    }
    
    /* 检查数字部分 */
    for (int i = 0; i < 10; i++) {
        if (i == 4 || i == 7) continue;  /* 跳过连字符 */
        if (!isdigit((unsigned char)date_str[i])) {
            return 0;
        }
    }
    
    /* 简单的范围验证 */
    int year = (date_str[0] - '0') * 1000 + (date_str[1] - '0') * 100 +
               (date_str[2] - '0') * 10 + (date_str[3] - '0');
    int month = (date_str[5] - '0') * 10 + (date_str[6] - '0');
    int day = (date_str[8] - '0') * 10 + (date_str[9] - '0');
    
    if (year < 1900 || year > 2100) return 0;
    if (month < 1 || month > 12) return 0;
    if (day < 1 || day > 31) return 0;
    
    return 1;
}

/* 比较两个ISO日期字符串
 * 返回: -1(date1 < date2), 0(相等), 1(date1 > date2), -999(无效)
 */
static int compare_iso_dates(const char* date1, const char* date2) {
    /* 验证格式 */
    if (!validate_iso_date_format(date1) || !validate_iso_date_format(date2)) {
        return -999;
    }
    
    /* 直接字符串比较（YYYY-MM-DD格式可以直接字典序比较） */
    int cmp = strcmp(date1, date2);
    if (cmp < 0) return -1;
    if (cmp > 0) return 1;
    return 0;
}

/* 批量验证ISO日期字符串格式 */
PyObject* batch_validate_iso_dates(PyObject* self, PyObject* args) {
    PyObject* date_list;
    
    if (!PyArg_ParseTuple(args, "O", &date_list)) {
        NATIVE_LOG_ERROR("backend.native.compute.core", "batch_validate_iso_dates", __LINE__, "invalid arguments to batch_validate_iso_dates");
        return NULL;
    }
    
    if (!PyList_Check(date_list)) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.compute.core", "batch_validate_iso_dates", __LINE__, "参数必须是列表", NULL);
        PyErr_SetString(PyExc_TypeError, "参数必须是列表");
        return NULL;
    }
    
    Py_ssize_t size = PyList_Size(date_list);
    PyObject* result = PyList_New(size);
    if (!result) {
        NATIVE_LOG_CRITICAL("backend.native.compute.core", "batch_validate_iso_dates", __LINE__, "failed to allocate result list");
        return NULL;
    }
    
    for (Py_ssize_t i = 0; i < size; i++) {
        PyObject* item = PyList_GetItem(date_list, i);
        int is_valid = 0;
        
        if (item && item != Py_None) {
            if (PyUnicode_Check(item)) {
                const char* date_str = PyUnicode_AsUTF8(item);
                if (date_str) {
                    is_valid = validate_iso_date_format(date_str);
                }
            }
        }
        
        PyList_SET_ITEM(result, i, PyBool_FromLong(is_valid));
    }
    
    return result;
}

/* 批量比较日期 */
PyObject* batch_compare_dates(PyObject* self, PyObject* args) {
    PyObject* date_list;
    const char* reference_date;
    
    if (!PyArg_ParseTuple(args, "Os", &date_list, &reference_date)) {
        NATIVE_LOG_ERROR("backend.native.compute.core", "batch_compare_dates", __LINE__, "invalid arguments to batch_compare_dates");
        return NULL;
    }
    
    if (!PyList_Check(date_list)) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.compute.core", "batch_compare_dates", __LINE__, "第一个参数必须是列表", NULL);
        PyErr_SetString(PyExc_TypeError, "第一个参数必须是列表");
        return NULL;
    }
    
    /* 验证参考日期格式 */
    if (!validate_iso_date_format(reference_date)) {
        NATIVE_LOG_ERROR_DETAILS("backend.native.compute.core", "batch_compare_dates", __LINE__, "参考日期格式无效", reference_date);
        PyErr_SetString(PyExc_ValueError, "参考日期格式无效");
        return NULL;
    }
    
    Py_ssize_t size = PyList_Size(date_list);
    PyObject* result = PyList_New(size);
    if (!result) {
        NATIVE_LOG_CRITICAL("backend.native.compute.core", "batch_compare_dates", __LINE__, "failed to allocate result list");
        return NULL;
    }
    
    for (Py_ssize_t i = 0; i < size; i++) {
        PyObject* item = PyList_GetItem(date_list, i);
        int cmp_result = -999;  /* 默认无效 */
        
        if (item && item != Py_None) {
            if (PyUnicode_Check(item)) {
                const char* date_str = PyUnicode_AsUTF8(item);
                if (date_str) {
                    cmp_result = compare_iso_dates(date_str, reference_date);
                }
            }
        }
        
        PyList_SET_ITEM(result, i, PyLong_FromLong(cmp_result));
    }
    
    return result;
}
