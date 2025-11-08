/* -*- coding: utf-8 -*- */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

/*
 * pipeline.c - 高性能日志原生缓冲区
 *
 * 功能特性：
 * 1. 支持批量阈值与定时触发的自动刷新。
 * 2. 内置重复日志压缩 `_repeat` 统计。
 * 3. 提供回调管线：flush 时先写入 SQLite（可选），再回调 Python 兜底处理。
 * 4. 线程安全，支持跨线程推送。
 */

#include <structmember.h>
#include <pythread.h>

#if defined(_WIN32)
#include <windows.h>
#endif
#if !defined(_WIN32)
#include <time.h>
#include <sys/time.h>
#endif

typedef struct {
    PyObject_HEAD
    PyObject *records;           /* 待刷写的列表 */
    PyObject *last_record;       /* 最近一次写入的记录 */
    PyObject *last_fingerprint;  /* 最近一次写入的指纹，用于重复压缩 */

    PyThread_type_lock lock;     /* 线程锁 */

    Py_ssize_t batch_size;       /* 批量刷写阈值 */
    double flush_ms;             /* 定时刷写间隔（毫秒） */
    double last_flush_at;        /* 上次刷写时间（毫秒） */

    PyObject *fallback;          /* Python 兜底回调 */
    PyObject *event_callback;    /* 事件桥接回调（可选） */

    PyObject *sqlite_path;       /* SQLite 路径（str 或 None） */
    PyObject *sqlite_conn;       /* SQLite 连接对象 */
    PyObject *sqlite_cursor;     /* SQLite cursor */
    PyObject *sqlite_insert_sql; /* INSERT 语句缓存 */

    Py_ssize_t total_pushed;
    Py_ssize_t total_flushed;
    Py_ssize_t total_flush_calls;
    Py_ssize_t total_fallback_errors;
    Py_ssize_t total_sqlite_errors;

    int closed;
} PipelineObject;

/* -------------------- 工具函数 -------------------- */

static double
now_monotonic_ms(void)
{
#if defined(_WIN32)
    static double freq = 0.0;
    LARGE_INTEGER counter;
    LARGE_INTEGER li_freq;

    if (freq == 0.0) {
        if (!QueryPerformanceFrequency(&li_freq) || li_freq.QuadPart == 0) {
            freq = 1000.0;
        } else {
            freq = (double)li_freq.QuadPart;
        }
    }

    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart * 1000.0 / freq;
#elif defined(CLOCK_MONOTONIC)
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
        return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
    }
#else
    struct timeval tv;
    if (gettimeofday(&tv, NULL) == 0) {
        return (double)tv.tv_sec * 1000.0 + (double)tv.tv_usec / 1000.0;
    }
    return 0.0;
#endif
}

static PyObject *
build_fingerprint(PyObject *record)
{
    PyObject *level = PyDict_GetItemString(record, "level");
    PyObject *message = PyDict_GetItemString(record, "message");
    PyObject *module = PyDict_GetItemString(record, "module");
    PyObject *logger_name = PyDict_GetItemString(record, "logger_name");

    if (!level) level = Py_None;
    if (!message) message = Py_None;
    if (!module) module = Py_None;
    if (!logger_name) logger_name = Py_None;

    return PyTuple_Pack(4, level, message, module, logger_name);
}

static int
ensure_sqlite(PipelineObject *self)
{
    if (!self->sqlite_path || self->sqlite_path == Py_None) {
        return 0;
    }

    if (self->sqlite_conn && self->sqlite_cursor && self->sqlite_insert_sql) {
        return 0;
    }

    PyObject *sqlite3 = PyImport_ImportModule("sqlite3");
    if (!sqlite3) {
        self->total_sqlite_errors += 1;
        return -1;
    }

    PyObject *connect = PyObject_GetAttrString(sqlite3, "connect");
    Py_DECREF(sqlite3);
    if (!connect) {
        self->total_sqlite_errors += 1;
        return -1;
    }

    PyObject *args = PyTuple_Pack(1, self->sqlite_path);
    PyObject *kwargs = Py_BuildValue("{s:O}", "check_same_thread", Py_False);
    PyObject *conn = PyObject_Call(connect, args, kwargs);
    Py_DECREF(connect);
    Py_DECREF(args);
    Py_DECREF(kwargs);

    if (!conn) {
        self->total_sqlite_errors += 1;
        return -1;
    }

    PyObject *cursor_method = PyObject_GetAttrString(conn, "cursor");
    if (!cursor_method) {
        Py_DECREF(conn);
        self->total_sqlite_errors += 1;
        return -1;
    }

    PyObject *cursor = PyObject_CallNoArgs(cursor_method);
    Py_DECREF(cursor_method);
    if (!cursor) {
        Py_DECREF(conn);
        self->total_sqlite_errors += 1;
        return -1;
    }

    PyObject *sql = PyUnicode_FromString(
        "INSERT INTO system_logs "
        "(timestamp, level, module, message, extra) "
        "VALUES (:timestamp, :level, :module, :message, :extra)"
    );
    if (!sql) {
        Py_DECREF(cursor);
        Py_DECREF(conn);
        self->total_sqlite_errors += 1;
        return -1;
    }

    self->sqlite_conn = conn;
    self->sqlite_cursor = cursor;
    self->sqlite_insert_sql = sql;
    return 0;
}

static void
reset_last_record(PipelineObject *self)
{
    Py_XDECREF(self->last_record);
    self->last_record = NULL;
    Py_XDECREF(self->last_fingerprint);
    self->last_fingerprint = NULL;
}

static int
append_record_locked(PipelineObject *self, PyObject *record)
{
    PyObject *record_copy = PyDict_Copy(record);
    if (!record_copy) {
        return -1;
    }

    PyObject *fingerprint = build_fingerprint(record_copy);
    if (!fingerprint) {
        Py_DECREF(record_copy);
        return -1;
    }

    int merged = 0;
    if (self->last_record && self->last_fingerprint) {
        int same = PyObject_RichCompareBool(self->last_fingerprint, fingerprint, Py_EQ);
        if (same == 1) {
            PyObject *repeat_obj = PyDict_GetItemString(self->last_record, "_repeat");
            long repeat = 1;
            if (repeat_obj) {
                repeat = PyLong_AsLong(repeat_obj);
                if (repeat < 1) {
                    repeat = 1;
                }
            }

            PyObject *new_repeat = PyLong_FromLong(repeat + 1);
            if (!new_repeat) {
                Py_DECREF(fingerprint);
                Py_DECREF(record_copy);
                return -1;
            }
            if (PyDict_SetItemString(self->last_record, "_repeat", new_repeat) < 0) {
                Py_DECREF(new_repeat);
                Py_DECREF(fingerprint);
                Py_DECREF(record_copy);
                return -1;
            }
            Py_DECREF(new_repeat);
            merged = 1;
        } else if (same < 0) {
            Py_DECREF(fingerprint);
            Py_DECREF(record_copy);
            return -1;
        }
    }

    if (!merged) {
        PyObject *repeat_one = PyLong_FromLong(1);
        if (!repeat_one) {
            Py_DECREF(fingerprint);
            Py_DECREF(record_copy);
            return -1;
        }
        if (PyDict_SetItemString(record_copy, "_repeat", repeat_one) < 0) {
            Py_DECREF(repeat_one);
            Py_DECREF(fingerprint);
            Py_DECREF(record_copy);
            return -1;
        }
        Py_DECREF(repeat_one);

        if (PyList_Append(self->records, record_copy) < 0) {
            Py_DECREF(fingerprint);
            Py_DECREF(record_copy);
            return -1;
        }

        reset_last_record(self);
        self->last_record = record_copy;
        Py_INCREF(self->last_record);
        self->last_fingerprint = fingerprint;
        Py_INCREF(self->last_fingerprint);
    }

    Py_DECREF(fingerprint);
    Py_DECREF(record_copy);
    return 0;
}

static PyObject *
collect_batch_locked(PipelineObject *self)
{
    PyObject *new_list = PyList_New(0);
    if (!new_list) {
        return NULL;
    }

    PyObject *batch = self->records;
    self->records = new_list;
    reset_last_record(self);
    self->last_flush_at = now_monotonic_ms();

    return batch;
}

static int
requeue_batch_locked(PipelineObject *self, PyObject *batch)
{
    Py_ssize_t size = PyList_GET_SIZE(batch);
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject *item = PyList_GET_ITEM(batch, i);
        Py_INCREF(item);
        if (PyList_Append(self->records, item) < 0) {
            Py_DECREF(item);
            return -1;
        }
        Py_DECREF(item);
    }

    if (size > 0) {
        PyObject *tail = PyList_GET_ITEM(self->records, PyList_GET_SIZE(self->records) - 1);
        Py_INCREF(tail);
        reset_last_record(self);
        self->last_record = tail;
        PyObject *fp = build_fingerprint(tail);
        if (fp) {
            self->last_fingerprint = fp;
        }
    }

    return 0;
}

static int
flush_to_sqlite(PipelineObject *self, PyObject *batch)
{
    if (!self->sqlite_path || self->sqlite_path == Py_None) {
        return 0;
    }

    if (ensure_sqlite(self) < 0) {
        return -1;
    }

    Py_ssize_t size = PyList_GET_SIZE(batch);
    if (size == 0) {
        return 0;
    }

    PyObject *executemany = PyObject_GetAttrString(self->sqlite_cursor, "executemany");
    if (!executemany) {
        self->total_sqlite_errors += 1;
        return -1;
    }

    PyObject *args = PyTuple_Pack(2, self->sqlite_insert_sql, batch);
    if (!args) {
        Py_DECREF(executemany);
        return -1;
    }

    PyObject *result = PyObject_Call(executemany, args, NULL);
    Py_DECREF(executemany);
    Py_DECREF(args);

    if (!result) {
        self->total_sqlite_errors += 1;
        return -1;
    }
    Py_DECREF(result);

    PyObject *commit = PyObject_GetAttrString(self->sqlite_conn, "commit");
    if (!commit) {
        self->total_sqlite_errors += 1;
        return -1;
    }
    PyObject *commit_result = PyObject_CallNoArgs(commit);
    Py_DECREF(commit);
    if (!commit_result) {
        self->total_sqlite_errors += 1;
        return -1;
    }
    Py_DECREF(commit_result);
    return 0;
}

static int
emit_batch(PipelineObject *self, PyObject *batch, int *fallback_failed)
{
    if (fallback_failed) {
        *fallback_failed = 0;
    }

    if (!batch || PyList_GET_SIZE(batch) == 0) {
        return 0;
    }

    if (flush_to_sqlite(self, batch) < 0) {
        return -1;
    }

    if (self->fallback && self->fallback != Py_None) {
        PyObject *args = PyTuple_Pack(1, batch);
        if (!args) {
            return -1;
        }
        PyObject *result = PyObject_Call(self->fallback, args, NULL);
        Py_DECREF(args);
        if (!result) {
            if (fallback_failed) {
                *fallback_failed = 1;
            }
            return -1;
        }
        Py_DECREF(result);
    }

    if (self->event_callback && self->event_callback != Py_None) {
        PyObject *args = PyTuple_Pack(1, batch);
        if (args) {
            PyObject *res = PyObject_Call(self->event_callback, args, NULL);
            Py_DECREF(args);
            if (!res) {
                PyErr_Clear();
            } else {
                Py_DECREF(res);
            }
        }
    }

    return 0;
}

/* -------------------- Pipeline 方法实现 -------------------- */

static int
Pipeline_init(PipelineObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {
        "batch_size",
        "flush_ms",
        "fallback",
        "event_callback",
        "sqlite_path",
        NULL
    };

    Py_ssize_t batch_size = 128;
    double flush_ms = 2000.0;
    PyObject *fallback = Py_None;
    PyObject *event_callback = Py_None;
    PyObject *sqlite_path = Py_None;

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "|ndOOO",
            kwlist,
            &batch_size,
            &flush_ms,
            &fallback,
            &event_callback,
            &sqlite_path)) {
        return -1;
    }

    if (batch_size <= 0) {
        PyErr_SetString(PyExc_ValueError, "batch_size must be greater than 0");
        return -1;
    }
    if (flush_ms < 0.0) {
        PyErr_SetString(PyExc_ValueError, "flush_ms must be non-negative");
        return -1;
    }

    self->records = PyList_New(0);
    if (!self->records) {
        return -1;
    }
    self->last_record = NULL;
    self->last_fingerprint = NULL;

    self->lock = PyThread_allocate_lock();
    if (!self->lock) {
        PyErr_SetString(PyExc_RuntimeError, "failed to create pipeline lock");
        return -1;
    }

    Py_INCREF(fallback);
    self->fallback = fallback;
    Py_INCREF(event_callback);
    self->event_callback = event_callback;
    Py_INCREF(sqlite_path);
    self->sqlite_path = sqlite_path;
    self->sqlite_conn = NULL;
    self->sqlite_cursor = NULL;
    self->sqlite_insert_sql = NULL;

    self->batch_size = batch_size;
    self->flush_ms = flush_ms;
    self->last_flush_at = now_monotonic_ms();

    self->total_pushed = 0;
    self->total_flushed = 0;
    self->total_flush_calls = 0;
    self->total_fallback_errors = 0;
    self->total_sqlite_errors = 0;
    self->closed = 0;

    return 0;
}

static int
Pipeline_traverse(PipelineObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->records);
    Py_VISIT(self->last_record);
    Py_VISIT(self->last_fingerprint);
    Py_VISIT(self->fallback);
    Py_VISIT(self->event_callback);
    Py_VISIT(self->sqlite_path);
    Py_VISIT(self->sqlite_conn);
    Py_VISIT(self->sqlite_cursor);
    Py_VISIT(self->sqlite_insert_sql);
    return 0;
}

static int
Pipeline_clear(PipelineObject *self)
{
    Py_CLEAR(self->records);
    Py_CLEAR(self->last_record);
    Py_CLEAR(self->last_fingerprint);
    Py_CLEAR(self->fallback);
    Py_CLEAR(self->event_callback);
    Py_CLEAR(self->sqlite_path);
    Py_CLEAR(self->sqlite_conn);
    Py_CLEAR(self->sqlite_cursor);
    Py_CLEAR(self->sqlite_insert_sql);
    return 0;
}

static void
Pipeline_dealloc(PipelineObject *self)
{
    Pipeline_clear(self);
    if (self->lock) {
        PyThread_free_lock(self->lock);
        self->lock = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
Pipeline_push(PipelineObject *self, PyObject *args)
{
    PyObject *record;
    if (!PyArg_ParseTuple(args, "O!", &PyDict_Type, &record)) {
        return NULL;
    }

    if (self->closed) {
        PyErr_SetString(PyExc_RuntimeError, "pipeline already closed");
        return NULL;
    }

    double now = now_monotonic_ms();
    int should_flush = 0;
    Py_ssize_t pending = 0;

    PyThread_acquire_lock(self->lock, 1);
    if (append_record_locked(self, record) < 0) {
        PyThread_release_lock(self->lock);
        return NULL;
    }
    self->total_pushed += 1;

    pending = PyList_GET_SIZE(self->records);
    if (pending >= self->batch_size) {
        should_flush = 1;
    } else if (self->flush_ms > 0.0 && pending > 0 &&
               (now - self->last_flush_at) >= self->flush_ms) {
        should_flush = 1;
    }
    PyThread_release_lock(self->lock);

    if (should_flush) {
        PyObject *result = PyObject_CallMethod((PyObject *)self, "flush", NULL);
        if (!result) {
            return NULL;
        }
        Py_DECREF(result);
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

static PyObject *
Pipeline_take_batch(PipelineObject *self, PyObject *Py_UNUSED(ignored))
{
    if (self->closed) {
        PyErr_SetString(PyExc_RuntimeError, "pipeline already closed");
        return NULL;
    }

    PyObject *batch = NULL;
    PyThread_acquire_lock(self->lock, 1);
    batch = collect_batch_locked(self);
    if (!batch) {
        PyThread_release_lock(self->lock);
        return NULL;
    }
    PyThread_release_lock(self->lock);
    return batch;
}

static PyObject *
Pipeline_pending(PipelineObject *self, PyObject *Py_UNUSED(ignored))
{
    Py_ssize_t pending = 0;
    PyThread_acquire_lock(self->lock, 1);
    pending = PyList_GET_SIZE(self->records);
    PyThread_release_lock(self->lock);
    return PyLong_FromSsize_t(pending);
}

static PyObject *
Pipeline_stats(PipelineObject *self, PyObject *Py_UNUSED(ignored))
{
    PyObject *stats = PyDict_New();
    if (!stats) {
        return NULL;
    }

    PyObject *value = PyLong_FromSsize_t(self->total_pushed);
    if (value) {
        PyDict_SetItemString(stats, "total_pushed", value);
        Py_DECREF(value);
    }

    value = PyLong_FromSsize_t(self->total_flushed);
    if (value) {
        PyDict_SetItemString(stats, "total_flushed", value);
        Py_DECREF(value);
    }

    value = PyLong_FromSsize_t(self->total_flush_calls);
    if (value) {
        PyDict_SetItemString(stats, "total_flush_calls", value);
        Py_DECREF(value);
    }

    value = PyLong_FromSsize_t(self->total_fallback_errors);
    if (value) {
        PyDict_SetItemString(stats, "fallback_errors", value);
        Py_DECREF(value);
    }

    value = PyLong_FromSsize_t(self->total_sqlite_errors);
    if (value) {
        PyDict_SetItemString(stats, "sqlite_errors", value);
        Py_DECREF(value);
    }

    value = PyLong_FromSsize_t(self->batch_size);
    if (value) {
        PyDict_SetItemString(stats, "batch_size", value);
        Py_DECREF(value);
    }

    value = PyFloat_FromDouble(self->flush_ms);
    if (value) {
        PyDict_SetItemString(stats, "flush_ms", value);
        Py_DECREF(value);
    }

    value = PyBool_FromLong(self->closed);
    if (value) {
        PyDict_SetItemString(stats, "closed", value);
        Py_DECREF(value);
    }

    return stats;
}

static PyObject *
Pipeline_flush_internal(PipelineObject *self, int force)
{
    if (self->closed && !force) {
        Py_RETURN_FALSE;
    }

    PyObject *batch = NULL;
    Py_ssize_t batch_size = 0;
    PyThread_acquire_lock(self->lock, 1);
    batch_size = PyList_GET_SIZE(self->records);
    if (batch_size == 0) {
        PyThread_release_lock(self->lock);
        Py_RETURN_FALSE;
    }

    batch = collect_batch_locked(self);
    if (!batch) {
        PyThread_release_lock(self->lock);
        return NULL;
    }
    PyThread_release_lock(self->lock);

    int fallback_failed = 0;
    int emit_status = emit_batch(self, batch, &fallback_failed);
    if (emit_status < 0) {
        PyThread_acquire_lock(self->lock, 1);
        requeue_batch_locked(self, batch);
        PyThread_release_lock(self->lock);
        if (fallback_failed) {
            self->total_fallback_errors += 1;
        }
        Py_DECREF(batch);
        return NULL;
    }

    self->total_flushed += PyList_GET_SIZE(batch);
    self->total_flush_calls += 1;
    Py_DECREF(batch);
    Py_RETURN_TRUE;
}

static PyObject *
Pipeline_flush(PipelineObject *self, PyObject *args, PyObject *kwargs)
{
    int force = 0;
    static char *kwlist[] = {"force", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|p", kwlist, &force)) {
        return NULL;
        }

    return Pipeline_flush_internal(self, force);
}

static PyObject *
Pipeline_flush_and_close(PipelineObject *self, PyObject *Py_UNUSED(ignored))
{
    if (self->closed) {
        Py_RETURN_FALSE;
    }

    self->closed = 1;
    PyObject *result = Pipeline_flush_internal(self, 1);
    if (!result) {
        return NULL;
    }
    Py_DECREF(result);

    PyThread_acquire_lock(self->lock, 1);
    Py_ssize_t remaining = PyList_GET_SIZE(self->records);
    if (remaining > 0) {
        PyThread_release_lock(self->lock);
        PyThread_acquire_lock(self->lock, 1);
        PyObject *batch = collect_batch_locked(self);
        PyThread_release_lock(self->lock);
        if (batch) {
            Py_DECREF(batch);
        }
    } else {
        PyThread_release_lock(self->lock);
    }

    Py_RETURN_TRUE;
}

static PyObject *
Pipeline_set_fallback(PipelineObject *self, PyObject *args)
{
    PyObject *fallback = NULL;
    if (!PyArg_ParseTuple(args, "O", &fallback)) {
        return NULL;
    }
    Py_INCREF(fallback);
    PyThread_acquire_lock(self->lock, 1);
    PyObject *old = self->fallback;
    self->fallback = fallback;
    PyThread_release_lock(self->lock);
    Py_XDECREF(old);
    Py_RETURN_NONE;
}

static PyObject *
Pipeline_configure(PipelineObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"batch_size", "flush_ms", NULL};
    Py_ssize_t batch_size = self->batch_size;
    double flush_ms = self->flush_ms;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|nd", kwlist, &batch_size, &flush_ms)) {
        return NULL;
    }

    if (batch_size <= 0) {
        PyErr_SetString(PyExc_ValueError, "batch_size must be greater than 0");
        return NULL;
    }
    if (flush_ms < 0.0) {
        PyErr_SetString(PyExc_ValueError, "flush_ms must be non-negative");
        return NULL;
    }

    PyThread_acquire_lock(self->lock, 1);
    self->batch_size = batch_size;
    self->flush_ms = flush_ms;
    PyThread_release_lock(self->lock);
    Py_RETURN_NONE;
}

static PyObject *
Pipeline_sqlite_path(PipelineObject *self, PyObject *Py_UNUSED(ignored))
{
    if (!self->sqlite_path) {
        Py_RETURN_NONE;
    }
    Py_INCREF(self->sqlite_path);
    return self->sqlite_path;
}

static PyMemberDef Pipeline_members[] = {
    {"batch_size", T_PYSSIZET, offsetof(PipelineObject, batch_size), READONLY, "当前批量阈值"},
    {"flush_ms", T_DOUBLE, offsetof(PipelineObject, flush_ms), READONLY, "刷新间隔（毫秒）"},
    {"closed", T_INT, offsetof(PipelineObject, closed), READONLY, "是否已关闭"},
    {NULL},
};

static PyMethodDef Pipeline_methods[] = {
    {"push", (PyCFunction)Pipeline_push, METH_VARARGS, PyDoc_STR("push(record) -> bool")},
    {"take_batch", (PyCFunction)Pipeline_take_batch, METH_NOARGS, PyDoc_STR("take_batch() -> list")},
    {"pending", (PyCFunction)Pipeline_pending, METH_NOARGS, PyDoc_STR("pending() -> int")},
    {"flush", (PyCFunction)Pipeline_flush, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("flush(force=False) -> bool")},
    {"flush_and_close", (PyCFunction)Pipeline_flush_and_close, METH_NOARGS, PyDoc_STR("flush_and_close() -> bool")},
    {"set_fallback", (PyCFunction)Pipeline_set_fallback, METH_VARARGS, PyDoc_STR("set_fallback(callable) -> None")},
    {"configure", (PyCFunction)Pipeline_configure, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("configure(*, batch_size, flush_ms) -> None")},
    {"clear", (PyCFunction)Pipeline_take_batch, METH_NOARGS, PyDoc_STR("clear() -> list (deprecated)")},
    {"stats", (PyCFunction)Pipeline_stats, METH_NOARGS, PyDoc_STR("stats() -> dict")},
    {"sqlite_path", (PyCFunction)Pipeline_sqlite_path, METH_NOARGS, PyDoc_STR("sqlite_path() -> Optional[str]")},
    {NULL, NULL, 0, NULL},
};

static PyTypeObject PipelineType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_log_pipeline.Pipeline",
    .tp_basicsize = sizeof(PipelineObject),
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,
    .tp_doc = "日志原生缓冲区对象",
    .tp_methods = Pipeline_methods,
    .tp_members = Pipeline_members,
    .tp_init = (initproc)Pipeline_init,
    .tp_new = PyType_GenericNew,
    .tp_dealloc = (destructor)Pipeline_dealloc,
    .tp_traverse = (traverseproc)Pipeline_traverse,
    .tp_clear = (inquiry)Pipeline_clear,
};

/* -------------------- 模块级接口 -------------------- */

static PyObject *
module_install(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwargs)
{
    return PyObject_Call((PyObject *)&PipelineType, args, kwargs);
}

static PyObject *
module_get_version(PyObject *Py_UNUSED(module), PyObject *Py_UNUSED(args))
{
    return PyUnicode_FromString("2.0.0");
}

static PyMethodDef module_methods[] = {
    {"install", (PyCFunction)(void *)module_install, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("install(*, batch_size=128, flush_ms=2000, fallback=None, event_callback=None, sqlite_path=None) -> Pipeline")},
    {"get_version", (PyCFunction)module_get_version, METH_NOARGS, PyDoc_STR("get_version() -> str")},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_log_pipeline.pipeline",
    .m_doc = "日志原生缓冲区模块",
    .m_size = -1,
    .m_methods = module_methods,
};

PyMODINIT_FUNC
PyInit_pipeline(void)
{
    if (PyType_Ready(&PipelineType) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&module_def);
    if (!module) {
        return NULL;
    }

    Py_INCREF(&PipelineType);
    if (PyModule_AddObject(module, "Pipeline", (PyObject *)&PipelineType) < 0) {
        Py_DECREF(&PipelineType);
        Py_DECREF(module);
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "DEFAULT_BATCH_SIZE", 128) < 0) {
        Py_DECREF(&PipelineType);
        Py_DECREF(module);
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "DEFAULT_FLUSH_MS", 2000) < 0) {
        Py_DECREF(&PipelineType);
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
