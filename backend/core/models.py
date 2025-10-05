# -*- coding: utf-8 -*-
"""
统一数据模型模块.

使用VNPY标准数据对象，避免重复定义。
"""

import logging  # Standard library import
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# 导入统一导入模块
from .imports import pd


class DataCategory(Enum):
    """数据类别枚举."""

    MARKET_DATA = "market_data"      # 行情数据
    TRANSACTION_DATA = "transaction_data"  # 交易数据
    PORTFOLIO_DATA = "portfolio_data"      # 组合数据
    RISK_DATA = "risk_data"          # 风险数据
    SYSTEM_DATA = "system_data"      # 系统数据


class DataSource(Enum):
    """数据源枚举."""

    VNPY = "vnpy"
    TUSHARE = "tushare"
    RQDATA = "rqdata"
    LOCAL_DB = "local_db"
    REAL_TIME = "real_time"
    HISTORICAL = "historical"


@dataclass
class DataMetadata:  # pylint: disable=too-many-instance-attributes
    """数据元数据."""

    category: DataCategory
    source: DataSource
    symbol: str = ""
    exchange: str = ""
    frequency: str = "1m"  # 数据频率，如：1m, 5m, 1d
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    count: int = 0
    quality_score: float = 1.0
    last_updated: Optional[datetime] = None
    tags: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedMarketData:  # pylint: disable=too-many-instance-attributes
    """统一行情数据模型."""

    # 基础信息
    symbol: str
    exchange: str
    data_type: str  # tick, bar, quote

    # 时间信息
    datetime: datetime
    timestamp: int

    # 价格数据
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    pre_close: float = 0.0

    # 成交数据
    volume: int = 0
    turnover: float = 0.0
    open_interest: int = 0

    # 买卖报价（用于tick数据）
    bid_price: float = 0.0
    bid_volume: int = 0
    ask_price: float = 0.0
    ask_volume: int = 0

    # 元数据
    metadata: DataMetadata = field(default_factory=lambda: DataMetadata(
        DataCategory.MARKET_DATA, DataSource.VNPY
    ))

    @classmethod
    def from_vnpy_tick(cls, tick: Any) -> 'UnifiedMarketData':
        """从VNPY TickData创建统一数据."""
        return cls(
            symbol=tick.symbol,
            exchange=tick.exchange if hasattr(tick, 'exchange') else "",
            data_type="tick",
            datetime=tick.datetime,
            timestamp=int(tick.datetime.timestamp()) if tick.datetime else 0,
            open_price=tick.open_price,
            high_price=tick.high_price,
            low_price=tick.low_price,
            close_price=tick.last_price,
            pre_close=tick.pre_close,
            volume=tick.volume,
            turnover=tick.turnover,
            open_interest=tick.open_interest,
            bid_price=tick.bid_price_1,
            bid_volume=tick.bid_volume_1,
            ask_price=tick.ask_price_1,
            ask_volume=tick.ask_volume_1,
            metadata=DataMetadata(
                DataCategory.MARKET_DATA,
                DataSource.VNPY,
                symbol=tick.symbol,
                exchange=tick.exchange if hasattr(tick, 'exchange') else "",
                count=1,
                last_updated=tick.datetime
            )
        )

    @classmethod
    def from_vnpy_bar(cls, bar_data: Any) -> 'UnifiedMarketData':
        """从VNPY BarData创建统一数据."""
        return cls(
            symbol=bar_data.symbol,
            exchange=bar_data.exchange,
            data_type="bar",
            datetime=bar_data.datetime,
            timestamp=(int(bar_data.datetime.timestamp())
                       if bar_data.datetime else 0),
            open_price=bar_data.open_price,
            high_price=bar_data.high_price,
            low_price=bar_data.low_price,
            close_price=bar_data.close_price,
            pre_close=0.0,  # BarData中没有pre_close
            volume=bar_data.volume,
            turnover=bar_data.turnover,
            open_interest=bar_data.open_interest,
            metadata=DataMetadata(
                DataCategory.MARKET_DATA,
                DataSource.VNPY,
                symbol=bar_data.symbol,
                exchange=bar_data.exchange,
                frequency=(f"{bar_data.interval}m"
                           if bar_data.interval else "1m"),
                count=1,
                last_updated=bar_data.datetime
            )
        )

    def to_pandas_row(self) -> Dict[str, Any]:
        """转换为pandas行数据."""
        return {
            'symbol': self.symbol,
            'exchange': self.exchange,
            'data_type': self.data_type,
            'datetime': self.datetime,
            'timestamp': self.timestamp,
            'open_price': self.open_price,
            'high_price': self.high_price,
            'low_price': self.low_price,
            'close_price': self.close_price,
            'pre_close': self.pre_close,
            'volume': self.volume,
            'turnover': self.turnover,
            'open_interest': self.open_interest,
            'bid_price': self.bid_price,
            'bid_volume': self.bid_volume,
            'ask_price': self.ask_price,
            'ask_volume': self.ask_volume
        }


@dataclass
class UnifiedOrder:  # pylint: disable=too-many-instance-attributes
    """统一订单数据模型."""

    # 基础信息
    order_id: str
    symbol: str
    exchange: str
    order_type: str  # market, limit, stop
    direction: str   # long, short

    # 价格和数量
    price: float
    volume: int

    # 状态信息
    status: str  # submitted, partial, filled, cancelled, rejected
    order_time: datetime
    traded_volume: int = 0

    # 元数据
    metadata: DataMetadata = field(default_factory=lambda: DataMetadata(
        DataCategory.TRANSACTION_DATA, DataSource.VNPY
    ))

    @classmethod
    def from_vnpy_order(cls, order: Any) -> 'UnifiedOrder':
        """从VNPY OrderData创建统一订单."""
        return cls(
            order_id=(order.orderid if hasattr(order, 'orderid')
                      else str(id(order))),
            symbol=order.symbol,
            exchange=order.exchange,
            order_type=order.type,
            direction=order.direction,
            price=order.price,
            volume=order.volume,
            traded_volume=order.traded,
            status=order.status,
            order_time=(datetime.strptime(order.time, "%H:%M:%S")
                        if order.time else datetime.now()),
            metadata=DataMetadata(
                DataCategory.TRANSACTION_DATA,
                DataSource.VNPY,
                symbol=order.symbol,
                exchange=order.exchange,
                count=1,
                last_updated=datetime.now()
            )
        )


@dataclass
class UnifiedTrade:  # pylint: disable=too-many-instance-attributes
    """统一成交数据模型."""

    # 基础信息
    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    direction: str

    # 成交信息
    price: float
    volume: int
    trade_time: datetime

    # 元数据
    metadata: DataMetadata = field(default_factory=lambda: DataMetadata(
        DataCategory.TRANSACTION_DATA, DataSource.VNPY
    ))

    @classmethod
    def from_vnpy_trade(cls, trade: Any) -> 'UnifiedTrade':
        """从VNPY TradeData创建统一成交."""
        return cls(
            trade_id=(trade.tradeid if hasattr(trade, 'tradeid')
                      else str(id(trade))),
            order_id="",  # TradeData中没有order_id
            symbol=trade.symbol,
            exchange=trade.exchange,
            direction=trade.direction,
            price=trade.price,
            volume=trade.volume,
            trade_time=(datetime.strptime(trade.time, "%H:%M:%S")
                        if trade.time else datetime.now()),
            metadata=DataMetadata(
                DataCategory.TRANSACTION_DATA,
                DataSource.VNPY,
                symbol=trade.symbol,
                exchange=trade.exchange,
                count=1,
                last_updated=datetime.now()
            )
        )


@dataclass
class UnifiedPosition:  # pylint: disable=too-many-instance-attributes
    """统一持仓数据模型."""

    # 基础信息
    symbol: str
    exchange: str
    direction: str  # long, short

    # 持仓信息
    volume: int
    frozen_volume: int
    available_volume: int
    cost_price: float
    market_price: float

    # 盈亏信息
    unrealized_pnl: float
    realized_pnl: float

    # 元数据
    metadata: DataMetadata = field(default_factory=lambda: DataMetadata(
        DataCategory.PORTFOLIO_DATA, DataSource.VNPY
    ))

    @classmethod
    def from_vnpy_position(cls, position: Any) -> 'UnifiedPosition':
        """从VNPY PositionData创建统一持仓."""
        return cls(
            symbol=position.symbol,
            exchange=position.exchange,
            direction=position.direction,
            volume=position.volume,
            frozen_volume=position.frozen,
            available_volume=max(0, position.volume - position.frozen),
            cost_price=position.price,
            market_price=0.0,  # 需要外部提供
            unrealized_pnl=position.pnl,
            realized_pnl=0.0,  # 需要外部计算
            metadata=DataMetadata(
                DataCategory.PORTFOLIO_DATA,
                DataSource.VNPY,
                symbol=position.symbol,
                exchange=position.exchange,
                count=1,
                last_updated=datetime.now()
            )
        )


@dataclass
class UnifiedAccount:  # pylint: disable=too-many-instance-attributes
    """统一账户数据模型."""

    # 基础信息
    account_id: str
    account_type: str  # stock, future, option

    # 资金信息
    balance: float
    available: float
    frozen: float

    # 费用信息
    commission: float
    margin: float

    # 盈亏信息
    close_profit: float
    position_profit: float
    total_profit: float

    # 元数据
    metadata: DataMetadata = field(default_factory=lambda: DataMetadata(
        DataCategory.PORTFOLIO_DATA, DataSource.VNPY
    ))

    @classmethod
    def from_vnpy_account(cls, account: Any) -> 'UnifiedAccount':
        """从VNPY AccountData创建统一账户."""
        total_profit = account.close_profit + account.position_profit

        return cls(
            account_id=account.accountid,
            account_type="future",  # 默认期货账户
            balance=account.balance,
            available=account.available,
            frozen=account.balance - account.available,
            commission=account.commission,
            margin=account.margin,
            close_profit=account.close_profit,
            position_profit=account.position_profit,
            total_profit=total_profit,
            metadata=DataMetadata(
                DataCategory.PORTFOLIO_DATA,
                DataSource.VNPY,
                count=1,
                last_updated=datetime.now()
            )
        )


class DataModelManager:
    """数据模型管理器."""

    def __init__(self):
        """初始化数据模型管理器."""
        self.logger = logging.getLogger(__name__)
        self._market_data_cache: Dict[str, List[UnifiedMarketData]] = {}
        self._order_cache: Dict[str, UnifiedOrder] = {}
        self._trade_cache: Dict[str, UnifiedTrade] = {}
        self._position_cache: Dict[str, UnifiedPosition] = {}
        self._account_cache: Dict[str, UnifiedAccount] = {}

    def add_market_data(self, data: UnifiedMarketData):
        """添加行情数据."""
        key = f"{data.symbol}_{data.exchange}"
        if key not in self._market_data_cache:
            self._market_data_cache[key] = []
        self._market_data_cache[key].append(data)

        # 限制缓存大小
        if len(self._market_data_cache[key]) > 10000:
            self._market_data_cache[key] = self._market_data_cache[key][-5000:]

    def get_market_data(self, symbol: str, exchange: str = "",
                        limit: int = 100) -> List[UnifiedMarketData]:
        """获取行情数据."""
        key = f"{symbol}_{exchange}"
        data_list = self._market_data_cache.get(key, [])
        return data_list[-limit:] if data_list else []

    def add_order(self, order: UnifiedOrder):
        """添加订单."""
        self._order_cache[order.order_id] = order

    def get_order(self, order_id: str) -> Optional[UnifiedOrder]:
        """获取订单."""
        return self._order_cache.get(order_id)

    def add_trade(self, trade: UnifiedTrade):
        """添加成交."""
        self._trade_cache[trade.trade_id] = trade

    def get_trade(self, trade_id: str) -> Optional[UnifiedTrade]:
        """获取成交."""
        return self._trade_cache.get(trade_id)

    def add_position(self, position: UnifiedPosition):
        """添加持仓."""
        key = f"{position.symbol}_{position.exchange}_{position.direction}"
        self._position_cache[key] = position

    def get_position(self, symbol: str, exchange: str = "",
                     direction: str = "long") -> Optional[UnifiedPosition]:
        """获取持仓."""
        key = f"{symbol}_{exchange}_{direction}"
        return self._position_cache.get(key)

    def add_account(self, account: UnifiedAccount):
        """添加账户."""
        self._account_cache[account.account_id] = account

    def get_account(self, account_id: str) -> Optional[UnifiedAccount]:
        """获取账户."""
        return self._account_cache.get(account_id)

    def to_pandas_dataframe(self, data_list: List[UnifiedMarketData]
                            ) -> Optional[Any]:
        """将行情数据转换为pandas DataFrame."""
        if not data_list or not pd:
            return None

        try:
            rows = [data.to_pandas_row() for data in data_list]
            df = pd.DataFrame(rows)
            if not df.empty:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df.set_index('datetime', inplace=True)
            return df
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.error("转换为pandas DataFrame失败: %s", e)
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息."""
        return {
            "market_data_count": sum(len(v) for v in
                                     self._market_data_cache.values()),
            "order_count": len(self._order_cache),
            "trade_count": len(self._trade_cache),
            "position_count": len(self._position_cache),
            "account_count": len(self._account_cache),
            "cache_memory_usage": self._estimate_memory_usage()
        }

    def _estimate_memory_usage(self) -> str:
        """估算内存使用量."""
        try:
            total_size = 0

            # 估算市场数据内存
            for data_list in self._market_data_cache.values():
                total_size += (sys.getsizeof(data_list) +
                               sum(sys.getsizeof(data) for data in data_list))

            # 估算其他数据内存
            total_size += sys.getsizeof(self._order_cache)
            total_size += sys.getsizeof(self._trade_cache)
            total_size += sys.getsizeof(self._position_cache)
            total_size += sys.getsizeof(self._account_cache)

            if total_size < 1024:
                return f"{total_size} B"
            if total_size < 1024 * 1024:
                return f"{total_size / 1024:.1f} KB"
            return f"{total_size / (1024 * 1024):.1f} MB"

        except (TypeError, AttributeError, OverflowError):
            return "未知"

    def clear_cache(self, data_type: str = "all"):
        """清空缓存."""
        if data_type in ["all", "market"]:
            self._market_data_cache.clear()

        if data_type in ["all", "order"]:
            self._order_cache.clear()

        if data_type in ["all", "trade"]:
            self._trade_cache.clear()

        if data_type in ["all", "position"]:
            self._position_cache.clear()

        if data_type in ["all", "account"]:
            self._account_cache.clear()

        self.logger.info("缓存已清空: %s", data_type)


# 全局数据模型管理器管理类
class _DataModelManagerRegistry:  # pylint: disable=invalid-name
    """数据模型管理器注册表."""

    def __init__(self):
        self._manager: Optional[DataModelManager] = None

    def get_manager(self) -> DataModelManager:
        """获取数据模型管理器实例."""
        if self._manager is None:
            self._manager = DataModelManager()
        return self._manager

    def reset_manager(self):
        """重置数据模型管理器（用于测试）."""
        if self._manager:
            self._manager.clear_cache()
            self._manager = None


# 全局注册表实例
_data_model_registry = _DataModelManagerRegistry()


def get_data_model_manager() -> DataModelManager:
    """获取全局数据模型管理器实例."""
    return _data_model_registry.get_manager()


def reset_data_model_manager():
    """重置数据模型管理器（用于测试）."""
    _data_model_registry.reset_manager()


# 导出所有公共接口
__all__ = [
    # 数据类别和源枚举
    'DataCategory', 'DataSource',

    # 数据模型类
    'DataMetadata', 'UnifiedMarketData', 'UnifiedOrder',
    'UnifiedTrade', 'UnifiedPosition', 'UnifiedAccount',

    # 管理器类
    'DataModelManager',

    # 全局函数
    'get_data_model_manager', 'reset_data_model_manager'
]
