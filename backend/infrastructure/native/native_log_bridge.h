/* -*- coding: utf-8 -*-
 * Native 日志桥接头文件
 *
 * 提供从 C 扩展调用 Python 侧日志桥 `backend.infrastructure.native.logging_bridge`
 * 的便捷方法与统一宏定义。
 */

#ifndef BACKEND_INFRASTRUCTURE_NATIVE_LOG_BRIDGE_H
#define BACKEND_INFRASTRUCTURE_NATIVE_LOG_BRIDGE_H

#include <Python.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 与 Python 侧 NativeLogLevel 一致 */
#define NATIVE_LOG_LEVEL_DEBUG     10
#define NATIVE_LOG_LEVEL_INFO      20
#define NATIVE_LOG_LEVEL_WARNING   30
#define NATIVE_LOG_LEVEL_ERROR     40
#define NATIVE_LOG_LEVEL_CRITICAL  50

/*
 * 初始化日志桥接模块。
 * 返回值：0 成功；-1 失败。
 */
static inline int native_log_bridge_init(void) {
    /* 目前不需要特殊初始化，直接返回成功 */
    return 0;
}

/*
 * 获取 Python 侧 log_from_native 回调。
 *
 * 说明：
 *  - 采用 static 缓存，首次调用时导入模块并获取函数对象；
 *  - 若导入失败，会打印异常并返回 NULL；
 *  - 调用者无需持有返回对象的引用（该函数会返回借用引用）。
 */
static inline PyObject *native_log_bridge_get_callback(void) {
    static PyObject *callback = NULL;

    if (callback != NULL) {
        return callback;
    }

    PyObject *module = PyImport_ImportModule("backend.infrastructure.native.logging_bridge");
    if (module == NULL) {
        PyErr_Print();
        return NULL;
    }

    callback = PyObject_GetAttrString(module, "log_from_native");
    Py_DECREF(module);

    if (callback == NULL) {
        PyErr_Print();
        return NULL;
    }

    return callback;
}

/*
 * 发送日志到 Python 侧桥接模块。
 * 返回值：0 成功；-1 失败（同时会保持/打印 Python 异常）。
 */
static inline int native_log_bridge_log(
    int level,
    const char *component,
    const char *function,
    int line,
    const char *message,
    const char *details
) {
    PyObject *callback = native_log_bridge_get_callback();
    if (callback == NULL) {
        return -1;
    }

    if (component == NULL) {
        component = "native";
    }
    if (function == NULL) {
        function = "<call>";
    }
    if (message == NULL) {
        message = "";
    }

    PyObject *details_obj;
    if (details != NULL) {
        details_obj = PyUnicode_FromString(details);
        if (details_obj == NULL) {
            PyErr_Print();
            return -1;
        }
    } else {
        details_obj = Py_None;
        Py_INCREF(Py_None);
    }

    PyObject *result = PyObject_CallFunction(
        callback,
        "issisO",
        level,
        component,
        function,
        line,
        message,
        details_obj
    );

    Py_DECREF(details_obj);

    if (result == NULL) {
        PyErr_Print();
        return -1;
    }

    Py_DECREF(result);
    return 0;
}

/*
 * 为常见等级提供便捷宏。
 */
#define NATIVE_LOG_DEBUG(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_DEBUG, component, function, line, message, NULL)

#define NATIVE_LOG_DEBUG_DETAILS(component, function, line, message, details) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_DEBUG, component, function, line, message, details)

#define NATIVE_LOG_INFO(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, component, function, line, message, NULL)

#define NATIVE_LOG_INFO_DETAILS(component, function, line, message, details) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, component, function, line, message, details)

#define NATIVE_LOG_WARNING(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_WARNING, component, function, line, message, NULL)

#define NATIVE_LOG_WARNING_DETAILS(component, function, line, message, details) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_WARNING, component, function, line, message, details)

#define NATIVE_LOG_ERROR(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, component, function, line, message, NULL)

#define NATIVE_LOG_ERROR_DETAILS(component, function, line, message, details) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, component, function, line, message, details)

#define NATIVE_LOG_CRITICAL(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_CRITICAL, component, function, line, message, NULL)

#define NATIVE_LOG_CRITICAL_DETAILS(component, function, line, message, details) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_CRITICAL, component, function, line, message, details)

/*
 * 为常见等级提供简化宏（自动填充函数名和行号参数）。
 */
#define NATIVE_LOG_DEBUG_SIMPLE(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_DEBUG, component, function, line, message, NULL)

#define NATIVE_LOG_INFO_SIMPLE(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, component, function, line, message, NULL)

#define NATIVE_LOG_WARNING_SIMPLE(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_WARNING, component, function, line, message, NULL)

#define NATIVE_LOG_ERROR_SIMPLE(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, component, function, line, message, NULL)

#define NATIVE_LOG_CRITICAL_SIMPLE(component, function, line, message) \
    native_log_bridge_log(NATIVE_LOG_LEVEL_CRITICAL, component, function, line, message, NULL)

#ifdef __cplusplus
}
#endif

#endif /* BACKEND_INFRASTRUCTURE_NATIVE_LOG_BRIDGE_H */
