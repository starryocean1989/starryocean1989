# -*- coding: utf-8 -*-
"""数据同步管理器模块.

提供数据同步功能，包括数据持久化服务接口和同步管理器实现.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataPersistenceService(ABC):
    """数据持久化服务接口."""

    @abstractmethod
    async def save_data(self, _data: Dict[str, Any], _source: str) -> bool:  # noqa: U101
        """保存数据."""
        raise NotImplementedError

    @abstractmethod
    async def load_data(
        self, _source: str, _filters: Optional[Dict[str, Any]] = None  # noqa: U101
    ) -> List[Dict[str, Any]]:
        """加载数据."""
        raise NotImplementedError


class SyncManager:
    """数据同步管理器."""

    def __init__(self, persistence_service: DataPersistenceService):
        """初始化同步管理器.

        Args:
            persistence_service: 数据持久化服务实例.
        """
        self.persistence_service = persistence_service
        self.logger = logging.getLogger(__name__)
        self.sync_tasks: Dict[str, asyncio.Task[None]] = {}

    async def start_sync(self, source: str, interval: int = 60) -> None:
        """启动数据同步."""
        if source in self.sync_tasks:
            self.logger.warning("同步任务 %s 已经在运行中", source)
            return

        task = asyncio.create_task(self._sync_loop(source, interval))
        self.sync_tasks[source] = task
        self.logger.info("启动数据同步: %s, 间隔: %d秒", source, interval)

    async def stop_sync(self, source: str) -> None:
        """停止数据同步."""
        if source not in self.sync_tasks:
            self.logger.warning("同步任务 %s 未找到", source)
            return

        task = self.sync_tasks[source]
        task.cancel()

        with suppress(asyncio.CancelledError):
            await task

        del self.sync_tasks[source]
        self.logger.info("停止数据同步: %s", source)

    async def _sync_loop(self, source: str, interval: int) -> None:
        """同步循环."""
        while True:
            try:
                # 这里应该从数据源获取数据并保存
                # 暂时留空,等待具体的实现
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except (ConnectionError, TimeoutError, ValueError) as e:
                self.logger.error("同步 %s 时出错: %s", source, e)
                await asyncio.sleep(interval)

    async def sync_now(self, source: str, data: Dict[str, Any]) -> bool:
        """立即同步数据."""
        try:
            success = await self.persistence_service.save_data(data, source)
            if success:
                self.logger.info("成功同步数据到 %s", source)
            else:
                self.logger.error("同步数据到 %s 失败", source)
            return success

        except (ConnectionError, TimeoutError, ValueError) as e:
            self.logger.error("同步数据到 %s 时出错: %s", source, e)
            return False

    async def get_synced_data(
        self, source: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """获取已同步的数据."""
        try:
            data = await self.persistence_service.load_data(source, filters)
            self.logger.info("从 %s 加载了 %d 条数据", source, len(data))
            return data

        except (ConnectionError, TimeoutError, ValueError) as e:
            self.logger.error("从 %s 加载数据时出错: %s", source, e)
            return []
