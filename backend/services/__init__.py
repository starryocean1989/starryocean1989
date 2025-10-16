# -*- coding: utf-8 -*-
"""
Backend功能模块.

按6个功能界面组织的业务服务模块（扁平化结构）。
"""

# 导出主要服务类
from .system_manager_service import SystemManagerService
from .data_center_service import DataCenterService
from .market_board_service import MarketBoardService
from .strategy_center_service import StrategyCenterService
from .ai_assistant_service import AIAssistantService
from .trading_gateway_service import TradingGatewayService
from .portfolio_service import PortfolioService

# 导出database_adapter
from .database_adapter import DatabaseManager, get_db_manager

# 导出vnpy_imports中常用的类和函数
from .vnpy_imports import (
    # VnPy核心
    MainEngine,
    EventEngine,
    Event,
    # 数据类型
    TickData,
    BarData,
    OrderData,
    TradeData,
    PositionData,
    AccountData,
    # 事件类型
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION,
    EVENT_ACCOUNT,
    EVENT_LOG,
    # 数据处理
    pd,
    np,
    # 可用性标志
    VNPY_AVAILABLE,
    PANDAS_AVAILABLE,
    NUMPY_AVAILABLE,
)

__all__ = [
    # 主要服务
    "SystemManagerService",
    "DataCenterService",
    "MarketBoardService",
    "StrategyCenterService",
    "AIAssistantService",
    "TradingGatewayService",
    "PortfolioService",
    # 数据库适配器
    "DatabaseManager",
    "get_db_manager",
    # VnPy核心
    "MainEngine",
    "EventEngine",
    "Event",
    # VnPy数据类型
    "TickData",
    "BarData",
    "OrderData",
    "TradeData",
    "PositionData",
    "AccountData",
    # VnPy事件
    "EVENT_TICK",
    "EVENT_ORDER",
    "EVENT_TRADE",
    "EVENT_POSITION",
    "EVENT_ACCOUNT",
    "EVENT_LOG",
    # 数据处理
    "pd",
    "np",
    # 可用性标志
    "VNPY_AVAILABLE",
    "PANDAS_AVAILABLE",
    "NUMPY_AVAILABLE",
]
