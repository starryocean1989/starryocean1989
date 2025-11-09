// DataConverter - pybind11 C++ module for fast record-to-bar field conversion
// Keeps architecture intact and focuses on accelerating Python-side
// conversions.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdio>

extern "C" {
#include "../native_log_bridge.h"
}

namespace {
constexpr const char *kComponentCore = "backend.native.dataconverter.core";
}

namespace py = pybind11;

// Helper: get value from dict with default
template <typename T>
T get_or_default(const py::dict &d, const char *key, const T &def_val) {
  if (d.contains(key)) {
    try {
      return d[key].cast<T>();
    } catch (...) {
      return def_val;
    }
  }
  return def_val;
}

// Normalize common TDX/records keys to vnpy BarData field names
// Input: list of dicts with typical keys: "open", "high", "low", "close",
// "vol", "volume", "amount", "turnover", "datetime"/"date"+"time" Output: list
// of dicts with keys: symbol, exchange, datetime, open_price, high_price,
// low_price, close_price, volume, turnover
py::list convert_records_to_bar_fields(const py::list &records,
                                       const std::string &symbol,
                                       const std::string &exchange) {
  NATIVE_LOG_DEBUG_SIMPLE(
      kComponentCore,
      "convert_records_to_bar_fields",
      __LINE__,
      "records normalization started");

  py::list out;
  // py::list does not support reserve; append items dynamically

  const size_t total_records = records.size();
  size_t skipped_non_dict = 0;
  size_t datetime_cast_failures = 0;
  size_t timestamp_cast_failures = 0;
  size_t volume_cast_failures = 0;
  size_t turnover_cast_failures = 0;

  for (const auto &item : records) {
    if (!py::isinstance<py::dict>(item)) {
      ++skipped_non_dict;
      continue; // skip non-dict entries
    }
    py::dict r = item.cast<py::dict>();

    // datetime normalization
    std::string dt;
    if (r.contains("datetime")) {
      try {
        dt = r["datetime"].cast<std::string>();
      } catch (...) {
        ++datetime_cast_failures;
        dt = std::string();
      }
    } else {
      // Try date + time
      std::string d = get_or_default<std::string>(r, "date", std::string());
      std::string t = get_or_default<std::string>(r, "time", std::string());
      if (!d.empty()) {
        if (!t.empty())
          dt = d + " " + t;
        else
          dt = d;
      } else {
        // Fallback: if a timestamp exists
        if (r.contains("timestamp")) {
          try {
            dt = r["timestamp"].cast<std::string>();
          } catch (...) {
            ++timestamp_cast_failures;
            dt = std::string();
          }
        }
      }
    }

    // price/volume/turnover
    double open = 0.0, high = 0.0, low = 0.0, close = 0.0;
    double turnover = 0.0; // amount/turnover
    long long volume = 0;

    open = get_or_default<double>(r, "open",
                                  get_or_default<double>(r, "open_price", 0.0));
    high = get_or_default<double>(r, "high",
                                  get_or_default<double>(r, "high_price", 0.0));
    low = get_or_default<double>(r, "low",
                                 get_or_default<double>(r, "low_price", 0.0));
    close = get_or_default<double>(
        r, "close", get_or_default<double>(r, "close_price", 0.0));

    // volume can be under "vol" or "volume"
    if (r.contains("volume")) {
      try {
        volume = r["volume"].cast<long long>();
      } catch (...) {
        ++volume_cast_failures;
      }
    } else if (r.contains("vol")) {
      try {
        volume = r["vol"].cast<long long>();
      } catch (...) {
        ++volume_cast_failures;
      }
    }

    // turnover/amount
    if (r.contains("turnover")) {
      try {
        turnover = r["turnover"].cast<double>();
      } catch (...) {
        ++turnover_cast_failures;
      }
    } else if (r.contains("amount")) {
      try {
        turnover = r["amount"].cast<double>();
      } catch (...) {
        ++turnover_cast_failures;
      }
    }

    py::dict o;
    o["symbol"] = symbol;
    o["exchange"] = exchange;
    o["datetime"] = dt;
    o["open_price"] = open;
    o["high_price"] = high;
    o["low_price"] = low;
    o["close_price"] = close;
    o["volume"] = volume;
    o["turnover"] = turnover;

    out.append(o);
  }

  const size_t converted_records = out.size();

  char summary[256];
  std::snprintf(
      summary,
      sizeof(summary),
      "records normalization finished: total=%zu, converted=%zu, skipped_non_dict=%zu, datetime_cast_failures=%zu, timestamp_cast_failures=%zu, volume_cast_failures=%zu, turnover_cast_failures=%zu",
      total_records,
      converted_records,
      skipped_non_dict,
      datetime_cast_failures,
      timestamp_cast_failures,
      volume_cast_failures,
      turnover_cast_failures);
  NATIVE_LOG_INFO_SIMPLE(
      kComponentCore,
      "convert_records_to_bar_fields",
      __LINE__,
      summary);

  if (skipped_non_dict || datetime_cast_failures || timestamp_cast_failures ||
      volume_cast_failures || turnover_cast_failures) {
    NATIVE_LOG_WARNING_SIMPLE(
        kComponentCore,
        "convert_records_to_bar_fields",
        __LINE__,
        "records normalization encountered recoverable issues, see info summary for counters");
  }

  return out;
}

PYBIND11_MODULE(dataconverter, m) {
  m.doc() = "Native DataConverter for fast record-to-bar field conversion "
            "(vnpy-friendly)";
  m.def("convert_records_to_bar_fields", &convert_records_to_bar_fields,
        py::arg("records"), py::arg("symbol"), py::arg("exchange"),
        "Convert list of records to standardized bar field dicts for "
        "vnpy.BarData");
}
