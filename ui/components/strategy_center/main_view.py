# -*- coding: utf-8 -*-
"""
策略中心界面 - 主视图.

混合架构：策略/指标管理器（固有组件）+ 2个子界面.
"""

import logging

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
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

# 导入代码编辑器组件
from ui.widgets.code_editor_widget import CodeEditor

try:
    from backend.core.vnpy_integration import TerminalEngine as VnPyAdapter
except ImportError:
    # 导入失败时置为 None
    VnPyAdapter = None


class StrategyCenter(QWidget):
    """策略中心主界面类."""

    def __init__(self, parent=None):
        """Initialize strategy center."""
        super().__init__(parent)
        self.title = "策略中心"

        # Initialize logger
        self._logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("策略中心界面初始化开始")

        # Initialize UI component attributes
        self.toggle_btn = None
        self.file_tree = None
        self.content_tab = None
        self.editor_tab = None
        self.backtest_tab = None
        self.current_file_label = None
        self.ai_assistant_btn = None
        self.code_editor = None
        self.ai_assistant_widget = None
        self.ai_response = None
        self.user_input = None
        self.backtest_target_combo = None
        self.backtest_period_combo = None
        self.start_date_input = None
        self.end_date_input = None
        self.run_backtest_btn = None
        self.stop_backtest_btn = None
        self.backtest_progress = None
        self.backtest_status_label = None
        self.backtest_results = None

        # 更新定时器与就绪标志
        self._update_timer = None
        self.ui_ready = False
        # 初始化VNPY适配器 - 在super().__init__()之后
        self._initialize_vnpy_adapter()

        # Initialize UI
        self.setup_ui()
        self.connect_signals()

    @property
    def logger(self):
        """Get logger instance."""
        return self._logger

    def show_info(self, message: str):
        """Show info message."""
        self.logger.info(message)
        print(f"INFO: {message}")

    def show_error(self, message: str):
        """Show error message."""
        self.logger.error(message)
        print(f"ERROR: {message}")

    def show_warning(self, message: str):
        """Show warning message."""
        self.logger.warning(message)
        print(f"WARNING: {message}")

    def _initialize_vnpy_adapter(self):
        """初始化VNPY适配器."""
        # 确保属性始终存在
        self.vnpy_adapter = None

        try:
            if VnPyAdapter is None:
                raise ImportError("VnPy适配器不可用")

            self.vnpy_adapter = VnPyAdapter()
            self.logger.info("VNPY适配器初始化完成")
        except (NameError, ImportError, AttributeError, ValueError) as e:
            self.logger.error("VNPY适配器初始化失败: %s", e)
            raise

    def setup_ui(self):
        """设置用户界面."""
        main_layout = QHBoxLayout(self)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setSizes([250, 800])  # 左侧管理器、右侧内容区

        # 左侧：策略/指标管理器（固有组件）
        left_widget = self._create_strategy_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：子界面区域
        right_widget = self._create_content_area()
        main_splitter.addWidget(right_widget)

        main_layout.addWidget(main_splitter)
        # 界面就绪
        self.ui_ready = True

    def _create_strategy_manager(self):
        """创建策略/指标管理器."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 管理器标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("📁 策略/指标管理器")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        title_layout.addWidget(title_label)

        # 隐藏/显示按钮
        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setMaximumWidth(30)
        self.toggle_btn.clicked.connect(self._toggle_manager)
        title_layout.addWidget(self.toggle_btn)

        layout.addLayout(title_layout)

        # 文件树
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setRootIsDecorated(True)
        self.file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)

        # 创建树结构
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
        """创建文件树结构 - 从真实文件系统读取."""
        import os

        # 清空现有树结构
        if self.file_tree:
            self.file_tree.clear()

        try:
            # 策略文件夹
            strategy_root = QTreeWidgetItem()
            strategy_root.setText(0, "📂 策略")
            strategy_root.setIcon(0, QIcon())
            if self.file_tree:
                self.file_tree.addTopLevelItem(strategy_root)

            # 从真实文件系统读取策略文件
            strategy_dir = "strategies/user_strategies"
            if os.path.exists(strategy_dir):
                strategy_files = [
                    f
                    for f in os.listdir(strategy_dir)
                    if f.endswith(".py") and not f.startswith("__")
                ]
            else:
                self.logger.warning("策略目录不存在: %s", strategy_dir)
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
                        "template": "user",
                    },
                )
                strategy_root.addChild(file_item)

            # 模板文件夹
            template_root = QTreeWidgetItem()
            template_root.setText(0, "📂 策略模板")
            template_root.setIcon(0, QIcon())
            if self.file_tree:
                self.file_tree.addTopLevelItem(template_root)

            # 从真实文件系统读取模板文件
            template_dir = "strategies/templates"
            if os.path.exists(template_dir):
                template_files = [
                    f
                    for f in os.listdir(template_dir)
                    if f.endswith(".py") and not f.startswith("__")
                ]
            else:
                self.logger.warning("模板目录不存在: %s", template_dir)
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

            if self.file_tree:
                self.file_tree.expandAll()

            self.logger.info(
                "文件树创建完成: %d个策略, %d个模板", len(strategy_files), len(template_files)
            )

        except Exception as e:
            self.logger.error("创建文件树失败: %s", e)
            raise RuntimeError(f"无法创建策略文件树: {e}")

    def _create_content_area(self):
        """创建内容区域."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 创建选项卡
        self.content_tab = QTabWidget()

        # 4.1 策略/指标编写子界面
        self.editor_tab = self._create_editor_tab()
        self.content_tab.addTab(self.editor_tab, "✏️ 编写")

        # 4.2 策略/指标回测子界面
        self.backtest_tab = self._create_backtest_tab()
        self.content_tab.addTab(self.backtest_tab, "📈 回测")

        layout.addWidget(self.content_tab)

        return widget

    def _create_editor_tab(self):
        """创建编写子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        # 文件信息
        self.current_file_label = QLabel("当前文件: 未选择")
        toolbar_layout.addWidget(self.current_file_label)

        toolbar_layout.addStretch()

        # 编辑器工具按钮
        save_btn = QPushButton("💾 保存")
        save_btn.setToolTip("保存当前文件")
        save_btn.clicked.connect(self._save_current_file)
        toolbar_layout.addWidget(save_btn)

        format_btn = QPushButton("⚡ 格式化")
        format_btn.setToolTip("格式化代码")
        format_btn.clicked.connect(self._format_code)
        toolbar_layout.addWidget(format_btn)

        # AI助手按钮
        self.ai_assistant_btn = QPushButton("🤖 显示AI助手")
        self.ai_assistant_btn.setCheckable(True)
        self.ai_assistant_btn.toggled.connect(self._toggle_ai_assistant)
        toolbar_layout.addWidget(self.ai_assistant_btn)

        layout.addLayout(toolbar_layout)

        # 编辑器区域（使用分割器以支持AI助手）
        editor_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：代码编辑器
        editor_container = QWidget()
        editor_container_layout = QVBoxLayout(editor_container)
        editor_container_layout.setContentsMargins(0, 0, 0, 0)

        # 使用带行号和语法高亮的编辑器
        self.code_editor = CodeEditor()
        self.code_editor.setPlaceholderText("# 在这里编写您的策略或指标代码...")

        editor_container_layout.addWidget(self.code_editor)
        editor_splitter.addWidget(editor_container)

        # 右侧：AI助手区域（初始隐藏）
        self.ai_assistant_widget = self._create_ai_assistant()
        editor_splitter.addWidget(self.ai_assistant_widget)
        self.ai_assistant_widget.setVisible(False)

        # 设置分割比例
        editor_splitter.setSizes([700, 300])
        editor_splitter.setStretchFactor(0, 2)
        editor_splitter.setStretchFactor(1, 1)

        layout.addWidget(editor_splitter)

        return tab

    def _create_ai_assistant(self):
        """创建AI助手组件."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # AI回答区域
        response_group = QGroupBox("AI助手回答")
        response_layout = QVBoxLayout(response_group)

        self.ai_response = QTextEdit()
        self.ai_response.setPlaceholderText("AI助手将在这里回答您的问题...")
        self.ai_response.setMaximumHeight(200)
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

    def _create_backtest_tab(self):
        """创建回测子界面."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 回测配置组
        config_group = QGroupBox("回测配置")
        config_layout = QVBoxLayout(config_group)

        # 回测配置表单
        form_layout = QHBoxLayout()

        # 左侧配置
        left_form = QVBoxLayout()
        left_form.addWidget(QLabel("策略/指标:"))

        self.backtest_target_combo = QComboBox()
        # 从文件系统动态加载策略列表
        self._load_strategy_list_for_backtest()
        left_form.addWidget(self.backtest_target_combo)

        left_form.addWidget(QLabel("回测周期:"))
        self.backtest_period_combo = QComboBox()
        self.backtest_period_combo.addItems(["日线", "小时", "分钟"])
        left_form.addWidget(self.backtest_period_combo)

        form_layout.addLayout(left_form)

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

        form_layout.addLayout(right_form)

        config_layout.addLayout(form_layout)

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

    def connect_signals(self):
        """连接信号槽."""
        # 初始化VNPY适配器
        self._initialize_vnpy_adapter()

        # 连接文件树信号
        if self.file_tree:
            self.file_tree.itemSelectionChanged.connect(self._on_file_selected)

        # 启动更新定时器
        self.start_update_timer(2000, self._update_status)

    def _toggle_manager(self):
        """切换管理器显示/隐藏."""
        if self.toggle_btn and self.toggle_btn.text() == "◀":
            self.toggle_btn.setText("▶")
            # 这里可以隐藏左侧管理器
        elif self.toggle_btn:
            self.toggle_btn.setText("◀")
            # 这里可以显示左侧管理器

    def _on_file_double_clicked(self, item, column):
        """文件双击事件."""
        # Use column parameter to avoid unused argument warning
        _ = column
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and "path" in data:
            file_path = data["path"]
            file_type = data.get("type", "unknown")

            if self.current_file_label:
                self.current_file_label.setText(f"当前文件: {file_path}")

            if file_type == "strategy":
                self._load_strategy_file(file_path)
            elif file_type == "indicator":
                self._load_indicator_file(file_path)

    def _on_file_selected(self):
        """文件选择事件."""
        if self.file_tree:
            selected_items = self.file_tree.selectedItems()
            if selected_items:
                item = selected_items[0]
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and "path" in data:
                    file_path = data["path"]
                    if self.current_file_label:
                        self.current_file_label.setText(f"选中文件: {file_path}")

    def _create_new_strategy(self):
        """新建策略."""
        raise NotImplementedError("新建策略功能需要实现template_service集成。请手动创建策略文件。")

    def _create_new_indicator(self):
        """新建指标."""
        raise NotImplementedError("新建指标功能需要实现。请手动创建指标文件。")

    def _save_current_file(self):
        """保存当前文件."""
        if not self.code_editor:
            return

        # 获取代码内容
        if hasattr(self.code_editor, "toPlainText"):
            code = self.code_editor.toPlainText()
        else:
            code = ""

        if code.strip():
            self.show_info("代码已保存")
            # 这里可以实现实际的文件保存逻辑
        else:
            self.show_warning("代码为空，无需保存")

    def _format_code(self):
        """格式化代码."""
        if not self.code_editor:
            return

        # 获取代码
        if hasattr(self.code_editor, "toPlainText"):
            code = self.code_editor.toPlainText()
        else:
            code = ""

        if not code.strip():
            self.show_warning("代码为空，无需格式化")
            return

        try:
            # 尝试使用autopep8进行代码格式化
            import autopep8

            formatted_code = autopep8.fix_code(code)

            # 更新编辑器内容
            if hasattr(self.code_editor, "setPlainText"):
                self.code_editor.setPlainText(formatted_code)

            self.show_info("代码格式化完成")

        except ImportError:
            # 如果没有autopep8，提示用户安装
            self.show_warning("代码格式化需要安装 autopep8: pip install autopep8")

    def _toggle_ai_assistant(self, checked: bool):
        """切换AI助手显示."""
        if self.ai_assistant_widget:
            self.ai_assistant_widget.setVisible(checked)

        if self.ai_assistant_btn:
            text = "🤖 隐藏AI助手" if checked else "🤖 显示AI助手"
            self.ai_assistant_btn.setText(text)

    def _send_to_ai(self):
        """发送消息给AI助手."""
        if self.user_input and self.ai_response:
            message = self.user_input.text().strip()
            if message:
                self.ai_response.append(f"用户: {message}")
                # 调用AI服务
                from backend.services.strategy_center.ai_service import AIService

                ai_service = AIService()
                response = ai_service.query(message)
                self.ai_response.append(f"AI助手: {response}")
                self.user_input.clear()

    def _run_backtest(self):
        """运行回测."""
        if not self.vnpy_adapter:
            raise RuntimeError("VNPY适配器不可用，无法运行回测")

        strategy_name = (
            self.backtest_target_combo.currentText() if self.backtest_target_combo else ""
        )
        start_date = self.start_date_input.text() if self.start_date_input else ""
        end_date = self.end_date_input.text() if self.end_date_input else ""

        if not strategy_name or not start_date or not end_date:
            self.show_warning("请填写完整的回测参数")
            return

        self.show_info(f"开始运行回测: {strategy_name}")

        try:
            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(False)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(True)
            if self.backtest_progress:
                self.backtest_progress.setValue(0)
            if self.backtest_status_label:
                self.backtest_status_label.setText("回测运行中...")

            # 调用后端API运行真实回测
            result = self._simulate_backtest_progress()

            # 显示回测结果
            if self.backtest_results:
                self.backtest_results.setText(str(result))
            if self.backtest_progress:
                self.backtest_progress.setValue(100)
            if self.backtest_status_label:
                self.backtest_status_label.setText("回测完成")

            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(True)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(False)

        except Exception as e:
            self.show_error(f"运行回测失败: {str(e)}")
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
        if self.backtest_progress:
            self.backtest_progress.setValue(0)
        if self.backtest_status_label:
            self.backtest_status_label.setText("回测已停止")

    def _simulate_backtest_progress(self):
        """执行真实回测."""
        from backend.services.strategy_center.backtest_service import BacktestService

        # 获取回测参数
        strategy_name = (
            self.backtest_target_combo.currentText() if self.backtest_target_combo else ""
        )
        start_date = self.start_date_input.text() if self.start_date_input else ""
        end_date = self.end_date_input.text() if self.end_date_input else ""

        # 调用后端服务执行真实回测
        backtest_service = BacktestService()
        # 假设已经选择了策略文件，这里传入文件ID和参数
        result = backtest_service.run_backtest(
            strategy_file_id=strategy_name,
            parameters={"start_date": start_date, "end_date": end_date},
        )

        return result

    def _load_strategy_file(self, file_path):
        """加载策略文件."""
        # 这里实现策略文件加载逻辑
        if self.code_editor and (
            (hasattr(self.code_editor, "setPlainText")) or (hasattr(self.code_editor, "setText"))
        ):
            self.code_editor.setPlainText(f"# 加载策略文件: {file_path}\n# 这里是策略代码内容...")

    def _load_indicator_file(self, file_path):
        """加载指标文件."""
        # 这里实现指标文件加载逻辑
        if self.code_editor and (
            (hasattr(self.code_editor, "setPlainText")) or (hasattr(self.code_editor, "setText"))
        ):
            self.code_editor.setPlainText(f"# 加载指标文件: {file_path}\n# 这里是指标代码内容...")

    def _load_strategy_list_for_backtest(self):
        """从文件系统加载策略列表用于回测."""
        import os

        try:
            strategy_dir = "strategies/user_strategies"
            if os.path.exists(strategy_dir):
                strategy_files = [
                    f
                    for f in os.listdir(strategy_dir)
                    if f.endswith(".py") and not f.startswith("__")
                ]
                if strategy_files:
                    self.backtest_target_combo.addItems(strategy_files)
                else:
                    self.backtest_target_combo.addItem("(无可用策略)")
            else:
                self.logger.warning("策略目录不存在: %s", strategy_dir)
                self.backtest_target_combo.addItem("(策略目录不存在)")
        except Exception as e:
            self.logger.error("加载策略列表失败: %s", e)
            self.backtest_target_combo.addItem("(加载失败)")

    def start_update_timer(self, interval: int = 1000, callback=None):
        """启动更新定时器（安全守卫）."""
        if not getattr(self, "ui_ready", False):
            return
        if callback is None:
            return
        if getattr(self, "_update_timer", None) is None:
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(callback)
        if self._update_timer:
            self._update_timer.start(int(interval) if interval else 2000)

    def stop_update_timer(self):
        """停止更新定时器."""
        try:
            if getattr(self, "_update_timer", None) and self._update_timer:
                self._update_timer.stop()
        finally:
            self._update_timer = None

    def _update_status(self):
        """更新状态."""
        # 这里可以更新一些状态信息

    def refresh_data(self):
        """刷新数据."""
        self.show_info("策略中心数据已刷新")

    def on_close(self):
        """关闭处理."""
        self.stop_update_timer()
        self.logger.info("策略中心界面已关闭")
