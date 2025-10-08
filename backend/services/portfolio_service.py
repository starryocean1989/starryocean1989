# -*- coding: utf-8 -*-
"""
组合投资服务.

提供组合管理和监控功能，包括：
- 组合管理（自动识别、自定义组合、虚拟网关）
- 组合监控（实时业绩、风险指标、历史分析）
"""

import logging
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.services.base_service import BaseService


class PortfolioService(BaseService):
    """组合投资服务.

    管理投资组合，提供：
    1. 自动组合识别 - 识别激活超过1个策略的网关
    2. 自定义组合管理 - 用户创建虚拟网关组合
    3. 组合监控 - 实时业绩、风险指标、历史分析
    """

    def __init__(self):
        """初始化组合投资服务."""
        super().__init__()

        # 自动识别的组合（不可删除）
        self.auto_portfolios: Dict[str, Dict[str, Any]] = {}

        # 自定义组合（可删除）
        self.custom_portfolios: Dict[str, Dict[str, Any]] = {}

        # 虚拟网关
        self.virtual_gateways: Dict[str, Any] = {}

        self.logger.info("组合投资服务已创建")

    def _do_initialize(self) -> bool:
        """初始化组合投资服务."""
        try:
            self.logger.info("初始化组合投资服务...")

            # 扫描现有网关，自动识别组合
            self._scan_and_create_auto_portfolios()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭组合投资服务."""
        try:
            # 清理所有组合
            self.auto_portfolios.clear()
            self.custom_portfolios.clear()
            self.virtual_gateways.clear()
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "auto_portfolio_count": len(self.auto_portfolios),
            "custom_portfolio_count": len(self.custom_portfolios),
            "virtual_gateway_count": len(self.virtual_gateways),
        }

    def _scan_and_create_auto_portfolios(self):
        """扫描并创建自动识别的组合."""
        try:
            # 从trading_gateway_service获取网关和策略信息
            from backend.core.shared_services import get_service_manager

            service_manager = get_service_manager()
            gateway_service = service_manager.get_service("trading_gateway_service")

            if not gateway_service:
                self.logger.warning("TradingGatewayService不可用，无法扫描自动组合")
                return

            # 识别激活超过1个策略的网关
            for gw_name, strategies in gateway_service.strategy_instances.items():
                active_strategies = [s for s in strategies.values() if s.get("status") == "running"]

                # 如果激活了多个策略，创建自动组合
                if len(active_strategies) > 1:
                    portfolio_id = f"auto_{gw_name}"
                    if portfolio_id not in self.auto_portfolios:
                        self.auto_portfolios[portfolio_id] = {
                            "id": portfolio_id,
                            "gateway_name": gw_name,
                            "strategy_count": len(active_strategies),
                            "create_time": datetime.now(),
                        }
                        self.logger.info(
                            f"自动创建组合: {portfolio_id} ({len(active_strategies)}个策略)"
                        )

        except Exception as e:
            self.logger.error(f"扫描自动组合失败: {e}")

    # ==================== 组合管理 ====================

    def create_custom_portfolio(
        self,
        portfolio_name: str,
        gateway_names: List[str],
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """创建自定义组合.

        Args:
            portfolio_name: 组合名称
            gateway_names: 成员网关列表
            weights: 权重配置（可选）

        Returns:
            Dict: 创建结果
        """
        try:
            if portfolio_name in self.custom_portfolios:
                return {"success": False, "message": "组合名称已存在"}

            # 生成虚拟网关ID
            virtual_gw_id = self._generate_virtual_gateway_id(portfolio_name)

            # 创建组合
            self.custom_portfolios[portfolio_name] = {
                "name": portfolio_name,
                "gateway_names": gateway_names,
                "weights": weights or {},
                "virtual_gateway_id": virtual_gw_id,
                "create_time": datetime.now(),
            }

            # 创建虚拟网关
            self.virtual_gateways[virtual_gw_id] = {
                "id": virtual_gw_id,
                "portfolio_name": portfolio_name,
                "gateway_names": gateway_names,
            }

            return {
                "success": True,
                "message": "自定义组合创建成功",
                "portfolio_name": portfolio_name,
                "virtual_gateway_id": virtual_gw_id,
            }

        except Exception as e:
            self._log_error("创建自定义组合", e)
            return {"success": False, "message": str(e)}

    def delete_custom_portfolio(self, portfolio_name: str) -> Dict[str, Any]:
        """删除自定义组合.

        Args:
            portfolio_name: 组合名称

        Returns:
            Dict: 操作结果
        """
        try:
            if portfolio_name not in self.custom_portfolios:
                return {"success": False, "message": "组合不存在"}

            # 获取虚拟网关ID
            virtual_gw_id = self.custom_portfolios[portfolio_name]["virtual_gateway_id"]

            # 删除组合和虚拟网关
            del self.custom_portfolios[portfolio_name]
            if virtual_gw_id in self.virtual_gateways:
                del self.virtual_gateways[virtual_gw_id]

            return {
                "success": True,
                "message": "自定义组合已删除",
            }

        except Exception as e:
            self._log_error("删除自定义组合", e)
            return {"success": False, "message": str(e)}

    def list_portfolios(self) -> Dict[str, Any]:
        """列出所有组合.

        Returns:
            Dict: 组合列表
        """
        portfolios = {
            "auto_portfolios": list(self.auto_portfolios.values()),
            "custom_portfolios": list(self.custom_portfolios.values()),
        }
        return {
            "success": True,
            "portfolios": portfolios,
        }

    def _generate_virtual_gateway_id(self, portfolio_name: str) -> str:
        """生成虚拟网关ID.

        Args:
            portfolio_name: 组合名称

        Returns:
            str: 虚拟网关ID
        """
        unique_str = f"{portfolio_name}_{datetime.now().isoformat()}"
        return f"VG_{hashlib.md5(unique_str.encode()).hexdigest()[:8]}"

    # ==================== 组合监控 ====================

    def get_portfolio_monitoring(self, portfolio_name: str) -> Dict[str, Any]:
        """获取组合监控数据.

        Args:
            portfolio_name: 组合名称或虚拟网关ID

        Returns:
            Dict: 监控数据
        """
        try:
            # 查找组合
            portfolio = None
            gateway_names = []

            # 先检查自定义组合
            if portfolio_name in self.custom_portfolios:
                portfolio = self.custom_portfolios[portfolio_name]
                gateway_names = portfolio["gateway_names"]
            # 再检查自动组合
            elif portfolio_name in self.auto_portfolios:
                portfolio = self.auto_portfolios[portfolio_name]
                gateway_names = [portfolio["gateway_name"]]
            else:
                return {
                    "success": False,
                    "message": f"组合 '{portfolio_name}' 不存在",
                }

            # 从TradingGatewayService获取监控数据
            from backend.core.shared_services import get_service_manager

            service_manager = get_service_manager()
            gateway_service = service_manager.get_service("trading_gateway_service")

            if not gateway_service:
                return {
                    "success": False,
                    "message": "TradingGatewayService不可用",
                }

            # 聚合多个网关的数据
            aggregated_data = {
                "positions": [],
                "accounts": [],
                "total_balance": 0,
                "total_pnl": 0,
            }

            for gw_name in gateway_names:
                try:
                    result = gateway_service.get_monitoring_data(gw_name)
                    if result.get("success"):
                        data = result.get("data", {})
                        aggregated_data["positions"].extend(data.get("positions", []))
                        aggregated_data["accounts"].extend(data.get("accounts", []))

                        # 计算总资金
                        for account in data.get("accounts", []):
                            aggregated_data["total_balance"] += account.get("balance", 0)

                        # 计算总盈亏
                        for position in data.get("positions", []):
                            aggregated_data["total_pnl"] += position.get("pnl", 0)

                except Exception as e:
                    self.logger.warning(f"获取网关 {gw_name} 数据失败: {e}")

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "data": aggregated_data,
            }

        except Exception as e:
            self._log_error("获取组合监控", e)
            return {"success": False, "message": str(e)}
