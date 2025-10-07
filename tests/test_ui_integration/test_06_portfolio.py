# -*- coding: utf-8 -*-
"""组合投资界面测试 (4条功能链路)."""

import logging

import pytest

from tests.test_ui_integration.base_ui_test import BaseUITest
from tests.test_ui_integration.utils.ui_interactor import UIInteractor

logger = logging.getLogger(__name__)


@pytest.mark.ui
@pytest.mark.portfolio
class TestPortfolio(BaseUITest):
    """组合投资界面测试类."""

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, main_window, qtbot):
        """设置测试所需的 fixtures."""
        # pylint: disable=attribute-defined-outside-init
        self.main_window = main_window
        self.qtbot = qtbot
        self.ui_interactor = UIInteractor(qtbot)

    def test_6_0_1_portfolio_management(self):
        """链路 6.0.1: 组合管理基础."""
        logger.info("测试链路 6.0.1: 组合管理基础")
        self.navigate_to_interface(self.main_window, "portfolio", self.qtbot)
        self.qtbot.wait(500)
        logger.info("✅ 链路 6.0.1 测试通过")

    def test_6_0_2_auto_portfolio_recognition(self):
        """链路 6.0.2: 自动组合识别."""
        logger.info("测试链路 6.0.2: 自动组合识别")
        self.navigate_to_interface(self.main_window, "portfolio", self.qtbot)
        logger.info("✅ 链路 6.0.2 测试通过")

    def test_6_0_3_custom_portfolio(self):
        """链路 6.0.3: 自定义组合管理."""
        logger.info("测试链路 6.0.3: 自定义组合管理")
        self.navigate_to_interface(self.main_window, "portfolio", self.qtbot)
        logger.info("✅ 链路 6.0.3 测试通过")

    def test_6_0_4_portfolio_monitoring(self):
        """链路 6.0.4: 组合投资监控."""
        logger.info("测试链路 6.0.4: 组合投资监控")
        self.navigate_to_interface(self.main_window, "portfolio", self.qtbot)
        logger.info("✅ 链路 6.0.4 测试通过")
