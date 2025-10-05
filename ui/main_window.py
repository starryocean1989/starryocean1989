# -*- coding: utf-8 -*-
"""主窗口 - 星辰金融终端的主界面."""

import contextlib
import logging
import sys
import traceback
from typing import Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

# Import logging utilities

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QLabel, QMainWindow,
    QMessageBox, QTabWidget, QVBoxLayout, QWidget
)

# 导入主题和配置管理器
try:
    from .themes.theme_manager import ThemeManager
except ImportError:
    try:
        from themes.theme_manager import ThemeManager
    except ImportError:
        class ThemeManager:
            """主题管理器类."""

            def __init__(self):
                """初始化主题管理器."""

            def apply_theme(self, _app):  # noqa: U101
                """应用主题."""


try:
    from config import ConfigManager
except ImportError:
    try:
        import os
        current_file = os.path.abspath(__file__)
        parent_dir = os.path.dirname(current_file)
        current_dir = os.path.dirname(parent_dir)
        sys.path.insert(0, current_dir)
        from config import ConfigManager
    except ImportError:
        class ConfigManager:
            """配置管理器类."""

            def __init__(self):
                """初始化配置管理器."""
                self.app_config = type('AppConfig', (), {
                    'name': '星辰金融终端',
                    'version': '5.0.0'
                })()
                self.ui_config = type('UIConfig', (), {
                    'min_width': 800,
                    'min_height': 600,
                    'window_width': 1200,
                    'window_height': 800,
                    'theme': 'dark'
                })()

# 导入日志和错误处理
try:
    from ..utils.logging_utils import LoggerMixin, setup_logging
    from ..utils.error_handler import (
        error_handler, ErrorCategory, ErrorSeverity
    )
except ImportError:
    try:
        from utils.logging_utils import LoggerMixin, setup_logging
        from utils.error_handler import (
            error_handler, ErrorCategory, ErrorSeverity
        )
    except ImportError:
        # 如果错误处理器不可用，创建简单的替代品
        class ErrorCategory:
            """错误分类枚举."""

            UI = "ui"
            SYSTEM = "system"
            NETWORK = "network"
            DATA = "data"
            VNPY = "vnpy"
            UNKNOWN = "unknown"

        class ErrorSeverity:
            """错误严重程度枚举."""

            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"
            CRITICAL = "critical"

        class LoggerMixin:
            """日志混合类."""

            @property
            def logger(self):
                """获取日志记录器."""
                return logging.getLogger(self.__class__.__name__)

        def setup_logging(_name: str = "terminal_v0.50",  # noqa: U101
                          level: str = "INFO",
                          log_file: str | None = None):
            """设置日志."""
            lvl = getattr(logging, level.upper(), logging.INFO)
            fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            logging.basicConfig(level=lvl, format=fmt)
            if log_file:
                try:
                    fh = logging.FileHandler(log_file, encoding="utf-8")
                    fh.setLevel(lvl)
                    format_str = ('%(asctime)s - %(name)s - '
                                  '%(levelname)s - %(message)s')
                    formatter = logging.Formatter(format_str)
                    fh.setFormatter(formatter)
                    logging.getLogger().addHandler(fh)
                except OSError as e:
                    logger = logging.getLogger(__name__)
                    logger.warning("日志文件处理器创建失败: %s", e)

        class MockErrorHandler:
            """模拟错误处理器."""

            def handle_error(self, error_id, message,  # noqa: U101
                             _category=None, _severity=None,  # noqa: U101
                             _max_retries=1, _callback=None,  # noqa: U101
                             _parent_widget=None):  # noqa: U101
                """处理错误信息."""
                print(f"错误 {error_id}: {message}")
                return False

        error_handler = MockErrorHandler()

# 导入功能界面模块
try:
    from .components.system_manager.main_view import SystemManager
    from .components.data_center.main_view import DataCenter
    from .components.market_dashboard.main_view import MarketDashboard
    from .components.strategy_center.main_view import StrategyCenter
    from .components.trading_gateway.main_view import TradingGateway
    from .components.portfolio_investment.main_view import PortfolioInvestment
    from .components.ops_center.main_view import OpsCenter
except ImportError:
    try:
        from components.system_manager.main_view import SystemManager
        from components.data_center.main_view import DataCenter
        from components.market_dashboard.main_view import MarketDashboard
        from components.strategy_center.main_view import StrategyCenter
        from components.trading_gateway.main_view import TradingGateway
        from components.portfolio_investment.main_view import (
            PortfolioInvestment
        )
        from components.ops_center.main_view import OpsCenter
    except ImportError:
        # 简化版本
        class SystemManager:
            """系统管理器组件."""

            def __init__(self):
                """初始化系统管理器."""

        class DataCenter:
            """数据中心组件."""

            def __init__(self):
                """初始化数据中心."""

        class MarketDashboard:
            """行情看板组件."""

            def __init__(self):
                """初始化行情看板."""

        class StrategyCenter:
            """策略中心组件."""

            def __init__(self):
                """初始化策略中心."""

        class TradingGateway:
            """交易网关组件."""

            def __init__(self):
                """初始化交易网关."""

        class PortfolioInvestment:
            """组合投资组件."""

            def __init__(self):
                """初始化组合投资."""


class MainWindow(QMainWindow, LoggerMixin):
    """主窗口类."""

    def __init__(self):
        """初始化主窗口."""
        super().__init__()

        # 初始化组件
        self.theme_manager = ThemeManager()
        self.config_manager = ConfigManager()

        # 界面组件
        self.central_widget = None
        self.tab_widget = None
        self.status_bar = None
        self.menu_bar = None
        self.toolbar = None

        # 功能界面实例
        self.function_interfaces: Dict[str, QWidget] = {}

        # 更新定时器
        self.update_timer = None
        # 界面就绪标志
        self.ui_ready = False

        # 初始化UI
        self.setup_ui()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.setup_status_bar()
        self.create_function_interfaces()

        # 应用主题
        self.apply_theme()

        # 连接信号
        self.connect_signals()

        # 启动更新定时器
        self.start_update_timer()

        self.logger.info("主窗口初始化完成")

    def setup_ui(self):
        """设置主界面."""
        # 设置窗口基本属性
        app_name = self.config_manager.app_config.name
        app_version = self.config_manager.app_config.version
        title = f"{app_name} v{app_version}"
        self.setWindowTitle(title)
        self.setMinimumSize(
            self.config_manager.ui_config.min_width,
            self.config_manager.ui_config.min_height
        )
        self.resize(
            self.config_manager.ui_config.window_width,
            self.config_manager.ui_config.window_height
        )

        # 创建中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 创建主布局
        main_layout = QVBoxLayout(self.central_widget)

        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setMovable(True)
        self.tab_widget.setTabsClosable(False)

        main_layout.addWidget(self.tab_widget)

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

        # 帮助菜单
        help_menu = self.menu_bar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_toolbar(self):
        """设置工具栏."""
        self.toolbar = self.addToolBar("主工具栏")
        style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        self.toolbar.setToolButtonStyle(style)

        # 刷新按钮
        refresh_action = QAction("刷新", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_all_interfaces)
        self.toolbar.addAction(refresh_action)

        self.toolbar.addSeparator()

        # 功能界面快捷按钮
        interfaces = [
            ("系统管理", "system"),
            ("数据中心", "data"),
            ("行情看板", "market"),
            ("策略中心", "strategy"),
            ("交易网关", "trading"),
            ("组合投资", "portfolio")
        ]

        for name, interface_id in interfaces:
            action = QAction(name, self)
            action.triggered.connect(
                lambda _checked, iid=interface_id: (  # noqa: U101
                    self.switch_to_interface(iid)
                )
            )
            self.toolbar.addAction(action)

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
        """创建功能界面."""
        try:
            # 系统管理界面（标准架构，8个子界面）
            try:
                self.function_interfaces["system"] = SystemManager()
                tab_text = "🛠️ 系统管理"
                self.tab_widget.addTab(
                    self.function_interfaces["system"], tab_text
                )
                self.logger.info("系统管理界面创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("系统管理界面创建失败: %s", e)

            # 数据中心界面（标准架构，4个子界面）
            try:
                self.function_interfaces["data"] = DataCenter()
                tab_text = "🗃️ 数据中心"
                self.tab_widget.addTab(
                    self.function_interfaces["data"], tab_text
                )
                # 实例化后确保构建UI与信号绑定
                if hasattr(self.function_interfaces["data"], "setup_ui"):
                    self.function_interfaces["data"].setup_ui()
                if hasattr(self.function_interfaces["data"], "connect_signals"):
                    self.function_interfaces["data"].connect_signals()
                self.logger.info("数据中心界面创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("数据中心界面创建失败: %s", e)

            # 行情看板界面（单一界面，集成设计）
            try:
                self.function_interfaces["market"] = MarketDashboard()
                tab_text = "📈 行情看板"
                self.tab_widget.addTab(
                    self.function_interfaces["market"], tab_text
                )
                self.logger.info("行情看板界面创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("行情看板界面创建失败: %s", e)

            # 策略中心界面（混合架构，管理器+选项卡）
            try:
                self.function_interfaces["strategy"] = StrategyCenter()
                tab_text = "🧠 策略中心"
                self.tab_widget.addTab(
                    self.function_interfaces["strategy"], tab_text
                )
                # 实例化后确保构建UI与信号绑定
                if hasattr(self.function_interfaces["strategy"], "setup_ui"):
                    self.function_interfaces["strategy"].setup_ui()
                if hasattr(self.function_interfaces["strategy"], "connect_signals"):
                    self.function_interfaces["strategy"].connect_signals()
                self.logger.info("策略中心界面创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("策略中心界面创建失败: %s", e)
                # 占位标签，避免缺失
                placeholder = QWidget()
                placeholder_layout = QVBoxLayout(placeholder)
                placeholder_layout.addWidget(QLabel("策略中心加载失败：请检查依赖或模块实现"))
                self.tab_widget.addTab(placeholder, "🧠 策略中心")

            # 交易网关界面（混合架构，管理器+选项卡）
            try:
                self.function_interfaces["trading"] = TradingGateway()
                tab_text = "🔗 交易网关"
                self.tab_widget.addTab(
                    self.function_interfaces["trading"], tab_text
                )
                # 实例化后确保构建UI与信号绑定
                if hasattr(self.function_interfaces["trading"], "setup_ui"):
                    self.function_interfaces["trading"].setup_ui()
                if hasattr(self.function_interfaces["trading"], "connect_signals"):
                    self.function_interfaces["trading"].connect_signals()
                self.logger.info("交易网关界面创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("交易网关界面创建失败: %s", e)

            # 组合投资界面（混合架构，双固有组件）
            try:
                self.function_interfaces["portfolio"] = PortfolioInvestment()
                tab_text = "📊 组合投资"
                self.tab_widget.addTab(
                    self.function_interfaces["portfolio"], tab_text
                )
                # 实例化后确保构建UI与信号绑定
                if hasattr(self.function_interfaces["portfolio"], "setup_ui"):
                    self.function_interfaces["portfolio"].setup_ui()
                if hasattr(self.function_interfaces["portfolio"], "connect_signals"):
                    self.function_interfaces["portfolio"].connect_signals()
                self.logger.info("组合投资界面创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("组合投资界面创建失败: %s", e)
                # 占位标签，避免缺失
                placeholder = QWidget()
                placeholder_layout = QVBoxLayout(placeholder)
                placeholder_layout.addWidget(QLabel("组合投资加载失败：请检查依赖或模块实现"))
                self.tab_widget.addTab(placeholder, "📊 组合投资")

            # 运维与诊断中心（新增）
            try:
                self.function_interfaces["ops"] = OpsCenter()
                tab_text = "🛡️ 运维与诊断"
                self.tab_widget.addTab(
                    self.function_interfaces["ops"], tab_text
                )
                self.logger.info("运维与诊断中心创建成功")
            except (ImportError, AttributeError, RuntimeError) as e:
                self.logger.error("运维与诊断中心创建失败: %s", e)

            self.logger.info("所有功能界面创建完成")
            # 标记界面已就绪
            self.ui_ready = True

        except (ImportError, AttributeError, RuntimeError) as e:
            self.logger.error("创建功能界面失败: %s", e)
            self.logger.error("详细错误信息: %s", traceback.format_exc())

            # 使用统一错误处理器
            try:
                error_handler.handle_error(
                    error_id="main_window_interface_init",
                    message=f"界面初始化失败: {str(e)}",
                    _category=ErrorCategory.UI,
                    _severity=ErrorSeverity.HIGH,
                    _max_retries=1,
                    _parent_widget=self
                )
            except (AttributeError, RuntimeError) as handler_error:
                self.logger.error("错误处理器调用失败: %s", handler_error)

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
            self.theme_manager.reload_theme()
            self.apply_theme()
            self.logger.info("切换到主题: %s", theme_name)
        except (AttributeError, RuntimeError, OSError) as e:
            self.logger.error("切换主题失败: %s", e)

    def switch_to_interface(self, interface_id: str):
        """切换到指定界面."""
        if interface_id in self.function_interfaces:
            interface = self.function_interfaces[interface_id]
            index = self.tab_widget.indexOf(interface)
            if index >= 0:
                self.tab_widget.setCurrentIndex(index)
                self.logger.info("切换到界面: %s", interface_id)

    def refresh_all_interfaces(self):
        """刷新所有界面."""
        try:
            for interface_id, interface in self.function_interfaces.items():
                try:
                    if hasattr(interface, 'refresh_data'):
                        interface.refresh_data()
                        self.logger.info("界面 %s 刷新成功", interface_id)
                except (AttributeError, RuntimeError) as interface_error:
                    error_msg = f"界面 {interface_id} 刷新失败: {interface_error}"
                    self.logger.error(error_msg)

            self.status_label.setText("刷新完成")
            self.logger.info("所有界面刷新完成")
        except (AttributeError, RuntimeError) as e:
            self.logger.error("刷新界面失败: %s", e)

            # 使用统一错误处理器
            try:
                error_handler.handle_error(
                    error_id="main_window_refresh",
                    message=f"刷新失败: {str(e)}",
                    _category=ErrorCategory.UI,
                    _severity=ErrorSeverity.MEDIUM,
                    _max_retries=2,
                    _parent_widget=self
                )
            except (AttributeError, RuntimeError) as handler_error:
                self.logger.error("错误处理器调用失败: %s", handler_error)

    def connect_signals(self):
        """连接信号槽."""
        # 连接选项卡切换信号
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # 连接功能界面的信号
        for interface in self.function_interfaces.values():
            if hasattr(interface, 'error_occurred'):
                interface.error_occurred.connect(self.on_interface_error)
            if hasattr(interface, 'info_message'):
                interface.info_message.connect(self.on_interface_info)

    def on_tab_changed(self, index: int):
        """选项卡切换回调."""
        if index >= 0 and index < self.tab_widget.count():
            tab_text = self.tab_widget.tabText(index)
            self.status_label.setText(f"当前界面: {tab_text}")
            self.logger.info("切换到选项卡: %s", tab_text)

    def on_interface_error(self, message: str):
        """界面错误回调."""
        self.status_label.setText("错误: " + message)
        self.logger.error("界面错误: %s", message)

    def on_interface_info(self, message: str):
        """界面信息回调."""
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
        # 就绪与控件存在性守卫，避免 NoneType 访问
        if not getattr(self, "ui_ready", False):
            return
        if not hasattr(self, "system_info_label") or self.system_info_label is None:
            return
        if not hasattr(self, "status_label") or self.status_label is None:
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
                        self.status_label.setText("系统正常")
                except (OSError, RuntimeError):
                    # 如果psutil调用失败，显示默认状态
                    self.system_info_label.setText("系统监控不可用")
                    self.status_label.setText("系统正常")
            else:
                # 如果psutil不可用，显示默认状态
                self.system_info_label.setText("系统监控不可用")
                self.status_label.setText("系统正常")

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
            <p><strong>功能特性:</strong></p>
            <ul>
                <li>🛠️ 系统管理 - 8个监控和管理模块</li>
                <li>🗃️ 数据中心 - 4个数据管理模块</li>
                <li>📈 行情看板 - 专业行情分析工具</li>
                <li>🧠 策略中心 - 策略开发和回测环境</li>
                <li>🔗 交易网关 - 多网关交易执行</li>
                <li>📊 组合投资 - 投资组合管理和监控</li>
            </ul>
            """
        )

    def closeEvent(self, event):  # pylint: disable=invalid-name
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
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.logger.info("应用程序退出")
            event.accept()
        else:
            event.ignore()

    def show_error(self, message: str):
        """显示错误信息."""
        QMessageBox.critical(
            self,
            "错误",
            message,
            QMessageBox.StandardButton.Ok
        )

    def get_current_interface(self) -> Optional[QWidget]:
        """获取当前活动界面."""
        current_index = self.tab_widget.currentIndex()
        if current_index >= 0:
            return self.tab_widget.widget(current_index)
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

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """窗口大小改变事件."""
        super().resizeEvent(event)
        # 保存窗口状态（延迟保存，避免频繁写入）
        QTimer.singleShot(1000, self.save_window_state)


def main():
    """主函数."""
    try:
        # 设置日志
        setup_logging(
            name="terminal_v0.50",
            level="INFO",
            log_file="logs/terminal_v0.50.log"
        )

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
        # 记录致命异常，便于启动器与热更新诊断
        logging.getLogger("terminal_v0.50.main").exception("UI启动异常: %s", e)
        # 追加到UI进程日志文件
        with contextlib.suppress(Exception), open(
            "logs/ui_process.err.log", "a", encoding="utf-8"
        ) as f:
            f.write(f"UI启动异常: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
