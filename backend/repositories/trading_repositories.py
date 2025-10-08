# -*- coding: utf-8 -*-
"""
交易相关仓库.

整合网关、策略、回测仓库。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== 网关仓库 ====================


class GatewayRepository:
    """网关仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.GatewayRepository")
        self._gateways: Dict[str, Dict[str, Any]] = {}

    def create(self, gateway_data: Dict[str, Any]) -> bool:
        """创建网关."""
        try:
            gateway_id = gateway_data["gateway_id"]
            self._gateways[gateway_id] = gateway_data
            return True
        except Exception as e:
            self.logger.error(f"创建网关失败: {e}")
            return False

    def get(self, gateway_id: str) -> Optional[Dict[str, Any]]:
        """获取网关."""
        return self._gateways.get(gateway_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有网关."""
        return list(self._gateways.values())

    def update(self, gateway_id: str, data: Dict[str, Any]) -> bool:
        """更新网关."""
        try:
            if gateway_id in self._gateways:
                self._gateways[gateway_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新网关失败: {e}")
            return False

    def delete(self, gateway_id: str) -> bool:
        """删除网关."""
        try:
            if gateway_id in self._gateways:
                del self._gateways[gateway_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除网关失败: {e}")
            return False


# ==================== 策略仓库 ====================


class StrategyRepository:
    """策略仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.StrategyRepository")
        self._strategies: Dict[str, Dict[str, Any]] = {}

    def create(self, strategy_data: Dict[str, Any]) -> bool:
        """创建策略."""
        try:
            strategy_id = strategy_data["strategy_id"]
            self._strategies[strategy_id] = strategy_data
            return True
        except Exception as e:
            self.logger.error(f"创建策略失败: {e}")
            return False

    def get(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取策略."""
        return self._strategies.get(strategy_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有策略."""
        return list(self._strategies.values())

    def update(self, strategy_id: str, data: Dict[str, Any]) -> bool:
        """更新策略."""
        try:
            if strategy_id in self._strategies:
                self._strategies[strategy_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新策略失败: {e}")
            return False

    def delete(self, strategy_id: str) -> bool:
        """删除策略."""
        try:
            if strategy_id in self._strategies:
                del self._strategies[strategy_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除策略失败: {e}")
            return False


# ==================== 回测仓库 ====================


class BacktestRepository:
    """回测仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.BacktestRepository")
        self._backtests: Dict[str, Dict[str, Any]] = {}

    def create(self, backtest_data: Dict[str, Any]) -> bool:
        """创建回测任务."""
        try:
            task_id = backtest_data["task_id"]
            self._backtests[task_id] = backtest_data
            return True
        except Exception as e:
            self.logger.error(f"创建回测任务失败: {e}")
            return False

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取回测任务."""
        return self._backtests.get(task_id)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取回测任务列表."""
        tasks = list(self._backtests.values())
        tasks.sort(key=lambda t: t.get("created_time", ""), reverse=True)
        return tasks[:limit]

    def update(self, task_id: str, data: Dict[str, Any]) -> bool:
        """更新回测任务."""
        try:
            if task_id in self._backtests:
                self._backtests[task_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新回测任务失败: {e}")
            return False

    def delete(self, task_id: str) -> bool:
        """删除回测任务."""
        try:
            if task_id in self._backtests:
                del self._backtests[task_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除回测任务失败: {e}")
            return False


__all__ = [
    "GatewayRepository",
    "StrategyRepository",
    "BacktestRepository",
]
