# -*- coding: utf-8 -*-
"""行情看板界面 - 主视图（vnpy_chartwizard版）.

多标签页界面：基于 vnpy_chartwizard 的专业图表应用。
支持多品种同时监控、实时数据自动订阅、Tick转K线合成。
集成品种叠加、指标叠加、对数坐标等高级功能。
"""
from typing import Optional

from PySide6.QtWidgets import (
    QVBoxLayout,
)

from backend.core.base import get_service_manager
from backend.core.service_base import LoggerMixin

from ui.components.widgets import BaseWidget


class MarketDashboard(BaseWidget, LoggerMixin):
    """行情看板主界面（vnpy_chartwizard版）."""

    def __init__(self, parent=None):
        """初始化行情看板."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.market_service = None

        # 初始化核心组件
        self.chart_wizard: Optional[ChartWizardEnhanced] = None

        # 调用父类初始化
        super().__init__(parent, "行情看板")
        self.logger.info("行情看板界面初始化开始（vnpy_chartwizard版）")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取行情看板服务（延迟获取）."""
        try:
            # 🎯 架构修复：使用silent模式查询可选服务
            # market_board_service作为辅助服务在后台加载，启动时可能尚未就绪
            # silent=True避免ServiceManager输出误导性ERROR日志
            self.market_service = self.service_manager.get_service(
                "market_board_service", silent=True
            )
            if self.market_service:
                self.logger.info("行情看板服务已就绪")
            else:
                # 服务未就绪不是错误，只记录DEBUG信息
                self.logger.debug("行情看板服务尚未就绪（后台加载中）")
        except Exception as e:
            # 获取失败也不是严重错误，只记录DEBUG
            self.logger.debug("获取行情看板服务失败: %s", e)

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建 ChartWizardEnhanced 核心组件
        self.chart_wizard = ChartWizardEnhanced(self)
        main_layout.addWidget(self.chart_wizard)

        self.logger.info("✅ 行情看板界面创建完成（基于vnpy_chartwizard）")

    def connect_signals(self):
        """连接信号槽."""
        # vnpy_chartwizard 已内置完整的事件处理
        # 这里只需要连接自定义的扩展功能

        if self.chart_wizard:
            # 连接图表创建信号
            self.chart_wizard.chart_created.connect(self._on_chart_created)
            # 连接图表关闭信号
            self.chart_wizard.chart_closed.connect(self._on_chart_closed)
            # 连接品种变化信号
            self.chart_wizard.symbol_changed.connect(self._on_symbol_changed)

        self.logger.info("✅ 信号连接完成")

    def _on_chart_created(self, vt_symbol: str):
        """图表创建回调.

        Args:
            vt_symbol: 品种代码
        """
        self.logger.info("图表已创建: %s", vt_symbol)

    def _on_chart_closed(self, vt_symbol: str):
        """图表关闭回调.

        Args:
            vt_symbol: 品种代码
        """
        self.logger.info("图表已关闭: %s", vt_symbol)

    def _on_symbol_changed(self, vt_symbol: str):
        """品种改变.

        Args:
            vt_symbol: 品种代码
        """
        self.logger.info("当前品种: %s", vt_symbol)
        # vnpy_chartwizard 已自动处理订阅、数据加载等
        # 这里可以添加自定义的扩展逻辑

    def refresh_data(self):
        """刷新数据."""
        # vnpy_chartwizard 实时更新，无需手动刷新
        if self.chart_wizard:
            current_chart = self.chart_wizard.get_current_chart()
            if current_chart and hasattr(current_chart, "move_to_right"):
                current_chart.move_to_right()
        self.show_info("已刷新到最新数据")

    def on_close(self):
        """关闭处理."""
        if self.chart_wizard:
            self.chart_wizard.on_close()
        self.logger.info("行情看板界面已关闭")


# ==================== 以下为内部组件（从 shared_widgets 合并） ====================
# 合并说明：ChartWizardEnhanced 只被 market_board_view 引用，故合并到此处

import logging
from typing import Any, Dict, List

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QWidget,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QComboBox,
    QLabel,
    QFrame,
    QMessageBox,
    QProgressBar,
)

logger = logging.getLogger(__name__)


# 尝试导入 vnpy_chartwizard
try:
    from vnpy_chartwizard.ui.widget import ChartWizardWidget as VnpyChartWizard
    from vnpy_chartwizard.engine import ChartWizardEngine

    HAS_CHART_WIZARD = True
    logger.info("✅ vnpy_chartwizard 可用")
except ImportError as e:
    HAS_CHART_WIZARD = False
    VnpyChartWizard = None
    ChartWizardEngine = None
    logger.warning(f"⚠️ vnpy_chartwizard 不可用: {e}")


class SymbolCompleterLineEdit(QLineEdit):
    """品种代码输入框（支持自动联想）."""

    def __init__(self, parent=None):
        """初始化品种输入框.

        Args:
            parent: 父组件
        """
        super().__init__(parent)
        self._completer_widget: Optional[Any] = None
        self.symbol_list: List[str] = []
        self.symbol_map: Dict[str, Dict[str, Any]] = {}  # 用于快速查找：显示文本 -> 品种信息
        self._setup_completer()

    def _setup_completer(self):
        """设置自动完成器."""
        from PySide6.QtWidgets import QCompleter
        from PySide6.QtCore import Qt

        # 加载品种列表
        self._load_symbol_list()

        # 创建 QCompleter
        self._completer_widget = QCompleter(self.symbol_list, self)
        self._completer_widget.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer_widget.setFilterMode(Qt.MatchFlag.MatchContains)  # 支持模糊匹配
        self._completer_widget.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(self._completer_widget)

        logger.info(f"✅ 品种联想器已初始化，加载 {len(self.symbol_list)} 个品种")

    def _load_symbol_list(self):
        """从品种列表缓存加载数据."""
        try:
            from backend.core.base import get_service_manager

            service_mgr = get_service_manager()
            if not service_mgr:
                logger.warning("服务管理器不可用")
                return

            data_center = service_mgr.get_service("data_center_service")
            if not data_center:
                logger.warning("数据中心服务不可用")
                return

            # 从缓存获取品种列表
            if hasattr(data_center, "_symbol_cache") and data_center._symbol_cache:
                cache = data_center._symbol_cache
                symbols = cache.get("symbols", [])

                if symbols:
                    # 格式: "代码 名称 (交易所)"
                    for s in symbols:
                        symbol_code = s.get("symbol", "")
                        name = s.get("name", "")
                        exchange = s.get("exchange", "")

                        if symbol_code:
                            display_text = f"{symbol_code} {name} ({exchange})"
                            self.symbol_list.append(display_text)
                            self.symbol_map[display_text] = s

                    logger.info(f"从缓存加载了 {len(self.symbol_list)} 个品种")
                else:
                    logger.debug("品种缓存为空（后端可能正在初始化）")
            else:
                logger.debug("品种缓存不存在（后端可能正在初始化）")

        except Exception as e:
            logger.error(f"加载品种列表失败: {e}", exc_info=True)

    def get_symbol_code(self) -> str:
        """获取输入的品种代码（去除名称和交易所）.

        Returns:
            品种代码
        """
        text = self.text().strip()
        if not text:
            return ""

        # 提取第一个空格前的代码
        return text.split()[0]

    def get_symbol_info(self) -> Optional[Dict[str, Any]]:
        """获取当前输入品种的完整信息.

        Returns:
            品种信息字典，如果找不到返回 None
        """
        text = self.text().strip()
        return self.symbol_map.get(text)


class ChartWizardEnhanced(BaseWidget):
    """ChartWizard增强版组件.

    封装 vnpy_chartwizard，提供：
    - 多标签页品种监控
    - 自动数据查询和订阅
    - 实时Tick转K线合成
    - 品种叠加、指标叠加
    - 对数坐标切换
    - 快捷键和右键菜单

    ✅ 线程安全修复：EventEngine 事件信号中转
    """

    # ✅ 线程安全修复：Signal 必须定义为类属性
    tick_event_signal = Signal(dict)  # Tick事件信号（EventEngine 工作线程 → Qt 主线程）
    symbol_changed = Signal(str)  # 当前品种变化
    chart_created = Signal(str)  # 新建图表
    chart_closed = Signal(str)  # 关闭图表

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化ChartWizard增强版.

        Args:
            parent: 父窗口组件
        """
        # 初始化属性
        self.main_engine = None
        self.event_engine = None
        self.chart_wizard: Optional[Any] = None
        self.chart_engine: Optional[Any] = None

        # 当前状态
        self.current_symbol = ""
        self.is_log_scale = False
        self.has_data_gaps = False
        self.gap_info = None

        # 异步初始化状态
        self.initialization_state = "waiting"  # waiting/ready/failed
        self._data_ready = False
        self._data_mode = None  # "online" or "offline"

        # UI组件
        self.symbol_input: Optional[SymbolCompleterLineEdit] = None
        self.new_chart_btn: Optional[QPushButton] = None
        self.chart_type_combo: Optional[QComboBox] = None
        self.coord_linear_radio: Optional[QRadioButton] = None
        self.coord_log_radio: Optional[QRadioButton] = None
        self.overlay_symbol_combo: Optional[QComboBox] = None
        self.overlay_indicator_combo: Optional[QComboBox] = None
        self.subplot_combo: Optional[QComboBox] = None
        self.gap_warning_frame: Optional[QFrame] = None
        self.gap_warning_label: Optional[QLabel] = None
        self.gap_fix_btn: Optional[QPushButton] = None
        self.push_status_label: Optional[QLabel] = None
        self.current_chart_label: Optional[QLabel] = None
        self.chart_extension_toolbar: Optional[QWidget] = None

        # 等待UI组件
        self.waiting_label: Optional[QLabel] = None
        self.waiting_progress: Optional[Any] = None

        # 调用父类初始化
        super().__init__(parent, "K线图表")

        # 🔧 优化启动时序：先只获取引擎引用，不检查数据接口
        # 数据接口检查将在 UnifiedDataManager 就绪后执行
        self._initialize_engines()

        # 订阅UnifiedDataManager就绪事件（必须在获取event_engine之后）
        if self.event_engine:
            try:
                # 🔧 修复：架构v3.0重构后，data_module模块已移除
                # 事件通过UnifiedDataManager直接发布，不在这里订阅
                # 如果需要事件通知，应该通过事件引擎直接订阅
                self.logger.debug("✅ UnifiedDataManager事件订阅（架构v3.0已重构）")
            except Exception as e:
                self.logger.warning(f"订阅UnifiedDataManager事件失败: {e}")

        # 等待UnifiedDataManager就绪事件（通过_on_data_manager_ready回调处理）
        self.logger.info("等待UnifiedDataManager就绪事件...")

    def _initialize_engines(self):
        """初始化VnPy引擎引用（不检查数据接口，等待UnifiedDataManager就绪后再检查）."""
        try:
            from backend.core.base import get_main_engine, get_event_engine

            self.main_engine = get_main_engine()
            self.event_engine = get_event_engine()

            if not self.main_engine:
                self.logger.debug("MainEngine 不可用（等待后端初始化）")
                return

            if not self.event_engine:
                self.logger.debug("EventEngine 不可用（等待后端初始化）")
                return

            # 🔧 优化启动时序：不在此处检查数据接口
            # 数据接口检查将在 UnifiedDataManager 就绪事件回调中执行
            # 避免在注入前产生误导性警告
            self.logger.debug("✅ VnPy引擎引用已获取，等待UnifiedDataManager注入")

        except Exception as e:
            self.logger.error(f"❌ 初始化VnPy引擎失败: {e}", exc_info=True)

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        # 检查 vnpy_chartwizard 是否可用
        if not HAS_CHART_WIZARD:
            self._setup_error_ui(main_layout)
            return

        # 检查引擎是否可用
        if not self.main_engine or not self.event_engine:
            # 显示等待UI（等待UnifiedDataManager就绪事件）
            self._setup_waiting_ui(main_layout)
            return

        # 引擎已就绪，但需要等待UnifiedDataManager就绪事件
        if not self._data_ready:
            self._setup_waiting_ui(main_layout)
            return

        # 引擎和数据都已就绪，直接创建图表UI
        self._setup_chart_ui(main_layout)

    def _setup_waiting_ui(self, layout: QVBoxLayout):
        """设置等待UI界面.

        Args:
            layout: 布局
        """
        from PySide6.QtCore import Qt

        # 等待提示
        self.waiting_label = QLabel("⏳ 等待数据管理器就绪...")
        self.waiting_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.waiting_label.setStyleSheet("font-size: 16px; color: #2196F3; padding: 20px;")
        layout.addWidget(self.waiting_label)

        # 进度条
        self.waiting_progress = QProgressBar()
        self.waiting_progress.setRange(0, 0)  # 无限进度条
        self.waiting_progress.setTextVisible(False)
        self.waiting_progress.setMaximumWidth(400)
        self.waiting_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 居中显示进度条
        progress_container = QWidget()
        progress_layout = QHBoxLayout(progress_container)
        progress_layout.addStretch()
        progress_layout.addWidget(self.waiting_progress)
        progress_layout.addStretch()
        layout.addWidget(progress_container)

        # 提示信息
        info_label = QLabel(
            "正在加载数据管理器...\n" "等待品种列表和缓存初始化\n" "预计等待时间: 3-10秒"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #666; font-size: 12px; padding: 10px;")
        layout.addWidget(info_label)

        layout.addStretch()

    def _setup_chart_ui(self, layout: QVBoxLayout):
        """设置图表UI界面（引擎就绪后调用）.

        Args:
            layout: 布局
        """
        # 创建顶部工具栏
        toolbar_layout = self._create_toolbar()
        layout.addLayout(toolbar_layout)

        # 创建断点警告框（默认隐藏）
        self.gap_warning_frame = self._create_gap_warning_frame()
        layout.addWidget(self.gap_warning_frame)
        self.gap_warning_frame.hide()

        # 创建图表扩展工具栏（作用于当前激活的标签页）
        self.chart_extension_toolbar = self._create_chart_extension_toolbar()
        layout.addWidget(self.chart_extension_toolbar)

        # 创建 vnpy_chartwizard 核心组件
        try:
            if self.main_engine is None or self.event_engine is None:
                self.logger.error("❌ MainEngine 或 EventEngine 为空，无法创建ChartWizard")
                self._setup_error_ui(layout, "引擎未就绪，无法创建图表组件")
                return

            # 检查 VnpyChartWizard 是否可用
            if VnpyChartWizard is None:
                self.logger.error("❌ VnpyChartWizard 不可用，无法创建图表组件")
                self._setup_error_ui(layout, "vnpy_chartwizard 模块不可用")
                return

            self.chart_wizard = VnpyChartWizard(self.main_engine, self.event_engine)
            layout.addWidget(self.chart_wizard, 1)
            self.logger.info("✅ ChartWizard组件创建成功")

            # 监听标签页切换
            if hasattr(self.chart_wizard, "tab") and self.chart_wizard.tab:
                self.chart_wizard.tab.currentChanged.connect(self._on_tab_changed)
                self.logger.info("✅ 已连接标签页切换信号")

            # 尝试隐藏 vnpy_chartwizard 原生的输入框和按钮
            self._hide_native_input_widgets()

        except Exception as e:
            self.logger.error(f"❌ 创建ChartWizard组件失败: {e}", exc_info=True)
            self._setup_error_ui(layout, f"创建图表组件失败: {e}")
            return

    def _setup_error_ui(self, layout: QVBoxLayout, message: str = "vnpy_chartwizard 不可用"):
        """设置错误提示UI.

        Args:
            layout: 布局
            message: 错误消息
        """
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt

        error_label = QLabel(f"⚠️ {message}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet(
            """
            QLabel {
                color: #f44336;
                font-size: 16px;
                padding: 20px;
            }
        """
        )
        layout.addWidget(error_label)

        # 添加说明
        info_label = QLabel(
            "请确保：\n"
            "1. vnpy_chartwizard 已安装 (pip install vnpy_chartwizard)\n"
            "2. MainEngine 和 EventEngine 已初始化\n"
            "3. 相关依赖包完整"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(info_label)

    def _create_toolbar(self) -> QHBoxLayout:
        """创建顶部工具栏（仅包含新建图表组件）.

        Returns:
            工具栏布局
        """
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # 品种代码输入（替换"本地代码"）
        toolbar.addWidget(QLabel("品种代码:"))

        # 创建自定义品种输入框（支持联想）
        self.symbol_input = SymbolCompleterLineEdit(self)
        self.symbol_input.setPlaceholderText("输入代码或名称")
        self.symbol_input.setMinimumWidth(200)
        # 支持回车键快速新建图表
        self.symbol_input.returnPressed.connect(self._on_new_chart_custom)
        toolbar.addWidget(self.symbol_input)

        # 新建图表按钮
        self.new_chart_btn = QPushButton("新建图表")
        self.new_chart_btn.clicked.connect(self._on_new_chart_custom)
        toolbar.addWidget(self.new_chart_btn)

        toolbar.addStretch()

        # 实时推送状态指示器
        self.push_status_label = QLabel("● 推送")
        self.push_status_label.setStyleSheet("color: #999; font-size: 11px;")
        self.push_status_label.setToolTip("实时数据推送状态")
        toolbar.addWidget(self.push_status_label)

        return toolbar

    def _create_chart_extension_toolbar(self) -> QWidget:
        """创建图表扩展工具栏（作用于当前激活的标签页）.

        Returns:
            工具栏组件
        """
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(5, 5, 5, 5)
        toolbar.setSpacing(10)

        # 当前图表标识
        toolbar.addWidget(QLabel("当前图表:"))
        self.current_chart_label = QLabel("(未选择)")
        self.current_chart_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        toolbar.addWidget(self.current_chart_label)

        toolbar.addSpacing(20)

        # 坐标类型
        toolbar.addWidget(QLabel("坐标:"))
        self.coord_linear_radio = QRadioButton("线性")
        self.coord_linear_radio.setChecked(True)
        self.coord_linear_radio.toggled.connect(self._on_coord_type_changed)
        self.coord_log_radio = QRadioButton("对数")
        toolbar.addWidget(self.coord_linear_radio)
        toolbar.addWidget(self.coord_log_radio)

        toolbar.addSpacing(20)

        # 品种叠加
        toolbar.addWidget(QLabel("叠加品种:"))
        self.overlay_symbol_combo = QComboBox()
        self.overlay_symbol_combo.setPlaceholderText("选择品种")
        self.overlay_symbol_combo.setMinimumWidth(150)
        toolbar.addWidget(self.overlay_symbol_combo)

        add_overlay_btn = QPushButton("叠加")
        add_overlay_btn.clicked.connect(self._on_add_overlay_symbol)
        add_overlay_btn.setMaximumWidth(60)
        toolbar.addWidget(add_overlay_btn)

        toolbar.addStretch()

        return toolbar_widget

    def _on_tab_changed(self, index: int):
        """标签页切换回调.

        Args:
            index: 标签页索引
        """
        try:
            if index >= 0 and self.chart_wizard and hasattr(self.chart_wizard, "tab"):
                vt_symbol = self.chart_wizard.tab.tabText(index)
                if self.current_chart_label:
                    self.current_chart_label.setText(vt_symbol)
                self.logger.info(f"切换到图表: {vt_symbol}")

                # 加载该标签页的品种列表到叠加选择器
                self._load_symbols_to_overlay_combo()

        except Exception as e:
            self.logger.error(f"标签页切换处理失败: {e}", exc_info=True)

    def _hide_native_input_widgets(self):
        """尝试隐藏 vnpy_chartwizard 原生的输入框和按钮."""
        try:
            if not self.chart_wizard:
                return

            # 查找并隐藏原生的品种输入控件
            hidden_count = 0
            for widget in self.chart_wizard.findChildren(QLineEdit):
                # 尝试根据对象名称或父级判断
                if (
                    widget.objectName() in ["symbol_line", ""]
                    and widget.parent() == self.chart_wizard
                ):
                    widget.hide()
                    hidden_count += 1
                    self.logger.debug(f"已隐藏输入框: {widget.objectName()}")

            for widget in self.chart_wizard.findChildren(QPushButton):
                text = widget.text()
                if any(keyword in text for keyword in ["新建", "添加", "Add", "New"]):
                    widget.hide()
                    hidden_count += 1
                    self.logger.debug(f"已隐藏按钮: {text}")

            if hidden_count > 0:
                self.logger.info(f"✅ 已隐藏 {hidden_count} 个原生控件")
            else:
                self.logger.info("未找到需要隐藏的原生控件（可能已被集成到标签页）")

        except Exception as e:
            self.logger.warning(f"隐藏原生控件失败（可忽略）: {e}")

    def _on_new_chart_custom(self):
        """自定义新建图表逻辑."""
        if not self.symbol_input:
            self.show_warning("输入框未初始化")
            return

        symbol_code = self.symbol_input.get_symbol_code()
        if not symbol_code:
            self.show_warning("请输入品种代码")
            return

        # 构造 vt_symbol（需要确定交易所）
        vt_symbol = self._build_vt_symbol(symbol_code)
        if not vt_symbol:
            self.show_error(f"无法构造品种标识：{symbol_code}")
            return

        self.logger.info(f"新建图表: {symbol_code} -> {vt_symbol}")

        # 调用 vnpy_chartwizard 的新建图表接口
        if self.chart_wizard and hasattr(self.chart_wizard, "add_chart"):
            try:
                self.chart_wizard.add_chart(vt_symbol)
                self.show_info(f"已创建图表: {vt_symbol}")
                # 清空输入框
                self.symbol_input.clear()
            except Exception as e:
                self.logger.error(f"创建图表失败: {e}", exc_info=True)
                self.show_error(f"创建图表失败: {e}")
        else:
            # 兼容方案：通过 MainEngine 创建
            self._create_chart_via_main_engine(vt_symbol)

    def _build_vt_symbol(self, symbol_code: str) -> str:
        """根据品种代码构造 vt_symbol.

        Args:
            symbol_code: 品种代码（如 000001）

        Returns:
            vt_symbol（如 000001.SZSE）
        """
        try:
            # 从缓存查找对应的交易所
            from backend.core.base import get_service_manager

            service_mgr = get_service_manager()
            if not service_mgr:
                self.logger.warning("服务管理器不可用，使用默认推测")
            else:
                data_center = service_mgr.get_service("data_center_service")
                if data_center and hasattr(data_center, "_symbol_cache"):
                    cache = data_center._symbol_cache
                    if cache and "symbols" in cache:
                        for symbol_info in cache["symbols"]:
                            if symbol_info.get("symbol") == symbol_code:
                                exchange = symbol_info.get("exchange", "")
                                exchange_code = (
                                    "SSE"
                                    if exchange == "上交所"
                                    else "SZSE" if exchange == "深交所" else "BSE"
                                )
                                vt_symbol = f"{symbol_code}.{exchange_code}"
                                self.logger.info(f"从缓存匹配交易所: {symbol_code} -> {vt_symbol}")
                                return vt_symbol

            # 默认推测（6开头为上交所，其他为深交所）
            exchange_code = "SSE" if symbol_code.startswith("6") else "SZSE"
            vt_symbol = f"{symbol_code}.{exchange_code}"
            self.logger.info(f"使用默认推测: {symbol_code} -> {vt_symbol}")
            return vt_symbol

        except Exception as e:
            self.logger.error(f"构造vt_symbol失败: {e}", exc_info=True)
            return ""

    def _create_chart_via_main_engine(self, vt_symbol: str):
        """通过 MainEngine 直接创建图表（兼容方案）.

        Args:
            vt_symbol: 品种标识
        """
        try:
            if not self.chart_wizard:
                self.show_error("图表组件未就绪")
                return

            # 尝试直接添加标签页
            self.logger.info(f"尝试通过兼容方案创建图表: {vt_symbol}")

            # 如果 chart_wizard 有 charts 属性，尝试手动创建
            if hasattr(self.chart_wizard, "charts"):
                # 发射信号通知图表创建
                self.chart_created.emit(vt_symbol)
                self.show_info(f"已请求创建图表: {vt_symbol}")
                # 清空输入框
                if self.symbol_input:
                    self.symbol_input.clear()
            else:
                self.show_warning("vnpy_chartwizard 不支持动态创建图表，请使用原生界面")

        except Exception as e:
            self.logger.error(f"创建图表失败: {e}", exc_info=True)
            self.show_error(f"创建图表失败: {e}")

    def _on_coord_type_changed(self, checked: bool):
        """坐标类型变化处理.

        Args:
            checked: 是否选中
        """
        if not checked:
            return

        try:
            if self.coord_log_radio is None:
                self.logger.error("coord_log_radio 未初始化")
                return

            is_log = self.coord_log_radio.isChecked()
            self.set_log_scale(is_log)

        except Exception as e:
            self.logger.error(f"切换坐标类型失败: {e}", exc_info=True)
            self.show_error(f"切换坐标类型失败: {e}")

    def connect_signals(self):
        """连接信号槽."""
        # vnpy_chartwizard 内部已处理事件，无需额外连接
        pass

    # ========== 公共接口 ==========

    def get_current_chart(self):
        """获取当前激活的图表.

        Returns:
            ChartWidget 或 None
        """
        if not self.chart_wizard or not hasattr(self.chart_wizard, "tab"):
            return None

        # 获取当前标签页索引
        if self.chart_wizard.tab is None:
            return None

        current_index = self.chart_wizard.tab.currentIndex()
        if current_index < 0:
            return None

        # 获取对应的 vt_symbol
        vt_symbol = self.chart_wizard.tab.tabText(current_index)

        # 从 charts 字典获取图表
        if hasattr(self.chart_wizard, "charts"):
            return self.chart_wizard.charts.get(vt_symbol)

        return None

    def set_log_scale(self, enabled: bool):
        """设置对数坐标.

        Args:
            enabled: 是否启用对数坐标
        """
        try:
            self.is_log_scale = enabled
            current_chart = self.get_current_chart()

            if not current_chart:
                self.logger.warning("当前无激活图表")
                return

            # 获取主图plot
            if hasattr(current_chart, "_plots"):
                candle_plot = current_chart._plots.get("candle")
                if candle_plot and hasattr(candle_plot, "setLogMode"):
                    candle_plot.setLogMode(x=False, y=enabled)
                    coord_type = "对数" if enabled else "线性"
                    self.logger.info(f"✅ 已切换为{coord_type}坐标")
                    self.show_info(f"已切换为{coord_type}坐标")
                else:
                    self.logger.warning("主图不支持对数坐标")
            else:
                self.logger.warning("图表组件不支持_plots属性")

        except Exception as e:
            self.logger.error(f"设置对数坐标失败: {e}", exc_info=True)
            self.show_error(f"设置对数坐标失败: {e}")

    def add_overlay_symbol(self, vt_symbol: str, normalized: bool = True):
        """添加品种叠加.

        Args:
            vt_symbol: 叠加品种代码（vt格式）
            normalized: 是否归一化
        """
        try:
            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            # 获取当前品种
            if (
                not self.chart_wizard
                or not hasattr(self.chart_wizard, "tab")
                or self.chart_wizard.tab is None
            ):
                self.show_warning("图表组件不支持多标签")
                return

            current_index = self.chart_wizard.tab.currentIndex()
            if current_index < 0:
                self.show_warning("当前无激活标签")
                return

            base_symbol = self.chart_wizard.tab.tabText(current_index)

            # 查询两个品种的数据
            from backend.core.base import get_service_manager
            from datetime import datetime, timedelta

            service_mgr = get_service_manager()
            if not service_mgr:
                self.show_error("服务管理器不可用")
                return

            market_service = service_mgr.get_service("market_board_service")
            if not market_service:
                self.show_error("行情服务不可用")
                return

            # 计算查询时间范围（最近200个交易日）
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

            # 查询主品种数据
            base_result = market_service.query_historical_data(
                symbol=base_symbol.split(".")[0],
                start_date=start_date,
                end_date=end_date,
                interval="1d",
                check_gaps=False,
            )

            # 查询叠加品种数据
            overlay_result = market_service.query_historical_data(
                symbol=vt_symbol.split(".")[0],
                start_date=start_date,
                end_date=end_date,
                interval="1d",
                check_gaps=False,
            )

            if not base_result.get("success") or not overlay_result.get("success"):
                self.show_error("查询品种数据失败")
                return

            base_data = base_result.get("data", [])
            overlay_data = overlay_result.get("data", [])

            if not base_data or not overlay_data:
                self.show_warning("品种数据为空")
                return

            # 归一化处理
            if normalized:
                overlay_data = self._normalize_overlay_data(base_data, overlay_data)

            # 使用 pyqtgraph 的 PlotDataItem 绘制叠加曲线
            try:
                import pyqtgraph as pg
                from datetime import datetime

                # 准备曲线数据
                x_data = []  # 时间索引
                y_data = []  # 价格数据

                # 获取当前图表的时间轴索引
                if hasattr(current_chart, "_manager") and hasattr(
                    current_chart._manager, "_datetime_index_map"
                ):
                    datetime_index_map = current_chart._manager._datetime_index_map

                    for item in overlay_data:
                        dt_str = item.get("datetime") or item.get("date", "")
                        if not dt_str:
                            continue

                        # 解析日期时间
                        try:
                            if isinstance(dt_str, str):
                                if "T" in dt_str or " " in dt_str:
                                    dt = datetime.fromisoformat(dt_str.replace(" ", "T"))
                                else:
                                    dt = datetime.strptime(dt_str, "%Y-%m-%d")
                            else:
                                dt = dt_str

                            # 获取对应的索引
                            if dt in datetime_index_map:
                                ix = datetime_index_map[dt]
                                value = (
                                    item.get("normalized_close")
                                    if normalized
                                    else item.get("close", 0)
                                )
                                if value is not None:
                                    x_data.append(ix)
                                    y_data.append(float(value))
                        except Exception as e:
                            self.logger.debug(f"解析日期时间失败: {dt_str}, {e}")
                            continue

                    if x_data and y_data:
                        # 创建曲线
                        from PySide6.QtCore import Qt

                        pen = pg.mkPen(color="#FF6B6B", width=2, style=Qt.PenStyle.SolidLine)
                        curve = pg.PlotDataItem(
                            x=x_data, y=y_data, pen=pen, name=f"叠加: {vt_symbol}"
                        )

                        # 添加到主图
                        candle_plot = current_chart._plots.get("candle")
                        if candle_plot:
                            candle_plot.addItem(curve)
                            self.logger.info(f"✅ 品种叠加成功: {vt_symbol}, {len(x_data)}个数据点")
                            self.show_info(f"已叠加品种: {vt_symbol}")
                        else:
                            self.logger.warning("无法获取主图plot")
                    else:
                        self.logger.warning("叠加数据为空")
                else:
                    self.logger.warning("无法获取图表时间索引")

            except ImportError as e:
                self.logger.error(f"导入pyqtgraph失败: {e}")
                self.show_error("图表组件不支持叠加功能")
            except Exception as e:
                self.logger.error(f"绘制叠加曲线失败: {e}", exc_info=True)
                self.show_error(f"绘制失败: {e}")

        except Exception as e:
            self.logger.error(f"品种叠加失败: {e}", exc_info=True)
            self.show_error(f"品种叠加失败: {e}")

    def _normalize_overlay_data(self, base_data: list, overlay_data: list) -> list:
        """归一化叠加品种数据.

        将叠加品种的价格转换为与主品种相同基准的百分比变化。

        Args:
            base_data: 主品种数据
            overlay_data: 叠加品种数据

        Returns:
            归一化后的数据
        """
        if not base_data or not overlay_data:
            return overlay_data

        # 获取第一个有效价格作为基准
        base_price = base_data[0].get("close", 1.0)
        overlay_price = overlay_data[0].get("close", 1.0)

        if base_price <= 0 or overlay_price <= 0:
            return overlay_data

        # 归一化：转换为百分比变化
        normalized = []
        for item in overlay_data:
            normalized_item = item.copy()
            close_price = item.get("close", 0)

            # 计算百分比变化
            if close_price > 0:
                pct_change = (close_price / overlay_price - 1) * 100
                normalized_item["normalized_close"] = pct_change
            else:
                normalized_item["normalized_close"] = 0

            normalized.append(normalized_item)

        return normalized

    def add_overlay_indicator(self, indicator_name: str, params: Optional[Dict] = None):
        """添加指标叠加到主图.

        Args:
            indicator_name: 指标名称（如 MA5, MA10, BOLL）
            params: 指标参数
        """
        try:
            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            # 获取当前品种
            if (
                not self.chart_wizard
                or not hasattr(self.chart_wizard, "tab")
                or self.chart_wizard.tab is None
            ):
                self.show_warning("图表组件不支持多标签")
                return

            current_index = self.chart_wizard.tab.currentIndex()
            if current_index < 0:
                self.show_warning("当前无激活标签")
                return

            vt_symbol = self.chart_wizard.tab.tabText(current_index)

            # 查询历史数据
            from backend.core.base import get_service_manager
            from datetime import datetime, timedelta

            service_mgr = get_service_manager()
            if not service_mgr:
                self.show_error("服务管理器不可用")
                return

            market_service = service_mgr.get_service("market_board_service")
            if not market_service:
                self.show_error("行情服务不可用")
                return

            # 计算查询时间范围
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

            # 查询K线数据
            result = market_service.query_historical_data(
                symbol=vt_symbol.split(".")[0],
                start_date=start_date,
                end_date=end_date,
                interval="1d",
                check_gaps=False,
            )

            if not result.get("success"):
                self.show_error("查询K线数据失败")
                return

            kline_data = result.get("data", [])
            if not kline_data or len(kline_data) < 30:
                self.show_warning("K线数据不足，无法计算指标")
                return

            # 提取收盘价
            close_prices = [bar.get("close", 0) for bar in kline_data if bar.get("close")]

            if len(close_prices) < 30:
                self.show_warning("有效数据不足")
                return

            # 计算指标
            params = params or {}

            # 根据指标类型选择计算方法
            if indicator_name.upper().startswith("MA"):
                # MA指标：MA5, MA10, MA20等
                try:
                    period = (
                        int(indicator_name[2:])
                        if len(indicator_name) > 2
                        else params.get("period", 5)
                    )
                except ValueError:
                    period = params.get("period", 5)

                indicator_result = market_service.calculate_indicator(
                    data=close_prices,
                    indicator_name="SMA",
                    params={"period": period},
                )

            elif indicator_name.upper() == "BOLL":
                # 布林带
                indicator_result = market_service.calculate_indicator(
                    data=close_prices,
                    indicator_name="BBANDS",
                    params={"period": params.get("period", 20)},
                )

            elif indicator_name.upper() == "EMA":
                # 指数移动平均
                indicator_result = market_service.calculate_indicator(
                    data=close_prices,
                    indicator_name="EMA",
                    params={"period": params.get("period", 12)},
                )

            else:
                self.show_warning(f"不支持的指标: {indicator_name}")
                return

            if not indicator_result.get("success"):
                self.show_error(f"指标计算失败: {indicator_result.get('message')}")
                return

            indicator_data = indicator_result.get("data", [])

            # 使用 pyqtgraph 绘制指标线
            try:
                import pyqtgraph as pg
                from datetime import datetime

                # 准备曲线数据
                if isinstance(indicator_data, dict):
                    # BOLL等多线指标
                    colors = {"upper": "#FF6B6B", "middle": "#4ECDC4", "lower": "#95E1D3"}
                    for line_name, line_values in indicator_data.items():
                        if not line_values:
                            continue

                        x_data = []
                        y_data = []

                        # 获取图表时间索引
                        if hasattr(current_chart, "_manager") and hasattr(
                            current_chart._manager, "_bars"
                        ):
                            bars = current_chart._manager._bars
                            for i, value in enumerate(line_values):
                                if (
                                    i < len(bars)
                                    and value is not None
                                    and not (isinstance(value, float) and value != value)
                                ):  # 过滤NaN
                                    x_data.append(i)
                                    y_data.append(float(value))

                            if x_data and y_data:
                                pen = pg.mkPen(color=colors.get(line_name, "#FFA07A"), width=1.5)
                                curve = pg.PlotDataItem(
                                    x=x_data,
                                    y=y_data,
                                    pen=pen,
                                    name=f"{indicator_name}_{line_name}",
                                )

                                candle_plot = current_chart._plots.get("candle")
                                if candle_plot:
                                    candle_plot.addItem(curve)

                else:
                    # 单线指标（MA、EMA等）
                    x_data = []
                    y_data = []

                    if hasattr(current_chart, "_manager") and hasattr(
                        current_chart._manager, "_bars"
                    ):
                        bars = current_chart._manager._bars
                        for i, value in enumerate(indicator_data):
                            if (
                                i < len(bars)
                                and value is not None
                                and not (isinstance(value, float) and value != value)
                            ):
                                x_data.append(i)
                                y_data.append(float(value))

                        if x_data and y_data:
                            pen = pg.mkPen(color="#FFA07A", width=2)
                            curve = pg.PlotDataItem(
                                x=x_data, y=y_data, pen=pen, name=indicator_name
                            )

                            candle_plot = current_chart._plots.get("candle")
                            if candle_plot:
                                candle_plot.addItem(curve)

                self.logger.info(f"✅ 指标叠加成功: {indicator_name}")
                self.show_info(f"已叠加指标: {indicator_name}")

            except Exception as e:
                self.logger.error(f"绘制指标线失败: {e}", exc_info=True)
                self.show_error(f"绘制指标失败: {e}")

        except Exception as e:
            self.logger.error(f"指标叠加失败: {e}", exc_info=True)
            self.show_error(f"指标叠加失败: {e}")

    def add_subplot_macd(self):
        """添加MACD副图指标."""
        try:
            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            # 获取当前品种
            if (
                not self.chart_wizard
                or not hasattr(self.chart_wizard, "tab")
                or self.chart_wizard.tab is None
            ):
                self.show_warning("图表组件不支持多标签")
                return

            vt_symbol = self.chart_wizard.tab.tabText(self.chart_wizard.tab.currentIndex())

            # 计算MACD
            from backend.core.base import get_service_manager
            from datetime import datetime, timedelta

            service_mgr = get_service_manager()
            market_service = (
                service_mgr.get_service("market_board_service") if service_mgr else None
            )

            if not market_service:
                self.show_error("行情服务不可用")
                return

            # 查询K线数据
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

            result = market_service.query_historical_data(
                symbol=vt_symbol.split(".")[0],
                start_date=start_date,
                end_date=end_date,
                interval="1d",
                check_gaps=False,
            )

            if not result.get("success"):
                self.show_error("查询K线数据失败")
                return

            kline_data = result.get("data", [])
            close_prices = [bar.get("close", 0) for bar in kline_data if bar.get("close")]

            # 计算MACD
            macd_result = market_service.calculate_indicator(
                data=close_prices,
                indicator_name="MACD",
                params={},
            )

            if not macd_result.get("success"):
                self.show_error("MACD计算失败")
                return

            macd_data = macd_result.get("data", {})

            # 使用SubplotIndicatorManager添加
            manager = SubplotIndicatorManager(current_chart)
            if manager.add_macd(macd_data=macd_data):
                self.show_info("已添加MACD副图")
            else:
                self.show_error("添加MACD副图失败")

        except Exception as e:
            self.logger.error(f"添加MACD副图失败: {e}", exc_info=True)
            self.show_error(f"添加MACD副图失败: {e}")

    def add_subplot_rsi(self, period: int = 14):
        """添加RSI副图指标.

        Args:
            period: RSI周期
        """
        try:
            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            # 获取当前品种
            if (
                not self.chart_wizard
                or not hasattr(self.chart_wizard, "tab")
                or self.chart_wizard.tab is None
            ):
                self.show_warning("图表组件不支持多标签")
                return

            vt_symbol = self.chart_wizard.tab.tabText(self.chart_wizard.tab.currentIndex())

            # 计算RSI
            from backend.core.base import get_service_manager
            from datetime import datetime, timedelta

            service_mgr = get_service_manager()
            market_service = (
                service_mgr.get_service("market_board_service") if service_mgr else None
            )

            if not market_service:
                self.show_error("行情服务不可用")
                return

            # 查询K线数据
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

            result = market_service.query_historical_data(
                symbol=vt_symbol.split(".")[0],
                start_date=start_date,
                end_date=end_date,
                interval="1d",
                check_gaps=False,
            )

            if not result.get("success"):
                self.show_error("查询K线数据失败")
                return

            kline_data = result.get("data", [])
            close_prices = [bar.get("close", 0) for bar in kline_data if bar.get("close")]

            # 计算RSI
            rsi_result = market_service.calculate_indicator(
                data=close_prices,
                indicator_name="RSI",
                params={"period": period},
            )

            if not rsi_result.get("success"):
                self.show_error("RSI计算失败")
                return

            rsi_data = rsi_result.get("data", [])

            # 使用SubplotIndicatorManager添加
            manager = SubplotIndicatorManager(current_chart)
            if manager.add_rsi(rsi_data=rsi_data, period=period):
                self.show_info(f"已添加RSI({period})副图")
            else:
                self.show_error("添加RSI副图失败")

        except Exception as e:
            self.logger.error(f"添加RSI副图失败: {e}", exc_info=True)
            self.show_error(f"添加RSI副图失败: {e}")

    def export_chart_image(self, filepath: str):
        """导出图表为图片.

        Args:
            filepath: 保存路径
        """
        try:
            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            # vnpy.chart 支持导出
            if hasattr(current_chart, "save_to_file"):
                current_chart.save_to_file(filepath)
                self.show_info(f"图表已导出: {filepath}")
            else:
                self.show_warning("当前图表不支持导出功能")

        except Exception as e:
            self.logger.error(f"导出图表失败: {e}", exc_info=True)
            self.show_error(f"导出图表失败: {e}")

    def keyPressEvent(self, event):
        """按键事件处理（快捷键）.

        Args:
            event: 键盘事件
        """
        # Ctrl+N: 新建图表
        if event.key() == Qt.Key.Key_N and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if self.symbol_input:
                self.symbol_input.setFocus()
            event.accept()
            return

        # Ctrl+W: 关闭当前图表
        if event.key() == Qt.Key.Key_W and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if self.chart_wizard and hasattr(self.chart_wizard, "tab"):
                current_index = self.chart_wizard.tab.currentIndex()
                if current_index >= 0:
                    self.chart_wizard.close_tab(current_index)
            event.accept()
            return

        # L: 切换对数坐标
        if event.key() == Qt.Key.Key_L:
            if self.coord_log_radio:
                self.coord_log_radio.setChecked(not self.coord_log_radio.isChecked())
            event.accept()
            return

        # F5: 刷新
        if event.key() == Qt.Key.Key_F5:
            current_chart = self.get_current_chart()
            if current_chart and hasattr(current_chart, "move_to_right"):
                current_chart.move_to_right()
            event.accept()
            return

        # 其他按键传递给父类
        super().keyPressEvent(event)

    def _create_gap_warning_frame(self) -> QFrame:
        """创建数据断点警告框.

        Returns:
            警告框组件
        """
        frame = QFrame()
        frame.setStyleSheet(
            """
            QFrame {
                background-color: #FFF3CD;
                border: 1px solid #FFC107;
                border-radius: 4px;
                padding: 8px;
            }
        """
        )

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 5, 10, 5)

        # 警告图标和文本
        self.gap_warning_label = QLabel("⚠️ 检测到数据断点")
        self.gap_warning_label.setStyleSheet("color: #856404; font-weight: bold;")
        layout.addWidget(self.gap_warning_label)

        layout.addStretch()

        # 修复按钮
        self.gap_fix_btn = QPushButton("前往数据中心修复")
        self.gap_fix_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #FFC107;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #FFB300;
            }
        """
        )
        self.gap_fix_btn.clicked.connect(self._on_fix_data_gaps)
        layout.addWidget(self.gap_fix_btn)

        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setMaximumWidth(25)
        close_btn.setStyleSheet("border: none; color: #856404; font-weight: bold;")
        close_btn.clicked.connect(lambda: frame.hide())
        layout.addWidget(close_btn)

        return frame

    def _load_symbols_to_overlay_combo(self):
        """加载品种列表到叠加选择器."""
        try:
            from backend.core.base import get_service_manager

            service_mgr = get_service_manager()
            if not service_mgr:
                return

            data_center = service_mgr.get_service("data_center_service")
            if not data_center:
                return

            # 从缓存获取品种列表（避免触发API请求）
            if hasattr(data_center, "_symbol_cache") and data_center._symbol_cache:
                symbols = data_center._symbol_cache.get("data", [])
                if symbols and self.overlay_symbol_combo:
                    for symbol in symbols[:100]:  # 限制100个常用品种
                        code = symbol.get("symbol", "")
                        name = symbol.get("name", "")
                        exchange = symbol.get("exchange", "")

                        # 构造vt_symbol
                        exchange_code = (
                            "SSE"
                            if exchange == "上交所"
                            else "SZSE" if exchange == "深交所" else "BSE"
                        )
                        vt_symbol = f"{code}.{exchange_code}"

                        display_name = f"{code} {name}" if name else code
                        self.overlay_symbol_combo.addItem(display_name, vt_symbol)

                    self.logger.info(f"已加载{len(symbols[:100])}个品种到叠加选择器")

        except Exception as e:
            self.logger.debug(f"加载品种列表失败: {e}")

    def _check_data_gaps_for_current_chart(self):
        """检测当前图表的数据断点."""
        try:
            if not self.chart_wizard or not hasattr(self.chart_wizard, "tab"):
                return

            current_index = self.chart_wizard.tab.currentIndex()
            if current_index < 0:
                return

            vt_symbol = self.chart_wizard.tab.tabText(current_index)
            symbol = vt_symbol.split(".")[0]

            # 调用market_board_service检测断点
            from backend.core.base import get_service_manager
            from datetime import datetime, timedelta

            service_mgr = get_service_manager()
            market_service = (
                service_mgr.get_service("market_board_service") if service_mgr else None
            )

            if not market_service:
                return

            # 检测最近30天的数据断点
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            gap_result = market_service.detect_data_gaps(
                symbol=symbol, start_date=start_date, end_date=end_date, interval="1d"
            )

            if gap_result.get("success") and gap_result.get("has_gaps"):
                gaps = gap_result.get("gaps", [])
                self.has_data_gaps = True
                self.gap_info = {
                    "symbol": symbol,
                    "vt_symbol": vt_symbol,
                    "gaps": gaps,
                    "start_date": start_date,
                    "end_date": end_date,
                }

                # 显示警告框
                gap_count = len(gaps)
                if self.gap_warning_label:
                    self.gap_warning_label.setText(f"⚠️ 检测到 {gap_count} 个数据断点，建议增量更新")
                if self.gap_warning_frame:
                    self.gap_warning_frame.show()

                self.logger.warning(f"品种 {symbol} 存在 {gap_count} 个数据断点")
            else:
                self.has_data_gaps = False
                self.gap_info = None
                if self.gap_warning_frame:
                    self.gap_warning_frame.hide()

        except Exception as e:
            self.logger.error(f"检测数据断点失败: {e}")

    def _on_fix_data_gaps(self):
        """点击修复按钮，跳转到数据中心."""
        try:
            if not self.gap_info:
                return

            # 发送跳转信号给主窗口
            # 主窗口负责切换到数据中心tab并传递参数

            # 通过父窗口链找到主窗口
            main_window = self.window()
            if main_window and hasattr(main_window, "switch_to_data_center"):
                symbol = self.gap_info["symbol"]
                start_date = self.gap_info.get("start_date", "")

                # 切换到数据中心并设置增量下载参数
                # 使用类型忽略，因为main_window的类型推断可能不准确
                getattr(main_window, "switch_to_data_center")(
                    action="incremental_download", symbol=symbol, start_date=start_date
                )

                self.logger.info(f"已跳转到数据中心，准备修复 {symbol} 的数据断点")
            else:
                # 如果无法跳转，弹出详细信息
                gaps = self.gap_info.get("gaps", [])
                gap_details = "\n".join(
                    [
                        f"  • {g['gap_start']} 至 {g['gap_end']} (缺失{g.get('expected_bars', 0)}根K线)"
                        for g in gaps[:5]  # 只显示前5个
                    ]
                )

                msg = (
                    f"品种：{self.gap_info['symbol']}\n"
                    f"断点数量：{len(gaps)}\n\n"
                    f"断点详情：\n{gap_details}\n\n"
                    f"请前往【数据中心】→【增量下载】修复"
                )

                QMessageBox.warning(self, "数据断点详情", msg)

        except Exception as e:
            self.logger.error(f"跳转失败: {e}")
            self.show_error(f"跳转失败: {e}")

    def _on_chart_type_changed(self, chart_type: str):
        """图表类型切换.

        Args:
            chart_type: 图表类型（K线图/分时图/Tick图）
        """
        try:
            self.logger.info(f"切换图表类型: {chart_type}")

            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            if chart_type == "K线图":
                # K线图是默认类型，vnpy_chartwizard已支持
                self.show_info("已切换到K线图模式")

            elif chart_type == "分时图":
                # 分时图需要切换数据源和绘制方式
                self._switch_to_timeline_chart()

            elif chart_type == "Tick图":
                # Tick图需要显示逐笔成交
                self._switch_to_tick_chart()

        except Exception as e:
            self.logger.error(f"切换图表类型失败: {e}", exc_info=True)
            self.show_error(f"切换失败: {e}")

    def _switch_to_timeline_chart(self):
        """切换到分时图."""
        try:
            self.logger.info("切换到分时图模式")
            # TODO: 实现分时图绘制逻辑
            # 1. 查询分时数据（1分钟K线）
            # 2. 转换为分时线格式
            # 3. 使用pyqtgraph绘制分时线和均价线
            self.show_info("分时图功能开发中...")

        except Exception as e:
            self.logger.error(f"切换到分时图失败: {e}")

    def _switch_to_tick_chart(self):
        """切换到Tick图."""
        try:
            self.logger.info("切换到Tick图模式")
            # TODO: 实现Tick图绘制逻辑
            # 1. 订阅实时Tick数据
            # 2. 使用pyqtgraph绘制逐笔成交点
            self.show_info("Tick图功能开发中...")

        except Exception as e:
            self.logger.error(f"切换到Tick图失败: {e}")

    def _on_add_overlay_symbol(self):
        """添加品种叠加按钮点击."""
        try:
            if not self.overlay_symbol_combo:
                return

            vt_symbol = self.overlay_symbol_combo.currentData()
            if not vt_symbol:
                self.show_warning("请选择要叠加的品种")
                return

            # 调用现有的品种叠加方法
            self.add_overlay_symbol(vt_symbol, normalized=True)

        except Exception as e:
            self.logger.error(f"添加品种叠加失败: {e}")
            self.show_error(f"添加失败: {e}")

    def _on_add_overlay_indicator(self):
        """添加指标叠加按钮点击."""
        try:
            if not self.overlay_indicator_combo:
                return

            indicator_name = self.overlay_indicator_combo.currentText()
            if not indicator_name:
                self.show_warning("请选择要叠加的指标")
                return

            # 解析指标参数
            params = {}
            if indicator_name.startswith("MA"):
                # MA5 -> period=5
                try:
                    period = int(indicator_name[2:])
                    params = {"period": period}
                except ValueError:
                    params = {"period": 5}
            elif indicator_name.startswith("EMA"):
                try:
                    period = int(indicator_name[3:])
                    params = {"period": period}
                except ValueError:
                    params = {"period": 12}
            elif indicator_name == "BOLL":
                params = {"period": 20}

            # 调用现有的指标叠加方法
            self.add_overlay_indicator(indicator_name, params)

        except Exception as e:
            self.logger.error(f"添加指标叠加失败: {e}")
            self.show_error(f"添加失败: {e}")

    def _on_add_subplot(self):
        """添加副图指标按钮点击."""
        try:
            if not self.subplot_combo:
                return

            indicator_type = self.subplot_combo.currentText()
            if not indicator_type:
                self.show_warning("请选择副图指标类型")
                return

            # 根据指标类型调用对应方法
            if indicator_type == "MACD":
                self.add_subplot_macd()
            elif indicator_type == "RSI":
                self.add_subplot_rsi()
            elif indicator_type == "KDJ":
                self.add_subplot_kdj()
            else:
                self.show_warning(f"暂不支持的副图指标: {indicator_type}")

        except Exception as e:
            self.logger.error(f"添加副图指标失败: {e}")
            self.show_error(f"添加失败: {e}")

    def add_subplot_kdj(self):
        """添加KDJ副图指标."""
        try:
            current_chart = self.get_current_chart()
            if not current_chart:
                self.show_warning("当前无激活图表")
                return

            # 获取当前品种
            if (
                not self.chart_wizard
                or not hasattr(self.chart_wizard, "tab")
                or self.chart_wizard.tab is None
            ):
                self.show_warning("图表组件不支持多标签")
                return

            vt_symbol = self.chart_wizard.tab.tabText(self.chart_wizard.tab.currentIndex())

            # 计算KDJ
            from backend.core.base import get_service_manager
            from datetime import datetime, timedelta

            service_mgr = get_service_manager()
            market_service = (
                service_mgr.get_service("market_board_service") if service_mgr else None
            )

            if not market_service:
                self.show_error("行情服务不可用")
                return

            # 查询K线数据
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

            result = market_service.query_historical_data(
                symbol=vt_symbol.split(".")[0],
                start_date=start_date,
                end_date=end_date,
                interval="1d",
                check_gaps=False,
            )

            if not result.get("success"):
                self.show_error("查询K线数据失败")
                return

            kline_data = result.get("data", [])

            # 提取OHLC数据
            import numpy as np

            closes = np.array([bar.get("close", 0) for bar in kline_data if bar.get("close")])
            highs = np.array([bar.get("high", 0) for bar in kline_data if bar.get("high")])
            lows = np.array([bar.get("low", 0) for bar in kline_data if bar.get("low")])

            if len(closes) < 30:
                self.show_warning("K线数据不足")
                return

            # 计算KDJ（使用talib的STOCH）
            try:
                import talib  # type: ignore

                # 使用talib的STOCH函数，MA_Type使用SMA（简单移动平均）
                from talib import MA_Type  # type: ignore

                slowk, slowd = talib.STOCH(  # type: ignore
                    highs,
                    lows,
                    closes,
                    fastk_period=9,
                    slowk_period=3,
                    slowk_matype=MA_Type.SMA,
                    slowd_period=3,
                    slowd_matype=MA_Type.SMA,
                )
                j_values = 3 * slowk - 2 * slowd

                kdj_data = {"k": slowk.tolist(), "d": slowd.tolist(), "j": j_values.tolist()}

            except ImportError:
                self.show_error("talib未安装，无法计算KDJ")
                return

            # 使用SubplotIndicatorManager添加
            manager = SubplotIndicatorManager(current_chart)
            if manager.add_kdj(kdj_data=kdj_data):
                self.show_info("已添加KDJ副图")
            else:
                self.show_error("添加KDJ副图失败")

        except Exception as e:
            self.logger.error(f"添加KDJ副图失败: {e}", exc_info=True)
            self.show_error(f"添加KDJ副图失败: {e}")

    def _on_data_manager_ready(self, event):
        """UnifiedDataManager就绪回调（事件驱动）."""
        try:
            contract_count = event.data.get("contract_count", 0)
            mode = event.data.get("mode", "unknown")

            self.logger.info(f"✅ UnifiedDataManager已就绪：{contract_count}个品种（{mode}模式）")

            # 🔧 优化：验证数据接口是否已注入
            if self.main_engine and hasattr(self.main_engine, "get_all_contracts"):
                try:
                    test_contracts = self.main_engine.get_all_contracts()
                    if test_contracts and len(test_contracts) > 0:
                        self.logger.info(
                            f"✅ MainEngine 数据接口已验证（品种数：{len(test_contracts)}）"
                        )
                    else:
                        self.logger.warning(
                            "⚠️ MainEngine.get_all_contracts() 返回空列表（可能是占位方法）"
                        )
                except Exception as e:
                    self.logger.warning(f"⚠️ 验证 MainEngine.get_all_contracts() 失败: {e}")

            self._data_ready = True
            self._data_mode = mode
            self.initialization_state = "ready"

            # 根据模式初始化UI
            if mode == "offline" and contract_count == 0:
                self.logger.warning("离线模式且无本地数据，功能受限")
                # 可以在这里显示友好的空状态提示
            else:
                # 初始化数据相关组件
                self._initialize_data_components()

        except Exception as e:
            self.logger.error(f"处理UnifiedDataManager就绪事件失败: {e}", exc_info=True)

    def _initialize_data_components(self):
        """初始化需要数据的UI组件（事件驱动调用）."""
        if not self._data_ready:
            return

        try:
            # 加载品种列表到叠加选择器
            self._load_symbols_to_overlay_combo()
            # 注册vnpy事件监听器（监听实时数据）
            self._register_vnpy_events()

            # 如果当前是等待UI，重建为完整图表UI
            if self.waiting_label and self.waiting_label.isVisible():
                self._rebuild_ui_with_chart()

            self.logger.info(f"✅ 数据组件初始化完成（{self._data_mode}模式）")

        except Exception as e:
            self.logger.error(f"初始化数据组件失败: {e}", exc_info=True)

    def _register_vnpy_events(self):
        """注册vnpy事件监听器."""
        try:
            if not self.event_engine:
                return

            from vnpy.trader.event import EVENT_TICK

            # 监听Tick事件以更新推送状态
            self.event_engine.register(EVENT_TICK, self._on_tick_event)

            # ✅ 线程安全修复：连接信号到 UI 更新槽函数
            self.tick_event_signal.connect(self._update_tick_ui)

            self.logger.info("✅ 已注册vnpy事件监听器并连接信号槽")

        except Exception as e:
            self.logger.warning(f"注册vnpy事件失败: {e}")

    def _on_tick_event(self, event):
        """处理Tick事件（EventEngine 工作线程）.

        ✅ 线程安全修复：此函数在 EventEngine 工作线程中执行，
        不能直接更新 UI，只发射信号让 Qt 主线程处理。

        Args:
            event: vnpy Event对象
        """
        try:
            # ✅ 只发射信号，不做任何 UI 操作（线程安全）
            if hasattr(event, "data") and event.data:
                self.tick_event_signal.emit({"tick": event.data, "event_type": "tick"})
        except Exception as e:
            self.logger.debug(f"发射Tick事件信号失败: {e}")

    def _update_tick_ui(self, data: dict):
        """更新Tick事件 UI（Qt 主线程，线程安全）.

        Args:
            data: Tick事件数据字典
        """
        try:
            # ✅ 所有 UI 操作都在主线程，线程安全！

            # 1. 更新推送状态指示器
            if self.push_status_label:
                self.push_status_label.setText("● 推送中")
                self.push_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")

                # 5秒后如果没有新Tick，恢复为未推送状态
                QTimer.singleShot(5000, self._reset_push_status)

            # 2. ✨ 自动刷新图表（如果Tick品种与当前图表匹配）
            if self.chart_wizard and "tick" in data:
                tick = data["tick"]
                if not tick:
                    return

                tick_symbol = getattr(tick, "vt_symbol", "") or getattr(tick, "symbol", "")

                # 获取当前图表的品种
                current_chart = self.get_current_chart()
                if current_chart and hasattr(self.chart_wizard, "tab"):
                    current_index = self.chart_wizard.tab.currentIndex()
                    if current_index >= 0:
                        chart_symbol = self.chart_wizard.tab.tabText(current_index)

                        # 如果Tick品种与当前图表匹配，触发图表刷新
                        if tick_symbol == chart_symbol:
                            # vnpy_chartwizard会自动处理Tick更新
                            # 这里只需要确保图表保持在最新位置
                            if hasattr(current_chart, "move_to_right"):
                                QTimer.singleShot(100, current_chart.move_to_right)
                                self.logger.debug(f"✅ Tick触发图表自动刷新: {tick_symbol}")

        except Exception as e:
            self.logger.debug(f"更新Tick事件 UI 失败: {e}")

    def _reset_push_status(self):
        """重置推送状态指示器."""
        try:
            if self.push_status_label:
                self.push_status_label.setText("● 推送")
                self.push_status_label.setStyleSheet("color: #999; font-size: 11px;")
        except Exception:
            pass

    def _rebuild_ui_with_chart(self):
        """重建UI为完整图表界面."""
        try:
            # 清空当前UI
            layout = self.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    widget = child.widget()
                    if widget is not None:
                        widget.deleteLater()

            # 重新创建图表UI
            if isinstance(layout, QVBoxLayout):
                self._setup_chart_ui(layout)
            else:
                self.logger.error("布局类型不匹配，无法重建UI")
                return

            self.logger.info("✅ 图表界面重建完成")
            self.show_info("后端初始化完成，图表功能已就绪")

        except Exception as e:
            self.logger.error(f"重建UI失败: {e}", exc_info=True)
            self.show_error(f"重建UI失败: {e}")

    def on_close(self):
        """关闭处理."""
        # 取消注册事件监听器
        try:
            if self.event_engine:
                from vnpy.trader.event import EVENT_TICK

                self.event_engine.unregister(EVENT_TICK, self._on_tick_event)

                # 🔧 修复：架构v3.0重构后，data_module模块已移除
                # 不再需要取消订阅UnifiedDataManager就绪事件
                try:
                    pass  # 不再需要取消订阅
                except Exception:
                    pass
        except Exception as e:
            self.logger.debug(f"取消注册事件失败: {e}")

        # ChartWizard 会自动清理资源
        self.logger.info("ChartWizard增强版已关闭")
        super().on_close()


class SubplotIndicatorManager:
    """副图指标管理器.

    负责在图表中添加和管理副图指标（MACD、RSI、KDJ等）。
    """

    def __init__(self, chart_widget):
        """初始化副图指标管理器.

        Args:
            chart_widget: ChartWidget实例
        """
        self.chart = chart_widget
        self.indicators: Dict[str, Any] = {}  # 指标名称 -> 指标实例

    def add_macd(self, plot_name: str = "macd", macd_data: Optional[Dict] = None):
        """添加MACD副图.

        Args:
            plot_name: Plot区域名称
            macd_data: MACD数据 {"macd": [], "signal": [], "hist": []}
        """
        try:
            import pyqtgraph as pg

            # 添加plot区域
            self.chart.add_plot(plot_name=plot_name, maximum_height=150, hide_x_axis=False)

            if macd_data:
                # 绘制MACD线
                macd_plot = self.chart._plots.get(plot_name)
                if macd_plot:
                    # MACD柱状图
                    if "hist" in macd_data:
                        hist = macd_data["hist"]
                        x_data = list(range(len(hist)))
                        y_data = [
                            h if h is not None and not (isinstance(h, float) and h != h) else 0
                            for h in hist
                        ]

                        # 使用BarGraphItem绘制柱状图
                        colors = ["r" if y < 0 else "g" for y in y_data]
                        bars = pg.BarGraphItem(x=x_data, height=y_data, width=0.6, brushes=colors)
                        macd_plot.addItem(bars)

                    # MACD线（DIF）
                    if "macd" in macd_data:
                        macd_line = macd_data["macd"]
                        x_data = []
                        y_data = []
                        for i, value in enumerate(macd_line):
                            if value is not None and not (
                                isinstance(value, float) and value != value
                            ):
                                x_data.append(i)
                                y_data.append(float(value))

                        if x_data and y_data:
                            pen = pg.mkPen(color="#FFA07A", width=2)
                            curve = pg.PlotDataItem(x=x_data, y=y_data, pen=pen, name="DIF")
                            macd_plot.addItem(curve)

                    # Signal线（DEA）
                    if "signal" in macd_data:
                        signal_line = macd_data["signal"]
                        x_data = []
                        y_data = []
                        for i, value in enumerate(signal_line):
                            if value is not None and not (
                                isinstance(value, float) and value != value
                            ):
                                x_data.append(i)
                                y_data.append(float(value))

                        if x_data and y_data:
                            pen = pg.mkPen(color="#4ECDC4", width=2)
                            curve = pg.PlotDataItem(x=x_data, y=y_data, pen=pen, name="DEA")
                            macd_plot.addItem(curve)

            self.indicators["MACD"] = {
                "plot_name": plot_name,
                "type": "MACD",
            }

            logger.info(f"✅ MACD副图已添加: {plot_name}")
            return True

        except Exception as e:
            logger.error(f"❌ 添加MACD副图失败: {e}", exc_info=True)
            return False

    def add_rsi(self, plot_name: str = "rsi", rsi_data: Optional[List] = None, period: int = 14):
        """添加RSI副图.

        Args:
            plot_name: Plot区域名称
            rsi_data: RSI数据列表
            period: RSI周期
        """
        try:
            import pyqtgraph as pg

            # 添加plot区域
            self.chart.add_plot(plot_name=plot_name, maximum_height=120, hide_x_axis=False)

            if rsi_data:
                rsi_plot = self.chart._plots.get(plot_name)
                if rsi_plot:
                    # 准备数据
                    x_data = []
                    y_data = []
                    for i, value in enumerate(rsi_data):
                        if value is not None and not (isinstance(value, float) and value != value):
                            x_data.append(i)
                            y_data.append(float(value))

                    if x_data and y_data:
                        # 绘制RSI线
                        pen = pg.mkPen(color="#FFA07A", width=2)
                        curve = pg.PlotDataItem(x=x_data, y=y_data, pen=pen, name=f"RSI({period})")
                        rsi_plot.addItem(curve)

                        # 添加超买超卖参考线
                        from PySide6.QtCore import Qt

                        pen_ref = pg.mkPen(color="#CCCCCC", width=1, style=Qt.PenStyle.DashLine)

                        # 超买线(70)
                        overbought = pg.InfiniteLine(pos=70, angle=0, pen=pen_ref)
                        rsi_plot.addItem(overbought)

                        # 超卖线(30)
                        oversold = pg.InfiniteLine(pos=30, angle=0, pen=pen_ref)
                        rsi_plot.addItem(oversold)

                        # 中线(50)
                        midline = pg.InfiniteLine(pos=50, angle=0, pen=pen_ref)
                        rsi_plot.addItem(midline)

            self.indicators["RSI"] = {
                "plot_name": plot_name,
                "type": "RSI",
                "period": period,
            }

            logger.info(f"✅ RSI副图已添加: {plot_name} (周期: {period})")
            return True

        except Exception as e:
            logger.error(f"❌ 添加RSI副图失败: {e}", exc_info=True)
            return False

    def add_kdj(self, plot_name: str = "kdj", kdj_data: Optional[Dict] = None):
        """添加KDJ副图.

        Args:
            plot_name: Plot区域名称
            kdj_data: KDJ数据 {"k": [], "d": [], "j": []}
        """
        try:
            import pyqtgraph as pg

            # 添加plot区域
            self.chart.add_plot(plot_name=plot_name, maximum_height=120, hide_x_axis=False)

            if kdj_data:
                kdj_plot = self.chart._plots.get(plot_name)
                if kdj_plot:
                    colors = {"k": "#FFA07A", "d": "#4ECDC4", "j": "#95E1D3"}

                    for line_name in ["k", "d", "j"]:
                        if line_name in kdj_data:
                            line_values = kdj_data[line_name]
                            x_data = []
                            y_data = []

                            for i, value in enumerate(line_values):
                                if value is not None and not (
                                    isinstance(value, float) and value != value
                                ):
                                    x_data.append(i)
                                    y_data.append(float(value))

                            if x_data and y_data:
                                pen = pg.mkPen(color=colors[line_name], width=2)
                                curve = pg.PlotDataItem(
                                    x=x_data, y=y_data, pen=pen, name=line_name.upper()
                                )
                                kdj_plot.addItem(curve)

                    # 添加超买超卖参考线
                    from PySide6.QtCore import Qt

                    pen_ref = pg.mkPen(color="#CCCCCC", width=1, style=Qt.PenStyle.DashLine)

                    # 超买线(80)
                    overbought = pg.InfiniteLine(pos=80, angle=0, pen=pen_ref)
                    kdj_plot.addItem(overbought)

                    # 超卖线(20)
                    oversold = pg.InfiniteLine(pos=20, angle=0, pen=pen_ref)
                    kdj_plot.addItem(oversold)

            self.indicators["KDJ"] = {
                "plot_name": plot_name,
                "type": "KDJ",
            }

            logger.info(f"✅ KDJ副图已添加: {plot_name}")
            return True

        except Exception as e:
            logger.error(f"❌ 添加KDJ副图失败: {e}", exc_info=True)
            return False

    def remove_indicator(self, indicator_type: str):
        """移除副图指标.

        Args:
            indicator_type: 指标类型（MACD、RSI、KDJ等）
        """
        if indicator_type not in self.indicators:
            logger.warning(f"指标不存在: {indicator_type}")
            return False

        try:
            indicator_info = self.indicators[indicator_type]
            plot_name = indicator_info["plot_name"]

            # 移除plot区域
            if hasattr(self.chart, "remove_plot"):
                self.chart.remove_plot(plot_name)

            # 从字典中删除
            del self.indicators[indicator_type]

            logger.info(f"✅ 已移除指标: {indicator_type}")
            return True

        except Exception as e:
            logger.error(f"❌ 移除指标失败: {e}", exc_info=True)
            return False

    def get_indicator_list(self) -> List[str]:
        """获取当前已添加的指标列表.

        Returns:
            指标类型列表
        """
        return list(self.indicators.keys())
