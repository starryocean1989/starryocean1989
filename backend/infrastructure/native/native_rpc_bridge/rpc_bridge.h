#ifndef RPC_BRIDGE_H
#define RPC_BRIDGE_H

#include <Python.h>
#include <stdint.h>

// 日志桥接函数声明
void native_log_from_c(int level, const char* component, const char* function,
                      int line, const char* message, const char* details);

// 原生协议常量
enum {
    RPC_BRIDGE_MAGIC = 0x4E525031u,  // 'NRP1'
    RPC_BRIDGE_VERSION = 1u,
    RPC_BRIDGE_HEADER_SIZE = 32u,
};

enum {
    RPC_FLAG_NATIVE = 0x0001,
    RPC_FLAG_BATCH = 0x0002,
    RPC_FLAG_BINARY_PAYLOAD = 0x0004,
    RPC_FLAG_ERROR = 0x0008,
};

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

// 函数声明

// 创建RPC消息头
RPCMessageHeader* create_rpc_header(uint32_t method_id, uint32_t payload_size);

// 序列化RPC请求
int serialize_rpc_request(RPCMessageHeader* header, const char* payload, char** output, size_t* output_size);

// 反序列化RPC响应
RPCResponse* deserialize_rpc_response(const char* data, size_t size);

// 批量解析与编码
PyObject* batch_decode_requests(PyObject* buffer_sequence, PyObject* method_resolver);
PyObject* batch_encode_responses(PyObject* response_sequence);

// 清理函数
void free_rpc_header(RPCMessageHeader* header);
void free_rpc_response(RPCResponse* response);

#endif // RPC_BRIDGE_H
