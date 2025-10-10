# -*- coding: utf-8 -*-
"""策略中心界面 - 重构版（现代IDE风格）.

采用现代IDE架构：
- 左侧：文件管理器（支持右键菜单、拖拽、搜索）
- 中央：多标签编辑器（支持多文件同时编辑）
- 右侧：AI助手（可隐藏）
- 底部：回测面板、终端、调试控制台（可折叠）
"""

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
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
    QVBoxLayout,
    QWidget,
)

from backend.core.base import get_service_manager
from backend.core.utils import LoggerMixin
from ui.widgets.base_widget import BaseWidget

# 导入新的组件
from ui.components.strategy_center.editor_tabs import EditorTabWidget
from ui.components.strategy_center.file_explorer import FileExplorerWidget


class StrategyCenterRefactored(BaseWidget, LoggerMixin):
    """策略中心主界面（重构版）- 现代IDE风格."""

    def __init__(self, parent=None):
        """初始化策略中心."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.strategy_service = None

        # 初始化UI组件
        self.file_explorer: Optional[FileExplorerWidget] = None
        self.editor_tabs: Optional[EditorTabWidget] = None
        self.ai_assistant_widget: Optional[QWidget] = None
        self.ai_assistant_btn: Optional[QPushButton] = None
        self.ai_response: Optional[QTextEdit] = None
        self.user_input: Optional[QLineEdit] = None

        # 回测相关组件
        self.backtest_panel: Optional[QWidget] = None
        self.backtest_target_combo: Optional[QComboBox] = None
        self.renderer_type_combo: Optional[QComboBox] = None
        self.start_date_input: Optional[QLineEdit] = None
        self.end_date_input: Optional[QLineEdit] = None
        self.run_backtest_btn: Optional[QPushButton] = None
        self.stop_backtest_btn: Optional[QPushButton] = None
        self.backtest_progress: Optional[QProgressBar] = None
        self.backtest_status_label: Optional[QLabel] = None
        self.backtest_results: Optional[QTextEdit] = None

        # 回测任务追踪
        self.current_backtest_task_id: Optional[str] = None
        self.backtest_timer: Optional[QTimer] = None

        # 调用父类初始化
        super().__init__(parent, "策略中心（IDE模式）")
        self.logger.info("策略中心界面（重构版）初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取策略中心服务."""
        try:
            self.strategy_service = self.service_manager.get_service("strategy_center_service")
            if self.strategy_service:
                self.logger.info("策略中心服务获取成功")
            else:
                self.logger.warning("策略中心服务未注册")
        except Exception as e:
            self.logger.error("获取策略中心服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面 - 恢复原架构：左侧策略管理器 + 右侧子页面切换."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 创建主分割器（水平）
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：策略/指标管理器（固定组件）
        left_widget = self._create_strategy_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：子界面区域（QTabWidget切换）
        right_widget = self._create_content_tabs()
        main_splitter.addWidget(right_widget)

        # 设置初始大小比例：左侧250，右侧800
        main_splitter.setSizes([250, 800])

        main_layout.addWidget(main_splitter)

    def _create_strategy_manager(self) -> QWidget:
        """创建策略/指标管理器（固定组件）.

        Returns:
            QWidget: 策略管理器组件
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("📁 策略/指标管理器")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 文件管理器（使用增强版）
        self.file_explorer = FileExplorerWidget("strategies/user_strategies")
        layout.addWidget(self.file_explorer)

        return widget

    def _create_content_tabs(self) -> QWidget:
        """创建右侧内容标签页（子界面切换）.

        Returns:
            QWidget: 内容标签页组件
        """
        # 创建标签页容器
        self.content_tab = QTabWidget()
        self.content_tab.setDocumentMode(True)

        # Tab1: 策略编写（IDE编辑器）
        self.editor_tab = self._create_editor_tab()
        self.content_tab.addTab(self.editor_tab, "📝 策略编写")

        # Tab2: 策略回测
        self.backtest_tab = self._create_backtest_tab()
        self.content_tab.addTab(self.backtest_tab, "📊 策略回测")

        return self.content_tab

    def _create_editor_tab(self) -> QWidget:
        """创建策略编写标签页.

        Returns:
            QWidget: 编辑器标签页组件
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # 编辑器 + AI助手（水平分割）
        editor_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 多标签编辑器
        self.editor_tabs = EditorTabWidget()
        editor_splitter.addWidget(self.editor_tabs)

        # AI助手
        self.ai_assistant_widget = self._create_ai_assistant()
        editor_splitter.addWidget(self.ai_assistant_widget)
        self.ai_assistant_widget.setVisible(False)

        editor_splitter.setSizes([800, 300])

        layout.addWidget(editor_splitter)

        return widget

    def _create_backtest_tab(self) -> QWidget:
        """创建策略回测标签页.

        Returns:
            QWidget: 回测标签页组件
        """
        # 使用现有的回测面板创建方法
        return self._create_backtest_panel()

    def _create_toolbar(self) -> QWidget:
        """创建工具栏.

        Returns:
            QWidget: 工具栏组件
        """
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)

        # 文件操作按钮
        new_btn = QPushButton("📄 新建")
        new_btn.clicked.connect(self._create_new_strategy)
        layout.addWidget(new_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(self._save_current_file)
        layout.addWidget(save_btn)

        save_all_btn = QPushButton("💾 保存全部")
        save_all_btn.clicked.connect(self._save_all_files)
        layout.addWidget(save_all_btn)

        layout.addSpacing(20)

        # 格式化按钮
        format_btn = QPushButton("⚡ 格式化")
        format_btn.clicked.connect(self._format_code)
        layout.addWidget(format_btn)

        layout.addSpacing(20)

        # AI助手按钮
        self.ai_assistant_btn = QPushButton("🤖 显示AI助手")
        self.ai_assistant_btn.setCheckable(True)
        self.ai_assistant_btn.toggled.connect(self._toggle_ai_assistant)
        layout.addWidget(self.ai_assistant_btn)

        layout.addStretch()

        # 当前文件路径标签
        current_file_label = QLabel("就绪")
        layout.addWidget(current_file_label)

        # 连接信号：当前文件切换时更新标签
        if self.editor_tabs:
            self.editor_tabs.current_file_changed.connect(
                lambda path: current_file_label.setText(f"📄 {Path(path).name}")
            )

        return toolbar

    def _create_ai_assistant(self) -> QWidget:
        """创建AI助手组件.

        Returns:
            QWidget: AI助手组件
        """
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

    def _create_backtest_tab(self) -> QWidget:
        """创建策略回测标签页.

        Returns:
            QWidget: 回测标签页组件
        """
        # 使用现有的回测面板创建方法
        return self._create_backtest_panel()

    def _create_backtest_panel(self) -> QWidget:
        """创建回测面板.

        Returns:
            QWidget: 回测面板组件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 回测配置
        config_group = QGroupBox("回测配置")
        config_layout = QHBoxLayout(config_group)

        # 左侧配置
        left_form = QVBoxLayout()
        left_form.addWidget(QLabel("策略/指标:"))

        self.backtest_target_combo = QComboBox()
        self._load_strategy_list()
        left_form.addWidget(self.backtest_target_combo)

        left_form.addWidget(QLabel("展示模板:"))
        self.renderer_type_combo = QComboBox()
        self.renderer_type_combo.addItems(
            ["默认展示", "CTA策略", "算法交易", "期权策略", "组合策略", "价差交易", "脚本交易"]
        )
        left_form.addWidget(self.renderer_type_combo)

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

        # 回测控制
        control_layout = QHBoxLayout()

        self.run_backtest_btn = QPushButton("▶️ 运行回测")
        self.run_backtest_btn.clicked.connect(self._run_backtest)
        control_layout.addWidget(self.run_backtest_btn)

        self.stop_backtest_btn = QPushButton("⏹️ 停止回测")
        self.stop_backtest_btn.clicked.connect(self._stop_backtest)
        self.stop_backtest_btn.setEnabled(False)
        control_layout.addWidget(self.stop_backtest_btn)

        control_layout.addStretch()

        layout.addLayout(control_layout)

        # 回测进度
        progress_group = QGroupBox("回测进度")
        progress_layout = QVBoxLayout(progress_group)

        self.backtest_progress = QProgressBar()
        progress_layout.addWidget(self.backtest_progress)

        self.backtest_status_label = QLabel("准备就绪")
        progress_layout.addWidget(self.backtest_status_label)

        layout.addWidget(progress_group)

        # 回测结果
        results_group = QGroupBox("回测结果")
        results_layout = QVBoxLayout(results_group)

        self.backtest_results = QTextEdit()
        self.backtest_results.setPlaceholderText("回测结果将显示在这里...")
        results_layout.addWidget(self.backtest_results)

        layout.addWidget(results_group)

        return panel

    # ==================== 事件处理 ====================

    def connect_signals(self):
        """连接信号槽."""
        # 文件管理器信号
        if self.file_explorer:
            self.file_explorer.file_double_clicked.connect(self._on_file_double_clicked)

        # 编辑器标签信号
        if self.editor_tabs:
            self.editor_tabs.file_saved.connect(self._on_file_saved)

    def _on_file_double_clicked(self, file_path: str):
        """文件双击事件.

        Args:
            file_path: 文件路径
        """
        if self.editor_tabs:
            self.editor_tabs.open_file(file_path)
            self.logger.info(f"打开文件: {file_path}")

    def _on_file_saved(self, file_path: str):
        """文件保存事件.

        Args:
            file_path: 文件路径
        """
        self.logger.info(f"文件已保存: {file_path}")
        self.show_info(f"文件已保存: {Path(file_path).name}")

    def _create_new_strategy(self):
        """新建策略."""
        if not self.strategy_service:
            self.show_error("策略中心服务不可用")
            return

        from PySide6.QtWidgets import QInputDialog

        # 弹出对话框让用户输入策略名称
        strategy_name, ok = QInputDialog.getText(
            self, "新建策略", "请输入策略名称:", text="my_strategy"
        )

        if ok and strategy_name:
            # 确保文件名有.py后缀
            if not strategy_name.endswith(".py"):
                strategy_name = f"{strategy_name}.py"

            # 创建策略文件
            result = self.strategy_service.create_strategy_file(
                file_path=strategy_name, template_type="cta"
            )

            if result.get("success"):
                self.show_info(f"策略 '{strategy_name}' 创建成功")

                # 刷新文件树
                if self.file_explorer:
                    self.file_explorer.refresh()

                # 打开新创建的文件
                file_path = f"strategies/user_strategies/{strategy_name}"
                if self.editor_tabs:
                    self.editor_tabs.open_file(file_path)
            else:
                self.show_error(f"创建策略失败: {result.get('message', '未知错误')}")

    def _save_current_file(self):
        """保存当前文件."""
        if self.editor_tabs:
            if self.editor_tabs.save_file():
                self.show_info("文件已保存")
            else:
                self.show_warning("没有打开的文件")

    def _save_all_files(self):
        """保存所有文件."""
        if self.editor_tabs:
            count = self.editor_tabs.save_all_files()
            if count > 0:
                self.show_info(f"已保存 {count} 个文件")
            else:
                self.show_info("没有需要保存的文件")

    def _format_code(self):
        """格式化代码."""
        current_editor = self.editor_tabs.get_current_editor() if self.editor_tabs else None

        if not current_editor:
            self.show_warning("没有打开的文件")
            return

        code = current_editor.toPlainText()
        if not code.strip():
            self.show_warning("代码为空")
            return

        try:
            import autopep8

            formatted_code = autopep8.fix_code(code)
            current_editor.setPlainText(formatted_code)
            self.show_info("代码格式化完成")
        except ImportError:
            self.show_warning("需要安装autopep8: pip install autopep8")

    def _toggle_ai_assistant(self, checked: bool):
        """切换AI助手显示.

        Args:
            checked: 是否显示
        """
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

        # 显示用户消息
        self.ai_response.append(f"\n>>> 用户: {message}\n")
        self.user_input.clear()

        # 获取AI助手服务
        try:
            ai_service = self.service_manager.get_service("ai_assistant_service")
            if not ai_service:
                self.ai_response.append("❌ AI助手服务不可用\n")
                return

            # 获取当前编辑器中的代码作为上下文
            context = {}
            current_editor = self.editor_tabs.get_current_editor() if self.editor_tabs else None
            if current_editor:
                current_code = current_editor.toPlainText()
                if current_code.strip():
                    context["strategy_code"] = current_code

            # 调用AI服务
            response = ai_service.chat(message, context=context)

            if not response.get("success"):
                error_msg = response.get("message", "未知错误")
                self.ai_response.append(f"❌ AI调用失败: {error_msg}\n")
                return

            # 处理AI回复
            message_type = response.get("message_type", "text")

            if message_type == "code":
                # 纯代码 - 插入到编辑器
                code = response.get("code", "")
                if code and current_editor:
                    current_editor.insertPlainText(f"\n{code}\n")
                    self.ai_response.append("✅ 代码已插入到编辑器\n")

            elif message_type == "text":
                # 纯文本 - 显示在AI反馈区
                text = response.get("text", response.get("message", ""))
                self.ai_response.append(f"🤖 AI助手:\n{text}\n")

            elif message_type == "mixed":
                # 混合内容
                code = response.get("code", "")
                text = response.get("text", "")

                if text:
                    self.ai_response.append(f"🤖 AI助手:\n{text}\n")

                if code and current_editor:
                    current_editor.insertPlainText(f"\n{code}\n")
                    self.ai_response.append("\n✅ 代码部分已插入到编辑器\n")

            # 如果AI修改了文件，刷新文件树
            files_modified = response.get("files_modified", [])
            if files_modified:
                self.ai_response.append(f"\n📁 AI助手已保存文件: {', '.join(files_modified)}\n")

                # 刷新文件树
                if self.file_explorer:
                    self.file_explorer.refresh()

                # 如果只修改了一个文件，自动打开
                if len(files_modified) == 1 and self.editor_tabs:
                    file_path = files_modified[0]
                    self.editor_tabs.open_file(file_path)
                    self.ai_response.append(f"✅ 文件已打开: {file_path}\n")

        except Exception as e:
            self.logger.error("AI助手调用失败: %s", e)
            self.ai_response.append(f"❌ 错误: {str(e)}\n")

    def _load_strategy_list(self):
        """加载策略列表到下拉框."""
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
        if not self.strategy_service:
            self.show_error("策略中心服务不可用")
            return

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

        # 获取展示模板类型
        renderer_type_text = (
            self.renderer_type_combo.currentText() if self.renderer_type_combo else "默认展示"
        )
        renderer_type_map = {
            "默认展示": "default",
            "CTA策略": "cta",
            "算法交易": "algo",
            "期权策略": "option",
            "组合策略": "portfolio",
            "价差交易": "spread",
            "脚本交易": "script",
        }
        renderer_type = renderer_type_map.get(renderer_type_text, "default")

        # 通过strategy_service运行回测
        backtest_config = {
            "start_date": start_date,
            "end_date": end_date,
            "capital": 1000000,
            "symbol": "000001",
            "exchange": "SZSE",
            "interval": "1d",
            "renderer_type": renderer_type,
        }

        result = self.strategy_service.start_backtest(
            strategy_file=strategy_name, config=backtest_config
        )

        if result.get("success"):
            self.current_backtest_task_id = result.get("task_id")
            self.show_info("回测已启动，正在后台运行...")

            # 启动进度监控定时器
            self.backtest_timer = QTimer()
            self.backtest_timer.timeout.connect(self._check_backtest_progress)
            self.backtest_timer.start(1000)  # 每秒检查一次
        else:
            self.show_error(f"启动回测失败: {result.get('message', '未知错误')}")
            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(True)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(False)

    def _check_backtest_progress(self):
        """检查回测进度."""
        if not self.strategy_service or not hasattr(self, "current_backtest_task_id"):
            return

        status = self.strategy_service.get_backtest_status(self.current_backtest_task_id)

        if not status:
            return

        progress = status.get("progress", 0)
        task_status = status.get("status", "unknown")

        # 更新进度条
        if self.backtest_progress:
            self.backtest_progress.setValue(progress)

        # 更新状态
        if self.backtest_status_label:
            self.backtest_status_label.setText(f"回测进度: {progress}%")

        # 检查是否完成
        if task_status == "completed":
            result = status.get("result", {})

            # 显示结果
            result_text = "=== 回测结果 ===\n"
            result_text += f"总收益率: {result.get('total_return', 0)*100:.2f}%\n"
            result_text += f"夏普比率: {result.get('sharpe_ratio', 0):.2f}\n"
            result_text += f"最大回撤: {result.get('max_drawdown', 0)*100:.2f}%\n"
            result_text += f"交易次数: {result.get('total_trades', 0)}\n"
            result_text += f"胜率: {result.get('winning_rate', 0)*100:.2f}%\n"
            result_text += f"\n{result.get('message', '')}"

            if self.backtest_results:
                self.backtest_results.setText(result_text)

            self.show_info("回测已完成")

            # 停止定时器
            if self.backtest_timer is not None:
                self.backtest_timer.stop()

            # 恢复按钮状态
            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(True)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(False)

        elif task_status == "failed":
            error = status.get("result", {}).get("error", "未知错误")
            self.show_error(f"回测失败: {error}")

            if self.backtest_results:
                self.backtest_results.setText(f"回测失败:\n{error}")

            # 停止定时器
            if self.backtest_timer is not None:
                self.backtest_timer.stop()

            # 恢复按钮状态
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

    def refresh_data(self):
        """刷新数据."""
        # 刷新文件树
        if self.file_explorer:
            self.file_explorer.refresh()

        self.logger.info("策略中心数据已手动刷新")

    def on_close(self):
        """关闭处理."""
        # 提示保存未保存的文件
        if self.editor_tabs:
            if self.editor_tabs.unsaved_files:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self,
                    "保存文件",
                    f"有 {len(self.editor_tabs.unsaved_files)} 个文件未保存。是否保存？",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )

                if reply == QMessageBox.StandardButton.Save:
                    self.editor_tabs.save_all_files()
                elif reply == QMessageBox.StandardButton.Cancel:
                    return False

        self.logger.info("策略中心界面已关闭")
        return True
