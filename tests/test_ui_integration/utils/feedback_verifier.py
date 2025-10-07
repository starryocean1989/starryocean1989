# -*- coding: utf-8 -*-
"""
反馈验证器.

验证UI反馈的完整性和正确性。
"""

import logging
from typing import Any, Dict, List

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QWidget,
)

logger = logging.getLogger(__name__)


class FeedbackVerifier:
    """验证UI反馈完整性."""

    def __init__(self):
        """初始化反馈验证器."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._verification_results: List[Dict[str, Any]] = []

    def verify_ui_state(self, widget: QWidget, expected_state: Dict[str, Any]) -> bool:
        """
        验证UI状态.

        Args:
            widget: 组件
            expected_state: 期望的状态字典
                - visible: 可见性
                - enabled: 可用性
                - text: 文本内容
                等

        Returns:
            bool: 是否验证通过
        """
        if widget is None:
            self.logger.error("组件为None，无法验证状态")
            return False

        passed = True

        # 验证可见性
        if "visible" in expected_state:
            expected_visible = expected_state["visible"]
            actual_visible = widget.isVisible()
            if expected_visible != actual_visible:
                self.logger.error(
                    "可见性不匹配: 期望=%s, 实际=%s", expected_visible, actual_visible
                )
                passed = False

        # 验证可用性
        if "enabled" in expected_state:
            expected_enabled = expected_state["enabled"]
            actual_enabled = widget.isEnabled()
            if expected_enabled != actual_enabled:
                self.logger.error(
                    "可用性不匹配: 期望=%s, 实际=%s", expected_enabled, actual_enabled
                )
                passed = False

        # 验证文本
        if "text" in expected_state:
            expected_text = expected_state["text"]
            actual_text = self._get_widget_text(widget)
            if expected_text not in actual_text:
                self.logger.error(
                    "文本不匹配: 期望包含='%s', 实际='%s'", expected_text, actual_text
                )
                passed = False

        if passed:
            self.logger.info("UI状态验证通过")

        self._record_result("verify_ui_state", passed, expected_state)
        return passed

    def verify_data_displayed(self, widget: QWidget, expected_data: Any) -> bool:
        """
        验证数据显示.

        Args:
            widget: 组件
            expected_data: 期望的数据

        Returns:
            bool: 是否验证通过
        """
        if widget is None:
            self.logger.error("组件为None，无法验证数据")
            return False

        passed = False

        # 根据组件类型验证数据
        if isinstance(widget, QTableWidget):
            passed = self._verify_table_data(widget, expected_data)
        elif isinstance(widget, QListWidget):
            passed = self._verify_list_data(widget, expected_data)
        elif isinstance(widget, (QLabel, QLineEdit)):
            actual_text = self._get_widget_text(widget)
            passed = str(expected_data) in actual_text

        if passed:
            self.logger.info("数据显示验证通过")
        else:
            self.logger.error("数据显示验证失败")

        self._record_result("verify_data_displayed", passed, expected_data)
        return passed

    def verify_error_message(self, widget: QWidget, expected_error: str) -> bool:
        """
        验证错误消息.

        Args:
            widget: 组件
            expected_error: 期望的错误消息

        Returns:
            bool: 是否验证通过
        """
        if widget is None:
            self.logger.error("组件为None，无法验证错误消息")
            return False

        actual_text = self._get_widget_text(widget)
        passed = expected_error in actual_text

        if passed:
            self.logger.info("错误消息验证通过: '%s'", expected_error)
        else:
            self.logger.error(
                "错误消息验证失败: 期望='%s', 实际='%s'", expected_error, actual_text
            )

        self._record_result("verify_error_message", passed, expected_error)
        return passed

    def verify_widget_count(
        self, parent: QWidget, widget_type: type, expected_count: int
    ) -> bool:
        """
        验证组件数量.

        Args:
            parent: 父组件
            widget_type: 组件类型
            expected_count: 期望数量

        Returns:
            bool: 是否验证通过
        """
        if parent is None:
            self.logger.error("父组件为None，无法验证组件数量")
            return False

        widgets = list(parent.findChildren(widget_type))
        actual_count = len(widgets)
        passed = actual_count == expected_count

        if passed:
            self.logger.info(
                "组件数量验证通过: %s=%s", widget_type.__name__, expected_count
            )
        else:
            self.logger.error(
                "组件数量验证失败: 期望=%s, 实际=%s", expected_count, actual_count
            )

        self._record_result("verify_widget_count", passed, expected_count)
        return passed

    def verify_progress(
        self, progress_bar: QProgressBar, expected_range: tuple
    ) -> bool:
        """
        验证进度条值.

        Args:
            progress_bar: 进度条组件
            expected_range: 期望范围 (min, max)

        Returns:
            bool: 是否验证通过
        """
        if progress_bar is None:
            self.logger.error("进度条为None，无法验证")
            return False

        actual_value = progress_bar.value()
        min_val, max_val = expected_range
        passed = min_val <= actual_value <= max_val

        if passed:
            self.logger.info(
                "进度验证通过: %s in [%s, %s]", actual_value, min_val, max_val
            )
        else:
            self.logger.error(
                "进度验证失败: %s not in [%s, %s]", actual_value, min_val, max_val
            )

        self._record_result("verify_progress", passed, expected_range)
        return passed

    def verify_button_states(
        self, parent: QWidget, button_states: Dict[str, bool]
    ) -> bool:
        """
        验证多个按钮的状态.

        Args:
            parent: 父组件
            button_states: 按钮文本到可用性的映射

        Returns:
            bool: 是否验证通过
        """
        if parent is None:
            self.logger.error("父组件为None，无法验证按钮状态")
            return False

        passed = True
        buttons = parent.findChildren(QPushButton)

        for button_text, expected_enabled in button_states.items():
            button = next((b for b in buttons if button_text in b.text()), None)
            if button is None:
                self.logger.error("未找到按钮: %s", button_text)
                passed = False
                continue

            actual_enabled = button.isEnabled()
            if actual_enabled != expected_enabled:
                self.logger.error(
                    "按钮状态不匹配: %s, 期望=%s, 实际=%s",
                    button_text,
                    expected_enabled,
                    actual_enabled,
                )
                passed = False

        if passed:
            self.logger.info("按钮状态验证通过")

        self._record_result("verify_button_states", passed, button_states)
        return passed

    def verify_response_time(self, actual_time: float, max_time: float) -> bool:
        """
        验证响应时间.

        Args:
            actual_time: 实际响应时间（秒）
            max_time: 最大允许时间（秒）

        Returns:
            bool: 是否验证通过
        """
        passed = actual_time <= max_time

        if passed:
            self.logger.info("响应时间验证通过: %.2f秒 <= %s秒", actual_time, max_time)
        else:
            self.logger.error("响应时间验证失败: %.2f秒 > %s秒", actual_time, max_time)

        self._record_result("verify_response_time", passed, max_time)
        return passed

    def _get_widget_text(self, widget: QWidget) -> str:
        """获取组件文本."""
        text_method = getattr(widget, "text", None)
        if text_method and callable(text_method):
            return str(text_method())

        plain_text_method = getattr(widget, "toPlainText", None)
        if plain_text_method and callable(plain_text_method):
            return str(plain_text_method())

        html_method = getattr(widget, "toHtml", None)
        if html_method and callable(html_method):
            return str(html_method())

        return ""

    def _verify_table_data(
        self, table: QTableWidget, expected_data: List[Dict]
    ) -> bool:
        """验证表格数据."""
        row_count = table.rowCount()
        if row_count == 0 and len(expected_data) > 0:
            self.logger.error("表格为空，但期望有数据")
            return False

        # 简单验证行数
        if row_count < len(expected_data):
            self.logger.error("表格行数不足: %s < %s", row_count, len(expected_data))
            return False

        return True

    def _verify_list_data(self, list_widget: QListWidget, expected_data: List) -> bool:
        """验证列表数据."""
        item_count = list_widget.count()
        if item_count == 0 and len(expected_data) > 0:
            self.logger.error("列表为空，但期望有数据")
            return False

        return True

    def _record_result(self, verification_type: str, passed: bool, expected: Any):
        """记录验证结果."""
        self._verification_results.append(
            {"type": verification_type, "passed": passed, "expected": expected}
        )

    def get_results(self) -> List[Dict[str, Any]]:
        """获取所有验证结果."""
        return self._verification_results

    def clear_results(self):
        """清除验证结果."""
        self._verification_results.clear()
        self.logger.info("已清除验证结果")

    def print_summary(self):
        """打印验证摘要."""
        total = len(self._verification_results)
        passed = sum(1 for r in self._verification_results if r["passed"])
        failed = total - passed

        self.logger.info("=" * 60)
        self.logger.info("验证结果摘要")
        self.logger.info("=" * 60)
        self.logger.info("  总计: %s", total)
        self.logger.info("  通过: %s (%.1f%%)", passed, passed / total * 100)
        self.logger.info("  失败: %s (%.1f%%)", failed, failed / total * 100)

        if failed > 0:
            self.logger.info("\n失败项:")
            for result in self._verification_results:
                if not result["passed"]:
                    self.logger.info("  - %s: %s", result["type"], result["expected"])

        self.logger.info("=" * 60)
