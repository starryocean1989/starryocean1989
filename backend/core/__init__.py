# -*- coding: utf-8 -*-
"""
Backend核心模块.

提供后端核心功能，包括VnPy集成、数据模型、服务管理等。
注意：不导出任何UI组件，保持后端纯净。
"""

__version__ = "1.0.0"
__author__ = "星辰科技"

# 基础导入
from .imports import (
    # 标准库
    os,
    sys,
    json,
    time,
    datetime,
    traceback,
    asyncio,
    threading,
    sqlite3,
    logging,
    Path,
    ThreadPoolExecutor,
    # 类型
    Dict,
    List,
    Optional,
    Any,
    Union,
    Tuple,
    # 网络
    requests,
    # 数据处理
    pd,
    np,
    PANDAS_AVAILABLE,
    NUMPY_AVAILABLE,
    # 系统
    psutil,
    PSUTIL_AVAILABLE,
    # VnPy核心
    VNPY_AVAILABLE,
    MainEngine,
    EventEngine,
    Event,
    TickData,
    BarData,
    OrderData,
    TradeData,
    PositionData,
    AccountData,
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION,
    EVENT_ACCOUNT,
    EVENT_LOG,
    # VnPy策略引擎
    CtaEngine,
    AlgoEngine,
    PortfolioEngine,
    CTA_ENGINE_AVAILABLE,
    ALGO_ENGINE_AVAILABLE,
    PORTFOLIO_ENGINE_AVAILABLE,
    # VnPy网关
    CtpGateway,
    IbGateway,
    PaperAccountGateway,
    CTP_GATEWAY_AVAILABLE,
    IB_GATEWAY_AVAILABLE,
    PAPERACCOUNT_GATEWAY_AVAILABLE,
    # VnPy数据源
    TushareDatafeed,
    RqdataDatafeed,
    TUSHARE_DATAFEED_AVAILABLE,
    RQDATA_DATAFEED_AVAILABLE,
    # Infrastructure
    SystemMonitor,
    ProcessManager,
    SYSTEM_MODULE_AVAILABLE,
    # 工具函数
    setup_logging,
    vnpy_to_pandas,
)

# 数据模型
from .models import (
    DataCategory,
    DataSource,
    DataMetadata,
    UnifiedMarketData,
    UnifiedOrder,
    UnifiedTrade,
    UnifiedPosition,
    UnifiedAccount,
    DataModelManager,
    get_data_model_manager,
    reset_data_model_manager,
)

# 共享服务
from .shared_services import (
    ServiceManager,
    ErrorSeverity,
    get_service_manager,
    get_main_engine,
    get_event_engine,
    get_china_stock_engine,
)

# 性能优化
from .performance import (
    Cache,
    DataCache,
    AsyncTaskManager,
    PerformanceOptimizer,
    AsyncDataProcessor,
    get_performance_optimizer,
    reset_performance_optimizer,
)

# 监控
from .monitoring import (
    PerformanceMonitor,
    HealthChecker,
    MonitoringManager,
    TestRunner,
)

# 数据库
from .database import DatabaseManager

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    # 标准库
    "os",
    "sys",
    "json",
    "time",
    "datetime",
    "traceback",
    "asyncio",
    "threading",
    "sqlite3",
    "logging",
    "Path",
    "ThreadPoolExecutor",
    "requests",
    # 类型
    "Dict",
    "List",
    "Optional",
    "Any",
    "Union",
    "Tuple",
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
    "CtaEngine",
    "AlgoEngine",
    "PortfolioEngine",
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
    "TushareDatafeed",
    "RqdataDatafeed",
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
    # 性能优化
    "Cache",
    "DataCache",
    "AsyncTaskManager",
    "PerformanceOptimizer",
    "AsyncDataProcessor",
    "get_performance_optimizer",
    "reset_performance_optimizer",
    # 监控
    "PerformanceMonitor",
    "HealthChecker",
    "MonitoringManager",
    "TestRunner",
    # 数据库
    "DatabaseManager",
]
