#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <windows.h>
#include <process.h>

typedef struct {
    PyObject_HEAD
    PyThread_type_lock lock;
    HANDLE event;
    int completed;
    int cancelled;
    PyObject *result;
    PyObject *exception;
} NativeFutureObject;

typedef struct {
    PyObject_HEAD
    PyThread_type_lock queue_lock;
    PyObject *task_queue; /* list */
    HANDLE queue_event;
    Py_ssize_t worker_count;
    int shutting_down;
    HANDLE *worker_handles;
} NativeThreadPoolObject;

static PyTypeObject NativeFutureType;
static PyTypeObject NativeThreadPoolType;

/* -------------------- NativeFuture -------------------- */

static int
NativeFuture_init(NativeFutureObject *self, PyObject *args, PyObject *kwargs)
{
    self->lock = PyThread_allocate_lock();
    if (self->lock == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "failed to allocate lock");
        return -1;
    }
    self->event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (self->event == NULL) {
        PyThread_free_lock(self->lock);
        self->lock = NULL;
        PyErr_SetFromWindowsErr(0);
        return -1;
    }
    self->completed = 0;
    self->cancelled = 0;
    self->result = Py_None;
    Py_INCREF(Py_None);
    self->exception = Py_None;
    Py_INCREF(Py_None);
    return 0;
}

static void
NativeFuture_dealloc(NativeFutureObject *self)
{
    if (self->event != NULL) {
        CloseHandle(self->event);
        self->event = NULL;
    }
    if (self->lock != NULL) {
        PyThread_free_lock(self->lock);
        self->lock = NULL;
    }
    Py_XDECREF(self->result);
    Py_XDECREF(self->exception);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
NativeFuture_done(NativeFutureObject *self, PyObject *Py_UNUSED(ignored))
{
    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS
    int completed = self->completed;
    PyThread_release_lock(self->lock);
    if (completed) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject *
NativeFuture_result(NativeFutureObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"timeout", NULL};
    double timeout = -1.0;
    DWORD wait_ms = INFINITE;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|d", kwlist, &timeout)) {
        return NULL;
    }
    if (timeout >= 0.0) {
        if (timeout > 4294967.0) {
            wait_ms = INFINITE;
        } else {
            wait_ms = (DWORD)(timeout * 1000.0);
        }
    }

    DWORD wait_result;

    Py_BEGIN_ALLOW_THREADS
    wait_result = WaitForSingleObject(self->event, wait_ms);
    Py_END_ALLOW_THREADS

    if (wait_result == WAIT_TIMEOUT) {
        PyErr_SetString(PyExc_TimeoutError, "future.result() timeout");
        return NULL;
    } else if (wait_result != WAIT_OBJECT_0) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    if (self->exception != Py_None) {
        PyObject *exc = self->exception;
        Py_INCREF(exc);
        PyThread_release_lock(self->lock);
        PyErr_SetObject(Py_TYPE(exc), exc);
        Py_DECREF(exc);
        return NULL;
    }

    PyObject *res = self->result;
    Py_INCREF(res);
    PyThread_release_lock(self->lock);
    return res;
}

static int
NativeFuture_set_result(NativeFutureObject *self, PyObject *result)
{
    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    if (self->completed) {
        PyThread_release_lock(self->lock);
        PyErr_SetString(PyExc_RuntimeError, "future already completed");
        return -1;
    }
    Py_INCREF(result);
    Py_DECREF(self->result);
    self->result = result;
    self->completed = 1;
    SetEvent(self->event);
    PyThread_release_lock(self->lock);
    return 0;
}

static int
NativeFuture_set_exception(NativeFutureObject *self, PyObject *exception)
{
    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(self->lock, 1);
    Py_END_ALLOW_THREADS

    if (self->completed) {
        PyThread_release_lock(self->lock);
        PyErr_SetString(PyExc_RuntimeError, "future already completed");
        return -1;
    }
    Py_INCREF(exception);
    Py_DECREF(self->exception);
    self->exception = exception;
    self->completed = 1;
    SetEvent(self->event);
    PyThread_release_lock(self->lock);
    return 0;
}

static PyMethodDef NativeFuture_methods[] = {
    {"result", (PyCFunction)NativeFuture_result, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("result(timeout=None)")},
    {"done", (PyCFunction)NativeFuture_done, METH_NOARGS, PyDoc_STR("done() -> bool")},
    {NULL, NULL, 0, NULL}};

static PyTypeObject NativeFutureType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_threadpool.NativeFuture",
    .tp_doc = "Future object for native thread pool",
    .tp_basicsize = sizeof(NativeFutureObject),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)NativeFuture_init,
    .tp_dealloc = (destructor)NativeFuture_dealloc,
    .tp_methods = NativeFuture_methods,
};

/* -------------------- NativeThreadPool -------------------- */

typedef struct {
    NativeThreadPoolObject *pool;
} WorkerContext;

static PyObject *
create_task_tuple(PyObject *callable, PyObject *args, PyObject *kwargs, NativeFutureObject *future)
{
    PyObject *task = PyTuple_New(4);
    if (!task) {
        return NULL;
    }
    Py_INCREF(callable);
    PyTuple_SET_ITEM(task, 0, callable);

    if (args == NULL) {
        args = PyTuple_New(0);
    } else if (!PyTuple_Check(args)) {
        PyErr_SetString(PyExc_TypeError, "args must be tuple");
        Py_DECREF(task);
        return NULL;
    } else {
        Py_INCREF(args);
    }
    PyTuple_SET_ITEM(task, 1, args);

    if (kwargs == NULL) {
        kwargs = PyDict_New();
    } else if (!PyDict_Check(kwargs)) {
        PyErr_SetString(PyExc_TypeError, "kwargs must be dict");
        Py_DECREF(task);
        return NULL;
    } else {
        Py_INCREF(kwargs);
    }
    PyTuple_SET_ITEM(task, 2, kwargs);

    Py_INCREF((PyObject *)future);
    PyTuple_SET_ITEM(task, 3, (PyObject *)future);
    return task;
}

static void
worker_main(void *arg)
{
    NativeThreadPoolObject *pool = (NativeThreadPoolObject *)arg;
    PyGILState_STATE gstate = PyGILState_Ensure();

    while (1) {
        PyObject *task = NULL;
        PyObject *callable = NULL;
        PyObject *args = NULL;
        PyObject *kwargs = NULL;
        NativeFutureObject *future = NULL;
        int should_shutdown = 0;

        PyThread_acquire_lock(pool->queue_lock, 1);
        while (PyList_GET_SIZE(pool->task_queue) == 0 && !pool->shutting_down) {
            PyThread_release_lock(pool->queue_lock);

            Py_BEGIN_ALLOW_THREADS
            WaitForSingleObject(pool->queue_event, INFINITE);
            Py_END_ALLOW_THREADS

            PyThread_acquire_lock(pool->queue_lock, 1);
        }

        if (pool->shutting_down && PyList_GET_SIZE(pool->task_queue) == 0) {
            should_shutdown = 1;
        } else {
            task = PyList_GET_ITEM(pool->task_queue, 0);
            Py_INCREF(task);
            PySequence_DelSlice(pool->task_queue, 0, 1);
        }
        PyThread_release_lock(pool->queue_lock);

        if (should_shutdown) {
            break;
        }

        if (task == NULL) {
            continue;
        }

        callable = PyTuple_GET_ITEM(task, 0);
        args = PyTuple_GET_ITEM(task, 1);
        kwargs = PyTuple_GET_ITEM(task, 2);
        future = (NativeFutureObject *)PyTuple_GET_ITEM(task, 3);

        PyObject *result = PyObject_Call(callable, args, kwargs);
        if (result == NULL) {
            PyObject *exc_type = NULL, *exc_value = NULL, *exc_tb = NULL;
            PyErr_Fetch(&exc_type, &exc_value, &exc_tb);
            if (exc_value == NULL && exc_type != NULL) {
                exc_value = PyObject_CallObject(exc_type, NULL);
            }
            if (exc_value == NULL) {
                exc_value = PyExc_RuntimeError;
                Py_INCREF(exc_value);
            }
            NativeFuture_set_exception(future, exc_value);
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_value);
            Py_XDECREF(exc_tb);
        } else {
            NativeFuture_set_result(future, result);
            Py_DECREF(result);
        }

        Py_DECREF(task);
    }

    PyGILState_Release(gstate);
    Py_DECREF(pool);
    // 使用与 _beginthreadex 对应的结束函数，确保线程句柄正确发信号
    _endthreadex(0);
}

static int
NativeThreadPool_init(NativeThreadPoolObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"max_workers", NULL};
    Py_ssize_t max_workers = 4;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|n", kwlist, &max_workers)) {
        return -1;
    }
    if (max_workers <= 0) {
        max_workers = 1;
    }

    self->queue_lock = PyThread_allocate_lock();
    if (self->queue_lock == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "failed to allocate queue lock");
        return -1;
    }

    self->queue_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (self->queue_event == NULL) {
        PyThread_free_lock(self->queue_lock);
        self->queue_lock = NULL;
        PyErr_SetFromWindowsErr(0);
        return -1;
    }

    self->task_queue = PyList_New(0);
    if (self->task_queue == NULL) {
        CloseHandle(self->queue_event);
        self->queue_event = NULL;
        PyThread_free_lock(self->queue_lock);
        self->queue_lock = NULL;
        return -1;
    }

    self->worker_count = max_workers;
    self->shutting_down = 0;
    self->worker_handles = PyMem_Calloc((size_t)self->worker_count, sizeof(HANDLE));
    if (self->worker_handles == NULL) {
        Py_DECREF(self->task_queue);
        self->task_queue = NULL;
        CloseHandle(self->queue_event);
        self->queue_event = NULL;
        PyThread_free_lock(self->queue_lock);
        self->queue_lock = NULL;
        PyErr_NoMemory();
        return -1;
    }

    for (Py_ssize_t i = 0; i < self->worker_count; ++i) {
        Py_INCREF(self);
        unsigned long thread_id;
        uintptr_t handle = _beginthreadex(NULL, 0, (unsigned (__stdcall *)(void *))worker_main, self, 0, &thread_id);
        if (handle == 0) {
            Py_DECREF(self);
            PyErr_SetFromWindowsErr(0);
            for (Py_ssize_t j = 0; j < i; ++j) {
                if (self->worker_handles[j] != NULL) {
                    CloseHandle(self->worker_handles[j]);
                    self->worker_handles[j] = NULL;
                }
            }
            PyMem_Free(self->worker_handles);
            self->worker_handles = NULL;
            return -1;
        }
        self->worker_handles[i] = (HANDLE)handle;
    }

    return 0;
}

static void
NativeThreadPool_dealloc(NativeThreadPoolObject *self)
{
    if (self->worker_handles != NULL) {
        for (Py_ssize_t i = 0; i < self->worker_count; ++i) {
            if (self->worker_handles[i] != NULL) {
                CloseHandle(self->worker_handles[i]);
                self->worker_handles[i] = NULL;
            }
        }
        PyMem_Free(self->worker_handles);
        self->worker_handles = NULL;
    }
    if (self->queue_lock != NULL) {
        PyThread_free_lock(self->queue_lock);
        self->queue_lock = NULL;
    }
    if (self->queue_event != NULL) {
        CloseHandle(self->queue_event);
        self->queue_event = NULL;
    }
    Py_XDECREF(self->task_queue);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
NativeThreadPool_submit(NativeThreadPoolObject *self, PyObject *args, PyObject *kwargs)
{
    PyObject *callable;
    PyObject *call_args = NULL;
    PyObject *call_kwargs = NULL;

    if (!PyArg_ParseTuple(args, "O|OO", &callable, &call_args, &call_kwargs)) {
        return NULL;
    }

    if (!PyCallable_Check(callable)) {
        PyErr_SetString(PyExc_TypeError, "callable argument must be callable");
        return NULL;
    }

    NativeFutureObject *future = (NativeFutureObject *)PyObject_CallObject((PyObject *)&NativeFutureType, NULL);
    if (future == NULL) {
        return NULL;
    }

    PyObject *task = create_task_tuple(callable, call_args, call_kwargs, future);
    if (task == NULL) {
        Py_DECREF(future);
        return NULL;
    }

    PyThread_acquire_lock(self->queue_lock, 1);
    PyList_Append(self->task_queue, task);
    PyThread_release_lock(self->queue_lock);
    Py_DECREF(task);

    SetEvent(self->queue_event);
    return (PyObject *)future;
}

static PyObject *
NativeThreadPool_shutdown(NativeThreadPoolObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"wait", NULL};
    int wait = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|p", kwlist, &wait)) {
        return NULL;
    }

    PyThread_acquire_lock(self->queue_lock, 1);
    self->shutting_down = 1;
    PyThread_release_lock(self->queue_lock);

    SetEvent(self->queue_event);

    if (wait && self->worker_handles != NULL) {
        for (Py_ssize_t i = 0; i < self->worker_count; ++i) {
            HANDLE handle = self->worker_handles[i];
            if (handle != NULL) {
                WaitForSingleObject(handle, INFINITE);
                CloseHandle(handle);
                self->worker_handles[i] = NULL;
            }
        }
    } else if (self->worker_handles != NULL) {
        for (Py_ssize_t i = 0; i < self->worker_count; ++i) {
            if (self->worker_handles[i] != NULL) {
                CloseHandle(self->worker_handles[i]);
                self->worker_handles[i] = NULL;
            }
        }
    }

    if (self->worker_handles != NULL) {
        PyMem_Free(self->worker_handles);
        self->worker_handles = NULL;
    }

    Py_RETURN_NONE;
}

static PyMethodDef NativeThreadPool_methods[] = {
    {"submit", (PyCFunction)NativeThreadPool_submit, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("submit(callable, *args, **kwargs) -> NativeFuture")},
    {"shutdown", (PyCFunction)NativeThreadPool_shutdown, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("shutdown(wait=True) -> None")},
    {NULL, NULL, 0, NULL}};

static PyTypeObject NativeThreadPoolType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_threadpool.NativeThreadPool",
    .tp_doc = "Simple native thread pool",
    .tp_basicsize = sizeof(NativeThreadPoolObject),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)NativeThreadPool_init,
    .tp_dealloc = (destructor)NativeThreadPool_dealloc,
    .tp_methods = NativeThreadPool_methods,
};

/* -------------------- Module -------------------- */

static PyMethodDef module_methods[] = { {NULL, NULL, 0, NULL} };

static struct PyModuleDef native_threadpool_module = {
    PyModuleDef_HEAD_INIT,
    "_native_threadpool",
    "Native thread pool implementation",
    -1,
    module_methods,
};

PyMODINIT_FUNC
PyInit__native_threadpool(void)
{
    PyObject *m;

    if (PyType_Ready(&NativeThreadPoolType) < 0) {
        return NULL;
    }
    if (PyType_Ready(&NativeFutureType) < 0) {
        return NULL;
    }

    m = PyModule_Create(&native_threadpool_module);
    if (m == NULL) {
        return NULL;
    }

    Py_INCREF(&NativeThreadPoolType);
    if (PyModule_AddObject(m, "NativeThreadPool", (PyObject *)&NativeThreadPoolType) < 0) {
        Py_DECREF(&NativeThreadPoolType);
        Py_DECREF(m);
        return NULL;
    }

    Py_INCREF(&NativeFutureType);
    if (PyModule_AddObject(m, "NativeFuture", (PyObject *)&NativeFutureType) < 0) {
        Py_DECREF(&NativeFutureType);
        Py_DECREF(&NativeThreadPoolType);
        Py_DECREF(m);
        return NULL;
    }

    if (PyModule_AddIntConstant(m, "THREADPOOL_AVAILABLE", 1) < 0) {
        Py_DECREF(&NativeFutureType);
        Py_DECREF(&NativeThreadPoolType);
        Py_DECREF(m);
        return NULL;
    }

    if (PyModule_AddStringConstant(m, "__version__", "0.1.0") < 0) {
        Py_DECREF(&NativeFutureType);
        Py_DECREF(&NativeThreadPoolType);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}

