# -*- coding: utf-8 -*-
"""
策略文件Repository.

提供策略文件的数据库操作。
"""

import logging
from typing import List, Optional

from backend.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class StrategyRepository(BaseRepository):
    """策略文件Repository."""

    def __init__(self):
        """初始化."""
        super().__init__("strategies")
        logger.info("策略Repository初始化完成")

    async def create_strategy(self, strategy_data: dict) -> dict:
        """
        创建策略记录.

        Args:
            strategy_data: 策略数据，包含id, name, path, type, content等

        Returns:
            dict: 创建的策略数据
        """
        from backend.core.database import get_db_manager
        from datetime import datetime

        try:
            db = get_db_manager()
            query = """
                INSERT INTO strategy_files (
                    id, name, path, type, content, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            now = datetime.now().isoformat()
            params = (
                strategy_data["id"],
                strategy_data["name"],
                strategy_data["path"],
                strategy_data["type"],
                strategy_data.get("content", ""),
                now,
                now,
            )
            db.execute_update(query, params)
            logger.info(f"创建策略文件记录: {strategy_data['id']}")
            return strategy_data
        except Exception as e:
            logger.error(f"创建策略文件记录失败: {e}")
            raise

    async def get_strategy(self, file_id: str) -> Optional[dict]:
        """
        获取策略记录.

        Args:
            file_id: 文件ID

        Returns:
            Optional[dict]: 策略数据，不存在返回None
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            query = "SELECT * FROM strategy_files WHERE id = ?"
            results = db.execute_query(query, (file_id,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"查询策略文件失败: {e}")
            return None

    async def list_strategies(self, folder_path: Optional[str] = None) -> List[dict]:
        """
        列出策略.

        Args:
            folder_path: 文件夹路径（可选）

        Returns:
            List[dict]: 策略列表
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            query = "SELECT * FROM strategy_files WHERE 1=1"
            params = []

            if folder_path:
                query += " AND path LIKE ?"
                params.append(f"{folder_path}%")

            query += " ORDER BY updated_at DESC"

            return db.execute_query(query, tuple(params) if params else None)
        except Exception as e:
            logger.error(f"列出策略文件失败: {e}")
            return []

    async def update_strategy(self, file_id: str, updates: dict) -> bool:
        """
        更新策略.

        Args:
            file_id: 文件ID
            updates: 更新内容

        Returns:
            bool: 是否成功
        """
        from backend.core.database import get_db_manager
        from datetime import datetime

        try:
            db = get_db_manager()
            # 动态构建更新语句
            set_clauses = []
            params = []

            for key, value in updates.items():
                if key in ["name", "path", "type", "content"]:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            if not set_clauses:
                return False

            # 添加updated_at
            set_clauses.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(file_id)

            query = f"UPDATE strategy_files SET {', '.join(set_clauses)} WHERE id = ?"
            rowcount = db.execute_update(query, tuple(params))

            if rowcount > 0:
                logger.info(f"更新策略文件: {file_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"更新策略文件失败: {e}")
            return False

    async def delete_strategy(self, file_id: str) -> bool:
        """
        删除策略.

        Args:
            file_id: 文件ID

        Returns:
            bool: 是否成功
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            query = "DELETE FROM strategy_files WHERE id = ?"
            rowcount = db.execute_update(query, (file_id,))
            if rowcount > 0:
                logger.info(f"删除策略文件: {file_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除策略文件失败: {e}")
            return False

    # 实现BaseRepository的抽象方法
    async def create(self, entity: dict) -> dict:
        """创建实体（实现抽象方法）."""
        return await self.create_strategy(entity)

    async def get_by_id(self, entity_id: str) -> Optional[dict]:
        """根据ID获取实体（实现抽象方法）."""
        return await self.get_strategy(entity_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """获取所有实体（实现抽象方法）."""
        return await self.list_strategies()

    async def update(self, entity: dict) -> dict:
        """更新实体（实现抽象方法）."""
        entity_id = entity.get("id")
        if not entity_id:
            raise ValueError("Entity must have an 'id' field")
        await self.update_strategy(entity_id, entity)
        return entity

    async def delete(self, entity_id: str) -> bool:
        """删除实体（实现抽象方法）."""
        return await self.delete_strategy(entity_id)

    async def count(self) -> int:
        """获取实体总数（实现抽象方法）."""
        strategies = await self.list_strategies()
        return len(strategies)

    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在（实现抽象方法）."""
        strategy = await self.get_strategy(entity_id)
        return strategy is not None


__all__ = ["StrategyRepository"]
