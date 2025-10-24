# -*- coding: utf-8 -*-
"""System VnPy包 - 监控进程V2架构.

🔧 v0.50重构：debug友好的文件组织（已合并小文件）
- monitor_core.py: 监控进程V2 + 系统分析器（SystemBottleneckAnalyzer, ScenarioAnalyzer）
- monitors.py: 基础监控工具 + 业务采集器（ProcessBottleneckAnalyzer, BusinessMetricsCollector）
- managers.py: 管理相关（ServiceHealthChecker, ProcessManager, SecurityManager）
- tools.py: 工具相关（诊断、文件、网络、性能工具）

核心功能模块:
- 监控进程V2: MonitoringProcessV2（asyncio+线程池混合并发）
- 系统分析: SystemBottleneckAnalyzer（系统级瓶颈分析，基于木桶理论）
- 场景分析: ScenarioAnalyzer（5大量化场景识别与优化）
- 进程分析: ProcessBottleneckAnalyzer（进程级瓶颈分析）
- 业务采集: BusinessMetricsCollector（量化业务指标采集）
- 自适应阈值: AdaptiveThresholdManager（统计学习+动态阈值）
- 硬盘SMART: SmartMonitor（pySMART集成）
- 硬件监控: HardwareMonitorFactory（LibreHardwareMonitor + 降级）
- 进程管理: ProcessManager, ServiceHealthChecker
- 安全管理: SecurityManager, EncryptionManager
- 工具集: 诊断、文件、网络、性能优化

调试提示:
- 监控进程核心逻辑全在monitor_core.py单文件，方便设置断点
- 启动入口: monitor_process_entry.py
- 日志文件: logs/monitor_process.log
"""

# 从monitor_core.py导入（监控进程V2核心 + 分析器）
from .monitor_core import (
    AdaptiveThresholdManager,
    DiskSmartData,
    HardwareMonitorFactory,
    MonitoringProcessV2,
    ScenarioAnalyzer,
    SmartMonitor,
    SystemBottleneckAnalyzer,
    ThresholdConfig,
    ThresholdResult,
)

# 从monitors.py导入（基础监控工具 + 业务采集器）
from .monitors import (
    BottleneckResult,
    BusinessMetricsCollector,
    HardwareMonitor,
    MonitoringProcess,
    ProcessBottleneckAnalyzer,
    ProcessMetrics,
    ProcessMonitor,
    ResourceMonitor,
    ResourceUsage,
    SystemInfo,
    SystemMonitor,
    get_business_metrics_collector,
    get_resource_usage,
    get_system_info,
)

# 从managers.py导入
from .managers import (
    AuditLogger,
    EncryptionManager,
    PermissionController,
    ProcessManager,
    SecurityManager,
    ServiceHealthChecker,
    ServiceRestarter,
)

# 从tools.py导入
from .tools import (
    AutoFixer,
    CacheManager,
    ConcurrencyOptimizer,
    DirectoryManager,
    FileManager,
    FileOperations,
    FilePermissionManager,
    LogAnalyzer,
    MemoryOptimizer,
    NetworkTester,
    PerformanceAnalyzer,
    PerformanceOptimizer,
    PortScanner,
    SSLValidator,
    batch_file_operations,
    optimize_performance,
    scan_ports,
    test_connectivity,
)

__all__ = [
    # 监控进程V2核心
    "MonitoringProcessV2",
    "AdaptiveThresholdManager",
    "SmartMonitor",
    "HardwareMonitorFactory",
    "ThresholdConfig",
    "ThresholdResult",
    "DiskSmartData",
    "SystemBottleneckAnalyzer",
    "ScenarioAnalyzer",
    # 基础监控工具
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    "SystemInfo",
    "ResourceUsage",
    "ProcessMonitor",
    "ProcessBottleneckAnalyzer",
    "ProcessMetrics",
    "BottleneckResult",
    "MonitoringProcess",
    "get_system_info",
    "get_resource_usage",
    # 业务指标采集
    "BusinessMetricsCollector",
    "get_business_metrics_collector",
    # 管理相关
    "ServiceHealthChecker",
    "ServiceRestarter",
    "ProcessManager",
    "SecurityManager",
    "PermissionController",
    "EncryptionManager",
    "AuditLogger",
    # 工具相关 - 诊断
    "LogAnalyzer",
    "PerformanceAnalyzer",
    "AutoFixer",
    # 工具相关 - 网络
    "NetworkTester",
    "PortScanner",
    "SSLValidator",
    "test_connectivity",
    "scan_ports",
    # 工具相关 - 文件
    "FileOperations",
    "FileManager",
    "DirectoryManager",
    "FilePermissionManager",
    "batch_file_operations",
    # 工具相关 - 性能
    "PerformanceOptimizer",
    "CacheManager",
    "MemoryOptimizer",
    "ConcurrencyOptimizer",
    "optimize_performance",
]
