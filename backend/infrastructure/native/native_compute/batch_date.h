/* -*- coding: utf-8 -*-
 * 批量日期处理头文件
 */

#ifndef BATCH_DATE_H
#define BATCH_DATE_H

#include <Python.h>

/* 批量验证ISO日期字符串格式 (YYYY-MM-DD)
 * 
 * Args:
 *     date_strings: 日期字符串列表
 * 
 * Returns:
 *     布尔值列表，True表示格式有效
 */
PyObject* batch_validate_iso_dates(PyObject* self, PyObject* args);

/* 批量比较日期（与给定日期比较）
 * 
 * Args:
 *     date_strings: 日期字符串列表 (YYYY-MM-DD格式)
 *     reference_date: 参考日期字符串 (YYYY-MM-DD格式)
 * 
 * Returns:
 *     整数列表：-1(早于), 0(等于), 1(晚于), -999(无效)
 */
PyObject* batch_compare_dates(PyObject* self, PyObject* args);

#endif /* BATCH_DATE_H */
