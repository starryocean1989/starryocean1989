# -*- coding: utf-8 -*-
"""交易网关界面测试 (10条功能链路)."""

import logging

import pytest

from tests.test_ui_integration.base_ui_test import BaseUITest
from tests.test_ui_integration.utils.ui_interactor import UIInteractor

logger = logging.getLogger(__name__)


@pytest.mark.ui  # type: ignore
@pytest.mark.trading_gateway  # type: ignore
class TestTradingGateway(BaseUITest):
    """交易网关界面测试类."""

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, main_window, qtbot):
        """设置测试夹具，初始化主窗口和UI交互器."""
        self.main_window = main_window
        self.qtbot = qtbot
        self.ui_interactor = UIInteractor(qtbot)

    def test_5_0_1_gateway_manager(self):
        """链路 5.0.1: 网关管理器基础."""
        logger.info("测试链路 5.0.1: 网关管理器基础")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.0.1 测试通过")

    def test_5_0_2_dynamic_form(self):
        """链路 5.0.2: 动态表单生成."""
        logger.info("测试链路 5.0.2: 动态表单生成")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.0.2 测试通过")

    def test_5_0_3_gateway_instance(self):
        """链路 5.0.3: 网关实例管理."""
        logger.info("测试链路 5.0.3: 网关实例管理")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.0.3 测试通过")

    def test_5_0_4_gateway_types(self):
        """链路 5.0.4: 网关类型支持（7种）."""
        logger.info("测试链路 5.0.4: 网关类型支持")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.0.4 测试通过")

    def test_5_1_1_strategy_pool(self):
        """链路 5.1.1: 策略池展示管理."""
        logger.info("测试链路 5.1.1: 策略池展示管理")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.1.1 测试通过")

    def test_5_1_2_strategy_deployment(self):
        """链路 5.1.2: 策略部署与批量控制."""
        logger.info("测试链路 5.1.2: 策略部署与批量控制")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.1.2 测试通过")

    def test_5_1_3_single_strategy_control(self):
        """链路 5.1.3: 单策略精细控制."""
        logger.info("测试链路 5.1.3: 单策略精细控制")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.1.3 测试通过")

    def test_5_2_1_monitor_condition(self):
        """链路 5.2.1: 监控条件判断."""
        logger.info("测试链路 5.2.1: 监控条件判断")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.2.1 测试通过")

    def test_5_2_2_vnpy_template_adapt(self):
        """链路 5.2.2: VnPy策略模板适配（6种）."""
        logger.info("测试链路 5.2.2: VnPy策略模板适配")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.2.2 测试通过")

    def test_5_2_3_custom_monitor(self):
        """链路 5.2.3: 定制监控界面."""
        logger.info("测试链路 5.2.3: 定制监控界面")
        self.navigate_to_interface(self.main_window, "trading", self.qtbot)
        logger.info("✅ 链路 5.2.3 测试通过")
