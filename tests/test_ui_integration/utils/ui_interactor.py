# -*- coding: utf-8 -*-
"""
UI交互工具类.

封装所有UI操作的工具方法。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QLineEdit,
        QPushButton,
        QRadioButton,
        QTabWidget,
        QTableWidget,
        QWidget,
    )

logger = logging.getLogger(__name__)


class UIInteractor:
    """UI交互工具类，封装所有UI操作."""

    def __init__(self, qtbot):
        """
        初始化UI交互器.

        Args:
            qtbot: pytest-qt的qtbot实例
        """
        self.qtbot = qtbot
        self.logger = logging.getLogger(self.__class__.__name__)

    def click_button(self, button: QPushButton, delay: int = 100):
        """
        点击按钮.

        Args:
            button: 按钮组件
            delay: 点击后延迟（毫秒）
        """
        if button is None:
            raise ValueError("按钮为None，无法点击")

        if not button.isEnabled():
            raise RuntimeError(f"按钮不可用: {button.text()}")

        self.logger.info("点击按钮: %s", button.text())
        self.qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        self.qtbot.wait(delay)

    def input_text(self, line_edit: QLineEdit, text: str, delay: int = 100):
        """
        输入文本.

        Args:
            line_edit: 输入框组件
            text: 要输入的文本
            delay: 输入后延迟（毫秒）
        """
        if line_edit is None:
            raise ValueError("输入框为None，无法输入")

        self.logger.info("输入文本: %s", text)
        line_edit.clear()
        self.qtbot.keyClicks(line_edit, text)
        self.qtbot.wait(delay)

    def select_combo_item(self, combo: QComboBox, item_text: str, delay: int = 100):
        """
        选择下拉框项.

        Args:
            combo: 下拉框组件
            item_text: 要选择的项文本
            delay: 选择后延迟（毫秒）
        """
        if combo is None:
            raise ValueError("下拉框为None，无法选择")

        # 查找项索引
        index = combo.findText(item_text)
        if index >= 0:
            self.logger.info("选择下拉框项: %s", item_text)
            combo.setCurrentIndex(index)
            self.qtbot.wait(delay)
        else:
            raise ValueError(f"下拉框中未找到项: {item_text}")

    def check_checkbox(
        self, checkbox: QCheckBox, checked: bool = True, delay: int = 100
    ):
        """
        勾选/取消勾选复选框.

        Args:
            checkbox: 复选框组件
            checked: 是否勾选
            delay: 操作后延迟（毫秒）
        """
        if checkbox is None:
            raise ValueError("复选框为None，无法操作")

        status = "勾选" if checked else "取消勾选"
        self.logger.info("设置复选框: %s", status)
        checkbox.setChecked(checked)
        self.qtbot.wait(delay)

    def click_radio_button(self, radio: QRadioButton, delay: int = 100):
        """
        点击单选按钮.

        Args:
            radio: 单选按钮组件
            delay: 点击后延迟（毫秒）
        """
        if radio is None:
            raise ValueError("单选按钮为None，无法点击")

        self.logger.info("点击单选按钮: %s", radio.text())
        self.qtbot.mouseClick(radio, Qt.MouseButton.LeftButton)
        self.qtbot.wait(delay)

    def switch_tab(self, tab_widget: QTabWidget, index_or_name, delay: int = 200):
        """
        切换选项卡.

        Args:
            tab_widget: 选项卡组件
            index_or_name: 选项卡索引或名称
            delay: 切换后延迟（毫秒）
        """
        if tab_widget is None:
            raise ValueError("选项卡组件为None，无法切换")

        if isinstance(index_or_name, int):
            self.logger.info("切换到选项卡索引: %s", index_or_name)
            tab_widget.setCurrentIndex(index_or_name)
        else:
            # 根据名称查找索引
            for i in range(tab_widget.count()):
                if tab_widget.tabText(i) == index_or_name:
                    self.logger.info("切换到选项卡: %s", index_or_name)
                    tab_widget.setCurrentIndex(i)
                    break

        self.qtbot.wait(delay)

    def double_click_widget(self, widget: QWidget, delay: int = 100):
        """
        双击组件.

        Args:
            widget: 组件
            delay: 双击后延迟（毫秒）
        """
        if widget is None:
            raise ValueError("组件为None，无法双击")

        self.logger.info("双击组件")
        self.qtbot.mouseDClick(widget, Qt.MouseButton.LeftButton)
        self.qtbot.wait(delay)

    def right_click_widget(self, widget: QWidget, delay: int = 100):
        """
        右键点击组件.

        Args:
            widget: 组件
            delay: 点击后延迟（毫秒）
        """
        if widget is None:
            raise ValueError("组件为None，无法右键点击")

        self.logger.info("右键点击组件")
        self.qtbot.mouseClick(widget, Qt.MouseButton.RightButton)
        self.qtbot.wait(delay)

    def click_table_cell(
        self, table: QTableWidget, row: int, column: int, delay: int = 100
    ):
        """
        点击表格单元格.

        Args:
            table: 表格组件
            row: 行索引
            column: 列索引
            delay: 点击后延迟（毫秒）
        """
        if table is None:
            raise ValueError("表格为None，无法点击")

        self.logger.info("点击表格单元格: (%s, %s)", row, column)
        item = table.item(row, column)
        if item:
            table.setCurrentItem(item)
            self.qtbot.wait(delay)
        else:
            raise ValueError(f"单元格不存在: ({row}, {column})")

    def drag_and_drop(
        self, source_widget: QWidget, target_widget: QWidget, delay: int = 200
    ):
        """
        拖拽操作.

        Args:
            source_widget: 源组件
            target_widget: 目标组件
            delay: 操作后延迟（毫秒）
        """
        if source_widget is None or target_widget is None:
            raise ValueError("拖拽组件为None，无法操作")

        self.logger.info("执行拖拽操作")
        # 获取组件中心位置
        source_pos = source_widget.rect().center()
        target_pos = target_widget.rect().center()

        # 执行拖拽
        self.qtbot.mousePress(source_widget, Qt.MouseButton.LeftButton, pos=source_pos)
        self.qtbot.mouseMove(source_widget, target_pos)
        self.qtbot.mouseRelease(
            target_widget, Qt.MouseButton.LeftButton, pos=target_pos
        )
        self.qtbot.wait(delay)

    def scroll_to_bottom(self, widget: QWidget, delay: int = 100):
        """
        滚动到底部.

        Args:
            widget: 组件
            delay: 滚动后延迟（毫秒）
        """
        if widget is None:
            raise ValueError("组件为None，无法滚动")

        self.logger.info("滚动到底部")
        if hasattr(widget, "verticalScrollBar"):
            # Type ignore: QWidget doesn't have verticalScrollBar
            scrollbar = widget.verticalScrollBar()  # type: ignore
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
                self.qtbot.wait(delay)

    def wait(self, milliseconds: int):
        """
        等待指定时间.

        Args:
            milliseconds: 等待时间（毫秒）
        """
        self.qtbot.wait(milliseconds)
