// -*- coding: utf-8 -*-
// Backtest metrics - pybind11 C++ module
// Provides fast computations for Sharpe ratio and max drawdown.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cmath>
#include <limits>
#include <sstream>
#include <string>

#include "../native_log_bridge.h"

namespace py = pybind11;

namespace {

constexpr const char *kComponentCore = "backend.native.metrics.core";
constexpr const char *kComponentWrapper = "backend.native.metrics.wrapper";

inline void log_warning(const char *function, int line, const std::string &message, const std::string &details = {}) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_WARNING,
        kComponentCore,
        function,
        line,
        message.c_str(),
        details.empty() ? nullptr : details.c_str());
}

inline void log_info(const char *function, int line, const std::string &message, const std::string &details = {}) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_INFO,
        kComponentCore,
        function,
        line,
        message.c_str(),
        details.empty() ? nullptr : details.c_str());
}

}  // namespace

double compute_sharpe(const std::vector<double> &returns, double risk_free_rate) {
    if (returns.empty()) {
        log_warning(
            __FUNCTION__,
            __LINE__,
            "compute_sharpe received empty returns; falling back to 0.0",
            "size=0");
        return 0.0;
    }

    double mean = 0.0;
    for (double r : returns) {
        mean += r;
    }
    mean /= static_cast<double>(returns.size());

    double excess = mean - risk_free_rate;
    double var = 0.0;
    for (double r : returns) {
        double diff = r - mean;
        var += diff * diff;
    }
    var /= static_cast<double>(returns.size());

    double stddev = std::sqrt(var);
    if (stddev <= std::numeric_limits<double>::epsilon()) {
        std::ostringstream oss;
        oss << "stddev=" << stddev << ", epsilon=" << std::numeric_limits<double>::epsilon()
            << ", risk_free_rate=" << risk_free_rate;
        log_warning(__FUNCTION__, __LINE__, "compute_sharpe detected near-zero variance; returning 0.0", oss.str());
        return 0.0;
    }

    double sharpe = excess / stddev;
    return sharpe;
}

double compute_max_drawdown(const std::vector<double> &equity) {
    if (equity.empty()) {
        log_warning(
            __FUNCTION__,
            __LINE__,
            "compute_max_drawdown received empty equity series; falling back to 0.0",
            "size=0");
        return 0.0;
    }

    double peak = equity.front();
    double max_dd = 0.0;
    for (double v : equity) {
        if (v > peak) {
            peak = v;
        }
        double denominator = (peak == 0.0 ? 1.0 : peak);
        double dd = (peak - v) / denominator;
        if (dd > max_dd) {
            max_dd = dd;
        }
    }
    return max_dd;
}

PYBIND11_MODULE(metrics_native, m) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_INFO,
        kComponentWrapper,
        __FUNCTION__,
        __LINE__,
        "metrics_native module initialised",
        nullptr);

    m.doc() = "Native metrics for backtesting (Sharpe, max drawdown)";
    m.def(
        "compute_sharpe",
        &compute_sharpe,
        py::arg("returns"),
        py::arg("risk_free_rate") = 0.0,
        "Compute Sharpe ratio for a sequence of returns");
    m.def(
        "compute_max_drawdown",
        &compute_max_drawdown,
        py::arg("equity"),
        "Compute maximum drawdown for an equity curve");
}

