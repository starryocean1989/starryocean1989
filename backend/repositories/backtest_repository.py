# -*- coding: utf-8 -*-
"""
回测任务Repository.

提供回测任务和结果的数据库操作。
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BacktestRepository:
    """回测任务Repository."""

    def __init__(self):
        """初始化回测Repository."""
        logger.info("回测Repository初始化完成")

    async def create_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建回测任务.

        Args:
            task_data: 任务数据

        Returns:
            Dict[str, Any]: 创建的任务数据
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            now = datetime.now().isoformat()

            query = """
                INSERT INTO backtest_tasks (
                    id, strategy_id, parameters, status, progress,
                    created_at, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                task_data["id"],
                task_data.get("strategy_id", ""),
                json.dumps(task_data.get("parameters", {})),
                task_data.get("status", "pending"),
                task_data.get("progress", 0.0),
                now,
                task_data.get("started_at"),
            )
            db.execute_update(query, params)
            logger.info("创建回测任务记录: %s", task_data["id"])
            return task_data
        except Exception as e:
            logger.error("创建回测任务记录失败: %s", e)
            raise

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取回测任务.

        Args:
            task_id: 任务ID

        Returns:
            Optional[Dict[str, Any]]: 任务数据
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            query = "SELECT * FROM backtest_tasks WHERE id = ?"
            results = db.execute_query(query, (task_id,))

            if results:
                task = dict(results[0])
                # 解析JSON字段
                if task.get("parameters"):
                    task["parameters"] = json.loads(task["parameters"])
                return task
            return None
        except Exception as e:
            logger.error("查询回测任务失败: %s", e)
            return None

    async def list_tasks(
        self, status: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        列出回测任务.

        Args:
            status: 状态筛选
            limit: 限制数量
            offset: 偏移量

        Returns:
            List[Dict[str, Any]]: 任务列表
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()

            if status:
                query = "SELECT * FROM backtest_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
                results = db.execute_query(query, (status, limit, offset))
            else:
                query = "SELECT * FROM backtest_tasks ORDER BY created_at DESC LIMIT ? OFFSET ?"
                results = db.execute_query(query, (limit, offset))

            tasks = []
            for row in results:
                task = dict(row)
                # 解析JSON字段
                if task.get("parameters"):
                    task["parameters"] = json.loads(task["parameters"])
                tasks.append(task)

            return tasks
        except Exception as e:
            logger.error("列出回测任务失败: %s", e)
            return []

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新回测任务.

        Args:
            task_id: 任务ID
            updates: 更新内容

        Returns:
            bool: 是否成功
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()

            # 构建动态更新语句
            set_clauses = []
            params = []

            for key, value in updates.items():
                if key in ["status", "progress", "error", "started_at", "completed_at"]:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
                elif key == "parameters":
                    set_clauses.append("parameters = ?")
                    params.append(json.dumps(value))

            if not set_clauses:
                return False

            params.append(task_id)
            query = f"UPDATE backtest_tasks SET {', '.join(set_clauses)} WHERE id = ?"
            rowcount = db.execute_update(query, tuple(params))

            if rowcount > 0:
                logger.info("更新回测任务: %s", task_id)
                return True
            return False
        except Exception as e:
            logger.error("更新回测任务失败: %s", e)
            return False

    async def save_result(self, task_id: str, result_data: Dict[str, Any]) -> bool:
        """
        保存回测结果.

        Args:
            task_id: 任务ID
            result_data: 结果数据

        Returns:
            bool: 是否成功
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            now = datetime.now().isoformat()

            # 检查是否已存在
            query_check = "SELECT task_id FROM backtest_results WHERE task_id = ?"
            existing = db.execute_query(query_check, (task_id,))

            if existing:
                # 更新现有记录
                query = """
                    UPDATE backtest_results
                    SET result_data = ?, metrics = ?, trades = ?
                    WHERE task_id = ?
                """
                params = (
                    json.dumps(result_data.get("result_data", {})),
                    json.dumps(result_data.get("metrics", {})),
                    json.dumps(result_data.get("trades", [])),
                    task_id,
                )
            else:
                # 插入新记录
                query = """
                    INSERT INTO backtest_results (
                        task_id, result_data, metrics, trades, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                """
                params = (
                    task_id,
                    json.dumps(result_data.get("result_data", {})),
                    json.dumps(result_data.get("metrics", {})),
                    json.dumps(result_data.get("trades", [])),
                    now,
                )

            db.execute_update(query, params)
            logger.info("保存回测结果: %s", task_id)
            return True
        except Exception as e:
            logger.error("保存回测结果失败: %s", e)
            return False

    async def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取回测结果.

        Args:
            task_id: 任务ID

        Returns:
            Optional[Dict[str, Any]]: 结果数据
        """
        from backend.core.database import get_db_manager

        try:
            db = get_db_manager()
            query = "SELECT * FROM backtest_results WHERE task_id = ?"
            results = db.execute_query(query, (task_id,))

            if results:
                result = dict(results[0])
                # 解析JSON字段
                if result.get("result_data"):
                    result["result_data"] = json.loads(result["result_data"])
                if result.get("metrics"):
                    result["metrics"] = json.loads(result["metrics"])
                if result.get("trades"):
                    result["trades"] = json.loads(result["trades"])
                return result
            return None
        except Exception as e:
            logger.error("查询回测结果失败: %s", e)
            return None


__all__ = ["BacktestRepository"]
