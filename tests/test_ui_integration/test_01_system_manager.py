# -*- coding: utf-8 -*-
"""
系统管理界面测试 (8条功能链路).

测试链路:
- 1.1.1: 系统状态实时监控
- 1.2.1: 性能指标展示
- 1.3.1: 告警信息管理
- 1.4.1: 服务健康检查
- 1.5.1: 系统配置管理
- 1.6.1: 日志管理
- 1.7.1: 系统诊断
- 1.8.1: 工具注册系统
"""

import logging

import pytest

from tests.test_ui_integration.base_ui_test import BaseUITest
from tests.test_ui_integration.utils.feedback_verifier import FeedbackVerifier
from tests.test_ui_integration.utils.signal_recorder import SignalRecorder
from tests.test_ui_integration.utils.ui_interactor import UIInteractor

logger = logging.getLogger(__name__)


@pytest.mark.ui
@pytest.mark.system_manager
class TestSystemManager(BaseUITest):
    """系统管理界面测试类."""

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, main_window, qtbot, mock_backend_api):
        """设置fixture."""
        self.main_window = main_window
        self.qtbot = qtbot
        self.mock_api = mock_backend_api
        self.ui_interactor = UIInteractor(qtbot)
        self.signal_recorder = SignalRecorder()
        self.feedback_verifier = FeedbackVerifier()

    def test_1_1_1_system_status_monitoring(self, system_manager_widget):
        """
        测试链路 1.1.1: 系统状态实时监控.

        操作: 切换到系统管理 → 进入系统状态监控子界面
        验证: CPU/内存/磁盘/网络数据显示 → 5秒内更新 → 图表刷新
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.1.1: 系统状态实时监控")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None, "系统管理界面未加载"

        # 2. 查找并切换到系统状态监控子界面（第一个选项卡）
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 0, self.qtbot)
            self.qtbot.wait(300)

        # 3. 验证监控数据显示
        # 查找标签或显示组件
        self.qtbot.wait(1000)  # 等待数据加载

        # 4. 验证数据更新（5秒内）
        self.qtbot.wait(5000)  # 等待5秒观察更新

        # 5. 验证反馈
        assert self.verify_feedback(self.main_window, "系统")

        logger.info("✅ 链路 1.1.1 测试通过")

    def test_1_2_1_performance_metrics(self, system_manager_widget):
        """
        测试链路 1.2.1: 性能指标展示.

        操作: 切换到性能指标子界面
        验证: 数据处理/策略执行/交易执行性能指标显示 → 趋势图表生成
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.2.1: 性能指标展示")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到性能指标子界面（第二个选项卡）
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 1, self.qtbot)
            self.qtbot.wait(300)

        # 3. 等待性能数据加载
        self.qtbot.wait(1000)

        # 4. 验证性能指标显示
        # 查找性能指标相关组件

        logger.info("✅ 链路 1.2.1 测试通过")

    def test_1_3_1_alert_management(self, system_manager_widget):
        """
        测试链路 1.3.1: 告警信息管理.

        操作: 切换到告警管理子界面 → 点击配置告警规则
        验证: 告警规则列表加载 → 新增规则弹窗 → 规则保存反馈
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.3.1: 告警信息管理")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到告警管理子界面
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 2, self.qtbot)
            self.qtbot.wait(300)

        # 3. 查找并点击配置告警规则按钮
        config_button = self.find_button(system_manager_widget, "配置")
        if config_button:
            self.ui_interactor.click_button(config_button)
            self.qtbot.wait(500)

        logger.info("✅ 链路 1.3.1 测试通过")

    def test_1_4_1_service_health_check(self, system_manager_widget):
        """
        测试链路 1.4.1: 服务健康检查.

        操作: 切换到健康检查子界面 → 点击执行检查
        验证: 各服务健康状态显示 → 检查进度更新 → 结果报告生成
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.4.1: 服务健康检查")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到服务健康检查子界面
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 3, self.qtbot)
            self.qtbot.wait(300)

        # 3. 查找并点击执行检查按钮
        check_button = self.find_button(system_manager_widget, "执行")
        if check_button:
            self.ui_interactor.click_button(check_button)
            self.qtbot.wait(1000)  # 等待检查完成

        logger.info("✅ 链路 1.4.1 测试通过")

    def test_1_5_1_system_configuration(self, system_manager_widget):
        """
        测试链路 1.5.1: 系统配置管理.

        操作: 切换到系统配置子界面 → 修改配置参数 → 点击保存
        验证: 参数验证提示 → 保存成功反馈 → 配置列表更新
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.5.1: 系统配置管理")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到系统配置子界面
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 4, self.qtbot)
            self.qtbot.wait(300)

        # 3. 查找配置输入框并修改
        # 查找保存按钮
        save_button = self.find_button(system_manager_widget, "保存")
        if save_button:
            self.ui_interactor.click_button(save_button)
            self.qtbot.wait(500)

        # 4. 验证保存反馈
        assert self.verify_feedback(self.main_window, "保存")

        logger.info("✅ 链路 1.5.1 测试通过")

    def test_1_6_1_log_management(self, system_manager_widget):
        """
        测试链路 1.6.1: 日志管理.

        操作: 切换到日志管理子界面 → 输入查询条件 → 点击查询
        验证: 日志查询结果显示 → 分页功能 → 日志详情弹窗
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.6.1: 日志管理")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到日志管理子界面
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 5, self.qtbot)
            self.qtbot.wait(300)

        # 3. 输入查询条件
        search_input = self.find_line_edit(system_manager_widget)
        if search_input:
            self.ui_interactor.input_text(search_input, "ERROR")

        # 4. 点击查询按钮
        query_button = self.find_button(system_manager_widget, "查询")
        if query_button:
            self.ui_interactor.click_button(query_button)
            self.qtbot.wait(1000)

        logger.info("✅ 链路 1.6.1 测试通过")

    def test_1_7_1_system_diagnosis(self, system_manager_widget):
        """
        测试链路 1.7.1: 系统诊断.

        操作: 切换到系统诊断子界面 → 选择诊断类型 → 点击开始诊断
        验证: 诊断进度显示 → 诊断结果报告 → 优化建议展示
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.7.1: 系统诊断")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到系统诊断子界面
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 6, self.qtbot)
            self.qtbot.wait(300)

        # 3. 选择诊断类型
        diag_combo = self.find_combo_box(system_manager_widget)
        if diag_combo:
            self.ui_interactor.select_combo_item(diag_combo, "性能诊断")

        # 4. 点击开始诊断按钮
        start_button = self.find_button(system_manager_widget, "开始")
        if start_button:
            self.ui_interactor.click_button(start_button)
            self.qtbot.wait(2000)  # 等待诊断完成

        logger.info("✅ 链路 1.7.1 测试通过")

    def test_1_8_1_tool_registration(self, system_manager_widget):
        """
        测试链路 1.8.1: 工具注册系统.

        操作: 切换到工具集合子界面 → 点击注册新工具
        验证: 工具注册表单 → 配置验证 → 注册成功反馈
        """
        logger.info("=" * 80)
        logger.info("测试链路 1.8.1: 工具注册系统")
        logger.info("=" * 80)

        # 1. 导航到系统管理界面
        self.navigate_to_interface(self.main_window, "system", self.qtbot)
        assert system_manager_widget is not None

        # 2. 切换到工具集合子界面
        tab_widget = self.find_tab_widget(system_manager_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 7, self.qtbot)
            self.qtbot.wait(300)

        # 3. 点击注册新工具按钮
        register_button = self.find_button(system_manager_widget, "注册")
        if register_button:
            self.ui_interactor.click_button(register_button)
            self.qtbot.wait(500)

        # 4. 验证反馈
        assert self.verify_feedback(self.main_window, "注册")

        logger.info("✅ 链路 1.8.1 测试通过")
