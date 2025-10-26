# -*- coding: utf-8 -*-
"""
数据标准化读取工具 - 极限合并版

本模块已完成极限合并：将原4个独立文件合并为1个统一文件data_readers.py

提供统一的接口读取各种格式的本地数据文件并标准化保存。

当前支持的数据类型：
- 通达信二进制数据（日线、5分钟线、1分钟线）

合并说明：
- 合并前：4个文件（base_reader.py, bj_decoder.py, tdx_reader.py, tdx_dynamic_executor.py）
- 合并后：1个文件（data_readers.py）
- API兼容性：100%向后兼容
"""

from .data_readers import (
    BaseReader,
    BjStockDecoder,
    TdxBinaryReader,
    TdxDynamicExecutor,
    ExecutionResult,
)

__all__ = [
    "BaseReader",
    "BjStockDecoder",
    "TdxBinaryReader",
    "TdxDynamicExecutor",
    "ExecutionResult",
]
