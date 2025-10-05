# -*- coding: utf-8 -*-
"""
主窗口 - 星辰金融终端的主界面
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QToolBar,
    QLabel, QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QPixmap

# 导入主题和配置管理器
from .themes.theme_manager import ThemeManager
from config import ConfigManager
from utils.logging_utils import LoggerMixin
try:
    from utils.error_handler import error_handler, ErrorCategory, ErrorSeverity
except ImportError:
    # 如果错误处理器不可用，创建简单的替代品
    class ErrorCategory:
        UI = "ui"
        SYSTEM = "system"
        NETWORK = "network"
        DATA = "data"
        VNPY = "vnpy"
        UNKNOWN = "unknown"

    class ErrorSeverity:
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"

    class MockErrorHandler:
        def handle_error(self, error_id, message, category=None, severity=None, max_retries=1, callback=None, parent_widget=None):
            print(f"错误 {error_id}: {message}")
            return False

    error_handler = MockErrorHandler()

# 导入功能界面模块
from .components.system_manager.main_view import SystemManager
from .components.data_center.main_view import DataCenter
from .components.market_dashboard.main_view import MarketDashboard
from .components.strategy_center.main_view import StrategyCenter
from .components.trading_gateway.main_view import TradingGateway
from .components.portfolio_investment.main_view import PortfolioInvestment


class MainWindow(QMainWindow, LoggerMixin):
    """主窗口类"""

    def __init__(self):
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
        """设置主界面"""
        # 设置窗口基本属性
        self.setWindowTitle(f"{self.config_manager.app_config.name} v{self.config_manager.app_config.version}")
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
        """设置菜单栏"""
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
        dark_theme_action.setChecked(self.config_manager.ui_config.theme == "dark")
        dark_theme_action.triggered.connect(lambda: self.switch_theme("dark"))
        theme_menu.addAction(dark_theme_action)

        # 帮助菜单
        help_menu = self.menu_bar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_toolbar(self):
        """设置工具栏"""
        self.toolbar = self.addToolBar("主工具栏")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

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
            action.triggered.connect(lambda checked, iid=interface_id: self.switch_to_interface(iid))
            self.toolbar.addAction(action)

    def setup_status_bar(self):
        """设置状态栏"""
        self.status_bar = self.statusBar()

        # 左侧状态信息
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label, 1)

        # 右侧系统信息
        self.system_info_label = QLabel("系统正常")
        self.status_bar.addPermanentWidget(self.system_info_label)

    def create_function_interfaces(self):
        """创建功能界面"""
        try:
            # 系统管理界面（标准架构，8个子界面）
            try:
                self.function_interfaces["system"] = SystemManager()
                self.tab_widget.addTab(self.function_interfaces["system"], "🛠️ 系统管理")
                self.logger.info("系统管理界面创建成功")
            except Exception as e:
                self.logger.error(f"系统管理界面创建失败: {e}")

            # 数据中心界面（标准架构，4个子界面）
            try:
                self.function_interfaces["data"] = DataCenter()
                self.tab_widget.addTab(self.function_interfaces["data"], "🗃️ 数据中心")
                self.logger.info("数据中心界面创建成功")
            except Exception as e:
                self.logger.error(f"数据中心界面创建失败: {e}")

            # 行情看板界面（单一界面，集成设计）
            try:
                self.function_interfaces["market"] = MarketDashboard()
                self.tab_widget.addTab(self.function_interfaces["market"], "📈 行情看板")
                self.logger.info("行情看板界面创建成功")
            except Exception as e:
                self.logger.error(f"行情看板界面创建失败: {e}")

            # 策略中心界面（混合架构，管理器+选项卡）
            try:
                self.function_interfaces["strategy"] = StrategyCenter()
                self.tab_widget.addTab(self.function_interfaces["strategy"], "🧠 策略中心")
                self.logger.info("策略中心界面创建成功")
            except Exception as e:
                self.logger.error(f"策略中心界面创建失败: {e}")

            # 交易网关界面（混合架构，管理器+选项卡）
            try:
                self.function_interfaces["trading"] = TradingGateway()
                self.tab_widget.addTab(self.function_interfaces["trading"], "🔗 交易网关")
                self.logger.info("交易网关界面创建成功")
            except Exception as e:
                self.logger.error(f"交易网关界面创建失败: {e}")

            # 组合投资界面（混合架构，双固有组件）
            try:
                self.function_interfaces["portfolio"] = PortfolioInvestment()
                self.tab_widget.addTab(self.function_interfaces["portfolio"], "📊 组合投资")
                self.logger.info("组合投资界面创建成功")
            except Exception as e:
                self.logger.error(f"组合投资界面创建失败: {e}")

            self.logger.info("所有功能界面创建完成")

        except Exception as e:
            import traceback
            self.logger.error(f"创建功能界面失败: {e}")
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")

            # 使用统一错误处理器
            try:
                error_handler.handle_error(
                    error_id="main_window_interface_init",
                    message=f"界面初始化失败: {str(e)}",
                    category=ErrorCategory.UI,
                    severity=ErrorSeverity.HIGH,
                    max_retries=1,
                    parent_widget=self
                )
            except Exception as handler_error:
                self.logger.error(f"错误处理器调用失败: {handler_error}")

    def apply_theme(self):
        """应用主题"""
        try:
            self.theme_manager.apply_theme(QApplication.instance())
            self.logger.info("主题应用完成")
        except Exception as e:
            self.logger.error(f"应用主题失败: {e}")

    def switch_theme(self, theme_name: str):
        """切换主题"""
        try:
            self.config_manager.ui_config.theme = theme_name
            self.config_manager.save_config()
            self.theme_manager.reload_theme()
            self.apply_theme()
            self.logger.info(f"切换到主题: {theme_name}")
        except Exception as e:
            self.logger.error(f"切换主题失败: {e}")

    def switch_to_interface(self, interface_id: str):
        """切换到指定界面"""
        if interface_id in self.function_interfaces:
            index = self.tab_widget.indexOf(self.function_interfaces[interface_id])
            if index >= 0:
                self.tab_widget.setCurrentIndex(index)
                self.logger.info(f"切换到界面: {interface_id}")

    def refresh_all_interfaces(self):
        """刷新所有界面"""
        try:
            for interface_id, interface in self.function_interfaces.items():
                try:
                    if hasattr(interface, 'refresh_data'):
                        interface.refresh_data()
                        self.logger.info(f"界面 {interface_id} 刷新成功")
                except Exception as interface_error:
                    self.logger.error(f"界面 {interface_id} 刷新失败: {interface_error}")

            self.status_label.setText("刷新完成")
            self.logger.info("所有界面刷新完成")
        except Exception as e:
            self.logger.error(f"刷新界面失败: {e}")

            # 使用统一错误处理器
            try:
                error_handler.handle_error(
                    error_id="main_window_refresh",
                    message=f"刷新失败: {str(e)}",
                    category=ErrorCategory.UI,
                    severity=ErrorSeverity.MEDIUM,
                    max_retries=2,
                    parent_widget=self
                )
            except Exception as handler_error:
                self.logger.error(f"错误处理器调用失败: {handler_error}")

    def connect_signals(self):
        """连接信号槽"""
        # 连接选项卡切换信号
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # 连接功能界面的信号
        for interface in self.function_interfaces.values():
            if hasattr(interface, 'error_occurred'):
                interface.error_occurred.connect(self.on_interface_error)
            if hasattr(interface, 'info_message'):
                interface.info_message.connect(self.on_interface_info)

    def on_tab_changed(self, index: int):
        """选项卡切换回调"""
        if index >= 0 and index < self.tab_widget.count():
            tab_text = self.tab_widget.tabText(index)
            self.status_label.setText(f"当前界面: {tab_text}")
            self.logger.info(f"切换到选项卡: {tab_text}")

    def on_interface_error(self, message: str):
        """界面错误回调"""
        self.status_label.setText("错误: " + message)
        self.logger.error(f"界面错误: {message}")

    def on_interface_info(self, message: str):
        """界面信息回调"""
        self.status_label.setText("信息: " + message)
        self.logger.info(f"界面信息: {message}")

    def start_update_timer(self):
        """启动状态更新定时器"""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(5000)  # 每5秒更新一次

    def update_status(self):
        """更新状态栏信息"""
        try:
            # 更新系统信息
            try:
                import psutil
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()

                status_text = f"CPU: {cpu_percent:.1f}% | 内存: {memory.percent:.1f}%"
                self.system_info_label.setText(status_text)

                # 检查性能阈值
                if cpu_percent > 80 or memory.percent > 80:
                    self.status_label.setText("警告: 系统负载较高")
                else:
                    self.status_label.setText("系统正常")
            except ImportError:
                # 如果psutil不可用，显示默认状态
                self.system_info_label.setText("系统监控不可用")
                self.status_label.setText("系统正常")

        except Exception as e:
            self.logger.error(f"更新状态失败: {e}")

    def show_about(self):
        """显示关于对话框"""
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

    def closeEvent(self, event):
        """窗口关闭事件"""
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
        """显示错误信息"""
        QMessageBox.critical(
            self,
            "错误",
            message,
            QMessageBox.StandardButton.Ok
        )

    def get_current_interface(self) -> Optional[QWidget]:
        """获取当前活动界面"""
        current_index = self.tab_widget.currentIndex()
        if current_index >= 0:
            return self.tab_widget.widget(current_index)
        return None

    def get_interface_by_id(self, interface_id: str) -> Optional[QWidget]:
        """根据ID获取界面"""
        return self.function_interfaces.get(interface_id)

    def save_window_state(self):
        """保存窗口状态"""
        try:
            # 保存窗口大小和位置
            self.config_manager.ui_config.window_width = self.width()
            self.config_manager.ui_config.window_height = self.height()
            self.config_manager.save_config()
            self.logger.info("窗口状态已保存")
        except Exception as e:
            self.logger.error(f"保存窗口状态失败: {e}")

    def resizeEvent(self, event):
        """窗口大小改变事件"""
        super().resizeEvent(event)
        # 保存窗口状态（延迟保存，避免频繁写入）
        QTimer.singleShot(1000, self.save_window_state)


def main():
    """主函数"""
    # 设置日志
    from utils.logging_utils import setup_logging
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


if __name__ == "__main__":
    main()
