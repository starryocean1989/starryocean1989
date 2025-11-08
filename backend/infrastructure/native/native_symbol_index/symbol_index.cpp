#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace py = pybind11;

class SymbolIndex {
public:
    SymbolIndex() = default;

    void build(const py::iterable& records) {
        code_index_.clear();
        market_index_.clear();
        sorted_codes_.clear();

        for (const auto& item : records) {
            py::handle handle = item;
            if (!py::isinstance<py::dict>(handle)) {
                continue;
            }
            py::dict record = py::reinterpret_borrow<py::dict>(handle);

            py::object code_obj = record.attr("get")("code", py::none());
            if (code_obj.is_none()) {
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
        }

        sorted_codes_.reserve(code_index_.size());
        for (const auto& item : code_index_) {
            sorted_codes_.push_back(item.first);
        }
        std::sort(sorted_codes_.begin(), sorted_codes_.end());
    }

    py::object get_symbol(const std::string& code) const {
        const auto normalised = normalise_code(code);
        const auto iter = code_index_.find(normalised);
        if (iter == code_index_.end()) {
            return py::none();
        }
        return iter->second;
    }

    std::vector<std::string> get_codes_by_market(const std::string& market) const {
        const auto iter = market_index_.find(market);
        if (iter == market_index_.end()) {
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
        return codes;
    }

    std::vector<std::string> all_codes() const {
        return sorted_codes_;
    }

    std::size_t size() const {
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


