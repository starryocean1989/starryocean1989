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

from backend.config import ConfigManager
from backend.core.utils import LoggerMixin
from backend.core.base import setup_logging

from ui.themes.theme_manager import ThemeManager


from ui.shared_widgets.responsive_helper import ResponsiveHelper
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
        except Exception as e:
            self.logger.error("初始化主题管理器失败: %s", e)
            self.theme_manager = None

        try:
            self.config_manager = ConfigManager()
        except Exception as e:
            self.logger.error("初始化配置管理器失败: %s", e)
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
        self.interface_order = ["data", "market", "strategy", "trading", "portfolio", "system"]

        # 界面元数据
        self.interface_metadata = {
            "system": {"icon": "🛠️", "name": "系统管理", "description": "系统监控与运维管理"},
            "data": {"icon": "🗃️", "name": "数据中心", "description": "数据管理解决方案"},
            "market": {"icon": "📈", "name": "行情看板", "description": "专业行情分析工具"},
            "strategy": {"icon": "🧠", "name": "策略中心", "description": "策略开发和回测环境"},
            "trading": {"icon": "🔗", "name": "交易网关", "description": "多网关交易执行"},
            "portfolio": {"icon": "📊", "name": "组合投资", "description": "投资组合管理和监控"},
        }

        # 动态导入映射：按需加载时根据ID导入对应类
        self.interface_imports = {
            "data": ("ui.modules.data_center.view", "DataCenter"),
            "market": ("ui.modules.market_board.view", "MarketDashboard"),
            "strategy": ("ui.modules.strategy_center.view", "StrategyCenter"),
            "trading": ("ui.modules.trading_gateway.view", "TradingGateway"),
            "portfolio": ("ui.modules.portfolio.view", "PortfolioInvestment"),
            "system": ("ui.modules.system_manager.view", "SystemManager"),
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
        if backend_ready:
            self.create_function_interfaces()

            # 应用主题
            self.apply_theme()

            # 连接信号
            self.connect_signals()

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
        else:
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
            from backend.config import init_settings, get_settings

            # 从环境变量获取配置文件路径
            config_file = os.getenv("CONFIG_FILE")

            if config_file:
                logging.getLogger(__name__).info("从环境变量加载配置: %s", config_file)
                init_settings(config_file)
            else:
                logging.getLogger(__name__).info("使用默认配置文件")
                init_settings()

            # 验证配置已加载
            settings = get_settings()
            if settings.ai.api_key:
                masked_key = (
                    f"{settings.ai.api_key[:4]}...{settings.ai.api_key[-4:]}"
                    if len(settings.ai.api_key) > 8
                    else "***"
                )
                logging.getLogger(__name__).info("配置已加载，API Key: %s", masked_key)
            else:
                logging.getLogger(__name__).warning("配置已加载，但API Key未设置")

        except Exception as e:
            logging.getLogger(__name__).error("配置初始化失败: %s", e, exc_info=True)

    def initialize_function_interfaces_after_backend(self):
        """在后端就绪后初始化功能界面（异步模式）."""
        try:
            self.logger.info("=" * 70)
            self.logger.info("🎨 开始创建UI功能界面（主线程）")
            self.logger.info("=" * 70)

            import threading

            self.logger.info("当前线程ID: %s", threading.current_thread().ident)
            self.logger.info("当前线程名: %s", threading.current_thread().name)
            self.logger.info(
                "是否为主线程: %s", threading.current_thread() == threading.main_thread()
            )

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
            # 标记就绪阶段（异步模式）
            try:
                if getattr(self, "boot_orchestrator", None):
                    self.boot_orchestrator.mark_ready("backend_ready")
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

            init_result = initialize_services()
            success = init_result.get("success", False)
            if success:
                logging.getLogger(__name__).info("后端服务初始化完成")
            else:
                logging.getLogger(__name__).warning("后端服务初始化失败")
                error_report = init_result.get("user_friendly_report", "")
                if error_report:
                    logging.getLogger(__name__).warning("错误详情: %s", error_report)

        except Exception as e:
            logging.getLogger(__name__).warning("后端服务初始化失败: %s", e)

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
        """设置状态栏."""
        self.status_bar = self.statusBar()

        # 左侧状态信息
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label, 1)

        # 中间告警滚动条
        from ui.shared_widgets.alert_ticker import AlertTicker

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
        # 定义所有功能界面（使用延迟加载，interface_class=None）
        interfaces = [
            ("data", None),
            ("market", None),
            ("strategy", None),
            ("trading", None),
            ("portfolio", None),
            ("system", None),
        ]

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
        """严格串行触发所有按需加载（100%避免并发）.

        使用就绪标志确保每次只加载一个界面，完全避免并发。
        """
        if self._is_loading_interface:
            self.logger.warning("⚠️ 已有界面正在加载，跳过重复触发")
            return

        if self._interfaces_loaded:
            self.logger.info("✅ 界面已全部加载，跳过")
            return

        self._is_loading_interface = True
        self.logger.info("=" * 70)
        self.logger.info("开始严格串行加载，共 %d 个界面", len(self.lazy_loaders))
        self.logger.info("=" * 70)

        loaded_count = 0
        failed_count = 0

        for idx, interface_id in enumerate(self.interface_order, 1):
            if interface_id in self.lazy_loaders:
                try:
                    metadata = self.interface_metadata.get(interface_id, {})
                    interface_name = metadata.get("name", interface_id)

                    self.logger.info("-" * 60)
                    self.logger.info(
                        "[%d/%d] 正在加载: %s (%s)",
                        idx,
                        len(self.lazy_loaders),
                        interface_name,
                        interface_id,
                    )
                    self.logger.info("-" * 60)
                    print(
                        f"[LAZY-LOAD] [{idx}/{len(self.lazy_loaders)}] 正在加载: {interface_name}"
                    )

                    # 严格串行：等待上一个完全完成再加载下一个
                    self._trigger_lazy_load(interface_id)

                    loaded_count += 1
                    self.logger.info(
                        "✅ [%d/%d] %s 加载完成", idx, len(self.lazy_loaders), interface_name
                    )
                    print(
                        f"[LAZY-LOAD] ✅ [{idx}/{len(self.lazy_loaders)}] {interface_name} 加载完成"
                    )

                except Exception as e:
                    failed_count += 1
                    self.logger.error(
                        "❌ [%d/%d] %s 加载失败: %s",
                        idx,
                        len(self.lazy_loaders),
                        interface_id,
                        e,
                        exc_info=True,
                    )
                    print(
                        f"[LAZY-LOAD] ❌ [{idx}/{len(self.lazy_loaders)}] {interface_id} 加载失败: {e}"
                    )
                    # 继续加载下一个，不中断流程

        self._interfaces_loaded = True
        self._is_loading_interface = False

        self.logger.info("=" * 70)
        self.logger.info("✅ 所有按需加载已完成")
        self.logger.info("   - 成功: %d 个", loaded_count)
        self.logger.info("   - 失败: %d 个", failed_count)
        self.logger.info("=" * 70)

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

                    # ✅ 禁用自动触发按需加载，避免并发
                    # 所有加载由_trigger_lazy_loads_sequentially()严格控制
                    # if interface_id in getattr(self, "lazy_loaders", {}):
                    #     self._trigger_lazy_load(interface_id)

                    # 更新状态栏
                    if self.status_label:
                        self.status_label.setText(f"当前界面: {interface_name}")

                    # 发送界面切换信号
                    self.interface_changed.emit(interface_id)

                    self.logger.info("切换到界面: %s (%s)", interface_name, interface_id)

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
            self.responsive_helper = ResponsiveHelper(self)
            self.responsive_helper.size_class_changed.connect(self._on_size_class_changed)
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

        setup_logging(name="terminal_v0.50", level="INFO", log_file="logs/terminal_v0.50.log")

        # 🔧 设置Qt属性以避免QStyleHints连接问题
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        # 🔧 关键修复：在创建任何UI组件之前先初始化配置
        import os
        from backend.config import init_settings

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

        setup_logging(name="terminal_v0.50", level="INFO", log_file="logs/terminal_v0.50.log")

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


if __name__ == "__main__":
    main_sync()  # 使用同步模式，避免异步初始化导致的崩溃
