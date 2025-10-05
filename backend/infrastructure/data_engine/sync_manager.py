# -*- coding: utf-8 -*-

import asyncio
import logging
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DataPersistenceService(ABC):

    """数据持久化服务接口"""

    @abstractmethod
    async def save_data(self, data: Dict[str, Any], source: str) -> bool:
        """保存数据"""
        pass

    @abstractmethod
    async def load_data(
        self, source: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """加载数据"""
        pass


class SyncManager:

    """数据同步管理器"""

    def __init__(self, persistence_service: DataPersistenceService):
        self.persistence_service = persistence_service
        self.logger = logging.getLogger(__name__)
        self.sync_tasks: Dict[str, asyncio.Task[None]] = {}

    async def start_sync(self, source: str, interval: int = 60) -> None:
        """启动数据同步"""
        if source in self.sync_tasks:
            self.logger.warning(f"同步任务 {source} 已经在运行中")
            return

        task = asyncio.create_task(self._sync_loop(source, interval))
        self.sync_tasks[source] = task
        self.logger.info(f"启动数据同步: {source}, 间隔: {interval}秒")

    async def stop_sync(self, source: str) -> None:
        """停止数据同步"""
        if source not in self.sync_tasks:
            self.logger.warning(f"同步任务 {source} 未找到")
            return

        task = self.sync_tasks[source]
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        del self.sync_tasks[source]
        self.logger.info(f"停止数据同步: {source}")

    async def _sync_loop(self, source: str, interval: int) -> None:
        """同步循环"""
        while True:
            try:
                # 这里应该从数据源获取数据并保存
                # 暂时留空,等待具体的实现
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"同步 {source} 时出错: {e}")
                await asyncio.sleep(interval)

    async def sync_now(self, source: str, data: Dict[str, Any]) -> bool:
        """立即同步数据"""
        try:
            success = await self.persistence_service.save_data(data, source)
            if success:
                self.logger.info(f"成功同步数据到 {source}")
            else:
                self.logger.error(f"同步数据到 {source} 失败")
            return success

        except Exception as e:
            self.logger.error(f"同步数据到 {source} 时出错: {e}")
            return False

    async def get_synced_data(
        self, source: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """获取已同步的数据"""
        try:
            data = await self.persistence_service.load_data(source, filters)
            self.logger.info(f"从 {source} 加载了 {len(data)} 条数据")
            return data

        except Exception as e:
            self.logger.error(f"从 {source} 加载数据时出错: {e}")
            return []
