# -*- coding: utf-8 -*-
"""
异步Socket客户端基类
使用asyncio替代threading，实现纯异步通信
"""
import asyncio
import functools
import time
from typing import Optional, Tuple

from .exceptions import TdxConnectionError, TdxFunctionCallError, ValidationException
from .logger import logger
from .parser.async_raw_parser import AsyncRawParser

DEFAULT_HEARTBEAT_INTERVAL = 10.0
CONNECT_TIMEOUT = 5.0
RECV_HEADER_LEN = 0x10


def async_last_ack_time(func):
    """
    异步装饰器: 更新最后 ack 时间
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kw):
        self.last_ack_time = time.time()

        logger.debug(f"last ack time update to {self.last_ack_time}")

        ret = None

        try:
            ret = await func(self, *args, **kw)
        except (TypeError, ValueError) as e:
            raise ValidationException(*e.args)
        except Exception as e:
            current_exception = e
            logger.debug(f"hit exception on req exception is {e}")

            if self.auto_retry:
                for time_interval in self.retry_strategy.generate():
                    try:
                        await asyncio.sleep(time_interval)

                        await self.disconnect()
                        await self.connect(self.ip, self.port)

                        ret = await func(self, *args, **kw)
                        return ret

                    except Exception as retry_e:
                        logger.debug(f"hit exception on *retry* req exception is {retry_e}")
                        current_exception = retry_e

                logger.debug("perform auto retry on req ")

            if self.raise_exception:
                to_raise = TdxFunctionCallError("calling function error")
                to_raise.original_exception = current_exception
                raise to_raise

        return ret

    return wrapper


class RetryStrategy:
    @classmethod
    def generate(cls):
        raise NotImplementedError("need to override")


class DefaultRetryStrategy(RetryStrategy):
    """
    默认的重试策略
    """

    @classmethod
    def generate(cls):
        yield from [0.1, 0.5, 1, 2]


class AsyncBaseSocketClient:
    """
    异步Socket客户端基类
    使用asyncio.open_connection替代socket.socket
    """

    def __init__(
        self,
        heartbeat=False,
        auto_retry=False,
        raise_exception=False
    ):
        """
        构造函数
        :param heartbeat: 是否心跳
        :param auto_retry: 是否自动重试
        :param raise_exception: 是否抛出异常
        """
        self.need_setup = True
        self.closed = True

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self.lock = asyncio.Lock()  # 异步锁

        self.heartbeat = heartbeat
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.stop_heartbeat = False

        self.heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL

        self.last_ack_time = time.time()

        self.ip, self.port = None, None

        self.auto_retry = auto_retry
        self.retry_strategy = DefaultRetryStrategy()
        self.raise_exception = raise_exception

        # 流量统计
        self.send_pkg_num = 0
        self.recv_pkg_num = 0
        self.send_pkg_bytes = 0
        self.recv_pkg_bytes = 0

    async def connect(
        self,
        ip: str = None,
        port: int = 7709,
        time_out=CONNECT_TIMEOUT
    ):
        """
        连接服务器（异步）

        :param ip: 服务器ip地址
        :param port: 服务器端口
        :param time_out: 连接超时时间
        :return: self
        """
        if not ip:
            raise ValidationException("IP Address bad.")

        logger.debug(f"connecting to server: {ip} on port: {port}")

        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=time_out
            )
        except asyncio.TimeoutError:
            logger.debug("connection expired")
            if self.raise_exception:
                raise TdxConnectionError("connection timeout error")
            return False
        except Exception as e:
            logger.debug(f"connection error: {e}")
            if self.raise_exception:
                raise TdxConnectionError(f"connection error: {e}")
            return False

        self.ip, self.port = ip, port
        self.closed = False
        logger.debug("connected!")

        if self.need_setup:
            await self.setup()

        # 启动心跳任务
        if self.heartbeat:
            self.stop_heartbeat = False
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return self

    async def disconnect(self):
        """
        断开连接（异步）
        """
        # 停止心跳任务
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.stop_heartbeat = True
            try:
                await asyncio.wait_for(self.heartbeat_task, timeout=1.0)
            except asyncio.TimeoutError:
                self.heartbeat_task.cancel()

        if self.writer:
            logger.debug("disconnecting")
            try:
                # 🔧 检查连接是否仍然有效
                if not self.writer.is_closing():
                    self.writer.close()
                    # 🔧 添加短暂超时，避免长时间等待
                    try:
                        await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
                    except asyncio.TimeoutError:
                        # 🔧 超时不算错误，静默处理
                        logger.debug("wait_closed timeout, connection may already closed")
                    except (ConnectionError, BrokenPipeError, OSError, RuntimeError) as e:
                        # 🔧 连接已断开或事件循环已关闭，静默处理
                        logger.debug(f"wait_closed: {type(e).__name__}")
                else:
                    logger.debug("writer already closing, skip")
            except (ConnectionError, BrokenPipeError, OSError, RuntimeError, AttributeError) as e:
                # 🔧 连接已断开或对象已释放的常见异常，静默处理
                logger.debug(f"disconnect: connection issue ({type(e).__name__})")
            except Exception as e:
                # 🔧 其他未知异常，记录但不崩溃
                logger.debug(f"disconnect unexpected err: {type(e).__name__}: {e}")
                if self.raise_exception:
                    raise TdxConnectionError(f"disconnect err: {e}")
            finally:
                # 🔧 确保资源清理，即使出现异常
                self.writer = None
                self.reader = None
                self.closed = True

            logger.debug("disconnected")

    async def close(self):
        """
        disconnect的别名
        """
        await self.disconnect()

    async def _heartbeat_loop(self):
        """
        异步心跳循环
        """
        while not self.stop_heartbeat:
            await asyncio.sleep(self.heartbeat_interval)
            if not self.stop_heartbeat:
                try:
                    await self.send_heartbeat()
                except Exception as e:
                    logger.debug(f"heartbeat error: {e}")
                    break

    async def setup(self):
        """
        初始化连接
        需要子类实现
        """
        pass

    async def send_heartbeat(self):
        """
        发送心跳包
        需要子类实现
        """
        pass

    async def send_pkg(self, pkg_bytes: bytes) -> bytes:
        """
        发送数据包并接收响应（异步）

        :param pkg_bytes: 要发送的字节数据
        :return: 接收到的响应数据
        """
        if self.closed or not self.writer:
            raise TdxConnectionError("connection is closed")

        async with self.lock:
            try:
                # 发送数据
                self.writer.write(pkg_bytes)
                await self.writer.drain()

                self.send_pkg_num += 1
                self.send_pkg_bytes += len(pkg_bytes)

                logger.debug(f"send pkg: {len(pkg_bytes)} bytes")

                # 接收响应头
                header = await self.reader.readexactly(RECV_HEADER_LEN)
                self.recv_pkg_bytes += len(header)

                # 解析响应体长度
                body_len = AsyncRawParser.parse_pkg_header(header)

                logger.debug(f"recv header, body_len: {body_len}")

                # 接收响应体
                if body_len > 0:
                    body = await self.reader.readexactly(body_len)
                    self.recv_pkg_bytes += len(body)
                    self.recv_pkg_num += 1

                    logger.debug(f"recv body: {len(body)} bytes")

                    return header + body
                else:
                    return header
            except (ConnectionResetError, BrokenPipeError) as e:
                # 连接被对端重置或管道已断开
                logger.error(f"连接已断开: {type(e).__name__}: {e}, server={self.ip}:{self.port}")
                self.closed = True
                raise TdxConnectionError(f"连接已断开 ({type(e).__name__}): {e}")
            except asyncio.TimeoutError as e:
                # 超时错误
                logger.error(f"操作超时: {e}, server={self.ip}:{self.port}")
                raise TdxConnectionError(f"操作超时: {e}")
            except asyncio.IncompleteReadError as e:
                # 读取不完整
                logger.error(f"数据读取不完整: {e}, server={self.ip}:{self.port}")
                self.closed = True
                raise TdxConnectionError(f"数据读取不完整: {e}")
            except Exception as e:
                # 其他未知异常
                logger.error(f"发送/接收数据时发生异常: {type(e).__name__}: {e}, server={self.ip}:{self.port}", exc_info=True)
                self.closed = True
                raise TdxConnectionError(f"通信异常 ({type(e).__name__}): {e}")

    def get_traffic_stats(self):
        """
        获取流量统计信息
        """
        return {
            "send_pkg_num": self.send_pkg_num,
            "recv_pkg_num": self.recv_pkg_num,
            "send_pkg_bytes": self.send_pkg_bytes,
            "recv_pkg_bytes": self.recv_pkg_bytes,
        }

