#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <tlhelp32.h>
#include <iphlpapi.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "iphlpapi.lib")

#include "../native_log_bridge.h"

#define PROCESS_METRICS_COMPONENT "backend.native.process_metrics.core"

static void process_metrics_log(
    int level,
    const char *function,
    int line,
    const char *message,
    const char *details
) {
    native_log_bridge_log(
        level,
        PROCESS_METRICS_COMPONENT,
        function,
        line,
        message,
        details);
}

static void log_windows_error(const char *function, int line, const char *context, DWORD error_code) {
    char details[256];
    snprintf(details, sizeof(details), "context=%s;win32_error=%lu", context ? context : "<unknown>", (unsigned long)error_code);
    process_metrics_log(NATIVE_LOG_LEVEL_ERROR, function, line, "Windows API call failed", details);
}

static void log_warning(const char *function, int line, const char *message, const char *details) {
    process_metrics_log(NATIVE_LOG_LEVEL_WARNING, function, line, message, details);
}

static void log_info_once(const char *function, int line, const char *message) {
    process_metrics_log(NATIVE_LOG_LEVEL_INFO, function, line, message, NULL);
}

static PyObject *g_process_times = NULL;
static double g_processor_count = 1.0;
static int g_cpu_initialized = 0;
static ULONGLONG g_prev_idle = 0;
static ULONGLONG g_prev_total = 0;
static PyObject *g_last_error = NULL;

static ULONGLONG
filetime_to_uint64(FILETIME ft)
{
    ULARGE_INTEGER ui;
    ui.LowPart = ft.dwLowDateTime;
    ui.HighPart = ft.dwHighDateTime;
    return ui.QuadPart;
}

static void
set_last_error(const char *context, DWORD error_code)
{
    log_windows_error(__FUNCTION__, __LINE__, context, error_code);
    PyObject *err_tuple;
    err_tuple = Py_BuildValue("(skI)", context, "win32", error_code);
    if (!err_tuple) {
        return;
    }
    Py_XDECREF(g_last_error);
    g_last_error = err_tuple;
}

static int
raise_windows_error(DWORD err, const char *context)
{
    set_last_error(context, err);
    if (err == ERROR_ACCESS_DENIED) {
        PyErr_SetExcFromWindowsErrWithFilenameObject(PyExc_PermissionError, err, NULL);
        return -1;
    }
    if (err == ERROR_NOT_SUPPORTED || err == ERROR_CALL_NOT_IMPLEMENTED) {
        PyErr_SetString(PyExc_NotImplementedError, context);
        return -1;
    }
    PyErr_SetFromWindowsErr(err);
    return -1;
}

static PyObject *
build_load_average_list(void)
{
    PyObject *list = PyList_New(3);
    int i;
    if (!list) {
        return NULL;
    }
    for (i = 0; i < 3; ++i) {
        PyList_SET_ITEM(list, i, PyFloat_FromDouble(0.0));
    }
    return list;
}

static int
get_network_counters(unsigned long long *in_bytes, unsigned long long *out_bytes)
{
    DWORD size = 0;
    DWORD result = GetIfTable(NULL, &size, FALSE);
    if (result != ERROR_INSUFFICIENT_BUFFER) {
        log_windows_error(__FUNCTION__, __LINE__, "GetIfTable probe failed", result);
        return -1;
    }

    PMIB_IFTABLE table = (PMIB_IFTABLE)PyMem_Malloc(size);
    if (!table) {
        log_warning(__FUNCTION__, __LINE__, "PyMem_Malloc failed in get_network_counters", NULL);
        return -1;
    }

    result = GetIfTable(table, &size, FALSE);
    if (result != NO_ERROR) {
        log_windows_error(__FUNCTION__, __LINE__, "GetIfTable", result);
        PyMem_Free(table);
        return -1;
    }

    unsigned long long in_total = 0;
    unsigned long long out_total = 0;

    {
        DWORD i;
        for (i = 0; i < table->dwNumEntries; ++i) {
            MIB_IFROW row = table->table[i];
        if (row.dwType == IF_TYPE_SOFTWARE_LOOPBACK) {
            continue;
        }
        in_total += row.dwInOctets;
        out_total += row.dwOutOctets;
    }
    }

    PyMem_Free(table);
    *in_bytes = in_total;
    *out_bytes = out_total;

    return 0;
}

static double
calculate_cpu_percent(void)
{
    FILETIME idle_ft, kernel_ft, user_ft;
    if (!GetSystemTimes(&idle_ft, &kernel_ft, &user_ft)) {
        return 0.0;
    }

    ULONGLONG idle = filetime_to_uint64(idle_ft);
    ULONGLONG kernel = filetime_to_uint64(kernel_ft);
    ULONGLONG user = filetime_to_uint64(user_ft);
    ULONGLONG total = kernel + user;

    if (!g_cpu_initialized) {
        g_prev_idle = idle;
        g_prev_total = total;
        g_cpu_initialized = 1;
        return 0.0;
    }

    ULONGLONG idle_diff = idle - g_prev_idle;
    ULONGLONG total_diff = total - g_prev_total;

    g_prev_idle = idle;
    g_prev_total = total;

    if (total_diff == 0) {
        return 0.0;
    }

    double usage = (double)(total_diff - idle_diff) / (double)total_diff;
    if (usage < 0.0) {
        usage = 0.0;
    }
    if (usage > 1.0) {
        usage = 1.0;
    }
    return usage * 100.0;
}

static PyObject *
get_system_metrics(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    MEMORYSTATUSEX mem_status;
    mem_status.dwLength = sizeof(mem_status);
    if (!GlobalMemoryStatusEx(&mem_status)) {
        log_windows_error(__FUNCTION__, __LINE__, "GlobalMemoryStatusEx", GetLastError());
        PyErr_SetFromWindowsErr(GetLastError());
        return NULL;
    }

    ULONGLONG total_bytes = mem_status.ullTotalPhys;
    ULONGLONG used_bytes = total_bytes - mem_status.ullAvailPhys;
    double memory_percent = total_bytes == 0 ? 0.0 : (double)used_bytes * 100.0 / (double)total_bytes;

    unsigned long long net_in = 0;
    unsigned long long net_out = 0;
    if (get_network_counters(&net_in, &net_out) != 0) {
        log_warning(__FUNCTION__, __LINE__, "Failed to query interface traffic, using zeros", NULL);
    }

    ULONGLONG free_bytes = 0;
    ULONGLONG total_disk = 0;
    double disk_percent = 0.0;
    ULARGE_INTEGER free_available, total_space, total_free;
    if (GetDiskFreeSpaceExW(L"C:\\", &free_available, &total_space, &total_free)) {
        total_disk = total_space.QuadPart;
        free_bytes = total_free.QuadPart;
        if (total_disk > 0) {
            disk_percent = (double)(total_disk - free_bytes) * 100.0 / (double)total_disk;
        }
    } else {
        log_windows_error(__FUNCTION__, __LINE__, "GetDiskFreeSpaceExW", GetLastError());
    }

    DWORD process_ids[2048];
    DWORD bytes_returned = 0;
    DWORD process_count = 0;
    if (EnumProcesses(process_ids, sizeof(process_ids), &bytes_returned)) {
        process_count = bytes_returned / sizeof(DWORD);
    }

    PyObject *metrics = PyDict_New();
    if (!metrics) {
        log_warning(__FUNCTION__, __LINE__, "Failed to allocate metrics dictionary", NULL);
        return NULL;
    }

    PyObject *load_list = build_load_average_list();
    if (!load_list) {
        Py_DECREF(metrics);
        return NULL;
    }

    PyDict_SetItemString(metrics, "cpu_percent", PyFloat_FromDouble(calculate_cpu_percent()));
    PyDict_SetItemString(metrics, "memory_percent", PyFloat_FromDouble(memory_percent));
    PyDict_SetItemString(metrics, "disk_percent", PyFloat_FromDouble(disk_percent));
    PyDict_SetItemString(metrics, "net_recv_bytes", PyLong_FromUnsignedLongLong(net_in));
    PyDict_SetItemString(metrics, "net_sent_bytes", PyLong_FromUnsignedLongLong(net_out));
    PyDict_SetItemString(metrics, "process_count", PyLong_FromUnsignedLong(process_count));
    PyDict_SetItemString(metrics, "timestamp", PyLong_FromUnsignedLongLong(GetTickCount64()));
    PyDict_SetItemString(metrics, "load_average", load_list);

    return metrics;
}

static DWORD
count_threads_for_pid(DWORD pid)
{
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return 0;
    }

    THREADENTRY32 entry;
    entry.dwSize = sizeof(entry);
    DWORD count = 0;
    if (Thread32First(snapshot, &entry)) {
        do {
            if (entry.th32OwnerProcessID == pid) {
                ++count;
            }
        } while (Thread32Next(snapshot, &entry));
    }

    CloseHandle(snapshot);
    return count;
}

static DWORD
count_all_threads(void)
{
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return 0;
    }

    THREADENTRY32 entry;
    entry.dwSize = sizeof(entry);
    DWORD count = 0;
    if (Thread32First(snapshot, &entry)) {
        do {
            ++count;
        } while (Thread32Next(snapshot, &entry));
    }

    CloseHandle(snapshot);
    return count;
}

static double
calculate_process_cpu_percent(DWORD pid, ULONGLONG proc_total_100ns, ULONGLONG timestamp_ms)
{
    if (!g_process_times) {
        return 0.0;
    }

    PyObject *pid_key = PyLong_FromUnsignedLong(pid);
    if (!pid_key) {
        return 0.0;
    }

    PyObject *prev = PyDict_GetItem(g_process_times, pid_key);
    double cpu_percent = 0.0;

    if (prev && PyTuple_Check(prev) && PyTuple_Size(prev) == 2) {
        PyObject *prev_total_obj = PyTuple_GET_ITEM(prev, 0);
        PyObject *prev_time_obj = PyTuple_GET_ITEM(prev, 1);
        ULONGLONG prev_total = PyLong_AsUnsignedLongLong(prev_total_obj);
        ULONGLONG prev_time = PyLong_AsUnsignedLongLong(prev_time_obj);

        ULONGLONG total_diff = proc_total_100ns - prev_total;
        ULONGLONG time_diff = timestamp_ms - prev_time;

        if (time_diff > 0 && total_diff > 0) {
            double cpu_time_seconds = (double)total_diff / 10000000.0;
            double elapsed_seconds = (double)time_diff / 1000.0;
            if (elapsed_seconds > 0.0) {
                cpu_percent = (cpu_time_seconds / elapsed_seconds) * 100.0 / g_processor_count;
            }
        }
    }

    PyObject *tuple = Py_BuildValue("KK", proc_total_100ns, timestamp_ms);
    if (tuple) {
        PyDict_SetItem(g_process_times, pid_key, tuple);
        Py_DECREF(tuple);
    }

    Py_DECREF(pid_key);
    return cpu_percent;
}

static PyObject *
make_process_snapshot(DWORD pid, MEMORYSTATUSEX *mem_status)
{
    HANDLE handle = OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
        FALSE,
        pid
    );

    if (!handle) {
        DWORD err = GetLastError();
        raise_windows_error(err, "OpenProcess failed");
        return NULL;
    }

    PyObject *result = PyDict_New();
    if (!result) {
        CloseHandle(handle);
        log_warning(__FUNCTION__, __LINE__, "Failed to allocate process snapshot dictionary", NULL);
        return NULL;
    }

    PROCESS_MEMORY_COUNTERS_EX pmc;
    memset(&pmc, 0, sizeof(pmc));
    pmc.cb = sizeof(pmc);
    GetProcessMemoryInfo(handle, (PROCESS_MEMORY_COUNTERS *)&pmc, sizeof(pmc));

    IO_COUNTERS io_counters;
    memset(&io_counters, 0, sizeof(io_counters));
    GetProcessIoCounters(handle, &io_counters);

    FILETIME create_time, exit_time, kernel_time, user_time;
    GetProcessTimes(handle, &create_time, &exit_time, &kernel_time, &user_time);
    ULONGLONG kernel = filetime_to_uint64(kernel_time);
    ULONGLONG user = filetime_to_uint64(user_time);
    ULONGLONG proc_total = kernel + user;
    ULONGLONG now_ms = GetTickCount64();

    double memory_percent = 0.0;
    if (mem_status && mem_status->ullTotalPhys > 0) {
        memory_percent = (double)pmc.WorkingSetSize * 100.0 / (double)mem_status->ullTotalPhys;
    }

    DWORD handle_count = 0;
    GetProcessHandleCount(handle, &handle_count);

    DWORD thread_count = count_threads_for_pid(pid);

    WCHAR image_path[MAX_PATH];
    DWORD path_len = MAX_PATH;
    image_path[0] = L'\0';
    QueryFullProcessImageNameW(handle, 0, image_path, &path_len);

    PyObject *path_py = PyUnicode_FromWideChar(image_path, (Py_ssize_t)wcslen(image_path));
    PyObject *name_py = NULL;
    if (path_py && PyUnicode_Check(path_py)) {
        PyObject *parts = NULL;
        PyObject *sep = PyUnicode_FromString("\\");
        if (sep) {
            parts = PyUnicode_Split(path_py, sep, -1);
            Py_DECREF(sep);
        }
        if (parts && PyList_Size(parts) > 0) {
            PyObject *last = PyList_GetItem(parts, PyList_Size(parts) - 1);
            if (last) {
                name_py = PyUnicode_FromObject(last);
            }
        }
        Py_XDECREF(parts);
    }
    if (!name_py) {
        name_py = PyUnicode_FromFormat("pid_%lu", pid);
    }

    PyObject *cmdline_list = PyList_New(0);
    PyObject *children_list = PyList_New(0);

    double cpu_percent = calculate_process_cpu_percent(pid, proc_total, now_ms);

    PyDict_SetItemString(result, "pid", PyLong_FromUnsignedLong(pid));
    PyDict_SetItemString(result, "name", name_py ? name_py : PyUnicode_FromString(""));
    PyDict_SetItemString(result, "exe", path_py ? path_py : PyUnicode_FromString(""));
    PyDict_SetItemString(result, "cpu_percent", PyFloat_FromDouble(cpu_percent));
    PyDict_SetItemString(result, "memory_percent", PyFloat_FromDouble(memory_percent));
    PyDict_SetItemString(result, "memory_rss", PyLong_FromUnsignedLongLong(pmc.WorkingSetSize));
    PyDict_SetItemString(result, "memory_vms", PyLong_FromUnsignedLongLong(pmc.PrivateUsage));
    PyDict_SetItemString(result, "io_read_bytes", PyLong_FromUnsignedLongLong(io_counters.ReadTransferCount));
    PyDict_SetItemString(result, "io_write_bytes", PyLong_FromUnsignedLongLong(io_counters.WriteTransferCount));
    PyDict_SetItemString(result, "num_threads", PyLong_FromUnsignedLong(thread_count));
    PyDict_SetItemString(result, "handles", PyLong_FromUnsignedLong(handle_count));
    PyDict_SetItemString(result, "status", PyUnicode_FromString("running"));
    PyDict_SetItemString(result, "cmdline", cmdline_list);
    PyDict_SetItemString(result, "children", children_list);
    PyDict_SetItemString(result, "timestamp", PyLong_FromUnsignedLongLong(now_ms));

    Py_XDECREF(path_py);
    Py_XDECREF(name_py);
    CloseHandle(handle);

    return result;
}

static PyObject *
get_process_snapshot(PyObject *Py_UNUSED(self), PyObject *args)
{
    unsigned long pid = 0;
    if (!PyArg_ParseTuple(args, "k", &pid)) {
        return NULL;
    }

    MEMORYSTATUSEX mem_status;
    mem_status.dwLength = sizeof(mem_status);
    GlobalMemoryStatusEx(&mem_status);

    if (pid == 0) {
        DWORD process_ids[4096];
        DWORD bytes_returned = 0;
        DWORD process_count = 0;
        if (EnumProcesses(process_ids, sizeof(process_ids), &bytes_returned)) {
            process_count = bytes_returned / sizeof(DWORD);
        } else {
            DWORD err = GetLastError();
            raise_windows_error(err, "EnumProcesses failed");
            return NULL;
        }

        PyObject *aggregate = PyDict_New();
        PyObject *result = PyDict_New();
        if (!aggregate || !result) {
            Py_XDECREF(aggregate);
            Py_XDECREF(result);
            return NULL;
        }

        PyDict_SetItemString(aggregate, "process_count", PyLong_FromUnsignedLong(process_count));
        PyDict_SetItemString(aggregate, "thread_count", PyLong_FromUnsignedLong(count_all_threads()));
        PyDict_SetItemString(aggregate, "timestamp", PyLong_FromUnsignedLongLong(GetTickCount64()));

        PyDict_SetItemString(result, "processes", PyList_New(0));
        PyDict_SetItemString(result, "aggregate", aggregate);
        Py_DECREF(aggregate);
        return result;
    }

    return make_process_snapshot((DWORD)pid, &mem_status);
}

typedef struct {
    PyObject *dict;
    double sort_value;
} ProcessEntry;

static double
extract_sort_value(PyObject *snapshot, const char *key)
{
    PyObject *value_obj = PyDict_GetItemString(snapshot, key);
    double value = 0.0;
    if (!value_obj) {
        return 0.0;
    }
    if (PyFloat_Check(value_obj) || PyLong_Check(value_obj)) {
        value = PyFloat_AsDouble(value_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            value = 0.0;
        }
        return value;
    }
    PyObject *tmp = PyNumber_Float(value_obj);
    if (!tmp) {
        PyErr_Clear();
        return 0.0;
    }
    value = PyFloat_AsDouble(tmp);
    Py_DECREF(tmp);
    if (PyErr_Occurred()) {
        PyErr_Clear();
        return 0.0;
    }
    return value;
}

static int
process_entry_compare(const void *a, const void *b)
{
    const ProcessEntry *pa = (const ProcessEntry *)a;
    const ProcessEntry *pb = (const ProcessEntry *)b;
    if (pa->sort_value > pb->sort_value) {
        return -1;
    }
    if (pa->sort_value < pb->sort_value) {
        return 1;
    }
    return 0;
}

static PyObject *
enumerate_processes(PyObject *Py_UNUSED(self), PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"limit", "sort_key", NULL};
    Py_ssize_t limit = 50;
    const char *sort_key = "memory_rss";

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|ns", kwlist, &limit, &sort_key)) {
        return NULL;
    }
    if (limit <= 0) {
        limit = 50;
    }

    DWORD process_ids[32768];
    DWORD bytes_returned = 0;
    if (!EnumProcesses(process_ids, sizeof(process_ids), &bytes_returned)) {
        DWORD err = GetLastError();
        raise_windows_error(err, "EnumProcesses failed");
        return NULL;
    }

    DWORD process_count = bytes_returned / sizeof(DWORD);
    MEMORYSTATUSEX mem_status;
    mem_status.dwLength = sizeof(mem_status);
    GlobalMemoryStatusEx(&mem_status);

    ProcessEntry *entries = PyMem_Calloc(process_count, sizeof(ProcessEntry));
    if (!entries) {
        PyErr_NoMemory();
        log_warning(__FUNCTION__, __LINE__, "PyMem_Calloc failed in enumerate_processes", NULL);
        return NULL;
    }

    Py_ssize_t entry_count = 0;
    for (DWORD i = 0; i < process_count; ++i) {
        DWORD pid = process_ids[i];
        if (pid == 0) {
            continue;
        }

        PyObject *snapshot = make_process_snapshot(pid, &mem_status);
        if (!snapshot) {
            if (PyErr_Occurred()) {
                PyErr_Clear();
                log_warning(__FUNCTION__, __LINE__, "make_process_snapshot returned NULL, skipping", NULL);
            }
            continue;
        }

        double value = extract_sort_value(snapshot, sort_key);
        entries[entry_count].dict = snapshot;
        entries[entry_count].sort_value = value;
        entry_count += 1;
    }

    if (entry_count > 1) {
        qsort(entries, (size_t)entry_count, sizeof(ProcessEntry), process_entry_compare);
    }

    Py_ssize_t limited = entry_count < limit ? entry_count : limit;
    PyObject *result_list = PyList_New(limited);
    if (!result_list) {
        for (Py_ssize_t idx = 0; idx < entry_count; ++idx) {
            Py_DECREF(entries[idx].dict);
        }
        PyMem_Free(entries);
        log_warning(__FUNCTION__, __LINE__, "Failed to allocate result list in enumerate_processes", NULL);
        return NULL;
    }

    for (Py_ssize_t idx = 0; idx < limited; ++idx) {
        PyList_SET_ITEM(result_list, idx, entries[idx].dict);
        entries[idx].dict = NULL;
    }

    for (Py_ssize_t idx = limited; idx < entry_count; ++idx) {
        Py_DECREF(entries[idx].dict);
    }

    PyMem_Free(entries);

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(result_list);
        log_warning(__FUNCTION__, __LINE__, "Failed to allocate result dictionary in enumerate_processes", NULL);
        return NULL;
    }

    PyObject *total_obj = PyLong_FromSsize_t(entry_count);
    PyObject *limit_obj = PyLong_FromSsize_t(limit);
    PyObject *sort_obj = PyUnicode_FromString(sort_key);
    PyObject *timestamp_obj = PyLong_FromUnsignedLongLong(GetTickCount64());

    if (!total_obj || !limit_obj || !sort_obj || !timestamp_obj) {
        Py_XDECREF(total_obj);
        Py_XDECREF(limit_obj);
        Py_XDECREF(sort_obj);
        Py_XDECREF(timestamp_obj);
        Py_DECREF(result_list);
        Py_DECREF(result);
        return NULL;
    }

    PyDict_SetItemString(result, "processes", result_list);
    PyDict_SetItemString(result, "total", total_obj);
    PyDict_SetItemString(result, "limit", limit_obj);
    PyDict_SetItemString(result, "sort_key", sort_obj);
    PyDict_SetItemString(result, "timestamp", timestamp_obj);

    Py_DECREF(result_list);
    Py_DECREF(total_obj);
    Py_DECREF(limit_obj);
    Py_DECREF(sort_obj);
    Py_DECREF(timestamp_obj);

    return result;
}

static PyObject *
get_last_error(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    if (!g_last_error) {
        Py_RETURN_NONE;
    }
    Py_INCREF(g_last_error);
    return g_last_error;
}

static PyMethodDef module_methods[] = {
    {"get_system_metrics", (PyCFunction)get_system_metrics, METH_NOARGS, PyDoc_STR("Return system metrics dictionary")},
    {"get_process_snapshot", (PyCFunction)get_process_snapshot, METH_VARARGS, PyDoc_STR("Return process snapshot dictionary")},
    {"get_last_error", (PyCFunction)get_last_error, METH_NOARGS, PyDoc_STR("Return last Windows error tuple")},
    {"enumerate_processes", (PyCFunction)enumerate_processes, METH_VARARGS | METH_KEYWORDS, PyDoc_STR("enumerate_processes(limit=50, sort_key='memory_rss') -> dict")},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_process_metrics.process_metrics",
    .m_doc = "Native process metrics module",
    .m_size = -1,
    .m_methods = module_methods,
};

PyMODINIT_FUNC
PyInit_process_metrics(void)
{
    SYSTEM_INFO sys_info;
    GetSystemInfo(&sys_info);
    if (sys_info.dwNumberOfProcessors > 0) {
        g_processor_count = (double)sys_info.dwNumberOfProcessors;
    }

    PyObject *module = PyModule_Create(&module_def);
    if (!module) {
        log_warning(__FUNCTION__, __LINE__, "PyModule_Create failed for process_metrics", NULL);
        return NULL;
    }

    g_last_error = Py_None;
    Py_INCREF(Py_None);

    g_process_times = PyDict_New();
    if (!g_process_times) {
        Py_DECREF(g_last_error);
        Py_DECREF(module);
        log_warning(__FUNCTION__, __LINE__, "Failed to allocate process times cache", NULL);
        return NULL;
    }

    PyObject *available = PyBool_FromLong(1);
    if (!available) {
        Py_DECREF(g_process_times);
        Py_DECREF(g_last_error);
        Py_DECREF(module);
        log_warning(__FUNCTION__, __LINE__, "Failed to create availability flag", NULL);
        return NULL;
    }
    if (PyModule_AddObject(module, "PROCESS_METRICS_AVAILABLE", available) < 0) {
        Py_DECREF(available);
        Py_DECREF(g_process_times);
        Py_DECREF(g_last_error);
        Py_DECREF(module);
        return NULL;
    }

    if (PyModule_AddObject(module, "_process_times_cache", g_process_times) < 0) {
        Py_DECREF(g_process_times);
        Py_DECREF(g_last_error);
        Py_DECREF(module);
        log_warning(__FUNCTION__, __LINE__, "Failed to add process times cache to module", NULL);
        return NULL;
    }

    Py_INCREF(g_process_times);

    if (PyModule_AddObject(module, "LAST_ERROR", g_last_error) < 0) {
        Py_DECREF(g_process_times);
        Py_DECREF(g_last_error);
        Py_DECREF(module);
        log_warning(__FUNCTION__, __LINE__, "Failed to expose LAST_ERROR", NULL);
        return NULL;
    }

    log_info_once(__FUNCTION__, __LINE__, "native_process_metrics module initialised");
    return module;
}

