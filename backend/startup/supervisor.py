# -*- coding: utf-8 -*-
"""
启动流程监督模块

提供 ProcessSupervisor 来统一调度后端启动阶段的 Worker，
负责：
- 统一监听运行状态并输出日志
- 向事件总线发布节点开始/完成/失败事件
- 聚合 WorkerResult 并在失败时提供上下文
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from backend.startup.context import StartupContext
from backend.startup.event_bus import StartupEvent, StartupEventType
from backend.startup.workers.base import StartupWorker, WorkerResult

logger = logging.getLogger("backend.startup.supervisor")


class ProcessSupervisor:
    """并行 Worker 调度器"""

    def __init__(self, context: StartupContext) -> None:
        self.context = context
        self.event_bus = context.get_event_bus()
        self._loop = asyncio.get_event_loop()

    async def run_workers(self, worker_map: Dict[str, StartupWorker]) -> Dict[str, WorkerResult]:
        """并行运行多个Worker

        Args:
            worker_map: {plan_node_id: worker}

        Returns:
            Dict[str, WorkerResult]: Worker执行结果
        """
        results: Dict[str, WorkerResult] = {}

        async def _wrapped(node_id: str, worker: StartupWorker) -> WorkerResult:
            await self._emit(
                StartupEventType.NODE_STARTED,
                node_id,
                message=f"Worker {worker.name} 启动",
                payload={"worker": worker.name},
            )
            try:
                result = await worker.run(self.context)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Worker %s 运行异常: %s", worker.name, exc)
                await self._emit(
                    StartupEventType.NODE_FAILED,
                    node_id,
                    message=str(exc),
                    payload={"worker": worker.name, "critical": True},
                )
                raise

            payload = {
                "worker": worker.name,
                "elapsed_ms": result.elapsed_ms,
                "ready_key": f"{node_id}:complete",
            }
            if result.success:
                await self._emit(
                    StartupEventType.NODE_READY,
                    node_id,
                    message=f"Worker {worker.name} 完成",
                    payload=payload,
                )
            else:
                await self._emit(
                    StartupEventType.NODE_FAILED,
                    node_id,
                    message=result.message,
                    payload=payload,
                )
            return result

        if hasattr(asyncio, "TaskGroup"):
            task_refs: Dict[str, asyncio.Task[WorkerResult]] = {}
            async with asyncio.TaskGroup() as tg:  # type: ignore[attr-defined]
                for node_id, worker in worker_map.items():
                    task_refs[node_id] = tg.create_task(_wrapped(node_id, worker))
            for node_id, task in task_refs.items():
                results[node_id] = task.result()
        else:  # Python < 3.11
            tasks = {
                node_id: self._loop.create_task(_wrapped(node_id, worker))
                for node_id, worker in worker_map.items()
            }
            for node_id, task in tasks.items():
                results[node_id] = await task

        return results

    async def _emit(
        self,
        event_type: StartupEventType,
        node_id: str,
        *,
        message: str = "",
        payload: Optional[Dict[str, object]] = None,
    ) -> None:
        if not self.event_bus:
            return
        event = StartupEvent(
            event_type=event_type,
            node_id=node_id,
            message=message,
            payload=payload or {},
        )
        await self.event_bus.publish(event)

