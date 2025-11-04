# -*- coding: utf-8 -*-
"""
原生IOCP异步文件I/O模块

提供真正的异步文件I/O，不使用线程池。
Windows平台：使用IOCP（完成端口）
其他平台：自动降级到aiofiles
"""

import platform
import logging

# 创建logger
logger = logging.getLogger(__name__)

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
        IOCP_AVAILABLE = True
        __all__ = [
            "AsyncIOCPFile",
            "open_file",
            "aopen",
            "IOCPCompletionHandler",
            "IOCPEventLoopExtension",
            "get_loop_extension",
            "setup_iocp_loop",
        ]
    except ImportError:
        # C扩展未编译
        IOCP_AVAILABLE = False
        __all__ = []

        def _raise_import_error():
            logger.warning("IOCP C扩展未编译，请运行: python setup.py build_ext --inplace in backend/infrastructure/native_iocp/", extra={"log_type": "SYSTEM"})
            raise ImportError(
                "IOCP C extension not compiled. "
                "Please run: python setup.py build_ext --inplace in backend/infrastructure/native_iocp/"
            )

        AsyncIOCPFile = _raise_import_error
        open_file = _raise_import_error
        aopen = _raise_import_error
        IOCPCompletionHandler = _raise_import_error
        IOCPEventLoopExtension = _raise_import_error
        get_loop_extension = _raise_import_error
        setup_iocp_loop = _raise_import_error
else:
    IOCP_AVAILABLE = False
    __all__ = []

    def _raise_platform_error():
        logger.critical("IOCP异步文件I/O仅支持Windows平台", extra={"log_type": "SYSTEM"})
        raise RuntimeError("IOCP async file I/O only supports Windows platform")

    AsyncIOCPFile = _raise_platform_error
    open_file = _raise_platform_error
    aopen = _raise_platform_error
    IOCPCompletionHandler = _raise_platform_error
    IOCPEventLoopExtension = _raise_platform_error
    get_loop_extension = _raise_platform_error
    setup_iocp_loop = _raise_platform_error

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

