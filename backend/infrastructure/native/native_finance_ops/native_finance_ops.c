// -*- coding: utf-8 -*-
/*
 * native_finance_ops.c - Python绑定层
 * 
 * 提供Python可调用的接口
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "finance_metrics.h"

// Python函数：aggregate_daily_pnl
static PyObject* py_aggregate_daily_pnl(PyObject* self, PyObject* args) {
    PyObject *dates_obj, *pnl_obj;
    
    if (!PyArg_ParseTuple(args, "OO", &dates_obj, &pnl_obj)) {
        return NULL;
    }

    // 转换为C数组
    Py_ssize_t count = PySequence_Length(dates_obj);
    if (count < 0) {
        PyErr_SetString(PyExc_ValueError, "Invalid dates sequence");
        return NULL;
    }

    int* dates = (int*)malloc(sizeof(int) * count);
    double* pnl = (double*)malloc(sizeof(double) * count);
    
    if (!dates || !pnl) {
        free(dates);
        free(pnl);
        return PyErr_NoMemory();
    }

    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *date_item = PySequence_GetItem(dates_obj, i);
        PyObject *pnl_item = PySequence_GetItem(pnl_obj, i);
        
        dates[i] = (int)PyLong_AsLong(date_item);
        pnl[i] = PyFloat_AsDouble(pnl_item);
        
        Py_DECREF(date_item);
        Py_DECREF(pnl_item);
    }

    // 调用C函数
    DailyAggregation* result = aggregate_daily_pnl(dates, pnl, (size_t)count);
    
    free(dates);
    free(pnl);

    if (!result) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to aggregate daily PnL");
        return NULL;
    }

    // 转换为Python dict
    PyObject* result_dict = PyDict_New();
    
    PyObject* dates_list = PyList_New(result->count);
    PyObject* returns_list = PyList_New(result->count);
    PyObject* equity_list = PyList_New(result->count);
    
    for (size_t i = 0; i < result->count; i++) {
        PyList_SetItem(dates_list, i, PyLong_FromLong((long)result->dates[i]));
        PyList_SetItem(returns_list, i, PyFloat_FromDouble(result->daily_returns[i]));
        PyList_SetItem(equity_list, i, PyFloat_FromDouble(result->cumulative_equity[i]));
    }
    
    PyDict_SetItemString(result_dict, "dates", dates_list);
    PyDict_SetItemString(result_dict, "daily_returns", returns_list);
    PyDict_SetItemString(result_dict, "cumulative_equity", equity_list);
    
    Py_DECREF(dates_list);
    Py_DECREF(returns_list);
    Py_DECREF(equity_list);

    free_daily_aggregation(result);

    return result_dict;
}

// Python函数：compute_return_metrics
static PyObject* py_compute_return_metrics(PyObject* self, PyObject* args, PyObject* kwargs) {
    PyObject *pnl_obj, *equity_obj;
    int trading_days = 252; // 默认值
    
    static char* kwlist[] = {"pnl_series", "equity_series", "trading_days_per_year", NULL};
    
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|i", kwlist, 
                                     &pnl_obj, &equity_obj, &trading_days)) {
        return NULL;
    }

    Py_ssize_t count = PySequence_Length(pnl_obj);
    if (count < 2) {
        PyErr_SetString(PyExc_ValueError, "Need at least 2 data points");
        return NULL;
    }

    double* pnl = (double*)malloc(sizeof(double) * count);
    double* equity = (double*)malloc(sizeof(double) * count);
    
    if (!pnl || !equity) {
        free(pnl);
        free(equity);
        return PyErr_NoMemory();
    }

    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *pnl_item = PySequence_GetItem(pnl_obj, i);
        PyObject *equity_item = PySequence_GetItem(equity_obj, i);
        
        pnl[i] = PyFloat_AsDouble(pnl_item);
        equity[i] = PyFloat_AsDouble(equity_item);
        
        Py_DECREF(pnl_item);
        Py_DECREF(equity_item);
    }

    PerformanceMetrics* metrics = compute_return_metrics(pnl, equity, (size_t)count, trading_days);
    
    free(pnl);
    free(equity);

    if (!metrics) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to compute metrics");
        return NULL;
    }

    PyObject* result_dict = PyDict_New();
    PyDict_SetItemString(result_dict, "total_return", PyFloat_FromDouble(metrics->total_return));
    PyDict_SetItemString(result_dict, "annualized_return", PyFloat_FromDouble(metrics->annualized_return));
    PyDict_SetItemString(result_dict, "volatility", PyFloat_FromDouble(metrics->volatility));
    PyDict_SetItemString(result_dict, "sharpe_ratio", PyFloat_FromDouble(metrics->sharpe_ratio));
    PyDict_SetItemString(result_dict, "max_drawdown", PyFloat_FromDouble(metrics->max_drawdown));
    PyDict_SetItemString(result_dict, "drawdown_days", PyLong_FromLong(metrics->drawdown_days));
    PyDict_SetItemString(result_dict, "calmar_ratio", PyFloat_FromDouble(metrics->calmar_ratio));

    free_performance_metrics(metrics);

    return result_dict;
}

// Python函数：bucketize_period
static PyObject* py_bucketize_period(PyObject* self, PyObject* args) {
    PyObject *equity_obj, *dates_obj;
    const char* period_mode = "monthly";
    
    if (!PyArg_ParseTuple(args, "OO|s", &equity_obj, &dates_obj, &period_mode)) {
        return NULL;
    }

    Py_ssize_t count = PySequence_Length(equity_obj);
    if (count < 1) {
        PyErr_SetString(PyExc_ValueError, "Empty sequence");
        return NULL;
    }

    double* equity = (double*)malloc(sizeof(double) * count);
    int* dates = (int*)malloc(sizeof(int) * count);
    
    if (!equity || !dates) {
        free(equity);
        free(dates);
        return PyErr_NoMemory();
    }

    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *equity_item = PySequence_GetItem(equity_obj, i);
        PyObject *date_item = PySequence_GetItem(dates_obj, i);
        
        equity[i] = PyFloat_AsDouble(equity_item);
        dates[i] = (int)PyLong_AsLong(date_item);
        
        Py_DECREF(equity_item);
        Py_DECREF(date_item);
    }

    PeriodBuckets* buckets = bucketize_period(equity, dates, (size_t)count, period_mode);
    
    free(equity);
    free(dates);

    if (!buckets) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to bucketize periods");
        return NULL;
    }

    PyObject* labels_list = PyList_New(buckets->count);
    PyObject* returns_list = PyList_New(buckets->count);
    
    for (size_t i = 0; i < buckets->count; i++) {
        PyList_SetItem(labels_list, i, PyUnicode_FromString(buckets->period_labels[i]));
        PyList_SetItem(returns_list, i, PyFloat_FromDouble(buckets->period_returns[i]));
    }

    PyObject* result_dict = PyDict_New();
    PyDict_SetItemString(result_dict, "period_labels", labels_list);
    PyDict_SetItemString(result_dict, "period_returns", returns_list);
    
    Py_DECREF(labels_list);
    Py_DECREF(returns_list);

    free_period_buckets(buckets);

    return result_dict;
}

// 方法定义表
static PyMethodDef FinanceOpsMethods[] = {
    {"aggregate_daily_pnl", py_aggregate_daily_pnl, METH_VARARGS,
     "Aggregate daily PnL and generate cumulative equity curve"},
    {"compute_return_metrics", (PyCFunction)py_compute_return_metrics, METH_VARARGS | METH_KEYWORDS,
     "Compute performance metrics (return, volatility, sharpe, drawdown, etc.)"},
    {"bucketize_period", py_bucketize_period, METH_VARARGS,
     "Bucketize equity series by period (weekly, monthly, yearly)"},
    {NULL, NULL, 0, NULL}
};

// 模块定义
static struct PyModuleDef finance_ops_module = {
    PyModuleDef_HEAD_INIT,
    "native_finance_ops",
    "Native C implementation of financial operations for portfolio analysis",
    -1,
    FinanceOpsMethods
};

// 模块初始化
PyMODINIT_FUNC PyInit_native_finance_ops(void) {
    PyObject* module = PyModule_Create(&finance_ops_module);
    if (module == NULL) {
        return NULL;
    }

    // 添加常量
    PyModule_AddIntConstant(module, "FINANCE_OPS_AVAILABLE", 1);
    PyModule_AddStringConstant(module, "VERSION", "1.0.0");

    return module;
}
