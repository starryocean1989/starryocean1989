# -*- coding: utf-8 -*-
"""System VnPy Package - 监控进程V2架构

## 重构版本: v1.0 (Complete Refactor)
## 创建日期: 2025-01-09

### 文件结构 (3个核心文件架构 - Debug友好)

**核心文件**:
- `core_engine.py`: 核心引擎与基础设施 (~1100行)
  - ConfigManager: 统一配置管理
  - CacheManager: 缓存管理
  - EventPublisher系列: 分类事件发布
  - EngineRegistry: 引擎注册表
  - SystemManagerEngine: 核心引擎

- `monitor_toolkit.py`: 监控工具集 (~1260行)
  - 管理员权限工具
  - 错误计数器
  - SMART监控
  - 事件定义
  - 监控版事件引擎
  - 服务工具
  - 性能分析
  - 网络工具

- `monitor_system.py`: 监控系统 (保留原架构,~6500行)
  - MonitoringProcessV2: 混合并发监控进程
  - 系统/进程/硬件监控
  - 瓶颈分析器
  - 场景分析器
  - 独立进程入口

**配置文件**:
- `config/system_config.yaml`: 系统监控配置
- `config/threshold_config.yaml`: 阈值配置
- `config/ping_servers.yaml`: 延迟测试池配置
- `config/speedtest_servers.yaml`: 带宽测试池配置
- `config/rules_*.yaml`: 日志规则配置

### 核心功能模块

**监控系统**:
- MonitoringProcessV2: asyncio+线程池混合并发
- SystemMonitor: 系统监控器
- HardwareMonitor: 硬件监控器
- SmartMonitor: SMART硬盘监控
- BusinessMetricsCollector: 业务指标采集

**分析器**:
- SystemBottleneckAnalyzer: 系统瓶颈分析(木桶理论)
- ScenarioAnalyzer: 场景识别与优化建议
- AdaptiveThresholdManager: 自适应阈值管理

**工具集**:
- 管理员权限工具
- 错误计数器
- SMART监控
- 服务健康检查
- 性能分析
- 网络测试

### 技术特性

- **事件驱动**: VnPy EventEngine松耦合通信
- **异步优先**: asyncio + native_iocp + native_ipc
- **智能负载**: 木桶理论评分,动态并发调整
- **进程隔离**: 监控进程独立运行
- **AI Debug友好**: Part分区标记,相关功能集中

### 调试提示

- 监控进程核心逻辑全在monitor_system.py单文件,方便设置断点
- 启动入口: python -m backend.infrastructure.system_vnpy.monitor_system
- 配置管理: core_engine.ConfigManager单例
- 事件系统: core_engine中的EventPublisher系列
"""

# ==============================================================================
# 从core_engine导入 - 核心引擎与基础设施
# ==============================================================================

from .core_engine import (
    # 配置管理
    ConfigManager,
    # 缓存管理
    CacheManager,
    CachedData,
    # 事件系统
    EventPublisher,
    SystemEventPublisher,
    HardwareEventPublisher,
    AlertEventPublisher,
    BusinessEventPublisher,
    # 引擎注册表
    EngineRegistry,
    # 核心引擎
    SystemManagerEngine,
)

# ==============================================================================
# 从monitor_toolkit导入 - 监控工具集
# ==============================================================================

from .monitor_toolkit import (
    # Part 1: 管理员权限工具
    is_admin,
    run_as_admin,
    ensure_admin,
    check_admin_for_hardware_monitoring,
    # Part 2: 错误计数器
    ErrorCounter,
    get_error_counter,
    # Part 3: SMART监控
    DiskType,
    SmartAttribute,
    DiskSmartData,
    WMISmartMonitor,
    get_wmi_smart_monitor,
    SmartMonitor,
    # Part 4: 事件定义
    EVENT_SYSTEM_METRICS,
    EVENT_HARDWARE_SENSORS,
    EVENT_BOTTLENECK_ANALYSIS,
    EVENT_SCENARIO_ANALYSIS,
    EVENT_PROCESS_MONITORING,
    EVENT_SERVICE_MONITORING,
    EVENT_SMART_DATA,
    EVENT_PERFORMANCE_SUMMARY,
    EVENT_SYSTEM_STATUS,
    EVENT_PERFORMANCE_METRICS,
    EVENT_SERVICE_STATUS,
    EVENT_DIAGNOSTIC_RESULT,
    EVENT_PROCESS_STATUS,
    EVENT_STRATEGY_STATUS_CHANGED,
    EVENT_GATEWAY_STATUS_CHANGED,
    EVENT_DATA_DOWNLOAD_COMPLETE,
    EVENT_RECORDING_STATUS_CHANGED,
    EVENT_LOG_RECORD,
    EVENT_ALERT_CREATED,
    EVENT_ALERT_UPDATED,
    # Part 5: 监控版事件引擎
    MonitoredEventEngine,
    # Part 6: 服务工具
    ServiceHealthChecker,
    ServiceRestarter,
    # Part 7: 性能分析
    PerformanceAnalyzer,
    LogAnalyzer,
    # Part 8: 网络工具
    NetworkTester,
    PortScanner,
    test_connectivity,
    scan_ports,
)

# ==============================================================================
# 从logging_system导入 - 统一日志系统（v6.0简化重构版）
# ==============================================================================

from .logging_system import (
    # 全局单例
    get_logging_hub,
)

# ==============================================================================
# 从monitor_system导入 - 监控系统(保留原架构)
# ==============================================================================

try:
    from .monitor_system import (
        # 阈值管理
        AdaptiveThresholdManager,
        ThresholdConfig,
        ThresholdResult,
        # 硬件监控工厂
        HardwareMonitorFactory,
        # 监控进程
        MonitoringProcessV2,
        # 分析器
        SystemBottleneckAnalyzer,
        ScenarioAnalyzer,
        # 监控器
        SystemMonitor,
        ResourceMonitor,
        HardwareMonitor,
        ProcessMonitor,
        # 数据结构
        SystemInfo,
        ResourceUsage,
        ProcessMetrics,
        BottleneckResult,
        # 业务采集器
        BusinessMetricsCollector,
        get_business_metrics_collector,
        # 便捷函数
        get_system_info,
        get_resource_usage,
    )
except ImportError as e:
    # 如果monitor_system未完成重构,提供警告但不中断导入
    import logging

    logger = logging.getLogger(__name__)
    logger.warning(f"无法导入monitor_system模块: {e}")
    logger.warning("某些监控功能可能不可用")

# ==============================================================================
# 模块导出清单
# ==============================================================================

__all__ = [
    # ========== core_engine ==========
    # 配置管理
    "ConfigManager",
    # 缓存管理
    "CacheManager",
    "CachedData",
    # 事件系统
    "EventPublisher",
    "SystemEventPublisher",
    "HardwareEventPublisher",
    "AlertEventPublisher",
    "BusinessEventPublisher",
    # 引擎注册表
    "EngineRegistry",
    # 核心引擎
    "SystemManagerEngine",
    # ========== unified_log_system ==========
    # 全局单例
    "get_logging_hub",
    # ========== monitor_toolkit ==========
    # 管理员权限工具
    "is_admin",
    "run_as_admin",
    "ensure_admin",
    "check_admin_for_hardware_monitoring",
    # 错误计数器
    "ErrorCounter",
    "get_error_counter",
    # SMART监控
    "DiskType",
    "SmartAttribute",
    "DiskSmartData",
    "WMISmartMonitor",
    "get_wmi_smart_monitor",
    "SmartMonitor",
    # 事件定义
    "EVENT_SYSTEM_METRICS",
    "EVENT_HARDWARE_SENSORS",
    "EVENT_BOTTLENECK_ANALYSIS",
    "EVENT_SCENARIO_ANALYSIS",
    "EVENT_PROCESS_MONITORING",
    "EVENT_SERVICE_MONITORING",
    "EVENT_SMART_DATA",
    "EVENT_PERFORMANCE_SUMMARY",
    "EVENT_SYSTEM_STATUS",
    "EVENT_PERFORMANCE_METRICS",
    "EVENT_SERVICE_STATUS",
    "EVENT_DIAGNOSTIC_RESULT",
    "EVENT_PROCESS_STATUS",
    "EVENT_STRATEGY_STATUS_CHANGED",
    "EVENT_GATEWAY_STATUS_CHANGED",
    "EVENT_DATA_DOWNLOAD_COMPLETE",
    "EVENT_RECORDING_STATUS_CHANGED",
    "EVENT_LOG_RECORD",
    "EVENT_ALERT_CREATED",
    "EVENT_ALERT_UPDATED",
    # 监控版事件引擎
    "MonitoredEventEngine",
    # 服务工具
    "ServiceHealthChecker",
    "ServiceRestarter",
    # 性能分析
    "PerformanceAnalyzer",
    "LogAnalyzer",
    # 网络工具
    "NetworkTester",
    "PortScanner",
    "test_connectivity",
    "scan_ports",
    # ========== monitor_system (条件导入) ==========
    # 阈值管理
    "AdaptiveThresholdManager",
    "ThresholdConfig",
    "ThresholdResult",
    # 硬件监控工厂
    "HardwareMonitorFactory",
    # 监控进程
    "MonitoringProcessV2",
    # 分析器
    "SystemBottleneckAnalyzer",
    "ScenarioAnalyzer",
    # 监控器
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    "ProcessMonitor",
    # 数据结构
    "SystemInfo",
    "ResourceUsage",
    "ProcessMetrics",
    "BottleneckResult",
    # 业务采集器
    "BusinessMetricsCollector",
    "get_business_metrics_collector",
    # 便捷函数
    "get_system_info",
    "get_resource_usage",
]

# 版本信息
__version__ = "1.0.0"
__author__ = "System Refactoring Team"
__date__ = "2025-01-09"
