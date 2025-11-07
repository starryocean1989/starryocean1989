#ifndef RPC_BRIDGE_H
#define RPC_BRIDGE_H

#include <Python.h>
#include <stdint.h>

// RPC消息头结构
typedef struct {
    uint32_t method_id;      // 方法ID
    uint32_t payload_size;   // 负载大小
    uint32_t request_id;     // 请求ID
    uint32_t flags;          // 标志位
} RPCMessageHeader;

// RPC响应结构
typedef struct {
    int status_code;         // 状态码：0=成功，非0=错误
    char* error_message;     // 错误消息
    void* data;              // 响应数据
    size_t data_size;        // 数据大小
} RPCResponse;

// 方法ID映射表
enum RPCMethodID {
    METHOD_GET_KLINE_DATA = 1,
    METHOD_GET_STOCK_LIST = 2,
    METHOD_GET_CACHE_STATUS = 3,
    METHOD_CALCULATE_INDICATORS = 10,
    METHOD_SCAN_DATA_QUALITY = 11,
};

// 函数声明

// 创建RPC消息头
RPCMessageHeader* create_rpc_header(uint32_t method_id, uint32_t payload_size);

// 序列化RPC请求
int serialize_rpc_request(RPCMessageHeader* header, const char* payload, char** output, size_t* output_size);

// 反序列化RPC响应
RPCResponse* deserialize_rpc_response(const char* data, size_t size);

// 清理函数
void free_rpc_header(RPCMessageHeader* header);
void free_rpc_response(RPCResponse* response);

// 方法名到ID的映射
uint32_t get_method_id(const char* method_name);
const char* get_method_name(uint32_t method_id);

#endif // RPC_BRIDGE_H
