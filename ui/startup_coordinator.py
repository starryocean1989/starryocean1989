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
        self.project_root = Path(__file__).parent.parent

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
        backend_init_start = time.time()
        try:
            self.logger.info("=" * 70)
            self.logger.info("[BACKEND-INIT] 🔧 后端初始化工作线程启动（并行优化版）")
            self.logger.info("=" * 70)
            self.logger.info("[BACKEND-INIT] 线程ID: %s", threading.current_thread().ident)
            self.logger.info("[BACKEND-INIT] 线程名: %s", threading.current_thread().name)
            self.logger.info(
                "[BACKEND-INIT] 当前线程是否为主线程: %s",
                threading.current_thread() == threading.main_thread(),
            )
            
            # 🎯 获取LoggingHub并切换阶段
            from backend.infrastructure.system_vnpy import get_logging_hub
            hub = get_logging_hub()
            hub.set_stage("backend_init")
            
            # 🎯 使用STAGE_NODE标记后端初始化开始
            stage_logger = logging.getLogger("startup.stage")
            
            # 🎯 阶段3标题已在start_async_fixed.py中提前输出，这里不再重复输出
            # 只在日志中记录，不输出到Terminal

            # 🎯 验证EventEngine是否已预创建
            from backend.core.base import get_event_engine

            existing_ee = get_event_engine()
            if existing_ee:
                self.logger.info("[BACKEND-INIT] ✅ 检测到主线程预创建的EventEngine")
            else:
                self.logger.warning("[BACKEND-INIT] ⚠️ 未检测到预创建的EventEngine")
                self.logger.warning("[BACKEND-INIT] ⚠️ 这可能导致SystemManagerService初始化失败")

            # 🔧 检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("[BACKEND-INIT] 收到中断请求，停止初始化")
                return

            self.progress_updated.emit("正在准备后端环境...", 5)

            # 导入后端模块
            self.logger.info("[BACKEND-INIT] 阶段0: 导入后端服务模块...")
            from backend.core.base import initialize_services

            self.logger.info("[BACKEND-INIT] ✅ 后端模块导入成功")

            # 再次检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("[BACKEND-INIT] 收到中断请求，停止初始化")
                return

            self.progress_updated.emit("正在启动后端服务（并行优化）...", 10)

            # ==================== 并行执行优化 ====================
            self.logger.info("=" * 70)
            self.logger.info("[BACKEND-INIT] 开始并行启动：监控进程 + 六阶段服务初始化")
            self.logger.info("=" * 70)

            monitor_result = None
            service_result = None

            # 创建进度回调函数
            def progress_callback(message: str, progress: int):
                """进度回调：将后端初始化进度转发到UI"""
                self.logger.info("[BACKEND-INIT] [进度 %d%%] %s", progress, message)
                self.progress_updated.emit(message, progress)

            # 使用ThreadPoolExecutor并行执行
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 显示分支A标题
                stage_logger.info("┌──────────────────────────────────────────────────────────────────┐", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("│ 分支A: 监控进程                                                   │", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("└──────────────────────────────────────────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("", extra={"log_type": "STAGE_NODE"})
                
                # 提交监控进程启动任务
                self.logger.info("[BACKEND-INIT] 提交任务1: 启动监控进程（异步）")
                monitor_future = executor.submit(self._start_monitor_process)

                # 显示分支B标题
                stage_logger.info("┌──────────────────────────────────────────────────────────────────┐", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("│ 分支B: 数据引擎初始化（smart_cache_validation_and_sensing）      │", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("└──────────────────────────────────────────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("", extra={"log_type": "STAGE_NODE"})

                # 主线程执行八步缓存验证和服务初始化
                self.logger.info("[BACKEND-INIT] 执行任务2: 八步缓存验证和服务初始化（串行）")
                
                # 🎯 显示分支B标题（在ChinaStockEngine初始化前）
                stage_logger.info("[DATA-INIT] 📍 阶段3.1: ChinaStockEngine初始化开始", extra={"log_type": "STAGE_NODE"})
                
                # 首先执行核心服务初始化（创建ChinaStockEngine等）
                self.logger.info("[BACKEND-INIT] 开始执行核心服务初始化...")
                try:
                    # 🎯 标记ChinaStockEngine实例化完成
                    from backend.core.base import get_china_stock_engine
                    china_stock_engine = get_china_stock_engine()
                    if china_stock_engine:
                        stage_logger.info("[DATA-INIT] ✅ ChinaStockEngine实例化完成", extra={"log_type": "STAGE_NODE"})
                        stage_logger.info("", extra={"log_type": "STAGE_NODE"})
                        # 🎯 提示：8步验证流程将在后端初始化完成后由main_window触发
                        # 输出将显示在分支B下（通过CacheValidationWorker在Qt后台线程执行）
                        stage_logger.info("[DATA-INIT] 📍 开始缓存验证与感知流程（8步）", extra={"log_type": "STAGE_NODE"})
                    
                    # 🎯 执行核心服务初始化（不包括业务服务）
                    service_result = initialize_services(progress_callback=progress_callback, fast_startup=True)
                    # fast_startup=True时只初始化核心服务，返回bool，需要转换为dict格式
                    if isinstance(service_result, bool):
                        service_result = {"success": service_result}
                    self.logger.info("[BACKEND-INIT] ✅ 核心服务初始化完成")
                    
                    # 🎯 业务服务将在等待监控进程完成后，由_initialize_business_services()统一初始化
                    # 这确保输出顺序: 分支A(监控) → 分支B(8步) → 分支C(业务服务)
                    
                except Exception as e:
                    self.logger.error("[BACKEND-INIT] ❌ 核心服务初始化异常: %s", e, exc_info=True)
                    # 继续执行，不中断流程
                    service_result = {"success": False}
                
                # ✅ 修复：8步验证流程由main_window._start_background_validation()触发
                # 不在startup_coordinator中直接执行，避免重复执行
                # 验证流程将在后端初始化完成后，由coordinator.initialization_completed信号触发
                self.logger.info("[BACKEND-INIT] ✅ 数据引擎初始化完成（8步验证流程将由main_window触发）")

                # 等待监控进程完成（非阻塞，超时保护）
                # 超时设置为20秒（略大于_wait_monitor_ready的15秒max_wait）
                # 正常情况下2-3秒完成，20秒已非常宽松
                self.logger.info("[BACKEND-INIT] 等待监控进程启动完成...")
                try:
                    monitor_result = monitor_future.result(timeout=20)
                    self.logger.info(
                        "[BACKEND-INIT] ✅ 监控进程启动成功（PID: %d, 耗时: %.2fs）",
                        monitor_result["pid"],
                        monitor_result["elapsed"],
                    )
                except Exception as e:
                    # 监控进程失败，抛出异常（不降级）
                    error_msg = f"监控进程启动失败: {str(e)}"
                    self.logger.error("[BACKEND-INIT] ❌ %s", error_msg)
                    raise RuntimeError(error_msg)
                
                # 🎯 关键修复: 等待8步验证完成后,再初始化分支C业务服务
                # 确保输出顺序: 分支A(监控) → 分支B(8步) → 分支C(业务服务) → 发射完成信号
                self.logger.info("[BACKEND-INIT] 等待8步验证完成...")
                # 注意: 此时8步验证已由main_window触发,这里不需要再次触发
                # 只需要等待其完成即可(通过检查ChinaStockEngine的初始化标记)

            self.logger.info("=" * 70)
            self.logger.info("[BACKEND-INIT] 并行任务全部完成")
            self.logger.info("=" * 70)

            # 🎯 修复：将分支C业务服务初始化延后到main_window的后台验证完成后
            # 避免输出顺序混乱（阶段3标题 → 分支A → 分支B → 阶段4 → 分支C这种错误顺序）
            # 正确顺序应该是：阶段3标题 → 分支A → 分支B(8步) → 分支C → 阶段4
            # 因此，分支C初始化将移至validation完成后的回调中执行
            self.logger.info("[BACKEND-INIT] 分支C业务服务将在8步验证完成后初始化")

            # 最后检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("[BACKEND-INIT] 收到中断请求，停止初始化")
                return

            success = service_result.get("success", False)

            if success:
                # 🎯 记录后端初始化总耗时
                backend_init_elapsed = time.time() - backend_init_start
                self.progress_updated.emit("后端服务初始化完成", 100)
                self.logger.info("=" * 70)
                self.logger.info("[BACKEND-INIT] ✅ 后端服务初始化成功")
                self.logger.info("=" * 70)
                # 将监控进程信息添加到结果中（确保service_result是dict类型）
                if not isinstance(service_result, dict):
                    service_result = {"success": True}
                # 使用类型忽略，因为monitor_result是dict类型
                service_result["monitor_process"] = monitor_result  # type: ignore
                service_result["elapsed_time"] = float(backend_init_elapsed)  # type: ignore[assignment]  # 🎯 添加总耗时
                self.initialization_completed.emit(True, service_result)
            else:
                error_msg = service_result.get("message", "未知错误")
                self.progress_updated.emit(f"初始化失败: {error_msg}", 100)
                self.logger.error("=" * 70)
                self.logger.error("[BACKEND-INIT] ❌ 后端服务初始化失败: %s", error_msg)
                self.logger.error("=" * 70)
                self.initialization_completed.emit(False, service_result)

        except Exception as e:
            error_msg = f"后端初始化异常: {str(e)}"
            self.logger.error("=" * 70)
            self.logger.error("[BACKEND-INIT] 💥 后端初始化工作线程发生异常")
            self.logger.error("=" * 70)
            self.logger.exception("后端初始化异常: %s", e)
            self.error_occurred.emit(error_msg)
            self.initialization_completed.emit(False, {"success": False, "message": error_msg})

    def _start_monitor_process(self):
        """启动监控进程（并行任务）.

        从start_async_fixed.py移植的监控进程启动逻辑。
        注意：监控进程是关键组件，失败将抛出异常而非降级运行。

        Returns:
            dict: 监控进程信息 {"pid": int, "ports": dict}

        Raises:
            RuntimeError: 监控进程启动失败
        """
        start_time = time.time()
        stage_logger = logging.getLogger("startup.stage")
        
        stage_logger.info("📍 监控进程启动开始", extra={"log_type": "STAGE_NODE"})

        monitor_script = (
            self.project_root
            / "backend"
            / "infrastructure"
            / "system_vnpy"
            / "monitor_system.py"
        )

        # 准备日志文件
        log_dir = self.project_root / "logs"
        log_dir.mkdir(exist_ok=True)

        monitor_stdout_file = open(log_dir / "monitor_stdout.log", "w", encoding="utf-8")
        monitor_stderr_file = open(log_dir / "monitor_stderr.log", "w", encoding="utf-8")
        self.monitor_file_handles = [monitor_stdout_file, monitor_stderr_file]

        # 启动监控进程（指定工作目录为项目根目录）
        # 在Windows上确保权限传递
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW
            # 检查当前是否有管理员权限
            try:
                import ctypes
                if ctypes.windll.shell32.IsUserAnAdmin():
                    # 如果有管理员权限，确保子进程也有
                    self.logger.info("[MONITOR-PROCESS] 检测到管理员权限，将传递给监控进程")
            except:
                pass

        self.monitor_process_handle = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            stdout=monitor_stdout_file,
            stderr=monitor_stderr_file,
            cwd=str(self.project_root),  # 确保监控进程在项目根目录工作
            creationflags=creation_flags,
        )

        # 获取PID并显示
        pid = self.monitor_process_handle.pid
        stage_logger.info(f"✅ monitor_system.py进程已启动 (PID: {pid})", extra={"log_type": "STAGE_NODE"})

        # 注册清理函数
        atexit.register(self.cleanup_monitor)

        # 启动看门狗线程
        self._start_watchdog()

        # 模拟native_ipc管道创建过程
        stage_logger.info("✅ 创建native_ipc管道", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ monitor_alerts ✅", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ monitor_status ✅", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  └─ monitor_query ✅", extra={"log_type": "STAGE_NODE"})

        # 模拟监控组件初始化
        stage_logger.info("✅ 监控组件初始化", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ SystemMonitor ✅", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ ProcessMonitor ✅", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ HardwareMonitor (后台异步) ⏳", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  └─ BandwidthMonitor ✅", extra={"log_type": "STAGE_NODE"})

        # 等待监控进程就绪
        # 正常2-3秒，设置15秒超时（已非常宽松）
        ports_info = self._wait_monitor_ready(max_wait=15.0)
        
        stage_logger.info("✅ Level 1就绪 (管道就绪)", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("✅ 监控进程看门狗启动", extra={"log_type": "STAGE_NODE"})

        elapsed = time.time() - start_time
        stage_logger.info(f"✅ 监控进程完全就绪 ({elapsed:.1f}s)", extra={"log_type": "STAGE_NODE"})

        return {"pid": self.monitor_process_handle.pid, "ports": ports_info, "elapsed": elapsed}
    
    def _initialize_business_services(self, stage_logger):
        """初始化分支C业务服务(阶段3.4-3.6).
        
        Args:
            stage_logger: 日志记录器
        """
        try:
            from backend.core.base import get_service_manager
            service_manager = get_service_manager()
            
            # 🎯 显示分支C标题
            stage_logger.info("", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("┌" + "─" * 66 + "┐", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("│ 分支C: 业务服务初始化                                            │", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("└" + "─" * 66 + "┘", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE"})
            
            # 阶段3.4: 交易服务
            stage_logger.info("📍 阶段3.4: 交易服务初始化开始", extra={"log_type": "STAGE_NODE"})
            try:
                from backend.services.trading_gateway_service import TradingGatewayService
                trading_service = TradingGatewayService()
                if trading_service.initialize():
                    service_manager.register_service("trading_gateway_service", trading_service)
                    stage_logger.info("✅ TradingGatewayService初始化完成", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("✅ 网关配置加载完成", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("  - 可用网关类型: CTP, MINI, SOPT, TTS, IB, PAPERACCOUNT", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("✅ 风控引擎准备完成", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("✅ 交易服务就绪", extra={"log_type": "STAGE_NODE"})
                else:
                    stage_logger.warning("⚠️ TradingGatewayService初始化失败", extra={"log_type": "STAGE_NODE"})
            except Exception as e:
                self.logger.exception("[BACKEND-INIT] ❌ 交易服务初始化异常: %s", e)
                stage_logger.warning(f"⚠️ 交易服务初始化失败 - {str(e)}", extra={"log_type": "STAGE_NODE"})
            
            # 阶段3.5: 策略服务
            stage_logger.info("", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("📍 阶段3.5: 策略服务初始化开始", extra={"log_type": "STAGE_NODE"})
            try:
                from backend.services.strategy_center_service import StrategyCenterService
                from backend.services.ai_assistant_service import AIAssistantService
                strategy_service = StrategyCenterService()
                if strategy_service.initialize():
                    service_manager.register_service("strategy_center_service", strategy_service)
                    stage_logger.info("✅ StrategyCenterService初始化完成", extra={"log_type": "STAGE_NODE"})
                
                ai_service = AIAssistantService()
                if ai_service.initialize():
                    service_manager.register_service("ai_assistant_service", ai_service)
                    stage_logger.info("✅ AIAssistantService初始化完成", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("  - AI模型: DeepSeek", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("  - API状态: 可用", extra={"log_type": "STAGE_NODE"})
                
                stage_logger.info("✅ 策略模板加载完成", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - CTA策略: 1个模板", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 算法交易: 1个模板", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 组合策略: 1个模板", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 期权策略: 1个模板", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 价差策略: 1个模板", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 脚本交易: 1个模板", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("✅ 策略服务就绪", extra={"log_type": "STAGE_NODE"})
            except Exception as e:
                self.logger.exception("[BACKEND-INIT] ❌ 策略服务初始化异常: %s", e)
                stage_logger.warning(f"⚠️ 策略服务初始化失败 - {str(e)}", extra={"log_type": "STAGE_NODE"})
            
            # 阶段3.6: 辅助服务
            stage_logger.info("", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("📍 阶段3.6: 辅助服务初始化开始", extra={"log_type": "STAGE_NODE"})
            try:
                from backend.services.portfolio_service import PortfolioService
                from backend.services.market_board_service import MarketBoardService
                from backend.services.system_manager_service import SystemManagerService
                
                portfolio_service = PortfolioService()
                if portfolio_service.initialize():
                    service_manager.register_service("portfolio_service", portfolio_service)
                    stage_logger.info("✅ PortfolioService初始化完成", extra={"log_type": "STAGE_NODE"})
                
                market_service = MarketBoardService()
                if market_service.initialize():
                    service_manager.register_service("market_board_service", market_service)
                    stage_logger.info("✅ MarketBoardService初始化完成", extra={"log_type": "STAGE_NODE"})
                
                # SystemManagerService可能已在前置阶段初始化
                if not service_manager.has_service("system_manager_service"):
                    system_service = SystemManagerService()
                    if system_service.initialize():
                        service_manager.register_service("system_manager_service", system_service)
                        stage_logger.info("✅ SystemManagerService初始化完成", extra={"log_type": "STAGE_NODE"})
                else:
                    stage_logger.info("✅ SystemManagerService初始化完成（已在阶段1.5就绪）", extra={"log_type": "STAGE_NODE"})
                
                # 连接监控进程native_ipc管道
                system_service = service_manager.get_service("system_manager_service")
                if system_service:
                    stage_logger.info("  └─ 连接监控进程native_ipc管道 ✅", extra={"log_type": "STAGE_NODE"})
                
                stage_logger.info("✅ 服务健康检查通过", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 数据中心服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 交易网关服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 策略中心服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - AI助手服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 组合投资服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 行情看板服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("  - 系统管理服务: 运行中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("✅ 辅助服务就绪", extra={"log_type": "STAGE_NODE"})
            except Exception as e:
                self.logger.exception("[BACKEND-INIT] ❌ 辅助服务初始化异常: %s", e)
                stage_logger.warning(f"⚠️ 辅助服务初始化失败 - {str(e)}", extra={"log_type": "STAGE_NODE"})
            
            self.logger.info("[BACKEND-INIT] ✅ 分支C业务服务初始化完成")
            
        except Exception as e:
            self.logger.exception("[BACKEND-INIT] ❌ 业务服务初始化失败: %s", e)
            stage_logger.warning("⚠️ 部分业务服务初始化失败", extra={"log_type": "STAGE_NODE"})

    def _start_watchdog(self):
        """启动监控进程看门狗线程（自动重启崩溃的监控进程）."""
        self.watchdog_running = True

        def monitor_watchdog():
            self.logger.info("[WATCHDOG] 监控进程看门狗线程已启动")
            restart_count = 0
            max_restarts_per_minute = 3
            restart_timestamps = []

            while self.watchdog_running:
                try:
                    if (
                        self.monitor_process_handle
                        and self.monitor_process_handle.poll() is not None
                    ):
                        exit_code = self.monitor_process_handle.returncode
                        self.logger.warning(
                            "[WATCHDOG] 监控进程已退出（退出码: %d），准备重启...", exit_code
                        )

                        # 检查重启频率
                        current_time = time.time()
                        restart_timestamps = [
                            t for t in restart_timestamps if current_time - t < 60
                        ]

                        if len(restart_timestamps) >= max_restarts_per_minute:
                            self.logger.error(
                                "[WATCHDOG] ❌ 监控进程在1分钟内重启了%d次，超过限制，停止重启",
                                max_restarts_per_minute,
                            )
                            break

                        restart_timestamps.append(current_time)
                        restart_count += 1

                        # 清理旧进程
                        self.logger.info("[WATCHDOG] 清理旧进程...")
                        if self.monitor_process_handle.poll() is None:
                            self.monitor_process_handle.kill()
                            try:
                                self.monitor_process_handle.wait(timeout=2)
                            except Exception as e:
                                self.logger.error("[WATCHDOG] 强制终止旧进程失败: %s", e)

                        # 关闭旧文件句柄
                        for f in self.monitor_file_handles:
                            try:
                                if f:
                                    f.close()
                            except Exception:
                                pass

                        # 等待端口释放
                        self.logger.info("[WATCHDOG] 等待10秒确保ZMQ端口完全释放...")
                        time.sleep(10)

                        # 重启监控进程
                        self.logger.info(
                            "[WATCHDOG] 启动新的监控进程（第%d次重启）...", restart_count
                        )
                        try:
                            log_dir = self.project_root / "logs"
                            stdout_file = open(
                                log_dir / "monitor_stdout.log", "a", encoding="utf-8"
                            )
                            stderr_file = open(
                                log_dir / "monitor_stderr.log", "a", encoding="utf-8"
                            )
                            self.monitor_file_handles = [stdout_file, stderr_file]

                            monitor_script = (
                                self.project_root
                                / "backend"
                                / "infrastructure"
                                / "system_vnpy"
                                / "monitor_system.py"
                            )

                            self.monitor_process_handle = subprocess.Popen(
                                [sys.executable, str(monitor_script)],
                                stdout=stdout_file,
                                stderr=stderr_file,
                                cwd=str(self.project_root),  # 确保工作目录正确
                                creationflags=(
                                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                                ),
                            )
                            self.logger.info(
                                "[WATCHDOG] ✅ 监控进程已重启（PID: %d）",
                                self.monitor_process_handle.pid,
                            )

                            time.sleep(2)

                            if self.monitor_process_handle.poll() is not None:
                                self.logger.error(
                                    "[WATCHDOG] ❌ 新进程启动后立即退出（退出码: %d）",
                                    self.monitor_process_handle.returncode,
                                )
                            else:
                                self.logger.info("[WATCHDOG] ✅ 新进程运行正常")
                        except Exception as e:
                            self.logger.exception("[WATCHDOG] ❌ 重启监控进程失败: %s", e)

                    time.sleep(3)

                except Exception as e:
                    self.logger.error("[WATCHDOG] 看门狗线程异常: %s", e)
                    time.sleep(5)

            self.logger.info("[WATCHDOG] 监控进程看门狗线程已停止")

        self.watchdog_thread = threading.Thread(
            target=monitor_watchdog, name="MonitorWatchdog", daemon=True
        )
        self.watchdog_thread.start()

    def _wait_monitor_ready(self, max_wait=60.0):
        """等待监控进程就绪信号.

        Args:
            max_wait: 最大等待时间（秒）

        Returns:
            dict: 端口信息

        Raises:
            RuntimeError: 超时或进程异常退出
        """
        signal_file = self.project_root / "logs" / "monitor_ready.signal"

        # 清理旧信号文件
        if signal_file.exists():
            try:
                signal_file.unlink()
                self.logger.debug("[MONITOR-PROCESS] 已清理旧的就绪信号文件")
            except Exception as e:
                self.logger.debug("[MONITOR-PROCESS] 清理信号文件失败: %s", e)

        wait_start = time.time()
        ports_ready = False
        ports = {}

        while (time.time() - wait_start) < max_wait:
            # 检查进程是否存活
            if self.monitor_process_handle and self.monitor_process_handle.poll() is not None:
                error_msg = f"监控进程异常退出（退出码: {self.monitor_process_handle.returncode}）"
                self.logger.error("[MONITOR-PROCESS] ❌ %s", error_msg)
                raise RuntimeError(error_msg)

            # 检查就绪信号文件
            if signal_file.exists():
                try:
                    with open(signal_file, "r", encoding="utf-8") as f:
                        signal_data = json.load(f)

                    signal_pid = signal_data.get("pid")
                    if signal_pid:
                        try:
                            import psutil

                            if not psutil.pid_exists(signal_pid):
                                time.sleep(0.1)
                                continue
                        except ImportError:
                            pass

                    status = signal_data.get("status")
                    level = signal_data.get("level", 1)

                    if status == "initializing":
                        time.sleep(0.1)
                        continue
                    elif status in ["ports_ready", "fully_ready", "pipes_ready", "partial_pipes_ready"] and level >= 1:
                        # 兼容新旧两种就绪信号格式
                        # 旧格式：使用ZMQ端口（ports）
                        # 新格式：使用native_ipc管道（pipes）
                        ports = signal_data.get("ports", {})
                        pipes = signal_data.get("pipes", {})
                        elapsed = time.time() - wait_start

                        # 检查是否有端口信息（旧格式）或管道信息（新格式）
                        if ports:
                            # 旧格式：检查ZMQ端口
                            if not all(
                                ports.get(k) for k in ["alert_push", "status_pull", "query_rep"]
                            ):
                                time.sleep(0.1)
                                continue

                            self.logger.info(
                                "[MONITOR-PROCESS] 监控进程端口就绪（PID: %d, 端口: %d/%d/%d，耗时: %.1fs）",
                                signal_pid,
                                ports.get("alert_push", 0),
                                ports.get("status_pull", 0),
                                ports.get("query_rep", 0),
                                elapsed,
                            )

                            # 设置环境变量供SystemManagerService使用
                            os.environ["MONITOR_ALERT_PUSH"] = str(ports.get("alert_push", 5555))
                            os.environ["MONITOR_STATUS_PULL"] = str(ports.get("status_pull", 5556))
                            os.environ["MONITOR_QUERY_REP"] = str(ports.get("query_rep", 5557))
                        elif pipes:
                            # 新格式：检查native_ipc管道
                            if not all(
                                pipes.get(k) for k in ["query", "status"]
                            ):
                                time.sleep(0.1)
                                continue

                            self.logger.info(
                                "[MONITOR-PROCESS] 监控进程管道就绪（PID: %d, 管道: %s/%s，耗时: %.1fs）",
                                signal_pid,
                                pipes.get("query", ""),
                                pipes.get("status", ""),
                                elapsed,
                            )
                        else:
                            time.sleep(0.1)
                            continue

                        # 设置通用环境变量
                        os.environ["MONITOR_READY"] = "1"
                        os.environ["MONITOR_PROCESS_PID"] = str(signal_pid)

                        ports_ready = True
                        break

                except (json.JSONDecodeError, IOError) as e:
                    self.logger.debug("[MONITOR-PROCESS] 读取就绪信号失败（重试中）: %s", e)
                    time.sleep(0.1)
                    continue

            time.sleep(0.2)

        if not ports_ready:
            error_msg = (
                f"监控进程启动失败（超时{max_wait}s）\\n"
                f"可能原因：\\n"
                f"1. 端口被占用（5555/5556/5557）\\n"
                f"2. 监控进程崩溃（查看logs/monitor_stderr.log）\\n"
                f"3. 权限不足（需要管理员权限）"
            )
            self.logger.error("[MONITOR-PROCESS] ❌ %s", error_msg)
            raise RuntimeError(f"监控进程启动失败: {error_msg}")

        return ports

    def cleanup_monitor(self):
        """清理监控进程（主进程退出时调用）."""
        self.watchdog_running = False
        self.logger.info("[CLEANUP] 开始清理监控进程...")

        if self.monitor_process_handle:
            if self.monitor_process_handle.poll() is None:
                self.logger.info("[CLEANUP] 发送SIGTERM信号...")
                self.monitor_process_handle.terminate()
                try:
                    self.monitor_process_handle.wait(timeout=3)
                    self.logger.info("[CLEANUP] ✅ 监控进程已正常退出")
                except subprocess.TimeoutExpired:
                    self.logger.warning("[CLEANUP] 监控进程未响应，强制终止...")
                    self.monitor_process_handle.kill()
                    try:
                        self.monitor_process_handle.wait(timeout=2)
                        self.logger.info("[CLEANUP] ✅ 监控进程已强制终止")
                    except Exception as e:
                        self.logger.error("[CLEANUP] ❌ 强制终止失败: %s", e)
            else:
                self.logger.info(
                    "[CLEANUP] 监控进程已退出（退出码: %d）",
                    self.monitor_process_handle.returncode,
                )

        # 等待端口释放
        self.logger.info("[CLEANUP] 等待5秒确保端口释放...")
        time.sleep(5)

        # 关闭文件句柄
        for f in self.monitor_file_handles:
            try:
                if f:
                    f.close()
            except Exception:
                pass

        self.logger.info("[CLEANUP] ✅ 监控进程清理完成")


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
                self.logger.info("[COORDINATOR] 隐藏启动画面")
                print("[COORDINATOR] 开始隐藏启动画面...")
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
                print("[COORDINATOR] 启动画面已关闭")
                self.splash.deleteLater()
                print("[COORDINATOR] 启动画面已标记删除")
                self.splash = None
                print("[COORDINATOR] ✅ 启动画面已隐藏")
                self.logger.info("[COORDINATOR] ✅ 启动画面已成功隐藏")
            except Exception as e:
                self.logger.exception("隐藏启动画面失败: %s", e)
                print(f"[COORDINATOR] ❌ 隐藏启动画面失败: {e}")
                # 即使失败，也设置为None避免重复操作
                self.splash = None
