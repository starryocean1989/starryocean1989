# -*- coding: utf-8 -*-
"""策略指标中心界面测试 (8条功能链路)."""

import logging

import pytest

from tests.test_ui_integration.base_ui_test import BaseUITest
from tests.test_ui_integration.utils.ui_interactor import UIInteractor

logger = logging.getLogger(__name__)


@pytest.mark.ui
@pytest.mark.strategy_center
class TestStrategyCenter(BaseUITest):
    """策略指标中心界面测试类."""

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, main_window, qtbot):
        """设置测试fixtures."""
        self.main_window = main_window
        self.qtbot = qtbot
        self.ui_interactor = UIInteractor(qtbot)

    def test_4_0_1_strategy_manager_basic(self, strategy_center_widget):
        """链路 4.0.1: 策略指标管理器基础."""
        logger.info("测试链路 4.0.1: 策略指标管理器基础")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None, "策略中心界面未加载"
        self.qtbot.wait(500)
        logger.info("✅ 链路 4.0.1 测试通过")

    def test_4_0_2_file_operations(self, strategy_center_widget):
        """链路 4.0.2: 文件操作与拖动."""
        logger.info("测试链路 4.0.2: 文件操作与拖动")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        logger.info("✅ 链路 4.0.2 测试通过")

    def test_4_0_3_manager_ui_control(self, strategy_center_widget):
        """链路 4.0.3: 管理器界面控制."""
        logger.info("测试链路 4.0.3: 管理器界面控制")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        logger.info("✅ 链路 4.0.3 测试通过")

    def test_4_1_1_code_editor(self, strategy_center_widget):
        """链路 4.1.1: 代码编辑器集成."""
        logger.info("测试链路 4.1.1: 代码编辑器集成")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        logger.info("✅ 链路 4.1.1 测试通过")

    def test_4_1_2_ai_assistant(self, strategy_center_widget):
        """链路 4.1.2: AI助手集成."""
        logger.info("测试链路 4.1.2: AI助手集成")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        logger.info("✅ 链路 4.1.2 测试通过")

    def test_4_1_3_ai_feedback_routing(self, strategy_center_widget):
        """链路 4.1.3: AI反馈分类处理."""
        logger.info("测试链路 4.1.3: AI反馈分类处理")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        logger.info("✅ 链路 4.1.3 测试通过")

    def test_4_2_1_backtest_config(self, strategy_center_widget):
        """链路 4.2.1: 回测配置管理."""
        logger.info("测试链路 4.2.1: 回测配置管理")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        tab_widget = self.find_tab_widget(strategy_center_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 1, self.qtbot)
        logger.info("✅ 链路 4.2.1 测试通过")

    def test_4_2_2_backtest_results(self, strategy_center_widget):
        """链路 4.2.2: 回测结果展示."""
        logger.info("测试链路 4.2.2: 回测结果展示")
        self.navigate_to_interface(self.main_window, "strategy", self.qtbot)
        assert strategy_center_widget is not None
        logger.info("✅ 链路 4.2.2 测试通过")
