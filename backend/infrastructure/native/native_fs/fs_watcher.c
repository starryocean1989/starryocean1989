/* -*- coding: utf-8 -*- */
/*
 * fs_watcher.c - Windows 原生目录监控扩展
 *
 * 提供 watch_directory(path, callback, recursive=True, buffer_size=64*1024) -> DirectoryWatcher
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <windows.h>
#include <process.h>

typedef struct {
    PyObject_HEAD
    PyObject *callback;          /* Python 回调 */
    PyObject *base_path;         /* Python 字符串，原始路径 */
    HANDLE dir_handle;           /* 目录句柄 */
    HANDLE stop_event;           /* 停止事件 */
    HANDLE notify_event;         /* Overlapped 完成事件 */
    HANDLE thread_handle;        /* 工作线程 */
    OVERLAPPED overlapped;       /* Overlapped 结构 */
    BYTE *buffer;                /* 事件缓冲区 */
    DWORD buffer_size;           /* 缓冲区大小 */
    int recursive;               /* 是否递归 */
    volatile LONG running;       /* 运行标志 */
} DirectoryWatcherObject;

static PyTypeObject DirectoryWatcherType;

/* 工具函数 ----------------------------------------------------------------- */

static PyObject *
py_from_widechar(const WCHAR *data, DWORD byte_len)
{
    if (!data || byte_len == 0) {
        return PyUnicode_New(0, 0);
    }
    Py_ssize_t char_count = (Py_ssize_t)(byte_len / sizeof(WCHAR));
    return PyUnicode_FromWideChar(data, char_count);
}

static PyObject *
build_event_dict(const wchar_t *event_name, PyObject *relative_path)
{
    PyObject *event = PyDict_New();
    if (!event) {
        return NULL;
    }

    PyObject *event_type = PyUnicode_FromWideChar(event_name, wcslen(event_name));
    if (!event_type) {
        Py_DECREF(event);
        return NULL;
    }
    if (PyDict_SetItemString(event, "event", event_type) != 0) {
        Py_DECREF(event_type);
        Py_DECREF(event);
        return NULL;
    }
    Py_DECREF(event_type);

    if (relative_path) {
        if (PyDict_SetItemString(event, "name", relative_path) != 0) {
            Py_DECREF(event);
            return NULL;
        }
    }

    PyObject *timestamp_ms = PyLong_FromUnsignedLongLong(GetTickCount64());
    if (!timestamp_ms) {
        Py_DECREF(event);
        return NULL;
    }
    if (PyDict_SetItemString(event, "timestamp_ms", timestamp_ms) != 0) {
        Py_DECREF(timestamp_ms);
        Py_DECREF(event);
        return NULL;
    }
    Py_DECREF(timestamp_ms);

    return event;
}

static void
dispatch_event(DirectoryWatcherObject *self, DWORD bytes_transferred)
{
    if (bytes_transferred == 0) {
        return;
    }

    BYTE *cursor = self->buffer;
    BYTE *end = self->buffer + bytes_transferred;

    while (cursor < end) {
        FILE_NOTIFY_INFORMATION *info = (FILE_NOTIFY_INFORMATION *)cursor;

        PyObject *relative = py_from_widechar(info->FileName, info->FileNameLength);
        if (!relative) {
            PyErr_WriteUnraisable((PyObject *)self->callback);
            goto next_entry;
        }

        const wchar_t *event_name = L"modified";
        switch (info->Action) {
            case FILE_ACTION_ADDED:
                event_name = L"created";
                break;
            case FILE_ACTION_REMOVED:
                event_name = L"deleted";
                break;
            case FILE_ACTION_MODIFIED:
                event_name = L"modified";
                break;
            case FILE_ACTION_RENAMED_OLD_NAME:
                event_name = L"renamed_old";
                break;
            case FILE_ACTION_RENAMED_NEW_NAME:
                event_name = L"renamed_new";
                break;
            default:
                event_name = L"unknown";
                break;
        }

        PyObject *event = build_event_dict(event_name, relative);
        Py_DECREF(relative);
        if (!event) {
            PyErr_WriteUnraisable((PyObject *)self->callback);
            goto next_entry;
        }

        PyObject *result = PyObject_CallFunctionObjArgs(self->callback, event, NULL);
        Py_DECREF(event);
        if (!result) {
            PyErr_WriteUnraisable((PyObject *)self->callback);
        } else {
            Py_DECREF(result);
        }

    next_entry:
        if (info->NextEntryOffset == 0) {
            break;
        }
        cursor += info->NextEntryOffset;
    }
}

static unsigned __stdcall
directory_watcher_thread(void *arg)
{
    DirectoryWatcherObject *self = (DirectoryWatcherObject *)arg;
    const DWORD notify_filter = FILE_NOTIFY_CHANGE_FILE_NAME |
                                FILE_NOTIFY_CHANGE_DIR_NAME |
                                FILE_NOTIFY_CHANGE_LAST_WRITE |
                                FILE_NOTIFY_CHANGE_SIZE |
                                FILE_NOTIFY_CHANGE_CREATION;

    HANDLE wait_handles[2] = {self->stop_event, self->notify_event};

    while (InterlockedCompareExchange(&self->running, 1, 1)) {
        ZeroMemory(&self->overlapped, sizeof(OVERLAPPED));
        self->overlapped.hEvent = self->notify_event;

        if (!ReadDirectoryChangesW(
                self->dir_handle,
                self->buffer,
                self->buffer_size,
                self->recursive,
                notify_filter,
                NULL,
                &self->overlapped,
                NULL)) {
            DWORD err = GetLastError();
            if (err == ERROR_OPERATION_ABORTED) {
                break;
            }
            PyGILState_STATE gstate = PyGILState_Ensure();
            PyErr_Format(PyExc_OSError, "ReadDirectoryChangesW failed: %lu", err);
            PyErr_WriteUnraisable((PyObject *)self);
            PyGILState_Release(gstate);
            break;
        }

        DWORD wait_result = WaitForMultipleObjects(2, wait_handles, FALSE, INFINITE);
        if (wait_result == WAIT_OBJECT_0) { /* stop_event */
            CancelIoEx(self->dir_handle, &self->overlapped);
            break;
        }
        if (wait_result == WAIT_OBJECT_0 + 1) { /* notify_event */
            DWORD bytes_transferred = 0;
            if (GetOverlappedResult(self->dir_handle, &self->overlapped, &bytes_transferred, FALSE)) {
                PyGILState_STATE gstate = PyGILState_Ensure();
                dispatch_event(self, bytes_transferred);
                PyGILState_Release(gstate);
            } else {
                DWORD err = GetLastError();
                if (err != ERROR_OPERATION_ABORTED) {
                    PyGILState_STATE gstate = PyGILState_Ensure();
                    PyErr_Format(PyExc_OSError, "GetOverlappedResult failed: %lu", err);
                    PyErr_WriteUnraisable((PyObject *)self);
                    PyGILState_Release(gstate);
                } else {
                    break;
                }
            }
        } else {
            DWORD err = GetLastError();
            PyGILState_STATE gstate = PyGILState_Ensure();
            PyErr_Format(PyExc_OSError, "WaitForMultipleObjects failed: %lu", err);
            PyErr_WriteUnraisable((PyObject *)self);
            PyGILState_Release(gstate);
            break;
        }
    }

    InterlockedExchange(&self->running, 0);
    _endthreadex(0);
    return 0;
}

static int
DirectoryWatcher_init(DirectoryWatcherObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"path", "callback", "recursive", "buffer_size", NULL};
    PyObject *path_obj;
    PyObject *callback;
    int recursive = 1;
    unsigned int buffer_size = 64 * 1024;

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "UO|pI:watch_directory",
            kwlist,
            &path_obj,
            &callback,
            &recursive,
            &buffer_size)) {
        return -1;
    }

    if (!PyCallable_Check(callback)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable");
        return -1;
    }

    if (buffer_size < 4096) {
        buffer_size = 4096;
    }
    if (buffer_size > 512 * 1024) {
        buffer_size = 512 * 1024;
    }

    self->thread_handle = NULL;
    self->dir_handle = INVALID_HANDLE_VALUE;
    self->stop_event = NULL;
    self->notify_event = NULL;

    Py_INCREF(path_obj);
    self->base_path = path_obj;

    Py_INCREF(callback);
    self->callback = callback;
    self->recursive = recursive ? 1 : 0;
    self->buffer_size = buffer_size;
    self->buffer = (BYTE *)PyMem_Malloc(buffer_size);
    if (!self->buffer) {
        PyErr_NoMemory();
        return -1;
    }

    wchar_t *path_w = PyUnicode_AsWideCharString(path_obj, NULL);
    if (!path_w) {
        return -1;
    }

    HANDLE dir_handle = CreateFileW(
        path_w,
        FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
        NULL);
    PyMem_Free(path_w);

    if (dir_handle == INVALID_HANDLE_VALUE) {
        PyErr_SetFromWindowsErrWithUnicodeFilename(0, path_obj);
        if (self->stop_event) {
            CloseHandle(self->stop_event);
            self->stop_event = NULL;
        }
        if (self->notify_event) {
            CloseHandle(self->notify_event);
            self->notify_event = NULL;
        }
        return -1;
    }

    self->dir_handle = dir_handle;
    self->stop_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    self->notify_event = CreateEventW(NULL, FALSE, FALSE, NULL);
    if (!self->stop_event || !self->notify_event) {
        DWORD err = GetLastError();
        if (self->stop_event) {
            CloseHandle(self->stop_event);
            self->stop_event = NULL;
        }
        if (self->notify_event) {
            CloseHandle(self->notify_event);
            self->notify_event = NULL;
        }
        if (self->dir_handle && self->dir_handle != INVALID_HANDLE_VALUE) {
            CloseHandle(self->dir_handle);
            self->dir_handle = INVALID_HANDLE_VALUE;
        }
        PyErr_SetFromWindowsErr(0);
        return -1;
    }

    InterlockedExchange(&self->running, 1);
    uintptr_t h_thread = _beginthreadex(
        NULL,
        0,
        directory_watcher_thread,
        self,
        0,
        NULL);

    if (h_thread == 0) {
        DWORD err = GetLastError();
        InterlockedExchange(&self->running, 0);
        CloseHandle(self->stop_event);
        self->stop_event = NULL;
        CloseHandle(self->notify_event);
        self->notify_event = NULL;
        if (self->dir_handle && self->dir_handle != INVALID_HANDLE_VALUE) {
            CloseHandle(self->dir_handle);
            self->dir_handle = INVALID_HANDLE_VALUE;
        }
        PyErr_SetString(PyExc_RuntimeError, "failed to start watcher thread");
        SetLastError(err);
        return -1;
    }

    self->thread_handle = (HANDLE)h_thread;

    return 0;
}

static void
DirectoryWatcher_dealloc(DirectoryWatcherObject *self)
{
    if (InterlockedCompareExchange(&self->running, 0, 0)) {
        SetEvent(self->stop_event);
        CancelIoEx(self->dir_handle, &self->overlapped);
        if (self->thread_handle) {
            WaitForSingleObject(self->thread_handle, 5000);
        }
    }

    if (self->thread_handle) {
        CloseHandle(self->thread_handle);
        self->thread_handle = NULL;
    }
    if (self->dir_handle && self->dir_handle != INVALID_HANDLE_VALUE) {
        CloseHandle(self->dir_handle);
        self->dir_handle = INVALID_HANDLE_VALUE;
    }
    if (self->stop_event) {
        CloseHandle(self->stop_event);
        self->stop_event = NULL;
    }
    if (self->notify_event) {
        CloseHandle(self->notify_event);
        self->notify_event = NULL;
    }
    if (self->buffer) {
        PyMem_Free(self->buffer);
        self->buffer = NULL;
    }

    Py_XDECREF(self->callback);
    Py_XDECREF(self->base_path);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
DirectoryWatcher_stop(DirectoryWatcherObject *self, PyObject *Py_UNUSED(args))
{
    if (InterlockedCompareExchange(&self->running, 0, 0)) {
        InterlockedExchange(&self->running, 0);
        if (self->stop_event) {
            SetEvent(self->stop_event);
        }
        if (self->dir_handle && self->dir_handle != INVALID_HANDLE_VALUE) {
            CancelIoEx(self->dir_handle, &self->overlapped);
        }
        if (self->thread_handle) {
            WaitForSingleObject(self->thread_handle, 5000);
        }
    }
    Py_RETURN_NONE;
}

static PyObject *
DirectoryWatcher_is_running(DirectoryWatcherObject *self, PyObject *Py_UNUSED(args))
{
    return PyBool_FromLong(InterlockedCompareExchange(&self->running, 0, 0) ? 1 : 0);
}

static PyObject *
DirectoryWatcher_enter(DirectoryWatcherObject *self, PyObject *Py_UNUSED(args))
{
    Py_INCREF(self);
    return (PyObject *)self;
}

static PyObject *
DirectoryWatcher_exit(DirectoryWatcherObject *self, PyObject *args)
{
    (void)args;
    return DirectoryWatcher_stop(self, NULL);
}

static PyMethodDef DirectoryWatcher_methods[] = {
    {"stop", (PyCFunction)DirectoryWatcher_stop, METH_NOARGS, PyDoc_STR("停止目录监控")},
    {"close", (PyCFunction)DirectoryWatcher_stop, METH_NOARGS, PyDoc_STR("停止目录监控")},
    {"is_running", (PyCFunction)DirectoryWatcher_is_running, METH_NOARGS, PyDoc_STR("返回监控是否仍在运行")},
    {"__enter__", (PyCFunction)DirectoryWatcher_enter, METH_NOARGS, PyDoc_STR("上下文管理协议")},
    {"__exit__", (PyCFunction)DirectoryWatcher_exit, METH_VARARGS, PyDoc_STR("上下文管理协议")},
    {NULL, NULL, 0, NULL},
};

static PyTypeObject DirectoryWatcherType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_fs.DirectoryWatcher",
    .tp_basicsize = sizeof(DirectoryWatcherObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = PyDoc_STR("Native directory watcher"),
    .tp_methods = DirectoryWatcher_methods,
    .tp_init = (initproc)DirectoryWatcher_init,
    .tp_new = PyType_GenericNew,
    .tp_dealloc = (destructor)DirectoryWatcher_dealloc,
};

static PyObject *
module_watch_directory(PyObject *self, PyObject *args, PyObject *kwargs)
{
    (void)self;
    DirectoryWatcherObject *watcher = (DirectoryWatcherObject *)PyObject_Call((PyObject *)&DirectoryWatcherType, args, kwargs);
    if (!watcher) {
        return NULL;
    }
    return (PyObject *)watcher;
}

static PyMethodDef module_methods[] = {
    {"watch_directory", (PyCFunction)module_watch_directory, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("watch_directory(path, callback, recursive=True, buffer_size=65536) -> DirectoryWatcher")},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "fs_watcher",
    .m_doc = "Native filesystem watcher using ReadDirectoryChangesW",
    .m_size = -1,
    .m_methods = module_methods,
};

PyMODINIT_FUNC
PyInit_fs_watcher(void)
{
    if (PyType_Ready(&DirectoryWatcherType) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&module_def);
    if (!module) {
        return NULL;
    }

    Py_INCREF(&DirectoryWatcherType);
    if (PyModule_AddObject(module, "DirectoryWatcher", (PyObject *)&DirectoryWatcherType) < 0) {
        Py_DECREF(&DirectoryWatcherType);
        Py_DECREF(module);
        return NULL;
    }

    PyObject *available = PyBool_FromLong(1);
    if (!available) {
        Py_DECREF(&DirectoryWatcherType);
        Py_DECREF(module);
        return NULL;
    }
    if (PyModule_AddObject(module, "FS_WATCH_AVAILABLE", available) < 0) {
        Py_DECREF(available);
        Py_DECREF(&DirectoryWatcherType);
        Py_DECREF(module);
        return NULL;
    }

    return module;
}


