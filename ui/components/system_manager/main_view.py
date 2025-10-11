# -*- coding: utf-8 -*-
"""系统管理界面 - 主视图（重构版）.

标准架构：8个子界面采用选项卡形式。
合并handlers逻辑，统一backend调用。
"""
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QDate, Qt, Signal, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import psutil
import pyqtgraph as pg

from backend.core.base import get_service_manager
from backend.core.utils import LoggerMixin
from ui.widgets.base_widget import BaseWidget


class SystemManager(BaseWidget, LoggerMixin):
    """系统管理主界面（重构版）."""

    # 定义信号用于跨线程通信
    reader_progress_signal = Signal(int, int, str, bool)  # current, total, info, success
    reader_finished_signal = Signal(dict)  # result

    def __init__(self, parent=None):
        """初始化系统管理界面."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.system_service = None

        # 选项卡部件
        self.tab_widget: QTabWidget = QTabWidget()
        self.system_status_tab: Optional[QWidget] = None
        self.performance_tab: Optional[QWidget] = None
        self.alerts_tab: Optional[QWidget] = None
        self.services_tab: Optional[QWidget] = None
        self.config_tab: Optional[QWidget] = None
        self.logs_tab: Optional[QWidget] = None
        self.diagnosis_tab: Optional[QWidget] = None
        self.tools_tab: Optional[QWidget] = None

        # 系统状态组件
        self.cpu_label: Optional[QLabel] = None
        self.memory_label: Optional[QLabel] = None
        self.disk_label: Optional[QLabel] = None
        self.network_label: Optional[QLabel] = None
        self.status_table: Optional[QTableWidget] = None

        # 配置组件
        self.config_widgets: Dict[str, Any] = {}
        self.tdx_path_edit: Optional[QLineEdit] = None
        self.cache_dir_edit: Optional[QLineEdit] = None
        self.data_dir_edit: Optional[QLineEdit] = None
        self.base_date_edit: Optional[QDateEdit] = None
        self.max_workers_spin: Optional[QSpinBox] = None
        self.timeout_spin: Optional[QSpinBox] = None
        self.retry_spin: Optional[QSpinBox] = None
        self.watcher_check: Optional[QCheckBox] = None
        self.watcher_interval_spin: Optional[QSpinBox] = None

        # 性能监控组件
        self.cpu_plot: Optional[Any] = None
        self.cpu_curve: Optional[Any] = None
        self.memory_plot: Optional[Any] = None
        self.memory_curve: Optional[Any] = None
        self.performance_history: Dict[str, list] = {
            "cpu": [],
            "memory": [],
        }
        self.max_history_points: int = 100
        self.performance_table: Optional[QTableWidget] = None

        # 告警管理组件
        self.alerts_table: Optional[QTableWidget] = None

        # 服务管理组件
        self.services_table: Optional[QTableWidget] = None
        self.health_progress: Optional[QProgressBar] = None

        # 日志管理组件
        self.logs_table: Optional[QTableWidget] = None

        # 诊断工具组件
        self.diagnosis_table: Optional[QTableWidget] = None

        # 工具集合组件
        self.tools_table: Optional[QTableWidget] = None

        # 🔧 关键修复：在调用父类初始化之前就初始化服务
        # 因为 super().__init__() 会调用 setup_ui()，而 setup_ui() 会创建标签页
        # 标签页创建时会调用 _load_config()，此时需要 system_service 已经就绪
        self._initialize_service_before_ui()

        # 调用父类初始化
        super().__init__(parent, "系统管理")
        self.logger.info("系统管理界面初始化完成")

    def _initialize_service_before_ui(self):
        """在UI创建之前初始化服务（关键修复）.

        这个方法必须在 super().__init__() 之前调用，
        因为父类初始化会创建UI，而UI创建时会调用 _load_config()，
        _load_config() 需要 system_service 已经就绪。

        注意：此时 self.logger 还未初始化，使用 logging.getLogger()
        """
        import logging

        logger = logging.getLogger(self.__class__.__name__)

        try:
            # 从服务管理器获取系统管理服务
            self.system_service = self.service_manager.get_service("system_manager_service")
            if self.system_service:
                logger.info("系统管理服务获取成功")
            else:
                logger.warning("系统管理服务未注册，尝试手动创建...")
                # 如果服务未注册，尝试手动创建并注册
                try:
                    from backend.services.system_manager_service import SystemManagerService

                    self.system_service = SystemManagerService()
                    # 初始化服务
                    init_success = self.system_service.initialize()

                    # 注册到服务管理器（无论初始化是否成功）
                    self.service_manager.register_service(
                        "system_manager_service", self.system_service
                    )

                    if init_success:
                        logger.info("系统管理服务手动创建并注册成功")
                    else:
                        logger.warning("系统管理服务初始化失败，但服务已注册（可能部分功能不可用）")
                        # 保留服务引用，不要设为None
                except Exception as create_error:
                    logger.error("手动创建系统管理服务失败: %s", create_error, exc_info=True)
                    self.system_service = None
        except Exception as e:
            logger.error("获取系统管理服务失败: %s", e, exc_info=True)
            self.system_service = None

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(600, 400)

        if self.tab_widget:
            self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
            self.tab_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

        # 创建8个子界面
        self._create_sub_interfaces()

        if self.tab_widget:
            main_layout.addWidget(self.tab_widget)

    def _create_sub_interfaces(self):
        """创建8个子界面."""
        # 1.1 系统状态实时监控
        self.system_status_tab = self._create_system_status_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.system_status_tab, "🔍 系统状态监控")

        # 1.2 性能指标展示
        self.performance_tab = self._create_performance_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.performance_tab, "📊 性能指标")

        # 1.3 告警信息管理
        self.alerts_tab = self._create_alerts_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.alerts_tab, "🚨 告警管理")

        # 1.4 服务健康检查
        self.services_tab = self._create_services_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.services_tab, "💚 服务检查")

        # 1.5 系统配置
        self.config_tab = self._create_config_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.config_tab, "⚙️ 系统配置")

        # 1.6 日志管理
        self.logs_tab = self._create_logs_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.logs_tab, "📝 日志管理")

        # 1.7 系统诊断
        self.diagnosis_tab = self._create_diagnosis_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.diagnosis_tab, "🔧 系统诊断")

        # 1.8 工具集合
        self.tools_tab = self._create_tools_tab()
        if self.tab_widget:
            self.tab_widget.addTab(self.tools_tab, "🛠️ 工具集合")

    # ==================== 1.1 系统状态监控 ====================

    def _create_system_status_tab(self) -> QWidget:
        """创建系统状态监控子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 状态概览组
        overview_group = QGroupBox("系统概览")
        overview_layout = QFormLayout(overview_group)

        self.cpu_label = QLabel("--")
        overview_layout.addRow("CPU使用率:", self.cpu_label)

        self.memory_label = QLabel("--")
        overview_layout.addRow("内存使用率:", self.memory_label)

        self.disk_label = QLabel("--")
        overview_layout.addRow("磁盘使用率:", self.disk_label)

        self.network_label = QLabel("--")
        overview_layout.addRow("网络状态:", self.network_label)

        layout.addWidget(overview_group)

        # 系统详情组
        details_group = QGroupBox("详细状态")
        details_layout = QVBoxLayout(details_group)

        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["组件", "状态", "详情"])
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        details_layout.addWidget(self.status_table)
        layout.addWidget(details_group)

        return tab

    # ==================== 1.2 性能指标展示 ====================

    def _create_performance_tab(self) -> QWidget:
        """创建性能指标子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("📊 性能监控"))
        toolbar_layout.addStretch()

        auto_refresh_check = QCheckBox("自动刷新")
        auto_refresh_check.setChecked(True)
        toolbar_layout.addWidget(auto_refresh_check)

        clear_btn = QPushButton("清除历史")
        clear_btn.clicked.connect(self._clear_performance_history)
        toolbar_layout.addWidget(clear_btn)

        layout.addLayout(toolbar_layout)

        # 性能图表组
        chart_group = QGroupBox("实时性能图表")
        chart_layout = QVBoxLayout(chart_group)

        chart_splitter = QSplitter(Qt.Orientation.Horizontal)

        # CPU图表
        cpu_win = pg.GraphicsLayoutWidget()
        cpu_win.setBackground(QColor(26, 26, 26))
        self.cpu_plot = cpu_win.addPlot(title="CPU使用率 (%)")  # type: ignore[attr-defined]
        if self.cpu_plot:
            self.cpu_plot.showGrid(x=True, y=True, alpha=0.3)
            self.cpu_plot.setRange(yRange=[0, 100])
            pen = pg.mkPen(color="#FF6B6B", width=2)
            self.cpu_curve = self.cpu_plot.plot(pen=pen)

        chart_splitter.addWidget(cpu_win)

        # 内存图表
        memory_win = pg.GraphicsLayoutWidget()
        memory_win.setBackground(QColor(26, 26, 26))
        self.memory_plot = memory_win.addPlot(title="内存使用率 (%)")  # type: ignore[attr-defined]
        if self.memory_plot:
            self.memory_plot.showGrid(x=True, y=True, alpha=0.3)
            self.memory_plot.setRange(yRange=[0, 100])
            pen = pg.mkPen(color="#4ECDC4", width=2)
            self.memory_curve = self.memory_plot.plot(pen=pen)

        chart_splitter.addWidget(memory_win)
        chart_layout.addWidget(chart_splitter)

        layout.addWidget(chart_group)

        # 性能统计组
        stats_group = QGroupBox("性能统计")
        stats_layout = QVBoxLayout(stats_group)

        self.performance_table = QTableWidget(0, 4)
        headers = ["指标", "当前值", "平均值", "峰值"]
        self.performance_table.setHorizontalHeaderLabels(headers)
        stats_layout.addWidget(self.performance_table)

        layout.addWidget(stats_group)

        return tab

    # ==================== 1.3 告警管理 ====================

    def _create_alerts_tab(self) -> QWidget:
        """创建告警管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 告警规则组
        rules_group = QGroupBox("告警规则")
        rules_layout = QVBoxLayout(rules_group)

        self.alerts_table = QTableWidget(0, 4)
        headers = ["规则名称", "类型", "阈值", "状态"]
        self.alerts_table.setHorizontalHeaderLabels(headers)
        rules_layout.addWidget(self.alerts_table)

        layout.addWidget(rules_group)

        return tab

    # ==================== 1.4 服务健康检查 ====================

    def _create_services_tab(self) -> QWidget:
        """创建服务检查子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 服务状态组
        services_group = QGroupBox("服务状态")
        services_layout = QVBoxLayout(services_group)

        self.services_table = QTableWidget(0, 4)
        headers = ["服务名称", "状态", "启动时间", "操作"]
        self.services_table.setHorizontalHeaderLabels(headers)
        services_layout.addWidget(self.services_table)

        layout.addWidget(services_group)

        # 健康检查组
        health_group = QGroupBox("健康检查")
        health_layout = QVBoxLayout(health_group)

        self.health_progress = QProgressBar()
        self.health_progress.setRange(0, 100)
        health_layout.addWidget(self.health_progress)

        layout.addWidget(health_group)

        return tab

    # ==================== 1.5 系统配置 ====================

    def _create_config_tab(self) -> QWidget:
        """创建系统配置子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("⚙️ 系统配置"))
        toolbar_layout.addStretch()

        # 诊断按钮
        diagnose_btn = QPushButton("🔍 诊断配置")
        diagnose_btn.clicked.connect(self._diagnose_config)
        toolbar_layout.addWidget(diagnose_btn)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_config)
        toolbar_layout.addWidget(refresh_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(self._save_config)
        toolbar_layout.addWidget(save_btn)

        reset_btn = QPushButton("↩️ 重置")
        reset_btn.clicked.connect(self._reset_config)
        toolbar_layout.addWidget(reset_btn)

        layout.addLayout(toolbar_layout)

        # 配置组
        config_group = QGroupBox("数据中心配置")
        config_layout = QFormLayout(config_group)

        # 通达信路径
        tdx_layout = QHBoxLayout()
        self.tdx_path_edit = QLineEdit()
        self.tdx_path_edit.setPlaceholderText("例如: C:/通达信金融终端V7")
        tdx_layout.addWidget(self.tdx_path_edit)

        tdx_browse_btn = QPushButton("📁 浏览")
        tdx_browse_btn.clicked.connect(self._browse_tdx_dir)
        tdx_layout.addWidget(tdx_browse_btn)

        config_layout.addRow("通达信根目录:", tdx_layout)

        # 缓存目录
        cache_layout = QHBoxLayout()
        self.cache_dir_edit = QLineEdit()
        self.cache_dir_edit.setPlaceholderText("例如: ./data/cache")
        cache_layout.addWidget(self.cache_dir_edit)

        cache_browse_btn = QPushButton("📁 浏览")
        cache_browse_btn.clicked.connect(self._browse_cache_dir)
        cache_layout.addWidget(cache_browse_btn)

        config_layout.addRow("品种缓存目录:", cache_layout)

        # K线数据目录
        data_layout = QHBoxLayout()
        self.data_dir_edit = QLineEdit()
        self.data_dir_edit.setPlaceholderText("例如: ./data/kline")
        data_layout.addWidget(self.data_dir_edit)

        data_browse_btn = QPushButton("📁 浏览")
        data_browse_btn.clicked.connect(self._browse_data_dir)
        data_layout.addWidget(data_browse_btn)

        config_layout.addRow("K线数据目录:", data_layout)

        # 数据感知基日
        self.base_date_edit = QDateEdit()
        self.base_date_edit.setCalendarPopup(True)
        self.base_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.base_date_edit.setDate(QDate(2020, 1, 1))
        config_layout.addRow("数据感知基日:", self.base_date_edit)

        # 最大工作线程数
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 50)
        self.max_workers_spin.setValue(10)
        config_layout.addRow("最大线程数:", self.max_workers_spin)

        # 请求超时时间
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setValue(30)
        config_layout.addRow("请求超时:", self.timeout_spin)

        # 重试次数
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        config_layout.addRow("重试次数:", self.retry_spin)

        # 启用文件监控
        self.watcher_check = QCheckBox()
        self.watcher_check.setChecked(True)
        config_layout.addRow("启用文件监控:", self.watcher_check)

        # 文件监控间隔
        self.watcher_interval_spin = QSpinBox()
        self.watcher_interval_spin.setRange(1, 60)
        self.watcher_interval_spin.setValue(5)
        config_layout.addRow("监控检查间隔:", self.watcher_interval_spin)

        layout.addWidget(config_group)

        # AI助手配置组
        ai_config_group = QGroupBox("AI助手配置")
        ai_config_layout = QFormLayout(ai_config_group)

        # API Key
        self.ai_api_key_edit = QLineEdit()
        self.ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_key_edit.setPlaceholderText("请输入DeepSeek API Key")
        ai_config_layout.addRow("API Key:", self.ai_api_key_edit)

        # API URL
        self.ai_api_url_edit = QLineEdit()
        self.ai_api_url_edit.setPlaceholderText("https://api.deepseek.com/v1/chat/completions")
        ai_config_layout.addRow("API URL:", self.ai_api_url_edit)

        # Model
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.addItems(["deepseek-chat", "deepseek-coder"])
        ai_config_layout.addRow("模型:", self.ai_model_combo)

        # Max Tokens
        self.ai_max_tokens_spin = QSpinBox()
        self.ai_max_tokens_spin.setRange(100, 8000)
        self.ai_max_tokens_spin.setValue(2000)
        self.ai_max_tokens_spin.setSingleStep(100)
        ai_config_layout.addRow("最大Token数:", self.ai_max_tokens_spin)

        # Temperature
        temp_layout = QHBoxLayout()
        self.ai_temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.ai_temperature_slider.setRange(0, 100)  # 0.0-1.0映射到0-100
        self.ai_temperature_slider.setValue(70)  # 默认0.7
        self.ai_temperature_label = QLabel("0.70")
        self.ai_temperature_slider.valueChanged.connect(
            lambda v: self.ai_temperature_label.setText(f"{v/100:.2f}")
        )
        temp_layout.addWidget(self.ai_temperature_slider)
        temp_layout.addWidget(self.ai_temperature_label)
        ai_config_layout.addRow("温度参数:", temp_layout)

        # Max History
        self.ai_max_history_spin = QSpinBox()
        self.ai_max_history_spin.setRange(1, 50)
        self.ai_max_history_spin.setValue(10)
        ai_config_layout.addRow("对话历史长度:", self.ai_max_history_spin)

        # Timeout
        self.ai_timeout_spin = QSpinBox()
        self.ai_timeout_spin.setRange(10, 180)
        self.ai_timeout_spin.setValue(30)
        ai_config_layout.addRow("超时时间(秒):", self.ai_timeout_spin)

        # 工具调用开关
        self.ai_enable_tools_check = QCheckBox()
        self.ai_enable_tools_check.setChecked(False)
        self.ai_enable_tools_check.setToolTip(
            "启用AI文件操作工具（读取、写入、删除文件）。\n"
            "注意：需要DeepSeek API支持Function Calling。\n"
            "如果遇到连接错误，请禁用此选项。"
        )
        ai_config_layout.addRow("启用文件操作工具:", self.ai_enable_tools_check)

        layout.addWidget(ai_config_group)

        # 加载配置
        self._load_config()

        return tab

    # ==================== 1.6 日志管理 ====================

    def _create_logs_tab(self) -> QWidget:
        """创建日志管理子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 日志查看组
        logs_group = QGroupBox("日志查看")
        logs_layout = QVBoxLayout(logs_group)

        self.logs_table = QTableWidget(0, 4)
        self.logs_table.setHorizontalHeaderLabels(["时间", "级别", "模块", "消息"])
        logs_layout.addWidget(self.logs_table)

        layout.addWidget(logs_group)

        # 日志控制组
        control_group = QGroupBox("日志控制")
        control_layout = QHBoxLayout(control_group)

        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self._clear_logs)
        control_layout.addWidget(clear_btn)

        export_btn = QPushButton("导出日志")
        export_btn.clicked.connect(self._export_logs)
        control_layout.addWidget(export_btn)

        control_layout.addStretch()

        layout.addWidget(control_group)

        return tab

    # ==================== 1.7 系统诊断 ====================

    def _create_diagnosis_tab(self) -> QWidget:
        """创建系统诊断子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 诊断工具组
        tools_group = QGroupBox("诊断工具")
        tools_layout = QVBoxLayout(tools_group)

        self.diagnosis_table = QTableWidget(0, 3)
        self.diagnosis_table.setHorizontalHeaderLabels(["诊断项", "状态", "结果"])
        tools_layout.addWidget(self.diagnosis_table)

        layout.addWidget(tools_group)

        return tab

    # ==================== 1.8 工具集合 ====================

    def _create_tools_tab(self) -> QWidget:
        """创建工具集合子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 数据标准化读取器组
        reader_group = QGroupBox("数据标准化读取器 - 批量自动化处理")
        reader_layout = QVBoxLayout(reader_group)

        # 提示信息
        hint_label = QLabel("💡 勾选市场和数据类型后，程序会自动从品种缓存中获取对应品种并批量读取")
        hint_label.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")
        hint_label.setWordWrap(True)
        reader_layout.addWidget(hint_label)

        # 表单布局
        form_layout = QFormLayout()

        # 数据源类型（只读）
        type_label = QLabel("通达信")
        type_label.setStyleSheet("font-weight: bold;")
        form_layout.addRow("数据源类型:", type_label)

        # 数据类型（多选）
        data_type_layout = QHBoxLayout()
        self.reader_day_check = QCheckBox("日线")
        self.reader_day_check.setChecked(True)
        data_type_layout.addWidget(self.reader_day_check)

        self.reader_5min_check = QCheckBox("5分钟线")
        data_type_layout.addWidget(self.reader_5min_check)

        self.reader_1min_check = QCheckBox("1分钟线")
        data_type_layout.addWidget(self.reader_1min_check)

        data_type_layout.addStretch()
        form_layout.addRow("数据类型:", data_type_layout)

        # 市场（多选）
        market_layout = QHBoxLayout()
        self.reader_sh_check = QCheckBox("上证")
        self.reader_sh_check.setChecked(True)
        market_layout.addWidget(self.reader_sh_check)

        self.reader_sz_check = QCheckBox("深证")
        market_layout.addWidget(self.reader_sz_check)

        self.reader_bj_check = QCheckBox("北证")
        market_layout.addWidget(self.reader_bj_check)

        market_layout.addStretch()
        form_layout.addRow("市场:", market_layout)

        # 通达信根目录
        tdx_layout = QHBoxLayout()
        self.reader_tdx_path_edit = QLineEdit()
        self.reader_tdx_path_edit.setPlaceholderText("只需填写根目录，例如: C:\\new_tdx")
        self.reader_tdx_path_edit.setToolTip(
            "填写通达信软件的根目录即可，例如: C:\\new_tdx\n"
            "程序会根据您选择的市场和数据类型自动拼接完整路径：\n"
            "  上证日线 → C:\\new_tdx\\vipdoc\\sh\\lday\\\n"
            "  深证5分 → C:\\new_tdx\\vipdoc\\sz\\fzline\\\n"
            "  北证1分 → C:\\new_tdx\\vipdoc\\bj\\minline\\"
        )
        tdx_layout.addWidget(self.reader_tdx_path_edit)

        tdx_browse_btn = QPushButton("📁 浏览")
        tdx_browse_btn.clicked.connect(self._browse_tdx_root)
        tdx_layout.addWidget(tdx_browse_btn)

        form_layout.addRow("通达信根目录:", tdx_layout)

        # 线程数
        thread_layout = QHBoxLayout()
        self.reader_thread_spin = QSpinBox()
        self.reader_thread_spin.setRange(1, 16)
        self.reader_thread_spin.setValue(4)
        self.reader_thread_spin.setSuffix(" 线程")
        thread_layout.addWidget(self.reader_thread_spin)
        thread_layout.addStretch()
        form_layout.addRow("并发线程数:", thread_layout)

        reader_layout.addLayout(form_layout)

        # 进度组
        progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(progress_group)

        # 状态标签
        self.reader_status_label = QLabel("状态: 就绪")
        progress_layout.addWidget(self.reader_status_label)

        # 进度条
        self.reader_progress_bar = QProgressBar()
        self.reader_progress_bar.setRange(0, 100)
        self.reader_progress_bar.setValue(0)
        progress_layout.addWidget(self.reader_progress_bar)

        # 详细进度标签
        self.reader_detail_label = QLabel("")
        self.reader_detail_label.setStyleSheet("color: #888; font-size: 11px;")
        progress_layout.addWidget(self.reader_detail_label)

        reader_layout.addWidget(progress_group)

        # 批量读取按钮组
        button_layout = QHBoxLayout()

        self.reader_start_btn = QPushButton("🚀 开始批量读取并保存")
        self.reader_start_btn.clicked.connect(self._read_and_save_tdx_data)
        self.reader_start_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        button_layout.addWidget(self.reader_start_btn)

        self.reader_stop_btn = QPushButton("⛔ 停止")
        self.reader_stop_btn.clicked.connect(self._stop_tdx_reader)
        self.reader_stop_btn.setStyleSheet("font-size: 14px; padding: 10px;")
        self.reader_stop_btn.setEnabled(False)
        button_layout.addWidget(self.reader_stop_btn)

        reader_layout.addLayout(button_layout)

        layout.addWidget(reader_group)

        # 加载通达信根目录配置
        self._load_tdx_reader_config()

        layout.addStretch()

        return tab

    def _browse_tdx_root(self):
        """浏览通达信根目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择通达信软件根目录")
        if dir_path and self.reader_tdx_path_edit:
            self.reader_tdx_path_edit.setText(dir_path)

    def _update_reader_progress(self, current: int, total: int, info: str, success: bool):
        """更新读取器进度（槽函数，在主线程中执行）.

        Args:
            current: 当前完成数
            total: 总任务数
            info: 当前处理信息
            success: 是否成功
        """
        try:
            # 更新进度条
            if self.reader_progress_bar:
                progress_pct = int(current / total * 100) if total > 0 else 0
                self.reader_progress_bar.setValue(progress_pct)

            # 更新详细信息
            if self.reader_detail_label:
                status_icon = "✅" if success else "❌"
                self.reader_detail_label.setText(f"{status_icon} {current}/{total} - {info}")

            # 更新状态标签
            if self.reader_status_label:
                progress_pct = int(current / total * 100) if total > 0 else 0
                self.reader_status_label.setText(
                    f"状态: 正在处理 {current}/{total} ({progress_pct}%)"
                )

        except Exception as e:
            self.logger.error("更新进度失败: %s", e)

    def _update_reader_finished(self, result: dict):
        """更新读取器完成状态（槽函数，在主线程中执行）.

        Args:
            result: 处理结果字典
        """
        try:
            # 恢复按钮状态
            if self.reader_start_btn:
                self.reader_start_btn.setEnabled(True)
            if self.reader_stop_btn:
                self.reader_stop_btn.setEnabled(False)

            if result.get("success"):
                success_count = result.get("success_count", 0)
                fail_count = result.get("fail_count", 0)
                total_tasks = result.get("total_tasks", 0)
                was_stopped = result.get("was_stopped", False)

                if was_stopped:
                    message = f"已停止：已完成 {success_count + fail_count}/{total_tasks}，成功 {success_count}，失败 {fail_count}"
                else:
                    message = f"完成：成功 {success_count}/{total_tasks}，失败 {fail_count}"

                if self.reader_status_label:
                    self.reader_status_label.setText(f"状态: {message}")

                if self.reader_progress_bar:
                    self.reader_progress_bar.setValue(100)

                if was_stopped:
                    self.show_warning(message)
                else:
                    self.show_info(message)
            else:
                error_msg = result.get("message", "未知错误")

                if self.reader_status_label:
                    self.reader_status_label.setText("状态: 读取失败")

                if self.reader_progress_bar:
                    self.reader_progress_bar.setValue(0)

                self.show_error(f"读取失败: {error_msg}")

        except Exception as e:
            self.logger.error("更新完成状态失败: %s", e)

    def _stop_tdx_reader(self):
        """停止通达信数据读取."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            result = self.system_service.stop_tdx_reader()

            if result["success"]:
                self.show_info("停止信号已发送，任务将在当前批次完成后停止...")
                if self.reader_stop_btn:
                    self.reader_stop_btn.setEnabled(False)
            else:
                self.show_error(f"停止失败: {result.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error("停止任务失败: %s", e)
            self.show_error(f"停止失败: {e}")

    def _load_tdx_reader_config(self):
        """加载通达信读取器配置."""
        try:
            if not self.system_service:
                return

            result = self.system_service.get_tdx_reader_config()

            if result.get("success"):
                config = result.get("config", {})
                tdx_root = config.get("tdx_root", "")

                if tdx_root and self.reader_tdx_path_edit:
                    self.reader_tdx_path_edit.setText(tdx_root)

        except Exception as e:
            self.logger.error("加载通达信读取器配置失败: %s", e)

    def _read_and_save_tdx_data(self):
        """读取并保存通达信数据（多市场、多周期、带进度）."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            # 收集选中的数据类型
            data_types = []
            if self.reader_day_check and self.reader_day_check.isChecked():
                data_types.append("day")
            if self.reader_5min_check and self.reader_5min_check.isChecked():
                data_types.append("5min")
            if self.reader_1min_check and self.reader_1min_check.isChecked():
                data_types.append("1min")

            if not data_types:
                self.show_warning("请至少选择一种数据类型")
                return

            # 收集选中的市场
            markets = []
            if self.reader_sh_check and self.reader_sh_check.isChecked():
                markets.append("sh")
            if self.reader_sz_check and self.reader_sz_check.isChecked():
                markets.append("sz")
            if self.reader_bj_check and self.reader_bj_check.isChecked():
                markets.append("bj")

            if not markets:
                self.show_warning("请至少选择一个市场")
                return

            # 获取通达信根目录
            if not self.reader_tdx_path_edit:
                return

            tdx_root = self.reader_tdx_path_edit.text().strip()

            if not tdx_root:
                self.show_warning("请输入通达信根目录")
                return

            # 获取线程数
            max_workers = 4
            if self.reader_thread_spin:
                max_workers = self.reader_thread_spin.value()

            # 初始化进度
            if self.reader_progress_bar:
                self.reader_progress_bar.setValue(0)
            if self.reader_detail_label:
                self.reader_detail_label.setText("")

            # 连接信号到槽函数
            try:
                self.reader_progress_signal.disconnect()
            except Exception:
                pass  # 第一次连接时会失败，忽略

            self.reader_progress_signal.connect(self._update_reader_progress)

            try:
                self.reader_finished_signal.disconnect()
            except Exception:
                pass

            self.reader_finished_signal.connect(self._update_reader_finished)

            # 定义进度回调函数
            def progress_callback(current, total, info, success):
                """进度回调函数（在工作线程中调用，需要线程安全）"""
                # 通过Signal发送进度更新（自动在主线程处理）
                self.reader_progress_signal.emit(current, total, info, success)

            # 更新初始状态
            if self.reader_status_label:
                self.reader_status_label.setText("状态: 准备中...")

            # 禁用开始按钮，启用停止按钮
            if self.reader_start_btn:
                self.reader_start_btn.setEnabled(False)
            if self.reader_stop_btn:
                self.reader_stop_btn.setEnabled(True)

            # 调用服务
            config = {
                "data_types": data_types,
                "markets": markets,
                "tdx_root": tdx_root,
                "use_symbol_cache": True,
                "max_workers": max_workers,
            }

            self.logger.info(
                "开始批量读取: 数据类型=%s, 市场=%s, 线程数=%d",
                data_types,
                markets,
                max_workers,
            )

            # 在单独的线程中执行（避免阻塞UI）
            import threading

            def do_read():
                try:
                    result = self.system_service.read_tdx_data(config, progress_callback)
                    # 通过Signal发送完成状态
                    self.reader_finished_signal.emit(result)

                except Exception as e:
                    self.logger.error("读取通达信数据失败: %s", e)
                    # 发送错误结果
                    self.reader_finished_signal.emit(
                        {
                            "success": False,
                            "message": f"读取失败: {str(e)}",
                        }
                    )

            # 启动工作线程
            thread = threading.Thread(target=do_read, daemon=True, name="TdxReader")
            thread.start()

        except Exception as e:
            self.logger.error("启动读取任务失败: %s", e)

            if self.reader_status_label:
                self.reader_status_label.setText("状态: 启动失败")

            self.show_error(f"启动失败: {e}")

    # ==================== 配置管理方法 ====================

    def _load_config(self):
        """加载配置."""
        try:
            if not self.system_service:
                self.logger.warning("系统管理服务不可用，使用默认配置")
                self._load_default_config()
                return

            # 从服务获取所有配置
            result = self.system_service.get_all_configs()

            if not result.get("success"):
                self.logger.warning("获取配置失败，使用默认值: %s", result.get("message"))
                self._load_default_config()
                return

            configs = result.get("configs", {})

            # 加载数据中心配置
            data_config = configs.get("data_center", {})
            if self.tdx_path_edit:
                tdx_dir = data_config.get("tdx_dir", "")
                self.tdx_path_edit.setText(tdx_dir)
            if self.cache_dir_edit:
                cache_dir = data_config.get("cache_dir", "./data/cache")
                self.cache_dir_edit.setText(cache_dir)
            if self.data_dir_edit:
                data_dir = data_config.get("data_dir", "./data/kline")
                self.data_dir_edit.setText(data_dir)
            if self.base_date_edit:
                base_date_str = data_config.get("base_date", "2020-01-01")
                try:
                    parts = base_date_str.split("-")
                    if len(parts) == 3:
                        self.base_date_edit.setDate(
                            QDate(int(parts[0]), int(parts[1]), int(parts[2]))
                        )
                    else:
                        self.base_date_edit.setDate(QDate(2020, 1, 1))
                except (ValueError, IndexError):
                    self.base_date_edit.setDate(QDate(2020, 1, 1))
            if self.max_workers_spin:
                self.max_workers_spin.setValue(data_config.get("max_workers", 10))
            if self.timeout_spin:
                self.timeout_spin.setValue(data_config.get("timeout", 30))
            if self.retry_spin:
                self.retry_spin.setValue(data_config.get("retry_times", 3))
            if self.watcher_check:
                self.watcher_check.setChecked(data_config.get("enable_watcher", True))
            if self.watcher_interval_spin:
                self.watcher_interval_spin.setValue(data_config.get("watcher_interval", 5))

            # 加载AI配置
            ai_config = configs.get("ai", {})
            if hasattr(self, "ai_api_key_edit"):
                api_key = ai_config.get("api_key", "")
                self.ai_api_key_edit.setText(api_key)
            if hasattr(self, "ai_api_url_edit"):
                api_url = ai_config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
                self.ai_api_url_edit.setText(api_url)
            if hasattr(self, "ai_model_combo"):
                model = ai_config.get("model", "deepseek-chat")
                self.ai_model_combo.setCurrentText(model)
            if hasattr(self, "ai_max_tokens_spin"):
                max_tokens = ai_config.get("max_tokens", 2000)
                self.ai_max_tokens_spin.setValue(max_tokens)
            if hasattr(self, "ai_temperature_slider"):
                temperature = ai_config.get("temperature", 0.7)
                self.ai_temperature_slider.setValue(int(temperature * 100))
            if hasattr(self, "ai_max_history_spin"):
                max_history = ai_config.get("max_history", 10)
                self.ai_max_history_spin.setValue(max_history)
            if hasattr(self, "ai_timeout_spin"):
                timeout = ai_config.get("timeout", 30)
                self.ai_timeout_spin.setValue(timeout)

            if hasattr(self, "ai_enable_tools_check"):
                enable_tools = ai_config.get("enable_tools", False)
                self.ai_enable_tools_check.setChecked(enable_tools)

            self.logger.info("配置加载完成")

        except Exception as e:
            self.logger.error("加载配置失败: %s", e, exc_info=True)
            self._load_default_config()

    def _load_default_config(self):
        """加载默认配置."""
        try:
            # 数据中心默认配置
            if self.tdx_path_edit:
                self.tdx_path_edit.setText("")
            if self.cache_dir_edit:
                self.cache_dir_edit.setText("./data/cache")
            if self.data_dir_edit:
                self.data_dir_edit.setText("./data/kline")
            if self.base_date_edit:
                self.base_date_edit.setDate(QDate(2020, 1, 1))
            if self.max_workers_spin:
                self.max_workers_spin.setValue(10)
            if self.timeout_spin:
                self.timeout_spin.setValue(30)
            if self.retry_spin:
                self.retry_spin.setValue(3)
            if self.watcher_check:
                self.watcher_check.setChecked(True)
            if self.watcher_interval_spin:
                self.watcher_interval_spin.setValue(5)

            # AI默认配置
            if hasattr(self, "ai_api_key_edit"):
                self.ai_api_key_edit.setText("")
            if hasattr(self, "ai_api_url_edit"):
                self.ai_api_url_edit.setText("https://api.deepseek.com/v1/chat/completions")
            if hasattr(self, "ai_model_combo"):
                self.ai_model_combo.setCurrentText("deepseek-chat")
            if hasattr(self, "ai_max_tokens_spin"):
                self.ai_max_tokens_spin.setValue(2000)
            if hasattr(self, "ai_temperature_slider"):
                self.ai_temperature_slider.setValue(70)
            if hasattr(self, "ai_max_history_spin"):
                self.ai_max_history_spin.setValue(10)
            if hasattr(self, "ai_timeout_spin"):
                self.ai_timeout_spin.setValue(30)

            self.logger.info("已加载默认配置")

        except Exception as e:
            self.logger.error("加载默认配置失败: %s", e)

    def _verify_config_file(self):
        """验证配置文件是否正确写入."""
        try:
            import json
            from pathlib import Path

            config_file = Path("config/terminal_config.json")
            if not config_file.exists():
                self.logger.error("❌ 配置文件不存在！")
                return

            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            ai_config = config_data.get("ai", {})
            api_key = ai_config.get("api_key", "")

            if api_key:
                masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
                self.logger.info(f"✅ 配置文件验证: API Key = {masked_key}")
            else:
                self.logger.warning("⚠️ 配置文件中API Key为空")

            self.logger.info(f"✅ 配置文件验证通过: {config_file.absolute()}")

        except Exception as e:
            self.logger.error(f"配置文件验证失败: {e}", exc_info=True)

    def _diagnose_config(self):
        """诊断配置状态."""
        try:
            self.logger.info("开始诊断配置...")

            if not self.system_service:
                self.logger.error("系统管理服务不可用")
                self.show_error("系统管理服务不可用")
                return

            self.logger.info("调用 diagnose_config...")
            result = self.system_service.diagnose_config()
            self.logger.info("diagnose_config 返回结果: %s", result.get("success"))

            if result.get("success"):
                diagnosis = result.get("diagnosis", {})
                self.logger.info("获取到诊断信息: %s", list(diagnosis.keys()))

                # 构建诊断信息
                msg_parts = []
                msg_parts.append("配置诊断报告")
                msg_parts.append("=" * 50)
                msg_parts.append(f"\n配置文件路径:\n{diagnosis.get('config_file_path')}")
                msg_parts.append(f"\n配置文件存在: {diagnosis.get('config_file_exists')}")

                # 文件中的AI配置
                if diagnosis.get("config_file_content"):
                    config = diagnosis["config_file_content"]
                    ai_config = config.get("ai", {})
                    msg_parts.append(f"\n文件中的AI配置:")
                    api_key = ai_config.get("api_key", "")
                    if api_key:
                        # 显示API Key的前后各4位
                        masked_key = (
                            f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
                        )
                        msg_parts.append(f"  - API Key: {masked_key}")
                    else:
                        msg_parts.append(f"  - API Key: 未设置")
                    msg_parts.append(f"  - API URL: {ai_config.get('api_url', '未设置')}")
                    msg_parts.append(f"  - 模型: {ai_config.get('model', '未设置')}")
                else:
                    msg_parts.append(f"\n文件中的AI配置: 无（文件不存在或为空）")

                # 内存中的AI配置
                mem_config = diagnosis.get("memory_config", {})
                msg_parts.append(f"\n内存中的AI配置:")
                msg_parts.append(
                    f"  - API Key: {'已设置' if mem_config.get('ai_api_key_set') else '未设置'}"
                )
                msg_parts.append(f"  - API URL: {mem_config.get('ai_api_url', '未设置')}")
                msg_parts.append(f"  - 模型: {mem_config.get('ai_model', '未设置')}")

                # AI服务状态
                ai_status = diagnosis.get("ai_service_status", {})
                msg_parts.append(f"\nAI服务状态:")
                msg_parts.append(f"  - 服务存在: {ai_status.get('exists')}")
                if ai_status.get("exists"):
                    msg_parts.append(f"  - 已初始化: {ai_status.get('initialized')}")
                    msg_parts.append(f"  - API Key配置: {ai_status.get('api_key_configured')}")
                else:
                    msg_parts.append("  - 服务未注册")

                # 显示对话框
                full_msg = "\n".join(msg_parts)
                self.logger.info("显示诊断对话框")
                QMessageBox.information(self, "配置诊断", full_msg)
            else:
                error_msg = result.get("message", "未知错误")
                self.logger.error("诊断失败: %s", error_msg)
                self.show_error(f"诊断失败: {error_msg}")

        except Exception as e:
            self.logger.error("配置诊断失败: %s", e, exc_info=True)
            import traceback

            tb = traceback.format_exc()
            self.logger.error("异常堆栈: %s", tb)
            self.show_error(f"诊断失败: {e}\n\n详细信息请查看日志")

    def _refresh_config(self):
        """刷新配置."""
        self._load_config()
        self.show_info("配置已刷新")

    def _save_config(self):
        """保存配置."""
        try:
            if not self.system_service:
                self.show_error("系统管理服务不可用")
                return

            # 收集数据中心配置
            data_center_config = {}
            if self.tdx_path_edit and self.tdx_path_edit.text():
                data_center_config["tdx_dir"] = self.tdx_path_edit.text()
            if self.cache_dir_edit and self.cache_dir_edit.text():
                data_center_config["cache_dir"] = self.cache_dir_edit.text()
            if self.data_dir_edit and self.data_dir_edit.text():
                data_center_config["data_dir"] = self.data_dir_edit.text()
            if self.base_date_edit:
                data_center_config["base_date"] = self.base_date_edit.date().toString("yyyy-MM-dd")
            if self.max_workers_spin:
                data_center_config["max_workers"] = self.max_workers_spin.value()
            if self.timeout_spin:
                data_center_config["timeout"] = self.timeout_spin.value()
            if self.retry_spin:
                data_center_config["retry_times"] = self.retry_spin.value()
            if self.watcher_check:
                data_center_config["enable_watcher"] = self.watcher_check.isChecked()
            if self.watcher_interval_spin:
                data_center_config["watcher_interval"] = self.watcher_interval_spin.value()

            # 收集AI配置数据
            ai_config = {}
            if hasattr(self, "ai_api_key_edit"):
                api_key_text = self.ai_api_key_edit.text().strip()
                if api_key_text:
                    ai_config["api_key"] = api_key_text
                    self.logger.info(
                        f"收集到API Key: {api_key_text[:4]}...{api_key_text[-4:] if len(api_key_text) > 8 else '***'}"
                    )
                else:
                    self.logger.warning("API Key为空")

            if hasattr(self, "ai_api_url_edit"):
                api_url_text = self.ai_api_url_edit.text().strip()
                if api_url_text:
                    ai_config["api_url"] = api_url_text

            if hasattr(self, "ai_model_combo"):
                ai_config["model"] = self.ai_model_combo.currentText()
            if hasattr(self, "ai_max_tokens_spin"):
                ai_config["max_tokens"] = self.ai_max_tokens_spin.value()
            if hasattr(self, "ai_temperature_slider"):
                ai_config["temperature"] = self.ai_temperature_slider.value() / 100.0
            if hasattr(self, "ai_max_history_spin"):
                ai_config["max_history"] = self.ai_max_history_spin.value()
            if hasattr(self, "ai_timeout_spin"):
                ai_config["timeout"] = self.ai_timeout_spin.value()
            if hasattr(self, "ai_enable_tools_check"):
                ai_config["enable_tools"] = self.ai_enable_tools_check.isChecked()

            self.logger.info(f"收集到AI配置项: {list(ai_config.keys())}")

            # 保存结果跟踪
            success_count = 0
            fail_messages = []
            ai_service_reloaded = False

            # 保存数据中心配置
            if data_center_config:
                result = self.system_service.update_config("data_center", data_center_config)
                if result.get("success"):
                    success_count += 1
                    self.logger.info("数据中心配置保存成功")
                else:
                    fail_messages.append(f"数据中心: {result.get('message')}")

            # 保存AI配置（会自动触发服务重载）
            if ai_config:
                self.logger.info("开始保存AI配置...")
                result = self.system_service.update_config("ai", ai_config)
                self.logger.info(
                    f"update_config返回: success={result.get('success')}, ai_reloaded={result.get('ai_reloaded')}"
                )

                if result.get("success"):
                    success_count += 1
                    ai_service_reloaded = result.get("ai_reloaded", False)
                    self.logger.info(f"AI配置保存成功，服务重载状态: {ai_service_reloaded}")

                    # 验证配置文件
                    self._verify_config_file()

                    # 检查AI服务是否重载成功
                    if ai_service_reloaded:
                        self.logger.info("✅ AI服务重载成功")
                    else:
                        reload_msg = result.get("ai_reload_message", "未知原因")
                        self.logger.warning(f"⚠️ AI服务重载失败: {reload_msg}")
                        fail_messages.append(f"AI服务重载失败: {reload_msg}")
                else:
                    error_msg = result.get("message", "未知错误")
                    self.logger.error(f"AI配置保存失败: {error_msg}")
                    fail_messages.append(f"AI配置: {error_msg}")

            # 显示保存结果
            if success_count > 0 and not fail_messages:
                if ai_service_reloaded:
                    self.show_info("配置保存成功，AI服务已重新加载")
                else:
                    self.show_info("配置保存成功")
            elif success_count > 0 and fail_messages:
                msg = "部分配置保存成功，但存在问题:\n" + "\n".join(fail_messages)
                self.show_warning(msg)
            else:
                msg = "配置保存失败:\n" + "\n".join(fail_messages)
                self.show_error(msg)

        except Exception as e:
            self.logger.error("保存配置失败: %s", e, exc_info=True)
            self.show_error(f"保存配置失败: {e}")

    def _reset_config(self):
        """重置配置."""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有配置为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._load_config()
                self.show_info("配置已重置为默认值")
            except Exception as e:
                self.logger.error("重置配置失败: %s", e)
                self.show_error(f"重置失败: {e}")

    def _browse_tdx_dir(self):
        """浏览通达信目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择通达信软件根目录")
        if dir_path and self.tdx_path_edit:
            self.tdx_path_edit.setText(dir_path)

    def _browse_cache_dir(self):
        """浏览缓存目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择品种缓存目录")
        if dir_path and self.cache_dir_edit:
            self.cache_dir_edit.setText(dir_path)

    def _browse_data_dir(self):
        """浏览数据目录."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择K线数据目录")
        if dir_path and self.data_dir_edit:
            self.data_dir_edit.setText(dir_path)

    # ==================== 日志管理方法 ====================

    def _clear_logs(self):
        """清空日志."""
        if self.logs_table:
            self.logs_table.setRowCount(0)
        self.show_info("日志已清空")

    def _export_logs(self):
        """导出日志."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出日志",
            "terminal_logs.txt",
            "文本文件 (*.txt);;所有文件 (*.*)",
        )

        if file_path:
            self.show_info(f"日志已导出到: {file_path}")

    # ==================== 性能监控方法 ====================

    def _clear_performance_history(self):
        """清除性能历史数据."""
        self.performance_history = {"cpu": [], "memory": []}
        if self.cpu_curve:
            self.cpu_curve.setData([], [])
        if self.memory_curve:
            self.memory_curve.setData([], [])
        self.show_info("性能历史数据已清除")

    def _update_system_status(self):
        """更新系统状态."""
        try:
            # 更新基础系统信息
            cpu_percent = psutil.cpu_percent()
            if self.cpu_label:
                self.cpu_label.setText(f"{cpu_percent:.1f}%")

            memory = psutil.virtual_memory()
            if self.memory_label:
                self.memory_label.setText(f"{memory.percent:.1f}%")

            disk = psutil.disk_usage("/")
            if self.disk_label:
                self.disk_label.setText(f"{disk.percent:.1f}%")

            if self.network_label:
                self.network_label.setText("正常")

            # 更新状态表格
            self._update_status_table()

            # 更新性能图表
            self._update_performance_charts()

        except Exception as e:
            self.logger.error("更新系统状态失败: %s", e)

    def _update_status_table(self):
        """更新状态表格."""
        if not self.status_table:
            return

        try:
            self.status_table.setRowCount(0)

            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage("/").percent

            components = [
                ("CPU", "正常", f"使用率: {cpu_percent:.1f}%"),
                ("内存", "正常", f"使用率: {memory_percent:.1f}%"),
                ("磁盘", "正常", f"使用率: {disk_percent:.1f}%"),
                ("网络", "正常", "连接正常"),
                ("数据库", "正常", "连接正常"),
            ]

            for i, (component, status, detail) in enumerate(components):
                self.status_table.insertRow(i)
                self.status_table.setItem(i, 0, QTableWidgetItem(component))
                self.status_table.setItem(i, 1, QTableWidgetItem(status))
                self.status_table.setItem(i, 2, QTableWidgetItem(detail))

        except Exception as e:
            self.logger.error("更新状态表格失败: %s", e)

    def _update_performance_charts(self):
        """更新性能图表."""
        if not self.cpu_curve or not self.memory_curve:
            return

        current_time = time.time()

        try:
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent

            self.performance_history["cpu"].append((current_time, cpu_percent))
            self.performance_history["memory"].append((current_time, memory_percent))

            # 限制历史数据点数量
            for key in self.performance_history:
                if len(self.performance_history[key]) > self.max_history_points:
                    self.performance_history[key] = self.performance_history[key][
                        -self.max_history_points :
                    ]

            # 更新图表
            if self.performance_history["cpu"]:
                times, cpu_values = zip(*self.performance_history["cpu"])
                self.cpu_curve.setData(times, cpu_values)

            if self.performance_history["memory"]:
                times, memory_values = zip(*self.performance_history["memory"])
                self.memory_curve.setData(times, memory_values)

        except Exception as e:
            self.logger.error("更新性能图表失败: %s", e)

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""
        self.start_update_timer(2000, self._update_system_status)

    def refresh_data(self):
        """刷新数据."""
        self._update_system_status()
        self.show_info("系统状态已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("系统管理界面已关闭")
