# -*- coding: utf-8 -*-
"""
VnPy导入适配器模块.

集中管理所有VnPy相关的导入、可用性标志和工具函数。
从backend/core/base.py提取（第14-346行）。
"""

import logging
from typing import Any, List, Optional

# 专用logger - 日志埋点v4.0
logger_alert = logging.getLogger("backend.vnpy.alert")

# 数据处理库
try:
    import numpy as np
    import pandas as pd

    PANDAS_AVAILABLE = True
    NUMPY_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    np = None  # type: ignore
    PANDAS_AVAILABLE = False
    NUMPY_AVAILABLE = False

# 系统监控
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore
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
        from vnpy_ctastrategy import CtaEngine as CTA_ENGINE

        CTA_ENGINE_AVAILABLE = True
    else:
        CTA_ENGINE_AVAILABLE = False
        CTA_ENGINE = None  # type: ignore
except ImportError:
    CTA_ENGINE_AVAILABLE = False
    CTA_ENGINE = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        from vnpy_algotrading import AlgoEngine as ALGO_ENGINE

        ALGO_ENGINE_AVAILABLE = True
    else:
        ALGO_ENGINE_AVAILABLE = False
        ALGO_ENGINE = None  # type: ignore
except ImportError:
    ALGO_ENGINE_AVAILABLE = False
    ALGO_ENGINE = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        from vnpy_portfoliostrategy import StrategyEngine as PORTFOLIO_ENGINE

        PORTFOLIO_ENGINE_AVAILABLE = True
    else:
        PORTFOLIO_ENGINE_AVAILABLE = False
        PORTFOLIO_ENGINE = None  # type: ignore
except ImportError:
    PORTFOLIO_ENGINE_AVAILABLE = False
    PORTFOLIO_ENGINE = None  # type: ignore

# VnPy网关
try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_ctp import CtpGateway as CTP_GATEWAY  # type: ignore

            CTP_GATEWAY_AVAILABLE = True
        except ImportError:
            CTP_GATEWAY_AVAILABLE = False
            CTP_GATEWAY = None  # type: ignore
    else:
        CTP_GATEWAY_AVAILABLE = False
        CTP_GATEWAY = None  # type: ignore
except ImportError:
    CTP_GATEWAY_AVAILABLE = False
    CTP_GATEWAY = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_ib import IbGateway as IB_GATEWAY  # type: ignore

            IB_GATEWAY_AVAILABLE = True
        except ImportError:
            IB_GATEWAY_AVAILABLE = False
            IB_GATEWAY = None  # type: ignore
    else:
        IB_GATEWAY_AVAILABLE = False
        IB_GATEWAY = None  # type: ignore
except ImportError:
    IB_GATEWAY_AVAILABLE = False
    IB_GATEWAY = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_paperaccount import PaperAccountGateway as PAPER_ACCOUNT_GATEWAY  # type: ignore

            PAPERACCOUNT_GATEWAY_AVAILABLE = True
        except ImportError:
            PAPERACCOUNT_GATEWAY_AVAILABLE = False
            PAPER_ACCOUNT_GATEWAY = None  # type: ignore
    else:
        PAPERACCOUNT_GATEWAY_AVAILABLE = False
        PAPER_ACCOUNT_GATEWAY = None  # type: ignore
except ImportError:
    PAPERACCOUNT_GATEWAY_AVAILABLE = False
    PAPER_ACCOUNT_GATEWAY = None  # type: ignore

# VnPy数据源
try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_tushare import TushareDatafeed as TUSHARE_DATAFEED  # type: ignore

            TUSHARE_DATAFEED_AVAILABLE = True
        except ImportError:
            TUSHARE_DATAFEED_AVAILABLE = False
            TUSHARE_DATAFEED = None  # type: ignore
    else:
        TUSHARE_DATAFEED_AVAILABLE = False
        TUSHARE_DATAFEED = None  # type: ignore
except ImportError:
    TUSHARE_DATAFEED_AVAILABLE = False
    TUSHARE_DATAFEED = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_rqdata import RqdataDatafeed as RQDATA_DATAFEED  # type: ignore

            RQDATA_DATAFEED_AVAILABLE = True
        except ImportError:
            RQDATA_DATAFEED_AVAILABLE = False
            RQDATA_DATAFEED = None  # type: ignore
    else:
        RQDATA_DATAFEED_AVAILABLE = False
        RQDATA_DATAFEED = None  # type: ignore
except ImportError:
    RQDATA_DATAFEED_AVAILABLE = False
    RQDATA_DATAFEED = None  # type: ignore

# Infrastructure模块
try:
    from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor  # type: ignore
    from backend.infrastructure.system_vnpy.system_toolkit import ProcessManager  # type: ignore

    SYSTEM_MODULE_AVAILABLE = True
except ImportError:
    SystemMonitor = None  # type: ignore
    ProcessManager = None  # type: ignore
    SYSTEM_MODULE_AVAILABLE = False


def setup_logging(name: str = "terminal", level: str = "INFO") -> logging.Logger:
    """
    配置日志系统（仅控制台输出，数据库日志由LogRecordHandler自动处理）.

    Args:
        name: 日志名称
        level: 日志级别

    Returns:
        配置好的Logger对象

    Note:
        日志自动写入数据库，由 LogRecordHandler 处理。
        文件日志功能已于 v0.50 移除。
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False  # 阻止传播到root logger，避免重复输出

    if logger.handlers:
        return logger

    # 控制台处理器（Terminal输出）
    import sys

    # 确保stdout使用UTF-8编码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


def vnpy_to_pandas(vnpy_data_list: List[Any], data_type: str = "bar") -> Optional[Any]:
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
        if not PANDAS_AVAILABLE or pd is None:
            return None

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
        logging.error("VnPy数据转换失败: %s", e)
        return None


# 别名定义
CtpGateway = CTP_GATEWAY if CTP_GATEWAY_AVAILABLE else None
IbGateway = IB_GATEWAY if IB_GATEWAY_AVAILABLE else None
PaperAccountGateway = (
    PAPER_ACCOUNT_GATEWAY
    if "PAPER_ACCOUNT_GATEWAY" in locals() and PAPER_ACCOUNT_GATEWAY is not None
    else None
)
PortfolioEngine = PORTFOLIO_ENGINE if PORTFOLIO_ENGINE_AVAILABLE else None
RqdataDatafeed = RQDATA_DATAFEED if RQDATA_DATAFEED_AVAILABLE else None
TushareDatafeed = TUSHARE_DATAFEED if TUSHARE_DATAFEED_AVAILABLE else None


__all__ = [
    # 数据处理库
    "pd",
    "np",
    "PANDAS_AVAILABLE",
    "NUMPY_AVAILABLE",
    # 系统监控
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
    "CTP_GATEWAY",
    "IB_GATEWAY",
    "PAPER_ACCOUNT_GATEWAY",
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
    # 别名定义
    "CtpGateway",
    "IbGateway",
    "PaperAccountGateway",
    "PortfolioEngine",
    "RqdataDatafeed",
    "TushareDatafeed",
]
