# -*- coding: utf-8 -*-
"""
AlertEngine service (Python wrapper)

- Evaluates alert rules using native `native_alert` C++ module for speed.
- Keeps existing architecture; can be wired to the event bus externally.
- 阶段11埋点：记录告警评估上下文、native模块调用状态、异常处理策略
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List
import logging
import time

from backend.infrastructure.native.native_alert import (
    ALERT_AVAILABLE as _NATIVE_AVAILABLE,
    evaluate_rules as _native_evaluate_rules,
)

logger = logging.getLogger("backend.alert.engine")


class AlertEngine:
    def __init__(self) -> None:
        self._rules: List[Dict[str, Any]] = []

    def set_rules(self, rules: Iterable[Dict[str, Any]]) -> None:
        """Set rules: each rule is dict {id, field, op, value}."""
        self._rules = list(rules)

    def evaluate(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Evaluate current rules against given records (tick/bar dicts).

        阶段11埋点：记录告警评估上下文，包括native模块使用状态、评估耗时、规则数量等
        """
        recs = list(records)
        rule_count = len(self._rules)
        record_count = len(recs)
        start_time = time.time()

        logger.debug(
            "[ALERT-EVAL] 开始评估告警规则: 规则数=%d, 记录数=%d, native可用=%s",
            rule_count, record_count, _NATIVE_AVAILABLE,
            extra={"log_type": "SYSTEM", "scenario": "alert_evaluation"}
        )

        if _NATIVE_AVAILABLE:
            try:
                result = list(_native_evaluate_rules(recs, self._rules))
                eval_time = time.time() - start_time
                alert_count = len(result)

                logger.info(
                    "[ALERT-EVAL] Native评估完成: 耗时=%.3fms, 触发告警=%d, 规则数=%d, 记录数=%d",
                    eval_time * 1000, alert_count, rule_count, record_count,
                    extra={"log_type": "SYSTEM", "scenario": "alert_evaluation"}
                )

                # 记录告警触发详情
                if alert_count > 0:
                    logger.warning(
                        "[ALERT-TRIGGER] 告警触发: 数量=%d, 场景=规则评估, 接收端=native评估器",
                        alert_count,
                        extra={"log_type": "ALERT", "scenario": "alert_evaluation", "alert_count": alert_count}
                    )

                return result

            except Exception as e:
                eval_time = time.time() - start_time
                logger.error(
                    "[ALERT-EVAL] Native评估失败: 耗时=%.3fms, 错误=%s, 降级到Python实现",
                    eval_time * 1000, str(e),
                    extra={"log_type": "SYSTEM", "scenario": "alert_evaluation"}
                )
                logger.exception("Native alert evaluation failed: %s", e)

        # Fallback python implementation
        alerts: List[Dict[str, Any]] = []
        for idx, r in enumerate(recs):
            for rule in self._rules:
                fid = rule.get("field")
                op = rule.get("op")
                val = float(rule.get("value", 0))
                if fid not in r:
                    continue
                try:
                    lhs = float(r[fid])
                except Exception:
                    continue
                ok = False
                if op == ">":
                    ok = lhs > val
                elif op == "<":
                    ok = lhs < val
                elif op == ">=":
                    ok = lhs >= val
                elif op == "<=":
                    ok = lhs <= val
                elif op == "==":
                    ok = lhs == val
                elif op == "!=":
                    ok = lhs != val
                if ok:
                    alerts.append({"id": rule.get("id"), "index": idx, "triggered_at": r.get("datetime")})

        eval_time = time.time() - start_time
        alert_count = len(alerts)

        logger.info(
            "[ALERT-EVAL] Python评估完成: 耗时=%.3fms, 触发告警=%d, 规则数=%d, 记录数=%d, native可用=%s",
            eval_time * 1000, alert_count, rule_count, record_count, _NATIVE_AVAILABLE,
            extra={"log_type": "SYSTEM", "scenario": "alert_evaluation"}
        )

        # 记录告警触发详情
        if alert_count > 0:
            logger.warning(
                "[ALERT-TRIGGER] 告警触发: 数量=%d, 场景=规则评估, 接收端=Python回退实现",
                alert_count,
                extra={"log_type": "ALERT", "scenario": "alert_evaluation", "alert_count": alert_count}
            )

        return alerts
