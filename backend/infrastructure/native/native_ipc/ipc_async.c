#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>

/* Native Log Bridge */
#include "../native_log_bridge.h"

/* 统一组件命名，符合统一日志规范 */
#define NATIVE_COMPONENT "backend.native.ipc.core"

/* Windows Named Pipe 常量 */
#ifndef PIPE_UNLIMITED_INSTANCES
#define PIPE_UNLIMITED_INSTANCES 255
#endif

/* 前向声明 */
typedef struct _IPCAsyncPipeObject IPCAsyncPipeObject;

/* 扩展的OVERLAPPED结构，包含额外信息 */
typedef struct {
    OVERLAPPED overlapped;
    IPCAsyncPipeObject *pipe_obj;  /* 回指管道对象 */
    int operation_type;             /* 操作类型：0=read, 1=write, 2=connect */
    Py_ssize_t buffer_size;        /* 缓冲区大小 */
} ExtendedOverlapped;

/* IPC异步管道对象结构 */
struct _IPCAsyncPipeObject {
    PyObject_HEAD
    HANDLE hPipe;                  /* 命名管道句柄 */
    HANDLE hIOCP;                  /* IOCP完成端口句柄 */
    ExtendedOverlapped *ext_overlapped;  /* 扩展OVERLAPPED结构 */
    HANDLE hEvent;                 /* Windows事件对象，用于通知完成 */
    int is_server;                 /* 是否为服务端：1=server, 0=client */
    int is_open;                   /* 管道是否已打开 */
    int is_complete;               /* I/O操作是否完成 */
    DWORD bytes_transferred;       /* 传输字节数 */
    DWORD error_code;              /* 错误代码 */
    char *buffer;                  /* 数据缓冲区 */
    size_t buffer_size;            /* 缓冲区大小 */
    Py_ssize_t pending_size;       /* 待处理的操作大小 */
};

/* 前向声明 */
static PyObject *IPCAsyncPipe_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void IPCAsyncPipe_dealloc(IPCAsyncPipeObject *self);
static PyObject *IPCAsyncPipe_create_server_pipe(IPCAsyncPipeObject *self, PyObject *args);
static PyObject *IPCAsyncPipe_create_client_pipe(IPCAsyncPipeObject *self, PyObject *args);
static PyObject *IPCAsyncPipe_read_async(IPCAsyncPipeObject *self, PyObject *args);
static PyObject *IPCAsyncPipe_write_async(IPCAsyncPipeObject *self, PyObject *args);
static PyObject *IPCAsyncPipe_close(IPCAsyncPipeObject *self);
static PyObject *IPCAsyncPipe_get_event_handle(IPCAsyncPipeObject *self, PyObject *args);
static PyObject *IPCAsyncPipe_check_completion(IPCAsyncPipeObject *self, PyObject *args);

/* 方法定义 */
static PyMethodDef IPCAsyncPipe_methods[] = {
    {"create_server_pipe", (PyCFunction)IPCAsyncPipe_create_server_pipe, METH_VARARGS, "Create server named pipe"},
    {"create_client_pipe", (PyCFunction)IPCAsyncPipe_create_client_pipe, METH_VARARGS, "Connect to server named pipe"},
    {"read_async", (PyCFunction)IPCAsyncPipe_read_async, METH_VARARGS, "Read from pipe asynchronously"},
    {"write_async", (PyCFunction)IPCAsyncPipe_write_async, METH_VARARGS, "Write to pipe asynchronously"},
    {"close", (PyCFunction)IPCAsyncPipe_close, METH_NOARGS, "Close pipe"},
    {"get_event_handle", (PyCFunction)IPCAsyncPipe_get_event_handle, METH_NOARGS, "Get event handle for completion notification"},
    {"check_completion", (PyCFunction)IPCAsyncPipe_check_completion, METH_NOARGS, "Check if I/O operation completed"},
    {NULL, NULL, 0, NULL}
};

/* 类型定义 */
static PyTypeObject IPCAsyncPipeType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "ipc_async.IPCAsyncPipe",
    .tp_doc = "IOCP-based async IPC pipe",
    .tp_basicsize = sizeof(IPCAsyncPipeObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = IPCAsyncPipe_new,
    .tp_dealloc = (destructor)IPCAsyncPipe_dealloc,
    .tp_methods = IPCAsyncPipe_methods,
};

/* 初始化对象 */
static PyObject *IPCAsyncPipe_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    IPCAsyncPipeObject *self;
    self = (IPCAsyncPipeObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->hPipe = INVALID_HANDLE_VALUE;
        self->hIOCP = NULL;
        self->ext_overlapped = NULL;
        self->hEvent = NULL;
        self->is_server = 0;
        self->is_open = 0;
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
static void IPCAsyncPipe_dealloc(IPCAsyncPipeObject *self) {
    if (self->hPipe != INVALID_HANDLE_VALUE) {
        if (self->is_server) {
            DisconnectNamedPipe(self->hPipe);
        }
        CloseHandle(self->hPipe);
        self->hPipe = INVALID_HANDLE_VALUE;
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
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 创建服务端命名管道 */
static PyObject *IPCAsyncPipe_create_server_pipe(IPCAsyncPipeObject *self, PyObject *args) {
    const char *pipe_name;
    char full_pipe_name[256];

    if (!PyArg_ParseTuple(args, "s", &pipe_name)) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__,
                        "Failed to parse arguments for server pipe creation");
        return NULL;
    }

    /* 构建完整的管道名称：\\.\pipe\{pipe_name} */
    snprintf(full_pipe_name, sizeof(full_pipe_name), "\\\\.\\pipe\\%s", pipe_name);

    NATIVE_LOG_INFO_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__,
                   "Creating server named pipe", pipe_name);

    /* 创建命名管道 */
    self->hPipe = CreateNamedPipeA(
        full_pipe_name,
        PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,  /* 双向通信，异步模式 */
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,  /* 字节流模式 */
        PIPE_UNLIMITED_INSTANCES,  /* 最大实例数 */
        4096,  /* 输出缓冲区大小 */
        4096,  /* 输入缓冲区大小 */
        0,     /* 默认超时 */
        NULL   /* 默认安全属性 */
    );

    if (self->hPipe == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();
        char error_details[256];
        snprintf(error_details, sizeof(error_details),
                "pipe_name=%s, error_code=%lu", pipe_name, error);
        NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Failed to create named pipe", error_details);
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Named pipe created successfully", pipe_name);

    self->is_server = 1;

    /* 创建IOCP完成端口 */
    self->hIOCP = CreateIoCompletionPort(
        INVALID_HANDLE_VALUE,
        NULL,
        0,
        0
    );

    if (self->hIOCP == NULL) {
        DWORD error = GetLastError();
        char error_details[256];
        snprintf(error_details, sizeof(error_details),
                "pipe_name=%s, error_code=%lu", pipe_name, error);
        NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Failed to create IOCP completion port", error_details);
        CloseHandle(self->hPipe);
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "IOCP completion port created successfully", pipe_name);

    /* 将管道句柄关联到IOCP */
    HANDLE result = CreateIoCompletionPort(
        self->hPipe,
        self->hIOCP,
        (ULONG_PTR)self,
        0
    );

    if (result == NULL) {
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 创建Windows事件对象 */
    self->hEvent = CreateEventA(NULL, TRUE, FALSE, NULL);
    if (self->hEvent == NULL) {
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 分配扩展的OVERLAPPED结构 */
    self->ext_overlapped = (ExtendedOverlapped *)malloc(sizeof(ExtendedOverlapped));
    if (self->ext_overlapped == NULL) {
        CloseHandle(self->hEvent);
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hEvent = NULL;
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate OVERLAPPED structure");
        return NULL;
    }
    memset(self->ext_overlapped, 0, sizeof(ExtendedOverlapped));

    /* 初始化OVERLAPPED结构 */
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->pipe_obj = self;
    self->ext_overlapped->operation_type = -1;
    self->ext_overlapped->buffer_size = 0;

    /* 异步等待客户端连接 */
    ResetEvent(self->hEvent);
    memset(&self->ext_overlapped->overlapped, 0, sizeof(OVERLAPPED));
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->operation_type = 2;  /* connect */

    NATIVE_LOG_INFO_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Waiting for client connection asynchronously", pipe_name);

    BOOL connect_result = ConnectNamedPipe(self->hPipe, (LPOVERLAPPED)self->ext_overlapped);
    DWORD error = GetLastError();

    if (!connect_result && error != ERROR_IO_PENDING && error != ERROR_PIPE_CONNECTED) {
        char error_details[256];
        snprintf(error_details, sizeof(error_details),
                "pipe_name=%s, error_code=%lu", pipe_name, error);
        NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Failed to initiate async connection wait", error_details);
        CloseHandle(self->hEvent);
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hEvent = NULL;
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        free(self->ext_overlapped);
        self->ext_overlapped = NULL;
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    /* 如果客户端已连接（ERROR_PIPE_CONNECTED），设置事件 */
    if (error == ERROR_PIPE_CONNECTED) {
        SetEvent(self->hEvent);
        self->is_open = 1;
        NATIVE_LOG_INFO_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Client already connected to pipe", pipe_name);
    } else if (error == ERROR_IO_PENDING) {
        NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Connection wait is pending", pipe_name);
    } else {
        NATIVE_LOG_INFO_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_server_pipe", __LINE__, "Server pipe setup completed", pipe_name);
    }

    self->is_open = 1;
    Py_RETURN_NONE;
}

/* 连接到服务端命名管道 */
static PyObject *IPCAsyncPipe_create_client_pipe(IPCAsyncPipeObject *self, PyObject *args) {
    const char *pipe_name;
    char full_pipe_name[256];

    if (!PyArg_ParseTuple(args, "s", &pipe_name)) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_create_client_pipe", __LINE__,
                        "Failed to parse arguments for client pipe creation");
        return NULL;
    }

    /* 构建完整的管道名称 */
    snprintf(full_pipe_name, sizeof(full_pipe_name), "\\\\.\\pipe\\%s", pipe_name);

    NATIVE_LOG_INFO_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_client_pipe", __LINE__, "Attempting to connect to server pipe", pipe_name);

    /* 等待管道可用 */
    if (!WaitNamedPipeA(full_pipe_name, 5000)) {  /* 等待5秒 */
        DWORD error = GetLastError();
        char error_details[256];
        snprintf(error_details, sizeof(error_details),
                "pipe_name=%s, timeout=5000ms, error_code=%lu", pipe_name, error);
        NATIVE_LOG_WARNING_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_client_pipe", __LINE__, "Timeout waiting for server pipe to become available", error_details);
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_create_client_pipe", __LINE__, "Server pipe is available, proceeding with connection", pipe_name);

    /* 打开命名管道 */
    self->hPipe = CreateFileA(
        full_pipe_name,
        GENERIC_READ | GENERIC_WRITE,
        0,
        NULL,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        NULL
    );

    if (self->hPipe == INVALID_HANDLE_VALUE) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    self->is_server = 0;

    /* 创建IOCP完成端口 */
    self->hIOCP = CreateIoCompletionPort(
        INVALID_HANDLE_VALUE,
        NULL,
        0,
        0
    );

    if (self->hIOCP == NULL) {
        CloseHandle(self->hPipe);
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 将管道句柄关联到IOCP */
    HANDLE result = CreateIoCompletionPort(
        self->hPipe,
        self->hIOCP,
        (ULONG_PTR)self,
        0
    );

    if (result == NULL) {
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 创建Windows事件对象 */
    self->hEvent = CreateEventA(NULL, TRUE, FALSE, NULL);
    if (self->hEvent == NULL) {
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    /* 分配扩展的OVERLAPPED结构 */
    self->ext_overlapped = (ExtendedOverlapped *)malloc(sizeof(ExtendedOverlapped));
    if (self->ext_overlapped == NULL) {
        CloseHandle(self->hEvent);
        CloseHandle(self->hIOCP);
        CloseHandle(self->hPipe);
        self->hEvent = NULL;
        self->hIOCP = NULL;
        self->hPipe = INVALID_HANDLE_VALUE;
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate OVERLAPPED structure");
        return NULL;
    }
    memset(self->ext_overlapped, 0, sizeof(ExtendedOverlapped));

    /* 初始化OVERLAPPED结构 */
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->pipe_obj = self;
    self->ext_overlapped->operation_type = -1;
    self->ext_overlapped->buffer_size = 0;

    self->is_open = 1;
    Py_RETURN_NONE;
}

/* 异步读取 */
static PyObject *IPCAsyncPipe_read_async(IPCAsyncPipeObject *self, PyObject *args) {
    Py_ssize_t size = 4096;

    if (!PyArg_ParseTuple(args, "|n", &size)) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__,
                        "Failed to parse arguments for async read");
        return NULL;
    }

    if (self->hPipe == INVALID_HANDLE_VALUE) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__,
                        "Attempted to read from unopened pipe");
        PyErr_SetString(PyExc_ValueError, "Pipe not opened");
        return NULL;
    }

    if (!self->is_open) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__,
                        "Attempted to read from disconnected pipe");
        PyErr_SetString(PyExc_ValueError, "Pipe not connected");
        return NULL;
    }

    if (self->ext_overlapped == NULL) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__,
                        "OVERLAPPED structure not initialized");
        PyErr_SetString(PyExc_ValueError, "OVERLAPPED structure not initialized");
        return NULL;
    }

    char size_details[64];
    snprintf(size_details, sizeof(size_details), "size=%zd", size);
    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__, "Initiating async read operation", size_details);

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
    self->ext_overlapped->pipe_obj = self;
    self->ext_overlapped->operation_type = 0;  /* read */
    self->ext_overlapped->buffer_size = size;

    self->is_complete = 0;
    self->bytes_transferred = 0;
    self->error_code = 0;
    self->pending_size = size;

    /* 启动异步读取 */
    BOOL result = ReadFile(
        self->hPipe,
        self->buffer,
        (DWORD)size,
        NULL,
        (LPOVERLAPPED)self->ext_overlapped
    );

    DWORD error = GetLastError();

    /* 如果立即完成 */
    if (result) {
        DWORD bytes_read;
        if (GetOverlappedResult(self->hPipe, (LPOVERLAPPED)self->ext_overlapped, &bytes_read, FALSE)) {
            char complete_details[64];
            snprintf(complete_details, sizeof(complete_details), "bytes_read=%lu", bytes_read);
            NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__, "Async read completed immediately", complete_details);
            PyObject *data = PyBytes_FromStringAndSize(self->buffer, bytes_read);
            self->is_complete = 1;
            return data;
        }
    } else if (error != ERROR_IO_PENDING) {
        char error_details[64];
        snprintf(error_details, sizeof(error_details), "error_code=%lu", error);
        NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__, "Failed to initiate async read", error_details);
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    /* I/O挂起，返回事件句柄 */
    NATIVE_LOG_DEBUG(NATIVE_COMPONENT, "IPCAsyncPipe_read_async", __LINE__,
                    "Async read operation pending");
    return Py_BuildValue("(iO)", 1, PyLong_FromVoidPtr((void *)self->hEvent));
}

/* 异步写入 */
static PyObject *IPCAsyncPipe_write_async(IPCAsyncPipeObject *self, PyObject *args) {
    Py_buffer buffer;

    if (!PyArg_ParseTuple(args, "y*", &buffer)) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__,
                        "Failed to parse arguments for async write");
        return NULL;
    }

    if (self->hPipe == INVALID_HANDLE_VALUE) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__,
                        "Attempted to write to unopened pipe");
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "Pipe not opened");
        return NULL;
    }

    if (!self->is_open) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__,
                        "Attempted to write to disconnected pipe");
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "Pipe not connected");
        return NULL;
    }

    if (self->ext_overlapped == NULL) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__,
                        "OVERLAPPED structure not initialized");
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "OVERLAPPED structure not initialized");
        return NULL;
    }

    char size_details[64];
    snprintf(size_details, sizeof(size_details), "size=%zd", buffer.len);
    NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__, "Initiating async write operation", size_details);

    /* 重置事件对象和OVERLAPPED结构 */
    ResetEvent(self->hEvent);
    memset(&self->ext_overlapped->overlapped, 0, sizeof(OVERLAPPED));
    self->ext_overlapped->overlapped.hEvent = self->hEvent;
    self->ext_overlapped->pipe_obj = self;
    self->ext_overlapped->operation_type = 1;  /* write */
    self->ext_overlapped->buffer_size = buffer.len;

    self->is_complete = 0;
    self->error_code = 0;
    self->pending_size = buffer.len;

    /* 启动异步写入 */
    BOOL result = WriteFile(
        self->hPipe,
        buffer.buf,
        (DWORD)buffer.len,
        NULL,
        (LPOVERLAPPED)self->ext_overlapped
    );

    DWORD error = GetLastError();

    if (result) {
        /* 立即完成 */
        DWORD bytes_written;
        if (GetOverlappedResult(self->hPipe, (LPOVERLAPPED)self->ext_overlapped, &bytes_written, FALSE)) {
            char complete_details[64];
            snprintf(complete_details, sizeof(complete_details), "bytes_written=%lu", bytes_written);
            NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__, "Async write completed immediately", complete_details);
            PyBuffer_Release(&buffer);
            self->is_complete = 1;
            return PyLong_FromLong(bytes_written);
        }
    } else if (error != ERROR_IO_PENDING) {
        char error_details[64];
        snprintf(error_details, sizeof(error_details), "error_code=%lu", error);
        NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__, "Failed to initiate async write", error_details);
        PyBuffer_Release(&buffer);
        PyErr_SetFromWindowsErr(error);
        return NULL;
    }

    /* I/O挂起，返回事件句柄 */
    NATIVE_LOG_DEBUG(NATIVE_COMPONENT, "IPCAsyncPipe_write_async", __LINE__,
                    "Async write operation pending");
    PyBuffer_Release(&buffer);
    return Py_BuildValue("(iO)", 1, PyLong_FromVoidPtr((void *)self->hEvent));
}

/* 关闭管道 */
static PyObject *IPCAsyncPipe_close(IPCAsyncPipeObject *self) {
    NATIVE_LOG_INFO(NATIVE_COMPONENT, "IPCAsyncPipe_close", __LINE__,
                   "Closing IPC pipe");
    if (self->hPipe != INVALID_HANDLE_VALUE) {
        if (self->is_server) {
            DisconnectNamedPipe(self->hPipe);
        }
        CloseHandle(self->hPipe);
        self->hPipe = INVALID_HANDLE_VALUE;
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
    self->is_open = 0;
    Py_RETURN_NONE;
}

/* 获取事件句柄 */
static PyObject *IPCAsyncPipe_get_event_handle(IPCAsyncPipeObject *self, PyObject *args) {
    if (self->hEvent == NULL) {
        PyErr_SetString(PyExc_ValueError, "Event not initialized");
        return NULL;
    }
    /* 返回事件句柄值（整数） */
    return PyLong_FromVoidPtr((void *)self->hEvent);
}

/* 检查完成状态 */
static PyObject *IPCAsyncPipe_check_completion(IPCAsyncPipeObject *self, PyObject *args) {
    if (self->ext_overlapped == NULL) {
        NATIVE_LOG_ERROR(NATIVE_COMPONENT, "IPCAsyncPipe_check_completion", __LINE__,
                        "OVERLAPPED structure not initialized");
        PyErr_SetString(PyExc_ValueError, "OVERLAPPED structure not initialized");
        return NULL;
    }

    /* 检查事件对象是否已触发 */
    DWORD wait_result = WaitForSingleObject(self->hEvent, 0);

    if (wait_result == WAIT_OBJECT_0) {
        /* 事件已触发，I/O完成 */
        DWORD bytes_transferred = 0;
        BOOL result = GetOverlappedResult(
            self->hPipe,
            (LPOVERLAPPED)self->ext_overlapped,
            &bytes_transferred,
            FALSE
        );

        if (result) {
            self->is_complete = 1;
            self->bytes_transferred = bytes_transferred;
            self->error_code = 0;

            char complete_details[128];
            /* 根据操作类型返回结果 */
            if (self->ext_overlapped->operation_type == 0) {
                /* 读取操作 */
                snprintf(complete_details, sizeof(complete_details),
                        "operation=read, bytes_transferred=%lu", bytes_transferred);
                NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_check_completion", __LINE__, "Async read operation completed", complete_details);
                PyObject *data = PyBytes_FromStringAndSize(self->buffer, bytes_transferred);
                return Py_BuildValue("(iN)", 1, data);  /* (complete=1, data) */
            } else if (self->ext_overlapped->operation_type == 1) {
                /* 写入操作 */
                snprintf(complete_details, sizeof(complete_details),
                        "operation=write, bytes_transferred=%lu", bytes_transferred);
                NATIVE_LOG_DEBUG_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_check_completion", __LINE__, "Async write operation completed", complete_details);
                return Py_BuildValue("(ii)", 1, (int)bytes_transferred);  /* (complete=1, bytes_written) */
            } else if (self->ext_overlapped->operation_type == 2) {
                /* 连接操作 */
                NATIVE_LOG_INFO(NATIVE_COMPONENT, "IPCAsyncPipe_check_completion", __LINE__,
                               "Async connect operation completed");
                return Py_BuildValue("(ii)", 1, 0);  /* (complete=1, 0) */
            }
        } else {
            /* 获取完成状态失败 */
            self->error_code = GetLastError();
            self->is_complete = 0;
            char error_details[64];
            snprintf(error_details, sizeof(error_details), "error_code=%lu", self->error_code);
            NATIVE_LOG_ERROR_DETAILS(NATIVE_COMPONENT, "IPCAsyncPipe_check_completion", __LINE__, "Failed to get overlapped result", error_details);
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

/* 模块初始化 */
static PyModuleDef ipc_asyncmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "ipc_async",
    .m_doc = "IOCP-based async IPC for Windows",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit_ipc_async(void) {
    PyObject *m;

    if (PyType_Ready(&IPCAsyncPipeType) < 0) {
        return NULL;
    }

    m = PyModule_Create(&ipc_asyncmodule);
    if (m == NULL) {
        return NULL;
    }

    Py_INCREF(&IPCAsyncPipeType);
    if (PyModule_AddObject(m, "IPCAsyncPipe", (PyObject *)&IPCAsyncPipeType) < 0) {
        Py_DECREF(&IPCAsyncPipeType);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}
