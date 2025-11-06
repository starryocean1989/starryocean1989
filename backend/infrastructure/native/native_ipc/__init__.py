# -*- coding: utf-8 -*-
"""
原生IOCP异步IPC模块

提供真正的异步跨进程通信，不使用线程池。
基于 Windows Named Pipe + IOCP 实现。

完全对标 native_iocp 的导出结构和API风格。
"""

import platform
import logging

# 创建logger
logger = logging.getLogger(__name__)

# 平台检测
IS_WINDOWS = platform.system() == "Windows"

# 尝试导入IPC实现
if IS_WINDOWS:
    try:
        from .async_ipc import AsyncIPCPipe, aopen_server, aopen_client
        from .ipc_loop import (
            IPCCompletionHandler,
            IPCEventLoopExtension,
            get_loop_extension,
            setup_ipc_loop,
        )
        IPC_AVAILABLE = True
        __all__ = [
            "AsyncIPCPipe",
            "aopen_server",
            "aopen_client",
            "IPCCompletionHandler",
            "IPCEventLoopExtension",
            "get_loop_extension",
            "setup_ipc_loop",
            "IPC_AVAILABLE",
        ]
    except ImportError as e:
        # C扩展未编译
        IPC_AVAILABLE = False
        __all__ = ["IPC_AVAILABLE"]

        def _raise_import_error():
            logger.warning("IPC C扩展未编译，请运行: python setup.py build_ext --inplace in backend/infrastructure/native/native_ipc/", extra={"log_type": "SYSTEM"})
            raise ImportError(
                "IPC C extension not compiled. "
                "Please run: python setup.py build_ext --inplace in backend/infrastructure/native/native_ipc/"
            )

        AsyncIPCPipe = _raise_import_error
        aopen_server = _raise_import_error
        aopen_client = _raise_import_error
        IPCCompletionHandler = _raise_import_error
        IPCEventLoopExtension = _raise_import_error
        get_loop_extension = _raise_import_error
        setup_ipc_loop = _raise_import_error
else:
    IPC_AVAILABLE = False
    __all__ = ["IPC_AVAILABLE"]

    def _raise_platform_error():
        logger.critical("IPC异步通信仅支持Windows平台", extra={"log_type": "SYSTEM"})
        raise RuntimeError("IPC async only supports Windows platform")

    AsyncIPCPipe = _raise_platform_error
    aopen_server = _raise_platform_error
    aopen_client = _raise_platform_error
    IPCCompletionHandler = _raise_platform_error
    IPCEventLoopExtension = _raise_platform_error
    get_loop_extension = _raise_platform_error
    setup_ipc_loop = _raise_platform_error

# 模块信息
__version__ = "1.0.0"
__author__ = "Terminal Project"
