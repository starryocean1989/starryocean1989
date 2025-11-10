# -*- coding: utf-8 -*-
"""
原生IOCP异步IPC - 高级Python API

基于Windows Named Pipe + IOCP实现真正的异步跨进程通信，不使用线程池。
完全对标 native_iocp/async_iocp_file.py 的架构和API风格。
"""

import asyncio
import sys
import platform
import logging
from typing import Optional, Type

# 导入native_call_guard装饰器
from backend.infrastructure.native.logging_bridge import native_call_guard, native_async_call_guard

# 创建logger
logger = logging.getLogger(__name__)

# 仅Windows平台支持
if platform.system() != "Windows":
    logger.critical("IPC异步通信仅支持Windows平台", extra={"log_type": "SYSTEM"})
    raise RuntimeError("IPC async only supports Windows platform")

try:
    from . import ipc_async  # type: ignore
    from .ipc_loop import get_loop_extension

    IPC_AVAILABLE = True
except ImportError:
    try:
        import ipc_async  # type: ignore
        from ipc_loop import get_loop_extension  # type: ignore
        IPC_AVAILABLE = True
    except ImportError:
        # C扩展未编译
        ipc_async = None  # type: ignore
        IPC_AVAILABLE = False


class _IPCPipeFactory:
    """支持await和async with的IPC管道工厂"""

    def __init__(
        self,
        pipe_cls: Type["AsyncIPCPipe"],
        pipe_name: str,
        role: str,
        wait_for_client: bool = True,
        connect_timeout: Optional[float] = None,
    ) -> None:
        self._pipe_cls = pipe_cls
        self._pipe_name = pipe_name
        self._role = role
        self._wait_for_client = wait_for_client
        self._connect_timeout = connect_timeout
        self._instance: Optional["AsyncIPCPipe"] = None

    async def _create(self) -> "AsyncIPCPipe":
        instance = self._pipe_cls(self._pipe_name, role=self._role)
        if self._role == "server":
            await instance._create_server(
                wait_for_client=self._wait_for_client,
                timeout=self._connect_timeout,
            )
        else:
            await instance._create_client()
        return instance

    def __await__(self):  # type: ignore[override]
        return self._create().__await__()

    async def __aenter__(self) -> "AsyncIPCPipe":
        self._instance = await self._create()
        return self._instance

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._instance is not None:
            await self._instance.close()
            self._instance = None


class AsyncIPCPipe:
    """
    基于IOCP的异步IPC管道对象

    使用Windows Named Pipe + IOCP实现真正的异步跨进程通信。
    不使用线程池，性能优于传统的线程池方案。

    完全对标 AsyncIOCPFile 的API风格。
    """

    def __init__(self, pipe_name: str, role: str = "server"):
        """
        初始化异步IPC管道对象

        Args:
            pipe_name: 管道名称
            role: 角色（'server' 或 'client'）
        """
        self.pipe_name = pipe_name
        self.role = role
        self._pipe = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False
        self._extension = None
        self._last_operation_type: Optional[str] = None

        if not IPC_AVAILABLE:
            logger.warning("IPC扩展不可用，请编译C扩展", extra={"log_type": "SYSTEM"})
            raise RuntimeError(
                "IPC extension not available. "
                "Please compile the C extension."
            )

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False

    @classmethod
    def server(
        cls,
        pipe_name: str,
        *,
        wait_for_client: bool = True,
        connect_timeout: Optional[float] = None,
    ) -> _IPCPipeFactory:
        """
        创建服务端管道（工厂方法）

        Args:
            pipe_name: 管道名称
            wait_for_client: 是否在返回前等待客户端连接完成
            connect_timeout: 等待客户端连接的超时时间（秒），None为无限等待

        Returns:
            AsyncIPCPipe实例

        Example:
            async with AsyncIPCPipe.server("monitor_service") as pipe:
                data = await pipe.read()
        """
        return _IPCPipeFactory(
            cls,
            pipe_name,
            role="server",
            wait_for_client=wait_for_client,
            connect_timeout=connect_timeout,
        )

    @classmethod
    def client(cls, pipe_name: str) -> _IPCPipeFactory:
        """
        连接到服务端管道（工厂方法）

        Args:
            pipe_name: 管道名称

        Returns:
            AsyncIPCPipe实例

        Example:
            async with AsyncIPCPipe.client("monitor_service") as pipe:
                await pipe.write(b"request")
        """
        return _IPCPipeFactory(cls, pipe_name, role="client")

    async def _create_server(
        self,
        *,
        wait_for_client: bool = True,
        timeout: Optional[float] = None,
    ):
        """创建服务端管道（内部方法）"""
        if self._closed:
            logger.error("管道已关闭，无法创建服务端", extra={"log_type": "SYSTEM"})
            raise ValueError("Pipe is closed")

        if not IPC_AVAILABLE:
            logger.warning("IPC扩展不可用", extra={"log_type": "SYSTEM"})
            raise RuntimeError("IPC extension not available")

        if ipc_async is None:
            logger.warning("ipc_async扩展不可用", extra={"log_type": "SYSTEM"})
            raise RuntimeError("ipc_async extension not available")

        self._loop = asyncio.get_running_loop()

        # 创建IPC管道对象
        try:
            self._pipe = ipc_async.IPCAsyncPipe()  # type: ignore
        except Exception as e:
            logger.error(f"创建IPC管道对象失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise

        # 创建服务端管道
        try:
            self._pipe.create_server_pipe(self.pipe_name)
        except Exception as e:
            logger.error(f"创建服务端管道失败: {self.pipe_name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise

        # 注册到事件循环扩展
        try:
            self._extension = get_loop_extension(self._loop)
            self._extension.register_iocp_pipe(self._pipe)
        except Exception as e:
            logger.error(f"注册IPC管道到事件循环扩展失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise

        # 等待客户端连接完成，避免在连接建立前执行读操作
        if wait_for_client:
            try:
                logger.info(f"IPC服务端 {self.pipe_name} 等待客户端连接...", extra={"log_type": "SYSTEM"})
                await self._wait_for_client_connection(timeout=timeout)
                logger.info(f"IPC服务端 {self.pipe_name} 客户端连接成功", extra={"log_type": "SYSTEM"})
            except Exception as exc:
                logger.error(
                    f"等待IPC客户端连接失败: {exc}",
                    exc_info=True,
                    extra={"log_type": "SYSTEM"},
                )
                await self.close()
                raise

    async def _create_client(self):
        """连接到服务端管道（内部方法）"""
        if self._closed:
            logger.error("管道已关闭，无法连接", extra={"log_type": "SYSTEM"})
            raise ValueError("Pipe is closed")

        if not IPC_AVAILABLE:
            logger.warning("IPC扩展不可用", extra={"log_type": "SYSTEM"})
            raise RuntimeError("IPC extension not available")

        if ipc_async is None:
            logger.warning("ipc_async扩展不可用", extra={"log_type": "SYSTEM"})
            raise RuntimeError("ipc_async extension not available")

        self._loop = asyncio.get_running_loop()

        # 创建IPC管道对象
        try:
            self._pipe = ipc_async.IPCAsyncPipe()  # type: ignore
        except Exception as e:
            logger.error(f"创建IPC管道对象失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise

        # 连接到服务端管道
        try:
            logger.info(f"IPC客户端尝试连接服务端: {self.pipe_name}", extra={"log_type": "SYSTEM"})
            self._pipe.create_client_pipe(self.pipe_name)
            logger.info(f"IPC客户端连接服务端成功: {self.pipe_name}", extra={"log_type": "SYSTEM"})
        except Exception as e:
            logger.error(f"连接服务端管道失败: {self.pipe_name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise

        # 注册到事件循环扩展
        try:
            self._extension = get_loop_extension(self._loop)
            self._extension.register_iocp_pipe(self._pipe)
        except Exception as e:
            logger.error(f"注册IPC管道到事件循环扩展失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            raise

    @native_async_call_guard(component="backend.native.ipc")
    async def read(self, size: int = 4096) -> bytes:
        """
        异步读取数据（真正的异步，不使用线程池）

        Args:
            size: 读取字节数，默认4096

        Returns:
            读取的数据（bytes）
        """
        if self._pipe is None:
            logger.error("管道未打开，无法读取", extra={"log_type": "SYSTEM"})
            raise ValueError("Pipe not opened")
        if self._closed:
            logger.error("管道已关闭，无法读取", extra={"log_type": "SYSTEM"})
            raise ValueError("Pipe is closed")

        if self._extension is None:
            logger.error("事件循环扩展未初始化", extra={"log_type": "SYSTEM"})
            raise RuntimeError("Event loop extension not initialized")

        # 启动异步读取
        result = self._pipe.read_async(size)  # type: ignore

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
                    self._pipe, operation_type="read", timeout=None
                )

                # 处理返回结果（对标AsyncIOCPFile的处理逻辑）
                if isinstance(result_data, tuple):
                    if len(result_data) == 2:
                        is_complete, data = result_data
                        if is_complete:
                            if isinstance(data, bytes):
                                return data
                            elif isinstance(data, int):
                                # 重新调用check_completion获取实际数据
                                result = self._pipe.check_completion()  # type: ignore
                                if isinstance(result, tuple) and len(result) == 2:
                                    _, actual_data = result
                                    if isinstance(actual_data, bytes):
                                        return actual_data
                    elif len(result_data) == 3:
                        is_complete, data, error_code = result_data
                        if is_complete and isinstance(data, bytes):
                            return data
                elif isinstance(result_data, bytes):
                    return result_data
                else:
                    # 最后的fallback
                    result = self._pipe.check_completion()  # type: ignore
                    if isinstance(result, tuple) and len(result) == 2:
                        is_complete, data = result
                        if is_complete and isinstance(data, bytes):
                            return data

                    logger.error(f"从管道读取时遇到意外的结果格式: {result_data}, 类型: {type(result_data)}", extra={"log_type": "SYSTEM"})
                    raise RuntimeError(
                        f"Unexpected result format: {result_data}, type: {type(result_data)}"
                    )
        else:
            logger.error(f"从管道读取时遇到意外的结果类型: {type(result)}", extra={"log_type": "SYSTEM"})
            raise RuntimeError(f"Unexpected result type: {type(result)}")

        # 最后的fallback
        if self._pipe is not None:
            try:
                result = self._pipe.check_completion()  # type: ignore
                if isinstance(result, tuple) and len(result) == 2:
                    is_complete, data = result
                    if is_complete and isinstance(data, bytes):
                        return data
            except Exception as e:
                logger.debug(f"检查完成状态时发生异常: {e}", extra={"log_type": "SYSTEM"})

        logger.error(f"从管道读取失败: 意外的结果格式, 管道: {self.pipe_name}", extra={"log_type": "SYSTEM"})
        raise RuntimeError("Failed to read from pipe: unexpected result format")

    @native_async_call_guard(component="backend.native.ipc")
    async def write(self, data: bytes) -> int:
        """
        异步写入数据（真正的异步，不使用线程池）

        Args:
            data: 要写入的数据

        Returns:
            写入的字节数
        """
        if self._pipe is None:
            logger.error("管道未打开，无法写入", extra={"log_type": "SYSTEM"})
            raise ValueError("Pipe not opened")
        if self._closed:
            logger.error("管道已关闭，无法写入", extra={"log_type": "SYSTEM"})
            raise ValueError("Pipe is closed")

        if self._extension is None:
            logger.error("事件循环扩展未初始化", extra={"log_type": "SYSTEM"})
            raise RuntimeError("Event loop extension not initialized")

        # 启动异步写入
        result = self._pipe.write_async(data)  # type: ignore

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
                    self._pipe, operation_type="write", timeout=None
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
                    logger.error(f"向管道写入时遇到意外的结果格式: {result_data}", extra={"log_type": "SYSTEM"})
                    raise RuntimeError(f"Unexpected result format: {result_data}")
        else:
            logger.error(f"向管道写入时遇到意外的结果类型: {type(result)}", extra={"log_type": "SYSTEM"})
            raise RuntimeError(f"Unexpected result type: {type(result)}")

        return 0  # fallback

    async def close(self):
        """异步关闭管道"""
        if self._closed:
            return

        if self._pipe is not None:
            # 取消注册
            if self._extension:
                self._extension.unregister_iocp_pipe(self._pipe)

            # 关闭管道
            self._pipe.close()
            self._pipe = None

        self._closed = True

    def __repr__(self):
        status = "closed" if self._closed else ("open" if self._pipe else "not opened")
        return f"<AsyncIPCPipe: {self.pipe_name} role={self.role} status={status}>"

    async def _wait_for_client_connection(self, timeout: Optional[float] = None) -> None:
        """等待客户端连接完成，确保命名管道已建立连接"""
        if self._pipe is None:
            raise RuntimeError("IPC pipe not initialized")
        if self._extension is None:
            raise RuntimeError("Event loop extension not initialized")

        # 连接操作使用与读写相同的事件句柄，wait_for_completion会在事件触发后返回
        await self._extension.wait_for_completion(
            self._pipe,
            operation_type="connect",
            timeout=timeout,
        )

    async def wait_for_client(self, timeout: Optional[float] = None) -> None:
        """显式等待客户端连接完成

        Args:
            timeout: 等待超时时间（秒），None表示无限等待
        """

        await self._wait_for_client_connection(timeout=timeout)


# 简化API（对标aopen）
def aopen_server(
    pipe_name: str,
    *,
    wait_for_client: bool = True,
    connect_timeout: Optional[float] = None,
) -> _IPCPipeFactory:
    """
    创建服务端管道（简化API）

    Args:
        pipe_name: 管道名称
        wait_for_client: 是否在返回前等待客户端连接完成
        connect_timeout: 等待客户端连接的超时时间（秒），None为无限等待

    Returns:
        AsyncIPCPipe工厂对象

    Example:
        async with aopen_server("monitor_service") as pipe:
            data = await pipe.read()
    """
    return AsyncIPCPipe.server(
        pipe_name,
        wait_for_client=wait_for_client,
        connect_timeout=connect_timeout,
    )


def aopen_client(pipe_name: str) -> _IPCPipeFactory:
    """
    连接到服务端管道（简化API）

    Args:
        pipe_name: 管道名称

    Returns:
        AsyncIPCPipe工厂对象

    Example:
        async with aopen_client("monitor_service") as pipe:
            await pipe.write(b"request")
    """
    return AsyncIPCPipe.client(pipe_name)


__all__ = ["AsyncIPCPipe", "aopen_server", "aopen_client"]

