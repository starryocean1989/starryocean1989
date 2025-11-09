# -*- coding: utf-8 -*-
"""native_symbol_index 测试文件."""

import pytest
from typing import Dict, List, Optional

from backend.infrastructure.native.native_symbol_index import (
    LOCKFREE_HASHMAP_AVAILABLE,
    LOCKFREE_INDEX_AVAILABLE,
    SYMBOL_INDEX_AVAILABLE,
    LockFreeSymbolIndex,
    NativeSymbolIndex,
    PythonSymbolIndex,
    create_symbol_index
)


class TestNativeSymbolIndex:
    """native_symbol_index 模块测试."""

    def test_availability_flags(self):
        """测试可用性标志."""
        assert isinstance(LOCKFREE_HASHMAP_AVAILABLE, bool)
        assert isinstance(LOCKFREE_INDEX_AVAILABLE, bool)
        assert isinstance(SYMBOL_INDEX_AVAILABLE, bool)

    def test_python_symbol_index(self):
        """测试 PythonSymbolIndex 实现."""
        index = PythonSymbolIndex()

        assert index.IS_NATIVE is False
        assert index.ENGINE == "python"

        # 测试构建索引
        records = [
            {"code": "000001", "market": "SSE", "name": "平安银行"},
            {"code": "000002", "market": "SSE", "name": "万科A"},
            {"code": "600000", "market": "SH", "name": "浦发银行"},
        ]

        index.build(records)

        # 测试基本查询
        symbol = index.get_symbol("000001")
        assert symbol is not None
        assert symbol["code"] == "000001"
        assert symbol["market"] == "SSE"
        assert symbol["name"] == "平安银行"

        # 测试按市场查询
        sse_codes = index.get_codes_by_market("SSE")
        assert len(sse_codes) == 2
        assert "000001" in sse_codes
        assert "000002" in sse_codes

        sh_codes = index.get_codes_by_market("SH")
        assert len(sh_codes) == 1
        assert "600000" in sh_codes

        # 测试所有代码
        all_codes = index.all_codes()
        assert len(all_codes) == 3
        assert all_codes == sorted(["000001", "000002", "600000"])

        # 测试大小
        assert index.size() == 3

    @pytest.mark.skipif(not LOCKFREE_INDEX_AVAILABLE, reason="LockFree index not available")
    def test_lockfree_symbol_index(self):
        """测试 LockFreeSymbolIndex 实现."""
        index = LockFreeSymbolIndex()

        assert index.IS_NATIVE is True
        assert index.ENGINE == "lockfree"

        # 测试构建索引
        records = [
            {"code": "000001", "market": "SSE", "name": "平安银行"},
            {"code": "000002", "market": "SSE", "name": "万科A"},
        ]

        index.build(records)

        # 测试基本查询
        symbol = index.get_symbol("000001")
        assert symbol is not None
        assert symbol["code"] == "000001"

        # 测试按市场查询
        sse_codes = index.get_codes_by_market("SSE")
        assert len(sse_codes) == 2

    @pytest.mark.skipif(not SYMBOL_INDEX_AVAILABLE, reason="Native symbol index not available")
    def test_native_symbol_index(self):
        """测试 NativeSymbolIndex 实现."""
        if NativeSymbolIndex is not None:
            index = NativeSymbolIndex()

            assert index.IS_NATIVE is True
            assert index.ENGINE == "cpp"
        else:
            pytest.skip("NativeSymbolIndex is not available")

    def test_create_symbol_index_auto(self):
        """测试 create_symbol_index 自动选择."""
        index = create_symbol_index()

        # 应该返回某个实现的实例
        assert index is not None
        assert hasattr(index, 'IS_NATIVE')
        assert hasattr(index, 'ENGINE')
        assert hasattr(index, 'build')
        assert hasattr(index, 'get_symbol')
        assert hasattr(index, 'get_codes_by_market')
        assert hasattr(index, 'all_codes')
        assert hasattr(index, 'size')

    def test_create_symbol_index_python(self):
        """测试强制使用Python实现."""
        index = create_symbol_index(impl="python")

        assert isinstance(index, PythonSymbolIndex)
        assert index.IS_NATIVE is False
        assert index.ENGINE == "python"

    @pytest.mark.skipif(not LOCKFREE_INDEX_AVAILABLE, reason="LockFree index not available")
    def test_create_symbol_index_lockfree(self):
        """测试强制使用LockFree实现."""
        index = create_symbol_index(impl="lockfree")

        assert isinstance(index, LockFreeSymbolIndex)
        assert index.IS_NATIVE is True
        assert index.ENGINE == "lockfree"

    @pytest.mark.skipif(not SYMBOL_INDEX_AVAILABLE, reason="Native symbol index not available")
    def test_create_symbol_index_cpp(self):
        """测试强制使用C++实现."""
        index = create_symbol_index(impl="cpp")

        if NativeSymbolIndex is not None:
            assert isinstance(index, NativeSymbolIndex)
            assert index.IS_NATIVE is True
            assert index.ENGINE == "cpp"

    def test_symbol_index_operations(self):
        """测试符号索引操作."""
        index = create_symbol_index(impl="python")  # 确保Python实现可用

        # 测试空索引
        assert index.size() == 0
        assert index.all_codes() == []
        assert index.get_symbol("nonexistent") is None
        assert index.get_codes_by_market("nonexistent") == []

        # 测试构建和查询
        records = [
            {"code": "1", "market": "TEST", "name": "Test Stock"},
            {"code": "2", "market": "TEST", "name": "Another Stock"},
        ]

        index.build(records)

        assert index.size() == 2

        symbol = index.get_symbol("000001")  # 应该填充到6位
        assert symbol is not None
        assert symbol["code"] == "000001"

        market_codes = index.get_codes_by_market("TEST")
        assert len(market_codes) == 2

    def test_symbol_normalization(self):
        """测试符号标准化."""
        index = PythonSymbolIndex()

        records = [
            {"code": "1", "market": "TEST"},  # 短代码
            {"code": "1234567", "market": "TEST"},  # 长代码
        ]

        index.build(records)

        # 验证代码标准化（填充到6位）
        symbol1 = index.get_symbol("1")
        assert symbol1["code"] == "000001"

        symbol2 = index.get_symbol("1234567")
        assert symbol2["code"] == "1234567"  # 长代码不变

    def test_market_grouping(self):
        """测试市场分组."""
        index = PythonSymbolIndex()

        records = [
            {"code": "000001", "market": "SSE"},
            {"code": "000002", "market": "SSE"},
            {"code": "600000", "market": "SH"},
            {"code": "000003", "market": "SSE"},
        ]

        index.build(records)

        sse_codes = index.get_codes_by_market("SSE")
        sh_codes = index.get_codes_by_market("SH")

        assert len(sse_codes) == 3
        assert len(sh_codes) == 1
        assert "000001" in sse_codes
        assert "600000" in sh_codes
