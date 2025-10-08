# -*- coding: utf-8 -*-
"""
Backend核心导入模块.

集中管理后端常用导入，简化代码。
注意：Backend层不应导入任何UI组件。
"""

import asyncio
import datetime
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# 网络请求
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

# VnPy核心模块 - 直接从vnpy包导入
try:
    from vnpy.event import Event, EventEngine
    from vnpy.trader.engine import MainEngine
    from vnpy.trader.object import (
        AccountData,
        BarData,
        OrderData,
        PositionData,
        TickData,
        TradeData,
    )
    from vnpy.trader.event import (
        EVENT_ACCOUNT,
        EVENT_LOG,
        EVENT_ORDER,
        EVENT_POSITION,
        EVENT_TICK,
        EVENT_TRADE,
    )

    VNPY_AVAILABLE = True
except ImportError:
    # 如果导入失败，提供存根
    VNPY_AVAILABLE = False
    MainEngine = None
    EventEngine = None
    Event = None
    TickData = None
    BarData = None
    OrderData = None
    TradeData = None
    PositionData = None
    AccountData = None
    EVENT_TICK = "eTick"
    EVENT_ORDER = "eOrder"
    EVENT_TRADE = "eTrade"
    EVENT_POSITION = "ePosition"
    EVENT_ACCOUNT = "eAccount"
    EVENT_LOG = "eLog"

# VnPy策略引擎
try:
    if VNPY_AVAILABLE:
        from vnpy_ctastrategy import CtaEngine

        CTA_ENGINE_AVAILABLE = True
    else:
        CTA_ENGINE_AVAILABLE = False
        CtaEngine = None
except ImportError:
    CTA_ENGINE_AVAILABLE = False
    CtaEngine = None

try:
    if VNPY_AVAILABLE:
        from vnpy_algotrading import AlgoEngine

        ALGO_ENGINE_AVAILABLE = True
    else:
        ALGO_ENGINE_AVAILABLE = False
        AlgoEngine = None
except ImportError:
    ALGO_ENGINE_AVAILABLE = False
    AlgoEngine = None

try:
    if VNPY_AVAILABLE:
        from vnpy_portfoliostrategy import StrategyEngine as PortfolioEngine

        PORTFOLIO_ENGINE_AVAILABLE = True
    else:
        PORTFOLIO_ENGINE_AVAILABLE = False
        PortfolioEngine = None
except ImportError:
    PORTFOLIO_ENGINE_AVAILABLE = False
    PortfolioEngine = None

# VnPy网关
try:
    if VNPY_AVAILABLE:
        from vnpy_ctp import CtpGateway

        CTP_GATEWAY_AVAILABLE = True
    else:
        CTP_GATEWAY_AVAILABLE = False
        CtpGateway = None
except ImportError:
    CTP_GATEWAY_AVAILABLE = False
    CtpGateway = None

try:
    if VNPY_AVAILABLE:
        from vnpy_ib import IbGateway

        IB_GATEWAY_AVAILABLE = True
    else:
        IB_GATEWAY_AVAILABLE = False
        IbGateway = None
except ImportError:
    IB_GATEWAY_AVAILABLE = False
    IbGateway = None

try:
    if VNPY_AVAILABLE:
        from vnpy_paperaccount import PaperAccountGateway

        PAPERACCOUNT_GATEWAY_AVAILABLE = True
    else:
        PAPERACCOUNT_GATEWAY_AVAILABLE = False
        PaperAccountGateway = None
except ImportError:
    PAPERACCOUNT_GATEWAY_AVAILABLE = False
    PaperAccountGateway = None

# VnPy数据源
try:
    if VNPY_AVAILABLE:
        from vnpy_tushare import TushareDatafeed

        TUSHARE_DATAFEED_AVAILABLE = True
    else:
        TUSHARE_DATAFEED_AVAILABLE = False
        TushareDatafeed = None
except ImportError:
    TUSHARE_DATAFEED_AVAILABLE = False
    TushareDatafeed = None

try:
    if VNPY_AVAILABLE:
        from vnpy_rqdata import RqdataDatafeed

        RQDATA_DATAFEED_AVAILABLE = True
    else:
        RQDATA_DATAFEED_AVAILABLE = False
        RqdataDatafeed = None
except ImportError:
    RQDATA_DATAFEED_AVAILABLE = False
    RqdataDatafeed = None

# Infrastructure模块
try:
    from ..infrastructure.system_vnpy.system_monitor import SystemMonitor
    from ..infrastructure.system_vnpy.process_manager import ProcessManager

    SYSTEM_MODULE_AVAILABLE = True
except ImportError:
    SystemMonitor = None
    ProcessManager = None
    SYSTEM_MODULE_AVAILABLE = False


def setup_logging(
    name: str = "terminal", level: str = "INFO", log_file: Optional[str] = None
) -> logging.Logger:
    """
    配置日志系统.

    Args:
        name: 日志名称
        level: 日志级别
        log_file: 日志文件路径（可选）

    Returns:
        配置好的Logger对象
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning(f"无法创建日志文件: {e}")

    return logger


def vnpy_to_pandas(vnpy_data_list: List[Any], data_type: str = "bar") -> Optional[pd.DataFrame]:
    """
    将VnPy数据对象转换为pandas DataFrame.

    Args:
        vnpy_data_list: VnPy数据对象列表
        data_type: 数据类型 ("bar" 或 "tick")

    Returns:
        pandas DataFrame或None
    """
    if not PANDAS_AVAILABLE or not vnpy_data_list:
        return None

    try:
        if data_type == "bar":
            df = pd.DataFrame(
                [
                    {
                        "datetime": data.datetime,
                        "symbol": data.symbol,
                        "open": data.open_price,
                        "high": data.high_price,
                        "low": data.low_price,
                        "close": data.close_price,
                        "volume": data.volume,
                    }
                    for data in vnpy_data_list
                ]
            )
        elif data_type == "tick":
            df = pd.DataFrame(
                [
                    {
                        "datetime": data.datetime,
                        "symbol": data.symbol,
                        "last_price": data.last_price,
                        "volume": data.volume,
                        "bid_price": data.bid_price_1,
                        "ask_price": data.ask_price_1,
                    }
                    for data in vnpy_data_list
                ]
            )
        else:
            return None

        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)

        return df
    except Exception as e:
        logging.error(f"VnPy数据转换失败: {e}")
        return None


__all__ = [
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
    # 类型
    "Dict",
    "List",
    "Optional",
    "Any",
    "Union",
    "Tuple",
    # 网络
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
]
