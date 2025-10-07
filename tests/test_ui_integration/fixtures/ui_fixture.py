# -*- coding: utf-8 -*-
"""
UI组件fixture.

提供各个功能界面的组件实例。
"""

import logging
from typing import TYPE_CHECKING, Optional

import pytest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def system_manager_widget(main_window) -> Optional["QWidget"]:
    """获取系统管理界面组件."""
    try:
        widget = main_window.get_interface_by_id("system")
        if widget:
            logger.info("获取系统管理界面成功")
        return widget
    except Exception as e:
        logger.error(f"获取系统管理界面失败: {e}")
        return None


@pytest.fixture(scope="function")
def data_center_widget(main_window) -> Optional["QWidget"]:
    """获取数据中心界面组件."""
    try:
        widget = main_window.get_interface_by_id("data")
        if widget:
            logger.info("获取数据中心界面成功")
        return widget
    except Exception as e:
        logger.error(f"获取数据中心界面失败: {e}")
        return None


@pytest.fixture(scope="function")
def market_board_widget(main_window) -> Optional["QWidget"]:
    """获取行情看板界面组件."""
    try:
        widget = main_window.get_interface_by_id("market")
        if widget:
            logger.info("获取行情看板界面成功")
        return widget
    except Exception as e:
        logger.error(f"获取行情看板界面失败: {e}")
        return None


@pytest.fixture(scope="function")
def strategy_center_widget(main_window) -> Optional["QWidget"]:
    """获取策略中心界面组件."""
    try:
        widget = main_window.get_interface_by_id("strategy")
        if widget:
            logger.info("获取策略中心界面成功")
        return widget
    except Exception as e:
        logger.error(f"获取策略中心界面失败: {e}")
        return None


@pytest.fixture(scope="function")
def trading_gateway_widget(main_window) -> Optional["QWidget"]:
    """获取交易网关界面组件."""
    try:
        widget = main_window.get_interface_by_id("trading")
        if widget:
            logger.info("获取交易网关界面成功")
        return widget
    except Exception as e:
        logger.error(f"获取交易网关界面失败: {e}")
        return None


@pytest.fixture(scope="function")
def portfolio_widget(main_window) -> Optional["QWidget"]:
    """获取组合投资界面组件."""
    try:
        widget = main_window.get_interface_by_id("portfolio")
        if widget:
            logger.info("获取组合投资界面成功")
        return widget
    except Exception as e:
        logger.error(f"获取组合投资界面失败: {e}")
        return None
