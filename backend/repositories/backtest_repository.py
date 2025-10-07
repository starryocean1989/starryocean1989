# -*- coding: utf-8 -*-
"""
回测Repository.

提供回测任务和结果的数据库操作。
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from backend.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BacktestRepository(BaseRepository):
    """回测Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="backtest_tasks")
        logger.info("回测Repository初始化完成")

    async def create_task(self, task_data: dict) -> dict:
        """创建回测任务."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = """
            INSERT INTO backtest_tasks
            (id, strategy_id, parameters, status, progress, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            task_data["id"],
            task_data["strategy_id"],
            json.dumps(task_data.get("parameters", {})),
            task_data.get("status", "pending"),
            0.0,
            datetime.now().isoformat(),
        )
        db.execute_update(query, params)
        logger.info("创建回测任务: %s", task_data["id"])
        return task_data

    async def get_task(self, task_id: str) -> Optional[dict]:
        """获取回测任务."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = "SELECT * FROM backtest_tasks WHERE id = ?"
        results = db.execute_query(query, (task_id,))
        if results:
            task = results[0]
            task["parameters"] = json.loads(task["parameters"])
            return task
        return None

    async def list_tasks(self, filters: Optional[dict] = None) -> List[dict]:
        """列出回测任务."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = "SELECT * FROM backtest_tasks WHERE 1=1"
        params = []

        if filters:
            if "status" in filters:
                query += " AND status = ?"
                params.append(filters["status"])
            if "strategy_id" in filters:
                query += " AND strategy_id = ?"
                params.append(filters["strategy_id"])

        query += " ORDER BY created_at DESC"
        results = db.execute_query(query, tuple(params) if params else None)

        for task in results:
            task["parameters"] = json.loads(task["parameters"])
        return results

    async def update_task(self, task_id: str, updates: dict) -> bool:
        """更新回测任务."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        set_clauses = []
        params = []

        for key, value in updates.items():
            if key in ["status", "progress", "error"]:
                set_clauses.append(f"{key} = ?")
                params.append(value)
            elif key == "started_at" and value:
                set_clauses.append("started_at = ?")
                params.append(datetime.now().isoformat())
            elif key == "completed_at" and value:
                set_clauses.append("completed_at = ?")
                params.append(datetime.now().isoformat())

        if not set_clauses:
            return False

        params.append(task_id)
        query = f"UPDATE backtest_tasks SET {', '.join(set_clauses)} WHERE id = ?"
        rowcount = db.execute_update(query, tuple(params))
        return rowcount > 0

    async def save_result(self, task_id: str, result_data: dict) -> bool:
        """保存回测结果."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = """
            INSERT OR REPLACE INTO backtest_results
            (task_id, result_data, metrics, trades, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            task_id,
            json.dumps(result_data),
            json.dumps(result_data.get("metrics", {})),
            json.dumps(result_data.get("trades", [])),
            datetime.now().isoformat(),
        )
        db.execute_update(query, params)
        logger.info("保存回测结果: %s", task_id)
        return True

    async def get_result(self, task_id: str) -> Optional[dict]:
        """获取回测结果."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = "SELECT * FROM backtest_results WHERE task_id = ?"
        results = db.execute_query(query, (task_id,))
        if results:
            result = results[0]
            result["result_data"] = json.loads(result["result_data"])
            result["metrics"] = json.loads(result["metrics"])
            result["trades"] = json.loads(result["trades"])
            return result
        return None

    # 实现BaseRepository的抽象方法
    async def create(self, entity: dict) -> dict:
        """创建实体（实现抽象方法）."""
        return await self.create_task(entity)

    async def get_by_id(self, entity_id: str) -> Optional[dict]:
        """根据ID获取实体（实现抽象方法）."""
        return await self.get_task(entity_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """获取所有实体（实现抽象方法）."""
        return await self.list_tasks()

    async def update(self, entity: dict) -> dict:
        """更新实体（实现抽象方法）."""
        entity_id = entity.get("id")
        if not entity_id:
            raise ValueError("Entity must have an 'id' field")
        await self.update_task(entity_id, entity)
        return entity

    async def delete(self, entity_id: str) -> bool:
        """删除实体（实现抽象方法）."""
        from backend.core.database import get_db_manager

        db = get_db_manager()
        query = "DELETE FROM backtest_tasks WHERE id = ?"
        rowcount = db.execute_update(query, (entity_id,))
        return rowcount > 0

    async def count(self) -> int:
        """获取实体总数（实现抽象方法）."""
        tasks = await self.list_tasks()
        return len(tasks)

    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在（实现抽象方法）."""
        task = await self.get_task(entity_id)
        return task is not None


__all__ = ["BacktestRepository"]
