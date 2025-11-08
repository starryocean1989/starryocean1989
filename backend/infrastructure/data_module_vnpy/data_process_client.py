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
import base64
import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union, Coroutine, TypeVar, cast

T = TypeVar("T")

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

# 原生RPC桥接
try:
    from backend.infrastructure.native.native_rpc_bridge import (
        RPC_BRIDGE_AVAILABLE,
        create_request_header,
        get_method_id,
        get_method_name,
    )
except ImportError:  # pragma: no cover - C 扩展缺失时降级
    RPC_BRIDGE_AVAILABLE = False  # type: ignore

    def create_request_header(method_id: int, payload_size: int) -> Dict[str, Any]:  # type: ignore
        raise ImportError("native_rpc_bridge not available")


    def get_method_id(method_name: str) -> int:  # type: ignore
        raise ImportError("native_rpc_bridge not available")


    def get_method_name(method_id: int) -> Optional[str]:  # type: ignore
        return None

# RPC 协议封装
from backend.infrastructure.data_module_vnpy.rpc_protocol import (
    FLAG_BATCH,
    RPCResponse,
    attach_binary_fields,
    decode_response,
    encode_native_request,
)

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
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._run_event_loop,
            name="DataProcessClientLoop",
            daemon=True,
        )
        self._loop_thread.start()
        self._loop_ready.wait()
        self._native_enabled = RPC_BRIDGE_AVAILABLE
        self._method_id_cache: Dict[str, int] = {}

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

        if self._native_enabled:
            logger.info("✅ 原生RPC协议已启用 (native_rpc_bridge)")
        else:
            logger.info("ℹ️ 使用 JSON RPC 协议模式")

        logger.info("数据进程客户端已创建")

    # ==================== 底层辅助方法 ====================

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        self._loop.run_forever()

    def _submit_coroutine(self, coro: Coroutine[Any, Any, T]) -> Future:
        if not self._loop_ready.is_set():
            self._loop_ready.wait()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _connect_internal(self) -> bool:
        if not IPC_AVAILABLE or AsyncIPCPipe is None:
            logger.error("❌ native_ipc不可用，无法连接数据进程")
            return False

        with self._lock:
            if self._connected:
                logger.debug("数据进程客户端已连接")
                return True

        try:
            logger.info("正在连接数据进程...")

            data_query_pipe = await AsyncIPCPipe.client("data_query")
            data_calculation_pipe: Optional[Any] = None
            try:
                data_calculation_pipe = await AsyncIPCPipe.client("data_calculation")
            except Exception as exc:
                logger.warning("⚠️ 无法连接计算任务管道: %s（可选）", exc)

            with self._lock:
                self._pipes["data_query"] = data_query_pipe
                if data_calculation_pipe:
                    self._pipes["data_calculation"] = data_calculation_pipe
                self._connected = True

            logger.info("✅ 数据进程连接成功")
            return True

        except Exception as exc:
            logger.error("❌ 连接数据进程失败: %s", exc, exc_info=True)
            self._close_pipes()
            return False

    async def _call_internal(self, method: str, *args, **kwargs) -> Any:
        if not self._connected:
            if not await self._connect_internal():
                raise ConnectionError("无法连接到数据进程")

        pipe_name = "data_query"
        if method.startswith("calculate_") or method.startswith("compute_"):
            pipe_name = "data_calculation"

        pipe = self._pipes.get(pipe_name)
        if not pipe:
            raise ConnectionError(f"管道不可用: {pipe_name}")

        request_id, payload_bytes, use_native = self._build_request_message(
            method,
            args,
            kwargs,
            extra_metadata={"protocol": "native_v1"} if self._native_enabled else None,
        )

        try:
            await pipe.write(payload_bytes)
            response_data = await asyncio.wait_for(pipe.read(), timeout=self._call_timeout)
            return self._parse_response_buffer(
                response_data,
                expect_native=use_native,
                expected_request_id=request_id,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"RPC调用超时: {method}") from exc
        except Exception as exc:
            logger.error("RPC调用失败: %s, 错误: %s", method, exc, exc_info=True)
            raise

    def _serialize_json(self, payload: Dict[str, Any]) -> bytes:
        if HAS_ORJSON:
            return cast(bytes, JSON_ENCODER.dumps(payload))
        return JSON_ENCODER.dumps(payload, ensure_ascii=False).encode("utf-8")  # type: ignore[call-arg]

    def _deserialize_json(self, payload: bytes) -> Dict[str, Any]:
        if HAS_ORJSON:
            return JSON_ENCODER.loads(payload)
        return json.loads(payload.decode("utf-8"))

    def _get_method_id(self, method: str) -> Optional[int]:
        if not self._native_enabled:
            return None
        cached = self._method_id_cache.get(method)
        if cached:
            return cached
        try:
            method_id = int(get_method_id(method))
        except Exception:
            logger.debug("native_rpc_bridge 无法获取方法ID，回退到JSON: %s", method)
            return None
        if method_id <= 0:
            return None
        self._method_id_cache[method] = method_id
        return method_id

    def _build_request_message(
        self,
        method: str,
        args: Sequence[Any],
        params: Dict[str, Any],
        *,
        extra_metadata: Optional[Dict[str, Any]] = None,
        request_flags: int = 0,
    ) -> Tuple[Union[int, str], bytes, bool]:
        method_id = self._get_method_id(method)
        if method_id is not None:
            try:
                request_id, message = encode_native_request(
                    method_id,
                    {"args": list(args), "kwargs": params},
                    create_header=create_request_header,
                    method_name=method,
                    extra_metadata=extra_metadata,
                    flags=request_flags,
                )
                return request_id, message, True
            except Exception:  # pragma: no cover - C 扩展异常时回退
                logger.debug("原生RPC编码失败，回退JSON协议", exc_info=True)
                self._native_enabled = False

        request_id = str(uuid.uuid4())
        request_payload = {
            "id": request_id,
            "method": method,
            "params": {
                "_args": list(args) if args else [],
                "_kwargs": params,
            },
            "timestamp": time.time(),
        }
        if extra_metadata:
            request_payload.update(extra_metadata)
        message = self._serialize_json(request_payload)
        return request_id, message, False

    def _parse_response_buffer(
        self,
        response_bytes: bytes,
        *,
        expect_native: bool,
        expected_request_id: Union[int, str],
    ) -> Any:
        if expect_native:
            decoded: RPCResponse = decode_response(response_bytes)
            if decoded.request_id != expected_request_id:
                logger.warning(
                    "响应ID不匹配: 期望 %s, 实际 %s", expected_request_id, decoded.request_id
                )
            metadata = decoded.metadata or {}
            binary_fields = metadata.get("binary_fields") if isinstance(metadata, dict) else None
            if binary_fields and decoded.payload is not None:
                attach_binary_fields(metadata, binary_fields, decoded.payload)
                # 避免调用方看到内部字段
                metadata.pop("binary_fields", None)

            if decoded.error:
                raise RuntimeError(f"RPC调用失败: {decoded.error}")

            return metadata.get("result") if isinstance(metadata, dict) else decoded.result

        response_payload = self._deserialize_json(response_bytes)
        if response_payload.get("id") != expected_request_id:
            logger.warning(
                "响应ID不匹配: 期望 %s, 实际 %s",
                expected_request_id,
                response_payload.get("id"),
            )

        if response_payload.get("error"):
            raise RuntimeError(f"RPC调用失败: {response_payload['error']}")

        result = response_payload.get("result")
        if (
            isinstance(result, dict)
            and result.get("transport") == "base64"
            and isinstance(result.get("data"), str)
        ):
            try:
                decoded_bytes = base64.b64decode(result["data"], validate=True)
                result["data"] = memoryview(decoded_bytes)
                result["transport"] = "buffer"
            except Exception:
                logger.debug("base64 数据解析失败，保持原样", exc_info=True)
        return result

    async def connect_async(self) -> bool:
        """异步连接到数据进程.

        Returns:
            bool: 连接是否成功
        """
        running_loop = None
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if running_loop is self._loop:
            return await self._connect_internal()

        future = self._submit_coroutine(self._connect_internal())
        return await asyncio.wrap_future(future)

    def connect(self) -> bool:
        """同步连接到数据进程（内部使用异步方法）.

        Returns:
            bool: 连接是否成功
        """
        future = self._submit_coroutine(self._connect_internal())
        return future.result(timeout=self._connect_timeout)

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

    def call(self, method: str, *args, **kwargs) -> Any:
        """同步RPC调用.

        Args:
            method: 方法名
            *args: 位置参数
            **kwargs: 方法参数

        Returns:
            调用结果

        Raises:
            Exception: 调用失败时抛出异常
        """
        future = self._submit_coroutine(self._call_internal(method, *args, **kwargs))
        return future.result(timeout=self._call_timeout)

    async def call_async(self, method: str, *args, **kwargs) -> Any:
        """异步RPC调用.

        Args:
            method: 方法名
            *args: 位置参数
            **kwargs: 方法参数

        Returns:
            调用结果

        Raises:
            Exception: 调用失败时抛出异常
        """
        running_loop = None
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if running_loop is self._loop:
            return await self._call_internal(method, *args, **kwargs)

        future = self._submit_coroutine(self._call_internal(method, *args, **kwargs))
        return await asyncio.wrap_future(future)

    async def call_many_async(
        self,
        method: str,
        params_list: Sequence[Dict[str, Any]],
    ) -> List[Any]:
        """批量异步RPC调用（顺序执行，复用同一连接）."""

        if not params_list:
            return []
        running_loop = None
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        results: List[Any] = []
        for params in params_list:
            if not isinstance(params, dict):
                raise TypeError("params_list 中的元素必须为 dict")

            if running_loop is self._loop:
                results.append(await self._call_internal(method, **params))
            else:
                future = self._submit_coroutine(self._call_internal(method, **params))
                results.append(await asyncio.wrap_future(future))
        return results

    def call_many(self, method: str, params_list: Sequence[Dict[str, Any]]) -> List[Any]:
        """批量同步RPC调用."""

        results: List[Any] = []
        for params in params_list:
            if not isinstance(params, dict):
                raise TypeError("params_list 中的元素必须为 dict")
            results.append(self.call(method, **params))
        return results

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
