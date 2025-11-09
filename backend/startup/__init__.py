# -*- coding: utf-8 -*-
"""
启动架构模块 - 统一启动编排器

提供统一的启动流程管理，包括：
- StartupOrchestrator: 启动编排器
- StartupContext: 启动上下文
- Stages: 启动阶段
- Workers: 后台工作线程
- Logging: 启动日志系统
"""

from backend.startup.orchestrator import StartupOrchestrator, StartupResult
from backend.startup.context import StartupContext
from backend.startup.event_bus import EventBus, StartupEvent, StartupEventType, ReadinessBarrier
from backend.startup.plan import StartupPlan, StartupNode
from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.workers.base import StartupWorker, WorkerResult

# 导入所有阶段类
from backend.startup.stages import (
    EnvSetupStage,
    LoggingInitStage,
    QtFrameworkStage,
    BackendInitStage,
    UIActivationStage,
)

__all__ = [
    "StartupOrchestrator",
    "StartupResult",
    "StartupContext",
    "StartupStage",
    "StageResult",
    "StartupWorker",
    "WorkerResult",
    "EventBus",
    "StartupEvent",
    "StartupEventType",
    "ReadinessBarrier",
    "StartupPlan",
    "StartupNode",
    # 阶段类
    "EnvSetupStage",
    "LoggingInitStage",
    "QtFrameworkStage",
    "BackendInitStage",
    "UIActivationStage",
]

