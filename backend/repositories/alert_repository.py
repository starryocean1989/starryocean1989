# -*- coding: utf-8 -*-
"""
告警Repository.

提供告警规则和记录的数据库操作。
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from backend.core.database import get_db_manager
from backend.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AlertRepository(BaseRepository):
    """告警Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="alerts")
        logger.info("告警Repository初始化完成")

    async def create_rule(self, rule_data: dict) -> dict:
        """创建告警规则."""
        db = get_db_manager()
        query = """
            INSERT INTO alert_rules (
                id, name, condition, level, enabled,
                actions, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now().isoformat()
        params = (
            rule_data["id"],
            rule_data["name"],
            rule_data["condition"],
            rule_data["level"],
            rule_data.get("enabled", 1),
            json.dumps(rule_data.get("actions", [])),
            now,
            now,
        )
        db.execute_update(query, params)
        logger.info("创建告警规则: %s", rule_data["id"])
        return rule_data

    async def get_rule(self, rule_id: str) -> Optional[dict]:
        """获取告警规则."""
        db = get_db_manager()
        query = "SELECT * FROM alert_rules WHERE id = ?"
        results = db.execute_query(query, (rule_id,))
        if results:
            rule = results[0]
            rule["actions"] = json.loads(rule["actions"])
            return rule
        return None

    async def list_rules(self) -> List[dict]:
        """列出告警规则."""
        db = get_db_manager()
        query = "SELECT * FROM alert_rules ORDER BY created_at DESC"
        results = db.execute_query(query)
        for rule in results:
            rule["actions"] = json.loads(rule["actions"])
        return results

    async def update_rule(self, rule_id: str, updates: dict) -> bool:
        """更新告警规则."""
        db = get_db_manager()
        set_clauses = []
        params = []

        for key, value in updates.items():
            if key in ["name", "condition", "level", "enabled"]:
                set_clauses.append(f"{key} = ?")
                params.append(value)
            elif key == "actions":
                set_clauses.append("actions = ?")
                params.append(json.dumps(value))

        if not set_clauses:
            return False

        set_clauses.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(rule_id)

        query = f"UPDATE alert_rules SET {', '.join(set_clauses)} WHERE id = ?"
        rowcount = db.execute_update(query, tuple(params))
        return rowcount > 0

    async def delete_rule(self, rule_id: str) -> bool:
        """删除告警规则."""
        db = get_db_manager()
        query = "DELETE FROM alert_rules WHERE id = ?"
        rowcount = db.execute_update(query, (rule_id,))
        if rowcount > 0:
            logger.info("删除告警规则: %s", rule_id)
            return True
        return False

    async def create_alert(self, alert_data: dict) -> dict:
        """创建告警记录."""
        db = get_db_manager()
        query = """
            INSERT INTO alert_records (
                id, rule_id, level, message, data, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            alert_data["id"],
            alert_data.get("rule_id"),
            alert_data["level"],
            alert_data["message"],
            json.dumps(alert_data.get("data", {})),
            alert_data.get("status", "new"),
            datetime.now().isoformat(),
        )
        db.execute_update(query, params)
        logger.info("创建告警记录: %s", alert_data["id"])
        return alert_data

    async def get_alert(self, alert_id: str) -> Optional[dict]:
        """获取告警记录."""
        db = get_db_manager()
        query = "SELECT * FROM alert_records WHERE id = ?"
        results = db.execute_query(query, (alert_id,))
        if results:
            alert = results[0]
            alert["data"] = json.loads(alert["data"])
            return alert
        return None

    async def list_alerts(self, filters: Optional[dict] = None) -> List[dict]:
        """列出告警记录."""
        db = get_db_manager()
        query = "SELECT * FROM alert_records WHERE 1=1"
        params = []

        if filters:
            if "status" in filters:
                query += " AND status = ?"
                params.append(filters["status"])
            if "level" in filters:
                query += " AND level = ?"
                params.append(filters["level"])

        query += " ORDER BY created_at DESC"
        results = db.execute_query(query, tuple(params) if params else None)
        for alert in results:
            alert["data"] = json.loads(alert["data"])
        return results


__all__ = ["AlertRepository"]
