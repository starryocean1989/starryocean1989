# -*- coding: utf-8 -*-
"""native_netprobe Python 接口."""

from __future__ import annotations

try:
    from .netprobe import (  # type: ignore[F401]
        NETPROBE_AVAILABLE,
        batch_test_connections,
        test_connection,
    )
except ImportError as exc:  # pragma: no cover - 扩展不可用回退
    NETPROBE_AVAILABLE = False  # type: ignore[assignment]

    def _raise(*_args, **_kwargs):  # type: ignore[override]
        raise ImportError(f"native_netprobe not available: {exc}")

    test_connection = _raise  # type: ignore[assignment]
    batch_test_connections = _raise  # type: ignore[assignment]

__all__ = [
    "NETPROBE_AVAILABLE",
    "test_connection",
    "batch_test_connections",
]

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
    from .netprobe import (
        test_connection,
        batch_test_connections,
        NETPROBE_AVAILABLE,
    )
    
    _AVAILABLE = True
    _ERROR = None
    VERSION = "1.0.0"  # Version defined in Python wrapper
    
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
