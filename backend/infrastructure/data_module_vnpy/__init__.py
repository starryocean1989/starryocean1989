"""
data_module_vnpy - 数据中心模块 v3.6

架构v3.6完整重构，包含以下核心模块：
- core_engine.py: 核心引擎与基础设施
- data_acquisition.py: 数据获取模块
- data_storage.py: 存储管理模块
- data_quality.py: 质量管理模块
- data_runtime.py: 运行时管理模块
- load_balancer.py: 负载均衡模块

架构特性：
- native_iocp深度集成：文件I/O性能提升50-80%
- native_ipc深度集成：跨进程通信，替代ZMQ
- 智能负载均衡：木桶理论，动态调整并发
- 统一数据管理：四层融合查询
- 代码精简：通用工具函数已迁移到 tdx_asyncio
- 性能优化：集成 native C 扩展，优化关键性能路径
- 100% API向后兼容

v3.6 更新：
- 工具函数迁移：safe_put_queue、configure_subprocess_logging 等已迁移到 tdx_asyncio.utils.helper
- 性能优化：集成 native C 扩展，优化关键性能路径
- 引用链更新：所有引用已更新，从 tdx_asyncio 导入

重构日期：2025年
作者：AI Assistant
"""

# ==============================================================================
# 核心引擎与基础设施
# ==============================================================================

from .core_engine import (
    # 核心引擎
    ChinaStockEngine,
    # 配置管理
    ConfigManager,
    # 缓存管理
    DailyCacheManager,
    # 网络时间同步
    NetworkTimeSync,
    # 事件发布器
    EventPublisher,
    ValidationEventPublisher,
    DownloadEventPublisher,
    QualityEventPublisher,
)

# ==============================================================================
# 数据获取模块
# ==============================================================================

from .data_acquisition import (
    # 品种加载器
    SymbolLoader,
    # 品种分类器
    BaseClassifier,
    ClassifierRegistry,
    ShanghaiStockClassifier,
    ShenzhenStockClassifier,
    BeijingStockClassifier,
    T0FundClassifier,
    ConvertibleBondClassifier,
    # 品种过滤器
    BaseFilter,
    FilterChain,
    UnlistedSymbolFilter,
    DuplicateSymbolFilter,
    InvalidDataFilter,
    # 数据下载器
    MultiProcessStockFetcher,
    DownloadState,
    DownloadStateMachine,
    DownloadTask,
    TaskQueueManager,
    # 动态执行器
    TdxDynamicExecutor,
    # IPO日期下载
    download_ipo_dates,
    # 任务日志
    TaskDetailLogger,
    get_task_logger,
    close_task_logger,
    close_all_task_loggers,
)

# TDX读取器和解析器（已迁移到 tdx_asyncio）
from backend.infrastructure.tdx_asyncio import (
    TdxBinaryReader,
    TdxDataReader,
    BjStockDecoder,
    BaseReader,
    TdxConfigFileParser,
    BlockParser,
    # v2.2新增：底层工具
    batch_get_ipo_dates,
    batch_get_finance_info,
    ServerTester,
    test_server,
    batch_test_servers,
    get_fastest_servers,
    TdxPathHelper,
    find_tdx_root,
    get_market_from_code,
    tdx_bars_to_dataframe,
    tdx_quotes_to_dataframe,
    normalize_tdx_data,
    # v2.3新增：高级封装函数
    get_security_list_batch,
    get_security_list_all,
    get_security_bars_by_interval,
    get_security_bars_safe,
    get_ipo_date_safe,
    bars_to_dataframe_safe,
    interval_to_category,
    category_to_interval,
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

# ==============================================================================
# 存储管理模块
# ==============================================================================

from .data_storage import (
    # 存储管理器
    StorageManager,
    # 预加载服务
    PreloadService,
    # LRU缓存管理
    LRUCacheManager,
    # 共享内存管理
    SharedMemoryManager,
)

# ==============================================================================
# 质量管理模块
# ==============================================================================

from .data_quality import (
    # 数据质量级别
    DataQualityLevel,
    ValidationStatus,
    # 数据结果
    QualityScanResult,
    ValidationResult,
    HealthCheckResult,
    # 核心组件
    DataSensor,
    StatelessValidator,
    DataFileWatcher,
    HealthChecker,
    IPODateCache,
)

# ==============================================================================
# 运行时管理模块
# ==============================================================================

from .data_runtime import (
    # 数据查询
    DataQueryPriority,
    UnifiedDataManager,
    # 数据源
    TdxDataSource,
    VirtualDataSource,
    # 订阅管理
    SubscriptionManager,
)

# ==============================================================================
# 负载均衡模块
# ==============================================================================

from .load_balancer import (
    # 资源监控
    ResourceMetrics,
    ResourceMonitor,
    # 配置计算
    DynamicConfigCalculator,
    # 服务器池
    ServerInfo,
    ServerPoolManager,
    # 负载均衡
    LoadBalancer,
)


# ==============================================================================
# 统一导出API（向后兼容）
# ==============================================================================

__all__ = [
    # ========== 核心引擎 ==========
    "ChinaStockEngine",
    "ConfigManager",
    "DailyCacheManager",
    "NetworkTimeSync",
    "EventPublisher",
    "ValidationEventPublisher",
    "DownloadEventPublisher",
    "QualityEventPublisher",
    # ========== 数据获取 ==========
    # 品种管理
    "SymbolLoader",
    "BaseClassifier",
    "ClassifierRegistry",
    "ShanghaiStockClassifier",
    "ShenzhenStockClassifier",
    "BeijingStockClassifier",
    "T0FundClassifier",
    "ConvertibleBondClassifier",
    "BaseFilter",
    "FilterChain",
    "UnlistedSymbolFilter",
    "DuplicateSymbolFilter",
    "InvalidDataFilter",
    # 数据下载
    "MultiProcessStockFetcher",
    "DownloadState",
    "DownloadStateMachine",
    "DownloadTask",
    "TaskQueueManager",
    # TDX读取器（已迁移到 tdx_asyncio）
    "TdxBinaryReader",
    "TdxDataReader",
    "BjStockDecoder",
    "BaseReader",
    # 动态执行器
    "TdxDynamicExecutor",
    # IPO日期
    "download_ipo_dates",
    # 任务日志
    "TaskDetailLogger",
    "get_task_logger",
    "close_task_logger",
    "close_all_task_loggers",
    # TDX解析
    "TdxConfigFileParser",
    "BlockParser",
    # TDX底层工具（v2.2新增）
    "batch_get_ipo_dates",
    "batch_get_finance_info",
    "ServerTester",
    "test_server",
    "batch_test_servers",
    "get_fastest_servers",
    "TdxPathHelper",
    "find_tdx_root",
    "get_market_from_code",
    "tdx_bars_to_dataframe",
    "tdx_quotes_to_dataframe",
    "normalize_tdx_data",
    # TDX高级封装函数（v2.3新增）
    "get_security_list_batch",
    "get_security_list_all",
    "get_security_bars_by_interval",
    "get_security_bars_safe",
    "get_ipo_date_safe",
    "bars_to_dataframe_safe",
    "interval_to_category",
    "category_to_interval",
    # 队列和子进程辅助函数（v2.4新增，迁移自data_module_vnpy）
    "safe_put_queue",
    "get_queue_skip_stats",
    "reset_queue_skip_stats",
    "configure_subprocess_logging",
    # 向后兼容：保留带下划线的函数名
    "_safe_put_queue",
    "_get_queue_skip_stats",
    "_reset_queue_skip_stats",
    "_configure_subprocess_logging",
    # ========== 存储管理 ==========
    "StorageManager",
    "PreloadService",
    "LRUCacheManager",
    "SharedMemoryManager",
    # ========== 质量管理 ==========
    "DataQualityLevel",
    "ValidationStatus",
    "QualityScanResult",
    "ValidationResult",
    "HealthCheckResult",
    "DataSensor",
    "StatelessValidator",
    "DataFileWatcher",
    "HealthChecker",
    "IPODateCache",
    # ========== 运行时管理 ==========
    "DataQueryPriority",
    "UnifiedDataManager",
    "TdxDataSource",
    "VirtualDataSource",
    "SubscriptionManager",
    # ========== 负载均衡 ==========
    "ResourceMetrics",
    "ResourceMonitor",
    "DynamicConfigCalculator",
    "ServerInfo",
    "ServerPoolManager",
    "LoadBalancer",
]

# ==============================================================================
# 版本信息
# ==============================================================================

__version__ = "3.6.0"
__author__ = "AI Assistant"
__description__ = "数据中心模块 - 架构v3.6完整重构版（代码精简和性能优化）"
