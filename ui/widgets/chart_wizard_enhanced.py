# -*- coding: utf-8 -*-
"""
ChartWizard增强版 - vnpy_chartwizard 适配器

完全基于 vnpy_chartwizard，提供多标签页K线图表、实时订阅、自动K线合成等专业功能。
"""

import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLineEdit,
    QPushButton,
    QGroupBox,
    QRadioButton,
    QComboBox,
    QLabel,
    QFrame,
    QMessageBox,
    QProgressBar,
)

from ui.widgets.base_widget import BaseWidget

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


class ChartWizardEnhanced(BaseWidget):
    """ChartWizard增强版组件.

    封装 vnpy_chartwizard，提供：
    - 多标签页品种监控
    - 自动数据查询和订阅
    - 实时Tick转K线合成
    - 品种叠加、指标叠加
    - 对数坐标切换
    - 快捷键和右键菜单
    """

    # 信号定义
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
        self.retry_count = 0
        self.retry_timer: Optional[Any] = None
        self.max_retries = 30  # 最多重试30次（15秒）
        self.retry_interval = 500  # 每500ms重试一次

        # UI组件
        self.symbol_input: Optional[QLineEdit] = None
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

        # 等待UI组件
        self.waiting_label: Optional[QLabel] = None
        self.waiting_progress: Optional[Any] = None

        # 调用父类初始化
        super().__init__(parent, "K线图表")

        # 初始化引擎
        self._initialize_engines()

        # 如果引擎已就绪，立即完成初始化
        if self.main_engine and self.event_engine:
            self.initialization_state = "ready"
            # 加载品种列表到叠加选择器
            self._load_symbols_to_overlay_combo()
            # 注册vnpy事件监听器（监听实时数据）
            self._register_vnpy_events()

    def _initialize_engines(self):
        """初始化VnPy引擎."""
        try:
            from backend.core.base import get_main_engine, get_event_engine

            self.main_engine = get_main_engine()
            self.event_engine = get_event_engine()

            if not self.main_engine:
                self.logger.warning("⚠️ MainEngine 不可用")
                return

            if not self.event_engine:
                self.logger.warning("⚠️ EventEngine 不可用")
                return

            self.logger.info("✅ VnPy引擎初始化成功")

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
            # 显示等待UI并启动自动重试
            self._setup_waiting_ui(main_layout)
            self._start_retry_timer()
            return

        # 引擎已就绪，直接创建图表UI
        self._setup_chart_ui(main_layout)

    def _setup_waiting_ui(self, layout: QVBoxLayout):
        """设置等待UI界面.

        Args:
            layout: 布局
        """
        from PySide6.QtCore import Qt

        # 等待提示
        self.waiting_label = QLabel("⏳ 等待后端初始化中...")
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
            f"正在初始化VnPy引擎...\n"
            f"重试次数: {self.retry_count}/{self.max_retries}\n"
            f"预计等待时间: 5-15秒"
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

        # 创建 vnpy_chartwizard 核心组件
        try:
            self.chart_wizard = VnpyChartWizard(self.main_engine, self.event_engine)
            layout.addWidget(self.chart_wizard, 1)
            self.logger.info("✅ ChartWizard组件创建成功")
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
        """创建顶部工具栏.

        Returns:
            工具栏布局
        """
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # 品种输入框
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("输入品种代码（如：000001.SZSE）")
        self.symbol_input.setMinimumWidth(250)
        self.symbol_input.returnPressed.connect(self._on_new_chart)
        toolbar.addWidget(QLabel("品种:"))
        toolbar.addWidget(self.symbol_input)

        # 新建图表按钮
        self.new_chart_btn = QPushButton("📊 新建图表")
        self.new_chart_btn.clicked.connect(self._on_new_chart)
        self.new_chart_btn.setMinimumWidth(100)
        toolbar.addWidget(self.new_chart_btn)

        toolbar.addSpacing(20)

        # 图表类型切换
        toolbar.addWidget(QLabel("图表:"))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(["K线图", "分时图", "Tick图"])
        self.chart_type_combo.currentTextChanged.connect(self._on_chart_type_changed)
        toolbar.addWidget(self.chart_type_combo)

        toolbar.addSpacing(10)

        # 坐标类型切换
        coord_group = QGroupBox("坐标类型")
        coord_layout = QHBoxLayout(coord_group)
        coord_layout.setContentsMargins(5, 5, 5, 5)

        self.coord_linear_radio = QRadioButton("线性")
        self.coord_linear_radio.setChecked(True)
        self.coord_linear_radio.toggled.connect(self._on_coord_type_changed)

        self.coord_log_radio = QRadioButton("对数")

        coord_layout.addWidget(self.coord_linear_radio)
        coord_layout.addWidget(self.coord_log_radio)
        toolbar.addWidget(coord_group)

        toolbar.addSpacing(10)

        # 品种叠加
        toolbar.addWidget(QLabel("叠加品种:"))
        self.overlay_symbol_combo = QComboBox()
        self.overlay_symbol_combo.setPlaceholderText("选择品种")
        self.overlay_symbol_combo.setMinimumWidth(150)
        toolbar.addWidget(self.overlay_symbol_combo)

        add_overlay_btn = QPushButton("➕ 叠加")
        add_overlay_btn.clicked.connect(self._on_add_overlay_symbol)
        add_overlay_btn.setMaximumWidth(60)
        toolbar.addWidget(add_overlay_btn)

        toolbar.addSpacing(10)

        # 指标叠加
        toolbar.addWidget(QLabel("叠加指标:"))
        self.overlay_indicator_combo = QComboBox()
        self.overlay_indicator_combo.addItems(
            ["MA5", "MA10", "MA20", "MA60", "BOLL", "EMA12", "EMA26"]
        )
        self.overlay_indicator_combo.setMinimumWidth(100)
        toolbar.addWidget(self.overlay_indicator_combo)

        add_indicator_btn = QPushButton("➕ 指标")
        add_indicator_btn.clicked.connect(self._on_add_overlay_indicator)
        add_indicator_btn.setMaximumWidth(60)
        toolbar.addWidget(add_indicator_btn)

        toolbar.addSpacing(10)

        # 副图指标
        toolbar.addWidget(QLabel("副图:"))
        self.subplot_combo = QComboBox()
        self.subplot_combo.addItems(["MACD", "RSI", "KDJ"])
        self.subplot_combo.setMinimumWidth(80)
        toolbar.addWidget(self.subplot_combo)

        add_subplot_btn = QPushButton("➕ 副图")
        add_subplot_btn.clicked.connect(self._on_add_subplot)
        add_subplot_btn.setMaximumWidth(60)
        toolbar.addWidget(add_subplot_btn)

        toolbar.addStretch()

        # 实时推送状态指示器
        self.push_status_label = QLabel("● 推送")
        self.push_status_label.setStyleSheet("color: #999; font-size: 11px;")
        self.push_status_label.setToolTip("实时数据推送状态")
        toolbar.addWidget(self.push_status_label)

        return toolbar

    def _on_new_chart(self):
        """新建图表."""
        if not self.chart_wizard:
            self.show_warning("图表组件未就绪")
            return

        vt_symbol = self.symbol_input.text().strip()
        if not vt_symbol:
            self.show_warning("请输入品种代码")
            return

        try:
            # 调用 vnpy_chartwizard 的新建图表方法
            # ChartWizardWidget 有内置的 new_chart() 方法
            if hasattr(self.chart_wizard, "new_chart"):
                # 设置品种输入框的值
                if hasattr(self.chart_wizard, "symbol_line"):
                    self.chart_wizard.symbol_line.setText(vt_symbol)
                # 触发新建
                self.chart_wizard.new_chart()
                self.logger.info(f"✅ 新建图表: {vt_symbol}")
                self.chart_created.emit(vt_symbol)
                self.current_symbol = vt_symbol

                # 清空输入框，准备输入下一个品种
                self.symbol_input.clear()

                # 自动检测数据断点
                from PySide6.QtCore import QTimer

                QTimer.singleShot(1000, self._check_data_gaps_for_current_chart)
            else:
                self.show_warning("图表组件不支持新建功能")

        except Exception as e:
            self.logger.error(f"❌ 新建图表失败: {e}", exc_info=True)
            self.show_error(f"新建图表失败: {e}")

    def _on_coord_type_changed(self, checked: bool):
        """坐标类型变化处理.

        Args:
            checked: 是否选中
        """
        if not checked:
            return

        try:
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

    def create_new_chart(self, vt_symbol: str):
        """创建新图表.

        Args:
            vt_symbol: 品种代码（vt格式，如 000001.SZSE）
        """
        if self.symbol_input:
            self.symbol_input.setText(vt_symbol)
        self._on_new_chart()

    def get_current_chart(self):
        """获取当前激活的图表.

        Returns:
            ChartWidget 或 None
        """
        if not self.chart_wizard or not hasattr(self.chart_wizard, "tab"):
            return None

        # 获取当前标签页索引
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
            if not hasattr(self.chart_wizard, "tab"):
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
            if not hasattr(self.chart_wizard, "tab"):
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
            from ui.widgets.chart_subplot_indicators import SubplotIndicatorManager

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
            from ui.widgets.chart_subplot_indicators import SubplotIndicatorManager

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
                self.gap_warning_label.setText(f"⚠️ 检测到 {gap_count} 个数据断点，建议增量更新")
                self.gap_warning_frame.show()

                self.logger.warning(f"品种 {symbol} 存在 {gap_count} 个数据断点")
            else:
                self.has_data_gaps = False
                self.gap_info = None
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
                main_window.switch_to_data_center(
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

                slowk, slowd = talib.STOCH(  # type: ignore
                    highs,
                    lows,
                    closes,
                    fastk_period=9,
                    slowk_period=3,
                    slowk_matype=0,
                    slowd_period=3,
                    slowd_matype=0,
                )
                j_values = 3 * slowk - 2 * slowd

                kdj_data = {"k": slowk.tolist(), "d": slowd.tolist(), "j": j_values.tolist()}

            except ImportError:
                self.show_error("talib未安装，无法计算KDJ")
                return

            # 使用SubplotIndicatorManager添加
            from ui.widgets.chart_subplot_indicators import SubplotIndicatorManager

            manager = SubplotIndicatorManager(current_chart)
            if manager.add_kdj(kdj_data=kdj_data):
                self.show_info("已添加KDJ副图")
            else:
                self.show_error("添加KDJ副图失败")

        except Exception as e:
            self.logger.error(f"添加KDJ副图失败: {e}", exc_info=True)
            self.show_error(f"添加KDJ副图失败: {e}")

    def _register_vnpy_events(self):
        """注册vnpy事件监听器."""
        try:
            if not self.event_engine:
                return

            from vnpy.trader.event import EVENT_TICK

            # 监听Tick事件以更新推送状态
            self.event_engine.register(EVENT_TICK, self._on_tick_event)

            self.logger.info("✅ 已注册vnpy事件监听器")

        except Exception as e:
            self.logger.warning(f"注册vnpy事件失败: {e}")

    def _on_tick_event(self, event):
        """处理Tick事件（更新推送状态指示器 + 自动刷新图表）.

        Args:
            event: vnpy Event对象
        """
        try:
            # 1. 更新推送状态指示器
            if self.push_status_label:
                self.push_status_label.setText("● 推送中")
                self.push_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")

                # 5秒后如果没有新Tick，恢复为未推送状态
                from PySide6.QtCore import QTimer

                QTimer.singleShot(5000, self._reset_push_status)

            # 2. ✨ 自动刷新图表（如果Tick品种与当前图表匹配）
            if self.chart_wizard and hasattr(event, "data"):
                tick = event.data
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
            self.logger.debug(f"处理Tick事件失败: {e}")

    def _reset_push_status(self):
        """重置推送状态指示器."""
        try:
            if self.push_status_label:
                self.push_status_label.setText("● 推送")
                self.push_status_label.setStyleSheet("color: #999; font-size: 11px;")
        except Exception:
            pass

    def _start_retry_timer(self):
        """启动自动重试定时器."""
        if self.retry_timer:
            return  # 已经启动

        self.logger.info("启动引擎就绪检测定时器...")
        self.retry_timer = QTimer(self)
        self.retry_timer.timeout.connect(self._retry_initialize)
        self.retry_timer.start(self.retry_interval)

    def _retry_initialize(self):
        """重试初始化（定时器回调）."""
        self.retry_count += 1

        # 重新获取引擎
        from backend.core.base import get_main_engine, get_event_engine

        self.main_engine = get_main_engine()
        self.event_engine = get_event_engine()

        # 更新等待UI的重试次数提示
        if self.waiting_label:
            self.waiting_label.setText(
                f"⏳ 等待后端初始化中... ({self.retry_count}/{self.max_retries})"
            )

        # 检查引擎是否就绪
        if self.main_engine and self.event_engine:
            self.logger.info(f"✅ 引擎就绪！重试{self.retry_count}次后成功")

            # 停止定时器
            if self.retry_timer:
                self.retry_timer.stop()
                self.retry_timer = None

            # 更新状态
            self.initialization_state = "ready"

            # 完成后续初始化
            self._load_symbols_to_overlay_combo()
            self._register_vnpy_events()

            # 重建UI
            self._rebuild_ui_with_chart()
            return

        # 检查是否超时
        if self.retry_count >= self.max_retries:
            self.logger.error(f"❌ 引擎初始化超时（{self.max_retries}次重试失败）")

            # 停止定时器
            if self.retry_timer:
                self.retry_timer.stop()
                self.retry_timer = None

            # 更新状态
            self.initialization_state = "failed"

            # 显示错误UI
            if self.waiting_label:
                self.waiting_label.setText("❌ 后端初始化超时")
                self.waiting_label.setStyleSheet("font-size: 16px; color: #FF5722; padding: 20px;")

            if self.waiting_progress:
                self.waiting_progress.hide()

    def _rebuild_ui_with_chart(self):
        """重建UI为完整图表界面."""
        try:
            # 清空当前UI
            layout = self.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

            # 重新创建图表UI
            self._setup_chart_ui(layout)

            self.logger.info("✅ 图表界面重建完成")
            self.show_info("后端初始化完成，图表功能已就绪")

        except Exception as e:
            self.logger.error(f"重建UI失败: {e}", exc_info=True)
            self.show_error(f"重建UI失败: {e}")

    def on_close(self):
        """关闭处理."""
        # 停止重试定时器
        if self.retry_timer:
            self.retry_timer.stop()
            self.retry_timer = None

        # 取消注册事件监听器
        try:
            if self.event_engine:
                from vnpy.trader.event import EVENT_TICK

                self.event_engine.unregister(EVENT_TICK, self._on_tick_event)
        except Exception as e:
            self.logger.debug(f"取消注册事件失败: {e}")

        # ChartWizard 会自动清理资源
        self.logger.info("ChartWizard增强版已关闭")
        super().on_close()
