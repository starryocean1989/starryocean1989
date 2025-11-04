# -*- coding: utf-8 -*-
"""
启动工作线程基类 - 定义Worker接口和通用功能

提供后台工作线程的抽象基类，用于执行初始化任务。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.workers.base")


@dataclass
class WorkerResult:
    """Worker执行结果

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


class StartupWorker(ABC):
    """启动工作线程基类

    职责：
    - 定义Worker接口
    - 提供Worker通用功能（日志、进度报告等）
    - 支持异步执行
    """

    def __init__(self, name: str, description: str = ""):
        """初始化Worker

        Args:
            name: Worker名称（如 "backend_initializer", "cache_validator"）
            description: Worker描述（可选）
        """
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"backend.startup.workers.{name}")

    async def run(self, context: StartupContext) -> WorkerResult:
        """运行Worker（模板方法）

        这是模板方法，子类应该重写 `_run()` 方法。

        Args:
            context: 启动上下文

        Returns:
            WorkerResult: Worker执行结果
        """
        start_time = time.time()

        try:
            self.logger.info(f"Worker {self.name} 开始执行")

            # 执行Worker逻辑
            result = await self._run(context)

            # 计算耗时
            elapsed_ms = (time.time() - start_time) * 1000
            result.elapsed_ms = elapsed_ms

            # 记录结果
            if result.success:
                self.logger.info(f"Worker {self.name} 执行成功 ({elapsed_ms:.0f}ms)")
            else:
                self.logger.error(
                    f"❌ [StartupWorker] Worker {self.name} 执行失败: {result.message}",
                    exc_info=result.error,
                    extra={"log_type": "SYSTEM"}
                )

            return result

        except Exception as e:
            # 捕获未处理的异常
            elapsed_ms = (time.time() - start_time) * 1000

            self.logger.exception(f"Worker {self.name} 发生异常")

            return WorkerResult(
                success=False,
                message=f"Worker {self.name} 发生异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    @abstractmethod
    async def _run(self, context: StartupContext) -> WorkerResult:
        """运行Worker逻辑（子类实现）

        Args:
            context: 启动上下文

        Returns:
            WorkerResult: Worker执行结果
        """
        pass

    def _report_progress(self, message: str, progress: int):
        """报告初始化进度

        Args:
            message: 进度消息
            progress: 进度百分比(0-100)
        """
        self.logger.info(f"[进度 {progress}%] {message}")

