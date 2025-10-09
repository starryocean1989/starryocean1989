# -*- coding: utf-8 -*-
"""数据调度器模块 - 提供行情数据调度功能."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

from .engine import DataScheduler

if TYPE_CHECKING:
    from .models import Quote

logger = logging.getLogger(__name__)


class AbstractAdapter(ABC):
    """数据适配器接口."""

    @abstractmethod
    async def get_quotes(self) -> List["Quote"]:
        """获取行情数据."""


class Scheduler(DataScheduler):
    """数据调度器."""

    def __init__(self, adapters: List[AbstractAdapter]):
        """初始化调度器."""
        self.adapters = adapters
        self.logger = logging.getLogger(__name__)

    async def get_data(self) -> List["Quote"]:  # type: ignore
        """
        从所有适配器获取数据.

        Returns:
            List["Quote"]: 所有适配器返回的行情数据列表.
        """
        all_quotes = []

        # 并行获取所有适配器的数据
        tasks = [adapter.get_quotes() for adapter in self.adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            adapter_name = self.adapters[i].__class__.__name__

            if isinstance(result, Exception):
                self.logger.error("适配器 %s 获取数据失败: %s", adapter_name, result)
                continue

            quotes = result
            if isinstance(quotes, list) and quotes:
                all_quotes.extend(quotes)
                self.logger.debug("适配器 %s 返回了 %d 条数据", adapter_name, len(quotes))

        self.logger.info("总共获取到 %d 条行情数据", len(all_quotes))
        return all_quotes
