# -*- coding: utf-8 -*-
"""
数据获取模块

包含远程数据源相关的功能：
- 品种列表获取和管理
- 增量K线下载
- 实时数据源
- 服务器池管理
- 自适应下载配置
"""

from .symbol_management import SymbolLoader
from .data_fetcher import MultiProcessStockFetcher
from .gateways import PollingGateway, VirtualGateway
from .server_pool_manager import ServerPoolManager
from .adaptive_config import AdaptiveDownloadConfig

__all__ = [
    "SymbolLoader",
    "MultiProcessStockFetcher",
    "PollingGateway",
    "VirtualGateway",
    "ServerPoolManager",
    "AdaptiveDownloadConfig",
]
