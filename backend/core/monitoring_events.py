# -*- coding: utf-8 -*-
"""系统监控事件类型定义.

所有监控相关的事件类型统一在此定义，便于管理和维护。
采用事件驱动架构，后端服务通过EventEngine推送事件，前端UI组件按需订阅。

架构模式：
监控进程 → (ZMQ) → SystemManagerService → (EventEngine) → UI组件(按需订阅)
"""

# 系统指标事件（CPU、内存、磁盘、网络使用率等）
EVENT_SYSTEM_METRICS = "eSystemMetrics"

# 硬件传感器事件（温度、功耗、电压、风扇转速等）
EVENT_HARDWARE_SENSORS = "eHardwareSensors"

# 瓶颈分析事件（系统性能瓶颈诊断）
EVENT_BOTTLENECK_ANALYSIS = "eBottleneckAnalysis"

# 场景分析事件（当前运行场景的优化建议）
EVENT_SCENARIO_ANALYSIS = "eScenarioAnalysis"

# 进程监控事件（Python进程、关键进程状态）
EVENT_PROCESS_MONITORING = "eProcessMonitoring"

# 服务状态事件（各服务的健康状态）
EVENT_SERVICE_MONITORING = "eServiceMonitoring"

# SMART数据事件（硬盘健康监控）
EVENT_SMART_DATA = "eSmartData"

# 性能指标汇总事件（多维度性能概览）
EVENT_PERFORMANCE_SUMMARY = "ePerformanceSummary"


__all__ = [
    "EVENT_SYSTEM_METRICS",
    "EVENT_HARDWARE_SENSORS",
    "EVENT_BOTTLENECK_ANALYSIS",
    "EVENT_SCENARIO_ANALYSIS",
    "EVENT_PROCESS_MONITORING",
    "EVENT_SERVICE_MONITORING",
    "EVENT_SMART_DATA",
    "EVENT_PERFORMANCE_SUMMARY",
]
