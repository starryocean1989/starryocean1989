#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

#include "rpc_bridge.h"
#include "../native_log_bridge.h"

#define RPC_COMPONENT_CORE "backend.native.rpc_bridge.core"
#define RPC_COMPONENT_WRAPPER "backend.native.rpc_bridge.wrapper"

#pragma pack(push, 1)
typedef struct {
    uint32_t magic;
    uint16_t version;
    uint16_t header_size;
    uint32_t method_id;
    uint32_t request_id;
    uint32_t flags;
    uint32_t metadata_size;
    uint32_t payload_size;
} RPCNativeHeader;
#pragma pack(pop)

static PyObject* g_loads_func = NULL;
static PyObject* g_dumps_func = NULL;
static uint32_t g_flag_native = RPC_FLAG_NATIVE;
static uint32_t g_flag_binary_payload = RPC_FLAG_BINARY_PAYLOAD;
static uint32_t g_flag_error = RPC_FLAG_ERROR;

static int
ensure_rpc_helpers(void) {
    if (g_loads_func != NULL && g_dumps_func != NULL) {
        return 0;
    }

    PyObject* module = PyImport_ImportModule("backend.infrastructure.data_module_vnpy.rpc_protocol");
    if (module == NULL) {
        return -1;
    }

    PyObject* loads_func = PyObject_GetAttrString(module, "_loads");
    PyObject* dumps_func = PyObject_GetAttrString(module, "_dumps");
    if (loads_func == NULL || dumps_func == NULL) {
        Py_XDECREF(loads_func);
        Py_XDECREF(dumps_func);
        Py_DECREF(module);
        return -1;
    }

    g_loads_func = loads_func;
    g_dumps_func = dumps_func;

    PyObject* flag_native_obj = PyObject_GetAttrString(module, "FLAG_NATIVE");
    if (flag_native_obj != NULL) {
        unsigned long value = PyLong_AsUnsignedLong(flag_native_obj);
        if (!PyErr_Occurred()) {
            g_flag_native = (uint32_t)value;
        } else {
            PyErr_Clear();
        }
        Py_DECREF(flag_native_obj);
    } else {
        PyErr_Clear();
    }

    PyObject* flag_binary_obj = PyObject_GetAttrString(module, "FLAG_BINARY_PAYLOAD");
    if (flag_binary_obj != NULL) {
        unsigned long value = PyLong_AsUnsignedLong(flag_binary_obj);
        if (!PyErr_Occurred()) {
            g_flag_binary_payload = (uint32_t)value;
        } else {
            PyErr_Clear();
        }
        Py_DECREF(flag_binary_obj);
    } else {
        PyErr_Clear();
    }

    PyObject* flag_error_obj = PyObject_GetAttrString(module, "FLAG_ERROR");
    if (flag_error_obj != NULL) {
        unsigned long value = PyLong_AsUnsignedLong(flag_error_obj);
        if (!PyErr_Occurred()) {
            g_flag_error = (uint32_t)value;
        } else {
            PyErr_Clear();
        }
        Py_DECREF(flag_error_obj);
    } else {
        PyErr_Clear();
    }

    Py_DECREF(module);
    return 0;
}

static PyObject*
create_header_result(const RPCMessageHeader* header) {
    PyObject* result_dict = PyDict_New();
    if (result_dict == NULL) {
        return NULL;
    }

    PyObject* method_id_obj = PyLong_FromUnsignedLong((unsigned long)header->method_id);
    PyObject* payload_size_obj = PyLong_FromUnsignedLong((unsigned long)header->payload_size);
    PyObject* request_id_obj = PyLong_FromUnsignedLong((unsigned long)header->request_id);
    PyObject* flags_obj = PyLong_FromUnsignedLong((unsigned long)header->flags);

    if (method_id_obj == NULL || payload_size_obj == NULL ||
        request_id_obj == NULL || flags_obj == NULL ||
        PyDict_SetItemString(result_dict, "method_id", method_id_obj) < 0 ||
        PyDict_SetItemString(result_dict, "payload_size", payload_size_obj) < 0 ||
        PyDict_SetItemString(result_dict, "request_id", request_id_obj) < 0 ||
        PyDict_SetItemString(result_dict, "flags", flags_obj) < 0) {
        Py_XDECREF(method_id_obj);
        Py_XDECREF(payload_size_obj);
        Py_XDECREF(request_id_obj);
        Py_XDECREF(flags_obj);
        Py_DECREF(result_dict);
        return NULL;
    }

    Py_DECREF(method_id_obj);
    Py_DECREF(payload_size_obj);
    Py_DECREF(request_id_obj);
    Py_DECREF(flags_obj);

    return result_dict;
}

static inline void
write_u32_le(unsigned char* dest, uint32_t value) {
    dest[0] = (unsigned char)(value & 0xFFu);
    dest[1] = (unsigned char)((value >> 8) & 0xFFu);
    dest[2] = (unsigned char)((value >> 16) & 0xFFu);
    dest[3] = (unsigned char)((value >> 24) & 0xFFu);
}

static inline void
write_u16_le(unsigned char* dest, uint16_t value) {
    dest[0] = (unsigned char)(value & 0xFFu);
    dest[1] = (unsigned char)((value >> 8) & 0xFFu);
}

static PyObject*
py_create_request_header(PyObject* self, PyObject* args) {
    unsigned long method_id = 0;
    unsigned long payload_size = 0;

    if (!PyArg_ParseTuple(args, "kk", &method_id, &payload_size)) {
        return NULL;
    }

    RPCMessageHeader* header = create_rpc_header((uint32_t)method_id, (uint32_t)payload_size);
    if (header == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to create RPC header");
        return NULL;
    }

    PyObject* result = create_header_result(header);
    free_rpc_header(header);
    return result;
}

static PyObject*
py_serialize_request(PyObject* self, PyObject* args) {
    unsigned long method_id = 0;
    PyObject* payload_obj = NULL;

    if (!PyArg_ParseTuple(args, "kO", &method_id, &payload_obj)) {
        return NULL;
    }

    PyObject* result = PyDict_New();
    if (result == NULL) {
        return NULL;
    }

    PyObject* method_id_obj = PyLong_FromUnsignedLong(method_id);
    if (method_id_obj == NULL || PyDict_SetItemString(result, "method_id", method_id_obj) < 0) {
        Py_XDECREF(method_id_obj);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(method_id_obj);

    if (PyDict_SetItemString(result, "payload", payload_obj) < 0) {
        Py_DECREF(result);
        return NULL;
    }
    Py_INCREF(payload_obj);

    return result;
}

static PyObject*
decode_single_request(PyObject* raw_buffer_obj, PyObject* method_resolver) {
    Py_buffer buffer_view;
    if (PyObject_GetBuffer(raw_buffer_obj, &buffer_view, PyBUF_CONTIG_RO) != 0) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "decode_single_request", __LINE__,
                        "Failed to get buffer from input object");
        return NULL;
    }

    if (buffer_view.len < (Py_ssize_t)RPC_BRIDGE_HEADER_SIZE) {
        char details[128];
        snprintf(details, sizeof(details), "buffer_size=%zd, required=%d",
                 buffer_view.len, RPC_BRIDGE_HEADER_SIZE);
        NATIVE_LOG_ERROR_DETAILS(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "RPC buffer too small", details);
        PyBuffer_Release(&buffer_view);
        PyErr_SetString(PyExc_ValueError, "RPC buffer too small");
        return NULL;
    }

    NATIVE_LOG_DEBUG(RPC_COMPONENT_CORE, "decode_single_request", __LINE__,
                    "Decoding RPC request buffer");

    RPCNativeHeader header;
    memcpy(&header, buffer_view.buf, sizeof(RPCNativeHeader));

    if (header.magic != RPC_BRIDGE_MAGIC) {
        char details[128];
        snprintf(details, sizeof(details), "expected_magic=0x%08x, actual_magic=0x%08x",
                 RPC_BRIDGE_MAGIC, header.magic);
        NATIVE_LOG_ERROR_DETAILS(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "Invalid RPC magic number - protocol mismatch", details);
        PyBuffer_Release(&buffer_view);
        PyErr_SetString(PyExc_ValueError, "Invalid RPC magic number");
        return NULL;
    }
    if (header.version != RPC_BRIDGE_VERSION || header.header_size != RPC_BRIDGE_HEADER_SIZE) {
        char details[128];
        snprintf(details, sizeof(details), "expected_version=%d, actual_version=%d, expected_header_size=%d, actual_header_size=%d",
                 RPC_BRIDGE_VERSION, header.version, RPC_BRIDGE_HEADER_SIZE, header.header_size);
        NATIVE_LOG_ERROR_DETAILS(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "Unsupported RPC header version - protocol mismatch", details);
        PyBuffer_Release(&buffer_view);
        PyErr_SetString(PyExc_ValueError, "Unsupported RPC header version");
        return NULL;
    }

    Py_ssize_t metadata_offset = (Py_ssize_t)header.header_size;
    Py_ssize_t metadata_size = (Py_ssize_t)header.metadata_size;
    Py_ssize_t payload_size = (Py_ssize_t)header.payload_size;
    Py_ssize_t total_size = metadata_offset + metadata_size + payload_size;
    if (buffer_view.len < total_size) {
        char details[256];
        snprintf(details, sizeof(details),
                 "buffer_size=%zd, required_total=%zd, metadata_offset=%zd, metadata_size=%zd, payload_size=%zd",
                 buffer_view.len, total_size, metadata_offset, metadata_size, payload_size);
        NATIVE_LOG_ERROR_DETAILS(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "Incomplete RPC message payload - buffer error", details);
        PyBuffer_Release(&buffer_view);
        PyErr_SetString(PyExc_ValueError, "Incomplete RPC message payload");
        return NULL;
    }

    char header_details[128];
    snprintf(header_details, sizeof(header_details),
             "method_id=%u, request_id=%u, flags=0x%x, metadata_size=%zd, payload_size=%zd",
             header.method_id, header.request_id, header.flags, metadata_size, payload_size);
    NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "RPC header parsed successfully", header_details);

    PyObject* metadata_bytes = PyBytes_FromStringAndSize(
        (const char*)buffer_view.buf + metadata_offset,
        metadata_size
    );
    if (metadata_bytes == NULL) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "Failed to create metadata bytes object");
        PyBuffer_Release(&buffer_view);
        return NULL;
    }

    PyObject* metadata_obj = PyObject_CallFunctionObjArgs(g_loads_func, metadata_bytes, NULL);
    Py_DECREF(metadata_bytes);
    if (metadata_obj == NULL) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "Failed to deserialize metadata - protocol error");
        PyBuffer_Release(&buffer_view);
        return NULL;
    }

    NATIVE_LOG_DEBUG(RPC_COMPONENT_CORE, "decode_single_request", __LINE__, "Metadata deserialized successfully");

    if (!PyDict_Check(metadata_obj)) {
        PyObject* metadata_dict = PyDict_New();
        if (metadata_dict == NULL) {
            Py_DECREF(metadata_obj);
            PyBuffer_Release(&buffer_view);
            return NULL;
        }
        Py_DECREF(metadata_obj);
        metadata_obj = metadata_dict;
    }

    PyObject* method_name_obj = PyDict_GetItemString(metadata_obj, "method");
    if (method_name_obj != NULL && PyUnicode_Check(method_name_obj) && method_name_obj != Py_None) {
        Py_INCREF(method_name_obj);
    } else {
        method_name_obj = NULL;
    }

    if (method_name_obj == NULL && PyCallable_Check(method_resolver)) {
        PyObject* resolved = PyObject_CallFunction(method_resolver, "I", header.method_id);
        if (resolved != NULL) {
            if (PyUnicode_Check(resolved)) {
                method_name_obj = resolved;
            } else {
                Py_DECREF(resolved);
            }
        } else {
            PyErr_Clear();
        }
    }

    PyObject* payload_view_obj = Py_None;
    if (payload_size > 0) {
        Py_buffer payload_buffer;
        Py_INCREF(buffer_view.obj);
        if (PyBuffer_FillInfo(
                &payload_buffer,
                buffer_view.obj,
                (char*)buffer_view.buf + metadata_offset + metadata_size,
                payload_size,
                1,
                PyBUF_CONTIG_RO) != 0) {
            Py_DECREF(buffer_view.obj);
            Py_DECREF(metadata_obj);
            Py_XDECREF(method_name_obj);
            PyBuffer_Release(&buffer_view);
            return NULL;
        }
        payload_view_obj = PyMemoryView_FromBuffer(&payload_buffer);
        if (payload_view_obj == NULL) {
            Py_DECREF(buffer_view.obj);
            Py_DECREF(metadata_obj);
            Py_XDECREF(method_name_obj);
            PyBuffer_Release(&buffer_view);
            return NULL;
        }
    } else {
        Py_INCREF(Py_None);
        payload_view_obj = Py_None;
    }

    PyBuffer_Release(&buffer_view);

    PyObject* result_tuple = PyTuple_New(6);
    if (result_tuple == NULL) {
        Py_DECREF(metadata_obj);
        Py_DECREF(payload_view_obj);
        Py_XDECREF(method_name_obj);
        return NULL;
    }

    PyObject* method_id_obj = PyLong_FromUnsignedLong(header.method_id);
    PyObject* request_id_obj = PyLong_FromUnsignedLong(header.request_id);
    PyObject* flags_obj = PyLong_FromUnsignedLong(header.flags);

    if (method_id_obj == NULL || request_id_obj == NULL || flags_obj == NULL) {
        Py_XDECREF(method_id_obj);
        Py_XDECREF(request_id_obj);
        Py_XDECREF(flags_obj);
        Py_DECREF(metadata_obj);
        Py_DECREF(payload_view_obj);
        Py_XDECREF(method_name_obj);
        Py_DECREF(result_tuple);
        return NULL;
    }

    PyTuple_SET_ITEM(result_tuple, 0, method_id_obj);
    PyTuple_SET_ITEM(result_tuple, 1, request_id_obj);
    PyTuple_SET_ITEM(result_tuple, 2, flags_obj);

    if (method_name_obj != NULL) {
        PyTuple_SET_ITEM(result_tuple, 3, method_name_obj);
    } else {
        Py_INCREF(Py_None);
        PyTuple_SET_ITEM(result_tuple, 3, Py_None);
    }

    PyTuple_SET_ITEM(result_tuple, 4, metadata_obj);
    PyTuple_SET_ITEM(result_tuple, 5, payload_view_obj);

    return result_tuple;
}

static PyObject*
py_batch_decode_requests(PyObject* self, PyObject* args) {
    PyObject* buffer_sequence = NULL;
    PyObject* method_resolver = Py_None;

    if (!PyArg_ParseTuple(args, "O|O", &buffer_sequence, &method_resolver)) {
        return NULL;
    }

    if (ensure_rpc_helpers() != 0) {
        return NULL;
    }

    // 获取序列长度用于日志
    Py_ssize_t seq_len = 0;
    if (PySequence_Check(buffer_sequence)) {
        seq_len = PySequence_Size(buffer_sequence);
    }

    char details[128];
    snprintf(details, sizeof(details), "batch_size=%zd", seq_len);
    NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "batch_decode_requests", __LINE__, "Starting batch decode of RPC requests", details);

    PyObject* iterator = PyObject_GetIter(buffer_sequence);
    if (iterator == NULL) {
        PyErr_SetString(PyExc_TypeError, "batch_decode_requests expects an iterable of buffers");
        return NULL;
    }

    PyObject* result_list = PyList_New(0);
    if (result_list == NULL) {
        Py_DECREF(iterator);
        return NULL;
    }

    PyObject* item = NULL;
    while ((item = PyIter_Next(iterator)) != NULL) {
        PyObject* decoded = decode_single_request(item, method_resolver);
        Py_DECREF(item);
        if (decoded == NULL) {
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }
        if (PyList_Append(result_list, decoded) < 0) {
            Py_DECREF(decoded);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }
        Py_DECREF(decoded);
    }

    Py_DECREF(iterator);
    if (PyErr_Occurred()) {
        Py_DECREF(result_list);
        return NULL;
    }

    return result_list;
}

static PyObject*
py_batch_encode_responses(PyObject* self, PyObject* args) {
    PyObject* response_sequence = NULL;
    if (!PyArg_ParseTuple(args, "O", &response_sequence)) {
        return NULL;
    }

    if (ensure_rpc_helpers() != 0) {
        return NULL;
    }

    // 获取序列长度用于日志
    Py_ssize_t seq_len = 0;
    if (PySequence_Check(response_sequence)) {
        seq_len = PySequence_Size(response_sequence);
    }

    char details[128];
    snprintf(details, sizeof(details), "batch_size=%zd", seq_len);
    NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "batch_encode_responses", __LINE__, "Starting batch encode of RPC responses", details);

    PyObject* iterator = PyObject_GetIter(response_sequence);
    if (iterator == NULL) {
        PyErr_SetString(PyExc_TypeError, "batch_encode_responses expects an iterable");
        return NULL;
    }

    PyObject* result_list = PyList_New(0);
    if (result_list == NULL) {
        Py_DECREF(iterator);
        return NULL;
    }

    PyObject* entry = NULL;
    while ((entry = PyIter_Next(iterator)) != NULL) {
        if (!PyTuple_Check(entry) || PyTuple_Size(entry) != 5) {
            PyErr_SetString(PyExc_TypeError, "Each response must be a tuple(method_id, request_id, flags, metadata_dict, payload)");
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        PyObject* method_id_obj = PyTuple_GET_ITEM(entry, 0);
        PyObject* request_id_obj = PyTuple_GET_ITEM(entry, 1);
        PyObject* flags_obj = PyTuple_GET_ITEM(entry, 2);
        PyObject* metadata_obj = PyTuple_GET_ITEM(entry, 3);
        PyObject* payload_obj = PyTuple_GET_ITEM(entry, 4);

        if (!PyDict_Check(metadata_obj)) {
            PyErr_SetString(PyExc_TypeError, "Response metadata must be a dict");
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        uint32_t method_id = (uint32_t)PyLong_AsUnsignedLong(method_id_obj);
        if (PyErr_Occurred()) {
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        uint32_t request_id = (uint32_t)PyLong_AsUnsignedLong(request_id_obj);
        if (PyErr_Occurred()) {
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        uint32_t flags = (uint32_t)PyLong_AsUnsignedLong(flags_obj);
        if (PyErr_Occurred()) {
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }
        flags |= g_flag_native;

        PyObject* metadata_bytes = PyObject_CallFunctionObjArgs(g_dumps_func, metadata_obj, NULL);
        if (metadata_bytes == NULL) {
            char error_details[256];
            snprintf(error_details, sizeof(error_details),
                     "method_id=%u, request_id=%u, flags=0x%x",
                     method_id, request_id, flags);
            NATIVE_LOG_ERROR_DETAILS(RPC_COMPONENT_CORE, "batch_encode_responses", __LINE__, "Failed to serialize metadata - callback error", error_details);
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        if (!PyBytes_Check(metadata_bytes)) {
            NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "batch_encode_responses", __LINE__, "_dumps function must return bytes - protocol error");
            PyErr_SetString(PyExc_TypeError, "_dumps must return bytes");
            Py_DECREF(metadata_bytes);
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        Py_ssize_t metadata_size = PyBytes_GET_SIZE(metadata_bytes);
        Py_buffer payload_buffer;
        memset(&payload_buffer, 0, sizeof(Py_buffer));
        Py_ssize_t payload_size = 0;

        int has_payload = payload_obj != Py_None;
        if (has_payload) {
            if (PyObject_GetBuffer(payload_obj, &payload_buffer, PyBUF_CONTIG_RO) != 0) {
                char error_details[256];
                snprintf(error_details, sizeof(error_details),
                         "method_id=%u, request_id=%u - payload buffer access failed",
                         method_id, request_id);
                NATIVE_LOG_ERROR_DETAILS(RPC_COMPONENT_CORE, "batch_encode_responses", __LINE__, "Failed to get payload buffer - buffer error", error_details);
                Py_DECREF(metadata_bytes);
                Py_DECREF(entry);
                Py_DECREF(iterator);
                Py_DECREF(result_list);
                return NULL;
            }
            payload_size = payload_buffer.len;
            if (payload_size > 0) {
                flags |= g_flag_binary_payload;
            }
        }

        unsigned char header_bytes[RPC_BRIDGE_HEADER_SIZE];
        write_u32_le(header_bytes, RPC_BRIDGE_MAGIC);
        write_u16_le(header_bytes + 4, RPC_BRIDGE_VERSION);
        write_u16_le(header_bytes + 6, RPC_BRIDGE_HEADER_SIZE);
        write_u32_le(header_bytes + 8, method_id);
        write_u32_le(header_bytes + 12, request_id);
        write_u32_le(header_bytes + 16, flags);
        write_u32_le(header_bytes + 20, (uint32_t)metadata_size);
        write_u32_le(header_bytes + 24, (uint32_t)payload_size);

        Py_ssize_t total_size = RPC_BRIDGE_HEADER_SIZE + metadata_size + payload_size;
        PyObject* response_bytes = PyBytes_FromStringAndSize(NULL, total_size);
        if (response_bytes == NULL) {
            if (has_payload) {
                PyBuffer_Release(&payload_buffer);
            }
            Py_DECREF(metadata_bytes);
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }

        unsigned char* dest = (unsigned char*)PyBytes_AS_STRING(response_bytes);
        memcpy(dest, header_bytes, RPC_BRIDGE_HEADER_SIZE);
        memcpy(dest + RPC_BRIDGE_HEADER_SIZE, PyBytes_AS_STRING(metadata_bytes), (size_t)metadata_size);

        if (has_payload && payload_size > 0) {
            memcpy(dest + RPC_BRIDGE_HEADER_SIZE + metadata_size, payload_buffer.buf, (size_t)payload_size);
            PyBuffer_Release(&payload_buffer);
        }

        Py_DECREF(metadata_bytes);

        if (PyList_Append(result_list, response_bytes) < 0) {
            Py_DECREF(response_bytes);
            Py_DECREF(entry);
            Py_DECREF(iterator);
            Py_DECREF(result_list);
            return NULL;
        }
        Py_DECREF(response_bytes);
        Py_DECREF(entry);
    }

    Py_DECREF(iterator);
    if (PyErr_Occurred()) {
        NATIVE_LOG_ERROR(RPC_COMPONENT_CORE, "batch_encode_responses", __LINE__, "Iterator error during batch encoding");
        Py_DECREF(result_list);
        return NULL;
    }

    char success_details[128];
    Py_ssize_t result_count = PyList_Size(result_list);
    snprintf(success_details, sizeof(success_details), "encoded_count=%zd", result_count);
    NATIVE_LOG_INFO_DETAILS(RPC_COMPONENT_CORE, "batch_encode_responses", __LINE__, "Batch encode of RPC responses completed successfully", success_details);

    return result_list;
}

static PyMethodDef RPCBridgeMethods[] = {
    {"create_request_header", py_create_request_header, METH_VARARGS,
     "Create RPC request header"},
    {"serialize_request", py_serialize_request, METH_VARARGS,
     "Serialize RPC request (simplified)"},
    {"batch_decode_requests", py_batch_decode_requests, METH_VARARGS,
     "Batch decode native RPC requests"},
    {"batch_encode_responses", py_batch_encode_responses, METH_VARARGS,
     "Batch encode native RPC responses"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef rpc_bridge_module = {
    PyModuleDef_HEAD_INIT,
    "native_rpc_bridge",
    "Native RPC bridge for zero-copy IPC communication",
    -1,
    RPCBridgeMethods
};

PyMODINIT_FUNC
PyInit_native_rpc_bridge(void) {
    PyObject* module = PyModule_Create(&rpc_bridge_module);
    if (module == NULL) {
        return NULL;
    }

    if (ensure_rpc_helpers() != 0) {
        Py_DECREF(module);
        return NULL;
    }

    PyModule_AddIntConstant(module, "RPC_BRIDGE_AVAILABLE", 1);
    PyModule_AddStringConstant(module, "VERSION", "1.1.0");

    NATIVE_LOG_INFO(RPC_COMPONENT_WRAPPER, "PyInit_native_rpc_bridge", __LINE__, "native_rpc_bridge module initialised");

    return module;
}
