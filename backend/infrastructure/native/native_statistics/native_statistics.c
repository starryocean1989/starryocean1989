// -*- coding: utf-8 -*-
// Streaming statistics native extension

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <pythread.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static PyTypeObject StreamingMetricHandleType;

typedef struct {
    PyObject_HEAD
    Py_ssize_t window_size;
    Py_ssize_t count;
    Py_ssize_t write_index;
    double *buffer;
    double sum;
    double sumsq;
    PyThread_type_lock lock;
} StreamingMetricHandleObject;

static int
streaming_metric_grow_buffer(StreamingMetricHandleObject *self) {
    if (self->buffer != NULL) {
        return 0;
    }
    self->buffer = PyMem_Calloc((size_t)self->window_size, sizeof(double));
    if (self->buffer == NULL) {
        PyErr_NoMemory();
        return -1;
    }
    return 0;
}

static Py_ssize_t
streaming_metric_effective_count(StreamingMetricHandleObject *self) {
    return self->count < self->window_size ? self->count : self->window_size;
}

static double
double_abs(double value) {
    return value >= 0.0 ? value : -value;
}

static void
copy_values_in_order(StreamingMetricHandleObject *self, double *dest) {
    Py_ssize_t count = streaming_metric_effective_count(self);
    if (count == 0) {
        return;
    }
    if (self->count < self->window_size) {
        memcpy(dest, self->buffer, (size_t)count * sizeof(double));
        return;
    }
    Py_ssize_t pos = self->write_index;
    for (Py_ssize_t idx = 0; idx < count; ++idx) {
        dest[idx] = self->buffer[pos];
        pos = (pos + 1) % self->window_size;
    }
}

static Py_ssize_t
partition(double *data, Py_ssize_t left, Py_ssize_t right, Py_ssize_t pivot_index) {
    double pivot_value = data[pivot_index];
    double tmp = data[pivot_index];
    data[pivot_index] = data[right];
    data[right] = tmp;

    Py_ssize_t store_index = left;
    for (Py_ssize_t i = left; i < right; ++i) {
        if (data[i] < pivot_value) {
            double swap = data[store_index];
            data[store_index] = data[i];
            data[i] = swap;
            store_index++;
        }
    }

    double swap = data[right];
    data[right] = data[store_index];
    data[store_index] = swap;
    return store_index;
}

static Py_ssize_t
choose_pivot(Py_ssize_t left, Py_ssize_t right) {
    Py_ssize_t mid = left + (right - left) / 2;
    return mid;
}

static double
quickselect(double *data, Py_ssize_t left, Py_ssize_t right, Py_ssize_t k) {
    while (left <= right) {
        if (left == right) {
            return data[left];
        }
        Py_ssize_t pivot_index = choose_pivot(left, right);
        pivot_index = partition(data, left, right, pivot_index);
        if (k == pivot_index) {
            return data[k];
        } else if (k < pivot_index) {
            right = pivot_index - 1;
        } else {
            left = pivot_index + 1;
        }
    }
    return data[left];
}

static double
compute_quantile(double *values, Py_ssize_t count, double ratio) {
    if (count <= 0) {
        return Py_NAN;
    }
    if (count == 1) {
        return values[0];
    }
    double clamped_ratio = ratio;
    if (clamped_ratio < 0.0) {
        clamped_ratio = 0.0;
    } else if (clamped_ratio > 1.0) {
        clamped_ratio = 1.0;
    }
    Py_ssize_t index = (Py_ssize_t)floor(clamped_ratio * (double)(count - 1));
    return quickselect(values, 0, count - 1, index);
}

static int
ensure_lock(StreamingMetricHandleObject *self) {
    if (self->lock != NULL) {
        return 0;
    }
    self->lock = PyThread_allocate_lock();
    if (self->lock == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "failed to allocate thread lock");
        return -1;
    }
    return 0;
}

static int
StreamingMetricHandle_traverse(StreamingMetricHandleObject *self, visitproc visit, void *arg) {
    (void)self;
    (void)visit;
    (void)arg;
    return 0;
}

static int
StreamingMetricHandle_clear(StreamingMetricHandleObject *self) {
    if (self->buffer != NULL) {
        PyMem_Free(self->buffer);
        self->buffer = NULL;
    }
    self->count = 0;
    self->write_index = 0;
    self->sum = 0.0;
    self->sumsq = 0.0;
    return 0;
}

static void
StreamingMetricHandle_dealloc(StreamingMetricHandleObject *self) {
    StreamingMetricHandle_clear(self);
    if (self->lock != NULL) {
        PyThread_free_lock(self->lock);
        self->lock = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
StreamingMetricHandle_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    StreamingMetricHandleObject *self = (StreamingMetricHandleObject *)type->tp_alloc(type, 0);
    if (self == NULL) {
        return NULL;
    }
    self->window_size = 1440;
    self->count = 0;
    self->write_index = 0;
    self->buffer = NULL;
    self->sum = 0.0;
    self->sumsq = 0.0;
    self->lock = NULL;
    return (PyObject *)self;
}

static int
StreamingMetricHandle_init(StreamingMetricHandleObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"window_size", NULL};
    Py_ssize_t window_size = 1440;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|n", kwlist, &window_size)) {
        return -1;
    }
    if (window_size <= 0) {
        PyErr_SetString(PyExc_ValueError, "window_size must be positive");
        return -1;
    }
    self->window_size = window_size;
    self->count = 0;
    self->write_index = 0;
    self->sum = 0.0;
    self->sumsq = 0.0;
    if (streaming_metric_grow_buffer(self) != 0) {
        return -1;
    }
    if (ensure_lock(self) != 0) {
        return -1;
    }
    return 0;
}

static int
streaming_metric_push_value(StreamingMetricHandleObject *self, double value) {
    if (streaming_metric_grow_buffer(self) != 0) {
        return -1;
    }
    Py_ssize_t write_index = self->write_index;
    Py_ssize_t effective = streaming_metric_effective_count(self);
    Py_ssize_t capacity = self->window_size;
    if (self->count < capacity) {
        self->count += 1;
    }
    if (effective == capacity) {
        double removed = self->buffer[write_index];
        self->sum -= removed;
        self->sumsq -= removed * removed;
    }
    self->buffer[write_index] = value;
    self->sum += value;
    self->sumsq += value * value;
    self->write_index = (write_index + 1) % capacity;
    return 0;
}

static PyObject *
StreamingMetricHandle_update(StreamingMetricHandleObject *self, PyObject *args) {
    double value;
    if (!PyArg_ParseTuple(args, "d", &value)) {
        return NULL;
    }
    if (ensure_lock(self) != 0) {
        return NULL;
    }
    PyThread_acquire_lock(self->lock, 1);
    int rc = streaming_metric_push_value(self, value);
    PyThread_release_lock(self->lock);
    if (rc != 0) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *
StreamingMetricHandle_extend(StreamingMetricHandleObject *self, PyObject *iterable) {
    if (ensure_lock(self) != 0) {
        return NULL;
    }
    PyObject *iterator = PyObject_GetIter(iterable);
    if (iterator == NULL) {
        return NULL;
    }
    int error = 0;
    PyThread_acquire_lock(self->lock, 1);
    for (PyObject *item = PyIter_Next(iterator); item != NULL; item = PyIter_Next(iterator)) {
        double value = PyFloat_AsDouble(item);
        Py_DECREF(item);
        if (PyErr_Occurred()) {
            error = 1;
            break;
        }
        if (streaming_metric_push_value(self, value) != 0) {
            error = 1;
            break;
        }
    }
    PyThread_release_lock(self->lock);
    Py_DECREF(iterator);
    if (error) {
        return NULL;
    }
    if (PyErr_Occurred()) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *
StreamingMetricHandle_reset(StreamingMetricHandleObject *self, PyObject *Py_UNUSED(ignored)) {
    if (ensure_lock(self) != 0) {
        return NULL;
    }
    PyThread_acquire_lock(self->lock, 1);
    StreamingMetricHandle_clear(self);
    streaming_metric_grow_buffer(self);
    PyThread_release_lock(self->lock);
    Py_RETURN_NONE;
}

static PyObject *
StreamingMetricHandle___len__(StreamingMetricHandleObject *self, PyObject *Py_UNUSED(ignored)) {
    Py_ssize_t count = streaming_metric_effective_count(self);
    return PyLong_FromSsize_t(count);
}

static PyObject *
StreamingMetricHandle_snapshot(StreamingMetricHandleObject *self, PyObject *Py_UNUSED(ignored)) {
    if (ensure_lock(self) != 0) {
        return NULL;
    }
    PyObject *result = NULL;
    PyThread_acquire_lock(self->lock, 1);
    Py_ssize_t count = streaming_metric_effective_count(self);
    if (count <= 0) {
        result = Py_BuildValue("{s:O,s:O,s:O,s:O,s:O}",
                               "sample_count", PyLong_FromLong(0),
                               "mean", Py_None,
                               "stddev", Py_None,
                               "p95", Py_None,
                               "p99", Py_None);
        if (result == NULL) {
            PyThread_release_lock(self->lock);
            return NULL;
        }
        Py_INCREF(Py_None);
        Py_INCREF(Py_None);
        Py_INCREF(Py_None);
        Py_INCREF(Py_None);
        PyThread_release_lock(self->lock);
        return result;
    }

    double *values = PyMem_Malloc((size_t)count * sizeof(double));
    if (values == NULL) {
        PyThread_release_lock(self->lock);
        PyErr_NoMemory();
        return NULL;
    }
    copy_values_in_order(self, values);

    double sum = self->sum;
    double sumsq = self->sumsq;
    PyThread_release_lock(self->lock);

    double mean = sum / (double)count;
    double variance = sumsq / (double)count - mean * mean;
    if (variance < 0.0) {
        variance = 0.0;
    }
    double stddev = sqrt(variance);

    double p95 = compute_quantile(values, count, 0.95);
    double p99 = compute_quantile(values, count, 0.99);

    PyMem_Free(values);

    result = Py_BuildValue("{s:n,s:d,s:d,s:d,s:d}",
                           "sample_count", count,
                           "mean", mean,
                           "stddev", stddev,
                           "p95", p95,
                           "p99", p99);
    return result;
}

static PyObject *
StreamingMetricHandle_get_window_size(StreamingMetricHandleObject *self, void *closure) {
    (void)closure;
    return PyLong_FromSsize_t(self->window_size);
}

static PyMethodDef StreamingMetricHandle_methods[] = {
    {"update", (PyCFunction)StreamingMetricHandle_update, METH_VARARGS, "Add a single sample into the window"},
    {"extend", (PyCFunction)StreamingMetricHandle_extend, METH_O, "Extend the window with an iterable of samples"},
    {"reset", (PyCFunction)StreamingMetricHandle_reset, METH_NOARGS, "Reset statistics and clear the window"},
    {"snapshot", (PyCFunction)StreamingMetricHandle_snapshot, METH_NOARGS, "Return current statistics"},
    {"__len__", (PyCFunction)StreamingMetricHandle___len__, METH_NOARGS, "Return sample count"},
    {NULL, NULL, 0, NULL}
};

static PyGetSetDef StreamingMetricHandle_getset[] = {
    {"window_size", (getter)StreamingMetricHandle_get_window_size, NULL, "window size", NULL},
    {NULL}
};

static PyTypeObject StreamingMetricHandleType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_statistics.StreamingMetricHandle",
    .tp_basicsize = sizeof(StreamingMetricHandleObject),
    .tp_itemsize = 0,
    .tp_dealloc = (destructor)StreamingMetricHandle_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "Streaming statistics handle with sliding window",
    .tp_methods = StreamingMetricHandle_methods,
    .tp_getset = StreamingMetricHandle_getset,
    .tp_init = (initproc)StreamingMetricHandle_init,
    .tp_new = StreamingMetricHandle_new,
    .tp_traverse = (traverseproc)StreamingMetricHandle_traverse,
    .tp_clear = (inquiry)StreamingMetricHandle_clear,
};

static PyObject *
module_create_streaming_metric(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwds) {
    return PyObject_Call((PyObject *)&StreamingMetricHandleType, args, kwds);
}

static PyMethodDef module_methods[] = {
    {"StreamingMetricHandle", (PyCFunction)module_create_streaming_metric, METH_VARARGS | METH_KEYWORDS,
     "Factory function creating StreamingMetricHandle"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_statistics_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_statistics",
    .m_doc = "Native streaming statistics module",
    .m_size = -1,
    .m_methods = module_methods,
};

PyMODINIT_FUNC
PyInit_native_statistics(void) {
    if (PyType_Ready(&StreamingMetricHandleType) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&native_statistics_module);
    if (module == NULL) {
        return NULL;
    }

    Py_INCREF(&StreamingMetricHandleType);
    if (PyModule_AddObject(module, "StreamingMetricHandle", (PyObject *)&StreamingMetricHandleType) < 0) {
        Py_DECREF(&StreamingMetricHandleType);
        Py_DECREF(module);
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "STATISTICS_AVAILABLE", 1) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
