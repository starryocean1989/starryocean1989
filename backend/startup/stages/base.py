# -*- coding: utf-8 -*-
"""
启动阶段基类 - 定义阶段接口和通用功能

提供阶段化启动流程的抽象基类，每个阶段独立、可测试、可回滚。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

from backend.infrastructure.system_vnpy.logging_system import bind_logger_defaults
from backend.startup.context import StartupContext

logger = bind_logger_defaults(
    logging.getLogger("backend.startup.stages.base"),
    log_type="SYSTEM",
    scenario="application_startup",
)


@dataclass
class StageResult:
    """阶段执行结果

    Attributes:
        success: 是否成功
        message: 结果消息
        elapsed_ms: 耗时（毫秒）
        data: 附加数据（可选）
        error: 错误信息（如果失败）
    """

    success: bool
    message: str = ""
    elapsed_ms: float = 0.0
    data: Optional[Dict[str, Any]] = None
    error: Optional[Exception] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.data is None:
            self.data = {}


class StartupStage(ABC):
    """启动阶段基类

    职责：
    - 定义阶段接口
    - 提供阶段通用功能（日志、进度报告等）
    - 支持阶段回滚
    """

    def __init__(self, name: str, description: str = ""):
        """初始化阶段

        Args:
            name: 阶段名称（如 "env_setup", "logging_init"）
            description: 阶段描述（可选）
        """
        self.name = name
        self.description = description
        self.logger = bind_logger_defaults(
            logging.getLogger(f"backend.startup.stages.{name}"),
            log_type="SYSTEM",
            scenario="application_startup",
        )
        # 注意：新架构不再需要startup_logger，日志系统已统一管理

    async def execute(self, context: StartupContext) -> StageResult:
        """执行阶段逻辑（模板方法）

        这是模板方法，子类应该重写 `_execute()` 方法。

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()

        try:
            # 记录阶段开始（新架构直接使用logger）
            self.logger.info(
                f"📍 阶段 {self.name} 开始",
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 执行阶段逻辑
            result = await self._execute(context)

            # 计算耗时
            elapsed_ms = (time.time() - start_time) * 1000
            result.elapsed_ms = elapsed_ms

            # 记录阶段成功（新架构直接使用logger）
            if result.success:
                self.logger.info(
                    f"✅ 阶段 {self.name} 完成 ({elapsed_ms:.0f}ms)",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

            # 记录阶段失败（新架构直接使用logger）
            else:
                self.logger.error(
                    f"❌ [StartupStage] 阶段 {self.name} 失败: {result.message}",
                    exc_info=result.error,
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            return result

        except Exception as e:
            # 捕获未处理的异常
            elapsed_ms = (time.time() - start_time) * 1000

            # 记录严重错误（启动阶段失败）
            self.logger.critical(
                "🔥 启动阶段 %s 执行失败: %s",
                self.name, e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )

            # 新架构直接使用logger
            self.logger.error(
                f"❌ [StartupStage] 阶段 {self.name} 发生异常",
                exc_info=True,
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return StageResult(
                success=False,
                message=f"阶段 {self.name} 发生异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    @abstractmethod
    async def _execute(self, context: StartupContext) -> StageResult:
        """执行阶段逻辑（子类实现）

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        pass

    async def rollback(self, context: StartupContext):
        """回滚阶段（可选实现）

        如果阶段失败，可以选择回滚操作。

        Args:
            context: 启动上下文
        """
        self.logger.warning(
            f"阶段 {self.name} 未实现回滚逻辑",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )
        # 子类可以重写此方法实现回滚逻辑

    def _report_progress(self, message: str, progress: int):
        """报告初始化进度

        Args:
            message: 进度消息
            progress: 进度百分比(0-100)
        """
        self.logger.info(f"[进度 {progress}%] {message}")

