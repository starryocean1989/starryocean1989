# -*- coding: utf-8 -*-
"""
配置Repository.

提供系统配置的数据库操作。
"""

import logging
from typing import List, Optional

from backend.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ConfigRepository(BaseRepository):
    """配置Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="configs")
        logger.info("配置Repository初始化完成")

    async def get_config(self, config_key: str) -> Optional[dict]:
        """获取配置."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = "SELECT * FROM system_config WHERE key = ?"
        results = db.execute_query(query, (config_key,))
        return results[0] if results else None

    async def set_config(self, config_key: str, config_data: dict) -> bool:
        """设置配置."""
        from backend.core.database import get_db_manager
        from datetime import datetime

        db = get_db_manager()
        query = """
            INSERT OR REPLACE INTO system_config (key, value, type, description, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            config_key,
            config_data["value"],
            config_data.get("type", "string"),
            config_data.get("description", ""),
            datetime.now().isoformat(),
        )
        db.execute_update(query, params)
        logger.info(f"设置配置: {config_key}")
        return True

    async def list_configs(self, config_type: Optional[str] = None) -> List[dict]:
        """列出配置."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        if config_type:
            query = "SELECT * FROM system_config WHERE type = ? ORDER BY key"
            results = db.execute_query(query, (config_type,))
        else:
            query = "SELECT * FROM system_config ORDER BY key"
            results = db.execute_query(query)
        return results

    async def delete_config(self, config_key: str) -> bool:
        """删除配置."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = "DELETE FROM system_config WHERE key = ?"
        rowcount = db.execute_update(query, (config_key,))
        if rowcount > 0:
            logger.info(f"删除配置: {config_key}")
            return True
        return False


__all__ = ["ConfigRepository"]
