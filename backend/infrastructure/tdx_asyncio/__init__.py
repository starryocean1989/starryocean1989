# -*- coding: utf-8 -*-
"""
tdx_asyncio - 异步版本的tdxpy库

纯异步实现，避免线程开销，支持高并发。
基于asyncio，适用于IO密集型数据下载场景。
"""

__version__ = "2.2.0"
__author__ = "Terminal Project"

# 核心API
from .api.hq import (
    AsyncTdxHq_API,
    get_security_list_batch,
    get_security_list_all,
    get_security_bars_by_interval,
    get_security_bars_safe,
)

# 扩展行情API（v2.1新增 - 期货/期权）
from .api.exhq import AsyncTdxExHq_API, get_future_markets, get_future_bars

# 连接池管理（v2.0新增）
from .core.connection_pool import (
    AsyncConnectionPool,
    AsyncConnectionPoolContext,
    ConnectionPoolConfig,
)

# 重试连接池（v2.1新增）
from .core.retry_pool import RetryConnectionPool

# IP池管理（v2.0新增）
from .network.ip_pool import AsyncIPPool, AsyncRandomIPPool, AsyncSmartIPPool

# 交易日历系统（v2.1新增）
from .utils.trading_calendar import (
    TradingCalendar,
    trading_calendar,
    get_trading_calendar_global,
    is_trading_day_global,
    get_next_trading_day_global,
    get_previous_trading_day_global,
    get_trading_days_in_range_global,
)

# 本地数据读取器（v2.1新增）
from .readers import (
    AsyncTdxDayReader,
    AsyncTdxMinuteReader,
    AsyncTdxLc5Reader,
    AsyncTdxBlockReader,
    read_day_data,
    read_minute_data,
    read_lc5_data,
    read_block_data,
    # v2.1.1新增：扩展读取器
    AsyncHistoryFinancialReader,
    AsyncTdxExHqDayReader,
    AsyncCustomerBlockReader,
    read_history_financial_data,
    read_exhq_day_data,
    read_customer_block_data,
)

# 数据读取器（迁移自data_module_vnpy）
from .readers.binary_reader import TdxBinaryReader
from .readers.data_reader import TdxDataReader
from .readers.bj_decoder import BjStockDecoder
from .readers.base import BaseReader

# 配置文件解析器（迁移自data_module_vnpy）
from .parsers.config_parser import TdxConfigFileParser
from .parsers.block_parser import BlockParser

# 数据处理工具（mootdx迁移）
from .utils.converters import to_dataframe, to_file_async, to_csv, to_json
from .utils.caching import AsyncFileCache, AsyncDataCache, async_file_cache
from .utils.adjustments import apply_adjustment, is_adjustment_needed


# 性能监控工具（mootdx迁移）
from .utils.logger import (
    async_timeit,
    sync_timeit,
    async_timeit_with_stats,
    PerformanceMonitor,
    performance_monitor,
)

# 异常类
from .core.exceptions import TdxConnectionError, TdxFunctionCallError, ValidationException

# 常量
from .network.constants import (
    TDXParams,
    BROKER_SERVERS_7709,
    FUTURE_HOSTS,
    EX_MARKET_SHANGHAI,
    EX_MARKET_NAME_MAP,
    ADJUST_TYPE_MAP,
    XDXR_CATEGORY_DIVIDEND,
    FILE_EXT_DAY,
    FILE_EXT_MINUTE,
    FILE_EXT_LC5,
)

# 辅助函数
from .utils.helper import (
    get_datetime,
    get_price,
    get_volume,
    get_time,
    get_security_coefficient,
    interval_to_category,  # v2.3新增
    category_to_interval,  # v2.3新增
    # v2.4新增：队列和子进程辅助函数（迁移自data_module_vnpy）
    safe_put_queue,
    get_queue_skip_stats,
    reset_queue_skip_stats,
    configure_subprocess_logging,
    # 向后兼容：保留带下划线的函数名
    _safe_put_queue,
    _get_queue_skip_stats,
    _reset_queue_skip_stats,
    _configure_subprocess_logging,
)

# 财务数据API（v2.2新增）
from .api.finance import (
    batch_get_ipo_dates,
    batch_get_ipo_dates_multiprocess,
    batch_get_finance_info,
    get_ipo_date_safe,  # v2.3新增
)

# 服务器测速工具（v2.2新增）
from .network.server_tester import (
    ServerTester,
    test_server,
    batch_test_servers,
    get_fastest_servers,
)

# 文件路径管理工具（v2.2新增）
from .utils.path_helper import TdxPathHelper, find_tdx_root, get_market_from_code

# 数据格式转换工具（v2.2新增）
from .utils.data_converter import (
    tdx_bars_to_dataframe,
    tdx_quotes_to_dataframe,
    tdx_security_list_to_dataframe,
    tdx_xdxr_to_dataframe,
    tdx_finance_to_dict,
    normalize_tdx_data,
    bars_to_dataframe_safe,  # v2.3新增
)

__all__ = [
    # 核心API
    "AsyncTdxHq_API",
    "AsyncTdxExHq_API",
    "get_future_markets",
    "get_future_bars",
    # 高级封装函数（v2.3新增）
    "get_security_list_batch",
    "get_security_list_all",
    "get_security_bars_by_interval",
    "get_security_bars_safe",
    # 连接池
    "AsyncConnectionPool",
    "AsyncConnectionPoolContext",
    "ConnectionPoolConfig",
    "RetryConnectionPool",
    # IP池
    "AsyncIPPool",
    "AsyncRandomIPPool",
    "AsyncSmartIPPool",
    # 交易日历
    "TradingCalendar",
    "trading_calendar",
    "get_trading_calendar_global",
    "is_trading_day_global",
    "get_next_trading_day_global",
    "get_previous_trading_day_global",
    "get_trading_days_in_range_global",
    # 数据读取器
    "AsyncTdxDayReader",
    "AsyncTdxMinuteReader",
    "AsyncTdxLc5Reader",
    "AsyncTdxBlockReader",
    "read_day_data",
    "read_minute_data",
    "read_lc5_data",
    "read_block_data",
    "AsyncHistoryFinancialReader",
    "AsyncTdxExHqDayReader",
    "AsyncCustomerBlockReader",
    "read_history_financial_data",
    "read_exhq_day_data",
    "read_customer_block_data",
    # 数据读取器（迁移）
    "TdxBinaryReader",
    "TdxDataReader",
    "BjStockDecoder",
    "BaseReader",
    # 配置文件解析器（迁移）
    "TdxConfigFileParser",
    "BlockParser",
    # 数据处理工具
    "to_dataframe",
    "to_file_async",
    "to_csv",
    "to_json",
    "AsyncFileCache",
    "AsyncDataCache",
    "async_file_cache",
    "apply_adjustment",
    "is_adjustment_needed",
    # 性能监控
    "async_timeit",
    "sync_timeit",
    "async_timeit_with_stats",
    "PerformanceMonitor",
    "performance_monitor",
    # 异常类
    "TdxConnectionError",
    "TdxFunctionCallError",
    "ValidationException",
    # 常量
    "TDXParams",
    "BROKER_SERVERS_7709",
    "FUTURE_HOSTS",
    "EX_MARKET_SHANGHAI",
    "EX_MARKET_NAME_MAP",
    "ADJUST_TYPE_MAP",
    "XDXR_CATEGORY_DIVIDEND",
    "FILE_EXT_DAY",
    "FILE_EXT_MINUTE",
    "FILE_EXT_LC5",
    # 辅助函数
    "get_datetime",
    "get_price",
    "get_volume",
    "get_time",
    "get_security_coefficient",
    "interval_to_category",  # v2.3新增
    "category_to_interval",  # v2.3新增
    # 财务数据API（v2.2新增）
    "batch_get_ipo_dates",
    "batch_get_ipo_dates_multiprocess",
    "batch_get_finance_info",
    "get_ipo_date_safe",  # v2.3新增
    # 服务器测速工具（v2.2新增）
    "ServerTester",
    "test_server",
    "batch_test_servers",
    "get_fastest_servers",
    # 文件路径管理工具（v2.2新增）
    "TdxPathHelper",
    "find_tdx_root",
    "get_market_from_code",
    # 数据格式转换工具（v2.2新增）
    "tdx_bars_to_dataframe",
    "tdx_quotes_to_dataframe",
    "tdx_security_list_to_dataframe",
    "tdx_xdxr_to_dataframe",
    "tdx_finance_to_dict",
    "normalize_tdx_data",
    "bars_to_dataframe_safe",  # v2.3新增
]
