# -*- coding: utf-8 -*-
"""
tdx_asyncio - 异步版本的tdxpy库

纯异步实现，避免线程开销，支持高并发。
基于asyncio，适用于IO密集型数据下载场景。
"""

__version__ = "2.1.1"
__author__ = "Terminal Project"

# 核心API
from .async_hq import AsyncTdxHq_API

# 扩展行情API（v2.1新增 - 期货/期权）
from .async_exhq import AsyncTdxExHq_API, get_future_markets, get_future_bars

# 连接池管理（v2.0新增）
from .async_connection_pool import AsyncConnectionPool, AsyncConnectionPoolContext, ConnectionPoolConfig

# 重试连接池（v2.1新增）
from .retry_connection_pool import RetryConnectionPool

# IP池管理（v2.0新增）
from .async_ip_pool import AsyncIPPool, AsyncRandomIPPool, AsyncSmartIPPool

# 交易日历系统（v2.1新增）
from .calendar import (
    TradingCalendar, trading_calendar,
    get_trading_calendar_global, is_trading_day_global,
    get_next_trading_day_global, get_previous_trading_day_global,
    get_trading_days_in_range_global
)

# 本地数据读取器（v2.1新增）
from .readers import (
    AsyncTdxDayReader, AsyncTdxMinuteReader, AsyncTdxLc5Reader, AsyncTdxBlockReader,
    read_day_data, read_minute_data, read_lc5_data, read_block_data,
    # v2.1.1新增：扩展读取器
    AsyncHistoryFinancialReader, AsyncTdxExHqDayReader, AsyncCustomerBlockReader,
    read_history_financial_data, read_exhq_day_data, read_customer_block_data
)

# 数据处理工具（mootdx迁移）
from .converters import to_dataframe, to_file_async, to_csv, to_json
from .caching import AsyncFileCache, AsyncDataCache, async_file_cache
from .adjustments import apply_adjustment, is_adjustment_needed


# 性能监控工具（mootdx迁移）
from .logger import (
    async_timeit, sync_timeit, async_timeit_with_stats,
    PerformanceMonitor, performance_monitor
)

# 异常类
from .exceptions import TdxConnectionError, TdxFunctionCallError, ValidationException

# 常量和类型
from .constants import (
    TDXParams, HQ_HOSTS, HQ_HOSTS_ALL, FUTURE_HOSTS, GP_HOSTS,
    FREQUENCY_MAP, MARKET_CODE_MAP, MARKET_NAME_MAP,
    SECURITY_EXCHANGE, SECURITY_TYPE, SECURITY_COEFFICIENT,
    # 扩展市场常量
    EX_MARKET_ZHENGZHOU, EX_MARKET_DALIAN, EX_MARKET_SHANGHAI,
    EX_MARKET_CFFEX, EX_MARKET_INE,
    EX_MARKET_NAME_MAP, EX_MARKET_CODE_MAP,
    # 复权类型映射
    ADJUST_TYPE_MAP, ADJUST_CODE_MAP,
    # 除权除息类别
    XDXR_CATEGORY_DIVIDEND, XDXR_CATEGORY_BONUS, XDXR_CATEGORY_ALLOT,
    # 协议调试常量
    PROTOCOL_HEADER_MAGIC, PROTOCOL_VERSION,
    # v2.1.1新增：扩展服务器
    EXHQ_HOSTS_GALAXY, FINANCE_HOSTS
)

__all__ = [
    # 核心API
    "AsyncTdxHq_API",

    # 扩展行情API v2.1
    "AsyncTdxExHq_API",
    "get_future_markets",
    "get_future_bars",

    # 连接池管理 v2.0
    "AsyncConnectionPool",
    "AsyncConnectionPoolContext",
    "ConnectionPoolConfig",

    # 重试连接池 v2.1
    "RetryConnectionPool",

    # IP池管理 v2.0
    "AsyncIPPool",
    "AsyncRandomIPPool",
    "AsyncSmartIPPool",

    # 交易日历系统 v2.1
    "TradingCalendar",
    "trading_calendar",
    "get_trading_calendar_global",
    "is_trading_day_global",
    "get_next_trading_day_global",
    "get_previous_trading_day_global",
    "get_trading_days_in_range_global",

    # 本地数据读取器 v2.1
    "AsyncTdxDayReader",
    "AsyncTdxMinuteReader",
    "AsyncTdxLc5Reader",
    "AsyncTdxBlockReader",
    "read_day_data",
    "read_minute_data",
    "read_lc5_data",
    "read_block_data",
    # v2.1.1新增：扩展读取器
    "AsyncHistoryFinancialReader",
    "AsyncTdxExHqDayReader",
    "AsyncCustomerBlockReader",
    "read_history_financial_data",
    "read_exhq_day_data",
    "read_customer_block_data",

    # 数据处理工具（mootdx迁移）
    "to_dataframe",
    "to_file_async",
    "to_csv",
    "to_json",
    "AsyncFileCache",
    "AsyncDataCache",
    "async_file_cache",
    "apply_adjustment",
    "is_adjustment_needed",


    # 性能监控工具（mootdx迁移）
    "async_timeit",
    "sync_timeit",
    "async_timeit_with_stats",
    "PerformanceMonitor",
    "performance_monitor",

    # 异常类
    "TdxConnectionError",
    "TdxFunctionCallError",
    "ValidationException",

    # 常量和类型
    "TDXParams",
    "HQ_HOSTS",
    "HQ_HOSTS_ALL",
    "FUTURE_HOSTS",
    "GP_HOSTS",
    "FREQUENCY_MAP",
    "MARKET_CODE_MAP",
    "MARKET_NAME_MAP",
    "SECURITY_EXCHANGE",
    "SECURITY_TYPE",
    "SECURITY_COEFFICIENT",
    # 扩展市场常量
    "EX_MARKET_ZHENGZHOU",
    "EX_MARKET_DALIAN",
    "EX_MARKET_SHANGHAI",
    "EX_MARKET_CFFEX",
    "EX_MARKET_INE",
    "EX_MARKET_NAME_MAP",
    "EX_MARKET_CODE_MAP",
    # 复权类型映射
    "ADJUST_TYPE_MAP",
    "ADJUST_CODE_MAP",
    # 除权除息类别
    "XDXR_CATEGORY_DIVIDEND",
    "XDXR_CATEGORY_BONUS",
    "XDXR_CATEGORY_ALLOT",
    # 协议调试常量
    "PROTOCOL_HEADER_MAGIC",
    "PROTOCOL_VERSION",
    # v2.1.1新增：扩展服务器
    "EXHQ_HOSTS_GALAXY",
    "FINANCE_HOSTS",
]

