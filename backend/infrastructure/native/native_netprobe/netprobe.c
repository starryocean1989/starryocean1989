/* -*- coding: utf-8 -*- */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mswsock.h>
#include <stdio.h>

#include "../native_log_bridge.h"

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "Mswsock.lib")

#define NETPROBE_COMPONENT "backend.native.netprobe.core"

static void netprobe_log(
    int level,
    const char *function,
    int line,
    const char *message,
    const char *details
) {
    native_log_bridge_log(level, NETPROBE_COMPONENT, function, line, message, details);
}

static void netprobe_log_error(const char *function, int line, const char *message, const char *details) {
    netprobe_log(NATIVE_LOG_LEVEL_ERROR, function, line, message, details);
}

static void netprobe_log_warning(const char *function, int line, const char *message, const char *details) {
    netprobe_log(NATIVE_LOG_LEVEL_WARNING, function, line, message, details);
}

static void netprobe_log_info(const char *function, int line, const char *message, const char *details) {
    netprobe_log(NATIVE_LOG_LEVEL_INFO, function, line, message, details);
}

typedef BOOL(PASCAL *LPFN_CONNECTEX)(SOCKET s, const struct sockaddr *name,
                                     int namelen, PVOID lpSendBuffer,
                                     DWORD dwSendDataLength,
                                     LPDWORD lpdwBytesSent,
                                     LPOVERLAPPED lpOverlapped);

typedef struct {
  OVERLAPPED overlapped;
  SOCKET socket;
  struct sockaddr_storage addr;
  int addr_len;
  char *host;
  unsigned short port;
  double start_ms;
  double latency_ms;
  int status; /* 0 success, 1 timeout, -1 error */
  int error_code;
  int in_progress;
  int completed;
  int family;
} ProbeRequest;

static double g_perf_frequency = 0.0;
static LPFN_CONNECTEX g_connectex_v4 = NULL;
static LPFN_CONNECTEX g_connectex_v6 = NULL;

static double now_ms(void) {
  if (g_perf_frequency == 0.0) {
    LARGE_INTEGER freq;
    if (!QueryPerformanceFrequency(&freq) || freq.QuadPart == 0) {
      g_perf_frequency = 1.0;
    } else {
      g_perf_frequency = (double)freq.QuadPart;
    }
  }

  LARGE_INTEGER counter;
  QueryPerformanceCounter(&counter);
  return (double)counter.QuadPart * 1000.0 / g_perf_frequency;
}

static int ensure_connectex(int family, LPFN_CONNECTEX *out_fn) {
  if (family == AF_INET && g_connectex_v4) {
    *out_fn = g_connectex_v4;
    return 0;
  }
  if (family == AF_INET6 && g_connectex_v6) {
    *out_fn = g_connectex_v6;
    return 0;
  }

  SOCKET temp =
      WSASocket(family, SOCK_STREAM, IPPROTO_TCP, NULL, 0, WSA_FLAG_OVERLAPPED);
  if (temp == INVALID_SOCKET) {
    netprobe_log_error(__FUNCTION__, __LINE__, "WSASocket failed while loading ConnectEx", NULL);
    return -1;
  }

  GUID guid = WSAID_CONNECTEX;
  LPFN_CONNECTEX fn = NULL;
  DWORD bytes = 0;
  int rc = WSAIoctl(temp, SIO_GET_EXTENSION_FUNCTION_POINTER, &guid,
                    sizeof(guid), &fn, sizeof(fn), &bytes, NULL, NULL);
  closesocket(temp);
  if (rc != 0 || fn == NULL) {
    char details[64];
    snprintf(details, sizeof(details), "family=%d;wsa_error=%d", family, WSAGetLastError());
    netprobe_log_error(__FUNCTION__, __LINE__, "WSAIoctl failed to resolve ConnectEx", details);
    return -1;
  }

  if (family == AF_INET) {
    g_connectex_v4 = fn;
  } else if (family == AF_INET6) {
    g_connectex_v6 = fn;
  }
  *out_fn = fn;
  return 0;
}

static void cleanup_request(ProbeRequest *req) {
  if (req->socket != INVALID_SOCKET) {
    closesocket(req->socket);
    req->socket = INVALID_SOCKET;
  }
  if (req->host) {
    PyMem_Free(req->host);
    req->host = NULL;
  }
}

static int prepare_request(ProbeRequest *req, const char *host_utf8,
                           unsigned short port) {
  memset(req, 0, sizeof(*req));
  req->socket = INVALID_SOCKET;
  req->latency_ms = -1.0;
  req->status = -2; /* pending sentinel */
  req->error_code = 0;
  req->in_progress = 0;
  req->completed = 0;

  size_t host_len = strlen(host_utf8);
  req->host = PyMem_Malloc(host_len + 1);
  if (!req->host) {
    netprobe_log_error(__FUNCTION__, __LINE__, "PyMem_Malloc failed while copying host", NULL);
    return -1;
  }
  memcpy(req->host, host_utf8, host_len + 1);
  req->port = port;

  char port_buf[16];
  snprintf(port_buf, sizeof(port_buf), "%u", port);

  struct addrinfo hints;
  memset(&hints, 0, sizeof(hints));
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_protocol = IPPROTO_TCP;
  hints.ai_family = AF_UNSPEC;

  struct addrinfo *result = NULL;
  int gai;

  /* Release GIL during potentially blocking DNS resolution */
  Py_BEGIN_ALLOW_THREADS gai =
      getaddrinfo(host_utf8, port_buf, &hints, &result);
  Py_END_ALLOW_THREADS

      if (gai != 0 || !result) {
    char details[256];
    snprintf(details, sizeof(details), "host=%s;port=%u;gai=%d", host_utf8, port, gai);
    netprobe_log_warning(__FUNCTION__, __LINE__, "getaddrinfo failed for netprobe request", details);
    req->status = -1;
    req->error_code = gai != 0 ? gai : WSAHOST_NOT_FOUND;
    req->completed = 1;
    return -1;
  }

  memcpy(&req->addr, result->ai_addr, result->ai_addrlen);
  req->addr_len = (int)result->ai_addrlen;
  req->family = result->ai_family;
  freeaddrinfo(result);
  return 0;
}

static int bind_local_address(SOCKET sock, int family) {
  if (family == AF_INET) {
    struct sockaddr_in local;
    memset(&local, 0, sizeof(local));
    local.sin_family = AF_INET;
    int rc = bind(sock, (SOCKADDR *)&local, sizeof(local));
    if (rc != 0) {
      char details[64];
      snprintf(details, sizeof(details), "family=AF_INET;wsa_error=%d", WSAGetLastError());
      netprobe_log_error(__FUNCTION__, __LINE__, "bind failed for IPv4 socket", details);
    }
    return rc;
  }
  if (family == AF_INET6) {
    struct sockaddr_in6 local6;
    memset(&local6, 0, sizeof(local6));
    local6.sin6_family = AF_INET6;
    int rc = bind(sock, (SOCKADDR *)&local6, sizeof(local6));
    if (rc != 0) {
      char details[64];
      snprintf(details, sizeof(details), "family=AF_INET6;wsa_error=%d", WSAGetLastError());
      netprobe_log_error(__FUNCTION__, __LINE__, "bind failed for IPv6 socket", details);
    }
    return rc;
  }
  netprobe_log_warning(__FUNCTION__, __LINE__, "bind_local_address received unsupported family", NULL);
  return -1;
}

static int start_request(ProbeRequest *req, HANDLE iocp) {
  LPFN_CONNECTEX connectex = NULL;
  if (ensure_connectex(req->family, &connectex) != 0) {
    req->status = -1;
    req->error_code = WSAEOPNOTSUPP;
    req->completed = 1;
    return -1;
  }

  SOCKET sock = WSASocket(req->family, SOCK_STREAM, IPPROTO_TCP, NULL, 0,
                          WSA_FLAG_OVERLAPPED);
  if (sock == INVALID_SOCKET) {
    netprobe_log_error(__FUNCTION__, __LINE__, "WSASocket failed during start_request", NULL);
    req->status = -1;
    req->error_code = WSAGetLastError();
    req->completed = 1;
    return -1;
  }
  req->socket = sock;

  if (!CreateIoCompletionPort((HANDLE)sock, iocp, (ULONG_PTR)req, 0)) {
    char details[128];
    snprintf(details, sizeof(details), "error=%lu", (unsigned long)GetLastError());
    netprobe_log_error(__FUNCTION__, __LINE__, "CreateIoCompletionPort failed", details);
    req->status = -1;
    req->error_code = (int)GetLastError();
    req->completed = 1;
    closesocket(sock);
    req->socket = INVALID_SOCKET;
    return -1;
  }

  if (bind_local_address(sock, req->family) != 0) {
    req->status = -1;
    req->error_code = WSAGetLastError();
    req->completed = 1;
    closesocket(sock);
    req->socket = INVALID_SOCKET;
    return -1;
  }

  ZeroMemory(&req->overlapped, sizeof(req->overlapped));
  req->start_ms = now_ms();
  req->in_progress = 1;

  BOOL immediate = connectex(sock, (SOCKADDR *)&req->addr, req->addr_len, NULL,
                             0, NULL, &req->overlapped);

  if (!immediate) {
    int err = WSAGetLastError();
    if (err == WSA_IO_PENDING) {
      return 0;
    }
    req->status = -1;
    req->error_code = err;
    req->completed = 1;
    req->in_progress = 0;
    closesocket(sock);
    req->socket = INVALID_SOCKET;
    return -1;
  }

  /* immediate success; post to IOCP manually */
  req->latency_ms = now_ms() - req->start_ms;
  req->status = 0;
  req->error_code = 0;
  req->completed = 1;
  req->in_progress = 0;

  setsockopt(req->socket, SOL_SOCKET, SO_UPDATE_CONNECT_CONTEXT, NULL, 0);
  PostQueuedCompletionStatus(iocp, 0, (ULONG_PTR)req, &req->overlapped);
  return 0;
}

static void finalize_request(ProbeRequest *req, int status, int error_code,
                             double now) {
  if (req->completed) {
    return;
  }

  req->completed = 1;
  req->status = status;
  req->error_code = error_code;
  req->latency_ms = status == 0 ? (now - req->start_ms) : -1.0;
  req->in_progress = 0;

  if (req->socket != INVALID_SOCKET) {
    if (status == 0) {
      setsockopt(req->socket, SOL_SOCKET, SO_UPDATE_CONNECT_CONTEXT, NULL, 0);
    }
    closesocket(req->socket);
    req->socket = INVALID_SOCKET;
  }
}

static PyObject *build_result(const ProbeRequest *req) {
  PyObject *result = PyDict_New();
  if (!result) {
    return NULL;
  }

  PyObject *host = PyUnicode_FromString(req->host ? req->host : "");
  PyObject *port = PyLong_FromUnsignedLong(req->port);
  if (!host || !port) {
    Py_XDECREF(host);
    Py_XDECREF(port);
    Py_DECREF(result);
    return NULL;
  }

  PyDict_SetItemString(result, "host", host);
  PyDict_SetItemString(result, "port", port);
  Py_DECREF(host);
  Py_DECREF(port);

  if (req->status == 0) {
    PyDict_SetItemString(result, "status", PyUnicode_FromString("success"));
    PyDict_SetItemString(
        result, "ping_ms",
        PyFloat_FromDouble(req->latency_ms >= 0.0 ? req->latency_ms : 0.0));
  } else if (req->status == 1) {
    PyDict_SetItemString(result, "status", PyUnicode_FromString("timeout"));
    PyDict_SetItemString(result, "ping_ms", PyFloat_FromDouble(-1.0));
    PyDict_SetItemString(result, "error", PyLong_FromLong(WSAETIMEDOUT));
  } else {
    PyDict_SetItemString(result, "status", PyUnicode_FromString("error"));
    PyDict_SetItemString(result, "ping_ms", PyFloat_FromDouble(-1.0));
    PyDict_SetItemString(result, "error", PyLong_FromLong(req->error_code));
  }

  return result;
}

static PyObject *run_batch(PyObject *server_list, double timeout,
                           int max_concurrent) {
  Py_ssize_t total = PyList_GET_SIZE(server_list);
  if (total <= 0) {
    PyObject *summary = PyDict_New();
    if (!summary) {
      return NULL;
    }
    PyDict_SetItemString(summary, "results", PyList_New(0));
    PyDict_SetItemString(summary, "success", PyLong_FromLong(0));
    PyDict_SetItemString(summary, "timeout", PyLong_FromLong(0));
    PyDict_SetItemString(summary, "error", PyLong_FromLong(0));
    PyDict_SetItemString(summary, "total", PyLong_FromLong(0));
    PyDict_SetItemString(summary, "duration_ms", PyFloat_FromDouble(0.0));
    return summary;
  }

  if (max_concurrent <= 0) {
    max_concurrent = 32;
  }

  double timeout_ms = timeout <= 0.0 ? 100.0 : timeout * 1000.0;
  double start_batch = now_ms();
  double deadline_ms = start_batch + timeout_ms; /* 计算超时截止时间 */

  ProbeRequest *requests = PyMem_Calloc((size_t)total, sizeof(ProbeRequest));
  if (!requests) {
    netprobe_log_error(__FUNCTION__, __LINE__, "PyMem_Calloc failed for ProbeRequest array", NULL);
    PyErr_NoMemory();
    return NULL;
  }

  Py_ssize_t prepared = 0;
  for (Py_ssize_t i = 0; i < total; ++i) {
    PyObject *item = PyList_GET_ITEM(server_list, i);
    if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) < 2) {
      netprobe_log_warning(__FUNCTION__, __LINE__, "Invalid server entry encountered", NULL);
      PyMem_Free(requests);
      PyErr_SetString(PyExc_TypeError, "each server must be (host, port)");
      return NULL;
    }

    PyObject *host_obj = PyTuple_GET_ITEM(item, 0);
    PyObject *port_obj = PyTuple_GET_ITEM(item, 1);

    const char *host_utf8 = PyUnicode_AsUTF8(host_obj);
    if (!host_utf8) {
      netprobe_log_warning(__FUNCTION__, __LINE__, "Failed to decode server host to UTF-8", NULL);
      PyMem_Free(requests);
      return NULL;
    }

    long port_long = PyLong_AsLong(port_obj);
    if (port_long < 0 || port_long > 65535) {
      netprobe_log_warning(__FUNCTION__, __LINE__, "Server port out of range", NULL);
      PyMem_Free(requests);
      PyErr_SetString(PyExc_ValueError, "port must be between 0 and 65535");
      return NULL;
    }

    if (prepare_request(&requests[i], host_utf8, (unsigned short)port_long) ==
        0) {
      prepared++;
    }
  }

  HANDLE iocp = NULL;
  if (prepared > 0) {
    iocp = CreateIoCompletionPort(INVALID_HANDLE_VALUE, NULL, 0, 0);
    if (!iocp) {
      netprobe_log_error(__FUNCTION__, __LINE__, "CreateIoCompletionPort failed for batch", NULL);
      PyMem_Free(requests);
      PyErr_SetFromWindowsErr(0);
      return NULL;
    }
  }

  Py_ssize_t completed = 0;
  Py_ssize_t active = 0;
  Py_ssize_t next_index = 0;

  while (completed < total) {
    while (next_index < total) {
      ProbeRequest *req = &requests[next_index];
      if (req->completed) {
        completed++;
        next_index++;
        continue;
      }
      if (active >= max_concurrent) {
        break;
      }

      if (iocp && start_request(req, iocp) == 0) {
        if (!req->completed) {
          active++;
        } else {
          completed++;
        }
      } else {
        completed++;
      }
      next_index++;
    }

    if (completed >= total || !iocp) {
      break;
    }

    /* 在等待之前先检查是否已经超时,如果超时则取消所有pending的请求 */
    double now_before_wait = now_ms();
    double remaining_ms = deadline_ms - now_before_wait;

    if (remaining_ms <= 0.0) {
      /* 已经超时,取消所有未完成的请求 */
      for (Py_ssize_t i = 0; i < total; ++i) {
        ProbeRequest *req = &requests[i];
        if (!req->completed && req->in_progress) {
          CancelIoEx((HANDLE)req->socket, &req->overlapped);
          finalize_request(req, 1, WSAETIMEDOUT, now_before_wait);
          if (active > 0) {
            active--;
          }
        }
      }
      netprobe_log_warning(__FUNCTION__, __LINE__, "Batch netprobe timed out", NULL);
      break; /* 超时后直接退出循环 */
    }

    DWORD wait_ms = (DWORD)remaining_ms;
    ULONG_PTR key = 0;
    LPOVERLAPPED overlapped = NULL;
    DWORD bytes = 0;
    BOOL ok;

    /* Release GIL during IOCP wait */
    Py_BEGIN_ALLOW_THREADS ok =
        GetQueuedCompletionStatus(iocp, &bytes, &key, &overlapped, wait_ms);
    Py_END_ALLOW_THREADS

        double now = now_ms();

    if (ok && key != 0) {
      ProbeRequest *req = (ProbeRequest *)key;
      finalize_request(req, 0, 0, now);
      if (active > 0 && req->in_progress) {
        active--;
      }
      continue;
    }

    DWORD err = GetLastError();
    if (!ok && overlapped != NULL && key != 0) {
      ProbeRequest *req = (ProbeRequest *)key;
      finalize_request(req, -1, (int)err, now);
      if (active > 0 && req->in_progress) {
        active--;
      }
      continue;
    }

    if (!ok && err == WAIT_TIMEOUT) {
      for (Py_ssize_t i = 0; i < total; ++i) {
        ProbeRequest *req = &requests[i];
        if (!req->completed && req->in_progress) {
          if (timeout_ms <= 0.0 || (now - req->start_ms) >= timeout_ms) {
            CancelIoEx((HANDLE)req->socket, &req->overlapped);
            finalize_request(req, 1, WSAETIMEDOUT, now);
            if (active > 0) {
              active--;
            }
          }
        }
      }
      netprobe_log_warning(__FUNCTION__, __LINE__, "Netprobe request timeout reached", NULL);
      continue;
    }

    if (!ok && err != WAIT_TIMEOUT) {
      char details[128];
      snprintf(details, sizeof(details), "err=%lu", (unsigned long)err);
      netprobe_log_error(__FUNCTION__, __LINE__, "GetQueuedCompletionStatus failed", details);
      PyErr_SetFromWindowsErr(err);
      break;
    }
  }

  if (iocp) {
    CloseHandle(iocp);
  }

  PyObject *results = PyList_New(total);
  if (!results) {
    for (Py_ssize_t i = 0; i < total; ++i) {
      cleanup_request(&requests[i]);
    }
    PyMem_Free(requests);
    netprobe_log_error(__FUNCTION__, __LINE__, "Failed to allocate results list", NULL);
    return NULL;
  }

  int success = 0;
  int timeout_count = 0;
  int error = 0;

  for (Py_ssize_t i = 0; i < total; ++i) {
    if (!requests[i].completed) {
      finalize_request(&requests[i], 1, WSAETIMEDOUT, now_ms());
    }

    if (requests[i].status == 0) {
      success++;
    } else if (requests[i].status == 1) {
      timeout_count++;
    } else {
      error++;
    }

    PyObject *entry = build_result(&requests[i]);
    if (!entry) {
      Py_DECREF(results);
      for (Py_ssize_t j = 0; j < total; ++j) {
        cleanup_request(&requests[j]);
      }
      PyMem_Free(requests);
      netprobe_log_error(__FUNCTION__, __LINE__, "build_result returned NULL", NULL);
      return NULL;
    }
    PyList_SET_ITEM(results, i, entry);
  }

  for (Py_ssize_t i = 0; i < total; ++i) {
    cleanup_request(&requests[i]);
  }
  PyMem_Free(requests);

  PyObject *summary = PyDict_New();
  if (!summary) {
    Py_DECREF(results);
    netprobe_log_error(__FUNCTION__, __LINE__, "Failed to allocate summary dictionary", NULL);
    return NULL;
  }

  PyDict_SetItemString(summary, "results", results);
  Py_DECREF(results);
  PyDict_SetItemString(summary, "success", PyLong_FromLong(success));
  PyDict_SetItemString(summary, "timeout", PyLong_FromLong(timeout_count));
  PyDict_SetItemString(summary, "error", PyLong_FromLong(error));
  PyDict_SetItemString(summary, "total", PyLong_FromSsize_t(total));
  PyDict_SetItemString(summary, "duration_ms",
                       PyFloat_FromDouble(now_ms() - start_batch));

  return summary;
}

static PyObject *py_batch_test_connections(PyObject *Py_UNUSED(self),
                                           PyObject *args, PyObject *kwargs) {
  PyObject *servers = NULL;
  double timeout = 3.0;
  int max_concurrent = 32;

  static char *kwlist[] = {"servers", "timeout", "max_concurrent", NULL};
  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|di", kwlist, &servers,
                                   &timeout, &max_concurrent)) {
    return NULL;
  }

  PyObject *sequence = PySequence_List(servers);
  if (!sequence) {
    PyErr_SetString(PyExc_TypeError, "servers must be iterable");
    return NULL;
  }

  PyObject *result = run_batch(sequence, timeout, max_concurrent);
  Py_DECREF(sequence);
  return result;
}

static PyObject *py_test_connection(PyObject *Py_UNUSED(self), PyObject *args,
                                    PyObject *kwargs) {
  const char *host = NULL;
  unsigned int port = 0;
  double timeout = 3.0;

  static char *kwlist[] = {"host", "port", "timeout", NULL};
  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sI|d", kwlist, &host, &port,
                                   &timeout)) {
    return NULL;
  }

  PyObject *pair = PyTuple_New(2);
  if (!pair) {
    return NULL;
  }
  PyTuple_SET_ITEM(pair, 0, PyUnicode_FromString(host));
  PyTuple_SET_ITEM(pair, 1, PyLong_FromUnsignedLong(port));
  if (!PyTuple_GET_ITEM(pair, 0) || !PyTuple_GET_ITEM(pair, 1)) {
    Py_DECREF(pair);
    return NULL;
  }

  PyObject *list = PyList_New(1);
  if (!list) {
    Py_DECREF(pair);
    return NULL;
  }
  PyList_SET_ITEM(list, 0, pair);

  PyObject *summary = run_batch(list, timeout, 1);
  Py_DECREF(list);
  if (!summary) {
    return NULL;
  }

  PyObject *results = PyDict_GetItemString(summary, "results");
  if (!results || !PyList_Check(results) || PyList_GET_SIZE(results) == 0) {
    Py_DECREF(summary);
    PyErr_SetString(PyExc_RuntimeError, "unexpected netprobe output");
    return NULL;
  }

  PyObject *single = PyList_GET_ITEM(results, 0);
  Py_INCREF(single);
  Py_DECREF(summary);
  return single;
}

static PyMethodDef module_methods[] = {
    {"test_connection", (PyCFunction)py_test_connection,
     METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("test_connection(host: str, port: int, timeout=3.0) -> dict")},
    {"batch_test_connections", (PyCFunction)py_batch_test_connections,
     METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("batch_test_connections(servers, timeout=3.0, "
               "max_concurrent=32) -> dict")},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_netprobe.netprobe",
    .m_doc = "High performance TCP probe powered by IOCP",
    .m_size = -1,
    .m_methods = module_methods,
};

PyMODINIT_FUNC PyInit_netprobe(void) {
  WSADATA data;
  if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
    PyErr_SetString(PyExc_RuntimeError, "WSAStartup failed");
    return NULL;
  }

  PyObject *module = PyModule_Create(&module_def);
  if (!module) {
    WSACleanup();
    return NULL;
  }

  if (PyModule_AddIntConstant(module, "NETPROBE_AVAILABLE", 1) < 0) {
    Py_DECREF(module);
    WSACleanup();
    return NULL;
  }

  return module;
}
