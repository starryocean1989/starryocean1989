/* -*- coding: utf-8 -*-
 * 无锁数据结构实现
 *
 * 使用Windows Interlocked API实现无锁队列和哈希表
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>
#include "lock_free.h"

/* ==================== LockFreeQueue 实现 ==================== */

/* 无锁队列节点结构 */
typedef struct _LockFreeNode {
    volatile PyObject *item;
    volatile struct _LockFreeNode *next;
} LockFreeNode;

/* 无锁队列方法声明 */
static PyObject* LockFreeQueue_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void LockFreeQueue_dealloc(LockFreeQueue *self);
static PyObject* LockFreeQueue_put(LockFreeQueue *self, PyObject *args);
static PyObject* LockFreeQueue_get(LockFreeQueue *self, PyObject *args);
static PyObject* LockFreeQueue_size(LockFreeQueue *self, PyObject *args);
static PyObject* LockFreeQueue_empty(LockFreeQueue *self, PyObject *args);

/* 方法定义 */
static PyMethodDef LockFreeQueue_methods[] = {
    {"put", (PyCFunction)LockFreeQueue_put, METH_VARARGS, "Put item into queue"},
    {"get", (PyCFunction)LockFreeQueue_get, METH_VARARGS, "Get item from queue"},
    {"size", (PyCFunction)LockFreeQueue_size, METH_NOARGS, "Get queue size"},
    {"empty", (PyCFunction)LockFreeQueue_empty, METH_NOARGS, "Check if queue is empty"},
    {NULL, NULL, 0, NULL}
};

/* LockFreeQueue类型定义 */
PyTypeObject LockFreeQueueType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_gil.LockFreeQueue",
    .tp_doc = "Lock-free queue for high-concurrency scenarios",
    .tp_basicsize = sizeof(LockFreeQueue),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = LockFreeQueue_new,
    .tp_dealloc = (destructor)LockFreeQueue_dealloc,
    .tp_methods = LockFreeQueue_methods,
};

/* 初始化队列 */
static PyObject* LockFreeQueue_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    LockFreeQueue *self;
    Py_ssize_t capacity = 16;

    if (!PyArg_ParseTuple(args, "|n", &capacity)) {
        return NULL;
    }

    if (capacity <= 0) {
        capacity = 16;
    }

    self = (LockFreeQueue *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->items = (volatile PyObject **)calloc(capacity, sizeof(PyObject *));
        if (self->items == NULL) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate queue items");
            return NULL;
        }
        self->head = 0LL;
        self->tail = 0LL;
        self->capacity = capacity;
    }
    return (PyObject *)self;
}

/* 清理队列 */
static void LockFreeQueue_dealloc(LockFreeQueue *self) {
    /* 释放所有Python对象引用 */
    for (Py_ssize_t i = 0; i < self->capacity; i++) {
        Py_XDECREF((PyObject *)self->items[i]);
    }

    free((void *)self->items);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 放入元素（使用CAS操作） */
static PyObject* LockFreeQueue_put(LockFreeQueue *self, PyObject *args) {
    PyObject *item;
    LONG64 current_tail, next_tail;
    LONG64 current_head;
    int retry_count = 0;
    const int MAX_RETRIES = 1000;

    if (!PyArg_ParseTuple(args, "O", &item)) {
        return NULL;
    }

    Py_INCREF(item);

    /* 使用CAS循环直到成功 */
    while (retry_count < MAX_RETRIES) {
        /* 使用内存屏障确保读取顺序 */
        MemoryBarrier();
        current_tail = self->tail;
        current_head = self->head;
        MemoryBarrier();

        /* 计算下一个位置 */
        next_tail = (current_tail + 1) % self->capacity;

        /* 检查队列是否满 */
        if (next_tail == current_head) {
            Py_DECREF(item);
            PyErr_SetString(PyExc_IndexError, "Queue is full");
            return NULL;
        }

        /* 尝试原子性地设置tail */
        if (InterlockedCompareExchange64(
            (volatile LONG64 *)&self->tail,
            (LONG64)next_tail,
            (LONG64)current_tail
        ) == (LONG64)current_tail) {
            /* 成功，设置元素（使用内存屏障确保写入顺序） */
            MemoryBarrier();
            Py_XDECREF((PyObject *)self->items[current_tail]);
            self->items[current_tail] = item;
            MemoryBarrier();
            break;
        }
        /* 失败，重试 */
        retry_count++;
        if (retry_count < MAX_RETRIES) {
            Sleep(0);  /* 短暂等待后重试 */
        }
    }

    if (retry_count >= MAX_RETRIES) {
        Py_DECREF(item);
        PyErr_SetString(PyExc_RuntimeError, "Queue put timeout: CAS failed");
        return NULL;
    }

    Py_RETURN_NONE;
}

/* 获取元素（使用CAS操作） */
static PyObject* LockFreeQueue_get(LockFreeQueue *self, PyObject *args) {
    PyObject *item = NULL;
    LONG64 current_head, next_head;
    LONG64 current_tail;
    int retry_count = 0;
    const int MAX_RETRIES = 1000;

    /* 使用CAS循环直到成功 */
    while (retry_count < MAX_RETRIES) {
        /* 使用内存屏障确保读取顺序 */
        MemoryBarrier();
        current_head = self->head;
        current_tail = self->tail;
        MemoryBarrier();

        /* 检查队列是否空 */
        if (current_head == current_tail) {
            PyErr_SetString(PyExc_IndexError, "Queue is empty");
            return NULL;
        }

        /* 获取元素（使用内存屏障确保读取到最新值） */
        MemoryBarrier();
        item = (PyObject *)self->items[current_head];

        /* 如果元素为NULL，说明put操作还未完成写入，先尝试CAS移动head（如果成功说明队列确实是空的） */
        if (item == NULL) {
            /* 再次检查队列是否真的为空 */
            MemoryBarrier();
            LONG64 check_head = self->head;
            LONG64 check_tail = self->tail;
            MemoryBarrier();

            if (check_head == check_tail) {
                /* 队列确实为空 */
                PyErr_SetString(PyExc_IndexError, "Queue is empty");
                return NULL;
            }

            /* 元素还未写入，可能是put操作正在进行，等待后重试 */
            retry_count++;
            if (retry_count >= MAX_RETRIES) {
                PyErr_SetString(PyExc_RuntimeError, "Queue get timeout: item not available");
                return NULL;
            }
            /* 短暂等待后重试 */
            Sleep(0);
            continue;
        }

        /* 计算下一个位置 */
        next_head = (current_head + 1) % self->capacity;

        /* 尝试原子性地设置head */
        if (InterlockedCompareExchange64(
            (volatile LONG64 *)&self->head,
            (LONG64)next_head,
            (LONG64)current_head
        ) == (LONG64)current_head) {
            /* 成功，清空位置并返回 */
            MemoryBarrier();
            self->items[current_head] = NULL;
            MemoryBarrier();
            break;
        }
        /* 失败，重试 */
        retry_count++;
    }

    if (retry_count >= MAX_RETRIES) {
        PyErr_SetString(PyExc_RuntimeError, "Queue get timeout: CAS failed");
        return NULL;
    }

    return item;
}

/* 获取队列大小 */
static PyObject* LockFreeQueue_size(LockFreeQueue *self, PyObject *args) {
    LONG64 head, tail;

    /* 使用内存屏障确保读取顺序 */
    MemoryBarrier();
    head = self->head;
    tail = self->tail;
    MemoryBarrier();

    Py_ssize_t size = (tail - head + self->capacity) % self->capacity;
    return PyLong_FromSsize_t(size);
}

/* 检查队列是否为空 */
static PyObject* LockFreeQueue_empty(LockFreeQueue *self, PyObject *args) {
    LONG64 head, tail;

    /* 使用内存屏障确保读取顺序 */
    MemoryBarrier();
    head = self->head;
    tail = self->tail;
    MemoryBarrier();

    if (head == tail) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

/* ==================== LockFreeHashMap 实现 ==================== */

/* 无锁哈希表方法声明 */
static PyObject* LockFreeHashMap_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static void LockFreeHashMap_dealloc(LockFreeHashMap *self);
static PyObject* LockFreeHashMap_set(LockFreeHashMap *self, PyObject *args);
static PyObject* LockFreeHashMap_get(LockFreeHashMap *self, PyObject *args);
static PyObject* LockFreeHashMap_remove(LockFreeHashMap *self, PyObject *args);

/* 方法定义 */
static PyMethodDef LockFreeHashMap_methods[] = {
    {"set", (PyCFunction)LockFreeHashMap_set, METH_VARARGS, "Set key-value pair"},
    {"get", (PyCFunction)LockFreeHashMap_get, METH_VARARGS, "Get value by key"},
    {"remove", (PyCFunction)LockFreeHashMap_remove, METH_VARARGS, "Remove key-value pair"},
    {NULL, NULL, 0, NULL}
};

/* LockFreeHashMap类型定义 */
PyTypeObject LockFreeHashMapType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_gil.LockFreeHashMap",
    .tp_doc = "Lock-free hash map for high-concurrency scenarios",
    .tp_basicsize = sizeof(LockFreeHashMap),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = LockFreeHashMap_new,
    .tp_dealloc = (destructor)LockFreeHashMap_dealloc,
    .tp_methods = LockFreeHashMap_methods,
};

/* 计算哈希值 */
static Py_hash_t calc_hash(PyObject *key) {
    if (PyUnicode_Check(key)) {
        return PyObject_Hash(key);
    } else if (PyLong_Check(key)) {
        return PyLong_AsSsize_t(key);
    } else {
        return PyObject_Hash(key);
    }
}

/* 初始化哈希表 */
static PyObject* LockFreeHashMap_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    LockFreeHashMap *self;
    Py_ssize_t bucket_count = 16;

    if (!PyArg_ParseTuple(args, "|n", &bucket_count)) {
        return NULL;
    }

    if (bucket_count <= 0) {
        bucket_count = 16;
    }

    self = (LockFreeHashMap *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->buckets = (volatile PyObject **)calloc(bucket_count * 2, sizeof(PyObject *));
        if (self->buckets == NULL) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate hash map buckets");
            return NULL;
        }
        self->bucket_count = bucket_count;
    }
    return (PyObject *)self;
}

/* 清理哈希表 */
static void LockFreeHashMap_dealloc(LockFreeHashMap *self) {
    /* 释放所有Python对象引用 */
    for (Py_ssize_t i = 0; i < self->bucket_count * 2; i += 2) {
        Py_XDECREF((PyObject *)self->buckets[i]);
        Py_XDECREF((PyObject *)self->buckets[i + 1]);
    }

    free((void *)self->buckets);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* 设置键值对 */
static PyObject* LockFreeHashMap_set(LockFreeHashMap *self, PyObject *args) {
    PyObject *key, *value;
    Py_hash_t hash_val;
    Py_ssize_t index;

    if (!PyArg_ParseTuple(args, "OO", &key, &value)) {
        return NULL;
    }

    hash_val = calc_hash(key);
    index = ((Py_ssize_t)hash_val % self->bucket_count) * 2;

    /* 使用CAS操作设置键值对 */
    Py_INCREF(key);
    Py_INCREF(value);

    /* 释放旧值 */
    Py_XDECREF((PyObject *)self->buckets[index]);
    Py_XDECREF((PyObject *)self->buckets[index + 1]);

    /* 设置新值 */
    self->buckets[index] = key;
    self->buckets[index + 1] = value;

    Py_RETURN_NONE;
}

/* 获取值 */
static PyObject* LockFreeHashMap_get(LockFreeHashMap *self, PyObject *args) {
    PyObject *key;
    Py_hash_t hash_val;
    Py_ssize_t index;
    PyObject *stored_key, *value;

    if (!PyArg_ParseTuple(args, "O", &key)) {
        return NULL;
    }

    hash_val = calc_hash(key);
    index = ((Py_ssize_t)hash_val % self->bucket_count) * 2;

    stored_key = (PyObject *)self->buckets[index];
    if (stored_key == NULL) {
        PyErr_SetString(PyExc_KeyError, "Key not found");
        return NULL;
    }

    /* 比较键 */
    if (PyObject_RichCompareBool(key, stored_key, Py_EQ) == 1) {
        value = (PyObject *)self->buckets[index + 1];
        Py_INCREF(value);
        return value;
    }

    PyErr_SetString(PyExc_KeyError, "Key not found");
    return NULL;
}

/* 删除键值对 */
static PyObject* LockFreeHashMap_remove(LockFreeHashMap *self, PyObject *args) {
    PyObject *key;
    Py_hash_t hash_val;
    Py_ssize_t index;
    PyObject *stored_key;

    if (!PyArg_ParseTuple(args, "O", &key)) {
        return NULL;
    }

    hash_val = calc_hash(key);
    index = ((Py_ssize_t)hash_val % self->bucket_count) * 2;

    stored_key = (PyObject *)self->buckets[index];
    if (stored_key == NULL) {
        PyErr_SetString(PyExc_KeyError, "Key not found");
        return NULL;
    }

    /* 比较键 */
    if (PyObject_RichCompareBool(key, stored_key, Py_EQ) == 1) {
        Py_XDECREF((PyObject *)self->buckets[index]);
        Py_XDECREF((PyObject *)self->buckets[index + 1]);
        self->buckets[index] = NULL;
        self->buckets[index + 1] = NULL;
        Py_RETURN_NONE;
    }

    PyErr_SetString(PyExc_KeyError, "Key not found");
    return NULL;
}

/* 获取类型对象 */
PyTypeObject* get_LockFreeQueueType(void) {
    return &LockFreeQueueType;
}

PyTypeObject* get_LockFreeHashMapType(void) {
    return &LockFreeHashMapType;
}

