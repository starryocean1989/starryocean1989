#ifndef BATCH_SERIALIZE_H
#define BATCH_SERIALIZE_H

#include <Python.h>

// 日志等级常量（与 Python NativeLogLevel 对应）
enum {
    NATIVE_LOG_DEBUG = 10,
    NATIVE_LOG_INFO = 20,
    NATIVE_LOG_WARNING = 30,
    NATIVE_LOG_ERROR = 40,
    NATIVE_LOG_CRITICAL = 50,
};

// 日志宏定义
#define NATIVE_LOG_DEBUG(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_DEBUG, component, function, line, message, details)

#define NATIVE_LOG_INFO(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_INFO, component, function, line, message, details)

#define NATIVE_LOG_WARNING(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_WARNING, component, function, line, message, details)

#define NATIVE_LOG_ERROR(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_ERROR, component, function, line, message, details)

#define NATIVE_LOG_CRITICAL(component, function, line, message, details) \
    native_log_from_c(NATIVE_LOG_CRITICAL, component, function, line, message, details)

// 日志桥接函数声明
void native_log_from_c(int level, const char* component, const char* function,
                      int line, const char* message, const char* details);

/* 函数声明 */
PyObject* batch_serialize_func(PyObject *self, PyObject *args);
PyObject* batch_deserialize_func(PyObject *self, PyObject *args);

#endif /* BATCH_SERIALIZE_H */

