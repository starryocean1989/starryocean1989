/* -*- coding: utf-8 -*- */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "../native_log_bridge.h"
#include <structmember.h>


static PyObject *ensure_unicode(PyObject *obj) {
  if (PyUnicode_Check(obj)) {
    Py_INCREF(obj);
    return obj;
  }
  return PyObject_Str(obj);
}

static PyObject *convert_with_fields(PyObject *obj, PyObject *fields) {
  PyObject *result = PyDict_New();
  if (!result) {
    return NULL;
  }

  Py_ssize_t len = PySequence_Length(fields);
  if (len < 0) {
    Py_DECREF(result);
    return NULL;
  }

  for (Py_ssize_t i = 0; i < len; ++i) {
    PyObject *field = PySequence_GetItem(fields, i);
    if (!field) {
      Py_DECREF(result);
      return NULL;
    }

    PyObject *name = ensure_unicode(field);
    Py_DECREF(field);
    if (!name) {
      Py_DECREF(result);
      return NULL;
    }

    PyObject *value = PyObject_GetAttr(obj, name);
    if (!value) {
      const char *fname = PyUnicode_AsUTF8(name);
      char details_buf[256];
      if (fname) {
        snprintf(details_buf, sizeof(details_buf), "missing_attr=%s", fname);
      } else {
        snprintf(details_buf, sizeof(details_buf),
                 "missing_attr=<non-unicode>");
      }
      native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                            "convert_with_fields", __LINE__,
                            "Object missing required attribute", details_buf);
      Py_DECREF(name);
      Py_DECREF(result);
      return NULL;
    }

    if (PyDict_SetItem(result, name, value) < 0) {
      Py_DECREF(name);
      Py_DECREF(value);
      Py_DECREF(result);
      return NULL;
    }

    Py_DECREF(name);
    Py_DECREF(value);
  }

  return result;
}

static PyObject *convert_object(PyObject *obj, PyObject *fields) {
  if (PyDict_Check(obj)) {
    Py_INCREF(obj);
    return obj;
  }

  if (fields && fields != Py_None) {
    PyObject *converted = convert_with_fields(obj, fields);
    if (!converted) {
      PyErr_Format(PyExc_AttributeError,
                   "object of type %.200s missing required attribute",
                   Py_TYPE(obj)->tp_name);
    }
    return converted;
  }

  PyObject *to_dict = PyObject_GetAttrString(obj, "to_dict");
  if (to_dict) {
    PyObject *converted = PyObject_CallObject(to_dict, NULL);
    Py_DECREF(to_dict);
    if (!converted) {
      native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                            "convert_object", __LINE__, "to_dict() call failed",
                            Py_TYPE(obj)->tp_name);
      return NULL;
    }
    if (!PyDict_Check(converted)) {
      Py_DECREF(converted);
      PyErr_SetString(PyExc_TypeError, "to_dict() must return dict");
      native_log_bridge_log(
          NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion", "convert_object",
          __LINE__, "to_dict() returned non-dict", Py_TYPE(obj)->tp_name);
      return NULL;
    }
    return converted;
  }
  PyErr_Clear();

  PyObject *mapping = PyObject_GetAttrString(obj, "__dict__");
  if (mapping && PyDict_Check(mapping)) {
    PyObject *converted = PyDict_Copy(mapping);
    Py_DECREF(mapping);
    native_log_bridge_log(NATIVE_LOG_LEVEL_DEBUG, "native_vnpy_conversion",
                          "convert_object", __LINE__,
                          "converted using __dict__", Py_TYPE(obj)->tp_name);
    return converted;
  }
  Py_XDECREF(mapping);

  PyObject *as_dict = PyObject_CallMethod(obj, "as_dict", NULL);
  if (as_dict) {
    if (!PyDict_Check(as_dict)) {
      Py_DECREF(as_dict);
      PyErr_SetString(PyExc_TypeError, "as_dict() must return dict");
      native_log_bridge_log(
          NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion", "convert_object",
          __LINE__, "as_dict() returned non-dict", Py_TYPE(obj)->tp_name);
      return NULL;
    }
    return as_dict;
  }
  PyErr_Clear();

  PyErr_Format(PyExc_TypeError,
               "cannot convert object of type %.200s; provide fields or "
               "to_dict/__dict__",
               Py_TYPE(obj)->tp_name);
  native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                        "convert_object", __LINE__, "conversion path not found",
                        Py_TYPE(obj)->tp_name);
  return NULL;
}

static PyObject *maybe_arrow_table(PyObject *pylist) {
  PyObject *pyarrow = PyImport_ImportModule("pyarrow");
  if (!pyarrow) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_WARNING, "native_vnpy_conversion",
                          "maybe_arrow_table", __LINE__,
                          "pyarrow not installed", NULL);
    return NULL;
  }

  PyObject *table_cls = PyObject_GetAttrString(pyarrow, "Table");
  Py_DECREF(pyarrow);
  if (!table_cls) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "maybe_arrow_table", __LINE__,
                          "pyarrow.Table missing", NULL);
    return NULL;
  }

  PyObject *from_pylist = PyObject_GetAttrString(table_cls, "from_pylist");
  Py_DECREF(table_cls);
  if (!from_pylist) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "maybe_arrow_table", __LINE__,
                          "pyarrow.Table.from_pylist missing", NULL);
    return NULL;
  }

  PyObject *args = PyTuple_Pack(1, pylist);
  if (!args) {
    Py_DECREF(from_pylist);
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "maybe_arrow_table", __LINE__,
                          "failed to build args for from_pylist", NULL);
    return NULL;
  }

  PyObject *table = PyObject_Call(from_pylist, args, NULL);
  Py_DECREF(from_pylist);
  Py_DECREF(args);
  if (!table) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "maybe_arrow_table", __LINE__,
                          "pyarrow.Table.from_pylist failed", NULL);
  }
  return table;
}

static PyObject *batch_convert(PyObject *Py_UNUSED(self), PyObject *args,
                               PyObject *kwargs) {
  static char *kwlist[] = {"objects", "data_type", "output", "fields", NULL};
  PyObject *objects = NULL;
  const char *data_type = NULL; // 预留扩展参数
  const char *output = "dict";
  PyObject *fields = Py_None;
  clock_t start_clock = clock();

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|szO", kwlist, &objects,
                                   &data_type, &output, &fields)) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "batch_convert", __LINE__, "argument parsing failed",
                          NULL);
    return NULL;
  }

  PyObject *seq = PySequence_Fast(objects, "objects must be iterable");
  if (!seq) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "batch_convert", __LINE__, "objects not iterable",
                          NULL);
    return NULL;
  }

  Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
  PyObject **items = PySequence_Fast_ITEMS(seq);

  PyObject *converted_list = PyList_New(size);
  if (!converted_list) {
    Py_DECREF(seq);
    return NULL;
  }

  native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, "native_vnpy_conversion",
                        "batch_convert", __LINE__, "begin batch conversion",
                        NULL);

  for (Py_ssize_t i = 0; i < size; ++i) {
    PyObject *converted = convert_object(items[i], fields);
    if (!converted) {
      Py_DECREF(converted_list);
      Py_DECREF(seq);
      const char *type_name = Py_TYPE(items[i])->tp_name;
      native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                            "batch_convert", __LINE__, "item conversion failed",
                            type_name);
      return NULL;
    }
    PyList_SET_ITEM(converted_list, i, converted);
  }

  Py_DECREF(seq);

  if (output &&
      (strcmp(output, "arrow") == 0 || strcmp(output, "pyarrow") == 0)) {
    PyObject *table = maybe_arrow_table(converted_list);
    if (!table) {
      Py_DECREF(converted_list);
      native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                            "batch_convert", __LINE__,
                            "arrow conversion failed", NULL);
      return NULL;
    }
    Py_DECREF(converted_list);
    clock_t end_clock = clock();
    char details_buf[256];
    double duration_ms =
        (double)(end_clock - start_clock) * 1000.0 / (double)CLOCKS_PER_SEC;
    snprintf(details_buf, sizeof(details_buf),
             "count=%zd, output=arrow, duration_ms=%.3f", size, duration_ms);
    native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, "native_vnpy_conversion",
                          "batch_convert", __LINE__,
                          "batch conversion completed", details_buf);
    return table;
  }

  clock_t end_clock2 = clock();
  char details_buf2[256];
  double duration_ms2 =
      (double)(end_clock2 - start_clock) * 1000.0 / (double)CLOCKS_PER_SEC;
  snprintf(details_buf2, sizeof(details_buf2),
           "count=%zd, output=dict, duration_ms=%.3f", size, duration_ms2);
  native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, "native_vnpy_conversion",
                        "batch_convert", __LINE__, "batch conversion completed",
                        details_buf2);
  return converted_list;
}

static PyObject *convert_one(PyObject *Py_UNUSED(self), PyObject *args,
                             PyObject *kwargs) {
  static char *kwlist[] = {"obj", "fields", NULL};
  PyObject *obj = NULL;
  PyObject *fields = Py_None;

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist, &obj,
                                   &fields)) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "convert_one", __LINE__, "argument parsing failed",
                          NULL);
    return NULL;
  }

  PyObject *converted = convert_object(obj, fields);
  if (!converted) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion", "convert_one",
        __LINE__, "single object conversion failed", Py_TYPE(obj)->tp_name);
    return NULL;
  }
  native_log_bridge_log(NATIVE_LOG_LEVEL_DEBUG, "native_vnpy_conversion",
                        "convert_one", __LINE__, "single object converted",
                        Py_TYPE(obj)->tp_name);
  return converted;
}

static PyObject *get_version(PyObject *Py_UNUSED(self),
                             PyObject *Py_UNUSED(args)) {
  return PyUnicode_FromString("1.0.0");
}

static PyMethodDef module_methods[] = {
    {"batch_convert", (PyCFunction)batch_convert, METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR(
         "batch_convert(objects, data_type='', output='dict', fields=None)")},
    {"convert_one", (PyCFunction)convert_one, METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("convert_one(obj, fields=None) -> dict")},
    {"get_version", (PyCFunction)get_version, METH_NOARGS,
     PyDoc_STR("get_version() -> str")},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    .m_name = "native_vnpy_conversion.conversion",
    .m_doc = "High performance batch converter for VnPy style objects",
    .m_size = -1,
    .m_methods = module_methods,
};

PyMODINIT_FUNC PyInit_conversion(void) {
  PyObject *module = PyModule_Create(&module_def);
  if (!module) {
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "PyInit_conversion", __LINE__,
                          "module creation failed", NULL);
    return NULL;
  }

  if (PyModule_AddIntConstant(module, "CONVERSION_AVAILABLE", 1) < 0) {
    Py_DECREF(module);
    native_log_bridge_log(NATIVE_LOG_LEVEL_ERROR, "native_vnpy_conversion",
                          "PyInit_conversion", __LINE__,
                          "failed to add CONVERSION_AVAILABLE", NULL);
    return NULL;
  }

  native_log_bridge_log(NATIVE_LOG_LEVEL_INFO, "native_vnpy_conversion",
                        "PyInit_conversion", __LINE__,
                        "native_vnpy_conversion module initialized", NULL);

  return module;
}
