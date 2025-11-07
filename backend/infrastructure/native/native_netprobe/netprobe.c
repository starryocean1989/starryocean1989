// -*- coding: utf-8 -*-
/*
 * netprobe.c - 网络探测核心实现（简化版）
 */

#include "netprobe.h"
#include <stdlib.h>
#include <string.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <time.h>

#pragma comment(lib, "ws2_32.lib")

// 初始化Winsock
static int init_winsock() {
    WSADATA wsaData;
    return WSAStartup(MAKEWORD(2, 2), &wsaData);
}

// 测试单个连接
ConnectionResult* test_connection(const char* host, int port, double timeout_sec) {
    ConnectionResult* result = (ConnectionResult*)malloc(sizeof(ConnectionResult));
    if (!result) return NULL;
    
    result->host = _strdup(host);
    result->port = port;
    result->status = -1;
    result->latency_ms = 0.0;
    result->error_message = NULL;
    
    // 初始化Winsock
    static int winsock_initialized = 0;
    if (!winsock_initialized) {
        if (init_winsock() != 0) {
            result->error_message = _strdup("Winsock initialization failed");
            return result;
        }
        winsock_initialized = 1;
    }
    
    // 创建socket
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) {
        result->error_message = _strdup("Socket creation failed");
        return result;
    }
    
    // 设置超时
    DWORD timeout_ms = (DWORD)(timeout_sec * 1000);
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));
    
    // 设置非阻塞模式
    u_long mode = 1;
    ioctlsocket(sock, FIONBIO, &mode);
    
    // 准备地址
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
    addr.sin_addr.s_addr = inet_addr(host);
    
    // 记录开始时间
    clock_t start = clock();
    
    // 尝试连接
    int conn_result = connect(sock, (struct sockaddr*)&addr, sizeof(addr));
    if (conn_result == SOCKET_ERROR) {
        int error = WSAGetLastError();
        if (error == WSAEWOULDBLOCK) {
            // 使用select等待连接完成
            fd_set write_fds;
            FD_ZERO(&write_fds);
            FD_SET(sock, &write_fds);
            
            struct timeval tv;
            tv.tv_sec = (long)timeout_sec;
            tv.tv_usec = (long)((timeout_sec - tv.tv_sec) * 1000000);
            
            int select_result = select(0, NULL, &write_fds, NULL, &tv);
            if (select_result > 0) {
                // 连接成功
                result->status = 0;
                result->latency_ms = (double)(clock() - start) * 1000.0 / CLOCKS_PER_SEC;
            } else {
                result->error_message = _strdup("Connection timeout");
            }
        } else {
            result->error_message = _strdup("Connection failed");
        }
    } else {
        // 连接立即成功
        result->status = 0;
        result->latency_ms = (double)(clock() - start) * 1000.0 / CLOCKS_PER_SEC;
    }
    
    closesocket(sock);
    return result;
}

// 批量测试连接（简化版：顺序执行）
BatchTestResult* batch_test_connections(
    const char** hosts, 
    const int* ports, 
    size_t count, 
    double timeout_sec,
    int max_concurrent
) {
    BatchTestResult* batch_result = (BatchTestResult*)malloc(sizeof(BatchTestResult));
    if (!batch_result) return NULL;
    
    batch_result->results = (ConnectionResult*)malloc(sizeof(ConnectionResult) * count);
    batch_result->count = count;
    
    clock_t total_start = clock();
    
    // 简化实现：顺序测试（实际应该并发）
    for (size_t i = 0; i < count; i++) {
        ConnectionResult* result = test_connection(hosts[i], ports[i], timeout_sec);
        if (result) {
            batch_result->results[i] = *result;
            free(result); // 只释放结构体本身，不释放内部字符串
        }
    }
    
    batch_result->total_time_ms = (double)(clock() - total_start) * 1000.0 / CLOCKS_PER_SEC;
    
    return batch_result;
}

// 清理函数
void free_connection_result(ConnectionResult* result) {
    if (result) {
        if (result->host) free(result->host);
        if (result->error_message) free(result->error_message);
        free(result);
    }
}

void free_batch_test_result(BatchTestResult* result) {
    if (result) {
        if (result->results) {
            for (size_t i = 0; i < result->count; i++) {
                if (result->results[i].host) free(result->results[i].host);
                if (result->results[i].error_message) free(result->results[i].error_message);
            }
            free(result->results);
        }
        free(result);
    }
}
