# -*- coding: utf-8 -*-
"""
响应式布局帮助类.

根据窗口大小自动调整UI布局
"""

from PySide6.QtCore import QObject, QSize, Signal


class ResponsiveHelper(QObject):
    """响应式布局帮助类."""

    # 信号定义
    size_class_changed = Signal(str)  # 尺寸级别变化信号：small/medium/large

    # 断点定义（像素）
    BREAKPOINT_SMALL = 800
    BREAKPOINT_MEDIUM = 1200
    BREAKPOINT_LARGE = 1600

    def __init__(self, parent=None):
        """初始化响应式帮助类."""
        super().__init__(parent)
        self._current_size_class = "medium"

    def get_size_class(self, width: int) -> str:
        """根据宽度获取尺寸级别."""
        if width < self.BREAKPOINT_SMALL:
            return "small"
        if width < self.BREAKPOINT_MEDIUM:
            return "medium"
        if width < self.BREAKPOINT_LARGE:
            return "large"

        return "xlarge"

    def update_size(self, size: QSize):
        """更新尺寸并发出信号."""
        width = size.width()
        new_class = self.get_size_class(width)

        if new_class != self._current_size_class:
            self._current_size_class = new_class
            self.size_class_changed.emit(new_class)

    @staticmethod
    def get_optimal_splitter_sizes(total_width: int, is_left_panel: bool = True):
        """获取优化的分割器尺寸."""
        if total_width < 800:
            # 小屏幕：隐藏侧边栏或最小化
            return [0, total_width] if is_left_panel else [total_width, 0]
        if total_width < 1200:
            # 中等屏幕：侧边栏较窄
            sidebar_width = 200
            return [sidebar_width, total_width - sidebar_width]
        if total_width < 1600:
            # 大屏幕：标准侧边栏
            sidebar_width = 250
            return [sidebar_width, total_width - sidebar_width]

        # 超大屏幕：较宽侧边栏
        sidebar_width = 300
        return [sidebar_width, total_width - sidebar_width]

    @staticmethod
    def get_table_page_size(height: int) -> int:
        """根据高度获取表格最优每页显示数量."""
        # 每行约30px高度
        row_height = 30
        header_height = 50
        pagination_height = 40

        available_height = height - header_height - pagination_height
        rows = max(10, available_height // row_height)

        # 取标准值
        if rows < 20:
            return 20
        if rows < 50:
            return 50
        if rows < 100:
            return 100

        return 200

    @staticmethod
    def get_font_size(width: int) -> int:
        """根据宽度获取最优字体大小."""
        if width < 800:
            return 9
        if width < 1200:
            return 10
        if width < 1600:
            return 11

        return 12

    @staticmethod
    def should_show_sidebar(width: int) -> bool:
        """判断是否应该显示侧边栏."""
        return width >= 800

    @staticmethod
    def get_card_columns(width: int) -> int:
        """获取卡片布局的列数."""
        if width < 800:
            return 1
        if width < 1200:
            return 2
        if width < 1600:
            return 3

        return 4
