/* -*- coding: utf-8 -*- */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <ctype.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#if !defined(NAN)
#define NAN (0.0 / 0.0)
#endif

typedef struct {
    double* data;
    Py_ssize_t size;
} double_buffer;

static void
free_buffer(double_buffer* buffer) {
    if (buffer && buffer->data) {
        PyMem_Free(buffer->data);
        buffer->data = NULL;
        buffer->size = 0;
    }
}

static int
read_iterable_as_double(PyObject* iterable, double_buffer* out_buffer) {
    PyObject* seq = PySequence_Fast(iterable, "closes must be iterable");
    if (!seq) {
        return -1;
    }

    Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
    double* values = PyMem_Calloc((size == 0 ? 1 : size), sizeof(double));
    if (!values) {
        Py_DECREF(seq);
        PyErr_NoMemory();
        return -1;
    }

    PyObject** items = PySequence_Fast_ITEMS(seq);
    for (Py_ssize_t i = 0; i < size; ++i) {
        double value = PyFloat_AsDouble(items[i]);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            PyMem_Free(values);
            return -1;
        }
        values[i] = value;
    }

    Py_DECREF(seq);

    out_buffer->data = values;
    out_buffer->size = size;
    return 0;
}

static PyObject*
create_nan_list(Py_ssize_t size) {
    PyObject* list = PyList_New(size);
    if (!list) {
        return NULL;
    }
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* value = PyFloat_FromDouble(NAN);
        if (!value) {
            Py_DECREF(list);
            return NULL;
        }
        PyList_SET_ITEM(list, i, value);
    }
    return list;
}

static PyObject*
build_list_from_array(const double* data, Py_ssize_t size) {
    PyObject* list = PyList_New(size);
    if (!list) {
        return NULL;
    }
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* value = PyFloat_FromDouble(data[i]);
        if (!value) {
            Py_DECREF(list);
            return NULL;
        }
        PyList_SET_ITEM(list, i, value);
    }
    return list;
}

static PyObject*
indicator_sma(const double_buffer* buffer, int period) {
    if (period <= 0) {
        PyErr_SetString(PyExc_ValueError, "period must be positive");
        return NULL;
    }

    Py_ssize_t size = buffer->size;
    if (size == 0) {
        return PyList_New(0);
    }

    PyObject* result = PyList_New(size);
    if (!result) {
        return NULL;
    }

    double running_sum = 0.0;
    for (Py_ssize_t i = 0; i < size; ++i) {
        running_sum += buffer->data[i];
        if (i >= period) {
            running_sum -= buffer->data[i - period];
        }

        PyObject* value;
        if (i + 1 < period) {
            value = PyFloat_FromDouble(NAN);
        } else {
            double avg = running_sum / (double)period;
            value = PyFloat_FromDouble(avg);
        }

        if (!value) {
            Py_DECREF(result);
            return NULL;
        }
        PyList_SET_ITEM(result, i, value);
    }

    return result;
}

static void
ema_kernel(const double* data, Py_ssize_t size, int period, double* output) {
    double alpha = 2.0 / (period + 1.0);
    double prev = data[0];
    output[0] = prev;

    for (Py_ssize_t i = 1; i < size; ++i) {
        double value = data[i];
        prev = alpha * value + (1.0 - alpha) * prev;
        output[i] = prev;
    }
}

static PyObject*
indicator_ema(const double_buffer* buffer, int period) {
    if (period <= 0) {
        PyErr_SetString(PyExc_ValueError, "period must be positive");
        return NULL;
    }

    Py_ssize_t size = buffer->size;
    if (size == 0) {
        return PyList_New(0);
    }

    double* temp = PyMem_Malloc(sizeof(double) * size);
    if (!temp) {
        PyErr_NoMemory();
        return NULL;
    }

    ema_kernel(buffer->data, size, period, temp);

    PyObject* list = PyList_New(size);
    if (!list) {
        PyMem_Free(temp);
        return NULL;
    }

    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* value = PyFloat_FromDouble(temp[i]);
        if (!value) {
            Py_DECREF(list);
            PyMem_Free(temp);
            return NULL;
        }
        PyList_SET_ITEM(list, i, value);
    }

    PyMem_Free(temp);
    return list;
}

static PyObject*
indicator_macd(const double_buffer* buffer, int fast, int slow, int signal) {
    if (fast <= 0 || slow <= 0 || signal <= 0) {
        PyErr_SetString(PyExc_ValueError, "fast/slow/signal must be positive");
        return NULL;
    }
    if (fast >= slow) {
        PyErr_SetString(PyExc_ValueError, "fast period must be less than slow period");
        return NULL;
    }

    Py_ssize_t size = buffer->size;
    if (size == 0) {
        PyObject* empty = PyList_New(0);
        if (!empty) {
            return NULL;
        }
        PyObject* dict = Py_BuildValue(
            "{s:O,s:O,s:O}", "macd", empty, "signal", empty, "hist", empty);
        Py_DECREF(empty);
        return dict;
    }

    double* fast_ema = PyMem_Malloc(sizeof(double) * size);
    double* slow_ema = PyMem_Malloc(sizeof(double) * size);
    double* macd_line = PyMem_Malloc(sizeof(double) * size);
    double* signal_line = PyMem_Malloc(sizeof(double) * size);

    if (!fast_ema || !slow_ema || !macd_line || !signal_line) {
        PyMem_Free(fast_ema);
        PyMem_Free(slow_ema);
        PyMem_Free(macd_line);
        PyMem_Free(signal_line);
        PyErr_NoMemory();
        return NULL;
    }

    ema_kernel(buffer->data, size, fast, fast_ema);
    ema_kernel(buffer->data, size, slow, slow_ema);

    for (Py_ssize_t i = 0; i < size; ++i) {
        macd_line[i] = fast_ema[i] - slow_ema[i];
    }

    ema_kernel(macd_line, size, signal, signal_line);

    PyObject* macd_list = PyList_New(size);
    PyObject* signal_list = PyList_New(size);
    PyObject* hist_list = PyList_New(size);

    if (!macd_list || !signal_list || !hist_list) {
        Py_XDECREF(macd_list);
        Py_XDECREF(signal_list);
        Py_XDECREF(hist_list);
        PyMem_Free(fast_ema);
        PyMem_Free(slow_ema);
        PyMem_Free(macd_line);
        PyMem_Free(signal_line);
        return NULL;
    }

    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* macd_value = PyFloat_FromDouble(macd_line[i]);
        PyObject* signal_value = PyFloat_FromDouble(signal_line[i]);
        PyObject* hist_value = PyFloat_FromDouble(macd_line[i] - signal_line[i]);
        if (!macd_value || !signal_value || !hist_value) {
            Py_XDECREF(macd_value);
            Py_XDECREF(signal_value);
            Py_XDECREF(hist_value);
            Py_DECREF(macd_list);
            Py_DECREF(signal_list);
            Py_DECREF(hist_list);
            PyMem_Free(fast_ema);
            PyMem_Free(slow_ema);
            PyMem_Free(macd_line);
            PyMem_Free(signal_line);
            return NULL;
        }
        PyList_SET_ITEM(macd_list, i, macd_value);
        PyList_SET_ITEM(signal_list, i, signal_value);
        PyList_SET_ITEM(hist_list, i, hist_value);
    }

    PyObject* result = Py_BuildValue(
        "{s:O,s:O,s:O}",
        "macd", macd_list,
        "signal", signal_list,
        "hist", hist_list);

    Py_DECREF(macd_list);
    Py_DECREF(signal_list);
    Py_DECREF(hist_list);

    PyMem_Free(fast_ema);
    PyMem_Free(slow_ema);
    PyMem_Free(macd_line);
    PyMem_Free(signal_line);
    return result;
}

static PyObject*
indicator_rsi(const double_buffer* buffer, int period) {
    if (period <= 0) {
        PyErr_SetString(PyExc_ValueError, "period must be positive");
        return NULL;
    }

    Py_ssize_t size = buffer->size;
    if (size == 0) {
        return PyList_New(0);
    }
    if (size == 1) {
        PyObject* list = PyList_New(1);
        if (!list) {
            return NULL;
        }
        PyList_SET_ITEM(list, 0, PyFloat_FromDouble(NAN));
        return list;
    }

    PyObject* result = create_nan_list(size);
    if (!result) {
        return NULL;
    }
    if (period >= (int)size) {
        return result;
    }

    double avg_gain = 0.0;
    double avg_loss = 0.0;

    Py_ssize_t initial = (period < (int)(size - 1)) ? period : (int)(size - 1);

    for (Py_ssize_t i = 0; i < initial; ++i) {
        double delta = buffer->data[i + 1] - buffer->data[i];
        if (delta > 0) {
            avg_gain += delta;
        } else {
            avg_loss -= delta;
        }
    }

    avg_gain /= period;
    avg_loss /= period;

    double rs = (avg_loss == 0.0) ? 0.0 : avg_gain / avg_loss;
    double rsi = 100.0 - (100.0 / (1.0 + rs));
    PyObject* initial_value = PyFloat_FromDouble(rsi);
    if (!initial_value) {
        Py_DECREF(result);
        return NULL;
    }
    if (PyList_SetItem(result, period, initial_value) != 0) {
        Py_DECREF(initial_value);
        Py_DECREF(result);
        return NULL;
    }

    for (Py_ssize_t i = period + 1; i < size; ++i) {
        double delta = buffer->data[i] - buffer->data[i - 1];
        double gain = delta > 0 ? delta : 0.0;
        double loss = delta < 0 ? -delta : 0.0;

        avg_gain = ((avg_gain * (period - 1)) + gain) / period;
        avg_loss = ((avg_loss * (period - 1)) + loss) / period;

        if (avg_loss == 0.0) {
            rsi = 100.0;
        } else {
            rs = avg_gain / avg_loss;
            rsi = 100.0 - (100.0 / (1.0 + rs));
        }
        PyObject* value = PyFloat_FromDouble(rsi);
        if (!value) {
            Py_DECREF(result);
            return NULL;
        }
        if (PyList_SetItem(result, i, value) != 0) {
            Py_DECREF(value);
            Py_DECREF(result);
            return NULL;
        }
    }

    return result;
}

static int
parse_indicator_kwargs(PyObject* kwargs, int* period, int* fast, int* slow, int* signal) {
    if (!kwargs) {
        return 0;
    }

    PyObject* value;
    if ((value = PyDict_GetItemString(kwargs, "period"))) {
        *period = (int)PyLong_AsLong(value);
        if (PyErr_Occurred()) {
            return -1;
        }
    }
    if ((value = PyDict_GetItemString(kwargs, "fast"))) {
        *fast = (int)PyLong_AsLong(value);
        if (PyErr_Occurred()) {
            return -1;
        }
    }
    if ((value = PyDict_GetItemString(kwargs, "slow"))) {
        *slow = (int)PyLong_AsLong(value);
        if (PyErr_Occurred()) {
            return -1;
        }
    }
    if ((value = PyDict_GetItemString(kwargs, "signal"))) {
        *signal = (int)PyLong_AsLong(value);
        if (PyErr_Occurred()) {
            return -1;
        }
    }
    return 0;
}

static PyObject*
py_sma(PyObject* Py_UNUSED(self), PyObject* args, PyObject* kwargs) {
    static char* kwlist[] = {"closes", "period", NULL};
    PyObject* closes = NULL;
    int period = 5;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|i", kwlist, &closes, &period)) {
        return NULL;
    }

    double_buffer buffer = {0};
    if (read_iterable_as_double(closes, &buffer) != 0) {
        return NULL;
    }

    PyObject* result = indicator_sma(&buffer, period);
    free_buffer(&buffer);
    return result;
}

static PyObject*
py_ema(PyObject* Py_UNUSED(self), PyObject* args, PyObject* kwargs) {
    static char* kwlist[] = {"closes", "period", NULL};
    PyObject* closes = NULL;
    int period = 5;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|i", kwlist, &closes, &period)) {
        return NULL;
    }

    double_buffer buffer = {0};
    if (read_iterable_as_double(closes, &buffer) != 0) {
        return NULL;
    }

    PyObject* result = indicator_ema(&buffer, period);
    free_buffer(&buffer);
    return result;
}

static PyObject*
py_macd(PyObject* Py_UNUSED(self), PyObject* args, PyObject* kwargs) {
    static char* kwlist[] = {"closes", "fast", "slow", "signal", NULL};
    PyObject* closes = NULL;
    int fast = 12;
    int slow = 26;
    int signal = 9;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|iii", kwlist, &closes, &fast, &slow, &signal)) {
        return NULL;
    }

    double_buffer buffer = {0};
    if (read_iterable_as_double(closes, &buffer) != 0) {
        return NULL;
    }

    PyObject* result = indicator_macd(&buffer, fast, slow, signal);
    free_buffer(&buffer);
    return result;
}

static PyObject*
py_rsi(PyObject* Py_UNUSED(self), PyObject* args, PyObject* kwargs) {
    static char* kwlist[] = {"closes", "period", NULL};
    PyObject* closes = NULL;
    int period = 14;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|i", kwlist, &closes, &period)) {
        return NULL;
    }

    double_buffer buffer = {0};
    if (read_iterable_as_double(closes, &buffer) != 0) {
        return NULL;
    }

    PyObject* result = indicator_rsi(&buffer, period);
    free_buffer(&buffer);
    return result;
}

static int
equals_ignore_case(const char* lhs, const char* rhs) {
    if (!lhs || !rhs) {
        return 0;
    }
    while (*lhs && *rhs) {
        if (toupper((unsigned char)*lhs) != toupper((unsigned char)*rhs)) {
            return 0;
        }
        lhs += 1;
        rhs += 1;
    }
    return *lhs == '\0' && *rhs == '\0';
}

static PyObject*
py_calculate_indicator(PyObject* Py_UNUSED(self), PyObject* args, PyObject* kwargs) {
    PyObject* closes = NULL;
    const char* indicator = NULL;

    if (!PyArg_ParseTuple(args, "sO", &indicator, &closes)) {
        return NULL;
    }

    double_buffer buffer = {0};
    if (read_iterable_as_double(closes, &buffer) != 0) {
        return NULL;
    }

    int period = 14;
    int fast = 12;
    int slow = 26;
    int signal = 9;

    if (parse_indicator_kwargs(kwargs, &period, &fast, &slow, &signal) != 0) {
        free_buffer(&buffer);
        return NULL;
    }

    PyObject* result = NULL;
    if (indicator) {
        if (equals_ignore_case(indicator, "SMA")) {
            result = indicator_sma(&buffer, period);
        } else if (equals_ignore_case(indicator, "EMA")) {
            result = indicator_ema(&buffer, period);
        } else if (equals_ignore_case(indicator, "MACD")) {
            result = indicator_macd(&buffer, fast, slow, signal);
        } else if (equals_ignore_case(indicator, "RSI")) {
            result = indicator_rsi(&buffer, period);
        } else {
            PyErr_SetString(PyExc_ValueError, "Unsupported indicator");
            result = NULL;
        }
    }

    free_buffer(&buffer);
    return result;
}

static PyObject*
py_calculate_indicator_batch(PyObject* Py_UNUSED(self), PyObject* args, PyObject* kwargs) {
    PyObject* datasets = NULL;
    const char* indicator = NULL;

    if (!PyArg_ParseTuple(args, "sO", &indicator, &datasets)) {
        return NULL;
    }

    PyObject* iterator = PyObject_GetIter(datasets);
    if (!iterator) {
        return NULL;
    }

    PyObject* result_list = PyList_New(0);
    if (!result_list) {
        Py_DECREF(iterator);
        return NULL;
    }

    int period = 14;
    int fast = 12;
    int slow = 26;
    int signal = 9;

    if (parse_indicator_kwargs(kwargs, &period, &fast, &slow, &signal) != 0) {
        Py_DECREF(iterator);
        Py_DECREF(result_list);
        return NULL;
    }

    PyObject* item;
    Py_ssize_t index = 0;
    while ((item = PyIter_Next(iterator))) {
        double_buffer buffer = {0};
        if (read_iterable_as_double(item, &buffer) != 0) {
            Py_DECREF(item);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        PyObject* computed = NULL;
        if (indicator) {
            if (equals_ignore_case(indicator, "SMA")) {
                computed = indicator_sma(&buffer, period);
            } else if (equals_ignore_case(indicator, "EMA")) {
                computed = indicator_ema(&buffer, period);
            } else if (equals_ignore_case(indicator, "MACD")) {
                computed = indicator_macd(&buffer, fast, slow, signal);
            } else if (equals_ignore_case(indicator, "RSI")) {
                computed = indicator_rsi(&buffer, period);
            } else {
                PyErr_SetString(PyExc_ValueError, "Unsupported indicator");
            }
        }

        free_buffer(&buffer);
        Py_DECREF(item);

        if (!computed) {
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        if (PyList_Append(result_list, computed) != 0) {
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            Py_DECREF(computed);
            return NULL;
        }
        Py_DECREF(computed);
        index += 1;
    }

    Py_DECREF(iterator);

    if (PyErr_Occurred()) {
        Py_DECREF(result_list);
        return NULL;
    }
    return result_list;
}

static PyMethodDef indicator_methods[] = {
    {"sma", (PyCFunction)py_sma, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("sma(closes, period=5)")},
    {"ema", (PyCFunction)py_ema, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("ema(closes, period=5)")},
    {"macd", (PyCFunction)py_macd, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("macd(closes, fast=12, slow=26, signal=9)")},
    {"rsi", (PyCFunction)py_rsi, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("rsi(closes, period=14)")},
    {"calculate_indicator", (PyCFunction)py_calculate_indicator, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("calculate_indicator(name, closes, **kwargs)")},
    {"calculate_indicator_batch", (PyCFunction)py_calculate_indicator_batch, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("calculate_indicator_batch(name, datasets, **kwargs)")},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef indicator_module = {
    PyModuleDef_HEAD_INIT,
    "native_indicator_core",
    "High performance indicator calculations",
    -1,
    indicator_methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit_native_indicator_core(void) {
    PyObject* module = PyModule_Create(&indicator_module);
    if (!module) {
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "INDICATOR_AVAILABLE", 1) != 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}


