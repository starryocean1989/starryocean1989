// -*- coding: utf-8 -*-
/*
 * rpc_bridge.c - RPC桥接核心实现
 */

#include "rpc_bridge.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint32_t g_request_id_counter = 0;

static uint32_t generate_request_id(void) {
    uint32_t next_id = ++g_request_id_counter;
    if (next_id == 0) {
        next_id = 1;
        g_request_id_counter = next_id;
    }
    return next_id;
}

RPCMessageHeader* create_rpc_header(uint32_t method_id, uint32_t payload_size) {
    RPCMessageHeader* header = (RPCMessageHeader*)malloc(sizeof(RPCMessageHeader));
    if (header == NULL) {
        return NULL;
    }

    header->method_id = method_id;
    header->payload_size = payload_size;
    header->request_id = generate_request_id();
    header->flags = RPC_FLAG_NATIVE;
    return header;
}

int serialize_rpc_request(RPCMessageHeader* header, const char* payload,
                         char** output, size_t* output_size) {
    if (header == NULL || payload == NULL || output == NULL || output_size == NULL) {
        return -1;
    }

    size_t total_size = sizeof(RPCMessageHeader) + header->payload_size;
    char* buffer = (char*)malloc(total_size);
    if (buffer == NULL) {
        return -1;
    }

    memcpy(buffer, header, sizeof(RPCMessageHeader));
    memcpy(buffer + sizeof(RPCMessageHeader), payload, header->payload_size);

    *output = buffer;
    *output_size = total_size;
    return 0;
}

RPCResponse* deserialize_rpc_response(const char* data, size_t size) {
    if (data == NULL || size < sizeof(int)) {
        return NULL;
    }

    RPCResponse* response = (RPCResponse*)malloc(sizeof(RPCResponse));
    if (response == NULL) {
        return NULL;
    }

    memset(response, 0, sizeof(RPCResponse));
    memcpy(&response->status_code, data, sizeof(int));

    if (response->status_code == 0 && size > sizeof(int)) {
        response->data_size = size - sizeof(int);
        response->data = malloc(response->data_size);
        if (response->data != NULL) {
            memcpy(response->data, data + sizeof(int), response->data_size);
        }
    } else {
        response->error_message = _strdup("RPC call failed");
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
