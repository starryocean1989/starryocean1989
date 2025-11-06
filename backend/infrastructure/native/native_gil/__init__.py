# -*- coding: utf-8 -*-
"""
native_gil - 底层GIL管理工具

提供底层工具，供各模块封装使用。
"""

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

    __all__ = [
        'release_gil',
        'restore_gil',
        'execute_cpu_task',
        'ThreadSafeQueue',
        'ThreadSafeCounter',
        'LockFreeQueue',
        'LockFreeHashMap',
        'HighPerfEvent',
        'HighPerfCondition',
    ]
except ImportError:
    # C扩展未编译或不可用
    __all__ = []

    def _import_error():
        raise ImportError(
            "native_gil C extension is not available. "
            "Please compile it using: python setup.py build_ext --inplace"
        )

    # 提供占位函数
    def release_gil(*args, **kwargs):
        _import_error()

    def restore_gil(*args, **kwargs):
        _import_error()

    def execute_cpu_task(*args, **kwargs):
        _import_error()

    class ThreadSafeQueue:
        def __init__(self, *args, **kwargs):
            _import_error()

    class ThreadSafeCounter:
        def __init__(self, *args, **kwargs):
            _import_error()

    class LockFreeQueue:
        def __init__(self, *args, **kwargs):
            _import_error()

    class LockFreeHashMap:
        def __init__(self, *args, **kwargs):
            _import_error()

    class HighPerfEvent:
        def __init__(self, *args, **kwargs):
            _import_error()

    class HighPerfCondition:
        def __init__(self, *args, **kwargs):
            _import_error()

