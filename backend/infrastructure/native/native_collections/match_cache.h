/* -*- coding: utf-8 -*-
 * match_cache.h - 组合撮合缓存类型声明
 */

#ifndef MATCH_CACHE_H
#define MATCH_CACHE_H

#include <Python.h>
#include <Windows.h>

typedef struct {
    PyObject_HEAD
    CRITICAL_SECTION lock;
    PyObject *positions_by_gateway;
    PyObject *accounts_by_gateway;
    PyObject *trades_by_gateway;
    PyObject *trade_stats_by_gateway;
} HighPerfMatchCache;

extern PyTypeObject HighPerfMatchCacheType;

PyTypeObject* get_MatchCacheType(void);

#endif /* MATCH_CACHE_H */


