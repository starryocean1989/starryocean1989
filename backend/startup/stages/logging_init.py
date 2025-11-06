# -*- coding: utf-8 -*-
"""
日志系统初始化阶段 - 初始化LoggingHub并重放缓冲日志

阶段1：日志系统初始化（5-10%）
- 使用MemoryHandler缓冲日志系统初始化前的日志
- 初始化LoggingHub
- 重放缓冲日志

注意：核心逻辑已迁移到 logging_system.py，此文件只保留入口
"""

import logging
import time
from logging.handlers import MemoryHandler
from typing import Optional

from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext
from backend.infrastructure.system_vnpy.logging_system import (
    PersistentBufferHandler,
    setup_memory_logging,
    initialize_logging_hub_complete,
    MultiProcessLogCollector,
    get_logging_hub,
)
import multiprocessing


class LoggingInitStage(StartupStage):
    """日志系统初始化阶段

    职责：
    - 使用MemoryHandler缓冲日志系统初始化前的日志
    - 初始化LoggingHub
    - 重放缓冲日志

    注意：核心逻辑在 logging_system.py 中，此文件只保留入口
    """

    def __init__(self):
        """初始化日志系统初始化阶段"""
        super().__init__(
            name="logging_init",
            description="日志系统初始化 - 初始化LoggingHub并重放缓冲日志",
        )
        self.memory_handler: Optional[MemoryHandler] = None
        self.persistent_buffer: Optional[PersistentBufferHandler] = None
        self.log_collector: Optional[MultiProcessLogCollector] = None

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行日志系统初始化逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果

        注意：核心逻辑在 logging_system.py 中，此方法只负责调用
        """
        start_time = time.time()
        logger = logging.getLogger("backend.startup.stages.logging_init")

        try:
            # DEBUG日志（记录初始化开始）
            logger.debug(
                "[LOG-INIT] 日志系统初始化开始",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"},
            )

            # 1. 获取环境准备阶段设置的MemoryHandler（如果存在）
            # 否则创建新的MemoryHandler（核心逻辑在logging_system.py中）
            memory_handler = getattr(context, "_memory_handler", None)
            if memory_handler is None:
                logger.debug(
                    "[LOG-INIT] MemoryHandler不存在，创建新的MemoryHandler",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"},
                )
                memory_handler, persistent_buffer = setup_memory_logging()
                self.persistent_buffer = persistent_buffer
            else:
                buffered_count = (
                    len(memory_handler.buffer) if hasattr(memory_handler, "buffer") else 0
                )
                logger.debug(
                    "[LOG-INIT] 使用环境准备阶段的MemoryHandler，已缓冲%d条日志",
                    buffered_count,
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"},
                )
                # 获取持久化缓冲Handler（如果存在）
                self.persistent_buffer = getattr(context, "_persistent_buffer", None)
            self.memory_handler = memory_handler

            # 2. 初始化LoggingHub并重放缓冲日志（核心逻辑在logging_system.py中）
            logger.debug(
                "[LOG-INIT] 开始初始化LoggingHub",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"},
            )
            logging_hub = await initialize_logging_hub_complete(
                memory_handler, scenario="application_startup"
            )

            if not logging_hub:
                # 降级处理失败
                logger.error(
                    "[LOG-INIT] ❌ LoggingHub初始化失败，使用降级日志输出",
                    extra={"log_type": "ALERT", "scenario": "application_startup"},
                )
                return StageResult(
                    success=False,
                    message="LoggingHub初始化失败，使用降级日志输出",
                    elapsed_ms=(time.time() - start_time) * 1000,
                )

            # 3. 初始化MultiProcessLogCollector（用于跨进程日志收集）
            logger.debug(
                "[LOG-INIT] 开始初始化MultiProcessLogCollector",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"},
            )
            try:
                log_collector = MultiProcessLogCollector(logging_hub)
                log_collector.start()
                self.log_collector = log_collector

                # 将日志队列保存到context（供子进程使用）
                context.log_queue = log_collector.get_queue()

                logger.info(
                    "[LOG-INIT] ✅ MultiProcessLogCollector已启动",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                logger.debug(
                    "[LOG-INIT] 日志队列已保存到context",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"},
                )
            except Exception as e:
                logger.warning(
                    f"[LOG-INIT] ⚠️ MultiProcessLogCollector初始化失败: {e}，将使用降级方案",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"},
                )
                # 降级处理：继续执行，但不支持跨进程日志收集
                context.log_queue = None

            # 4. 标记日志系统已初始化
            context.logging_hub_initialized = True
            logger.debug(
                "[LOG-INIT] 日志系统已标记为已初始化",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"},
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "[LOG-INIT] 日志系统初始化完成: 耗时=%.0fms",
                elapsed_ms,
                extra={"log_type": "SYSTEM", "scenario": "application_startup"},
            )

            return StageResult(
                success=True,
                message="日志系统初始化完成",
                elapsed_ms=elapsed_ms,
                data={
                    "logging_hub": logging_hub,
                    "memory_handler": memory_handler,
                    "log_collector": self.log_collector,
                },
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            logger.error(
                "[LOG-INIT] ❌ 日志系统初始化失败: %s",
                str(e),
                extra={"log_type": "ALERT", "scenario": "application_startup"},
                exc_info=True,
            )

            return StageResult(
                success=False,
                message="日志系统初始化失败: %s" % str(e),
                elapsed_ms=elapsed_ms,
                error=e,
            )
