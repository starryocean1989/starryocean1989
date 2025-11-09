# -*- coding: utf-8 -*-
"""native_alert 测试文件."""

import pytest
from typing import Dict, Any, List

from backend.infrastructure.native.native_alert import evaluate_rules, ALERT_AVAILABLE


class TestNativeAlert:
    """native_alert 模块测试."""

    def test_alert_available(self):
        """测试 ALERT_AVAILABLE 状态."""
        assert isinstance(ALERT_AVAILABLE, bool)

    def test_evaluate_rules_basic(self):
        """测试 evaluate_rules 基本功能."""
        records = [
            {"field1": 10.0, "field2": 5.0, "datetime": "2023-01-01"},
            {"field1": 20.0, "field2": 15.0, "datetime": "2023-01-02"},
        ]

        rules = [
            {"id": "rule1", "field": "field1", "op": ">", "value": "15"},
            {"id": "rule2", "field": "field2", "op": "<", "value": "10"},
        ]

        result = evaluate_rules(records, rules)

        assert isinstance(result, list)
        # 第一个记录 field1=10.0 > 15.0? No
        # 第一个记录 field2=5.0 < 10.0? Yes -> 匹配 rule2
        # 第二个记录 field1=20.0 > 15.0? Yes -> 匹配 rule1
        # 第二个记录 field2=15.0 < 10.0? No

        # 应该有两个匹配结果
        assert len(result) == 2

        # 检查结果结构
        for item in result:
            assert "id" in item
            assert "index" in item
            assert "triggered_at" in item

    def test_evaluate_rules_edge_cases(self):
        """测试 evaluate_rules 边界情况."""
        # 空记录
        result = evaluate_rules([], [])
        assert result == []

        # 无效记录
        records = [None, "invalid", {"field": "not_a_number"}]
        rules = [{"id": "rule1", "field": "field", "op": ">", "value": "5"}]
        result = evaluate_rules(records, rules)
        assert result == []

        # 无效规则值
        records = [{"field": 10.0}]
        rules = [{"id": "rule1", "field": "field", "op": ">", "value": "invalid"}]
        result = evaluate_rules(records, rules)
        assert result == []

    def test_evaluate_rules_operators(self):
        """测试所有操作符."""
        record = {"value": 10.0}

        operators = [
            (">", "5", True),  # 10 > 5
            ("<", "15", True),  # 10 < 15
            (">=", "10", True),  # 10 >= 10
            ("<=", "10", True),  # 10 <= 10
            ("==", "10", True),  # 10 == 10
            ("!=", "5", True),   # 10 != 5
            (">", "15", False),  # 10 > 15
            ("==", "5", False),  # 10 == 5
        ]

        for op, val, should_match in operators:
            rules = [{"id": f"rule_{op}", "field": "value", "op": op, "value": val}]
            result = evaluate_rules([record], rules)

            if should_match:
                assert len(result) == 1, f"Operator {op} with value {val} should match"
                assert result[0]["id"] == f"rule_{op}"
            else:
                assert len(result) == 0, f"Operator {op} with value {val} should not match"
