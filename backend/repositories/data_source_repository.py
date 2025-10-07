# -*- coding: utf-8 -*-
"""
数据源仓库.

提供数据源配置的数据库操作功能。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from .base_repository import InMemoryRepository

if TYPE_CHECKING:
    from backend.core.models import DataSourceConfig

logger = logging.getLogger(__name__)


class DataSourceRepository(InMemoryRepository["DataSourceConfig"]):
    """数据源仓库."""

    def __init__(self):
        """初始化数据源仓库."""
        super().__init__("data_sources")

    async def get_by_type(self, source_type: str) -> List["DataSourceConfig"]:
        """根据类型获取数据源列表."""
        try:
            sources = [s for s in self._data.values() if s.source_type == source_type]
            self._log_operation(
                "get_by_type", source_type=source_type, count=len(sources)
            )
            return sources

        except Exception as e:
            self._log_error("get_by_type", e, source_type=source_type)
            raise

    async def get_enabled_sources(self) -> List["DataSourceConfig"]:
        """获取启用的数据源列表."""
        try:
            sources = [s for s in self._data.values() if s.is_enabled]
            self._log_operation("get_enabled_sources", count=len(sources))
            return sources

        except Exception as e:
            self._log_error("get_enabled_sources", e)
            raise

    async def get_connected_sources(self) -> List["DataSourceConfig"]:
        """获取已连接的数据源列表."""
        try:
            sources = [s for s in self._data.values() if s.is_connected]
            self._log_operation("get_connected_sources", count=len(sources))
            return sources

        except Exception as e:
            self._log_error("get_connected_sources", e)
            raise

    async def get_by_name(self, name: str) -> Optional["DataSourceConfig"]:
        """根据名称获取数据源."""
        try:
            for source in self._data.values():
                if source.name == name:
                    self._log_operation("get_by_name", name=name)
                    return source

            self.logger.warning("数据源不存在: %s", name)
            return None

        except Exception as e:
            self._log_error("get_by_name", e, name=name)
            raise

    async def update_connection_status(
        self, source_id: str, is_connected: bool, error_count: Optional[int] = None
    ) -> Optional["DataSourceConfig"]:
        """更新连接状态."""
        try:
            source = await self.get_by_id(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return None

            # 更新连接状态
            source.is_connected = is_connected

            if is_connected:
                source.last_connected = datetime.now()
                source.error_count = 0
            else:
                if error_count is not None:
                    source.error_count = error_count
                else:
                    source.error_count += 1

            # 保存更新
            updated_source = await self.update(source)

            self._log_operation(
                "update_connection_status",
                source_id=source_id,
                is_connected=is_connected,
            )
            return updated_source

        except Exception as e:
            self._log_error(
                "update_connection_status",
                e,
                source_id=source_id,
                is_connected=is_connected,
            )
            raise

    async def update_config(
        self, source_id: str, config: Dict[str, Any]
    ) -> Optional["DataSourceConfig"]:
        """更新配置参数."""
        try:
            source = await self.get_by_id(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return None

            # 更新配置
            source.config.update(config)

            # 保存更新
            updated_source = await self.update(source)

            self._log_operation(
                "update_config", source_id=source_id, config_keys=list(config.keys())
            )
            return updated_source

        except Exception as e:
            self._log_error("update_config", e, source_id=source_id, config=config)
            raise

    async def enable_source(self, source_id: str) -> Optional["DataSourceConfig"]:
        """启用数据源."""
        try:
            source = await self.get_by_id(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return None

            # 启用数据源
            source.is_enabled = True

            # 保存更新
            updated_source = await self.update(source)

            self._log_operation("enable_source", source_id=source_id)
            return updated_source

        except Exception as e:
            self._log_error("enable_source", e, source_id=source_id)
            raise

    async def disable_source(self, source_id: str) -> Optional["DataSourceConfig"]:
        """禁用数据源."""
        try:
            source = await self.get_by_id(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return None

            # 禁用数据源
            source.is_enabled = False
            source.is_connected = False

            # 保存更新
            updated_source = await self.update(source)

            self._log_operation("disable_source", source_id=source_id)
            return updated_source

        except Exception as e:
            self._log_error("disable_source", e, source_id=source_id)
            raise

    async def get_sources_by_filter(
        self, filters: Dict[str, Any], limit: int = 100, offset: int = 0
    ) -> List["DataSourceConfig"]:
        """根据过滤条件获取数据源列表."""
        try:
            filtered_sources = []

            for source in self._data.values():
                match = True
                for key, value in filters.items():
                    if hasattr(source, key):
                        source_value = getattr(source, key)
                        if source_value != value:
                            match = False
                            break
                    else:
                        match = False
                        break

                if match:
                    filtered_sources.append(source)

            # 按创建时间倒序排序
            filtered_sources.sort(key=lambda x: x.created_at, reverse=True)

            # 分页
            result = filtered_sources[offset : offset + limit]
            self._log_operation(
                "get_sources_by_filter", filters=filters, count=len(result)
            )
            return result

        except Exception as e:
            self._log_error("get_sources_by_filter", e, filters=filters)
            raise

    async def get_source_types(self) -> List[str]:
        """获取所有数据源类型."""
        try:
            types = list(set(s.source_type for s in self._data.values()))
            types.sort()
            self._log_operation("get_source_types", count=len(types))
            return types

        except Exception as e:
            self._log_error("get_source_types", e)
            raise

    async def get_sources_with_errors(
        self, min_error_count: int = 1
    ) -> List["DataSourceConfig"]:
        """获取有错误的数据源列表."""
        try:
            sources = [
                s for s in self._data.values() if s.error_count >= min_error_count
            ]
            self._log_operation(
                "get_sources_with_errors",
                min_error_count=min_error_count,
                count=len(sources),
            )
            return sources

        except Exception as e:
            self._log_error(
                "get_sources_with_errors", e, min_error_count=min_error_count
            )
            raise

    async def reset_error_count(self, source_id: str) -> Optional["DataSourceConfig"]:
        """重置错误计数."""
        try:
            source = await self.get_by_id(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return None

            # 重置错误计数
            source.error_count = 0

            # 保存更新
            updated_source = await self.update(source)

            self._log_operation("reset_error_count", source_id=source_id)
            return updated_source

        except Exception as e:
            self._log_error("reset_error_count", e, source_id=source_id)
            raise

    async def get_source_statistics(self) -> Dict[str, Any]:
        """获取数据源统计信息."""
        try:
            total_sources = len(self._data)
            enabled_sources = len([s for s in self._data.values() if s.is_enabled])
            connected_sources = len([s for s in self._data.values() if s.is_connected])

            # 统计各类型数据源数量
            type_counts = {}
            for source in self._data.values():
                source_type = source.source_type
                if source_type not in type_counts:
                    type_counts[source_type] = 0
                type_counts[source_type] += 1

            # 统计错误情况
            sources_with_errors = len(
                [s for s in self._data.values() if s.error_count > 0]
            )
            total_errors = sum(s.error_count for s in self._data.values())

            stats = {
                "total_sources": total_sources,
                "enabled_sources": enabled_sources,
                "connected_sources": connected_sources,
                "disabled_sources": total_sources - enabled_sources,
                "disconnected_sources": total_sources - connected_sources,
                "type_counts": type_counts,
                "sources_with_errors": sources_with_errors,
                "total_errors": total_errors,
                "timestamp": datetime.now().isoformat(),
            }

            self._log_operation("get_source_statistics", stats=stats)
            return stats

        except Exception as e:
            self._log_error("get_source_statistics", e)
            raise

    async def bulk_update_status(self, source_ids: List[str], is_enabled: bool) -> int:
        """批量更新数据源状态."""
        try:
            updated_count = 0

            for source_id in source_ids:
                source = await self.get_by_id(source_id)
                if source:
                    source.is_enabled = is_enabled
                    if not is_enabled:
                        source.is_connected = False

                    await self.update(source)
                    updated_count += 1

            self._log_operation(
                "bulk_update_status",
                source_ids=len(source_ids),
                is_enabled=is_enabled,
                updated_count=updated_count,
            )
            return updated_count

        except Exception as e:
            self._log_error(
                "bulk_update_status", e, source_ids=source_ids, is_enabled=is_enabled
            )
            raise


# 导出公共接口
__all__ = ["DataSourceRepository"]
