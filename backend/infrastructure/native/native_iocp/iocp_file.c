#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>

/* Native Log Bridge */
#include "../native_log_bridge.h"

/* 统一组件命名，符合统一日志规范 */
#define NATIVE_COMPONENT "backend.native.iocp.core"

/* Windows IOCP 常量（检查是否已定义） */
#ifndef FILE_FLAG_OVERLAPPED
#define FILE_FLAG_OVERLAPPED 0x40000000
#endif

/* 前向声明 */
typedef struct _IOCPFileObject IOCPFileObject;

/* 扩展的OVERLAPPED结构，包含额外信息 */
typedef struct {
    OVERLAPPED overlapped;
    IOCPFileObject *file_obj;  /* 回指文件对象 */
    int operation_type;        /* 操作类型：0=read, 1=write */
    Py_ssize_t buffer_size;   /* 缓冲区大小 */
} ExtendedOverlapped;

/* IOCP文件对象结构 */
struct _IOCPFileObject {
    PyObject_HEAD
    HANDLE hFile;
    HANDLE hIOCP;
    ExtendedOverlapped *ext_overlapped;
    HANDLE hEvent;            /* Windows事件对象，用于通知完成 */
    PyObject *future;
    PyObject *loop;
    int is_complete;
    DWORD bytes_transferred;
    DWORD error_code;
    char *buffer;
    size_t buffer_size;
    Py_ssize_t pending_size;  /* 待处理的操作大小 */
};

/* 前向声明 */
static PyObject *IOCPFile_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void IOCPFile_dealloc(IOCPFileObject *self);
static PyObject *IOCPFile_open(IOCPFileObject *self, PyObject *args);
static PyObject *IOCPFile_read_async(IOCPFileObject *self, PyObject *args);
static PyObject *IOCPFile_write_async(IOCPFileObject *self, PyObject *args);
static PyObject *IOCPFile_close(IOCPFileObject *self);
static PyObject *IOCPFile_get_iocp_handle(IOCPFileObject *self, PyObject *args);
static PyObject *IOCPFile_get_event_handle(IOCPFileObject *self, PyObject *args);
static PyObject *IOCPFile_check_completion(IOCPFileObject *self, PyObject *args);

/* 完成回调处理函数 */
static VOID WINAPI IOCP_CompletionRoutine(
    DWORD dwErrorCode,
    DWORD dwNumberOfBytesTransfered,
    LPOVERLAPPED lpOverlapped
);

/* 方法定义 */
static PyMethodDef IOCPFile_methods[] = {
    {"open", (PyCFunction)IOCPFile_open, METH_VARARGS, "Open file with IOCP"},
    {"read_async", (PyCFunction)IOCPFile_read_async, METH_VARARGS, "Read file asynchronously"},
    {"write_async", (PyCFunction)IOCPFile_write_async, METH_VARARGS, "Write file asynchronously"},
    {"close", (PyCFunction)IOCPFile_close, METH_NOARGS, "Close file"},
    {"get_iocp_handle", (PyCFunction)IOCPFile_get_iocp_handle, METH_NOARGS, "Get IOCP handle"},
    {"get_event_handle", (PyCFunction)IOCPFile_get_event_handle, METH_NOARGS, "Get event handle for completion notification"},
    {"check_completion", (PyCFunction)IOCPFile_check_completion, METH_NOARGS, "Check if I/O operation completed"},
    {NULL, NULL, 0, NULL}
};

/* 类型定义 */
static PyTypeObject IOCPFileType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "iocp_file.IOCPFile",
    .tp_doc = "IOCP-based async file I/O",
    .tp_basicsize = sizeof(IOCPFileObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = IOCPFile_new,
    .tp_dealloc = (destructor)IOCPFile_dealloc,
    .tp_methods = IOCPFile_methods,
};

/* 初始化对象 */
static PyObject *IOCPFile_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    IOCPFileObject *self;
    self = (IOCPFileObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->hFile = INVALID_HANDLE_VALUE;
        self->hIOCP = NULL;
        self->ext_overlapped = NULL;
        self->hEvent = NULL;
        self->future = NULL;
        self->loop = NULL;
        self->is_complete = 0;
        self->bytes_transferred = 0;
        self->error_code = 0;
        self->buffer = NULL;
        self->buffer_size = 0;
        self->pending_size = 0;
    }
    return (PyObject *)self;
}

/* 清理对象 */
static void IOCPFile_dealloc(IOCPFileObject *self) {
    if (self->hFile != INVALID_HANDLE_VALUE) {
        CloseHandle(self->hFile);
        self->hFile = INVALID_HANDLE_VALUE;
    }
    if (self->hIOCP != NULL) {
        CloseHandle(self->hIOCP);
        self->hIOCP = NULL;
    }
    if (self->hEvent != NULL) {
        CloseHandle(self->hEvent);
        self->hEvent = NULL;
    }
    if (self->ext_overlapped != NULL) {
        free(self->ext_overlapped);
        self->ext_overlapped = NULL;
    }
    if (self->buffer != NULL) {
        free(self->buffer);
        self->buffer = NULL;
    }
    Py_XDECREF(self->future);
    Py_XDECREF(self->loop);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 打开文件 */
static PyObject *IOCPFile_open(IOCPFileObject *self, PyObject *args) {
    const char *filename;
    const char *mode = "rb";
    DWORD access = GENERIC_READ;
    DWORD create = OPEN_EXISTING;

    if (!PyArg_ParseTuple(args, "s|s", &filename, &mode)) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IOCPFile_open", __LINE__,
                        "Failed to parse arguments for file open");
        return NULL;
    }

    char open_details[256];
    snprintf(open_details, sizeof(open_details), "filename=%s, mode=%s", filename, mode);
    NATIVE_LOG_INFO_DETAILS(NATIVE_COMPONENT, "IOCPFile_open", __LINE__,
                   "Opening file with IOCP", open_details);

    /* 解析模式 */
    if (strchr(mode, 'w') != NULL) {
        access = GENERIC_WRITE;
        create = (strchr(mode, 'a') != NULL) ? OPEN_ALWAYS : CREATE_ALWAYS;
    } else if (strchr(mode, 'a') != NULL) {
        access = GENERIC_WRITE;
        create = OPEN_ALWAYS;
    }

    if (strchr(mode, '+') != NULL) {
        access |= GENERIC_READ | GENERIC_WRITE;
    }

    /* 打开文件，使用OVERLAPPED标志 */
    self->hFile = CreateFileA(
        filename,
        access,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        create,
        FILE_FLAG_OVERLAPPED,
        NULL
    );

    if (self->hFile == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();
        char error_details[256];
        snprintf(error_details, sizeof(error_details),
                "filename=%s, error_code=%lu", filename, error);
        NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IOCPFile_open", __LINE__,
                        "Failed to open file", error_details);
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IOCPFile_open", __LINE__,
                    "File opened successfully", filename);

    /* 创建IOCP */
    self->hIOCP = CreateIoCompletionPort(
        INVALID_HANDLE_VALUE,
        NULL,
        0,
        0
    );

    if (self->hIOCP == NULL) {
        CloseHandle(self->hFile);
        self->hFile = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 将文件句柄关联到IOCP */
    HANDLE result = CreateIoCompletionPort(
        self->hFile,
        self->hIOCP,
        (ULONG_PTR)self,
        0
    );

    if (result == NULL) {
        CloseHandle(self->hIOCP);
        CloseHandle(self->hFile);
        self->hIOCP = NULL;
        self->hFile = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 创建Windows事件对象，用于完成通知 */
    self->hEvent = CreateEventA(NULL, TRUE, FALSE, NULL);
    if (self->hEvent == NULL) {
        CloseHandle(self->hIOCP);
        CloseHandle(self->hFile);
        self->hIOCP = NULL;
        self->hFile = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 分配扩展的OVERLAPPED结构 */
    self->ext_overlapped = (ExtendedOverlapped *)malloc(sizeof(ExtendedOverlapped));
    if (self->ext_overlapped == NULL) {
        CloseHandle(self->hEvent);
        CloseHandle(self->hIOCP);
        CloseHandle(self->hFile);
        self->hEvent = NULL;
        self->hIOCP = NULL;
        self->hFile = INVALID_HANDLE_VALUE;
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate OVERLAPPED structure");
        return NULL;
    }
    memset(self->ext_overlapped, 0, sizeof(ExtendedOverlapped));

    /* 初始化OVERLAPPED结构 */
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->file_obj = self;
    self->ext_overlapped->operation_type = -1;
    self->ext_overlapped->buffer_size = 0;

    Py_RETURN_NONE;
}

/* 异步读取 */
static PyObject *IOCPFile_read_async(IOCPFileObject *self, PyObject *args) {
    Py_ssize_t size = 4096;

    if (!PyArg_ParseTuple(args, "|n", &size)) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IOCPFile_read_async", __LINE__,
                        "Failed to parse arguments for async read");
        return NULL;
    }

    if (self->hFile == INVALID_HANDLE_VALUE) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IOCPFile_read_async", __LINE__,
                        "Attempted to read from unopened file");
        PyErr_SetString(PyExc_ValueError, "File not opened");
        return NULL;
    }

    if (self->ext_overlapped == NULL) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IOCPFile_read_async", __LINE__,
                        "OVERLAPPED structure not initialized");
        PyErr_SetString(PyExc_ValueError, "OVERLAPPED structure not initialized");
        return NULL;
    }

    char size_details[64];
    snprintf(size_details, sizeof(size_details), "size=%zd", size);
    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IOCPFile_read_async", __LINE__,
                    "Initiating async file read operation", size_details);

    /* 分配缓冲区 */
    if (self->buffer == NULL || self->buffer_size < (size_t)size) {
        if (self->buffer != NULL) {
            free(self->buffer);
        }
        self->buffer = (char *)malloc(size);
        if (self->buffer == NULL) {
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate buffer");
            return NULL;
        }
        self->buffer_size = size;
    }

    /* 重置事件对象和OVERLAPPED结构 */
    ResetEvent(self->hEvent);
    memset(&self->ext_overlapped->overlapped, 0, sizeof(OVERLAPPED));
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->file_obj = self;
    self->ext_overlapped->operation_type = 0;  /* read */
    self->ext_overlapped->buffer_size = size;

    self->is_complete = 0;
    self->bytes_transferred = 0;
    self->error_code = 0;
    self->pending_size = size;

    /* 启动异步读取 */
    BOOL result = ReadFile(
        self->hFile,
        self->buffer,
        (DWORD)size,
        NULL,
        (LPOVERLAPPED)self->ext_overlapped
    );

    DWORD error = GetLastError();

    /* 如果立即完成 */
    if (result) {
        DWORD bytes_read;
        if (GetOverlappedResult(self->hFile, (LPOVERLAPPED)self->ext_overlapped, &bytes_read, FALSE)) {
            PyObject *data = PyBytes_FromStringAndSize(self->buffer, bytes_read);
            self->is_complete = 1;
            return data;
        }
    } else if (error != ERROR_IO_PENDING) {
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    /* I/O挂起，返回事件句柄（用于asyncio事件循环注册） */
    /* 返回元组：(pending标志, 事件句柄) */
    return Py_BuildValue("(iO)", 1, PyLong_FromVoidPtr((void *)self->hEvent));
}

/* 异步写入 */
static PyObject *IOCPFile_write_async(IOCPFileObject *self, PyObject *args) {
    Py_buffer buffer;

    if (!PyArg_ParseTuple(args, "y*", &buffer)) {
        return NULL;
    }

    if (self->hFile == INVALID_HANDLE_VALUE) {
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "File not opened");
        return NULL;
    }

    if (self->ext_overlapped == NULL) {
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "OVERLAPPED structure not initialized");
        return NULL;
    }

    /* 重置事件对象和OVERLAPPED结构 */
    ResetEvent(self->hEvent);
    memset(&self->ext_overlapped->overlapped, 0, sizeof(OVERLAPPED));
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->file_obj = self;
    self->ext_overlapped->operation_type = 1;  /* write */
    self->ext_overlapped->buffer_size = buffer.len;

    self->is_complete = 0;
    self->error_code = 0;
    self->pending_size = buffer.len;

    /* 启动异步写入 */
    BOOL result = WriteFile(
        self->hFile,
        buffer.buf,
        (DWORD)buffer.len,
        NULL,
        (LPOVERLAPPED)self->ext_overlapped
    );

    DWORD error = GetLastError();

    if (result) {
        /* 立即完成 */
        DWORD bytes_written;
        if (GetOverlappedResult(self->hFile, (LPOVERLAPPED)self->ext_overlapped, &bytes_written, FALSE)) {
            PyBuffer_Release(&buffer);
            self->is_complete = 1;
            return PyLong_FromLong(bytes_written);
        }
    } else if (error != ERROR_IO_PENDING) {
        PyBuffer_Release(&buffer);
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    /* I/O挂起，返回事件句柄 */
    PyBuffer_Release(&buffer);
    return Py_BuildValue("(iO)", 1, PyLong_FromVoidPtr((void *)self->hEvent));
}

/* 关闭文件 */
static PyObject *IOCPFile_close(IOCPFileObject *self) {
    if (self->hFile != INVALID_HANDLE_VALUE) {
        CloseHandle(self->hFile);
        self->hFile = INVALID_HANDLE_VALUE;
    }
    if (self->hIOCP != NULL) {
        CloseHandle(self->hIOCP);
        self->hIOCP = NULL;
    }
    if (self->hEvent != NULL) {
        CloseHandle(self->hEvent);
        self->hEvent = NULL;
    }
    if (self->ext_overlapped != NULL) {
        free(self->ext_overlapped);
        self->ext_overlapped = NULL;
    }
    if (self->buffer != NULL) {
        free(self->buffer);
        self->buffer = NULL;
        self->buffer_size = 0;
    }
    Py_RETURN_NONE;
}

/* 获取IOCP句柄 */
static PyObject *IOCPFile_get_iocp_handle(IOCPFileObject *self, PyObject *args) {
    if (self->hIOCP == NULL) {
        PyErr_SetString(PyExc_ValueError, "IOCP not initialized");
        return NULL;
    }
    /* 返回句柄值（整数） */
    return PyLong_FromVoidPtr((void *)self->hIOCP);
}

/* 获取事件句柄 */
static PyObject *IOCPFile_get_event_handle(IOCPFileObject *self, PyObject *args) {
    if (self->hEvent == NULL) {
        PyErr_SetString(PyExc_ValueError, "Event not initialized");
        return NULL;
    }
    /* 返回事件句柄值（整数） */
    return PyLong_FromVoidPtr((void *)self->hEvent);
}

/* 检查完成状态 */
static PyObject *IOCPFile_check_completion(IOCPFileObject *self, PyObject *args) {
    if (self->ext_overlapped == NULL) {
        PyErr_SetString(PyExc_ValueError, "OVERLAPPED structure not initialized");
        return NULL;
    }

    /* 检查事件对象是否已触发 */
    DWORD wait_result = WaitForSingleObject(self->hEvent, 0);

    if (wait_result == WAIT_OBJECT_0) {
        /* 事件已触发，I/O完成 */
        DWORD bytes_transferred = 0;
        BOOL result = GetOverlappedResult(
            self->hFile,
            (LPOVERLAPPED)self->ext_overlapped,
            &bytes_transferred,
            FALSE
        );

        if (result) {
            self->is_complete = 1;
            self->bytes_transferred = bytes_transferred;
            self->error_code = 0;

            /* 根据操作类型返回结果 */
            if (self->ext_overlapped->operation_type == 0) {
                /* 读取操作 */
                PyObject *data = PyBytes_FromStringAndSize(self->buffer, bytes_transferred);
                return Py_BuildValue("(iN)", 1, data);  /* (complete=1, data) */
            } else if (self->ext_overlapped->operation_type == 1) {
                /* 写入操作 */
                return Py_BuildValue("(ii)", 1, (int)bytes_transferred);  /* (complete=1, bytes_written) */
            }
        } else {
            /* 获取完成状态失败 */
            self->error_code = GetLastError();
            self->is_complete = 0;
            return Py_BuildValue("(ii)", 0, (int)self->error_code);  /* (complete=0, error_code) */
        }
    } else if (wait_result == WAIT_TIMEOUT) {
        /* 事件未触发，I/O仍在进行 */
        return Py_BuildValue("(ii)", 0, 0);  /* (complete=0, error_code=0) */
    } else {
        /* 等待失败 */
        DWORD error = GetLastError();
        return Py_BuildValue("(ii)", 0, (int)error);  /* (complete=0, error_code) */
    }

    Py_RETURN_NONE;
}

/* 完成回调处理函数 */
static VOID WINAPI IOCP_CompletionRoutine(
    DWORD dwErrorCode,
    DWORD dwNumberOfBytesTransfered,
    LPOVERLAPPED lpOverlapped
) {
    /* 这个函数用于ReadFileEx/WriteFileEx */
    /* 当前实现使用GetQueuedCompletionStatus */
}

/* 模块初始化 */
static PyModuleDef iocp_filemodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "iocp_file",
    .m_doc = "IOCP-based async file I/O for Windows",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit_iocp_file(void) {
    PyObject *m;

    if (PyType_Ready(&IOCPFileType) < 0) {
        return NULL;
    }

    m = PyModule_Create(&iocp_filemodule);
    if (m == NULL) {
        return NULL;
    }

    Py_INCREF(&IOCPFileType);
    if (PyModule_AddObject(m, "IOCPFile", (PyObject *)&IOCPFileType) < 0) {
        Py_DECREF(&IOCPFileType);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}

