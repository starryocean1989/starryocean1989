# -*- coding: utf-8 -*-
"""
IPC Queue Adapter - multiprocessing.Queue 的高性能替代方案

提供与 multiprocessing.Queue 兼容的接口，底层使用 native_ipc。
适用于高频率的跨进程数据交换场景。

核心特性:
- 提供类似 multiprocessing.Queue 的接口
- 底层使用 native_ipc (Windows Named Pipe + IOCP)
- 支持异步操作
- 自动序列化/反序列化
- 向后兼容，支持fallback到multiprocessing.Queue
"""

import asyncio
import logging
import pickle
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# 🚀 原生IPC异步跨进程通信：优先使用Windows Named Pipe+IOCP
try:
    from backend.infrastructure.native_ipc import AsyncIPCPipe, IPC_AVAILABLE
    _USE_IPC = True
    _AsyncIPCPipeType = AsyncIPCPipe
except ImportError:
    _AsyncIPCPipeType = Any  # type: ignore
    IPC_AVAILABLE = False
    _USE_IPC = False


class IPCQueue:
    """
    基于 native_ipc 的异步队列

    提供类似 multiprocessing.Queue 的接口，但使用真正的异步IPC。
    适用于高频率的跨进程数据交换，如监控指标上报、结果收集等。

    注意：仅适用于主进程和worker进程之间的单向或双向通信。
    multiprocessing.Queue 适用于多进程池中的任务分发，有更完善的进程间同步机制。
    """

    def __init__(
        self,
        pipe_name: str,
        role: str = "server",
        maxsize: int = 0,
        enable_ipc: Optional[bool] = None,
    ):
        """
        初始化IPC队列

        Args:
            pipe_name: 管道名称（全局唯一）
            role: 角色（'server' 或 'client'）
            maxsize: 队列最大容量（0表示无限制，IPC不支持有界队列）
            enable_ipc: 是否启用IPC（None则自动检测）
        """
        self.pipe_name = pipe_name
        self.role = role
        self.maxsize = maxsize  # IPC原生不支持maxsize，仅用于兼容性

        # 自动检测是否使用IPC
        if enable_ipc is None:
            enable_ipc = _USE_IPC and IPC_AVAILABLE

        self._use_ipc = enable_ipc
        self._pipe: Optional[_AsyncIPCPipeType] = None  # type: ignore
        self._closed = False

        if self._use_ipc:
            logger.debug(f"IPCQueue 启用 native_ipc: {pipe_name} (role={role})")
        else:
            logger.debug(f"IPCQueue 使用 fallback (native_ipc 不可用): {pipe_name}")

    async def connect(self):
        """连接管道（异步）"""
        if self._closed:
            raise ValueError("IPCQueue is closed")

        if not self._use_ipc or AsyncIPCPipe is None:
            raise RuntimeError("IPC not available, cannot connect")

        if self._pipe is None:
            if self.role == "server":
                self._pipe = await AsyncIPCPipe.server(self.pipe_name)
            elif self.role == "client":
                self._pipe = await AsyncIPCPipe.client(self.pipe_name)
            else:
                raise ValueError(f"Invalid role: {self.role}")

            logger.debug(f"IPCQueue connected: {self.pipe_name} (role={self.role})")

    async def put(self, item: Any):
        """异步发送数据"""
        if self._closed:
            raise ValueError("IPCQueue is closed")

        if self._pipe is None:
            await self.connect()

        try:
            # 序列化数据
            data = pickle.dumps(item)

            # 发送数据
            if self._pipe:
                bytes_written = await self._pipe.write(data)
                if bytes_written != len(data):
                    raise RuntimeError(f"Partial write: {bytes_written}/{len(data)} bytes")
        except Exception as e:
            logger.error(f"IPCQueue.put failed: {e}")
            raise

    async def get(self) -> Any:
        """异步接收数据"""
        if self._closed:
            raise ValueError("IPCQueue is closed")

        if self._pipe is None:
            await self.connect()

        try:
            # 接收数据
            if self._pipe:
                data = await self._pipe.read()

                # 反序列化数据
                item = pickle.loads(data)
                return item
        except Exception as e:
            logger.error(f"IPCQueue.get failed: {e}")
            raise

    def put_nowait(self, item: Any):
        """
        非阻塞发送（需要运行事件循环）

        注意：这会在后台创建一个Task，不等待完成。
        适用于fire-and-forget场景。
        """
        if not self._use_ipc:
            raise RuntimeError("put_nowait requires IPC mode")

        # 在当前事件循环中调度
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self.put(item))
        else:
            # 如果循环未运行，同步等待
            asyncio.run(self.put(item))

    async def close(self):
        """关闭队列"""
        if self._pipe:
            await self._pipe.close()
            self._pipe = None
        self._closed = True
        logger.debug(f"IPCQueue closed: {self.pipe_name}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False

    def qsize(self) -> int:
        """
        返回队列大小（IPC不支持，返回0）

        注意：IPC Native Pipe没有内置队列大小概念。
        如果需要队列长度监控，需要在应用层实现。
        """
        return 0

    def empty(self) -> bool:
        """
        检查队列是否为空（IPC不支持，返回False）

        注意：IPC Native Pipe是流式通信，没有队列概念。
        """
        return False

    def full(self) -> bool:
        """
        检查队列是否已满（IPC不支持，返回False）

        注意：IPC Native Pipe没有队列大小限制。
        """
        return False


def create_fallback_queue(maxsize: int = 0):
    """
    创建fallback队列（multiprocessing.Queue）

    当IPC不可用时使用此函数创建标准的multiprocessing.Queue。
    """
    import multiprocessing as mp
    return mp.Queue(maxsize=maxsize)


async def create_ipc_queue_pair(
    base_name: str,
    maxsize: int = 0,
    enable_ipc: Optional[bool] = None,
) -> tuple[IPCQueue, IPCQueue]:
    """
    创建一对连接的IPC队列（用于双向通信）

    Args:
        base_name: 基础管道名称
        maxsize: 队列最大容量
        enable_ipc: 是否启用IPC

    Returns:
        (server_queue, client_queue): 服务端队列和客户端队列

    Example:
        server_q, client_q = await create_ipc_queue_pair("monitor_metrics")

        # 在一个进程中
        await server_q.put("data")

        # 在另一个进程中
        data = await client_q.get()
    """
    server_name = f"{base_name}_server"
    client_name = f"{base_name}_client"

    server_queue = IPCQueue(server_name, role="server", maxsize=maxsize, enable_ipc=enable_ipc)
    client_queue = IPCQueue(client_name, role="client", maxsize=maxsize, enable_ipc=enable_ipc)

    # 预先连接
    await server_queue.connect()
    await client_queue.connect()

    return server_queue, client_queue

