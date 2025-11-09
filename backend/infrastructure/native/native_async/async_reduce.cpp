#include <Python.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <string>
#include <vector>

#include "../native_log_bridge.h"

namespace py = pybind11;

#define ASYNC_COMPONENT "backend.native.async.core"

#define ASYNC_LOG(level, message, details) \
    native_log_bridge_log(level, ASYNC_COMPONENT, __FUNCTION__, __LINE__, message, details)

#define ASYNC_LOG_INFO(message, details) \
    ASYNC_LOG(NATIVE_LOG_LEVEL_INFO, message, details)

#define ASYNC_LOG_WARNING(message, details) \
    ASYNC_LOG(NATIVE_LOG_LEVEL_WARNING, message, details)

#define ASYNC_LOG_ERROR(message, details) \
    ASYNC_LOG(NATIVE_LOG_LEVEL_ERROR, message, details)

py::dict reduce_task_results(
    const py::iterable& task_results,
    std::size_t total,
    std::size_t progress_stride,
    py::object progress_callback,
    py::object symbols_obj) {

    /* Log function entry */
    char init_details[256];
    sprintf(
        init_details,
        "total=%zu, progress_stride=%zu, has_symbols=%d, has_callback=%d",
        total,
        progress_stride,
        !symbols_obj.is_none(),
        !progress_callback.is_none());
    ASYNC_LOG_INFO("Starting task result reduction", init_details);

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
            std::string symbol_str = symbol.is_none() ? "unknown" : py::str(symbol).cast<std::string>();
            std::string repr_str = py::str(repr).cast<std::string>();

            if (!symbol.is_none()) {
                error_messages.append(py::str(symbol_str + ": " + repr_str));
                error_symbols.append(symbol);
            } else {
                error_messages.append(repr);
                error_symbols.append(py::none());
            }
            error_count += 1;
            handled = true;

            /* Log task execution exception */
            char error_details[512];
            sprintf(error_details, "index=%zu, symbol=%s, exception=%s", index, symbol_str.c_str(), repr_str.c_str());
            ASYNC_LOG_ERROR("Task result contains exception", error_details);
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
                        std::string symbol_str = py::str(symbol).cast<std::string>();
                        std::string message = "[progress-callback] ";
                        message += err.what();
                        error_messages.append(py::str(message));
                        error_symbols.append(symbol);

                        /* Log progress callback error */
                        char callback_error_details[512];
                        sprintf(callback_error_details, "symbol=%s, error=%s", symbol_str.c_str(), err.what());
                        ASYNC_LOG_ERROR("Progress callback failed", callback_error_details);

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

    /* Log function completion */
    char completion_details[256];
    sprintf(
        completion_details,
        "processed=%zu, success=%zu, null=%zu, errors=%zu",
        completed,
        success_count,
        null_count,
        error_count);
    ASYNC_LOG_INFO("Task result reduction completed", completion_details);

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

    native_log_bridge_log(
        NATIVE_LOG_LEVEL_INFO,
        "backend.native.async.module",
        "async_reduce_module_init",
        __LINE__,
        "async_reduce module initialized",
        nullptr);
}


