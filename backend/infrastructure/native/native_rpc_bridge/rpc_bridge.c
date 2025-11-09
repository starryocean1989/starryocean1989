// -*- coding: utf-8 -*-
/*
 * rpc_bridge.c - RPC桥接核心实现
 */

#include "rpc_bridge.h"
#include "../native_log_bridge.h"

#define RPC_COMPONENT_CORE "backend.native.rpc_bridge.core"
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdio.h>

static uint32_t g_request_id_counter = 0;

// 日志桥接实现
void native_log_from_c(int level, const char* component, const char* function,
                      int line, const char* message, const char* details) {
    native_log_bridge_log(level, component, function, line, message, details);
}

static uint32_t generate_request_id(void) {
    uint32_t next_id = ++g_request_id_counter;
    if (next_id == 0) {
        next_id = 1;
        g_request_id_counter = next_id;
    }
    return next_id;
}

RPCMessageHeader* create_rpc_header(uint32_t method_id, uint32_t payload_size) {
    NATIVE_LOG_DEBUG(RPC_COMPONENT_CORE, "create_rpc_header", __LINE__,
                    "Creating RPC header");

    RPCMessageHeader* header = (RPCMessageHeader*)malloc(sizeof(RPCMessageHeader));
    if (header == NULL) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "create_rpc_header", __LINE__,
                        "Failed to allocate memory for RPC header");
        return NULL;
    }

    uint32_t request_id = generate_request_id();
    header->method_id = method_id;
    header->payload_size = payload_size;
    header->request_id = request_id;
    header->flags = RPC_FLAG_NATIVE;

    char details[128];
    snprintf(details, sizeof(details), "method_id=%u, request_id=%u, payload_size=%u",
             method_id, request_id, payload_size);
    NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "create_rpc_header", __LINE__,
                   "RPC header created successfully", details);

    return header;
}

int serialize_rpc_request(RPCMessageHeader* header, const char* payload,
                         char** output, size_t* output_size) {
    if (header == NULL || payload == NULL || output == NULL || output_size == NULL) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "serialize_rpc_request", __LINE__,
                        "Invalid parameters: null pointer(s) provided");
        return -1;
    }

    char details[128];
    snprintf(details, sizeof(details), "request_id=%u, payload_size=%u",
             header->request_id, header->payload_size);
    NATIVE_LOG_DEBUG_DETAILS(RPC_COMPONENT_CORE, "serialize_rpc_request", __LINE__,
                    "Serializing RPC request", details);

    size_t total_size = sizeof(RPCMessageHeader) + header->payload_size;
    char* buffer = (char*)malloc(total_size);
    if (buffer == NULL) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "serialize_rpc_request", __LINE__,
                        "Failed to allocate memory for serialized request");
        return -1;
    }

    memcpy(buffer, header, sizeof(RPCMessageHeader));
    memcpy(buffer + sizeof(RPCMessageHeader), payload, header->payload_size);

    *output = buffer;
    *output_size = total_size;

    NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "serialize_rpc_request", __LINE__,
                   "RPC request serialized successfully", details);
    return 0;
}

RPCResponse* deserialize_rpc_response(const char* data, size_t size) {
    if (data == NULL || size < sizeof(int)) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "deserialize_rpc_response", __LINE__,
                        "Invalid parameters: null data or insufficient size");
        return NULL;
    }

    char details[128];
    snprintf(details, sizeof(details), "data_size=%zu", size);
    NATIVE_LOG_DEBUG_DETAILS(RPC_COMPONENT_CORE, "deserialize_rpc_response", __LINE__,
                    "Deserializing RPC response", details);

    RPCResponse* response = (RPCResponse*)malloc(sizeof(RPCResponse));
    if (response == NULL) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "deserialize_rpc_response", __LINE__,
                        "Failed to allocate memory for RPC response");
        return NULL;
    }

    memset(response, 0, sizeof(RPCResponse));
    memcpy(&response->status_code, data, sizeof(int));

    if (response->status_code == 0 && size > sizeof(int)) {
        response->data_size = size - sizeof(int);
        response->data = malloc(response->data_size);
        if (response->data != NULL) {
            memcpy(response->data, data + sizeof(int), response->data_size);
            NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "deserialize_rpc_response", __LINE__,
                           "RPC response deserialized successfully", details);
        } else {
            NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "deserialize_rpc_response", __LINE__,
                            "Failed to allocate memory for response data");
        }
    } else {
        response->error_message = _strdup("RPC call failed");
        char error_details[128];
        snprintf(error_details, sizeof(error_details), "status_code=%d, data_size=%zu",
                 response->status_code, size);
        NATIVE_LOG_WARNING_DETAILS(RPC_COMPONENT_CORE, "deserialize_rpc_response", __LINE__,
                          "RPC response indicates failure", error_details);
    }

    return response;
}

void free_rpc_header(RPCMessageHeader* header) {
    if (header != NULL) {
        free(header);
    }
}

void free_rpc_response(RPCResponse* response) {
    if (response != NULL) {
        if (response->data != NULL) {
            free(response->data);
        }
        if (response->error_message != NULL) {
            free(response->error_message);
        }
        free(response);
    }
}
