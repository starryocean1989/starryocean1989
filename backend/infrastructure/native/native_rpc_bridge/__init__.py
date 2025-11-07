# -*- coding: utf-8 -*-
"""
native_rpc_bridge - 零拷贝RPC桥接

提供高性能RPC通信功能：
1. 方法名到ID的快速映射
2. 消息头创建与管理
3. 请求序列化优化

使用方式：
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

try:
    from .native_rpc_bridge import (
        get_method_id,
        get_method_name,
        create_request_header,
        serialize_request,
        RPC_BRIDGE_AVAILABLE,
        VERSION,
        METHOD_GET_KLINE_DATA,
        METHOD_GET_STOCK_LIST,
        METHOD_GET_CACHE_STATUS,
        METHOD_CALCULATE_INDICATORS,
        METHOD_SCAN_DATA_QUALITY,
    )
    
    _AVAILABLE = True
    _ERROR = None
    
except ImportError as e:
    _AVAILABLE = False
    _ERROR = str(e)
    RPC_BRIDGE_AVAILABLE = False
    
    # 提供降级函数
    def get_method_id(method_name):
        raise ImportError(f"native_rpc_bridge not available: {_ERROR}")
    
    def get_method_name(method_id):
        raise ImportError(f"native_rpc_bridge not available: {_ERROR}")
    
    def create_request_header(method_id, payload_size):
        raise ImportError(f"native_rpc_bridge not available: {_ERROR}")
    
    def serialize_request(method_id, payload):
        raise ImportError(f"native_rpc_bridge not available: {_ERROR}")
    
    VERSION = "0.0.0"
    METHOD_GET_KLINE_DATA = 1
    METHOD_GET_STOCK_LIST = 2
    METHOD_GET_CACHE_STATUS = 3
    METHOD_CALCULATE_INDICATORS = 10
    METHOD_SCAN_DATA_QUALITY = 11


__all__ = [
    'get_method_id',
    'get_method_name',
    'create_request_header',
    'serialize_request',
    'RPC_BRIDGE_AVAILABLE',
    'VERSION',
    'METHOD_GET_KLINE_DATA',
    'METHOD_GET_STOCK_LIST',
    'METHOD_GET_CACHE_STATUS',
    'METHOD_CALCULATE_INDICATORS',
    'METHOD_SCAN_DATA_QUALITY',
]


def is_available():
    """检查native_rpc_bridge是否可用"""
    return _AVAILABLE


def get_error():
    """获取导入错误信息"""
    return _ERROR
