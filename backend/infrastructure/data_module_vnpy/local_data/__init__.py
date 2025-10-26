# -*- coding: utf-8 -*-
"""
本地数据管理模块

包含本地数据存储、感知、校验相关的功能：
- 统一数据管理器
- 数据质量感知和校验
- 自适应扫描配置
- 文件监视器
- 预加载服务
- 健康检查
"""

# 传统数据质量核心
from .data_quality import (
    StorageManager,
    DataValidator,
    ValidationSummary,
    DataFileWatcher,
    DataSensor,
    QualityOverview,
    KlineFileWatcher,
    HealthChecker,
    format_quality_config_summary,
)

# 统一数据管理器
from .unified_data_manager import UnifiedDataManager, PreloadService

# 中期优化：无状态验证器和共享内存（已合并到validators.py）
from .validators import (
    StatelessValidator,
    StatelessValidationResult,
    ValidationContext,
    validate_symbol_stateless,
    IncrementalScanManager,
    ScanRecord,
    ScanMetadata,
    create_incremental_scan_manager,
    GPUValidator,
    GPUDetector,
    create_gpu_validator,
    detect_and_log_gpu,
)
from .cache_and_memory import (
    # 缓存管理
    LRUCacheManager,
    CacheStats,
    create_lru_cache,
    lru_cache,
    # 共享内存管理
    SharedMemoryManager,
    create_shared_validation_context,
)

__all__ = [
    # 传统数据质量
    "StorageManager",
    "DataValidator",
    "ValidationSummary",
    "DataFileWatcher",
    "DataSensor",
    "QualityOverview",
    "KlineFileWatcher",
    "HealthChecker",
    "format_quality_config_summary",
    # 统一数据管理
    "UnifiedDataManager",
    "PreloadService",
    # 中期优化
    "StatelessValidator",
    "StatelessValidationResult",
    "ValidationContext",
    "validate_symbol_stateless",
    "SharedMemoryManager",
    "create_shared_validation_context",
    "IncrementalScanManager",
    "ScanRecord",
    "ScanMetadata",
    "create_incremental_scan_manager",
    # 长期优化
    "GPUValidator",
    "GPUDetector",
    "create_gpu_validator",
    "detect_and_log_gpu",
    # Cache Management
    "LRUCacheManager",
    "CacheStats",
    "create_lru_cache",
    "lru_cache",
]
