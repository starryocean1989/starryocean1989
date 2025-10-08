# -*- coding: utf-8 -*-
"""
回测服务.

提供策略回测功能，集成VnPy的6种回测引擎。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio

from backend.repositories.backtest_repository import BacktestRepository

logger = logging.getLogger(__name__)


class BacktestService:
    """回测服务."""

    def __init__(self):
        """初始化回测服务."""
        self.running_tasks: Dict[str, Any] = {}
        self.repository = BacktestRepository()
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

            # 保存到数据库
            await self.repository.create_task(task_info)

            # 异步执行回测
            asyncio.create_task(self._execute_backtest(task_id, parameters))

            logger.info("回测任务已创建: task_id=%s, strategy_type=%s", task_id, strategy_type)
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

            # 集成VnPy回测引擎
            logger.info("开始执行回测: task_id=%s, strategy_type=%s", task_id, strategy_type)

            # 创建回测引擎
            from backend.services.strategy_center.backtest_engines import (
                BacktestEngineFactory,
            )

            engine = BacktestEngineFactory.create_engine(strategy_type)
            if not engine:
                raise ValueError(f"不支持的策略类型: {strategy_type}")

            # 初始化引擎
            task["progress"] = 10
            logger.info("初始化回测引擎: task_id=%s", task_id)
            if not engine.initialize(parameters):
                raise RuntimeError("回测引擎初始化失败")

            # 执行回测
            task["progress"] = 30
            logger.info("执行回测计算: task_id=%s", task_id)
            backtest_result = engine.run_backtest()

            # 获取结果
            task["progress"] = 80
            logger.info("收集回测结果: task_id=%s", task_id)
            results = engine.get_results()

            # 保存结果
            task["progress"] = 90
            task["results"] = results
            task["backtest_info"] = backtest_result

            # 完成回测
            task["status"] = "completed"
            task["progress"] = 100.0
            task["end_time"] = datetime.now().isoformat()

            # 保存结果到数据库
            await self.repository.save_result(
                task_id,
                {
                    "result_data": backtest_result,
                    "metrics": results,
                    "trades": results.get("trades", []),
                },
            )

            # 更新任务状态到数据库
            await self.repository.update_task(
                task_id,
                {"status": "completed", "progress": 100.0, "completed_at": task["end_time"]},
            )

            logger.info(
                "回测任务完成: task_id=%s, 总收益率=%.2f%%",
                task_id,
                results.get("total_return", 0) * 100,
            )

        except Exception as e:
            logger.error("执行回测失败: task_id=%s, error=%s", task_id, e)
            if task_id in self.running_tasks:
                self.running_tasks[task_id]["status"] = "failed"
                self.running_tasks[task_id]["error_message"] = str(e)

                # 更新数据库
                await self.repository.update_task(task_id, {"status": "failed", "error": str(e)})

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取回测任务."""
        # 优先从内存获取（包含最新状态）
        if task_id in self.running_tasks:
            return self.running_tasks[task_id]

        # 从数据库获取
        return await self.repository.get_task(task_id)

    async def list_tasks(
        self, status: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出回测任务."""
        # 从数据库获取
        db_tasks = await self.repository.list_tasks(status, limit, offset)

        # 合并内存中的最新状态
        result_tasks = []
        for task in db_tasks:
            task_id = task.get("id")
            if task_id in self.running_tasks:
                # 使用内存中的最新状态
                result_tasks.append(self.running_tasks[task_id])
            else:
                result_tasks.append(task)

        return result_tasks

    async def cancel_task(self, task_id: str) -> bool:
        """取消回测任务."""
        try:
            if task_id in self.running_tasks:
                self.running_tasks[task_id]["status"] = "cancelled"

                # 更新数据库
                await self.repository.update_task(task_id, {"status": "cancelled"})

                logger.info("回测任务已取消: task_id=%s", task_id)
                return True
            return False

        except Exception as e:
            logger.error("取消回测任务失败: %s", e)
            raise

    async def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取回测结果."""
        try:
            # 检查任务状态
            task = await self.get_task(task_id)
            if not task:
                logger.warning("任务不存在: %s", task_id)
                return None

            if task["status"] != "completed":
                logger.warning("任务未完成: %s, 状态: %s", task_id, task["status"])
                return None

            # 从数据库获取回测结果
            result = await self.repository.get_result(task_id)

            if result:
                # 合并metrics数据
                return {
                    "task_id": task_id,
                    "strategy_type": task.get("strategy_type", "ctastrategy"),
                    **result.get("metrics", {}),
                    "trades": result.get("trades", []),
                    "result_data": result.get("result_data", {}),
                }

            # 如果数据库中没有，尝试从内存获取
            if task_id in self.running_tasks:
                task_mem = self.running_tasks[task_id]
                if "results" in task_mem:
                    return {
                        "task_id": task_id,
                        "strategy_type": task.get("strategy_type", "ctastrategy"),
                        **task_mem["results"],
                    }

            logger.warning("未找到回测结果: %s", task_id)
            return None

        except Exception as e:
            logger.error("获取回测结果失败: %s", e)
            raise


__all__ = ["BacktestService"]
