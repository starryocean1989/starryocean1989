# -*- coding: utf-8 -*-
"""
IOCP异步文件I/O - 兼容层

提供平台检测和降级机制：
- Windows平台：优先使用IOCP，失败时降级到aiofiles
- 非Windows平台：直接使用aiofiles
"""

import sys
import platform
from typing import Optional, Union
from pathlib import Path

# 尝试导入IOCP实现
try:
    from . import async_iocp_file
    from .async_iocp_file import AsyncIOCPFile, open_file, aopen as iocp_aopen
    IOCP_IMPORT_SUCCESS = True
except (ImportError, RuntimeError):
    IOCP_IMPORT_SUCCESS = False
    async_iocp_file = None
    AsyncIOCPFile = None
    open_file = None
    iocp_aopen = None

# 尝试导入aiofiles作为降级方案
try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    aiofiles = None
    AIOFILES_AVAILABLE = False

# 平台检测
IS_WINDOWS = platform.system() == "Windows"

# 全局配置：是否优先使用IOCP
_USE_IOCP_PREFERRED = True


def set_iocp_preferred(enabled: bool = True) -> None:
    """
    设置是否优先使用IOCP

    Args:
        enabled: 是否优先使用IOCP（Windows平台）
    """
    global _USE_IOCP_PREFERRED
    _USE_IOCP_PREFERRED = enabled


def is_iocp_available() -> bool:
    """
    检查IOCP是否可用

    Returns:
        是否可用
    """
    return IS_WINDOWS and IOCP_IMPORT_SUCCESS


def is_fallback_available() -> bool:
    """
    检查降级方案（aiofiles）是否可用

    Returns:
        是否可用
    """
    return AIOFILES_AVAILABLE


def _choose_backend() -> str:
    """
    选择后端实现

    Returns:
        'iocp', 'aiofiles', 或 'none'
    """
    # Windows平台优先使用IOCP
    if IS_WINDOWS and _USE_IOCP_PREFERRED and IOCP_IMPORT_SUCCESS:
        return 'iocp'

    # 降级到aiofiles
    if AIOFILES_AVAILABLE:
        return 'aiofiles'

    # 无可用后端
    return 'none'


# 选择的后端
_BACKEND = _choose_backend()


class AsyncFileWrapper:
    """
    异步文件包装类

    根据平台和后端可用性，自动选择最佳实现。
    """

    @staticmethod
    async def open(filepath: Union[str, Path], mode: str = "rb"):
        """
        异步打开文件（自动选择后端）

        Args:
            filepath: 文件路径
            mode: 打开模式

        Returns:
            文件对象
        """
        backend = _choose_backend()

        if backend == 'iocp':
            if iocp_aopen is None:
                raise RuntimeError("IOCP not available")
            return await iocp_aopen(filepath, mode)
        elif backend == 'aiofiles':
            if not AIOFILES_AVAILABLE or aiofiles is None:
                raise RuntimeError("aiofiles not available")
            return await aiofiles.open(filepath, mode)  # type: ignore
        else:
            raise RuntimeError(
                "No async file I/O backend available. "
                "Please install aiofiles or compile IOCP extension."
            )


# 导出API（自动选择后端）
async def aopen(filepath: Union[str, Path], mode: str = "rb"):
    """
    异步打开文件（自动选择最佳后端）

    Windows平台：优先使用IOCP，失败时降级到aiofiles
    其他平台：使用aiofiles

    Args:
        filepath: 文件路径
        mode: 打开模式

    Returns:
        文件对象
    """
    return await AsyncFileWrapper.open(filepath, mode)


# 获取当前使用的后端
def get_backend() -> str:
    """
    获取当前使用的后端

    Returns:
        'iocp', 'aiofiles', 或 'none'
    """
    return _choose_backend()


# 兼容性函数：提供类似aiofiles的接口
async def open_async(filepath: Union[str, Path], mode: str = "rb"):
    """
    异步打开文件（兼容aiofiles接口）

    Args:
        filepath: 文件路径
        mode: 打开模式

    Returns:
        文件对象
    """
    return await aopen(filepath, mode)


__all__ = [
    "AsyncFileWrapper",
    "aopen",
    "open_async",
    "is_iocp_available",
    "is_fallback_available",
    "get_backend",
    "set_iocp_preferred",
]

