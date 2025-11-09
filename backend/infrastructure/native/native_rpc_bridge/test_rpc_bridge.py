# -*- coding: utf-8 -*-
"""native_rpc_bridge 测试文件."""

import pytest
from typing import Dict, Any

from backend.infrastructure.native.native_rpc_bridge import (
    get_method_id,
    get_method_name,
    create_request_header,
    serialize_request,
    batch_decode_requests,
    batch_encode_responses,
    RPC_BRIDGE_AVAILABLE,
    VERSION,
    RPCMethod,
    METHOD_ID_MAP,
    ID_METHOD_MAP,
    is_available,
    get_error
)


class TestNativeRpcBridge:
    """native_rpc_bridge 模块测试."""

    def test_rpc_bridge_available(self):
        """测试 RPC_BRIDGE_AVAILABLE 状态."""
        assert isinstance(RPC_BRIDGE_AVAILABLE, bool)
        assert isinstance(is_available(), bool)

    def test_version_info(self):
        """测试版本信息."""
        assert isinstance(VERSION, str)
        assert len(VERSION) > 0

    def test_error_info(self):
        """测试错误信息."""
        error = get_error()
        assert error is None or isinstance(error, str)

    def test_rpc_method_enum(self):
        """测试 RPCMethod 枚举."""
        # 验证预定义的方法常量
        assert hasattr(RPCMethod, 'GET_KLINE_DATA')
        assert hasattr(RPCMethod, 'GET_STOCK_LIST')
        assert hasattr(RPCMethod, 'GET_CACHE_STATUS')
        assert hasattr(RPCMethod, 'CALCULATE_INDICATORS')
        assert hasattr(RPCMethod, 'SCAN_DATA_QUALITY')

    def test_method_id_mapping(self):
        """测试方法ID映射."""
        # 测试基本映射
        method_name = "get_kline_data"
        method_id = get_method_id(method_name)
        assert isinstance(method_id, int)

        # 测试反向映射
        recovered_name = get_method_name(method_id)
        assert recovered_name == method_name

        # 测试映射字典
        assert isinstance(METHOD_ID_MAP, dict)
        assert isinstance(ID_METHOD_MAP, dict)

        # 验证映射一致性
        for name, mid in METHOD_ID_MAP.items():
            assert ID_METHOD_MAP.get(mid) == name

    def test_create_request_header(self):
        """测试 create_request_header 功能."""
        method_id = 1
        payload_size = 1024

        header = create_request_header(method_id, payload_size)

        assert isinstance(header, dict)
        assert "method_id" in header
        assert "payload_size" in header
        assert header["method_id"] == method_id
        assert header["payload_size"] == payload_size

    def test_serialize_request(self):
        """测试 serialize_request 功能."""
        method_id = 1
        payload = {"key": "value", "data": [1, 2, 3]}

        result = serialize_request(method_id, payload)

        assert isinstance(result, dict)
        assert "method_id" in result
        assert "payload" in result
        assert result["method_id"] == method_id
        assert result["payload"] == payload

    def test_batch_decode_requests(self):
        """测试 batch_decode_requests 功能."""
        # 模拟缓冲区序列
        buffer_sequence = [
            b"request_data_1",
            b"request_data_2",
            b"request_data_3"
        ]

        results = batch_decode_requests(buffer_sequence)

        assert isinstance(results, list)
        assert len(results) == len(buffer_sequence)

        # 每个结果应该是一个元组
        for result in results:
            assert isinstance(result, tuple)

    def test_batch_encode_responses(self):
        """测试 batch_encode_responses 功能."""
        response_sequence = [
            {"status": "ok", "data": [1, 2, 3]},
            b"raw_response_data",
            "string_response"
        ]

        results = batch_encode_responses(response_sequence)

        assert isinstance(results, list)
        assert len(results) == len(response_sequence)

        # 验证编码结果
        for result in results:
            # 结果应该是bytes或其他原始类型
            assert isinstance(result, (bytes, bytearray, memoryview)) or result is not None

    def test_backward_compatibility_constants(self):
        """测试向后兼容性常量."""
        from backend.infrastructure.native.native_rpc_bridge import (
            METHOD_GET_KLINE_DATA,
            METHOD_GET_STOCK_LIST,
            METHOD_GET_CACHE_STATUS,
            METHOD_CALCULATE_INDICATORS,
            METHOD_SCAN_DATA_QUALITY
        )

        # 验证这些常量存在且是RPCMethod枚举值
        assert METHOD_GET_KLINE_DATA == RPCMethod.GET_KLINE_DATA
        assert METHOD_GET_STOCK_LIST == RPCMethod.GET_STOCK_LIST
        assert METHOD_GET_CACHE_STATUS == RPCMethod.GET_CACHE_STATUS
        assert METHOD_CALCULATE_INDICATORS == RPCMethod.CALCULATE_INDICATORS
        assert METHOD_SCAN_DATA_QUALITY == RPCMethod.SCAN_DATA_QUALITY

    def test_invalid_method_handling(self):
        """测试无效方法的处理."""
        # 测试不存在的方法名
        invalid_id = get_method_id("nonexistent_method")
        assert isinstance(invalid_id, int)  # 应该返回一个默认ID

        # 测试无效的ID
        invalid_name = get_method_name(99999)
        assert invalid_name is None or isinstance(invalid_name, str)
