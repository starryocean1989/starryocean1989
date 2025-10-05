# -*- coding: utf-8 -*-
"""
星辰金融终端 - 核心模块包.

提供统一的架构支撑和服务集成
"""

__version__ = "1.0.0"
__author__ = "星辰科技"

# 导出核心模块
from .imports import (
    AlgoEngine, Any, CtaEngine, CtpGateway, DataAPI, DataManager,
    Dict, IbGateway, IntegrationManager, List, MiniGateway,
    ModuleAvailability, Optional, PortfolioEngine, ProcessManager,
    QApplication, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QSplitter, QTabWidget, QTableWidget,
    QVBoxLayout, QWidget, Qt, RqdataDatafeed, Signal, SystemMonitor,
    ThreadPoolExecutor, Tuple, TushareDatafeed, Union, asyncio,
    check_module_availability, datetime, json, np, os, pd, plt,
    psutil, pymongo, requests, safe_import, setup_logging, sns,
    sqlite3, sys, threading, time, traceback, vnpy_to_pandas
)
from .models import (
    DataCategory, DataMetadata, DataModelManager, DataSource,
    UnifiedAccount, UnifiedMarketData, UnifiedOrder, UnifiedPosition,
    UnifiedTrade, get_data_model_manager, reset_data_model_manager
)
from .monitoring import (
    HealthChecker, MonitoringManager, PerformanceMonitor, TestRunner
)
from .performance import (
    AsyncDataProcessor, AsyncTaskManager, Cache, DataCache,
    PerformanceOptimizer, get_performance_optimizer,
    reset_performance_optimizer
)
from .shared_services import (
    ConfigService, LoggingService, MonitoringService
)
from .vnpy_integration import (
    AccountData, BarData, EVENT_ACCOUNT, EVENT_LOG, EVENT_ORDER,
    EVENT_POSITION, EVENT_TICK, EVENT_TRADE, Event, EventEngine,
    MainEngine, OrderData, PositionData, TerminalEngine, TickData,
    TradeData, VNPY_AVAILABLE, get_terminal_engine, reset_terminal_engine
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
