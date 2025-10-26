# -*- coding: utf-8 -*-
"""
日志表格Model - 基于Qt Model/View架构的高性能实现.

遵循PySide6和VNPy最佳实践：
1. 数据-视图分离（Model/View架构）
2. 虚拟滚动（只渲染可见行）
3. 批量更新（避免频繁重绘）
4. 最小化主线程UI操作
"""

from typing import Any, List, Dict, Optional
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QBrush, QPalette


class LogTableModel(QAbstractTableModel):
    """日志表格数据模型（高性能实现）.

    架构优势：
    - Model只存储数据，View按需渲染
    - 支持虚拟滚动，只渲染可见行
    - 批量更新，一次性通知View刷新
    - 最小化对象创建，复用底层数据
    """

    # 列定义（第一列为复选框）
    HEADERS = ["☑", "时间", "级别", "模块", "函数", "行号", "消息"]
    COLUMN_KEYS = [None, "timestamp", "level", "module", "function", "line", "message"]

    # 级别文字颜色映射（使用深色文字，无背景色）
    LEVEL_COLORS = {
        "DEBUG": QColor(100, 100, 100),  # 深灰色
        "INFO": QColor(0, 100, 200),  # 深蓝色
        "WARNING": QColor(200, 120, 0),  # 深橙黄色
        "ERROR": QColor(200, 0, 0),  # 深红色
        "CRITICAL": QColor(139, 0, 0),  # 暗红色
    }

    # 选中行视觉反馈：复选框列左侧边框高亮
    SELECTED_INDICATOR_COLOR = QColor(0, 120, 215)  # 蓝色指示器

    def __init__(self, parent=None):
        """初始化Model."""
        super().__init__(parent)
        self._data: List[Dict[str, Any]] = []
        self._selected_rows: set = set()  # 存储选中的行索引

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """返回行数."""
        if parent.isValid():
            return 0
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """返回列数."""
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """返回表头数据。"""
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.HEADERS):
                if role == Qt.ItemDataRole.DisplayRole:
                    if section == 0:
                        # 动态三态：全未选☐、部分◩、全选☑
                        total = len(self._data)
                        selected = len(self._selected_rows)
                        if total == 0 or selected == 0:
                            mark = "☐"
                        elif selected == total:
                            mark = "☑"
                        else:
                            mark = "◩"
                        return f"{mark}"
                    return self.HEADERS[section]
                elif role == Qt.ItemDataRole.ToolTipRole:
                    # 🔧 关键修复：处理ToolTipRole，避免与setHeaderData()冲突
                    if section == 0:  # 复选框列
                        total = len(self._data)
                        selected = len(self._selected_rows)
                        if total == 0:
                            state = "无数据"
                        elif selected == 0:
                            state = "全未选"
                        elif selected == total:
                            state = "全选"
                        else:
                            state = "部分选择"
                        return f"点击切换全选/取消全选（当前：{state}）"
                    return None
                elif role == Qt.ItemDataRole.BackgroundRole:
                    # 为第一列表头设置柔和底色，避免白底突兀
                    if section == 0:
                        return QBrush(QColor(232, 244, 248))  # #E8F4F8
                elif role == Qt.ItemDataRole.ForegroundRole:
                    # 第一列使用深蓝文本以匹配主题
                    if section == 0:
                        return QBrush(QColor(0, 85, 170))  # 深蓝
                elif role == Qt.ItemDataRole.TextAlignmentRole:
                    # 居中显示三态符号
                    if section == 0:
                        return Qt.AlignmentFlag.AlignCenter
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """返回单元格标志（使复选框可交互）。"""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.column() == 0:  # 复选框列
            # 为复选框列加入 ItemIsSelectable，确保点击可触发CheckState切换
            return (
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """设置单元格数据（处理复选框点击）。"""
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            row = index.row()
            if value == Qt.CheckState.Checked:
                self._selected_rows.add(row)
            else:
                self._selected_rows.discard(row)
            # 通知整行数据变化（以便更新行背景色）
            left_index = self.index(row, 0)
            right_index = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(left_index, right_index)
            # 刷新表头三态
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)
            return True
        return False

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """返回单元格数据（按需提供，View调用时才计算）."""
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._data):
            return None
        if col < 0 or col >= len(self.COLUMN_KEYS):
            return None

        # 第一列：复选框
        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return (
                    Qt.CheckState.Checked if row in self._selected_rows else Qt.CheckState.Unchecked
                )
            if role == Qt.ItemDataRole.TextAlignmentRole:
                # 居中显示复选状态
                return Qt.AlignmentFlag.AlignCenter
            if role == Qt.ItemDataRole.BackgroundRole:
                # 选中：浅蓝高亮；未选中：与表格行底色保持一致（Base/AlternateBase）
                if row in self._selected_rows:
                    return QBrush(QColor(220, 235, 255))
                try:
                    from PySide6.QtWidgets import QApplication

                    app = QApplication.instance()
                    palette = QPalette()
                    if app is not None and isinstance(app, QApplication):
                        palette = app.palette()
                except Exception:
                    palette = QPalette()

                color = (
                    palette.color(QPalette.ColorRole.AlternateBase)
                    if (row % 2) == 1
                    else palette.color(QPalette.ColorRole.Base)
                )
                return QBrush(color)
            # 其他角色：使用默认渲染
            return None

        record = self._data[row]

        # 显示角色：返回文本
        if role == Qt.ItemDataRole.DisplayRole:
            key = self.COLUMN_KEYS[col]
            value = record.get(key, "")

            # 消息列截断处理
            if key == "message" and isinstance(value, str) and len(value) > 200:
                return value[:200] + "..."

            return str(value) if value else ""

        # 前景色角色：级别列使用深色文字区分
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 2:  # 级别列
                level = record.get("level", "")
                return QBrush(self.LEVEL_COLORS.get(level, QColor(0, 0, 0)))

        # 其余列的背景色由视图和样式决定，此处不覆盖

        return None

    def update_data(self, new_data: List[Dict[str, Any]]) -> None:
        """批量更新数据（高性能实现）。

        Args:
            new_data: 新的日志记录列表
        """
        # 🔧 关键优化：使用beginResetModel/endResetModel一次性通知View
        # 而不是逐行插入/删除，避免频繁重绘
        self.beginResetModel()
        self._data = new_data
        self._selected_rows.clear()  # 数据更新时清除选择
        self.endResetModel()
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def get_record(self, row: int) -> Optional[Dict[str, Any]]:
        """获取指定行的原始记录.

        Args:
            row: 行索引

        Returns:
            日志记录字典，如果索引无效返回None
        """
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def clear(self) -> None:
        """清空数据。"""
        self.beginResetModel()
        self._data.clear()
        self._selected_rows.clear()
        self.endResetModel()
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def select_all(self) -> None:
        """全选所有行。"""
        self._selected_rows = set(range(len(self._data)))
        if self._data:
            # 通知所有行所有列数据变化（复选框 + 背景色）
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._data) - 1, self.columnCount() - 1),
            )
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def clear_selection(self) -> None:
        """清除所有选择。"""
        if self._selected_rows:
            self._selected_rows.clear()
            if self._data:
                # 通知所有行所有列数据变化（复选框 + 背景色）
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(self._data) - 1, self.columnCount() - 1),
                )
        # 刷新表头三态
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def get_selected_records(self) -> List[Dict[str, Any]]:
        """获取选中的记录.

        Returns:
            选中的日志记录列表
        """
        return [self._data[i] for i in sorted(self._selected_rows) if i < len(self._data)]

    def get_selected_count(self) -> int:
        """获取选中数量.

        Returns:
            选中的行数
        """
        return len(self._selected_rows)
