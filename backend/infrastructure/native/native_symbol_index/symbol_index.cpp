#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include <sstream>

extern "C" {
#include "../native_log_bridge.h"
}

namespace {
constexpr const char *COMPONENT_CORE = "backend.native.native_symbol_index.core";

inline void log_core(int level, const char *function, int line, const std::string &message, const std::string &details = {}) {
    native_log_bridge_log(level, COMPONENT_CORE, function, line, message.c_str(), details.empty() ? nullptr : details.c_str());
}
}  // namespace

namespace py = pybind11;

class SymbolIndex {
public:
    SymbolIndex() = default;

    void build(const py::iterable& records) {
        code_index_.clear();
        market_index_.clear();
        sorted_codes_.clear();

        std::size_t processed = 0;
        std::size_t skipped_invalid = 0;
        std::size_t skipped_missing_code = 0;

        for (const auto& item : records) {
            py::handle handle = item;
            if (!py::isinstance<py::dict>(handle)) {
                ++skipped_invalid;
                continue;
            }
            py::dict record = py::reinterpret_borrow<py::dict>(handle);

            py::object code_obj = record.attr("get")("code", py::none());
            if (code_obj.is_none()) {
                ++skipped_missing_code;
                continue;
            }
            std::string code = py::cast<std::string>(code_obj);
            if (code.empty()) {
                continue;
            }

            py::object market_obj = record.attr("get")("market", py::none());
            if (market_obj.is_none()) {
                market_obj = record.attr("get")("market_name", py::none());
            }
            std::string market = market_obj.is_none() ? "" : py::cast<std::string>(market_obj);

            code_index_[code] = record;
            market_index_[market].push_back(record);
            ++processed;
        }

        sorted_codes_.reserve(code_index_.size());
        for (const auto& item : code_index_) {
            sorted_codes_.push_back(item.first);
        }
        std::sort(sorted_codes_.begin(), sorted_codes_.end());

        std::ostringstream oss;
        oss << "{\"processed\":" << processed
            << ",\"skipped_invalid\":" << skipped_invalid
            << ",\"skipped_missing_code\":" << skipped_missing_code
            << ",\"distinct_codes\":" << sorted_codes_.size()
            << "}";
        log_core(
            NATIVE_LOG_LEVEL_INFO,
            "SymbolIndex::build",
            __LINE__,
            "Native symbol index build completed",
            oss.str());
    }

    py::object get_symbol(const std::string& code) const {
        const auto normalised = normalise_code(code);
        const auto iter = code_index_.find(normalised);
        if (iter == code_index_.end()) {
            log_core(
                NATIVE_LOG_LEVEL_DEBUG,
                "SymbolIndex::get_symbol",
                __LINE__,
                "Symbol not found",
                std::string("{\"code\":\"") + normalised + "\"}");
            return py::none();
        }
        log_core(
            NATIVE_LOG_LEVEL_DEBUG,
            "SymbolIndex::get_symbol",
            __LINE__,
            "Symbol resolved",
            std::string("{\"code\":\"") + normalised + "\"}");
        return iter->second;
    }

    std::vector<std::string> get_codes_by_market(const std::string& market) const {
        const auto iter = market_index_.find(market);
        if (iter == market_index_.end()) {
            log_core(
                NATIVE_LOG_LEVEL_DEBUG,
                "SymbolIndex::get_codes_by_market",
                __LINE__,
                "Market not found",
                std::string("{\"market\":\"") + market + "\"}");
            return {};
        }

        std::vector<std::string> codes;
        codes.reserve(iter->second.size());
        for (const auto& record : iter->second) {
            py::object code_obj = record.attr("get")("code", py::none());
            if (code_obj.is_none()) {
                continue;
            }
            codes.push_back(py::cast<std::string>(code_obj));
        }

        std::sort(codes.begin(), codes.end());
        log_core(
            NATIVE_LOG_LEVEL_DEBUG,
            "SymbolIndex::get_codes_by_market",
            __LINE__,
            "Codes fetched for market",
            std::string("{\"market\":\"") + market + "\",\"count\":" + std::to_string(codes.size()) + "}");
        return codes;
    }

    std::vector<std::string> all_codes() const {
        log_core(
            NATIVE_LOG_LEVEL_DEBUG,
            "SymbolIndex::all_codes",
            __LINE__,
            "Enumerating all codes",
            std::string("{\"count\":") + std::to_string(sorted_codes_.size()) + "}");
        return sorted_codes_;
    }

    std::size_t size() const {
        log_core(
            NATIVE_LOG_LEVEL_DEBUG,
            "SymbolIndex::size",
            __LINE__,
            "Symbol index size queried",
            std::string("{\"count\":") + std::to_string(code_index_.size()) + "}");
        return code_index_.size();
    }

private:
    static std::string normalise_code(const std::string& code) {
        if (code.size() >= 6) {
            return code;
        }
        std::string result = std::string(6 - code.size(), '0');
        result += code;
        return result;
    }

    std::unordered_map<std::string, py::dict> code_index_;
    std::unordered_map<std::string, std::vector<py::dict>> market_index_;
    std::vector<std::string> sorted_codes_;
};

PYBIND11_MODULE(symbol_index, m) {
    py::class_<SymbolIndex>(m, "SymbolIndex")
        .def(py::init<>())
        .def("build", &SymbolIndex::build, py::arg("records"))
        .def("get_symbol", &SymbolIndex::get_symbol, py::arg("code"))
        .def("get_codes_by_market", &SymbolIndex::get_codes_by_market, py::arg("market"))
        .def("all_codes", &SymbolIndex::all_codes)
        .def("size", &SymbolIndex::size);
}


