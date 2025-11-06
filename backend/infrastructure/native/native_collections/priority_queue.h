#ifndef PRIORITY_QUEUE_H
#define PRIORITY_QUEUE_H

#include <Python.h>
#include <Windows.h>

/* 前向声明 */
struct _PriorityNode;
typedef struct _PriorityNode PriorityNode;

/* 类型声明 */
typedef struct {
    PyObject_HEAD
    CRITICAL_SECTION lock;
    PriorityNode *head;
    Py_ssize_t size;
} HighPerfPriorityQueue;

/* 类型对象声明 */
extern PyTypeObject HighPerfPriorityQueueType;

/* 函数声明 */
PyTypeObject* get_PriorityQueueType(void);

#endif /* PRIORITY_QUEUE_H */

