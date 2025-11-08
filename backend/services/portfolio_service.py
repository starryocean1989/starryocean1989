# -*- coding: utf-8 -*-
"""
组合投资服务.

提供组合管理和监控功能，包括：
- 组合管理（自动识别、自定义组合、虚拟网关）
- 组合监控（实时业绩、风险指标、历史分析）
"""

import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime
from threading import Timer
import logging

from backend.core.service_base import BaseService
from backend.infrastructure.native.match_cache import create_match_cache

# 专用logger - 日志埋点v4.0
logger_alert = logging.getLogger("backend.portfolio.alert")


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

        # 定时扫描器
        self.scan_timer: Optional[Timer] = None
        self.scan_interval = 30  # 扫描间隔（秒）

        # ✨ 实时数据缓存（组合撮合缓存，自动降级）
        self.realtime_cache, self._use_native_match_cache = create_match_cache()
        if self._use_native_match_cache:
            self.logger.info("✅ 使用原生组合撮合缓存（HighPerfMatchCache）")
        else:
            self.logger.info("⚠️ 组合撮合缓存降级为Python实现")

        # ✨ 开仓成本追踪（用于Trading P&L计算）
        self.position_costs: Dict[str, Dict[str, float]] = {}  # {gateway: {symbol: cost}}

        self.logger.info("组合投资服务已创建")

    def _do_initialize(self) -> bool:
        """初始化组合投资服务."""
        try:
            self.logger.info("正在初始化组合投资服务...")

            # 初始化数据进程RPC客户端
            self._init_data_client()

            # 注册vnpy事件处理器（用于实时数据获取）
            self._register_trading_events()

            # 扫描现有网关，自动识别组合
            self._scan_and_create_auto_portfolios()

            # 启动定时扫描
            self._start_auto_scan()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _init_data_client(self):
        """初始化数据进程RPC客户端."""
        try:
            from backend.infrastructure.data_module_vnpy.data_process_client import (
                get_data_process_client,
            )

            self.data_client = get_data_process_client()
            self.logger.info("✅ 已初始化数据进程RPC客户端")

        except Exception as e:
            self.logger.error(
                "初始化数据进程客户端失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"}
            )
            self.data_client = None

    def _register_trading_events(self):
        """注册vnpy事件处理器（获取实时交易数据）."""
        try:
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if not event_engine:
                self.logger.warning("EventEngine不可用，无法注册事件处理器", extra={"log_type": "SYSTEM"})
                return

            # 尝试导入vnpy事件类型
            try:
                from vnpy.trader.event import EVENT_POSITION, EVENT_ACCOUNT, EVENT_TRADE
                from backend.infrastructure.system_vnpy import (
                    EVENT_STRATEGY_STATUS_CHANGED,
                )

                # 注册事件处理器
                event_engine.register(EVENT_POSITION, self._on_position_update)
                event_engine.register(EVENT_ACCOUNT, self._on_account_update)
                event_engine.register(EVENT_TRADE, self._on_trade_update)

                # ✨ 新增：监听策略状态变化事件，自动更新组合识别
                event_engine.register(
                    EVENT_STRATEGY_STATUS_CHANGED, self._on_strategy_status_changed
                )

                self.logger.info("✅ 已注册vnpy交易事件处理器（包含策略状态监听）")

            except ImportError:
                self.logger.warning("无法导入vnpy事件类型，实时数据获取功能不可用", extra={"log_type": "SYSTEM"})

        except Exception as e:
            self.logger.error("注册事件处理器失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"})

    def _on_position_update(self, event):
        """处理持仓更新事件（增强版：实时缓存）.

        Args:
            event: vnpy Event对象
        """
        try:
            position = event.data
            if not position:
                return

            gateway_name = position.gateway_name
            symbol = position.vt_symbol

            # ✨ 缓存持仓数据（用于实时业绩计算）
            self.realtime_cache.upsert_position(position)

            self.logger.debug(
                "持仓已缓存: gateway=%s, symbol=%s, volume=%s, pnl=%s",
                gateway_name,
                symbol,
                position.volume,
                position.pnl if hasattr(position, "pnl") else 0,
            )

        except Exception as e:
            self.logger.error("处理持仓更新失败：%s", e, extra={"log_type": "SYSTEM"}, exc_info=True)

    def _on_account_update(self, event):
        """处理资金更新事件（增强版：实时缓存）.

        Args:
            event: vnpy Event对象
        """
        try:
            account = event.data
            if not account:
                return

            gateway_name = account.gateway_name

            # ✨ 缓存资金数据
            self.realtime_cache.upsert_account(account)

            self.logger.debug(
                "资金已缓存: gateway=%s, account=%s, balance=%s",
                gateway_name,
                account.accountid,
                account.balance,
            )

        except Exception as e:
            self.logger.error("处理资金更新失败：%s", e, extra={"log_type": "SYSTEM"}, exc_info=True)

    def _on_trade_update(self, event):
        """处理成交更新事件（增强版：实时缓存和成本追踪）.

        Args:
            event: vnpy Event对象
        """
        try:
            trade = event.data
            if not trade:
                return

            gateway_name = trade.gateway_name
            symbol = trade.vt_symbol

            # ✨ 缓存成交数据
            self.realtime_cache.upsert_trade(trade)

            # ✨ 更新开仓成本（用于Trading P&L计算）
            self._update_position_cost(gateway_name, trade)

            self.logger.debug(
                "成交已缓存: gateway=%s, symbol=%s, volume=%s, price=%s, direction=%s",
                gateway_name,
                symbol,
                trade.volume,
                trade.price,
                trade.direction.value if hasattr(trade, "direction") else "unknown",
            )

        except Exception as e:
            self.logger.error("处理成交更新失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)

    def _update_position_cost(self, gateway_name: str, trade):
        """更新开仓成本.

        Args:
            gateway_name: 网关名称
            trade: 成交对象
        """
        try:
            symbol = trade.vt_symbol
            volume = trade.volume
            price = trade.price

            # 初始化网关成本字典
            if gateway_name not in self.position_costs:
                self.position_costs[gateway_name] = {}

            # 获取方向
            from vnpy.trader.constant import Offset

            offset = trade.offset if hasattr(trade, "offset") else None

            # 简化处理：累积成本
            if symbol not in self.position_costs[gateway_name]:
                self.position_costs[gateway_name][symbol] = 0.0

            # 开仓增加成本，平仓减少成本
            if offset and offset == Offset.OPEN:
                self.position_costs[gateway_name][symbol] += price * volume
            elif offset and offset == Offset.CLOSE:
                self.position_costs[gateway_name][symbol] -= price * volume

            self.logger.debug(
                f"成本已更新: {gateway_name}.{symbol} = {self.position_costs[gateway_name][symbol]:.2f}"
            )

        except Exception as e:
            self.logger.warning(f"更新开仓成本失败: {e}", extra={"log_type": "SYSTEM"})

    def _on_strategy_status_changed(self, event):
        """处理策略状态变化事件（自动更新组合识别）.

        Args:
            event: vnpy Event对象
        """
        try:
            data = event.data if hasattr(event, "data") else event
            gateway_name = data.get("gateway_name", "")
            strategy_name = data.get("strategy_name", "")
            status = data.get("status", "")
            active_count = data.get("active_count", 0)

            self.logger.info(
                f"📢 组合服务收到策略状态变化: {gateway_name}.{strategy_name} -> {status}, "
                f"激活数={active_count}"
            )

            # ✨ 自动更新组合识别：如果激活策略数>1，自动创建或更新自动组合
            if active_count > 1:
                portfolio_id = f"auto_{gateway_name}"
                if portfolio_id not in self.auto_portfolios:
                    # 创建新的自动组合
                    self.auto_portfolios[portfolio_id] = {
                        "id": portfolio_id,
                        "gateway_name": gateway_name,
                        "strategy_count": active_count,
                        "create_time": datetime.now(),
                    }
                    self.logger.info(f"✅ 自动创建组合: {portfolio_id} (策略数: {active_count})")
                else:
                    # 更新已有组合的策略数量
                    self.auto_portfolios[portfolio_id]["strategy_count"] = active_count
                    self.logger.info(f"🔄 更新组合策略数: {portfolio_id} -> {active_count}")

            elif active_count <= 1:
                # 如果策略数<=1，移除自动组合
                portfolio_id = f"auto_{gateway_name}"
                if portfolio_id in self.auto_portfolios:
                    del self.auto_portfolios[portfolio_id]
                    self.logger.info(f"➖ 移除自动组合: {portfolio_id} (策略数: {active_count})")

        except Exception as e:
            self.logger.error(f"处理策略状态变化失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _do_shutdown(self) -> bool:
        """关闭组合投资服务."""
        try:
            # 停止定时扫描
            self._stop_auto_scan()

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
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            gateway_service = service_manager.get_service("trading_gateway_service")

            if not gateway_service:
                self.logger.warning("TradingGatewayService不可用，无法扫描自动组合", extra={"log_type": "SYSTEM"})
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
            self.logger.error(f"扫描自动组合失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _start_auto_scan(self):
        """启动自动扫描定时器."""
        try:
            self.logger.info(f"启动组合自动扫描（间隔{self.scan_interval}秒）")
            self._schedule_next_scan()
        except Exception as e:
            self.logger.error(f"启动自动扫描失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def _stop_auto_scan(self):
        """停止自动扫描定时器."""
        if self.scan_timer:
            self.scan_timer.cancel()
            self.scan_timer = None
            self.logger.info("已停止组合自动扫描")

    def _schedule_next_scan(self):
        """调度下一次扫描."""
        if self.scan_timer:
            self.scan_timer.cancel()

        def scan_task():
            try:
                self._scan_and_create_auto_portfolios()
                self._schedule_next_scan()  # 递归调度
            except Exception as e:
                self.logger.error(f"定时扫描任务失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

        self.scan_timer = Timer(self.scan_interval, scan_task)
        self.scan_timer.daemon = True
        self.scan_timer.start()

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

    def calculate_realtime_pnl(self, portfolio_name: str) -> Dict[str, Any]:
        """计算组合实时盈亏（增强版：优先使用缓存，分离Trading P&L和Holding P&L，事件驱动更新）.

        Args:
            portfolio_name: 组合名称或虚拟网关ID

        Returns:
            Dict: 实时盈亏数据，包含：
                - total_pnl: 总盈亏
                - holding_pnl: 持仓盈亏（未实现收益）
                - trading_pnl: 交易盈亏（已实现收益）
                - positions: 持仓明细
                - accounts: 账户明细
        """
        import time
        start_time = time.time()
        stage_logger = logging.getLogger("task.portfolio_pnl_calculation.stage")

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
                # 阶段节点日志（输出到Terminal）
                stage_logger.warning(
                    f"⚠️ 组合不存在: {portfolio_name}",
                    extra={"log_type": "STAGE_NODE", "scenario": "portfolio_pnl_calculation"},
                )
                return {
                    "success": False,
                    "message": f"组合 '{portfolio_name}' 不存在",
                }

            total_pnl = 0
            total_holding_pnl = 0
            total_trading_pnl = 0
            positions_detail = []
            accounts_detail = []

            for gw_name in gateway_names:
                try:
                    # ✨ 优先使用缓存数据（事件驱动已更新，避免重复查询）
                    gateway_positions = self.realtime_cache.get_positions(gw_name)

                    # 如果缓存为空，从main_engine获取（降级方案）
                    if not gateway_positions and self.main_engine:
                        positions = self.main_engine.get_all_positions()
                        gateway_positions = [p for p in positions if p.gateway_name == gw_name]
                        for position in gateway_positions:
                            self.realtime_cache.upsert_position(position)
                        self.logger.debug(
                            f"从main_engine获取持仓并缓存: {gw_name}, {len(gateway_positions)}条"
                        )

                    # 计算盈亏
                    for position in gateway_positions:
                        symbol = position.vt_symbol
                        volume = position.volume

                        # ✨ 计算Holding P&L（未实现收益 - 持仓盈亏）
                        holding_pnl = position.pnl if hasattr(position, "pnl") else 0

                        # ✨ 计算Trading P&L（已实现收益 - 从成本追踪）
                        trading_pnl = self._calculate_trading_pnl(gw_name, symbol)

                        positions_detail.append(
                            {
                                "gateway": gw_name,
                                "symbol": symbol,
                                "volume": volume,
                                "price": position.price if hasattr(position, "price") else 0,
                                "holding_pnl": holding_pnl,  # 未实现收益
                                "trading_pnl": trading_pnl,  # 已实现收益
                                "total_pnl": holding_pnl + trading_pnl,
                            }
                        )

                        total_holding_pnl += holding_pnl
                        total_trading_pnl += trading_pnl

                    # ✨ 优先使用缓存的账户数据
                    gateway_accounts = self.realtime_cache.get_accounts(gw_name)

                    # 如果缓存为空，从main_engine获取
                    if not gateway_accounts and self.main_engine:
                        accounts = self.main_engine.get_all_accounts()
                        gateway_accounts = [a for a in accounts if a.gateway_name == gw_name]
                        for account in gateway_accounts:
                            self.realtime_cache.upsert_account(account)
                        self.logger.debug(
                            f"从main_engine获取账户并缓存: {gw_name}, {len(gateway_accounts)}条"
                        )

                    for account in gateway_accounts:
                        accounts_detail.append(
                            {
                                "gateway": gw_name,
                                "account_id": account.accountid,
                                "balance": account.balance,
                                "available": (
                                    account.available if hasattr(account, "available") else 0
                                ),
                            }
                        )

                except Exception as e:
                    self.logger.warning("获取网关 %s 数据失败: %s", gw_name, e, extra={"log_type": "SYSTEM"})

            # 总盈亏 = 持仓盈亏 + 交易盈亏
            total_pnl = total_holding_pnl + total_trading_pnl
            elapsed_ms = (time.time() - start_time) * 1000

            # 业绩计算完成通知 - 日志埋点v4.0
            self.logger.info(
                "实时盈亏计算完成: 组合=%s, 总盈亏=%.2f, 持仓盈亏=%.2f, 交易盈亏=%.2f, 持仓数=%d",
                portfolio_name,
                total_pnl,
                total_holding_pnl,
                total_trading_pnl,
                len(positions_detail),
            )

            # 阶段节点日志（输出到Terminal，仅记录关键计算结果，避免频繁输出）
            # 注意：由于可能被频繁调用，只在有持仓或盈亏不为0时记录
            if len(positions_detail) > 0 or abs(total_pnl) > 0.01:
                cache_hit_rate = self._calculate_cache_hit_rate(gateway_names)
                stage_logger.info(
                    f"✅ 盈亏计算完成: 组合={portfolio_name}, 总盈亏={total_pnl:.2f}, "
                    f"持仓={len(positions_detail)}个, 缓存命中={cache_hit_rate:.0%}, 耗时={elapsed_ms:.0f}ms",
                    extra={"log_type": "STAGE_NODE", "scenario": "portfolio_pnl_calculation"},
                )

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "gateway_names": gateway_names,
                "total_pnl": total_pnl,
                "holding_pnl": total_holding_pnl,  # 未实现收益
                "trading_pnl": total_trading_pnl,  # 已实现收益
                "positions": positions_detail,
                "accounts": accounts_detail,
                "update_time": datetime.now().isoformat(),
                "data_source": "cache",  # 标识数据来源（事件驱动缓存）
                "cache_hit_rate": self._calculate_cache_hit_rate(gateway_names),
            }

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            self._log_error("计算实时盈亏", e)
            # 阶段节点日志（输出到Terminal）
            try:
                stage_logger.error(
                    f"❌ 盈亏计算异常: 组合={portfolio_name}, 错误={str(e)}, 耗时={elapsed_ms:.0f}ms",
                    extra={"log_type": "STAGE_NODE", "scenario": "portfolio_pnl_calculation"},
                )
            except Exception:
                pass
            return {"success": False, "message": str(e)}

    def _calculate_cache_hit_rate(self, gateway_names: List[str]) -> float:
        """计算缓存命中率.

        Args:
            gateway_names: 网关名称列表

        Returns:
            float: 缓存命中率（0-1）
        """
        try:
            total_gateways = len(gateway_names)
            cached_gateways = sum(
                1
                for gw in gateway_names
                if self.realtime_cache.has_positions(gw) or self.realtime_cache.has_accounts(gw)
            )

            return cached_gateways / total_gateways if total_gateways > 0 else 0.0

        except Exception:
            return 0.0

    def _calculate_trading_pnl(self, gateway_name: str, symbol: str) -> float:
        """计算Trading P&L（已实现收益）.

        Args:
            gateway_name: 网关名称
            symbol: 品种代码

        Returns:
            float: 已实现收益
        """
        try:
            stats = self.realtime_cache.get_trade_stats(gateway_name, symbol)
            if not stats:
                return 0.0

            buy_value = float(stats.get("buy_value", 0.0))
            sell_value = float(stats.get("sell_value", 0.0))

            return sell_value - buy_value

        except Exception as e:
            self.logger.warning(f"计算Trading P&L失败: {e}", extra={"log_type": "SYSTEM"})
            return 0.0

    def _calculate_holding_pnl(
        self, gateway_name: str, symbol: str, current_price: float, volume: int
    ) -> float:
        """计算Holding P&L（未实现收益）.

        Args:
            gateway_name: 网关名称
            symbol: 品种代码
            current_price: 当前价格
            volume: 持仓量

        Returns:
            float: 未实现收益
        """
        try:
            # 获取开仓成本
            if gateway_name not in self.position_costs:
                return 0.0

            cost = self.position_costs[gateway_name].get(symbol, 0.0)

            # 计算当前市值
            current_value = current_price * volume

            # Holding P&L = 当前市值 - 开仓成本
            holding_pnl = current_value - cost

            return holding_pnl

        except Exception as e:
            self.logger.warning(f"计算Holding P&L失败: {e}", extra={"log_type": "SYSTEM"})
            return 0.0

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
            from backend.core.base import get_service_manager

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
                    self.logger.warning(f"获取网关 {gw_name} 数据失败: {e}", extra={"log_type": "SYSTEM"})

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "data": aggregated_data,
            }

        except Exception as e:
            self._log_error("获取组合监控", e)
            return {"success": False, "message": str(e)}

    def get_historical_performance(
        self,
        portfolio_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
    ) -> Dict[str, Any]:
        """获取组合历史业绩分析.

        对应需求：组合投资的历史业绩分析功能

        Args:
            portfolio_name: 组合名称
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
            period: 统计周期（daily/weekly/monthly/yearly）

        Returns:
            Dict: 历史业绩数据
        """
        try:
            from datetime import datetime, timedelta

            # 默认查询最近30天
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            # 1. 从数据库或日志获取历史交易记录
            trades = self._load_historical_trades(portfolio_name, start_date, end_date)

            # 2. 计算历史业绩曲线
            performance_curve = self._calculate_performance_curve(trades)

            # 3. 按周期统计
            period_stats = self._calculate_period_statistics_data(performance_curve, period)

            # 4. 回撤分析
            drawdown_analysis = self._analyze_drawdowns(performance_curve)

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "start_date": start_date,
                "end_date": end_date,
                "period": period,
                "data": {
                    "performance_curve": performance_curve,
                    "period_statistics": period_stats,
                    "drawdown_analysis": drawdown_analysis,
                },
                "message": "历史业绩数据获取成功",
            }

        except Exception as e:
            self._log_error("获取历史业绩", e)
            return {"success": False, "message": str(e)}

    def calculate_period_statistics(
        self,
        portfolio_name: str | None = None,
        period_type: str = "daily",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Dict[str, Any]:
        """按时间段统计业绩.

        Args:
            portfolio_name: 组合名称（可选，为空时统计所有组合）
            period_type: 周期类型（daily/weekly/monthly）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            Dict: 周期统计数据
        """
        try:
            import pandas as pd
            import numpy as np
            from datetime import datetime

            # 1. 获取成交记录
            all_trades = []
            if portfolio_name:
                # 特定组合
                if portfolio_name.startswith("auto_"):
                    gateway_name = portfolio_name.replace("auto_", "")
                    gateway_trades = self.realtime_cache.get_trades(gateway_name)
                    if gateway_trades:
                        all_trades = gateway_trades
                elif portfolio_name in self.custom_portfolios:
                    # 自定义组合：聚合多个网关
                    portfolio = self.custom_portfolios[portfolio_name]
                    for gw_name in portfolio.get("gateway_names", []):
                        gateway_trades = self.realtime_cache.get_trades(gw_name)
                        if gateway_trades:
                            all_trades.extend(gateway_trades)
            else:
                # 所有组合 - 遍历所有缓存值
                all_trades = self.realtime_cache.get_trades()

            if not all_trades:
                return {
                    "success": True,
                    "period_type": period_type,
                    "statistics": {
                        "daily": [],
                        "weekly": [],
                        "monthly": [],
                        "total_return": 0.0,
                        "max_drawdown": 0.0,
                        "sharpe_ratio": 0.0,
                        "win_rate": 0.0,
                    },
                    "message": "暂无成交数据",
                }

            # 2. 将成交记录转换为DataFrame
            trade_records = []
            for trade in all_trades:
                try:
                    from vnpy.trader.constant import Direction

                    # 解析日期
                    trade_time = trade.datetime if hasattr(trade, "datetime") else datetime.now()
                    date_str = trade_time.strftime("%Y-%m-%d")

                    # 计算交易金额（买入为负，卖出为正）
                    amount = trade.price * trade.volume
                    if hasattr(trade, "direction") and trade.direction == Direction.LONG:
                        amount = -amount  # 买入花钱

                    trade_records.append(
                        {
                            "date": date_str,
                            "symbol": trade.vt_symbol,
                            "price": trade.price,
                            "volume": trade.volume,
                            "amount": amount,
                        }
                    )
                except Exception as e:
                    self.logger.debug(f"跳过无效成交记录: {e}")

            initial_equity = 1_000_000.0

            if not trade_records:
                return self._calculate_period_statistics_local(
                    trade_records, portfolio_name, period_type, initial_equity
                )

            dates = [record["date"] for record in trade_records]
            amounts = [record["amount"] for record in trade_records]

            if self.data_client:
                try:
                    rpc_result = self.data_client.call(
                        "compute_period_statistics",
                        dates=dates,
                        pnl=amounts,
                        initial_equity=initial_equity,
                        risk_free_rate=0.03,
                        trading_days_per_year=252,
                    )
                    if isinstance(rpc_result, dict) and rpc_result.get("success"):
                        summary = rpc_result.get("summary", {})
                        statistics = {
                            "daily": rpc_result.get("daily", []),
                            "weekly": rpc_result.get("weekly", []),
                            "monthly": rpc_result.get("monthly", []),
                            "equity_curve": rpc_result.get("equity_curve", []),
                            "summary": summary,
                            "total_return": float(summary.get("total_return", 0.0)),
                            "max_drawdown": float(summary.get("max_drawdown", 0.0)),
                            "sharpe_ratio": float(summary.get("sharpe_ratio", 0.0)),
                            "win_rate": float(summary.get("win_rate", 0.0)),
                            "total_pnl": float(summary.get("total_pnl", sum(amounts))),
                        }
                        return {
                            "success": True,
                            "portfolio_name": portfolio_name or "全部组合",
                            "period_type": period_type,
                            "statistics": statistics,
                            "message": "周期统计计算完成（数据进程）",
                        }
                except Exception as rpc_exc:
                    self.logger.warning(
                        "数据进程周期统计计算失败，回退本地实现: %s",
                        rpc_exc,
                        exc_info=True,
                        extra={"log_type": "SYSTEM"},
                    )

            return self._calculate_period_statistics_local(
                trade_records, portfolio_name, period_type, initial_equity
            )

        except Exception as e:
            self._log_error("计算周期统计", e)
            return {"success": False, "message": str(e)}

    # ==================== 高级风险指标 ====================

    def calculate_portfolio_risk_metrics(
        self, portfolio_name: str, price_history: List[float], confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """计算组合高级风险指标.

        Args:
            portfolio_name: 组合名称
            price_history: 价格历史数据列表
            confidence_level: 置信水平（默认95%）

        Returns:
            Dict: 风险指标
        """
        try:
            import numpy as np

            if not price_history or len(price_history) < 2:
                return {
                    "success": False,
                    "message": "价格数据不足，无法计算风险指标",
                }

            # 转换为numpy数组
            prices = np.array(price_history)

            # 1. 计算收益率
            returns = np.diff(prices) / prices[:-1]

            # 2. 计算波动率（年化）
            volatility = np.std(returns) * np.sqrt(252)  # 假设252个交易日

            # 3. 计算VaR（Value at Risk）
            var_percentile = (1 - confidence_level) * 100
            var_value = np.percentile(returns, var_percentile)
            var_amount = abs(var_value * prices[-1])  # 转换为金额

            # 4. 计算CVaR（Conditional VaR，期望损失）
            cvar_returns = returns[returns <= var_value]
            cvar_value = np.mean(cvar_returns) if len(cvar_returns) > 0 else var_value
            cvar_amount = abs(cvar_value * prices[-1])

            # 5. 计算最大回撤
            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0.0

            # 6. 计算夏普比率（假设无风险利率为3%）
            risk_free_rate = 0.03
            excess_returns = np.mean(returns) * 252 - risk_free_rate
            sharpe_ratio = excess_returns / volatility if volatility > 0 else 0.0

            self.logger.info(
                "组合 %s 风险指标计算完成: VaR=%.2f, CVaR=%.2f, 最大回撤=%.2f%%, 夏普比率=%.2f",
                portfolio_name,
                var_amount,
                cvar_amount,
                max_drawdown * 100,
                sharpe_ratio,
            )

            # 风险告警检查 - 日志埋点v4.0
            if abs(max_drawdown) > 0.20:  # 最大回撤超过20%
                logger_alert.warning(
                    "风险告警: 最大回撤过大, 组合=%s, 最大回撤=%.2f%%",
                    portfolio_name,
                    max_drawdown * 100,
                    extra={"log_type": "ALERT"}
                )

            if volatility > 0.40:  # 年化波动率超过40%
                logger_alert.warning(
                    "风险告警: 波动率过高, 组合=%s, 年化波动率=%.2f%%",
                    portfolio_name,
                    volatility * 100,
                    extra={"log_type": "ALERT"}
                )

            if sharpe_ratio < 0:  # 夏普比率为负
                logger_alert.error(
                    "风险告警: 夏普比率为负, 组合=%s, 夏普比率=%.2f", portfolio_name, sharpe_ratio, extra={"log_type": "ALERT"}
                )

            return {
                "success": True,
                "metrics": {
                    "volatility": float(volatility),
                    "var_95": float(var_amount),
                    "cvar_95": float(cvar_amount),
                    "max_drawdown": float(max_drawdown),
                    "sharpe_ratio": float(sharpe_ratio),
                    "mean_return": float(np.mean(returns)),
                    "std_return": float(np.std(returns)),
                },
            }

        except ImportError as e:
            self.logger.warning(f"scipy或numpy未安装: {e}", extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "message": "scipy或numpy未安装，无法计算高级风险指标",
            }
        except Exception as e:
            self._log_error("计算风险指标", e)
            return {
                "success": False,
                "message": f"计算失败: {str(e)}",
            }

    def calculate_correlation_matrix(
        self, portfolio_name: str, returns_data: Dict[str, List[float]]
    ) -> Dict[str, Any]:
        """计算组合内品种间的相关性矩阵.

        Args:
            portfolio_name: 组合名称
            returns_data: 各品种的收益率数据 {"symbol": [returns...]}

        Returns:
            Dict: 相关性矩阵和分析结果
        """
        try:
            import numpy as np

            if not returns_data or len(returns_data) < 2:
                return {
                    "success": False,
                    "message": "至少需要2个品种的数据才能计算相关性",
                }

            # 构建收益率矩阵
            symbols = list(returns_data.keys())
            min_length = min(len(data) for data in returns_data.values())

            returns_matrix = np.array([returns_data[symbol][:min_length] for symbol in symbols])

            # 计算相关性矩阵
            correlation_matrix = np.corrcoef(returns_matrix)

            # 转换为字典格式
            correlation_dict = {}
            for i, symbol1 in enumerate(symbols):
                correlation_dict[symbol1] = {}
                for j, symbol2 in enumerate(symbols):
                    correlation_dict[symbol1][symbol2] = float(correlation_matrix[i, j])

            # 计算平均相关性（排除对角线）
            n = len(symbols)
            avg_correlation = (np.sum(correlation_matrix) - n) / (n * (n - 1)) if n > 1 else 0.0

            self.logger.info(f"组合 {portfolio_name} 相关性矩阵计算完成")

            return {
                "success": True,
                "symbols": symbols,
                "correlation_matrix": correlation_dict,
                "avg_correlation": float(avg_correlation),
            }

        except ImportError:
            return {
                "success": False,
                "message": "numpy未安装，无法计算相关性矩阵",
            }
        except Exception as e:
            self._log_error("计算相关性矩阵", e)
            return {
                "success": False,
                "message": f"计算失败: {str(e)}",
            }

    def _load_historical_trades(
        self, portfolio_name: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """从数据库加载历史交易记录.

        Args:
            portfolio_name: 组合名称
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict]: 交易记录列表
        """
        try:
            from backend.services.database_adapter import get_db_manager

            self.logger.info(
                "加载组合 %s 的历史交易记录 (%s ~ %s)", portfolio_name, start_date, end_date
            )

            # 从数据库查询历史交易记录
            db_manager = get_db_manager()
            query = """
                SELECT
                    trade_date as date,
                    symbol,
                    direction,
                    price,
                    volume,
                    pnl
                FROM trade_history
                WHERE portfolio_id = ?
                  AND trade_date BETWEEN ? AND ?
                ORDER BY trade_date, trade_time
            """

            trades = db_manager.execute_query(query, (portfolio_name, start_date, end_date))

            # 如果数据库中没有数据，生成模拟数据用于演示
            if not trades:
                self.logger.warning("数据库中无历史交易记录，使用模拟数据", extra={"log_type": "SYSTEM"})
                trades = self._generate_mock_trades(start_date, end_date)

            self.logger.info("加载了 %d 条历史交易记录", len(trades))
            return trades

        except Exception as e:
            self.logger.error("加载历史交易记录失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            # 发生错误时返回模拟数据
            return self._generate_mock_trades(start_date, end_date)

    def _generate_mock_trades(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """生成模拟交易数据（用于演示和测试）.

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict]: 模拟交易记录列表
        """
        try:
            from datetime import datetime, timedelta
            import random

            trades = []
            current_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            # 生成模拟交易数据
            while current_date <= end_dt:
                # 每天可能有0-3笔交易
                num_trades = random.randint(0, 3)
                for _ in range(num_trades):
                    trades.append(
                        {
                            "date": current_date.strftime("%Y-%m-%d"),
                            "symbol": random.choice(["600000.SSE", "600036.SSE", "000001.SZSE"]),
                            "price": random.uniform(10, 50),
                            "volume": random.randint(100, 1000),
                            "direction": random.choice(["BUY", "SELL"]),
                            "pnl": random.uniform(-500, 1000),
                        }
                    )
                current_date += timedelta(days=1)

            return trades

        except Exception as e:
            self.logger.error("生成模拟交易数据失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return []

    def _calculate_performance_curve(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """计算业绩曲线.

        Args:
            trades: 交易记录列表

        Returns:
            List[Dict]: 业绩曲线数据点
        """
        try:
            if not trades:
                return []

            # 按日期分组统计
            from collections import defaultdict

            daily_pnl = defaultdict(float)

            for trade in trades:
                date = trade.get("date", "")
                pnl = trade.get("pnl", 0)
                daily_pnl[date] += pnl

            # 计算累计收益
            sorted_dates = sorted(daily_pnl.keys())
            cumulative_pnl = 0
            initial_capital = 1000000  # 初始资金100万

            performance_curve = []
            for date in sorted_dates:
                daily = daily_pnl[date]
                cumulative_pnl += daily
                equity = initial_capital + cumulative_pnl
                return_rate = cumulative_pnl / initial_capital if initial_capital > 0 else 0

                performance_curve.append(
                    {
                        "date": date,
                        "daily_pnl": round(daily, 2),
                        "cumulative_pnl": round(cumulative_pnl, 2),
                        "equity": round(equity, 2),
                        "return_rate": round(return_rate * 100, 2),  # 百分比
                    }
                )

            return performance_curve

        except Exception as e:
            self.logger.error("计算业绩曲线失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return []

    def _calculate_period_statistics_data(
        self, performance_curve: List[Dict[str, Any]], period: str
    ) -> List[Dict[str, Any]]:
        """按周期统计业绩数据.

        Args:
            performance_curve: 业绩曲线
            period: 统计周期（daily/weekly/monthly/yearly）

        Returns:
            List[Dict]: 周期统计数据
        """
        try:
            if not performance_curve:
                return []

            from datetime import datetime

            # 按周期分组
            period_data = {}
            for point in performance_curve:
                date_str = point["date"]
                date = datetime.strptime(date_str, "%Y-%m-%d")

                # 确定周期键
                if period == "daily":
                    period_key = date_str
                elif period == "weekly":
                    period_key = date.strftime("%Y-W%U")  # 年-周
                elif period == "monthly":
                    period_key = date.strftime("%Y-%m")  # 年-月
                elif period == "yearly":
                    period_key = date.strftime("%Y")  # 年
                else:
                    period_key = date_str

                if period_key not in period_data:
                    period_data[period_key] = {
                        "period": period_key,
                        "start_equity": point["equity"],
                        "end_equity": point["equity"],
                        "pnl": 0,
                        "return_rate": 0,
                        "max_drawdown": 0,
                    }

                period_data[period_key]["end_equity"] = point["equity"]
                period_data[period_key]["pnl"] += point["daily_pnl"]

            # 计算各周期的收益率和回撤
            statistics = []
            for data in sorted(period_data.values(), key=lambda x: x["period"]):
                start_eq = data["start_equity"]
                end_eq = data["end_equity"]
                return_rate = ((end_eq - start_eq) / start_eq * 100) if start_eq > 0 else 0

                statistics.append(
                    {
                        "period": data["period"],
                        "pnl": round(data["pnl"], 2),
                        "return_rate": round(return_rate, 2),
                        "start_equity": round(start_eq, 2),
                        "end_equity": round(end_eq, 2),
                    }
                )

            return statistics

        except Exception as e:
            self.logger.error("计算周期统计失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return []

    def _calculate_period_statistics_local(
        self,
        trade_records: List[Dict[str, Any]],
        portfolio_name: str | None,
        period_type: str,
        initial_equity: float,
    ) -> Dict[str, Any]:
        """本地降级版周期统计（使用pandas/numpy）"""
        try:
            import pandas as pd
            import numpy as np

            if not trade_records:
                return {
                    "success": True,
                    "portfolio_name": portfolio_name or "全部组合",
                    "period_type": period_type,
                    "statistics": {
                        "daily": [],
                        "weekly": [],
                        "monthly": [],
                        "total_return": 0.0,
                        "max_drawdown": 0.0,
                        "sharpe_ratio": 0.0,
                        "win_rate": 0.0,
                        "total_pnl": 0.0,
                        "summary": {
                            "initial_equity": initial_equity,
                            "final_equity": initial_equity,
                        },
                    },
                    "message": "暂无成交数据",
                }

            df = pd.DataFrame(trade_records)
            df["date"] = pd.to_datetime(df["date"])

            daily_pnl = df.groupby("date")["amount"].sum().reset_index()
            daily_pnl.columns = ["date", "pnl"]
            daily_pnl["date_str"] = daily_pnl["date"].dt.strftime("%Y-%m-%d")

            cumulative_pnl = daily_pnl["pnl"].cumsum()
            prev_equity = cumulative_pnl.shift(1) + initial_equity
            prev_equity.iloc[0] = initial_equity
            daily_pnl["return"] = np.where(prev_equity > 0, daily_pnl["pnl"] / prev_equity, 0.0)
            daily_pnl["cumulative_return"] = (1 + daily_pnl["return"].fillna(0)).cumprod() - 1

            weekly_pnl = (
                daily_pnl.set_index("date")["pnl"].resample("W").sum().reset_index()
            )
            weekly_pnl.columns = ["date", "pnl"]
            weekly_prev_equity = weekly_pnl["pnl"].cumsum().shift(1) + initial_equity
            weekly_prev_equity.iloc[0] = initial_equity
            weekly_pnl["date_str"] = weekly_pnl["date"].dt.strftime("%Y-W%U")
            weekly_pnl["return"] = np.where(
                weekly_prev_equity > 0, weekly_pnl["pnl"] / weekly_prev_equity, 0.0
            )
            weekly_pnl["cumulative_return"] = (1 + weekly_pnl["return"].fillna(0)).cumprod() - 1

            monthly_pnl = (
                daily_pnl.set_index("date")["pnl"].resample("M").sum().reset_index()
            )
            monthly_pnl.columns = ["date", "pnl"]
            monthly_prev_equity = monthly_pnl["pnl"].cumsum().shift(1) + initial_equity
            monthly_prev_equity.iloc[0] = initial_equity
            monthly_pnl["date_str"] = monthly_pnl["date"].dt.strftime("%Y-%m")
            monthly_pnl["return"] = np.where(
                monthly_prev_equity > 0, monthly_pnl["pnl"] / monthly_prev_equity, 0.0
            )
            monthly_pnl["cumulative_return"] = (
                1 + monthly_pnl["return"].fillna(0)
            ).cumprod() - 1

            total_pnl = daily_pnl["pnl"].sum()
            total_return = daily_pnl["cumulative_return"].iloc[-1] if len(daily_pnl) > 0 else 0.0

            cumulative = (1 + daily_pnl["return"].fillna(0)).cumprod()
            running_max = cumulative.cummax()
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = drawdowns.min() if len(drawdowns) > 0 else 0.0

            if len(daily_pnl) > 1:
                mean_return = daily_pnl["return"].mean() * 252
                std_return = daily_pnl["return"].std() * np.sqrt(252)
                sharpe_ratio = (mean_return - 0.03) / std_return if std_return > 0 else 0.0
            else:
                sharpe_ratio = 0.0

            win_count = (daily_pnl["pnl"] > 0).sum()
            total_count = len(daily_pnl)
            win_rate = win_count / total_count if total_count > 0 else 0.0

            daily_stats = daily_pnl[
                ["date_str", "pnl", "return", "cumulative_return"]
            ].rename(columns={"date_str": "period"}).to_dict(orient="records")  # type: ignore[arg-type]
            weekly_stats = weekly_pnl[
                ["date_str", "pnl", "return", "cumulative_return"]
            ].rename(columns={"date_str": "period"}).to_dict(orient="records")  # type: ignore[arg-type]
            monthly_stats = monthly_pnl[
                ["date_str", "pnl", "return", "cumulative_return"]
            ].rename(columns={"date_str": "period"}).to_dict(orient="records")  # type: ignore[arg-type]

            statistics = {
                "daily": daily_stats,
                "weekly": weekly_stats,
                "monthly": monthly_stats,
                "total_return": float(total_return),
                "max_drawdown": float(max_drawdown),
                "sharpe_ratio": float(sharpe_ratio),
                "win_rate": float(win_rate),
                "total_pnl": float(total_pnl),
                "summary": {
                    "initial_equity": float(initial_equity),
                    "final_equity": float(initial_equity + total_pnl),
                },
            }

            return {
                "success": True,
                "portfolio_name": portfolio_name or "全部组合",
                "period_type": period_type,
                "statistics": statistics,
                "message": "周期统计计算完成（本地）",
            }

        except ImportError as e:
            self.logger.error("pandas未安装，无法计算周期统计: %s", e, extra={"log_type": "SYSTEM"})
            return {"success": False, "message": "pandas库未安装"}
        except Exception as e:
            self._log_error("计算周期统计", e)
            return {"success": False, "message": str(e)}

    def _analyze_drawdowns(self, performance_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """分析回撤情况.

        Args:
            performance_curve: 业绩曲线

        Returns:
            List[Dict]: 回撤分析数据
        """
        try:
            if not performance_curve:
                return []

            import numpy as np

            # 提取权益曲线
            equities = [p["equity"] for p in performance_curve]
            dates = [p["date"] for p in performance_curve]

            # 计算回撤
            equities_arr = np.array(equities)
            running_max = np.maximum.accumulate(equities_arr)
            drawdowns = (equities_arr - running_max) / running_max * 100  # 百分比

            # 找出主要回撤期
            drawdown_periods = []
            in_drawdown = False
            start_idx = 0

            for i, dd in enumerate(drawdowns):
                if dd < -0.5 and not in_drawdown:  # 回撤超过0.5%
                    in_drawdown = True
                    start_idx = i
                elif dd >= 0 and in_drawdown:  # 回撤结束
                    in_drawdown = False
                    # 找出这段期间的最大回撤
                    period_drawdowns = drawdowns[start_idx : i + 1]
                    max_dd_idx = start_idx + np.argmin(period_drawdowns)

                    drawdown_periods.append(
                        {
                            "start_date": dates[start_idx],
                            "end_date": dates[i],
                            "max_drawdown": round(float(drawdowns[max_dd_idx]), 2),
                            "max_drawdown_date": dates[max_dd_idx],
                            "recovery_days": i - start_idx,
                        }
                    )

            # 计算最大回撤
            max_drawdown = float(np.min(drawdowns))
            max_dd_idx = int(np.argmin(drawdowns))

            analysis = {
                "max_drawdown": round(max_drawdown, 2),
                "max_drawdown_date": dates[max_dd_idx],
                "drawdown_periods": drawdown_periods[:10],  # 返回前10个主要回撤期
                "current_drawdown": round(float(drawdowns[-1]), 2),
            }

            return [analysis]

        except Exception as e:
            self.logger.error("分析回撤失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return []

    def save_trade_to_history(
        self,
        portfolio_id: str,
        gateway_name: str,
        strategy_name: str,
        trade_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """保存交易记录到历史数据库.

        Args:
            portfolio_id: 组合ID
            gateway_name: 网关名称
            strategy_name: 策略名称
            trade_data: 交易数据

        Returns:
            Dict: 保存结果
        """
        try:
            from backend.services.database_adapter import get_db_manager
            from datetime import datetime

            db_manager = get_db_manager()

            # 准备数据
            trade_date = trade_data.get("date") or datetime.now().strftime("%Y-%m-%d")
            trade_time = trade_data.get("time") or datetime.now().isoformat()

            query = """
                INSERT INTO trade_history (
                    portfolio_id, gateway_name, strategy_name,
                    trade_date, trade_time, symbol, direction, offset,
                    price, volume, turnover, commission, slippage, pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            params = (
                portfolio_id,
                gateway_name,
                strategy_name,
                trade_date,
                trade_time,
                trade_data.get("symbol", ""),
                trade_data.get("direction", ""),
                trade_data.get("offset", ""),
                trade_data.get("price", 0),
                trade_data.get("volume", 0),
                trade_data.get("turnover", 0),
                trade_data.get("commission", 0),
                trade_data.get("slippage", 0),
                trade_data.get("pnl", 0),
            )

            db_manager.execute_update(query, params)

            return {"success": True, "message": "交易记录已保存"}

        except Exception as e:
            self.logger.error("保存交易记录失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return {"success": False, "message": str(e)}

    def save_account_snapshot(
        self, portfolio_id: str, snapshot_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """保存账户快照.

        Args:
            portfolio_id: 组合ID
            snapshot_data: 快照数据

        Returns:
            Dict: 保存结果
        """
        try:
            from backend.services.database_adapter import get_db_manager
            from datetime import datetime

            db_manager = get_db_manager()

            snapshot_date = snapshot_data.get("date") or datetime.now().strftime("%Y-%m-%d")
            snapshot_time = snapshot_data.get("time") or datetime.now().isoformat()

            query = """
                INSERT OR REPLACE INTO account_snapshots (
                    portfolio_id, snapshot_date, snapshot_time,
                    balance, available, frozen, margin, total_pnl, daily_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            params = (
                portfolio_id,
                snapshot_date,
                snapshot_time,
                snapshot_data.get("balance", 0),
                snapshot_data.get("available", 0),
                snapshot_data.get("frozen", 0),
                snapshot_data.get("margin", 0),
                snapshot_data.get("total_pnl", 0),
                snapshot_data.get("daily_pnl", 0),
            )

            db_manager.execute_update(query, params)

            return {"success": True, "message": "账户快照已保存"}

        except Exception as e:
            self.logger.error("保存账户快照失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return {"success": False, "message": str(e)}

    def calculate_portfolio_volatility(
        self,
        portfolio_name: str,
        weights: Dict[str, float],
        volatilities: Dict[str, float],
        correlation_matrix: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """计算组合波动率（考虑相关性）.

        Args:
            portfolio_name: 组合名称
            weights: 各品种权重 {"symbol": weight}
            volatilities: 各品种波动率 {"symbol": volatility}
            correlation_matrix: 相关性矩阵

        Returns:
            Dict: 组合波动率
        """
        try:
            import numpy as np

            symbols = list(weights.keys())
            n = len(symbols)

            if n < 1:
                return {
                    "success": False,
                    "message": "没有品种数据",
                }

            # 构建权重向量
            w = np.array([weights[s] for s in symbols])

            # 构建协方差矩阵
            cov_matrix = np.zeros((n, n))
            for i, s1 in enumerate(symbols):
                for j, s2 in enumerate(symbols):
                    vol1 = volatilities.get(s1, 0)
                    vol2 = volatilities.get(s2, 0)
                    corr = correlation_matrix.get(s1, {}).get(s2, 0)
                    cov_matrix[i, j] = vol1 * vol2 * corr

            # 计算组合波动率: sqrt(w^T * Cov * w)
            portfolio_variance = np.dot(w, np.dot(cov_matrix, w))
            portfolio_volatility = np.sqrt(portfolio_variance)

            # 计算分散化效益
            weighted_avg_vol = np.sum(w * np.array([volatilities[s] for s in symbols]))
            diversification_benefit = weighted_avg_vol - portfolio_volatility

            self.logger.info(f"组合 {portfolio_name} 波动率计算完成: {portfolio_volatility:.4f}")

            return {
                "success": True,
                "portfolio_volatility": float(portfolio_volatility),
                "weighted_avg_volatility": float(weighted_avg_vol),
                "diversification_benefit": float(diversification_benefit),
            }

        except ImportError:
            return {
                "success": False,
                "message": "numpy未安装，无法计算组合波动率",
            }
        except Exception as e:
            self._log_error("计算组合波动率", e)
            return {
                "success": False,
                "message": f"计算失败: {str(e)}",
            }

    # ==================== 高级风险指标计算 ====================

    def _calculate_risk_metrics_legacy(
        self, portfolio_name: str, lookback_days: int = 60
    ) -> Dict[str, Any]:
        """计算高级风险指标（VaR、CVaR、夏普比率等）.

        Args:
            portfolio_name: 组合名称
            lookback_days: 回溯天数（默认60天）

        Returns:
            Dict: {
                "success": True,
                "metrics": {
                    "var_95": 0.05,      # 95%置信度VaR
                    "var_99": 0.08,      # 99%置信度VaR
                    "cvar_95": 0.07,     # 95%条件VaR
                    "cvar_99": 0.10,     # 99%条件VaR
                    "volatility": 0.15,  # 年化波动率
                    "sharpe_ratio": 1.5, # 夏普比率
                    "sortino_ratio": 1.8,# 索提诺比率
                    "max_drawdown": 0.12,# 最大回撤
                    "max_drawdown_duration": 15,  # 最大回撤持续天数
                    "calmar_ratio": 1.2, # 卡玛比率
                    "beta": 1.2,         # Beta值
                    "alpha": 0.03,       # Alpha值
                    "information_ratio": 0.8,  # 信息比率
                }
            }
        """
        try:
            import numpy as np
            from scipy import stats

            # 1. 获取收益率序列
            returns_result = self._get_portfolio_returns(portfolio_name, lookback_days)

            if not returns_result.get("success"):
                return returns_result

            returns = returns_result.get("returns", [])

            if len(returns) < 30:
                return {
                    "success": False,
                    "message": f"数据不足（需要至少30天数据，当前{len(returns)}天）",
                }

            returns_array = np.array(returns)

            # 2. VaR计算（参数法 - 基于正态分布假设）
            mean_return = np.mean(returns_array)
            std_return = np.std(returns_array)

            var_95 = stats.norm.ppf(0.05, loc=mean_return, scale=std_return)
            var_99 = stats.norm.ppf(0.01, loc=mean_return, scale=std_return)

            # 3. CVaR计算（条件VaR / 预期损失）
            # CVaR是在VaR阈值之下的平均损失
            losses_95 = returns_array[returns_array <= var_95]
            cvar_95 = losses_95.mean() if len(losses_95) > 0 else var_95

            losses_99 = returns_array[returns_array <= var_99]
            cvar_99 = losses_99.mean() if len(losses_99) > 0 else var_99

            # 4. 波动率（年化）
            volatility = std_return * np.sqrt(252)  # 假设252个交易日

            # 5. 夏普比率
            risk_free_rate = 0.03  # 3%无风险利率（可配置）
            excess_return = mean_return * 252 - risk_free_rate
            sharpe_ratio = excess_return / volatility if volatility > 0 else 0

            # 6. 索提诺比率（只考虑下行风险）
            downside_returns = returns_array[returns_array < 0]
            downside_std = np.std(downside_returns) if len(downside_returns) > 0 else std_return
            downside_volatility = downside_std * np.sqrt(252)
            sortino_ratio = excess_return / downside_volatility if downside_volatility > 0 else 0

            # 7. 最大回撤和持续时间
            cumulative = np.cumprod(1 + returns_array)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = np.min(drawdown)

            # 计算最大回撤持续天数
            max_dd_duration = self._calculate_max_drawdown_duration(drawdown)

            # 8. 卡玛比率（收益/最大回撤）
            annual_return = mean_return * 252
            calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

            # 9. Beta和Alpha（需要基准数据）
            benchmark_result = self._get_benchmark_returns(lookback_days)

            beta = None
            alpha = None
            information_ratio = None

            if benchmark_result.get("success"):
                benchmark_returns = np.array(benchmark_result.get("returns", []))

                # 确保长度一致
                min_len = min(len(returns_array), len(benchmark_returns))
                returns_array_aligned = returns_array[-min_len:]
                benchmark_aligned = benchmark_returns[-min_len:]

                if len(benchmark_aligned) > 0:
                    # Beta = Cov(Portfolio, Benchmark) / Var(Benchmark)
                    covariance = np.cov(returns_array_aligned, benchmark_aligned)[0, 1]
                    benchmark_variance = np.var(benchmark_aligned)
                    beta = covariance / benchmark_variance if benchmark_variance > 0 else 1.0

                    # Alpha = Portfolio_Return - (Risk_Free_Rate + Beta * (Benchmark_Return - Risk_Free_Rate))
                    benchmark_return = np.mean(benchmark_aligned) * 252
                    portfolio_return = mean_return * 252
                    alpha = portfolio_return - (
                        risk_free_rate + beta * (benchmark_return - risk_free_rate)
                    )

                    # 信息比率 = (Portfolio_Return - Benchmark_Return) / Tracking_Error
                    active_returns = returns_array_aligned - benchmark_aligned
                    tracking_error = np.std(active_returns) * np.sqrt(252)
                    information_ratio = (
                        (portfolio_return - benchmark_return) / tracking_error
                        if tracking_error > 0
                        else 0
                    )

            metrics = {
                "var_95": float(var_95),
                "var_99": float(var_99),
                "cvar_95": float(cvar_95),
                "cvar_99": float(cvar_99),
                "volatility": float(volatility),
                "sharpe_ratio": float(sharpe_ratio),
                "sortino_ratio": float(sortino_ratio),
                "max_drawdown": float(max_drawdown),
                "max_drawdown_duration": int(max_dd_duration),
                "calmar_ratio": float(calmar_ratio),
                "annual_return": float(mean_return * 252),
                "beta": float(beta) if beta is not None else None,
                "alpha": float(alpha) if alpha is not None else None,
                "information_ratio": (
                    float(information_ratio) if information_ratio is not None else None
                ),
            }

            return {
                "success": True,
                "portfolio_name": portfolio_name,
                "lookback_days": lookback_days,
                "metrics": metrics,
                "message": "风险指标计算成功",
            }

        except ImportError as e:
            return {"success": False, "message": f"缺少必要的库: {str(e)}"}
        except Exception as e:
            self._log_error("计算风险指标", e)
            return {"success": False, "message": f"计算失败: {str(e)}"}

    def calculate_risk_metrics(
        self, portfolio_name: str, lookback_days: int = 60
    ) -> Dict[str, Any]:
        """计算高级风险指标，优先使用数据进程原生实现."""
        try:
            returns_result = self._get_portfolio_returns(portfolio_name, lookback_days)
            if not returns_result.get("success"):
                return returns_result

            returns = returns_result.get("returns", [])
            equity_curve = returns_result.get("equity_curve", [])
            dates = returns_result.get("dates", [])

            if not returns or len(returns) < 30:
                return {
                    "success": False,
                    "message": f"数据不足（需要至少30天数据，当前{len(returns)}天）",
                }

            scale = equity_curve[-1] if equity_curve else 1.0
            benchmark_result = self._get_benchmark_returns(lookback_days)
            risk_profile: Optional[Dict[str, Any]] = None

            if self.data_client:
                try:
                    risk_profile = self.data_client.call(
                        "compute_risk_profile",
                        returns=returns,
                        scale=scale,
                        risk_free_rate=0.03,
                        trading_days_per_year=252,
                        confidence_levels=[0.95, 0.99],
                    )
                    if not isinstance(risk_profile, dict) or not risk_profile.get("success", True):
                        risk_profile = None
                except Exception as rpc_exc:
                    self.logger.warning(
                        "数据进程风险画像计算失败，回退本地实现: %s",
                        rpc_exc,
                        exc_info=True,
                        extra={"log_type": "SYSTEM"},
                    )
                    risk_profile = None

            if risk_profile:
                try:
                    var_map = (
                        risk_profile.get("var", {})
                        if isinstance(risk_profile.get("var"), dict)
                        else {}
                    )
                    var_95 = float(var_map.get("0.95", {}).get("var_amount", 0.0))
                    var_99 = float(var_map.get("0.99", {}).get("var_amount", 0.0))
                    cvar_95 = float(var_map.get("0.95", {}).get("cvar_amount", 0.0))
                    cvar_99 = float(var_map.get("0.99", {}).get("cvar_amount", 0.0))

                    volatility = float(risk_profile.get("annual_volatility", 0.0))
                    sharpe_ratio = float(risk_profile.get("sharpe_ratio", 0.0))
                    sortino_ratio = float(risk_profile.get("sortino_ratio", 0.0))
                    max_drawdown = float(risk_profile.get("max_drawdown", 0.0))
                    max_drawdown_duration = int(risk_profile.get("max_drawdown_duration", 0))
                    calmar_ratio = float(risk_profile.get("calmar_ratio", 0.0))
                    annual_return = float(risk_profile.get("annual_return", 0.0))
                    mean_return = float(risk_profile.get("mean_return", 0.0))
                    std_return = float(risk_profile.get("std_return", 0.0))
                    cumulative_return = float(risk_profile.get("cumulative_return", 0.0))

                    beta = None
                    alpha = None
                    information_ratio = None

                    try:
                        import numpy as np

                        if benchmark_result.get("success"):
                            benchmark_returns = np.array(benchmark_result.get("returns", []), dtype=float)
                            min_len = min(len(returns), len(benchmark_returns))
                            if min_len > 0:
                                returns_array = np.array(returns[-min_len:], dtype=float)
                                benchmark_array = benchmark_returns[-min_len:]

                                covariance = float(np.cov(returns_array, benchmark_array)[0, 1])
                                benchmark_variance = float(np.var(benchmark_array))
                                if benchmark_variance > 0:
                                    beta = covariance / benchmark_variance

                                benchmark_return = float(np.mean(benchmark_array) * 252)
                                portfolio_return = mean_return * 252
                                risk_free_rate = 0.03
                                if beta is not None:
                                    alpha = portfolio_return - (
                                        risk_free_rate + beta * (benchmark_return - risk_free_rate)
                                    )

                                active_returns = returns_array - benchmark_array
                                tracking_error = float(np.std(active_returns) * np.sqrt(252))
                                if tracking_error > 0:
                                    information_ratio = (portfolio_return - benchmark_return) / tracking_error
                    except Exception:
                        self.logger.debug(
                            "计算Beta/Alpha信息比率失败（数据进程路径）",
                            exc_info=True,
                            extra={"log_type": "SYSTEM"},
                        )

                    metrics: Dict[str, Any] = {
                        "volatility": float(volatility),
                        "var_95": float(var_95),
                        "var_99": float(var_99),
                        "cvar_95": float(cvar_95),
                        "cvar_99": float(cvar_99),
                        "max_drawdown": float(max_drawdown),
                        "max_drawdown_duration": int(max_drawdown_duration),
                        "sharpe_ratio": float(sharpe_ratio),
                        "sortino_ratio": float(sortino_ratio),
                        "calmar_ratio": float(calmar_ratio),
                        "annual_return": float(annual_return),
                        "mean_return": float(mean_return),
                        "std_return": float(std_return),
                        "total_return": float(cumulative_return),
                        "beta": float(beta) if beta is not None else None,
                        "alpha": float(alpha) if alpha is not None else None,
                        "information_ratio": float(information_ratio) if information_ratio is not None else None,
                        "skewness": float(risk_profile.get("skewness", 0.0)),
                        "kurtosis": float(risk_profile.get("kurtosis", 0.0)),
                        "win_rate": float(risk_profile.get("win_rate", 0.0)),
                        "loss_rate": float(risk_profile.get("loss_rate", 0.0)),
                        "avg_gain": float(risk_profile.get("avg_gain", 0.0)),
                        "avg_loss": float(risk_profile.get("avg_loss", 0.0)),
                        "downside_deviation": float(risk_profile.get("downside_deviation", 0.0)),
                    }

                    if abs(max_drawdown) > 0.20:
                        logger_alert.warning(
                            "风险告警: 最大回撤过大, 组合=%s, 最大回撤=%.2f%%",
                            portfolio_name,
                            max_drawdown * 100,
                            extra={"log_type": "ALERT"},
                        )
                    if volatility > 0.40:
                        logger_alert.warning(
                            "风险告警: 波动率过高, 组合=%s, 年化波动率=%.2f%%",
                            portfolio_name,
                            volatility * 100,
                            extra={"log_type": "ALERT"},
                        )
                    if sharpe_ratio < 0:
                        logger_alert.error(
                            "风险告警: 夏普比率为负, 组合=%s, 夏普比率=%.2f",
                            portfolio_name,
                            sharpe_ratio,
                            extra={"log_type": "ALERT"},
                        )

                    self.logger.info(
                        "组合 %s 风险指标计算完成（数据进程）: VaR95=%.2f, CVaR95=%.2f, 最大回撤=%.2f%%, 夏普=%.2f",
                        portfolio_name,
                        var_95,
                        cvar_95,
                        max_drawdown * 100,
                        sharpe_ratio,
                    )

                    return {
                        "success": True,
                        "portfolio_name": portfolio_name,
                        "lookback_days": lookback_days,
                        "metrics": metrics,
                        "dates": dates,
                        "message": "风险指标计算成功（数据进程）",
                    }
                except Exception as build_exc:
                    self.logger.warning(
                        "解析数据进程风险画像结果失败，回退本地实现: %s",
                        build_exc,
                        exc_info=True,
                        extra={"log_type": "SYSTEM"},
                    )

            return self._calculate_risk_metrics_legacy(portfolio_name, lookback_days)

        except Exception as e:
            self._log_error("计算风险指标", e)
            return {"success": False, "message": str(e)}

    def _get_portfolio_returns(
        self, portfolio_name: str, lookback_days: int = 60
    ) -> Dict[str, Any]:
        """获取组合收益率序列.

        Args:
            portfolio_name: 组合名称
            lookback_days: 回溯天数

        Returns:
            Dict: {
                "success": True,
                "returns": [0.01, -0.005, 0.02, ...],  # 日收益率列表
                "equity_curve": [100000, 101000, 100495, ...]  # 权益曲线
            }
        """
        try:
            from datetime import datetime, timedelta

            # 从历史成交记录计算收益率
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            trades = self._load_historical_trades(portfolio_name, start_date, end_date)

            if not trades:
                return {"success": False, "message": "无历史成交数据"}

            # 按日聚合盈亏
            daily_pnl = {}
            for trade in trades:
                trade_date = trade.get("date", "")[:10]  # 提取日期部分
                pnl = trade.get("pnl", 0)

                if trade_date:
                    if trade_date not in daily_pnl:
                        daily_pnl[trade_date] = 0
                    daily_pnl[trade_date] += pnl

            # 构造权益曲线
            sorted_dates = sorted(daily_pnl.keys())
            initial_equity = 1000000  # 初始资金（可配置）

            equity_curve = [initial_equity]
            returns = []

            for date in sorted_dates:
                pnl = daily_pnl[date]
                new_equity = equity_curve[-1] + pnl
                equity_curve.append(new_equity)

                # 计算收益率
                ret = pnl / equity_curve[-2] if equity_curve[-2] > 0 else 0
                returns.append(ret)

            return {
                "success": True,
                "returns": returns,
                "equity_curve": equity_curve,
                "dates": sorted_dates,
            }

        except Exception as e:
            self.logger.error(f"获取组合收益率失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return {"success": False, "message": str(e)}

    def _get_benchmark_returns(
        self, lookback_days: int = 60, index_code: str = "000300"
    ) -> Dict[str, Any]:
        """获取基准收益率序列（真实数据）.

        Args:
            lookback_days: 回溯天数
            index_code: 指数代码（默认沪深300）

        Returns:
            Dict: {
                "success": True,
                "returns": [0.008, -0.003, ...],  # 日收益率列表
                "benchmark": "沪深300",
                "index_code": "000300"
            }
        """
        try:
            # ✅ 三进程架构：通过RPC客户端获取数据进程中的基准指数数据
            if self.data_client:
                try:
                    # 通过RPC调用数据进程的get_index_returns方法
                    result = self.data_client.call(
                        "get_index_returns",
                        index_code=index_code,
                        lookback_days=lookback_days,
                    )

                    if result and isinstance(result, dict) and result.get("success", False):
                        returns = result.get("returns", [])
                        index_name = result.get("index_name", f"指数{index_code}")

                        self.logger.info(f"✅ 通过RPC获取基准数据成功: {index_name}, {len(returns)}个数据点")
                        return {
                            "success": True,
                            "returns": returns,
                            "benchmark": index_name,
                            "index_code": index_code
                        }
                    else:
                        self.logger.warning(f"RPC调用失败: {result.get('message', '未知错误')}", extra={"log_type": "SYSTEM"})
                        return self._get_mock_benchmark_returns(lookback_days)
                except Exception as e:
                    self.logger.warning(f"RPC调用异常: {e}，使用模拟数据", extra={"log_type": "SYSTEM"}, exc_info=True)
                    return self._get_mock_benchmark_returns(lookback_days)
            else:
                # 降级：尝试从data_center_service获取（兼容模式）
                from backend.core.base import get_service_manager

                service_manager = get_service_manager()
                data_center = service_manager.get_service("data_center_service")

                if not data_center:
                    self.logger.warning("数据中心服务不可用，使用模拟数据", extra={"log_type": "SYSTEM"})
                    return self._get_mock_benchmark_returns(lookback_days)

            # 调用数据中心的指数收益率查询API
            result = data_center.get_index_returns(
                index_code=index_code, lookback_days=lookback_days
            )

            if result.get("success"):
                returns = result.get("returns", [])
                index_name = result.get("index_name", f"指数{index_code}")

                self.logger.info(f"✅ 获取基准数据成功: {index_name}, {len(returns)}个数据点")

                return {
                    "success": True,
                    "returns": returns,
                    "benchmark": index_name,
                    "index_code": index_code,
                }
            else:
                # 如果查询失败，降级到模拟数据
                self.logger.warning(f"查询指数数据失败: {result.get('message')}, 使用模拟数据", extra={"log_type": "SYSTEM"})
                return self._get_mock_benchmark_returns(lookback_days)

        except Exception as e:
            self.logger.warning(f"获取基准收益率失败: {e}, 使用模拟数据", extra={"log_type": "SYSTEM"})
            return self._get_mock_benchmark_returns(lookback_days)

    def _get_mock_benchmark_returns(self, lookback_days: int) -> Dict[str, Any]:
        """获取模拟基准收益率（降级方案）.

        Args:
            lookback_days: 回溯天数

        Returns:
            Dict: 模拟收益率数据
        """
        try:
            import numpy as np

            # 生成模拟基准收益率（正态分布）
            np.random.seed(42)
            returns = np.random.normal(0.0005, 0.015, lookback_days).tolist()

            return {
                "success": True,
                "returns": returns,
                "benchmark": "沪深300（模拟数据）",
                "is_mock": True,
            }

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _calculate_max_drawdown_duration(self, drawdown) -> int:
        """计算最大回撤持续天数.

        Args:
            drawdown: 回撤序列（numpy数组）

        Returns:
            int: 最大回撤持续天数
        """
        try:
            import numpy as np

            # 找到最大回撤的位置
            max_dd_idx = np.argmin(drawdown)

            # 从最大回撤点向前找到上一个峰值（回撤=0）
            start_idx = max_dd_idx
            for i in range(max_dd_idx - 1, -1, -1):
                if drawdown[i] >= 0:
                    start_idx = i
                    break

            duration = max_dd_idx - start_idx

            return max(int(duration), 0)

        except Exception as e:
            self.logger.warning(f"计算回撤持续时间失败: {e}", extra={"log_type": "SYSTEM"})
            return 0
