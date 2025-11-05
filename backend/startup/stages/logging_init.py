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
from backend.infrastructure.system_vnpy.unified_log_system import PersistentBufferHandler, MultiProcessLogCollector


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
        self.persistent_buffer: Optional[PersistentBufferHandler] = None
        self.multiprocess_collector: Optional[MultiProcessLogCollector] = None

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行日志系统初始化逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()
        logger = logging.getLogger("backend.startup.stages.logging_init")

        try:
            # DEBUG日志（记录初始化开始）
            logger.debug(
                "[LOG-INIT] 日志系统初始化开始",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 1. 获取环境准备阶段设置的MemoryHandler（如果存在）
            # 否则创建新的MemoryHandler
            memory_handler = getattr(context, '_memory_handler', None)
            if memory_handler is None:
                logger.debug(
                    "[LOG-INIT] MemoryHandler不存在，创建新的MemoryHandler",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                memory_handler, persistent_buffer = self._setup_memory_logging()
                self.persistent_buffer = persistent_buffer
            else:
                buffered_count = len(memory_handler.buffer) if hasattr(memory_handler, 'buffer') else 0
                logger.debug(
                    f"[LOG-INIT] 使用环境准备阶段的MemoryHandler，已缓冲{buffered_count}条日志",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                # 获取持久化缓冲Handler（如果存在）
                self.persistent_buffer = getattr(context, '_persistent_buffer', None)
            self.memory_handler = memory_handler

            # 2. 初始化LoggingHub并重放缓冲日志
            logger.debug(
                "[LOG-INIT] 开始初始化LoggingHub",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logging_hub = await self._initialize_logging_hub(memory_handler, context)

            if not logging_hub:
                # 降级处理失败
                logger.error(
                    "[LOG-INIT] ❌ LoggingHub初始化失败，使用降级日志输出",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                return StageResult(
                    success=False,
                    message="LoggingHub初始化失败，使用降级日志输出",
                    elapsed_ms=(time.time() - start_time) * 1000,
                )

            # 3. 标记日志系统已初始化
            context.logging_hub_initialized = True
            logger.debug(
                "[LOG-INIT] 日志系统已标记为已初始化",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"[LOG-INIT] 日志系统初始化完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return StageResult(
                success=True,
                message="日志系统初始化完成",
                elapsed_ms=elapsed_ms,
                data={"logging_hub": logging_hub, "memory_handler": memory_handler},
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            logger.error(
                f"[LOG-INIT] ❌ 日志系统初始化失败: {str(e)}",
                extra={"log_type": "ALERT", "scenario": "application_startup"},
                exc_info=True
            )

            return StageResult(
                success=False,
                message=f"日志系统初始化失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    def _setup_memory_logging(self) -> tuple[MemoryHandler, PersistentBufferHandler]:
        """设置MemoryHandler和PersistentBufferHandler缓冲日志系统初始化前的日志

        Returns:
            tuple[MemoryHandler, PersistentBufferHandler]: MemoryHandler和PersistentBufferHandler实例
        """
        logger = logging.getLogger("backend.startup.stages.logging_init")
        
        # DEBUG日志
        logger.debug(
            "[LOG-INIT] 开始设置MemoryHandler",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )
        
        # 修复编码问题：确保stdout/stderr使用UTF-8编码
        stdout_reconfigured = False
        stderr_reconfigured = False
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
                stdout_reconfigured = True
                logger.debug(
                    "[LOG-INIT] stdout已重新配置为UTF-8编码",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            except (OSError, ValueError) as e:
                logger.debug(
                    f"[LOG-INIT] stdout重新配置失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8")  # type: ignore
                stderr_reconfigured = True
                logger.debug(
                    "[LOG-INIT] stderr已重新配置为UTF-8编码",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            except (OSError, ValueError) as e:
                logger.debug(
                    f"[LOG-INIT] stderr重新配置失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

        # 配置root logger
        root_logger = logging.getLogger()
        old_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)  # 接收所有级别的日志
        logger.debug(
            f"[LOG-INIT] root logger级别已设置: {logging.getLevelName(old_level)} -> DEBUG",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        # 创建MemoryHandler作为临时缓冲（容量10000条）
        # target先设为None，LoggingHub初始化后再设置
        memory_handler = MemoryHandler(capacity=10000, target=None)
        memory_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(memory_handler)
        logger.debug(
            f"[LOG-INIT] MemoryHandler已创建: 容量={memory_handler.capacity}条",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        # 🔧 优化：创建持久化缓冲Handler（防止进程崩溃导致日志丢失）
        persistent_buffer = PersistentBufferHandler(buffer_dir="logs/buffer", capacity=10000)
        persistent_buffer.setLevel(logging.DEBUG)
        root_logger.addHandler(persistent_buffer)
        logger.debug(
            "[LOG-INIT] PersistentBufferHandler已创建",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        # 创建启动logger
        from backend.core.base import setup_logging as base_setup_logging

        startup_logger = base_setup_logging(name="StartupOptimized", level="INFO")
        logger.debug(
            "[LOG-INIT] 启动logger已创建",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        # 关键修复：移除logger自己的handlers，避免绕过LoggingHub
        # base_setup_logging会给logger添加StreamHandler，导致日志直接输出到stdout
        # 我们需要所有日志都通过LoggingHub统一路由
        removed_handlers_count = 0
        for handler in startup_logger.handlers[:]:
            startup_logger.removeHandler(handler)
            handler.close()
            removed_handlers_count += 1
        logger.debug(
            f"[LOG-INIT] 已移除启动logger的{removed_handlers_count}个handlers",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        # 设置propagate=True，让日志传播到root logger，经过LoggingHub处理
        startup_logger.propagate = True
        logger.debug(
            "[LOG-INIT] 启动logger已设置为传播到root logger",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        return memory_handler, persistent_buffer

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
        logger = logging.getLogger("backend.startup.stages.logging_init")
        
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
            logger.debug(
                "[LOG-INIT] 开始获取LoggingHub实例",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logging_hub = get_logging_hub()
            logger.debug(
                "[LOG-INIT] LoggingHub实例已获取",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 2. 创建并注入handlers
            logger.debug(
                "[LOG-INIT] 开始创建并注入handlers",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)  # LoggingHub内部会根据规则过滤
            # 终端仅显示消息内容
            console_formatter = logging.Formatter("%(message)s")
            console_handler.setFormatter(console_formatter)
            logging_hub.set_console_handler(console_handler)
            logger.debug(
                "[LOG-INIT] ConsoleHandler已创建并注入",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 创建常规文件Handler（logs/terminal.log）
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            terminal_log_file = log_dir / "terminal.log"
            file_handler = logging.FileHandler(terminal_log_file, mode="a", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # 接收所有级别
            # 文件保留完整格式
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            logging_hub.set_file_handler(file_handler)
            logger.debug(
                f"[LOG-INIT] FileHandler已创建并注入: {terminal_log_file.absolute()}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 3. 🔧 关键修复：先获取AI日志Handler并注入到LoggingHub，再启动AI流程
            # 这样可以确保后续所有日志都能正确写入AI日志文件
            logger.debug(
                "[LOG-INIT] 开始获取AI日志Handler",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            ai_handler = get_ai_log_handler()
            logging_hub.set_ai_log_handler(ai_handler)
            logger.debug(
                "[LOG-INIT] AILogHandler已获取并注入",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 4. 🔧 关键修复：在LoggingHub添加到root logger之前启动AI流程
            # 这样可以确保start_ai_process内部的日志也能写入AI日志文件
            logger.debug(
                "[LOG-INIT] 开始启动AI流程",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            ai_log_file = start_ai_process(
                "application_startup",
                metadata={
                    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    "platform": sys.platform,
                },
            )
            logger.debug(
                f"[LOG-INIT] AI流程已启动: {ai_log_file}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 验证AI日志文件是否创建成功
            if not ai_log_file or not ai_log_file.exists():
                logger.warning(
                    f"[LOG-INIT] ⚠️ AI日志文件创建失败: {ai_log_file}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                logger.debug(
                    f"[LOG-INIT] AI日志文件已创建: {ai_log_file.absolute()}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            # 注意：场景信息通过日志记录的extra参数传递，无需全局设置

            # 5. 集成多进程日志收集器
            logger.debug(
                "[LOG-INIT] 开始创建多进程日志收集器",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            multiprocess_collector = MultiProcessLogCollector(logging_hub)
            multiprocess_collector.start()
            self.multiprocess_collector = multiprocess_collector
            logger.debug(
                "[LOG-INIT] 多进程日志收集器已启动",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 6. 集成有序日志队列（启动阶段）
            from backend.startup.startup_logging.startup_logger import OrderedLogQueue

            logger.debug(
                "[LOG-INIT] 开始创建有序日志队列",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            ordered_queue = OrderedLogQueue(max_wait_seconds=30)
            logging_hub.set_ordered_log_queue(ordered_queue)
            logging_hub.enable_ordered_queue(scenario="startup")
            logger.debug(
                f"[LOG-INIT] 有序日志队列已创建并启用: 最大等待时间={ordered_queue.max_wait_seconds}秒",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            stage_logger.info(
                "✅ 有序日志队列初始化完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 7. 将LoggingHub添加到root logger
            root_logger.addHandler(logging_hub)
            logger.debug(
                "[LOG-INIT] LoggingHub已添加到root logger",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 8. 设置MemoryHandler的target为LoggingHub
            memory_handler.setTarget(logging_hub)
            logger.debug(
                "[LOG-INIT] MemoryHandler的target已设置为LoggingHub",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 9. 直接刷新MemoryHandler（重放启动前的日志到AI日志文件）
            # LoggingHub会自动通过emit方法处理所有日志
            buffered_count = len(memory_handler.buffer)
            logger.debug(
                f"[LOG-INIT] 开始刷新MemoryHandler: 已缓冲{buffered_count}条日志",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            memory_handler.flush()
            logger.debug(
                f"[LOG-INIT] MemoryHandler已刷新: {buffered_count}条日志已重放",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

                          # 9. 移除MemoryHandler（已完成使命）
            root_logger.removeHandler(memory_handler)
            memory_handler.close()
            logger.debug(
                "[LOG-INIT] MemoryHandler已移除并关闭",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 9. 全局清理：移除所有logger的StreamHandler，确保所有日志都经过LoggingHub
            logger.debug(
                "[LOG-INIT] 开始全局清理logger handlers",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            cleaned_count = self._cleanup_all_logger_handlers()
            logger.debug(
                f"[LOG-INIT] 全局清理完成: 已清理{cleaned_count}个handlers",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 10. 阶段1标题与分隔（此时LoggingHub已就绪）
            # 注意：阶段0的输出已经在env_setup阶段通过print直接输出，无需在这里补输出
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("【阶段1: 日志系统初始化】 (5-10%)", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

            # 添加阶段1开始标记
            stage_logger.info("📍 阶段1: 日志系统初始化开始", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

            # 使用logger输出（此时已经过LoggingHub）
            # 阶段输出（使用STAGE_NODE以显示在Terminal）
            stage_logger.info(
                "✅ LoggingHub创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 路由规则统计
            try:
                re = logging_hub._routing_engine
                stage_logger.info(
                    "✅ 路由规则引擎初始化完成", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                global_rules_count = len(getattr(re, 'global_rules', {}))
                stage_rules_count = len(getattr(re, 'stage_rules', {}))
                module_rules_count = len(getattr(re, 'module_rules', {}))
                scenario_rules_count = len(getattr(re, 'scenario_rules', {}))
                
                logger.debug(
                    f"[LOG-INIT] 路由规则统计: 全局={global_rules_count}, 阶段={stage_rules_count}, "
                    f"模块={module_rules_count}, 场景={scenario_rules_count}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                
                stage_logger.info(
                    f"   - 全局规则: {global_rules_count} 个LogType",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"   - 阶段规则: {stage_rules_count} 个阶段",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"   - 模块规则: {module_rules_count} 个模块",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"   - 场景规则: {scenario_rules_count} 个场景",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
            except Exception as e:
                logger.warning(
                    f"[LOG-INIT] 路由规则统计失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            # AI日志Handler信息
            stage_logger.info(
                "✅ AI日志Handler初始化完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                f"  - 基础目录: {Path('logs/ai').absolute()}", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # MemoryHandler日志重放信息
            stage_logger.info(
                f"✅ MemoryHandler日志重放完成 ({buffered_count}条)", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 有序日志队列信息（如果已启用）
            if ordered_queue:
                stage_logger.info(
                    "✅ 有序日志队列已启用（启动阶段日志将按顺序输出）",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )

            # 初始化阶段完成耗时
            t_ms = int((time.time() - t0) * 1000)
            logger.info(
                f"[LOG-INIT] 日志系统初始化完成: 总耗时={t_ms}ms",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            stage_logger.info(
                f"✅ 日志系统就绪 ({t_ms}ms)", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 设置初始阶段为startup
            logging_hub.set_stage("startup")
            logger.debug(
                "[LOG-INIT] 日志系统阶段已设置为startup",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return logging_hub

        except Exception as e:
            logger = logging.getLogger("backend.startup.stages.logging_init")
            
            # 降级处理
            logger.critical(
                f"[LOG-INIT] 🔥 LoggingHub初始化失败，使用降级日志输出: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"},
                exc_info=True
            )
            print(f"[日志系统] ❌ LoggingHub初始化失败: {e}")
            import traceback

            traceback.print_exc()

            # 添加简单的StreamHandler作为降级
            root_logger = logging.getLogger()
            if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
                fallback = logging.StreamHandler(sys.stdout)
                fallback.setLevel(logging.INFO)
                root_logger.addHandler(fallback)
                logger.warning(
                    "[LOG-INIT] ⚠️ 已添加降级StreamHandler",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )

            # 刷新MemoryHandler到降级handler
            memory_handler.setTarget(fallback)
            memory_handler.flush()
            logger.debug(
                "[LOG-INIT] MemoryHandler已刷新到降级handler",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return None

    def _cleanup_all_logger_handlers(self) -> int:
        """清理所有logger的handlers，确保所有日志都经过LoggingHub

        这个函数会：
        1. 移除所有logger的StreamHandler（避免绕过LoggingHub直接输出）
        2. 设置所有logger的propagate=True（让日志传播到root logger）

        Returns:
            int: 清理的handler数量
        """
        logger = logging.getLogger("backend.startup.stages.logging_init")
        
        # 尝试获取 LoggingHub 类型，用于避免误删
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import LoggingHub as _LoggingHub
            logger.debug(
                "[LOG-INIT] LoggingHub类型已获取，用于避免误删",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except Exception as e:
            _LoggingHub = None
            logger.debug(
                f"[LOG-INIT] 无法获取LoggingHub类型: {e}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

        # 获取所有已创建的logger
        # 使用getattr避免linter错误，loggerDict是标准的logging API
        logger_dict = getattr(logging.root.manager, "loggerDict", {})
        all_loggers = [logging.getLogger(name) for name in logger_dict]
        # 包含root logger在清理范围内
        all_loggers.append(logging.root)
        
        logger.debug(
            f"[LOG-INIT] 找到{len(all_loggers)}个logger需要清理",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        cleaned_count = 0
        propagate_set_count = 0

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
                try:
                    handler.close()
                except Exception:
                    pass
                cleaned_count += 1

            # 设置propagate=True，让日志传播到root logger
            if not lgr.propagate:
                lgr.propagate = True
                propagate_set_count += 1

        logger.debug(
            f"[LOG-INIT] 清理完成: 移除{cleaned_count}个handlers, 设置{propagate_set_count}个logger的propagate=True",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        return cleaned_count

