# -*- coding: utf-8 -*-
"""WebSocket服务器模块.

提供WebSocket连接管理和消息广播功能。

本模块包含WebSocket服务器的实现，支持：
- WebSocket连接管理
- 消息广播功能
- 心跳机制
- 客户端订阅管理
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, Set

# 初始化标志
HAS_WEBSOCKETS = False
websockets = None  # type: ignore

try:
    import websockets

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    websockets = None  # type: ignore

# 移除类型别名，使用Any避免类型检查问题
WebSocketServerProtocol = Any

logger = logging.getLogger(__name__)


class WebSocketServer:
    """WebSocket服务器.

    管理WebSocket连接，支持消息广播。
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        """初始化WebSocket服务器.

        Args:
            host: 监听地址
            port: 监听端口
        """
        self.host = host
        self.port = port

        # 连接池
        self.connections: Set[WebSocketServerProtocol] = set()

        # 服务器实例
        self.server = None

        # 运行状态
        self.running = False

        logger.info("WebSocket服务器初始化: %s:%s", host, port)

    async def handler(self, websocket: WebSocketServerProtocol) -> None:
        """处理WebSocket连接.

        Args:
            websocket: WebSocket连接
        """
        # 注册连接
        self.connections.add(websocket)
        client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info("新客户端连接: %s, 当前连接数: %d", client_info, len(self.connections))

        # 启动心跳任务
        heartbeat_task = asyncio.create_task(self._send_heartbeat(websocket))

        try:
            # 发送欢迎消息
            welcome_msg = {
                "type": "welcome",
                "message": "已连接到星辰金融终端WebSocket服务器",
                "timestamp": datetime.now().isoformat(),
                "server_version": "v0.50",
            }
            await websocket.send(json.dumps(welcome_msg))

            # 保持连接，接收客户端消息
            async for message in websocket:
                try:
                    # 解析客户端消息
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "ping":
                        # 响应ping
                        await websocket.send(
                            json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()})
                        )
                    elif msg_type == "subscribe":
                        # 处理订阅请求
                        topic = data.get("topic", "")
                        logger.info("客户端 %s 订阅: %s", client_info, topic)
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "subscribed",
                                    "topic": topic,
                                    "message": f"已订阅 {topic}",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        )
                    elif msg_type == "unsubscribe":
                        # 处理取消订阅
                        topic = data.get("topic", "")
                        logger.info("客户端 %s 取消订阅: %s", client_info, topic)
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "unsubscribed",
                                    "topic": topic,
                                    "message": f"已取消订阅 {topic}",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        )
                    else:
                        logger.debug("收到客户端消息: %s", data)

                except json.JSONDecodeError:
                    logger.warning("无效的JSON消息: %s", message)
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "无效的JSON格式",
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )

        except Exception as e:
            if (
                HAS_WEBSOCKETS
                and websockets is not None
                and hasattr(websockets, "ConnectionClosed")
                and isinstance(e, websockets.ConnectionClosed)
            ):
                logger.info("客户端断开连接: %s", client_info)
            else:
                logger.error("WebSocket处理异常: %s", e, exc_info=True)
        finally:
            # 取消心跳任务
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

            # 移除连接
            if websocket in self.connections:
                self.connections.remove(websocket)
            logger.info("客户端移除: %s, 剩余连接数: %d", client_info, len(self.connections))

    async def broadcast(self, message: Dict[str, Any]):
        """广播消息到所有连接的客户端.

        Args:
            message: 要广播的消息字典
        """
        if not self.connections:
            return

        # 序列化消息
        message_json = json.dumps(message)

        # 广播到所有连接
        disconnected = set()
        for websocket in self.connections:
            try:
                await websocket.send(message_json)
            except Exception as e:
                if (
                    HAS_WEBSOCKETS
                    and websockets is not None
                    and hasattr(websockets, "ConnectionClosed")
                    and isinstance(e, websockets.ConnectionClosed)
                ):
                    disconnected.add(websocket)
                    continue
                logger.error("发送消息失败: %s", e)
                disconnected.add(websocket)

        # 移除断开的连接
        self.connections -= disconnected

    async def start(self):
        """启动WebSocket服务器."""
        if not HAS_WEBSOCKETS:
            logger.warning("websockets库未安装，WebSocket服务器无法启动")
            return

        try:
            if not HAS_WEBSOCKETS or websockets is None:
                logger.warning("websockets库未安装，WebSocket服务器无法启动")
                return

            # 启动服务器
            if websockets is not None:
                self.server = await websockets.serve(self.handler, self.host, self.port)
                self.running = True
                logger.info("✅ WebSocket服务器已启动: ws://%s:%s", self.host, self.port)

        except Exception as e:
            logger.error("WebSocket服务器启动失败: %s", e, exc_info=True)
            self.running = False

    async def stop(self):
        """停止WebSocket服务器."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.running = False
            logger.info("WebSocket服务器已停止")

    async def _send_heartbeat(self, websocket: WebSocketServerProtocol) -> None:
        """发送心跳消息到客户端.

        Args:
            websocket: WebSocket连接
        """
        try:
            while True:
                await asyncio.sleep(30)  # 每30秒发送一次心跳
                if websocket in self.connections:
                    heartbeat_msg = {
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat(),
                        "connections": len(self.connections),
                    }
                    await websocket.send(json.dumps(heartbeat_msg))
        except asyncio.CancelledError:
            # 任务被取消，正常退出
            pass
        except Exception as e:
            logger.warning("心跳发送失败: %s", e)

    def broadcast_sync(self, message: Dict[str, Any]):
        """同步方式广播消息（用于非async上下文）.

        Args:
            message: 要广播的消息字典
        """
        if not self.running:
            return

        try:
            # 在新的事件循环中执行广播
            asyncio.run(self.broadcast(message))
        except RuntimeError:
            # 如果已经在事件循环中，使用create_task
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.broadcast(message))
                else:
                    # 创建新任务在新循环中
                    asyncio.ensure_future(self.broadcast(message))
            except Exception as e:
                logger.error("同步广播失败: %s", e)

    async def send_to_client(
        self, websocket: WebSocketServerProtocol, message: Dict[str, Any]
    ) -> None:
        """发送消息到指定客户端.

        Args:
            websocket: WebSocket连接
            message: 要发送的消息字典
        """
        if websocket not in self.connections:
            return

        try:
            message_json = json.dumps(message)
            await websocket.send(message_json)
        except Exception as e:
            if (
                HAS_WEBSOCKETS
                and websockets is not None
                and hasattr(websockets, "ConnectionClosed")
                and isinstance(e, websockets.ConnectionClosed)
            ):
                if websocket in self.connections:
                    self.connections.remove(websocket)
                return
            logger.error("发送消息失败: %s", e)

    def get_connection_count(self) -> int:
        """获取当前连接数.

        Returns:
            连接数
        """
        return len(self.connections)
