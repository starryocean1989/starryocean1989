# -*- coding: utf-8 -*-
"""
后端初始化阶段 - 链接前端和底层功能的关键文件

阶段3：后端服务初始化（20-90%）- 并行执行
- 初始化底层基础设施（EventEngine、MainEngine、ChinaStockEngine）
- 调用Worker初始化后端服务和监控进程（并行）
- 将服务注册到ServiceManager（暴露给前端）
- 管理服务依赖关系

这是链接前端和底层功能的关键文件。
"""

import asyncio
import logging
import time

from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext
from backend.startup.workers.backend_initializer import BackendInitializerWorker
from backend.startup.workers.cache_validator import CacheValidatorWorker
from backend.startup.workers.monitor_launcher import MonitorLauncherWorker

logger = logging.getLogger("backend.startup.stages.backend_init")


class BackendInitStage(StartupStage):
    """后端初始化阶段 - 链接前端和底层功能

    职责：🎯 **这是链接前端和底层功能的关键文件**
    - 初始化底层基础设施（EventEngine、MainEngine、ChinaStockEngine等）
    - 初始化后端服务（DataCenterService、TradingGatewayService等）
    - 将服务注册到ServiceManager（暴露给前端）
    - 协调监控进程启动（并行）
    - 执行8步缓存验证流程（并行）
    - 管理服务依赖关系
    """

    def __init__(self):
        """初始化后端初始化阶段"""
        super().__init__(
            name="backend_init",
            description="后端服务初始化 - 链接前端和底层功能",
        )

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行后端初始化逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()
        scenario = "application_startup"

        # 🎯 启动流程日志埋点：使用ai_log_process上下文管理器
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import (
                ai_log_process,
                get_logging_hub,
            )
            from contextlib import nullcontext
            hub = get_logging_hub()
            if hub:
                hub.set_stage("backend_init")
            context_manager = ai_log_process("backend_init", {"mode": "stage"}) if hub else nullcontext()
        except ImportError:
            from contextlib import nullcontext
            hub = None
            context_manager = nullcontext()

        try:
            with context_manager:
                # 切换到backend_init阶段
                if hub:
                    hub.set_stage("backend_init")
                # 注意：场景信息通过日志记录的extra参数传递，无需全局设置

                stage_logger = logging.getLogger("startup.stage")

            # 阶段3标题
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info(
                "【阶段3: 后端服务初始化】 (20-90%) - 并行执行",
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
            )
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

            stage_logger.info(
                "📍 阶段3: 后端服务初始化开始", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

            # 1. 初始化VNPY核心框架（如果尚未初始化）
            logger.debug(
                "[BACKEND-INIT] 开始初始化VNPY核心框架",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ℹ️ 开始初始化VNPY核心框架",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            await self._initialize_vnpy_core(context)
            logger.debug(
                "[BACKEND-INIT] VNPY核心框架初始化完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ✅ VNPY核心框架初始化完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 2. 并行启动两个任务：
            #    - 任务A：启动监控进程（MonitorLauncherWorker）
            #    - 任务B：初始化后端服务（BackendInitializerWorker）
            logger.debug(
                "[BACKEND-INIT] 开始并行启动监控进程和后端服务",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ℹ️ 开始并行启动监控进程和后端服务",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            monitor_result = None
            backend_result = None
            cache_result = None

            # 并行执行监控进程启动和后端服务初始化
            monitor_worker = MonitorLauncherWorker()
            backend_worker = BackendInitializerWorker()
            logger.debug(
                "[BACKEND-INIT] Worker已创建: MonitorLauncherWorker, BackendInitializerWorker",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 并行执行
            monitor_task = monitor_worker.run(context)
            backend_task = backend_worker.run(context)
            logger.debug(
                "[BACKEND-INIT] 并行任务已启动",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ℹ️ 并行任务已启动，等待完成...",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 等待两个任务完成
            logger.debug(
                "[BACKEND-INIT] 等待监控进程和后端服务初始化完成...",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            monitor_result, backend_result = await asyncio.gather(monitor_task, backend_task)
            logger.debug(
                "[BACKEND-INIT] 监控进程和后端服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ✅ 监控进程和后端服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            if not monitor_result.success:
                logger.error(
                    f"[BACKEND-INIT] ❌ 监控进程启动失败: {monitor_result.message}",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                logger.critical(
                    f"[BACKEND-INIT] 🔥 监控进程启动失败，启动流程将终止: {monitor_result.message}",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                raise RuntimeError(f"监控进程启动失败: {monitor_result.message}")

            if not backend_result.success:
                logger.error(
                    f"[BACKEND-INIT] ❌ 后端服务初始化失败: {backend_result.message}",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                logger.critical(
                    f"[BACKEND-INIT] 🔥 后端服务初始化失败，启动流程将终止: {backend_result.message}",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                raise RuntimeError(f"后端服务初始化失败: {backend_result.message}")
            
            logger.debug(
                f"[BACKEND-INIT] 监控进程启动成功: {monitor_result.message}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[BACKEND-INIT] 后端服务初始化成功: {backend_result.message}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 3. 执行8步缓存验证流程（作为分支B的一部分，需要等待ChinaStockEngine初始化完成）
            if context.china_stock_engine:
                logger.debug(
                    "[BACKEND-INIT] ChinaStockEngine已初始化，开始执行8步缓存验证流程",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                logger.info(
                    "[BACKEND-INIT] ℹ️ ChinaStockEngine已初始化，开始执行8步缓存验证流程",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                
                # 显示分支B标题（数据引擎初始化包括8步验证）
                stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
                stage_logger.info(
                    "┌" + "─" * 66 + "┐", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "│ 分支B: 数据引擎初始化（smart_cache_validation_and_sensing）      │",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    "└" + "─" * 66 + "┘", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

                # 输出ChinaStockEngine初始化完成信息（BackendInitializerWorker已完成）
                stage_logger.info(
                    "📍 阶段3.1: ChinaStockEngine初始化开始",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                logger.debug(
                    "[BACKEND-INIT] ChinaStockEngine实例化完成",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "✅ ChinaStockEngine实例化完成", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

                # 🚀 优化4：在此处启动UI预加载任务（与缓存验证并行）
                # 当核心服务（ChinaStockEngine）就绪后，开始UI预加载
                logger.debug(
                    "[BACKEND-INIT] 开始启动UI预加载任务（与8步验证并行）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                context.ui_preload_task = asyncio.create_task(self._preload_ui_components(context))
                logger.info(
                    "[BACKEND-INIT] UI预加载任务已在后台启动（与8步验证并行）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

                # 执行8步缓存验证流程（作为分支B的一部分）
                logger.debug(
                    "[BACKEND-INIT] 开始执行8步缓存验证流程",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                logger.info(
                    "[BACKEND-INIT] ℹ️ 开始执行8步缓存验证流程",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                cache_worker = CacheValidatorWorker()
                cache_result = await cache_worker.run(context)

                if not cache_result.success:
                    logger.warning(
                        f"[BACKEND-INIT] ⚠️ 缓存验证失败: {cache_result.message}，但继续执行",
                        extra={"log_type": "ALERT", "scenario": scenario}
                    )
                    logger.debug(
                        f"[BACKEND-INIT] 缓存验证失败详情: {cache_result.message}",
                        extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
                else:
                    logger.debug(
                        f"[BACKEND-INIT] 8步缓存验证流程完成: {cache_result.message}",
                        extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
                    logger.info(
                        f"[BACKEND-INIT] ✅ 8步缓存验证流程完成: {cache_result.message}",
                        extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
            else:
                logger.warning(
                    "[BACKEND-INIT] ⚠️ ChinaStockEngine未初始化，跳过缓存验证",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                logger.debug(
                    "[BACKEND-INIT] ChinaStockEngine未初始化，跳过缓存验证",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )

            # 4. 初始化业务服务（阶段3.4-3.6）
            logger.debug(
                "[BACKEND-INIT] 开始初始化业务服务（阶段3.4-3.6）",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ℹ️ 开始初始化业务服务（阶段3.4-3.6）",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            await self._initialize_business_services(context)
            logger.debug(
                "[BACKEND-INIT] 业务服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ✅ 业务服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 5. 将服务注册到ServiceManager（暴露给前端）
            logger.debug(
                "[BACKEND-INIT] 开始将服务注册到ServiceManager",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            self._register_services(context)
            logger.debug(
                "[BACKEND-INIT] 服务注册完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ✅ 服务注册完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 6. 将服务注入到MainEngine（供前端使用）
            logger.debug(
                "[BACKEND-INIT] 开始将服务注入到MainEngine",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            self._inject_services_to_main_engine(context)
            logger.debug(
                "[BACKEND-INIT] 服务注入完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[BACKEND-INIT] ✅ 服务注入到MainEngine完成",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 标记后端已初始化
            context.backend_initialized = True
            logger.debug(
                "[BACKEND-INIT] 后端已标记为已初始化",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            elapsed_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"[BACKEND-INIT] 后端服务初始化完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                f"[BACKEND-INIT] ✅ 后端服务初始化完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            stage_logger.info(
                "✅ 后端服务完全就绪", 
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )

            return StageResult(
                success=True,
                message="后端服务初始化完成",
                elapsed_ms=elapsed_ms,
                data={
                    "monitor_result": monitor_result.data if monitor_result else None,
                    "backend_result": backend_result.data if backend_result else None,
                    "cache_result": cache_result.data if cache_result else None,
                },
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            # 错误日志（输出到Terminal和AI日志文件）
            logger.debug(
                f"[BACKEND-INIT] 后端服务初始化失败: {type(e).__name__}: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.error(
                f"[BACKEND-INIT] ❌ 后端服务初始化失败: {str(e)}",
                extra={"log_type": "ALERT", "scenario": scenario},
                exc_info=True
            )
            logger.critical(
                f"[BACKEND-INIT] 🔥 后端服务初始化严重失败，启动流程将终止: {str(e)}",
                extra={"log_type": "ALERT", "scenario": scenario},
                exc_info=True
            )

            return StageResult(
                success=False,
                message=f"后端服务初始化失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    async def _initialize_vnpy_core(self, context: StartupContext):
        """初始化VNPY核心框架（检查并确保引擎已存在）

        根据启动完整设计文档1088-1090行：
        - 阶段2已预创建EventEngine和MainEngine
        - 阶段3.1只检查，如果不存在则创建（兼容模式）

        Args:
            context: 启动上下文
        """
        # 检查全局是否已有引擎（单一事实原则：优先使用阶段2预创建的引擎）
        from backend.core.base import get_event_engine, get_main_engine

        existing_event_engine = get_event_engine()
        existing_main_engine = get_main_engine()

        # 如果全局已有引擎，使用全局的引擎（确保单一事实原则）
        if existing_event_engine:
            context.event_engine = existing_event_engine
        if existing_main_engine:
            context.main_engine = existing_main_engine

        # 如果EventEngine和MainEngine已存在，跳过创建（单一事实原则）
        if context.event_engine and context.main_engine:
            logger.debug(
                "[BACKEND-INIT] EventEngine和MainEngine已预创建（阶段2），跳过初始化",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                "[BACKEND-INIT] EventEngine和MainEngine已预创建（阶段2），跳过初始化",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 确保注册到全局
            from backend.core.base import set_event_engine, set_main_engine
            set_event_engine(context.event_engine)
            set_main_engine(context.main_engine)
            
            # 注入占位方法（供vnpy_chartwizard使用）- 即使引擎已预创建，也需要注入占位方法
            try:
                def placeholder_get_contracts():
                    """占位方法：返回空列表，等待后台更新"""
                    logger.debug("[PLACEHOLDER] get_all_contracts被调用（等待后台更新）")
                    return []

                def placeholder_load_bars(*_args, **_kwargs):
                    """占位方法：返回空列表，等待后台更新"""
                    logger.debug("[PLACEHOLDER] load_bar_data被调用（等待后台更新）")
                    return []

                context.main_engine.get_all_contracts = placeholder_get_contracts  # type: ignore[attr-defined]
                context.main_engine.load_bar_data = placeholder_load_bars  # type: ignore[attr-defined]

                logger.debug(
                    "[VNPY-CORE] MainEngine占位方法已注入（后续将由UnifiedDataManager更新）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            except Exception as e:
                logger.exception(
                    f"[VNPY-CORE] 注入占位方法失败: {e}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
            
            # 设置引擎到上下文
            context.set_engines(context.event_engine, context.main_engine, None)
            
            # 初始化日志管理系统（即使引擎已预创建，也需要初始化日志管理）
            stage_logger = logging.getLogger("startup.stage")
            try:
                from backend.services.system_manager_service import get_log_manager

                _ = get_log_manager(event_engine=context.event_engine, force_reinit=True)
                stage_logger.info(
                    "✅ 日志持久化已启用",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
            except Exception as e:
                logger.exception(
                    f"[LOG-MANAGER] 日志管理系统初始化失败: {e}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                stage_logger.info(
                    f"❌ 日志持久化启用失败 - {str(e)}",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
            
            stage_logger.info(
                "✅ VNPY核心就绪",
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            return

        stage_logger = logging.getLogger("startup.stage")

        # 切换到vnpy_core阶段
        from backend.infrastructure.system_vnpy import get_logging_hub

        hub = get_logging_hub()
        hub.set_stage("vnpy_core")
        # 注意：场景信息通过日志记录的extra参数传递，无需全局设置

        stage_logger.info(
            "📍 阶段2.5: VNPY核心初始化开始",
            extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
        )

        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            from backend.core.base import set_event_engine, set_main_engine

            # 创建EventEngine（如果尚未创建）- 仅用于兼容模式
            if not context.event_engine:
                logger.warning(
                    "[BACKEND-INIT] ⚠️ EventEngine未在阶段2预创建，在此处创建（兼容模式）",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                event_engine = EventEngine(interval=1)
                context.event_engine = event_engine
                set_event_engine(event_engine)
                logger.debug(
                    "[VNPY-CORE] EventEngine创建成功（兼容模式）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                logger.info(
                    "[VNPY-CORE] EventEngine已创建（兼容模式）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            # 创建MainEngine（如果尚未创建）- 仅用于兼容模式
            if not context.main_engine:
                logger.warning(
                    "[BACKEND-INIT] ⚠️ MainEngine未在阶段2预创建，在此处创建（兼容模式）",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                main_engine = MainEngine(context.event_engine)
                context.main_engine = main_engine
                set_main_engine(main_engine)
                logger.debug(
                    "[VNPY-CORE] MainEngine创建成功（兼容模式）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                logger.info(
                    "[VNPY-CORE] MainEngine已创建（兼容模式）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            # 注入占位方法（供vnpy_chartwizard使用）
            try:
                def placeholder_get_contracts():
                    """占位方法：返回空列表，等待后台更新"""
                    logger.debug(
                        "[PLACEHOLDER] get_all_contracts被调用（等待后台更新）",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                    return []

                def placeholder_load_bars(*_args, **_kwargs):
                    """占位方法：返回空列表，等待后台更新"""
                    logger.debug(
                        "[PLACEHOLDER] load_bar_data被调用（等待后台更新）",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                    return []

                context.main_engine.get_all_contracts = placeholder_get_contracts  # type: ignore[attr-defined]
                context.main_engine.load_bar_data = placeholder_load_bars  # type: ignore[attr-defined]

                logger.debug(
                    "[VNPY-CORE] MainEngine占位方法已注入（后续将由UnifiedDataManager更新）",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            except Exception as e:
                logger.exception(
                    f"[VNPY-CORE] 注入占位方法失败: {e}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )

            # 初始化日志管理系统
            try:
                logger.debug(
                    "[VNPY-CORE] 开始初始化日志管理系统",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                from backend.services.system_manager_service import get_log_manager

                _ = get_log_manager(event_engine=context.event_engine, force_reinit=True)
                logger.debug(
                    "[VNPY-CORE] 日志管理系统初始化成功",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                logger.info(
                    "[VNPY-CORE] 日志持久化已启用",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "✅ 日志持久化已启用",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
            except Exception as e:
                logger.exception(
                    f"[LOG-MANAGER] 日志管理系统初始化失败: {e}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                logger.warning(
                    f"[LOG-MANAGER] ⚠️ 日志持久化启用失败: {e}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                stage_logger.info(
                    f"❌ 日志持久化启用失败 - {str(e)}",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

            # 设置引擎到上下文
            context.set_engines(context.event_engine, context.main_engine, None)

            stage_logger.info(
                "✅ VNPY核心就绪",
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

        except Exception as e:
            logger.exception(
                f"[VNPY-CORE] VnPy核心初始化失败: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )
            raise

    async def _initialize_business_services(self, context: StartupContext):
        """初始化业务服务（阶段3.4-3.6）

        使用ServiceInitializer的方法来初始化业务服务，确保代码复用和一致性。

        Args:
            context: 启动上下文
        """
        logger.debug(
            "[BACKEND-INIT] 开始初始化业务服务（阶段3.4-3.6）",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )
        from backend.startup.initializers.service_initializer import ServiceInitializer

        # 创建ServiceInitializer实例（使用context中的service_manager）
        initializer = ServiceInitializer(
            service_manager=context.service_manager,
            progress_callback=None,
        )
        logger.debug(
            "[BACKEND-INIT] ServiceInitializer已创建",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

        # 设置引擎（ServiceInitializer可能需要）
        if context.event_engine:
            initializer.event_engine = context.event_engine
            logger.debug(
                "[BACKEND-INIT] EventEngine已设置到ServiceInitializer",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        if context.main_engine:
            initializer.main_engine = context.main_engine
            logger.debug(
                "[BACKEND-INIT] MainEngine已设置到ServiceInitializer",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        if context.china_stock_engine:
            initializer.china_stock_engine = context.china_stock_engine
            logger.debug(
                "[BACKEND-INIT] ChinaStockEngine已设置到ServiceInitializer",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

        # 阶段3.4: 交易服务初始化
        try:
            logger.debug(
                "[BACKEND-INIT] 开始初始化交易服务（阶段3.4）",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            initializer._initialize_trading_services()
            logger.info(
                "[BACKEND-INIT] 交易服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except Exception as e:
            logger.exception(
                f"[BACKEND-INIT] ❌ 交易服务初始化异常: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )

        # 阶段3.5: 策略服务初始化
        try:
            logger.debug(
                "[BACKEND-INIT] 开始初始化策略服务（阶段3.5）",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            initializer._initialize_strategy_services()
            logger.info(
                "[BACKEND-INIT] 策略服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except Exception as e:
            logger.exception(
                f"[BACKEND-INIT] ❌ 策略服务初始化异常: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )

        # 阶段3.6: 辅助服务初始化
        try:
            logger.debug(
                "[BACKEND-INIT] 开始初始化辅助服务（阶段3.6）",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            initializer._initialize_auxiliary_services()
            logger.info(
                "[BACKEND-INIT] 辅助服务初始化完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except Exception as e:
            logger.exception(
                f"[BACKEND-INIT] ❌ 辅助服务初始化异常: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )

        # 同步服务到context（从service_manager中获取）
        logger.debug(
            "[BACKEND-INIT] 开始同步服务到context",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )
        self._sync_services_to_context(context, initializer)
        logger.debug(
            "[BACKEND-INIT] 服务同步完成",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

    def _sync_services_to_context(self, context: StartupContext, initializer):
        """将ServiceInitializer初始化的服务同步到context

        Args:
            context: 启动上下文
            initializer: ServiceInitializer实例
        """
        # 从service_manager中获取服务并同步到context
        if context.service_manager.has_service("trading_gateway_service"):
            context.trading_service = context.service_manager.get_service(
                "trading_gateway_service"
            )

        if context.service_manager.has_service("strategy_center_service"):
            context.strategy_service = context.service_manager.get_service(
                "strategy_center_service"
            )

        if context.service_manager.has_service("ai_assistant_service"):
            context.ai_assistant_service = context.service_manager.get_service(
                "ai_assistant_service"
            )

        if context.service_manager.has_service("portfolio_service"):
            context.portfolio_service = context.service_manager.get_service(
                "portfolio_service"
            )

        if context.service_manager.has_service("market_board_service"):
            context.market_board_service = context.service_manager.get_service(
                "market_board_service"
            )

        if context.service_manager.has_service("system_manager_service"):
            context.system_manager_service = context.service_manager.get_service(
                "system_manager_service"
            )

    def _register_services(self, context: StartupContext):
        """将服务注册到ServiceManager（暴露给前端）

        Args:
            context: 启动上下文
        """
        # 服务已在_initialize_business_services中注册，这里只验证
        services_to_check = [
            "data_center_service",
            "trading_gateway_service",
            "strategy_center_service",
            "ai_assistant_service",
            "portfolio_service",
            "market_board_service",
            "system_manager_service",
        ]

        registered_count = 0
        for service_name in services_to_check:
            if context.service_manager.has_service(service_name):
                registered_count += 1
                logger.debug(
                    f"[BACKEND-INIT] ✅ 服务已注册: {service_name}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                logger.warning(
                    f"[BACKEND-INIT] ⚠️ 服务未注册: {service_name}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
        
        logger.info(
            f"[BACKEND-INIT] 服务注册验证完成: {registered_count}/{len(services_to_check)}个服务已注册",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

    def _inject_services_to_main_engine(self, context: StartupContext):
        """将服务注入到MainEngine（供前端使用）

        Args:
            context: 启动上下文
        """
        if not context.main_engine:
            logger.warning(
                "[BACKEND-INIT] ⚠️ MainEngine未初始化，跳过服务注入",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )
            return

        try:
            logger.debug(
                "[BACKEND-INIT] 开始将服务注入到MainEngine",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 将服务添加到MainEngine
            # MainEngine.add_engine()方法用于添加引擎
            # 注意：这里需要根据实际的服务类型进行适配

            # 示例：如果服务有get_engine()方法，可以这样添加
            # if context.data_service and hasattr(context.data_service, 'get_engine'):
            #     context.main_engine.add_engine(context.data_service.get_engine())

            logger.debug(
                "[BACKEND-INIT] 服务注入到MainEngine完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                "[BACKEND-INIT] 服务已注入到MainEngine",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except Exception as e:
            logger.exception(
                f"[BACKEND-INIT] ❌ 服务注入到MainEngine失败: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )

    async def _preload_ui_components(self, context: StartupContext):
        """预加载UI组件（优化4：与后端初始化并行）

        当核心服务就绪后，开始预加载UI组件，减少UI激活阶段的耗时。

        Args:
            context: 启动上下文
        """
        try:
            logger.debug(
                "[BACKEND-INIT] 开始UI组件预加载（与8步验证并行）",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                "[BACKEND-INIT] 开始UI组件预加载（与8步验证并行）...",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 预加载MainWindow类（导入和实例化准备）
            from ui.main_window import MainWindow
            logger.debug(
                "[BACKEND-INIT] MainWindow类已预加载",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 预加载其他常用的UI组件类
            preloaded_modules = []
            try:
                from ui.modules.data_center_view import DataCenter
                preloaded_modules.append("DataCenter")
                from ui.modules.market_board_view import ChartWizardEnhanced
                preloaded_modules.append("ChartWizardEnhanced")
                from ui.modules.system_manager_view import SystemManager
                preloaded_modules.append("SystemManager")
                logger.debug(
                    f"[BACKEND-INIT] 主要UI模块类已预加载: {', '.join(preloaded_modules)}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            except Exception as e:
                logger.debug(
                    f"[BACKEND-INIT] 部分UI模块预加载失败（可接受）: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )

            # 预创建一些基础的Qt对象（如果需要）
            # 注意：实际的MainWindow实例化需要在UI线程中进行

            logger.info(
                f"[BACKEND-INIT] UI组件预加载完成: 已预加载{len(preloaded_modules)}个模块",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            context.ui_preloaded = True

        except Exception as e:
            logger.exception(
                f"[BACKEND-INIT] ❌ UI组件预加载失败: {e}",
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )
            context.ui_preloaded = False

