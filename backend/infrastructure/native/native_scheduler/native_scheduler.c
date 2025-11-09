#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>

/* NativeLogBridge declarations */
static PyObject *g_log_bridge_module = NULL;
static PyObject *g_log_from_native_func = NULL;

/* Log level constants matching Python side */
#define NATIVE_LOG_DEBUG 10
#define NATIVE_LOG_INFO 20
#define NATIVE_LOG_WARNING 30
#define NATIVE_LOG_ERROR 40
#define NATIVE_LOG_CRITICAL 50

#define COMPONENT_CORE "backend.native.native_scheduler.core"

/* Logging utility functions */
static void native_log(int level, const char *component, const char *function, int line, const char *message, const char *details) {
    if (!g_log_from_native_func) {
        return;  /* Silent fail if logging not initialized */
    }

    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(g_log_from_native_func, "ississs",
        level, component, function, line, message, details ? details : "");

    if (result) {
        Py_DECREF(result);
    } else {
        /* Log the logging failure, but avoid recursion */
        PyErr_Clear();
    }

    PyGILState_Release(gstate);
}

static void native_log_error(const char *component, const char *function, int line, const char *message, const char *details) {
    native_log(NATIVE_LOG_ERROR, component, function, line, message, details);
}

static void native_log_warning(const char *component, const char *function, int line, const char *message, const char *details) {
    native_log(NATIVE_LOG_WARNING, component, function, line, message, details);
}

static void native_log_info(const char *component, const char *function, int line, const char *message, const char *details) {
    native_log(NATIVE_LOG_INFO, component, function, line, message, details);
}

static void native_log_debug(const char *component, const char *function, int line, const char *message, const char *details) {
    native_log(NATIVE_LOG_DEBUG, component, function, line, message, details);
}

typedef struct {
    PyObject *threadpool;
    PyThread_type_lock pending_lock;
    Py_ssize_t pending;
    Py_ssize_t max_workers;
} CategoryContext;

typedef struct {
    PyObject_HEAD
    PyObject *categories;       /* dict[name] -> capsule */
    PyObject *executor_factory; /* callable(max_workers) -> threadpool */
    int shutting_down;
} NativeSchedulerObject;

static PyTypeObject NativeSchedulerType;
static PyObject *EXECUTE_TASK_FUNC = NULL;
static PyObject *SUBMIT_STR = NULL;
static PyObject *SHUTDOWN_STR = NULL;

/* ------------------------------------------------------------------------- */
/* Helper utilities                                                          */
/* ------------------------------------------------------------------------- */

static void
category_context_free(CategoryContext *ctx)
{
    if (ctx == NULL) {
        return;
    }
    Py_XDECREF(ctx->threadpool);
    if (ctx->pending_lock != NULL) {
        PyThread_free_lock(ctx->pending_lock);
    }
    PyMem_Free(ctx);
}

static CategoryContext *
category_context_new(PyObject *threadpool, Py_ssize_t max_workers)
{
    CategoryContext *ctx = PyMem_Calloc(1, sizeof(CategoryContext));
    if (ctx == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
    ctx->pending_lock = PyThread_allocate_lock();
    if (ctx->pending_lock == NULL) {
        PyMem_Free(ctx);
        PyErr_SetString(PyExc_RuntimeError, "failed to allocate scheduler lock");
        return NULL;
    }
    Py_INCREF(threadpool);
    ctx->threadpool = threadpool;
    ctx->pending = 0;
    ctx->max_workers = max_workers;
    return ctx;
}

static void
category_capsule_destructor(PyObject *capsule)
{
    CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(
        capsule, "native_scheduler.CategoryContext");
    category_context_free(ctx);
}

static CategoryContext *
get_category(NativeSchedulerObject *self, PyObject *name)
{
    PyObject *capsule = PyDict_GetItemWithError(self->categories, name);
    if (capsule == NULL) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_KeyError, "category not registered");
        }
        return NULL;
    }
    return (CategoryContext *)PyCapsule_GetPointer(
        capsule, "native_scheduler.CategoryContext");
}

static int
ensure_not_shutdown(NativeSchedulerObject *self)
{
    if (self->shutting_down) {
        PyErr_SetString(PyExc_RuntimeError, "scheduler is shutting down");
        return -1;
    }
    return 0;
}

/* ------------------------------------------------------------------------- */
/* NativeScheduler type                                                      */
/* ------------------------------------------------------------------------- */

static int
NativeScheduler_init(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"executor_factory", NULL};
    PyObject *factory = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O", kwlist, &factory)) {
        return -1;
    }
    if (!PyCallable_Check(factory)) {
        PyErr_SetString(PyExc_TypeError, "executor_factory must be callable");
        return -1;
    }

    self->categories = PyDict_New();
    if (self->categories == NULL) {
        return -1;
    }

    Py_INCREF(factory);
    self->executor_factory = factory;
    self->shutting_down = 0;

    if (EXECUTE_TASK_FUNC == NULL || SUBMIT_STR == NULL || SHUTDOWN_STR == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "native scheduler module not initialised");
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
                category_capsule_destructor(capsule);
            }
            Py_DECREF(values);
        }
        Py_DECREF(self->categories);
    }
    Py_XDECREF(self->executor_factory);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
NativeScheduler_register_category(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"name", "queue_capacity", "max_workers", NULL};
    PyObject *name_obj = NULL;
    Py_ssize_t queue_capacity = 1024;  /* kept for API compatibility */
    Py_ssize_t max_workers = 4;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|nn", kwlist,
                                     &name_obj, &queue_capacity, &max_workers)) {
        return NULL;
    }
    if (!PyUnicode_Check(name_obj)) {
        PyErr_SetString(PyExc_TypeError, "name must be str");
        return NULL;
    }
    if (max_workers <= 0) {
        max_workers = 1;
    }

    if (ensure_not_shutdown(self) != 0) {
        return NULL;
    }
    if (PyDict_Contains(self->categories, name_obj)) {
        PyErr_SetString(PyExc_ValueError, "category already registered");
        return NULL;
    }

    PyObject *threadpool = PyObject_CallFunction(self->executor_factory, "n", max_workers);
    if (threadpool == NULL) {
        return NULL;
    }

    CategoryContext *ctx = category_context_new(threadpool, max_workers);
    Py_DECREF(threadpool);
    if (ctx == NULL) {
        return NULL;
    }

    PyObject *capsule = PyCapsule_New(ctx, "native_scheduler.CategoryContext",
                                      category_capsule_destructor);
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
    PyObject *category_name = NULL;
    PyObject *callable = NULL;
    PyObject *call_args = NULL;
    PyObject *call_kwargs = NULL;
    PyObject *call_args_owned = NULL;
    PyObject *call_kwargs_owned = NULL;
    PyObject *worker_args = NULL;
    PyObject *future = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|OO:submit", kwlist,
                                     &category_name, &callable, &call_args, &call_kwargs)) {
        native_log_error(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Failed to parse submit arguments", NULL);
        return NULL;
    }
    if (!PyUnicode_Check(category_name)) {
        native_log_error(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Category name must be string", NULL);
        PyErr_SetString(PyExc_TypeError, "category must be str");
        return NULL;
    }
    if (!PyCallable_Check(callable)) {
        native_log_error(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Submitted object is not callable", NULL);
        PyErr_SetString(PyExc_TypeError, "callable must be callable");
        return NULL;
    }

    if (call_args == NULL || call_args == Py_None) {
        call_args_owned = PyTuple_New(0);
    } else if (PyTuple_Check(call_args)) {
        Py_INCREF(call_args);
        call_args_owned = call_args;
    } else {
        PyErr_SetString(PyExc_TypeError, "call_args must be tuple");
        return NULL;
    }
    if (call_args_owned == NULL) {
        return NULL;
    }

    if (call_kwargs == NULL || call_kwargs == Py_None) {
        call_kwargs_owned = PyDict_New();
    } else if (PyDict_Check(call_kwargs)) {
        Py_INCREF(call_kwargs);
        call_kwargs_owned = call_kwargs;
    } else {
        Py_DECREF(call_args_owned);
        PyErr_SetString(PyExc_TypeError, "call_kwargs must be dict");
        return NULL;
    }
    if (call_kwargs_owned == NULL) {
        Py_DECREF(call_args_owned);
        return NULL;
    }

    CategoryContext *ctx = get_category(self, category_name);
    if (ctx == NULL) {
        const char *category_str = PyUnicode_AsUTF8(category_name);
        char error_details[256];
        sprintf(error_details, "Category '%s' not registered", category_str ? category_str : "<invalid>");
        native_log_error(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Category not found", error_details);
        Py_DECREF(call_args_owned);
        Py_DECREF(call_kwargs_owned);
        return NULL;
    }

    PyThread_acquire_lock(ctx->pending_lock, 1);
    ctx->pending += 1;
    Py_ssize_t current_pending = ctx->pending;
    PyThread_release_lock(ctx->pending_lock);

    /* Log successful task submission */
    const char *category_str = PyUnicode_AsUTF8(category_name);
    char submit_details[256];
    sprintf(submit_details, "category='%s', pending=%zd, callable=%s",
            category_str ? category_str : "<unknown>", current_pending, callable->ob_type->tp_name);
    native_log_debug(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Task submitted to scheduler", submit_details);

    PyObject *ctx_capsule = PyCapsule_New(ctx, "native_scheduler.CategoryContext", NULL);
    if (ctx_capsule == NULL) {
        PyThread_acquire_lock(ctx->pending_lock, 1);
        ctx->pending -= 1;
        PyThread_release_lock(ctx->pending_lock);
        Py_DECREF(call_args_owned);
        Py_DECREF(call_kwargs_owned);
        return NULL;
    }

    worker_args = PyTuple_New(4);
    if (worker_args == NULL) {
        Py_DECREF(ctx_capsule);
        PyThread_acquire_lock(ctx->pending_lock, 1);
        ctx->pending -= 1;
        PyThread_release_lock(ctx->pending_lock);
        Py_DECREF(call_args_owned);
        Py_DECREF(call_kwargs_owned);
        return NULL;
    }

    Py_INCREF(callable);
    PyTuple_SET_ITEM(worker_args, 0, ctx_capsule);          /* steals */
    PyTuple_SET_ITEM(worker_args, 1, callable);             /* steals */
    PyTuple_SET_ITEM(worker_args, 2, call_args_owned);      /* steals */
    PyTuple_SET_ITEM(worker_args, 3, call_kwargs_owned);    /* steals */

    future = PyObject_CallMethodObjArgs(ctx->threadpool, SUBMIT_STR,
                                        EXECUTE_TASK_FUNC, worker_args, NULL);
    Py_DECREF(worker_args);

    if (future == NULL) {
        PyThread_acquire_lock(ctx->pending_lock, 1);
        ctx->pending -= 1;
        PyThread_release_lock(ctx->pending_lock);

        const char *category_str = PyUnicode_AsUTF8(category_name);
        char error_details[256];
        sprintf(error_details, "category='%s', callable=%s",
                category_str ? category_str : "<unknown>", callable->ob_type->tp_name);
        native_log_error(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Failed to submit task to thread pool", error_details);
        return NULL;
    }

    /* Log successful task submission to thread pool */
    const char *category_str = PyUnicode_AsUTF8(category_name);
    char success_details[256];
    sprintf(success_details, "category='%s', callable=%s, future=%s",
            category_str ? category_str : "<unknown>", callable->ob_type->tp_name, future->ob_type->tp_name);
    native_log_debug(COMPONENT_CORE, "NativeScheduler_submit", __LINE__, "Task successfully queued for execution", success_details);

    return future;
}

static PyObject *
NativeScheduler_stats(NativeSchedulerObject *self, PyObject *Py_UNUSED(ignored))
{
    PyObject *stats = PyDict_New();
    if (stats == NULL) {
        return NULL;
    }

    PyObject *key = NULL;
    PyObject *value = NULL;
    Py_ssize_t pos = 0;

    while (PyDict_Next(self->categories, &pos, &key, &value)) {
        CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(
            value, "native_scheduler.CategoryContext");
        if (ctx == NULL) {
            Py_DECREF(stats);
            return NULL;
        }

        PyObject *category_stats = PyDict_New();
        if (category_stats == NULL) {
            Py_DECREF(stats);
            return NULL;
        }

        PyObject *pending = PyLong_FromSsize_t(ctx->pending);
        PyObject *queue_size = PyLong_FromSsize_t(ctx->pending);
        PyObject *max_workers = PyLong_FromSsize_t(ctx->max_workers);

        if (pending == NULL || queue_size == NULL || max_workers == NULL ||
            PyDict_SetItemString(category_stats, "pending", pending) < 0 ||
            PyDict_SetItemString(category_stats, "queue_size", queue_size) < 0 ||
            PyDict_SetItemString(category_stats, "max_workers", max_workers) < 0) {
            Py_XDECREF(pending);
            Py_XDECREF(queue_size);
            Py_XDECREF(max_workers);
            Py_DECREF(category_stats);
            Py_DECREF(stats);
            return NULL;
        }

        Py_DECREF(pending);
        Py_DECREF(queue_size);
        Py_DECREF(max_workers);

        if (PyDict_SetItem(stats, key, category_stats) < 0) {
            Py_DECREF(category_stats);
            Py_DECREF(stats);
            return NULL;
        }
        Py_DECREF(category_stats);
    }

    return stats;
}

static PyObject *
NativeScheduler_shutdown(NativeSchedulerObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"wait", NULL};
    int wait = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|p:shutdown", kwlist, &wait)) {
        native_log_error(COMPONENT_CORE, "NativeScheduler_shutdown", __LINE__, "Failed to parse shutdown arguments", NULL);
        return NULL;
    }

    char shutdown_details[256];
    sprintf(shutdown_details, "wait=%d", wait);
    native_log_info(COMPONENT_CORE, "NativeScheduler_shutdown", __LINE__, "Shutting down scheduler", shutdown_details);

    if (self->shutting_down) {
        native_log_warning(COMPONENT_CORE, "NativeScheduler_shutdown", __LINE__, "Scheduler already shutting down", NULL);
        Py_RETURN_NONE;
    }
    self->shutting_down = 1;

    PyObject *items = PyDict_Items(self->categories);
    if (items == NULL) {
        return NULL;
    }

    Py_ssize_t size = PyList_GET_SIZE(items);
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject *pair = PyList_GET_ITEM(items, i);
        PyObject *value = PyTuple_GET_ITEM(pair, 1);
        CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(
            value, "native_scheduler.CategoryContext");
        if (ctx == NULL) {
            PyErr_Clear();
            continue;
        }

        PyObject *result = PyObject_CallMethodObjArgs(
            ctx->threadpool, SHUTDOWN_STR, wait ? Py_True : Py_False, NULL);
        if (result == NULL) {
            PyErr_Clear();
        } else {
            Py_DECREF(result);
        }

        if (PyCapsule_SetDestructor(value, NULL) != 0) {
            PyErr_Clear();
        }
        category_context_free(ctx);
    }

    Py_DECREF(items);
    PyDict_Clear(self->categories);
    Py_RETURN_NONE;
}

/* ------------------------------------------------------------------------- */
/* Worker trampoline                                                         */
/* ------------------------------------------------------------------------- */

static PyObject *
execute_task(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *ctx_capsule = NULL;
    PyObject *callable = NULL;
    PyObject *call_args = NULL;
    PyObject *call_kwargs = NULL;

    if (!PyArg_ParseTuple(args, "OOOO", &ctx_capsule, &callable, &call_args, &call_kwargs)) {
        PyErr_Print();
        return NULL;
    }

    CategoryContext *ctx = (CategoryContext *)PyCapsule_GetPointer(
        ctx_capsule, "native_scheduler.CategoryContext");
    if (ctx == NULL) {
        PyErr_Print();
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

    /* Log task execution start */
    char exec_start_details[256];
    sprintf(exec_start_details, "callable=%s, args_count=%zd",
            callable->ob_type->tp_name, PyTuple_GET_SIZE(call_args));
    native_log_debug(COMPONENT_CORE, "execute_task", __LINE__, "Starting task execution", exec_start_details);

    PyObject *result = PyObject_Call(callable, call_args, call_kwargs);
    if (result == NULL) {
        /* Task execution failed */
        PyObject *exc_type = NULL, *exc_value = NULL, *exc_tb = NULL;
        PyErr_Fetch(&exc_type, &exc_value, &exc_tb);

        PyObject *exc_str = PyObject_Str(exc_value);
        const char *exc_msg = exc_str ? PyUnicode_AsUTF8(exc_str) : "Unknown exception";
        char exec_error_details[512];
        sprintf(exec_error_details, "callable=%s, exception=%s",
                callable->ob_type->tp_name, exc_msg);
        native_log_error(COMPONENT_CORE, "execute_task", __LINE__, "Task execution failed", exec_error_details);
        Py_XDECREF(exc_str);

        PyErr_Restore(exc_type, exc_value, exc_tb);
    } else {
        /* Task execution succeeded */
        char exec_success_details[256];
        sprintf(exec_success_details, "callable=%s, result_type=%s",
                callable->ob_type->tp_name, result->ob_type->tp_name);
        native_log_debug(COMPONENT_CORE, "execute_task", __LINE__, "Task execution completed successfully", exec_success_details);
    }
    return result;
}

/* ------------------------------------------------------------------------- */
/* Type definitions                                                          */
/* ------------------------------------------------------------------------- */

static PyMethodDef NativeScheduler_methods[] = {
    {"register_category", (PyCFunction)NativeScheduler_register_category,
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("register_category(name, *, queue_capacity=1024, max_workers=4)")},
    {"submit", (PyCFunction)NativeScheduler_submit,
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("submit(category, callable, call_args=(), call_kwargs=None)")},
    {"stats", (PyCFunction)NativeScheduler_stats, METH_NOARGS,
     PyDoc_STR("Return scheduler statistics")},
    {"shutdown", (PyCFunction)NativeScheduler_shutdown,
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("shutdown(wait=True)")},
    {NULL, NULL, 0, NULL}};

static PyObject *
NativeScheduler_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    NativeSchedulerObject *self = (NativeSchedulerObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->categories = NULL;
        self->executor_factory = NULL;
        self->shutting_down = 0;
    }
    return (PyObject *)self;
}

static PyTypeObject NativeSchedulerType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_scheduler.NativeScheduler",
    .tp_doc = "Native scheduler core",
    .tp_basicsize = sizeof(NativeSchedulerObject),
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = NativeScheduler_new,
    .tp_init = (initproc)NativeScheduler_init,
    .tp_dealloc = (destructor)NativeScheduler_dealloc,
    .tp_methods = NativeScheduler_methods,
};

static PyMethodDef module_methods[] = {
    {"_execute_task", (PyCFunction)execute_task, METH_VARARGS, PyDoc_STR("Internal executor trampoline")},
    {NULL, NULL, 0, NULL}};

static void
_native_scheduler_cleanup(void)
{
    /* Clean up logging bridge references */
    Py_XDECREF(g_log_bridge_module);
    Py_XDECREF(g_log_from_native_func);
    g_log_bridge_module = NULL;
    g_log_from_native_func = NULL;

    /* Clean up module-level references */
    Py_XDECREF(EXECUTE_TASK_FUNC);
    Py_XDECREF(SUBMIT_STR);
    Py_XDECREF(SHUTDOWN_STR);
    EXECUTE_TASK_FUNC = NULL;
    SUBMIT_STR = NULL;
    SHUTDOWN_STR = NULL;
}

static struct PyModuleDef native_scheduler_module = {
    PyModuleDef_HEAD_INIT,
    "_native_scheduler",
    "Native scheduler module",
    -1,
    module_methods,
    NULL,  /* m_slots */
    NULL,  /* m_traverse */
    NULL,  /* m_clear */
    _native_scheduler_cleanup,  /* m_free */
};

PyMODINIT_FUNC
PyInit__native_scheduler(void)
{
    PyObject *module = NULL;

    /* Initialize logging bridge */
    g_log_bridge_module = PyImport_ImportModule("backend.infrastructure.native.logging_bridge");
    if (g_log_bridge_module != NULL) {
        g_log_from_native_func = PyObject_GetAttrString(g_log_bridge_module, "log_from_native");
        if (g_log_from_native_func == NULL) {
            Py_DECREF(g_log_bridge_module);
            g_log_bridge_module = NULL;
        }
    }

    if (g_log_bridge_module != NULL && g_log_from_native_func != NULL) {
        native_log_info(COMPONENT_CORE, "PyInit__native_scheduler", __LINE__, "Logging bridge initialized successfully", NULL);
    } else {
        /* Logging bridge not available, continue without logging */
        Py_XDECREF(g_log_bridge_module);
        Py_XDECREF(g_log_from_native_func);
        g_log_bridge_module = NULL;
        g_log_from_native_func = NULL;
    }

    if (PyType_Ready(&NativeSchedulerType) < 0) {
        Py_XDECREF(g_log_bridge_module);
        Py_XDECREF(g_log_from_native_func);
        g_log_bridge_module = NULL;
        g_log_from_native_func = NULL;
        return NULL;
    }

    module = PyModule_Create(&native_scheduler_module);
    if (module == NULL) {
        Py_XDECREF(g_log_bridge_module);
        Py_XDECREF(g_log_from_native_func);
        g_log_bridge_module = NULL;
        g_log_from_native_func = NULL;
        return NULL;
    }

    Py_INCREF(&NativeSchedulerType);
    if (PyModule_AddObject(module, "NativeScheduler", (PyObject *)&NativeSchedulerType) < 0) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(module);
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "SCHEDULER_AVAILABLE", 1) < 0) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(module);
        return NULL;
    }
    if (PyModule_AddStringConstant(module, "__version__", "1.0.0") < 0) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(module);
        return NULL;
    }

    EXECUTE_TASK_FUNC = PyObject_GetAttrString(module, "_execute_task");
    if (EXECUTE_TASK_FUNC == NULL) {
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(module);
        return NULL;
    }

    SUBMIT_STR = PyUnicode_FromString("submit");
    if (SUBMIT_STR == NULL) {
        Py_DECREF(EXECUTE_TASK_FUNC);
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(module);
        return NULL;
    }

    SHUTDOWN_STR = PyUnicode_FromString("shutdown");
    if (SHUTDOWN_STR == NULL) {
        Py_DECREF(SUBMIT_STR);
        Py_DECREF(EXECUTE_TASK_FUNC);
        Py_DECREF(&NativeSchedulerType);
        Py_DECREF(module);
        return NULL;
    }

    return module;
}

