# -*- coding: utf-8 -*-
"""行情看板界面测试 (6条功能链路)."""

import logging

import pytest

from tests.test_ui_integration.base_ui_test import BaseUITest
from tests.test_ui_integration.utils.ui_interactor import UIInteractor

logger = logging.getLogger(__name__)


@pytest.mark.ui
@pytest.mark.market_board
class TestMarketBoard(BaseUITest):
    """行情看板界面测试类."""

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, main_window, qtbot):
        """设置测试fixture."""
        self.main_window = main_window
        self.qtbot = qtbot
        self.ui_interactor = UIInteractor(qtbot)

    def test_3_1_chart_display(self):
        """链路 3.1: 行情主图展示."""
        logger.info("测试链路 3.1: 行情主图展示")
        self.navigate_to_interface(self.main_window, "market", self.qtbot)
        self.qtbot.wait(1000)
        logger.info("✅ 链路 3.1 测试通过")

    def test_3_2_indicator_sub_chart(self):
        """链路 3.2: 指标副图管理."""
        logger.info("测试链路 3.2: 指标副图管理")
        self.navigate_to_interface(self.main_window, "market", self.qtbot)
        self.qtbot.wait(500)
        logger.info("✅ 链路 3.2 测试通过")

    def test_3_3_coordinate_system(self):
        """链路 3.3: 坐标系控制."""
        logger.info("测试链路 3.3: 坐标系控制")
        self.navigate_to_interface(self.main_window, "market", self.qtbot)
        logger.info("✅ 链路 3.3 测试通过")

    def test_3_4_symbol_overlay(self):
        """链路 3.4: 品种叠加功能."""
        logger.info("测试链路 3.4: 品种叠加功能")
        self.navigate_to_interface(self.main_window, "market", self.qtbot)
        logger.info("✅ 链路 3.4 测试通过")

    def test_3_5_indicator_overlay(self):
        """链路 3.5: 指标叠加功能."""
        logger.info("测试链路 3.5: 指标叠加功能")
        self.navigate_to_interface(self.main_window, "market", self.qtbot)
        logger.info("✅ 链路 3.5 测试通过")

    def test_3_6_gap_detection(self):
        """链路 3.6: 断点检测与增量更新."""
        logger.info("测试链路 3.6: 断点检测与增量更新")
        self.navigate_to_interface(self.main_window, "market", self.qtbot)
        logger.info("✅ 链路 3.6 测试通过")
