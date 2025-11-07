#ifndef NETPROBE_H
#define NETPROBE_H

#include <Python.h>
#include <stdint.h>

// 连接测试结果
typedef struct {
    char* host;
    int port;
    int status;           // 0=成功, -1=失败
    double latency_ms;    // 延迟(毫秒)
    char* error_message;
} ConnectionResult;

// 批量测试结果
typedef struct {
    ConnectionResult* results;
    size_t count;
    double total_time_ms;
} BatchTestResult;

// 函数声明

// 测试单个连接
ConnectionResult* test_connection(const char* host, int port, double timeout_sec);

// 批量测试连接
BatchTestResult* batch_test_connections(
    const char** hosts, 
    const int* ports, 
    size_t count, 
    double timeout_sec,
    int max_concurrent
);

// 清理函数
void free_connection_result(ConnectionResult* result);
void free_batch_test_result(BatchTestResult* result);

#endif // NETPROBE_H
