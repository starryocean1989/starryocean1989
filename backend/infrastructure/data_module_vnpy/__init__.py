# -*- coding: utf-8 -*-
"""
data_module_vnpy - 中国A股数据管理模块

基于vnpy架构的量化交易数据管理模块，集成mootdx接口获取中国A股数据，
支持品种列表获取、K线数据下载、数据存储、数据感知等功能。

主要功能：
- 品种列表获取：支持上证A股、深证A股、北证A股、T+0基金、含可转债
- K线数据下载：全量下载和增量下载
- 数据存储：Parquet列式压缩格式
- 数据感知：品种缺失、历史缺失、逻辑错误、格式错误检查
- 文件监控：实时监控数据变化并推送结果
"""

from pathlib import Path
from vnpy.trader.app import BaseApp

from .events import (
    APP_NAME,
    EVENT_CHINASTOCK_LOG,
    EVENT_CHINASTOCK_VALIDATION,
    EVENT_CHINASTOCK_DOWNLOAD,
    EVENT_DATA_QUALITY_UPDATE,
    EventPublisher,
    ValidationEventPublisher,
    DownloadEventPublisher,
    QualityEventPublisher,
)
from .core import ChinaStockEngine
from .data_acquisition.gateways import PollingGateway, VirtualGateway
from .data_readers import BaseReader, TdxBinaryReader
from .local_data.unified_data_manager import UnifiedDataManager, PreloadService
from .data_acquisition.symbol_management import SymbolLoader
from .data_acquisition.data_fetcher import MultiProcessStockFetcher, download_incremental_unified
from .local_data.data_quality import HealthChecker
from .server_pool_manager import (
    ServerPoolManager,
    server_pool_manager,
    get_best_servers,
    get_best_server,
    get_all_servers,
)

__all__ = [
    # 常量和事件
    "APP_NAME",
    "EVENT_CHINASTOCK_LOG",
    "EVENT_CHINASTOCK_VALIDATION",
    "EVENT_CHINASTOCK_DOWNLOAD",
    "EVENT_DATA_QUALITY_UPDATE",
    # 核心引擎
    "ChinaStockEngine",
    "ChinaStockApp",
    # 事件发布器
    "EventPublisher",
    "ValidationEventPublisher",
    "DownloadEventPublisher",
    "QualityEventPublisher",
    # 功能模块
    "SymbolLoader",
    "MultiProcessStockFetcher",
    "download_incremental_unified",
    "PollingGateway",
    "VirtualGateway",
    "BaseReader",
    "TdxBinaryReader",
    "PreloadService",
    "UnifiedDataManager",
    "HealthChecker",
    # 服务器池管理
    "ServerPoolManager",
    "server_pool_manager",
    "get_best_servers",
    "get_best_server",
    "get_all_servers",
]

__version__ = "2.0.0"  # 升级到2.0.0版本


class ChinaStockApp(BaseApp):
    """中国A股数据管理应用"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "中国A股数据管理"
    engine_class: type[ChinaStockEngine] = ChinaStockEngine
    widget_name: str = "ChinaStockWidget"
    icon_name: str = str(app_path.joinpath("ui", "chinastock.ico"))
