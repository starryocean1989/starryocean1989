# -*- coding: utf-8 -*-
"""
数据进程RPC客户端 - 提供与数据进程的跨进程通信

职责：
- 连接数据进程的native_ipc管道
- 提供RPC调用接口（同步/异步）
- 缓存连接状态和重连逻辑
- 处理数据序列化/反序列化

使用方式：
```python
from backend.infrastructure.data_module_vnpy.data_process_client import DataProcessClient

client = DataProcessClient()
# 同步调用
result = client.call("get_kline_data", symbol="000001.SZ", start_date="2023-01-01")
# 异步调用
result = await client.call_async("get_kline_data", symbol="000001.SZ", start_date="2023-01-01")
```
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, Union
from concurrent.futures import ThreadPoolExecutor, Future
import threading

# 高性能JSON库（优先使用orjson）
try:
    import orjson
    JSON_ENCODER = orjson
    HAS_ORJSON = True
except ImportError:
    import json as JSON_ENCODER
    HAS_ORJSON = False

# native_ipc相关导入
try:
    from backend.infrastructure.native.native_ipc import AsyncIPCPipe, IPC_AVAILABLE
except ImportError:
    IPC_AVAILABLE = False
    AsyncIPCPipe = None

logger = logging.getLogger(__name__)


class DataProcessClient:
    """数据进程RPC客户端.

    提供与数据进程的同步和异步RPC调用接口。
    """

    def __init__(self):
        """初始化数据进程客户端."""
        self._connected = False
        self._pipes: Dict[str, Any] = {}  # {pipe_type: AsyncIPCPipe}
        self._lock = threading.Lock()
        self._response_futures: Dict[str, asyncio.Future] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="data_client")
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 连接配置
        self._connect_timeout = 5.0
        self._call_timeout = 30.0
        self._max_retries = 3
        self._retry_delay = 1.0

        # 记录使用的JSON库
        if HAS_ORJSON:
            logger.info("✅ 使用orjson高性能JSON库")
        else:
            logger.warning("⚠️ orjson不可用，使用标准json库（降级模式）")

        logger.info("数据进程客户端已创建")

    async def connect_async(self) -> bool:
        """异步连接到数据进程.

        Returns:
            bool: 连接是否成功
        """
        if not IPC_AVAILABLE or AsyncIPCPipe is None:
            logger.error("❌ native_ipc不可用，无法连接数据进程")
            return False

        with self._lock:
            if self._connected:
                logger.debug("数据进程客户端已连接")
                return True

            try:
                logger.info("正在连接数据进程...")

                # 连接数据查询管道（用于发送数据请求）
                try:
                    data_query_pipe = await AsyncIPCPipe.client("data_query")
                    self._pipes["data_query"] = data_query_pipe
                    logger.info("✅ 数据查询管道连接成功")
                except Exception as e:
                    logger.error(f"❌ 无法连接数据查询管道: {e}")
                    self._close_pipes()
                    return False

                # 连接计算任务管道（用于发送计算任务）
                try:
                    data_calculation_pipe = await AsyncIPCPipe.client("data_calculation")
                    self._pipes["data_calculation"] = data_calculation_pipe
                    logger.info("✅ 计算任务管道连接成功")
                except Exception as e:
                    logger.warning(f"⚠️ 无法连接计算任务管道: {e}（可选）")

                self._connected = True
                logger.info("✅ 数据进程连接成功")

                return True

            except Exception as e:
                logger.error(f"❌ 连接数据进程失败: {e}", exc_info=True)
                self._close_pipes()
                return False

    def connect(self) -> bool:
        """同步连接到数据进程（内部使用异步方法）.

        Returns:
            bool: 连接是否成功
        """
        if not IPC_AVAILABLE or AsyncIPCPipe is None:
            logger.error("❌ native_ipc不可用，无法连接数据进程")
            return False

        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
            # 如果事件循环已经在运行，使用run_coroutine_threadsafe
            if loop.is_running():
                future = Future()
                asyncio.run_coroutine_threadsafe(self._connect_with_future(future), loop)
                return future.result(timeout=self._connect_timeout)
            else:
                # 事件循环未运行，可以使用run_until_complete
                self._loop = loop
                return loop.run_until_complete(self.connect_async())
        except RuntimeError:
            # 没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                return loop.run_until_complete(self.connect_async())
            finally:
                loop.close()

    async def _connect_with_future(self, future: Future) -> None:
        """在已运行的事件循环中连接，并将结果设置到Future中."""
        try:
            result = await self.connect_async()
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)

    def disconnect(self) -> None:
        """断开与数据进程的连接."""
        with self._lock:
            if not self._connected:
                return

            logger.info("正在断开数据进程连接...")
            self._close_pipes()
            self._connected = False
            logger.info("✅ 数据进程连接已断开")

    def _close_pipes(self) -> None:
        """关闭所有管道."""
        for pipe_type, pipe in self._pipes.items():
            try:
                if pipe:
                    # AsyncIPCPipe没有显式的close方法，通过上下文管理器或直接删除引用
                    # 这里我们只清理引用，让Python的GC处理
                    logger.debug(f"管道已关闭: {pipe_type}")
            except Exception as e:
                logger.warning(f"关闭管道失败 {pipe_type}: {e}")

        self._pipes.clear()

    def is_connected(self) -> bool:
        """检查连接状态.

        Returns:
            bool: 是否已连接
        """
        return self._connected

    def call(self, method: str, **kwargs) -> Any:
        """同步RPC调用.

        Args:
            method: 方法名
            **kwargs: 方法参数

        Returns:
            调用结果

        Raises:
            Exception: 调用失败时抛出异常
        """
        if not self._connected and not self.connect():
            raise ConnectionError("无法连接到数据进程")

        # 创建异步任务并等待结果
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.call_async(method, **kwargs))

    async def call_async(self, method: str, **kwargs) -> Any:
        """异步RPC调用.

        Args:
            method: 方法名
            **kwargs: 方法参数

        Returns:
            调用结果

        Raises:
            Exception: 调用失败时抛出异常
        """
        if not self._connected:
            if not await self.connect_async():
                raise ConnectionError("无法连接到数据进程")

        request_id = str(uuid.uuid4())

        # 构建请求
        request = {"id": request_id, "method": method, "params": kwargs, "timestamp": time.time()}

        # 选择管道（根据方法类型选择）
        pipe_name = "data_query"  # 默认使用数据查询管道
        if method.startswith("calculate_") or method.startswith("compute_"):
            pipe_name = "data_calculation"

        pipe = self._pipes.get(pipe_name)
        if not pipe:
            raise ConnectionError(f"管道不可用: {pipe_name}")

        try:
            # 序列化请求（使用orjson优化）
            if HAS_ORJSON:
                # orjson.dumps返回bytes，直接使用
                request_data = orjson.dumps(request)
            else:
                # 降级到标准json
                request_data = json.dumps(request, ensure_ascii=False).encode("utf-8")

            # 发送请求
            await pipe.write(request_data)

            # 读取响应（带超时）
            response_data = await asyncio.wait_for(pipe.read(), timeout=self._call_timeout)

            # 反序列化响应（使用orjson优化）
            if HAS_ORJSON:
                response = orjson.loads(response_data)
            else:
                # 降级到标准json
                response = json.loads(response_data.decode("utf-8"))

            # 验证响应ID
            if response.get("id") != request_id:
                logger.warning(f"响应ID不匹配: 期望{request_id}, 收到{response.get('id')}")

            # 处理响应
            if response.get("error"):
                error = response["error"]
                raise Exception(f"RPC调用失败: {error}")

            return response.get("result")

        except asyncio.TimeoutError:
            raise TimeoutError(f"RPC调用超时: {method}")
        except Exception as e:
            logger.error(f"RPC调用失败: {method}, 错误: {e}", exc_info=True)
            raise

    def __enter__(self):
        """上下文管理器入口."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口."""
        self.disconnect()


# 全局客户端实例
_global_data_client: Optional[DataProcessClient] = None
_client_lock = threading.Lock()


def get_data_process_client() -> DataProcessClient:
    """获取全局数据进程客户端实例.

    Returns:
        DataProcessClient: 客户端实例
    """
    global _global_data_client

    if _global_data_client is None:
        with _client_lock:
            if _global_data_client is None:
                _global_data_client = DataProcessClient()

    return _global_data_client
