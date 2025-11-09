#define PY_SSIZE_T_CLEAN
#include <Python.h>
/* 日志桥接宏 */
#include "../native_log_bridge.h"

#define COMPONENT_DATAFRAME_CORE "backend.native.dataframe_ops.core"

static int trim_unicode(PyObject *value, PyObject **out_trimmed, int drop_empty) {
    if (value == NULL || value == Py_None) {
        return 1;
    }

    PyObject *unicode = PyUnicode_FromObject(value);
    if (unicode == NULL) {
        return -1;
    }

    if (PyUnicode_READY(unicode) == -1) {
        Py_DECREF(unicode);
        return -1;
    }

    const Py_ssize_t original_length = PyUnicode_GET_LENGTH(unicode);
    Py_ssize_t start = 0;
    Py_ssize_t end = original_length;

    void *data = PyUnicode_DATA(unicode);
    int kind = PyUnicode_KIND(unicode);

    while (start < end) {
        Py_UCS4 ch = PyUnicode_READ(kind, data, start);
        if (!Py_UNICODE_ISSPACE(ch)) {
            break;
        }
        start++;
    }

    while (end > start) {
        Py_UCS4 ch = PyUnicode_READ(kind, data, end - 1);
        if (!Py_UNICODE_ISSPACE(ch)) {
            break;
        }
        end--;
    }

    if (start == 0 && end == original_length) {
        if (drop_empty && original_length == 0) {
            Py_DECREF(unicode);
            return 1;
        }
        *out_trimmed = unicode;
        return 0;
    }

    PyObject *substring = PyUnicode_Substring(unicode, start, end);
    Py_DECREF(unicode);
    if (substring == NULL) {
        return -1;
    }

    if (drop_empty && PyUnicode_GetLength(substring) == 0) {
        Py_DECREF(substring);
        return 1;
    }

    *out_trimmed = substring;
    return 0;
}

static PyObject *dataframe_to_records(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *df = NULL;
    int include_index = 0;
    const char *index_field = NULL;

    static char *kwlist[] = {"df", "include_index", "index_field", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "O|ps",
            kwlist,
            &df,
            &include_index,
            &index_field)) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "invalid arguments to dataframe_to_records");
        return NULL;
    }

    PyObject *working_df = df;
    Py_INCREF(working_df);
    PyObject *temp_obj = NULL;

    if (include_index) {
        PyObject *reset_index_method = PyObject_GetAttrString(working_df, "reset_index");
        if (reset_index_method == NULL) {
            NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "missing method: reset_index", NULL);
            Py_DECREF(working_df);
            return NULL;
        }

        temp_obj = PyObject_CallFunction(reset_index_method, "");
        Py_DECREF(reset_index_method);
        if (temp_obj == NULL) {
            NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "reset_index call failed");
            Py_DECREF(working_df);
            return NULL;
        }

        Py_DECREF(working_df);
        working_df = temp_obj;
        temp_obj = NULL;

        if (index_field != NULL && index_field[0] != '\0') {
            PyObject *columns_attr = PyObject_GetAttrString(working_df, "columns");
            if (columns_attr == NULL) {
                NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "missing attribute: columns", NULL);
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *iter = PyObject_GetIter(columns_attr);
            Py_DECREF(columns_attr);
            if (iter == NULL) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "columns not iterable");
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *first_name = PyIter_Next(iter);
            Py_DECREF(iter);
            if (first_name == NULL) {
                NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "无法确定索引列名称", NULL);
                Py_DECREF(working_df);
                PyErr_SetString(PyExc_RuntimeError, "无法确定索引列名称");
                return NULL;
            }

            PyObject *rename_method = PyObject_GetAttrString(working_df, "rename");
            if (rename_method == NULL) {
                NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "missing method: rename", NULL);
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *columns_dict = PyDict_New();
            if (columns_dict == NULL) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to create columns dict");
                Py_DECREF(rename_method);
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *new_name = PyUnicode_FromString(index_field);
            if (new_name == NULL) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to create new index name");
                Py_DECREF(columns_dict);
                Py_DECREF(rename_method);
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            if (PyDict_SetItem(columns_dict, first_name, new_name) != 0) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to set columns mapping");
                Py_DECREF(new_name);
                Py_DECREF(columns_dict);
                Py_DECREF(rename_method);
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            Py_DECREF(new_name);
            Py_DECREF(first_name);

            PyObject *kwargs_dict = PyDict_New();
            if (kwargs_dict == NULL) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to create kwargs dict");
                Py_DECREF(columns_dict);
                Py_DECREF(rename_method);
                Py_DECREF(working_df);
                return NULL;
            }

            if (PyDict_SetItemString(kwargs_dict, "columns", columns_dict) != 0) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to set kwargs: columns");
                Py_DECREF(columns_dict);
                Py_DECREF(kwargs_dict);
                Py_DECREF(rename_method);
                Py_DECREF(working_df);
                return NULL;
            }

            Py_DECREF(columns_dict);

            PyObject *empty_args = PyTuple_New(0);
            if (empty_args == NULL) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to create empty args");
                Py_DECREF(kwargs_dict);
                Py_DECREF(rename_method);
                Py_DECREF(working_df);
                return NULL;
            }

            temp_obj = PyObject_Call(rename_method, empty_args, kwargs_dict);
            Py_DECREF(empty_args);
            Py_DECREF(kwargs_dict);
            Py_DECREF(rename_method);
            if (temp_obj == NULL) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "rename call failed");
                Py_DECREF(working_df);
                return NULL;
            }

            Py_DECREF(working_df);
            working_df = temp_obj;
            temp_obj = NULL;
        }
    }

    PyObject *to_dict_method = PyObject_GetAttrString(working_df, "to_dict");
    if (to_dict_method == NULL) {
        NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "missing method: to_dict", NULL);
        Py_DECREF(working_df);
        return NULL;
    }

    PyObject *records_str = PyUnicode_FromString("records");
    if (records_str == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to create 'records' string");
        Py_DECREF(to_dict_method);
        Py_DECREF(working_df);
        return NULL;
    }

    PyObject *method_args = PyTuple_Pack(1, records_str);
    Py_DECREF(records_str);
    if (method_args == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "failed to create method args");
        Py_DECREF(to_dict_method);
        Py_DECREF(working_df);
        return NULL;
    }

    PyObject *records = PyObject_Call(to_dict_method, method_args, NULL);
    Py_DECREF(to_dict_method);
    Py_DECREF(method_args);
    Py_DECREF(working_df);

    if (records == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "to_dict('records') call failed");
        return NULL;
    }

    if (!PyList_Check(records)) {
        Py_DECREF(records);
        PyErr_SetString(PyExc_TypeError, "to_dict('records') 返回值类型错误");
        NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_to_records", __LINE__, "to_dict('records') 返回值类型错误", NULL);
        return NULL;
    }

    return records;
}

static PyObject *dataframe_quality_counters(PyObject *self, PyObject *args) {
    PyObject *df = NULL;
    PyObject *columns = NULL;

    if (!PyArg_ParseTuple(args, "OO", &df, &columns)) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "invalid arguments to dataframe_quality_counters");
        return NULL;
    }

    PyObject *index_attr = PyObject_GetAttrString(df, "index");
    if (index_attr == NULL) {
        NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "missing attribute: index", NULL);
        return NULL;
    }

    PyObject *duplicated = PyObject_CallMethod(index_attr, "duplicated", NULL);
    Py_DECREF(index_attr);
    if (duplicated == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "index.duplicated call failed");
        return NULL;
    }

    PyObject *dup_count_obj = PyObject_CallMethod(duplicated, "sum", NULL);
    Py_DECREF(duplicated);
    if (dup_count_obj == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "duplicated.sum call failed");
        return NULL;
    }

    long long duplicate_count = PyLong_AsLongLong(dup_count_obj);
    Py_DECREF(dup_count_obj);
    if (PyErr_Occurred()) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "failed to convert duplicate_count");
        return NULL;
    }

    PyObject *subset = PyObject_GetItem(df, columns);
    if (subset == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "df[columns] failed");
        return NULL;
    }

    PyObject *isna = PyObject_CallMethod(subset, "isna", NULL);
    Py_DECREF(subset);
    if (isna == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "subset.isna call failed");
        return NULL;
    }

    PyObject *any_axis = PyObject_CallMethod(isna, "any", "i", 1);
    Py_DECREF(isna);
    if (any_axis == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "isna.any(axis=1) failed");
        return NULL;
    }

    PyObject *invalid_count_obj = PyObject_CallMethod(any_axis, "sum", NULL);
    Py_DECREF(any_axis);
    if (invalid_count_obj == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "any_axis.sum call failed");
        return NULL;
    }

    long long invalid_count = PyLong_AsLongLong(invalid_count_obj);
    Py_DECREF(invalid_count_obj);
    if (PyErr_Occurred()) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "dataframe_quality_counters", __LINE__, "failed to convert invalid_count");
        return NULL;
    }

    return Py_BuildValue("(LL)", duplicate_count, invalid_count);
}

static PyObject *filter_symbols(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *records_obj = NULL;
    int deduplicate = 1;
    int drop_empty_code = 1;
    int require_name = 0;

    static char *kwlist[] = {"records", "deduplicate", "drop_empty_code", "require_name", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "O|ppp",
            kwlist,
            &records_obj,
            &deduplicate,
            &drop_empty_code,
            &require_name)) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "invalid arguments to filter_symbols");
        return NULL;
    }

    PyObject *records = PySequence_Fast(records_obj, "records must be a sequence");
    if (records == NULL) {
        NATIVE_LOG_ERROR_DETAILS(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "records must be a sequence", NULL);
        return NULL;
    }

    PyObject *result = PyList_New(0);
    if (result == NULL) {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "failed to allocate result list");
        Py_DECREF(records);
        return NULL;
    }

    PyObject *seen_codes = NULL;
    if (deduplicate) {
        seen_codes = PySet_New(NULL);
        if (seen_codes == NULL) {
            NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "failed to create seen_codes set");
            Py_DECREF(records);
            Py_DECREF(result);
            return NULL;
        }
    }

    PyObject **items = PySequence_Fast_ITEMS(records);
    const Py_ssize_t count = PySequence_Fast_GET_SIZE(records);

    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject *item = items[index];
        if (!PyDict_Check(item)) {
            continue;
        }

        PyObject *code_trim = NULL;
        int code_state = trim_unicode(PyDict_GetItemString(item, "code"), &code_trim, drop_empty_code);
        if (code_state != 0) {
            if (code_state < 0) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "trim_unicode on code failed");
                Py_DECREF(records);
                Py_XDECREF(code_trim);
                Py_XDECREF(seen_codes);
                Py_DECREF(result);
                return NULL;
            }
            Py_XDECREF(code_trim);
            continue;
        }

        if (require_name) {
            PyObject *name_trim = NULL;
            int name_state = trim_unicode(PyDict_GetItemString(item, "name"), &name_trim, 1);
            if (name_state != 0) {
                if (name_state < 0) {
                    NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "trim_unicode on name failed");
                    Py_DECREF(records);
                    Py_DECREF(code_trim);
                    Py_XDECREF(name_trim);
                    Py_XDECREF(seen_codes);
                    Py_DECREF(result);
                    return NULL;
                }
                Py_DECREF(code_trim);
                Py_XDECREF(name_trim);
                continue;
            }
            Py_DECREF(name_trim);
        }

        if (deduplicate) {
            int contains = PySet_Contains(seen_codes, code_trim);
            if (contains == 1) {
                Py_DECREF(code_trim);
                continue;
            }
            if (contains == -1) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "PySet_Contains returned error");
                Py_DECREF(records);
                Py_DECREF(code_trim);
                Py_DECREF(seen_codes);
                Py_DECREF(result);
                return NULL;
            }
            if (PySet_Add(seen_codes, code_trim) != 0) {
                NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "PySet_Add failed");
                Py_DECREF(records);
                Py_DECREF(code_trim);
                Py_DECREF(seen_codes);
                Py_DECREF(result);
                return NULL;
            }
        }

        Py_DECREF(code_trim);

        if (PyList_Append(result, item) != 0) {
            NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "filter_symbols", __LINE__, "PyList_Append failed");
            Py_DECREF(records);
            Py_XDECREF(seen_codes);
            Py_DECREF(result);
            return NULL;
        }
    }

    Py_DECREF(records);
    Py_XDECREF(seen_codes);
    return result;
}

static PyMethodDef DataFrameOpsMethods[] = {
    {"dataframe_to_records", (PyCFunction)dataframe_to_records, METH_VARARGS | METH_KEYWORDS, "Convert pandas DataFrame to list of dict records"},
    {"dataframe_quality_counters", dataframe_quality_counters, METH_VARARGS, "Return duplicate and invalid counts for DataFrame"},
    {"filter_symbols", (PyCFunction)filter_symbols, METH_VARARGS | METH_KEYWORDS, "Filter symbol dictionaries with native optimizations"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef dataframeopsmodule = {
    PyModuleDef_HEAD_INIT,
    "dataframe_ops",
    "Native dataframe helpers",
    -1,
    DataFrameOpsMethods,
};

PyMODINIT_FUNC PyInit_dataframe_ops(void) {
    PyObject *m = PyModule_Create(&dataframeopsmodule);
    if (m) {
        NATIVE_LOG_INFO(COMPONENT_DATAFRAME_CORE, "PyInit_dataframe_ops", __LINE__, "dataframe_ops module loaded");
    } else {
        NATIVE_LOG_ERROR(COMPONENT_DATAFRAME_CORE, "PyInit_dataframe_ops", __LINE__, "failed to create dataframe_ops module");
    }
    return m;
}


