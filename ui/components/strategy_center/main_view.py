# -*- coding: utf-8 -*-
"""策略中心界面 - 主视图（重构版）.

混合架构：策略/指标管理器（固有组件）+ 2个子界面。
通过StrategyCenterService访问策略和回测功能。
"""
import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.core.shared_services import get_service_manager
from backend.core.utils.logging_utils import LoggerMixin
from ui.widgets.base_widget import BaseWidget
from ui.widgets.code_editor_widget import CodeEditor


class StrategyCenter(BaseWidget, LoggerMixin):
    """策略中心主界面（重构版）."""

    def __init__(self, parent=None):
        """初始化策略中心."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.strategy_service = None

        # 初始化UI组件
        self.toggle_btn: Optional[QPushButton] = None
        self.file_tree: Optional[QTreeWidget] = None
        self.content_tab: Optional[QTabWidget] = None
        self.editor_tab: Optional[QWidget] = None
        self.backtest_tab: Optional[QWidget] = None
        self.current_file_label: Optional[QLabel] = None
        self.ai_assistant_btn: Optional[QPushButton] = None
        self.code_editor: Optional[CodeEditor] = None
        self.ai_assistant_widget: Optional[QWidget] = None
        self.ai_response: Optional[QTextEdit] = None
        self.user_input: Optional[QLineEdit] = None
        self.backtest_target_combo: Optional[QComboBox] = None
        self.start_date_input: Optional[QLineEdit] = None
        self.end_date_input: Optional[QLineEdit] = None
        self.run_backtest_btn: Optional[QPushButton] = None
        self.stop_backtest_btn: Optional[QPushButton] = None
        self.backtest_progress: Optional[QProgressBar] = None
        self.backtest_status_label: Optional[QLabel] = None
        self.backtest_results: Optional[QTextEdit] = None

        # 调用父类初始化
        super().__init__(parent, "策略中心")
        self.logger.info("策略中心界面初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取策略中心服务."""
        try:
            # 从服务管理器获取策略中心服务
            self.strategy_service = self.service_manager.get_service("strategy_center_service")
            if self.strategy_service:
                self.logger.info("策略中心服务获取成功")
            else:
                self.logger.warning("策略中心服务未注册")
        except Exception as e:
            self.logger.error("获取策略中心服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QHBoxLayout(self)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([250, 800])

        # 左侧：策略/指标管理器（固有组件）
        left_widget = self._create_strategy_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：子界面区域
        right_widget = self._create_content_area()
        main_splitter.addWidget(right_widget)

        main_layout.addWidget(main_splitter)

    # ==================== 策略/指标管理器（固有组件）====================

    def _create_strategy_manager(self) -> QWidget:
        """创建策略/指标管理器."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("📁 策略/指标管理器")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)

        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setMaximumWidth(30)
        self.toggle_btn.clicked.connect(self._toggle_manager)
        title_layout.addWidget(self.toggle_btn)

        layout.addLayout(title_layout)

        # 文件树
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        self._create_file_tree()
        layout.addWidget(self.file_tree)

        # 底部按钮
        button_layout = QHBoxLayout()

        new_strategy_btn = QPushButton("新建策略")
        new_strategy_btn.clicked.connect(self._create_new_strategy)
        button_layout.addWidget(new_strategy_btn)

        new_indicator_btn = QPushButton("新建指标")
        new_indicator_btn.clicked.connect(self._create_new_indicator)
        button_layout.addWidget(new_indicator_btn)

        layout.addLayout(button_layout)

        return widget

    def _create_file_tree(self):
        """创建文件树结构."""
        if not self.file_tree:
            return

        self.file_tree.clear()

        try:
            # 策略文件夹
            strategy_root = QTreeWidgetItem()
            strategy_root.setText(0, "📂 策略")
            self.file_tree.addTopLevelItem(strategy_root)

            strategy_dir = "strategies/user_strategies"
            if os.path.exists(strategy_dir):
                strategy_files = [
                    f
                    for f in os.listdir(strategy_dir)
                    if f.endswith(".py") and not f.startswith("__")
                ]
            else:
                strategy_files = []

            for file_name in strategy_files:
                file_item = QTreeWidgetItem()
                file_item.setText(0, f"📄 {file_name}")
                file_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "type": "strategy",
                        "path": os.path.join(strategy_dir, file_name),
                    },
                )
                strategy_root.addChild(file_item)

            # 模板文件夹
            template_root = QTreeWidgetItem()
            template_root.setText(0, "📂 策略模板")
            self.file_tree.addTopLevelItem(template_root)

            template_dir = "strategies/templates"
            if os.path.exists(template_dir):
                template_files = [
                    f
                    for f in os.listdir(template_dir)
                    if f.endswith(".py") and not f.startswith("__")
                ]
            else:
                template_files = []

            for file_name in template_files:
                file_item = QTreeWidgetItem()
                file_item.setText(0, f"📋 {file_name}")
                file_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "type": "template",
                        "path": os.path.join(template_dir, file_name),
                    },
                )
                template_root.addChild(file_item)

            self.file_tree.expandAll()

            self.logger.info(
                "文件树创建完成: %s策略, %s模板", len(strategy_files), len(template_files)
            )

        except Exception as e:
            self.logger.error("创建文件树失败: %s", e)

    # ==================== 内容区域 ====================

    def _create_content_area(self) -> QWidget:
        """创建内容区域."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.content_tab = QTabWidget()

        # 4.1 策略/指标编写子界面
        self.editor_tab = self._create_editor_tab()
        self.content_tab.addTab(self.editor_tab, "✏️ 编写")

        # 4.2 策略/指标回测子界面
        self.backtest_tab = self._create_backtest_tab()
        self.content_tab.addTab(self.backtest_tab, "📈 回测")

        layout.addWidget(self.content_tab)

        return widget

    # ==================== 编写子界面 ====================

    def _create_editor_tab(self) -> QWidget:
        """创建编写子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        self.current_file_label = QLabel("当前文件: 未选择")
        toolbar_layout.addWidget(self.current_file_label)
        toolbar_layout.addStretch()

        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(self._save_current_file)
        toolbar_layout.addWidget(save_btn)

        format_btn = QPushButton("⚡ 格式化")
        format_btn.clicked.connect(self._format_code)
        toolbar_layout.addWidget(format_btn)

        self.ai_assistant_btn = QPushButton("🤖 显示AI助手")
        self.ai_assistant_btn.setCheckable(True)
        self.ai_assistant_btn.toggled.connect(self._toggle_ai_assistant)
        toolbar_layout.addWidget(self.ai_assistant_btn)

        layout.addLayout(toolbar_layout)

        # 编辑器区域
        editor_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 代码编辑器
        self.code_editor = CodeEditor()
        self.code_editor.setPlaceholderText("# 在这里编写您的策略或指标代码...")
        editor_splitter.addWidget(self.code_editor)

        # AI助手区域
        self.ai_assistant_widget = self._create_ai_assistant()
        editor_splitter.addWidget(self.ai_assistant_widget)
        self.ai_assistant_widget.setVisible(False)

        editor_splitter.setSizes([700, 300])

        layout.addWidget(editor_splitter)

        return tab

    def _create_ai_assistant(self) -> QWidget:
        """创建AI助手组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # AI回答区域
        response_group = QGroupBox("AI助手回答")
        response_layout = QVBoxLayout(response_group)

        self.ai_response = QTextEdit()
        self.ai_response.setPlaceholderText("AI助手将在这里回答您的问题...")
        response_layout.addWidget(self.ai_response)

        layout.addWidget(response_group)

        # 用户指令区域
        input_group = QGroupBox("您的指令")
        input_layout = QVBoxLayout(input_group)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("请输入您的问题或指令...")
        self.user_input.returnPressed.connect(self._send_to_ai)
        input_layout.addWidget(self.user_input)

        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._send_to_ai)
        input_layout.addWidget(send_btn)

        layout.addWidget(input_group)

        return widget

    # ==================== 回测子界面 ====================

    def _create_backtest_tab(self) -> QWidget:
        """创建回测子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 回测配置组
        config_group = QGroupBox("回测配置")
        config_layout = QHBoxLayout(config_group)

        # 左侧配置
        left_form = QVBoxLayout()
        left_form.addWidget(QLabel("策略/指标:"))

        self.backtest_target_combo = QComboBox()
        self._load_strategy_list()
        left_form.addWidget(self.backtest_target_combo)

        config_layout.addLayout(left_form)

        # 右侧配置
        right_form = QVBoxLayout()
        right_form.addWidget(QLabel("开始日期:"))

        self.start_date_input = QLineEdit()
        self.start_date_input.setPlaceholderText("YYYY-MM-DD")
        right_form.addWidget(self.start_date_input)

        right_form.addWidget(QLabel("结束日期:"))
        self.end_date_input = QLineEdit()
        self.end_date_input.setPlaceholderText("YYYY-MM-DD")
        right_form.addWidget(self.end_date_input)

        config_layout.addLayout(right_form)

        layout.addWidget(config_group)

        # 回测控制组
        control_group = QGroupBox("回测控制")
        control_layout = QHBoxLayout(control_group)

        self.run_backtest_btn = QPushButton("运行回测")
        self.run_backtest_btn.clicked.connect(self._run_backtest)
        control_layout.addWidget(self.run_backtest_btn)

        self.stop_backtest_btn = QPushButton("停止回测")
        self.stop_backtest_btn.clicked.connect(self._stop_backtest)
        self.stop_backtest_btn.setEnabled(False)
        control_layout.addWidget(self.stop_backtest_btn)

        control_layout.addStretch()

        layout.addWidget(control_group)

        # 回测进度组
        progress_group = QGroupBox("回测进度")
        progress_layout = QVBoxLayout(progress_group)

        self.backtest_progress = QProgressBar()
        progress_layout.addWidget(self.backtest_progress)

        self.backtest_status_label = QLabel("准备就绪")
        progress_layout.addWidget(self.backtest_status_label)

        layout.addWidget(progress_group)

        # 回测结果组
        results_group = QGroupBox("回测结果")
        results_layout = QVBoxLayout(results_group)

        self.backtest_results = QTextEdit()
        self.backtest_results.setPlaceholderText("回测结果将显示在这里...")
        results_layout.addWidget(self.backtest_results)

        layout.addWidget(results_group)

        return tab

    # ==================== 事件处理 ====================

    def _toggle_manager(self):
        """切换管理器显示/隐藏."""
        if self.toggle_btn:
            if self.toggle_btn.text() == "◀":
                self.toggle_btn.setText("▶")
            else:
                self.toggle_btn.setText("◀")

    def _on_file_double_clicked(self, item: QTreeWidgetItem, _column: int):  # noqa: U100
        """文件双击事件."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or "path" not in data:
            return

        file_path = data["path"]
        if self.current_file_label:
            self.current_file_label.setText(f"当前文件: {file_path}")

        self._load_file(file_path)

    def _load_file(self, file_path: str):
        """加载文件."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if self.code_editor:
                self.code_editor.setPlainText(content)

            self.logger.info("文件加载成功: %s", file_path)

        except Exception as e:
            self.logger.error("加载文件失败: %s", e)
            self.show_error(f"加载文件失败: {e}")

    def _save_current_file(self):
        """保存当前文件."""
        if not self.code_editor:
            return

        code = self.code_editor.toPlainText()
        if code.strip():
            self.show_info("代码已保存")
        else:
            self.show_warning("代码为空，无需保存")

    def _format_code(self):
        """格式化代码."""
        if not self.code_editor:
            return

        code = self.code_editor.toPlainText()
        if not code.strip():
            self.show_warning("代码为空，无需格式化")
            return

        try:
            import autopep8

            formatted_code = autopep8.fix_code(code)
            self.code_editor.setPlainText(formatted_code)
            self.show_info("代码格式化完成")
        except ImportError:
            self.show_warning("需要安装autopep8: pip install autopep8")

    def _toggle_ai_assistant(self, checked: bool):
        """切换AI助手显示."""
        if self.ai_assistant_widget:
            self.ai_assistant_widget.setVisible(checked)

        if self.ai_assistant_btn:
            text = "🤖 隐藏AI助手" if checked else "🤖 显示AI助手"
            self.ai_assistant_btn.setText(text)

    def _send_to_ai(self):
        """发送消息给AI助手."""
        if not self.user_input or not self.ai_response:
            return

        message = self.user_input.text().strip()
        if not message:
            return

        self.ai_response.append(f"用户: {message}")
        self.user_input.clear()

        # vnpy集成后通过strategy_service调用AI功能
        self.ai_response.append("AI助手: [功能需要vnpy集成]")

    def _create_new_strategy(self):
        """新建策略."""
        self.show_info("新建策略功能需要vnpy集成")

    def _create_new_indicator(self):
        """新建指标."""
        self.show_info("新建指标功能需要vnpy集成")

    def _load_strategy_list(self):
        """加载策略列表."""
        if not self.backtest_target_combo:
            return

        try:
            strategy_dir = "strategies/user_strategies"
            if os.path.exists(strategy_dir):
                strategy_files = [
                    f
                    for f in os.listdir(strategy_dir)
                    if f.endswith(".py") and not f.startswith("__")
                ]
                self.backtest_target_combo.addItems(strategy_files)
            else:
                self.backtest_target_combo.addItem("(策略目录不存在)")

        except Exception as e:
            self.logger.error("加载策略列表失败: %s", e)

    def _run_backtest(self):
        """运行回测."""
        strategy_name = (
            self.backtest_target_combo.currentText() if self.backtest_target_combo else ""
        )
        start_date = self.start_date_input.text() if self.start_date_input else ""
        end_date = self.end_date_input.text() if self.end_date_input else ""

        if not strategy_name or not start_date or not end_date:
            self.show_warning("请填写完整的回测参数")
            return

        self.show_info(f"开始运行回测: {strategy_name}")

        if self.run_backtest_btn:
            self.run_backtest_btn.setEnabled(False)
        if self.stop_backtest_btn:
            self.stop_backtest_btn.setEnabled(True)
        if self.backtest_progress:
            self.backtest_progress.setValue(0)
        if self.backtest_status_label:
            self.backtest_status_label.setText("回测运行中...")

        # vnpy集成后通过strategy_service运行回测
        if self.backtest_results:
            self.backtest_results.setText("回测功能需要vnpy集成")
        if self.backtest_progress:
            self.backtest_progress.setValue(100)
        if self.backtest_status_label:
            self.backtest_status_label.setText("等待vnpy集成")

        if self.run_backtest_btn:
            self.run_backtest_btn.setEnabled(True)
        if self.stop_backtest_btn:
            self.stop_backtest_btn.setEnabled(False)

    def _stop_backtest(self):
        """停止回测."""
        self.show_info("停止回测")
        if self.run_backtest_btn:
            self.run_backtest_btn.setEnabled(True)
        if self.stop_backtest_btn:
            self.stop_backtest_btn.setEnabled(False)

    # ==================== 通用方法 ====================

    def connect_signals(self):
        """连接信号槽."""

    def refresh_data(self):
        """刷新数据."""
        self.show_info("策略中心数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.logger.info("策略中心界面已关闭")
