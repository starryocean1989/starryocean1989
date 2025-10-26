# -*- coding: utf-8 -*-
"""启动协调器 - 管理应用启动顺序."""

import logging
import os
import threading
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
        self.logger = logging.getLogger(self.__class__.__name__)

        # 🔧 确保日志能输出到控制台
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.DEBUG)

    def run(self):
        """运行后端初始化.

        六阶段初始化流程：
        1. VNPY核心（EventEngine, MainEngine）
        2. 数据引擎（ChinaStockEngine）
        3. 数据服务（DataCenterService）
        4. 交易服务（TradingGatewayService）
        5. 策略服务（StrategyCenterService, AIAssistantService）
        6. 辅助服务（PortfolioService, MarketBoardService, SystemManagerService）
        """
        try:
            self.logger.info("=" * 70)
            self.logger.info("[BACKEND-INIT] 🔧 后端初始化工作线程启动")
            self.logger.info("=" * 70)
            self.logger.info("[BACKEND-INIT] 线程ID: %s", threading.current_thread().ident)
            self.logger.info("[BACKEND-INIT] 线程名: %s", threading.current_thread().name)
            self.logger.info(
                "[BACKEND-INIT] 当前线程是否为主线程: %s",
                threading.current_thread() == threading.main_thread(),
            )

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

            # 🔧 配置后端日志输出到控制台
            import logging

            backend_logger = logging.getLogger("backend")
            if not backend_logger.handlers:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                console_handler.setFormatter(formatter)
                backend_logger.addHandler(console_handler)
                backend_logger.setLevel(logging.DEBUG)
                self.logger.info("[BACKEND-INIT] ✅ 后端日志配置完成（输出到控制台）")

            # 导入后端模块
            self.logger.info("[BACKEND-INIT] 阶段0: 导入后端服务模块...")
            from backend.core.base import initialize_services

            self.logger.info("[BACKEND-INIT] ✅ 后端模块导入成功")

            # 再次检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("[BACKEND-INIT] 收到中断请求，停止初始化")
                return

            self.progress_updated.emit("正在启动后端服务...", 10)

            # 执行初始化
            self.logger.info("[BACKEND-INIT] 开始执行六阶段后端服务初始化...")
            self.logger.info("[BACKEND-INIT] ⚠️ 注意：此过程中不应创建任何Qt GUI对象")

            # 创建进度回调函数
            def progress_callback(message: str, progress: int):
                """进度回调：将后端初始化进度转发到UI"""
                self.logger.info("[BACKEND-INIT] [进度 %d%%] %s", progress, message)
                self.progress_updated.emit(message, progress)

            # 执行初始化（传入回调）
            result = initialize_services(progress_callback=progress_callback)

            self.logger.info("[BACKEND-INIT] ✅ initialize_services() 执行完成")

            # 最后检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("[BACKEND-INIT] 收到中断请求，停止初始化")
                return

            success = result.get("success", False)

            if success:
                self.progress_updated.emit("后端服务初始化完成", 100)
                self.logger.info("=" * 70)
                self.logger.info("[BACKEND-INIT] ✅ 后端服务初始化成功")
                self.logger.info("=" * 70)
                self.initialization_completed.emit(True, result)
            else:
                error_msg = result.get("message", "未知错误")
                self.progress_updated.emit(f"初始化失败: {error_msg}", 100)
                self.logger.error("=" * 70)
                self.logger.error("[BACKEND-INIT] ❌ 后端服务初始化失败: %s", error_msg)
                self.logger.error("=" * 70)
                self.initialization_completed.emit(False, result)

        except Exception as e:
            error_msg = f"后端初始化异常: {str(e)}"
            self.logger.error("=" * 70)
            self.logger.error("[BACKEND-INIT] 💥 后端初始化工作线程发生异常")
            self.logger.error("=" * 70)
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            self.initialization_completed.emit(False, {"success": False, "message": error_msg})


class StartupCoordinator(QObject):
    """启动协调器 - 管理整个应用的启动流程.

    职责：
    1. 显示启动画面并更新进度
    2. 管理后台初始化线程
    3. 协调UI和后端的就绪状态
    4. 处理启动失败和错误恢复
    """

    # 信号定义
    startup_completed = Signal()  # 启动完成
    startup_failed = Signal(str)  # 启动失败

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
        self.initialization_timeout = 30  # 30秒超时

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
            self.logger.error("[COORDINATOR] 启动失败: %s", e, exc_info=True)
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
        self.logger.warning("[COORDINATOR] ⚠️ 后端初始化超时（%d秒）", self.initialization_timeout)

        # 优先尝试降级继续：如果核心服务部分就绪，则允许UI继续工作（功能受限）
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            status = service_manager.get_service_status()

            # 判定核心服务可用性（任一关键服务就绪即允许降级继续）
            core_candidates = [
                "data_center_service",
                "system_manager_service",
                "market_board_service",
            ]
            core_ready = any(name in status for name in core_candidates)

            if core_ready:
                self.logger.warning("[COORDINATOR] 启动降级：核心服务部分就绪，继续完成UI启动")
                self.show_message("后端部分就绪，已进入降级模式（功能可能受限）", 80)
                # 允许完成启动流程
                self._complete_startup()
                return
        except Exception as e:
            self.logger.error("[COORDINATOR] 降级检测异常: %s", e)

        # 无法降级继续，保持提示并发出失败信号（不强制退出，交给外部处理）
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
                self.logger.error("[COORDINATOR] 隐藏启动画面失败: %s", e, exc_info=True)
                print(f"[COORDINATOR] ❌ 隐藏启动画面失败: {e}")
                # 即使失败，也设置为None避免重复操作
                self.splash = None
