/* -*- coding: utf-8 -*-
 * 批量数值运算实现
 *
 * 批量执行数值运算，减少Python调用开销
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>
#include <math.h>
#include "batch_compute.h"

/* 批量数值运算函数 */
PyObject* batch_compute_func(PyObject *self, PyObject *args) {
    PyObject *data, *operation = NULL, *operands = NULL;
    PyObject *result = NULL;
    Py_ssize_t count;
    const char *op = "add";

    if (!PyArg_ParseTuple(args, "O|sO", &data, &operation, &operands)) {
        return NULL;
    }

    if (!PyList_Check(data)) {
        PyErr_SetString(PyExc_TypeError, "data must be a list");
        return NULL;
    }

    if (operation != NULL && PyUnicode_Check(operation)) {
        op = PyUnicode_AsUTF8(operation);
        if (op == NULL) {
            return NULL;
        }
    }

    count = PyList_Size(data);
    if (count == 0) {
        return PyList_New(0);
    }

    /* 创建结果列表 */
    result = PyList_New(count);
    if (result == NULL) {
        return NULL;
    }

    /* 批量运算 */
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *item = PyList_GET_ITEM(data, i);
        PyObject *computed = NULL;

        if (strcmp(op, "add") == 0) {
            /* 加法运算 */
            PyObject *operand = NULL;
            if (operands != NULL && PyList_Check(operands) && i < PyList_Size(operands)) {
                operand = PyList_GET_ITEM(operands, i);
                Py_INCREF(operand);
            } else {
                operand = PyLong_FromLong(1);
            }
            computed = PyNumber_Add(item, operand);
            Py_DECREF(operand);
        } else if (strcmp(op, "multiply") == 0) {
            /* 乘法运算 */
            PyObject *operand = NULL;
            if (operands != NULL && PyList_Check(operands) && i < PyList_Size(operands)) {
                operand = PyList_GET_ITEM(operands, i);
                Py_INCREF(operand);
            } else {
                operand = PyFloat_FromDouble(2.0);
            }
            computed = PyNumber_Multiply(item, operand);
            Py_DECREF(operand);
        } else if (strcmp(op, "square") == 0) {
            /* 平方运算 */
            computed = PyNumber_Multiply(item, item);
        } else if (strcmp(op, "divide") == 0 || strcmp(op, "divide_by_100") == 0) {
            /* 除法运算：除以100.0 */
            if (PyLong_Check(item)) {
                computed = PyNumber_TrueDivide(item, PyFloat_FromDouble(100.0));
            } else if (PyFloat_Check(item)) {
                computed = PyNumber_TrueDivide(item, PyFloat_FromDouble(100.0));
            } else {
                computed = PyNumber_TrueDivide(item, PyFloat_FromDouble(100.0));
            }
        } else if (strcmp(op, "divide_by_1000") == 0) {
            /* 除法运算：除以1000.0（用于TDX价格转换） */
            if (PyLong_Check(item)) {
                computed = PyNumber_TrueDivide(item, PyFloat_FromDouble(1000.0));
            } else if (PyFloat_Check(item)) {
                computed = PyNumber_TrueDivide(item, PyFloat_FromDouble(1000.0));
            } else {
                computed = PyNumber_TrueDivide(item, PyFloat_FromDouble(1000.0));
            }
        } else if (strcmp(op, "get_volume") == 0) {
            /* 批量get_volume运算（用于TDX成交量转换） */
            unsigned long vol;
            double dbl_ret;

            if (PyLong_Check(item)) {
                vol = PyLong_AsUnsignedLong(item);
            } else if (PyFloat_Check(item)) {
                vol = (unsigned long)PyFloat_AsDouble(item);
            } else {
                PyObject *long_obj = PyNumber_Long(item);
                if (long_obj == NULL) {
                    Py_DECREF(result);
                    return NULL;
                }
                vol = PyLong_AsUnsignedLong(long_obj);
                Py_DECREF(long_obj);
            }

            /* 实现get_volume逻辑 */
            unsigned long logpoint = vol >> (8 * 3);
            unsigned long hleax = (vol >> (8 * 2)) & 0xFF;
            unsigned long lheax = (vol >> 8) & 0xFF;
            unsigned long lleax = vol & 0xFF;

            long dw_ecx = logpoint * 2 - 0x7F;
            long dw_edx = logpoint * 2 - 0x86;
            long dw_esi = logpoint * 2 - 0x8E;
            long dw_eax = logpoint * 2 - 0x96;

            double dbl_xmm6;
            if (dw_ecx < 0) {
                dbl_xmm6 = 1.0 / pow(2.0, -dw_ecx);
            } else {
                dbl_xmm6 = pow(2.0, dw_ecx);
            }

            double dbl_xmm4;
            if (hleax > 0x80) {
                long dwtmpeax = dw_edx + 1;
                double tmpdbl_xmm3 = pow(2.0, dwtmpeax);
                dbl_xmm4 = pow(2.0, dw_edx) * 128.0 + (hleax & 0x7F) * tmpdbl_xmm3;
            } else {
                if (dw_edx >= 0) {
                    dbl_xmm4 = pow(2.0, dw_edx) * hleax;
                } else {
                    dbl_xmm4 = (1.0 / pow(2.0, -dw_edx)) * hleax;
                }
            }

            double dbl_xmm3 = pow(2.0, dw_esi) * lheax;
            double dbl_xmm1 = pow(2.0, dw_eax) * lleax;

            if (hleax & 0x80) {
                dbl_xmm3 *= 2.0;
                dbl_xmm1 *= 2.0;
            }

            dbl_ret = dbl_xmm6 + dbl_xmm4 + dbl_xmm3 + dbl_xmm1;
            computed = PyFloat_FromDouble(dbl_ret);
        } else {
            PyErr_SetString(PyExc_ValueError, "Unsupported operation");
            Py_DECREF(result);
            return NULL;
        }

        if (computed == NULL) {
            Py_DECREF(result);
            return NULL;
        }

        PyList_SET_ITEM(result, i, computed);
    }

    return result;
}

/* 批量get_price解析函数（用于TDX价格解析） */
PyObject* batch_get_price_func(PyObject *self, PyObject *args) {
    PyObject *data_obj;
    Py_ssize_t start_pos;
    Py_ssize_t count;
    PyObject *result = NULL;
    PyObject *values_list = NULL;
    PyObject *positions_list = NULL;
    const unsigned char *data;
    Py_ssize_t data_len;
    Py_ssize_t pos;

    if (!PyArg_ParseTuple(args, "Onn", &data_obj, &start_pos, &count)) {
        return NULL;
    }

    if (!PyBytes_Check(data_obj)) {
        PyErr_SetString(PyExc_TypeError, "data must be bytes");
        return NULL;
    }

    if (count <= 0) {
        return Py_BuildValue("(OO)", PyList_New(0), PyLong_FromSsize_t(start_pos));
    }

    data = (const unsigned char *)PyBytes_AsString(data_obj);
    if (data == NULL) {
        return NULL;
    }

    data_len = PyBytes_Size(data_obj);
    if (start_pos < 0 || start_pos >= data_len) {
        PyErr_SetString(PyExc_ValueError, "start_pos out of range");
        return NULL;
    }

    /* 创建结果列表 */
    values_list = PyList_New(count);
    positions_list = PyList_New(count);
    if (values_list == NULL || positions_list == NULL) {
        Py_XDECREF(values_list);
        Py_XDECREF(positions_list);
        return NULL;
    }

    pos = start_pos;

    /* 批量解析get_price */
    for (Py_ssize_t i = 0; i < count; i++) {
        Py_ssize_t pos_byte = 6;
        long int_data = 0;
        int sign = 0;

        if (pos >= data_len) {
            PyErr_SetString(PyExc_ValueError, "data buffer too short");
            Py_DECREF(values_list);
            Py_DECREF(positions_list);
            return NULL;
        }

        unsigned char bdata = data[pos];
        int_data = bdata & 0x3F;

        if (bdata & 0x40) {
            sign = 1;
        }

        if (bdata & 0x80) {
            while (1) {
                pos++;
                if (pos >= data_len) {
                    PyErr_SetString(PyExc_ValueError, "data buffer too short");
                    Py_DECREF(values_list);
                    Py_DECREF(positions_list);
                    return NULL;
                }

                bdata = data[pos];
                int_data += (bdata & 0x7F) << pos_byte;
                pos_byte += 7;

                if (!(bdata & 0x80)) {
                    break;
                }
            }
        }

        pos++;

        if (sign) {
            int_data = -int_data;
        }

        PyObject *value_obj = PyLong_FromLong(int_data);
        PyObject *pos_obj = PyLong_FromSsize_t(pos);
        if (value_obj == NULL || pos_obj == NULL) {
            Py_XDECREF(value_obj);
            Py_XDECREF(pos_obj);
            Py_DECREF(values_list);
            Py_DECREF(positions_list);
            return NULL;
        }

        PyList_SET_ITEM(values_list, i, value_obj);
        PyList_SET_ITEM(positions_list, i, pos_obj);
    }

    result = Py_BuildValue("(OO)", values_list, positions_list);
    Py_DECREF(values_list);
    Py_DECREF(positions_list);
    return result;
}

