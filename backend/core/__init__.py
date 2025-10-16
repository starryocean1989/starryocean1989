# -*- coding: utf-8 -*-
"""
Backend核心模块.

提供后端核心功能，包括VnPy集成、数据模型、服务管理等。
注意：不导出任何UI组件，保持后端纯净。
"""

__version__ = "1.0.0"
__author__ = "星辰科技"

# 基础模块导入（仅导出在__all__中的）

# 第三方库导入（避免循环导入）
import requests

# 数据处理库
try:
    import numpy as np
    import pandas as pd

    PANDAS_AVAILABLE = True
    NUMPY_AVAILABLE = True
except ImportError:
    pd = None
    np = None
    PANDAS_AVAILABLE = False
    NUMPY_AVAILABLE = False

# 系统监控
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

# 基础导入
from .base import (
    ALGO_ENGINE_AVAILABLE,
    AccountData,
    ALGO_ENGINE,
    BarData,
    CTA_ENGINE_AVAILABLE,
    CTP_GATEWAY_AVAILABLE,
    CTA_ENGINE,
    CtpGateway,
    EVENT_ACCOUNT,
    EVENT_LOG,
    EVENT_ORDER,
    EVENT_POSITION,
    EVENT_TICK,
    EVENT_TRADE,
    Event,
    EventEngine,
    IB_GATEWAY_AVAILABLE,
    IbGateway,
    MainEngine,
    OrderData,
    PAPERACCOUNT_GATEWAY_AVAILABLE,
    PORTFOLIO_ENGINE_AVAILABLE,
    PaperAccountGateway,
    PORTFOLIO_ENGINE,
    PositionData,
    ProcessManager,
    RQDATA_DATAFEED_AVAILABLE,
    RQDATA_DATAFEED,
    SYSTEM_MODULE_AVAILABLE,
    SystemMonitor,
    TUSHARE_DATAFEED_AVAILABLE,
    TickData,
    TradeData,
    TUSHARE_DATAFEED,
    VNPY_AVAILABLE,
    setup_logging,
    vnpy_to_pandas,
)
from .models import (
    DataCategory,
    DataMetadata,
    DataModelManager,
    DataSource,
    UnifiedAccount,
    UnifiedMarketData,
    UnifiedOrder,
    UnifiedPosition,
    UnifiedTrade,
    get_data_model_manager,
    reset_data_model_manager,
)
from .base import (
    ErrorSeverity,
    ServiceManager,
    get_china_stock_engine,
    get_event_engine,
    get_main_engine,
    get_service_manager,
)
# Cache和DataCache已迁移到utils.py
from .utils import Cache, DataCache

# 配置管理
from .config import (
    Settings,
    get_settings,
    DatabaseConfig,
    VnPyConfig,
    APIConfig,
    AIConfig,
    DataModuleConfig,
)

# 数据仓库
from .repositories import (
    BaseRepository,
    InMemoryRepository,
    SymbolRepository,
    DataSourceRepository,
    DownloadTaskRepository,
    GatewayRepository,
    StrategyRepository,
    BacktestRepository,
    AlertRepository,
    LogRepository,
    ConfigRepository,
    PortfolioRepository,
)

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    # 第三方库
    "requests",
    # 数据处理
    "pd",
    "np",
    "PANDAS_AVAILABLE",
    "NUMPY_AVAILABLE",
    # 系统
    "psutil",
    "PSUTIL_AVAILABLE",
    # VnPy核心
    "VNPY_AVAILABLE",
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
    # VnPy策略引擎
    "CTA_ENGINE",
    "ALGO_ENGINE",
    "PORTFOLIO_ENGINE",
    "CTA_ENGINE_AVAILABLE",
    "ALGO_ENGINE_AVAILABLE",
    "PORTFOLIO_ENGINE_AVAILABLE",
    # VnPy网关
    "CtpGateway",
    "IbGateway",
    "PaperAccountGateway",
    "CTP_GATEWAY_AVAILABLE",
    "IB_GATEWAY_AVAILABLE",
    "PAPERACCOUNT_GATEWAY_AVAILABLE",
    # VnPy数据源
    "TUSHARE_DATAFEED",
    "RQDATA_DATAFEED",
    "TUSHARE_DATAFEED_AVAILABLE",
    "RQDATA_DATAFEED_AVAILABLE",
    # Infrastructure
    "SystemMonitor",
    "ProcessManager",
    "SYSTEM_MODULE_AVAILABLE",
    # 工具函数
    "setup_logging",
    "vnpy_to_pandas",
    # 数据模型
    "DataCategory",
    "DataSource",
    "DataMetadata",
    "UnifiedMarketData",
    "UnifiedOrder",
    "UnifiedTrade",
    "UnifiedPosition",
    "UnifiedAccount",
    "DataModelManager",
    "get_data_model_manager",
    "reset_data_model_manager",
    # 共享服务
    "ServiceManager",
    "ErrorSeverity",
    "get_service_manager",
    "get_main_engine",
    "get_event_engine",
    "get_china_stock_engine",
    # 缓存系统
    "Cache",
    "DataCache",
    # 配置管理
    "Settings",
    "get_settings",
    "DatabaseConfig",
    "VnPyConfig",
    "APIConfig",
    "AIConfig",
    "DataModuleConfig",
    # 数据仓库
    "BaseRepository",
    "InMemoryRepository",
    "SymbolRepository",
    "DataSourceRepository",
    "DownloadTaskRepository",
    "GatewayRepository",
    "StrategyRepository",
    "BacktestRepository",
    "AlertRepository",
    "LogRepository",
    "ConfigRepository",
    "PortfolioRepository",
]
