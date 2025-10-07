# -*- coding: utf-8 -*-
"""
回测服务.

提供策略回测功能，集成VnPy的6种回测引擎。
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class BacktestService:
    """回测服务."""

    def __init__(self):
        """初始化回测服务."""
        self.running_tasks: Dict[str, Any] = {}
        self.backtest_engines = {
            "ctastrategy": "vnpy_ctabacktester",
            "algotrading": "vnpy_algotrading",
            "optionmaster": "vnpy_optionmaster",
            "portfoliostrategy": "vnpy_portfoliostrategy",
            "scripttrader": "vnpy_scripttrader",
            "spreadtrading": "vnpy_spreadtrading",
        }
        logger.info("回测服务初始化完成，支持6种策略类型回测")

    async def run_backtest(
        self, strategy_file_id: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """运行回测任务."""
        try:
            task_id = f"backtest_{int(datetime.now().timestamp())}"

            # 提取回测参数
            strategy_type = parameters.get("strategy_type", "ctastrategy")
            symbol = parameters.get("symbol", "")
            exchange = parameters.get("exchange", "")
            start_date = parameters.get("start_date")
            end_date = parameters.get("end_date")
            capital = parameters.get("capital", 1000000.0)

            # 创建回测任务
            task_info = {
                "task_id": task_id,
                "strategy_file_id": strategy_file_id,
                "strategy_type": strategy_type,
                "parameters": parameters,
                "status": "running",
                "progress": 0.0,
                "start_time": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            }

            # 保存任务到运行队列
            self.running_tasks[task_id] = task_info

            # 异步执行回测
            asyncio.create_task(self._execute_backtest(task_id, parameters))

            logger.info(
                "回测任务已创建: task_id=%s, strategy_type=%s", task_id, strategy_type
            )
            return task_info

        except Exception as e:
            logger.error("创建回测任务失败: %s", e)
            raise

    async def _execute_backtest(self, task_id: str, parameters: Dict[str, Any]) -> None:
        """执行回测（异步）."""
        try:
            task = self.running_tasks.get(task_id)
            if not task:
                return

            strategy_type = parameters.get("strategy_type", "ctastrategy")

            # 模拟回测执行
            # TODO: 集成实际的VnPy回测引擎
            logger.info("开始执行回测: task_id=%s", task_id)

            # 模拟进度更新
            for progress in [20, 40, 60, 80, 100]:
                await asyncio.sleep(1)
                task["progress"] = progress
                logger.info(
                    "回测进度更新: task_id=%s, progress=%d%%", task_id, progress
                )

            # 完成回测
            task["status"] = "completed"
            task["progress"] = 100.0
            task["end_time"] = datetime.now().isoformat()

            logger.info("回测任务完成: task_id=%s", task_id)

        except Exception as e:
            logger.error("执行回测失败: task_id=%s, error=%s", task_id, e)
            if task_id in self.running_tasks:
                self.running_tasks[task_id]["status"] = "failed"
                self.running_tasks[task_id]["error_message"] = str(e)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取回测任务."""
        return self.running_tasks.get(task_id)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出回测任务."""
        tasks = list(self.running_tasks.values())

        if status:
            tasks = [t for t in tasks if t.get("status") == status]

        return tasks

    def cancel_task(self, task_id: str) -> bool:
        """取消回测任务."""
        try:
            if task_id in self.running_tasks:
                self.running_tasks[task_id]["status"] = "cancelled"
                logger.info("回测任务已取消: task_id=%s", task_id)
                return True
            return False

        except Exception as e:
            logger.error("取消回测任务失败: %s", e)
            raise

    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取回测结果."""
        try:
            task = self.running_tasks.get(task_id)
            if not task or task["status"] != "completed":
                return None

            # TODO: 从数据库或缓存中获取实际回测结果
            # 模拟回测结果
            mock_result = {
                "task_id": task_id,
                "strategy_type": task.get("strategy_type", "ctastrategy"),
                "total_days": 365,
                "total_return": 0.25,
                "annual_return": 0.25,
                "sharpe_ratio": 1.8,
                "max_drawdown": -0.15,
                "win_rate": 0.55,
                "total_trades": 120,
                "winning_trades": 66,
                "losing_trades": 54,
                "avg_winning_trade": 5000.0,
                "avg_losing_trade": -3000.0,
                "profit_factor": 1.67,
            }

            return mock_result

        except Exception as e:
            logger.error("获取回测结果失败: %s", e)
            raise


__all__ = ["BacktestService"]
