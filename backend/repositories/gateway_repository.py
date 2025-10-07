# -*- coding: utf-8 -*-
"""
网关Repository.

提供网关实例的数据库操作。
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from backend.core.database import get_db_manager
from backend.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class GatewayRepository(BaseRepository):
    """网关Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="gateways")
        logger.info("网关Repository初始化完成")

    async def create_gateway(self, gateway_data: dict) -> dict:
        """创建网关实例."""
        db = get_db_manager()
        query = """
            INSERT INTO gateway_instances (
                id, name, gateway_type, config, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now().isoformat()
        params = (
            gateway_data["id"],
            gateway_data["name"],
            gateway_data["gateway_type"],
            json.dumps(gateway_data.get("config", {})),
            gateway_data.get("status", "disconnected"),
            now,
            now,
        )
        db.execute_update(query, params)
        logger.info("创建网关实例: %s", gateway_data["id"])
        return gateway_data

    async def get_gateway(self, instance_id: str) -> Optional[dict]:
        """获取网关实例."""
        db = get_db_manager()
        query = "SELECT * FROM gateway_instances WHERE id = ?"
        results = db.execute_query(query, (instance_id,))
        if results:
            gateway = results[0]
            gateway["config"] = json.loads(gateway["config"])
            return gateway
        return None

    async def list_gateways(self) -> List[dict]:
        """列出网关实例."""
        db = get_db_manager()
        query = "SELECT * FROM gateway_instances ORDER BY created_at DESC"
        results = db.execute_query(query)
        for gateway in results:
            gateway["config"] = json.loads(gateway["config"])
        return results

    async def update_gateway(self, instance_id: str, updates: dict) -> bool:
        """更新网关实例."""
        db = get_db_manager()
        set_clauses = []
        params = []

        for key, value in updates.items():
            if key in ["name", "status"]:
                set_clauses.append(f"{key} = ?")
                params.append(value)
            elif key == "config":
                set_clauses.append("config = ?")
                params.append(json.dumps(value))

        if not set_clauses:
            return False

        set_clauses.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(instance_id)

        query = (
            f"UPDATE gateway_instances SET {', '.join(set_clauses)} " f"WHERE id = ?"
        )
        rowcount = db.execute_update(query, tuple(params))
        return rowcount > 0

    async def delete_gateway(self, instance_id: str) -> bool:
        """删除网关实例."""
        db = get_db_manager()
        query = "DELETE FROM gateway_instances WHERE id = ?"
        rowcount = db.execute_update(query, (instance_id,))
        if rowcount > 0:
            logger.info("删除网关实例: %s", instance_id)
            return True
        return False

    # 实现BaseRepository的抽象方法
    async def create(self, entity: dict) -> dict:
        """创建实体（实现抽象方法）."""
        return await self.create_gateway(entity)

    async def get_by_id(self, entity_id: str) -> Optional[dict]:
        """根据ID获取实体（实现抽象方法）."""
        return await self.get_gateway(entity_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """获取所有实体（实现抽象方法）."""
        return await self.list_gateways()

    async def update(self, entity: dict) -> dict:
        """更新实体（实现抽象方法）."""
        entity_id = entity.get("id")
        if not entity_id:
            raise ValueError("Entity must have an 'id' field")
        await self.update_gateway(entity_id, entity)
        return entity

    async def delete(self, entity_id: str) -> bool:
        """删除实体（实现抽象方法）."""
        return await self.delete_gateway(entity_id)

    async def count(self) -> int:
        """获取实体总数（实现抽象方法）."""
        gateways = await self.list_gateways()
        return len(gateways)

    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在（实现抽象方法）."""
        gateway = await self.get_gateway(entity_id)
        return gateway is not None


class StrategyInstanceRepository(BaseRepository):
    """策略实例Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="strategy_instances")
        logger.info("策略实例Repository初始化完成")

    async def create_instance(self, instance_data: dict) -> dict:
        """创建策略实例."""
        db = get_db_manager()
        query = """
            INSERT INTO strategy_instances (
                id, gateway_id, strategy_name, parameters, status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            instance_data["id"],
            instance_data["gateway_id"],
            instance_data["strategy_name"],
            json.dumps(instance_data.get("parameters", {})),
            instance_data.get("status", "stopped"),
            datetime.now().isoformat(),
        )
        db.execute_update(query, params)
        logger.info("创建策略实例: %s", instance_data["id"])
        return instance_data

    async def get_instance(self, strategy_id: str) -> Optional[dict]:
        """获取策略实例."""
        db = get_db_manager()
        query = "SELECT * FROM strategy_instances WHERE id = ?"
        results = db.execute_query(query, (strategy_id,))
        if results:
            instance = results[0]
            instance["parameters"] = json.loads(instance["parameters"])
            return instance
        return None

    async def list_instances(self, gateway_id: Optional[str] = None) -> List[dict]:
        """列出策略实例."""
        db = get_db_manager()
        if gateway_id:
            query = (
                "SELECT * FROM strategy_instances "
                "WHERE gateway_id = ? ORDER BY created_at DESC"
            )
            results = db.execute_query(query, (gateway_id,))
        else:
            query = "SELECT * FROM strategy_instances " "ORDER BY created_at DESC"
            results = db.execute_query(query)

        for instance in results:
            instance["parameters"] = json.loads(instance["parameters"])
        return results

    async def update_instance(self, strategy_id: str, updates: dict) -> bool:
        """更新策略实例."""
        db = get_db_manager()
        set_clauses = []
        params = []

        for key, value in updates.items():
            if key == "status":
                set_clauses.append("status = ?")
                params.append(value)
            elif key == "parameters":
                set_clauses.append("parameters = ?")
                params.append(json.dumps(value))

        if not set_clauses:
            return False

        params.append(strategy_id)
        query = (
            f"UPDATE strategy_instances SET {', '.join(set_clauses)} " f"WHERE id = ?"
        )
        rowcount = db.execute_update(query, tuple(params))
        return rowcount > 0

    async def delete_instance(self, strategy_id: str) -> bool:
        """删除策略实例."""
        db = get_db_manager()
        query = "DELETE FROM strategy_instances WHERE id = ?"
        rowcount = db.execute_update(query, (strategy_id,))
        if rowcount > 0:
            logger.info("删除策略实例: %s", strategy_id)
            return True
        return False

    # 实现BaseRepository的抽象方法
    async def create(self, entity: dict) -> dict:
        """创建实体（实现抽象方法）."""
        return await self.create_instance(entity)

    async def get_by_id(self, entity_id: str) -> Optional[dict]:
        """根据ID获取实体（实现抽象方法）."""
        return await self.get_instance(entity_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """获取所有实体（实现抽象方法）."""
        return await self.list_instances()

    async def update(self, entity: dict) -> dict:
        """更新实体（实现抽象方法）."""
        entity_id = entity.get("id")
        if not entity_id:
            raise ValueError("Entity must have an 'id' field")
        await self.update_instance(entity_id, entity)
        return entity

    async def delete(self, entity_id: str) -> bool:
        """删除实体（实现抽象方法）."""
        return await self.delete_instance(entity_id)

    async def count(self) -> int:
        """获取实体总数（实现抽象方法）."""
        instances = await self.list_instances()
        return len(instances)

    async def exists(self, entity_id: str) -> bool:
        """检查实体是否存在（实现抽象方法）."""
        instance = await self.get_instance(entity_id)
        return instance is not None


__all__ = ["GatewayRepository", "StrategyInstanceRepository"]
