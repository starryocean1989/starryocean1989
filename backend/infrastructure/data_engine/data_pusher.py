# -*- coding: utf-8 -*-
"""
数据推送模块.

提供事件引擎,事件类和Tick数据类的定义,用于处理数据推送相关功能.
"""

from typing import Any, Dict, Union


class EventEngine:
    """事件引擎接口."""

    def put(self, event: "Event") -> None:  # noqa: U100
        """推送事件."""
        raise NotImplementedError("Subclasses must implement put method")


class Event:
    """事件类."""

    def __init__(
        self,
        event_type: str,
        data: Union[Dict[str, Any], str, int, float, None],
    ) -> None:
        """初始化事件对象."""
        self.event_type = event_type
        self.data = data


class TickData:
    """Tick数据类."""

    def __init__(
        self,
        symbol: str,
        vt_symbol: str,
        last_price: float,
        volume: int,
        datetime: str,
    ) -> None:
        """初始化Tick数据对象."""
        self.symbol = symbol
        self.vt_symbol = vt_symbol
        self.last_price = last_price
        self.volume = volume
        self.datetime = datetime

    @staticmethod
    def from_quote(quote: Any) -> "TickData":
        """从quote对象创建TickData实例."""
        vt_symbol = f"{quote.symbol}.PYDE"
        return TickData(
            symbol=quote.symbol,
            vt_symbol=vt_symbol,
            last_price=quote.price,
            volume=quote.volume,
            datetime=quote.timestamp,
        )
