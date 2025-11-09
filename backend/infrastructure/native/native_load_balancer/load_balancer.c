/* -*- coding: utf-8 -*- */
/*
 * load_balancer.c - 负载均衡配置原生优化
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>

/* NativeLogBridge declarations */
static PyObject *g_log_bridge_module = NULL;
static PyObject *g_log_from_native_func = NULL;

/* Log level constants matching Python side */
#define NATIVE_LOG_DEBUG 10
#define NATIVE_LOG_INFO 20
#define NATIVE_LOG_WARNING 30
#define NATIVE_LOG_ERROR 40
#define NATIVE_LOG_CRITICAL 50

/* 统一组件命名，符合统一日志规范 */
#define NATIVE_COMPONENT "backend.native.load_balancer.core"

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

static void native_log_info(const char *component, const char *function, int line, const char *message, const char *details) {
    native_log(NATIVE_LOG_INFO, component, function, line, message, details);
}

static void native_log_error(const char *component, const char *function, int line, const char *message, const char *details) {
    native_log(NATIVE_LOG_ERROR, component, function, line, message, details);
}

static long clamp_long(long value, long min_value, long max_value)
{
    if (value < min_value) {
        return min_value;
    }
    if (max_value > 0 && value > max_value) {
        return max_value;
    }
    return value;
}

static long round_up_positive(double value)
{
    if (value <= 0.0) {
        return 0;
    }
    return (long)ceil(value);
}

static unsigned long long min_ull(unsigned long long a, unsigned long long b)
{
    return (a < b) ? a : b;
}

static void adjust_to_target_total(
    unsigned long long target_total,
    long min_coroutines,
    long max_coroutines,
    long max_processes,
    long *processes,
    long *coroutines)
{
    if (target_total == 0ULL) {
        target_total = 1ULL;
    }

    long proc = (*processes < 1) ? 1 : *processes;
    if (max_processes > 0 && proc > max_processes) {
        proc = max_processes;
    }

    unsigned long long max_proc_by_target = target_total / (unsigned long long)((min_coroutines < 1) ? 1 : min_coroutines);
    if (max_proc_by_target == 0ULL) {
        max_proc_by_target = 1ULL;
    }
    if ((unsigned long long)proc > max_proc_by_target) {
        proc = (long)max_proc_by_target;
        if (proc < 1) {
            proc = 1;
        }
    }

    unsigned long long per_process = target_total / (unsigned long long)proc;
    if (per_process == 0ULL) {
        per_process = 1ULL;
    }

    long coro = (long)per_process;
    if (coro < min_coroutines) {
        coro = min_coroutines;
    }
    if (max_coroutines > 0 && coro > max_coroutines) {
        coro = max_coroutines;
    }

    unsigned long long total = (unsigned long long)proc * (unsigned long long)coro;
    if (total > target_total) {
        unsigned long long max_allowed = target_total / (unsigned long long)proc;
        if (max_allowed == 0ULL) {
            max_allowed = 1ULL;
        }
        if (max_allowed < (unsigned long long)min_coroutines) {
            max_allowed = (unsigned long long)min_coroutines;
        }
        if (max_coroutines > 0 && max_allowed > (unsigned long long)max_coroutines) {
            max_allowed = (unsigned long long)max_coroutines;
        }
        coro = (long)max_allowed;
        total = (unsigned long long)proc * (unsigned long long)coro;

        while (total > target_total && coro > min_coroutines) {
            coro--;
            total -= (unsigned long long)proc;
        }

        if (total > target_total && proc > 1) {
            long new_proc = (long)((target_total + (unsigned long long)coro - 1ULL) / (unsigned long long)coro);
            if (new_proc < 1) {
                new_proc = 1;
            }
            if (new_proc < proc) {
                proc = new_proc;
                if (proc > max_processes && max_processes > 0) {
                    proc = max_processes;
                }
                total = (unsigned long long)proc * (unsigned long long)coro;
                while (total > target_total && coro > min_coroutines) {
                    coro--;
                    total -= (unsigned long long)proc;
                }
            }
        }
    } else if (total < target_total) {
        while (coro < max_coroutines || max_coroutines <= 0) {
            unsigned long long next_total = (unsigned long long)proc * (unsigned long long)(coro + 1);
            if (next_total > target_total) {
                break;
            }
            coro += 1;
        }
    }

    if (proc < 1) {
        proc = 1;
    }
    if (coro < 1) {
        coro = 1;
    }

    *processes = proc;
    *coroutines = coro;
}

static PyObject *
py_optimize(PyObject *Py_UNUSED(self), PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {
        "bottleneck_value",
        "queue_factor",
        "base_processes",
        "base_coroutines",
        "max_processes",
        "max_coroutines",
        "min_coroutines",
        "total_max_connections",
        "task_total_count",
        NULL
    };

    double bottleneck_value = 50.0;
    double queue_factor = 1.0;
    long base_processes = 1;
    long base_coroutines = 10;
    long max_processes = 1;
    long max_coroutines = 10;
    long min_coroutines = 10;
    unsigned long long total_max_connections = 0;
    unsigned long long task_total_count = 0;

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "ddlllllKK:optimize",
            kwlist,
            &bottleneck_value,
            &queue_factor,
            &base_processes,
            &base_coroutines,
            &max_processes,
            &max_coroutines,
            &min_coroutines,
            &total_max_connections,
            &task_total_count)) {
        native_log_error(NATIVE_COMPONENT, "py_optimize", __LINE__, "Failed to parse optimize arguments", "invalid_arguments");
        return NULL;
    }

    /* Log optimization start */
    char opt_details[256];
    sprintf(opt_details, "bottleneck=%.1f, queue_factor=%.1f, tasks=%llu",
            bottleneck_value, queue_factor, task_total_count);
    native_log_info(NATIVE_COMPONENT, "py_optimize", __LINE__, "Starting load balancing optimization", opt_details);

    if (base_processes < 1) base_processes = 1;
    if (base_coroutines < 1) base_coroutines = 1;
    if (min_coroutines < 1) min_coroutines = 1;
    if (max_processes < 1) max_processes = 1;
    if (max_coroutines < 1) max_coroutines = 1;

    double resource_scale = 1.0;
    if (bottleneck_value > 80.0) {
        resource_scale = 0.3;
    } else if (bottleneck_value > 60.0) {
        resource_scale = 0.6;
    } else if (bottleneck_value > 40.0) {
        resource_scale = 1.0;
    } else {
        resource_scale = 1.6;
    }

    long base_proc_scaled = round_up_positive((double)base_processes * resource_scale);
    long base_coro_scaled = round_up_positive((double)base_coroutines * resource_scale);
    base_proc_scaled = clamp_long(base_proc_scaled, 1, max_processes);
    base_coro_scaled = clamp_long(base_coro_scaled, min_coroutines, max_coroutines);

    unsigned long long pre_constraint_concurrency =
        (unsigned long long)base_proc_scaled * (unsigned long long)base_coro_scaled;

    double effective_queue = (queue_factor > 0.0) ? queue_factor : 1.0;
    long processes = round_up_positive((double)base_proc_scaled * effective_queue);
    long coroutines = round_up_positive((double)base_coro_scaled * effective_queue);
    processes = clamp_long(processes, 1, max_processes);
    coroutines = clamp_long(coroutines, min_coroutines, max_coroutines);

    unsigned long long unconstrained_concurrency =
        (unsigned long long)processes * (unsigned long long)coroutines;

    int server_constrained = 0;
    if (total_max_connections > 0ULL &&
        (pre_constraint_concurrency > total_max_connections || unconstrained_concurrency > total_max_connections)) {
        server_constrained = 1;
    }

    int task_constrained = 0;
    if (task_total_count > 0ULL &&
        (pre_constraint_concurrency > task_total_count || unconstrained_concurrency > task_total_count)) {
        task_constrained = 1;
    }

    unsigned long long target_total = unconstrained_concurrency;
    if (total_max_connections > 0ULL && target_total > total_max_connections) {
        target_total = total_max_connections;
    }
    if (task_total_count > 0ULL && target_total > task_total_count) {
        target_total = task_total_count;
    }

    unsigned long long max_capacity = (unsigned long long)max_processes * (unsigned long long)max_coroutines;
    if (max_capacity > 0ULL) {
        target_total = min_ull(target_total, max_capacity);
    }

    adjust_to_target_total(
        target_total,
        min_coroutines,
        max_coroutines,
        max_processes,
        &processes,
        &coroutines);

    unsigned long long total_concurrency =
        (unsigned long long)processes * (unsigned long long)coroutines;

    PyObject *result = PyDict_New();
    if (!result) {
        return NULL;
    }

    PyObject *value = PyLong_FromLong(processes);
    if (!value || PyDict_SetItemString(result, "processes", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyLong_FromLong(coroutines);
    if (!value || PyDict_SetItemString(result, "coroutines_per_process", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyBool_FromLong(server_constrained);
    if (!value || PyDict_SetItemString(result, "server_constrained", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyBool_FromLong(task_constrained);
    if (!value || PyDict_SetItemString(result, "task_constrained", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyFloat_FromDouble(resource_scale);
    if (!value || PyDict_SetItemString(result, "resource_scale", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyFloat_FromDouble(queue_factor);
    if (!value || PyDict_SetItemString(result, "queue_factor", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyLong_FromUnsignedLongLong(total_concurrency);
    if (!value || PyDict_SetItemString(result, "total_concurrency", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyLong_FromUnsignedLongLong(total_max_connections);
    if (!value || PyDict_SetItemString(result, "total_max_connections", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    value = PyLong_FromUnsignedLongLong(task_total_count);
    if (!value || PyDict_SetItemString(result, "task_total_count", value) != 0) {
        Py_XDECREF(value);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(value);

    return result;
}

static PyMethodDef LoadBalancerMethods[] = {
    {"optimize", (PyCFunction)py_optimize, METH_VARARGS | METH_KEYWORDS, "Optimize load balancing configuration"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef loadbalancermodule = {
    PyModuleDef_HEAD_INIT,
    "load_balancer",
    "Native load balancer optimizer",
    -1,
    LoadBalancerMethods,
};

PyMODINIT_FUNC
PyInit_load_balancer(void)
{
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
        native_log_info(NATIVE_COMPONENT, "PyInit_load_balancer", __LINE__, "Logging bridge initialized successfully", NULL);
    } else {
        /* Logging bridge not available, continue without logging */
        Py_XDECREF(g_log_bridge_module);
        Py_XDECREF(g_log_from_native_func);
        g_log_bridge_module = NULL;
        g_log_from_native_func = NULL;
    }

    return PyModule_Create(&loadbalancermodule);
}


