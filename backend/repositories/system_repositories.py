# -*- coding: utf-8 -*-
"""
系统相关仓库.

整合告警、日志、配置、组合仓库。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== 告警仓库 ====================


class AlertRepository:
    """告警仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.AlertRepository")
        self._alerts: Dict[str, Dict[str, Any]] = {}

    def create(self, alert_data: Dict[str, Any]) -> bool:
        """创建告警."""
        try:
            alert_id = alert_data["alert_id"]
            self._alerts[alert_id] = alert_data
            return True
        except Exception as e:
            self.logger.error(f"创建告警失败: {e}")
            return False

    def get(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """获取告警."""
        return self._alerts.get(alert_id)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表."""
        alerts = list(self._alerts.values())
        alerts.sort(key=lambda a: a.get("created_time", ""), reverse=True)
        return alerts[:limit]

    def update(self, alert_id: str, data: Dict[str, Any]) -> bool:
        """更新告警."""
        try:
            if alert_id in self._alerts:
                self._alerts[alert_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新告警失败: {e}")
            return False

    def delete(self, alert_id: str) -> bool:
        """删除告警."""
        try:
            if alert_id in self._alerts:
                del self._alerts[alert_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除告警失败: {e}")
            return False


# ==================== 日志仓库 ====================


class LogRepository:
    """日志仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.LogRepository")
        self._logs: List[Dict[str, Any]] = []

    def create(self, log_data: Dict[str, Any]) -> bool:
        """创建日志记录."""
        try:
            self._logs.append(log_data)
            return True
        except Exception as e:
            self.logger.error(f"创建日志失败: {e}")
            return False

    def list(self, level: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """查询日志."""
        logs = self._logs
        if level:
            logs = [log for log in logs if log.get("level") == level]
        logs.sort(key=lambda log: log.get("timestamp", ""), reverse=True)
        return logs[:limit]


# ==================== 配置仓库 ====================


class ConfigRepository:
    """配置仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ConfigRepository")
        self._configs: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        """获取配置."""
        return self._configs.get(key)

    def set(self, key: str, value: Any) -> bool:
        """设置配置."""
        try:
            self._configs[key] = value
            return True
        except Exception as e:
            self.logger.error(f"设置配置失败: {e}")
            return False

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置."""
        return self._configs.copy()

    def delete(self, key: str) -> bool:
        """删除配置."""
        try:
            if key in self._configs:
                del self._configs[key]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除配置失败: {e}")
            return False


# ==================== 组合仓库 ====================


class PortfolioRepository:
    """组合仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.PortfolioRepository")
        self._portfolios: Dict[str, Dict[str, Any]] = {}

    def create(self, portfolio_data: Dict[str, Any]) -> bool:
        """创建组合."""
        try:
            portfolio_id = portfolio_data["portfolio_id"]
            self._portfolios[portfolio_id] = portfolio_data
            return True
        except Exception as e:
            self.logger.error(f"创建组合失败: {e}")
            return False

    def get(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """获取组合."""
        return self._portfolios.get(portfolio_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有组合."""
        return list(self._portfolios.values())

    def update(self, portfolio_id: str, data: Dict[str, Any]) -> bool:
        """更新组合."""
        try:
            if portfolio_id in self._portfolios:
                self._portfolios[portfolio_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新组合失败: {e}")
            return False

    def delete(self, portfolio_id: str) -> bool:
        """删除组合."""
        try:
            if portfolio_id in self._portfolios:
                del self._portfolios[portfolio_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除组合失败: {e}")
            return False


__all__ = [
    "AlertRepository",
    "LogRepository",
    "ConfigRepository",
    "PortfolioRepository",
]
