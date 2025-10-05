# -*- coding: utf-8 -*-
"""
星辰金融终端 - 核心模块包
提供统一的架构支撑和服务集成
"""

__version__ = "1.0.0"
__author__ = "星辰科技"

# 导出核心模块
from .vnpy_integration import (
    TerminalEngine, MainEngine, EventEngine, Event,
    TickData, BarData, OrderData, TradeData,
    PositionData, AccountData,
    EVENT_TICK, EVENT_ORDER, EVENT_TRADE,
    EVENT_POSITION, EVENT_ACCOUNT, EVENT_LOG,
    get_terminal_engine, reset_terminal_engine,
    VNPY_AVAILABLE
)

from .imports import (
    # 系统模块
    os, sys, json, time, datetime, traceback,
    asyncio, threading, requests, ThreadPoolExecutor,

    # 数据处理
    pd, np, plt, sns,

    # 系统监控
    psutil,

    # GUI组件
    QWidget, QApplication, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMainWindow, QTabWidget,
    QTableWidget, QHeaderView, QSplitter, QSizePolicy,
    Qt, Signal,

    # VNPY引擎和网关
    CtaEngine, AlgoEngine, PortfolioEngine,
    CtpGateway, MiniGateway, IbGateway,

    # VNPY数据源
    TushareDatafeed, RqdataDatafeed,

    # 本地模块
    DataManager, DataAPI, IntegrationManager,
    SystemMonitor, ProcessManager,

    # 工具函数
    setup_logging, check_module_availability, safe_import,
    vnpy_to_pandas, ModuleAvailability,

    # 数据库
    sqlite3, pymongo,

    # 类型注解
    Dict, List, Optional, Any, Union, Tuple
)

from .models import (
    DataCategory, DataSource,
    DataMetadata, UnifiedMarketData, UnifiedOrder,
    UnifiedTrade, UnifiedPosition, UnifiedAccount,
    DataModelManager,
    get_data_model_manager, reset_data_model_manager
)

from .performance import (
    Cache, DataCache, AsyncTaskManager,
    PerformanceOptimizer, AsyncDataProcessor,
    get_performance_optimizer, reset_performance_optimizer
)

from .monitoring import (
    PerformanceMonitor, TestRunner, HealthChecker, MonitoringManager
)

from .shared_services import (
    ConfigService, LoggingService, MonitoringService
)

# 包信息
__all__ = [
    # 版本信息
    '__version__', '__author__',

    # VNPY集成
    'TerminalEngine', 'MainEngine', 'EventEngine', 'Event',
    'TickData', 'BarData', 'OrderData', 'TradeData',
    'PositionData', 'AccountData',
    'EVENT_TICK', 'EVENT_ORDER', 'EVENT_TRADE',
    'EVENT_POSITION', 'EVENT_ACCOUNT', 'EVENT_LOG',
    'get_terminal_engine', 'reset_terminal_engine',
    'VNPY_AVAILABLE',

    # 统一导入
    'os', 'sys', 'json', 'time', 'datetime', 'traceback',
    'asyncio', 'threading', 'requests', 'ThreadPoolExecutor',
    'pd', 'np', 'plt', 'sns', 'psutil',
    'QWidget', 'QApplication', 'QVBoxLayout', 'QHBoxLayout',
    'QLabel', 'QPushButton', 'QMainWindow', 'QTabWidget',
    'QTableWidget', 'QHeaderView', 'QSplitter', 'QSizePolicy',
    'Qt', 'Signal',
    'CtaEngine', 'AlgoEngine', 'PortfolioEngine',
    'CtpGateway', 'MiniGateway', 'IbGateway',
    'TushareDatafeed', 'RqdataDatafeed',
    'DataManager', 'DataAPI', 'IntegrationManager',
    'SystemMonitor', 'PerformanceOptimizer', 'ProcessManager',
    'setup_logging', 'check_module_availability', 'safe_import',
    'vnpy_to_pandas', 'ModuleAvailability',
    'sqlite3', 'pymongo',
    'Dict', 'List', 'Optional', 'Any', 'Union', 'Tuple',

    # 统一数据模型
    'DataCategory', 'DataSource',
    'DataMetadata', 'UnifiedMarketData', 'UnifiedOrder',
    'UnifiedTrade', 'UnifiedPosition', 'UnifiedAccount',
    'DataModelManager',
    'get_data_model_manager', 'reset_data_model_manager',

    # 性能优化
    'Cache', 'DataCache', 'AsyncTaskManager',
    'PerformanceOptimizer', 'AsyncDataProcessor',
    'get_performance_optimizer', 'reset_performance_optimizer',

    # 监控和测试
    'PerformanceMonitor', 'TestRunner', 'HealthChecker', 'MonitoringManager',

    # 共享服务
    'ConfigService', 'LoggingService', 'MonitoringService'
]
