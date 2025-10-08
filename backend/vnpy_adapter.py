# -*- coding: utf-8 -*-
"""
VNPY适配器 - 统一接口适配器.

提供统一的VNPY接口，支持数据获取、交易、风控等功能。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 尝试导入VnPy相关模块
try:
    from vnpy.trader.database import get_database, BaseDatabase
    from vnpy.trader.object import BarData, TickData
    from vnpy.trader.constant import Exchange, Interval

    VNPY_AVAILABLE = True
except ImportError as e:
    logger.error("VnPy模块导入失败: %s", e)
    VNPY_AVAILABLE = False
    BaseDatabase = None
    BarData = None
    TickData = None
    Exchange = None
    Interval = None


class VnPyAdapter:
    """VNPY适配器主类."""

    def __init__(self):
        """初始化VNPY适配器."""
        if not VNPY_AVAILABLE:
            raise ImportError("VnPy未安装或配置错误，请先安装VnPy: pip install vnpy")

        self.database: Optional[BaseDatabase] = None
        self.connected = False
        self.gateways = []
        self.positions = {}
        self.account_info = {}

        # 连接VNPY
        self._connect()

    def _connect(self):
        """连接VNPY系统."""
        try:
            # 获取VnPy数据库实例
            self.database = get_database()
            if not self.database:
                raise ConnectionError("无法获取VnPy数据库实例")

            self.connected = True
            logger.info("VNPY适配器连接成功")
        except Exception as e:
            logger.error("VNPY连接失败: %s", e)
            raise ConnectionError(f"VNPY连接失败: {e}")

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

        # 映射周期类型
        interval_map = {
            "日K": Interval.DAILY,
            "周K": Interval.WEEKLY,
            "月K": Interval.MONTHLY,
            "5分钟": Interval.MINUTE_5,
            "15分钟": Interval.MINUTE_15,
            "30分钟": Interval.MINUTE_30,
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
            bars: List[BarData] = self.database.load_bar_data(
                symbol=symbol_code,
                exchange=exchange,
                interval=interval,
                start=None,  # 获取最新limit条数据
                end=datetime.now(),
            )

            if not bars:
                raise ValueError(f"未找到品种 {symbol} 的K线数据")

            # 转换为字典格式
            result = []
            for bar in bars[-limit:]:  # 只取最近limit条
                result.append(
                    {
                        "datetime": bar.datetime,
                        "open": bar.open_price,
                        "high": bar.high_price,
                        "low": bar.low_price,
                        "close": bar.close_price,
                        "volume": bar.volume,
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
        elif symbol[0].isupper():
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

        return {
            "connected": self.connected,
            "gateways": self.gateways,
            "vnpy_available": VNPY_AVAILABLE,
            "real_time_worker_running": False,
            "connected_gateways": self.gateways if self.connected else [],
            "database_connected": self.database is not None,
        }

    def get_positions(self, gateway_name: str) -> List[Dict[str, Any]]:
        """获取持仓信息.

        Args:
            gateway_name: 网关名称

        Returns:
            持仓信息列表

        Raises:
            RuntimeError: 服务未连接
        """
        if not self.connected:
            raise RuntimeError("VnPy服务未连接")

        # TODO: 实现真实的持仓查询逻辑
        # 需要通过VnPy的gateway接口获取实时持仓
        logger.warning("get_positions需要实现真实的持仓查询逻辑")
        raise NotImplementedError("持仓查询功能待实现，需要配置VnPy网关")

    def get_account_info(self, gateway_name: str) -> Dict[str, Any]:
        """获取账户信息.

        Args:
            gateway_name: 网关名称

        Returns:
            账户信息字典

        Raises:
            RuntimeError: 服务未连接
        """
        if not self.connected:
            raise RuntimeError("VnPy服务未连接")

        # TODO: 实现真实的账户查询逻辑
        # 需要通过VnPy的gateway接口获取实时账户信息
        logger.warning("get_account_info需要实现真实的账户查询逻辑")
        raise NotImplementedError("账户查询功能待实现，需要配置VnPy网关")

    def switch_data_source(self, source_name: str) -> bool:
        """切换数据源.

        Args:
            source_name: 数据源名称

        Returns:
            是否切换成功
        """
        logger.info("切换数据源到: %s", source_name)
        # TODO: 实现数据源切换逻辑
        return True


# 创建全局实例
try:
    vnpy_adapter = VnPyAdapter()
except (ImportError, ConnectionError) as e:
    logger.error("VnPy适配器初始化失败: %s", e)
    vnpy_adapter = None
