# -*- coding: utf-8 -*-
"""
WebSocket连接管理模块.

提供WebSocket连接的统一管理，包括连接池、消息广播、连接状态监控等。
"""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """WebSocket连接封装."""

    def __init__(
        self, websocket: WebSocket, client_id: str, connection_type: str = "default"
    ):
        """初始化WebSocket连接."""
        self.websocket = websocket
        self.client_id = client_id
        self.connection_type = connection_type
        self.connected_at = asyncio.get_event_loop().time()
        self.last_activity = self.connected_at
        self.subscriptions: Set[str] = set()

    async def send_json(self, data: dict) -> bool:
        """发送JSON数据."""
        try:
            await self.websocket.send_json(data)
            self.last_activity = asyncio.get_event_loop().time()
            return True
        except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
            logger.error("发送消息失败 %s: %s", self.client_id, e)
            return False

    async def send_text(self, text: str) -> bool:
        """发送文本数据."""
        try:
            await self.websocket.send_text(text)
            self.last_activity = asyncio.get_event_loop().time()
            return True
        except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
            logger.error("发送文本失败 %s: %s", self.client_id, e)
            return False

    def subscribe(self, topic: str) -> None:
        """订阅主题."""
        self.subscriptions.add(topic)
        logger.info("客户端 %s 订阅主题: %s", self.client_id, topic)

    def unsubscribe(self, topic: str) -> None:
        """取消订阅主题."""
        self.subscriptions.discard(topic)
        logger.info("客户端 %s 取消订阅主题: %s", self.client_id, topic)

    def is_subscribed(self, topic: str) -> bool:
        """检查是否订阅了主题."""
        return topic in self.subscriptions


class WebSocketManager:
    """WebSocket连接管理器."""

    def __init__(self):
        """初始化WebSocket管理器."""
        self.connections: Dict[str, WebSocketConnection] = {}
        self.connections_by_type: Dict[str, Set[str]] = defaultdict(set)
        self.topic_subscribers: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, client_id: str, connection_type: str = "default"
    ) -> WebSocketConnection:
        """接受WebSocket连接."""
        await websocket.accept()

        async with self._lock:
            # 如果客户端已存在连接，先断开旧连接
            if client_id in self.connections:
                await self.disconnect(client_id)

            # 创建新连接
            connection = WebSocketConnection(websocket, client_id, connection_type)
            self.connections[client_id] = connection
            self.connections_by_type[connection_type].add(client_id)

            logger.info(
                "WebSocket连接已建立: %s (类型: %s)", client_id, connection_type
            )

            return connection

    async def disconnect(self, client_id: str) -> None:
        """断开WebSocket连接."""
        async with self._lock:
            if client_id not in self.connections:
                return

            connection = self.connections[client_id]

            # 取消所有订阅
            for topic in list(connection.subscriptions):
                self.topic_subscribers[topic].discard(client_id)
                if not self.topic_subscribers[topic]:
                    del self.topic_subscribers[topic]

            # 从类型索引中移除
            self.connections_by_type[connection.connection_type].discard(client_id)

            # 移除连接
            del self.connections[client_id]

            logger.info("WebSocket连接已断开: %s", client_id)

    async def send_to_client(self, client_id: str, message: dict) -> bool:
        """向指定客户端发送消息."""
        async with self._lock:
            connection = self.connections.get(client_id)
            if not connection:
                logger.warning("客户端不存在: %s", client_id)
                return False

            return await connection.send_json(message)

    async def send_to_type(self, connection_type: str, message: dict) -> int:
        """向指定类型的所有连接发送消息."""
        async with self._lock:
            client_ids = list(self.connections_by_type[connection_type])

        sent_count = 0
        for client_id in client_ids:
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    async def broadcast(self, message: dict) -> int:
        """向所有连接广播消息."""
        async with self._lock:
            client_ids = list(self.connections.keys())

        sent_count = 0
        for client_id in client_ids:
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    async def broadcast_to_topic(self, topic: str, message: dict) -> int:
        """向订阅了指定主题的所有连接广播消息."""
        async with self._lock:
            subscriber_ids = list(self.topic_subscribers[topic])

        sent_count = 0
        for client_id in subscriber_ids:
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    def subscribe_to_topic(self, client_id: str, topic: str) -> bool:
        """订阅主题."""
        connection = self.connections.get(client_id)
        if not connection:
            logger.warning("客户端不存在: %s", client_id)
            return False

        connection.subscribe(topic)
        self.topic_subscribers[topic].add(client_id)
        return True

    def unsubscribe_from_topic(self, client_id: str, topic: str) -> bool:
        """取消订阅主题."""
        connection = self.connections.get(client_id)
        if not connection:
            logger.warning("客户端不存在: %s", client_id)
            return False

        connection.unsubscribe(topic)
        self.topic_subscribers[topic].discard(client_id)

        # 如果没有订阅者了，删除主题
        if not self.topic_subscribers[topic]:
            del self.topic_subscribers[topic]

        return True

    def get_connection_info(self, client_id: str) -> Optional[dict]:
        """获取连接信息."""
        connection = self.connections.get(client_id)
        if not connection:
            return None

        return {
            "client_id": connection.client_id,
            "connection_type": connection.connection_type,
            "connected_at": connection.connected_at,
            "last_activity": connection.last_activity,
            "subscriptions": list(connection.subscriptions),
        }

    def get_statistics(self) -> dict:
        """获取连接统计信息."""
        total_connections = len(self.connections)
        connections_by_type = {
            conn_type: len(client_ids)
            for conn_type, client_ids in self.connections_by_type.items()
        }
        total_topics = len(self.topic_subscribers)

        return {
            "total_connections": total_connections,
            "connections_by_type": connections_by_type,
            "total_topics": total_topics,
            "active_topics": list(self.topic_subscribers.keys()),
        }

    async def cleanup_inactive_connections(self, timeout: float = 300.0) -> int:
        """清理不活跃的连接."""
        current_time = asyncio.get_event_loop().time()
        inactive_clients = []

        async with self._lock:
            for client_id, connection in self.connections.items():
                if current_time - connection.last_activity > timeout:
                    inactive_clients.append(client_id)

        # 断开不活跃的连接
        for client_id in inactive_clients:
            await self.disconnect(client_id)
            logger.info("清理不活跃连接: %s", client_id)

        return len(inactive_clients)


# 全局WebSocket管理器实例
_websocket_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    """获取WebSocket管理器实例."""
    return _websocket_manager


# 导出公共接口
__all__ = ["WebSocketConnection", "WebSocketManager", "get_websocket_manager"]
