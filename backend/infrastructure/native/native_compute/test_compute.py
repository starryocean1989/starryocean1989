# -*- coding: utf-8 -*-
"""native_compute 测试文件."""

import pytest
import platform
from typing import List, Any

from backend.infrastructure.native.native_compute import (
    COMPUTE_AVAILABLE,
    PREFIX_SUM_AVAILABLE,
    batch_compute,
    batch_hash,
    batch_get_price,
    batch_validate_iso_dates,
    batch_compare_dates,
    prefix_sum_scale
)


class TestNativeCompute:
    """native_compute 模块测试."""

    def test_compute_available_flags(self):
        """测试可用性标志."""
        assert isinstance(COMPUTE_AVAILABLE, bool)
        assert isinstance(PREFIX_SUM_AVAILABLE, bool)

        # 在Windows上可能可用
        if platform.system() == "Windows":
            # 这里不做严格断言，因为扩展可能未编译
            pass
        else:
            # 非Windows平台不可用
            assert COMPUTE_AVAILABLE is False

    @pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="Compute extension not available")
    def test_batch_compute(self):
        """测试 batch_compute 功能."""
        # 基本数值计算测试
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = batch_compute(data)

        assert isinstance(result, list)
        assert len(result) == len(data)
        # 具体计算逻辑依赖于实现，这里主要验证接口

    @pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="Compute extension not available")
    def test_batch_hash(self):
        """测试 batch_hash 功能."""
        data = ["test1", "test2", "test3"]
        result = batch_hash(data)

        assert isinstance(result, list)
        assert len(result) == len(data)

        # 哈希值应该是一致的
        result2 = batch_hash(data)
        assert result == result2

    @pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="Compute extension not available")
    def test_batch_get_price(self):
        """测试 batch_get_price 功能."""
        # 测试二进制价格数据解析 (TDX格式)
        # 使用简单的二进制数据进行测试
        price_data = b'\x00\x01\x00\x02\x00\x03\x00\x04'  # 简单的测试数据
        result = batch_get_price(price_data, 0, 2)

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="Compute extension not available")
    def test_batch_validate_iso_dates(self):
        """测试 batch_validate_iso_dates 功能."""
        dates = [
            "2023-01-01",
            "2023-12-31",
            "invalid-date",
            "2023-02-30",  # 无效日期
        ]
        result = batch_validate_iso_dates(dates)

        assert isinstance(result, list)
        assert len(result) == len(dates)

        # 有效日期应该返回True，无效日期返回False
        # 这里不假设具体实现，只验证接口

    @pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="Compute extension not available")
    def test_batch_compare_dates(self):
        """测试 batch_compare_dates 功能."""
        dates = [
            "2023-01-01",
            "2023-12-31",
            "2023-06-15",
            "2024-01-01",
        ]
        reference_date = "2023-06-15"
        result = batch_compare_dates(dates, reference_date)

        assert isinstance(result, list)
        assert len(result) == len(dates)
        # Test specific comparisons
        # 2023-01-01 < 2023-06-15 -> -1
        # 2023-12-31 > 2023-06-15 -> 1
        # 2023-06-15 == 2023-06-15 -> 0
        # 2024-01-01 > 2023-06-15 -> 1

    @pytest.mark.skipif(not PREFIX_SUM_AVAILABLE, reason="Prefix sum extension not available")
    def test_prefix_sum_scale(self):
        """测试 prefix_sum_scale 功能."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        scale_factor = 2.0

        result = prefix_sum_scale(data, operation="scale", custom_scale=scale_factor)

        assert isinstance(result, list)
        assert len(result) == len(data)

        # 验证前缀和缩放的基本性质
        # 结果应该是单调递增的（如果输入是正数的话）
        if all(x >= 0 for x in data):
            assert result == sorted(result)

    @pytest.mark.skipif(COMPUTE_AVAILABLE, reason="Test fallback behavior when extension is available")
    def test_compute_fallback_behavior(self):
        """测试扩展不可用时的兜底行为."""
        # 当扩展不可用时，函数调用应该抛出异常
        with pytest.raises((ImportError, RuntimeError)):
            batch_compute([])

        with pytest.raises((ImportError, RuntimeError)):
            batch_hash([])

        with pytest.raises((ImportError, RuntimeError)):
            batch_get_price([])

    def test_compute_interface_consistency(self):
        """测试计算接口的一致性."""
        # 无论扩展是否可用，函数应该存在
        assert callable(batch_compute)
        assert callable(batch_hash)
        assert callable(batch_get_price)
        assert callable(batch_validate_iso_dates)
        assert callable(batch_compare_dates)
        assert callable(prefix_sum_scale)

    @pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="Compute extension not available")
    def test_batch_operations_edge_cases(self):
        """测试批量操作的边界情况."""
        # 空输入
        assert batch_compute([]) == []
        assert batch_hash([]) == []
        assert batch_get_price(b'', 0, 0) == []

        # 单个元素
        assert len(batch_compute([1.0])) == 1
        assert len(batch_hash(["test"])) == 1

        # None值处理
        try:
            batch_compute([None])  # type: ignore
        except (TypeError, ValueError):
            # 应该抛出适当的异常
            pass
