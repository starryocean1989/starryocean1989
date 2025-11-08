// -*- coding: utf-8 -*-
/*
 * native_finance_ops.c - Python绑定层
 *
 * 提供Python可调用的接口
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "finance_metrics.h"

typedef struct {
    int date;
    double pnl;
} DatePnlItem;

typedef struct {
    int yyyymmdd;
    struct tm tm_date;
    double pnl;
    double start_equity;
    double end_equity;
    double daily_return;
    double cumulative_return;
    char label[32];
} DailyEntry;

typedef struct {
    char label[32];
    double pnl;
    double return_ratio;
    double start_equity;
    double end_equity;
    double cumulative_return;
} PeriodEntry;

#define ADJUST_MODE_QFQ 0
#define ADJUST_MODE_HFQ 1

typedef struct {
    int present;
    Py_buffer view;
    double* data;
    Py_ssize_t length;
} DoubleBuffer;

static void release_double_buffer(DoubleBuffer* buf) {
    if (!buf) {
        return;
    }
    if (buf->view.buf) {
        PyBuffer_Release(&buf->view);
        buf->view.buf = NULL;
    }
    buf->data = NULL;
    buf->length = 0;
    buf->present = 0;
}

static int acquire_double_buffer(PyObject* dict, const char* key, int required, Py_ssize_t expected_length, DoubleBuffer* out) {
    if (!out) {
        return 0;
    }

    out->present = 0;
    out->data = NULL;
    out->length = 0;
    memset(&out->view, 0, sizeof(Py_buffer));

    PyObject* obj = PyDict_GetItemString(dict, key);
    if (!obj) {
        if (required) {
            PyErr_Format(PyExc_KeyError, "缺少必要列: %s", key);
            return 0;
        }
        out->length = (expected_length >= 0) ? expected_length : 0;
        return 1;
    }

    if (PyObject_GetBuffer(obj, &out->view, PyBUF_WRITABLE | PyBUF_CONTIG | PyBUF_FORMAT) != 0) {
        return 0;
    }

    if (out->view.ndim > 1) {
        PyErr_Format(PyExc_TypeError, "%s必须是一维数组", key);
        release_double_buffer(out);
        return 0;
    }

    if (out->view.itemsize != (Py_ssize_t)sizeof(double)) {
        PyErr_Format(PyExc_TypeError, "%s的数据类型必须为float64", key);
        release_double_buffer(out);
        return 0;
    }

    Py_ssize_t length = out->view.len / out->view.itemsize;
    if (expected_length >= 0 && length != expected_length) {
        PyErr_Format(PyExc_ValueError, "%s长度不匹配，期望%zd，实际%zd", key, expected_length, length);
        release_double_buffer(out);
        return 0;
    }

    out->present = 1;
    out->data = (double*)out->view.buf;
    out->length = length;
    return 1;
}

static int parse_adjust_mode(const char* adjust_type) {
    if (!adjust_type) {
        return ADJUST_MODE_QFQ;
    }

    char buffer[16];
    size_t len = strlen(adjust_type);
    if (len >= sizeof(buffer)) {
        len = sizeof(buffer) - 1;
    }
    for (size_t i = 0; i < len; i++) {
        buffer[i] = (char)tolower((unsigned char)adjust_type[i]);
    }
    buffer[len] = '\0';

    if (strcmp(buffer, "qfq") == 0 || strcmp(buffer, "before") == 0 || strcmp(buffer, "01") == 0) {
        return ADJUST_MODE_QFQ;
    }
    if (strcmp(buffer, "hfq") == 0 || strcmp(buffer, "after") == 0 || strcmp(buffer, "02") == 0) {
        return ADJUST_MODE_HFQ;
    }

    PyErr_SetString(PyExc_ValueError, "不支持的复权类型");
    return -1;
}

static void multiply_series(double* values, const double* adj, Py_ssize_t length) {
    if (!values || !adj) {
        return;
    }
    for (Py_ssize_t i = 0; i < length; i++) {
        double scale = adj[i];
        if (!isfinite(scale)) {
            scale = 1.0;
        }
        values[i] *= scale;
    }
}

static void divide_series(double* values, const double* adj, Py_ssize_t length) {
    if (!values || !adj) {
        return;
    }
    for (Py_ssize_t i = 0; i < length; i++) {
        double scale = adj[i];
        if (!isfinite(scale) || fabs(scale) < 1e-15) {
            scale = 1.0;
        }
        values[i] /= scale;
    }
}

static int compare_date_pnl_item(const void* a, const void* b) {
    const DatePnlItem* pa = (const DatePnlItem*)a;
    const DatePnlItem* pb = (const DatePnlItem*)b;
    if (pa->date == pb->date) {
        return 0;
    }
    return (pa->date < pb->date) ? -1 : 1;
}

static int compare_double_asc(const void* a, const void* b) {
    double da = *(const double*)a;
    double db = *(const double*)b;
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
}

static int dict_set_double(PyObject* dict, const char* key, double value) {
    PyObject* obj = PyFloat_FromDouble(value);
    if (!obj) {
        return 0;
    }
    int rc = PyDict_SetItemString(dict, key, obj);
    Py_DECREF(obj);
    return rc == 0;
}

static int dict_set_long(PyObject* dict, const char* key, Py_ssize_t value) {
    PyObject* obj = PyLong_FromSsize_t(value);
    if (!obj) {
        return 0;
    }
    int rc = PyDict_SetItemString(dict, key, obj);
    Py_DECREF(obj);
    return rc == 0;
}

static int convert_date_pyobject(PyObject* obj, int* out_date) {
    if (PyLong_Check(obj)) {
        long value = PyLong_AsLong(obj);
        if (PyErr_Occurred()) {
            return 0;
        }
        *out_date = (int)value;
        return 1;
    }

    if (PyUnicode_Check(obj)) {
        const char* text = PyUnicode_AsUTF8(obj);
        if (!text) {
            return 0;
        }

        char buffer[16];
        size_t idx = 0;
        for (size_t i = 0; text[i] != '\0' && idx < sizeof(buffer) - 1; i++) {
            if (text[i] >= '0' && text[i] <= '9') {
                buffer[idx++] = text[i];
            }
        }
        buffer[idx] = '\0';

        if (idx != 8) {
            PyErr_SetString(PyExc_ValueError, "日期格式必须为YYYYMMDD或YYYY-MM-DD");
            return 0;
        }

        *out_date = (int)strtol(buffer, NULL, 10);
        return 1;
    }

    PyErr_SetString(PyExc_TypeError, "日期必须为整数或字符串");
    return 0;
}

static int parse_date_to_tm(int yyyymmdd, struct tm* out_tm) {
    int year = yyyymmdd / 10000;
    int month = (yyyymmdd / 100) % 100;
    int day = yyyymmdd % 100;

    if (year < 1900 || month < 1 || month > 12 || day < 1 || day > 31) {
        return 0;
    }

    memset(out_tm, 0, sizeof(struct tm));
    out_tm->tm_year = year - 1900;
    out_tm->tm_mon = month - 1;
    out_tm->tm_mday = day;
    out_tm->tm_isdst = -1;

    if (mktime(out_tm) == (time_t)-1) {
        return 0;
    }

    return 1;
}

static void format_period_label(const struct tm* tm_date, const char* mode, char* buffer, size_t buffer_size) {
    if (strcmp(mode, "weekly") == 0) {
        strftime(buffer, buffer_size, "%G-W%V", tm_date);
        return;
    }

    if (strcmp(mode, "monthly") == 0) {
        strftime(buffer, buffer_size, "%Y-%m", tm_date);
        return;
    }

    if (strcmp(mode, "yearly") == 0) {
        strftime(buffer, buffer_size, "%Y", tm_date);
        return;
    }

    strftime(buffer, buffer_size, "%Y-%m-%d", tm_date);
}

static int build_daily_entries(const int* dates, const double* pnl, size_t count, double initial_equity, DailyEntry** out_entries, size_t* out_count) {
    if (count == 0) {
        *out_entries = NULL;
        *out_count = 0;
        return 1;
    }

    DatePnlItem* pairs = (DatePnlItem*)malloc(sizeof(DatePnlItem) * count);
    if (!pairs) {
        PyErr_NoMemory();
        return 0;
    }

    for (size_t i = 0; i < count; i++) {
        pairs[i].date = dates[i];
        pairs[i].pnl = pnl[i];
    }

    qsort(pairs, count, sizeof(DatePnlItem), compare_date_pnl_item);

    DailyEntry* entries = (DailyEntry*)malloc(sizeof(DailyEntry) * count);
    if (!entries) {
        free(pairs);
        PyErr_NoMemory();
        return 0;
    }

    size_t entry_count = 0;
    int current_date = pairs[0].date;
    double current_pnl = pairs[0].pnl;

    for (size_t i = 1; i < count; i++) {
        if (pairs[i].date == current_date) {
            current_pnl += pairs[i].pnl;
        } else {
            DailyEntry* entry = &entries[entry_count];
            if (!parse_date_to_tm(current_date, &entry->tm_date)) {
                free(entries);
                free(pairs);
                PyErr_SetString(PyExc_ValueError, "无效的日期数据");
                return 0;
            }
            format_period_label(&entry->tm_date, "daily", entry->label, sizeof(entry->label));

            entry->yyyymmdd = current_date;
            entry->start_equity = initial_equity;
            if (entry_count > 0) {
                entry->start_equity = entries[entry_count - 1].end_equity;
            }
            entry->pnl = current_pnl;
            entry->end_equity = entry->start_equity + current_pnl;
            entry->daily_return = (entry->start_equity > 0.0) ? (current_pnl / entry->start_equity) : 0.0;
            entry->cumulative_return = (entry->end_equity - initial_equity) / (initial_equity > 0.0 ? initial_equity : 1.0);
            entry_count++;

            current_date = pairs[i].date;
            current_pnl = pairs[i].pnl;
        }
    }

    DailyEntry* entry = &entries[entry_count];
    if (!parse_date_to_tm(current_date, &entry->tm_date)) {
        free(entries);
        free(pairs);
        PyErr_SetString(PyExc_ValueError, "无效的日期数据");
        return 0;
    }
    format_period_label(&entry->tm_date, "daily", entry->label, sizeof(entry->label));

    entry->yyyymmdd = current_date;
    entry->start_equity = initial_equity;
    if (entry_count > 0) {
        entry->start_equity = entries[entry_count - 1].end_equity;
    }
    entry->pnl = current_pnl;
    entry->end_equity = entry->start_equity + current_pnl;
    entry->daily_return = (entry->start_equity > 0.0) ? (current_pnl / entry->start_equity) : 0.0;
    entry->cumulative_return = (entry->end_equity - initial_equity) / (initial_equity > 0.0 ? initial_equity : 1.0);
    entry_count++;

    free(pairs);

    *out_entries = entries;
    *out_count = entry_count;
    return 1;
}

static void finalize_period_entry(PeriodEntry* entry) {
    if (!entry) {
        return;
    }
    if (entry->start_equity > 0.0) {
        entry->return_ratio = (entry->end_equity - entry->start_equity) / entry->start_equity;
    } else {
        entry->return_ratio = 0.0;
    }
}

static int build_period_entries(const DailyEntry* daily_entries, size_t daily_count, const char* mode, double initial_equity, PeriodEntry** out_entries, size_t* out_count) {
    if (daily_count == 0) {
        *out_entries = NULL;
        *out_count = 0;
        return 1;
    }

    PeriodEntry* entries = (PeriodEntry*)malloc(sizeof(PeriodEntry) * daily_count);
    if (!entries) {
        PyErr_NoMemory();
        return 0;
    }

    size_t count = 0;
    PeriodEntry current;
    int has_current = 0;

    for (size_t i = 0; i < daily_count; i++) {
        char label[32];
        format_period_label(&daily_entries[i].tm_date, mode, label, sizeof(label));

        if (!has_current || strcmp(label, current.label) != 0) {
            if (has_current) {
                finalize_period_entry(&current);
                entries[count++] = current;
            }
            memset(&current, 0, sizeof(PeriodEntry));
            strncpy(current.label, label, sizeof(current.label) - 1);
            current.label[sizeof(current.label) - 1] = '\0';
            current.start_equity = daily_entries[i].start_equity;
            current.end_equity = daily_entries[i].end_equity;
            current.pnl = daily_entries[i].pnl;
            current.cumulative_return = (daily_entries[i].end_equity - initial_equity) / (initial_equity > 0.0 ? initial_equity : 1.0);
            has_current = 1;
        } else {
            current.pnl += daily_entries[i].pnl;
            current.end_equity = daily_entries[i].end_equity;
            current.cumulative_return = (daily_entries[i].end_equity - initial_equity) / (initial_equity > 0.0 ? initial_equity : 1.0);
        }
    }

    if (has_current) {
        finalize_period_entry(&current);
        entries[count++] = current;
    }

    *out_entries = entries;
    *out_count = count;
    return 1;
}

static double compute_max_drawdown(const DailyEntry* entries, size_t count, double* out_duration_days) {
    if (count == 0) {
        if (out_duration_days) {
            *out_duration_days = 0.0;
        }
        return 0.0;
    }

    double peak = entries[0].end_equity;
    double max_dd = 0.0;
    size_t peak_index = 0;
    size_t trough_index = 0;
    size_t current_peak_index = 0;

    for (size_t i = 0; i < count; i++) {
        double equity = entries[i].end_equity;
        if (equity > peak) {
            peak = equity;
            current_peak_index = i;
        }
        double drawdown = (equity - peak) / (peak > 0.0 ? peak : 1.0);
        if (drawdown < max_dd) {
            max_dd = drawdown;
            peak_index = current_peak_index;
            trough_index = i;
        }
    }

    if (out_duration_days) {
        if (trough_index > peak_index) {
            *out_duration_days = (double)(trough_index - peak_index);
        } else {
            *out_duration_days = 0.0;
        }
    }

    return max_dd;
}

static double compute_quantile(const double* sorted_values, size_t count, double q) {
    if (count == 0) {
        return 0.0;
    }

    if (q <= 0.0) {
        return sorted_values[0];
    }

    if (q >= 1.0) {
        return sorted_values[count - 1];
    }

    double position = q * (double)(count - 1);
    size_t lower = (size_t)floor(position);
    size_t upper = (size_t)ceil(position);
    double weight = position - (double)lower;

    if (upper >= count) {
        upper = count - 1;
    }

    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight;
}

static int extract_confidence_levels(PyObject* obj, double** out_levels, size_t* out_count) {
    if (obj == Py_None || obj == NULL) {
        *out_levels = NULL;
        *out_count = 0;
        return 1;
    }

    PyObject* seq = PySequence_Fast(obj, "confidence_levels必须是可迭代对象");
    if (!seq) {
        return 0;
    }

    Py_ssize_t len = PySequence_Fast_GET_SIZE(seq);
    if (len <= 0) {
        Py_DECREF(seq);
        *out_levels = NULL;
        *out_count = 0;
        return 1;
    }

    double* levels = (double*)malloc(sizeof(double) * (size_t)len);
    if (!levels) {
        Py_DECREF(seq);
        PyErr_NoMemory();
        return 0;
    }

    int success = 1;
    for (Py_ssize_t i = 0; i < len; i++) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        double value = PyFloat_AsDouble(item);
        if (PyErr_Occurred()) {
            success = 0;
            break;
        }
        if (value <= 0.0 || value >= 1.0) {
            PyErr_SetString(PyExc_ValueError, "置信水平必须在(0,1)之间");
            success = 0;
            break;
        }
        levels[i] = value;
    }

    Py_DECREF(seq);

    if (!success) {
        free(levels);
        return 0;
    }

    *out_levels = levels;
    *out_count = (size_t)len;
    return 1;
}


static PyObject* py_apply_price_adjustments(PyObject* self, PyObject* args, PyObject* kwargs) {
    PyObject* prices_dict = NULL;
    PyObject* adjustments_dict = NULL;
    const char* adjust_type = "qfq";
    int success = 0;

    static char* kwlist[] = {"prices", "adjustments", "adjust_type", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|s", kwlist, &prices_dict, &adjustments_dict, &adjust_type)) {
        return NULL;
    }

    if (!PyDict_Check(prices_dict) || !PyDict_Check(adjustments_dict)) {
        PyErr_SetString(PyExc_TypeError, "prices和adjustments必须为dict");
        return NULL;
    }

    DoubleBuffer close_buf = {0};
    DoubleBuffer adj_buf = {0};
    DoubleBuffer preclose_buf = {0};
    DoubleBuffer open_buf = {0};
    DoubleBuffer high_buf = {0};
    DoubleBuffer low_buf = {0};
    DoubleBuffer volume_buf = {0};
    DoubleBuffer vol_buf = {0};
    DoubleBuffer fenhong_buf = {0};
    DoubleBuffer peigu_buf = {0};
    DoubleBuffer peigujia_buf = {0};
    DoubleBuffer songzhuangu_buf = {0};

    if (!acquire_double_buffer(prices_dict, "close", 1, -1, &close_buf)) {
        goto cleanup;
    }

    Py_ssize_t length = close_buf.length;
    if (!acquire_double_buffer(prices_dict, "adj", 1, length, &adj_buf) ||
        !acquire_double_buffer(prices_dict, "preclose", 1, length, &preclose_buf) ||
        !acquire_double_buffer(prices_dict, "open", 0, length, &open_buf) ||
        !acquire_double_buffer(prices_dict, "high", 0, length, &high_buf) ||
        !acquire_double_buffer(prices_dict, "low", 0, length, &low_buf) ||
        !acquire_double_buffer(prices_dict, "volume", 0, length, &volume_buf) ||
        !acquire_double_buffer(prices_dict, "vol", 0, length, &vol_buf)) {
        goto cleanup;
    }

    if (!acquire_double_buffer(adjustments_dict, "fenhong", 1, length, &fenhong_buf) ||
        !acquire_double_buffer(adjustments_dict, "peigu", 1, length, &peigu_buf) ||
        !acquire_double_buffer(adjustments_dict, "peigujia", 1, length, &peigujia_buf) ||
        !acquire_double_buffer(adjustments_dict, "songzhuangu", 1, length, &songzhuangu_buf)) {
        goto cleanup;
    }

    if (length == 0) {
        success = 1;
        goto cleanup;
    }

    int mode = parse_adjust_mode(adjust_type);
    if (mode < 0) {
        goto cleanup;
    }

    double* close = close_buf.data;
    double* adj = adj_buf.data;
    double* preclose = preclose_buf.data;
    double* open = open_buf.data;
    double* high = high_buf.data;
    double* low = low_buf.data;
    double* volume = volume_buf.data;
    double* vol = vol_buf.data;
    double* fenhong = fenhong_buf.data;
    double* peigu = peigu_buf.data;
    double* peigujia = peigujia_buf.data;
    double* songzhuangu = songzhuangu_buf.data;

    preclose[0] = close[0];
    double prev_close = close[0];

    for (Py_ssize_t i = 1; i < length; i++) {
        double numerator = prev_close * 10.0 - fenhong[i] + peigu[i] * peigujia[i];
        double denominator = 10.0 + peigu[i] + songzhuangu[i];
        double value = prev_close;

        if (fabs(denominator) > 1e-12) {
            value = numerator / denominator;
        }

        if (!isfinite(value)) {
            value = prev_close;
        }

        preclose[i] = value;
        prev_close = close[i];
    }

    if (mode == ADJUST_MODE_QFQ) {
        adj[length - 1] = 1.0;
        double cumulative = 1.0;
        for (Py_ssize_t idx = length - 1; idx > 0; --idx) {
            Py_ssize_t i = idx - 1;
            double ratio = 1.0;
            if (close[i] != 0.0) {
                ratio = preclose[i + 1] / close[i];
            }
            if (!isfinite(ratio) || ratio <= 0.0) {
                ratio = 1.0;
            }
            cumulative *= ratio;
            adj[i] = cumulative;
        }
    } else {
        double cumulative = 1.0;
        for (Py_ssize_t i = 0; i < length; i++) {
            double ratio = 1.0;
            if (i < length - 1 && close[i] != 0.0) {
                ratio = preclose[i + 1] / close[i];
            }
            if (!isfinite(ratio) || ratio <= 0.0) {
                ratio = 1.0;
            }
            cumulative *= ratio;
            adj[i] = cumulative;
        }
    }

    if (mode == ADJUST_MODE_QFQ) {
        multiply_series(close, adj, length);
        multiply_series(preclose, adj, length);
        if (open_buf.present) {
            multiply_series(open, adj, length);
        }
        if (high_buf.present) {
            multiply_series(high, adj, length);
        }
        if (low_buf.present) {
            multiply_series(low, adj, length);
        }
    } else {
        divide_series(close, adj, length);
        divide_series(preclose, adj, length);
        if (open_buf.present) {
            divide_series(open, adj, length);
        }
        if (high_buf.present) {
            divide_series(high, adj, length);
        }
        if (low_buf.present) {
            divide_series(low, adj, length);
        }
    }

    if (volume_buf.present) {
        divide_series(volume, adj, length);
    }
    if (vol_buf.present) {
        divide_series(vol, adj, length);
    }

    success = 1;

cleanup:
    release_double_buffer(&close_buf);
    release_double_buffer(&adj_buf);
    release_double_buffer(&preclose_buf);
    release_double_buffer(&open_buf);
    release_double_buffer(&high_buf);
    release_double_buffer(&low_buf);
    release_double_buffer(&volume_buf);
    release_double_buffer(&vol_buf);
    release_double_buffer(&fenhong_buf);
    release_double_buffer(&peigu_buf);
    release_double_buffer(&peigujia_buf);
    release_double_buffer(&songzhuangu_buf);

    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}


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

static PyObject* py_compute_period_statistics(PyObject* self, PyObject* args, PyObject* kwargs) {
    PyObject *dates_obj, *pnl_obj;
    double initial_equity = 1000000.0;
    double risk_free_rate = 0.03;
    int trading_days = 252;

    static char* kwlist[] = {"dates", "pnl", "initial_equity", "risk_free_rate", "trading_days_per_year", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|ddi", kwlist, &dates_obj, &pnl_obj, &initial_equity, &risk_free_rate, &trading_days)) {
        return NULL;
    }

    Py_ssize_t count = PySequence_Length(dates_obj);
    if (count < 0) {
        PyErr_SetString(PyExc_ValueError, "无法获取日期序列长度");
        return NULL;
    }

    if (PySequence_Length(pnl_obj) != count) {
        PyErr_SetString(PyExc_ValueError, "日期与盈亏序列长度不匹配");
        return NULL;
    }

    if (count == 0) {
        PyObject* empty_list = PyList_New(0);
        if (!empty_list) {
            return NULL;
        }
        PyObject* summary = PyDict_New();
        if (!summary) {
            Py_DECREF(empty_list);
            return NULL;
        }
        if (!dict_set_double(summary, "initial_equity", initial_equity) ||
            !dict_set_double(summary, "final_equity", initial_equity) ||
            !dict_set_double(summary, "total_pnl", 0.0) ||
            !dict_set_double(summary, "total_return", 0.0) ||
            !dict_set_double(summary, "annual_return", 0.0) ||
            !dict_set_double(summary, "volatility", 0.0) ||
            !dict_set_double(summary, "sharpe_ratio", 0.0) ||
            !dict_set_double(summary, "max_drawdown", 0.0) ||
            !dict_set_double(summary, "max_drawdown_duration", 0.0) ||
            !dict_set_double(summary, "win_rate", 0.0) ||
            !dict_set_long(summary, "trading_days", 0)) {
            Py_DECREF(empty_list);
            Py_DECREF(summary);
            return NULL;
        }

        PyObject* result = PyDict_New();
        if (!result) {
            Py_DECREF(empty_list);
            Py_DECREF(summary);
            return NULL;
        }
        Py_INCREF(Py_True);
        if (PyDict_SetItemString(result, "success", Py_True) < 0) {
            Py_DECREF(Py_True);
            Py_DECREF(result);
            Py_DECREF(empty_list);
            Py_DECREF(summary);
            return NULL;
        }
        Py_DECREF(Py_True);

        if (PyDict_SetItemString(result, "daily", empty_list) < 0 ||
            PyDict_SetItemString(result, "weekly", empty_list) < 0 ||
            PyDict_SetItemString(result, "monthly", empty_list) < 0 ||
            PyDict_SetItemString(result, "equity_curve", empty_list) < 0 ||
            PyDict_SetItemString(result, "summary", summary) < 0) {
            Py_DECREF(result);
            Py_DECREF(empty_list);
            Py_DECREF(summary);
            return NULL;
        }

        Py_DECREF(empty_list);
        Py_DECREF(summary);
        return result;
    }

    int* dates = (int*)malloc(sizeof(int) * (size_t)count);
    double* pnls = (double*)malloc(sizeof(double) * (size_t)count);
    if (!dates || !pnls) {
        free(dates);
        free(pnls);
        return PyErr_NoMemory();
    }

    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject* date_item = PySequence_GetItem(dates_obj, i);
        PyObject* pnl_item = PySequence_GetItem(pnl_obj, i);
        if (!date_item || !pnl_item) {
            Py_XDECREF(date_item);
            Py_XDECREF(pnl_item);
            free(dates);
            free(pnls);
            PyErr_SetString(PyExc_ValueError, "无法读取日期或盈亏数据");
            return NULL;
        }

        if (!convert_date_pyobject(date_item, &dates[i])) {
            Py_DECREF(date_item);
            Py_DECREF(pnl_item);
            free(dates);
            free(pnls);
            return NULL;
        }

        pnls[i] = PyFloat_AsDouble(pnl_item);
        Py_DECREF(date_item);
        Py_DECREF(pnl_item);

        if (PyErr_Occurred()) {
            free(dates);
            free(pnls);
            PyErr_SetString(PyExc_ValueError, "盈亏数据无法转换为浮点数");
            return NULL;
        }
    }

    DailyEntry* daily_entries = NULL;
    size_t daily_count = 0;
    if (!build_daily_entries(dates, pnls, (size_t)count, initial_equity, &daily_entries, &daily_count)) {
        free(dates);
        free(pnls);
        return NULL;
    }

    free(dates);
    free(pnls);

    PyObject *daily_list = NULL, *weekly_list = NULL, *monthly_list = NULL, *equity_curve = NULL, *summary = NULL, *result = NULL;
    PeriodEntry *weekly_entries = NULL, *monthly_entries = NULL;
    size_t weekly_count = 0;
    size_t monthly_count = 0;

    daily_list = PyList_New((Py_ssize_t)daily_count);
    equity_curve = PyList_New((Py_ssize_t)daily_count);
    if (!daily_list || !equity_curve) {
        goto error;
    }

    double total_pnl = 0.0;
    double sum_returns = 0.0;
    double sum_square_returns = 0.0;
    size_t win_days = 0;

    for (size_t i = 0; i < daily_count; i++) {
        PyObject* entry_dict = PyDict_New();
        PyObject* curve_point = PyDict_New();
        PyObject* label = NULL;
        PyObject* date_label = NULL;
        if (!entry_dict || !curve_point) {
            Py_XDECREF(entry_dict);
            Py_XDECREF(curve_point);
            goto error;
        }

        label = PyUnicode_FromString(daily_entries[i].label);
        if (!label || PyDict_SetItemString(entry_dict, "period", label) < 0) {
            Py_XDECREF(label);
            Py_DECREF(entry_dict);
            Py_DECREF(curve_point);
            goto error;
        }
        Py_DECREF(label);

        if (!dict_set_double(entry_dict, "pnl", daily_entries[i].pnl) ||
            !dict_set_double(entry_dict, "return", daily_entries[i].daily_return) ||
            !dict_set_double(entry_dict, "start_equity", daily_entries[i].start_equity) ||
            !dict_set_double(entry_dict, "end_equity", daily_entries[i].end_equity) ||
            !dict_set_double(entry_dict, "cumulative_return", daily_entries[i].cumulative_return)) {
            Py_DECREF(entry_dict);
            Py_DECREF(curve_point);
            goto error;
        }

        if (PyList_SetItem(daily_list, (Py_ssize_t)i, entry_dict) < 0) {
            Py_DECREF(entry_dict);
            Py_DECREF(curve_point);
            goto error;
        }

        date_label = PyUnicode_FromString(daily_entries[i].label);
        if (!date_label || PyDict_SetItemString(curve_point, "date", date_label) < 0) {
            Py_XDECREF(date_label);
            Py_DECREF(curve_point);
            goto error;
        }
        Py_DECREF(date_label);
        if (!dict_set_double(curve_point, "equity", daily_entries[i].end_equity)) {
            Py_DECREF(curve_point);
            goto error;
        }

        if (PyList_SetItem(equity_curve, (Py_ssize_t)i, curve_point) < 0) {
            Py_DECREF(curve_point);
            goto error;
        }

        total_pnl += daily_entries[i].pnl;
        sum_returns += daily_entries[i].daily_return;
        sum_square_returns += daily_entries[i].daily_return * daily_entries[i].daily_return;
        if (daily_entries[i].pnl > 0.0) {
            win_days += 1;
        }
    }

    if (!build_period_entries(daily_entries, daily_count, "weekly", initial_equity, &weekly_entries, &weekly_count)) {
        goto error;
    }

    if (!build_period_entries(daily_entries, daily_count, "monthly", initial_equity, &monthly_entries, &monthly_count)) {
        goto error;
    }

    weekly_list = PyList_New((Py_ssize_t)weekly_count);
    monthly_list = PyList_New((Py_ssize_t)monthly_count);
    if (!weekly_list || !monthly_list) {
        goto error;
    }

    for (size_t i = 0; i < weekly_count; i++) {
        PyObject* entry_dict = PyDict_New();
        PyObject* label = PyUnicode_FromString(weekly_entries[i].label);
        if (!entry_dict || !label) {
            Py_XDECREF(entry_dict);
            Py_XDECREF(label);
            goto error;
        }
        if (PyDict_SetItemString(entry_dict, "period", label) < 0 ||
            !dict_set_double(entry_dict, "pnl", weekly_entries[i].pnl) ||
            !dict_set_double(entry_dict, "return", weekly_entries[i].return_ratio) ||
            !dict_set_double(entry_dict, "start_equity", weekly_entries[i].start_equity) ||
            !dict_set_double(entry_dict, "end_equity", weekly_entries[i].end_equity) ||
            !dict_set_double(entry_dict, "cumulative_return", weekly_entries[i].cumulative_return)) {
            Py_DECREF(entry_dict);
            Py_DECREF(label);
            goto error;
        }
        Py_DECREF(label);
        if (PyList_SetItem(weekly_list, (Py_ssize_t)i, entry_dict) < 0) {
            Py_DECREF(entry_dict);
            goto error;
        }
    }

    for (size_t i = 0; i < monthly_count; i++) {
        PyObject* entry_dict = PyDict_New();
        PyObject* label = PyUnicode_FromString(monthly_entries[i].label);
        if (!entry_dict || !label) {
            Py_XDECREF(entry_dict);
            Py_XDECREF(label);
            goto error;
        }
        if (PyDict_SetItemString(entry_dict, "period", label) < 0 ||
            !dict_set_double(entry_dict, "pnl", monthly_entries[i].pnl) ||
            !dict_set_double(entry_dict, "return", monthly_entries[i].return_ratio) ||
            !dict_set_double(entry_dict, "start_equity", monthly_entries[i].start_equity) ||
            !dict_set_double(entry_dict, "end_equity", monthly_entries[i].end_equity) ||
            !dict_set_double(entry_dict, "cumulative_return", monthly_entries[i].cumulative_return)) {
            Py_DECREF(entry_dict);
            Py_DECREF(label);
            goto error;
        }
        Py_DECREF(label);
        if (PyList_SetItem(monthly_list, (Py_ssize_t)i, entry_dict) < 0) {
            Py_DECREF(entry_dict);
            goto error;
        }
    }

    double daily_count_d = (double)daily_count;
    double mean_return = sum_returns / daily_count_d;
    double variance = (sum_square_returns / daily_count_d) - (mean_return * mean_return);
    if (variance < 0.0) {
        variance = 0.0;
    }
    double std_daily = sqrt(variance);
    double annual_return = mean_return * trading_days;
    double annual_volatility = std_daily * sqrt((double)trading_days);
    double sharpe_ratio = (annual_volatility > 0.0) ? ((annual_return - risk_free_rate) / annual_volatility) : 0.0;
    double win_rate = daily_count > 0 ? ((double)win_days / daily_count_d) : 0.0;

    double max_drawdown_duration = 0.0;
    double max_drawdown = compute_max_drawdown(daily_entries, daily_count, &max_drawdown_duration);
    double final_equity = daily_entries[daily_count - 1].end_equity;
    double total_return = (final_equity - initial_equity) / (initial_equity > 0.0 ? initial_equity : 1.0);

    summary = PyDict_New();
    if (!summary ||
        !dict_set_double(summary, "initial_equity", initial_equity) ||
        !dict_set_double(summary, "final_equity", final_equity) ||
        !dict_set_double(summary, "total_pnl", total_pnl) ||
        !dict_set_double(summary, "total_return", total_return) ||
        !dict_set_double(summary, "annual_return", annual_return) ||
        !dict_set_double(summary, "volatility", annual_volatility) ||
        !dict_set_double(summary, "sharpe_ratio", sharpe_ratio) ||
        !dict_set_double(summary, "max_drawdown", max_drawdown) ||
        !dict_set_double(summary, "max_drawdown_duration", max_drawdown_duration) ||
        !dict_set_double(summary, "win_rate", win_rate) ||
        !dict_set_long(summary, "trading_days", (Py_ssize_t)daily_count)) {
        goto error;
    }

    result = PyDict_New();
    if (!result) {
        goto error;
    }
    Py_INCREF(Py_True);
    if (PyDict_SetItemString(result, "success", Py_True) < 0) {
        Py_DECREF(Py_True);
        goto error;
    }
    Py_DECREF(Py_True);

    if (PyDict_SetItemString(result, "daily", daily_list) < 0 ||
        PyDict_SetItemString(result, "weekly", weekly_list) < 0 ||
        PyDict_SetItemString(result, "monthly", monthly_list) < 0 ||
        PyDict_SetItemString(result, "equity_curve", equity_curve) < 0 ||
        PyDict_SetItemString(result, "summary", summary) < 0) {
        goto error;
    }

    Py_DECREF(daily_list);
    Py_DECREF(weekly_list);
    Py_DECREF(monthly_list);
    Py_DECREF(equity_curve);
    Py_DECREF(summary);

    free(daily_entries);
    free(weekly_entries);
    free(monthly_entries);

    return result;

error:
    Py_XDECREF(daily_list);
    Py_XDECREF(weekly_list);
    Py_XDECREF(monthly_list);
    Py_XDECREF(equity_curve);
    Py_XDECREF(summary);
    Py_XDECREF(result);
    free(daily_entries);
    free(weekly_entries);
    free(monthly_entries);
    return NULL;
}

static PyObject* py_compute_risk_profile(PyObject* self, PyObject* args, PyObject* kwargs) {
    PyObject* returns_obj;
    double scale = 1.0;
    double risk_free_rate = 0.03;
    int trading_days = 252;
    PyObject* confidence_levels_obj = Py_None;

    static char* kwlist[] = {"returns", "scale", "risk_free_rate", "trading_days_per_year", "confidence_levels", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|ddiO", kwlist, &returns_obj, &scale, &risk_free_rate, &trading_days, &confidence_levels_obj)) {
        return NULL;
    }

    PyObject* returns_seq = PySequence_Fast(returns_obj, "returns必须是可迭代对象");
    if (!returns_seq) {
        return NULL;
    }

    Py_ssize_t count = PySequence_Fast_GET_SIZE(returns_seq);
    if (count < 2) {
        Py_DECREF(returns_seq);
        PyErr_SetString(PyExc_ValueError, "计算风险指标至少需要2个收益率数据点");
        return NULL;
    }

    double* returns = (double*)malloc(sizeof(double) * (size_t)count);
    double* returns_sorted = (double*)malloc(sizeof(double) * (size_t)count);
    if (!returns || !returns_sorted) {
        Py_DECREF(returns_seq);
        free(returns);
        free(returns_sorted);
        return PyErr_NoMemory();
    }

    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject* item = PySequence_Fast_GET_ITEM(returns_seq, i);
        returns[i] = PyFloat_AsDouble(item);
        if (PyErr_Occurred()) {
            Py_DECREF(returns_seq);
            free(returns);
            free(returns_sorted);
            PyErr_SetString(PyExc_ValueError, "收益率序列必须为浮点数");
            return NULL;
        }
        returns_sorted[i] = returns[i];
    }
    Py_DECREF(returns_seq);

    qsort(returns_sorted, (size_t)count, sizeof(double), compare_double_asc);

    double sum = 0.0;
    double sum_sq = 0.0;
    double sum_cub = 0.0;
    double sum_quad = 0.0;
    size_t wins = 0;
    size_t losses = 0;
    double sum_gain = 0.0;
    double sum_loss = 0.0;
    size_t downside_count = 0;
    double downside_sum_sq = 0.0;

    for (Py_ssize_t i = 0; i < count; i++) {
        double r = returns[i];
        sum += r;
        sum_sq += r * r;
        sum_cub += r * r * r;
        sum_quad += r * r * r * r;
        if (r > 0.0) {
            wins += 1;
            sum_gain += r;
        } else if (r < 0.0) {
            losses += 1;
            sum_loss += r;
            downside_sum_sq += r * r;
            downside_count += 1;
        } else {
            downside_count += 1;
        }
    }

    double count_d = (double)count;
    double mean_return = sum / count_d;
    double variance = (sum_sq / count_d) - (mean_return * mean_return);
    if (variance < 0.0) {
        variance = 0.0;
    }
    double std_return = sqrt(variance);
    double skewness = 0.0;
    double kurtosis = 0.0;
    if (std_return > 0.0) {
        double m3 = sum_cub / count_d - 3.0 * mean_return * variance - pow(mean_return, 3.0);
        double m4 = sum_quad / count_d - 4.0 * mean_return * sum_cub / count_d + 6.0 * mean_return * mean_return * variance + 3.0 * pow(mean_return, 4.0);
        skewness = m3 / pow(std_return, 3.0);
        kurtosis = m4 / (variance * variance);
    }

    double annual_return = mean_return * trading_days;
    double annual_volatility = std_return * sqrt((double)trading_days);
    double sharpe_ratio = (annual_volatility > 0.0) ? ((annual_return - risk_free_rate) / annual_volatility) : 0.0;

    double downside_deviation = 0.0;
    if (downside_count > 0) {
        downside_deviation = sqrt(downside_sum_sq / (double)downside_count) * sqrt((double)trading_days);
    }
    double sortino_ratio = (downside_deviation > 0.0) ? ((annual_return - risk_free_rate) / downside_deviation) : 0.0;

    double win_rate = wins > 0 ? ((double)wins / count_d) : 0.0;
    double loss_rate = losses > 0 ? ((double)losses / count_d) : 0.0;
    double avg_gain = wins > 0 ? (sum_gain / (double)wins) : 0.0;
    double avg_loss = losses > 0 ? (sum_loss / (double)losses) : 0.0;

    double* confidence_levels = NULL;
    size_t level_count = 0;
    if (!extract_confidence_levels(confidence_levels_obj, &confidence_levels, &level_count)) {
        free(returns);
        free(returns_sorted);
        return NULL;
    }

    int use_default_levels = 0;
    if (level_count == 0) {
        static double default_levels[] = {0.95, 0.99};
        confidence_levels = default_levels;
        level_count = sizeof(default_levels) / sizeof(default_levels[0]);
        use_default_levels = 1;
    }

    PyObject* var_dict = PyDict_New();
    if (!var_dict) {
        free(returns);
        free(returns_sorted);
        if (!use_default_levels && confidence_levels) {
            free(confidence_levels);
        }
        return NULL;
    }

    for (size_t i = 0; i < level_count; i++) {
        double level = confidence_levels[i];
        double var_value = compute_quantile(returns_sorted, (size_t)count, 1.0 - level);

        double cvar_sum = 0.0;
        size_t cvar_count = 0;
        for (Py_ssize_t j = 0; j < count; j++) {
            if (returns[j] <= var_value) {
                cvar_sum += returns[j];
                cvar_count += 1;
            }
        }
        double cvar_value = (cvar_count > 0) ? (cvar_sum / (double)cvar_count) : var_value;

        PyObject* entry = PyDict_New();
        if (!entry ||
            !dict_set_double(entry, "var_value", var_value) ||
            !dict_set_double(entry, "var_amount", fabs(var_value * scale)) ||
            !dict_set_double(entry, "cvar_value", cvar_value) ||
            !dict_set_double(entry, "cvar_amount", fabs(cvar_value * scale))) {
            Py_XDECREF(entry);
            Py_DECREF(var_dict);
            free(returns);
            free(returns_sorted);
            if (!use_default_levels && confidence_levels) {
                free(confidence_levels);
            }
            return NULL;
        }

        char key_buffer[16];
        PyOS_snprintf(key_buffer, sizeof(key_buffer), "%.2f", level);
        PyObject* key = PyUnicode_FromString(key_buffer);
        if (!key || PyDict_SetItem(var_dict, key, entry) < 0) {
            Py_XDECREF(key);
            Py_DECREF(entry);
            Py_DECREF(var_dict);
            free(returns);
            free(returns_sorted);
            if (!use_default_levels && confidence_levels) {
                free(confidence_levels);
            }
            return NULL;
        }
        Py_DECREF(key);
        Py_DECREF(entry);
    }

    if (!use_default_levels && confidence_levels) {
        free(confidence_levels);
    }

    double* equity_curve = (double*)malloc(sizeof(double) * ((size_t)count + 1));
    if (!equity_curve) {
        free(returns);
        free(returns_sorted);
        Py_DECREF(var_dict);
        return PyErr_NoMemory();
    }
    equity_curve[0] = 1.0;
    for (Py_ssize_t i = 0; i < count; i++) {
        equity_curve[i + 1] = equity_curve[i] * (1.0 + returns[i]);
    }

    double max_drawdown_duration = 0.0;
    double peak = equity_curve[0];
    double max_drawdown = 0.0;
    size_t peak_index = 0;
    size_t trough_index = 0;
    size_t current_peak_index = 0;
    for (Py_ssize_t i = 1; i <= count; i++) {
        double equity = equity_curve[i];
        if (equity > peak) {
            peak = equity;
            current_peak_index = (size_t)i;
        }
        double drawdown = (equity - peak) / (peak > 0.0 ? peak : 1.0);
        if (drawdown < max_drawdown) {
            max_drawdown = drawdown;
            peak_index = current_peak_index;
            trough_index = (size_t)i;
        }
    }
    if (trough_index > peak_index) {
        max_drawdown_duration = (double)(trough_index - peak_index);
    }
    double calmar_ratio = (max_drawdown < 0.0) ? (annual_return / fabs(max_drawdown)) : 0.0;
    double cumulative_return = equity_curve[count] - 1.0;

    PyObject* equity_list = PyList_New((Py_ssize_t)(count + 1));
    if (!equity_list) {
        free(returns);
        free(returns_sorted);
        free(equity_curve);
        Py_DECREF(var_dict);
        return NULL;
    }

    for (Py_ssize_t i = 0; i <= count; i++) {
        PyObject* value = PyFloat_FromDouble(equity_curve[i]);
        if (!value) {
            Py_DECREF(equity_list);
            free(returns);
            free(returns_sorted);
            free(equity_curve);
            Py_DECREF(var_dict);
            return NULL;
        }
        PyList_SET_ITEM(equity_list, i, value);
    }

    PyObject* result = PyDict_New();
    if (!result ||
        !dict_set_long(result, "count", count) ||
        !dict_set_double(result, "mean_return", mean_return) ||
        !dict_set_double(result, "std_return", std_return) ||
        !dict_set_double(result, "annual_return", annual_return) ||
        !dict_set_double(result, "annual_volatility", annual_volatility) ||
        !dict_set_double(result, "sharpe_ratio", sharpe_ratio) ||
        !dict_set_double(result, "sortino_ratio", sortino_ratio) ||
        !dict_set_double(result, "skewness", skewness) ||
        !dict_set_double(result, "kurtosis", kurtosis) ||
        !dict_set_double(result, "win_rate", win_rate) ||
        !dict_set_double(result, "loss_rate", loss_rate) ||
        !dict_set_double(result, "avg_gain", avg_gain) ||
        !dict_set_double(result, "avg_loss", avg_loss) ||
        !dict_set_double(result, "downside_deviation", downside_deviation) ||
        !dict_set_double(result, "max_drawdown", max_drawdown) ||
        !dict_set_double(result, "max_drawdown_duration", max_drawdown_duration) ||
        !dict_set_double(result, "calmar_ratio", calmar_ratio) ||
        !dict_set_double(result, "cumulative_return", cumulative_return) ||
        PyDict_SetItemString(result, "var", var_dict) < 0 ||
        PyDict_SetItemString(result, "equity_curve", equity_list) < 0) {
        Py_XDECREF(result);
        Py_DECREF(var_dict);
        Py_DECREF(equity_list);
        free(returns);
        free(returns_sorted);
        free(equity_curve);
        return NULL;
    }

    Py_DECREF(var_dict);
    Py_DECREF(equity_list);

    free(returns);
    free(returns_sorted);
    free(equity_curve);

    return result;
}

// 方法定义表
static PyMethodDef FinanceOpsMethods[] = {
    {"apply_price_adjustments", (PyCFunction)py_apply_price_adjustments, METH_VARARGS | METH_KEYWORDS,
     "Apply price adjustments (前复权/后复权) using native implementation"},
    {"aggregate_daily_pnl", py_aggregate_daily_pnl, METH_VARARGS,
     "Aggregate daily PnL and generate cumulative equity curve"},
    {"compute_return_metrics", (PyCFunction)py_compute_return_metrics, METH_VARARGS | METH_KEYWORDS,
     "Compute performance metrics (return, volatility, sharpe, drawdown, etc.)"},
    {"bucketize_period", py_bucketize_period, METH_VARARGS,
     "Bucketize equity series by period (weekly, monthly, yearly)"},
    {"compute_period_statistics", (PyCFunction)py_compute_period_statistics, METH_VARARGS | METH_KEYWORDS,
     "Compute aggregated period statistics (daily/weekly/monthly) using native routines"},
    {"compute_risk_profile", (PyCFunction)py_compute_risk_profile, METH_VARARGS | METH_KEYWORDS,
     "Compute portfolio risk profile including VaR/CVaR, drawdown, and ratios"},
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
