# -*- coding: utf-8 -*-
"""
启动事件总线与就绪工具

提供启动流程中的事件发布/订阅、就绪屏障以及状态追踪能力，支持：
- 节点开始/完成/失败事件
- 统一的有序事件历史
- 基于事件的就绪等待（Barrier）
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("backend.startup.event_bus")

CallbackType = Callable[["StartupEvent"], Union[None, Awaitable[None]]]


class StartupEventType(str, enum.Enum):
    """启动事件类型"""

    NODE_STARTED = "node_started"
    NODE_READY = "node_ready"
    NODE_FAILED = "node_failed"
    NODE_PROGRESS = "node_progress"
    METRIC = "metric"
    CUSTOM = "custom"


@dataclass
class StartupEvent:
    """启动事件数据结构"""

    event_type: StartupEventType
    node_id: str
    message: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def ready_key(self) -> Optional[str]:
        """获取就绪事件的唯一键"""
        if self.event_type != StartupEventType.NODE_READY:
            return None
        if "ready_key" in self.payload:
            return str(self.payload["ready_key"])
        level = self.payload.get("level")
        if level is None:
            return self.node_id
        return f"{self.node_id}:{level}"


class EventBus:
    """简单的异步事件总线"""

    def __init__(self, max_history: int = 200) -> None:
        self._subscriptions: Dict[Optional[StartupEventType], Dict[str, CallbackType]] = {}
        self._history: List[StartupEvent] = []
        self._max_history = max_history
        self._loop = asyncio.get_event_loop()
        self._lock = asyncio.Lock()

    def subscribe(
        self, callback: CallbackType, event_type: Optional[StartupEventType] = None
    ) -> str:
        """订阅事件

        Args:
            callback: 回调函数（同步或异步）
            event_type: 指定事件类型，None 表示订阅所有事件

        Returns:
            str: 订阅 token，可用于取消订阅
        """
        token = uuid.uuid4().hex
        bucket = self._subscriptions.setdefault(event_type, {})
        bucket[token] = callback
        return token

    def unsubscribe(self, token: str) -> None:
        """取消订阅"""
        for bucket in self._subscriptions.values():
            if token in bucket:
                bucket.pop(token, None)

    async def publish(self, event: StartupEvent) -> None:
        """发布事件"""
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

        await asyncio.gather(*self._dispatch(event), return_exceptions=True)

    def publish_nowait(self, event: StartupEvent) -> None:
        """在当前线程或loop中发布事件."""
        loop = self._loop
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is loop and loop.is_running():
            loop.create_task(self.publish(event))
        else:
            self.publish_threadsafe(event)

    def publish_threadsafe(self, event: StartupEvent) -> None:
        """跨线程安全发布事件."""
        try:
            asyncio.run_coroutine_threadsafe(self.publish(event), self._loop)
        except RuntimeError:
            # loop 可能尚未启动，退回到 call_soon_threadsafe
            self._loop.call_soon_threadsafe(asyncio.create_task, self.publish(event))

    def _dispatch(self, event: StartupEvent) -> List[Awaitable[Any]]:
        callbacks: List[CallbackType] = []
        callbacks.extend(self._subscriptions.get(None, {}).values())
        callbacks.extend(self._subscriptions.get(event.event_type, {}).values())

        tasks: List[Awaitable[Any]] = []
        for cb in callbacks:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    tasks.append(asyncio.create_task(result))
            except Exception as exc:  # noqa: BLE001
                logger.exception("事件回调执行失败: %s", exc)
        return tasks

    async def wait_for(
        self,
        event_type: StartupEventType,
        *,
        node_id: Optional[str] = None,
        predicate: Optional[Callable[[StartupEvent], bool]] = None,
        timeout: Optional[float] = None,
    ) -> StartupEvent:
        """等待符合条件的事件"""

        loop = self._loop
        future: asyncio.Future[StartupEvent] = loop.create_future()

        def _listener(event: StartupEvent) -> None:
            if node_id and event.node_id != node_id:
                return
            if predicate and not predicate(event):
                return
            if not future.done():
                future.set_result(event)
            self.unsubscribe(token)

        token = self.subscribe(_listener, event_type=event_type)
        try:
            if timeout is not None:
                return await asyncio.wait_for(future, timeout=timeout)
            return await future
        except asyncio.TimeoutError:
            self.unsubscribe(token)
            raise

    @property
    def history(self) -> List[StartupEvent]:
        """获取事件历史（只读副本）"""
        return list(self._history)


class ReadinessBarrier:
    """启动就绪屏障

    监听 NODE_READY 事件，等待所有目标事件到达后返回。
    """

    def __init__(
        self,
        bus: EventBus,
        ready_keys: List[str],
        *,
        auto_close: bool = True,
    ) -> None:
        self._bus = bus
        self._required = set(ready_keys)
        self._arrived: Dict[str, StartupEvent] = {}
        self._event = asyncio.Event()
        self._token = bus.subscribe(self._on_ready, event_type=StartupEventType.NODE_READY)
        self._auto_close = auto_close
        self._prime_from_history()

    def _on_ready(self, event: StartupEvent) -> None:
        key = event.ready_key()
        if key is None:
            return
        if key not in self._required:
            return
        self._arrived[key] = event
        if self._required.issubset(self._arrived.keys()):
            self._event.set()
            if self._auto_close:
                self.close()

    def _prime_from_history(self) -> None:
        """使用已有历史事件预热屏障状态"""
        for event in self._bus.history:
            if event.event_type != StartupEventType.NODE_READY:
                continue
            self._on_ready(event)

    async def wait(self, timeout: Optional[float] = None) -> Dict[str, StartupEvent]:
        """等待所有目标就绪"""
        try:
            if timeout is not None:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
            else:
                await self._event.wait()
        except asyncio.TimeoutError:
            raise
        return dict(self._arrived)

    def close(self) -> None:
        """释放资源"""
        if self._token:
            self._bus.unsubscribe(self._token)
            self._token = ""

    def __del__(self) -> None:  # noqa: D401
        self.close()


