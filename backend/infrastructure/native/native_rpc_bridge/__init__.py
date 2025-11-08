# -*- coding: utf-8 -*-
"""
native_rpc_bridge - 零拷贝RPC桥接

提供高性能RPC通信功能:
1. 方法名到ID的快速映射
2. 消息头创建与管理
3. 请求序列化优化

使用方式:
```python
from backend.infrastructure.native.native_rpc_bridge import (
    get_method_id,
    get_method_name,
    create_request_header,
    RPC_BRIDGE_AVAILABLE
)

# 获取方法ID
method_id = get_method_id("get_kline_data")

# 创建请求头
header = create_request_header(method_id, payload_size=1024)
```
"""

from .rpc_methods import (
    RPCMethod,
    get_method_id,
    get_method_name,
    METHOD_ID_MAP,
    ID_METHOD_MAP
)

try:
    from .native_rpc_bridge import (
        create_request_header,
        serialize_request,
        batch_decode_requests,
        batch_encode_responses,
        RPC_BRIDGE_AVAILABLE,
        VERSION,
    )

    _AVAILABLE = True
    _ERROR = None

except ImportError as e:
    _AVAILABLE = False
    _ERROR = str(e)
    RPC_BRIDGE_AVAILABLE = False

    # 提供降级函数
    def create_request_header(method_id: int, payload_size: int) -> dict:
        return {
            "method_id": method_id,
            "payload_size": payload_size,
            "request_id": 0,
            "flags": 0,
        }

    def serialize_request(method_id: int, payload: object) -> dict:
        return {"method_id": method_id, "payload": payload}

    def batch_decode_requests(buffer_sequence, method_resolver=None):
        results = []
        for raw in buffer_sequence:
            results.append((0, 0, 0, None, raw, None))
        return results

    def batch_encode_responses(response_sequence):
        return [bytes(item) if isinstance(item, (bytearray, memoryview)) else item for item in response_sequence]

    VERSION = "0.0.0 (fallback)"

# 保持向后兼容性
METHOD_GET_KLINE_DATA = RPCMethod.GET_KLINE_DATA
METHOD_GET_STOCK_LIST = RPCMethod.GET_STOCK_LIST
METHOD_GET_CACHE_STATUS = RPCMethod.GET_CACHE_STATUS
METHOD_CALCULATE_INDICATORS = RPCMethod.CALCULATE_INDICATORS
METHOD_SCAN_DATA_QUALITY = RPCMethod.SCAN_DATA_QUALITY

__all__ = [
    "get_method_id",
    "get_method_name",
    "create_request_header",
    "serialize_request",
    "batch_decode_requests",
    "batch_encode_responses",
    "RPC_BRIDGE_AVAILABLE",
    "VERSION",
    "RPCMethod",
    "METHOD_ID_MAP",
    "ID_METHOD_MAP",
    "METHOD_GET_KLINE_DATA",
    "METHOD_GET_STOCK_LIST",
    "METHOD_GET_CACHE_STATUS",
    "METHOD_CALCULATE_INDICATORS",
    "METHOD_SCAN_DATA_QUALITY",
]

def is_available():
    """检查native_rpc_bridge是否可用"""
    return _AVAILABLE

def get_error():
    """获取导入错误信息"""
    return _ERROR
