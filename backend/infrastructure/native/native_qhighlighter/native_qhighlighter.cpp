// -*- coding: utf-8 -*-

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <regex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "../native_log_bridge.h"

namespace py = pybind11;

namespace {

constexpr const char *kComponentCore = "backend.native.qhighlighter.core";
constexpr const char *kComponentWrapper = "backend.native.qhighlighter.wrapper";

inline void log_warning(const char *function, int line, const std::string &message, const std::string &details = {}) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_WARNING,
        kComponentCore,
        function,
        line,
        message.c_str(),
        details.empty() ? nullptr : details.c_str());
}

inline void log_error(const char *function, int line, const std::string &message, const std::string &details = {}) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_ERROR,
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

struct HighlightRule {
    std::string name;
    std::regex pattern;
    std::string color;
    bool bold;
    bool italic;

    HighlightRule(std::string name_,
                  const std::string &pattern_,
                  bool case_sensitive,
                  std::string color_,
                  bool bold_,
                  bool italic_)
        : name(std::move(name_)),
          pattern(pattern_, case_sensitive ? std::regex::ECMAScript
                                           : std::regex::ECMAScript | std::regex::icase),
          color(std::move(color_)),
          bold(bold_),
          italic(italic_) {}
};

struct Token {
    std::string name;
    std::size_t start;
    std::size_t length;
    std::string color;
    bool bold;
    bool italic;
};

class HighlighterEngine {
public:
    explicit HighlighterEngine(const std::vector<py::dict> &rules, std::string theme_name = "monaco-dark")
        : theme_name_(std::move(theme_name)) {
        set_theme(rules);
    }

    std::vector<py::dict> highlight(const std::string &text) const {
        if (text.empty()) {
            log_info(__FUNCTION__, __LINE__, "highlight received empty text buffer", "length=0");
            return {};
        }

        std::vector<Token> tokens;
        tokens.reserve(rules_.size() * 4);

        for (const auto &rule : rules_) {
            auto begin = std::sregex_iterator(text.begin(), text.end(), rule.pattern);
            auto end = std::sregex_iterator();
            for (auto it = begin; it != end; ++it) {
                const auto &match = *it;
                Token token{
                    rule.name,
                    static_cast<std::size_t>(match.position()),
                    static_cast<std::size_t>(match.length()),
                    rule.color,
                    rule.bold,
                    rule.italic,
                };
                tokens.emplace_back(std::move(token));
            }
        }

        std::sort(tokens.begin(), tokens.end(), [](const Token &lhs, const Token &rhs) {
            if (lhs.start == rhs.start) {
                return lhs.length > rhs.length;
            }
            return lhs.start < rhs.start;
        });

        std::vector<py::dict> result;
        result.reserve(tokens.size());
        for (const auto &token : tokens) {
            py::dict item;
            item["name"] = token.name;
            item["start"] = token.start;
            item["length"] = token.length;
            item["color"] = token.color;
            item["bold"] = token.bold;
            item["italic"] = token.italic;
            result.emplace_back(std::move(item));
        }

        log_info(__FUNCTION__, __LINE__, "highlight completed", "token_count=" + std::to_string(result.size()));
        return result;
    }

    void set_theme(const std::vector<py::dict> &rules) {
        rules_.clear();
        rules_.reserve(rules.size());

        for (const auto &rule : rules) {
            std::string pattern;
            try {
                pattern = rule["pattern"].cast<std::string>();
            } catch (const py::cast_error &exc) {
                log_error(__FUNCTION__, __LINE__, "failed to cast pattern field to string", exc.what());
                throw;
            }

            if (pattern.empty()) {
                log_error(__FUNCTION__, __LINE__, "pattern is empty", "theme=" + theme_name_);
                throw std::invalid_argument("pattern 不能为空");
            }

            const auto name_iter = rule.contains("name") ? rule["name"].cast<std::string>() : pattern;
            const auto color = rule.contains("color") ? rule["color"].cast<std::string>() : "#FFFFFF";
            const auto bold = rule.contains("bold") ? rule["bold"].cast<bool>() : false;
            const auto italic = rule.contains("italic") ? rule["italic"].cast<bool>() : false;
            const auto case_sensitive =
                rule.contains("case_sensitive") ? rule["case_sensitive"].cast<bool>() : false;

            try {
                rules_.emplace_back(name_iter, pattern, case_sensitive, color, bold, italic);
            } catch (const std::regex_error &rex) {
                log_error(__FUNCTION__, __LINE__, "failed to compile regex pattern", rex.what());
                throw;
            }
        }

        log_info(__FUNCTION__, __LINE__, "theme rules updated",
                 "rule_count=" + std::to_string(rules_.size()) + ",theme=" + theme_name_);
    }

    std::string theme_name() const {
        return theme_name_;
    }

private:
    std::string theme_name_;
    std::vector<HighlightRule> rules_;
};

PYBIND11_MODULE(native_qhighlighter_core, m) {
    native_log_bridge_log(
        NATIVE_LOG_LEVEL_INFO,
        kComponentWrapper,
        __FUNCTION__,
        __LINE__,
        "native_qhighlighter_core module initialised",
        nullptr);

    py::class_<HighlighterEngine>(m, "HighlighterEngine")
        .def(py::init<const std::vector<py::dict> &, std::string>(),
             py::arg("rules"),
             py::arg("theme_name") = "monaco-dark")
        .def("highlight", &HighlighterEngine::highlight, py::arg("text"))
        .def("set_theme", &HighlighterEngine::set_theme, py::arg("rules"))
        .def_property_readonly("theme_name", &HighlighterEngine::theme_name);
}

