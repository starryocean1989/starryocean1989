#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <regex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace py = pybind11;

struct HighlightRule {
    std::string name;
    std::regex pattern;
    std::string color;
    bool bold;
    bool italic;

    HighlightRule(std::string name_,
                  const std::string& pattern_,
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
    explicit HighlighterEngine(const std::vector<py::dict>& rules, std::string theme_name = "monaco-dark")
        : theme_name_(std::move(theme_name)) {
        set_theme(rules);
    }

    std::vector<py::dict> highlight(const std::string& text) const {
        std::vector<Token> tokens;
        tokens.reserve(rules_.size() * 4);

        for (const auto& rule : rules_) {
            auto begin = std::sregex_iterator(text.begin(), text.end(), rule.pattern);
            auto end = std::sregex_iterator();
            for (auto it = begin; it != end; ++it) {
                const auto& match = *it;
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

        std::sort(tokens.begin(), tokens.end(), [](const Token& lhs, const Token& rhs) {
            if (lhs.start == rhs.start) {
                return lhs.length > rhs.length;
            }
            return lhs.start < rhs.start;
        });

        std::vector<py::dict> result;
        result.reserve(tokens.size());
        for (const auto& token : tokens) {
            py::dict item;
            item["name"] = token.name;
            item["start"] = token.start;
            item["length"] = token.length;
            item["color"] = token.color;
            item["bold"] = token.bold;
            item["italic"] = token.italic;
            result.emplace_back(std::move(item));
        }
        return result;
    }

    void set_theme(const std::vector<py::dict>& rules) {
        rules_.clear();
        rules_.reserve(rules.size());
        for (const auto& rule : rules) {
            const auto pattern = rule["pattern"].cast<std::string>();
            if (pattern.empty()) {
                throw std::invalid_argument("pattern 不能为空");
            }

            const auto name_iter = rule.contains("name") ? rule["name"].cast<std::string>() : pattern;
            const auto color = rule.contains("color") ? rule["color"].cast<std::string>() : "#FFFFFF";
            const auto bold = rule.contains("bold") ? rule["bold"].cast<bool>() : false;
            const auto italic = rule.contains("italic") ? rule["italic"].cast<bool>() : false;
            const auto case_sensitive =
                rule.contains("case_sensitive") ? rule["case_sensitive"].cast<bool>() : false;

            rules_.emplace_back(name_iter, pattern, case_sensitive, color, bold, italic);
        }
    }

    std::string theme_name() const {
        return theme_name_;
    }

private:
    std::string theme_name_;
    std::vector<HighlightRule> rules_;
};

PYBIND11_MODULE(native_qhighlighter_core, m) {
    py::class_<HighlighterEngine>(m, "HighlighterEngine")
        .def(py::init<const std::vector<py::dict>&, std::string>(),
             py::arg("rules"),
             py::arg("theme_name") = "monaco-dark")
        .def("highlight", &HighlighterEngine::highlight, py::arg("text"))
        .def("set_theme", &HighlighterEngine::set_theme, py::arg("rules"))
        .def_property_readonly("theme_name", &HighlighterEngine::theme_name);
}


