# -*- coding: utf-8 -*-
"""
data_module_vnpy - 中国A股数据管理模块 v2.0

基于vnpy架构的量化交易数据管理模块，集成mootdx接口获取中国A股数据，
支持品种列表获取、K线数据下载、数据存储、数据感知等功能。

主要功能：
- 品种列表获取：支持上证A股、深证A股、北证A股、T+0基金、含可转债
- K线数据下载：全量下载和增量下载
- 数据存储：Parquet列式压缩格式
- 数据感知：品种缺失、历史缺失、逻辑错误、格式错误检查
- 文件监控：实时监控数据变化并推送结果

v2.0更新：
- 激进合并：20个文件 → 6个核心文件
- AI Debug友好：相关功能集中，减少跨文件跳转
- 统一API：所有公共接口统一导出
"""

from pathlib import Path
from vnpy.trader.app import BaseApp

# ==================== 第1部分：核心模块（data_module.py）====================
from .data_module import (
    # 核心引擎
    ChinaStockEngine,
    # 配置管理
    ConfigManager,
    # 事件系统
    APP_NAME,
    EVENT_CHINASTOCK_LOG,
    EVENT_CHINASTOCK_VALIDATION,
    EVENT_CHINASTOCK_DOWNLOAD,
    EVENT_DATA_QUALITY_UPDATE,
    EventPublisher,
    ValidationEventPublisher,
    DownloadEventPublisher,
    QualityEventPublisher,
    # 缓存管理
    DailyCacheManager,
    # Qt工作线程
    DataValidationWorker,
    # 工具函数
    get_network_time,
)

# ==================== 第2部分：数据获取模块（data_acquisition.py）====================
from .data_acquisition import (
    # 品种管理
    SymbolLoader,
    # K线下载
    MultiProcessStockFetcher,
    # 数据读取器
    BaseReader,
    TdxBinaryReader,
    TdxDynamicExecutor,
    BjStockDecoder,
)

# ==================== 第3部分：数据管理模块（data_management.py）====================
from .data_management import (
    # 统一数据管理器
    UnifiedDataManager,
    PreloadService,
    TdxDataSource,
    VirtualDataSource,
    # 向后兼容别名
    PollingGateway,
    VirtualGateway,
    # 数据验证器
    StatelessValidator,
    ValidationContext,
    StatelessValidationResult,
    # 缓存和内存管理
    LRUCacheManager,
    SharedMemoryManager,
    # 智能调优器
    IntelligentAdaptiveTuner,
)

# ==================== 第4部分：数据质量模块（data_quality.py）====================
from .data_quality import (
    HealthChecker,
    StorageManager,
    DataQualityManager,
    FileWatcher,
)

# ==================== 第5部分：负载均衡模块（load_balancer.py）====================
from .load_balancer import (
    ServerPoolManager,
    server_pool_manager,
    get_best_servers,
    get_best_server,
    get_all_servers,
)

__all__ = [
    # ==================== 常量和事件 ====================
    "APP_NAME",
    "EVENT_CHINASTOCK_LOG",
    "EVENT_CHINASTOCK_VALIDATION",
    "EVENT_CHINASTOCK_DOWNLOAD",
    "EVENT_DATA_QUALITY_UPDATE",
    # ==================== 核心引擎和应用 ====================
    "ChinaStockEngine",
    "ChinaStockApp",
    # ==================== 配置管理 ====================
    "ConfigManager",
    # ==================== 事件发布器 ====================
    "EventPublisher",
    "ValidationEventPublisher",
    "DownloadEventPublisher",
    "QualityEventPublisher",
    # ==================== 缓存管理 ====================
    "DailyCacheManager",
    "LRUCacheManager",
    "SharedMemoryManager",
    # ==================== Qt工作线程 ====================
    "DataValidationWorker",
    # ==================== 工具函数 ====================
    "get_network_time",
    # ==================== 品种管理 ====================
    "SymbolLoader",
    # ==================== K线下载 ====================
    "MultiProcessStockFetcher",
    # ==================== 数据读取器 ====================
    "BaseReader",
    "TdxBinaryReader",
    "TdxDynamicExecutor",
    "BjStockDecoder",
    # ==================== 数据源（新架构）====================
    "TdxDataSource",
    "VirtualDataSource",
    "UnifiedDataManager",
    "PreloadService",
    # ==================== 数据源（向后兼容别名）====================
    "PollingGateway",
    "VirtualGateway",
    # ==================== 数据验证器 ====================
    "StatelessValidator",
    "ValidationContext",
    "StatelessValidationResult",
    # ==================== 智能调优器 ====================
    "IntelligentAdaptiveTuner",
    # ==================== 数据质量管理 ====================
    "HealthChecker",
    "StorageManager",
    "DataQualityManager",
    "FileWatcher",
    # ==================== 服务器池管理 ====================
    "ServerPoolManager",
    "server_pool_manager",
    "get_best_servers",
    "get_best_server",
    "get_all_servers",
]

__version__ = "2.0.0"  # v2.0 - 激进合并版本


class ChinaStockApp(BaseApp):
    """中国A股数据管理应用"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "中国A股数据管理"
    engine_class: type[ChinaStockEngine] = ChinaStockEngine
    widget_name: str = "ChinaStockWidget"
    icon_name: str = str(app_path.joinpath("ui", "chinastock.ico"))
