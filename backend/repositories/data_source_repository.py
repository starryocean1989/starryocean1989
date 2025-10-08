# -*- coding: utf-8 -*-
"""
数据源Repository.

提供数据源配置的数据库操作。
"""

import logging
from typing import List, Optional

from backend.repositories.base_repository import InMemoryRepository
from backend.core.models import DataSourceConfig

logger = logging.getLogger(__name__)


class DataSourceRepository(InMemoryRepository[DataSourceConfig]):
    """数据源Repository."""

    def __init__(self):
        """初始化数据源Repository."""
        super().__init__("data_sources")
        logger.info("数据源Repository初始化完成")

    async def get_by_name(self, name: str) -> Optional[DataSourceConfig]:
        """根据名称获取数据源."""
        try:
            for source in self._data.values():
                if source.name == name:
                    return source
            return None
        except Exception as e:
            logger.error("根据名称获取数据源失败: %s", e)
            raise

    async def get_by_type(self, source_type: str) -> List[DataSourceConfig]:
        """根据类型获取数据源列表."""
        try:
            sources = [s for s in self._data.values() if s.source_type == source_type]
            logger.info("根据类型获取数据源: %s, 数量: %d", source_type, len(sources))
            return sources
        except Exception as e:
            logger.error("根据类型获取数据源失败: %s", e)
            raise


__all__ = ["DataSourceRepository"]
