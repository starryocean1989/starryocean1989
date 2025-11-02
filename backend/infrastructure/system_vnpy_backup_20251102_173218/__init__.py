# -*- coding: utf-8 -*-
"""System VnPy包 - 监控进程V2架构.

🔧 v0.50重构：激进合并 - 3核心文件架构（debug友好）
最终文件结构（8个→3个）:
- system_toolkit.py: 系统工具包（合并 core_utils + monitoring_core + utilities精简版）
  包含：管理员权限、错误计数器、事件引擎、SMART监控、服务管理、诊断工具
- monitor_system.py: 监控系统完整模块（合并 monitor_core + monitors + monitor_process_entry）
  包含：MonitoringProcessV2、系统/进程监控、分析器、业务采集器、独立进程入口
- unified_log_system.py: 统一日志架构（保持独立）
  包含：LoggingHub、AI日志路由、日志规则验证

核心功能模块:
- 监控进程V2: MonitoringProcessV2（asyncio+线程池混合并发）
- 系统分析: SystemBottleneckAnalyzer（系统级瓶颈分析，基于木桶理论）
- 场景分析: ScenarioAnalyzer（5大量化场景识别与优化）
- 进程分析: ProcessBottleneckAnalyzer（进程级瓶颈分析）
- 业务采集: BusinessMetricsCollector（量化业务指标采集）
- 自适应阈值: AdaptiveThresholdManager（统计学习+动态阈值）
- 硬盘SMART: SmartMonitor（WMI包装器，带告警）+ WMISmartMonitor（WMI纯Python）
- 硬件监控: HardwareMonitorFactory（LibreHardwareMonitor + 降级）
- 进程管理: ProcessManager, ServiceHealthChecker, ServiceRestarter
- 诊断工具: LogAnalyzer, PerformanceAnalyzer, AutoFixer
- 网络工具: NetworkTester, PortScanner

调试提示:
- 监控进程核心逻辑全在monitor_system.py单文件，方便设置断点
- 启动入口: python -m backend.infrastructure.system_vnpy.monitor_system
- 日志系统: unified_log_system.py（AI日志、终端输出、路由规则）
"""

# 从system_toolkit导入（合并了 core_utils + monitoring_core + utilities精简版）
from .system_toolkit import (
    # Part 1-3: 管理员权限 + 错误计数器 + 终端输出（来自core_utils）
    is_admin,
    run_as_admin,
    ensure_admin,
    check_admin_for_hardware_monitoring,
    ErrorCounter,
    get_error_counter,
    print_stage,
    configure_debug,
    get_debug_config,
    # Part 4-6: 事件定义 + 监控引擎 + SMART监控（来自monitoring_core）
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
    MonitoredEventEngine,
    DiskType,
    SmartAttribute,
    DiskSmartData,
    WMISmartMonitor,
    get_wmi_smart_monitor,
    SmartMonitor,
    # Part 7-10: 实际使用的工具类（来自utilities精简版）
    ServiceHealthChecker,
    ServiceRestarter,
    ProcessManager,
    LogAnalyzer,
    PerformanceAnalyzer,
    AutoFixer,
    NetworkTester,
    PortScanner,
    test_connectivity,
    scan_ports,
)

# 从monitor_system.py导入（合并了monitor_core.py + monitors.py）
from .monitor_system import (
    # 从原 monitor_core.py
    AdaptiveThresholdManager,
    HardwareMonitorFactory,
    MonitoringProcessV2,
    ScenarioAnalyzer,
    SystemBottleneckAnalyzer,
    ThresholdConfig,
    ThresholdResult,
    # 从原 monitors.py
    BottleneckResult,
    BusinessMetricsCollector,
    HardwareMonitor,
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

# utilities.py 已被合并到 system_toolkit.py，此处不再需要导入

__all__ = [
    # Part 1-3: 管理员权限 + 错误计数器 + 终端输出（system_toolkit）
    "is_admin",
    "run_as_admin",
    "ensure_admin",
    "check_admin_for_hardware_monitoring",
    "ErrorCounter",
    "get_error_counter",
    "print_stage",
    "configure_debug",
    "get_debug_config",
    # Part 4-6: 事件定义 + 监控引擎 + SMART监控（system_toolkit）
    "MonitoredEventEngine",
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
    "DiskType",
    "SmartAttribute",
    "DiskSmartData",
    "WMISmartMonitor",
    "get_wmi_smart_monitor",
    "SmartMonitor",
    # Part 7-10: 实际使用的工具类（system_toolkit）
    "ServiceHealthChecker",
    "ServiceRestarter",
    "ProcessManager",
    "LogAnalyzer",
    "PerformanceAnalyzer",
    "AutoFixer",
    "NetworkTester",
    "PortScanner",
    "test_connectivity",
    "scan_ports",
    # 监控系统（monitor_system）
    "MonitoringProcessV2",
    "AdaptiveThresholdManager",
    "HardwareMonitorFactory",
    "ThresholdConfig",
    "ThresholdResult",
    "SystemBottleneckAnalyzer",
    "ScenarioAnalyzer",
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    "SystemInfo",
    "ResourceUsage",
    "ProcessMonitor",
    "ProcessBottleneckAnalyzer",
    "ProcessMetrics",
    "BottleneckResult",
    "get_system_info",
    "get_resource_usage",
    "BusinessMetricsCollector",
    "get_business_metrics_collector",
]
