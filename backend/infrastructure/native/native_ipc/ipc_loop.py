# -*- coding: utf-8 -*-
"""
IPC异步通信 - asyncio事件循环深度集成

使用Windows事件对象实现真正的Future等待，不依赖线程池。
完全对标 native_iocp/iocp_loop.py 的架构和逻辑。
"""

import asyncio
import sys
import platform
import ctypes
import logging
from ctypes import wintypes, cast, c_void_p
from typing import Optional, Dict, Any

# 创建logger
logger = logging.getLogger(__name__)

# 仅Windows平台支持
if platform.system() != "Windows":
    logger.critical("IPC事件循环仅支持Windows平台", extra={"log_type": "SYSTEM"})
    raise RuntimeError("IPC loop only supports Windows platform")

# Windows API定义
kernel32 = ctypes.windll.kernel32

# WaitForMultipleObjects
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF
INFINITE = 0xFFFFFFFF

try:
    from . import ipc_async  # type: ignore
    IPC_AVAILABLE = True
except ImportError:
    try:
        import ipc_async  # type: ignore
        IPC_AVAILABLE = True
    except ImportError:
        ipc_async = None  # type: ignore
        IPC_AVAILABLE = False


class IPCCompletionHandler:
    """
    IPC完成通知处理器

    使用Windows事件对象和asyncio事件循环的机制。
    完全对标 IOCPCompletionHandler。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        """
        初始化完成处理器

        Args:
            loop: asyncio事件循环
        """
        self.loop = loop
        self.pending_operations: Dict[int, asyncio.Future] = {}
        self.event_handles: Dict[int, int] = {}  # overlapped_ptr -> event_handle
        self._monitoring = False

    def register_operation(self, event_handle: int, future: asyncio.Future, overlapped_ptr: int = 0) -> None:
        """
        注册待处理的I/O操作

        Args:
            event_handle: Windows事件句柄（整数）
            future: asyncio Future对象
            overlapped_ptr: OVERLAPPED结构指针（可选）
        """
        handle_int = int(event_handle)
        self.pending_operations[handle_int] = future
        self.event_handles[handle_int] = handle_int

        if not self._monitoring:
            self._start_monitoring()

    def unregister_operation(self, event_handle: int) -> None:
        """取消注册I/O操作"""
        handle_int = int(event_handle)
        self.pending_operations.pop(handle_int, None)
        self.event_handles.pop(handle_int, None)

    def _start_monitoring(self) -> None:
        """开始监听完成事件"""
        if self._monitoring:
            return

        self._monitoring = True
        self._check_completions()

    def _check_completions(self) -> None:
        """检查完成状态（非阻塞轮询）"""
        if not self._monitoring:
            return

        # 检查所有待处理的操作
        completed = []
        for handle_int, future in list(self.pending_operations.items()):
            # 使用WaitForSingleObject非阻塞检查
            handle_ptr = ctypes.cast(handle_int, ctypes.c_void_p).value
            result = kernel32.WaitForSingleObject(handle_ptr, 0)

            if result == WAIT_OBJECT_0:
                # 事件已触发，操作完成
                completed.append(handle_int)

                # 唤醒Future（在主线程中执行）
                if not future.done():
                    self.loop.call_soon(self._complete_operation, handle_int, future)

        # 移除已完成的操作
        for handle_int in completed:
            self.unregister_operation(handle_int)

        # 继续监听（如果还有待处理的操作）
        if self.pending_operations:
            self.loop.call_later(0.01, self._check_completions)
        else:
            self._monitoring = False

    def _complete_operation(self, handle_int: int, future: asyncio.Future) -> None:
        """完成操作（在主线程中执行）"""
        if future.done():
            return

        try:
            future.set_result(None)
        except Exception:
            pass

    def stop_monitoring(self) -> None:
        """停止监听"""
        self._monitoring = False
        # 取消所有未完成的操作
        for handle_int, future in list(self.pending_operations.items()):
            if not future.done():
                future.cancel()
            self.unregister_operation(handle_int)


class IPCEventLoopExtension:
    """
    asyncio事件循环扩展，深度集成IPC异步通信

    使用Windows事件对象实现真正的异步等待，不依赖线程池。
    完全对标 IOCPEventLoopExtension。
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        初始化扩展

        Args:
            loop: asyncio事件循环，None时使用当前循环
        """
        self.loop = loop or asyncio.get_event_loop()
        self.completion_handler = IPCCompletionHandler(self.loop)
        self._active_ipc_pipes: Dict[int, Any] = {}

    def register_iocp_pipe(self, ipc_pipe_obj: Any) -> None:
        """
        注册IPC管道对象

        Args:
            ipc_pipe_obj: IPCAsyncPipe对象
        """
        if not IPC_AVAILABLE or ipc_async is None:
            logger.warning("ipc_async扩展不可用", extra={"log_type": "SYSTEM"})
            raise RuntimeError("ipc_async extension not available")

        # 获取事件句柄
        event_handle = ipc_pipe_obj.get_event_handle()
        if event_handle is None:
            logger.warning("IPC管道对象没有事件句柄", extra={"log_type": "SYSTEM"})
            return

        handle_value = int(event_handle)
        if handle_value not in self._active_ipc_pipes:
            self._active_ipc_pipes[handle_value] = ipc_pipe_obj

    def unregister_iocp_pipe(self, ipc_pipe_obj: Any) -> None:
        """取消注册IPC管道对象"""
        if not IPC_AVAILABLE or ipc_async is None:
            return

        event_handle = ipc_pipe_obj.get_event_handle()
        if event_handle is None:
            return

        handle_value = int(event_handle)
        self._active_ipc_pipes.pop(handle_value, None)
        self.completion_handler.unregister_operation(handle_value)

    async def wait_for_completion(
        self,
        ipc_pipe_obj: Any,
        operation_type: str = "read",
        timeout: Optional[float] = None
    ) -> Any:
        """
        等待IPC操作完成（真正的异步等待，不使用线程池）

        Args:
            ipc_pipe_obj: IPCAsyncPipe对象
            operation_type: 操作类型（'read'或'write'）
            timeout: 超时时间（秒），None表示无超时

        Returns:
            操作结果（读取返回bytes，写入返回int）
        """
        if not IPC_AVAILABLE or ipc_async is None:
            logger.error("ipc_async扩展不可用", extra={"log_type": "SYSTEM"})
            raise RuntimeError("ipc_async extension not available")

        # 获取事件句柄
        event_handle = ipc_pipe_obj.get_event_handle()
        if event_handle is None:
            logger.error("事件句柄不可用", extra={"log_type": "SYSTEM"})
            raise ValueError("Event handle not available")

        handle_value = int(event_handle)

        # 创建Future
        future = self.loop.create_future()

        # 注册操作
        self.completion_handler.register_operation(handle_value, future)

        try:
            # 等待完成（真正的异步等待）
            if timeout is not None:
                await asyncio.wait_for(self._wait_event(handle_value), timeout=timeout)
            else:
                await self._wait_event(handle_value)

            # 获取结果
            result = ipc_pipe_obj.check_completion()

            if isinstance(result, tuple) and len(result) == 2:
                is_complete, data = result
                if is_complete:
                    return data
                else:
                    # 错误处理
                    if isinstance(data, int) and data != 0:
                        logger.error(f"IPC操作失败，错误代码: {data}, 操作类型: {operation_type}", extra={"log_type": "SYSTEM"})
                        raise OSError(f"I/O operation failed with error code: {data}")
                    return None
            else:
                return result

        except asyncio.TimeoutError:
            self.completion_handler.unregister_operation(handle_value)
            logger.warning(f"IPC操作超时，操作类型: {operation_type}, 超时时间: {timeout}", extra={"log_type": "SYSTEM"})
            raise
        except Exception as e:
            self.completion_handler.unregister_operation(handle_value)
            logger.error(f"等待IPC操作完成时发生异常，操作类型: {operation_type}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise
        finally:
            self.completion_handler.unregister_operation(handle_value)

    async def _wait_event(self, event_handle: int) -> None:
        """
        等待事件对象（真正的异步等待）

        使用asyncio的事件循环机制等待Windows事件对象。
        完全对标 IOCPEventLoopExtension._wait_event。
        """
        # 检查事件循环类型
        if isinstance(self.loop, asyncio.ProactorEventLoop):
            # ProactorEventLoop支持IOCP
            pass

        # 优化轮询方案，缩短轮询间隔
        check_interval = 0.0001  # 100µs，加快完成通知响应

        while True:
            # yield让出控制权
            await asyncio.sleep(0)

            # 非阻塞检查事件是否已触发
            handle_ptr = cast(event_handle, c_void_p).value if isinstance(event_handle, int) else event_handle
            result = kernel32.WaitForSingleObject(handle_ptr, 0)

            if result == WAIT_OBJECT_0:
                # 事件已触发
                return
            elif result == WAIT_TIMEOUT:
                # 事件未触发，等待后再检查
                await asyncio.sleep(check_interval)
            else:
                # 等待失败
                error_code = kernel32.GetLastError()
                logger.error(f"WaitForSingleObject失败，代码: {result}, 错误: {error_code}", extra={"log_type": "SYSTEM"})
                raise OSError(f"WaitForSingleObject failed with code: {result}, error: {error_code}")


# 全局扩展实例
_loop_extension: Optional[IPCEventLoopExtension] = None


def get_loop_extension(loop: Optional[asyncio.AbstractEventLoop] = None) -> IPCEventLoopExtension:
    """
    获取事件循环扩展实例（单例模式）

    Args:
        loop: asyncio事件循环

    Returns:
        IPCEventLoopExtension实例
    """
    global _loop_extension

    current_loop = loop or asyncio.get_event_loop()

    if (
        _loop_extension is None
        or _loop_extension.loop is None
        or _loop_extension.loop is not current_loop
        or _loop_extension.loop.is_closed()
    ):
        if _loop_extension is not None:
            # 旧循环可能已关闭，确保停止监听任务
            _loop_extension.completion_handler.stop_monitoring()
        _loop_extension = IPCEventLoopExtension(current_loop)

    return _loop_extension


def setup_ipc_loop(loop: Optional[asyncio.AbstractEventLoop] = None) -> IPCEventLoopExtension:
    """
    设置IPC事件循环扩展

    Args:
        loop: asyncio事件循环

    Returns:
        IPCEventLoopExtension实例
    """
    return get_loop_extension(loop)


__all__ = [
    "IPCCompletionHandler",
    "IPCEventLoopExtension",
    "get_loop_extension",
    "setup_ipc_loop",
]
