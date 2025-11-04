# -*- coding: utf-8 -*-
"""
日志系统初始化阶段 - 初始化LoggingHub并重放缓冲日志

阶段1：日志系统初始化（5-10%）
- 使用MemoryHandler缓冲日志系统初始化前的日志
- 初始化LoggingHub
- 重放缓冲日志
"""

import logging
import sys
import time
from logging.handlers import MemoryHandler
from pathlib import Path
from typing import Optional

from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext


class LoggingInitStage(StartupStage):
    """日志系统初始化阶段

    职责：
    - 使用MemoryHandler缓冲日志系统初始化前的日志
    - 初始化LoggingHub
    - 重放缓冲日志
    """

    def __init__(self):
        """初始化日志系统初始化阶段"""
        super().__init__(
            name="logging_init",
            description="日志系统初始化 - 初始化LoggingHub并重放缓冲日志",
        )
        self.memory_handler: Optional[MemoryHandler] = None

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行日志系统初始化逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()

        try:
            # 1. 获取环境准备阶段设置的MemoryHandler（如果存在）
            # 否则创建新的MemoryHandler
            memory_handler = getattr(context, '_memory_handler', None)
            if memory_handler is None:
                memory_handler = self._setup_memory_logging()
            self.memory_handler = memory_handler

            # 2. 初始化LoggingHub并重放缓冲日志
            logging_hub = await self._initialize_logging_hub(memory_handler, context)

            if not logging_hub:
                # 降级处理失败
                return StageResult(
                    success=False,
                    message="LoggingHub初始化失败，使用降级日志输出",
                    elapsed_ms=(time.time() - start_time) * 1000,
                )

            # 3. 标记日志系统已初始化
            context.logging_hub_initialized = True

            elapsed_ms = (time.time() - start_time) * 1000

            return StageResult(
                success=True,
                message="日志系统初始化完成",
                elapsed_ms=elapsed_ms,
                data={"logging_hub": logging_hub, "memory_handler": memory_handler},
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            return StageResult(
                success=False,
                message=f"日志系统初始化失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    def _setup_memory_logging(self) -> MemoryHandler:
        """设置MemoryHandler缓冲日志系统初始化前的日志

        Returns:
            MemoryHandler: MemoryHandler实例
        """
        # 修复编码问题：确保stdout/stderr使用UTF-8编码
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
            except (OSError, ValueError):
                pass
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8")  # type: ignore
            except (OSError, ValueError):
                pass

        # 配置root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)  # 接收所有级别的日志

        # 创建MemoryHandler作为临时缓冲（容量10000条）
        # target先设为None，LoggingHub初始化后再设置
        memory_handler = MemoryHandler(capacity=10000, target=None)
        memory_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(memory_handler)

        # 创建启动logger
        from backend.core.base import setup_logging as base_setup_logging

        logger = base_setup_logging(name="StartupOptimized", level="INFO")

        # 关键修复：移除logger自己的handlers，避免绕过LoggingHub
        # base_setup_logging会给logger添加StreamHandler，导致日志直接输出到stdout
        # 我们需要所有日志都通过LoggingHub统一路由
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

        # 设置propagate=True，让日志传播到root logger，经过LoggingHub处理
        logger.propagate = True

        return memory_handler

    async def _initialize_logging_hub(
        self, memory_handler: MemoryHandler, context: StartupContext
    ):
        """初始化LoggingHub并重放缓冲日志

        Args:
            memory_handler: MemoryHandler实例
            context: 启动上下文（用于获取阶段结果）

        Returns:
            LoggingHub实例或None
        """
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                get_ai_log_handler,
                get_logging_hub,
                start_ai_process,
            )

            root_logger = logging.getLogger()
            stage_logger = logging.getLogger("startup.stage")
            t0 = time.time()

            # 1. 初始化LoggingHub
            logging_hub = get_logging_hub()

            # 2. 创建并注入handlers
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)  # LoggingHub内部会根据规则过滤
            # 终端仅显示消息内容
            console_formatter = logging.Formatter("%(message)s")
            console_handler.setFormatter(console_formatter)
            logging_hub.set_console_handler(console_handler)

            # 创建常规文件Handler（logs/terminal.log）
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            file_handler = logging.FileHandler(log_dir / "terminal.log", mode="a", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # 接收所有级别
            # 文件保留完整格式
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            logging_hub.set_file_handler(file_handler)

            ai_handler = get_ai_log_handler()
            logging_hub.set_ai_log_handler(ai_handler)

            # 3. 启动AI流程
            ai_log_file = start_ai_process(
                "application_startup",
                metadata={
                    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    "platform": sys.platform,
                },
            )

            # 4. 集成有序日志队列（启动阶段）
            from backend.startup.startup_logging.startup_logger import OrderedLogQueue

            ordered_queue = OrderedLogQueue(max_wait_seconds=30)
            logging_hub.set_ordered_log_queue(ordered_queue)

            stage_logger.info(
                "✅ 有序日志队列初始化完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 5. 将LoggingHub添加到root logger
            root_logger.addHandler(logging_hub)

            # 6. 设置MemoryHandler的target为LoggingHub
            memory_handler.setTarget(logging_hub)

            # 7. 直接刷新MemoryHandler
            # LoggingHub会自动通过emit方法处理所有日志
            buffered_count = len(memory_handler.buffer)
            memory_handler.flush()

            # 8. 移除MemoryHandler（已完成使命）
            root_logger.removeHandler(memory_handler)
            memory_handler.close()

            # 9. 全局清理：移除所有logger的StreamHandler，确保所有日志都经过LoggingHub
            cleaned_count = self._cleanup_all_logger_handlers()

            # 10. 阶段1标题与分隔（此时LoggingHub已就绪）
            # 注意：阶段0的输出已经在env_setup阶段通过print直接输出，无需在这里补输出
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
            stage_logger.info("【阶段1: 日志系统初始化】 (5-10%)", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

            # 添加阶段1开始标记
            stage_logger.info("📍 阶段1: 日志系统初始化开始", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

            # 使用logger输出（此时已经过LoggingHub）
            # 阶段输出（使用STAGE_NODE以显示在Terminal）
            stage_logger.info(
                "✅ LoggingHub创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 路由规则统计
            try:
                re = logging_hub._routing_engine
                stage_logger.info(
                    "✅ 路由规则引擎初始化完成", 
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                )
                stage_logger.info(
                    f"   - 全局规则: {len(getattr(re, 'global_rules', {}))} 个LogType",
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"},
                )
                stage_logger.info(
                    f"   - 阶段规则: {len(getattr(re, 'stage_rules', {}))} 个阶段",
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"},
                )
                stage_logger.info(
                    f"   - 模块规则: {len(getattr(re, 'module_rules', {}))} 个模块",
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"},
                )
                stage_logger.info(
                    f"   - 场景规则: {len(getattr(re, 'scenario_rules', {}))} 个场景",
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"},
                )
            except Exception:
                pass

            # AI日志Handler信息
            stage_logger.info(
                "✅ AI日志Handler初始化完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )
            stage_logger.info(
                f"  - 基础目录: {Path('logs/ai').absolute()}", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # MemoryHandler日志重放信息
            stage_logger.info(
                f"✅ MemoryHandler日志重放完成 ({buffered_count}条)", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 有序日志队列信息（如果已启用）
            if ordered_queue:
                stage_logger.info(
                    "✅ 有序日志队列已启用（启动阶段日志将按顺序输出）",
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"},
                )

            # 初始化阶段完成耗时
            t_ms = int((time.time() - t0) * 1000)
            stage_logger.info(
                f"✅ 日志系统就绪 ({t_ms}ms)", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 设置初始阶段为startup
            logging_hub.set_stage("startup")

            return logging_hub

        except Exception as e:
            # 降级处理
            print(f"[日志系统] ❌ LoggingHub初始化失败: {e}")
            import traceback

            traceback.print_exc()

            # 添加简单的StreamHandler作为降级
            root_logger = logging.getLogger()
            if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
                fallback = logging.StreamHandler(sys.stdout)
                fallback.setLevel(logging.INFO)
                root_logger.addHandler(fallback)

            # 刷新MemoryHandler到降级handler
            memory_handler.setTarget(fallback)
            memory_handler.flush()

            return None

    def _cleanup_all_logger_handlers(self) -> int:
        """清理所有logger的handlers，确保所有日志都经过LoggingHub

        这个函数会：
        1. 移除所有logger的StreamHandler（避免绕过LoggingHub直接输出）
        2. 设置所有logger的propagate=True（让日志传播到root logger）

        Returns:
            int: 清理的handler数量
        """
        # 尝试获取 LoggingHub 类型，用于避免误删
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import LoggingHub as _LoggingHub
        except Exception:
            _LoggingHub = None

        # 获取所有已创建的logger
        # 使用getattr避免linter错误，loggerDict是标准的logging API
        logger_dict = getattr(logging.root.manager, "loggerDict", {})
        all_loggers = [logging.getLogger(name) for name in logger_dict]
        # 包含root logger在清理范围内
        all_loggers.append(logging.root)

        cleaned_count = 0

        for lgr in all_loggers:
            # 移除所有StreamHandler（这些会直接输出到stdout，绕过LoggingHub）
            handlers_to_remove = []
            for handler in lgr.handlers[:]:
                if isinstance(handler, logging.StreamHandler):
                    # 保留LoggingHub（不是StreamHandler的子类），移除其他StreamHandler
                    if _LoggingHub is not None and isinstance(handler, _LoggingHub):
                        continue
                    handlers_to_remove.append(handler)

            for handler in handlers_to_remove:
                lgr.removeHandler(handler)
                handler.close()
                cleaned_count += 1

            # 设置propagate=True，让日志传播到root logger
            if not lgr.propagate:
                lgr.propagate = True

        return cleaned_count

