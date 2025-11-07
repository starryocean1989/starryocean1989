#define PY_SSIZE_T_CLEAN
#include <Python.h>

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
        return NULL;
    }

    PyObject *working_df = df;
    Py_INCREF(working_df);
    PyObject *temp_obj = NULL;

    if (include_index) {
        PyObject *reset_index_method = PyObject_GetAttrString(working_df, "reset_index");
        if (reset_index_method == NULL) {
            Py_DECREF(working_df);
            return NULL;
        }

        temp_obj = PyObject_CallFunction(reset_index_method, "");
        Py_DECREF(reset_index_method);
        if (temp_obj == NULL) {
            Py_DECREF(working_df);
            return NULL;
        }

        Py_DECREF(working_df);
        working_df = temp_obj;
        temp_obj = NULL;

        if (index_field != NULL && index_field[0] != '\0') {
            PyObject *columns_attr = PyObject_GetAttrString(working_df, "columns");
            if (columns_attr == NULL) {
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *iter = PyObject_GetIter(columns_attr);
            Py_DECREF(columns_attr);
            if (iter == NULL) {
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *first_name = PyIter_Next(iter);
            Py_DECREF(iter);
            if (first_name == NULL) {
                Py_DECREF(working_df);
                PyErr_SetString(PyExc_RuntimeError, "无法确定索引列名称");
                return NULL;
            }

            PyObject *rename_method = PyObject_GetAttrString(working_df, "rename");
            if (rename_method == NULL) {
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *columns_dict = PyDict_New();
            if (columns_dict == NULL) {
                Py_DECREF(rename_method);
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            PyObject *new_name = PyUnicode_FromString(index_field);
            if (new_name == NULL) {
                Py_DECREF(columns_dict);
                Py_DECREF(rename_method);
                Py_DECREF(first_name);
                Py_DECREF(working_df);
                return NULL;
            }

            if (PyDict_SetItem(columns_dict, first_name, new_name) != 0) {
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
                Py_DECREF(columns_dict);
                Py_DECREF(rename_method);
                Py_DECREF(working_df);
                return NULL;
            }

            if (PyDict_SetItemString(kwargs_dict, "columns", columns_dict) != 0) {
                Py_DECREF(columns_dict);
                Py_DECREF(kwargs_dict);
                Py_DECREF(rename_method);
                Py_DECREF(working_df);
                return NULL;
            }

            Py_DECREF(columns_dict);

            PyObject *empty_args = PyTuple_New(0);
            if (empty_args == NULL) {
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
        Py_DECREF(working_df);
        return NULL;
    }

    PyObject *records_str = PyUnicode_FromString("records");
    if (records_str == NULL) {
        Py_DECREF(to_dict_method);
        Py_DECREF(working_df);
        return NULL;
    }

    PyObject *method_args = PyTuple_Pack(1, records_str);
    Py_DECREF(records_str);
    if (method_args == NULL) {
        Py_DECREF(to_dict_method);
        Py_DECREF(working_df);
        return NULL;
    }

    PyObject *records = PyObject_Call(to_dict_method, method_args, NULL);
    Py_DECREF(to_dict_method);
    Py_DECREF(method_args);
    Py_DECREF(working_df);

    if (records == NULL) {
        return NULL;
    }

    if (!PyList_Check(records)) {
        Py_DECREF(records);
        PyErr_SetString(PyExc_TypeError, "to_dict('records') 返回值类型错误");
        return NULL;
    }

    return records;
}

static PyObject *dataframe_quality_counters(PyObject *self, PyObject *args) {
    PyObject *df = NULL;
    PyObject *columns = NULL;

    if (!PyArg_ParseTuple(args, "OO", &df, &columns)) {
        return NULL;
    }

    PyObject *index_attr = PyObject_GetAttrString(df, "index");
    if (index_attr == NULL) {
        return NULL;
    }

    PyObject *duplicated = PyObject_CallMethod(index_attr, "duplicated", NULL);
    Py_DECREF(index_attr);
    if (duplicated == NULL) {
        return NULL;
    }

    PyObject *dup_count_obj = PyObject_CallMethod(duplicated, "sum", NULL);
    Py_DECREF(duplicated);
    if (dup_count_obj == NULL) {
        return NULL;
    }

    long long duplicate_count = PyLong_AsLongLong(dup_count_obj);
    Py_DECREF(dup_count_obj);
    if (PyErr_Occurred()) {
        return NULL;
    }

    PyObject *subset = PyObject_GetItem(df, columns);
    if (subset == NULL) {
        return NULL;
    }

    PyObject *isna = PyObject_CallMethod(subset, "isna", NULL);
    Py_DECREF(subset);
    if (isna == NULL) {
        return NULL;
    }

    PyObject *any_axis = PyObject_CallMethod(isna, "any", "i", 1);
    Py_DECREF(isna);
    if (any_axis == NULL) {
        return NULL;
    }

    PyObject *invalid_count_obj = PyObject_CallMethod(any_axis, "sum", NULL);
    Py_DECREF(any_axis);
    if (invalid_count_obj == NULL) {
        return NULL;
    }

    long long invalid_count = PyLong_AsLongLong(invalid_count_obj);
    Py_DECREF(invalid_count_obj);
    if (PyErr_Occurred()) {
        return NULL;
    }

    return Py_BuildValue("(LL)", duplicate_count, invalid_count);
}

static PyMethodDef DataFrameOpsMethods[] = {
    {"dataframe_to_records", (PyCFunction)dataframe_to_records, METH_VARARGS | METH_KEYWORDS, "Convert pandas DataFrame to list of dict records"},
    {"dataframe_quality_counters", dataframe_quality_counters, METH_VARARGS, "Return duplicate and invalid counts for DataFrame"},
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
    return PyModule_Create(&dataframeopsmodule);
}


