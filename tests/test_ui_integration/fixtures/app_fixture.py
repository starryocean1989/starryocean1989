# -*- coding: utf-8 -*-
"""
应用实例fixture.

提供测试用的应用实例和主窗口。
"""

import logging
import sys
from typing import Generator, cast
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def qapp(qtbot) -> Generator[QApplication, None, None]:
    """提供QApplication实例."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    else:
        app = cast("QApplication", app)

    yield app

    # 清理
    qtbot.wait(100)


@pytest.fixture(scope="function")
def main_window(  # noqa: F811  # pylint: disable=W0621,W0613
    qapp,  # noqa: U100
    qtbot,
    mock_backend_services,  # noqa: U100
):
    """
    提供主窗口实例.

    Args:
        qapp: QApplication实例
        qtbot: pytest-qt的qtbot fixture
        mock_backend_services: mock的后端服务

    Yields:
        MainWindow: 主窗口实例
    """
    logger.info("开始创建主窗口...")
    try:
        # 导入主窗口
        # pylint: disable=import-outside-toplevel
        from ui.main_window import MainWindow

        logger.info("主窗口类导入成功")

        # 创建主窗口
        window = MainWindow()
        logger.info("主窗口实例创建成功")

        # 显示窗口
        window.show()
        qtbot.addWidget(window)
        qtbot.waitExposed(window, timeout=5000)
        logger.info("主窗口显示并添加到qtbot")

        # 等待UI初始化完成
        qtbot.wait(500)

        logger.info("主窗口创建成功")

        yield window

    except Exception as e:
        logger.error(f"创建主窗口时发生错误: {e}", exc_info=True)
        pytest.fail(f"创建主窗口失败: {e}")

    # 清理
    try:
        window.close()
        qtbot.wait(100)
    except Exception as e:  # noqa: BLE001  # pylint: disable=W0718
        logger.warning("关闭主窗口时出错: %s", e)


@pytest.fixture(scope="function")
def mock_backend_services():
    """
    Mock后端服务.

    Returns:
        dict: mock的服务字典
    """
    services = {
        "vnpy_service": MagicMock(),
        "event_service": MagicMock(),
        "data_service": MagicMock(),
        "strategy_service": MagicMock(),
        "trading_service": MagicMock(),
        "portfolio_service": MagicMock(),
    }

    # 配置mock服务的默认行为
    services["vnpy_service"].get_symbols.return_value = [
        {
            "symbol": "000001",
            "exchange": "SSE",
            "name": "平安银行",
            "product": "股票",
        },
        {
            "symbol": "600000",
            "exchange": "SSE",
            "name": "浦发银行",
            "product": "股票",
        },
    ]

    with patch(
        "backend.api.dependencies.get_vnpy_service",
        return_value=services["vnpy_service"],
    ):
        with patch(
            "backend.api.dependencies.get_event_service",
            return_value=services["event_service"],
        ):
            yield services
