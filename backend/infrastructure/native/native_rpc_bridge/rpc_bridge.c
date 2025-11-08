// -*- coding: utf-8 -*-
/*
 * rpc_bridge.c - RPC桥接核心实现
 */

#include "rpc_bridge.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>

// 静态请求ID计数器
static uint32_t g_request_id_counter = 0;

// 创建RPC消息头
RPCMessageHeader* create_rpc_header(uint32_t method_id, uint32_t payload_size) {
    RPCMessageHeader* header = (RPCMessageHeader*)malloc(sizeof(RPCMessageHeader));
    if (!header) return NULL;
    
    header->method_id = method_id;
    header->payload_size = payload_size;
    header->request_id = ++g_request_id_counter;
    header->flags = 0;
    
    return header;
}

// 序列化RPC请求（简化版：header + payload）
int serialize_rpc_request(RPCMessageHeader* header, const char* payload, 
                         char** output, size_t* output_size) {
    if (!header || !payload || !output || !output_size) {
        return -1;
    }
    
    size_t total_size = sizeof(RPCMessageHeader) + header->payload_size;
    char* buffer = (char*)malloc(total_size);
    if (!buffer) return -1;
    
    // 拷贝消息头
    memcpy(buffer, header, sizeof(RPCMessageHeader));
    
    // 拷贝负载
    memcpy(buffer + sizeof(RPCMessageHeader), payload, header->payload_size);
    
    *output = buffer;
    *output_size = total_size;
    
    return 0;
}

// 反序列化RPC响应
RPCResponse* deserialize_rpc_response(const char* data, size_t size) {
    if (!data || size < sizeof(int)) {
        return NULL;
    }
    
    RPCResponse* response = (RPCResponse*)malloc(sizeof(RPCResponse));
    if (!response) return NULL;
    
    // 简化实现：假设响应格式为 status_code + data
    memcpy(&response->status_code, data, sizeof(int));
    
    if (response->status_code == 0 && size > sizeof(int)) {
        // 成功响应，复制数据
        response->data_size = size - sizeof(int);
        response->data = malloc(response->data_size);
        if (response->data) {
            memcpy(response->data, data + sizeof(int), response->data_size);
        }
        response->error_message = NULL;
    } else {
        // 错误响应
        response->data = NULL;
        response->data_size = 0;
        response->error_message = strdup("RPC call failed");
    }
    
    return response;
}

// 清理函数
void free_rpc_header(RPCMessageHeader* header) {
    if (header) {
        free(header);
    }
}

void free_rpc_response(RPCResponse* response) {
    if (response) {
        if (response->data) {
            free(response->data);
        }
        if (response->error_message) {
            free(response->error_message);
        }
        free(response);
    }
}
