"""
Framework Foundation - 项目基石
提供VnPy集成、数据模型、配置系统、服务抽象

原子来源（原子化打散重组）:
- core/vnpy_imports.py (340行)
- core/base.py (932行)
- core/models.py (1145行)
- core/contracts.py (54行)
- core/config.py (485行)
- core/service_base.py (815行)
- system_vnpy/core_engine.py (1009行)
- system_vnpy/module_lifecycle.py (488行)
- system_vnpy/module_dependency.py (385行)
- scheduling/cron.py (215行)

职责：提供项目最底层的抽象、集成、配置，是整个框架的基石
"""

import asyncio
import inspect
import logging
from collections import deque
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json

from backend.core.config import AppConfig, UIConfig

logger = logging.getLogger("framework.foundation")

# ============================================================================
# Section 1: VnPy集成和数据模型 (行 1-300)
# ============================================================================

# VnPy可用性检测
VNPY_AVAILABLE = False
PANDAS_AVAILABLE = False
NUMPY_AVAILABLE = False

# pandas和numpy别名（延迟导入）
pd = None  # pylint: disable=invalid-name
np = None  # pylint: disable=invalid-name

# VnPy核心组件（延迟导入）
MainEngine: Optional[Any] = None  # pylint: disable=invalid-name
EventEngine: Optional[Any] = None  # pylint: disable=invalid-name
Event: Optional[Any] = None  # pylint: disable=invalid-name
TickData: Optional[Any] = None  # pylint: disable=invalid-name
BarData: Optional[Any] = None  # pylint: disable=invalid-name
OrderData: Optional[Any] = None  # pylint: disable=invalid-name
TradeData: Optional[Any] = None  # pylint: disable=invalid-name
PositionData: Optional[Any] = None  # pylint: disable=invalid-name
AccountData: Optional[Any] = None  # pylint: disable=invalid-name

# VnPy事件类型
EVENT_TICK = "eTick"
EVENT_ORDER = "eOrder"
EVENT_TRADE = "eTrade"
EVENT_POSITION = "ePosition"
EVENT_ACCOUNT = "eAccount"
EVENT_LOG = "eLog"


def _lazy_import_vnpy():
    """延迟导入VnPy组件"""
    global VNPY_AVAILABLE, PANDAS_AVAILABLE, NUMPY_AVAILABLE
    global MainEngine, EventEngine, Event, pd, np
    global TickData, BarData, OrderData, TradeData, PositionData, AccountData

    try:
        from vnpy.event import EventEngine, Event
        from vnpy.trader.engine import MainEngine
        from vnpy.trader.object import (
            TickData,
            BarData,
            OrderData,
            TradeData,
            PositionData,
            AccountData,
        )

        VNPY_AVAILABLE = True
        logger.info("✅ VnPy组件导入成功")
    except ImportError as e:
        logger.warning("⚠️ VnPy不可用: %s", e)
        VNPY_AVAILABLE = False

    # 尝试导入pandas和numpy
    try:
        import pandas as pd
        PANDAS_AVAILABLE = True
        logger.debug("✅ pandas导入成功")
    except ImportError:
        logger.debug("⚠️ pandas不可用")
        PANDAS_AVAILABLE = False

    try:
        import numpy as np
        NUMPY_AVAILABLE = True
        logger.debug("✅ numpy导入成功")
    except ImportError:
        logger.debug("⚠️ numpy不可用")
        NUMPY_AVAILABLE = False


def ensure_vnpy_imported():
    """确保VnPy已导入"""
    if not VNPY_AVAILABLE:
        _lazy_import_vnpy()
    return VNPY_AVAILABLE


# 数据源枚举
class DataSource(str, Enum):
    """数据来源"""

    VNPY_CTP = "vnpy_ctp"
    VNPY_IB = "vnpy_ib"
    TUSHARE = "tushare"
    RQDATA = "rqdata"
    TDX = "tdx"
    LOCAL_DB = "local_db"


class Exchange(str, Enum):
    """交易所"""

    SSE = "SSE"  # 上交所
    SZSE = "SZSE"  # 深交所
    CFFEX = "CFFEX"  # 中金所
    SHFE = "SHFE"  # 上期所
    DCE = "DCE"  # 大商所
    CZCE = "CZCE"  # 郑商所


@dataclass
class UnifiedMarketData:
    """统一行情数据 - 支持Tick和Bar"""

    symbol: str
    exchange: Exchange
    datetime: "datetime"

    # 价格字段
    last_price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0

    # 成交量
    volume: float = 0.0
    turnover: float = 0.0
    open_interest: float = 0.0

    # 买卖盘
    bid_price_1: float = 0.0
    ask_price_1: float = 0.0
    bid_volume_1: float = 0.0
    ask_volume_1: float = 0.0

    # 元数据
    source: DataSource = DataSource.LOCAL_DB
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_vnpy_tick(cls, tick: Any) -> "UnifiedMarketData":
        """从VnPy Tick转换"""
        return cls(
            symbol=tick.symbol,
            exchange=Exchange(tick.exchange.value),
            datetime=tick.datetime,
            # 价格字段
            last_price=tick.last_price,
            open_price=getattr(tick, "open_price", 0.0),
            high_price=getattr(tick, "high_price", 0.0),
            low_price=getattr(tick, "low_price", 0.0),
            close_price=getattr(tick, "last_price", 0.0),  # Tick一般用last_price
            # 成交量
            volume=tick.volume,
            turnover=getattr(tick, "turnover", 0.0),
            open_interest=getattr(tick, "open_interest", 0.0),
            # 买卖盘
            bid_price_1=getattr(tick, "bid_price_1", 0.0),
            ask_price_1=getattr(tick, "ask_price_1", 0.0),
            bid_volume_1=getattr(tick, "bid_volume_1", 0.0),
            ask_volume_1=getattr(tick, "ask_volume_1", 0.0),
            # 元数据
            source=DataSource.VNPY_CTP,
        )

    @classmethod
    def from_vnpy_bar(cls, bar_data: Any) -> "UnifiedMarketData":
        """从VnPy Bar转换"""
        return cls(
            symbol=bar_data.symbol,
            exchange=Exchange(bar_data.exchange.value),
            datetime=bar_data.datetime,
            # 价格字段
            last_price=bar_data.close_price,  # Bar用close_price作为last_price
            open_price=bar_data.open_price,
            high_price=bar_data.high_price,
            low_price=bar_data.low_price,
            close_price=bar_data.close_price,
            # 成交量
            volume=bar_data.volume,
            turnover=getattr(bar_data, "turnover", 0.0),
            open_interest=getattr(bar_data, "open_interest", 0.0),
            # 元数据
            source=DataSource.VNPY_CTP,
        )

    def to_dict(self) -> Dict:
        """转为字典"""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange.value,
            "datetime": self.datetime.isoformat(),
            # 价格
            "last_price": self.last_price,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            # 成交量
            "volume": self.volume,
            "turnover": self.turnover,
            "open_interest": self.open_interest,
            # 买卖盘
            "bid_price_1": self.bid_price_1,
            "ask_price_1": self.ask_price_1,
            "bid_volume_1": self.bid_volume_1,
            "ask_volume_1": self.ask_volume_1,
            # 元数据
            "source": self.source.value,
        }


@dataclass
class UnifiedOrder:
    """统一订单数据"""

    orderid: str
    symbol: str
    exchange: Exchange
    direction: str  # "LONG" / "SHORT"
    offset: str  # "OPEN" / "CLOSE"
    price: float
    volume: float
    traded: float = 0.0
    status: str = "SUBMITTING"
    datetime: "datetime" = field(default_factory=datetime.now)
    source: DataSource = DataSource.LOCAL_DB


@dataclass
class UnifiedTrade:
    """统一成交数据"""

    tradeid: str
    orderid: str
    symbol: str
    exchange: Exchange
    direction: str
    offset: str
    price: float
    volume: float
    datetime: "datetime"
    source: DataSource = DataSource.LOCAL_DB


@dataclass
class UnifiedPosition:
    """统一持仓数据"""

    symbol: str
    exchange: Exchange
    direction: str
    volume: float
    frozen: float = 0.0
    price: float = 0.0
    pnl: float = 0.0
    datetime: "datetime" = field(default_factory=datetime.now)


@dataclass
class UnifiedAccount:
    """统一账户数据"""

    accountid: str
    balance: float
    frozen: float
    available: float
    datetime: "datetime" = field(default_factory=datetime.now)


@dataclass
class ContractInfo:
    """合约信息"""

    symbol: str
    exchange: Exchange
    name: str
    product: str
    size: float
    pricetick: float
    min_volume: float = 1.0
    margin_rate: float = 0.1


class DataConverter:
    """数据格式转换器"""

    @staticmethod
    def vnpy_to_unified_tick(vnpy_tick) -> UnifiedMarketData:
        """VnPy Tick → 统一格式"""
        return UnifiedMarketData.from_vnpy_tick(vnpy_tick)

    @staticmethod
    def vnpy_to_unified_bar(vnpy_bar) -> UnifiedMarketData:
        """VnPy Bar → 统一格式"""
        return UnifiedMarketData.from_vnpy_bar(vnpy_bar)

    @staticmethod
    def batch_convert(
        data_list: List[Any], source_type: str
    ) -> List[UnifiedMarketData]:
        """批量转换

        Args:
            data_list: 待转换的数据列表
            source_type: 数据源类型，"tick" 或 "bar"

        Returns:
            统一格式数据列表
        """
        result = []
        for data in data_list:
            try:
                if source_type.lower() == "tick":
                    result.append(UnifiedMarketData.from_vnpy_tick(data))
                elif source_type.lower() == "bar":
                    result.append(UnifiedMarketData.from_vnpy_bar(data))
                else:
                    logger.warning("未知的数据源类型: %s", source_type)
            except Exception as e:
                logger.error("转换失败: %s", e)
        return result


# ============================================================================
# Section 2: 配置系统 (行 300-500)
# ============================================================================


@dataclass
class DatabaseConfig:
    """数据库配置"""

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "terminal"
    sqlite_path: str = "data/terminal.db"
    sqlite_timeout: float = 30.0

    def to_connection_string(self) -> str:
        return f"mysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class LoggingConfig:
    """日志配置"""

    level: str = "INFO"
    file_path: str = "logs/terminal.log"
    max_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    format: str = "%(asctime)s [%(levelname)s] %(message)s"


@dataclass
class TradingConfig:
    """交易配置"""

    default_gateway: str = "CTP"
    slippage: float = 1.0
    commission_rate: float = 0.0003
    risk_limit: float = 1000000.0


@dataclass
class AIConfig:
    """AI配置"""
    enabled: bool = False
    provider: str = "deepseek"
    api_key: str = ""
    api_url: str = "https://api.deepseek.com/v1/chat/completions"
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30
    max_history: int = 10
    system_prompt: str = "你是一个专业的量化交易策略编写助手，擅长Python和VnPy框架。"
    enable_tools: bool = False


@dataclass
class APIConfig:
    """API配置"""
    host: str = "localhost"
    port: int = 8080
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    debug: bool = False


@dataclass
class AdaptiveConfig:
    """自适应配置"""
    enabled: bool = True
    baseline_async_concurrency: int = 4
    baseline_thread_concurrency: int = 2
    baseline_process_concurrency: int = 1


@dataclass
class VnPyConfig:
    """VnPy配置"""
    enabled: bool = True
    auto_start: bool = False
    event_engine_enabled: bool = True
    main_engine_enabled: bool = True
    event_engine_timer_interval: float = 1.0
    data_storage_path: str = "data/vnpy"
    recording_data_path: str = "data/recording"
    log_level: str = "INFO"
    log_file: str = "logs/vnpy.log"


@dataclass
class TerminalSettings:
    """终端全局配置"""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    api: APIConfig = field(default_factory=APIConfig)
    vnpy: VnPyConfig = field(default_factory=VnPyConfig)
    app_config: AppConfig = field(default_factory=AppConfig)
    ui_config: UIConfig = field(default_factory=UIConfig)

    # 其他配置项
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    config_file: Optional[str] = None

    def __post_init__(self):
        """确保所有属性都被正确初始化"""
        # 不需要额外的初始化逻辑

    @classmethod
    def load_from_file(cls, filepath: str) -> "TerminalSettings":
        """从文件加载配置"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 解析数据库配置
            db_config = DatabaseConfig(
                host=data.get("database", {}).get("host", "localhost"),
                port=data.get("database", {}).get("port", 3306),
                user=data.get("database", {}).get("user", "root"),
                password=data.get("database", {}).get("password", ""),
                database=data.get("database", {}).get("database", "terminal"),
            )

            # 解析日志配置
            log_config = LoggingConfig(
                level=data.get("logging", {}).get("level", "INFO"),
                file_path=data.get("logging", {}).get("file_path", "logs/terminal.log"),
                max_size=data.get("logging", {}).get("max_size", 10 * 1024 * 1024),
                backup_count=data.get("logging", {}).get("backup_count", 5),
                format=data.get("logging", {}).get(
                    "format", "%(asctime)s [%(levelname)s] %(message)s"
                ),
            )

            # 解析交易配置
            trading_config = TradingConfig(
                default_gateway=data.get("trading", {}).get("default_gateway", "CTP"),
                slippage=data.get("trading", {}).get("slippage", 1.0),
                commission_rate=data.get("trading", {}).get("commission_rate", 0.0003),
                risk_limit=data.get("trading", {}).get("risk_limit", 1000000.0),
            )

            return cls(database=db_config, logging=log_config, trading=trading_config)
        except FileNotFoundError:
            logger.warning("配置文件不存在: %s，使用默认配置", filepath)
            return cls()
        except json.JSONDecodeError as e:
            logger.error("配置文件格式错误: %s，使用默认配置", e)
            return cls()
        except Exception as e:
            logger.error("加载配置失败: %s，使用默认配置", e)
            return cls()

    def save_to_file(self, filepath: str):
        """保存配置到文件"""
        try:
            # 确保目录存在
            from pathlib import Path

            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            # 构造配置字典
            config_dict = {
                "database": {
                    "host": self.database.host,
                    "port": self.database.port,
                    "user": self.database.user,
                    "password": self.database.password,
                    "database": self.database.database,
                },
                "logging": {
                    "level": self.logging.level,
                    "file_path": self.logging.file_path,
                    "max_size": self.logging.max_size,
                    "backup_count": self.logging.backup_count,
                    "format": self.logging.format,
                },
                "trading": {
                    "default_gateway": self.trading.default_gateway,
                    "slippage": self.trading.slippage,
                    "commission_rate": self.trading.commission_rate,
                    "risk_limit": self.trading.risk_limit,
                },
            }

            # 保存到文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)

            logger.info("配置已保存到: %s", filepath)
        except Exception as e:
            logger.error("保存配置失败: %s", e)


class ConfigManager:
    """配置管理器 - 单例"""

    _instance = None
    _settings: Optional[TerminalSettings] = None

    def __init__(self):
        if ConfigManager._instance is not None:
            raise RuntimeError("请使用 ConfigManager.get_instance()")
        self._settings = TerminalSettings()

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self, filepath: str):
        """加载配置"""
        self._settings = TerminalSettings.load_from_file(filepath)
        logger.info("配置已加载: %s", filepath)

    def get_settings(self) -> TerminalSettings:
        """获取配置"""
        if self._settings is None:
            self._settings = TerminalSettings()
        return self._settings

    def update(self, **kwargs):
        """更新配置"""
        if self._settings is None:
            self._settings = TerminalSettings()
        for key, value in kwargs.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)

    @property
    def app_config(self):
        """应用配置"""
        if self._settings is None:
            self._settings = TerminalSettings()
        assert self._settings is not None
        return self._settings.app_config

    @property
    def ui_config(self):
        """UI配置"""
        if self._settings is None:
            self._settings = TerminalSettings()
        assert self._settings is not None
        return self._settings.ui_config

    def save_config(self):
        """保存配置"""
        raise NotImplementedError("配置保存功能尚未实现")


def get_settings() -> TerminalSettings:
    """获取全局配置"""
    return ConfigManager.get_instance().get_settings()


# ============================================================================
# Section 3: 服务抽象 (行 500-700)
# ============================================================================


class ServiceStatus(str, Enum):
    """服务状态"""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ServiceError:
    """服务错误"""

    service_name: str
    error_type: str
    message: str
    severity: str  # "low" / "medium" / "high" / "critical"
    timestamp: datetime = field(default_factory=datetime.now)


class ServiceBase(ABC):
    """服务基类 - 所有业务服务的基类"""

    def __init__(self, name: str):
        self.name = name
        self.status = ServiceStatus.CREATED
        self.logger = logging.getLogger(f"service.{name}")
        self._main_engine: Optional[Any] = None
        self._event_engine: Optional[Any] = None
        self._errors: List[str] = []

    @abstractmethod
    def initialize(self) -> bool:
        """初始化服务"""
        pass  # pylint: disable=unnecessary-pass

    @abstractmethod
    def shutdown(self) -> bool:
        """关闭服务"""
        pass  # pylint: disable=unnecessary-pass

    @abstractmethod
    def get_status(self) -> Dict:
        """获取服务状态"""
        pass  # pylint: disable=unnecessary-pass

    def set_engines(self, main_engine: Any, event_engine: Any):
        """设置VnPy引擎"""
        self._main_engine = main_engine
        self._event_engine = event_engine

    def get_main_engine(self) -> Optional[Any]:
        """获取主引擎"""
        return self._main_engine

    def get_event_engine(self) -> Optional[Any]:
        """获取事件引擎"""
        return self._event_engine

    @property
    def main_engine(self) -> Optional[Any]:
        """获取主引擎（兼容性属性）"""
        return self._main_engine

    @main_engine.setter
    def main_engine(self, value: Optional[Any]):
        """设置主引擎（兼容性属性）"""
        self._main_engine = value

    @property
    def event_engine(self) -> Optional[Any]:
        """获取事件引擎（兼容性属性）"""
        return self._event_engine

    @event_engine.setter
    def event_engine(self, value: Optional[Any]):
        """设置事件引擎（兼容性属性）"""
        self._event_engine = value

    def _log_operation(self, operation: str, **kwargs) -> None:
        """记录操作日志（兼容性方法）"""
        details = ", ".join("%s=%s" % (k, v) for k, v in kwargs.items())
        if details:
            self.logger.info("[%s] %s %s", self.name, operation, details)
        else:
            self.logger.info("[%s] %s", self.name, operation)

    def _log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """记录错误日志（兼容性方法）"""
        error_msg = "%s: %s" % (operation, str(error))
        self._errors.append(error_msg)

        # 限制错误列表大小
        if len(self._errors) > 100:
            self._errors = self._errors[-50:]

        details = ", ".join("%s=%s" % (k, v) for k, v in kwargs.items())
        if details:
            self.logger.error(
                "❌ [%s] %s 失败 - %s",
                self.name,
                operation,
                details,
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )
        else:
            self.logger.error(
                "❌ [%s] %s 失败",
                self.name,
                operation,
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )

    def clear_errors(self):
        """清空错误记录（兼容性方法）"""
        self._errors.clear()

    def get_errors(self, limit: int = 10) -> List[str]:
        """获取最近的错误记录（兼容性方法）"""
        return self._errors[-limit:] if self._errors else []

    def log_operation_start(self, operation: str, **kwargs) -> None:
        """记录操作开始日志（兼容性方法）"""
        params_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        if params_str:
            self.logger.info(f"[开始] {operation} ({params_str})")
        else:
            self.logger.info(f"[开始] {operation}")

    def log_operation_success(self, operation: str, **kwargs) -> None:
        """记录操作成功日志（兼容性方法）"""
        result_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        if result_str:
            self.logger.info(f"[成功] {operation} ({result_str})")
        else:
            self.logger.info(f"[成功] {operation}")

    def log_operation_failure(self, operation: str, error: Exception, **kwargs) -> None:
        """记录操作失败日志（兼容性方法）"""
        context_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        if context_str:
            self.logger.error(
                "❌ [失败] %s: %s (%s)",
                operation,
                str(error),
                context_str,
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )
        else:
            self.logger.error(
                "❌ [失败] %s: %s",
                operation,
                str(error),
                exc_info=True,
                extra={"log_type": "SYSTEM"},
            )

    # 新增方法：数据查询和监控相关
    @property
    def strategy_instances(self) -> Dict[str, Any]:
        """获取策略实例"""
        return getattr(self, '_strategy_instances', {})

    def get_monitoring_data(self) -> Dict[str, Any]:
        """获取监控数据"""
        return {
            "service_name": self.name,
            "status": self.status.value,
            "uptime": getattr(self, '_uptime', 0),
            "error_count": len(self._errors),
        }

    def query_local_data(self, _query: str, **_kwargs) -> Any:
        """查询本地数据"""
        # 基础实现，子类可重写
        self.logger.warning("query_local_data not implemented in base class")
        return None

    def check_data_quality(self, data: Any) -> bool:
        """检查数据质量"""
        # 基础实现，子类可重写
        return data is not None

    def get_index_returns(self, _index_code: str, _start_date: str, _end_date: str) -> Any:
        """获取指数收益率数据"""
        # 基础实现，子类可重写
        self.logger.warning("get_index_returns not implemented in base class")
        return None

    def log_performance(self, operation: str, duration: float, **kwargs) -> None:
        """记录性能日志"""
        context_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        if context_str:
            self.logger.info(
                f"[性能] {operation} 耗时 {duration:.3f}s ({context_str})"
            )
        else:
            self.logger.info(f"[性能] {operation} 耗时 {duration:.3f}s")

    # 业务方法声明（由具体服务类实现）
    def query_historical_data(
        self,
        _symbol: str,
        _start_date: str,
        _end_date: str,
        _interval: str = "1d",
        _check_gaps: bool = False,
    ) -> Any:
        """查询历史数据（基类声明，子类实现）"""
        self.logger.warning("query_historical_data not implemented in base class")
        return None

    def calculate_indicator(
        self, _data: List[float], _indicator_name: str, _params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """计算技术指标（基类声明，子类实现）"""
        self.logger.warning("calculate_indicator not implemented in base class")
        return None

    def detect_data_gaps(
        self,
        _symbol: str,
        _start_date: str,
        _end_date: str,
        _interval: str = "1d"
    ) -> Any:
        """检测数据断点（基类声明，子类实现）"""
        self.logger.warning("detect_data_gaps not implemented in base class")
        return None

    # 新增业务相关方法
    @property
    def is_initialized(self) -> bool:
        """检查服务是否已初始化"""
        return self.status in [ServiceStatus.RUNNING]

    @property
    def api_key(self) -> str:
        """获取API密钥"""
        return getattr(self, '_api_key', '')

    def refresh_symbol_list(self) -> Any:
        """刷新品种列表"""
        # 基础实现，子类可重写
        self.logger.warning("refresh_symbol_list not implemented in base class")
        return []

    def get_all_datafeed_status(self) -> Dict[str, Any]:
        """获取所有数据源状态"""
        # 基础实现，子类可重写
        return {}

    def get_download_task_count(self) -> int:
        """获取下载任务数量"""
        # 基础实现，子类可重写
        return 0

    def list_gateways(self) -> Dict[str, Any]:
        """列出所有网关"""
        # 基础实现，子类可重写
        return {"success": True, "gateways": []}

    def list_portfolios(self) -> Dict[str, Any]:
        """列出所有组合"""
        # 基础实现，子类可重写
        return {"success": True, "portfolios": {"auto_portfolios": [], "custom_portfolios": []}}

    def get_available_strategies(self) -> Dict[str, Any]:
        """获取可用策略列表"""
        # 基础实现，子类可重写
        return {"success": True, "strategies": []}

    @property
    def _backtest_tasks(self) -> List[Any]:
        """获取回测任务列表"""
        return getattr(self, '_backtest_tasks_list', [])


class ServiceRegistry:
    """服务注册表 - 单例"""

    _instance = None

    def __init__(self):
        self._services: Dict[str, ServiceBase] = {}
        self._main_engine: Optional[Any] = None
        self._event_engine: Optional[Any] = None
        self._error_log: List[ServiceError] = []
        self._initialization_attempted: bool = False
        self._initialization_completed: bool = False

    @classmethod
    def get_instance(cls) -> "ServiceRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, service: ServiceBase):
        """注册服务"""
        self._services[service.name] = service
        logger.info("服务已注册: %s", service.name)

    def get(self, name: str) -> Optional[ServiceBase]:
        """获取服务"""
        return self._services.get(name)

    def get_service(self, name: str) -> Optional[ServiceBase]:
        """获取服务（兼容性方法）"""
        return self.get(name)

    def has_service(self, name: str) -> bool:
        """检查服务是否存在"""
        return name in self._services

    def register_service(self, name: str, service: ServiceBase):
        """注册服务（带名称）"""
        self._services[name] = service
        logger.info("服务已注册: %s", name)

    def get_all(self) -> Dict[str, ServiceBase]:
        """获取所有服务"""
        return self._services.copy()

    def initialize_all(self) -> bool:
        """初始化所有服务"""
        success = True
        for service in self._services.values():
            try:
                if not service.initialize():
                    success = False
                    self.log_error(
                        ServiceError(
                            service_name=service.name,
                            error_type="initialization_error",
                            message="Service initialization returned False",
                            severity="high",
                        )
                    )
            except Exception as e:
                success = False
                self.log_error(
                    ServiceError(
                        service_name=service.name,
                        error_type="initialization_error",
                        message=str(e),
                        severity="high",
                    )
                )
        return success

    def shutdown_all(self) -> bool:
        """关闭所有服务"""
        success = True
        for service in reversed(list(self._services.values())):
            try:
                if not service.shutdown():
                    success = False
                    logger.error("关闭服务失败 %s: shutdown returned False", service.name)
            except Exception as e:
                success = False
                logger.error("关闭服务失败 %s: %s", service.name, e)
        return success

    def set_engines(self, main_engine: Any, event_engine: Any):
        """设置全局引擎"""
        self._main_engine = main_engine
        self._event_engine = event_engine
        for service in self._services.values():
            service.set_engines(main_engine, event_engine)

    def log_error(self, error: ServiceError):
        """记录错误"""
        self._error_log.append(error)
        logger.error("服务错误: %s - %s", error.service_name, error.message)

    def get_error_report(self) -> List[ServiceError]:
        """获取错误报告"""
        return self._error_log.copy()

    @property
    def initialization_attempted(self) -> bool:
        """获取初始化尝试状态"""
        return self._initialization_attempted

    @initialization_attempted.setter
    def initialization_attempted(self, value: bool):
        """设置初始化尝试状态"""
        self._initialization_attempted = value

    @property
    def initialization_completed(self) -> bool:
        """获取初始化完成状态"""
        return self._initialization_completed

    @initialization_completed.setter
    def initialization_completed(self, value: bool):
        """设置初始化完成状态"""
        self._initialization_completed = value

    @property
    def services(self) -> Dict[str, ServiceBase]:
        """获取所有服务（兼容性属性）"""
        return self._services.copy()

    def record_error(self, service_name: str, error_type: str, message: str, severity: str = "medium"):
        """记录错误（兼容性方法）"""
        error = ServiceError(
            service_name=service_name,
            error_type=error_type,
            message=message,
            severity=severity,
        )
        self.log_error(error)

    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要（兼容性方法）"""
        error_counts = {}
        for error in self._error_log:
            error_counts[error.severity] = error_counts.get(error.severity, 0) + 1

        return {
            "total_errors": len(self._error_log),
            "error_counts": error_counts,
            "recent_errors": [error.message for error in self._error_log[-5:]],
        }

    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """获取服务状态（兼容性方法）"""
        service = self.get(service_name)
        if service is None:
            return {"status": "not_found"}

        # 尝试获取服务状态信息
        try:
            status_info = service.get_status()
            return status_info
        except AttributeError:
            return {"status": "unknown"}

    def get_user_friendly_error_report(self) -> str:
        """获取用户友好的错误报告（兼容性方法）"""
        if not self._error_log:
            return "所有服务运行正常。"

        summary = self.get_error_summary()
        report_lines = ["服务状态报告:", f"总错误数: {summary['total_errors']}"]

        for severity, count in summary["error_counts"].items():
            report_lines.append(f"{severity}级别错误: {count}个")

        if summary["recent_errors"]:
            report_lines.append("\n最近错误:")
            for error in summary["recent_errors"]:
                report_lines.append(f"- {error}")

        return "\n".join(report_lines)


def get_service_registry() -> ServiceRegistry:
    return ServiceRegistry.get_instance()


def register_service(service: ServiceBase):
    get_service_registry().register(service)


def get_service(name: str) -> Optional[ServiceBase]:
    return get_service_registry().get(name)


# ============================================================================
# Section 4: 核心引擎管理 (行 700-800)
# ============================================================================


class EngineManager:
    """VnPy引擎管理器"""

    _instance = None

    def __init__(self):
        self._main_engine: Optional[Any] = None
        self._event_engine: Optional[Any] = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "EngineManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self):
        """初始化VnPy引擎"""
        if not ensure_vnpy_imported():
            logger.warning("VnPy不可用，引擎无法初始化")
            return False

        try:
            if EventEngine is None or MainEngine is None:
                logger.error("VnPy组件未正确导入")
                return False

            self._event_engine = EventEngine()  # type: ignore
            self._main_engine = MainEngine(self._event_engine)  # type: ignore
            self._initialized = True
            logger.info("✅ VnPy引擎初始化成功")
            return True
        except Exception as e:
            logger.error("VnPy引擎初始化失败: %s", e)
            return False

    def get_main_engine(self) -> Optional[Any]:
        return self._main_engine

    def get_event_engine(self) -> Optional[Any]:
        return self._event_engine

    def shutdown(self):
        """关闭引擎"""
        if self._main_engine:
            self._main_engine.close()
        if self._event_engine:
            self._event_engine.stop()
        self._initialized = False
        logger.info("VnPy引擎已关闭")


def get_main_engine() -> Optional[Any]:
    return EngineManager.get_instance().get_main_engine()


def get_event_engine() -> Optional[Any]:
    return EngineManager.get_instance().get_event_engine()


# ============================================================================
# Section 5: 扩展数据模型 - 数据中心模块
# ============================================================================


@dataclass
class SymbolInfo:
    """品种信息模型

    用于数据中心模块的品种管理
    原始来源: core/models.py#457-472
    """

    id: Optional[str] = None
    symbol: str = ""
    exchange: str = ""
    name: str = ""
    product: str = ""
    size: float = 1.0
    pricetick: float = 0.01
    min_volume: int = 1
    max_volume: int = 1000000
    is_active: bool = True
    listed_date: Optional[datetime] = None
    expired_date: Optional[datetime] = None


@dataclass
class DownloadTask:
    """下载任务模型

    用于数据下载任务管理
    原始来源: core/models.py#474-490
    """

    task_id: str = ""
    symbol: str = ""
    exchange: str = ""
    start_date: datetime = field(default_factory=datetime.now)
    end_date: datetime = field(default_factory=datetime.now)
    data_type: str = "bar"
    frequency: str = "1m"
    status: str = "pending"  # pending/running/completed/failed
    progress: float = 0.0
    total_count: int = 0
    downloaded_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class DataSourceConfig:
    """数据源配置模型

    用于配置和管理多个数据源
    原始来源: core/models.py#493-503
    """

    source_id: str = ""
    source_type: str = ""  # vnpy/tushare/rqdata/tdx
    name: str = ""
    is_enabled: bool = True
    is_connected: bool = False
    config: Dict[str, Any] = field(default_factory=dict)
    last_connected: Optional[datetime] = None
    error_count: int = 0


@dataclass
class GapInfo:
    """数据断点信息模型

    用于记录和修复数据缺失
    原始来源: core/models.py#536-545
    """

    symbol: str = ""
    exchange: str = ""
    gap_start: datetime = field(default_factory=datetime.now)
    gap_end: datetime = field(default_factory=datetime.now)
    gap_type: str = ""  # missing/corrupt/incomplete
    severity: str = "medium"  # low/medium/high/critical
    suggested_action: str = ""


# ============================================================================
# Section 6: 扩展数据模型 - 图表和指标
# ============================================================================


@dataclass
class ChartConfig:
    """图表配置模型

    用于行情看板的图表配置
    原始来源: core/models.py#511-522
    """

    chart_id: str = ""
    symbol: str = ""
    exchange: str = ""
    chart_type: str = "kline"  # kline/line/bar/scatter
    period: str = "1m"
    indicators: List[Dict[str, Any]] = field(default_factory=list)
    overlays: List[Dict[str, Any]] = field(default_factory=list)
    theme: str = "dark"
    auto_refresh: bool = True


@dataclass
class IndicatorConfig:
    """指标配置模型

    用于技术指标的配置
    原始来源: core/models.py#525-533
    """

    indicator_id: str = ""
    name: str = ""
    type: str = ""  # MA/MACD/RSI/BOLL/KDJ等
    parameters: Dict[str, Any] = field(default_factory=dict)
    style: Dict[str, Any] = field(default_factory=dict)
    sub_chart: int = 0  # 0=主图，1+=副图


# ============================================================================
# Section 7: 扩展数据模型 - 策略和回测
# ============================================================================


@dataclass
class StrategyFile:
    """策略文件模型

    用于策略文件管理
    原始来源: core/models.py#553-562
    """

    file_path: str = ""
    file_name: str = ""
    file_type: str = ""  # python/template
    size: int = 0
    modified_time: datetime = field(default_factory=datetime.now)
    strategy_type: Optional[str] = None  # cta/option/algo
    is_valid: bool = True


@dataclass
class BacktestConfig:
    """回测配置模型

    用于回测参数配置
    原始来源: core/models.py#565-578
    """

    backtest_id: str = ""
    strategy_name: str = ""
    symbol: str = ""
    start_date: datetime = field(default_factory=datetime.now)
    end_date: datetime = field(default_factory=datetime.now)
    initial_capital: float = 100000.0
    commission_rate: float = 0.0003
    slippage_rate: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    progress: float = 0.0


@dataclass
class BacktestResult:
    """回测结果模型

    用于存储回测结果
    原始来源: core/models.py#581-595
    """

    backtest_id: str = ""
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    trade_records: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OptimizationConfig:
    """优化配置模型

    用于参数优化配置
    """

    optimization_id: str = ""
    strategy_name: str = ""
    target_metric: str = "sharpe_ratio"  # sharpe_ratio/total_return/max_drawdown
    parameters_range: Dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 100
    parallel_workers: int = 4


# ============================================================================
# Section 8: 扩展数据模型 - 交易网关
# ============================================================================


@dataclass
class GatewayConfig:
    """网关配置模型

    用于交易网关配置
    原始来源: core/models.py#613-624
    """

    gateway_id: str = ""
    gateway_type: str = ""  # CTP/IB/PAPER
    gateway_name: str = ""
    is_active: bool = False
    is_connected: bool = False
    config: Dict[str, Any] = field(default_factory=dict)
    status: str = "disconnected"
    last_connected: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class StrategyInstance:
    """策略实例模型

    用于实盘策略实例管理
    原始来源: core/models.py#627-640
    """

    instance_id: str = ""
    gateway_id: str = ""
    strategy_name: str = ""
    strategy_type: str = ""  # cta/option/algo
    symbol: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = False
    status: str = "stopped"  # stopped/running/paused/error
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


# ============================================================================
# Section 9: 扩展数据模型 - 系统监控
# ============================================================================


@dataclass
class SystemStatus:
    """系统状态模型

    用于系统整体状态监控
    """

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    network_io: Dict[str, int] = field(default_factory=dict)
    process_count: int = 0
    thread_count: int = 0
    uptime_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProcessInfo:
    """进程信息模型

    用于进程监控
    """

    pid: int = 0
    name: str = ""
    status: str = ""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    num_threads: int = 0
    create_time: datetime = field(default_factory=datetime.now)


@dataclass
class AlertConfig:
    """告警配置模型

    用于系统告警配置
    """

    alert_id: str = ""
    alert_type: str = ""  # cpu/memory/disk/network/service
    threshold: float = 80.0
    comparison: str = ">"  # >/</==/>=/<=/!=
    duration_seconds: int = 60
    is_enabled: bool = True
    notification_channels: List[str] = field(default_factory=list)


@dataclass
class NotificationConfig:
    """通知配置模型

    用于告警通知配置
    """

    notification_id: str = ""
    channel_type: str = ""  # email/webhook/sms
    config: Dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = True


# ============================================================================
# Section 10: 扩展数据模型 - 其他业务模型
# ============================================================================


@dataclass
class UserConfig:
    """用户配置模型

    用于用户个性化配置
    """

    user_id: str = ""
    username: str = ""
    preferences: Dict[str, Any] = field(default_factory=dict)
    last_login: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ThemeConfig:
    """主题配置模型

    用于UI主题配置
    """

    theme_id: str = ""
    theme_name: str = "dark"
    colors: Dict[str, str] = field(default_factory=dict)
    fonts: Dict[str, str] = field(default_factory=dict)
    is_custom: bool = False


@dataclass
class AIChatMessage:
    """AI聊天消息模型

    用于AI助手对话
    原始来源: core/models.py#598-605
    """

    message_id: str = ""
    role: str = ""  # user/assistant/system
    content: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Section 11: 模块生命周期系统
# ============================================================================


class ModuleState(str, Enum):
    """模块状态枚举"""

    CREATED = "created"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    RESTARTING = "restarting"


class ModuleEventBus:
    """模块事件总线

    支持模块间事件通信，内部使用Topic → 回调列表模型
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[..., Any]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, payload: Dict[str, Any]):
        """发布事件"""
        async with self._lock:
            callbacks = list(self._subscribers.get(topic, []))
            callbacks.extend(self._subscribers.get("*", []))

        for callback in callbacks:
            try:
                result = callback(topic, payload)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.error("模块事件处理失败 %s: %s", topic, exc, exc_info=True)

    async def subscribe(self, topic: str, callback: Callable[..., Any]):
        """订阅事件"""
        async with self._lock:
            self._subscribers.setdefault(topic, []).append(callback)

    async def unsubscribe(self, topic: str, callback: Callable[..., Any]):
        """取消订阅"""
        async with self._lock:
            callbacks = self._subscribers.get(topic)
            if not callbacks:
                return
            if callback in callbacks:
                callbacks.remove(callback)
            if not callbacks:
                self._subscribers.pop(topic, None)


class ModuleLifecycle:
    """模块生命周期管理器

    管理单个模块的完整生命周期，包括：
    - 状态管理和转换
    - 依赖检查
    - 超时控制
    - 错误恢复
    """

    _TRANSITIONS: Dict[ModuleState, Set[ModuleState]] = {
        ModuleState.CREATED: {ModuleState.INITIALIZING, ModuleState.ERROR},
        ModuleState.INITIALIZING: {
            ModuleState.INITIALIZED,
            ModuleState.ERROR,
        },
        ModuleState.INITIALIZED: {
            ModuleState.STARTING,
            ModuleState.STOPPING,
            ModuleState.ERROR,
        },
        ModuleState.STARTING: {ModuleState.RUNNING, ModuleState.ERROR},
        ModuleState.RUNNING: {
            ModuleState.STOPPING,
            ModuleState.ERROR,
            ModuleState.RESTARTING,
        },
        ModuleState.STOPPING: {ModuleState.STOPPED, ModuleState.ERROR},
        ModuleState.STOPPED: {
            ModuleState.STARTING,
            ModuleState.INITIALIZING,
            ModuleState.ERROR,
        },
        ModuleState.ERROR: {
            ModuleState.RESTARTING,
            ModuleState.STOPPING,
            ModuleState.INITIALIZING,
        },
        ModuleState.RESTARTING: {
            ModuleState.STARTING,
            ModuleState.STOPPING,
            ModuleState.ERROR,
        },
    }

    def __init__(
        self,
        module_name: str,
        event_bus: Optional[ModuleEventBus] = None,
        dependency_resolver: Optional["DependencyResolver"] = None,
        timeout: float = 30.0,
    ):
        self.module_name = module_name
        self.state: ModuleState = ModuleState.CREATED
        self._event_bus = event_bus or ModuleEventBus()
        self._dependency_resolver = dependency_resolver
        self._timeout = timeout
        self._dependencies: List[str] = []
        self._state_history: List[Tuple[datetime, ModuleState]] = [
            (datetime.now(), self.state)
        ]
        self._lock = asyncio.Lock()
        self._state_callbacks: List[
            Callable[[ModuleState, ModuleState], Optional[Awaitable[None]]]
        ] = []
        self._last_error: Optional[Exception] = None

    @property
    def dependencies(self) -> List[str]:
        return list(self._dependencies)

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def last_error(self) -> Optional[Exception]:
        return self._last_error

    def set_dependencies(self, dependencies: List[str]):
        """设置模块依赖"""
        self._dependencies = list(dict.fromkeys(dependencies))
        if self._dependency_resolver:
            self._dependency_resolver.register_module(
                self.module_name, self._dependencies
            )

    def set_dependency_resolver(self, resolver: "DependencyResolver"):
        """注入依赖解析器"""
        self._dependency_resolver = resolver
        if self._dependencies:
            resolver.register_module(self.module_name, self._dependencies)

    def set_timeout(self, timeout: float):
        """更新超时时间"""
        self._timeout = max(0.1, timeout)

    def on_state_change(
        self, callback: Callable[[ModuleState, ModuleState], Awaitable[None]]
    ):
        """注册状态变化回调"""
        self._state_callbacks.append(callback)

    async def initialize(
        self, initializer: Optional[Callable[[], Awaitable[None]]] = None
    ) -> bool:
        """初始化模块"""
        return await self._run_action(
            action=initializer,
            valid_states=(ModuleState.CREATED, ModuleState.STOPPED, ModuleState.ERROR),
            entering_state=ModuleState.INITIALIZING,
            success_state=ModuleState.INITIALIZED,
        )

    async def start(
        self, starter: Optional[Callable[[], Awaitable[None]]] = None
    ) -> bool:
        """启动模块"""
        return await self._run_action(
            action=starter,
            valid_states=(ModuleState.INITIALIZED, ModuleState.STOPPED),
            entering_state=ModuleState.STARTING,
            success_state=ModuleState.RUNNING,
        )

    async def stop(
        self, stopper: Optional[Callable[[], Awaitable[None]]] = None
    ) -> bool:
        """停止模块"""
        return await self._run_action(
            action=stopper,
            valid_states=(
                ModuleState.RUNNING,
                ModuleState.STARTING,
                ModuleState.RESTARTING,
                ModuleState.INITIALIZED,
            ),
            entering_state=ModuleState.STOPPING,
            success_state=ModuleState.STOPPED,
        )

    async def restart(
        self,
        starter: Optional[Callable[[], Awaitable[None]]] = None,
        stopper: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> bool:
        """重启模块"""
        async with self._lock:
            if self.state not in {
                ModuleState.RUNNING,
                ModuleState.ERROR,
                ModuleState.STOPPED,
                ModuleState.INITIALIZED,
            }:
                logger.warning(
                    f"模块 {self.module_name} 当前状态不支持重启: {self.state}"
                )
                return False
            await self._transition(ModuleState.RESTARTING, {"reason": "manual"})

        stop_ok = await self.stop(stopper)
        if not stop_ok:
            return False
        return await self.start(starter)

    def get_state_history(self) -> List[Tuple[datetime, ModuleState]]:
        """获取状态变更历史"""
        return list(self._state_history)

    async def _run_action(
        self,
        action: Optional[Callable[[], Awaitable[None]]],
        valid_states: Tuple[ModuleState, ...],
        entering_state: ModuleState,
        success_state: ModuleState,
    ) -> bool:
        async with self._lock:
            if self.state not in valid_states:
                logger.warning(
                    f"模块 {self.module_name} 当前状态 {self.state} 不允许执行 {entering_state}"
                )
                return False

            if not self._can_transition(entering_state):
                logger.warning(
                    f"模块 {self.module_name} 状态转换非法: {self.state} -> {entering_state}"
                )
                return False

            if self._dependency_resolver:
                if not self._dependency_resolver.validate_dependencies():
                    raise RuntimeError("依赖关系存在循环或未满足条件")
                order = self._dependency_resolver.resolved_order()
                position = {name: idx for idx, name in enumerate(order)}
                module_index = position.get(self.module_name, float("inf"))
                unresolved = [
                    dep
                    for dep in self._dependencies
                    if dep not in position or position[dep] > module_index
                ]
                if unresolved:
                    raise RuntimeError(f"依赖未就绪: {', '.join(unresolved)}")

            await self._transition(entering_state, {"action": entering_state.value})

        try:
            if action:
                if inspect.iscoroutinefunction(action):
                    await asyncio.wait_for(action(), timeout=self._timeout)
                else:
                    result = action()
                    if inspect.isawaitable(result):
                        await asyncio.wait_for(result, timeout=self._timeout)
            await self._transition(success_state, {"action": success_state.value})
            return True
        except asyncio.TimeoutError as exc:
            self._last_error = exc
            await self._transition(
                ModuleState.ERROR, {"error": "timeout", "action": entering_state.value}
            )
            return False
        except Exception as exc:  # pylint: disable=broad-except
            self._last_error = exc
            logger.error("模块 %s 执行动作失败: %s", self.module_name, exc, exc_info=True)
            await self._transition(
                ModuleState.ERROR,
                {"error": str(exc), "action": entering_state.value},
            )
            return False

    def _can_transition(self, target_state: ModuleState) -> bool:
        return target_state in self._TRANSITIONS.get(self.state, set())

    async def _transition(
        self, new_state: ModuleState, metadata: Optional[Dict[str, Any]] = None
    ):
        previous_state = self.state
        self.state = new_state
        timestamp = datetime.now()
        self._state_history.append((timestamp, new_state))
        payload = {
            "module": self.module_name,
            "previous": previous_state.value,
            "current": new_state.value,
            "timestamp": timestamp.isoformat(),
            "metadata": metadata or {},
        }
        await self._event_bus.publish("module.state_changed", payload)
        for callback in self._state_callbacks:
            try:
                result = callback(previous_state, new_state)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    f"状态回调执行失败 {self.module_name}: {exc}", exc_info=True
                )


# ============================================================================
# Section 12: 依赖管理系统
# ============================================================================


class DependencyGraph:
    """依赖关系图

    使用邻接表表示模块间的依赖关系
    """

    def __init__(self):
        self._nodes: Dict[str, Set[str]] = {}
        self._reverse_nodes: Dict[str, Set[str]] = {}

    def add_dependency(self, module: str, depends_on: str):
        """添加依赖关系: module 依赖 depends_on"""
        if module == depends_on:
            raise ValueError("模块不能依赖自身")
        self._nodes.setdefault(module, set()).add(depends_on)
        self._nodes.setdefault(depends_on, set())
        self._reverse_nodes.setdefault(depends_on, set()).add(module)
        self._reverse_nodes.setdefault(module, set())

    def remove_module(self, module: str):
        """移除模块及相关依赖"""
        if module in self._nodes:
            for dependency in self._nodes[module]:
                dependents = self._reverse_nodes.get(dependency, set())
                dependents.discard(module)
            self._nodes.pop(module, None)
        for dependency in list(self._reverse_nodes.get(module, set())):
            deps = self._nodes.get(dependency, set())
            deps.discard(module)
        self._reverse_nodes.pop(module, None)

    def detect_cycles(self) -> List[List[str]]:
        """检测循环依赖，返回所有环"""
        visited: Set[str] = set()
        stack: Set[str] = set()
        cycles: List[List[str]] = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            stack.add(node)
            path.append(node)

            for neighbor in self._nodes.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in stack:
                    index = path.index(neighbor)
                    cycles.append(path[index:].copy())

            stack.remove(node)
            path.pop()

        for node in list(self._nodes.keys()):
            if node not in visited:
                dfs(node, [])

        return cycles

    def topological_sort(self) -> List[str]:
        """拓扑排序，返回模块启动顺序"""
        in_degree: Dict[str, int] = {
            node: len(deps) for node, deps in self._nodes.items()
        }
        for node in self._nodes:
            in_degree.setdefault(node, 0)
        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        order: List[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for dependent in self._reverse_nodes.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(in_degree):
            raise ValueError("检测到循环依赖，无法拓扑排序")

        return order

    def nodes(self) -> List[str]:
        """返回图中所有节点"""
        return list(self._nodes.keys())


class DependencyResolver:
    """依赖解析器

    解析模块依赖关系，生成启动顺序
    """

    def __init__(self):
        self.graph = DependencyGraph()
        self._modules: Dict[str, List[str]] = {}
        self._resolved_cache: Optional[List[str]] = None

    def register_module(self, module: str, dependencies: Optional[List[str]] = None):
        """注册模块及其依赖"""
        dependencies = dependencies or []
        self._modules[module] = list(dict.fromkeys(dependencies))
        self.graph.remove_module(module)
        self.graph._nodes.setdefault(module, set())  # pylint: disable=protected-access
        self.graph._reverse_nodes.setdefault(
            module, set()
        )  # pylint: disable=protected-access
        for dependency in dependencies:
            self.graph.add_dependency(module, dependency)
        self._resolved_cache = None

    def resolve_order(self, modules: Optional[List[str]] = None) -> List[str]:
        """解析启动顺序"""
        order = self.graph.topological_sort()
        if modules is None:
            self._resolved_cache = order
            return order
        filtered = [module for module in order if module in modules]
        self._resolved_cache = filtered
        return filtered

    def validate_dependencies(self) -> bool:
        """验证依赖关系的合法性"""
        cycles = self.graph.detect_cycles()
        if cycles:
            logger.error(
                "检测到循环依赖: %s", " -> ".join(" -> ".join(c) for c in cycles)
            )
            return False
        return True

    def resolved_order(self) -> List[str]:
        """获取最近一次解析的顺序"""
        if self._resolved_cache is None:
            return self.resolve_order()
        return self._resolved_cache


# ============================================================================
# Section 13: 调度系统
# ============================================================================


@dataclass
class CronPattern:
    """Cron模式配置类"""

    minutes: Set[int]
    hours: Set[int]
    days: Set[int]
    months: Set[int]
    weekdays: Set[int]

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.days
            and dt.month in self.months
            and dt.weekday() in self.weekdays
        )


@dataclass
class ScheduledTask:
    """定时任务配置类"""

    name: str
    cron: CronPattern
    func: Callable[..., Any]
    kwargs: Dict[str, Any]
    next_run: datetime
    last_run: Optional[datetime] = None
    enabled: bool = True


class CronScheduler:
    """Cron定时调度器

    支持标准Cron表达式: * * * * * (分/时/日/月/周)
    """

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}
        self._task_history: List[Dict[str, Any]] = []
        self._running = False
        self._runner_task: Optional[asyncio.Task] = None
        self._history_lock = asyncio.Lock()

    def add_task(self, name: str, cron_expr: str, func: Callable[..., Any], **kwargs):
        """添加定时任务"""
        if name in self._tasks:
            raise ValueError(f"任务已存在: {name}")
        pattern = self._parse_cron(cron_expr)
        next_run = self._calculate_next_run(pattern, datetime.now())
        self._tasks[name] = ScheduledTask(
            name=name,
            cron=pattern,
            func=func,
            kwargs=kwargs,
            next_run=next_run,
        )
        logger.info("定时任务已添加: %s -> %s", name, cron_expr)

    def remove_task(self, name: str) -> bool:
        """移除任务"""
        removed = self._tasks.pop(name, None)
        if removed:
            logger.info("定时任务已移除: %s", name)
            return True
        return False

    def start(self):
        """启动调度器"""
        if self._running:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError("CronScheduler 需要在事件循环中启动") from exc
        self._running = True
        self._runner_task = loop.create_task(self._run_loop())
        logger.info("CronScheduler 已启动")

    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
        self._running = False
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            self._runner_task = None
        logger.info("CronScheduler 已停止")

    def get_task_history(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取任务执行历史"""
        if name is None:
            return list(self._task_history)
        return [record for record in self._task_history if record.get("name") == name]

    async def _run_loop(self):
        try:
            while self._running:
                now = datetime.now().replace(second=0, microsecond=0)
                for task in list(self._tasks.values()):
                    if not task.enabled:
                        continue
                    if task.next_run <= now:
                        asyncio.create_task(self._execute_task(task, now))
                        task.last_run = now
                        task.next_run = self._calculate_next_run(
                            task.cron, now + timedelta(minutes=1)
                        )
                await asyncio.sleep(60 - datetime.now().second)
        except asyncio.CancelledError:
            logger.debug("CronScheduler 主循环被取消")
            raise

    async def _execute_task(self, task: ScheduledTask, scheduled_time: datetime):
        record = {
            "name": task.name,
            "scheduled_at": scheduled_time.isoformat(),
            "started_at": datetime.now().isoformat(),
            "status": "running",
            "error": None,
        }
        try:
            result = task.func(**task.kwargs)
            if inspect.isawaitable(result):
                await result
            record["status"] = "success"
        except Exception as exc:  # pylint: disable=broad-except
            record["status"] = "failed"
            record["error"] = str(exc)
            logger.error("定时任务执行失败 %s: %s", task.name, exc, exc_info=True)
        finally:
            record["finished_at"] = datetime.now().isoformat()
            async with self._history_lock:
                self._task_history.append(record)

    def _parse_cron(self, expression: str) -> CronPattern:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(f"Cron 表达式格式错误: {expression}")
        minute, hour, day, month, weekday = parts
        return CronPattern(
            minutes=self._parse_field(minute, 0, 59, "minute"),
            hours=self._parse_field(hour, 0, 23, "hour"),
            days=self._parse_field(day, 1, 31, "day"),
            months=self._parse_field(month, 1, 12, "month"),
            weekdays=self._parse_field(weekday, 0, 6, "weekday"),
        )

    def _parse_field(
        self, field: str, min_value: int, max_value: int, name: str
    ) -> Set[int]:
        values: Set[int] = set()
        for part in field.split(","):
            part = part.strip()
            if part == "*":
                values.update(range(min_value, max_value + 1))
            elif part.startswith("*/"):
                step = int(part[2:])
                values.update(range(min_value, max_value + 1, step))
            elif "-" in part:
                start_str, end_str = part.split("-", 1)
                start = int(start_str)
                end = int(end_str)
                if start > end:
                    raise ValueError(f"Cron 字段范围错误: {field}")
                values.update(range(start, end + 1))
            else:
                value = int(part)
                if value < min_value or value > max_value:
                    raise ValueError(f"Cron 字段超出范围 {name}: {value}")
                values.add(value)
        if not values:
            raise ValueError(f"Cron 字段无有效数值: {field}")
        return values

    def _calculate_next_run(self, pattern: CronPattern, start: datetime) -> datetime:
        candidate = start.replace(second=0, microsecond=0)
        for _ in range(525600):  # up to one year
            if pattern.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise RuntimeError("无法在一年内计算下次运行时间，请检查 Cron 表达式")


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # VnPy
    "ensure_vnpy_imported",
    "VNPY_AVAILABLE",
    "PANDAS_AVAILABLE",
    "NUMPY_AVAILABLE",
    "MainEngine",
    "EventEngine",
    "Event",
    "TickData",
    "BarData",
    "OrderData",
    "TradeData",
    "PositionData",
    "AccountData",
    "EVENT_TICK",
    "EVENT_ORDER",
    "EVENT_TRADE",
    "EVENT_POSITION",
    "EVENT_ACCOUNT",
    "EVENT_LOG",
    "pd",
    "np",
    # 数据模型
    "UnifiedMarketData",
    "UnifiedOrder",
    "UnifiedTrade",
    "UnifiedPosition",
    "UnifiedAccount",
    "ContractInfo",
    "Exchange",
    "DataSource",
    "DataConverter",
    # 配置
    "TerminalSettings",
    "DatabaseConfig",
    "LoggingConfig",
    "TradingConfig",
    "ConfigManager",
    "get_settings",
    # 服务
    "ServiceBase",
    "ServiceStatus",
    "ServiceError",
    "ServiceRegistry",
    "get_service_registry",
    "register_service",
    "get_service",
    # 引擎
    "EngineManager",
    "get_main_engine",
    "get_event_engine",
    # 扩展数据模型 - 数据中心模块
    "SymbolInfo",
    "DownloadTask",
    "DataSourceConfig",
    "GapInfo",
    # 扩展数据模型 - 图表和指标
    "ChartConfig",
    "IndicatorConfig",
    # 扩展数据模型 - 策略和回测
    "StrategyFile",
    "BacktestConfig",
    "BacktestResult",
    "OptimizationConfig",
    # 扩展数据模型 - 交易网关
    "GatewayConfig",
    "StrategyInstance",
    # 扩展数据模型 - 系统监控
    "SystemStatus",
    "ProcessInfo",
    "AlertConfig",
    "NotificationConfig",
    # 扩展数据模型 - 其他
    "UserConfig",
    "ThemeConfig",
    "AIChatMessage",
    # 模块生命周期系统
    "ModuleState",
    "ModuleEventBus",
    "ModuleLifecycle",
    # 依赖管理系统
    "DependencyGraph",
    "DependencyResolver",
    # 调度系统
    "CronScheduler",
]
