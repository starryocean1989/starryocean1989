# -*- coding: utf-8 -*-
"""数据引擎模块 - 提供行情数据调度和推送功能"""

import asyncio
import logging
from typing import List, Set, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Quote:
    """行情数据类"""

    def __init__(self, symbol: str, price: float, volume: int, timestamp: str):
        self.symbol = symbol
        self.price = price
        self.volume = volume
        self.timestamp = timestamp


class DataScheduler(ABC):
    """数据调度器接口"""

    @abstractmethod
    async def get_data(self) -> List[Quote]:
        """获取数据"""


class DataPusher(ABC):
    """数据推送器接口"""

    @abstractmethod
    async def push_quotes(self, quotes: List[Quote]) -> None:
        """推送行情数据"""


class DataEngine:
    """数据引擎"""

    def __init__(
        self,
        scheduler: DataScheduler,
        pusher: DataPusher,
        poll_interval: int = 5,
    ):
        self.scheduler = scheduler
        self.pusher = pusher
        self.poll_interval = poll_interval
        self.running = False
        self.logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """启动引擎"""
        self.running = True
        self.logger.info("数据引擎启动")

        try:
            await self._main_loop()
        except Exception as e:
            self.logger.error("数据引擎运行出错: %s", e)
            raise  # 重新抛出异常
        finally:
            self.running = False
            self.logger.info("数据引擎停止")

    async def stop(self) -> None:
        """停止引擎"""
        self.running = False
        self.logger.info("正在停止数据引擎...")

    async def _main_loop(self) -> None:
        """主循环"""
        while self.running:
            try:
                # 获取数据
                quotes = await self.scheduler.get_data()

                if quotes:
                    # 过滤重复数据
                    filtered_quotes = self._filter_duplicates(quotes)

                    if filtered_quotes:
                        # 推送数据
                        await self.pusher.push_quotes(filtered_quotes)

                    self.logger.info(
                        "处理了 %d 条行情数据", len(filtered_quotes)
                    )

                # 等待下次轮询
                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                self.logger.error("主循环出错: %s", e)
                await asyncio.sleep(1)  # 异常时稍作等待
                raise  # 重新抛出异常

    def _filter_duplicates(self, quotes: List[Quote]) -> List[Quote]:
        """
        过滤重复的行情数据

        简化的重复过滤逻辑
        在实际实现中,可以使用更复杂的算法
        """
        seen: Set[Tuple[str, str]] = set()
        filtered = []

        for quote in quotes:
            key = (quote.symbol, quote.timestamp)
            if key not in seen:
                seen.add(key)
                filtered.append(quote)

        return filtered
