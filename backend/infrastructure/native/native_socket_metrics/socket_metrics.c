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

typedef struct {
    unsigned long pid;
    unsigned long count;
} pid_count_entry;

typedef struct {
    unsigned long total_connections;
    unsigned long established_connections;
} tcp_snapshot_t;

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

static const char *tcp_state_to_string(DWORD state) {
    switch (state) {
        case MIB_TCP_STATE_CLOSED:
            return "CLOSED";
        case MIB_TCP_STATE_LISTEN:
            return "LISTEN";
        case MIB_TCP_STATE_SYN_SENT:
            return "SYN_SENT";
        case MIB_TCP_STATE_SYN_RCVD:
            return "SYN_RCVD";
        case MIB_TCP_STATE_ESTAB:
            return "ESTABLISHED";
        case MIB_TCP_STATE_FIN_WAIT1:
            return "FIN_WAIT_1";
        case MIB_TCP_STATE_FIN_WAIT2:
            return "FIN_WAIT_2";
        case MIB_TCP_STATE_CLOSE_WAIT:
            return "CLOSE_WAIT";
        case MIB_TCP_STATE_CLOSING:
            return "CLOSING";
        case MIB_TCP_STATE_LAST_ACK:
            return "LAST_ACK";
        case MIB_TCP_STATE_TIME_WAIT:
            return "TIME_WAIT";
        case MIB_TCP_STATE_DELETE_TCB:
            return "DELETE_TCB";
        default:
            return "UNKNOWN";
    }
}

static int increment_state_count(PyObject *state_counts, DWORD state) {
    const char *name = tcp_state_to_string(state);
    PyObject *key = PyUnicode_FromString(name);
    if (!key) {
        return 0;
    }
    PyObject *current = PyDict_GetItem(state_counts, key);
    PyObject *new_value = NULL;
    if (current) {
        long value = PyLong_AsLong(current);
        if (PyErr_Occurred()) {
            Py_DECREF(key);
            return 0;
        }
        new_value = PyLong_FromLong(value + 1);
    } else {
        new_value = PyLong_FromLong(1);
    }
    if (!new_value) {
        Py_DECREF(key);
        return 0;
    }
    if (PyDict_SetItem(state_counts, key, new_value) != 0) {
        Py_DECREF(new_value);
        Py_DECREF(key);
        return 0;
    }
    Py_DECREF(new_value);
    Py_DECREF(key);
    return 1;
}

static int increment_pid_count(PyObject *pid_counts, DWORD pid) {
    PyObject *key = PyLong_FromUnsignedLong(pid);
    if (!key) {
        return 0;
    }
    PyObject *current = PyDict_GetItem(pid_counts, key);
    PyObject *new_value = NULL;
    if (current) {
        unsigned long value = PyLong_AsUnsignedLong(current);
        if (PyErr_Occurred()) {
            Py_DECREF(key);
            return 0;
        }
        new_value = PyLong_FromUnsignedLong(value + 1);
    } else {
        new_value = PyLong_FromUnsignedLong(1);
    }
    if (!new_value) {
        Py_DECREF(key);
        return 0;
    }
    if (PyDict_SetItem(pid_counts, key, new_value) != 0) {
        Py_DECREF(new_value);
        Py_DECREF(key);
        return 0;
    }
    Py_DECREF(new_value);
    Py_DECREF(key);
    return 1;
}

static int collect_tcp_table(int family, tcp_snapshot_t *snapshot, PyObject *state_counts, PyObject *pid_counts) {
    DWORD size = 0;
    DWORD result = GetExtendedTcpTable(NULL, &size, FALSE, (ULONG)family, TCP_TABLE_OWNER_PID_ALL, 0);
    if (result != ERROR_INSUFFICIENT_BUFFER) {
        if (result == ERROR_NOT_SUPPORTED || result == ERROR_INVALID_PARAMETER) {
            return 1;
        }
        PyErr_Format(PyExc_RuntimeError, "GetExtendedTcpTable pre-call failed (family=%d): %lu", family, result);
        return 0;
    }

    BYTE *buffer = (BYTE *)PyMem_Malloc(size);
    if (!buffer) {
        PyErr_NoMemory();
        return 0;
    }

    result = GetExtendedTcpTable(buffer, &size, FALSE, (ULONG)family, TCP_TABLE_OWNER_PID_ALL, 0);
    if (result != NO_ERROR) {
        PyMem_Free(buffer);
        if (result == ERROR_NOT_SUPPORTED || result == ERROR_INVALID_PARAMETER) {
            return 1;
        }
        PyErr_Format(PyExc_RuntimeError, "GetExtendedTcpTable failed (family=%d): %lu", family, result);
        return 0;
    }

    if (family == AF_INET) {
        PMIB_TCPTABLE_OWNER_PID table = (PMIB_TCPTABLE_OWNER_PID)buffer;
        snapshot->total_connections += table->dwNumEntries;
        for (DWORD i = 0; i < table->dwNumEntries; ++i) {
            MIB_TCPROW_OWNER_PID row = table->table[i];
            if (!increment_state_count(state_counts, row.dwState) ||
                !increment_pid_count(pid_counts, row.dwOwningPid)) {
                PyMem_Free(buffer);
                return 0;
            }
            if (row.dwState == MIB_TCP_STATE_ESTAB) {
                snapshot->established_connections += 1;
            }
        }
    } else {
        PMIB_TCP6TABLE_OWNER_PID table6 = (PMIB_TCP6TABLE_OWNER_PID)buffer;
        snapshot->total_connections += table6->dwNumEntries;
        for (DWORD i = 0; i < table6->dwNumEntries; ++i) {
            MIB_TCP6ROW_OWNER_PID row6 = table6->table[i];
            if (!increment_state_count(state_counts, row6.dwState) ||
                !increment_pid_count(pid_counts, row6.dwOwningPid)) {
                PyMem_Free(buffer);
                return 0;
            }
            if (row6.dwState == MIB_TCP_STATE_ESTAB) {
                snapshot->established_connections += 1;
            }
        }
    }

    PyMem_Free(buffer);
    return 1;
}

static int pid_entry_compare(const void *a, const void *b) {
    const pid_count_entry *pa = (const pid_count_entry *)a;
    const pid_count_entry *pb = (const pid_count_entry *)b;
    if (pa->count < pb->count) {
        return 1;
    }
    if (pa->count > pb->count) {
        return -1;
    }
    if (pa->pid < pb->pid) {
        return -1;
    }
    if (pa->pid > pb->pid) {
        return 1;
    }
    return 0;
}

static PyObject *build_pid_top_list(PyObject *pid_counts, size_t max_items) {
    Py_ssize_t dict_size = PyDict_Size(pid_counts);
    if (dict_size <= 0) {
        return PyList_New(0);
    }

    pid_count_entry *entries = (pid_count_entry *)PyMem_Malloc(sizeof(pid_count_entry) * (size_t)dict_size);
    if (!entries) {
        PyErr_NoMemory();
        return NULL;
    }

    Py_ssize_t pos = 0;
    PyObject *key, *value;
    size_t idx = 0;
    while (PyDict_Next(pid_counts, &pos, &key, &value)) {
        unsigned long pid = PyLong_AsUnsignedLong(key);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            continue;
        }
        unsigned long count = PyLong_AsUnsignedLong(value);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            count = 0;
        }
        entries[idx].pid = pid;
        entries[idx].count = count;
        idx += 1;
    }

    if (idx == 0) {
        PyMem_Free(entries);
        return PyList_New(0);
    }

    qsort(entries, idx, sizeof(pid_count_entry), pid_entry_compare);
    size_t limit = idx < max_items ? idx : max_items;
    PyObject *list = PyList_New((Py_ssize_t)limit);
    if (!list) {
        PyMem_Free(entries);
        return NULL;
    }

    for (size_t i = 0; i < limit; ++i) {
        PyObject *entry = Py_BuildValue("{s:k,s:k}", "pid", entries[i].pid, "connections", entries[i].count);
        if (!entry) {
            Py_DECREF(list);
            PyMem_Free(entries);
            return NULL;
        }
        PyList_SET_ITEM(list, (Py_ssize_t)i, entry);
    }

    PyMem_Free(entries);
    return list;
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

static PyObject *py_get_tcp_buffer_snapshot(PyObject *self, PyObject *Py_UNUSED(args)) {
    if (!ensure_wsa_started()) {
        return NULL;
    }

    PyObject *state_counts = PyDict_New();
    PyObject *pid_counts = PyDict_New();
    if (!state_counts || !pid_counts) {
        Py_XDECREF(state_counts);
        Py_XDECREF(pid_counts);
        return NULL;
    }

    tcp_snapshot_t snapshot = {0, 0};

    if (!collect_tcp_table(AF_INET, &snapshot, state_counts, pid_counts)) {
        Py_DECREF(state_counts);
        Py_DECREF(pid_counts);
        return NULL;
    }

    if (!collect_tcp_table(AF_INET6, &snapshot, state_counts, pid_counts)) {
        Py_DECREF(state_counts);
        Py_DECREF(pid_counts);
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
    if (snapshot.total_connections > 0) {
        usage_ratio = ((double)snapshot.established_connections / (double)snapshot.total_connections) * 100.0;
        if (usage_ratio > 100.0) {
            usage_ratio = 100.0;
        }
    }

    unsigned long long estimated_recv_bytes = (unsigned long long)recv_buf * (unsigned long long)snapshot.established_connections;
    unsigned long long estimated_send_bytes = (unsigned long long)send_buf * (unsigned long long)snapshot.established_connections;

    MIB_TCPSTATS stats_v4;
    MIB_TCPSTATS stats_v6;
    ZeroMemory(&stats_v4, sizeof(stats_v4));
    ZeroMemory(&stats_v6, sizeof(stats_v6));
    if (GetTcpStatisticsEx(&stats_v4, AF_INET) != NO_ERROR) {
        ZeroMemory(&stats_v4, sizeof(stats_v4));
    }
    if (GetTcpStatisticsEx(&stats_v6, AF_INET6) != NO_ERROR) {
        ZeroMemory(&stats_v6, sizeof(stats_v6));
    }
    unsigned long curr_established = stats_v4.dwCurrEstab + stats_v6.dwCurrEstab;

    PyObject *pid_top = build_pid_top_list(pid_counts, 10);
    Py_DECREF(pid_counts);
    if (!pid_top) {
        Py_DECREF(state_counts);
        return NULL;
    }

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(state_counts);
        Py_DECREF(pid_top);
        return NULL;
    }

#define SET_ITEM(key, value_expr)                                                                  \
    do {                                                                                           \
        PyObject *tmp_value = (value_expr);                                                        \
        if (tmp_value == NULL) {                                                                   \
            Py_DECREF(state_counts);                                                               \
            Py_DECREF(pid_top);                                                                    \
            Py_DECREF(result);                                                                     \
            return NULL;                                                                           \
        }                                                                                          \
        if (PyDict_SetItemString(result, (key), tmp_value) != 0) {                                 \
            Py_DECREF(tmp_value);                                                                  \
            Py_DECREF(state_counts);                                                               \
            Py_DECREF(pid_top);                                                                    \
            Py_DECREF(result);                                                                     \
            return NULL;                                                                           \
        }                                                                                          \
        Py_DECREF(tmp_value);                                                                      \
    } while (0)

    SET_ITEM("recv_buffer_size_avg", PyLong_FromLong(recv_buf));
    SET_ITEM("send_buffer_size_avg", PyLong_FromLong(send_buf));
    SET_ITEM("recv_buffer_size_min", PyLong_FromLong(recv_buf));
    SET_ITEM("recv_buffer_size_max", PyLong_FromLong(recv_buf));
    SET_ITEM("send_buffer_size_min", PyLong_FromLong(send_buf));
    SET_ITEM("send_buffer_size_max", PyLong_FromLong(send_buf));
    SET_ITEM("recv_buffer_usage_ratio", PyFloat_FromDouble(usage_ratio));
    SET_ITEM("send_buffer_usage_ratio", PyFloat_FromDouble(usage_ratio));
    SET_ITEM("total_connections", PyLong_FromUnsignedLong(snapshot.total_connections));
    SET_ITEM("tcp_connections", PyLong_FromUnsignedLong(snapshot.total_connections));
    SET_ITEM("established_connections", PyLong_FromUnsignedLong(snapshot.established_connections));
    SET_ITEM("established_current", PyLong_FromUnsignedLong(curr_established));
    SET_ITEM("default_recv_buffer", PyLong_FromLong(recv_buf));
    SET_ITEM("default_send_buffer", PyLong_FromLong(send_buf));
    SET_ITEM("estimated_recv_buffer_bytes", PyLong_FromUnsignedLongLong(estimated_recv_bytes));
    SET_ITEM("estimated_send_buffer_bytes", PyLong_FromUnsignedLongLong(estimated_send_bytes));
    SET_ITEM("estimated_usage_ratio", PyFloat_FromDouble(usage_ratio));
    SET_ITEM("timestamp", PyLong_FromUnsignedLongLong(GetTickCount64()));

#undef SET_ITEM

    if (PyDict_SetItemString(result, "state_counts", state_counts) != 0) {
        Py_DECREF(state_counts);
        Py_DECREF(pid_top);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(state_counts);

    if (PyDict_SetItemString(result, "per_pid_top", pid_top) != 0) {
        Py_DECREF(pid_top);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(pid_top);

    return result;
}

static PyMethodDef SocketMetricsMethods[] = {
    {"get_socket_metrics", (PyCFunction)py_get_socket_metrics, METH_NOARGS, "Get aggregated socket buffer metrics"},
    {"get_tcp_buffer_snapshot", (PyCFunction)py_get_tcp_buffer_snapshot, METH_NOARGS, "Get aggregated TCP buffer snapshot"},
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


