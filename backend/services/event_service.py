# -*- coding: utf-8 -*-
"""
事件服务.

提供基于VnPy事件引擎的事件处理和分发功能。
"""

import logging
import asyncio
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from .base_service import BaseService
from backend.api.websocket_manager import get_websocket_manager

if TYPE_CHECKING:
    from vnpy.event import EventEngine
    from .vnpy_service import VnpyService

logger = logging.getLogger(__name__)


class EventService(BaseService):
    """事件服务."""

    def __init__(self, vnpy_service: "VnpyService"):
        """初始化事件服务."""
        super().__init__("Event")
        self.vnpy_service = vnpy_service
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._websocket_manager = get_websocket_manager()
        self._event_queue = asyncio.Queue()
        self._event_processor_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """初始化事件服务."""
        try:
            self.logger.info("正在初始化事件服务...")

            # 获取VnPy事件引擎
            self._event_engine = self.vnpy_service.get_event_engine()
            if not self._event_engine:
                raise RuntimeError("VnPy事件引擎不可用")

            # 注册VnPy事件处理器
            await self._register_vnpy_handlers()

            # 启动事件处理任务
            self._event_processor_task = asyncio.create_task(self._process_events())

            self.logger.info("事件服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("事件服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭事件服务."""
        try:
            self.logger.info("正在关闭事件服务...")

            # 停止事件处理任务
            if self._event_processor_task:
                self._event_processor_task.cancel()
                try:
                    await self._event_processor_task
                except asyncio.CancelledError:
                    pass

            # 取消所有事件处理器
            await self._unregister_vnpy_handlers()

            self._event_handlers.clear()

            self.logger.info("事件服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("事件服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查事件服务健康状态."""
        try:
            status = {
                "event_engine_active": self._event_engine is not None,
                "handlers_count": len(self._event_handlers),
                "queue_size": self._event_queue.qsize(),
                "processor_task_active": (
                    self._event_processor_task is not None
                    and not self._event_processor_task.done()
                ),
                "timestamp": datetime.now().isoformat(),
            }

            # 检查事件引擎状态
            if self._event_engine:
                status["event_engine_status"] = "active"
            else:
                status["event_engine_status"] = "inactive"

            return status

        except Exception as e:
            self.logger.error("事件服务健康检查失败: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _register_vnpy_handlers(self) -> None:
        """注册VnPy事件处理器."""
        try:
            # 注册各种VnPy事件
            vnpy_events = [
                "eTick",
                "eOrder",
                "eTrade",
                "ePosition",
                "eAccount",
                "eContract",
                "eLog",
                "eError",
            ]

            for event_type in vnpy_events:
                self._event_engine.register(event_type, self._vnpy_event_handler)
                self.logger.debug("注册VnPy事件处理器: %s", event_type)

        except Exception as e:
            self.logger.error("注册VnPy事件处理器失败: %s", e)
            raise

    async def _unregister_vnpy_handlers(self) -> None:
        """取消注册VnPy事件处理器."""
        try:
            vnpy_events = [
                "eTick",
                "eOrder",
                "eTrade",
                "ePosition",
                "eAccount",
                "eContract",
                "eLog",
                "eError",
            ]

            for event_type in vnpy_events:
                self._event_engine.unregister(event_type, self._vnpy_event_handler)
                self.logger.debug("取消注册VnPy事件处理器: %s", event_type)

        except Exception as e:
            self.logger.error("取消注册VnPy事件处理器失败: %s", e)

    def _vnpy_event_handler(self, event) -> None:
        """VnPy事件处理器."""
        try:
            # 将VnPy事件转换为统一格式并放入队列
            unified_event = self._convert_vnpy_event(event)
            if unified_event:
                # 使用线程安全的方式放入队列
                asyncio.create_task(self._put_event_to_queue(unified_event))

        except Exception as e:
            self.logger.error("处理VnPy事件失败: %s", e)

    async def _put_event_to_queue(self, event: Dict[str, Any]) -> None:
        """将事件放入队列."""
        try:
            await self._event_queue.put(event)
        except Exception as e:
            self.logger.error("事件入队失败: %s", e)

    def _convert_vnpy_event(self, event) -> Optional[Dict[str, Any]]:
        """转换VnPy事件为统一格式."""
        try:
            event_type = event.type
            event_data = event.data

            unified_event = {
                "type": event_type,
                "data": self._convert_event_data(event_data),
                "timestamp": datetime.now().isoformat(),
                "source": "vnpy",
            }

            return unified_event

        except Exception as e:
            self.logger.error("转换VnPy事件失败: %s", e)
            return None

    def _convert_event_data(self, data: Any) -> Dict[str, Any]:
        """转换事件数据."""
        try:
            if hasattr(data, "__dict__"):
                return {
                    key: value
                    for key, value in data.__dict__.items()
                    if not key.startswith("_")
                }
            elif isinstance(data, dict):
                return data
            else:
                return {"raw_data": str(data)}

        except Exception as e:
            self.logger.error("转换事件数据失败: %s", e)
            return {"raw_data": str(data), "error": str(e)}

    async def _process_events(self) -> None:
        """处理事件队列."""
        try:
            while True:
                try:
                    # 从队列获取事件
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)

                    # 处理事件
                    await self._handle_event(event)

                    # 标记任务完成
                    self._event_queue.task_done()

                except asyncio.TimeoutError:
                    # 超时是正常的，继续循环
                    continue
                except asyncio.CancelledError:
                    # 任务被取消
                    break
                except Exception as e:
                    self.logger.error("处理事件失败: %s", e)

        except Exception as e:
            self.logger.error("事件处理循环失败: %s", e)

    async def _handle_event(self, event: Dict[str, Any]) -> None:
        """处理单个事件."""
        try:
            event_type = event.get("type")
            if not event_type:
                self.logger.warning("事件缺少type字段，跳过处理")
                return

            # 调用注册的事件处理器
            handlers = self._event_handlers.get(event_type, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    self.logger.error("事件处理器执行失败: %s - %s", event_type, e)

            # 通过WebSocket广播事件
            await self._broadcast_event(event)

        except Exception as e:
            self.logger.error("处理事件失败: %s", e)

    async def _broadcast_event(self, event: Dict[str, Any]) -> None:
        """通过WebSocket广播事件."""
        try:
            event_type = event.get("type")
            if not event_type:
                self.logger.warning("事件缺少type字段，跳过广播")
                return

            # 构造广播消息
            message = {
                "type": "vnpy_event",
                "event_type": event_type,
                "data": event.get("data"),
                "timestamp": event.get("timestamp"),
            }

            # 根据事件类型决定广播范围
            if event_type in ["eTick", "eOrder", "eTrade"]:
                # 实时交易数据广播给所有连接
                await self._websocket_manager.broadcast(message)
            elif event_type in ["eLog", "eError"]:
                # 日志和错误信息广播给管理员连接
                await self._websocket_manager.send_to_type("admin", message)
            else:
                # 其他事件广播给相关订阅者
                await self._websocket_manager.broadcast_to_topic(event_type, message)

        except Exception as e:
            self.logger.error("广播事件失败: %s", e)

    def register_handler(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

        self._event_handlers[event_type].append(handler)
        self.logger.info("注册事件处理器: %s", event_type)

    def unregister_handler(self, event_type: str, handler: Callable) -> None:
        """取消注册事件处理器."""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
                self.logger.info("取消注册事件处理器: %s", event_type)
            except ValueError:
                self.logger.warning("事件处理器不存在: %s", event_type)

    async def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """发送自定义事件."""
        try:
            event = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
                "source": "custom",
            }

            await self._event_queue.put(event)

        except Exception as e:
            self.logger.error("发送事件失败: %s", e)

    def get_event_statistics(self) -> Dict[str, Any]:
        """获取事件统计信息."""
        return {
            "handlers_count": len(self._event_handlers),
            "queue_size": self._event_queue.qsize(),
            "registered_events": list(self._event_handlers.keys()),
            "processor_task_active": (
                self._event_processor_task is not None
                and not self._event_processor_task.done()
            ),
        }


# 导出公共接口
__all__ = ["EventService"]
