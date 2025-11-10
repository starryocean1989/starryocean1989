# -*- coding: utf-8 -*-
"""
原生IOCP异步文件I/O模块

提供真正的异步文件I/O，不使用线程池。
Windows平台：使用IOCP（完成端口）
其他平台：自动降级到aiofiles
"""

import logging
import platform

from backend.infrastructure.native.logging_bridge import native_call_guard

_LOGGER = logging.getLogger("backend.native.iocp")
_ALERT_LOGGER = logging.getLogger("backend.native.iocp.alert")

# 平台检测
IS_WINDOWS = platform.system() == "Windows"

# 尝试导入IOCP实现
if IS_WINDOWS:
    try:
        from .async_iocp_file import AsyncIOCPFile, open_file, aopen
        from .iocp_loop import (
            IOCPCompletionHandler,
            IOCPEventLoopExtension,
            get_loop_extension,
            setup_iocp_loop,
        )
        try:
            from . import iocp_batch  # type: ignore
            batch_file_exists = iocp_batch.batch_file_exists
            batch_file_delete = iocp_batch.batch_file_delete
            batch_file_stat = iocp_batch.batch_file_stat
            fast_dir_walk = iocp_batch.fast_dir_walk
            fast_dir_list = iocp_batch.fast_dir_list
            BATCH_AVAILABLE = True
        except ImportError:
            BATCH_AVAILABLE = False
            def _raise_batch_error_unavailable():
                raise ImportError("Batch file operations not available")
            batch_file_exists = batch_file_delete = batch_file_stat = _raise_batch_error_unavailable
            fast_dir_walk = fast_dir_list = _raise_batch_error_unavailable
        IOCP_AVAILABLE = True
        _LOGGER.debug(
            "native_iocp C 扩展已加载",
            extra={
                "scenario": "backend.native.iocp",
                "native_module": "backend.native.iocp.core",
            },
        )
        __all__ = [
            "AsyncIOCPFile",
            "open_file",
            "aopen",
            "IOCPCompletionHandler",
            "IOCPEventLoopExtension",
            "get_loop_extension",
            "setup_iocp_loop",
        ]
        if BATCH_AVAILABLE:
            __all__.extend([
                "batch_file_exists",
                "batch_file_delete",
                "batch_file_stat",
                "fast_dir_walk",
                "fast_dir_list",
            ])
    except ImportError:
        # C扩展未编译
        IOCP_AVAILABLE = False
        __all__ = []

        def _raise_import_error():
            _ALERT_LOGGER.error(
                "native_iocp C 扩展未编译，已降级至 Python 兼容实现",
                extra={
                    "log_type": "ALERT",
                    "scenario": "backend.native.iocp",
                    "action_required": "compile_extension",
                    "fallback": "python_async_file",
                },
            )
            raise ImportError(
                "IOCP C extension not compiled. "
                "Please run: python setup.py build_ext --inplace in backend/infrastructure/native/native_iocp/"
            )

        AsyncIOCPFile = _raise_import_error
        open_file = _raise_import_error
        aopen = _raise_import_error
        IOCPCompletionHandler = _raise_import_error
        IOCPEventLoopExtension = _raise_import_error
        get_loop_extension = _raise_import_error
        setup_iocp_loop = _raise_import_error
        BATCH_AVAILABLE = False
        def _raise_batch_error_iocp():
            _raise_import_error()
        batch_file_exists = batch_file_delete = batch_file_stat = _raise_batch_error_iocp
        fast_dir_walk = fast_dir_list = _raise_batch_error_iocp
else:
    IOCP_AVAILABLE = False
    __all__ = []

    def _raise_platform_error():
        _ALERT_LOGGER.critical(
            "IOCP异步文件I/O仅支持Windows平台，当前平台不受支持",
            extra={
                "log_type": "ALERT",
                "scenario": "backend.native.iocp",
                "current_platform": platform.system(),
                "action_required": "unsupported_platform",
            },
        )
        raise RuntimeError("IOCP async file I/O only supports Windows platform")

    AsyncIOCPFile = _raise_platform_error
    open_file = _raise_platform_error
    aopen = _raise_platform_error
    IOCPCompletionHandler = _raise_platform_error
    IOCPEventLoopExtension = _raise_platform_error
    get_loop_extension = _raise_platform_error
    setup_iocp_loop = _raise_platform_error
    BATCH_AVAILABLE = False
    def _raise_batch_error_platform():
        _raise_platform_error()
    batch_file_exists = batch_file_delete = batch_file_stat = _raise_batch_error_platform
    fast_dir_walk = fast_dir_list = _raise_batch_error_platform

# 导入兼容层
try:
    from .compat import (
        AsyncFileWrapper,
        aopen as compat_aopen,
        open_async,
        is_iocp_available,
        is_fallback_available,
        get_backend,
        set_iocp_preferred,
    )
    # 添加兼容层导出
    __all__.extend([
        "AsyncFileWrapper",
        "compat_aopen",
        "open_async",
        "is_iocp_available",
        "is_fallback_available",
        "get_backend",
        "set_iocp_preferred",
    ])
except ImportError:
    pass

# 模块信息
__version__ = "1.0.0"
__author__ = "Terminal Project"

