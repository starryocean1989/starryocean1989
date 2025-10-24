# -*- coding: utf-8 -*-
"""
数据获取模块

包含远程数据源相关的功能：
- 品种列表获取和管理
- 增量K线下载
- 实时数据源（已迁移到unified_data_manager.py）
- 服务器池管理
- 自适应下载配置
"""

from .symbol_management import SymbolLoader
from .data_fetcher import MultiProcessStockFetcher

# 向后兼容：PollingGateway 和 VirtualGateway 已迁移到 unified_data_manager.py
# 从新位置重新导出以保持兼容性
from ..local_data.unified_data_manager import (
    TdxDataSource as PollingGateway,
    VirtualDataSource as VirtualGateway,
)

__all__ = [
    "SymbolLoader",
    "MultiProcessStockFetcher",
    "PollingGateway",
    "VirtualGateway",
]
