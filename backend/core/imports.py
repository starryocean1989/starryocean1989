# -*- coding: utf-8 -*-
"""
统一导入管理模块.

减少重复导入，提升代码复用性和维护性。
"""

import asyncio
import datetime
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# 数据处理模块
try:
    import pandas as pd
    import numpy as np

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None
    np = None

# 科学计算和可视化
try:
    import matplotlib.pyplot as plt
    import seaborn as sns

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    sns = None

# 系统监控
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

# 网络和并发
import requests

# GUI框架（可选）
try:
    from PySide6.QtWidgets import (
        QWidget,
        QApplication,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QMainWindow,
        QTabWidget,
        QTableWidget,
        QHeaderView,
        QSplitter,
        QSizePolicy,
    )
    from PySide6.QtCore import Qt, Signal

    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False
    # 不创建存根类，使用条件导入模式


# VNPY核心模块
from .vnpy_integration import (
    AccountData,
    BarData,
    EVENT_ACCOUNT,
    EVENT_LOG,
    EVENT_ORDER,
    EVENT_POSITION,
    EVENT_TICK,
    EVENT_TRADE,
    Event,
    EventEngine,
    MainEngine,
    OrderData,
    PositionData,
    TerminalEngine,
    TickData,
    TradeData,
    VNPY_AVAILABLE,
)

# VNPY策略引擎
try:
    if VNPY_AVAILABLE:
        from vnpy_ctastrategy import CtaEngine

        CTA_ENGINE_AVAILABLE = True
    else:
        CTA_ENGINE_AVAILABLE = False
        CtaEngine = None  # pylint: disable=invalid-name
except ImportError:
    CTA_ENGINE_AVAILABLE = False
    CtaEngine = None  # pylint: disable=invalid-name

try:
    if VNPY_AVAILABLE:
        from vnpy_algotrading import AlgoEngine

        ALGO_ENGINE_AVAILABLE = True
    else:
        ALGO_ENGINE_AVAILABLE = False
        AlgoEngine = None  # pylint: disable=invalid-name
except ImportError:
    ALGO_ENGINE_AVAILABLE = False
    AlgoEngine = None  # pylint: disable=invalid-name

try:
    if VNPY_AVAILABLE:
        from vnpy_portfoliostrategy import (
            StrategyEngine as PortfolioEngine,
        )  # noqa: F401

        PORTFOLIO_ENGINE_AVAILABLE = True
    else:
        PORTFOLIO_ENGINE_AVAILABLE = False
        PortfolioEngine = None  # pylint: disable=invalid-name
except ImportError:
    PORTFOLIO_ENGINE_AVAILABLE = False
    PortfolioEngine = None  # pylint: disable=invalid-name

# VNPY网关
try:
    if VNPY_AVAILABLE:
        from vnpy_ctp import CtpGateway

        CTP_GATEWAY_AVAILABLE = True
    else:
        CTP_GATEWAY_AVAILABLE = False
        CtpGateway = None  # pylint: disable=invalid-name
except ImportError:
    CTP_GATEWAY_AVAILABLE = False
    CtpGateway = None  # pylint: disable=invalid-name

# vnpy_mini 模块不存在，已移除
MINI_GATEWAY_AVAILABLE = False
MiniGateway = None  # pylint: disable=invalid-name

try:
    if VNPY_AVAILABLE:
        from vnpy_ib import IbGateway

        IB_GATEWAY_AVAILABLE = True
    else:
        IB_GATEWAY_AVAILABLE = False
        IbGateway = None  # pylint: disable=invalid-name
except ImportError:
    IB_GATEWAY_AVAILABLE = False
    IbGateway = None  # pylint: disable=invalid-name

# VNPY数据源
try:
    if VNPY_AVAILABLE:
        from vnpy_tushare import TushareDatafeed  # type: ignore

        TUSHARE_DATAFEED_AVAILABLE = True
    else:
        TUSHARE_DATAFEED_AVAILABLE = False
        TushareDatafeed = None  # pylint: disable=invalid-name
except ImportError:
    TUSHARE_DATAFEED_AVAILABLE = False
    TushareDatafeed = None  # pylint: disable=invalid-name

try:
    if VNPY_AVAILABLE:
        from vnpy_rqdata import RqdataDatafeed  # type: ignore

        RQDATA_DATAFEED_AVAILABLE = True
    else:
        RQDATA_DATAFEED_AVAILABLE = False
        RqdataDatafeed = None  # pylint: disable=invalid-name
except ImportError:
    RQDATA_DATAFEED_AVAILABLE = False
    RqdataDatafeed = None  # pylint: disable=invalid-name

# 本地数据模块
try:
    from ..infrastructure.data_module_vnpy.data_manager import DataManager
    from ..infrastructure.data_module_vnpy.data_api import DataAPI
    from ..infrastructure.data_module_vnpy.integration_manager import (
        VnPyIntegrationManager as IntegrationManager,
    )

    DATA_MODULE_AVAILABLE = True
except ImportError:
    DATA_MODULE_AVAILABLE = False
    DataManager = None
    DataAPI = None
    IntegrationManager = None

# 系统模块
try:
    from ..infrastructure.system_vnpy.system_monitor import SystemMonitor
    from ..infrastructure.system_vnpy.performance_optimizer import (
        CacheManager,
        MemoryOptimizer,
        ConcurrencyOptimizer,
    )  # noqa: F401
    from ..infrastructure.system_vnpy.process_manager import ProcessManager

    SYSTEM_MODULE_AVAILABLE = True
except ImportError:
    SYSTEM_MODULE_AVAILABLE = False
    SystemMonitor = None
    CacheManager = None
    MemoryOptimizer = None
    ConcurrencyOptimizer = None
    ProcessManager = None

# 工具模块
try:
    from ..infrastructure.data_engine.utils import (
        setup_logging as engine_setup_logging,  # noqa: F401
        validate_symbol,  # noqa: F401
        format_datetime,  # noqa: F401
    )

    DATA_ENGINE_UTILS_AVAILABLE = True
except ImportError:
    DATA_ENGINE_UTILS_AVAILABLE = False

# 图表和可视化
try:
    import pyqtgraph  # noqa: F401  # pylint: disable=unused-import

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

# 数据库和存储
try:
    import sqlite3
    import pymongo

    SQLITE_AVAILABLE = True
    MONGODB_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False
    MONGODB_AVAILABLE = False
    sqlite3 = None
    pymongo = None


# 常量定义 - 模块可用性
class ModuleAvailability:
    """模块可用性常量."""

    def __init__(self):
        """初始化常量类以避免pylint警告."""
        # 无需初始化，常量类。

    # 系统模块
    PANDAS = PANDAS_AVAILABLE
    NUMPY = PANDAS_AVAILABLE and np is not None
    MATPLOTLIB = MATPLOTLIB_AVAILABLE
    PSUTIL = PSUTIL_AVAILABLE
    PYSIDE6 = PYSIDE6_AVAILABLE
    PYQTGRAPH = PYQTGRAPH_AVAILABLE

    # VNPY模块
    VNPY = VNPY_AVAILABLE
    CTA_ENGINE = CTA_ENGINE_AVAILABLE
    ALGO_ENGINE = ALGO_ENGINE_AVAILABLE
    PORTFOLIO_ENGINE = PORTFOLIO_ENGINE_AVAILABLE

    # 网关模块
    CTP_GATEWAY = CTP_GATEWAY_AVAILABLE
    MINI_GATEWAY = MINI_GATEWAY_AVAILABLE
    IB_GATEWAY = IB_GATEWAY_AVAILABLE

    # 数据源模块
    TUSHARE_DATAFEED = TUSHARE_DATAFEED_AVAILABLE
    RQDATA_DATAFEED = RQDATA_DATAFEED_AVAILABLE

    # 本地模块
    DATA_MODULE = DATA_MODULE_AVAILABLE
    SYSTEM_MODULE = SYSTEM_MODULE_AVAILABLE

    @classmethod
    def is_module_available(cls, module_name: str) -> bool:
        """检查模块是否可用."""
        return getattr(cls, module_name.upper(), False)

    # 数据库模块
    SQLITE = SQLITE_AVAILABLE
    MONGODB = MONGODB_AVAILABLE

    @classmethod
    def get_available_modules(cls) -> list:
        """获取所有可用模块的列表."""
        available = []
        for attr_name in dir(cls):
            if not attr_name.startswith("_"):
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, bool) and attr_value:
                    available.append(attr_name.lower())
        return available

    @classmethod
    def get_unavailable_modules(cls) -> list:
        """获取所有不可用模块的列表."""
        unavailable = []
        for attr_name in dir(cls):
            if not attr_name.startswith("_"):
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, bool) and not attr_value:
                    unavailable.append(attr_name.lower())
        return unavailable


def check_module_availability() -> Dict[str, bool]:
    """检查所有模块的可用性."""
    return {
        "pandas": PANDAS_AVAILABLE,
        "numpy": PANDAS_AVAILABLE and np is not None,
        "matplotlib": MATPLOTLIB_AVAILABLE,
        "psutil": PSUTIL_AVAILABLE,
        "pyside6": PYSIDE6_AVAILABLE,
        "pyqtgraph": PYQTGRAPH_AVAILABLE,
        "vnpy": VNPY_AVAILABLE,
        "cta_engine": CTA_ENGINE_AVAILABLE,
        "algo_engine": ALGO_ENGINE_AVAILABLE,
        "portfolio_engine": PORTFOLIO_ENGINE_AVAILABLE,
        "ctp_gateway": CTP_GATEWAY_AVAILABLE,
        "mini_gateway": MINI_GATEWAY_AVAILABLE,
        "ib_gateway": IB_GATEWAY_AVAILABLE,
        "tushare_datafeed": TUSHARE_DATAFEED_AVAILABLE,
        "rqdata_datafeed": RQDATA_DATAFEED_AVAILABLE,
        "data_module": DATA_MODULE_AVAILABLE,
        "system_module": SYSTEM_MODULE_AVAILABLE,
        "data_engine_utils": DATA_ENGINE_UTILS_AVAILABLE,
        "sqlite": SQLITE_AVAILABLE,
        "mongodb": MONGODB_AVAILABLE,
    }


def safe_import(module_name: str, fallback=None):
    """安全导入模块."""
    try:
        # 使用字典映射来减少返回语句数量
        module_map = {
            "pandas": pd,
            "numpy": np,
            "psutil": psutil,
            "matplotlib": plt,
            "vnpy_ctastrategy": CtaEngine,
        }

        # 扩展模块映射
        extended_map = module_map.copy()
        extended_map.update(
            {
                "vnpy_algotrading": AlgoEngine,
                "vnpy_ctp": CtpGateway,
            }
        )

        if module_name in extended_map:
            return extended_map[module_name]

        # 对于其他模块，使用动态导入
        __import__(module_name)
        return sys.modules[module_name]
    except ImportError:
        return fallback


# 统一日志配置
def setup_logging(
    name: str = "terminal", level: str = "INFO", log_file: Optional[str] = None
):
    """统一日志配置."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定）
    if log_file:
        try:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - "
                "%(filename)s:%(lineno)d - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning("无法创建日志文件处理器: %s", e)

    return logger


# 数据转换工具
def vnpy_to_pandas(vnpy_data_list: List[Any], data_type: str = "tick") -> Optional[Any]:
    """将VNPY数据转换为pandas DataFrame."""
    if not PANDAS_AVAILABLE or not vnpy_data_list:
        return None

    try:
        if data_type == "tick" and pd is not None:
            df = pd.DataFrame(
                [
                    {
                        "datetime": data.datetime,
                        "symbol": data.symbol,
                        "last_price": data.last_price,
                        "volume": data.volume,
                        "turnover": data.turnover,
                        "open_interest": data.open_interest,
                        "bid_price": data.bid_price_1,
                        "ask_price": data.ask_price_1,
                        "bid_volume": data.bid_volume_1,
                        "ask_volume": data.ask_volume_1,
                    }
                    for data in vnpy_data_list
                ]
            )
        elif data_type == "bar" and pd is not None:
            df = pd.DataFrame(
                [
                    {
                        "datetime": data.datetime,
                        "symbol": data.symbol,
                        "open_price": data.open_price,
                        "high_price": data.high_price,
                        "low_price": data.low_price,
                        "close_price": data.close_price,
                        "volume": data.volume,
                        "turnover": data.turnover,
                    }
                    for data in vnpy_data_list
                ]
            )
        else:
            return None

        if not df.empty and pd is not None:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)

        return df

    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logging.error("数据转换失败: %s", e)
        return None


# 导出所有公共接口
__all__ = [
    # 基础类型和常量
    "Path",
    "Dict",
    "List",
    "Optional",
    "Any",
    "Union",
    "Tuple",
    # 系统模块
    "os",
    "sys",
    "json",
    "time",
    "datetime",
    "traceback",
    "asyncio",
    "threading",
    "requests",
    "ThreadPoolExecutor",
    # 数据处理
    "pd",
    "np",
    "plt",
    "sns",
    # 系统监控
    "psutil",
    # GUI组件
    "QWidget",
    "QApplication",
    "QVBoxLayout",
    "QHBoxLayout",
    "QLabel",
    "QPushButton",
    "QMainWindow",
    "QTabWidget",
    "QTableWidget",
    "QHeaderView",
    "QSplitter",
    "QSizePolicy",
    "Qt",
    "Signal",
    # VNPY核心
    "TerminalEngine",
    "MainEngine",
    "EventEngine",
    "Event",
    "TickData",
    "BarData",
    "OrderData",
    "TradeData",
    "PositionData",
    "AccountData",
    # VNPY事件常量
    "EVENT_TICK",
    "EVENT_ORDER",
    "EVENT_TRADE",
    "EVENT_POSITION",
    "EVENT_ACCOUNT",
    "EVENT_LOG",
    # VNPY引擎
    "CtaEngine",
    "AlgoEngine",
    "PortfolioEngine",
    # VNPY网关
    "CtpGateway",
    "MiniGateway",
    "IbGateway",
    # VNPY数据源
    "TushareDatafeed",
    "RqdataDatafeed",
    # 本地模块
    "DataManager",
    "DataAPI",
    "IntegrationManager",
    "SystemMonitor",
    "ProcessManager",
    "CacheManager",
    "MemoryOptimizer",
    "ConcurrencyOptimizer",
    # 工具函数
    "setup_logging",
    "check_module_availability",
    "safe_import",
    "vnpy_to_pandas",
    "engine_setup_logging",
    "validate_symbol",
    "format_datetime",
    # 可用性常量
    "ModuleAvailability",
    # 数据库
    "sqlite3",
    "pymongo",
]
