# -*- coding: utf-8 -*-
"""
基础仓库类.

提供数据库操作的基础功能和接口定义。
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """基础仓库类."""

    def __init__(self, table_name: str):
        """初始化基础仓库."""
        self.table_name = table_name
        self.logger = logging.getLogger(f"{__name__}.{table_name}")

    @abstractmethod
    async def create(self, entity: T) -> T:  # noqa: U100
        """创建实体."""
        pass

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[T]:  # noqa: U100
        """根据ID获取实体."""
        pass

    @abstractmethod
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:  # noqa: U100
        """获取所有实体."""
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:  # noqa: U100
        """更新实体."""
        pass

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:  # noqa: U100
        """删除实体."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """获取实体总数."""
        pass

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:  # noqa: U100
        """检查实体是否存在."""
        pass

    def _log_operation(self, operation: str, **kwargs) -> None:
        """记录操作日志."""
        self.logger.info(
            "数据库操作: %s - %s",
            operation,
            ", ".join(f"{k}={v}" for k, v in kwargs.items()),
        )

    def _log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """记录错误日志."""
        self.logger.error(
            "数据库操作错误: %s - %s - %s",
            operation,
            str(error),
            ", ".join(f"{k}={v}" for k, v in kwargs.items()),
        )


class InMemoryRepository(BaseRepository[T]):
    """内存仓库实现."""

    def __init__(self, table_name: str):
        """初始化内存仓库."""
        super().__init__(table_name)
        self._data: Dict[str, T] = {}
        self._id_counter = 0

    async def create(self, entity: T) -> T:
        """创建实体."""
        try:
            self._log_operation("create", table=self.table_name)

            # 生成ID
            entity_id = str(self._id_counter + 1)
            self._id_counter += 1

            # 设置ID和创建时间
            if hasattr(entity, "id"):
                entity.id = entity_id  # type: ignore
            if hasattr(entity, "created_at"):
                entity.created_at = datetime.now()  # type: ignore
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now()  # type: ignore

            # 保存到内存
            self._data[entity_id] = entity

            self.logger.info("实体创建成功: id=%s", entity_id)
            return entity

        except Exception as e:
            self._log_error("create", e, table=self.table_name)
            raise

    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """根据ID获取实体."""
        try:
            entity = self._data.get(entity_id)
            if entity:
                self._log_operation("get_by_id", table=self.table_name, id=entity_id)
            else:
                self.logger.warning("实体不存在: id=%s", entity_id)
            return entity

        except Exception as e:
            self._log_error("get_by_id", e, table=self.table_name, id=entity_id)
            raise

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """获取所有实体."""
        try:
            entities = list(self._data.values())[offset : offset + limit]
            self._log_operation(
                "get_all",
                table=self.table_name,
                limit=limit,
                offset=offset,
                count=len(entities),
            )
            return entities

        except Exception as e:
            self._log_error(
                "get_all", e, table=self.table_name, limit=limit, offset=offset
            )
            raise

    async def update(self, entity: T) -> T:
        """更新实体."""
        try:
            # 获取实体ID
            entity_id = None
            if hasattr(entity, "id"):
                entity_id = entity.id  # type: ignore
            elif hasattr(entity, "task_id"):
                entity_id = entity.task_id  # type: ignore
            elif hasattr(entity, "source_id"):
                entity_id = entity.source_id  # type: ignore

            if not entity_id:
                raise ValueError("实体缺少ID字段")

            # 检查实体是否存在
            if entity_id not in self._data:
                raise ValueError(f"实体不存在: id={entity_id}")

            # 更新更新时间
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now()  # type: ignore

            # 更新实体
            self._data[entity_id] = entity

            self._log_operation("update", table=self.table_name, id=entity_id)
            self.logger.info("实体更新成功: id=%s", entity_id)
            return entity

        except Exception as e:
            self._log_error("update", e, table=self.table_name)
            raise

    async def delete(self, entity_id: str) -> bool:
        """删除实体."""
        try:
            if entity_id not in self._data:
                self.logger.warning("实体不存在: id=%s", entity_id)
                return False

            del self._data[entity_id]
            self._log_operation("delete", table=self.table_name, id=entity_id)
            self.logger.info("实体删除成功: id=%s", entity_id)
            return True

        except Exception as e:
            self._log_error("delete", e, table=self.table_name, id=entity_id)
            raise

    async def count(self) -> int:
        """获取实体总数."""
        try:
            count = len(self._data)
            self._log_operation("count", table=self.table_name, count=count)
            return count

        except Exception as e:
            self._log_error("count", e, table=self.table_name)
            raise

    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在."""
        try:
            exists = entity_id in self._data
            self._log_operation(
                "exists", table=self.table_name, id=entity_id, exists=exists
            )
            return exists

        except Exception as e:
            self._log_error("exists", e, table=self.table_name, id=entity_id)
            raise

    async def search(
        self, filters: Dict[str, Any], limit: int = 100, offset: int = 0
    ) -> List[T]:
        """搜索实体."""
        try:
            filtered_entities = []

            for entity in self._data.values():
                match = True
                for key, value in filters.items():
                    if hasattr(entity, key):
                        entity_value = getattr(entity, key)
                        if entity_value != value:
                            match = False
                            break
                    else:
                        match = False
                        break

                if match:
                    filtered_entities.append(entity)

            # 分页
            result = filtered_entities[offset : offset + limit]
            self._log_operation(
                "search", table=self.table_name, filters=filters, count=len(result)
            )
            return result

        except Exception as e:
            self._log_error("search", e, table=self.table_name, filters=filters)
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取仓库统计信息."""
        try:
            return {
                "table_name": self.table_name,
                "total_entities": len(self._data),
                "id_counter": self._id_counter,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取仓库统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["BaseRepository", "InMemoryRepository"]
