# -*- coding: utf-8 -*-
"""
native_gil - 底层GIL管理工具

提供底层工具，供各模块封装使用。
阶段11埋点：记录关键GIL操作的参数与返回码，便于排查权限/资源问题
"""

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    log_from_native,
    native_call_guard,
)

_COMPONENT_WRAPPER = "backend.native.gil.wrapper"
_COMPONENT_FALLBACK = "backend.native.gil.fallback"

try:
    from .native_gil import (
        release_gil as _release_gil_native,
        restore_gil as _restore_gil_native,
        execute_cpu_task as _execute_cpu_task_native,
        ThreadSafeQueue,
        ThreadSafeCounter,
        LockFreeQueue,
        LockFreeHashMap,
        HighPerfEvent,
        HighPerfCondition,
    )

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def release_gil(*args, **kwargs):
        return _release_gil_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def restore_gil(*args, **kwargs):
        return _restore_gil_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def execute_cpu_task(*args, **kwargs):
        return _execute_cpu_task_native(*args, **kwargs)

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
        # 阶段11埋点：记录native_gil扩展未编译的情况
        log_from_native(
            NativeLogLevel.ERROR,
            _COMPONENT_FALLBACK,
            "import_native_gil",
            0,
            "native_gil C extension is not available; raising ImportError",
        )
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

