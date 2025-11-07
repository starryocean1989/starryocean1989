# -*- coding: utf-8 -*-
"""启动协调器 - 管理应用启动顺序."""

import atexit
import json
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import QApplication, QSplashScreen, QWidget


class BackendInitializerWorker(QObject):
    """后端初始化工作线程.

    负责在后台线程中异步初始化所有后端服务，避免阻塞主线程UI。
    采用六阶段初始化策略，每个阶段完成后发送进度更新。
    """

    # 信号定义
    progress_updated = Signal(str, int)  # (消息, 进度百分比)
    initialization_completed = Signal(bool, dict)  # (成功, 结果)
    error_occurred = Signal(str)  # 错误消息

    def __init__(self):
        """初始化后端初始化工作线程."""
        super().__init__()
        # ✅ 使用标准logger命名，依赖LoggingHub进行统一管理
        self.logger = logging.getLogger("ui.startup.worker")

        # 监控进程管理
        self.monitor_process_handle = None
        self.monitor_file_handles = []
        self.watchdog_running = False
        self.watchdog_thread = None

        # 项目根目录
        self.project_root = Path(__file__).parent.parent.parent.parent

    def run(self):
        """运行后端初始化（并行优化版）.

        并行启动两个任务：
        1. 异步线程A：启动监控进程（1-2秒）
        2. 主任务：执行六阶段服务初始化（0.3秒，内部串行）

        六阶段初始化流程：
        1. VNPY核心（EventEngine, MainEngine）
        2. 数据引擎（ChinaStockEngine）
        3. 数据服务（DataCenterService）
        4. 交易服务（TradingGatewayService）
        5. 策略服务（StrategyCenterService, AIAssistantService）
        6. 辅助服务（PortfolioService, MarketBoardService, SystemManagerService）
        """
        # 🎯 启动流程日志埋点：使用事件日志流程上下文管理器
        try:
            from backend.infrastructure.system_vnpy.logging_system import (
                event_log_process,
                get_logging_hub,
            )
            hub = get_logging_hub()
            if hub:
                hub.set_stage("startup")
                # 注意：场景通过日志记录的extra参数传递，不需要hub.set_scenario()
        except ImportError:
            hub = None

        stage_logger = logging.getLogger("startup.stage")

        backend_init_start = time.time()
        # 使用事件日志流程创建独立日志文件（统一到application_startup事件）
        context_manager = event_log_process("application_startup", {"mode": "parallel"}) if hub else __import__("contextlib").nullcontext()
        try:
            with context_manager:
                self.logger.debug("=" * 70)
                self.logger.debug("[BACKEND-INIT] 🔧 后端初始化工作线程启动（并行优化版）")
                self.logger.debug("=" * 70)
                self.logger.info("[BACKEND-INIT] ℹ️ 后端初始化工作线程启动（并行优化版）", extra={"log_type": "SYSTEM", "scenario": "backend_init"})
                self.logger.debug(
                    "[BACKEND-INIT] 线程ID: %s",
                    threading.current_thread().ident,
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.debug(
                    "[BACKEND-INIT] 线程名: %s",
                    threading.current_thread().name,
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.debug(
                    "[BACKEND-INIT] 当前线程是否为主线程: %s",
                    threading.current_thread() == threading.main_thread(),
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )

                # 阶段节点日志（输出到Terminal）
                stage_logger.info("📍 后端初始化工作线程启动（并行优化版）", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

                # 🎯 验证EventEngine是否已预创建
                from backend.core.base import get_event_engine

                existing_ee = get_event_engine()
                if existing_ee:
                    self.logger.debug(
                        "[BACKEND-INIT] ✅ 检测到主线程预创建的EventEngine",
                        extra={"scenario": "backend_init"}
                    )
                else:
                    self.logger.warning(
                        "[BACKEND-INIT] ⚠️ 未检测到预创建的EventEngine",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.warning(
                        "[BACKEND-INIT] ⚠️ 这可能导致SystemManagerService初始化失败",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )

                # 🔧 检查中断请求
                if self.thread() and self.thread().isInterruptionRequested():
                    self.logger.debug(
                        "[BACKEND-INIT] 收到中断请求，停止初始化",
                        extra={"scenario": "backend_init"}
                    )
                    return

                self.progress_updated.emit("正在准备后端环境...", 5)

                # 导入后端模块
                self.logger.debug(
                    "[BACKEND-INIT] 阶段0: 导入后端服务模块...",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.info(
                    "[BACKEND-INIT] ℹ️ 开始导入后端服务模块...",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                from backend.startup.initializers.service_initializer import initialize_services

                self.logger.debug(
                    "[BACKEND-INIT] ✅ 后端模块导入成功",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.info(
                    "[BACKEND-INIT] ✅ 后端模块导入成功",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )

                # 再次检查中断请求
                if self.thread() and self.thread().isInterruptionRequested():
                    self.logger.debug(
                        "[BACKEND-INIT] 收到中断请求，停止初始化",
                        extra={"scenario": "backend_init"}
                    )
                    return

                self.progress_updated.emit("正在启动后端服务（并行优化）...", 10)

                # ==================== 并行执行优化 ====================
                self.logger.debug(
                    "=" * 70,
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.debug(
                    "[BACKEND-INIT] 开始并行启动：监控进程 + 六阶段服务初始化",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.info(
                    "[BACKEND-INIT] ℹ️ 开始并行启动：监控进程 + 六阶段服务初始化",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.debug(
                    "=" * 70,
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )

            monitor_result = None
            service_result = None

            # 创建进度回调函数
            def progress_callback(message: str, progress: int):
                """进度回调：将后端初始化进度转发到UI"""
                self.logger.debug(
                    "[BACKEND-INIT] [进度 %d%%] %s",
                    progress,
                    message,
                    extra={"scenario": "backend_init"}
                )
                self.progress_updated.emit(message, progress)

            # 使用ThreadPoolExecutor并行执行
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 显示分支A标题
                stage_logger.info("┌──────────────────────────────────────────────────────────────────┐", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
                stage_logger.info("│ 分支A: 监控进程                                                   │", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
                stage_logger.info("└──────────────────────────────────────────────────────────────────┘", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
                stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

                # 提交监控进程启动任务
                self.logger.debug(
                    "[BACKEND-INIT] 提交任务1: 启动监控进程（异步）",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.info(
                    "[BACKEND-INIT] ℹ️ 提交任务1: 启动监控进程（异步）",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                from backend.startup.workers.monitor_launcher import MonitorLauncherWorker
                monitor_worker = MonitorLauncherWorker()
                monitor_future = executor.submit(self._run_monitor_worker, monitor_worker)
                self.logger.debug(
                    "[BACKEND-INIT] 监控进程启动任务已提交",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )

                # 显示分支B标题
                stage_logger.info("┌──────────────────────────────────────────────────────────────────┐", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
                stage_logger.info("│ 分支B: 数据引擎初始化（smart_cache_validation_and_sensing）      │", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
                stage_logger.info("└──────────────────────────────────────────────────────────────────┘", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
                stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

                # 主线程执行八步缓存验证和服务初始化
                self.logger.debug(
                    "[BACKEND-INIT] 执行任务2: 八步缓存验证和服务初始化（串行）",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.info(
                    "[BACKEND-INIT] ℹ️ 执行任务2: 八步缓存验证和服务初始化（串行）",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )

                # 🎯 显示分支B标题（在ChinaStockEngine初始化前）
                stage_logger.info("[DATA-INIT] 📍 阶段3.1: ChinaStockEngine初始化开始", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

                # 直接初始化数据服务（符合单一事实原则，不重复初始化VNPY核心）
                self.logger.debug(
                    "[BACKEND-INIT] 开始初始化数据服务...",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )
                self.logger.info(
                    "[BACKEND-INIT] ℹ️ 开始初始化数据服务...",
                    extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                )

                # 🎯 直接初始化数据服务（不调用initialize_services，避免重复初始化VNPY核心）
                # 从context获取已初始化的引擎（阶段3已经初始化）
                from backend.core.base import get_event_engine, get_main_engine
                event_engine = get_event_engine()
                main_engine = get_main_engine()

                if not event_engine or not main_engine:
                    raise RuntimeError("EventEngine或MainEngine未初始化")

                # 初始化ChinaStockEngine
                china_stock_engine = None
                data_service = None
                init_success = False
                data_init_success = False

                try:
                    self.logger.debug(
                        "[BACKEND-INIT] 初始化ChinaStockEngine...",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.info(
                        "[BACKEND-INIT] ℹ️ 开始初始化ChinaStockEngine...",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    from backend.infrastructure.data_module_vnpy import ChinaStockEngine
                    from backend.core.base import set_china_stock_engine

                    china_stock_engine = ChinaStockEngine(main_engine, event_engine)
                    init_start_time = time.time()
                    init_success = china_stock_engine.initialize()
                    init_elapsed = (time.time() - init_start_time) * 1000

                    if init_success:
                        self.logger.debug(
                            "[BACKEND-INIT] ✅ ChinaStockEngine 初始化成功，耗时=%.0fms",
                            init_elapsed,
                            extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                        )
                        self.logger.info(
                            "[BACKEND-INIT] ✅ ChinaStockEngine 初始化成功，耗时=%.0fms",
                            init_elapsed,
                            extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                        )
                        stage_logger.info(
                            "[DATA-INIT] ✅ ChinaStockEngine初始化完成",
                            extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                        )
                        set_china_stock_engine(china_stock_engine)
                    else:
                        self.logger.warning(
                            "[BACKEND-INIT] ⚠️ ChinaStockEngine 初始化失败",
                            extra={"log_type": "ALERT", "scenario": "backend_init"}
                        )
                        self.logger.error(
                            "[BACKEND-INIT] ❌ ChinaStockEngine 初始化失败，耗时=%.0fms",
                            init_elapsed,
                            extra={"log_type": "ALERT", "scenario": "backend_init"}
                        )
                        stage_logger.warning(
                            "[DATA-INIT] ⚠️ ChinaStockEngine初始化失败",
                            extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                        )
                except Exception as e:
                    self.logger.debug(
                        "[BACKEND-INIT] ChinaStockEngine 初始化异常详情: %s, 异常类型=%s",
                        str(e), type(e).__name__,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.error(
                        f"[BACKEND-INIT] ❌ ChinaStockEngine 初始化异常: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    stage_logger.error(
                        f"[DATA-INIT] ❌ ChinaStockEngine初始化异常: {e}",
                        extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                    )
                    init_success = False

                # 初始化DataCenterService
                try:
                    self.logger.debug(
                        "[BACKEND-INIT] 初始化DataCenterService...",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.info(
                        "[BACKEND-INIT] ℹ️ 开始初始化DataCenterService...",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    from backend.services.data_center_service import DataCenterService

                    data_service = DataCenterService()
                    data_init_start_time = time.time()
                    data_init_success = data_service.initialize()
                    data_init_elapsed = (time.time() - data_init_start_time) * 1000

                    if data_init_success:
                        self.logger.debug(
                            "[BACKEND-INIT] ✅ DataCenterService 初始化成功，耗时=%.0fms",
                            data_init_elapsed,
                            extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                        )
                        self.logger.info(
                            "[BACKEND-INIT] ✅ DataCenterService 初始化成功，耗时=%.0fms",
                            data_init_elapsed,
                            extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                        )
                        stage_logger.info(
                            "[DATA-INIT] ✅ DataCenterService初始化完成",
                            extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                        )
                        # 注册到服务管理器
                        from backend.core.base import get_service_manager
                        service_manager = get_service_manager()
                        service_manager.register_service("data_center_service", data_service)
                        self.logger.debug(
                            "[BACKEND-INIT] DataCenterService已注册到ServiceManager",
                            extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                        )
                    else:
                        self.logger.warning(
                            "[BACKEND-INIT] ⚠️ DataCenterService 初始化失败",
                            extra={"log_type": "ALERT", "scenario": "backend_init"}
                        )
                        self.logger.error(
                            "[BACKEND-INIT] ❌ DataCenterService 初始化失败，耗时=%.0fms",
                            data_init_elapsed,
                            extra={"log_type": "ALERT", "scenario": "backend_init"}
                        )
                        stage_logger.warning(
                            "[DATA-INIT] ⚠️ DataCenterService初始化失败",
                            extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                        )
                except Exception as e:
                    self.logger.debug(
                        "[BACKEND-INIT] DataCenterService 初始化异常详情: %s, 异常类型=%s",
                        str(e), type(e).__name__,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.error(
                        f"[BACKEND-INIT] ❌ DataCenterService 初始化异常: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    stage_logger.error(
                        f"[DATA-INIT] ❌ DataCenterService初始化异常: {e}",
                        extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                    )
                    data_init_success = False

                # 返回结果
                service_success = init_success and data_init_success
                service_result = {
                    "success": service_success,
                    "china_stock_engine": china_stock_engine,
                    "data_service": data_service,
                    "china_stock_success": init_success,
                    "data_service_success": data_init_success,
                }

                if service_success:
                    self.logger.debug(
                        "[BACKEND-INIT] 数据服务初始化完成",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.info(
                        "[BACKEND-INIT] ✅ 数据服务初始化完成",
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    stage_logger.info(
                        "[DATA-INIT] ✅ 数据服务初始化完成",
                        extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                    )
                else:
                    self.logger.warning(
                        "[BACKEND-INIT] ⚠️ 数据服务初始化部分失败",
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    self.logger.error(
                        "[BACKEND-INIT] ❌ 数据服务初始化部分失败，可能影响系统功能",
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    stage_logger.warning(
                        "[DATA-INIT] ⚠️ 数据服务初始化部分失败",
                        extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                    )

                # 🎯 业务服务将在等待监控进程完成后，由_initialize_business_services()统一初始化
                # 这确保输出顺序: 分支A(监控) → 分支B(8步) → 分支C(业务服务)

            # 等待监控进程完成后，继续后续处理
            self.logger.debug(
                "=" * 70,
                extra={"scenario": "backend_init"}
            )
            self.logger.debug(
                "[BACKEND-INIT] 并行任务全部完成",
                extra={"scenario": "backend_init"}
            )
            self.logger.debug(
                "=" * 70,
                extra={"scenario": "backend_init"}
            )

            # 🎯 修复：将分支C业务服务初始化延后到main_window的后台验证完成后
            # 避免输出顺序混乱（阶段3标题 → 分支A → 分支B → 阶段4 → 分支C这种错误顺序）
            # 正确顺序应该是：阶段3标题 → 分支A → 分支B(8步) → 分支C → 阶段4
            # 因此，分支C初始化将移至validation完成后的回调中执行
            self.logger.debug(
                "[BACKEND-INIT] 分支C业务服务将在8步验证完成后初始化",
                extra={"scenario": "backend_init"}
            )

            # 最后检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.debug(
                    "[BACKEND-INIT] 收到中断请求，停止初始化",
                    extra={"scenario": "backend_init"}
                )
                return

                success = service_result.get("success", False)

                if success:
                    # 🎯 记录后端初始化总耗时
                    backend_init_elapsed = time.time() - backend_init_start
                    self.progress_updated.emit("后端服务初始化完成", 100)
                    self.logger.debug(
                        "[BACKEND-INIT] 后端服务初始化成功，总耗时=%.2fs",
                        backend_init_elapsed,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.info(
                        "=" * 70,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.info(
                        "[BACKEND-INIT] ✅ 后端服务初始化成功，总耗时=%.2fs",
                        backend_init_elapsed,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.info(
                        "=" * 70,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    stage_logger.info(
                        f"✅ 后端服务初始化完成 ({backend_init_elapsed:.2f}s)",
                        extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                    )
                    # 将监控进程信息添加到结果中（确保service_result是dict类型）
                    if not isinstance(service_result, dict):
                        service_result = {"success": True}
                    # 使用类型忽略，因为monitor_result是dict类型
                    service_result["monitor_process"] = monitor_result  # type: ignore
                    service_result["elapsed_time"] = float(backend_init_elapsed)  # type: ignore[assignment]  # 🎯 添加总耗时
                    self.initialization_completed.emit(True, service_result)
                else:
                    error_msg = service_result.get("message", "未知错误")
                    backend_init_elapsed = time.time() - backend_init_start
                    self.progress_updated.emit(f"初始化失败: {error_msg}", 100)
                    self.logger.debug(
                        "[BACKEND-INIT] 后端服务初始化失败，总耗时=%.2fs: %s",
                        backend_init_elapsed, error_msg,
                        extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                    )
                    self.logger.error(
                        "=" * 70,
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    self.logger.error(
                        "[BACKEND-INIT] ❌ 后端服务初始化失败: %s",
                        error_msg,
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    self.logger.error(
                        "=" * 70,
                        extra={"log_type": "ALERT", "scenario": "backend_init"}
                    )
                    stage_logger.error(
                        f"❌ 后端服务初始化失败: {error_msg}",
                        extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                    )
                    self.initialization_completed.emit(False, service_result)

                    # ✅ 修复：8步验证流程由main_window._start_background_validation()触发
                    # 不在startup_coordinator中直接执行，避免重复执行
                    # 验证流程将在后端初始化完成后，由coordinator.initialization_completed信号触发
                    self.logger.debug(
                        "[BACKEND-INIT] ✅ 数据引擎初始化完成（8步验证流程将由main_window触发）",
                        extra={"scenario": "backend_init"}
                    )

                    # 等待监控进程完成（非阻塞，超时保护）
                    # 超时设置为20秒（略大于_wait_monitor_ready的15秒max_wait）
                    # 正常情况下2-3秒完成，20秒已非常宽松
                    self.logger.debug(
                        "[BACKEND-INIT] 等待监控进程启动完成...",
                        extra={"scenario": "backend_init"}
                    )
                    try:
                        monitor_result = monitor_future.result(timeout=20)
                        self.logger.info(
                            "[BACKEND-INIT] ✅ 监控进程启动成功（PID: %d, 耗时: %.2fs）",
                            monitor_result["pid"],
                            monitor_result["elapsed"],
                            extra={"scenario": "backend_init"}
                        )
                        stage_logger.info(
                            f"✅ 监控进程启动成功（PID: {monitor_result['pid']}, 耗时: {monitor_result['elapsed']:.2f}s）",
                            extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                        )
                    except Exception as e:
                        # 监控进程失败，抛出异常（不降级）
                        error_msg = f"监控进程启动失败: {str(e)}"
                        self.logger.error(
                            "[BACKEND-INIT] ❌ %s",
                            error_msg,
                            extra={"log_type": "SYSTEM", "scenario": "backend_init"}
                        )
                        stage_logger.error(
                            f"❌ 监控进程启动失败: {e}",
                            extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                        )
                        raise RuntimeError(error_msg)
        except Exception as e:
            # 后端初始化工作线程异常处理
            backend_init_elapsed = time.time() - backend_init_start
            self.logger.debug(
                "[BACKEND-INIT] 后端初始化工作线程异常详情: %s, 异常类型=%s, 总耗时=%.2fs",
                str(e), type(e).__name__, backend_init_elapsed,
                extra={"log_type": "SYSTEM", "scenario": "backend_init"}
            )
            self.logger.error(
                "[BACKEND-INIT] ❌ 后端初始化工作线程异常: %s",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "backend_init"}
            )
            self.logger.critical(
                "[BACKEND-INIT] 🔥 后端初始化工作线程严重异常，启动流程将终止: %s",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "backend_init"}
            )
            stage_logger.error(
                f"❌ 后端初始化工作线程异常: {e}",
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )
            self.progress_updated.emit(f"后端初始化失败: {str(e)}", 100)
            self.initialization_completed.emit(False, {"success": False, "message": str(e)})

    def _run_monitor_worker(self, worker):
        """运行监控Worker并返回结果"""
        import asyncio
        # 创建新的事件循环来运行异步Worker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(worker.run(None))  # 传递None作为context，因为MonitorLauncherWorker不需要context
            if result.success:
                # 返回监控进程信息
                monitor_info = result.data.get("monitor_info", {})
                return {
                    "pid": monitor_info.get("pid"),
                    "ports": monitor_info.get("ports", {}),
                    "elapsed": monitor_info.get("elapsed", 0),
                }
            else:
                raise RuntimeError(f"监控进程启动失败: {result.message}")
        finally:
            loop.close()


class StartupCoordinator(QObject):
    """启动协调器 - 管理整个应用的启动流程.

    职责：
    1. 显示启动画面并更新进度
    2. 管理后台初始化线程
    3. 协调UI和后端的就绪状态
    4. 处理启动失败和错误恢复
    """

    # 信号定义
    startup_completed = Signal()  # 启动完成（旧版，兼容保留）
    startup_failed = Signal(str)  # 启动失败
    initialization_completed = Signal(bool, dict)  # 后端初始化完成（新增，用于触发validation）

    def __init__(self, app: QApplication, config_already_initialized: bool = False):
        """初始化启动协调器.

        Args:
            app: QApplication 实例
            config_already_initialized: 配置是否已经初始化（避免重复初始化）
        """
        super().__init__()
        self.app = app
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_already_initialized = config_already_initialized

        # 组件
        self.splash: Optional[QSplashScreen] = None
        self.backend_thread: Optional[QThread] = None
        self.backend_worker: Optional[BackendInitializerWorker] = None

        # 初始化结果
        self.backend_initialized = False
        self.backend_result: Optional[dict] = None

        # 超时监视
        self.timeout_timer: Optional[QTimer] = None
        self.initialization_timeout = 60  # 🔧 修复: 从30秒增加到60秒,为时间同步降级提供足够时间

        self.logger.info("[COORDINATOR] 启动协调器已创建")

    def start(self):
        """开始启动流程.

        启动流程：
        1. 初始化配置（如果需要）
        2. 显示启动画面
        3. 启动后台初始化线程
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("[COORDINATOR] 启动协调器：开始启动流程")
            self.logger.info("=" * 60)

            # 步骤1: 初始化配置
            self._initialize_config()

            # 步骤2: 显示启动画面
            self._show_splash_screen()

            # 步骤3: 异步初始化后端
            self._start_backend_initialization()

        except Exception as e:
            self.logger.exception("启动失败: %s", e)
            self.startup_failed.emit(str(e))

    def _initialize_config(self):
        """步骤1: 初始化配置（同步，必须最先完成）."""
        if self.config_already_initialized:
            self.logger.info("[COORDINATOR] 配置已在主入口初始化，跳过")
            return

        self.logger.info("[COORDINATOR] 初始化配置...")

        from backend.core.config import init_settings

        config_file = os.getenv("CONFIG_FILE")
        if config_file:
            self.logger.info("[COORDINATOR] 从环境变量加载配置: %s", config_file)
            init_settings(config_file)
        else:
            self.logger.info("[COORDINATOR] 使用默认配置文件")
            init_settings()

        self.logger.info("[COORDINATOR] ✅ 配置初始化完成")

    def _show_splash_screen(self):
        """步骤2: 显示启动画面."""
        self.logger.info("[COORDINATOR] 显示启动画面...")

        # 创建启动画面
        self.splash = QSplashScreen()
        self.splash.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )

        # 设置启动画面大小
        self.splash.setFixedSize(500, 300)

        # 设置启动画面样式
        self.splash.setStyleSheet(
            """
            QSplashScreen {
                background-color: #1e1e1e;
                border: 2px solid #007acc;
                border-radius: 10px;
            }
        """
        )

        # 显示初始消息
        self.show_message("正在启动星辰金融终端...", 0)
        self.splash.show()
        self.app.processEvents()

        self.logger.info("[COORDINATOR] ✅ 启动画面已显示")

    def show_message(self, message: str, progress: int = 0):
        """在启动画面显示消息.

        Args:
            message: 消息文本
            progress: 进度百分比 (0-100)
        """
        if self.splash:
            # 构建完整消息（包含进度）
            full_message = f"{message}\n\n进度: {progress}%"

            self.splash.showMessage(
                full_message,
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                Qt.GlobalColor.white,
            )
            self.app.processEvents()

    def _start_backend_initialization(self):
        """步骤3: 异步初始化后端服务."""
        self.logger.info("[COORDINATOR] 启动后端服务初始化（异步）...")

        # 创建工作线程
        self.backend_thread = QThread()
        self.backend_worker = BackendInitializerWorker()

        # 将worker移到线程
        self.backend_worker.moveToThread(self.backend_thread)

        # 连接信号
        self.backend_thread.started.connect(self.backend_worker.run)
        self.backend_worker.progress_updated.connect(self._on_backend_progress)
        self.backend_worker.initialization_completed.connect(self._on_backend_completed)
        self.backend_worker.error_occurred.connect(self._on_backend_error)

        # 🆕 转发initialization_completed信号（用于触发validation）
        self.backend_worker.initialization_completed.connect(self.initialization_completed)

        # 安全清理机制
        self.backend_worker.initialization_completed.connect(self._safe_cleanup_thread)

        # 启动超时监视定时器
        self._start_timeout_monitor()

        # 启动线程
        self.backend_thread.start()

        self.logger.info("[COORDINATOR] ✅ 后端初始化线程已启动")

    def _safe_cleanup_thread(self):
        """安全清理QThread资源."""
        if self.backend_thread and self.backend_thread.isRunning():
            self.logger.info("[COORDINATOR] 开始安全清理后端线程...")

            # 请求中断
            self.backend_thread.requestInterruption()

            # 使用QTimer实现异步等待，避免阻塞主线程
            from PySide6.QtCore import QTimer

            QTimer.singleShot(100, self._finish_thread_cleanup)
        else:
            self._finish_thread_cleanup()

    def _finish_thread_cleanup(self):
        """完成线程清理."""
        try:
            if self.backend_thread:
                if self.backend_thread.isRunning():
                    self.backend_thread.quit()
                    # 不使用wait()避免阻塞

                # 在线程完成后清理资源
                self.backend_thread.finished.connect(
                    lambda: (
                        self.backend_worker.deleteLater() if self.backend_worker else None,
                        self.backend_thread.deleteLater() if self.backend_thread else None,
                    )
                )

                self.logger.info("[COORDINATOR] ✅ 后端线程清理完成")
        except Exception as e:
            self.logger.error("[COORDINATOR] 线程清理异常: %s", e)

    def _start_timeout_monitor(self):
        """启动超时监视定时器."""
        from PySide6.QtCore import QTimer

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_initialization_timeout)
        self.timeout_timer.start(self.initialization_timeout * 1000)  # 转换为毫秒

        self.logger.info("[COORDINATOR] 启动超时监视定时器（%d秒）", self.initialization_timeout)

    def _stop_timeout_monitor(self):
        """停止超时监视定时器."""
        if self.timeout_timer:
            self.timeout_timer.stop()
            self.timeout_timer = None
            self.logger.info("[COORDINATOR] 停止超时监视定时器")

    def _on_initialization_timeout(self):
        """初始化超时处理."""
        self.logger.warning("后端初始化超时: %d秒", self.initialization_timeout)

        # 优先尝试降级继续：如果核心服务部分就绪，则允许UI继续工作（功能受限）
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            status = service_manager.get_service_status()

            # 记录哪些服务就绪、哪些服务失败
            ready_services = [
                name
                for name, info in status.items()
                if isinstance(info, dict) and info.get("status") == "running"
            ]
            failed_services = [
                name
                for name, info in status.items()
                if isinstance(info, dict) and info.get("status") == "error"
            ]
            pending_services = [
                name
                for name, info in status.items()
                if isinstance(info, dict) and info.get("status") not in ("running", "error")
            ]

            self.logger.warning(
                "降级模式: 就绪服务=%s, 失败服务=%s, 待启动=%s",
                ready_services,
                failed_services,
                pending_services,
            )

            # 判定核心服务可用性（任一关键服务就绪即允许降级继续）
            core_candidates = [
                "data_center_service",
                "system_manager_service",
                "market_board_service",
            ]
            core_ready = any(name in status for name in core_candidates)

            if core_ready:
                self.logger.info("启动降级成功: 核心服务可用")
                self.show_message("后端部分就绪，已进入降级模式（功能可能受限）", 80)
                # 允许完成启动流程
                self._complete_startup()
                return
        except Exception as e:
            self.logger.exception("降级检测失败: %s", e)

        # 无法降级继续，保持提示并发出失败信号（不强制退出，交给外部处理）
        self.logger.error("启动失败: 无可用服务")
        self.show_message(
            f"后端初始化超时（{self.initialization_timeout}秒），请检查日志后重试",
            50,
        )
        self.startup_failed.emit("后端初始化超时")

    def _on_backend_progress(self, message: str, progress: int):
        """后端初始化进度更新."""
        self.logger.info("[COORDINATOR] 后端初始化进度 [%d%%]: %s", progress, message)
        self.show_message(message, progress)

    def _on_backend_completed(self, success: bool, result: dict):
        """后端初始化完成."""
        # 停止超时监视
        self._stop_timeout_monitor()

        self.backend_initialized = success
        self.backend_result = result

        if success:
            self.logger.info("[COORDINATOR] ✅ 后端服务初始化成功，准备启动UI")
            self.show_message("后端服务就绪，正在启动界面...", 100)

            # 延迟一下让用户看到消息
            from PySide6.QtCore import QTimer

            QTimer.singleShot(500, self._complete_startup)
        else:
            error_msg = result.get("message", "后端初始化失败")
            self.logger.error("[COORDINATOR] ❌ 后端服务初始化失败: %s", error_msg)
            self.startup_failed.emit(error_msg)

    def _on_backend_error(self, error_msg: str):
        """后端初始化错误."""
        # 停止超时监视
        self._stop_timeout_monitor()

        self.logger.error("[COORDINATOR] 后端初始化错误: %s", error_msg)
        self.show_message(f"错误: {error_msg}", 0)
        self.startup_failed.emit(error_msg)

    def _complete_startup(self):
        """完成启动流程."""
        self.logger.info("[COORDINATOR] ✅ 启动流程完成，发送 startup_completed 信号")
        self.startup_completed.emit()

    def hide_splash(self, main_window: Optional[QWidget] = None):
        """隐藏启动画面."""
        if self.splash:
            try:
                self.logger.info(
                    "[COORDINATOR] 隐藏启动画面",
                    extra={"log_type": "STAGE_NODE"},
                )
                self.logger.info(
                    "[COORDINATOR] 开始隐藏启动画面...",
                    extra={"log_type": "STAGE_NODE"},
                )
                if main_window:
                    try:
                        self.splash.finish(main_window)
                    except Exception as finish_error:  # fallback if finish fails
                        self.logger.warning(
                            "[COORDINATOR] finish 调用失败，使用 close(): %s",
                            finish_error,
                        )
                        self.splash.close()
                else:
                    self.splash.close()
                self.logger.info(
                    "[COORDINATOR] 启动画面已关闭",
                    extra={"log_type": "STAGE_NODE"},
                )
                self.splash.deleteLater()
                self.logger.info(
                    "[COORDINATOR] 启动画面已标记删除",
                    extra={"log_type": "STAGE_NODE"},
                )
                self.splash = None
                self.logger.info(
                    "[COORDINATOR] ✅ 启动画面已隐藏",
                    extra={"log_type": "STAGE_NODE"},
                )
                self.logger.info(
                    "[COORDINATOR] ✅ 启动画面已成功隐藏",
                    extra={"log_type": "STAGE_NODE"},
                )
            except Exception as e:
                self.logger.exception("隐藏启动画面失败: %s", e)
                self.logger.info(
                    f"[COORDINATOR] ❌ 隐藏启动画面失败: {e}",
                    extra={"log_type": "STAGE_NODE"},
                )
                # 即使失败，也设置为None避免重复操作
                self.splash = None
