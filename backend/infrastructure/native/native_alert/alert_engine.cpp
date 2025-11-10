// AlertEngine - pybind11 C++ module
// Evaluates simple threshold/comparison rules against tick/bar records.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>

#include "../native_log_bridge.h"

#define ALERT_COMPONENT_CORE "backend.native.alert.core"
#define ALERT_COMPONENT_MODULE "backend.native.alert.module"

#define ALERT_LOG(level, message, details) \
    native_log_bridge_log(level, ALERT_COMPONENT_CORE, __FUNCTION__, __LINE__, message, details)

#define ALERT_LOG_INFO(message, details) \
    ALERT_LOG(NATIVE_LOG_LEVEL_INFO, message, details)

#define ALERT_LOG_WARNING(message, details) \
    ALERT_LOG(NATIVE_LOG_LEVEL_WARNING, message, details)

#define ALERT_LOG_ERROR(message, details) \
    ALERT_LOG(NATIVE_LOG_LEVEL_ERROR, message, details)

namespace py = pybind11;

struct Rule {
    std::string id;
    std::string field;
    std::string op;  // one of: >, <, >=, <=, ==, !=
    double value;
};

bool eval_rule(const py::dict &rec, const Rule &r) {
    if (!rec.contains(r.field.c_str())) return false;
    double lhs = 0.0;
    try { lhs = py::float_(rec[r.field.c_str()]); } catch (...) { return false; }
    if (r.op == ">") return lhs > r.value;
    if (r.op == "<") return lhs < r.value;
    if (r.op == ">=") return lhs >= r.value;
    if (r.op == "<=") return lhs <= r.value;
    if (r.op == "==") return lhs == r.value;
    if (r.op == "!=") return lhs != r.value;
    return false;
}

py::list evaluate_rules(const py::list &records, const py::list &rules) {
    std::vector<Rule> rs;
    rs.reserve(py::len(rules));
    for (const auto &item : rules) {
        if (!py::isinstance<py::dict>(item)) {
            ALERT_LOG_WARNING("Skipped rule because item is not dict", nullptr);
            continue;
        }
        py::dict d = item.cast<py::dict>();
        Rule r;
        r.id = d.contains("id") ? py::str(d["id"]).cast<std::string>() : std::string();
        r.field = d.contains("field") ? py::str(d["field"]).cast<std::string>() : std::string();
        r.op = d.contains("op") ? py::str(d["op"]).cast<std::string>() : std::string();
        r.value = d.contains("value") ? py::float_(d["value"]).cast<double>() : 0.0;
        if (!r.field.empty() && !r.op.empty()) {
            rs.push_back(std::move(r));
        } else {
            ALERT_LOG_WARNING("Rule missing field/op, ignored", r.id.empty() ? nullptr : r.id.c_str());
        }
    }

    py::list alerts;
    size_t idx = 0;
    std::string summary_details = "rules=" + std::to_string(rs.size()) + ", records=" + std::to_string(py::len(records));
    ALERT_LOG_INFO("Starting rule evaluation", summary_details.c_str());
    for (const auto &rec_item : records) {
        if (!py::isinstance<py::dict>(rec_item)) {
            ALERT_LOG_WARNING("Input record is not dict, skipped", nullptr);
            idx++;
            continue;
        }
        py::dict rec = rec_item.cast<py::dict>();
        for (const auto &r : rs) {
            if (eval_rule(rec, r)) {
                py::dict a;
                a["id"] = r.id;
                a["index"] = py::int_(idx);
                if (rec.contains("datetime")) a["triggered_at"] = rec["datetime"]; // optional
                alerts.append(a);
            }
        }
        idx++;
    }
    std::string completion_details =
        "evaluated_records=" + std::to_string(idx) + ", alerts=" + std::to_string(py::len(alerts));
    ALERT_LOG_INFO("Rule evaluation finished", completion_details.c_str());
    return alerts;
}

PYBIND11_MODULE(native_alert, m) {
    m.doc() = "Native AlertEngine evaluator for simple threshold/comparison rules";
    m.def("evaluate_rules", &evaluate_rules, py::arg("records"), py::arg("rules"),
          "Evaluate rules over records, returning alert dicts");

    native_log_bridge_log(
        NATIVE_LOG_LEVEL_INFO,
        ALERT_COMPONENT_MODULE,
        "alert_engine_module_init",
        __LINE__,
        "native_alert module initialized",
        nullptr);
}

