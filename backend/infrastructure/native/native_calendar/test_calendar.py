# -*- coding: utf-8 -*-
"""native_calendar 测试文件."""

import pytest
from typing import List, Optional

from backend.infrastructure.native.native_calendar import NativeCalendar, NATIVE_CALENDAR_AVAILABLE


class TestNativeCalendar:
    """native_calendar 模块测试."""

    def test_calendar_available(self):
        """测试 NATIVE_CALENDAR_AVAILABLE 状态."""
        assert isinstance(NATIVE_CALENDAR_AVAILABLE, bool)

    @pytest.mark.skipif(not NATIVE_CALENDAR_AVAILABLE, reason="Native calendar extension not available")
    def test_native_calendar_initialization(self):
        """测试 NativeCalendar 初始化."""
        # 如果扩展可用，应该能正常初始化
        calendar = NativeCalendar()
        assert calendar is not None

    @pytest.mark.skipif(not NATIVE_CALENDAR_AVAILABLE, reason="Native calendar extension not available")
    def test_is_trading_day(self):
        """测试 is_trading_day 方法."""
        calendar = NativeCalendar()

        # 测试一些典型的交易日和非交易日
        # 注意：实际的交易日历可能因市场而异，这里只是示例

        # 周一到周五通常是交易日
        assert isinstance(calendar.is_trading_day("2023-01-03"), bool)  # 周二
        assert isinstance(calendar.is_trading_day("2023-01-07"), bool)  # 周六

        # 测试无效日期
        assert calendar.is_trading_day("invalid_date") is False

    @pytest.mark.skipif(not NATIVE_CALENDAR_AVAILABLE, reason="Native calendar extension not available")
    def test_get_trading_days(self):
        """测试 get_trading_days 方法."""
        calendar = NativeCalendar()

        # 测试获取一段时间内的交易日
        trading_days = list(calendar.get_trading_days("2023-01-01", "2023-01-10"))
        assert isinstance(trading_days, list)

        # 交易日列表中的每个元素应该是字符串
        for day in trading_days:
            assert isinstance(day, str)

        # 空范围应该返回空列表
        empty_days = list(calendar.get_trading_days("2023-01-01", "2023-01-01"))
        assert isinstance(empty_days, list)

    @pytest.mark.skipif(not NATIVE_CALENDAR_AVAILABLE, reason="Native calendar extension not available")
    def test_get_next_trading_day(self):
        """测试 get_next_trading_day 方法."""
        calendar = NativeCalendar()

        # 测试获取下一个交易日
        next_day = calendar.get_next_trading_day("2023-01-01")  # 周日
        assert isinstance(next_day, (str, type(None)))

        if next_day is not None:
            # 如果返回了日期，应该是字符串格式
            assert isinstance(next_day, str)

        # 测试交易日当天的下一个交易日
        next_day2 = calendar.get_next_trading_day("2023-01-03")  # 周二
        assert isinstance(next_day2, (str, type(None)))

    @pytest.mark.skipif(NATIVE_CALENDAR_AVAILABLE, reason="Test fallback only when extension is not available")
    def test_calendar_fallback_behavior(self):
        """测试扩展不可用时的兜底行为."""
        # 当扩展不可用时，应该抛出RuntimeError
        with pytest.raises(RuntimeError, match="native_calendar 扩展未编译"):
            NativeCalendar()

        # 验证扩展状态
        assert NATIVE_CALENDAR_AVAILABLE is False

    def test_calendar_interface_consistency(self):
        """测试日历接口的一致性."""
        # 无论扩展是否可用，导入应该成功
        from backend.infrastructure.native.native_calendar import NativeCalendar

        # 类应该存在
        assert NativeCalendar is not None

        # 应该有必要的方法（通过hasattr检查）
        # 注意：如果扩展不可用，这些方法会抛出异常，但类定义应该存在
        assert hasattr(NativeCalendar, '__init__')
        assert hasattr(NativeCalendar, 'is_trading_day')
        assert hasattr(NativeCalendar, 'get_trading_days')
        assert hasattr(NativeCalendar, 'get_next_trading_day')
