# -*- coding: utf-8 -*-
"""
UI测试基类.

提供所有UI测试的通用方法和工具。
"""

import logging
import time
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QWidget,
)

logger = logging.getLogger(__name__)


class BaseUITest:
    """UI测试基类，提供通用测试方法."""

    @classmethod
    def setup_class(cls):
        """初始化测试基类."""
        cls.logger = logging.getLogger(cls.__name__)

    def setup_method(self, method):
        """
        测试前准备.

        Args:
            method: 测试方法
        """
        self.logger.info(f"开始测试: {method.__name__}")
        self.start_time = time.time()

    def teardown_method(self, method):
        """
        测试后清理.

        Args:
            method: 测试方法
        """
        elapsed_time = time.time() - self.start_time
        self.logger.info(f"测试完成: {method.__name__}, 耗时: {elapsed_time:.2f}秒")

    def navigate_to_interface(self, main_window, interface_name: str, qtbot):
        """
        导航到指定界面.

        Args:
            main_window: 主窗口实例
            interface_name: 界面名称
                (system/data/market/strategy/trading/portfolio)
            qtbot: pytest-qt的qtbot
        """
        self.logger.info(f"导航到界面: {interface_name}")

        # 映射界面名称到索引
        interface_map = {
            "system": 0,
            "data": 1,
            "market": 2,
            "strategy": 3,
            "trading": 4,
            "portfolio": 5,
        }

        if interface_name not in interface_map:
            raise ValueError(f"无效的界面名称: {interface_name}")

        # 切换到目标界面
        main_window.switch_to_interface(interface_name)
        qtbot.wait(300)

        # 验证切换成功
        current_widget = main_window.get_current_interface()
        assert current_widget is not None, f"切换到界面 {interface_name} 失败"

        self.logger.info(f"成功导航到界面: {interface_name}")

    def wait_for_ui_update(self, qtbot, timeout: int = 5000):
        """
        等待UI更新完成.

        Args:
            qtbot: pytest-qt的qtbot
            timeout: 超时时间（毫秒）
        """
        # 处理所有待处理的事件
        qtbot.wait(timeout)

    def find_button(self, widget: QWidget, button_text: str) -> Optional[QPushButton]:
        """
        查找按钮.

        Args:
            widget: 父组件
            button_text: 按钮文本

        Returns:
            QPushButton or None
        """
        buttons = widget.findChildren(QPushButton)
        for button in buttons:
            if button.text() == button_text or button_text in button.text():
                return button

        self.logger.warning(f"未找到按钮: {button_text}")
        return None

    def find_line_edit(
        self, widget: QWidget, object_name: Optional[str] = None
    ) -> Optional[QLineEdit]:
        """
        查找输入框.

        Args:
            widget: 父组件
            object_name: 对象名称

        Returns:
            QLineEdit or None
        """
        if object_name:
            line_edit = widget.findChild(QLineEdit, object_name)
            return line_edit if line_edit else None
        else:
            line_edits = list(widget.findChildren(QLineEdit))
            return line_edits[0] if line_edits else None

    def find_combo_box(
        self, widget: QWidget, object_name: Optional[str] = None
    ) -> Optional[QComboBox]:
        """
        查找下拉框.

        Args:
            widget: 父组件
            object_name: 对象名称

        Returns:
            QComboBox or None
        """
        if object_name:
            combo_box = widget.findChild(QComboBox, object_name)
            return combo_box if combo_box else None
        else:
            combo_boxes = list(widget.findChildren(QComboBox))
            return combo_boxes[0] if combo_boxes else None

    def find_tab_widget(self, widget: QWidget) -> Optional[QTabWidget]:
        """
        查找选项卡组件.

        Args:
            widget: 父组件

        Returns:
            QTabWidget or None
        """
        tab_widgets = list(widget.findChildren(QTabWidget))
        return tab_widgets[0] if tab_widgets else None

    def switch_tab(self, tab_widget: QTabWidget, tab_index_or_name, qtbot):
        """
        切换选项卡.

        Args:
            tab_widget: 选项卡组件
            tab_index_or_name: 选项卡索引或名称
            qtbot: pytest-qt的qtbot
        """
        if isinstance(tab_index_or_name, int):
            tab_widget.setCurrentIndex(tab_index_or_name)
        else:
            # 根据名称查找索引
            for i in range(tab_widget.count()):
                if tab_widget.tabText(i) == tab_index_or_name:
                    tab_widget.setCurrentIndex(i)
                    break

        qtbot.wait(200)
        self.logger.info(f"切换到选项卡: {tab_index_or_name}")

    def verify_widget_visible(self, widget: QWidget, should_be_visible: bool = True):
        """
        验证组件可见性.

        Args:
            widget: 组件
            should_be_visible: 是否应该可见
        """
        if widget is None:
            raise AssertionError("组件为None")

        is_visible = widget.isVisible()
        if should_be_visible:
            assert is_visible, "组件应该可见，但实际不可见"
        else:
            assert not is_visible, "组件应该不可见，但实际可见"

        self.logger.info(f"组件可见性验证通过: {should_be_visible}")

    def verify_widget_enabled(self, widget: QWidget, should_be_enabled: bool = True):
        """
        验证组件是否可用.

        Args:
            widget: 组件
            should_be_enabled: 是否应该可用
        """
        if widget is None:
            raise AssertionError("组件为None")

        is_enabled = widget.isEnabled()
        if should_be_enabled:
            assert is_enabled, "组件应该可用，但实际不可用"
        else:
            assert not is_enabled, "组件应该不可用，但实际可用"

        self.logger.info(f"组件可用性验证通过: {should_be_enabled}")

    def verify_text_contains(self, widget: QWidget, expected_text: str):
        """
        验证组件包含指定文本.

        Args:
            widget: 组件
            expected_text: 期望的文本
        """
        if widget is None:
            raise AssertionError("组件为None")

        actual_text = ""
        if hasattr(widget, "text"):
            actual_text = widget.text()  # type: ignore
        elif hasattr(widget, "toPlainText"):
            actual_text = widget.toPlainText()  # type: ignore

        assert (
            expected_text in actual_text
        ), f"文本不匹配，期望包含: '{expected_text}', 实际: '{actual_text}'"

        self.logger.info(f"文本验证通过: '{expected_text}'")

    def verify_feedback(self, main_window, expected_feedback: str):
        """
        验证UI反馈.

        Args:
            main_window: 主窗口实例
            expected_feedback: 期望的反馈信息
        """
        # 检查状态栏消息
        if hasattr(main_window, "status_label"):
            status_text = main_window.status_label.text()
            if expected_feedback in status_text:
                self.logger.info(f"反馈验证通过: '{expected_feedback}'")
                return True

        self.logger.warning(f"未找到期望的反馈: '{expected_feedback}'")
        return False

    def measure_response_time(self, operation_func, max_time: float = 5.0):
        """
        测量操作响应时间.

        Args:
            operation_func: 操作函数
            max_time: 最大允许时间（秒）

        Returns:
            float: 实际响应时间
        """
        start_time = time.time()
        operation_func()
        response_time = time.time() - start_time

        assert (
            response_time <= max_time
        ), f"响应时间超时: {response_time:.2f}秒 > {max_time}秒"

        self.logger.info(f"响应时间: {response_time:.2f}秒")
        return response_time
