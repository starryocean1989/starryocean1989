# -*- coding: utf-8 -*-
"""
原生内存操作模块

提供零拷贝内存操作和内存池功能。
Windows平台：使用C扩展实现高性能
其他平台：自动降级到标准库
阶段11埋点：记录关键内存系统调用的参数与返回码，便于排查权限/资源问题
"""

import logging
import platform

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
    get_alert_logger,
)

# 创建logger
logger = bind_logger_defaults(
    logging.getLogger("backend.native.memory"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.memory",
)
alert_logger = get_alert_logger(
    "backend.native.memory.alert",
    scenario="backend.native.memory",
)

# 平台检测
IS_WINDOWS = platform.system() == "Windows"

# 尝试导入C扩展实现
if IS_WINDOWS:
    try:
        from .native_memory import (
            ZeroCopyMemory,
            MemoryPool,
            batch_alloc,
            batch_free,
        )
        MEMORY_AVAILABLE = True
        logger.debug(
            "native_memory C 扩展已加载",
            extra={
                "scenario": "backend.native.memory",
                "native_module": "backend.native.memory.core",
            },
        )
        __all__ = [
            "ZeroCopyMemory",
            "MemoryPool",
            "batch_alloc",
            "batch_free",
            "MEMORY_AVAILABLE",
        ]
    except ImportError:
        # C扩展未编译
        MEMORY_AVAILABLE = False
        __all__ = ["MEMORY_AVAILABLE"]

        def _raise_import_error():
            # 阶段11埋点：记录native_memory扩展未编译的情况
            alert_logger.error(
                "[NATIVE-MEMORY] native_memory扩展未编译，降级使用异常: 场景=内存操作初始化, 返回码=ImportError",
                extra={
                    "log_type": LogType.ALERT.value,
                    "scenario": "backend.native.memory",
                    "action_required": "compile_extension",
                    "fallback": "python_memory_ops",
                }
            )
            raise ImportError(
                "Memory C extension not compiled. "
                "Please run: python setup.py build_ext --inplace in backend/infrastructure/native/native_memory/"
            )

        ZeroCopyMemory = _raise_import_error
        MemoryPool = _raise_import_error
        batch_alloc = _raise_import_error
        batch_free = _raise_import_error
else:
    MEMORY_AVAILABLE = False
    __all__ = ["MEMORY_AVAILABLE"]

    def _raise_platform_error():
        # 阶段11埋点：记录平台不支持的情况
        alert_logger.critical(
            "[NATIVE-MEMORY] native_memory仅支持Windows平台，当前平台=%s: 场景=内存操作初始化, 返回码=RuntimeError",
            platform.system(),
            extra={
                "log_type": LogType.ALERT.value,
                "scenario": "backend.native.memory",
                "action_required": "unsupported_platform",
            }
        )
        raise RuntimeError("Memory operations extension only supports Windows platform")

    ZeroCopyMemory = _raise_platform_error
    MemoryPool = _raise_platform_error
    batch_alloc = _raise_platform_error
    batch_free = _raise_platform_error

# 模块信息
__version__ = "1.0.0"
__author__ = "Terminal Project"

