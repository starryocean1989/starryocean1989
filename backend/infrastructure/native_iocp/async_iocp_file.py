# -*- coding: utf-8 -*-
"""
原生IOCP异步文件I/O - 高级Python API（改进版）

使用Windows事件对象和asyncio事件循环深度集成，实现真正的异步等待，不使用线程池。
"""

import asyncio
import sys
import platform
from typing import Optional, Union, Tuple, Any
from pathlib import Path

# 仅Windows平台支持
if platform.system() != "Windows":
    raise RuntimeError("IOCP async file I/O only supports Windows platform")

try:
    from . import iocp_file  # type: ignore
    from .iocp_loop import get_loop_extension

    IOCP_AVAILABLE = True
except ImportError:
    # C扩展未编译
    iocp_file = None  # type: ignore
    IOCP_AVAILABLE = False


class AsyncIOCPFile:
    """
    基于IOCP的异步文件对象（改进版）

    使用Windows事件对象和asyncio事件循环深度集成，实现真正的异步I/O。
    不使用线程池，性能优于aiofiles。
    """

    def __init__(self, filepath: Union[str, Path], mode: str = "rb"):
        """
        初始化异步文件对象

        Args:
            filepath: 文件路径
            mode: 打开模式（'rb', 'wb', 'ab'等）
        """
        self.filepath = Path(filepath)
        self.mode = mode
        self._file = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False
        self._extension = None
        self._last_operation_type: Optional[str] = None

        if not IOCP_AVAILABLE:
            raise RuntimeError(
                "IOCP extension not available. "
                "Please compile the C extension or use compat layer."
            )

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False

    async def open(self):
        """异步打开文件"""
        if self._closed:
            raise ValueError("File is closed")

        if not IOCP_AVAILABLE:
            raise RuntimeError("IOCP extension not available")

        if iocp_file is None:
            raise RuntimeError("iocp_file extension not available")

        self._loop = asyncio.get_running_loop()

        # 创建IOCP文件对象
        self._file = iocp_file.IOCPFile()  # type: ignore

        # 打开文件（同步操作，很快）
        self._file.open(str(self.filepath), self.mode)

        # 注册到事件循环扩展
        self._extension = get_loop_extension(self._loop)
        self._extension.register_iocp_file(self._file)

    async def read(self, size: int = -1) -> bytes:
        """
        异步读取文件（真正的异步，不使用线程池）

        Args:
            size: 读取大小，-1表示读取默认大小（4KB）

        Returns:
            读取的数据（bytes）
        """
        if self._file is None:
            raise ValueError("File not opened")
        if self._closed:
            raise ValueError("File is closed")

        if size == -1:
            size = 4096  # 默认4KB

        if self._extension is None:
            raise RuntimeError("Event loop extension not initialized")

        # 启动异步读取
        result = self._file.read_async(size)  # type: ignore

        # 如果立即完成（返回bytes）
        if isinstance(result, bytes):
            return result

        # I/O挂起，等待完成（真正的异步等待，不使用线程池）
        if isinstance(result, tuple) and len(result) == 2:
            pending_flag, event_handle = result

            if pending_flag == 1:  # pending
                self._last_operation_type = "read"

                # 使用事件循环扩展等待完成（不使用线程池）
                result_data = await self._extension.wait_for_completion(
                    self._file, operation_type="read", timeout=None
                )

                # 处理返回结果
                # check_completion返回的格式：
                # - 读取: (complete=1, data=bytes) 或 (complete=0, error_code=0)
                # - 写入: (complete=1, bytes_written=int) 或 (complete=0, error_code=0)
                if isinstance(result_data, tuple):
                    if len(result_data) == 2:
                        is_complete, data = result_data
                        if is_complete:
                            # 完成时返回数据
                            if isinstance(data, bytes):
                                return data
                            elif isinstance(data, int):
                                # 如果是int，说明是错误代码（不应该是complete=1的情况）
                                # 但如果是complete=1且data是int，可能是特殊情况
                                # 重新调用check_completion获取实际数据
                                result = self._file.check_completion()  # type: ignore
                                if isinstance(result, tuple) and len(result) == 2:
                                    _, actual_data = result
                                    if isinstance(actual_data, bytes):
                                        return actual_data
                    elif len(result_data) == 3:
                        # 可能是 (complete, data, error_code) 格式
                        is_complete, data, error_code = result_data
                        if is_complete and isinstance(data, bytes):
                            return data
                elif isinstance(result_data, bytes):
                    return result_data
                else:
                    # 如果结果不是预期的格式，再次检查完成状态
                    result = self._file.check_completion()  # type: ignore
                    if isinstance(result, tuple) and len(result) == 2:
                        is_complete, data = result
                        if is_complete and isinstance(data, bytes):
                            return data

                    raise RuntimeError(
                        f"Unexpected result format: {result_data}, type: {type(result_data)}"
                    )
        else:
            raise RuntimeError(f"Unexpected result type: {type(result)}")

        # 最后的fallback：尝试再次检查完成状态
        if self._file is not None:
            try:
                result = self._file.check_completion()  # type: ignore
                if isinstance(result, tuple) and len(result) == 2:
                    is_complete, data = result
                    if is_complete and isinstance(data, bytes):
                        return data
            except Exception:
                pass

        raise RuntimeError("Failed to read file: unexpected result format")

    async def write(self, data: bytes) -> int:
        """
        异步写入文件（真正的异步，不使用线程池）

        Args:
            data: 要写入的数据

        Returns:
            写入的字节数
        """
        if self._file is None:
            raise ValueError("File not opened")
        if self._closed:
            raise ValueError("File is closed")

        if self._extension is None:
            raise RuntimeError("Event loop extension not initialized")

        # 启动异步写入
        result = self._file.write_async(data)  # type: ignore

        # 如果立即完成（返回int）
        if isinstance(result, int) and result >= 0:
            return result

        # I/O挂起，等待完成（真正的异步等待，不使用线程池）
        if isinstance(result, tuple) and len(result) == 2:
            pending_flag, event_handle = result

            if pending_flag == 1:  # pending
                self._last_operation_type = "write"

                # 使用事件循环扩展等待完成（不使用线程池）
                result_data = await self._extension.wait_for_completion(
                    self._file, operation_type="write", timeout=None
                )

                # 处理返回结果
                if isinstance(result_data, tuple) and len(result_data) == 2:
                    is_complete, data = result_data
                    if is_complete:
                        if isinstance(data, int):
                            return data
                        else:
                            return len(data) if isinstance(data, bytes) else 0
                elif isinstance(result_data, int):
                    return result_data
                else:
                    raise RuntimeError(f"Unexpected result format: {result_data}")
        else:
            raise RuntimeError(f"Unexpected result type: {type(result)}")

        return 0  # fallback

    async def close(self):
        """异步关闭文件"""
        if self._closed:
            return

        if self._file is not None:
            # 取消注册
            if self._extension:
                self._extension.unregister_iocp_file(self._file)

            # 关闭文件
            self._file.close()
            self._file = None

        self._closed = True

    def __repr__(self):
        status = "closed" if self._closed else ("open" if self._file else "not opened")
        return f"<AsyncIOCPFile: {self.filepath} mode={self.mode} status={status}>"


async def open_file(filepath: Union[str, Path], mode: str = "rb") -> AsyncIOCPFile:
    """
    异步打开文件（IOCP）

    Args:
        filepath: 文件路径
        mode: 打开模式

    Returns:
        AsyncIOCPFile对象

    Example:
        async with open_file('data.txt', 'rb') as f:
            data = await f.read()
    """
    file = AsyncIOCPFile(filepath, mode)
    await file.open()
    return file


# 简化API（类似aiofiles）
async def aopen(filepath: Union[str, Path], mode: str = "rb") -> AsyncIOCPFile:
    """
    异步打开文件（IOCP版本）

    Args:
        filepath: 文件路径
        mode: 打开模式

    Returns:
        AsyncIOCPFile对象
    """
    return await open_file(filepath, mode)


__all__ = ["AsyncIOCPFile", "open_file", "aopen"]
