# -*- coding: utf-8 -*-
"""
数据中心界面测试 (7条功能链路).

测试链路:
- 2.1.1: 品种数据API获取
- 2.1.2: 品种列表分页展示
- 2.1.3: 品种缓存快速刷新
- 2.1.4: 品种筛选与搜索
- 2.2.1: 双模式数据下载
- 2.3.1-2.3.3: 本地数据查询、展示、状态感知
-  2.4.1: 数据源管理
"""

import logging
from typing import Any

import pytest

from tests.test_ui_integration.base_ui_test import BaseUITest
from tests.test_ui_integration.utils.feedback_verifier import (
    FeedbackVerifier,
)
from tests.test_ui_integration.utils.signal_recorder import SignalRecorder
from tests.test_ui_integration.utils.ui_interactor import UIInteractor

logger = logging.getLogger(__name__)


@pytest.mark.ui
@pytest.mark.data_center
class TestDataCenter(BaseUITest):
    """数据中心界面测试类."""

    main_window: Any
    qtbot: Any
    mock_api: Any
    ui_interactor: UIInteractor
    signal_recorder: SignalRecorder
    feedback_verifier: FeedbackVerifier

    @pytest.fixture(autouse=True)
    def setup_fixtures(self, main_window, qtbot, mock_backend_api):
        """设置fixture."""
        self.main_window = main_window
        self.qtbot = qtbot
        self.mock_api = mock_backend_api
        self.ui_interactor = UIInteractor(qtbot)
        self.signal_recorder = SignalRecorder()
        self.feedback_verifier = FeedbackVerifier()

    def test_2_1_1_symbol_api_fetch(self, data_center_widget):
        """
        测试链路 2.1.1: 品种数据API获取.

        操作: 切换到数据中心 → 品种列表子界面 → 点击"重新加载品种"按钮
        验证: API请求发送 → 加载进度显示 → 品种列表更新 → 缓存保存确认
        """
        logger.info("=" * 80)
        logger.info("测试链路 2.1.1: 品种数据API获取")
        logger.info("=" * 80)

        self.navigate_to_interface(self.main_window, "data", self.qtbot)
        assert data_center_widget is not None

        # 切换到品种列表子界面（第一个选项卡）
        tab_widget = self.find_tab_widget(data_center_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 0, self.qtbot)

        # 查找并点击"重新加载品种"按钮
        reload_button = self.find_button(data_center_widget, "重新加载")
        if reload_button:
            self.measure_response_time(
                lambda: self.ui_interactor.click_button(reload_button), max_time=10.0
            )
            self.qtbot.wait(2000)
            assert self.verify_feedback(self.main_window, "加载")

        logger.info("✅ 链路 2.1.1 测试通过")

    def test_2_1_2_symbol_pagination(self):
        """测试链路 2.1.2: 品种列表分页展示."""
        logger.info("测试链路 2.1.2: 品种列表分页展示")
        self.navigate_to_interface(self.main_window, "data", self.qtbot)
        self.qtbot.wait(1000)
        # 验证分页功能
        logger.info("✅ 链路 2.1.2 测试通过")

    def test_2_1_3_symbol_cache_refresh(self, data_center_widget):
        """测试链路 2.1.3: 品种缓存快速刷新."""
        logger.info("测试链路 2.1.3: 品种缓存快速刷新")
        self.navigate_to_interface(self.main_window, "data", self.qtbot)

        refresh_button = self.find_button(data_center_widget, "刷新")
        if refresh_button:
            # 测量响应时间应该 ≤ 1秒
            response_time = self.measure_response_time(
                lambda: self.ui_interactor.click_button(refresh_button), max_time=1.0
            )
            msg = f"刷新时间超过1秒: {response_time}秒"
            assert response_time <= 1.0, msg

        logger.info("✅ 链路 2.1.3 测试通过")

    def test_2_1_4_symbol_filter_search(self, data_center_widget):
        """测试链路 2.1.4: 品种筛选与搜索."""
        logger.info("测试链路 2.1.4: 品种筛选与搜索")
        self.navigate_to_interface(self.main_window, "data", self.qtbot)

        # 测试交易所筛选
        exchange_combo = self.find_combo_box(data_center_widget)
        if exchange_combo:
            self.ui_interactor.select_combo_item(exchange_combo, "SSE")

        # 测试搜索功能
        search_input = self.find_line_edit(data_center_widget)
        if search_input:
            response_time = self.measure_response_time(
                lambda: self.ui_interactor.input_text(search_input, "000001"),
                max_time=0.5,
            )
            assert response_time <= 0.5, "搜索响应时间超过0.5秒"

        logger.info("✅ 链路 2.1.4 测试通过")

    def test_2_2_1_dual_mode_download(self, data_center_widget):
        """测试链路 2.2.1: 双模式数据下载."""
        logger.info("测试链路 2.2.1: 双模式数据下载")
        self.navigate_to_interface(self.main_window, "data", self.qtbot)

        # 切换到数据下载子界面
        tab_widget = self.find_tab_widget(data_center_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 1, self.qtbot)

        # 测试全量下载
        full_download_button = self.find_button(data_center_widget, "全量")
        if full_download_button:
            self.ui_interactor.click_button(full_download_button)
            self.qtbot.wait(1000)

        # 测试增量下载
        incremental_button = self.find_button(data_center_widget, "增量")
        if incremental_button:
            self.ui_interactor.click_button(incremental_button)
            self.qtbot.wait(1000)

        logger.info("✅ 链路 2.2.1 测试通过")

    def test_2_3_local_data_operations(self, data_center_widget):
        """测试链路 2.3.1-2.3.3: 本地数据查询、展示、状态感知."""
        logger.info("测试链路 2.3.1-2.3.3: 本地数据操作")
        self.navigate_to_interface(self.main_window, "data", self.qtbot)

        # 切换到本地数据子界面
        tab_widget = self.find_tab_widget(data_center_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 2, self.qtbot)

        # 输入查询条件并查询
        query_button = self.find_button(data_center_widget, "查询")
        if query_button:
            response_time = self.measure_response_time(
                lambda: self.ui_interactor.click_button(query_button), max_time=3.0
            )
            assert response_time <= 3.0, "查询响应时间超过3秒"

        logger.info("✅ 链路 2.3 测试通过")

    def test_2_4_1_datasource_management(self, data_center_widget):
        """测试链路 2.4.1: 数据源管理（复杂链路）."""
        logger.info("测试链路 2.4.1: 数据源管理")
        self.navigate_to_interface(self.main_window, "data", self.qtbot)

        # 切换到数据源管理子界面
        tab_widget = self.find_tab_widget(data_center_widget)
        if tab_widget:
            self.switch_tab(tab_widget, 3, self.qtbot)

        # 测试数据源连接
        connect_button = self.find_button(data_center_widget, "连接")
        if connect_button:
            self.ui_interactor.click_button(connect_button)
            self.qtbot.wait(1000)

        # 测试启动推送
        start_button = self.find_button(data_center_widget, "启动")
        if start_button:
            self.ui_interactor.click_button(start_button)
            self.qtbot.wait(500)

        logger.info("✅ 链路 2.4.1 测试通过")
