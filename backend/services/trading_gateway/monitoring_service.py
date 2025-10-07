# -*- coding: utf-8 -*-
"""
交易监控服务.

提供订单、持仓、资金等交易数据监控。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MonitoringService:
    """交易监控服务."""

    def __init__(self):
        """初始化监控服务."""
        # 存储各网关的监控数据
        self.orders: Dict[str, List[Dict[str, Any]]] = {}
        self.positions: Dict[str, List[Dict[str, Any]]] = {}
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.trades: Dict[str, List[Dict[str, Any]]] = {}
        logger.info("交易监控服务初始化完成")

    def get_monitoring_data(self, gateway_id: str) -> Dict[str, Any]:
        """获取网关监控数据汇总."""
        try:
            orders = self.orders.get(gateway_id, [])
            positions = self.positions.get(gateway_id, [])
            account = self.accounts.get(gateway_id, {})

            return {
                "gateway_id": gateway_id,
                "orders_count": len(orders),
                "active_orders": sum(1 for o in orders if o["status"] == "submitted"),
                "positions_count": len(positions),
                "total_position_value": sum(p.get("pnl", 0) for p in positions),
                "account_balance": account.get("balance", 0.0),
                "account_available": account.get("available", 0.0),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("获取监控数据失败: %s", e)
            raise

    def get_orders(self, gateway_id: str) -> List[Dict[str, Any]]:
        """获取委托列表."""
        return self.orders.get(gateway_id, [])

    def get_positions(self, gateway_id: str) -> List[Dict[str, Any]]:
        """获取持仓列表."""
        return self.positions.get(gateway_id, [])

    def get_accounts(self, gateway_id: str) -> Dict[str, Any]:
        """获取资金账户."""
        return self.accounts.get(gateway_id, {})

    def get_trades(self, gateway_id: str) -> List[Dict[str, Any]]:
        """获取成交列表."""
        return self.trades.get(gateway_id, [])

    def update_order(self, gateway_id: str, order_data: Dict[str, Any]) -> None:
        """更新委托数据."""
        try:
            if gateway_id not in self.orders:
                self.orders[gateway_id] = []

            # 查找并更新或添加
            order_id = order_data.get("order_id")
            found = False

            for i, order in enumerate(self.orders[gateway_id]):
                if order.get("order_id") == order_id:
                    self.orders[gateway_id][i] = order_data
                    found = True
                    break

            if not found:
                self.orders[gateway_id].append(order_data)

            logger.debug("委托数据已更新: order_id=%s", order_id)

        except Exception as e:
            logger.error("更新委托数据失败: %s", e)

    def update_position(self, gateway_id: str, position_data: Dict[str, Any]) -> None:
        """更新持仓数据."""
        try:
            if gateway_id not in self.positions:
                self.positions[gateway_id] = []

            # 查找并更新或添加
            position_key = (
                f"{position_data.get('symbol')}_{position_data.get('direction')}"
            )
            found = False

            for i, pos in enumerate(self.positions[gateway_id]):
                if f"{pos.get('symbol')}_{pos.get('direction')}" == position_key:
                    self.positions[gateway_id][i] = position_data
                    found = True
                    break

            if not found:
                self.positions[gateway_id].append(position_data)

            logger.debug("持仓数据已更新: %s", position_key)

        except Exception as e:
            logger.error("更新持仓数据失败: %s", e)

    def update_account(self, gateway_id: str, account_data: Dict[str, Any]) -> None:
        """更新资金账户."""
        try:
            self.accounts[gateway_id] = account_data
            logger.debug("资金账户已更新: gateway_id=%s", gateway_id)

        except Exception as e:
            logger.error("更新资金账户失败: %s", e)


__all__ = ["MonitoringService"]
