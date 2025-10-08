# -*- coding: utf-8 -*-
"""
实时数据服务.

提供实时市场数据推送和订阅管理功能。
"""

import logging
import asyncio
from contextlib import suppress
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from datetime import datetime

from backend.services.base_service import BaseService

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class RealtimeService(BaseService):
    """实时数据服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化实时数据服务."""
        super().__init__("RealtimeService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._subscriptions: Dict[str, Set[str]] = {}  # client_id -> symbols
        self._broadcast_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self) -> None:
        """初始化实时数据服务."""
        try:
            self.logger.info("正在初始化实时数据服务...")

            # 注册事件处理器
            self.event_service.register_handler("tick_data_updated", self._handle_tick_data_updated)
            self.event_service.register_handler("bar_data_updated", self._handle_bar_data_updated)

            # 启动广播任务
            self._running = True
            self._broadcast_task = asyncio.create_task(self._broadcast_realtime_data())

            self.logger.info("实时数据服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("实时数据服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭实时数据服务."""
        try:
            self.logger.info("正在关闭实时数据服务...")

            # 停止广播任务
            self._running = False
            if self._broadcast_task:
                self._broadcast_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._broadcast_task

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "tick_data_updated", self._handle_tick_data_updated
            )
            self.event_service.unregister_handler("bar_data_updated", self._handle_bar_data_updated)

            # 清理订阅
            self._subscriptions.clear()

            self.logger.info("实时数据服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("实时数据服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查实时数据服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "is_running": self._running,
                "active_subscriptions": len(self._subscriptions),
                "total_symbols": sum(len(symbols) for symbols in self._subscriptions.values()),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("实时数据服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def subscribe_symbol(self, client_id: str, symbol: str, exchange: str) -> bool:
        """订阅品种实时数据."""
        try:
            full_symbol = f"{symbol}.{exchange}"

            if client_id not in self._subscriptions:
                self._subscriptions[client_id] = set()

            self._subscriptions[client_id].add(full_symbol)

            self.logger.info("客户端 %s 订阅品种: %s", client_id, full_symbol)

            # 发送订阅确认事件
            await self.event_service.emit_event(
                "symbol_subscribed",
                {
                    "client_id": client_id,
                    "symbol": full_symbol,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            return True

        except Exception as e:
            self.logger.error("订阅品种失败: %s", e)
            return False

    async def unsubscribe_symbol(self, client_id: str, symbol: str, exchange: str) -> bool:
        """取消订阅品种实时数据."""
        try:
            full_symbol = f"{symbol}.{exchange}"

            if client_id in self._subscriptions:
                self._subscriptions[client_id].discard(full_symbol)

                # 如果客户端没有其他订阅，删除客户端
                if not self._subscriptions[client_id]:
                    del self._subscriptions[client_id]

            self.logger.info("客户端 %s 取消订阅品种: %s", client_id, full_symbol)

            # 发送取消订阅确认事件
            await self.event_service.emit_event(
                "symbol_unsubscribed",
                {
                    "client_id": client_id,
                    "symbol": full_symbol,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            return True

        except Exception as e:
            self.logger.error("取消订阅品种失败: %s", e)
            return False

    async def unsubscribe_client(self, client_id: str) -> bool:
        """取消客户端所有订阅."""
        try:
            if client_id in self._subscriptions:
                symbols = list(self._subscriptions[client_id])
                del self._subscriptions[client_id]

                self.logger.info("客户端 %s 取消所有订阅: %d 个品种", client_id, len(symbols))

                # 发送取消订阅事件
                for symbol in symbols:
                    await self.event_service.emit_event(
                        "symbol_unsubscribed",
                        {
                            "client_id": client_id,
                            "symbol": symbol,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

            return True

        except Exception as e:
            self.logger.error("取消客户端订阅失败: %s", e)
            return False

    async def get_client_subscriptions(self, client_id: str) -> List[str]:
        """获取客户端订阅的品种列表."""
        try:
            if client_id in self._subscriptions:
                return list(self._subscriptions[client_id])
            return []

        except Exception as e:
            self.logger.error("获取客户端订阅失败: %s", e)
            return []

    async def get_all_subscriptions(self) -> Dict[str, List[str]]:
        """获取所有订阅信息."""
        try:
            return {client_id: list(symbols) for client_id, symbols in self._subscriptions.items()}

        except Exception as e:
            self.logger.error("获取所有订阅信息失败: %s", e)
            return {}

    async def get_subscribed_symbols(self) -> Set[str]:
        """获取所有被订阅的品种."""
        try:
            all_symbols = set()
            for symbols in self._subscriptions.values():
                all_symbols.update(symbols)
            return all_symbols

        except Exception as e:
            self.logger.error("获取被订阅品种失败: %s", e)
            return set()

    async def get_tick_data(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """获取实时Tick数据."""
        try:
            tick_data = self.vnpy_service.get_latest_tick(symbol, exchange)

            if not tick_data:
                return None

            return {
                "symbol": tick_data.symbol,
                "exchange": tick_data.exchange,
                "datetime": tick_data.datetime.isoformat(),
                "timestamp": int(tick_data.datetime.timestamp() * 1000),
                "last_price": float(tick_data.last_price),
                "volume": int(tick_data.volume),
                "turnover": float(tick_data.turnover),
                "open_interest": int(tick_data.open_interest),
                "bid_price_1": (
                    float(tick_data.bid_price_1) if tick_data.bid_price_1 > 0 else None
                ),
                "bid_volume_1": (int(tick_data.bid_volume_1) if tick_data.bid_volume_1 > 0 else 0),
                "ask_price_1": (
                    float(tick_data.ask_price_1) if tick_data.ask_price_1 > 0 else None
                ),
                "ask_volume_1": (int(tick_data.ask_volume_1) if tick_data.ask_volume_1 > 0 else 0),
            }

        except Exception as e:
            self.logger.error("获取实时Tick数据失败: %s", e)
            return None

    async def get_bar_data(
        self, symbol: str, exchange: str, frequency: str = "1m"
    ) -> Optional[Dict[str, Any]]:
        """获取实时K线数据."""
        try:
            bar_data = self.vnpy_service.get_latest_bar(symbol, exchange, frequency)

            if not bar_data:
                return None

            return {
                "symbol": bar_data.symbol,
                "exchange": bar_data.exchange,
                "datetime": bar_data.datetime.isoformat(),
                "timestamp": int(bar_data.datetime.timestamp() * 1000),
                "open": float(bar_data.open_price),
                "high": float(bar_data.high_price),
                "low": float(bar_data.low_price),
                "close": float(bar_data.close_price),
                "volume": int(bar_data.volume),
                "turnover": float(bar_data.turnover),
                "open_interest": int(bar_data.open_interest),
                "frequency": frequency,
            }

        except Exception as e:
            self.logger.error("获取实时K线数据失败: %s", e)
            return None

    async def _broadcast_realtime_data(self) -> None:
        """广播实时数据任务."""
        try:
            while self._running:
                if not self._subscriptions:
                    await asyncio.sleep(1)
                    continue

                # 获取所有被订阅的品种
                subscribed_symbols = await self.get_subscribed_symbols()

                if not subscribed_symbols:
                    await asyncio.sleep(1)
                    continue

                # 为每个被订阅的品种获取最新数据
                for full_symbol in subscribed_symbols:
                    try:
                        symbol, exchange = full_symbol.split(".", 1)

                        # 获取Tick数据
                        tick_data = await self.get_tick_data(symbol, exchange)
                        if tick_data:
                            await self.event_service.emit_event(
                                "realtime_tick_broadcast",
                                {
                                    "symbol": full_symbol,
                                    "data": tick_data,
                                    "timestamp": datetime.now().isoformat(),
                                },
                            )

                        # 获取K线数据
                        bar_data = await self.get_bar_data(symbol, exchange)
                        if bar_data:
                            await self.event_service.emit_event(
                                "realtime_bar_broadcast",
                                {
                                    "symbol": full_symbol,
                                    "data": bar_data,
                                    "timestamp": datetime.now().isoformat(),
                                },
                            )

                    except Exception as e:
                        self.logger.error("广播品种数据失败: %s, %s", full_symbol, e)

                # 等待下次广播
                await asyncio.sleep(0.5)  # 每500ms广播一次

        except asyncio.CancelledError:
            self.logger.info("实时数据广播任务已取消")
        except Exception as e:
            self.logger.error("实时数据广播任务异常: %s", e)

    async def _handle_tick_data_updated(self, event: Dict[str, Any]) -> None:
        """处理Tick数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")

            if symbol and exchange:
                full_symbol = f"{symbol}.{exchange}"

                # 查找订阅该品种的客户端
                subscribers = []
                for client_id, symbols in self._subscriptions.items():
                    if full_symbol in symbols:
                        subscribers.append(client_id)

                if subscribers:
                    # 发送实时数据给订阅者
                    await self.event_service.emit_event(
                        "realtime_tick_update",
                        {
                            "symbol": full_symbol,
                            "data": data,
                            "subscribers": subscribers,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

        except Exception as e:
            self.logger.error("处理Tick数据更新事件失败: %s", e)

    async def _handle_bar_data_updated(self, event: Dict[str, Any]) -> None:
        """处理K线数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")

            if symbol and exchange:
                full_symbol = f"{symbol}.{exchange}"

                # 查找订阅该品种的客户端
                subscribers = []
                for client_id, symbols in self._subscriptions.items():
                    if full_symbol in symbols:
                        subscribers.append(client_id)

                if subscribers:
                    # 发送实时数据给订阅者
                    await self.event_service.emit_event(
                        "realtime_bar_update",
                        {
                            "symbol": full_symbol,
                            "data": data,
                            "subscribers": subscribers,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

        except Exception as e:
            self.logger.error("处理K线数据更新事件失败: %s", e)

    def get_subscription_statistics(self) -> Dict[str, Any]:
        """获取订阅统计信息."""
        try:
            total_clients = len(self._subscriptions)
            total_symbols = sum(len(symbols) for symbols in self._subscriptions.values())
            # 收集所有唯一品种
            all_symbols = set()
            for symbols in self._subscriptions.values():
                all_symbols.update(symbols)
            unique_symbols = len(all_symbols)

            return {
                "total_clients": total_clients,
                "total_subscriptions": total_symbols,
                "unique_symbols": unique_symbols,
                "clients": list(self._subscriptions.keys()),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取订阅统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["RealtimeService"]
