# -*- coding: utf-8 -*-
"""
Backend主模块.

提供统一的后端服务入口。
"""

__version__ = "1.0.0"
__author__ = "星辰科技"

# 导出核心模块
from .core import (
    # VnPy集成
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
    # 共享服务
    ServiceManager,
    ErrorSeverity,
    get_service_manager,
    get_main_engine,
    get_event_engine,
    get_china_stock_engine,
    # 数据模型
    DataModelManager,
    get_data_model_manager,
    # 数据库
    DatabaseManager,
    # 工具
    setup_logging,
)

# 导出服务
from .modules.data_center.service import DataCenterService
from .modules.market_board.service import MarketBoardService
from .modules.portfolio.service import PortfolioService
from .modules.strategy_center.service import StrategyCenterService
from .modules.strategy_center.ai_assistant import AIAssistantService
from .modules.system_manager.service import SystemManagerService
from .modules.trading_gateway.service import TradingGatewayService

# 导出仓库
from .repositories import (
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

# 导出工具
from .core.utils import (
    success_response,
    error_response,
    validate_required_fields,
    SimpleCache,
)

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
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
    # 服务管理
    "ServiceManager",
    "ErrorSeverity",
    "get_service_manager",
    "get_main_engine",
    "get_event_engine",
    "get_china_stock_engine",
    # 数据库
    "DatabaseManager",
    "DataModelManager",
    "get_data_model_manager",
    # 业务服务
    "DataCenterService",
    "MarketBoardService",
    "PortfolioService",
    "StrategyCenterService",
    "AIAssistantService",
    "SystemManagerService",
    "TradingGatewayService",
    # 数据仓库
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
    # 工具函数
    "success_response",
    "error_response",
    "validate_required_fields",
    "SimpleCache",
    "setup_logging",
]
