# -*- coding: utf-8 -*-
"""
tdx_asyncio.readers - 数据读取器模块

包含：
- base: 读取器基类
- binary_reader: TDX二进制文件读取器（迁移自data_module_vnpy）
- data_reader: TDX数据读取器（多进程+多协程，迁移自data_module_vnpy）
- bj_decoder: 北证股票解码器（迁移自data_module_vnpy）
- async_readers: 异步本地数据读取器（原有功能）
"""

# 迁移自data_module_vnpy的读取器
from .base import BaseReader
from .binary_reader import TdxBinaryReader
from .data_reader import TdxDataReader
from .bj_decoder import BjStockDecoder

# 原有的异步读取器（从async_readers.py导出）
from .async_readers import (
    AsyncTdxDayReader,
    AsyncTdxMinuteReader,
    AsyncTdxLc5Reader,
    AsyncTdxBlockReader,
    AsyncHistoryFinancialReader,
    AsyncTdxExHqDayReader,
    AsyncCustomerBlockReader,
    read_day_data,
    read_minute_data,
    read_lc5_data,
    read_block_data,
    read_history_financial_data,
    read_exhq_day_data,
    read_customer_block_data,
)

__all__ = [
    # 迁移自data_module_vnpy
    "BaseReader",
    "TdxBinaryReader",
    "TdxDataReader",
    "BjStockDecoder",
    # 原有的异步读取器
    "AsyncTdxDayReader",
    "AsyncTdxMinuteReader",
    "AsyncTdxLc5Reader",
    "AsyncTdxBlockReader",
    "AsyncHistoryFinancialReader",
    "AsyncTdxExHqDayReader",
    "AsyncCustomerBlockReader",
    "read_day_data",
    "read_minute_data",
    "read_lc5_data",
    "read_block_data",
    "read_history_financial_data",
    "read_exhq_day_data",
    "read_customer_block_data",
]
