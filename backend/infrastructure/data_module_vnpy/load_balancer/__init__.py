# -*- coding: utf-8 -*-
"""
统一负载均衡模块 - 极限合并版（单文件）

本模块已完成极限合并：将原8个独立文件合并为1个统一文件load_balancer.py（6,330行）

核心组件：
- LoadBalancer: 统一负载均衡器（单例）
- BaseTask, NetworkTask, LocalProcessingTask: 任务基类
- SystemMetricsMonitor: 系统监控指标获取器
- ResourcePressureEvaluator: 资源压力评估器
- DynamicConfigCalculator: 动态配置计算器
- LoadBalancerQueueFacade: 队列化门面
- ServerPoolManager: 服务器池管理（已合并）
- ParameterTuner: 参数调优（已合并）
- LoadBalancerMonitoringService: 监控服务（已合并）

使用示例：
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LoadBalancer,
        NetworkTask,
        TaskMetrics,
        TaskType,
        ResourceProfile,
        get_load_balancer,
    )

    # 定义任务
    class MyTask(NetworkTask):
        def _define_metrics(self):
            return TaskMetrics(
                task_name="my_task",
                task_type=TaskType.NETWORK,
                resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
                critical_metrics=["network_speed"],
                estimated_connections=100,
            )

        def execute(self, config):
            # 使用动态配置执行任务
            pass

    # 使用LoadBalancer
    load_balancer = get_load_balancer()
    task = MyTask("my_task")
    config = load_balancer.get_optimal_config(task)
    result = task.execute(config)

极限合并说明：
================================================================================
原结构（8个文件）                                 → 新结构（1个文件）
--------------------------------------------------------------------------------
1. lb_core.py (1,246行)                           ┐
2. lb_monitoring.py (1,109行)                     │
3. lb_execution.py (1,227行)                      │
4. queue_system.py (1,034行)                      ├─→ load_balancer.py (6,330行)
5. server_pool_manager.py (1,140行)               │
6. parameter_tuning.py (406行)                    │
7. resource_management.py (504行)                 │
8. loadbalancer_service.py (271行)                │
9. intelligent_adaptive_tuner.py (166行)          ┘

合并优势：
- 文件数量减少：9个 → 1个（减少88.9%）
- Debug上下文友好：所有逻辑在一个文件中，无需跨文件跳转
- AI分析友好：大型语言模型可一次性读取完整逻辑
- API 100%向后兼容：所有导入语句保持有效
- 模块清晰：按功能分区，每个分区有明确标识

文件分区：
- 第1部分：任务定义（枚举、数据类、任务基类）
- 第2部分：策略配置（模型配置、策略定义、配置计算）
- 第3部分：监控评估（系统监控、压力评估、告警管理）
- 第4部分：执行层（执行模型、进程池、流式处理）
- 第5部分：队列系统（任务队列、QThread Worker、调度器、队列门面）
- 第6部分：资源管理（资源限制配置、Job Objects、应用层限制器、Qt监控）
- 第7部分：服务器池管理（ServerPoolManager、便捷函数）
- 第8部分：参数调优（ParameterSet、ParameterTuner、预定义参数组合）
- 第9部分：监控服务和LoadBalancer主类

合并日期：2025-10-26
================================================================================
"""

# ==================== 从单文件导入所有内容 ====================

from .load_balancer import (
    # ========== 第1部分：任务定义 ==========
    TaskType,
    ResourceProfile,
    TaskMetrics,
    BaseTask,
    NetworkTask,
    LocalProcessingTask,
    # ========== 第2部分：策略配置 ==========
    ModelConfig,
    AdjustmentStrategy,
    ExecutionPlan,
    AdaptiveThresholdCalculator,
    get_adaptive_calculator,
    ExecutionPolicy,
    DynamicConfigCalculator,
    # ========== 第3部分：监控评估 ==========
    SystemMetricsMonitor,
    ResourcePressure,
    ResourceMonitor,
    ResourcePressureEvaluator,
    LoadBalancerMetricsCollector,
    PerformanceAlertManager,
    Alert,
    AlertLevel,
    AlertRule,
    log_alert_callback,
    create_metrics_collector,
    create_alert_manager,
    # ========== 第4部分：执行层 ==========
    TaskUnit,
    TaskResult,
    ExecutionModel,
    MultiProcessAsyncModel,
    PersistentProcessPool,
    MultiProcessBatchModel,
    StreamProcessingModel,
    AdaptiveBatchSizeCalculatorFull,
    ChunkReader,
    StreamAggregator,
    EnhancedStreamProcessor,
    get_process_pool,
    get_adaptive_batch_calculator,
    # ========== 第5部分：队列系统 ==========
    TaskPriority,
    TaskStatus,
    TaskMetadata,
    TaskQueue,
    QTaskWorker,
    TaskQueueManager,
    ExecutionStrategy,
    AdaptiveScheduler,
    PriorityScheduler,
    HybridScheduler,
    LoadBalancerQueueFacade,
    get_queue_facade,
    # ========== 第6部分：资源管理 ==========
    ResourceLimitConfig,
    WindowsJobObjectLimiter,
    ApplicationLevelLimiter,
    QResourceMonitor,
    HybridResourceLimiter,
    # ========== 第7部分：服务器池 ==========
    ServerPoolManager,
    server_pool_manager,
    get_best_servers,
    get_best_server,
    get_all_servers,
    get_verified_servers_random,
    get_verified_servers,
    get_random_servers,
    ServerPoolTestTask,
    # ========== 第8部分：参数调优 ==========
    ParameterSet,
    PerformanceMetrics,
    TuningResult,
    ParameterTuner,
    get_default_parameter_sets,
    create_parameter_tuner,
    # ========== 第9部分：服务层和核心类 ==========
    LoadBalancerMonitoringService,
    get_loadbalancer_service,
    reset_loadbalancer_service,
    LoadBalancer,
    get_load_balancer,
    # ========== 智能调优器 ==========
    IntelligentAdaptiveTuner,
)

__all__ = [
    # ========== 第1部分：任务定义 ==========
    "TaskType",
    "ResourceProfile",
    "TaskMetrics",
    "BaseTask",
    "NetworkTask",
    "LocalProcessingTask",
    # ========== 第2部分：策略配置 ==========
    "ModelConfig",
    "AdjustmentStrategy",
    "ExecutionPlan",
    "AdaptiveThresholdCalculator",
    "get_adaptive_calculator",
    "ExecutionPolicy",
    "DynamicConfigCalculator",
    # ========== 第3部分：监控评估 ==========
    "SystemMetricsMonitor",
    "ResourcePressure",
    "ResourceMonitor",
    "ResourcePressureEvaluator",
    "LoadBalancerMetricsCollector",
    "PerformanceAlertManager",
    "Alert",
    "AlertLevel",
    "AlertRule",
    "log_alert_callback",
    "create_metrics_collector",
    "create_alert_manager",
    # ========== 第4部分：执行层 ==========
    "TaskUnit",
    "TaskResult",
    "ExecutionModel",
    "MultiProcessAsyncModel",
    "PersistentProcessPool",
    "MultiProcessBatchModel",
    "StreamProcessingModel",
    "AdaptiveBatchSizeCalculatorFull",
    "ChunkReader",
    "StreamAggregator",
    "EnhancedStreamProcessor",
    "get_process_pool",
    "get_adaptive_batch_calculator",
    # ========== 第5部分：队列系统 ==========
    "TaskPriority",
    "TaskStatus",
    "TaskMetadata",
    "TaskQueue",
    "QTaskWorker",
    "TaskQueueManager",
    "ExecutionStrategy",
    "AdaptiveScheduler",
    "PriorityScheduler",
    "HybridScheduler",
    "LoadBalancerQueueFacade",
    "get_queue_facade",
    # ========== 第6部分：资源管理 ==========
    "ResourceLimitConfig",
    "WindowsJobObjectLimiter",
    "ApplicationLevelLimiter",
    "QResourceMonitor",
    "HybridResourceLimiter",
    # ========== 第7部分：服务器池 ==========
    "ServerPoolManager",
    "server_pool_manager",
    "get_best_servers",
    "get_best_server",
    "get_all_servers",
    "get_verified_servers_random",
    "get_verified_servers",
    "get_random_servers",
    "ServerPoolTestTask",
    # ========== 第8部分：参数调优 ==========
    "ParameterSet",
    "PerformanceMetrics",
    "TuningResult",
    "ParameterTuner",
    "get_default_parameter_sets",
    "create_parameter_tuner",
    # ========== 第9部分：服务层和核心类 ==========
    "LoadBalancerMonitoringService",
    "get_loadbalancer_service",
    "reset_loadbalancer_service",
    "LoadBalancer",
    "get_load_balancer",
    # ========== 智能调优器 ==========
    "IntelligentAdaptiveTuner",
]
