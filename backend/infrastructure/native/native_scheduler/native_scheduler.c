#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>

typedef struct {
    PyObject *threadpool;
    PyThread_type_lock pending_lock;
    Py_ssize_t pending;
    Py_ssize_t max_workers;
} CategoryContext;

typedef struct {
    PyObject_HEAD
    PyObject *categories;      /* dict: name -> capsule */
    PyObject *threadpool_type; /* NativeThreadPool type */
} NativeSchedulerObject;

static PyTypeObject NativeSchedulerType;
static PyObject *EXECUTE_TASK_FUNC = NULL;

static CategoryContext *
category_context_new(PyObject *threadpool, Py_ssize_t max_workers)
{
    CategoryContext *ctx = PyMem_Calloc(1, sizeof(CategoryContext));
    if (ctx == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    ctx->threadpool = threadpool;
    ctx->pending_lock = PyThread_allocate_lock();
    if (ctx->pending_lock == NULL) {
        PyMem_Free(ctx);
        PyErr_SetString(PyExc_RuntimeError, "failed to allocate scheduler lock");
        return NULL;
    }
    ctx->pending = 0;
    ctx->max_workers = max_workers;
    Py_INCREF(threadpool);
    return ctx;
}

static void
category_context_free(CategoryContext *ctx)
{
    if (ctx == NULL) {
        return;
    }
    Py_XDECREF(ctx->threadpool);
    if (ctx->pending_lock != NULL) {
        PyThread_free_lock(ctx->pending_lock);
        ctx->pending_lock = NULL;
    }
    PyMem_Free(ctx);
}

static void
category_capsule_destructor(PyObject *capsule)
{
    CategoryContext *ctx = PyCapsule_GetPointer(capsule, "native_scheduler.CategoryContext");
    category_context_free(ctx);
}

static CategoryContext *
get_category(NativeSchedulerObject *self, PyObject *name)
{
    PyObject *capsule = PyDict_GetItem(self->categories, name);
    if (capsule == NULL) {
        PyErr_SetString(PyExc_KeyError, "category not registered");
        return NULL;
    }
    return (CategoryContext *)PyCapsule_GetPointer(capsule, "native_scheduler.CategoryContext");
}

/* -------------------- 调度器方法 -------------------- */

static int
NativeScheduler_init(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    PyObject *threadpool_module = NULL;

    self->categories = PyDict_New();
    if (self->categories == NULL) {
        return -1;
    }

    threadpool_module = PyImport_ImportModule("backend.infrastructure.native.native_threadpool");
    if (threadpool_module == NULL) {
        Py_DECREF(self->categories);
        self->categories = NULL;
        return -1;
    }

    self->threadpool_type = PyObject_GetAttrString(threadpool_module, "NativeThreadPool");
    Py_DECREF(threadpool_module);

    if (self->threadpool_type == NULL) {
        Py_XDECREF(self->threadpool_type);
        Py_DECREF(self->categories);
        self->categories = NULL;
        return -1;
    }

    if (EXECUTE_TASK_FUNC == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "scheduler execute function not initialised");
        return -1;
    }
    return 0;
}

static void
NativeScheduler_dealloc(NativeSchedulerObject *self)
{
    if (self->categories != NULL) {
        PyObject *values = PyDict_Values(self->categories);
        if (values != NULL) {
            Py_ssize_t size = PyList_GET_SIZE(values);
            for (Py_ssize_t i = 0; i < size; ++i) {
                PyObject *capsule = PyList_GET_ITEM(values, i);
                /* trigger capsule destructor */
                category_capsule_destructor(capsule);
            }
            Py_DECREF(values);
        }
        Py_DECREF(self->categories);
        self->categories = NULL;
    }

    Py_XDECREF(self->threadpool_type);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
NativeScheduler_register_category(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"name", "queue_capacity", "max_workers", NULL};
    PyObject *name_obj;
    Py_ssize_t queue_capacity = 1024;
    Py_ssize_t max_workers = 4;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|nn", kwlist, &name_obj, &queue_capacity, &max_workers)) {
        return NULL;
    }
    if (!PyUnicode_Check(name_obj)) {
        PyErr_SetString(PyExc_TypeError, "name must be str");
        return NULL;
    }
    if (queue_capacity <= 0) {
        queue_capacity = 1024;
    }
    if (max_workers <= 0) {
        max_workers = 1;
    }

    if (PyDict_Contains(self->categories, name_obj)) {
        PyErr_SetString(PyExc_ValueError, "category already registered");
        return NULL;
    }

    PyObject *threadpool = PyObject_CallFunction(self->threadpool_type, "n", max_workers);
    if (threadpool == NULL) {
        return NULL;
    }

    CategoryContext *ctx = category_context_new(threadpool, max_workers);
    Py_DECREF(threadpool);
    if (ctx == NULL) {
        return NULL;
    }

    PyObject *capsule = PyCapsule_New(ctx, "native_scheduler.CategoryContext", category_capsule_destructor);
    if (capsule == NULL) {
        category_context_free(ctx);
        return NULL;
    }

    if (PyDict_SetItem(self->categories, name_obj, capsule) < 0) {
        Py_DECREF(capsule);
        return NULL;
    }
    Py_DECREF(capsule);

    Py_RETURN_NONE;
}

static PyObject *
NativeScheduler_submit(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"category", "callable", "call_args", "call_kwargs", NULL};
    PyObject *category_name;
    PyObject *callable;
    PyObject *call_args = NULL;
    PyObject *call_kwargs = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|OO", kwlist, &category_name, &callable, &call_args, &call_kwargs)) {
        return NULL;
    }
    if (!PyUnicode_Check(category_name)) {
        PyErr_SetString(PyExc_TypeError, "category must be str");
        return NULL;
    }
    if (!PyCallable_Check(callable)) {
        PyErr_SetString(PyExc_TypeError, "callable must be callable");
        return NULL;
    }

    if (call_args == NULL) {
        call_args = PyTuple_New(0);
    } else if (!PyTuple_Check(call_args)) {
        PyErr_SetString(PyExc_TypeError, "call_args must be tuple");
        return NULL;
    } else {
        Py_INCREF(call_args);
    }

    if (call_kwargs == NULL || call_kwargs == Py_None) {
        call_kwargs = PyDict_New();
    } else if (!PyDict_Check(call_kwargs)) {
        Py_DECREF(call_args);
        PyErr_SetString(PyExc_TypeError, "call_kwargs must be dict");
        return NULL;
    } else {
        Py_INCREF(call_kwargs);
    }

    CategoryContext *ctx = get_category(self, category_name);
    if (ctx == NULL) {
        Py_DECREF(call_args);
        Py_DECREF(call_kwargs);
        return NULL;
    }

    PyThread_acquire_lock(ctx->pending_lock, 1);
    ctx->pending += 1;
    PyThread_release_lock(ctx->pending_lock);

    PyObject *ctx_capsule = PyCapsule_New(ctx, "native_scheduler.CategoryContext", NULL);
    if (ctx_capsule == NULL) {
        Py_DECREF(call_args);
        Py_DECREF(call_kwargs);
        PyThread_acquire_lock(ctx->pending_lock, 1);
        ctx->pending -= 1;
        PyThread_release_lock(ctx->pending_lock);
        return NULL;
    }

    PyObject *worker_args = PyTuple_New(4);
    if (worker_args == NULL) {
        Py_DECREF(ctx_capsule);
        Py_DECREF(call_args);
        Py_DECREF(call_kwargs);
        PyThread_acquire_lock(ctx->pending_lock, 1);
        ctx->pending -= 1;
        PyThread_release_lock(ctx->pending_lock);
        return NULL;
    }

    PyTuple_SET_ITEM(worker_args, 0, ctx_capsule);

    Py_INCREF(callable);
    PyTuple_SET_ITEM(worker_args, 1, callable);

    PyTuple_SET_ITEM(worker_args, 2, call_args);
    PyTuple_SET_ITEM(worker_args, 3, call_kwargs);

    PyObject *future = PyObject_CallMethod(ctx->threadpool, "submit", "OO",
                                           EXECUTE_TASK_FUNC, worker_args);
    Py_DECREF(worker_args);
    Py_DECREF(call_args);
    Py_DECREF(call_kwargs);

    if (future == NULL) {
        PyThread_acquire_lock(ctx->pending_lock, 1);
        ctx->pending -= 1;
        PyThread_release_lock(ctx->pending_lock);
        return NULL;
    }
    return future;
}

static PyObject *
NativeScheduler_stats(NativeSchedulerObject *self, PyObject *Py_UNUSED(ignored))
{
    PyObject *result = PyDict_New();
    if (result == NULL) {
        return NULL;
    }
    PyObject *items = PyDict_Items(self->categories);
    if (items == NULL) {
        Py_DECREF(result);
        return NULL;
    }

    Py_ssize_t size = PyList_GET_SIZE(items);
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject *pair = PyList_GET_ITEM(items, i);
        PyObject *name = PyTuple_GET_ITEM(pair, 0);
        CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(PyTuple_GET_ITEM(pair, 1),
                                                                       "native_scheduler.CategoryContext");
        if (ctx == NULL) {
            Py_DECREF(items);
            Py_DECREF(result);
            return NULL;
        }

        PyThread_acquire_lock(ctx->pending_lock, 1);
        Py_ssize_t pending = ctx->pending;
        PyThread_release_lock(ctx->pending_lock);

        PyObject *pending_obj = PyLong_FromSsize_t(pending);
        if (pending_obj == NULL) {
            Py_DECREF(items);
            Py_DECREF(result);
            return NULL;
        }

        PyObject *entry = Py_BuildValue("{sO,sn}", "queue_size", pending_obj, "max_workers", ctx->max_workers);
        Py_DECREF(pending_obj);
        if (entry == NULL) {
            Py_DECREF(items);
            Py_DECREF(result);
            return NULL;
        }
        if (PyDict_SetItem(result, name, entry) < 0) {
            Py_DECREF(entry);
            Py_DECREF(items);
            Py_DECREF(result);
            return NULL;
        }
        Py_DECREF(entry);
    }

    Py_DECREF(items);
    return result;
}

static PyObject *
NativeScheduler_shutdown(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"wait", NULL};
    int wait = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|p", kwlist, &wait)) {
        return NULL;
    }

    PyObject *values = PyDict_Values(self->categories);
    if (values == NULL) {
        return NULL;
    }
    Py_ssize_t size = PyList_GET_SIZE(values);
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject *capsule = PyList_GET_ITEM(values, i);
        CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(capsule, "native_scheduler.CategoryContext");
        if (ctx == NULL) {
            Py_DECREF(values);
            return NULL;
        }
        PyObject *res = PyObject_CallMethod(ctx->threadpool, "shutdown", "(p)", wait);
        if (res == NULL) {
            Py_DECREF(values);
            return NULL;
        }
        Py_DECREF(res);
    }
    Py_DECREF(values);
    Py_RETURN_NONE;
}

/* -------------------- 模块级函数 -------------------- */

static PyObject *
execute_task(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *ctx_capsule;
    PyObject *callable;
    PyObject *call_args;
    PyObject *call_kwargs;

    if (!PyArg_ParseTuple(args, "OOOO", &ctx_capsule, &callable, &call_args, &call_kwargs)) {
        return NULL;
    }

    CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(ctx_capsule, "native_scheduler.CategoryContext");
    if (ctx == NULL) {
        return NULL;
    }

    PyThread_acquire_lock(ctx->pending_lock, 1);
    if (ctx->pending > 0) {
        ctx->pending -= 1;
    }
    PyThread_release_lock(ctx->pending_lock);

    if (!PyTuple_Check(call_args)) {
        PyErr_SetString(PyExc_TypeError, "call_args must be tuple");
        return NULL;
    }
    if (!PyDict_Check(call_kwargs)) {
        PyErr_SetString(PyExc_TypeError, "call_kwargs must be dict");
        return NULL;
    }

    return PyObject_Call(callable, call_args, call_kwargs);
}

/* -------------------- 类型与模块定义 -------------------- */

static PyMethodDef NativeScheduler_methods[] = {
    {"register_category", (PyCFunction)NativeScheduler_register_category, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("register_category(name, *, queue_capacity=1024, max_workers=4)")},
    {"submit", (PyCFunction)NativeScheduler_submit, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("submit(category, callable, call_args=(), call_kwargs=None) -> Future")},
    {"stats", (PyCFunction)NativeScheduler_stats, METH_NOARGS, PyDoc_STR("stats() -> dict")},
    {"shutdown", (PyCFunction)NativeScheduler_shutdown, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("shutdown(wait=True) -> None")},
    {NULL, NULL, 0, NULL}};

static PyTypeObject NativeSchedulerType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_scheduler.NativeScheduler",
    .tp_doc = "Native scheduler core",
    .tp_basicsize = sizeof(NativeSchedulerObject),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)NativeScheduler_init,
    .tp_dealloc = (destructor)NativeScheduler_dealloc,
    .tp_methods = NativeScheduler_methods,
};

static PyMethodDef module_methods[] = {
    {"_execute_task", (PyCFunction)execute_task, METH_VARARGS, PyDoc_STR("Internal helper")},
    {NULL, NULL, 0, NULL}};

static struct PyModuleDef native_scheduler_module = {
    PyModuleDef_HEAD_INIT,
    "_native_scheduler",
    "Native scheduler module",
    -1,
    module_methods,
};

PyMODINIT_FUNC
PyInit__native_scheduler(void)
{
    PyObject *m;

    if (PyType_Ready(&NativeSchedulerType) < 0) {
        return NULL;
    }

    m = PyModule_Create(&native_scheduler_module);
    if (m == NULL) {
        return NULL;
    }

    Py_INCREF(&NativeSchedulerType);
    if (PyModule_AddObject(m, "NativeScheduler", (PyObject *)&NativeSchedulerType) < 0) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(m);
        return NULL;
    }

    if (PyModule_AddIntConstant(m, "SCHEDULER_AVAILABLE", 1) < 0) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(m);
        return NULL;
    }

    if (PyModule_AddStringConstant(m, "__version__", "0.1.0") < 0) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(m);
        return NULL;
    }

    EXECUTE_TASK_FUNC = PyObject_GetAttrString(m, "_execute_task");
    if (EXECUTE_TASK_FUNC == NULL) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}

