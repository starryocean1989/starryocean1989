# -*- coding: utf-8 -*-
"""
告警服务.

提供告警规则管理和通知功能。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertService:
    """告警服务."""

    def __init__(self):
        """初始化告警服务."""
        self.rules: Dict[str, Dict[str, Any]] = {}
        self.alerts: Dict[str, Dict[str, Any]] = {}
        logger.info("告警服务初始化完成")

    def create_rule(
        self,
        rule_name: str,
        metric_type: str,
        condition: str,
        threshold: float,
        severity: str = "warning",
        notification_methods: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """创建告警规则."""
        try:
            rule_id = f"rule_{int(datetime.now().timestamp())}"

            rule = {
                "rule_id": rule_id,
                "rule_name": rule_name,
                "metric_type": metric_type,
                "condition": condition,
                "threshold": threshold,
                "severity": severity,
                "is_enabled": True,
                "notification_methods": notification_methods or ["log"],
                "created_at": datetime.now().isoformat(),
            }

            self.rules[rule_id] = rule

            logger.info("告警规则创建成功: rule_id=%s, name=%s", rule_id, rule_name)
            return rule

        except Exception as e:
            logger.error("创建告警规则失败: %s", e)
            raise

    def check_rules(self, metrics: Dict[str, float]) -> List[Dict[str, Any]]:
        """检查告警规则."""
        try:
            triggered_alerts = []

            for rule in self.rules.values():
                if not rule["is_enabled"]:
                    continue

                metric_type = rule["metric_type"]
                if metric_type not in metrics:
                    continue

                metric_value = metrics[metric_type]
                threshold = rule["threshold"]
                condition = rule["condition"]

                # 判断是否触发
                is_triggered = (
                    (condition == ">" and metric_value > threshold)
                    or (condition == "<" and metric_value < threshold)
                    or (condition == "==" and metric_value == threshold)
                    or (condition == ">=" and metric_value >= threshold)
                    or (condition == "<=" and metric_value <= threshold)
                )

                if is_triggered:
                    alert = self._create_alert(rule, metric_value)
                    triggered_alerts.append(alert)

            if triggered_alerts:
                logger.info("触发%d条告警", len(triggered_alerts))

            return triggered_alerts

        except Exception as e:
            logger.error("检查告警规则失败: %s", e)
            raise

    def _create_alert(self, rule: Dict[str, Any], metric_value: float) -> Dict[str, Any]:
        """创建告警."""
        alert_id = f"alert_{int(datetime.now().timestamp())}"

        alert = {
            "alert_id": alert_id,
            "rule_id": rule["rule_id"],
            "alert_type": rule["metric_type"],
            "severity": rule["severity"],
            "title": f"{rule['rule_name']}告警",
            "message": f"{rule['metric_type']}={metric_value} {rule['condition']} {rule['threshold']}",
            "source": "system_manager",
            "status": "active",
            "triggered_at": datetime.now().isoformat(),
            "acknowledged_at": None,
            "resolved_at": None,
            "metadata": {
                "metric_value": metric_value,
                "threshold": rule["threshold"],
                "condition": rule["condition"],
            },
        }

        self.alerts[alert_id] = alert

        # 发送通知
        self._send_notification(alert, rule["notification_methods"])

        return alert

    def _send_notification(self, alert: Dict[str, Any], methods: List[str]) -> None:
        """发送告警通知."""
        try:
            for method in methods:
                if method == "log":
                    logger.warning("告警: %s - %s", alert["title"], alert["message"])
                elif method == "email":
                    # 实现邮件通知 (smtplib) - 按计划暂缓实施
                    logger.info("邮件通知已发送（待实现）")
                elif method == "webhook":
                    # 实现Webhook通知 (requests) - 按计划暂缓实施
                    logger.info("Webhook通知已发送（待实现）")

        except Exception as e:
            logger.error("发送告警通知失败: %s", e)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警."""
        try:
            if alert_id not in self.alerts:
                raise ValueError(f"告警不存在: {alert_id}")

            self.alerts[alert_id]["status"] = "acknowledged"
            self.alerts[alert_id]["acknowledged_at"] = datetime.now().isoformat()

            logger.info("告警已确认: alert_id=%s", alert_id)
            return True

        except Exception as e:
            logger.error("确认告警失败: %s", e)
            raise

    def get_rules(self) -> List[Dict[str, Any]]:
        """获取所有规则."""
        return list(self.rules.values())

    def list_rules(self) -> List[Dict[str, Any]]:
        """列出所有规则."""
        return list(self.rules.values())

    def get_alerts(
        self, status: Optional[str] = None, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取告警列表."""
        alerts = list(self.alerts.values())

        if status:
            alerts = [a for a in alerts if a["status"] == status]

        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        return alerts

    def list_alerts(
        self, status: Optional[str] = None, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出告警."""
        return self.get_alerts(status=status, severity=severity)

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """更新告警规则."""
        try:
            if rule_id not in self.rules:
                raise ValueError(f"告警规则不存在: {rule_id}")

            self.rules[rule_id].update(updates)
            logger.info("告警规则更新成功: rule_id=%s", rule_id)
            return True

        except Exception as e:
            logger.error("更新告警规则失败: %s", e)
            raise

    def delete_rule(self, rule_id: str) -> bool:
        """删除告警规则."""
        try:
            if rule_id not in self.rules:
                raise ValueError(f"告警规则不存在: {rule_id}")

            del self.rules[rule_id]
            logger.info("告警规则删除成功: rule_id=%s", rule_id)
            return True

        except Exception as e:
            logger.error("删除告警规则失败: %s", e)
            raise


__all__ = ["AlertService"]
