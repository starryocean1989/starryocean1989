# -*- coding: utf-8 -*-
"""
等待辅助函数.

提供各种等待和超时控制功能。
"""

import logging
import time
from typing import Callable, Any, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


def wait_for_condition(
    condition_func: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.1,
    error_message: str = "等待条件超时",
) -> bool:
    """
    等待条件满足.

    Args:
        condition_func: 条件检查函数，返回True表示条件满足
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）
        error_message: 超时错误消息

    Returns:
        bool: 条件是否满足

    Raises:
        TimeoutError: 超时
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            if condition_func():
                elapsed = time.time() - start_time
                logger.info(f"条件满足，耗时: {elapsed:.2f}秒")
                return True
        except Exception as e:
            logger.warning(f"条件检查出错: {e}")

        time.sleep(interval)

    elapsed = time.time() - start_time
    logger.error(f"{error_message}, 超时: {elapsed:.2f}秒")
    raise TimeoutError(error_message)


def wait_for_widget_visible(
    widget: QWidget, timeout: float = 5.0, interval: float = 0.1
) -> bool:
    """
    等待组件可见.

    Args:
        widget: 组件
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        bool: 组件是否可见
    """

    def check_visible():
        return widget is not None and widget.isVisible()

    try:
        return wait_for_condition(
            check_visible,
            timeout=timeout,
            interval=interval,
            error_message=f"等待组件可见超时",
        )
    except TimeoutError:
        return False


def wait_for_widget_enabled(
    widget: QWidget, timeout: float = 5.0, interval: float = 0.1
) -> bool:
    """
    等待组件可用.

    Args:
        widget: 组件
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        bool: 组件是否可用
    """

    def check_enabled():
        return widget is not None and widget.isEnabled()

    try:
        return wait_for_condition(
            check_enabled,
            timeout=timeout,
            interval=interval,
            error_message=f"等待组件可用超时",
        )
    except TimeoutError:
        return False


def wait_for_text_change(
    widget: QWidget,
    expected_text: str,
    timeout: float = 5.0,
    interval: float = 0.1,
    exact_match: bool = False,
) -> bool:
    """
    等待文本变化.

    Args:
        widget: 组件
        expected_text: 期望的文本
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）
        exact_match: 是否精确匹配

    Returns:
        bool: 文本是否匹配
    """

    def check_text():
        if widget is None:
            return False

        actual_text = ""
        if hasattr(widget, "text"):
            actual_text = widget.text()
        elif hasattr(widget, "toPlainText"):
            actual_text = widget.toPlainText()

        if exact_match:
            return actual_text == expected_text
        else:
            return expected_text in actual_text

    try:
        return wait_for_condition(
            check_text,
            timeout=timeout,
            interval=interval,
            error_message=f"等待文本'{expected_text}'超时",
        )
    except TimeoutError:
        return False


def wait_for_widget_count(
    parent: QWidget,
    widget_type: type,
    expected_count: int,
    timeout: float = 5.0,
    interval: float = 0.1,
) -> bool:
    """
    等待组件数量.

    Args:
        parent: 父组件
        widget_type: 组件类型
        expected_count: 期望数量
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        bool: 数量是否匹配
    """

    def check_count():
        if parent is None:
            return False
        widgets = parent.findChildren(widget_type)
        return len(widgets) == expected_count

    try:
        return wait_for_condition(
            check_count,
            timeout=timeout,
            interval=interval,
            error_message=f"等待组件数量{expected_count}超时",
        )
    except TimeoutError:
        return False


def wait_for_data_loaded(
    widget: QWidget, min_items: int = 1, timeout: float = 10.0, interval: float = 0.2
) -> bool:
    """
    等待数据加载.

    Args:
        widget: 组件（表格、列表等）
        min_items: 最小项目数
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        bool: 数据是否加载
    """

    def check_data():
        if widget is None:
            return False

        # 检查不同类型的组件
        if hasattr(widget, "rowCount"):
            # 表格
            return widget.rowCount() >= min_items
        elif hasattr(widget, "count"):
            # 列表
            return widget.count() >= min_items
        elif hasattr(widget, "topLevelItemCount"):
            # 树形控件
            return widget.topLevelItemCount() >= min_items

        return False

    try:
        return wait_for_condition(
            check_data,
            timeout=timeout,
            interval=interval,
            error_message=f"等待数据加载(最小{min_items}项)超时",
        )
    except TimeoutError:
        return False


def wait_for_feedback(
    status_label: QWidget,
    expected_feedback: str,
    timeout: float = 3.0,
    interval: float = 0.1,
) -> bool:
    """
    等待UI反馈.

    Args:
        status_label: 状态标签
        expected_feedback: 期望的反馈信息
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        bool: 是否收到反馈
    """
    return wait_for_text_change(
        status_label,
        expected_feedback,
        timeout=timeout,
        interval=interval,
        exact_match=False,
    )


def wait_with_progress(
    total_time: float, callback: Optional[Callable[[int], None]] = None, steps: int = 10
):
    """
    带进度的等待.

    Args:
        total_time: 总等待时间（秒）
        callback: 进度回调函数，接收进度百分比（0-100）
        steps: 进度步数
    """
    interval = total_time / steps

    for i in range(steps + 1):
        progress = int((i / steps) * 100)
        if callback:
            callback(progress)

        if i < steps:
            time.sleep(interval)

    logger.info(f"等待完成: {total_time}秒")


class TimeoutContext:
    """超时上下文管理器."""

    def __init__(self, timeout: float, error_message: str = "操作超时"):
        """
        初始化超时上下文.

        Args:
            timeout: 超时时间（秒）
            error_message: 超时错误消息
        """
        self.timeout = timeout
        self.error_message = error_message
        self.start_time = None

    def __enter__(self):
        """进入上下文."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文."""
        elapsed = time.time() - self.start_time
        if elapsed > self.timeout:
            logger.error(f"{self.error_message}: {elapsed:.2f}秒 > {self.timeout}秒")
            raise TimeoutError(f"{self.error_message}: {elapsed:.2f}秒")
        return False

    def check_timeout(self):
        """检查是否超时."""
        if self.start_time is None:
            return False

        elapsed = time.time() - self.start_time
        if elapsed > self.timeout:
            raise TimeoutError(f"{self.error_message}: {elapsed:.2f}秒")
        return False

    def get_elapsed(self) -> float:
        """获取已经过时间."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
