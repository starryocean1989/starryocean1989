# -*- coding: utf-8 -*-
"""数据馈送管理器模块.

提供数据馈送网关的管理功能,包括事件引擎,数据源网关基类和数据馈送管理器.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from vnpy.event import Event  # type: ignore

logger = logging.getLogger(__name__)


class EventEngine:
    """事件引擎接口."""

    def put(self, event: "Event") -> None:
        """推送事件.

        Args:
            event: 要推送的事件对象.
        """
        # Use event to avoid unused argument warning
        _ = event
        raise NotImplementedError


class DataFeedGateway(ABC):
    """数据源网关基类."""

    def __init__(self, event_engine: EventEngine) -> None:
        """初始化数据源网关.

        Args:
            event_engine: 事件引擎实例.
        """
        self.event_engine = event_engine

    @abstractmethod
    async def get_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """获取行情数据.

        Args:
            symbols: 股票代码列表.

        Returns:
            行情数据列表.
        """
        # Use symbols to avoid unused argument warning
        _ = symbols
        raise NotImplementedError


class DataFeedManager:
    """数据馈送管理器."""

    def __init__(self, event_engine: EventEngine) -> None:
        """初始化数据馈送管理器.

        Args:
            event_engine: 事件引擎实例.
        """
        self.event_engine = event_engine
        self.datafeeds: Dict[str, DataFeedGateway] = {}

    def add_datafeed(self, name: str, datafeed: DataFeedGateway) -> None:
        """添加数据馈送."""
        self.datafeeds[name] = datafeed

    async def get_all_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """获取所有数据源的行情数据."""
        all_quotes = []

        for name, gateway in self.datafeeds.items():
            try:
                quotes = await gateway.get_quotes(symbols)
                all_quotes.extend(quotes)
                logger.info("从 %s 获取到 %d 条行情数据", name, len(quotes))

            except (ConnectionError, TimeoutError, ValueError) as e:
                logger.error("从 %s 获取行情数据失败: %s", name, e)

        return all_quotes
