# -*- coding: utf-8 -*-
"""
策略池服务.

提供策略部署、启停、管理等功能。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StrategyPoolService:
    """策略池服务."""

    def __init__(self):
        """初始化策略池服务."""
        # gateway_id -> List[strategy]
        self.strategy_pools: Dict[str, List[Dict[str, Any]]] = {}
        logger.info("策略池服务初始化完成")

    def deploy_strategy(
        self,
        gateway_id: str,
        strategy_file_id: str,
        strategy_name: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """部署策略到网关."""
        try:
            strategy_id = f"strat_{int(datetime.now().timestamp())}"

            strategy = {
                "strategy_id": strategy_id,
                "gateway_id": gateway_id,
                "strategy_file_id": strategy_file_id,
                "strategy_name": strategy_name,
                "strategy_type": parameters.get("strategy_type", "ctastrategy"),
                "parameters": parameters,
                "status": "stopped",
                "deployed_at": datetime.now().isoformat(),
            }

            # 添加到策略池
            if gateway_id not in self.strategy_pools:
                self.strategy_pools[gateway_id] = []

            self.strategy_pools[gateway_id].append(strategy)

            logger.info(
                "策略部署成功: strategy_id=%s, gateway_id=%s", strategy_id, gateway_id
            )
            return strategy

        except Exception as e:
            logger.error("部署策略失败: %s", e)
            raise

    def start_strategy(self, strategy_id: str) -> bool:
        """启动策略."""
        try:
            strategy = self._find_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"策略不存在: {strategy_id}")

            # TODO: 调用VnPy策略引擎的start_strategy方法
            strategy["status"] = "running"
            strategy["started_at"] = datetime.now().isoformat()

            logger.info("策略启动成功: strategy_id=%s", strategy_id)
            return True

        except Exception as e:
            logger.error("启动策略失败: %s", e)
            raise

    def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略."""
        try:
            strategy = self._find_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"策略不存在: {strategy_id}")

            # TODO: 调用VnPy策略引擎的stop_strategy方法
            strategy["status"] = "stopped"
            strategy["stopped_at"] = datetime.now().isoformat()

            logger.info("策略停止成功: strategy_id=%s", strategy_id)
            return True

        except Exception as e:
            logger.error("停止策略失败: %s", e)
            raise

    def start_all_strategies(self, gateway_id: str) -> int:
        """启动所有策略."""
        try:
            if gateway_id not in self.strategy_pools:
                return 0

            count = 0
            for strategy in self.strategy_pools[gateway_id]:
                if strategy["status"] != "running":
                    self.start_strategy(strategy["strategy_id"])
                    count += 1

            logger.info("批量启动策略完成: gateway_id=%s, count=%d", gateway_id, count)
            return count

        except Exception as e:
            logger.error("批量启动策略失败: %s", e)
            raise

    def stop_all_strategies(self, gateway_id: str) -> int:
        """停止所有策略."""
        try:
            if gateway_id not in self.strategy_pools:
                return 0

            count = 0
            for strategy in self.strategy_pools[gateway_id]:
                if strategy["status"] == "running":
                    self.stop_strategy(strategy["strategy_id"])
                    count += 1

            logger.info("批量停止策略完成: gateway_id=%s, count=%d", gateway_id, count)
            return count

        except Exception as e:
            logger.error("批量停止策略失败: %s", e)
            raise

    def delete_strategy(self, strategy_id: str) -> bool:
        """删除策略."""
        try:
            for gateway_id, strategies in self.strategy_pools.items():
                for i, strategy in enumerate(strategies):
                    if strategy["strategy_id"] == strategy_id:
                        # 如果策略正在运行，先停止
                        if strategy["status"] == "running":
                            self.stop_strategy(strategy_id)

                        # 删除策略
                        del strategies[i]
                        logger.info("策略删除成功: strategy_id=%s", strategy_id)
                        return True

            raise ValueError(f"策略不存在: {strategy_id}")

        except Exception as e:
            logger.error("删除策略失败: %s", e)
            raise

    def list_strategies(self, gateway_id: str) -> List[Dict[str, Any]]:
        """列出网关的策略池."""
        return self.strategy_pools.get(gateway_id, [])

    def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取策略详情."""
        return self._find_strategy(strategy_id)

    def get_active_strategy_count(self, gateway_id: str) -> int:
        """获取网关激活的策略数量."""
        if gateway_id not in self.strategy_pools:
            return 0

        return sum(
            1 for s in self.strategy_pools[gateway_id] if s["status"] == "running"
        )

    def _find_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """查找策略."""
        for strategies in self.strategy_pools.values():
            for strategy in strategies:
                if strategy["strategy_id"] == strategy_id:
                    return strategy
        return None


__all__ = ["StrategyPoolService"]
