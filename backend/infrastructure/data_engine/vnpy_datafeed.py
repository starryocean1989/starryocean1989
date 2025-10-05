# -*- coding: utf-8 -*-
"""VnPy数据馈送模块 - 通过vnpy主包统一接入数据引擎"""

import logging
from typing import Any, List, Dict

from vnpy.trader.gateway import BaseGateway

# 通过vnpy主包统一导入
from ..data_module_vnpy.core_adapter import (
    vnpy_adapter,
    Exchange,
    SubscribeRequest, OrderRequest, CancelRequest
)

logger = logging.getLogger(__name__)

EVENT_TICK = "eTick."

__all__ = ["VnpyDataPusher", "EngineDatafeed"]


class VnpyDataPusher:
    """VnPy数据推送器 - 通过vnpy主包统一接入"""

    def __init__(self):
        # 使用全局适配器
        if not vnpy_adapter.is_initialized():
            vnpy_adapter.initialize()
        self.event_engine = vnpy_adapter.get_event_engine()

    async def push_quotes(self, quotes: List[Dict[str, Any]]) -> None:
        """推送行情数据到VnPy事件引擎"""
        if not self.event_engine:
            logger.error("VnPy事件引擎未初始化")
            return

        for quote in quotes:
            try:
                # 通过适配器创建TickData对象
                tick = vnpy_adapter.create_tick_data(
                    gateway_name="data_engine",
                    symbol=quote.get("symbol", ""),
                    exchange=Exchange.SSE,  # 默认上交所,可以根据需要调整
                    datetime=quote.get("datetime", ""),
                    name=quote.get("name", ""),
                    last_price=quote.get("last_price", 0.0),
                    volume=quote.get("volume", 0),
                    open_price=quote.get("open_price", 0.0),
                    high_price=quote.get("high_price", 0.0),
                    low_price=quote.get("low_price", 0.0),
                    prev_close=quote.get("prev_close", 0.0),
                )
                # 通过适配器创建并推送事件
                event = vnpy_adapter.create_event(EVENT_TICK + quote.get("symbol", ""), tick)
                vnpy_adapter.put_event(event)
                logger.debug("推送行情数据: %s", quote.get('symbol'))
            except (ValueError, KeyError, TypeError) as e:
                logger.error("推送行情数据失败: %s", e)


class EngineDatafeed(BaseGateway):
    """引擎数据馈送网关 - 通过vnpy主包统一接入"""

    def __init__(self, gateway_name: str = "data_engine"):
        # 使用全局适配器的事件引擎
        if not vnpy_adapter.is_initialized():
            vnpy_adapter.initialize()
        event_engine = vnpy_adapter.get_event_engine()
        super().__init__(event_engine, gateway_name)
        self.logger = logging.getLogger(__name__)

    def connect(self, setting: Dict[str, Any]) -> None:
        """连接网关"""
        self.logger.info("连接数据引擎网关")

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.logger.info("订阅行情: %s", req.symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送委托"""
        self.logger.warning("数据引擎网关不支持发送委托")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销委托"""
        self.logger.warning("数据引擎网关不支持撤销委托")

    def query_account(self) -> None:
        """查询账户"""
        self.logger.warning("数据引擎网关不支持查询账户")

    def query_position(self) -> None:
        """查询持仓"""
        self.logger.warning("数据引擎网关不支持查询持仓")

    def close(self) -> None:
        """关闭连接"""
        self.logger.info("关闭数据引擎网关连接")
