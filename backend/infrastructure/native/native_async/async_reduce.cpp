#include <Python.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <string>
#include <vector>

namespace py = pybind11;

py::dict reduce_task_results(
    const py::iterable& task_results,
    std::size_t total,
    std::size_t progress_stride,
    py::object progress_callback,
    py::object symbols_obj) {
    py::list normalized_items;
    py::list error_messages;
    py::list error_symbols;
    py::list milestones;

    std::size_t completed = 0;
    std::size_t success_count = 0;
    std::size_t null_count = 0;
    std::size_t error_count = 0;
    const std::size_t stride = progress_stride;

    py::sequence symbols_seq;
    bool has_symbol_sequence = false;
    std::size_t symbols_length = 0;
    if (!symbols_obj.is_none()) {
        symbols_seq = py::reinterpret_borrow<py::sequence>(symbols_obj);
        has_symbol_sequence = true;
        symbols_length = py::len(symbols_seq);
    }

    std::size_t index = 0;

    for (const auto& entry : task_results) {
        completed += 1;
        py::object symbol = py::none();

        if (has_symbol_sequence && index < symbols_length) {
            symbol = symbols_seq[index];
        }

        bool handled = false;

        if (PyExceptionInstance_Check(entry.ptr())) {
            py::object repr = py::reinterpret_borrow<py::object>(PyObject_Repr(entry.ptr()));
            if (!symbol.is_none()) {
                std::string symbol_str = py::str(symbol).cast<std::string>();
                std::string repr_str = py::str(repr).cast<std::string>();
                error_messages.append(py::str(symbol_str + ": " + repr_str));
                error_symbols.append(symbol);
            } else {
                error_messages.append(repr);
                error_symbols.append(py::none());
            }
            error_count += 1;
            handled = true;
        } else if (py::isinstance<py::tuple>(entry) && py::len(entry) == 2) {
            auto tuple_entry = py::reinterpret_borrow<py::tuple>(entry);
            symbol = tuple_entry[0];
            py::object value = tuple_entry[1];

            if (PyExceptionInstance_Check(value.ptr())) {
                py::object repr = py::reinterpret_borrow<py::object>(PyObject_Repr(value.ptr()));
                std::string symbol_str = py::str(symbol).cast<std::string>();
                std::string repr_str = py::str(repr).cast<std::string>();
                error_messages.append(py::str(symbol_str + ": " + repr_str));
                error_symbols.append(symbol);
                error_count += 1;
                handled = true;
            } else {
                normalized_items.append(py::make_tuple(symbol, value));

                if (value.is_none()) {
                    null_count += 1;
                } else {
                    success_count += 1;
                }

                if (!progress_callback.is_none()) {
                    try {
                        progress_callback(completed, total, symbol);
                    } catch (py::error_already_set& err) {
                        std::string message = "[progress-callback] ";
                        message += err.what();
                        error_messages.append(py::str(message));
                        error_symbols.append(symbol);
                        err.restore();
                        PyErr_Clear();
                    }
                }
                handled = true;
            }
        }

        if (!handled) {
            py::object repr = py::reinterpret_borrow<py::object>(PyObject_Repr(entry.ptr()));
            if (!symbol.is_none()) {
                std::string symbol_str = py::str(symbol).cast<std::string>();
                std::string repr_str = py::str(repr).cast<std::string>();
                error_messages.append(py::str(symbol_str + ": " + repr_str));
                error_symbols.append(symbol);
            } else {
                error_messages.append(repr);
                error_symbols.append(py::none());
            }
            error_count += 1;
        }

        if (stride > 0 && (completed % stride == 0 || completed == total)) {
            milestones.append(py::make_tuple(completed, success_count, null_count, error_count));
        }

        index += 1;
    }

    py::dict summary;
    summary["total"] = completed;
    summary["success_count"] = success_count;
    summary["null_count"] = null_count;
    summary["error_count"] = error_count;

    py::dict result;
    result["summary"] = summary;
    result["items"] = normalized_items;
    result["errors"] = error_messages;
    result["error_symbols"] = error_symbols;
    result["milestones"] = milestones;

    return result;
}

PYBIND11_MODULE(async_reduce, m) {
    m.doc() = "Native asynchronous task reduction helpers";

    m.def(
        "reduce_task_results",
        &reduce_task_results,
        py::arg("task_results"),
        py::arg("total"),
        py::arg("progress_stride") = 0,
        py::arg("progress_callback") = py::none(),
        py::arg("symbols") = py::none()
    );
}


