# -*- coding: utf-8 -*-
"""
VnPy集成服务.

提供VnPy主引擎的封装和管理功能。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from .base_service import BaseService

if TYPE_CHECKING:
    # VnPy相关导入（延迟导入以避免循环依赖）
    pass

logger = logging.getLogger(__name__)


class VnpyService(BaseService):
    """VnPy服务."""

    def __init__(self):
        """初始化VnPy服务."""
        super().__init__("VnPy")
        self._main_engine = None
        self._event_engine = None
        self._gateways: Dict[str, Any] = {}
        self._engines: Dict[str, Any] = {}
        self._chinastock_engine = None

    async def initialize(self) -> None:
        """初始化VnPy主引擎."""
        try:
            # 延迟导入VnPy模块
            # pylint: disable=import-outside-toplevel
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine

            self.logger.info("正在初始化VnPy主引擎...")

            # 创建事件引擎（不手动启动，让MainEngine自动启动）
            self._event_engine = EventEngine()

            # 创建主引擎（MainEngine会自动启动EventEngine）
            self._main_engine = MainEngine(self._event_engine)

            # 初始化各种引擎
            await self._initialize_engines()

            # MainEngine通过EventEngine自动启动，无需手动调用start()

            self.logger.info("VnPy主引擎初始化完成")
            self.is_initialized = True

        except ImportError as e:
            self.logger.error("VnPy模块导入失败: %s", e)
            raise RuntimeError(f"VnPy模块不可用: {e}") from e
        except Exception as e:
            self.logger.error("VnPy主引擎初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭VnPy主引擎."""
        try:
            self.logger.info("正在关闭VnPy主引擎...")

            if self._main_engine:
                # MainEngine.close()会关闭所有引擎和网关，并停止EventEngine
                self._main_engine.close()
                self._main_engine = None
                self._event_engine = None  # EventEngine已被MainEngine.close()停止

            self._gateways.clear()
            self._engines.clear()

            self.logger.info("VnPy主引擎关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("VnPy主引擎关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查VnPy服务健康状态."""
        try:
            status = {
                "main_engine_active": self._main_engine is not None,
                "event_engine_active": self._event_engine is not None,
                "gateways_count": len(self._gateways),
                "engines_count": len(self._engines),
                "active_gateways": [
                    name
                    for name, gateway in self._gateways.items()
                    if hasattr(gateway, "is_active") and gateway.is_active
                ],
                "timestamp": datetime.now().isoformat(),
            }

            # 检查主引擎状态
            if self._main_engine:
                status["main_engine_status"] = "active"
            else:
                status["main_engine_status"] = "inactive"

            # 检查事件引擎状态
            if self._event_engine:
                status["event_engine_status"] = "active"
            else:
                status["event_engine_status"] = "inactive"

            return status

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("VnPy健康检查失败: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _initialize_engines(self) -> None:
        """初始化各种引擎."""
        try:
            # 添加中国A股数据管理应用（data_module_vnpy）
            # pylint: disable=import-outside-toplevel
            from backend.infrastructure.data_module_vnpy import ChinaStockApp

            self.logger.info("正在加载中国A股数据管理应用...")
            self._chinastock_engine = self._main_engine.add_app(ChinaStockApp)
            self._engines["chinastock"] = self._chinastock_engine
            self.logger.info("中国A股数据管理应用已加载")

        except ImportError as e:
            self.logger.warning("data_module_vnpy模块不可用: %s", e)
            self._chinastock_engine = None
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("引擎初始化失败: %s", e)
            self._chinastock_engine = None
            raise

    def get_main_engine(self) -> Any:
        """获取主引擎实例."""
        if not self.is_initialized:
            raise RuntimeError("VnPy服务未初始化")
        return self._main_engine

    def get_event_engine(self) -> Any:
        """获取事件引擎实例."""
        if not self.is_initialized:
            raise RuntimeError("VnPy服务未初始化")
        return self._event_engine

    def get_engine(self, engine_name: str) -> Optional[Any]:
        """获取指定引擎."""
        return self._engines.get(engine_name)

    def get_all_engines(self) -> Dict[str, Any]:
        """获取所有引擎."""
        return self._engines.copy()

    def get_chinastock_engine(self) -> Optional[Any]:
        """获取中国A股数据管理引擎."""
        return self._chinastock_engine if hasattr(self, "_chinastock_engine") else None

    def get_gateway(self, gateway_name: str) -> Optional[Any]:
        """获取指定网关."""
        return self._gateways.get(gateway_name)

    def get_all_gateways(self) -> Dict[str, Any]:
        """获取所有网关."""
        return self._gateways.copy()

    async def add_gateway(
        self,
        gateway_class: Any,
        gateway_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """添加网关."""
        try:
            if not self.is_initialized or not self._main_engine:
                raise RuntimeError("VnPy服务未初始化")

            if config is None:
                config = {}

            # 通过主引擎添加网关
            self._main_engine.add_gateway(gateway_class, gateway_name)

            # 保存网关引用
            gateway = self._main_engine.get_gateway(gateway_name)
            if gateway:
                self._gateways[gateway_name] = gateway
                self.logger.info("网关添加成功: %s", gateway_name)
                return True
            else:
                self.logger.error("网关添加失败: %s", gateway_name)
                return False

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("添加网关失败: %s - %s", gateway_name, e)
            return False

    async def connect_gateway(
        self, gateway_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """连接网关."""
        try:
            if not self.is_initialized or not self._main_engine:
                raise RuntimeError("VnPy服务未初始化")

            gateway = self.get_gateway(gateway_name)
            if not gateway:
                self.logger.error("网关不存在: %s", gateway_name)
                return False

            if config is None:
                config = {}

            # 连接网关
            self._main_engine.connect(config, gateway_name)
            self.logger.info("网关连接成功: %s", gateway_name)
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("连接网关失败: %s - %s", gateway_name, e)
            return False

    async def disconnect_gateway(self, gateway_name: str) -> bool:
        """断开网关连接."""
        try:
            if not self.is_initialized:
                raise RuntimeError("VnPy服务未初始化")

            gateway = self.get_gateway(gateway_name)
            if not gateway:
                self.logger.error("网关不存在: %s", gateway_name)
                return False

            # 断开网关连接 - 调用gateway的close方法
            gateway.close()
            self.logger.info("网关断开成功: %s", gateway_name)
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("断开网关失败: %s - %s", gateway_name, e)
            return False

    def get_symbols(self) -> List[Dict[str, Any]]:
        """从data_module_vnpy获取品种列表."""
        try:
            # 优先从data_module_vnpy获取品种列表
            chinastock_engine = self.get_chinastock_engine()
            if chinastock_engine:
                self.logger.debug("从data_module_vnpy获取品种列表...")
                stocks_dict = chinastock_engine.refresh_stock_list()

                if stocks_dict and isinstance(stocks_dict, dict):
                    # 转换为统一格式
                    symbols = []
                    for market_type, stock_codes in stocks_dict.items():
                        if not isinstance(stock_codes, list):
                            continue

                        for code in stock_codes:
                            # 根据代码判断交易所
                            if code.startswith(("6", "688")):
                                exchange = "SSE"  # 上海证券交易所
                            elif code.startswith(("0", "1", "2", "3")):
                                exchange = "SZSE"  # 深圳证券交易所
                            else:
                                exchange = "SSE"  # 默认上海

                            symbols.append(
                                {
                                    "symbol": code,
                                    "exchange": exchange,
                                    "name": code,  # 简化，使用代码作为名称
                                    "product": market_type,
                                    "size": 100,
                                    "pricetick": 0.01,
                                }
                            )

                    if symbols:
                        self.logger.info("从data_module_vnpy获取品种列表: %d 个品种", len(symbols))
                        return symbols

            # 如果data_module_vnpy不可用，尝试从网关获取（兼容旧逻辑）
            if not self.is_initialized:
                return []

            symbols = []
            for gateway_name, gateway in self._gateways.items():
                if hasattr(gateway, "get_all_contracts"):
                    contracts = gateway.get_all_contracts()
                    for contract in contracts:
                        symbols.append(
                            {
                                "symbol": contract.symbol,
                                "exchange": contract.exchange,
                                "name": getattr(contract, "name", contract.symbol),
                                "product": getattr(contract, "product", ""),
                                "size": getattr(contract, "size", 1),
                                "pricetick": getattr(contract, "pricetick", 0.01),
                                "gateway": gateway_name,
                            }
                        )

            return symbols

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取品种信息失败: %s", e)
            return []

    def get_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账户信息."""
        try:
            if not self.is_initialized:
                return []

            accounts = []
            for gateway_name, gateway in self._gateways.items():
                if hasattr(gateway, "get_all_accounts"):
                    gateway_accounts = gateway.get_all_accounts()
                    for account in gateway_accounts:
                        accounts.append(
                            {
                                "account_id": account.accountid,
                                "gateway": gateway_name,
                                "balance": account.balance,
                                "available": account.available,
                                "frozen": account.balance - account.available,
                                "commission": account.commission,
                                "margin": account.margin,
                            }
                        )

            return accounts

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取账户信息失败: %s", e)
            return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓信息."""
        try:
            if not self.is_initialized:
                return []

            positions = []
            for gateway_name, gateway in self._gateways.items():
                if hasattr(gateway, "get_all_positions"):
                    gateway_positions = gateway.get_all_positions()
                    for position in gateway_positions:
                        positions.append(
                            {
                                "symbol": position.symbol,
                                "exchange": position.exchange,
                                "direction": position.direction,
                                "volume": position.volume,
                                "frozen": position.frozen,
                                "price": position.price,
                                "pnl": position.pnl,
                                "gateway": gateway_name,
                            }
                        )

            return positions

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取持仓信息失败: %s", e)
            return []

    def get_orders(self) -> List[Dict[str, Any]]:
        """获取所有订单信息."""
        try:
            if not self.is_initialized:
                return []

            orders = []
            for gateway_name, gateway in self._gateways.items():
                if hasattr(gateway, "get_all_orders"):
                    gateway_orders = gateway.get_all_orders()
                    for order in gateway_orders:
                        orders.append(
                            {
                                "order_id": order.orderid,
                                "symbol": order.symbol,
                                "exchange": order.exchange,
                                "type": order.type,
                                "direction": order.direction,
                                "price": order.price,
                                "volume": order.volume,
                                "traded": order.traded,
                                "status": order.status,
                                "gateway": gateway_name,
                            }
                        )

            return orders

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取订单信息失败: %s", e)
            return []

    def get_trades(self) -> List[Dict[str, Any]]:
        """获取所有成交信息."""
        try:
            if not self.is_initialized:
                return []

            trades = []
            for gateway_name, gateway in self._gateways.items():
                if hasattr(gateway, "get_all_trades"):
                    gateway_trades = gateway.get_all_trades()
                    for trade in gateway_trades:
                        trades.append(
                            {
                                "trade_id": trade.tradeid,
                                "order_id": trade.orderid,
                                "symbol": trade.symbol,
                                "exchange": trade.exchange,
                                "direction": trade.direction,
                                "price": trade.price,
                                "volume": trade.volume,
                                "time": trade.time,
                                "gateway": gateway_name,
                            }
                        )

            return trades

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取成交信息失败: %s", e)
            return []

    def get_historical_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = "1m",
        limit: int = 1000,
    ) -> List[Any]:
        """获取历史数据."""
        try:
            if not self.is_initialized:
                self.logger.warning("VnPy服务未初始化，返回空数据")
                return []

            # 导入VnPy数据类型
            # pylint: disable=import-outside-toplevel
            from vnpy.trader.constant import Interval
            from vnpy.trader.object import HistoryRequest

            # 转换频率字符串到VnPy Interval
            interval_mapping = {
                "1m": Interval.MINUTE,
                "5m": Interval.MINUTE,  # 使用MINUTE，后续通过参数控制
                "15m": Interval.MINUTE,
                "30m": Interval.MINUTE,
                "1h": Interval.HOUR,
                "1d": Interval.DAILY,
                "1w": Interval.WEEKLY,
            }
            interval = interval_mapping.get(frequency, Interval.MINUTE)

            # 导入Exchange枚举类型
            # pylint: disable=import-outside-toplevel
            from vnpy.trader.constant import Exchange as ExchangeEnum

            # 转换exchange字符串为Exchange枚举
            try:
                exchange_enum = ExchangeEnum[exchange.upper()]
            except (KeyError, AttributeError):
                self.logger.warning("无效的交易所代码: %s", exchange)
                return []

            # 创建历史数据请求
            req = HistoryRequest(
                symbol=symbol,
                exchange=exchange_enum,
                interval=interval,
                start=start_date if start_date else datetime.now(),
                end=end_date if end_date else datetime.now(),
            )

            # 从主引擎查询历史数据
            # 注意：需要先连接数据网关才能查询历史数据
            try:
                # 尝试通过主引擎查询历史数据
                # VnPy的query_history通常需要通过具体的gateway或data service
                bars = []

                # 如果有可用的网关，尝试从网关获取数据
                for _gateway_name, gateway in self._gateways.items():
                    if hasattr(gateway, "query_history"):
                        bars = gateway.query_history(req)
                        if bars:
                            break

                # 限制返回数量
                if bars and len(bars) > limit:
                    bars = bars[-limit:]

                return bars if bars else []
            except AttributeError:
                self.logger.warning("没有可用的历史数据查询接口")
                return []

        except ImportError as e:
            self.logger.error("导入VnPy模块失败: %s", e)
            return []
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取历史数据失败: %s", e)
            return []

    def get_symbol_info(self, symbol: str, exchange: str) -> Optional[Any]:
        """获取品种信息."""
        try:
            if not self.is_initialized or not self._main_engine:
                self.logger.warning("VnPy服务未初始化")
                return None

            # 从主引擎获取合约信息
            # pylint: disable=import-outside-toplevel
            from vnpy.trader.constant import Exchange

            # 转换交易所字符串
            try:
                exchange_enum = Exchange[exchange.upper()]
            except KeyError:
                self.logger.warning("无效的交易所代码: %s", exchange)
                return None

            # 获取合约信息
            contract = self._main_engine.get_contract(f"{symbol}.{exchange_enum.value}")

            return contract

        except ImportError as e:
            self.logger.error("导入VnPy模块失败: %s", e)
            return None
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取品种信息失败: %s", e)
            return None

    def get_latest_tick(self, symbol: str, exchange: str) -> Optional[Any]:
        """获取最新Tick数据."""
        try:
            if not self.is_initialized or not self._main_engine:
                self.logger.warning("VnPy服务未初始化")
                return None

            # pylint: disable=import-outside-toplevel
            from vnpy.trader.constant import Exchange

            # 转换交易所字符串
            try:
                exchange_enum = Exchange[exchange.upper()]
            except KeyError:
                self.logger.warning("无效的交易所代码: %s", exchange)
                return None

            # 从主引擎获取最新tick
            tick = self._main_engine.get_tick(f"{symbol}.{exchange_enum.value}")

            return tick

        except ImportError as e:
            self.logger.error("导入VnPy模块失败: %s", e)
            return None
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取最新Tick数据失败: %s", e)
            return None

    def get_latest_bar(self, symbol: str, exchange: str, frequency: str = "1m") -> Optional[Any]:
        """获取最新K线数据."""
        try:
            if not self.is_initialized:
                self.logger.warning("VnPy服务未初始化")
                return None

            # 获取最近的历史数据
            bars = self.get_historical_data(
                symbol=symbol, exchange=exchange, frequency=frequency, limit=1
            )

            if bars and len(bars) > 0:
                return bars[-1]

            return None

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("获取最新K线数据失败: %s", e)
            return None


# 导出公共接口
__all__ = ["VnpyService"]
