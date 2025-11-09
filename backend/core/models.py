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

from pydantic import BaseModel, Field

# 直接导入pandas，避免循环导入
try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    PANDAS_AVAILABLE = False

# 导入native_collections（高性能LRU缓存）
from backend.infrastructure.native.native_collections import HighPerfLRUCache

# ✅ 添加logger定义
logger = logging.getLogger("backend.core.models")
logger_quality = logging.getLogger("backend.data.quality")  # 数据质量专用


class DataCategory(Enum):
    """数据类别枚举."""

    MARKET_DATA = "market_data"  # 行情数据
    TRANSACTION_DATA = "transaction_data"  # 交易数据
    PORTFOLIO_DATA = "portfolio_data"  # 组合数据
    RISK_DATA = "risk_data"  # 风险数据
    SYSTEM_DATA = "system_data"  # 系统数据


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
    metadata: DataMetadata = field(
        default_factory=lambda: DataMetadata(DataCategory.MARKET_DATA, DataSource.VNPY)
    )

    @classmethod
    def from_vnpy_tick(cls, tick: Any) -> "UnifiedMarketData":
        """从VNPY TickData创建统一数据."""
        try:
            # ✅ 数据验证
            if not hasattr(tick, "symbol") or not tick.symbol:
                logger.warning("Tick数据缺少symbol字段", extra={"log_type": "SYSTEM"})
                raise ValueError("Invalid tick: missing symbol")

            # ✅ 数据转换
            data = cls(
                symbol=tick.symbol,
                exchange=getattr(tick, "exchange", ""),
                data_type="tick",
                datetime=tick.datetime,
                timestamp=int(tick.datetime.timestamp()) if tick.datetime else 0,
                open_price=getattr(tick, "open_price", 0.0),
                high_price=getattr(tick, "high_price", 0.0),
                low_price=getattr(tick, "low_price", 0.0),
                close_price=getattr(tick, "last_price", 0.0),
                pre_close=getattr(tick, "pre_close", 0.0),
                volume=getattr(tick, "volume", 0),
                turnover=getattr(tick, "turnover", 0.0),
                open_interest=getattr(tick, "open_interest", 0),
                bid_price=getattr(tick, "bid_price_1", 0.0),
                bid_volume=getattr(tick, "bid_volume_1", 0),
                ask_price=getattr(tick, "ask_price_1", 0.0),
                ask_volume=getattr(tick, "ask_volume_1", 0),
                metadata=DataMetadata(
                    DataCategory.MARKET_DATA,
                    DataSource.VNPY,
                    symbol=tick.symbol,
                    exchange=getattr(tick, "exchange", ""),
                    count=1,
                    last_updated=tick.datetime,
                ),
            )

            # ✅ 数据质量检查
            if data.close_price <= 0:
                logger_quality.warning(
                    "Tick数据价格异常: 品种=%s, 价格=%.2f", tick.symbol, data.close_price
                )

            return data

        except AttributeError as e:
            logger.error(
                "❌ Tick数据字段缺失: 品种=%s, 错误=%s",
                getattr(tick, "symbol", "UNKNOWN"),
                e,
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )
            raise
        except Exception as e:
            logger.error("❌ Tick数据转换失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            raise

    @classmethod
    def from_vnpy_bar(cls, bar_data: Any) -> "UnifiedMarketData":
        """从VNPY BarData创建统一数据."""
        try:
            # ✅ 数据验证
            if not hasattr(bar_data, "symbol") or not bar_data.symbol:
                logger.warning("Bar数据缺少symbol字段", extra={"log_type": "SYSTEM"})
                raise ValueError("Invalid bar: missing symbol")

            # ✅ 数据转换
            data = cls(
                symbol=bar_data.symbol,
                exchange=getattr(bar_data, "exchange", ""),
                data_type="bar",
                datetime=bar_data.datetime,
                timestamp=(int(bar_data.datetime.timestamp()) if bar_data.datetime else 0),
                open_price=getattr(bar_data, "open_price", 0.0),
                high_price=getattr(bar_data, "high_price", 0.0),
                low_price=getattr(bar_data, "low_price", 0.0),
                close_price=getattr(bar_data, "close_price", 0.0),
                pre_close=0.0,  # BarData中没有pre_close
                volume=getattr(bar_data, "volume", 0),
                turnover=getattr(bar_data, "turnover", 0.0),
                open_interest=getattr(bar_data, "open_interest", 0),
                metadata=DataMetadata(
                    DataCategory.MARKET_DATA,
                    DataSource.VNPY,
                    symbol=bar_data.symbol,
                    exchange=getattr(bar_data, "exchange", ""),
                    frequency=(
                        f"{bar_data.interval}m"
                        if hasattr(bar_data, "interval") and bar_data.interval
                        else "1m"
                    ),
                    count=1,
                    last_updated=bar_data.datetime,
                ),
            )

            # ✅ 数据质量检查
            if data.close_price <= 0:
                logger_quality.warning(
                    "Bar数据价格异常: 品种=%s, 价格=%.2f", bar_data.symbol, data.close_price
                )

            return data

        except AttributeError as e:
            logger.error(
                "❌ Bar数据字段缺失: 品种=%s, 错误=%s",
                getattr(bar_data, "symbol", "UNKNOWN"),
                e,
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )
            raise
        except Exception as e:
            logger.error("❌ Bar数据转换失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            raise

    def to_pandas_row(self) -> Dict[str, Any]:
        """转换为pandas行数据."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "data_type": self.data_type,
            "datetime": self.datetime,
            "timestamp": self.timestamp,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "pre_close": self.pre_close,
            "volume": self.volume,
            "turnover": self.turnover,
            "open_interest": self.open_interest,
            "bid_price": self.bid_price,
            "bid_volume": self.bid_volume,
            "ask_price": self.ask_price,
            "ask_volume": self.ask_volume,
        }


@dataclass
class UnifiedOrder:  # pylint: disable=too-many-instance-attributes
    """统一订单数据模型."""

    # 基础信息
    order_id: str
    symbol: str
    exchange: str
    order_type: str  # market, limit, stop
    direction: str  # long, short

    # 价格和数量
    price: float
    volume: int

    # 状态信息
    status: str  # submitted, partial, filled, cancelled, rejected
    order_time: datetime
    traded_volume: int = 0

    # 元数据
    metadata: DataMetadata = field(
        default_factory=lambda: DataMetadata(DataCategory.TRANSACTION_DATA, DataSource.VNPY)
    )

    @classmethod
    def from_vnpy_order(cls, order: Any) -> "UnifiedOrder":
        """从VNPY OrderData创建统一订单."""
        return cls(
            order_id=(order.orderid if hasattr(order, "orderid") else str(id(order))),
            symbol=order.symbol,
            exchange=order.exchange,
            order_type=order.type,
            direction=order.direction,
            price=order.price,
            volume=order.volume,
            traded_volume=order.traded,
            status=order.status,
            order_time=(
                datetime.strptime(order.time, "%H:%M:%S") if order.time else datetime.now()
            ),
            metadata=DataMetadata(
                DataCategory.TRANSACTION_DATA,
                DataSource.VNPY,
                symbol=order.symbol,
                exchange=order.exchange,
                count=1,
                last_updated=datetime.now(),
            ),
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
    metadata: DataMetadata = field(
        default_factory=lambda: DataMetadata(DataCategory.TRANSACTION_DATA, DataSource.VNPY)
    )

    @classmethod
    def from_vnpy_trade(cls, trade: Any) -> "UnifiedTrade":
        """从VNPY TradeData创建统一成交."""
        return cls(
            trade_id=(trade.tradeid if hasattr(trade, "tradeid") else str(id(trade))),
            order_id="",  # TradeData中没有order_id
            symbol=trade.symbol,
            exchange=trade.exchange,
            direction=trade.direction,
            price=trade.price,
            volume=trade.volume,
            trade_time=(
                datetime.strptime(trade.time, "%H:%M:%S") if trade.time else datetime.now()
            ),
            metadata=DataMetadata(
                DataCategory.TRANSACTION_DATA,
                DataSource.VNPY,
                symbol=trade.symbol,
                exchange=trade.exchange,
                count=1,
                last_updated=datetime.now(),
            ),
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
    metadata: DataMetadata = field(
        default_factory=lambda: DataMetadata(DataCategory.PORTFOLIO_DATA, DataSource.VNPY)
    )

    @classmethod
    def from_vnpy_position(cls, position: Any) -> "UnifiedPosition":
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
                last_updated=datetime.now(),
            ),
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
    metadata: DataMetadata = field(
        default_factory=lambda: DataMetadata(DataCategory.PORTFOLIO_DATA, DataSource.VNPY)
    )

    @classmethod
    def from_vnpy_account(cls, account: Any) -> "UnifiedAccount":
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
                last_updated=datetime.now(),
            ),
        )


# =============================================================================
# 数据中心模块数据模型
# =============================================================================


class SymbolInfo(BaseModel):
    """品种信息模型."""

    id: Optional[str] = Field(None, description="品种ID")
    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    name: str = Field(..., description="品种名称")
    product: str = Field(..., description="产品类型")
    size: float = Field(..., description="合约乘数")
    pricetick: float = Field(..., description="最小变动价位")
    min_volume: int = Field(default=1, description="最小交易量")
    max_volume: int = Field(default=1000000, description="最大交易量")
    is_active: bool = Field(default=True, description="是否活跃")
    listed_date: Optional[datetime] = Field(None, description="上市日期")
    expired_date: Optional[datetime] = Field(None, description="到期日期")


class DownloadTask(BaseModel):
    """下载任务模型."""

    task_id: str = Field(..., description="任务ID")
    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    start_date: datetime = Field(..., description="开始日期")
    end_date: datetime = Field(..., description="结束日期")
    data_type: str = Field(default="bar", description="数据类型")
    frequency: str = Field(default="1m", description="数据频率")
    status: str = Field(default="pending", description="任务状态")
    progress: float = Field(default=0.0, description="进度百分比")
    total_count: int = Field(default=0, description="总数据量")
    downloaded_count: int = Field(default=0, description="已下载数量")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class DataSourceConfig(BaseModel):
    """数据源配置模型."""

    source_id: str = Field(..., description="数据源ID")
    source_type: str = Field(..., description="数据源类型")
    name: str = Field(..., description="数据源名称")
    is_enabled: bool = Field(default=True, description="是否启用")
    is_connected: bool = Field(default=False, description="是否连接")
    config: Dict[str, Any] = Field(default_factory=dict, description="配置参数")
    last_connected: Optional[datetime] = Field(None, description="最后连接时间")
    error_count: int = Field(default=0, description="错误次数")


# =============================================================================
# 行情看板模块数据模型
# =============================================================================


class ChartConfig(BaseModel):
    """图表配置模型."""

    chart_id: str = Field(..., description="图表ID")
    symbol: str = Field(..., description="主品种")
    exchange: str = Field(..., description="交易所")
    chart_type: str = Field(default="kline", description="图表类型")
    period: str = Field(default="1m", description="周期")
    indicators: List[Dict[str, Any]] = Field(default_factory=list, description="指标配置")
    overlays: List[Dict[str, Any]] = Field(default_factory=list, description="叠加配置")
    theme: str = Field(default="dark", description="主题")
    auto_refresh: bool = Field(default=True, description="自动刷新")


class IndicatorConfig(BaseModel):
    """指标配置模型."""

    indicator_id: str = Field(..., description="指标ID")
    name: str = Field(..., description="指标名称")
    type: str = Field(..., description="指标类型")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数")
    style: Dict[str, Any] = Field(default_factory=dict, description="样式配置")
    sub_chart: int = Field(default=0, description="副图编号")


class GapInfo(BaseModel):
    """数据断点信息模型."""

    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    gap_start: datetime = Field(..., description="断点开始时间")
    gap_end: datetime = Field(..., description="断点结束时间")
    gap_type: str = Field(..., description="断点类型")
    severity: str = Field(default="medium", description="严重程度")
    suggested_action: str = Field(..., description="建议操作")


# =============================================================================
# 策略指标中心模块数据模型
# =============================================================================


class StrategyFile(BaseModel):
    """策略文件模型."""

    file_path: str = Field(..., description="文件路径")
    file_name: str = Field(..., description="文件名")
    file_type: str = Field(..., description="文件类型")
    size: int = Field(default=0, description="文件大小")
    modified_time: datetime = Field(..., description="修改时间")
    strategy_type: Optional[str] = Field(None, description="策略类型")
    is_valid: bool = Field(default=True, description="是否有效")


class BacktestConfig(BaseModel):
    """回测配置模型."""

    backtest_id: str = Field(..., description="回测ID")
    strategy_name: str = Field(..., description="策略名称")
    symbol: str = Field(..., description="品种代码")
    start_date: datetime = Field(..., description="开始日期")
    end_date: datetime = Field(..., description="结束日期")
    initial_capital: float = Field(default=100000.0, description="初始资金")
    commission_rate: float = Field(default=0.0003, description="手续费率")
    slippage_rate: float = Field(default=0.0, description="滑点率")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="策略参数")
    status: str = Field(default="pending", description="回测状态")
    progress: float = Field(default=0.0, description="进度百分比")


class BacktestResult(BaseModel):
    """回测结果模型."""

    backtest_id: str = Field(..., description="回测ID")
    total_return: float = Field(default=0.0, description="总收益率")
    annual_return: float = Field(default=0.0, description="年化收益率")
    max_drawdown: float = Field(default=0.0, description="最大回撤")
    sharpe_ratio: float = Field(default=0.0, description="夏普比率")
    win_rate: float = Field(default=0.0, description="胜率")
    profit_factor: float = Field(default=0.0, description="盈利因子")
    total_trades: int = Field(default=0, description="总交易次数")
    winning_trades: int = Field(default=0, description="盈利交易次数")
    losing_trades: int = Field(default=0, description="亏损交易次数")
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list, description="权益曲线")
    trade_records: List[Dict[str, Any]] = Field(default_factory=list, description="交易记录")


class AIChatMessage(BaseModel):
    """AI聊天消息模型."""

    message_id: str = Field(..., description="消息ID")
    role: str = Field(..., description="角色")
    content: str = Field(..., description="内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


# =============================================================================
# 交易网关模块数据模型
# =============================================================================


class GatewayConfig(BaseModel):
    """网关配置模型."""

    gateway_id: str = Field(..., description="网关ID")
    gateway_type: str = Field(..., description="网关类型")
    gateway_name: str = Field(..., description="网关名称")
    is_active: bool = Field(default=False, description="是否激活")
    is_connected: bool = Field(default=False, description="是否连接")
    config: Dict[str, Any] = Field(default_factory=dict, description="配置参数")
    status: str = Field(default="disconnected", description="连接状态")
    last_connected: Optional[datetime] = Field(None, description="最后连接时间")
    error_message: Optional[str] = Field(None, description="错误信息")


class StrategyInstance(BaseModel):
    """策略实例模型."""

    instance_id: str = Field(..., description="实例ID")
    gateway_id: str = Field(..., description="网关ID")
    strategy_name: str = Field(..., description="策略名称")
    strategy_type: str = Field(..., description="策略类型")
    symbol: str = Field(..., description="品种代码")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数")
    is_active: bool = Field(default=False, description="是否激活")
    status: str = Field(default="stopped", description="运行状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: Optional[datetime] = Field(None, description="启动时间")
    stopped_at: Optional[datetime] = Field(None, description="停止时间")


class MonitorData(BaseModel):
    """监控数据模型."""

    gateway_id: str = Field(..., description="网关ID")
    data_type: str = Field(..., description="数据类型")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    data: Dict[str, Any] = Field(default_factory=dict, description="数据内容")


# =============================================================================
# 组合投资模块数据模型
# =============================================================================


class Portfolio(BaseModel):
    """组合模型."""

    portfolio_id: str = Field(..., description="组合ID")
    portfolio_name: str = Field(..., description="组合名称")
    portfolio_type: str = Field(default="custom", description="组合类型")
    description: str = Field(default="", description="描述")
    is_active: bool = Field(default=True, description="是否激活")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    config: Dict[str, Any] = Field(default_factory=dict, description="配置参数")


class PortfolioPosition(BaseModel):
    """组合持仓模型."""

    portfolio_id: str = Field(..., description="组合ID")
    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    direction: str = Field(..., description="方向")
    volume: float = Field(default=0.0, description="数量")
    price: float = Field(default=0.0, description="价格")
    market_value: float = Field(default=0.0, description="市值")
    cost_value: float = Field(default=0.0, description="成本")
    unrealized_pnl: float = Field(default=0.0, description="未实现盈亏")
    realized_pnl: float = Field(default=0.0, description="已实现盈亏")
    weight: float = Field(default=0.0, description="权重")


class PortfolioPerformance(BaseModel):
    """组合业绩模型."""

    portfolio_id: str = Field(..., description="组合ID")
    date: datetime = Field(..., description="日期")
    total_value: float = Field(default=0.0, description="总市值")
    cash: float = Field(default=0.0, description="现金")
    total_return: float = Field(default=0.0, description="总收益率")
    daily_return: float = Field(default=0.0, description="日收益率")
    cumulative_return: float = Field(default=0.0, description="累计收益率")
    volatility: float = Field(default=0.0, description="波动率")
    sharpe_ratio: float = Field(default=0.0, description="夏普比率")
    max_drawdown: float = Field(default=0.0, description="最大回撤")


# =============================================================================
# 系统管理模块数据模型
# =============================================================================


class SystemMetric(BaseModel):
    """系统指标模型."""

    metric_id: str = Field(..., description="指标ID")
    metric_type: str = Field(..., description="指标类型")
    name: str = Field(..., description="指标名称")
    value: float = Field(default=0.0, description="指标值")
    unit: str = Field(default="", description="单位")
    threshold_warning: Optional[float] = Field(None, description="警告阈值")
    threshold_critical: Optional[float] = Field(None, description="严重阈值")
    status: str = Field(default="normal", description="状态")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class AlertRule(BaseModel):
    """告警规则模型."""

    rule_id: str = Field(..., description="规则ID")
    rule_name: str = Field(..., description="规则名称")
    metric_type: str = Field(..., description="指标类型")
    condition: str = Field(..., description="条件")
    threshold: float = Field(..., description="阈值")
    severity: str = Field(default="warning", description="严重程度")
    is_enabled: bool = Field(default=True, description="是否启用")
    notification_methods: List[str] = Field(default_factory=list, description="通知方式")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class AlertRecord(BaseModel):
    """告警记录模型."""

    alert_id: str = Field(..., description="告警ID")
    rule_id: str = Field(..., description="规则ID")
    metric_type: str = Field(..., description="指标类型")
    metric_value: float = Field(..., description="指标值")
    threshold: float = Field(..., description="阈值")
    severity: str = Field(..., description="严重程度")
    message: str = Field(..., description="告警消息")
    status: str = Field(default="active", description="状态")
    triggered_at: datetime = Field(default_factory=datetime.now, description="触发时间")
    acknowledged_at: Optional[datetime] = Field(None, description="确认时间")
    resolved_at: Optional[datetime] = Field(None, description="解决时间")


class HealthCheck(BaseModel):
    """健康检查模型."""

    service_name: str = Field(..., description="服务名称")
    status: str = Field(..., description="状态")
    response_time: float = Field(default=0.0, description="响应时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    last_check: datetime = Field(default_factory=datetime.now, description="最后检查时间")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细信息")


class SystemTool(BaseModel):
    """系统工具模型."""

    tool_id: str = Field(..., description="工具ID")
    tool_name: str = Field(..., description="工具名称")
    tool_type: str = Field(..., description="工具类型")
    description: str = Field(default="", description="描述")
    command: str = Field(..., description="命令")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数")
    is_enabled: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class LogEntry(BaseModel):
    """日志条目模型."""

    log_id: str = Field(..., description="日志ID")
    level: str = Field(..., description="日志级别")
    logger_name: str = Field(..., description="记录器名称")
    message: str = Field(..., description="日志消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    module: Optional[str] = Field(None, description="模块名称")
    function: Optional[str] = Field(None, description="函数名称")
    line_number: Optional[int] = Field(None, description="行号")
    extra_data: Dict[str, Any] = Field(default_factory=dict, description="额外数据")


class DiagnosticReport(BaseModel):
    """诊断报告模型."""

    report_id: str = Field(..., description="报告ID")
    report_type: str = Field(..., description="报告类型")
    status: str = Field(..., description="诊断状态")
    summary: str = Field(..., description="摘要")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细信息")
    recommendations: List[str] = Field(default_factory=list, description="建议")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class ConfigItem(BaseModel):
    """配置项模型."""

    config_key: str = Field(..., description="配置键")
    config_value: Any = Field(..., description="配置值")
    config_type: str = Field(..., description="配置类型")
    description: str = Field(default="", description="描述")
    is_encrypted: bool = Field(default=False, description="是否加密")
    last_modified: datetime = Field(default_factory=datetime.now, description="最后修改时间")
    modified_by: Optional[str] = Field(None, description="修改人")


# =============================================================================
# 扩展的策略中心模块数据模型
# =============================================================================


class StrategyTemplate(BaseModel):
    """策略模板模型."""

    template_id: str = Field(..., description="模板ID")
    template_name: str = Field(..., description="模板名称")
    strategy_type: str = Field(..., description="策略类型")
    description: str = Field(default="", description="描述")
    template_code: str = Field(..., description="模板代码")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数定义")
    is_builtin: bool = Field(default=False, description="是否内置模板")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class BacktestTask(BaseModel):
    """回测任务模型."""

    task_id: str = Field(..., description="任务ID")
    strategy_file_id: str = Field(..., description="策略文件ID")
    strategy_name: str = Field(..., description="策略名称")
    strategy_type: str = Field(..., description="策略类型")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="回测参数")
    status: str = Field(default="pending", description="任务状态")
    progress: float = Field(default=0.0, description="进度")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


# =============================================================================
# 扩展的交易网关模块数据模型
# =============================================================================


class GatewayInstance(BaseModel):
    """网关实例模型."""

    instance_id: str = Field(..., description="实例ID")
    gateway_type: str = Field(..., description="网关类型")
    instance_name: str = Field(..., description="实例名称")
    config: Dict[str, Any] = Field(default_factory=dict, description="配置")
    status: str = Field(default="disconnected", description="状态")
    connected_at: Optional[datetime] = Field(None, description="连接时间")
    disconnected_at: Optional[datetime] = Field(None, description="断开时间")
    error_count: int = Field(default=0, description="错误计数")
    last_error: Optional[str] = Field(None, description="最后错误")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class OrderInfo(BaseModel):
    """委托信息模型."""

    order_id: str = Field(..., description="委托ID")
    gateway_id: str = Field(..., description="网关ID")
    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    direction: str = Field(..., description="方向")
    offset: str = Field(..., description="开平")
    price: float = Field(..., description="价格")
    volume: float = Field(..., description="数量")
    traded_volume: float = Field(default=0.0, description="成交数量")
    status: str = Field(..., description="状态")
    order_time: datetime = Field(default_factory=datetime.now, description="委托时间")
    strategy_name: Optional[str] = Field(None, description="策略名称")


class PositionInfo(BaseModel):
    """持仓信息模型."""

    position_id: str = Field(..., description="持仓ID")
    gateway_id: str = Field(..., description="网关ID")
    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    direction: str = Field(..., description="方向")
    volume: float = Field(..., description="数量")
    frozen: float = Field(default=0.0, description="冻结数量")
    price: float = Field(..., description="价格")
    pnl: float = Field(default=0.0, description="盈亏")
    last_update: datetime = Field(default_factory=datetime.now, description="更新时间")


class AccountInfo(BaseModel):
    """资金信息模型."""

    account_id: str = Field(..., description="账户ID")
    gateway_id: str = Field(..., description="网关ID")
    balance: float = Field(..., description="余额")
    frozen: float = Field(default=0.0, description="冻结")
    available: float = Field(..., description="可用")
    margin: float = Field(default=0.0, description="保证金")
    commission: float = Field(default=0.0, description="手续费")
    last_update: datetime = Field(default_factory=datetime.now, description="更新时间")


class TradeInfo(BaseModel):
    """成交信息模型."""

    trade_id: str = Field(..., description="成交ID")
    order_id: str = Field(..., description="委托ID")
    gateway_id: str = Field(..., description="网关ID")
    symbol: str = Field(..., description="品种代码")
    exchange: str = Field(..., description="交易所")
    direction: str = Field(..., description="方向")
    offset: str = Field(..., description="开平")
    price: float = Field(..., description="价格")
    volume: float = Field(..., description="数量")
    trade_time: datetime = Field(default_factory=datetime.now, description="成交时间")
    strategy_name: Optional[str] = Field(None, description="策略名称")


# =============================================================================
# 扩展的组合投资模块数据模型
# =============================================================================


class VirtualGateway(BaseModel):
    """虚拟网关模型."""

    virtual_id: str = Field(..., description="虚拟网关ID")
    virtual_name: str = Field(..., description="虚拟网关名称")
    member_gateways: List[str] = Field(default_factory=list, description="成员网关ID列表")
    description: str = Field(default="", description="描述")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class PortfolioMember(BaseModel):
    """组合成员模型."""

    portfolio_id: str = Field(..., description="组合ID")
    member_id: str = Field(..., description="成员ID")
    member_type: str = Field(..., description="成员类型")
    weight: float = Field(default=0.0, description="权重")
    is_active: bool = Field(default=True, description="是否激活")
    added_at: datetime = Field(default_factory=datetime.now, description="添加时间")


class PerformanceMetrics(BaseModel):
    """业绩指标模型."""

    portfolio_id: str = Field(..., description="组合ID")
    date: datetime = Field(..., description="日期")
    net_value: float = Field(..., description="净值")
    total_return: float = Field(..., description="总收益率")
    daily_return: float = Field(..., description="日收益率")
    annual_return: float = Field(default=0.0, description="年化收益率")
    sharpe_ratio: float = Field(default=0.0, description="夏普比率")
    sortino_ratio: float = Field(default=0.0, description="索提诺比率")
    max_drawdown: float = Field(default=0.0, description="最大回撤")
    win_rate: float = Field(default=0.0, description="胜率")


class RiskMetrics(BaseModel):
    """风险指标模型."""

    portfolio_id: str = Field(..., description="组合ID")
    date: datetime = Field(..., description="日期")
    volatility: float = Field(..., description="波动率")
    var_95: float = Field(..., description="95% VaR")
    var_99: float = Field(..., description="99% VaR")
    cvar_95: float = Field(..., description="95% CVaR")
    beta: float = Field(default=0.0, description="Beta值")
    correlation_matrix: Dict[str, Any] = Field(default_factory=dict, description="相关性矩阵")
    exposure: Dict[str, float] = Field(default_factory=dict, description="风险暴露")


class AttributionResult(BaseModel):
    """归因分析结果模型."""

    portfolio_id: str = Field(..., description="组合ID")
    date: datetime = Field(..., description="日期")
    total_return: float = Field(..., description="总收益")
    asset_allocation: Dict[str, float] = Field(default_factory=dict, description="资产配置贡献")
    security_selection: Dict[str, float] = Field(default_factory=dict, description="证券选择贡献")
    timing: float = Field(default=0.0, description="择时贡献")
    interaction: float = Field(default=0.0, description="交互效应")
    residual: float = Field(default=0.0, description="残差")


# =============================================================================
# 扩展的系统管理模块数据模型
# =============================================================================


class SystemStatus(BaseModel):
    """系统状态模型."""

    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    cpu_percent: float = Field(..., description="CPU使用率")
    memory_percent: float = Field(..., description="内存使用率")
    disk_percent: float = Field(..., description="磁盘使用率")
    network_sent: float = Field(default=0.0, description="网络发送")
    network_recv: float = Field(default=0.0, description="网络接收")
    process_count: int = Field(default=0, description="进程数")
    thread_count: int = Field(default=0, description="线程数")
    status: str = Field(default="normal", description="状态")


class AlertInfo(BaseModel):
    """告警信息模型."""

    alert_id: str = Field(..., description="告警ID")
    alert_type: str = Field(..., description="告警类型")
    severity: str = Field(..., description="严重程度")
    title: str = Field(..., description="标题")
    message: str = Field(..., description="消息")
    source: str = Field(..., description="来源")
    status: str = Field(default="active", description="状态")
    triggered_at: datetime = Field(default_factory=datetime.now, description="触发时间")
    acknowledged_at: Optional[datetime] = Field(None, description="确认时间")
    resolved_at: Optional[datetime] = Field(None, description="解决时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class HealthCheckResult(BaseModel):
    """健康检查结果模型."""

    service_name: str = Field(..., description="服务名称")
    status: str = Field(..., description="状态")
    response_time_ms: float = Field(..., description="响应时间(毫秒)")
    message: str = Field(default="", description="消息")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细信息")
    checked_at: datetime = Field(default_factory=datetime.now, description="检查时间")


class ToolInfo(BaseModel):
    """工具信息模型."""

    tool_id: str = Field(..., description="工具ID")
    tool_name: str = Field(..., description="工具名称")
    tool_category: str = Field(..., description="工具类别")
    version: str = Field(default="1.0.0", description="版本")
    description: str = Field(default="", description="描述")
    entry_point: str = Field(..., description="入口点")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, description="参数模式")
    is_enabled: bool = Field(default=True, description="是否启用")
    registered_at: datetime = Field(default_factory=datetime.now, description="注册时间")
    usage_count: int = Field(default=0, description="使用次数")


class DataModelManager:
    """数据模型管理器."""

    def __init__(self):
        """初始化数据模型管理器."""
        self.logger = logging.getLogger(__name__)

        # 市场数据缓存：使用HighPerfLRUCache存储品种列表（自动淘汰不常用的品种）
        # 每个品种的列表最大5000条，超过时自动淘汰最旧的数据
        # 最多缓存1000个品种（基于访问频率自动淘汰）
        # type: ignore - HighPerfLRUCache是C扩展，类型检查器无法识别其构造函数
        self._market_data_cache: Any = HighPerfLRUCache(1000)  # 最多1000个品种  # type: ignore
        self._order_cache: Any = HighPerfLRUCache(10000)  # 最大10000个订单  # type: ignore
        self._trade_cache: Any = HighPerfLRUCache(10000)  # 最大10000个成交  # type: ignore
        self._position_cache: Any = HighPerfLRUCache(5000)  # 最大5000个持仓  # type: ignore
        self._account_cache: Any = HighPerfLRUCache(100)  # 最大100个账户  # type: ignore

        # 每个品种的最大缓存条数
        self._max_market_data_per_symbol = 5000

    @staticmethod
    def _safe_cache_get(cache: Any, key: Any, default: Any = None) -> Any:
        """安全地从HighPerfLRUCache或降级实现中获取数据."""
        if cache is None:
            return default

        try:
            getter = cache.get  # type: ignore[attr-defined]
        except AttributeError:
            return default

        try:
            return getter(key)  # type: ignore[misc]
        except KeyError:
            return default
        except TypeError:
            # 降级实现可能支持默认值参数，尝试带默认值调用
            try:
                return getter(key, default)  # type: ignore[misc]
            except Exception:  # noqa: BLE001 - 降级逻辑，保证稳健性
                return default

    def add_market_data(self, data: UnifiedMarketData):
        """添加行情数据."""
        key = f"{data.symbol}_{data.exchange}"

        # 从缓存获取列表（如果存在）
        data_list = self._safe_cache_get(self._market_data_cache, key)
        if data_list is None:
            data_list = []

        # 添加新数据
        data_list.append(data)

        # 限制每个品种的缓存大小（最大5000条，自动淘汰最旧的数据）
        if len(data_list) > self._max_market_data_per_symbol:
            # 只保留最新的max_size条数据
            data_list = data_list[-self._max_market_data_per_symbol:]

        # 更新缓存（会自动更新LRU顺序）
        self._market_data_cache.set(key, data_list)  # type: ignore

    def get_market_data(
        self, symbol: str, exchange: str = "", limit: int = 100
    ) -> List[UnifiedMarketData]:
        """获取行情数据."""
        key = f"{symbol}_{exchange}"

        # get()方法会自动更新LRU顺序
        data_list = self._safe_cache_get(self._market_data_cache, key)
        if not data_list:
            return []
        return data_list[-limit:] if data_list else []

    def add_order(self, order: UnifiedOrder):
        """添加订单."""
        self._order_cache.set(order.order_id, order)  # type: ignore

    def get_order(self, order_id: str) -> Optional[UnifiedOrder]:
        """获取订单."""
        return self._safe_cache_get(self._order_cache, order_id)

    def add_trade(self, trade: UnifiedTrade):
        """添加成交."""
        self._trade_cache.set(trade.trade_id, trade)  # type: ignore

    def get_trade(self, trade_id: str) -> Optional[UnifiedTrade]:
        """获取成交."""
        return self._safe_cache_get(self._trade_cache, trade_id)

    def add_position(self, position: UnifiedPosition):
        """添加持仓."""
        key = f"{position.symbol}_{position.exchange}_{position.direction}"
        self._position_cache.set(key, position)  # type: ignore

    def get_position(
        self, symbol: str, exchange: str = "", direction: str = "long"
    ) -> Optional[UnifiedPosition]:
        """获取持仓."""
        key = f"{symbol}_{exchange}_{direction}"
        return self._safe_cache_get(self._position_cache, key)

    def add_account(self, account: UnifiedAccount):
        """添加账户."""
        self._account_cache.set(account.account_id, account)  # type: ignore

    def get_account(self, account_id: str) -> Optional[UnifiedAccount]:
        """获取账户."""
        return self._safe_cache_get(self._account_cache, account_id)

    def to_pandas_dataframe(self, data_list: List[UnifiedMarketData]) -> Optional[Any]:
        """将行情数据转换为pandas DataFrame."""
        if not data_list or not pd:
            return None

        try:
            rows = [data.to_pandas_row() for data in data_list]
            df = pd.DataFrame(rows)
            if not df.empty:
                df["datetime"] = pd.to_datetime(df["datetime"])
                df.set_index("datetime", inplace=True)
            return df
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.error(
                "转换为pandas DataFrame失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True
            )
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息."""
        # 注意：HighPerfLRUCache没有直接遍历的方法，这里使用size()获取品种数量
        # 实际数据条数无法精确统计，使用估算值
        market_data_count = self._market_data_cache.size() * 100  # type: ignore  # 估算：每个品种平均100条

        return {
            "market_data_count": market_data_count,
            "market_symbol_count": self._market_data_cache.size(),  # type: ignore
            "order_count": self._order_cache.size(),  # type: ignore
            "trade_count": self._trade_cache.size(),  # type: ignore
            "position_count": self._position_cache.size(),  # type: ignore
            "account_count": self._account_cache.size(),  # type: ignore
            "cache_memory_usage": self._estimate_memory_usage(),
        }

    def _estimate_memory_usage(self) -> str:
        """估算内存使用量."""
        try:
            total_size = 0

            # 注意：HighPerfLRUCache是C扩展，sys.getsizeof可能不准确
            # 使用size()获取元素数量，粗略估算每个元素平均大小
            avg_market_data_size = 300  # 每个市场数据条目平均大小（字节）
            avg_element_size = 200  # 其他数据条目平均大小（字节）

            # 估算市场数据内存（品种数 * 平均每个品种的数据条数 * 平均大小）
            market_symbol_count = self._market_data_cache.size()  # type: ignore
            avg_data_per_symbol = 100  # 估算每个品种平均100条数据
            total_size += market_symbol_count * avg_data_per_symbol * avg_market_data_size

            # 估算其他数据内存
            total_size += self._order_cache.size() * avg_element_size  # type: ignore
            total_size += self._trade_cache.size() * avg_element_size  # type: ignore
            total_size += self._position_cache.size() * avg_element_size  # type: ignore
            total_size += self._account_cache.size() * avg_element_size  # type: ignore

            if total_size < 1024:
                return f"{total_size} B"
            if total_size < 1024 * 1024:
                return f"{total_size / 1024:.1f} KB"
            return f"{total_size / (1024 * 1024):.1f} MB"

        except (TypeError, AttributeError, OverflowError):
            return "未知"

    def clear_cache(self, data_type: str = "all"):
        """清空缓存."""
        # HighPerfLRUCache没有clear()方法，需要重新创建实例
        if data_type in ["all", "market"]:
            self._market_data_cache = HighPerfLRUCache(1000)  # type: ignore

        if data_type in ["all", "order"]:
            self._order_cache = HighPerfLRUCache(10000)  # type: ignore

        if data_type in ["all", "trade"]:
            self._trade_cache = HighPerfLRUCache(10000)  # type: ignore

        if data_type in ["all", "position"]:
            self._position_cache = HighPerfLRUCache(5000)  # type: ignore

        if data_type in ["all", "account"]:
            self._account_cache = HighPerfLRUCache(100)  # type: ignore

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
    "DataCategory",
    "DataSource",
    # 原始数据模型类
    "DataMetadata",
    "UnifiedMarketData",
    "UnifiedOrder",
    "UnifiedTrade",
    "UnifiedPosition",
    "UnifiedAccount",
    # 数据中心模块模型
    "SymbolInfo",
    "DownloadTask",
    "DataSourceConfig",
    # 行情看板模块模型
    "ChartConfig",
    "IndicatorConfig",
    "GapInfo",
    # 策略指标中心模块模型
    "StrategyFile",
    "BacktestConfig",
    "BacktestResult",
    "AIChatMessage",
    # 交易网关模块模型
    "GatewayConfig",
    "StrategyInstance",
    "MonitorData",
    # 组合投资模块模型
    "Portfolio",
    "PortfolioPosition",
    "PortfolioPerformance",
    # 系统管理模块模型
    "SystemMetric",
    "AlertRule",
    "AlertRecord",
    "HealthCheck",
    "SystemTool",
    "LogEntry",
    "DiagnosticReport",
    "ConfigItem",
    # 扩展的策略中心模型
    "StrategyTemplate",
    "BacktestTask",
    # 扩展的交易网关模型
    "GatewayInstance",
    "OrderInfo",
    "PositionInfo",
    "AccountInfo",
    "TradeInfo",
    # 扩展的组合投资模型
    "VirtualGateway",
    "PortfolioMember",
    "PerformanceMetrics",
    "RiskMetrics",
    "AttributionResult",
    # 扩展的系统管理模型
    "SystemStatus",
    "AlertInfo",
    "HealthCheckResult",
    "ToolInfo",
    # 管理器类
    "DataModelManager",
    # 全局函数
    "get_data_model_manager",
    "reset_data_model_manager",
]
