# -*- coding: utf-8 -*-
"""
native_netprobe - 网络探测器

提供高性能网络连通性测试功能：
1. 单个连接测试
2. 批量连接测试
3. 超时控制

使用方式：
```python
from backend.infrastructure.native.native_netprobe import (
    test_connection,
    batch_test_connections,
    NETPROBE_AVAILABLE
)

# 测试单个连接
result = test_connection("127.0.0.1", 8080, timeout=3.0)

# 批量测试
servers = [("192.168.1.1", 80), ("192.168.1.2", 80)]
results = batch_test_connections(servers, timeout=2.0, max_concurrent=10)
```
"""

try:
    from .native_netprobe import (
        test_connection,
        batch_test_connections,
        NETPROBE_AVAILABLE,
        VERSION,
    )
    
    _AVAILABLE = True
    _ERROR = None
    
except ImportError as e:
    _AVAILABLE = False
    _ERROR = str(e)
    NETPROBE_AVAILABLE = False
    
    # 提供降级函数
    def test_connection(host, port, timeout=3.0):
        raise ImportError(f"native_netprobe not available: {_ERROR}")
    
    def batch_test_connections(servers, timeout=3.0, max_concurrent=10):
        raise ImportError(f"native_netprobe not available: {_ERROR}")
    
    VERSION = "0.0.0"


__all__ = [
    'test_connection',
    'batch_test_connections',
    'NETPROBE_AVAILABLE',
    'VERSION',
]


def is_available():
    """检查native_netprobe是否可用"""
    return _AVAILABLE


def get_error():
    """获取导入错误信息"""
    return _ERROR
