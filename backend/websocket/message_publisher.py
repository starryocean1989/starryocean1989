# -*- coding: utf-8 -*-
"""
消息发布器.

将VnPy事件引擎的事件转换为WebSocket消息并推送给客户端。
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from vnpy.event import Event, EventEngine

logger = logging.getLogger(__name__)


class MessagePublisher:
    """消息发布器.

    连接VnPy事件引擎和WebSocket服务器，
    将事件转换为WebSocket消息并推送。
    """

    def __init__(self, event_engine: EventEngine, websocket_server: Any):
        """初始化消息发布器.

        Args:
            event_engine: VnPy事件引擎
            websocket_server: WebSocket服务器实例
        """
        self.event_engine = event_engine
        self.websocket_server = websocket_server

        # 注册事件监听
        self._register_event_handlers()

        logger.info("消息发布器已初始化")

    def _register_event_handlers(self):
        """注册事件处理器."""
        from vnpy.trader.event import (
            EVENT_TICK,
            EVENT_ORDER,
            EVENT_TRADE,
            EVENT_POSITION,
            EVENT_ACCOUNT,
            EVENT_LOG,
        )

        # 注册行情事件
        self.event_engine.register(EVENT_TICK, self._on_tick)

        # 注册交易事件
        self.event_engine.register(EVENT_ORDER, self._on_order)
        self.event_engine.register(EVENT_TRADE, self._on_trade)
        self.event_engine.register(EVENT_POSITION, self._on_position)
        self.event_engine.register(EVENT_ACCOUNT, self._on_account)

        # 注册日志事件
        self.event_engine.register(EVENT_LOG, self._on_log)

        logger.info("已注册VnPy事件监听器")

    def _on_tick(self, event: Event):
        """处理Tick行情事件.

        Args:
            event: VnPy事件对象
        """
        tick = event.data
        message = {
            "type": "tick",
            "data": {
                "symbol": tick.symbol,
                "exchange": tick.exchange.value,
                "last_price": tick.last_price,
                "volume": tick.volume,
                "datetime": tick.datetime.isoformat() if tick.datetime else None,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    def _on_order(self, event: Event):
        """处理委托事件.

        Args:
            event: VnPy事件对象
        """
        order = event.data
        message = {
            "type": "order",
            "data": {
                "orderid": order.orderid,
                "symbol": order.symbol,
                "direction": order.direction.value,
                "offset": order.offset.value,
                "price": order.price,
                "volume": order.volume,
                "traded": order.traded,
                "status": order.status.value,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    def _on_trade(self, event: Event):
        """处理成交事件.

        Args:
            event: VnPy事件对象
        """
        trade = event.data
        message = {
            "type": "trade",
            "data": {
                "tradeid": trade.tradeid,
                "symbol": trade.symbol,
                "direction": trade.direction.value,
                "offset": trade.offset.value,
                "price": trade.price,
                "volume": trade.volume,
                "datetime": trade.datetime.isoformat() if trade.datetime else None,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    def _on_position(self, event: Event):
        """处理持仓事件.

        Args:
            event: VnPy事件对象
        """
        position = event.data
        message = {
            "type": "position",
            "data": {
                "symbol": position.symbol,
                "direction": position.direction.value,
                "volume": position.volume,
                "frozen": position.frozen,
                "price": position.price,
                "pnl": position.pnl,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    def _on_account(self, event: Event):
        """处理资金事件.

        Args:
            event: VnPy事件对象
        """
        account = event.data
        message = {
            "type": "account",
            "data": {
                "accountid": account.accountid,
                "balance": account.balance,
                "frozen": account.frozen,
                "available": account.available,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    def _on_log(self, event: Event):
        """处理日志事件.

        Args:
            event: VnPy事件对象
        """
        log = event.data
        message = {
            "type": "log",
            "data": {
                "msg": log.msg,
                "level": log.level,
                "gateway_name": log.gateway_name,
            },
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    def _broadcast(self, message: Dict[str, Any]):
        """广播消息.

        Args:
            message: 消息字典
        """
        try:
            if self.websocket_server and self.websocket_server.running:
                self.websocket_server.broadcast_sync(message)
        except Exception as e:
            logger.error("广播消息失败: %s", e)

    def publish_custom_message(self, msg_type: str, data: Dict[str, Any]):
        """发布自定义消息.

        Args:
            msg_type: 消息类型
            data: 消息数据
        """
        message = {
            "type": msg_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        self._broadcast(message)

    # ==================== 下载进度推送（链条2.2.2） ====================

    def publish_download_started(self, task_id: str, task_info: Dict[str, Any]):
        """推送下载任务开始事件.

        Args:
            task_id: 任务ID
            task_info: 任务信息
        """
        self.publish_custom_message(
            "download.started",
            {
                "task_id": task_id,
                "task_type": task_info.get("type", "unknown"),
                "total_symbols": task_info.get("total_symbols", 0),
                "start_time": datetime.now().isoformat(),
            },
        )

    def publish_download_progress(
        self,
        task_id: str,
        progress: int,
        current_symbol: Optional[str] = None,
        completed_symbols: int = 0,
        total_symbols: int = 0,
    ):
        """推送下载进度更新事件.

        Args:
            task_id: 任务ID
            progress: 进度百分比（0-100）
            current_symbol: 当前下载的品种
            completed_symbols: 已完成品种数
            total_symbols: 总品种数
        """
        self.publish_custom_message(
            "download.progress",
            {
                "task_id": task_id,
                "progress": progress,
                "current_symbol": current_symbol,
                "completed_symbols": completed_symbols,
                "total_symbols": total_symbols,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def publish_download_completed(self, task_id: str, result: Dict[str, Any]):
        """推送下载任务完成事件.

        Args:
            task_id: 任务ID
            result: 任务结果
        """
        self.publish_custom_message(
            "download.completed",
            {
                "task_id": task_id,
                "success": result.get("success", False),
                "completed_symbols": result.get("completed_symbols", 0),
                "failed_symbols": result.get("failed_symbols", 0),
                "duration_seconds": result.get("duration", 0),
                "end_time": datetime.now().isoformat(),
            },
        )

    def publish_download_failed(self, task_id: str, error_message: str):
        """推送下载任务失败事件.

        Args:
            task_id: 任务ID
            error_message: 错误信息
        """
        self.publish_custom_message(
            "download.failed",
            {
                "task_id": task_id,
                "error": error_message,
                "timestamp": datetime.now().isoformat(),
            },
        )
