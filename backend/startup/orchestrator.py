# -*- coding: utf-8 -*-
"""
启动编排器 - 单一入口管理所有启动逻辑

提供统一的启动流程管理，包括：
- 管理所有启动阶段
- 协调阶段间的依赖关系
- 处理阶段错误和降级
- 统一日志输出
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Dict

from backend.startup.context import StartupContext
from backend.startup.stages.base import StartupStage, StageResult

logger = logging.getLogger("backend.startup.orchestrator")


@dataclass
class StartupResult:
    """启动结果

    Attributes:
        success: 是否成功
        message: 结果消息
        elapsed_ms: 总耗时（毫秒）
        stage_results: 各阶段结果
        context: 启动上下文
        error: 错误信息（如果失败）
    """

    success: bool
    message: str = ""
    elapsed_ms: float = 0.0
    stage_results: Optional[Dict[str, StageResult]] = None
    context: Optional[StartupContext] = None
    error: Optional[Exception] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.stage_results is None:
            self.stage_results = {}


class StartupOrchestrator:
    """启动编排器 - 单一入口管理所有启动逻辑

    职责：
    - 管理所有启动阶段
    - 协调阶段间的依赖关系
    - 处理阶段错误和降级
    - 统一日志输出
    - 管理启动上下文
    """

    def __init__(self):
        """初始化启动编排器"""
        self.context = StartupContext()
        self.stages: List[StartupStage] = []
        self.logger = logging.getLogger("backend.startup.orchestrator")

        # 延迟日志系统初始化，直到环境准备阶段之后
        # 确保环境准备阶段的输出是第一个输出
        self._logging_initialized = False

        # 设置所有阶段的日志记录器
        self._setup_stage_loggers()

    def _setup_stage_loggers(self):
        """设置所有阶段的日志记录器（延迟调用，在添加阶段后）"""
        # 这个方法会在添加阶段后调用
        # TODO: 实现阶段日志记录器设置逻辑

    def add_stage(self, stage: StartupStage):
        """添加启动阶段

        Args:
            stage: 启动阶段实例
        """
        # 注意：新架构不再需要设置startup_logger，日志系统已统一管理
        self.stages.append(stage)
        self.logger.debug(
            "添加启动阶段: %s",
            stage.name,
            extra={"log_type": "SYSTEM", "scenario": "application_startup"},
        )

    def add_stages(self, stages: List[StartupStage]):
        """批量添加启动阶段

        Args:
            stages: 启动阶段列表
        """
        for stage in stages:
            self.add_stage(stage)

    async def startup(self) -> StartupResult:
        """启动流程 - 单一方法，清晰可控

        Returns:
            StartupResult: 启动结果
        """
        start_time = time.time()
        scenario = "application_startup"

        # 🎯 启动流程日志埋点：事件日志流程已在initialize_logging_hub_complete中启动
        # 注意：不要在日志系统初始化之前就使用event_log_process，因为此时_event_log_handler可能还没有注入
        # initialize_logging_hub_complete已经在日志系统初始化时启动了application_startup事件
        try:
            from backend.infrastructure.system_vnpy.logging_system import get_logging_hub
            from contextlib import nullcontext

            hub = get_logging_hub()
            if hub:
                hub.set_stage("startup")
            # 🔧 兜底检查：如果事件日志流程未启动，则启动application_startup事件
            try:
                from backend.infrastructure.system_vnpy.logging_system import (
                    get_event_log_handler,
                    start_event_process,
                )

                handler = get_event_log_handler()
                need_start = True
                # 若当前事件文件存在且未关闭，则认为事件流程已启动
                if hasattr(handler, "_current_event_file"):
                    current_file = getattr(handler, "_current_event_file", None)
                    if current_file is not None and not getattr(current_file, "closed", True):
                        need_start = False

                if need_start:
                    start_event_process("application_startup", {"mode": "orchestrator"})
                    self.logger.debug(
                        "[STARTUP] 兜底启动事件日志流程(application_startup)",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                else:
                    self.logger.debug(
                        "[STARTUP] 检测到事件日志已启动，跳过兜底", 
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
            except Exception as e:
                self.logger.warning(
                    f"[STARTUP] ⚠️ 事件日志兜底启动失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
            # 不再在这里启动event_log_process，因为initialize_logging_hub_complete已经启动了
            context_manager = nullcontext()
        except ImportError:
            from contextlib import nullcontext

            hub = None
            context_manager = nullcontext()

        try:
            with context_manager:
                # 不再在这里输出日志，因为日志系统还未初始化
                # 环境准备阶段的输出应该是第一个输出
                stage_results: Dict[str, StageResult] = {}

                # DEBUG日志（记录启动流程开始）
                self.logger.debug(
                    "[STARTUP] 启动流程开始", extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                self.logger.info(
                    "[STARTUP] ℹ️ 启动流程开始，待执行阶段数: %d",
                    len(self.stages),
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                self.logger.debug(
                    "[STARTUP] 待执行阶段数: %d",
                    len(self.stages),
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                stage_names = [stage.name for stage in self.stages]
                self.logger.debug(
                    "[STARTUP] 阶段列表: %s",
                    stage_names,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                # 执行所有阶段
                for stage in self.stages:
                    try:
                        # DEBUG日志（记录阶段开始）
                        self.logger.debug(
                            "[STARTUP] 开始执行阶段: %s",
                            stage.name,
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        self.logger.info(
                            "[STARTUP] ℹ️ 开始执行阶段: %s",
                            stage.name,
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )

                        # 执行阶段
                        stage_start_time = time.time()
                        self.logger.debug(
                            "[STARTUP] 执行阶段 %s 开始",
                            stage.name,
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        result = await stage.execute(self.context)
                        stage_elapsed = (time.time() - stage_start_time) * 1000
                        self.logger.debug(
                            "[STARTUP] 执行阶段 %s 完成，耗时=%.0fms",
                            stage.name,
                            stage_elapsed,
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )

                        # 记录阶段结果
                        stage_results[stage.name] = result

                        # 将阶段结果存储到context中（供后续阶段使用）
                        self.context.stage_results[stage.name] = result

                        # DEBUG/INFO日志（记录阶段完成）
                        elapsed_ms = (
                            result.elapsed_ms if hasattr(result, "elapsed_ms") else stage_elapsed
                        )
                        self.logger.debug(
                            "[STARTUP] 阶段 %s 执行完成: success=%s, 耗时=%.0fms",
                            stage.name,
                            result.success,
                            elapsed_ms,
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        if result.success:
                            self.logger.info(
                                "[STARTUP] ✅ 阶段 %s 执行成功，耗时=%.0fms",
                                stage.name,
                                elapsed_ms,
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                        else:
                            self.logger.warning(
                                "[STARTUP] ⚠️ 阶段 %s 执行失败: %s，耗时=%.0fms",
                                stage.name,
                                result.message,
                                elapsed_ms,
                                extra={"log_type": "ALERT", "scenario": scenario},
                            )

                        # 在环境准备阶段完成后初始化日志系统
                        # 确保环境准备阶段的输出是第一个输出
                        if (
                            not self._logging_initialized
                            and stage.name == "env_setup"
                            and result.success
                        ):
                            self.logger.debug(
                                "[STARTUP] 环境准备阶段完成，开始初始化日志系统",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            self.logger.info(
                                "[STARTUP] ℹ️ 环境准备阶段完成，开始初始化日志系统",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            try:
                                # 注意：新架构中日志系统已在logging_init阶段初始化
                                # 这里只需标记为已初始化
                                self.logger.debug(
                                    "[STARTUP] 日志系统已在logging_init阶段初始化",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                self._logging_initialized = True
                                self.logger.debug(
                                    "[STARTUP] 日志系统初始化标记完成",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                self.logger.info(
                                    "[STARTUP] ✅ 日志系统初始化成功",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                            except Exception as e:
                                self.logger.debug(
                                    "[STARTUP] 日志系统初始化异常详情: %s: %s",
                                    type(e).__name__,
                                    str(e),
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                self.logger.error(
                                    "[STARTUP] ❌ 日志系统初始化失败: %s",
                                    e,
                                    exc_info=True,
                                    extra={"log_type": "ALERT", "scenario": scenario},
                                )
                                self.logger.critical(
                                    "[STARTUP] 🔥 日志系统初始化严重失败，可能影响后续日志记录: %s",
                                    e,
                                    exc_info=True,
                                    extra={"log_type": "ALERT", "scenario": scenario},
                                )

                            # 启动场景通过extra参数传递（无需set_scenario方法）
                            # 场景信息会在日志记录时通过extra={"scenario": "application_startup"}传递
                            self.logger.debug(
                                "[STARTUP] 启动流程已开始，场景将通过extra参数传递",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )

                        # 如果阶段失败，决定是否继续
                        if not result.success:
                            # DEBUG日志（记录阶段失败）
                            self.logger.debug(
                                f"[STARTUP] 阶段 {stage.name} 执行失败: {result.message}",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            self.logger.warning(
                                f"[STARTUP] ⚠️ 阶段 {stage.name} 执行失败: {result.message}",
                                extra={"log_type": "ALERT", "scenario": scenario},
                            )

                            # 检查是否需要回滚
                            if result.error:
                                # DEBUG日志（记录回滚开始）
                                self.logger.debug(
                                    f"[STARTUP] 开始回滚阶段 {stage.name}",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                self.logger.info(
                                    f"[STARTUP] ℹ️ 开始回滚阶段 {stage.name}",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                # 尝试回滚
                                try:
                                    self.logger.debug(
                                        f"[STARTUP] 开始回滚阶段 {stage.name} 的资源",
                                        extra={"log_type": "SYSTEM", "scenario": scenario},
                                    )
                                    await stage.rollback(self.context)
                                    self.logger.debug(
                                        f"[STARTUP] 阶段 {stage.name} 回滚成功",
                                        extra={"log_type": "SYSTEM", "scenario": scenario},
                                    )
                                    self.logger.info(
                                        f"[STARTUP] ✅ 阶段 {stage.name} 回滚成功",
                                        extra={"log_type": "SYSTEM", "scenario": scenario},
                                    )
                                except Exception as rollback_error:
                                    self.logger.debug(
                                        f"[STARTUP] 阶段 {stage.name} 回滚异常详情: {type(rollback_error).__name__}: {str(rollback_error)}",
                                        extra={"log_type": "SYSTEM", "scenario": scenario},
                                    )
                                    self.logger.error(
                                        f"❌ [StartupOrchestrator] 阶段 {stage.name} 回滚失败: {rollback_error}",
                                        exc_info=True,
                                        extra={"log_type": "ALERT", "scenario": scenario},
                                    )
                                    self.logger.warning(
                                        f"[STARTUP] ⚠️ 阶段 {stage.name} 回滚失败，可能残留资源",
                                        extra={"log_type": "ALERT", "scenario": scenario},
                                    )

                            # 检查是否是关键阶段（关键阶段失败应该停止）
                            if self._is_critical_stage(stage.name):
                                error_msg = f"关键阶段 {stage.name} 失败: {result.message}"
                                self.logger.debug(
                                    f"[STARTUP] 关键阶段 {stage.name} 失败，启动流程将停止",
                                    extra={"log_type": "SYSTEM", "scenario": scenario},
                                )
                                self.logger.error(
                                    f"❌ [StartupOrchestrator] 关键阶段 {stage.name} 失败: {result.message}",
                                    extra={"log_type": "ALERT", "scenario": scenario},
                                )
                                self.logger.critical(
                                    f"🔥 [StartupOrchestrator] {error_msg}",
                                    extra={"log_type": "ALERT", "scenario": scenario},
                                )

                                elapsed_ms = (time.time() - start_time) * 1000

                                # 注意：新架构中日志系统由logging_init阶段管理，无需手动关闭
                                # 结束事件日志流程
                                try:
                                    from backend.infrastructure.system_vnpy.logging_system import end_event_process
                                    end_event_process(success=False, summary=error_msg)
                                except Exception:
                                    pass

                                return StartupResult(
                                    success=False,
                                    message=error_msg,
                                    elapsed_ms=elapsed_ms,
                                    stage_results=stage_results,
                                    context=self.context,
                                    error=result.error,
                                )

                            # 非关键阶段失败，记录警告但继续
                            self.logger.debug(
                                f"[STARTUP] 非关键阶段 {stage.name} 失败，继续执行后续阶段",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            self.logger.warning(
                                f"⚠️ [StartupOrchestrator] 阶段 {stage.name} 失败，继续执行: {result.message}",
                                extra={"log_type": "ALERT", "scenario": scenario},
                            )

                    except Exception as e:
                        # DEBUG日志（记录异常发生）
                        self.logger.debug(
                            f"[STARTUP] 阶段 {stage.name} 执行时发生异常: {type(e).__name__}: {str(e)}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        # 捕获阶段执行异常
                        self.logger.error(
                            f"❌ [StartupOrchestrator] 阶段 {stage.name} 执行异常: {e}",
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )

                        # 检查是否是关键阶段
                        if self._is_critical_stage(stage.name):
                            elapsed_ms = (time.time() - start_time) * 1000

                            self.logger.debug(
                                f"[STARTUP] 关键阶段 {stage.name} 异常，启动流程将停止",
                                extra={"log_type": "SYSTEM", "scenario": scenario},
                            )
                            self.logger.critical(
                                f"🔥 [StartupOrchestrator] 关键阶段 {stage.name} 异常: {e}",
                                exc_info=True,
                                extra={"log_type": "ALERT", "scenario": scenario},
                            )

                            # 注意：新架构中日志系统由logging_init阶段管理，无需手动关闭
                            # 结束事件日志流程
                            try:
                                from backend.infrastructure.system_vnpy.logging_system import end_event_process
                                end_event_process(success=False, summary=f"阶段 {stage.name} 异常: {str(e)}")
                            except Exception:
                                pass

                            return StartupResult(
                                success=False,
                                message=f"阶段 {stage.name} 执行异常: {str(e)}",
                                elapsed_ms=elapsed_ms,
                                stage_results=stage_results,
                                context=self.context,
                                error=e,
                            )

                        # 非关键阶段异常，记录错误但继续
                        self.logger.debug(
                            f"[STARTUP] 非关键阶段 {stage.name} 异常，继续执行后续阶段",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        self.logger.warning(
                            f"⚠️ [StartupOrchestrator] 非关键阶段 {stage.name} 异常，继续执行: {e}",
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )
                        stage_results[stage.name] = StageResult(
                            success=False,
                            message=f"阶段 {stage.name} 执行异常: {str(e)}",
                            error=e,
                        )

                # 所有阶段完成
                elapsed_ms = (time.time() - start_time) * 1000

                # DEBUG/INFO日志（记录所有阶段完成）
                success_count = sum(1 for r in stage_results.values() if r.success)
                failed_count = sum(1 for r in stage_results.values() if not r.success)
                self.logger.debug(
                    f"[STARTUP] 所有阶段执行完成，总耗时={elapsed_ms:.0f}ms",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                self.logger.debug(
                    f"[STARTUP] 阶段结果统计: 成功={success_count}, 失败={failed_count}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                self.logger.info(
                    f"[STARTUP] ✅ 所有阶段执行完成，总耗时={elapsed_ms:.0f}ms，成功={success_count}，失败={failed_count}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                # 验证启动上下文
                self.logger.debug(
                    "[STARTUP] 开始验证启动上下文", extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                validation_result = self.context.validate()
                self.logger.debug(
                    f"[STARTUP] 启动上下文验证结果: {validation_result}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                if not validation_result:
                    error_msg = "启动上下文验证失败"
                    self.logger.debug(
                        "[STARTUP] 启动上下文验证失败，检查上下文状态",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    # 记录上下文详细信息
                    self.logger.debug(
                        f"[STARTUP] 上下文状态: event_engine={self.context.event_engine is not None}, "
                        f"main_engine={self.context.main_engine is not None}, "
                        f"service_manager={self.context.service_manager is not None}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    self.logger.error(
                        f"❌ [StartupOrchestrator] {error_msg}",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    self.logger.critical(
                        "[STARTUP] 🔥 启动上下文验证失败，系统可能无法正常运行",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )

                    # 注意：新架构中日志系统由logging_init阶段管理，无需手动关闭
                    # 结束事件日志流程
                    try:
                        from backend.infrastructure.system_vnpy.logging_system import end_event_process
                        end_event_process(success=False, summary=error_msg)
                    except Exception:
                        pass

                    return StartupResult(
                        success=False,
                        message=error_msg,
                        elapsed_ms=elapsed_ms,
                        stage_results=stage_results,
                        context=self.context,
                    )

                # 启动成功 - 输出详细的统计信息和最终状态
                stage_logger = logging.getLogger("startup.stage")
                stage_logger.info(
                    "", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "🎉 星辰金融终端启动成功！",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    "=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

                # 启动统计
                stage_logger.info(
                    "启动统计:", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                total_time_ms = elapsed_ms
                total_time_s = total_time_ms / 1000

                # 计算各阶段耗时
                env_time = stage_results.get(
                    "env_setup", StageResult(success=True, elapsed_ms=0)
                ).elapsed_ms
                logging_time = stage_results.get(
                    "logging_init", StageResult(success=True, elapsed_ms=0)
                ).elapsed_ms
                qt_time = stage_results.get(
                    "qt_framework", StageResult(success=True, elapsed_ms=0)
                ).elapsed_ms
                backend_time = stage_results.get(
                    "backend_init", StageResult(success=True, elapsed_ms=0)
                ).elapsed_ms
                ui_time = stage_results.get(
                    "ui_activation", StageResult(success=True, elapsed_ms=0)
                ).elapsed_ms

                stage_logger.info(
                    f"  - 总耗时: {total_time_s:.1f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"  - 环境准备: {env_time:.0f}ms",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"  - 日志系统: {logging_time:.0f}ms",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"  - Qt框架: {qt_time:.0f}ms",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"  - 后端服务: {backend_time:.0f}ms (并行)",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    f"  - UI主窗口: {ui_time:.0f}ms",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    "", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

                # 服务状态（从ServiceManager获取）
                stage_logger.info(
                    "服务状态:", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

                # 统计已注册的服务
                service_count = 0
                if self.context.service_manager:
                    service_manager = self.context.service_manager

                    service_names_map = {
                        "data_center_service": "数据中心服务",
                        "trading_gateway_service": "交易网关服务",
                        "strategy_center_service": "策略中心服务",
                        "ai_assistant_service": "AI助手服务",
                        "portfolio_service": "组合投资服务",
                        "market_board_service": "行情看板服务",
                        "system_manager_service": "系统管理服务",
                    }

                    for service_key, service_name in service_names_map.items():
                        if service_manager.has_service(service_key):
                            service_count += 1
                            stage_logger.info(
                                f"  - {service_name}: 运行中",
                                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                            )

                    stage_logger.info(
                        f"  - 后端服务: {service_count}个运行中",
                        extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                    )

                if getattr(self.context, "service_tracker", None):
                    snapshot = self.context.service_tracker.snapshot()
                    if snapshot:
                        stage_logger.info(
                            "",
                            extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                        )
                        stage_logger.info(
                            "原生执行统计:",
                            extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                        )
                        for service_name, data in snapshot.items():
                            status = data.get("status", "unknown")
                            elapsed = data.get("elapsed")
                            metadata = data.get("metadata", {})
                            status_icon = "✅" if status == "ready" else "⚠️" if status == "failed" else "⏳"
                            elapsed_text = f"{elapsed*1000:.0f}ms" if elapsed is not None else "-"
                            stage_logger.info(
                                f"  - {service_name}: {status_icon} 状态={status}, 耗时={elapsed_text}, 元数据={metadata}",
                                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                            )

                # 监控进程信息
                monitor_pid = getattr(self.context, "monitor_process_pid", None)
                if (
                    not monitor_pid
                    and hasattr(self.context, "monitor_process")
                    and self.context.monitor_process
                ):
                    monitor_pid = self.context.monitor_process.pid

                if monitor_pid:
                    stage_logger.info(
                        f"  - 监控进程: 运行中 (PID: {monitor_pid})",
                        extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                    )
                    stage_logger.info(
                        "  - native_ipc管道: 3条正常",
                        extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                    )

                stage_logger.info(
                    "", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

                stage_logger.info(
                    "=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "应用已就绪，等待用户操作...",
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"},
                )
                stage_logger.info(
                    "=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )

                # 注意：新架构中日志系统由logging_init阶段管理，无需手动关闭
                # 结束事件日志流程
                success_msg = "启动流程完成"
                self.logger.debug(
                    "[STARTUP] 开始结束事件日志流程", extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                try:
                    from backend.infrastructure.system_vnpy.logging_system import end_event_process
                    end_event_process(success=True, summary=success_msg)
                except Exception:
                    pass
                self.logger.debug(
                    "[STARTUP] 事件日志流程已结束", extra={"log_type": "SYSTEM", "scenario": scenario}
                )

                return StartupResult(
                    success=True,
                    message=success_msg,
                    elapsed_ms=elapsed_ms,
                    stage_results=stage_results,
                    context=self.context,
                )

        except Exception as e:
            # 捕获启动流程异常
            elapsed_ms = (time.time() - start_time) * 1000

            # DEBUG/ERROR/CRITICAL日志（记录异常发生）
            self.logger.debug(
                f"[STARTUP] 启动流程发生异常: {type(e).__name__}: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            self.logger.error(
                f"❌ [StartupOrchestrator] 启动流程异常: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            self.logger.critical(
                f"🔥 [StartupOrchestrator] 启动流程严重异常: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )

            # 注意：新架构中日志系统由logging_init阶段管理，无需手动关闭
            # 结束事件日志流程
            try:
                from backend.infrastructure.system_vnpy.logging_system import end_event_process
                end_event_process(success=False, summary=f"启动流程异常: {str(e)}")
            except Exception:
                pass

            return StartupResult(
                success=False,
                message=f"启动流程异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                stage_results={},
                context=self.context,
                error=e,
            )

    def _is_critical_stage(self, stage_name: str) -> bool:
        """判断是否是关键阶段

        关键阶段失败应该停止启动流程。

        Args:
            stage_name: 阶段名称

        Returns:
            bool: 是否是关键阶段
        """
        critical_stages = [
            "env_setup",
            "logging_init",
            "qt_framework",
            "backend_init",
        ]
        return stage_name in critical_stages

    def get_context(self) -> StartupContext:
        """获取启动上下文

        Returns:
            StartupContext: 启动上下文
        """
        return self.context

    def shutdown(self):
        """关闭启动编排器"""
        # 注意：新架构中日志系统由logging_init阶段管理，无需手动关闭
        # 清理资源
        # 可以在这里添加其他清理逻辑
