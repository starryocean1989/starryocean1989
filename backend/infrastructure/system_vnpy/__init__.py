# -*- coding: utf-8 -*-
"""System VnPy包 - 监控进程V2架构.

🔧 v0.50重构：激进合并 - debug友好的文件组织（大文件优化）
- monitor_system.py: 监控系统完整模块（合并 monitor_core.py + monitors.py）
  包含：MonitoringProcessV2、系统/进程监控、分析器、业务采集器
- utilities.py: 工具和管理模块（合并 managers.py + tools.py）
  包含：服务/进程/安全管理、诊断/文件/网络/性能工具

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
- 监控进程核心逻辑全在monitor_system.py单文件，方便设置断点
- 启动入口: monitor_process_entry.py
- 日志文件: logs/monitor_process.log
"""

# 从monitor_system.py导入（合并了monitor_core.py + monitors.py）
from .monitor_system import (
    # 从原 monitor_core.py
    AdaptiveThresholdManager,
    DiskSmartData,
    HardwareMonitorFactory,
    MonitoringProcessV2,
    ScenarioAnalyzer,
    SmartMonitor,
    SystemBottleneckAnalyzer,
    ThresholdConfig,
    ThresholdResult,
    # 从原 monitors.py
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

# 从utilities.py导入（合并了managers.py + tools.py）
from .utilities import (
    # 管理相关（来自 managers.py）
    AuditLogger,
    EncryptionManager,
    PermissionController,
    ProcessManager,
    SecurityManager,
    ServiceHealthChecker,
    ServiceRestarter,
    # 工具相关（来自 tools.py）
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
