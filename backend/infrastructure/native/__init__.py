# -*- coding: utf-8 -*-
"""
Native扩展模块统一导入

包含所有原生扩展模块：
- native_gil: GIL管理和CPU密集型任务执行器
- native_iocp: 异步文件I/O（Windows IOCP）
- native_ipc: 异步进程间通信（Windows Named Pipe + IOCP）
- native_memory: 内存操作（零拷贝、内存池）
- native_serialization: 序列化（批量、零拷贝）
- native_conversion: 数据转换（批量类型转换、批量字符串操作）
- native_collections: 高性能容器（LRU缓存、优先级队列）
- native_compute: 数值计算（批量数值运算、批量哈希计算）
- native_calendar: 高性能交易日历查询
"""

import importlib
from typing import TYPE_CHECKING

__all__ = []

# Native模块的类型将在使用时通过直接导入获得

# 并发/同步 - native_gil
try:
    from .native_gil import (
        release_gil,
        restore_gil,
        execute_cpu_task,
        ThreadSafeQueue,
        ThreadSafeCounter,
        LockFreeQueue,
        LockFreeHashMap,
        HighPerfEvent,
        HighPerfCondition,
    )
    __all__.extend([
        'release_gil',
        'restore_gil',
        'execute_cpu_task',
        'ThreadSafeQueue',
        'ThreadSafeCounter',
        'LockFreeQueue',
        'LockFreeHashMap',
        'HighPerfEvent',
        'HighPerfCondition',
    ])
except ImportError:
    pass

# 所有native模块的导入将在需要时通过各自的子模块进行
# 这里只提供统一的访问接口

# 进程指标 - native_process_metrics
try:
    from .native_process_metrics import (
        PROCESS_METRICS_AVAILABLE,
        get_system_metrics,
        get_process_snapshot,
        enumerate_processes,
        get_last_error,
        NativeProcessMetricsError,
    )
    __all__.extend([
        'PROCESS_METRICS_AVAILABLE',
        'get_system_metrics',
        'get_process_snapshot',
        'enumerate_processes',
        'get_last_error',
        'NativeProcessMetricsError',
    ])
except ImportError:
    pass

# Socket指标 - native_socket_metrics
try:
    from .native_socket_metrics import (
        SOCKET_METRICS_AVAILABLE,
        get_socket_metrics,
    )
    __all__.extend([
        'SOCKET_METRICS_AVAILABLE',
        'get_socket_metrics',
    ])
except ImportError:
    pass


def get_native_module_info() -> dict:
    """获取所有可用的native模块信息"""
    info = {}

    modules = [
        'native_gil', 'native_iocp', 'native_ipc', 'native_memory',
        'native_serialization', 'native_conversion', 'native_collections',
        'native_compute', 'native_calendar', 'native_fs',
        'native_process_metrics', 'native_socket_metrics'
    ]

    for module_name in modules:
        try:
            module = importlib.import_module(f'.{module_name}', package=__name__)
            info[module_name] = {
                'available': True,
                'version': getattr(module, '__version__', 'unknown'),
                'functions': [name for name in dir(module) if not name.startswith('_')],
            }
        except ImportError:
            info[module_name] = {
                'available': False,
                'error': 'Module not found or failed to load',
            }

    return info


def list_available_features() -> list:
    """列出所有可用的native功能"""
    features = []

    if 'release_gil' in globals():
        features.append('GIL管理')
    if 'AsyncFileReader' in globals():
        features.append('异步文件I/O')
    if 'NamedPipeServer' in globals():
        features.append('命名管道IPC')
    if 'MemoryPool' in globals():
        features.append('内存池')
    if 'BatchSerializer' in globals():
        features.append('批量序列化')
    if 'BatchConverter' in globals():
        features.append('批量数据转换')
    if 'LRUCache' in globals():
        features.append('LRU缓存')
    if 'BatchCalculator' in globals():
        features.append('批量数值计算')
    if 'TradingCalendar' in globals():
        features.append('交易日历')
    if 'DirectoryWatcher' in globals():
        features.append('目录监控')

    return features


# 模块级别的便利函数
def is_native_available() -> bool:
    """检查是否有任何native模块可用"""
    return len(__all__) > 0


def get_performance_boost() -> dict:
    """获取性能提升信息"""
    boosts = {}

    if 'ThreadSafeQueue' in globals():
        boosts['concurrency'] = '线程安全队列，支持高并发场景'
    if 'AsyncFileReader' in globals():
        boosts['io'] = '异步文件I/O，使用Windows IOCP提升性能'
    if 'NamedPipeServer' in globals():
        boosts['ipc'] = '命名管道通信，支持进程间高效数据传输'
    if 'MemoryPool' in globals():
        boosts['memory'] = '内存池管理，减少内存分配开销'
    if 'BatchSerializer' in globals():
        boosts['serialization'] = '批量序列化，提升数据处理效率'
    if 'LRUCache' in globals():
        boosts['cache'] = 'LRU缓存，优化内存使用和访问速度'
    if 'BatchCalculator' in globals():
        boosts['compute'] = '批量数值计算，加速数据处理任务'
    if 'TradingCalendar' in globals():
        boosts['calendar'] = '高性能交易日历查询'
    if 'DirectoryWatcher' in globals():
        boosts['fs'] = '文件系统监控，支持实时文件变更通知'

    return boosts
