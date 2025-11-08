# -*- coding: utf-8 -*-
"""
原生IOCP异步IPC模块

提供真正的异步跨进程通信，不使用线程池。
基于 Windows Named Pipe + IOCP 实现。

完全对标 native_iocp 的导出结构和API风格。
"""

import platform
import logging
from typing import Any, Callable, TypeVar, cast

# 使用统一的日志系统
from backend.infrastructure.system_vnpy.logging_system import (
    bind_logger_defaults,
    get_alert_logger,
    LogType,
)

# 创建logger并绑定默认属性
logger = bind_logger_defaults(
    logging.getLogger("backend.native.ipc"),
    log_type=LogType.SYSTEM.value,
    scenario="native.ipc"
)

# 创建告警logger
alert_logger = get_alert_logger("backend.native.ipc.alert", scenario="native.ipc")

T = TypeVar('T', bound=Callable[..., Any])

def log_alert_on_error(func: T) -> T:
    """装饰器：捕获异常并记录告警日志"""
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            alert_logger.error(
                f"Native IPC 模块发生错误: {str(e)}",
                exc_info=True,
                extra={
                    "error_type": type(e).__name__,
                    "module": func.__module__,
                    "function": func.__name__,
                },
            )
            raise
    return cast(T, wrapper)

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

        @log_alert_on_error
        def _raise_import_error():
            alert_msg = (
                "⚠️ IPC C扩展未编译，请运行: python setup.py build_ext --inplace in backend/infrastructure/native/native_ipc/\n"
                "这将导致性能下降，建议尽快编译安装原生扩展以获取最佳性能。"
            )
            alert_logger.critical(
                alert_msg,
                extra={
                    "log_type": LogType.ALERT.value,
                    "action_required": "compile_extension",
                    "module_path": "backend/infrastructure/native/native_ipc",
                },
            )
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

    @log_alert_on_error
    def _raise_platform_error():
        error_msg = "❌ IPC异步通信仅支持Windows平台，当前平台: {}".format(platform.system())
        alert_logger.critical(
            error_msg,
            extra={
                "log_type": LogType.ALERT.value,
                "current_platform": platform.system(),
                "action_required": "unsupported_platform",
            },
        )
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
