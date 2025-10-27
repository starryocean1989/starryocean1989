# -*- coding: utf-8 -*-
"""主窗口 - 星辰金融终端的主界面（重构版）."""

# 🔧 关键修复：在任何导入之前设置Python解释器环境变量
# 这样PySide6 WebEngine进程会使用正确的Python路径
import os
import sys

if not os.environ.get("PYTHONEXECUTABLE"):
    os.environ["PYTHONEXECUTABLE"] = sys.executable
if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
    os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable

from pathlib import Path

# Add project root to Python path to ensure backend module can be imported
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

# UI层专用logger
logger = logging.getLogger("ui.main_window")
logger_user = logging.getLogger("ui.user_feedback")

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.core.config import ConfigManager
from backend.core.service_base import LoggerMixin
from backend.core.base import setup_logging

from ui.components.theme_system import ThemeManager
from ui.core.boot_orchestrator import get_boot_orchestrator


class MainWindow(QMainWindow, LoggerMixin):
    """主窗口类（重构版）.

    架构设计：
    - 左侧：垂直导航列表
    - 右侧：内容显示区
    - 顶部：菜单栏
    - 底部：状态栏
    """

    interface_changed = Signal(str)

    def __init__(self, backend_ready: bool = True):
        """初始化主窗口.

        Args:
            backend_ready: 后端服务是否已就绪（True=同步模式，False=异步模式）
        """
        super().__init__()

        # 🔧 关键修复：在LoggerMixin初始化之前设置自定义logger
        # LoggerMixin使用@property返回self._logger，所以直接设置_logger即可
        self._logger = logger
        self._logger_user = logger_user

        # 现在初始化LoggerMixin（它会使用我们设置的_logger）
        LoggerMixin.__init__(self)

        self.backend_ready = backend_ready

        # 如果是同步模式（向后兼容），先初始化配置和后端
        if backend_ready:
            # 🔧 关键修复：在任何服务创建之前就初始化配置
            self._initialize_config_first()

            # 初始化后端服务
            self._initialize_backend_services()

        # 初始化组件
        try:
            self.theme_manager = ThemeManager()
            self.logger.debug("主题管理器初始化成功")
        except Exception as e:
            self.logger.exception("初始化主题管理器失败: %s", e)
            self.theme_manager = None
            # 向用户显示友好错误
            QMessageBox.warning(self, "初始化警告", "主题管理器初始化失败，将使用默认主题")

        try:
            self.config_manager = ConfigManager()
            self.logger.debug("配置管理器初始化成功")
        except Exception as e:
            self.logger.exception("初始化配置管理器失败: %s", e)
            # 先设置为 None，后面会处理
            self.config_manager = None

        # 界面组件
        self.central_widget: Optional[QWidget] = None
        self.nav_list: Optional[QListWidget] = None
        self.content_stack: Optional[QStackedWidget] = None
        self.status_label: Optional[QLabel] = None
        self.system_info_label: Optional[QLabel] = None

        # 功能界面实例
        self.function_interfaces: Dict[str, Any] = {}
        # 按需加载器：记录需要延迟创建的界面
        self.lazy_loaders: Dict[str, Any] = {}
        # 🔧 调整顺序：系统管理提到第一位
        self.interface_order = ["system", "data", "market", "strategy", "trading", "portfolio"]

        # 界面元数据
        self.interface_metadata = {
            "system": {"icon": "🛠️", "name": "系统管理", "description": "系统监控与运维管理"},
            "data": {"icon": "🗃️", "name": "数据中心", "description": "数据管理解决方案"},
            "market": {"icon": "📈", "name": "行情看板", "description": "专业行情分析工具"},
            "strategy": {"icon": "🧠", "name": "策略中心", "description": "策略开发和回测环境"},
            "trading": {"icon": "🔗", "name": "交易网关", "description": "多网关交易执行"},
            "portfolio": {"icon": "📊", "name": "组合投资", "description": "投资组合管理和监控"},
        }

        # 动态导入映射：按需加载时根据ID导入对应类（扁平化后的新路径）
        self.interface_imports = {
            "data": ("ui.modules.data_center_view", "DataCenter"),
            "market": ("ui.modules.market_board_view", "MarketDashboard"),
            "strategy": ("ui.modules.strategy_center_view", "StrategyCenter"),
            "trading": ("ui.modules.trading_gateway_view", "TradingGateway"),
            "portfolio": ("ui.modules.portfolio_view", "PortfolioInvestment"),
            "system": ("ui.modules.system_manager_view", "SystemManager"),
        }

        # 更新定时器
        self.update_timer: Optional[QTimer] = None
        self.responsive_helper: Optional[ResponsiveHelper] = None
        # 启动就绪编排器
        self.boot_orchestrator = get_boot_orchestrator()

        # ✅ 严格串行化：就绪标志
        self._interfaces_created = False
        self._interfaces_loaded = False
        self._is_loading_interface = False  # 防止并发加载

        # 初始化UI框架
        self._init_responsive_helper()
        self.setup_ui()
        self.setup_menu_bar()
        self.setup_status_bar()

        # 如果后端已就绪，立即创建功能界面
        if self.backend_ready:
            self.create_function_interfaces()

            # 应用主题
            self.apply_theme()

            # 连接信号
            self.connect_signals()

            # 完成同步初始化的剩余部分
            self._complete_sync_init()
        else:
            # 完成异步初始化
            self._complete_async_init()

    @property
    def logger_user(self) -> logging.Logger:
        """获取用户反馈日志记录器.

        Returns:
            logging.Logger: 用户反馈日志记录器实例
        """
        return self._logger_user

    def _complete_sync_init(self):
        """完成同步模式的初始化（原__init__的后续代码）."""
        # 启动更新定时器
        self.start_update_timer()

        # 标记就绪阶段（同步模式）
        try:
            if getattr(self, "boot_orchestrator", None):
                self.boot_orchestrator.mark_ready("backend_ready")
                self.boot_orchestrator.mark_ready("ui_ready")
        except Exception:
            pass
        self.logger.info("主窗口初始化完成（同步模式）")

    def _complete_async_init(self):
        """完成异步模式的初始化."""
        # 异步模式：功能界面稍后创建
        self.apply_theme()
        self.logger.info("主窗口框架初始化完成（异步模式，等待后端就绪）")

    def show(self):
        """重写show方法以确保窗口正确显示."""
        super().show()
        # 强制窗口显示并置顶
        self.raise_()
        self.activateWindow()
        # 确保窗口不是最小化状态
        if self.isMinimized():
            self.showNormal()
        self.logger.info("主窗口已显示")
        # 标记 UI 可见
        try:
            if getattr(self, "boot_orchestrator", None):
                self.boot_orchestrator.mark_ready("ui_visible")
        except Exception:
            pass

    def _initialize_config_first(self):
        """在所有服务创建之前初始化配置.

        这个方法必须在任何后端服务或UI组件创建之前调用，
        确保所有服务都使用正确的配置文件。
        """
        try:
            import os
            from backend.core.config import init_settings, get_settings

            # 使用专用logger记录启动流程
            logger.info("开始初始化配置模块")

            # 从环境变量获取配置文件路径
            config_file = os.getenv("CONFIG_FILE")

            if config_file:
                logger.info("从环境变量加载配置文件: %s", config_file)
                init_settings(config_file)
            else:
                logger.info("使用默认配置文件")
                init_settings()

            # 验证配置已加载
            settings = get_settings()
            if settings.ai.api_key:
                masked_key = (
                    "%s...%s" % (settings.ai.api_key[:4], settings.ai.api_key[-4:])
                    if len(settings.ai.api_key) > 8
                    else "***"
                )
                logger.info("配置加载完成: API Key=%s", masked_key)
            else:
                logger.warning("配置加载完成，但API Key未设置")

        except Exception as e:
            logger.exception("配置初始化失败: %s", e)

    def initialize_function_interfaces_after_backend(self):
        """在后端就绪后初始化功能界面（异步模式）."""
        try:
            # 升级状态栏（如果尚未升级）
            if not hasattr(self, "enhanced_statusbar") or self.enhanced_statusbar is None:
                try:
                    from backend.core.base import get_event_engine
                    from ui.components.enhanced_statusbar import EnhancedStatusBar

                    event_engine = get_event_engine()
                    if event_engine:
                        # 移除占位状态栏
                        if hasattr(self, "status_label") and self.status_label:
                            self.status_bar.removeWidget(self.status_label)
                        if hasattr(self, "alert_ticker") and self.alert_ticker:
                            self.status_bar.removeWidget(self.alert_ticker)
                        if hasattr(self, "system_info_label") and self.system_info_label:
                            self.status_bar.removeWidget(self.system_info_label)

                        # 创建增强状态栏
                        self.enhanced_statusbar = EnhancedStatusBar(event_engine)
                        self.status_bar.addWidget(self.enhanced_statusbar, 1)

                        # 保留兼容性引用
                        self.status_label = self.enhanced_statusbar.status_label
                        self.system_info_label = self.enhanced_statusbar.resource_label

                        self.logger.info("✅ 状态栏已升级为增强模式")
                except Exception as e:
                    self.logger.warning("状态栏升级失败: %s", e)

            self.logger.info("=" * 70)
            self.logger.info("🎨 开始创建UI功能界面（主线程）")
            self.logger.info("=" * 70)

            import threading

            self.logger.info("当前线程ID: %s", threading.current_thread().ident)
            self.logger.info("当前线程名: %s", threading.current_thread().name)
            self.logger.info(
                "是否为主线程: %s", threading.current_thread() == threading.main_thread()
            )

            # 🆕 连接后台初始化进度信号
            self.logger.info("步骤0: 连接后台进度信号...")
            try:
                self._connect_backend_progress_signals()
                self.logger.info("✅ 后台进度信号连接完成")
            except Exception as e:
                self.logger.error("❌ 后台进度信号连接失败: %s", e, exc_info=True)

            # 创建功能界面
            self.logger.info("步骤1: 创建6个功能界面...")
            try:
                self.create_function_interfaces()
                self.logger.info("✅ 功能界面创建完成")
            except Exception as e:
                self.logger.error("❌ 功能界面创建失败: %s", e, exc_info=True)
                # 不抛出异常，让应用继续运行（即使部分功能不可用）

            # 步骤2: 连接信号槽
            self.logger.info("步骤2: 连接信号槽...")
            try:
                self.connect_signals()
                self.logger.info("✅ 信号槽连接完成")
            except Exception as e:
                self.logger.error("❌ 信号槽连接失败: %s", e, exc_info=True)
                # 信号连接失败不致命，继续执行

            # 步骤3: 启动更新定时器
            self.logger.info("步骤3: 启动更新定时器...")
            try:
                self.start_update_timer()
                self.logger.info("✅ 更新定时器启动完成")
            except Exception as e:
                self.logger.error("❌ 更新定时器启动失败: %s", e, exc_info=True)
                # 定时器失败不致命，继续执行

            # 步骤4: 逐个触发按需加载
            self.logger.info("步骤4: 逐个触发按需加载...")
            try:
                self._trigger_lazy_loads_sequentially()
                self.logger.info("✅ 按需加载完成")
            except Exception as e:
                self.logger.error("❌ 按需加载失败: %s", e, exc_info=True)

            # 步骤5: 设置默认选中界面
            self.logger.info("步骤5: 设置默认选中界面...")
            try:
                if self.nav_list and self.nav_list.count() > 0:
                    self.nav_list.setCurrentRow(0)
                    self.logger.info("✅ 默认界面设置完成")
            except Exception as e:
                self.logger.error("❌ 设置默认界面失败: %s", e, exc_info=True)

            self.logger.info("=" * 70)
            self.logger.info("✅ UI功能界面初始化完成")
            # 🔧 修复：不在这里触发backend_ready，而是在后端真正就绪时触发
            # backend_ready应该由start_async_fixed.py在收到initialization_completed信号后触发
            try:
                if getattr(self, "boot_orchestrator", None):
                    # 只标记ui_ready，backend_ready由后端初始化完成时触发
                    self.boot_orchestrator.mark_ready("ui_ready")
            except Exception:
                pass
            self.logger.info("=" * 70)

        except Exception as e:
            self.logger.error("=" * 70)
            self.logger.error("💥 UI功能界面初始化发生严重异常")
            self.logger.error("=" * 70)
            self.logger.error("异常信息: %s", e, exc_info=True)
            # 不再重新抛出异常，避免应用崩溃

            # 显示错误信息给用户
            try:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,
                    "初始化警告",
                    f"功能界面初始化时遇到问题：\n\n{str(e)}\n\n但UI框架仍可使用。",
                )
            except Exception:
                pass

    def _initialize_backend_services(self):
        """初始化后端服务."""
        try:
            from backend.core.base import initialize_services

            logger.info("开始初始化后端服务")
            init_result = initialize_services()
            success = init_result.get("success", False)
            if success:
                logger.info("后端服务初始化完成")
            else:
                logger.warning("后端服务初始化失败")
                error_report = init_result.get("user_friendly_report", "")
                if error_report:
                    logger.warning("错误详情: %s", error_report)

        except Exception as e:
            logger.exception("后端服务初始化异常: %s", e)

    def _connect_backend_progress_signals(self):
        """连接后台初始化进度信号."""
        try:
            from backend.core.base import get_china_stock_engine

            # 获取data_module_vnpy引擎
            engine = get_china_stock_engine()
            if engine and hasattr(engine, "progress_emitter"):
                # 连接进度信号到UI更新槽
                engine.progress_emitter.progress_updated.connect(
                    self._update_cache_validation_progress
                )
                self.logger.info("✓ 已连接后台进度信号")
            else:
                self.logger.warning("⚠️ 后端引擎或进度发射器不可用")

        except Exception as e:
            self.logger.error("连接后台进度信号失败: %s", e, exc_info=True)

    def _update_cache_validation_progress(self, stage: str, percent: int):
        """更新缓存验证进度（在状态栏显示）.

        Args:
            stage: 当前阶段描述
            percent: 进度百分比 (0-100)
        """
        try:
            if self.status_label:
                self.status_label.setText(f"后台初始化: {stage} ({percent}%)")

            # 当进度达到100%时，显示"系统就绪"
            if percent >= 100:
                QTimer.singleShot(2000, self._set_status_ready)

        except Exception as e:
            self.logger.error("更新进度显示失败: %s", e)

    def _set_status_ready(self):
        """设置状态栏为"系统就绪"."""
        if self.status_label:
            self.status_label.setText("系统就绪")

    def setup_ui(self):
        """设置主界面."""
        # 设置窗口基本属性
        if self.config_manager:
            app_name = self.config_manager.app_config.name
            app_version = self.config_manager.app_config.version
            title = f"{app_name} v{app_version}"
            self.setWindowTitle(title)
            self.setMinimumSize(
                self.config_manager.ui_config.min_width,
                self.config_manager.ui_config.min_height,
            )
            self.resize(
                self.config_manager.ui_config.window_width,
                self.config_manager.ui_config.window_height,
            )
        else:
            # 使用默认值
            self.setWindowTitle("星辰金融终端 v5.0.0")
            self.setMinimumSize(1024, 768)
            self.resize(1400, 900)

        # 创建中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 创建主布局
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建水平分割器：左侧导航 + 右侧内容区
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)  # 不允许折叠

        # 左侧：导航列表
        self.nav_list = self._create_navigation_list()
        main_splitter.addWidget(self.nav_list)

        # 右侧：内容显示区
        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_stack.setStyleSheet(
            """
            QStackedWidget {
                background-color: #1e1e1e;
                border-left: 1px solid #404040;
            }
            """
        )
        main_splitter.addWidget(self.content_stack)

        # 设置分割比例：左侧固定宽度，右侧自适应
        main_splitter.setStretchFactor(0, 0)  # 左侧不拉伸
        main_splitter.setStretchFactor(1, 1)  # 右侧拉伸
        main_splitter.setSizes([200, 1000])  # 初始大小

        main_layout.addWidget(main_splitter)

    def _create_navigation_list(self) -> QListWidget:
        """创建左侧导航列表."""
        nav_list = QListWidget()
        nav_list.setMaximumWidth(220)
        nav_list.setMinimumWidth(180)

        # 设置导航列表样式
        nav_list.setStyleSheet(
            """
            QListWidget {
                background-color: #2d2d2d;
                border: none;
                outline: none;
                padding: 5px;
            }
            QListWidget::item {
                color: #ffffff;
                padding: 15px 10px;
                margin: 2px 0px;
                border: 1px solid transparent;
                border-radius: 6px;
                font-size: 13px;
            }
            QListWidget::item:hover {
                background-color: #383838;
                border: 1px solid #505050;
            }
            QListWidget::item:selected {
                background-color: #1e88e5;
                border: 1px solid #42a5f5;
                font-weight: bold;
            }
            """
        )

        # 设置字体
        font = QFont()
        font.setPointSize(11)
        nav_list.setFont(font)

        return nav_list

    def setup_menu_bar(self):
        """设置菜单栏."""
        self.menu_bar = self.menuBar()

        # 文件菜单
        file_menu = self.menu_bar.addMenu("文件(&F)")

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 视图菜单
        view_menu = self.menu_bar.addMenu("视图(&V)")

        refresh_action = QAction("刷新(&R)", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_all_interfaces)
        view_menu.addAction(refresh_action)

        # 主题切换
        theme_menu = view_menu.addMenu("主题(&T)")

        dark_theme_action = QAction("暗黑主题", self)
        dark_theme_action.setCheckable(True)
        is_dark = True  # 默认为暗黑主题
        if self.config_manager:
            is_dark = self.config_manager.ui_config.theme == "dark"
        dark_theme_action.setChecked(is_dark)
        dark_theme_action.triggered.connect(lambda: self.switch_theme("dark"))
        theme_menu.addAction(dark_theme_action)

        light_theme_action = QAction("明亮主题", self)
        light_theme_action.setCheckable(True)
        light_theme_action.setChecked(not is_dark)
        light_theme_action.triggered.connect(lambda: self.switch_theme("light"))
        theme_menu.addAction(light_theme_action)

        # 帮助菜单
        help_menu = self.menu_bar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_status_bar(self):
        """设置状态栏（使用增强版）."""
        self.status_bar = self.statusBar()

        # 检查backend是否就绪
        if not self.backend_ready:
            # 后端未就绪，创建占位状态栏
            self.logger.info("后端未就绪，使用占位状态栏（将在backend就绪后升级）")
            self._setup_fallback_status_bar()
            return

        try:
            # 🆕 使用增强状态栏
            from ui.components.enhanced_statusbar import EnhancedStatusBar
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if event_engine:
                self.enhanced_statusbar = EnhancedStatusBar(event_engine)
                self.status_bar.addWidget(self.enhanced_statusbar, 1)
                self.logger.info("✅ 增强状态栏已加载")

                # 保留兼容性引用（供现有代码使用）
                self.status_label = self.enhanced_statusbar.status_label
                self.system_info_label = self.enhanced_statusbar.resource_label
            else:
                # 降级：使用传统状态栏
                self._setup_fallback_status_bar()
                self.logger.warning("⚠️ EventEngine不可用，使用传统状态栏")
        except Exception as e:
            # 降级：使用传统状态栏
            self.logger.error("增强状态栏加载失败: %s，使用传统状态栏", e)
            self._setup_fallback_status_bar()

    def _setup_fallback_status_bar(self):
        """设置传统状态栏（降级方案）."""
        # 左侧状态信息
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label, 1)

        # 中间告警滚动条
        self.alert_ticker = AlertTicker()
        self.alert_ticker.clicked.connect(self._on_alert_ticker_clicked)
        self.status_bar.addWidget(self.alert_ticker, 2)  # 伸展因子2，更大空间

        # 右侧系统信息
        self.system_info_label = QLabel("系统正常")
        self.status_bar.addPermanentWidget(self.system_info_label)

    def _on_alert_ticker_clicked(self):
        """处理告警滚动条点击事件."""
        # 切换到系统管理界面的告警管理标签页
        system_manager = self.function_interfaces.get("system")
        if system_manager and hasattr(system_manager, "tab_widget"):
            # 找到告警管理标签页的索引
            for i in range(system_manager.tab_widget.count()):
                tab_text = system_manager.tab_widget.tabText(i)
                if "告警管理" in tab_text:
                    system_manager.tab_widget.setCurrentIndex(i)
                    break

    def create_function_interfaces(self):
        """创建6个功能界面."""
        # ✅ 使用 interface_order 定义界面创建顺序（使用延迟加载，interface_class=None）
        interfaces = [(interface_id, None) for interface_id in self.interface_order]

        self.logger.info("准备创建%d个功能界面", len(interfaces))
        print("[SERIAL] 准备创建6个界面（严格串行模式）")

        # ✅ 严格串行化：阻塞所有可能触发事件的组件
        blocked_widgets = []
        if self.nav_list:
            self.nav_list.blockSignals(True)
            blocked_widgets.append(("nav_list", self.nav_list))
        if self.content_stack:
            self.content_stack.blockSignals(True)
            blocked_widgets.append(("content_stack", self.content_stack))

        # ✅ 阻塞主窗口本身的信号
        self.blockSignals(True)
        blocked_widgets.append(("MainWindow", self))

        self.logger.info("✅ 已阻塞 %d 个组件的信号，确保100%%串行创建", len(blocked_widgets))
        print(f"[SERIAL] 已阻塞 {len(blocked_widgets)} 个组件的信号")

        # ✅ 强制刷新所有挂起的Qt事件（清空队列）
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        print("[SERIAL] 已清空Qt事件队列")

        for idx, (interface_id, interface_class) in enumerate(interfaces, 1):
            self.logger.info("-" * 70)
            self.logger.info(
                "创建界面 %d/%d: %s (%s)",
                idx,
                len(interfaces),
                interface_id,
                (interface_class.__name__ if interface_class else "Lazy(SystemManager)"),
            )
            self.logger.info("-" * 70)
            print(
                f"[UI-CREATE] 正在创建界面 {idx}/{len(interfaces)}: {interface_id} ({interface_class.__name__ if interface_class else 'Lazy'})"
            )

            try:
                self._create_interface(interface_id, interface_class)
                self.logger.info("✅ 界面 %s 创建完成", interface_id)
                print(f"[UI-CREATE] ✅ 界面 {interface_id} 创建成功")
            except Exception as e:
                self.logger.error("❌ 界面 %s 创建失败: %s", interface_id, e, exc_info=True)
                print(f"[UI-CREATE] ❌ 界面 {interface_id} 创建失败: {e}")
                # 继续创建下一个界面，不中断整个流程

        print("[SERIAL] 所有6个界面占位符创建完成")
        self.logger.info("=" * 70)
        self.logger.info("✅ 所有功能界面创建完成")
        self.logger.info("=" * 70)

        # ✅ 恢复所有组件的信号（创建完成）
        if self.nav_list:
            self.nav_list.blockSignals(False)
        if self.content_stack:
            self.content_stack.blockSignals(False)
        self.blockSignals(False)
        self.logger.info("✅ 已恢复所有组件信号")
        print("[SERIAL] 已恢复所有组件信号，准备进入下一阶段")

        # ✅ 标记占位符创建完成
        self._interfaces_created = True
        self.logger.info("✅ 界面创建阶段完成，等待后端就绪后触发加载")

    def _create_interface(self, interface_id: str, interface_class: type | None):
        """创建单个功能界面.

        Args:
            interface_id: 界面ID
            interface_class: 界面类
        """
        metadata = self.interface_metadata.get(interface_id, {})
        interface_name = metadata.get("name", interface_id)

        try:
            # 创建界面实例
            self.logger.info("  → 步骤1: 实例化 %s 类...", interface_name)
            # 注意：BaseWidget会在__init__中自动调用setup_ui()和connect_signals()
            # 所以这里不需要再次调用
            try:
                # 统一按需加载：先创建占位，不立即实例化真实界面
                placeholder = QWidget()
                ph_layout = QVBoxLayout(placeholder)
                ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label = QLabel(f"{interface_name} 按需加载中…就绪后将自动初始化")
                label.setStyleSheet("color: #aaa; font-size: 12px;")
                ph_layout.addWidget(label)

                interface = placeholder
                # ✅ 登记延迟加载器（使用偏函数避免lambda闭包问题）
                from functools import partial

                self.lazy_loaders[interface_id] = partial(
                    self._instantiate_and_replace, interface_id, None
                )
                self.logger.info("  ⚠️ %s 使用占位并登记延迟加载器（偏函数）", interface_name)
            except Exception as inst_error:
                # 捕获实例化过程中的任何异常（包括访问违例）
                self.logger.error(
                    "  ❌ %s 实例化失败: %s", interface_name, inst_error, exc_info=True
                )
                raise  # 重新抛出，让外层捕获

            # 保存到字典
            self.logger.info("  → 步骤2: 保存到界面字典...")
            self.function_interfaces[interface_id] = interface
            self.logger.info("  ✅ 已保存到字典")

            # 添加到内容区
            self.logger.info("  → 步骤3: 添加到内容显示区...")
            if self.content_stack:
                self.content_stack.addWidget(interface)
                self.logger.info("  ✅ 已添加到内容区")

            # 添加到左侧导航列表
            self.logger.info("  → 步骤4: 添加到导航列表...")
            if self.nav_list:
                item_text = f"{metadata['icon']}  {interface_name}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, interface_id)
                item.setToolTip(metadata["description"])
                # ✅ 添加时确保信号被阻塞（避免触发任何回调）
                self.nav_list.addItem(item)
                self.logger.info("  ✅ 已添加到导航列表（信号已阻塞）")

            self.logger.info("✨ %s 界面创建成功", interface_name)
            # ✅ 完全移除boot_orchestrator回调机制，改为手动控制

        except Exception as e:
            self.logger.error("❌ %s 界面创建失败: %s", interface_id, e, exc_info=True)
            print(f"\n⚠️  界面 '{interface_id}' 创建失败: {e}")
            print(f"   类名: {interface_class.__name__ if interface_class else 'Lazy'}")

            # 创建错误占位符
            placeholder = self._create_error_placeholder(interface_id, str(e))

            # 添加到内容区
            if self.content_stack:
                self.content_stack.addWidget(placeholder)

            # 添加到导航列表（带错误标记）
            if self.nav_list:
                metadata = self.interface_metadata[interface_id]
                item_text = f"{metadata['icon']}  {metadata['name']} ⚠️"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, interface_id)
                item.setToolTip(f"加载失败：{str(e)}")
                self.nav_list.addItem(item)

    def _trigger_lazy_load(self, interface_id: str):
        """触发按需加载（如果尚未替换占位）."""
        try:
            loader = self.lazy_loaders.get(interface_id)
            if loader:
                loader()
                # 成功后移除加载器，避免重复加载
                self.lazy_loaders.pop(interface_id, None)
        except Exception as e:
            self.logger.error("按需加载 '%s' 失败: %s", interface_id, e, exc_info=True)

    def _trigger_lazy_loads_sequentially(self):
        """异步串行触发所有按需加载（避免阻塞UI）.

        使用QTimer异步加载，避免长时间阻塞主线程。
        """
        if self._is_loading_interface:
            self.logger.warning("⚠️ 已有界面正在加载，跳过重复触发")
            return

        if self._interfaces_loaded:
            self.logger.info("✅ 界面已全部加载，跳过")
            return

        self._is_loading_interface = True
        self.logger.info("=" * 70)
        self.logger.info("开始异步串行加载，共 %d 个界面", len(self.lazy_loaders))
        self.logger.info("=" * 70)

        # 准备加载队列
        self._load_queue = [
            interface_id
            for interface_id in self.interface_order
            if interface_id in self.lazy_loaders
        ]
        self._loaded_count = 0
        self._failed_count = 0
        self._load_index = 0

        # 启动异步加载
        self._load_next_interface()

    def _load_next_interface(self):
        """加载下一个界面（异步）"""
        if self._load_index >= len(self._load_queue):
            # 所有界面加载完成
            self._interfaces_loaded = True
            self._is_loading_interface = False

            self.logger.info("=" * 70)
            self.logger.info("✅ 所有按需加载已完成")
            self.logger.info("   - 成功: %d 个", self._loaded_count)
            self.logger.info("   - 失败: %d 个", self._failed_count)
            self.logger.info("=" * 70)
            return

        interface_id = self._load_queue[self._load_index]
        self._load_index += 1

        try:
            metadata = self.interface_metadata.get(interface_id, {})
            interface_name = metadata.get("name", interface_id)

            self.logger.info("-" * 60)
            self.logger.info(
                "[%d/%d] 正在加载: %s (%s)",
                self._load_index,
                len(self._load_queue),
                interface_name,
                interface_id,
            )
            self.logger.info("-" * 60)

            # 加载界面
            self._trigger_lazy_load(interface_id)

            self._loaded_count += 1
            self.logger.info(
                "✅ [%d/%d] %s 加载完成", self._load_index, len(self._load_queue), interface_name
            )

        except Exception as e:
            self._failed_count += 1
            self.logger.error(
                "❌ [%d/%d] %s 加载失败: %s",
                self._load_index,
                len(self._load_queue),
                interface_id,
                e,
                exc_info=True,
            )

        # 使用QTimer异步加载下一个界面，避免阻塞UI
        QTimer.singleShot(50, self._load_next_interface)

    def _instantiate_and_replace(self, interface_id: str, interface_class: type | None):
        """实例化真实界面并替换占位."""
        try:
            if not interface_class:
                # 通用动态导入：根据映射导入对应类
                from importlib import import_module

                module_path, class_name = self.interface_imports.get(interface_id, (None, None))
                if not module_path or not class_name:
                    raise RuntimeError(f"未找到界面映射: {interface_id}")
                klass = getattr(import_module(module_path), class_name)
                real = klass()
            else:
                real = interface_class()
            # 在内容栈中替换：找到占位索引并替换为真实界面
            if self.content_stack and interface_id in self.function_interfaces:
                placeholder = self.function_interfaces[interface_id]
                for i in range(self.content_stack.count()):
                    if self.content_stack.widget(i) is placeholder:
                        self.content_stack.removeWidget(placeholder)
                        placeholder.deleteLater()
                        self.content_stack.insertWidget(i, real)
                        break
            # 更新字典
            self.function_interfaces[interface_id] = real
            self.logger.info("✅ 按需加载完成并替换占位: %s", interface_id)
        except Exception as e:
            self.logger.error("实例化并替换 '%s' 失败: %s", interface_id, e, exc_info=True)
            # 替换为错误占位
            error_placeholder = self._create_error_placeholder(interface_id, str(e))
            if self.content_stack:
                self.content_stack.addWidget(error_placeholder)
            self.function_interfaces[interface_id] = error_placeholder

    def _create_error_placeholder(self, interface_id: str, error_msg: str) -> QWidget:
        """创建错误占位符.

        Args:
            interface_id: 界面ID
            error_msg: 错误消息

        Returns:
            错误占位符widget
        """
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        metadata = self.interface_metadata[interface_id]

        # 图标
        icon_label = QLabel(f"{metadata['icon']}")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon_label)

        # 标题
        title_label = QLabel(f"{metadata['name']}加载失败")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #ff6b6b; margin: 10px;"
        )
        layout.addWidget(title_label)

        # 错误信息
        error_label = QLabel(f"错误信息：{error_msg}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet("color: #999; font-size: 12px;")
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        # 建议
        hint_label = QLabel("请检查依赖或模块实现")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 10px;")
        layout.addWidget(hint_label)

        return placeholder

    def apply_theme(self):
        """应用主题."""
        try:
            app_instance = QApplication.instance()
            # 确保 app_instance 是 QApplication 类型
            if isinstance(app_instance, QApplication):
                # 🔧 增加安全性检查
                if hasattr(self, "theme_manager") and self.theme_manager:
                    self.theme_manager.apply_theme(app_instance)
                    self.logger.info("主题应用完成")
                else:
                    self.logger.warning("主题管理器不可用，跳过主题应用")
            else:
                self.logger.warning("无法获取 QApplication 实例")
        except (AttributeError, RuntimeError, ImportError) as e:
            self.logger.error("应用主题失败: %s", e)
            # 应用基本样式作为回退方案
            try:
                self._apply_fallback_style()
            except Exception as fallback_error:
                self.logger.error("应用回退样式也失败: %s", fallback_error)

    def _apply_fallback_style(self):
        """应用回退样式（当主题管理器失败时）."""
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QListWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                border: none;
            }
            QListWidget::item:selected {
                background-color: #1e88e5;
            }
        """
        )
        self.logger.info("已应用回退样式")

    def switch_theme(self, theme_name: str):
        """切换主题."""
        try:
            if self.config_manager:
                self.config_manager.ui_config.theme = theme_name
                self.config_manager.save_config()

            if self.theme_manager and hasattr(self.theme_manager, "reload_theme"):
                self.theme_manager.reload_theme()

            self.apply_theme()
            self.logger.info("切换到主题: %s", theme_name)
        except (AttributeError, RuntimeError, OSError) as e:
            self.logger.error("切换主题失败: %s", e)

    def switch_to_interface(self, interface_id: str):
        """切换到指定界面."""
        if interface_id in self.interface_order:
            index = self.interface_order.index(interface_id)
            if self.nav_list and index >= 0 and index < self.nav_list.count():
                self.nav_list.setCurrentRow(index)
                self.logger.info("切换到界面: %s", interface_id)

    def refresh_all_interfaces(self):
        """刷新所有界面."""
        try:
            for interface_id, interface in self.function_interfaces.items():
                try:
                    if hasattr(interface, "refresh_data"):
                        interface.refresh_data()
                        self.logger.info("界面 %s 刷新成功", interface_id)
                except (AttributeError, RuntimeError) as interface_error:
                    error_msg = f"界面 {interface_id} 刷新失败: {interface_error}"
                    self.logger.error(error_msg)

            if self.status_label:
                self.status_label.setText("刷新完成")
            self.logger.info("所有界面刷新完成")
        except Exception as e:
            self.logger.error("刷新界面失败: %s", e)

    def connect_signals(self):
        """连接信号槽."""
        # 连接左侧导航列表的切换信号
        if self.nav_list:
            self.nav_list.currentRowChanged.connect(self.on_nav_changed)

        # 连接功能界面的信号
        for interface in self.function_interfaces.values():
            if hasattr(interface, "error_occurred"):
                interface.error_occurred.connect(self.on_interface_error)
            if hasattr(interface, "info_message"):
                interface.info_message.connect(self.on_interface_info)

    def on_nav_changed(self, current_row: int):
        """左侧导航切换回调."""
        if current_row >= 0 and self.content_stack:
            # 切换右侧内容区
            self.content_stack.setCurrentIndex(current_row)

            # 获取界面ID
            if self.nav_list:
                item = self.nav_list.item(current_row)
                if item:
                    interface_id = item.data(Qt.ItemDataRole.UserRole)
                    metadata = self.interface_metadata.get(interface_id, {})
                    interface_name = metadata.get("name", "未知")

                    # 用户操作反馈日志
                    self.logger_user.info("用户切换界面: %s", interface_name)

                    # ✅ 禁用自动触发按需加载，避免并发
                    # 所有加载由_trigger_lazy_loads_sequentially()严格控制
                    # if interface_id in getattr(self, "lazy_loaders", {}):
                    #     self._trigger_lazy_load(interface_id)

                    # 更新状态栏（用户可见反馈）
                    if self.status_label:
                        self.status_label.setText(f"当前界面: {interface_name}")

                    # 发送界面切换信号
                    self.interface_changed.emit(interface_id)

                    self.logger.info("界面已切换: %s (%s)", interface_name, interface_id)

    def on_interface_error(self, message: str):
        """界面错误回调."""
        if self.status_label:
            self.status_label.setText("错误: " + message)
        self.logger.error("界面错误: %s", message)

    def on_interface_info(self, message: str):
        """界面信息回调."""
        if self.status_label:
            self.status_label.setText("信息: " + message)
        self.logger.info("界面信息: %s", message)

    def start_update_timer(self):
        """启动状态更新定时器."""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(5000)

    def update_status(self):
        """更新状态栏信息."""
        if not self.system_info_label:
            return

        try:
            if psutil:
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                status_text = f"CPU: {cpu_percent:.1f}% | 内存: {memory.percent:.1f}%"
                self.system_info_label.setText(status_text)
            else:
                self.system_info_label.setText("系统监控不可用")

        except Exception as e:
            self.logger.error("更新状态失败: %s", e)

    def show_about(self):
        """显示关于对话框."""
        version = "5.0.0"
        if self.config_manager:
            version = self.config_manager.app_config.version

        QMessageBox.about(
            self,
            "关于星辰金融终端",
            f"""<h3>星辰金融终端 v{version}</h3>
            <p>专业的金融交易终端系统</p>
            <p>基于 VNPY 生态系统构建</p>
            <p>提供完整的交易工具和服务</p>
            <br>
            <p><strong>6个功能界面:</strong></p>
            <ul>
                <li>🛠️ 系统管理 - 系统监控与运维管理 (8个子界面)</li>
                <li>🗃️ 数据中心 - 数据管理解决方案 (4个子界面)</li>
                <li>📈 行情看板 - 专业行情分析工具 (单一界面)</li>
                <li>🧠 策略中心 - 策略开发和回测环境 (混合架构)</li>
                <li>🔗 交易网关 - 多网关交易执行 (混合架构)</li>
                <li>📊 组合投资 - 投资组合管理和监控 (混合架构)</li>
            </ul>
            """,
        )

    def showEvent(self, event):  # pylint: disable=invalid-name
        """窗口显示事件（Qt原生事件）.

        在窗口首次显示后触发后台验证，使用Qt原生的QThread机制。

        架构说明：
        - 移除了SmartCacheValidator (threading.Thread)，避免跨线程Qt警告
        - 改用Qt原生的QThread + QObject模式，完全兼容EventEngine
        - 验证延迟到UI完全就绪后，不阻塞启动
        """
        super().showEvent(event)

        # 只在首次显示时触发
        if not hasattr(self, "_validation_triggered"):
            self._validation_triggered = True
            self.logger.info("🚀 UI已显示，准备启动后台验证...")

            # 延迟500ms后启动验证（确保UI完全就绪）
            QTimer.singleShot(500, self._start_background_validation)

    def _start_background_validation(self):
        """启动后台验证（使用Qt原生QThread）.

        使用Qt的QThread替代Python的threading.Thread，确保：
        1. 完全兼容EventEngine（基于Qt实现）
        2. 信号槽通信线程安全
        3. 不产生Qt Timer跨线程警告
        """
        try:
            # 获取ChinaStockEngine实例
            from backend.core.base import get_china_stock_engine

            engine = get_china_stock_engine()
            if not engine:
                self.logger.warning("ChinaStockEngine未就绪，跳过后台验证")
                return

            self.logger.info("创建Qt原生验证工作对象...")

            # 导入Qt原生的验证工作对象
            from PySide6.QtCore import QThread
            from backend.infrastructure.data_module_vnpy.validation_worker import (
                CacheValidationWorker,
            )

            # 创建工作对象和线程
            self._validation_worker = CacheValidationWorker(engine)
            self._validation_thread = QThread()

            # 将工作对象移到线程中（Qt的moveToThread模式）
            self._validation_worker.moveToThread(self._validation_thread)

            # 连接信号
            self._validation_thread.started.connect(self._validation_worker.run)
            self._validation_worker.finished.connect(self._validation_thread.quit)
            self._validation_worker.finished.connect(self._on_validation_finished)
            self._validation_worker.progress.connect(self._on_validation_progress)
            self._validation_worker.error.connect(self._on_validation_error)

            # 启动线程（Qt原生，EventEngine安全）
            self._validation_thread.start()
            self.logger.info("✅ 后台验证线程已启动（Qt QThread）")

        except Exception as e:
            self.logger.error("启动后台验证失败: %s", e, exc_info=True)

    def _on_validation_progress(self, message: str, progress: int):
        """验证进度回调.

        Args:
            message: 进度消息
            progress: 进度百分比 (0-100)
        """
        self.logger.debug("验证进度: %s (%d%%)", message, progress)
        # 可以在这里更新状态栏或进度条
        if self.status_label:
            self.status_label.setText(f"后台验证: {message} ({progress}%)")

    def _on_validation_finished(self, success: bool):
        """验证完成回调.

        Args:
            success: 是否成功
        """
        if success:
            self.logger.info("✅ 后台验证完成")
            if self.status_label:
                self.status_label.setText("系统就绪")
        else:
            self.logger.warning("⚠️ 后台验证失败")
            if self.status_label:
                self.status_label.setText("验证失败")

    def _on_validation_error(self, error_msg: str):
        """验证错误回调.

        Args:
            error_msg: 错误消息
        """
        self.logger.error("验证错误: %s", error_msg)

    def on_service_ready(self, service_name: str, success: bool):
        """服务就绪回调（快速启动优化）.

        当可选服务在后台加载完成后，此方法会被调用以动态启用对应的UI功能。

        Args:
            service_name: 服务名称
            success: 服务是否成功初始化
        """
        status = "成功" if success else "失败"
        icon = "✅" if success else "⚠️"
        self.logger.info("%s 服务就绪: %s (%s)", icon, service_name, status)

        # 🎯 架构修复：转发服务就绪通知到对应的UI模块
        # 服务映射关系：
        # - system_manager_service -> 系统管理tab
        # - trading_gateway_service -> 交易接口tab
        # - strategy_center_service -> 策略管理tab
        # - auxiliary_services -> 辅助功能

        # 转发到SystemManagerView
        if service_name == "system_manager_service":
            if hasattr(self, "system_manager_view") and self.system_manager_view:
                try:
                    self.system_manager_view.on_service_ready(service_name, success)
                except Exception as e:
                    self.logger.error("转发服务就绪通知到SystemManagerView失败: %s", e)

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """窗口关闭事件."""
        if self.update_timer:
            self.update_timer.stop()

        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出星辰金融终端吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backend.core.base import shutdown_services

                shutdown_services()
            except Exception as e:
                self.logger.warning("关闭后端服务失败: %s", e)

            self.logger.info("应用程序退出")
            event.accept()
        else:
            event.ignore()

    def show_error(self, message: str):
        """显示错误信息."""
        QMessageBox.critical(self, "错误", message, QMessageBox.StandardButton.Ok)

    def get_current_interface(self) -> Optional[QWidget]:
        """获取当前活动界面."""
        if self.content_stack:
            current_index = self.content_stack.currentIndex()
            if current_index >= 0:
                return self.content_stack.widget(current_index)
        return None

    def get_interface_by_id(self, interface_id: str) -> Optional[QWidget]:
        """根据ID获取界面."""
        return self.function_interfaces.get(interface_id)

    def save_window_state(self):
        """保存窗口状态."""
        try:
            if self.config_manager:
                # 保存窗口大小和位置
                self.config_manager.ui_config.window_width = self.width()
                self.config_manager.ui_config.window_height = self.height()
                self.config_manager.save_config()
                self.logger.info("窗口状态已保存")
            else:
                self.logger.warning("配置管理器不可用，无法保存窗口状态")
        except (AttributeError, OSError) as e:
            self.logger.error("保存窗口状态失败: %s", e)

    def _init_responsive_helper(self):
        """初始化响应式布局帮助器."""
        try:
            self.responsive_helper = ResponsiveHelper()
            # ResponsiveHelper 没有 size_class_changed 信号，手动处理尺寸变化
            # self.responsive_helper.size_class_changed.connect(self._on_size_class_changed)
        except ImportError:
            self.responsive_helper = None

    def _on_size_class_changed(self, size_class: str):
        """尺寸级别变化时调整布局."""
        self.logger.info("窗口尺寸级别变化: %s", size_class)

        # 根据尺寸调整导航列表宽度
        if self.nav_list:
            if size_class == "small":
                self.nav_list.setMaximumWidth(160)
                self.nav_list.setMinimumWidth(140)
            elif size_class == "medium":
                self.nav_list.setMaximumWidth(200)
                self.nav_list.setMinimumWidth(160)
            else:  # large or xlarge
                self.nav_list.setMaximumWidth(240)
                self.nav_list.setMinimumWidth(180)

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """窗口大小改变事件."""
        super().resizeEvent(event)

        # 更新响应式布局
        if self.responsive_helper:
            self.responsive_helper.update_size(event.size())

        # 保存窗口状态（延迟保存，避免频繁写入）
        QTimer.singleShot(1000, self.save_window_state)


def main():
    """主函数（使用启动协调器）."""
    try:
        # 🔧 在创建QApplication之前设置Python解释器环境变量
        # 这样PySide6 WebEngine进程会使用正确的Python路径
        import os

        if not os.environ.get("PYTHONEXECUTABLE"):
            os.environ["PYTHONEXECUTABLE"] = sys.executable
        if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
            os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable

        setup_logging(name="terminal_v0.50", level="INFO")

        # 🔧 设置Qt属性以避免QStyleHints连接问题
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        # 🔧 关键修复：在创建任何UI组件之前先初始化配置
        import os
        from backend.core.config import init_settings

        config_file = os.getenv("CONFIG_FILE")
        if config_file:
            logging.getLogger(__name__).info("主入口：从环境变量加载配置: %s", config_file)
            init_settings(config_file)
        else:
            logging.getLogger(__name__).info("主入口：使用默认配置文件")
            init_settings()

        # 创建启动协调器（告知配置已初始化）
        from ui.startup_coordinator import StartupCoordinator

        coordinator = StartupCoordinator(app, config_already_initialized=True)

        # 创建主窗口（异步模式）
        main_window = MainWindow(backend_ready=False)

        # 连接信号
        def on_startup_completed():
            """启动完成回调."""
            logging.getLogger(__name__).info("=" * 70)
            logging.getLogger(__name__).info("📡 收到启动完成信号")
            logging.getLogger(__name__).info("=" * 70)

            # 初始化功能界面
            logging.getLogger(__name__).info("步骤1: 初始化UI组件...")
            main_window.initialize_function_interfaces_after_backend()
            logging.getLogger(__name__).info("✅ UI组件初始化完成")

            # 显示主窗口
            logging.getLogger(__name__).info("步骤2: 显示主窗口...")
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()
            logging.getLogger(__name__).info("✅ 主窗口已显示")

            # 隐藏启动画面
            logging.getLogger(__name__).info("步骤3: 隐藏启动画面...")
            coordinator.hide_splash(main_window)
            logging.getLogger(__name__).info("✅ 启动画面已隐藏")

            logging.getLogger(__name__).info("=" * 70)
            logging.getLogger(__name__).info("🎉 应用启动完成！")
            logging.getLogger(__name__).info("=" * 70)

        def on_startup_failed(error: str):
            """启动失败回调."""
            logging.getLogger(__name__).error("=" * 70)
            logging.getLogger(__name__).error("💥 启动失败")
            logging.getLogger(__name__).error("=" * 70)
            logging.getLogger(__name__).error("错误信息: %s", error)
            coordinator.hide_splash()

            # 显示错误对话框
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                None, "启动失败", f"应用启动失败:\n\n{error}\n\n请查看日志文件了解详情。"
            )
            sys.exit(1)

        coordinator.startup_completed.connect(on_startup_completed)
        coordinator.startup_failed.connect(on_startup_failed)

        # 开始启动流程
        coordinator.start()

        # 运行应用
        sys.exit(app.exec())

    except Exception as e:
        logging.getLogger("terminal_v0.50.main").exception("UI启动异常: %s", e)
        sys.exit(1)


def main_sync():
    """主函数（同步模式，向后兼容）."""
    try:
        # 🔧 在创建QApplication之前设置Python解释器环境变量
        # 这样PySide6 WebEngine进程会使用正确的Python路径
        import os

        if not os.environ.get("PYTHONEXECUTABLE"):
            os.environ["PYTHONEXECUTABLE"] = sys.executable
        if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
            os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable

        setup_logging(name="terminal_v0.50", level="INFO")

        # 🔧 设置Qt属性以避免QStyleHints连接问题
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        main_window = MainWindow(backend_ready=True)
        main_window.show()

        sys.exit(app.exec())

    except Exception as e:
        logging.getLogger("terminal_v0.50.main").exception("UI启动异常: %s", e)
        sys.exit(1)


# ==================== 以下为内部组件（从 shared_widgets 合并） ====================
# 合并说明：AlertTicker, ResponsiveHelper 只被 main_window 引用，故合并到此处


class AlertTicker(QWidget):
    """告警滚动条组件."""

    # 信号定义
    clicked = Signal()  # 点击信号

    def __init__(self, parent=None):
        """初始化告警滚动条."""
        super().__init__(parent)

        # 设置固定高度和背景色
        self.setFixedHeight(30)
        self.setStyleSheet(
            """
            QWidget {
                background-color: #dc3545;
                border-radius: 5px;
                margin: 2px;
            }
        """
        )

        # 告警信息
        self.current_alert: Optional[Dict[str, Any]] = None
        self.display_text = ""

        # 动画相关
        from PySide6.QtCore import QPropertyAnimation

        self.animation: Optional[QPropertyAnimation] = None
        self.slide_timer: Optional[QTimer] = None

        # 显示控制
        self.show_duration = 5000  # 显示5秒
        self.hide_timer: Optional[QTimer] = None

        # 字体设置
        self.font: QFont = QFont("Arial", 10, QFont.Weight.Bold)

        # 隐藏初始状态
        self.hide()

    def show_alert(self, alert_data: Dict[str, Any], duration: int = 5000) -> None:
        """显示告警信息.

        Args:
            alert_data: 告警数据
            duration: 显示时长（毫秒）
        """
        self.current_alert = alert_data
        self.show_duration = duration

        # 构建显示文本
        severity = alert_data.get("severity", "info").upper()
        message = alert_data.get("message", "")
        rule_name = alert_data.get("rule_name", "")

        self.display_text = f"⚠️ [{severity}] {message} (来源: {rule_name})"

        # 调整字体大小以适应宽度
        self._adjust_font_size()

        # 显示组件
        self.show()
        self.raise_()

        # 启动隐藏定时器
        self._start_hide_timer()

        # 启动滚动动画（如果文本过长）
        if self._needs_scrolling():
            self._start_scroll_animation()
        else:
            # 重置位置
            self.updateGeometry()

    def _adjust_font_size(self) -> None:
        """调整字体大小以适应组件宽度."""
        parent = self.parent()
        parent_width = parent.width() if isinstance(parent, QWidget) and parent else 800

        # 计算可用宽度（留出边距）
        available_width = parent_width - 20

        # 尝试不同的字体大小
        for font_size in range(10, 7, -1):  # 从10到8递减
            test_font = QFont("Arial", font_size, QFont.Weight.Bold)
            font_metrics = self.fontMetrics()

            # 计算文本宽度
            text_width = font_metrics.boundingRect(self.display_text).width()

            if text_width <= available_width:
                self.font = test_font
                break

    def _needs_scrolling(self) -> bool:
        """判断是否需要滚动动画."""
        if not self.display_text:
            return False

        # 计算文本宽度
        font_metrics = self.fontMetrics()
        text_width = font_metrics.boundingRect(self.display_text).width()

        # 如果文本宽度超过组件宽度，需要滚动
        return text_width > self.width()

    def _start_scroll_animation(self) -> None:
        """启动滚动动画."""
        if self.animation:
            self.animation.stop()

        from PySide6.QtCore import QPropertyAnimation, QPoint

        # 计算滚动距离
        font_metrics = self.fontMetrics()
        text_width = font_metrics.boundingRect(self.display_text).width()
        scroll_distance = text_width - self.width() + 20  # 额外滚动一点

        if scroll_distance <= 0:
            return

        # 创建滚动动画
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(3000)  # 3秒完成一次滚动
        self.animation.setStartValue(self.pos())
        self.animation.setEndValue(self.pos() + QPoint(-scroll_distance, 0))
        self.animation.setLoopCount(-1)  # 无限循环

        self.animation.start()

    def _start_hide_timer(self) -> None:
        """启动隐藏定时器."""
        if self.hide_timer:
            self.hide_timer.stop()

        self.hide_timer = QTimer()
        self.hide_timer.timeout.connect(self.hide)
        self.hide_timer.start(self.show_duration)

    def hide(self) -> None:
        """隐藏组件."""
        super().hide()

        # 停止所有动画和定时器
        if self.animation:
            self.animation.stop()

        if self.slide_timer:
            self.slide_timer.stop()

        if self.hide_timer:
            self.hide_timer.stop()

        # 清空当前告警
        self.current_alert = None

    def mousePressEvent(self, event) -> None:
        """鼠标点击事件."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:
        """绘制事件."""
        if not self.display_text:
            return

        from PySide6.QtGui import QPainter, QColor

        painter = QPainter(self)
        painter.setFont(self.font)

        # 设置文字颜色
        painter.setPen(QColor(255, 255, 255))

        # 绘制文字
        rect = self.rect()
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.display_text)

    def resizeEvent(self, event) -> None:
        """大小改变事件."""
        super().resizeEvent(event)

        # 重新判断是否需要滚动
        if self._needs_scrolling() and self.isVisible():
            self._start_scroll_animation()
        else:
            # 停止滚动动画
            if self.animation:
                self.animation.stop()

    def get_alert_data(self) -> Optional[Dict[str, Any]]:
        """获取当前显示的告警数据.

        Returns:
            告警数据或None
        """
        return self.current_alert

    def set_display_duration(self, duration_ms: int) -> None:
        """设置显示时长.

        Args:
            duration_ms: 显示时长（毫秒）
        """
        self.show_duration = duration_ms


class ResponsiveHelper:
    """响应式布局帮助类."""

    # 断点定义（像素）
    BREAKPOINT_SMALL = 800
    BREAKPOINT_MEDIUM = 1200
    BREAKPOINT_LARGE = 1600

    def __init__(self):
        """初始化响应式帮助类."""
        self._current_size_class = "medium"

    def get_size_class(self, width: int) -> str:
        """根据宽度获取尺寸级别."""
        if width < self.BREAKPOINT_SMALL:
            return "small"
        if width < self.BREAKPOINT_MEDIUM:
            return "medium"
        if width < self.BREAKPOINT_LARGE:
            return "large"

        return "xlarge"

    def update_size(self, size):
        """更新尺寸并发出信号."""
        width = size.width()
        new_class = self.get_size_class(width)

        if new_class != self._current_size_class:
            self._current_size_class = new_class

    @staticmethod
    def get_optimal_splitter_sizes(total_width: int, is_left_panel: bool = True):
        """获取优化的分割器尺寸."""
        if total_width < 800:
            # 小屏幕：隐藏侧边栏或最小化
            return [0, total_width] if is_left_panel else [total_width, 0]
        if total_width < 1200:
            # 中等屏幕：侧边栏较窄
            sidebar_width = 200
            return [sidebar_width, total_width - sidebar_width]
        if total_width < 1600:
            # 大屏幕：标准侧边栏
            sidebar_width = 250
            return [sidebar_width, total_width - sidebar_width]

        # 超大屏幕：较宽侧边栏
        sidebar_width = 300
        return [sidebar_width, total_width - sidebar_width]

    @staticmethod
    def get_table_page_size(height: int) -> int:
        """根据高度获取表格最优每页显示数量."""
        # 每行约30px高度
        row_height = 30
        header_height = 50
        pagination_height = 40

        available_height = height - header_height - pagination_height
        rows = max(10, available_height // row_height)

        # 取标准值
        if rows < 20:
            return 20
        if rows < 50:
            return 50
        if rows < 100:
            return 100

        return 200

    @staticmethod
    def get_font_size(width: int) -> int:
        """根据宽度获取最优字体大小."""
        if width < 800:
            return 9
        if width < 1200:
            return 10
        if width < 1600:
            return 11

        return 12

    @staticmethod
    def should_show_sidebar(width: int) -> bool:
        """判断是否应该显示侧边栏."""
        return width >= 800

    @staticmethod
    def get_card_columns(width: int) -> int:
        """获取卡片布局的列数."""
        if width < 800:
            return 1
        if width < 1200:
            return 2
        if width < 1600:
            return 3

        return 4


if __name__ == "__main__":
    main_sync()  # 使用同步模式，避免异步初始化导致的崩溃
