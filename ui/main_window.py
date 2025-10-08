# -*- coding: utf-8 -*-
# type: ignore
"""主窗口 - 星辰金融终端的主界面（完全重建版）."""

import contextlib
import logging
import sys
import traceback
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


from backend.core.utils.error_handler import error_handler
from backend.core.utils.logging_utils import (
    LoggerMixin,
    setup_logging,
)

# UI模块导入
from ui.themes.theme_manager import ThemeManager
from ui.components.data_center.main_view import DataCenter
from ui.components.market_dashboard.main_view import MarketDashboard
from ui.components.portfolio_investment.main_view import PortfolioInvestment
from ui.components.strategy_center.main_view import StrategyCenter
from ui.components.system_manager.main_view import SystemManager
from ui.components.trading_gateway.main_view import TradingGateway
from ui.widgets.responsive_helper import ResponsiveHelper


class MainWindow(QMainWindow, LoggerMixin):
    """主窗口类 - 完全重建版.

    架构设计：
    - 左侧：垂直导航列表（QListWidget）
    - 右侧：内容显示区（QStackedWidget）
    - 顶部：菜单栏和工具栏
    - 底部：状态栏
    """

    # 定义信号
    interface_changed = Signal(str)  # 界面切换信号

    def __init__(self):
        """初始化主窗口."""
        super().__init__()

        # 先初始化后端服务
        self._initialize_backend_services()

        # 初始化组件
        self.theme_manager: Any = ThemeManager()
        self.config_manager: Any = ConfigManager()

        # 界面组件
        self.central_widget: Optional[QWidget] = None
        self.nav_list: Optional[QListWidget] = None  # 左侧导航列表
        self.content_stack: Optional[QStackedWidget] = None  # 右侧内容区
        self.status_bar = None
        self.status_label: Optional[QLabel] = None
        self.system_info_label: Optional[QLabel] = None
        self.menu_bar = None
        # 不使用工具栏，只保留左侧导航

        # 功能界面实例 - 按顺序存储
        self.function_interfaces: Dict[str, Any] = {}
        self.interface_order = [
            "system",
            "data",
            "market",
            "strategy",
            "trading",
            "portfolio",
        ]

        # 界面元数据
        self.interface_metadata = {
            "system": {"icon": "🛠️", "name": "系统管理", "description": "系统监控与运维管理"},
            "data": {"icon": "🗃️", "name": "数据中心", "description": "数据管理解决方案"},
            "market": {"icon": "📈", "name": "行情看板", "description": "专业行情分析工具"},
            "strategy": {"icon": "🧠", "name": "策略中心", "description": "策略开发和回测环境"},
            "trading": {"icon": "🔗", "name": "交易网关", "description": "多网关交易执行"},
            "portfolio": {"icon": "📊", "name": "组合投资", "description": "投资组合管理和监控"},
        }

        # 更新定时器
        self.update_timer = None
        # 界面就绪标志
        self.ui_ready = False

        # 响应式布局帮助器
        self.responsive_helper = None
        self._init_responsive_helper()

        # 初始化UI
        self.setup_ui()
        self.setup_menu_bar()
        # self.setup_toolbar()  # 删除顶部工具栏，只保留左侧导航
        self.setup_status_bar()
        self.create_function_interfaces()

        # 应用主题
        self.apply_theme()

        # 连接信号
        self.connect_signals()

        # 启动更新定时器
        self.start_update_timer()

        self.logger.info("主窗口初始化完成（重建版）")

    def _initialize_backend_services(self):
        """初始化后端服务（同步方式）."""
        try:
            import asyncio
            from backend.core.shared_services import get_service_manager
            from backend.services.vnpy_service import VnpyService
            from backend.services.event_service import EventService
            from backend.services.data_center.symbol_service import SymbolService
            from backend.services.data_center.local_data_service import LocalDataService
            from backend.services.data_center.download_service import DownloadService
            from backend.services.data_center.data_source_service import DataSourceService

            # 获取共享服务管理器
            service_manager = get_service_manager()

            # 创建事件循环（如果没有）
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # 初始化核心服务
            vnpy_service = VnpyService()
            loop.run_until_complete(vnpy_service.initialize())
            service_manager.register("vnpy_service", vnpy_service)

            event_service = EventService(vnpy_service)
            service_manager.register("event_service", event_service)

            # 初始化数据中心服务
            symbol_service = SymbolService(vnpy_service)
            loop.run_until_complete(symbol_service.initialize())
            service_manager.register("symbol_service", symbol_service)

            local_data_service = LocalDataService(vnpy_service, event_service)
            loop.run_until_complete(local_data_service.initialize())
            service_manager.register("local_data_service", local_data_service)

            download_service = DownloadService(vnpy_service, event_service)
            loop.run_until_complete(download_service.initialize())
            service_manager.register("download_service", download_service)

            data_source_service = DataSourceService(vnpy_service, event_service)
            loop.run_until_complete(data_source_service.initialize())
            service_manager.register("data_source_service", data_source_service)

            logging.getLogger(__name__).info("后端服务初始化完成")

        except Exception as e:
            logging.getLogger(__name__).warning("后端服务初始化失败，部分功能可能不可用: %s", e)
            import traceback

            traceback.print_exc()

    def setup_ui(self):
        """设置主界面."""
        # 设置窗口基本属性
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

        # 右侧系统信息
        self.system_info_label = QLabel("系统正常")
        self.status_bar.addPermanentWidget(self.system_info_label)

    def create_function_interfaces(self):
        """创建6个功能界面."""
        try:
            # 1. 系统管理界面（标准架构，8个子界面）
            self._create_interface(
                interface_id="system",
                interface_class=SystemManager,
            )

            # 2. 数据中心界面（标准架构，4个子界面）
            self._create_interface(
                interface_id="data",
                interface_class=DataCenter,
            )

            # 3. 行情看板界面（单一界面，集成设计）
            self._create_interface(
                interface_id="market",
                interface_class=MarketDashboard,
            )

            # 4. 策略中心界面（混合架构，管理器+选项卡）
            self._create_interface(
                interface_id="strategy",
                interface_class=StrategyCenter,
            )

            # 5. 交易网关界面（混合架构，管理器+选项卡）
            self._create_interface(
                interface_id="trading",
                interface_class=TradingGateway,
            )

            # 6. 组合投资界面（混合架构，双固有组件）
            self._create_interface(
                interface_id="portfolio",
                interface_class=PortfolioInvestment,
            )

            self.logger.info("所有功能界面创建完成")

            # 默认选中第一个界面
            if self.nav_list and self.nav_list.count() > 0:
                self.nav_list.setCurrentRow(0)

            # 标记界面已就绪
            self.ui_ready = True

        except Exception as e:
            self.logger.error("创建功能界面失败: %s", e)
            self.logger.error("详细错误信息: %s", traceback.format_exc())
            error_handler.handle_error(
                error_id="main_window_interface_init",
                message=f"界面初始化失败: {str(e)}",
            )

    def _create_interface(self, interface_id: str, interface_class: type):
        """创建单个功能界面.

        Args:
            interface_id: 界面ID
            interface_class: 界面类
        """
        try:
            # 创建界面实例
            # 注意：BaseWidget会在__init__中自动调用setup_ui()和connect_signals()
            # 所以这里不需要再次调用
            interface = interface_class()

            # 保存到字典
            self.function_interfaces[interface_id] = interface

            # 添加到内容区
            if self.content_stack:
                self.content_stack.addWidget(interface)

            # 添加到左侧导航列表
            if self.nav_list:
                metadata = self.interface_metadata[interface_id]
                item_text = f"{metadata['icon']}  {metadata['name']}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, interface_id)
                item.setToolTip(metadata["description"])
                self.nav_list.addItem(item)

            self.logger.info("%s界面创建成功", metadata["name"])

        except (ImportError, AttributeError, RuntimeError) as e:
            self.logger.error("%s界面创建失败: %s", interface_id, e)
            self.logger.error("详细错误信息: %s", traceback.format_exc())

            # 打印到控制台以便立即看到
            print(f"❌ {interface_id}界面创建失败: {e}")
            print(f"详细堆栈: {traceback.format_exc()}")

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
            self.theme_manager.apply_theme(app_instance)
            self.logger.info("主题应用完成")
        except (AttributeError, RuntimeError, ImportError) as e:
            self.logger.error("应用主题失败: %s", e)

    def switch_theme(self, theme_name: str):
        """切换主题."""
        try:
            self.config_manager.ui_config.theme = theme_name
            self.config_manager.save_config()
            if hasattr(self.theme_manager, "reload_theme"):
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
        except (AttributeError, RuntimeError) as e:
            self.logger.error("刷新界面失败: %s", e)
            error_handler.handle_error(
                error_id="main_window_refresh", message=f"刷新失败: {str(e)}"
            )

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
        # 就绪守卫，未就绪不启动定时器
        if not getattr(self, "ui_ready", False):
            return
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(5000)  # 每5秒更新一次

    def update_status(self):
        """更新状态栏信息."""
        # 就绪与控件存在性守卫
        if not getattr(self, "ui_ready", False):
            return
        if not self.system_info_label or not self.status_label:
            return

        try:
            # 更新系统信息
            if psutil is not None:
                try:
                    cpu_percent = psutil.cpu_percent()
                    memory = psutil.virtual_memory()

                    cpu_text = f"CPU: {cpu_percent:.1f}%"
                    memory_text = f"内存: {memory.percent:.1f}%"
                    status_text = f"{cpu_text} | {memory_text}"
                    self.system_info_label.setText(status_text)

                    # 检查性能阈值
                    if cpu_percent > 80 or memory.percent > 80:
                        self.status_label.setText("警告: 系统负载较高")
                    else:
                        current_text = self.status_label.text()
                        if not current_text.startswith("当前界面:"):
                            self.status_label.setText("系统正常")
                except (OSError, RuntimeError):
                    self.system_info_label.setText("系统监控不可用")
            else:
                self.system_info_label.setText("系统监控不可用")

        except (AttributeError, RuntimeError, OSError) as e:
            self.logger.error("更新状态失败: %s", e)

    def show_about(self):
        """显示关于对话框."""
        QMessageBox.about(
            self,
            "关于星辰金融终端",
            f"""<h3>星辰金融终端 v{self.config_manager.app_config.version}</h3>
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

    def closeEvent(self, event):
        """窗口关闭事件."""
        # 停止定时器
        if self.update_timer:
            self.update_timer.stop()

        # 询问用户是否确认退出
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出星辰金融终端吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
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
            # 保存窗口大小和位置
            self.config_manager.ui_config.window_width = self.width()
            self.config_manager.ui_config.window_height = self.height()
            self.config_manager.save_config()
            self.logger.info("窗口状态已保存")
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

    def resizeEvent(self, event):
        """窗口大小改变事件."""
        super().resizeEvent(event)

        # 更新响应式布局
        if self.responsive_helper:
            self.responsive_helper.update_size(event.size())

        # 保存窗口状态（延迟保存，避免频繁写入）
        QTimer.singleShot(1000, self.save_window_state)


def main():
    """主函数."""
    try:
        # 设置日志
        setup_logging(name="terminal_v0.50", level="INFO", log_file="logs/terminal_v0.50.log")

        # 创建应用程序
        app = QApplication(sys.argv)

        # 设置应用程序属性
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        # 创建主窗口
        main_window = MainWindow()
        main_window.show()

        # 运行应用程序
        sys.exit(app.exec())
    except (ImportError, OSError, RuntimeError, SystemError) as e:
        # 记录致命异常
        logging.getLogger("terminal_v0.50.main").exception("UI启动异常: %s", e)
        with (
            contextlib.suppress(Exception),
            open("logs/ui_process.err.log", "a", encoding="utf-8") as f,
        ):
            f.write(f"UI启动异常: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
