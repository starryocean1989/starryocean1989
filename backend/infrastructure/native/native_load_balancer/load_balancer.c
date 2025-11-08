/* -*- coding: utf-8 -*- */
/*
 * load_balancer.c - 负载均衡配置原生优化
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

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
        return NULL;
    }

    if (base_processes < 1) {
        base_processes = 1;
    }
    if (base_coroutines < 1) {
        base_coroutines = 1;
    }
    if (min_coroutines < 1) {
        min_coroutines = 1;
    }
    if (max_processes < 1) {
        max_processes = 1;
    }
    if (max_coroutines < 1) {
        max_coroutines = 1;
    }

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

    long processes = (long)((double)base_processes * resource_scale);
    if (processes < 1) {
        processes = 1;
    }

    long coroutines = (long)((double)base_coroutines * resource_scale);
    if (coroutines < min_coroutines) {
        coroutines = min_coroutines;
    }

    if (queue_factor > 0.0 && queue_factor != 1.0) {
        long scaled_processes = (long)((double)processes * queue_factor);
        long scaled_coroutines = (long)((double)coroutines * queue_factor);
        if (scaled_processes < 1) {
            scaled_processes = 1;
        }
        if (scaled_coroutines < min_coroutines) {
            scaled_coroutines = min_coroutines;
        }
        processes = scaled_processes;
        coroutines = scaled_coroutines;
    }

    int server_constrained = 0;
    if (total_max_connections > 0ULL) {
        unsigned long long total_concurrency = (unsigned long long)processes * (unsigned long long)coroutines;
        if (total_concurrency > total_max_connections) {
            server_constrained = 1;
            if (processes > 0) {
                long new_coroutines = (long)(total_max_connections / (unsigned long long)processes);
                if (new_coroutines < 1) {
                    new_coroutines = 1;
                }
                coroutines = new_coroutines;
                if (coroutines < min_coroutines) {
                    coroutines = min_coroutines;
                }
                if (coroutines < 3 && processes > 1) {
                    long new_processes = (long)(total_max_connections / 3ULL);
                    if (new_processes < 1) {
                        new_processes = 1;
                    }
                    processes = new_processes;
                    long recomputed = (long)(total_max_connections / (unsigned long long)processes);
                    if (recomputed < 1) {
                        recomputed = 1;
                    }
                    coroutines = recomputed;
                    if (coroutines < min_coroutines) {
                        coroutines = min_coroutines;
                    }
                }
            }
        }
    }

    int task_constrained = 0;
    if (task_total_count > 0ULL) {
        unsigned long long total_concurrency = (unsigned long long)processes * (unsigned long long)coroutines;
        if (total_concurrency > task_total_count) {
            task_constrained = 1;
            if (processes > 0) {
                long new_coroutines = (long)(task_total_count / (unsigned long long)processes);
                if (new_coroutines < 1) {
                    new_coroutines = 1;
                }
                coroutines = new_coroutines;
                if (coroutines < min_coroutines) {
                    coroutines = min_coroutines;
                }
                if (coroutines < 3 && processes > 1) {
                    long new_processes = (long)(task_total_count / 3ULL);
                    if (new_processes < 1) {
                        new_processes = 1;
                    }
                    processes = new_processes;
                    long recomputed = (long)(task_total_count / (unsigned long long)processes);
                    if (recomputed < 1) {
                        recomputed = 1;
                    }
                    coroutines = recomputed;
                    if (coroutines < min_coroutines) {
                        coroutines = min_coroutines;
                    }
                }
            }
        }
    }

    if (processes > max_processes) {
        processes = max_processes;
    }
    if (coroutines > max_coroutines) {
        coroutines = max_coroutines;
    }

    if (processes < 1) {
        processes = 1;
    }
    if (coroutines < 1) {
        coroutines = 1;
    }

    unsigned long long total_concurrency = (unsigned long long)processes * (unsigned long long)coroutines;

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
    return PyModule_Create(&loadbalancermodule);
}


