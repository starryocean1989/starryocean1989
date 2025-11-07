#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <winsock2.h>
#include <ws2tcpip.h>
#include <iphlpapi.h>

#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "ws2_32.lib")

typedef struct {
    unsigned long total_connections;
    unsigned long established_connections;
} tcp_counts_t;

static int ensure_wsa_started(void) {
    static int initialized = 0;
    if (!initialized) {
        WSADATA wsaData;
        int result = WSAStartup(MAKEWORD(2, 2), &wsaData);
        if (result != 0) {
            PyErr_Format(PyExc_RuntimeError, "WSAStartup failed: %d", result);
            return 0;
        }
        initialized = 1;
    }
    return 1;
}

static int collect_tcp_counts(ULONG family, tcp_counts_t *counts) {
    DWORD size = 0;
    PMIB_TCPTABLE_OWNER_PID table = NULL;
    DWORD result;

    result = GetExtendedTcpTable(NULL, &size, FALSE, family, TCP_TABLE_OWNER_PID_ALL, 0);
    if (result != ERROR_INSUFFICIENT_BUFFER) {
        if (result == ERROR_NOT_SUPPORTED || result == ERROR_INVALID_PARAMETER) {
            return 1;  /* family not supported, treat as zero counts */
        }
        PyErr_Format(PyExc_RuntimeError, "GetExtendedTcpTable pre-call failed: %lu", result);
        return 0;
    }

    table = (PMIB_TCPTABLE_OWNER_PID)PyMem_Malloc(size);
    if (table == NULL) {
        PyErr_NoMemory();
        return 0;
    }

    result = GetExtendedTcpTable(table, &size, FALSE, family, TCP_TABLE_OWNER_PID_ALL, 0);
    if (result != NO_ERROR) {
        PyMem_Free(table);
        if (result == ERROR_NOT_SUPPORTED || result == ERROR_INVALID_PARAMETER) {
            return 1;
        }
        PyErr_Format(PyExc_RuntimeError, "GetExtendedTcpTable failed: %lu", result);
        return 0;
    }

    counts->total_connections += table->dwNumEntries;

    if (table->dwNumEntries > 0) {
        for (DWORD i = 0; i < table->dwNumEntries; ++i) {
            if (table->table[i].dwState == MIB_TCP_STATE_ESTAB) {
                counts->established_connections += 1;
            }
        }
    }

    PyMem_Free(table);
    return 1;
}

static PyObject *py_get_socket_metrics(PyObject *self, PyObject *Py_UNUSED(args)) {
    if (!ensure_wsa_started()) {
        return NULL;
    }

    tcp_counts_t counts = {0, 0};

    if (!collect_tcp_counts(AF_INET, &counts)) {
        return NULL;
    }

    if (!collect_tcp_counts(AF_INET6, &counts)) {
        return NULL;
    }

    SOCKET probe = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    int recv_buf = 0;
    int send_buf = 0;
    int optlen = sizeof(int);

    if (probe != INVALID_SOCKET) {
        if (getsockopt(probe, SOL_SOCKET, SO_RCVBUF, (char *)&recv_buf, &optlen) == SOCKET_ERROR) {
            recv_buf = 0;
        }
        optlen = sizeof(int);
        if (getsockopt(probe, SOL_SOCKET, SO_SNDBUF, (char *)&send_buf, &optlen) == SOCKET_ERROR) {
            send_buf = 0;
        }
        closesocket(probe);
    }

    if (recv_buf < 0) {
        recv_buf = 0;
    }
    if (send_buf < 0) {
        send_buf = 0;
    }

    double usage_ratio = 0.0;
    if (counts.total_connections > 0) {
        usage_ratio = ((double)counts.established_connections / (double)counts.total_connections) * 100.0;
        if (usage_ratio > 100.0) {
            usage_ratio = 100.0;
        }
    }

    PyObject *result = PyDict_New();
    if (result == NULL) {
        return NULL;
    }

#define SET_ITEM(key, value_expr)                                                                  \
    do {                                                                                           \
        PyObject *tmp_value = (value_expr);                                                        \
        if (tmp_value == NULL) {                                                                   \
            Py_DECREF(result);                                                                     \
            return NULL;                                                                           \
        }                                                                                          \
        if (PyDict_SetItemString(result, (key), tmp_value) != 0) {                                 \
            Py_DECREF(tmp_value);                                                                  \
            Py_DECREF(result);                                                                     \
            return NULL;                                                                           \
        }                                                                                          \
        Py_DECREF(tmp_value);                                                                      \
    } while (0)

    SET_ITEM("recv_buffer_size_avg", PyLong_FromLong(recv_buf));
    SET_ITEM("send_buffer_size_avg", PyLong_FromLong(send_buf));
    SET_ITEM("recv_buffer_size_max", PyLong_FromLong(recv_buf));
    SET_ITEM("send_buffer_size_max", PyLong_FromLong(send_buf));
    SET_ITEM("recv_buffer_size_min", PyLong_FromLong(recv_buf));
    SET_ITEM("send_buffer_size_min", PyLong_FromLong(send_buf));
    SET_ITEM("recv_buffer_usage_ratio", PyFloat_FromDouble(usage_ratio));
    SET_ITEM("send_buffer_usage_ratio", PyFloat_FromDouble(usage_ratio));
    SET_ITEM("total_connections", PyLong_FromUnsignedLong(counts.total_connections));
    SET_ITEM("tcp_connections", PyLong_FromUnsignedLong(counts.total_connections));
    SET_ITEM("established_connections", PyLong_FromUnsignedLong(counts.established_connections));

#undef SET_ITEM

    return result;
}

static PyMethodDef SocketMetricsMethods[] = {
    {"get_socket_metrics", (PyCFunction)py_get_socket_metrics, METH_NOARGS, "Get aggregated socket buffer metrics"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef socketmetricsmodule = {
    PyModuleDef_HEAD_INIT,
    "socket_metrics",
    "Native socket metrics collector",
    -1,
    SocketMetricsMethods,
};

PyMODINIT_FUNC PyInit_socket_metrics(void) {
    if (!ensure_wsa_started()) {
        return NULL;
    }
    return PyModule_Create(&socketmetricsmodule);
}


