# -*- coding: utf-8 -*-
"""native_smart_monitor 简单导入测试."""

from __future__ import annotations

import importlib

import pytest

try:
    native_smart_monitor_module = importlib.import_module(
        "backend.infrastructure.native.native_smart_monitor"
    )
    SMART_MONITOR_AVAILABLE = getattr(native_smart_monitor_module, "SMART_MONITOR_AVAILABLE", False)
    get_drive_temperature_data = getattr(native_smart_monitor_module, "get_drive_temperature_data", None)
except ImportError:
    SMART_MONITOR_AVAILABLE = False  # type: ignore
    get_drive_temperature_data = None  # type: ignore


@pytest.mark.skipif(
    not SMART_MONITOR_AVAILABLE,
    reason="native_smart_monitor 模块不可用",
)
def test_get_drive_temperature_data_returns_list():
    """验证原生 SMART 获取接口返回列表."""

    if get_drive_temperature_data is None:
        pytest.skip("native_smart_monitor 不可用")

    data = get_drive_temperature_data()
    assert isinstance(data, list)
    for item in data:
        assert isinstance(item, dict)

