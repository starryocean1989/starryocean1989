# -*- coding: utf-8 -*-
"""
VNPY适配器 - 统一接口适配器.

提供统一的VNPY接口，支持数据获取、交易、风控等功能。
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# 尝试导入VnPy相关模块
try:
    from vnpy.trader.database import get_database, BaseDatabase
    from vnpy.trader.object import BarData, TickData
    from vnpy.trader.constant import Exchange, Interval  # type: ignore[assignment]

    VNPY_AVAILABLE = True
except ImportError as e:
    logger.error("VnPy模块导入失败: %s", e)
    VNPY_AVAILABLE = False
    BaseDatabase = None  # type: ignore
    BarData = None  # type: ignore
    TickData = None  # type: ignore

    # 创建存根枚举类（确保类型安全）
    class Exchange(Enum):
        """交易所枚举（存根）."""

        SSE = "SSE"  # 上交所
        SZSE = "SZSE"  # 深交所
        BSE = "BSE"  # 北交所
        CFFEX = "CFFEX"  # 中金所
        DCE = "DCE"  # 大商所
        CZCE = "CZCE"  # 郑商所
        SHFE = "SHFE"  # 上期所

    class Interval(Enum):
        """时间周期枚举（存根）."""

        MINUTE = "1m"
        HOUR = "1h"
        DAILY = "d"
        WEEKLY = "w"
        TICK = "tick"


class VnPyAdapter:
    """VNPY适配器主类."""

    def __init__(self):
        """初始化VNPY适配器."""
        if not VNPY_AVAILABLE:
            raise ImportError("VnPy未安装或配置错误，请先安装VnPy: pip install vnpy")

        self.database: Any = None  # BaseDatabase类型，使用Any避免条件导入的类型问题
        self.connected = False
        self.gateways: List[str] = []
        self.positions: Dict[str, Any] = {}
        self.account_info: Dict[str, Any] = {}

        # 集成TerminalEngine（延迟导入避免循环依赖）
        self.terminal_engine = None

        # 连接VNPY
        self._connect()

    def _connect(self):
        """连接VNPY系统."""
        try:
            # 获取VnPy数据库实例
            self.database = get_database()
            if not self.database:
                raise ConnectionError("无法获取VnPy数据库实例")

            # 获取TerminalEngine实例
            try:
                from backend.core.vnpy_integration import get_terminal_engine

                self.terminal_engine = get_terminal_engine()
                logger.info("TerminalEngine集成成功")
            except Exception as e:
                logger.warning("TerminalEngine集成失败（部分功能不可用）: %s", e)
                self.terminal_engine = None

            self.connected = True
            logger.info("VNPY适配器连接成功")
        except Exception as e:
            logger.error("VNPY连接失败: %s", e)
            raise ConnectionError(f"VNPY连接失败: {e}") from e

    def get_kline_data(self, symbol: str, period: str, limit: int = 200) -> List[Dict[str, Any]]:
        """获取K线数据.

        Args:
            symbol: 品种代码
            period: 周期类型
            limit: 数据数量限制

        Returns:
            K线数据列表

        Raises:
            RuntimeError: 服务未连接
            ValueError: 参数错误
        """
        if not self.connected or not self.database:
            raise RuntimeError("VnPy服务未连接")

        if not VNPY_AVAILABLE:
            raise RuntimeError("VnPy不可用，无法获取K线数据")

        # 映射周期类型
        interval_map = {
            "日K": Interval.DAILY,
            "周K": Interval.WEEKLY,
            "月K": Interval.DAILY,  # VnPy没有MONTHLY，使用DAILY
            "5分钟": Interval.MINUTE,  # VnPy使用MINUTE表示分钟级别
            "15分钟": Interval.MINUTE,
            "30分钟": Interval.MINUTE,
            "1小时": Interval.HOUR,
        }

        interval = interval_map.get(period, Interval.DAILY)

        # 解析品种代码和交易所
        # 假设格式为 "代码" 或 "代码.交易所"
        if "." in symbol:
            symbol_code, exchange_str = symbol.split(".", 1)
            exchange = Exchange(exchange_str)
        else:
            symbol_code = symbol
            # 根据代码前缀推断交易所
            exchange = self._infer_exchange(symbol_code)

        try:
            # 从VnPy数据库获取K线数据
            bars: List[Any] = (
                self.database.load_bar_data(  # BarData类型，使用Any避免条件导入的类型问题
                    symbol=symbol_code,
                    exchange=exchange,
                    interval=interval,
                    start=None,  # 获取最新limit条数据
                    end=datetime.now(),
                )
            )

            if not bars:
                raise ValueError(f"未找到品种 {symbol} 的K线数据")

            # 转换为字典格式
            result = []
            for bar_data in bars[-limit:]:  # 只取最近limit条
                result.append(
                    {
                        "datetime": bar_data.datetime,
                        "open": bar_data.open_price,
                        "high": bar_data.high_price,
                        "low": bar_data.low_price,
                        "close": bar_data.close_price,
                        "volume": bar_data.volume,
                    }
                )

            logger.info("从VnPy获取K线数据: %s, %d条", symbol, len(result))
            return result

        except Exception as e:
            logger.error("获取K线数据失败: %s", e)
            raise

    def _infer_exchange(self, symbol: str) -> Exchange:
        """根据品种代码推断交易所."""
        # 股票代码规则
        if symbol.startswith("6"):
            return Exchange.SSE  # 上交所
        elif symbol.startswith(("0", "3")):
            return Exchange.SZSE  # 深交所
        elif symbol.startswith("8"):
            return Exchange.BSE  # 北交所
        # 期货代码规则
        elif symbol and symbol[0].isupper():
            first_char = symbol[0]
            if first_char in ["I", "T"]:
                return Exchange.CFFEX  # 中金所
            elif first_char in ["A", "B", "C", "J", "M", "P", "Y"]:
                return Exchange.DCE  # 大商所
            elif first_char in ["S", "T", "C", "F", "R", "M", "O"]:
                return Exchange.CZCE  # 郑商所
            else:
                return Exchange.SHFE  # 上期所
        else:
            # 默认返回上交所
            return Exchange.SSE

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态.

        Returns:
            系统状态字典

        Raises:
            RuntimeError: 服务未连接
        """
        if not self.connected:
            raise RuntimeError("VnPy服务未连接")

        # 如果有TerminalEngine，获取其状态
        terminal_status = {}
        if self.terminal_engine:
            try:
                terminal_status = self.terminal_engine.get_status()
            except Exception as e:
                logger.error("获取TerminalEngine状态失败: %s", e)

        return {
            "connected": self.connected,
            "gateways": self.gateways,
            "vnpy_available": VNPY_AVAILABLE,
            "real_time_worker_running": terminal_status.get("event_engine_running", False),
            "connected_gateways": self.gateways if self.connected else [],
            "database_connected": self.database is not None,
            "terminal_engine_status": terminal_status,
        }

    def get_positions(self, gateway_name: str) -> List[Dict[str, Any]]:
        """获取持仓信息.

        Args:
            gateway_name: 网关名称

        Returns:
            持仓信息列表

        Raises:
            RuntimeError: 服务未连接
            NotImplementedError: TerminalEngine不可用
        """
        if not self.connected:
            raise RuntimeError("VnPy服务未连接")

        if not self.terminal_engine:
            logger.error("TerminalEngine未初始化，无法获取持仓信息")
            raise NotImplementedError("TerminalEngine未初始化，持仓查询功能不可用")

        try:
            # 通过TerminalEngine获取持仓
            positions_dict = self.terminal_engine.get_positions(gateway_name)

            # 转换为列表格式
            positions_list = []
            for symbol, position in positions_dict.items():
                position_info = {
                    "symbol": getattr(position, "symbol", symbol),
                    "exchange": (
                        position.exchange.value
                        if hasattr(position, "exchange") and hasattr(position.exchange, "value")
                        else str(getattr(position, "exchange", ""))
                    ),
                    "direction": (
                        position.direction.value
                        if hasattr(position, "direction") and hasattr(position.direction, "value")
                        else str(getattr(position, "direction", ""))
                    ),
                    "volume": getattr(position, "volume", 0),
                    "frozen": getattr(position, "frozen", 0),
                    "price": getattr(position, "price", 0.0),
                    "pnl": getattr(position, "pnl", 0.0),
                    "yd_volume": getattr(position, "yd_volume", 0),
                }
                positions_list.append(position_info)

            logger.info("获取持仓信息成功: %s, %d条", gateway_name, len(positions_list))
            return positions_list

        except Exception as e:
            logger.error("获取持仓信息失败: %s", e)
            raise

    def get_account_info(self, gateway_name: str) -> Dict[str, Any]:
        """获取账户信息.

        Args:
            gateway_name: 网关名称

        Returns:
            账户信息字典

        Raises:
            RuntimeError: 服务未连接
            NotImplementedError: TerminalEngine不可用
        """
        if not self.connected:
            raise RuntimeError("VnPy服务未连接")

        if not self.terminal_engine:
            logger.error("TerminalEngine未初始化，无法获取账户信息")
            raise NotImplementedError("TerminalEngine未初始化，账户查询功能不可用")

        try:
            # 通过TerminalEngine获取账户信息
            account_dict = self.terminal_engine.get_account_info(gateway_name)

            # 转换为统一格式
            # 如果返回的是嵌套字典，提取对应网关的账户信息
            if isinstance(account_dict, dict) and gateway_name in account_dict:
                account = account_dict[gateway_name]
            else:
                account = account_dict

            # 统一转换为字典格式
            if hasattr(account, "__dict__"):
                # 如果是对象，转换属性
                result = {
                    "accountid": getattr(account, "accountid", gateway_name),
                    "balance": getattr(account, "balance", 0.0),
                    "available": getattr(account, "available", 0.0),
                    "commission": getattr(account, "commission", 0.0),
                    "margin": getattr(account, "margin", 0.0),
                    "close_profit": getattr(account, "close_profit", 0.0),
                    "position_profit": getattr(account, "position_profit", 0.0),
                }
            elif isinstance(account, dict):
                # 如果已经是字典，直接使用
                result = {
                    "accountid": account.get("accountid", gateway_name),
                    "balance": account.get("balance", 0.0),
                    "available": account.get("available", 0.0),
                    "commission": account.get("commission", 0.0),
                    "margin": account.get("margin", 0.0),
                    "close_profit": account.get("close_profit", 0.0),
                    "position_profit": account.get("position_profit", 0.0),
                }
            else:
                # 未知类型，返回默认值
                result = {
                    "accountid": gateway_name,
                    "balance": 0.0,
                    "available": 0.0,
                    "commission": 0.0,
                    "margin": 0.0,
                    "close_profit": 0.0,
                    "position_profit": 0.0,
                }

            logger.info("获取账户信息成功: %s", gateway_name)
            return result

        except Exception as e:
            logger.error("获取账户信息失败: %s", e)
            raise

    def switch_data_source(self, source_name: str) -> bool:
        """切换数据源.

        Args:
            source_name: 数据源名称

        Returns:
            是否切换成功
        """
        try:
            logger.info("切换数据源到: %s", source_name)

            if not self.terminal_engine:
                logger.warning("TerminalEngine未初始化，使用默认数据源")
                return True

            # 通过TerminalEngine切换数据源
            # 检查数据源是否已注册
            if source_name in self.terminal_engine.datafeeds:
                # 数据源已存在，标记为活跃
                logger.info("数据源 %s 已注册并激活", source_name)
                return True
            else:
                logger.warning("数据源 %s 未注册，切换失败", source_name)
                return False

        except Exception as e:
            logger.error("切换数据源失败: %s", e)
            return False

    def connect_gateway(
        self, gateway_name: Union[str, Dict[str, Any]], config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """连接交易网关.

        Args:
            gateway_name: 网关名称（可以是字符串或包含name字段的配置字典）
            config: 网关配置参数

        Returns:
            是否连接成功
        """
        # 兼容传入字典的情况
        gateway_name_str: str
        if isinstance(gateway_name, dict):
            config = gateway_name
            gateway_name_str = config.get("name", "")
        else:
            gateway_name_str = gateway_name

        try:
            logger.info("连接网关: %s, 配置: %s", gateway_name_str, config)

            if not self.terminal_engine:
                logger.warning("TerminalEngine未初始化，网关连接功能受限")
                # 暂时添加到网关列表以允许UI继续运行
                if gateway_name_str and gateway_name_str not in self.gateways:
                    self.gateways.append(gateway_name_str)
                return True

            # 通过TerminalEngine连接网关
            result = self.terminal_engine.connect_gateway(gateway_name_str, **(config or {}))

            if result:
                # 连接成功，添加到网关列表
                if gateway_name_str and gateway_name_str not in self.gateways:
                    self.gateways.append(gateway_name_str)
                logger.info("网关 %s 连接成功", gateway_name_str)
            else:
                logger.error("网关 %s 连接失败", gateway_name_str)

            return result

        except Exception as e:
            logger.error("连接网关失败: %s", e)
            return False

    def get_strategies(self) -> List[Dict[str, Any]]:
        """获取策略列表.

        Returns:
            策略信息列表
        """
        try:
            logger.info("获取策略列表")

            if not self.terminal_engine:
                logger.warning("TerminalEngine未初始化，返回空策略列表")
                return []

            # 通过TerminalEngine获取策略列表
            strategies = self.terminal_engine.get_strategies()

            logger.info("获取策略列表成功: %d个策略", len(strategies))
            return strategies

        except Exception as e:
            logger.error("获取策略列表失败: %s", e)
            return []


# 创建全局实例
try:
    VNPY_ADAPTER = VnPyAdapter()
except (ImportError, ConnectionError) as e:
    logger.error("VnPy适配器初始化失败: %s", e)
    VNPY_ADAPTER = None

# 向后兼容：保留小写别名
vnpy_adapter = VNPY_ADAPTER
