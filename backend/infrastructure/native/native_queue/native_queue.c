#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#include "../native_log_bridge.h"

#define NATIVE_QUEUE_COMPONENT "backend.native.queue.core"
#define NATIVE_QUEUE_WRAPPER_COMPONENT "backend.native.queue.wrapper"

static void queue_log(
    int level,
    const char *function,
    int line,
    const char *message,
    const char *details
) {
    native_log_bridge_log(
        level,
        NATIVE_QUEUE_COMPONENT,
        function,
        line,
        message,
        details);
}

static void queue_log_warning(const char *function, int line, const char *message, const char *details) {
    queue_log(NATIVE_LOG_LEVEL_WARNING, function, line, message, details);
}

static void queue_log_error(const char *function, int line, const char *message, const char *details) {
    queue_log(NATIVE_LOG_LEVEL_ERROR, function, line, message, details);
}

static void queue_log_info(const char *function, int line, const char *message, const char *details) {
    queue_log(NATIVE_LOG_LEVEL_INFO, function, line, message, details);
}

typedef struct {
    PyObject_HEAD
    PyObject **buffer;
    Py_ssize_t capacity;
    Py_ssize_t head;
    Py_ssize_t tail;
    Py_ssize_t count;
    PyThread_type_lock lock;
} NativeQueueObject;

static int
native_queue_resize(NativeQueueObject *self, Py_ssize_t new_capacity)
{
    PyObject **new_buffer = (PyObject **)PyMem_Realloc(self->buffer, sizeof(PyObject *) * new_capacity);
    if (new_buffer == NULL) {
        PyErr_NoMemory();
        return -1;
    }

    /* realign elements if head is not zero */
    if (self->count > 0 && self->head != 0) {
        if (self->head < self->tail) {
            /* contiguous block already */
        } else {
            /* wrap-around, rearrange */
            Py_ssize_t right_count = self->capacity - self->head;
            memmove(new_buffer + (new_capacity - right_count), new_buffer + self->head, sizeof(PyObject *) * right_count);
            memmove(new_buffer, new_buffer + self->tail, sizeof(PyObject *) * self->tail);
            self->head = new_capacity - right_count;
        }
    }

    self->buffer = new_buffer;
    self->capacity = new_capacity;
    if (self->count == 0) {
        self->head = 0;
        self->tail = 0;
    } else {
        self->tail = (self->head + self->count) % new_capacity;
    }
    return 0;
}

static int
NativeQueue_init(NativeQueueObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"capacity", NULL};
    Py_ssize_t capacity = 1024;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|n", kwlist, &capacity)) {
        return -1;
    }
    if (capacity <= 0) {
        capacity = 1024;
    }

    self->buffer = (PyObject **)PyMem_Calloc(capacity, sizeof(PyObject *));
    if (self->buffer == NULL) {
        PyErr_NoMemory();
        return -1;
    }
    self->capacity = capacity;
    self->head = 0;
    self->tail = 0;
    self->count = 0;
    self->lock = PyThread_allocate_lock();
    if (self->lock == NULL) {
        PyMem_Free(self->buffer);
        self->buffer = NULL;
        PyErr_SetString(PyExc_RuntimeError, "failed to allocate lock");
        return -1;
    }
    return 0;
}

static void
NativeQueue_dealloc(NativeQueueObject *self)
{
    if (self->lock != NULL) {
        PyThread_free_lock(self->lock);
        self->lock = NULL;
    }
    if (self->buffer != NULL) {
        Py_ssize_t i;
        for (i = 0; i < self->capacity; ++i) {
            Py_XDECREF(self->buffer[i]);
        }
        PyMem_Free(self->buffer);
        self->buffer = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
NativeQueue_push(NativeQueueObject *self, PyObject *arg)
{
    if (arg == NULL) {
        PyErr_SetString(PyExc_ValueError, "item cannot be NULL");
        queue_log_warning(__FUNCTION__, __LINE__, "Attempted to push NULL item into queue", NULL);
        return NULL;
    }

    Py_INCREF(arg);

    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    if (self->count == self->capacity) {
        Py_ssize_t old_capacity = self->capacity;
        PyThread_release_lock(self->lock);
        Py_BEGIN_ALLOW_THREADS
        PyThread_acquire_lock(self->lock, 1);
        Py_END_ALLOW_THREADS
        Py_ssize_t new_capacity = self->capacity * 2;
        if (native_queue_resize(self, new_capacity) < 0) {
            char resize_error_details[256];
            snprintf(resize_error_details, sizeof(resize_error_details), "old_capacity=%zd,new_capacity=%zd", old_capacity, new_capacity);
            queue_log_error(__FUNCTION__, __LINE__, "Failed to resize queue buffer", resize_error_details);
            PyThread_release_lock(self->lock);
            Py_DECREF(arg);
            return NULL;
        }
        char resize_details[256];
        snprintf(resize_details, sizeof(resize_details), "old_capacity=%zd,new_capacity=%zd", old_capacity, new_capacity);
        queue_log_info(__FUNCTION__, __LINE__, "Queue buffer resized successfully", resize_details);
    }

    self->buffer[self->tail] = arg;
    self->tail = (self->tail + 1) % self->capacity;
    self->count += 1;

    PyThread_release_lock(self->lock);
    Py_RETURN_NONE;
}

static PyObject *
NativeQueue_pop(NativeQueueObject *self, PyObject *Py_UNUSED(ignored))
{
    PyObject *item = NULL;

    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    if (self->count == 0) {
        PyThread_release_lock(self->lock);
        Py_RETURN_NONE;
    }

    item = self->buffer[self->head];
    self->buffer[self->head] = NULL;
    self->head = (self->head + 1) % self->capacity;
    self->count -= 1;

    PyThread_release_lock(self->lock);
    return item;
}

static PyObject *
NativeQueue_size(NativeQueueObject *self, PyObject *Py_UNUSED(ignored))
{
    Py_ssize_t size;

    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    size = self->count;

    PyThread_release_lock(self->lock);
    return PyLong_FromSsize_t(size);
}

static PyObject *
NativeQueue_clear(NativeQueueObject *self, PyObject *Py_UNUSED(ignored))
{
    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    for (Py_ssize_t i = 0; i < self->capacity; ++i) {
        Py_XDECREF(self->buffer[i]);
        self->buffer[i] = NULL;
    }
    self->head = 0;
    self->tail = 0;
    self->count = 0;

    PyThread_release_lock(self->lock);
    Py_RETURN_NONE;
}

static PyObject *
NativeQueue_repr(NativeQueueObject *self)
{
    return PyUnicode_FromFormat("<NativeQueue size=%zd capacity=%zd>", self->count, self->capacity);
}

static PyMethodDef NativeQueue_methods[] = {
    {"push", (PyCFunction)NativeQueue_push, METH_O, PyDoc_STR("push(item) -> None")},
    {"pop", (PyCFunction)NativeQueue_pop, METH_NOARGS, PyDoc_STR("pop() -> item | None")},
    {"size", (PyCFunction)NativeQueue_size, METH_NOARGS, PyDoc_STR("size() -> int")},
    {"clear", (PyCFunction)NativeQueue_clear, METH_NOARGS, PyDoc_STR("clear() -> None")},
    {NULL, NULL, 0, NULL}};

static PyTypeObject NativeQueueType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_queue.NativeQueue",
    .tp_doc = "Multi-producer queue implemented in C",
    .tp_basicsize = sizeof(NativeQueueObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)NativeQueue_init,
    .tp_dealloc = (destructor)NativeQueue_dealloc,
    .tp_methods = NativeQueue_methods,
    .tp_repr = (reprfunc)NativeQueue_repr,
};

static PyMethodDef module_methods[] = { {NULL, NULL, 0, NULL} };

static struct PyModuleDef native_queue_module = {
    PyModuleDef_HEAD_INIT,
    "_native_queue",
    "Native queue implementation",
    -1,
    module_methods,
};

PyMODINIT_FUNC
PyInit__native_queue(void)
{
    PyObject *m;

    if (PyType_Ready(&NativeQueueType) < 0) {
        return NULL;
    }

    m = PyModule_Create(&native_queue_module);
    if (m == NULL) {
        return NULL;
    }

    Py_INCREF(&NativeQueueType);
    if (PyModule_AddObject(m, "NativeQueue", (PyObject *)&NativeQueueType) < 0) {
        Py_DECREF(&NativeQueueType);
        Py_DECREF(m);
        return NULL;
    }

    if (PyModule_AddIntConstant(m, "QUEUE_AVAILABLE", 1) < 0) {
        Py_DECREF(&NativeQueueType);
        Py_DECREF(m);
        return NULL;
    }

    if (PyModule_AddStringConstant(m, "__version__", "0.1.0") < 0) {
        Py_DECREF(&NativeQueueType);
        Py_DECREF(m);
        return NULL;
    }

    queue_log_info(__FUNCTION__, __LINE__, "native_queue module initialised", NULL);
    return m;
}

