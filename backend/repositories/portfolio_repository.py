# -*- coding: utf-8 -*-
"""
组合Repository.

提供组合投资的数据库操作。
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from backend.core.database import get_db_manager
from backend.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class PortfolioRepository(BaseRepository):
    """组合Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="portfolios")
        logger.info("组合Repository初始化完成")

    async def create_portfolio(self, portfolio_data: dict) -> dict:
        """创建组合."""
        db = get_db_manager()
        query = """
            INSERT INTO portfolios (id, name, type, members, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        now = datetime.now().isoformat()
        params = (
            portfolio_data["id"],
            portfolio_data["name"],
            portfolio_data["type"],
            json.dumps(portfolio_data.get("members", [])),
            now,
            now,
        )
        db.execute_update(query, params)
        logger.info("创建组合: %s", portfolio_data["id"])
        return portfolio_data

    async def get_portfolio(self, portfolio_id: str) -> Optional[dict]:
        """获取组合."""
        db = get_db_manager()
        query = "SELECT * FROM portfolios WHERE id = ?"
        results = db.execute_query(query, (portfolio_id,))
        if results:
            portfolio = results[0]
            portfolio["members"] = json.loads(portfolio["members"])
            return portfolio
        return None

    async def list_portfolios(self) -> List[dict]:
        """列出组合."""
        db = get_db_manager()
        query = "SELECT * FROM portfolios ORDER BY created_at DESC"
        results = db.execute_query(query)
        for portfolio in results:
            portfolio["members"] = json.loads(portfolio["members"])
        return results

    async def update_portfolio(self, portfolio_id: str, updates: dict) -> bool:
        """更新组合."""
        db = get_db_manager()
        set_clauses = []
        params = []

        for key, value in updates.items():
            if key == "name":
                set_clauses.append("name = ?")
                params.append(value)
            elif key == "members":
                set_clauses.append("members = ?")
                params.append(json.dumps(value))

        if not set_clauses:
            return False

        set_clauses.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(portfolio_id)

        query = f"UPDATE portfolios SET {', '.join(set_clauses)} WHERE id = ?"
        rowcount = db.execute_update(query, tuple(params))
        return rowcount > 0

    async def delete_portfolio(self, portfolio_id: str) -> bool:
        """删除组合."""
        db = get_db_manager()
        query = "DELETE FROM portfolios WHERE id = ?"
        rowcount = db.execute_update(query, (portfolio_id,))
        if rowcount > 0:
            logger.info("删除组合: %s", portfolio_id)
            return True
        return False


class PortfolioDataRepository(BaseRepository):
    """组合数据Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="portfolio_data")
        logger.info("组合数据Repository初始化完成")

    async def save_performance(self, portfolio_id: str, data: dict) -> bool:
        """保存业绩数据."""
        db = get_db_manager()
        query = """
            INSERT OR REPLACE INTO portfolio_data
            (portfolio_id, timestamp, data_type, data)
            VALUES (?, ?, ?, ?)
        """
        params = (
            portfolio_id,
            datetime.now().isoformat(),
            "performance",
            json.dumps(data),
        )
        db.execute_update(query, params)
        return True

    async def get_performance(self, portfolio_id: str) -> Optional[dict]:
        """获取业绩数据."""
        db = get_db_manager()
        query = """
            SELECT * FROM portfolio_data
            WHERE portfolio_id = ? AND data_type = 'performance'
            ORDER BY timestamp DESC LIMIT 1
        """
        results = db.execute_query(query, (portfolio_id,))
        if results:
            result = results[0]
            result["data"] = json.loads(result["data"])
            return result
        return None

    async def save_risk_metrics(self, portfolio_id: str, data: dict) -> bool:
        """保存风险指标."""
        db = get_db_manager()
        query = """
            INSERT OR REPLACE INTO portfolio_data
            (portfolio_id, timestamp, data_type, data)
            VALUES (?, ?, ?, ?)
        """
        params = (
            portfolio_id,
            datetime.now().isoformat(),
            "risk_metrics",
            json.dumps(data),
        )
        db.execute_update(query, params)
        return True

    async def get_risk_metrics(self, portfolio_id: str) -> Optional[dict]:
        """获取风险指标."""
        db = get_db_manager()
        query = """
            SELECT * FROM portfolio_data
            WHERE portfolio_id = ? AND data_type = 'risk_metrics'
            ORDER BY timestamp DESC LIMIT 1
        """
        results = db.execute_query(query, (portfolio_id,))
        if results:
            result = results[0]
            result["data"] = json.loads(result["data"])
            return result
        return None


__all__ = ["PortfolioRepository", "PortfolioDataRepository"]
