# -*- coding: utf-8 -*-
"""
图表工具栏组件

提供K线图表的画线工具、十字光标等高级交互功能
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)


class ChartToolbar(QWidget):
    """图表工具栏."""

    # 信号定义
    tool_changed = Signal(str)  # 工具切换信号
    crosshair_toggled = Signal(bool)  # 十字光标切换
    drawing_mode_changed = Signal(str)  # 画线模式切换

    def __init__(self, parent=None):
        """初始化工具栏."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """设置UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 工具标签
        layout.addWidget(QLabel("图表工具:"))

        # 创建工具按钮组（互斥）
        self.tool_group = QButtonGroup(self)

        # 选择工具（默认）
        select_btn = QToolButton()
        select_btn.setText("🖱️ 选择")
        select_btn.setCheckable(True)
        select_btn.setChecked(True)
        select_btn.setToolTip("选择和拖动模式")
        select_btn.clicked.connect(lambda: self.tool_changed.emit("select"))
        self.tool_group.addButton(select_btn, 0)
        layout.addWidget(select_btn)

        # 十字光标
        crosshair_btn = QToolButton()
        crosshair_btn.setText("✛ 十字")
        crosshair_btn.setCheckable(True)
        crosshair_btn.setToolTip("十字光标（显示价格和时间）")
        crosshair_btn.toggled.connect(self.crosshair_toggled.emit)
        layout.addWidget(crosshair_btn)
        self.crosshair_btn = crosshair_btn

        # 画线工具分隔符
        layout.addWidget(QLabel("|"))
        layout.addWidget(QLabel("画线:"))

        # 趋势线
        trend_btn = QToolButton()
        trend_btn.setText("📈 趋势")
        trend_btn.setCheckable(True)
        trend_btn.setToolTip("绘制趋势线")
        trend_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("trend"))
        self.tool_group.addButton(trend_btn, 1)
        layout.addWidget(trend_btn)

        # 水平线
        hline_btn = QToolButton()
        hline_btn.setText("━ 水平")
        hline_btn.setCheckable(True)
        hline_btn.setToolTip("绘制水平线（支撑位/压力位）")
        hline_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("hline"))
        self.tool_group.addButton(hline_btn, 2)
        layout.addWidget(hline_btn)

        # 垂直线
        vline_btn = QToolButton()
        vline_btn.setText("┃ 垂直")
        vline_btn.setCheckable(True)
        vline_btn.setToolTip("绘制垂直线（时间标记）")
        vline_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("vline"))
        self.tool_group.addButton(vline_btn, 3)
        layout.addWidget(vline_btn)

        # 矩形框
        rect_btn = QToolButton()
        rect_btn.setText("▭ 矩形")
        rect_btn.setCheckable(True)
        rect_btn.setToolTip("绘制矩形框（区域标记）")
        rect_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("rectangle"))
        self.tool_group.addButton(rect_btn, 4)
        layout.addWidget(rect_btn)

        # 文本标注
        text_btn = QToolButton()
        text_btn.setText("📝 文本")
        text_btn.setCheckable(True)
        text_btn.setToolTip("添加文本标注")
        text_btn.clicked.connect(lambda: self.drawing_mode_changed.emit("text"))
        self.tool_group.addButton(text_btn, 5)
        layout.addWidget(text_btn)

        # 工具分隔符
        layout.addWidget(QLabel("|"))

        # 撤销/重做
        undo_btn = QPushButton("↶ 撤销")
        undo_btn.setToolTip("撤销上一步操作")
        undo_btn.clicked.connect(self._on_undo)
        layout.addWidget(undo_btn)

        redo_btn = QPushButton("↷ 重做")
        redo_btn.setToolTip("重做")
        redo_btn.clicked.connect(self._on_redo)
        layout.addWidget(redo_btn)

        # 清除所有标注
        clear_all_btn = QPushButton("🗑️ 清除")
        clear_all_btn.setToolTip("清除所有画线和标注")
        clear_all_btn.clicked.connect(self._on_clear_all)
        layout.addWidget(clear_all_btn)

        # 缩放工具
        layout.addWidget(QLabel("|"))

        zoom_in_btn = QPushButton("🔍+ 放大")
        zoom_in_btn.clicked.connect(self._on_zoom_in)
        layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("🔍- 缩小")
        zoom_out_btn.clicked.connect(self._on_zoom_out)
        layout.addWidget(zoom_out_btn)

        reset_btn = QPushButton("⟲ 重置")
        reset_btn.setToolTip("重置缩放")
        reset_btn.clicked.connect(self._on_reset_zoom)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _on_undo(self):
        """撤销操作 - 这里可以实现撤销逻辑."""

    def _on_redo(self):
        """重做操作 - 这里可以实现重做逻辑."""

    def _on_clear_all(self):
        """清除所有标注 - 这里可以实现清除逻辑."""

    def _on_zoom_in(self):
        """放大 - 这里可以实现放大逻辑."""

    def _on_zoom_out(self):
        """缩小 - 这里可以实现缩小逻辑."""

    def _on_reset_zoom(self):
        """重置缩放 - 这里可以实现重置逻辑."""
