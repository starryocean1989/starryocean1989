/* -*- coding: utf-8 -*-
 * match_cache.c - 组合撮合缓存实现
 *
 * 该实现提供网关粒度的实时持仓/资金/成交缓存，支持常数时间更新和聚合统计。
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <structmember.h>
#include <stdbool.h>

#include "match_cache.h"

/* ==================== 工具函数声明 ==================== */
static PyObject* ensure_unicode(PyObject *value);
static PyObject* normalize_direction(PyObject *direction_obj);
static int is_buy_direction(PyObject *direction_key);
static PyObject* get_or_create_dict(PyObject *mapping, PyObject *key);
static int update_trade_stats(
    HighPerfMatchCache *self,
    PyObject *gateway_key,
    PyObject *symbol_key,
    PyObject *direction_key,
    double price,
    double volume,
    int factor);
static int extract_double_attr(PyObject *obj, const char *attr_name, double *out_value);

/* ==================== 类型方法声明 ==================== */
static PyObject* HighPerfMatchCache_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int HighPerfMatchCache_init(HighPerfMatchCache *self, PyObject *args, PyObject *kwds);
static void HighPerfMatchCache_dealloc(HighPerfMatchCache *self);

static PyObject* HighPerfMatchCache_upsert_position(HighPerfMatchCache *self, PyObject *position);
static PyObject* HighPerfMatchCache_get_positions(HighPerfMatchCache *self, PyObject *args, PyObject *kwds);
static PyObject* HighPerfMatchCache_has_positions(HighPerfMatchCache *self, PyObject *args);

static PyObject* HighPerfMatchCache_upsert_account(HighPerfMatchCache *self, PyObject *account);
static PyObject* HighPerfMatchCache_get_accounts(HighPerfMatchCache *self, PyObject *args, PyObject *kwds);
static PyObject* HighPerfMatchCache_has_accounts(HighPerfMatchCache *self, PyObject *args);

static PyObject* HighPerfMatchCache_upsert_trade(HighPerfMatchCache *self, PyObject *trade);
static PyObject* HighPerfMatchCache_get_trades(HighPerfMatchCache *self, PyObject *args, PyObject *kwds);
static PyObject* HighPerfMatchCache_get_trade_stats(HighPerfMatchCache *self, PyObject *args, PyObject *kwds);

static PyObject* HighPerfMatchCache_gateway_with_positions(HighPerfMatchCache *self, PyObject *Py_UNUSED(ignored));
static PyObject* HighPerfMatchCache_gateway_with_accounts(HighPerfMatchCache *self, PyObject *Py_UNUSED(ignored));

/* ==================== 类型方法定义 ==================== */
static PyMethodDef HighPerfMatchCache_methods[] = {
    {"upsert_position", (PyCFunction)HighPerfMatchCache_upsert_position, METH_O, "Upsert a position object into cache"},
    {"get_positions", (PyCFunction)HighPerfMatchCache_get_positions, METH_VARARGS | METH_KEYWORDS, "Get positions for gateway"},
    {"has_positions", (PyCFunction)HighPerfMatchCache_has_positions, METH_VARARGS, "Check if gateway has cached positions"},
    {"upsert_account", (PyCFunction)HighPerfMatchCache_upsert_account, METH_O, "Upsert an account object into cache"},
    {"get_accounts", (PyCFunction)HighPerfMatchCache_get_accounts, METH_VARARGS | METH_KEYWORDS, "Get accounts for gateway"},
    {"has_accounts", (PyCFunction)HighPerfMatchCache_has_accounts, METH_VARARGS, "Check if gateway has cached accounts"},
    {"upsert_trade", (PyCFunction)HighPerfMatchCache_upsert_trade, METH_O, "Upsert a trade object and update statistics"},
    {"get_trades", (PyCFunction)HighPerfMatchCache_get_trades, METH_VARARGS | METH_KEYWORDS, "Get trade list for gateway"},
    {"get_trade_stats", (PyCFunction)HighPerfMatchCache_get_trade_stats, METH_VARARGS | METH_KEYWORDS, "Get aggregated trade stats"},
    {"gateway_with_positions", (PyCFunction)HighPerfMatchCache_gateway_with_positions, METH_NOARGS, "List gateways with cached positions"},
    {"gateway_with_accounts", (PyCFunction)HighPerfMatchCache_gateway_with_accounts, METH_NOARGS, "List gateways with cached accounts"},
    {NULL, NULL, 0, NULL}
};

PyTypeObject HighPerfMatchCacheType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "native_collections.HighPerfMatchCache",
    .tp_doc = "High-performance gateway scoped match cache",
    .tp_basicsize = sizeof(HighPerfMatchCache),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = HighPerfMatchCache_new,
    .tp_init = (initproc)HighPerfMatchCache_init,
    .tp_dealloc = (destructor)HighPerfMatchCache_dealloc,
    .tp_methods = HighPerfMatchCache_methods,
};

PyTypeObject* get_MatchCacheType(void) {
    return &HighPerfMatchCacheType;
}

/* ==================== 工具函数实现 ==================== */
static PyObject* ensure_unicode(PyObject *value) {
    if (value == NULL) {
        return NULL;
    }
    if (PyUnicode_Check(value)) {
        Py_INCREF(value);
        return value;
    }
    return PyObject_Str(value);
}

static PyObject* normalize_direction(PyObject *direction_obj) {
    PyObject *candidate = NULL;
    if (direction_obj != NULL) {
        candidate = PyObject_GetAttrString(direction_obj, "name");
        if (candidate && !PyUnicode_Check(candidate)) {
            Py_DECREF(candidate);
            candidate = NULL;
        }
    }
    if (candidate == NULL && direction_obj != NULL) {
        candidate = PyObject_GetAttrString(direction_obj, "value");
        if (candidate && !PyUnicode_Check(candidate)) {
            Py_DECREF(candidate);
            candidate = NULL;
        }
    }
    if (candidate == NULL && direction_obj != NULL) {
        candidate = PyObject_Str(direction_obj);
    }
    if (candidate == NULL) {
        candidate = PyUnicode_FromString("UNKNOWN");
    }
    if (candidate == NULL) {
        return NULL;
    }
    PyObject *upper = PyObject_CallMethod(candidate, "upper", NULL);
    Py_DECREF(candidate);
    if (!upper) {
        PyErr_Clear();
        return PyUnicode_FromString("UNKNOWN");
    }
    return upper;
}

static int is_buy_direction(PyObject *direction_key) {
    if (direction_key == NULL) {
        return 0;
    }
    if (!PyUnicode_Check(direction_key)) {
        return 0;
    }
    if (PyUnicode_CompareWithASCIIString(direction_key, "LONG") == 0) {
        return 1;
    }
    if (PyUnicode_CompareWithASCIIString(direction_key, "BUY") == 0) {
        return 1;
    }
    if (PyUnicode_CompareWithASCIIString(direction_key, "BID") == 0) {
        return 1;
    }
    return 0;
}

static PyObject* get_or_create_dict(PyObject *mapping, PyObject *key) {
    PyObject *dict = PyDict_GetItemWithError(mapping, key);
    if (dict) {
        Py_INCREF(dict);
        return dict;
    }
    if (PyErr_Occurred()) {
        return NULL;
    }
    dict = PyDict_New();
    if (!dict) {
        return NULL;
    }
    if (PyDict_SetItem(mapping, key, dict) < 0) {
        Py_DECREF(dict);
        return NULL;
    }
    return dict;
}

static int update_trade_stats(
    HighPerfMatchCache *self,
    PyObject *gateway_key,
    PyObject *symbol_key,
    PyObject *direction_key,
    double price,
    double volume,
    int factor) {
    PyObject *stats_for_gateway = get_or_create_dict(self->trade_stats_by_gateway, gateway_key);
    if (!stats_for_gateway) {
        return -1;
    }

    PyObject *symbol_stats = PyDict_GetItemWithError(stats_for_gateway, symbol_key);
    if (!symbol_stats && PyErr_Occurred()) {
        Py_DECREF(stats_for_gateway);
        return -1;
    }

    if (!symbol_stats) {
        if (factor < 0) {
            Py_DECREF(stats_for_gateway);
            return 0;
        }
        symbol_stats = PyDict_New();
        if (!symbol_stats) {
            Py_DECREF(stats_for_gateway);
            return -1;
        }
        if (PyDict_SetItem(stats_for_gateway, symbol_key, symbol_stats) < 0) {
            Py_DECREF(symbol_stats);
            Py_DECREF(stats_for_gateway);
            return -1;
        }
        Py_DECREF(symbol_stats);
        symbol_stats = PyDict_GetItem(stats_for_gateway, symbol_key);
        if (!symbol_stats) {
            Py_DECREF(stats_for_gateway);
            return -1;
        }
        if (PyDict_SetItemString(symbol_stats, "buy_value", PyFloat_FromDouble(0.0)) < 0 ||
            PyDict_SetItemString(symbol_stats, "sell_value", PyFloat_FromDouble(0.0)) < 0 ||
            PyDict_SetItemString(symbol_stats, "buy_volume", PyFloat_FromDouble(0.0)) < 0 ||
            PyDict_SetItemString(symbol_stats, "sell_volume", PyFloat_FromDouble(0.0)) < 0 ||
            PyDict_SetItemString(symbol_stats, "trade_count", PyLong_FromLong(0)) < 0) {
            Py_DECREF(stats_for_gateway);
            return -1;
        }
    }

    int is_buy = is_buy_direction(direction_key);
    double turnover = price * volume * (double)factor;
    double volume_delta = volume * (double)factor;
    long count_delta = factor;

    const char *value_key = is_buy ? "buy_value" : "sell_value";
    const char *volume_key = is_buy ? "buy_volume" : "sell_volume";

    PyObject *value_obj = PyDict_GetItemString(symbol_stats, value_key);
    PyObject *volume_obj = PyDict_GetItemString(symbol_stats, volume_key);
    PyObject *count_obj = PyDict_GetItemString(symbol_stats, "trade_count");

    double current_value = value_obj ? PyFloat_AsDouble(value_obj) : 0.0;
    if (PyErr_Occurred()) {
        PyErr_Clear();
        current_value = 0.0;
    }
    double current_volume = volume_obj ? PyFloat_AsDouble(volume_obj) : 0.0;
    if (PyErr_Occurred()) {
        PyErr_Clear();
        current_volume = 0.0;
    }
    long current_count = count_obj ? PyLong_AsLong(count_obj) : 0;
    if (PyErr_Occurred()) {
        PyErr_Clear();
        current_count = 0;
    }

    PyObject *new_value = PyFloat_FromDouble(current_value + turnover);
    PyObject *new_volume = PyFloat_FromDouble(current_volume + volume_delta);
    PyObject *new_count = PyLong_FromLong(current_count + count_delta);

    if (!new_value || !new_volume || !new_count) {
        Py_XDECREF(new_value);
        Py_XDECREF(new_volume);
        Py_XDECREF(new_count);
        Py_DECREF(stats_for_gateway);
        return -1;
    }

    if (PyDict_SetItemString(symbol_stats, value_key, new_value) < 0 ||
        PyDict_SetItemString(symbol_stats, volume_key, new_volume) < 0 ||
        PyDict_SetItemString(symbol_stats, "trade_count", new_count) < 0) {
        Py_DECREF(new_value);
        Py_DECREF(new_volume);
        Py_DECREF(new_count);
        Py_DECREF(stats_for_gateway);
        return -1;
    }

    Py_DECREF(new_value);
    Py_DECREF(new_volume);
    Py_DECREF(new_count);
    Py_DECREF(stats_for_gateway);
    return 0;
}

static int extract_double_attr(PyObject *obj, const char *attr_name, double *out_value) {
    PyObject *attr = PyObject_GetAttrString(obj, attr_name);
    if (!attr) {
        return -1;
    }
    double value = PyFloat_AsDouble(attr);
    Py_DECREF(attr);
    if (PyErr_Occurred()) {
        PyErr_Clear();
        return -1;
    }
    *out_value = value;
    return 0;
}

/* ==================== 生命周期管理 ==================== */
static PyObject* HighPerfMatchCache_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    HighPerfMatchCache *self = (HighPerfMatchCache *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->positions_by_gateway = NULL;
        self->accounts_by_gateway = NULL;
        self->trades_by_gateway = NULL;
        self->trade_stats_by_gateway = NULL;
    }
    return (PyObject *)self;
}

static int HighPerfMatchCache_init(HighPerfMatchCache *self, PyObject *args, PyObject *kwds) {
    InitializeCriticalSection(&self->lock);
    self->positions_by_gateway = PyDict_New();
    if (!self->positions_by_gateway) {
        return -1;
    }
    self->accounts_by_gateway = PyDict_New();
    if (!self->accounts_by_gateway) {
        return -1;
    }
    self->trades_by_gateway = PyDict_New();
    if (!self->trades_by_gateway) {
        return -1;
    }
    self->trade_stats_by_gateway = PyDict_New();
    if (!self->trade_stats_by_gateway) {
        return -1;
    }
    return 0;
}

static void HighPerfMatchCache_dealloc(HighPerfMatchCache *self) {
    DeleteCriticalSection(&self->lock);

    Py_XDECREF(self->positions_by_gateway);
    Py_XDECREF(self->accounts_by_gateway);
    Py_XDECREF(self->trades_by_gateway);
    Py_XDECREF(self->trade_stats_by_gateway);

    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* ==================== 辅助函数 ==================== */
static int extract_position_keys(PyObject *position, PyObject **gateway_key, PyObject **symbol_key, PyObject **direction_key) {
    PyObject *gateway = PyObject_GetAttrString(position, "gateway_name");
    if (!gateway) {
        return -1;
    }
    PyObject *gateway_unicode = ensure_unicode(gateway);
    Py_DECREF(gateway);
    if (!gateway_unicode) {
        return -1;
    }

    PyObject *symbol = PyObject_GetAttrString(position, "vt_symbol");
    if (!symbol) {
        PyErr_Clear();
        symbol = PyObject_GetAttrString(position, "symbol");
    }
    if (!symbol) {
        Py_DECREF(gateway_unicode);
        return -1;
    }
    PyObject *symbol_unicode = ensure_unicode(symbol);
    Py_DECREF(symbol);
    if (!symbol_unicode) {
        Py_DECREF(gateway_unicode);
        return -1;
    }

    PyObject *direction_obj = PyObject_GetAttrString(position, "direction");
    PyObject *direction_unicode = normalize_direction(direction_obj);
    Py_XDECREF(direction_obj);
    if (!direction_unicode) {
        Py_DECREF(gateway_unicode);
        Py_DECREF(symbol_unicode);
        return -1;
    }

    *gateway_key = gateway_unicode;
    *symbol_key = symbol_unicode;
    *direction_key = direction_unicode;
    return 0;
}

static int extract_trade_basic(PyObject *trade, PyObject **symbol_key, PyObject **direction_key, double *price, double *volume) {
    PyObject *symbol = PyObject_GetAttrString(trade, "vt_symbol");
    if (!symbol) {
        PyErr_Clear();
        symbol = PyObject_GetAttrString(trade, "symbol");
    }
    if (!symbol) {
        return -1;
    }
    PyObject *symbol_unicode = ensure_unicode(symbol);
    Py_DECREF(symbol);
    if (!symbol_unicode) {
        return -1;
    }

    PyObject *direction_obj = PyObject_GetAttrString(trade, "direction");
    PyObject *direction_unicode = normalize_direction(direction_obj);
    Py_XDECREF(direction_obj);
    if (!direction_unicode) {
        Py_DECREF(symbol_unicode);
        return -1;
    }

    if (extract_double_attr(trade, "price", price) < 0) {
        Py_DECREF(symbol_unicode);
        Py_DECREF(direction_unicode);
        return -1;
    }
    if (extract_double_attr(trade, "volume", volume) < 0) {
        Py_DECREF(symbol_unicode);
        Py_DECREF(direction_unicode);
        return -1;
    }

    *symbol_key = symbol_unicode;
    *direction_key = direction_unicode;
    return 0;
}

static int extract_trade_keys(
    PyObject *trade,
    PyObject **gateway_key,
    PyObject **trade_id_key,
    PyObject **symbol_key,
    PyObject **direction_key,
    double *price,
    double *volume) {
    PyObject *gateway = PyObject_GetAttrString(trade, "gateway_name");
    if (!gateway) {
        return -1;
    }
    PyObject *gateway_unicode = ensure_unicode(gateway);
    Py_DECREF(gateway);
    if (!gateway_unicode) {
        return -1;
    }

    PyObject *trade_id = PyObject_GetAttrString(trade, "vt_tradeid");
    if (!trade_id) {
        PyErr_Clear();
        trade_id = PyObject_GetAttrString(trade, "tradeid");
    }
    if (!trade_id) {
        Py_DECREF(gateway_unicode);
        return -1;
    }
    PyObject *trade_id_unicode = ensure_unicode(trade_id);
    Py_DECREF(trade_id);
    if (!trade_id_unicode) {
        Py_DECREF(gateway_unicode);
        return -1;
    }

    if (extract_trade_basic(trade, symbol_key, direction_key, price, volume) < 0) {
        Py_DECREF(gateway_unicode);
        Py_DECREF(trade_id_unicode);
        return -1;
    }

    *gateway_key = gateway_unicode;
    *trade_id_key = trade_id_unicode;
    return 0;
}

/* ==================== 业务方法实现 ==================== */
static PyObject* HighPerfMatchCache_upsert_position(HighPerfMatchCache *self, PyObject *position) {
    PyObject *gateway_key = NULL;
    PyObject *symbol_key = NULL;
    PyObject *direction_key = NULL;

    if (extract_position_keys(position, &gateway_key, &symbol_key, &direction_key) < 0) {
        Py_XDECREF(gateway_key);
        Py_XDECREF(symbol_key);
        Py_XDECREF(direction_key);
        PyErr_SetString(PyExc_ValueError, "Position object missing required attributes");
        return NULL;
    }

    EnterCriticalSection(&self->lock);

    PyObject *gateway_positions = get_or_create_dict(self->positions_by_gateway, gateway_key);
    if (!gateway_positions) {
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(symbol_key);
        Py_DECREF(direction_key);
        return NULL;
    }

    PyObject *key_tuple = PyTuple_Pack(2, symbol_key, direction_key);
    if (!key_tuple) {
        Py_DECREF(gateway_positions);
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(symbol_key);
        Py_DECREF(direction_key);
        return NULL;
    }

    if (PyDict_SetItem(gateway_positions, key_tuple, position) < 0) {
        Py_DECREF(key_tuple);
        Py_DECREF(gateway_positions);
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(symbol_key);
        Py_DECREF(direction_key);
        return NULL;
    }

    Py_DECREF(key_tuple);
    Py_DECREF(gateway_positions);
    LeaveCriticalSection(&self->lock);

    Py_DECREF(gateway_key);
    Py_DECREF(symbol_key);
    Py_DECREF(direction_key);

    Py_RETURN_NONE;
}

static PyObject* HighPerfMatchCache_get_positions(HighPerfMatchCache *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"gateway", NULL};
    PyObject *gateway = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|O", kwlist, &gateway)) {
        return NULL;
    }

    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);

    if (gateway == Py_None || gateway == NULL) {
        PyObject *gw_key, *inner_dict;
        Py_ssize_t pos = 0;
        while (PyDict_Next(self->positions_by_gateway, &pos, &gw_key, &inner_dict)) {
            PyObject *inner_key, *position_obj;
            Py_ssize_t inner_pos = 0;
            while (PyDict_Next(inner_dict, &inner_pos, &inner_key, &position_obj)) {
                Py_INCREF(position_obj);
                if (PyList_Append(result, position_obj) < 0) {
                    Py_DECREF(position_obj);
                    LeaveCriticalSection(&self->lock);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(position_obj);
            }
        }
    } else {
        PyObject *gateway_key = ensure_unicode(gateway);
        if (!gateway_key) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(result);
            return NULL;
        }
        PyObject *inner_dict = PyDict_GetItemWithError(self->positions_by_gateway, gateway_key);
        Py_DECREF(gateway_key);
        if (inner_dict) {
            PyObject *inner_key, *position_obj;
            Py_ssize_t inner_pos = 0;
            while (PyDict_Next(inner_dict, &inner_pos, &inner_key, &position_obj)) {
                Py_INCREF(position_obj);
                if (PyList_Append(result, position_obj) < 0) {
                    Py_DECREF(position_obj);
                    LeaveCriticalSection(&self->lock);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(position_obj);
            }
        } else if (PyErr_Occurred()) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(result);
            return NULL;
        }
    }

    LeaveCriticalSection(&self->lock);
    return result;
}

static PyObject* HighPerfMatchCache_has_positions(HighPerfMatchCache *self, PyObject *args) {
    PyObject *gateway;
    if (!PyArg_ParseTuple(args, "O", &gateway)) {
        return NULL;
    }
    PyObject *gateway_key = ensure_unicode(gateway);
    if (!gateway_key) {
        return NULL;
    }

    int has_data = 0;
    EnterCriticalSection(&self->lock);
    PyObject *inner = PyDict_GetItemWithError(self->positions_by_gateway, gateway_key);
    if (inner && PyDict_Size(inner) > 0) {
        has_data = 1;
    } else if (!inner && PyErr_Occurred()) {
        has_data = 0;
        PyErr_Clear();
    }
    LeaveCriticalSection(&self->lock);
    Py_DECREF(gateway_key);

    if (has_data) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject* HighPerfMatchCache_upsert_account(HighPerfMatchCache *self, PyObject *account) {
    PyObject *gateway = PyObject_GetAttrString(account, "gateway_name");
    if (!gateway) {
        PyErr_SetString(PyExc_ValueError, "Account object missing gateway_name");
        return NULL;
    }
    PyObject *gateway_key = ensure_unicode(gateway);
    Py_DECREF(gateway);
    if (!gateway_key) {
        return NULL;
    }

    PyObject *account_id = PyObject_GetAttrString(account, "accountid");
    if (!account_id) {
        PyErr_Clear();
        account_id = PyObject_GetAttrString(account, "account_id");
    }
    if (!account_id) {
        Py_DECREF(gateway_key);
        PyErr_SetString(PyExc_ValueError, "Account object missing accountid");
        return NULL;
    }
    PyObject *account_key = ensure_unicode(account_id);
    Py_DECREF(account_id);
    if (!account_key) {
        Py_DECREF(gateway_key);
        return NULL;
    }

    EnterCriticalSection(&self->lock);
    PyObject *gateway_accounts = get_or_create_dict(self->accounts_by_gateway, gateway_key);
    if (!gateway_accounts) {
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(account_key);
        return NULL;
    }

    if (PyDict_SetItem(gateway_accounts, account_key, account) < 0) {
        Py_DECREF(gateway_accounts);
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(account_key);
        return NULL;
    }

    Py_DECREF(gateway_accounts);
    LeaveCriticalSection(&self->lock);
    Py_DECREF(gateway_key);
    Py_DECREF(account_key);
    Py_RETURN_NONE;
}

static PyObject* HighPerfMatchCache_get_accounts(HighPerfMatchCache *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"gateway", NULL};
    PyObject *gateway = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|O", kwlist, &gateway)) {
        return NULL;
    }

    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);
    if (gateway == Py_None || gateway == NULL) {
        PyObject *gw_key, *inner_dict;
        Py_ssize_t pos = 0;
        while (PyDict_Next(self->accounts_by_gateway, &pos, &gw_key, &inner_dict)) {
            PyObject *acc_key, *account_obj;
            Py_ssize_t inner_pos = 0;
            while (PyDict_Next(inner_dict, &inner_pos, &acc_key, &account_obj)) {
                Py_INCREF(account_obj);
                if (PyList_Append(result, account_obj) < 0) {
                    Py_DECREF(account_obj);
                    LeaveCriticalSection(&self->lock);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(account_obj);
            }
        }
    } else {
        PyObject *gateway_key = ensure_unicode(gateway);
        if (!gateway_key) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(result);
            return NULL;
        }
        PyObject *inner_dict = PyDict_GetItemWithError(self->accounts_by_gateway, gateway_key);
        Py_DECREF(gateway_key);
        if (inner_dict) {
            PyObject *acc_key, *account_obj;
            Py_ssize_t inner_pos = 0;
            while (PyDict_Next(inner_dict, &inner_pos, &acc_key, &account_obj)) {
                Py_INCREF(account_obj);
                if (PyList_Append(result, account_obj) < 0) {
                    Py_DECREF(account_obj);
                    LeaveCriticalSection(&self->lock);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(account_obj);
            }
        } else if (PyErr_Occurred()) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(result);
            return NULL;
        }
    }
    LeaveCriticalSection(&self->lock);
    return result;
}

static PyObject* HighPerfMatchCache_has_accounts(HighPerfMatchCache *self, PyObject *args) {
    PyObject *gateway;
    if (!PyArg_ParseTuple(args, "O", &gateway)) {
        return NULL;
    }
    PyObject *gateway_key = ensure_unicode(gateway);
    if (!gateway_key) {
        return NULL;
    }

    int has_data = 0;
    EnterCriticalSection(&self->lock);
    PyObject *inner = PyDict_GetItemWithError(self->accounts_by_gateway, gateway_key);
    if (inner && PyDict_Size(inner) > 0) {
        has_data = 1;
    } else if (!inner && PyErr_Occurred()) {
        has_data = 0;
        PyErr_Clear();
    }
    LeaveCriticalSection(&self->lock);
    Py_DECREF(gateway_key);

    if (has_data) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject* HighPerfMatchCache_upsert_trade(HighPerfMatchCache *self, PyObject *trade) {
    PyObject *gateway_key = NULL;
    PyObject *trade_id_key = NULL;
    PyObject *symbol_key = NULL;
    PyObject *direction_key = NULL;
    double price = 0.0;
    double volume = 0.0;

    if (extract_trade_keys(trade, &gateway_key, &trade_id_key, &symbol_key, &direction_key, &price, &volume) < 0) {
        Py_XDECREF(gateway_key);
        Py_XDECREF(trade_id_key);
        Py_XDECREF(symbol_key);
        Py_XDECREF(direction_key);
        PyErr_SetString(PyExc_ValueError, "Trade object missing required attributes");
        return NULL;
    }

    EnterCriticalSection(&self->lock);

    PyObject *gateway_trades = get_or_create_dict(self->trades_by_gateway, gateway_key);
    if (!gateway_trades) {
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(trade_id_key);
        Py_DECREF(symbol_key);
        Py_DECREF(direction_key);
        return NULL;
    }

    PyObject *existing_trade = PyDict_GetItemWithError(gateway_trades, trade_id_key);
    if (existing_trade && PyErr_Occurred()) {
        PyErr_Clear();
        existing_trade = NULL;
    }

    if (existing_trade) {
        PyObject *old_symbol = NULL;
        PyObject *old_direction = NULL;
        double old_price = 0.0;
        double old_volume = 0.0;

        if (extract_trade_basic(existing_trade, &old_symbol, &old_direction, &old_price, &old_volume) == 0) {
            if (update_trade_stats(self, gateway_key, old_symbol, old_direction, old_price, old_volume, -1) < 0) {
                Py_XDECREF(old_symbol);
                Py_XDECREF(old_direction);
                Py_DECREF(gateway_trades);
                LeaveCriticalSection(&self->lock);
                Py_DECREF(gateway_key);
                Py_DECREF(trade_id_key);
                Py_DECREF(symbol_key);
                Py_DECREF(direction_key);
                return NULL;
            }
        }
        Py_XDECREF(old_symbol);
        Py_XDECREF(old_direction);
    }

    if (PyDict_SetItem(gateway_trades, trade_id_key, trade) < 0) {
        Py_DECREF(gateway_trades);
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(trade_id_key);
        Py_DECREF(symbol_key);
        Py_DECREF(direction_key);
        return NULL;
    }

    if (update_trade_stats(self, gateway_key, symbol_key, direction_key, price, volume, 1) < 0) {
        Py_DECREF(gateway_trades);
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_DECREF(trade_id_key);
        Py_DECREF(symbol_key);
        Py_DECREF(direction_key);
        return NULL;
    }

    Py_DECREF(gateway_trades);
    LeaveCriticalSection(&self->lock);

    Py_DECREF(gateway_key);
    Py_DECREF(trade_id_key);
    Py_DECREF(symbol_key);
    Py_DECREF(direction_key);

    Py_RETURN_NONE;
}

static PyObject* HighPerfMatchCache_get_trades(HighPerfMatchCache *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"gateway", NULL};
    PyObject *gateway = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|O", kwlist, &gateway)) {
        return NULL;
    }

    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);
    if (gateway == Py_None || gateway == NULL) {
        PyObject *gw_key, *inner_dict;
        Py_ssize_t pos = 0;
        while (PyDict_Next(self->trades_by_gateway, &pos, &gw_key, &inner_dict)) {
            PyObject *trade_id, *trade_obj;
            Py_ssize_t inner_pos = 0;
            while (PyDict_Next(inner_dict, &inner_pos, &trade_id, &trade_obj)) {
                Py_INCREF(trade_obj);
                if (PyList_Append(result, trade_obj) < 0) {
                    Py_DECREF(trade_obj);
                    LeaveCriticalSection(&self->lock);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(trade_obj);
            }
        }
    } else {
        PyObject *gateway_key = ensure_unicode(gateway);
        if (!gateway_key) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(result);
            return NULL;
        }
        PyObject *inner_dict = PyDict_GetItemWithError(self->trades_by_gateway, gateway_key);
        Py_DECREF(gateway_key);
        if (inner_dict) {
            PyObject *trade_id, *trade_obj;
            Py_ssize_t inner_pos = 0;
            while (PyDict_Next(inner_dict, &inner_pos, &trade_id, &trade_obj)) {
                Py_INCREF(trade_obj);
                if (PyList_Append(result, trade_obj) < 0) {
                    Py_DECREF(trade_obj);
                    LeaveCriticalSection(&self->lock);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(trade_obj);
            }
        } else if (PyErr_Occurred()) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(result);
            return NULL;
        }
    }
    LeaveCriticalSection(&self->lock);
    return result;
}

static PyObject* HighPerfMatchCache_get_trade_stats(HighPerfMatchCache *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"gateway", "symbol", NULL};
    PyObject *gateway;
    PyObject *symbol = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|O", kwlist, &gateway, &symbol)) {
        return NULL;
    }

    PyObject *gateway_key = ensure_unicode(gateway);
    if (!gateway_key) {
        return NULL;
    }

    PyObject *symbol_key = NULL;
    if (symbol != Py_None && symbol != NULL) {
        symbol_key = ensure_unicode(symbol);
        if (!symbol_key) {
            Py_DECREF(gateway_key);
            return NULL;
        }
    }

    PyObject *result = NULL;

    EnterCriticalSection(&self->lock);
    PyObject *stats_for_gateway = PyDict_GetItemWithError(self->trade_stats_by_gateway, gateway_key);
    if (!stats_for_gateway) {
        if (PyErr_Occurred()) {
            PyErr_Clear();
        }
        result = PyDict_New();
        LeaveCriticalSection(&self->lock);
        Py_DECREF(gateway_key);
        Py_XDECREF(symbol_key);
        return result;
    }

    if (!symbol_key) {
        result = PyDict_New();
        if (!result) {
            LeaveCriticalSection(&self->lock);
            Py_DECREF(gateway_key);
            return NULL;
        }
        PyObject *sym_key, *stats_dict;
        Py_ssize_t pos = 0;
        while (PyDict_Next(stats_for_gateway, &pos, &sym_key, &stats_dict)) {
            PyObject *copy = PyDict_Copy(stats_dict);
            if (!copy) {
                Py_DECREF(result);
                LeaveCriticalSection(&self->lock);
                Py_DECREF(gateway_key);
                return NULL;
            }
            if (PyDict_SetItem(result, sym_key, copy) < 0) {
                Py_DECREF(copy);
                Py_DECREF(result);
                LeaveCriticalSection(&self->lock);
                Py_DECREF(gateway_key);
                return NULL;
            }
            Py_DECREF(copy);
        }
    } else {
        PyObject *stats_dict = PyDict_GetItemWithError(stats_for_gateway, symbol_key);
        if (stats_dict) {
            result = PyDict_Copy(stats_dict);
        } else {
            if (PyErr_Occurred()) {
                PyErr_Clear();
            }
            result = PyDict_New();
        }
    }

    LeaveCriticalSection(&self->lock);
    Py_DECREF(gateway_key);
    Py_XDECREF(symbol_key);
    return result;
}

static PyObject* HighPerfMatchCache_gateway_with_positions(HighPerfMatchCache *self, PyObject *Py_UNUSED(ignored)) {
    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);
    PyObject *gw_key, *inner_dict;
    Py_ssize_t pos = 0;
    while (PyDict_Next(self->positions_by_gateway, &pos, &gw_key, &inner_dict)) {
        if (PyDict_Size(inner_dict) > 0) {
            Py_INCREF(gw_key);
            if (PyList_Append(result, gw_key) < 0) {
                Py_DECREF(gw_key);
                LeaveCriticalSection(&self->lock);
                Py_DECREF(result);
                return NULL;
            }
            Py_DECREF(gw_key);
        }
    }
    LeaveCriticalSection(&self->lock);
    return result;
}

static PyObject* HighPerfMatchCache_gateway_with_accounts(HighPerfMatchCache *self, PyObject *Py_UNUSED(ignored)) {
    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    EnterCriticalSection(&self->lock);
    PyObject *gw_key, *inner_dict;
    Py_ssize_t pos = 0;
    while (PyDict_Next(self->accounts_by_gateway, &pos, &gw_key, &inner_dict)) {
        if (PyDict_Size(inner_dict) > 0) {
            Py_INCREF(gw_key);
            if (PyList_Append(result, gw_key) < 0) {
                Py_DECREF(gw_key);
                LeaveCriticalSection(&self->lock);
                Py_DECREF(result);
                return NULL;
            }
            Py_DECREF(gw_key);
        }
    }
    LeaveCriticalSection(&self->lock);
    return result;
}


