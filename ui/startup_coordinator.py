# -*- coding: utf-8 -*-
"""启动协调器 - 管理应用启动顺序."""

import logging
import os
import threading
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import QSplashScreen, QApplication


class BackendInitializerWorker(QObject):
    """后端初始化工作线程."""

    # 信号定义
    progress_updated = Signal(str, int)  # (消息, 进度百分比)
    initialization_completed = Signal(bool, dict)  # (成功, 结果)
    error_occurred = Signal(str)  # 错误消息

    def __init__(self):
        """初始化后端初始化工作线程."""
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self):
        """运行后端初始化."""
        try:
            self.logger.info("=" * 70)
            self.logger.info("🔧 后端初始化工作线程启动")
            self.logger.info("=" * 70)
            self.logger.info("线程ID: %s", threading.current_thread().ident)
            self.logger.info("线程名: %s", threading.current_thread().name)
            self.logger.info(
                "当前线程是否为主线程: %s", threading.current_thread() == threading.main_thread()
            )
            
            # 🔧 检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("收到中断请求，停止初始化")
                return
                
            self.progress_updated.emit("正在初始化配置...", 10)

            # 导入后端模块
            self.logger.info("步骤1: 导入后端服务模块...")
            from backend.core.base import initialize_services

            self.logger.info("✅ 后端模块导入成功")
            
            # 再次检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("收到中断请求，停止初始化")
                return

            self.progress_updated.emit("正在启动后端服务...", 30)

            # 执行初始化
            self.logger.info("步骤2: 开始执行后端服务初始化...")
            self.logger.info("⚠️ 注意：此过程中不应创建任何Qt GUI对象")
            result = initialize_services()
            self.logger.info("✅ initialize_services() 执行完成")
            
            # 最后检查中断请求
            if self.thread() and self.thread().isInterruptionRequested():
                self.logger.info("收到中断请求，停止初始化")
                return

            success = result.get("success", False)

            if success:
                self.progress_updated.emit("后端服务初始化完成", 100)
                self.logger.info("=" * 70)
                self.logger.info("✅ 后端服务初始化成功")
                self.logger.info("=" * 70)
                self.initialization_completed.emit(True, result)
            else:
                error_msg = result.get("message", "未知错误")
                self.progress_updated.emit(f"初始化失败: {error_msg}", 100)
                self.logger.error("=" * 70)
                self.logger.error("❌ 后端服务初始化失败: %s", error_msg)
                self.logger.error("=" * 70)
                self.initialization_completed.emit(False, result)

        except Exception as e:
            error_msg = f"后端初始化异常: {str(e)}"
            self.logger.error("=" * 70)
            self.logger.error("💥 后端初始化工作线程发生异常")
            self.logger.error("=" * 70)
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            self.initialization_completed.emit(False, {"success": False, "message": error_msg})


class StartupCoordinator(QObject):
    """启动协调器 - 管理整个应用的启动流程."""

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

    def start(self):
        """开始启动流程."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("启动协调器：开始启动流程")
            self.logger.info("=" * 60)

            # 步骤1: 初始化配置
            self._initialize_config()

            # 步骤2: 显示启动画面
            self._show_splash_screen()

            # 步骤3: 异步初始化后端
            self._start_backend_initialization()

        except Exception as e:
            self.logger.error("启动失败: %s", e, exc_info=True)
            self.startup_failed.emit(str(e))

    def _initialize_config(self):
        """步骤1: 初始化配置（同步，必须最先完成）."""
        if self.config_already_initialized:
            self.logger.info("步骤1: 配置已在主入口初始化，跳过")

            # 验证配置
            from backend.config import get_settings

            settings = get_settings()
            if settings.ai.api_key:
                masked_key = (
                    f"{settings.ai.api_key[:4]}...{settings.ai.api_key[-4:]}"
                    if len(settings.ai.api_key) > 8
                    else "***"
                )
                self.logger.info("验证配置：API Key: %s", masked_key)
            return

        self.logger.info("步骤1: 初始化配置...")

        from backend.config import init_settings, get_settings

        config_file = os.getenv("CONFIG_FILE")
        if config_file:
            self.logger.info("从环境变量加载配置: %s", config_file)
            init_settings(config_file)
        else:
            self.logger.info("使用默认配置文件")
            init_settings()

        # 验证配置
        settings = get_settings()
        if settings.ai.api_key:
            masked_key = (
                f"{settings.ai.api_key[:4]}...{settings.ai.api_key[-4:]}"
                if len(settings.ai.api_key) > 8
                else "***"
            )
            self.logger.info("配置已加载，API Key: %s", masked_key)
        else:
            self.logger.info("配置已加载，但API Key未设置")

        self.logger.info("✅ 配置初始化完成")

    def _show_splash_screen(self):
        """步骤2: 显示启动画面."""
        self.logger.info("步骤2: 显示启动画面...")

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

        self.logger.info("✅ 启动画面已显示")

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
        self.logger.info("步骤3: 启动后端服务初始化（异步）...")

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

        # 🔧 按照记忆中的QThread安全终止实践，使用安全的清理机制
        self.backend_worker.initialization_completed.connect(self._safe_cleanup_thread)
        
        # 启动线程
        self.backend_thread.start()

        self.logger.info("✅ 后端初始化线程已启动")

    def _safe_cleanup_thread(self):
        """安全清理QThread资源."""
        if self.backend_thread and self.backend_thread.isRunning():
            self.logger.info("开始安全清理后端线程...")
            
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
                self.backend_thread.finished.connect(lambda: (
                    self.backend_worker.deleteLater() if self.backend_worker else None,
                    self.backend_thread.deleteLater() if self.backend_thread else None
                ))
                
                self.logger.info("✅ 后端线程清理完成")
        except Exception as e:
            self.logger.error("线程清理异常: %s", e)

    def _on_backend_progress(self, message: str, progress: int):
        """后端初始化进度更新."""
        self.logger.info("后端初始化进度 [%d%%]: %s", progress, message)
        self.show_message(message, progress)

    def _on_backend_completed(self, success: bool, result: dict):
        """后端初始化完成."""
        self.backend_initialized = success
        self.backend_result = result

        if success:
            self.logger.info("✅ 后端服务初始化成功，准备启动UI")
            self.show_message("后端服务就绪，正在启动界面...", 100)

            # 延迟一下让用户看到消息
            from PySide6.QtCore import QTimer

            QTimer.singleShot(500, self._complete_startup)
        else:
            error_msg = result.get("message", "后端初始化失败")
            self.logger.error("❌ 后端服务初始化失败: %s", error_msg)
            self.startup_failed.emit(error_msg)

    def _on_backend_error(self, error_msg: str):
        """后端初始化错误."""
        self.logger.error("后端初始化错误: %s", error_msg)
        self.show_message(f"错误: {error_msg}", 0)
        self.startup_failed.emit(error_msg)

    def _complete_startup(self):
        """完成启动流程."""
        self.logger.info("✅ 启动流程完成，发送 startup_completed 信号")
        self.startup_completed.emit()

    def hide_splash(self):
        """隐藏启动画面."""
        if self.splash:
            self.logger.info("隐藏启动画面")
            self.splash.close()
            self.splash.deleteLater()
            self.splash = None
