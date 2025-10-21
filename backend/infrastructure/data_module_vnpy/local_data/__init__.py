# -*- coding: utf-8 -*-
"""
本地数据管理模块

包含本地数据存储、感知、校验相关的功能：
- 统一数据管理器
- 数据质量感知和校验
- 文件监视器
- 预加载服务
- 健康检查
- 混合异步扫描引擎
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
)

# 统一数据管理器
from .unified_data_manager import UnifiedDataManager, PreloadService

# 🆕 混合异步引擎
from .hybrid_async_engine import (
    ResourceMonitor,
    AdaptiveQualityConfig,
    FileMetadataScanner,
    FileMetadata,
    SmartScheduler,
    ScanTask,
    AsyncIOExecutor,
    CPUIntensiveWorker,
    ConcurrencyTuner,
    PerformanceTracker,
    PhaseTimer,
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
    # 统一数据管理
    "UnifiedDataManager",
    "PreloadService",
    # 混合异步引擎
    "ResourceMonitor",
    "AdaptiveQualityConfig",
    "FileMetadataScanner",
    "FileMetadata",
    "SmartScheduler",
    "ScanTask",
    "AsyncIOExecutor",
    "CPUIntensiveWorker",
    "ConcurrencyTuner",
    "PerformanceTracker",
    "PhaseTimer",
]
