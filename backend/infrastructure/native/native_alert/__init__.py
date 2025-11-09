# -*- coding: utf-8 -*-
"""native_alert 模块包装.

提供统一的 Python API，并在缺少 C 扩展时自动降级。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from backend.infrastructure.native.logging_bridge import native_call_guard
from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.alert.wrapper"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.alert",
)

ALERT_AVAILABLE = False

try:
    from . import alert_native as _native  # type: ignore

    evaluate_rules = _native.evaluate_rules  # type: ignore[attr-defined]
    ALERT_AVAILABLE = True
    _logger.debug(
        "native_alert extension loaded",
        extra={"native_module": "backend.native.alert.core"},
    )
except ImportError as exc:  # pragma: no cover - 仅在缺少扩展时执行
    ALERT_AVAILABLE = False
    _logger.error(
        "native_alert extension unavailable, falling back to Python implementation",
        extra={"native_module": "backend.native.alert.core", "error": str(exc)},
    )

    @native_call_guard(component="backend.native.alert.fallback")
    def evaluate_rules(
        records: Iterable[Dict[str, Any]],
        rules: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Python 兜底实现."""

        result: List[Dict[str, Any]] = []
        rule_list = list(rules)
        record_list = list(records)

        for idx, rec in enumerate(record_list):
            if not isinstance(rec, dict):
                continue
            for rule in rule_list:
                field = rule.get("field")
                operator = rule.get("op")
                try:
                    target = float(rule.get("value", 0))
                except Exception:
                    continue

                if field not in rec:
                    continue

                try:
                    source = float(rec[field])
                except Exception:
                    continue

                matched = False
                if operator == ">":
                    matched = source > target
                elif operator == "<":
                    matched = source < target
                elif operator == ">=":
                    matched = source >= target
                elif operator == "<=":
                    matched = source <= target
                elif operator == "==":
                    matched = source == target
                elif operator == "!=":
                    matched = source != target

                if matched:
                    result.append(
                        {
                            "id": rule.get("id"),
                            "index": idx,
                            "triggered_at": rec.get("datetime"),
                        }
                    )

        return result


__all__ = ["evaluate_rules", "ALERT_AVAILABLE"]

