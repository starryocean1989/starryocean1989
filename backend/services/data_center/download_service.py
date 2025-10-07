# -*- coding: utf-8 -*-
"""
下载服务.

提供数据下载任务管理相关的业务逻辑。
"""

import logging
import asyncio
from contextlib import suppress
from typing import Any, Dict, Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum

from backend.services.base_service import BaseService
from backend.core.models import DownloadTask

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadService(BaseService):
    """下载服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化下载服务."""
        super().__init__("DownloadService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._tasks: Dict[str, DownloadTask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._task_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """初始化下载服务."""
        try:
            self.logger.info("正在初始化下载服务...")

            # 注册事件处理器
            self.event_service.register_handler(
                "download_task_created", self._handle_task_created
            )
            self.event_service.register_handler(
                "download_task_cancelled", self._handle_task_cancelled
            )

            self.logger.info("下载服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("下载服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭下载服务."""
        try:
            self.logger.info("正在关闭下载服务...")

            # 取消所有运行中的任务
            await self._cancel_all_running_tasks()

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "download_task_created", self._handle_task_created
            )
            self.event_service.unregister_handler(
                "download_task_cancelled", self._handle_task_cancelled
            )

            # 清理任务数据
            self._tasks.clear()
            self._running_tasks.clear()

            self.logger.info("下载服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("下载服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查下载服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "total_tasks": len(self._tasks),
                "running_tasks": len(self._running_tasks),
                "pending_tasks": len(
                    [
                        t
                        for t in self._tasks.values()
                        if t.status == TaskStatus.PENDING.value
                    ]
                ),
                "completed_tasks": len(
                    [
                        t
                        for t in self._tasks.values()
                        if t.status == TaskStatus.COMPLETED.value
                    ]
                ),
                "failed_tasks": len(
                    [
                        t
                        for t in self._tasks.values()
                        if t.status == TaskStatus.FAILED.value
                    ]
                ),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("下载服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def create_download_task(
        self,
        symbol: str,
        exchange: str,
        start_date: datetime,
        end_date: datetime,
        data_type: str = "bar",
        frequency: str = "1m",
    ) -> DownloadTask:
        """创建下载任务."""
        try:
            async with self._task_lock:
                # 生成任务ID
                task_id = (
                    f"download_{symbol}_{exchange}_{int(datetime.now().timestamp())}"
                )

                # 创建下载任务
                download_task = DownloadTask(
                    task_id=task_id,
                    symbol=symbol,
                    exchange=exchange,
                    start_date=start_date,
                    end_date=end_date,
                    data_type=data_type,
                    frequency=frequency,
                    status=TaskStatus.PENDING.value,
                    progress=0.0,
                    error_message=None,
                )

                # 保存任务
                self._tasks[task_id] = download_task

                # 发送任务创建事件
                await self.event_service.emit_event(
                    "download_task_created", download_task.dict()
                )

                self.logger.info("下载任务创建成功: task_id=%s", task_id)
                return download_task

        except Exception as e:
            self.logger.error("创建下载任务失败: %s", e)
            raise

    async def get_download_tasks(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """获取下载任务列表."""
        try:
            # 过滤任务
            filtered_tasks = list(self._tasks.values())

            if status:
                filtered_tasks = [t for t in filtered_tasks if t.status == status]
            if symbol:
                filtered_tasks = [t for t in filtered_tasks if t.symbol == symbol]

            # 按创建时间倒序排序
            filtered_tasks.sort(key=lambda x: x.created_at, reverse=True)

            # 分页
            total = len(filtered_tasks)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_tasks = filtered_tasks[start_idx:end_idx]

            # 转换为字典格式
            tasks_data = [task.dict() for task in page_tasks]

            self.logger.info("获取下载任务列表: %d 个任务", len(tasks_data))
            return {
                "items": tasks_data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                    "has_next": page * page_size < total,
                    "has_prev": page > 1,
                },
            }

        except Exception as e:
            self.logger.error("获取下载任务列表失败: %s", e)
            raise

    async def get_download_task_detail(self, task_id: str) -> Optional[DownloadTask]:
        """获取下载任务详情."""
        try:
            task = self._tasks.get(task_id)
            if task:
                self.logger.info("获取下载任务详情: task_id=%s", task_id)
            else:
                self.logger.warning("下载任务不存在: task_id=%s", task_id)

            return task

        except Exception as e:
            self.logger.error("获取下载任务详情失败: %s", e)
            raise

    async def cancel_download_task(self, task_id: str) -> bool:
        """取消下载任务."""
        try:
            async with self._task_lock:
                task = self._tasks.get(task_id)
                if not task:
                    self.logger.warning("下载任务不存在: task_id=%s", task_id)
                    return False

                # 检查任务状态
                if task.status in [
                    TaskStatus.COMPLETED.value,
                    TaskStatus.FAILED.value,
                    TaskStatus.CANCELLED.value,
                ]:
                    self.logger.warning(
                        "任务已完成，无法取消: task_id=%s, status=%s",
                        task_id,
                        task.status,
                    )
                    return False

                # 更新任务状态
                task.status = TaskStatus.CANCELLED.value
                task.updated_at = datetime.now()

                # 如果有运行中的任务，取消它
                if task_id in self._running_tasks:
                    running_task = self._running_tasks[task_id]
                    running_task.cancel()
                    del self._running_tasks[task_id]

                # 发送任务取消事件
                await self.event_service.emit_event(
                    "download_task_cancelled", {"task_id": task_id}
                )

                self.logger.info("下载任务取消成功: task_id=%s", task_id)
                return True

        except Exception as e:
            self.logger.error("取消下载任务失败: %s", e)
            raise

    async def start_download_task(self, task_id: str) -> bool:
        """启动下载任务."""
        try:
            async with self._task_lock:
                task = self._tasks.get(task_id)
                if not task:
                    self.logger.warning("下载任务不存在: task_id=%s", task_id)
                    return False

                # 检查任务状态
                if task.status != TaskStatus.PENDING.value:
                    self.logger.warning(
                        "任务状态不正确，无法启动: task_id=%s, status=%s",
                        task_id,
                        task.status,
                    )
                    return False

                # 检查是否已有运行中的任务
                if task_id in self._running_tasks:
                    self.logger.warning("任务已在运行中: task_id=%s", task_id)
                    return False

                # 更新任务状态
                task.status = TaskStatus.RUNNING.value
                task.updated_at = datetime.now()

                # 创建异步任务
                running_task = asyncio.create_task(self._execute_download_task(task))
                self._running_tasks[task_id] = running_task

                self.logger.info("下载任务启动成功: task_id=%s", task_id)
                return True

        except Exception as e:
            self.logger.error("启动下载任务失败: %s", e)
            raise

    async def _execute_download_task(self, task: DownloadTask) -> None:
        """执行下载任务."""
        try:
            self.logger.info("开始执行下载任务: task_id=%s", task.task_id)

            # 模拟下载过程
            total_days = (task.end_date - task.start_date).days
            for day in range(total_days + 1):
                # 检查任务是否被取消
                if task.status == TaskStatus.CANCELLED.value:
                    self.logger.info("下载任务被取消: task_id=%s", task.task_id)
                    return

                # 更新进度
                progress = (day + 1) / (total_days + 1) * 100
                task.progress = progress
                task.updated_at = datetime.now()

                # 发送进度更新事件
                await self.event_service.emit_event(
                    "download_progress",
                    {
                        "task_id": task.task_id,
                        "progress": progress,
                        "status": task.status,
                    },
                )

                # 模拟下载延迟
                await asyncio.sleep(0.1)

            # 任务完成
            task.status = TaskStatus.COMPLETED.value
            task.progress = 100.0
            task.total_count = 1000  # 模拟数据
            task.downloaded_count = 1000
            task.updated_at = datetime.now()

            # 发送任务完成事件
            await self.event_service.emit_event("download_completed", task.dict())

            # 清理运行中的任务
            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]

            self.logger.info("下载任务执行完成: task_id=%s", task.task_id)

        except asyncio.CancelledError:
            # 任务被取消
            task.status = TaskStatus.CANCELLED.value
            task.updated_at = datetime.now()
            self.logger.info("下载任务执行被取消: task_id=%s", task.task_id)

        except Exception as e:
            # 任务失败
            task.status = TaskStatus.FAILED.value
            task.error_message = str(e)
            task.updated_at = datetime.now()

            # 发送任务失败事件
            await self.event_service.emit_event(
                "download_failed", {"task_id": task.task_id, "error": str(e)}
            )

            # 清理运行中的任务
            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]

            self.logger.error("下载任务执行失败: task_id=%s, error=%s", task.task_id, e)

    async def _cancel_all_running_tasks(self) -> None:
        """取消所有运行中的任务."""
        try:
            for task_id, running_task in list(self._running_tasks.items()):
                running_task.cancel()
                with suppress(asyncio.CancelledError):
                    await running_task

                # 更新任务状态
                if task_id in self._tasks:
                    self._tasks[task_id].status = TaskStatus.CANCELLED.value
                    self._tasks[task_id].updated_at = datetime.now()

            self._running_tasks.clear()
            self.logger.info("所有运行中的下载任务已取消")

        except Exception as e:
            self.logger.error("取消运行中的下载任务失败: %s", e)

    async def _handle_task_created(self, event: Dict[str, Any]) -> None:
        """处理任务创建事件."""
        try:
            task_data = event.get("data", {})
            task_id = task_data.get("task_id")

            if task_id:
                # 自动启动任务
                await self.start_download_task(task_id)
                self.logger.info("自动启动下载任务: task_id=%s", task_id)

        except Exception as e:
            self.logger.error("处理任务创建事件失败: %s", e)

    async def _handle_task_cancelled(self, event: Dict[str, Any]) -> None:
        """处理任务取消事件."""
        try:
            task_data = event.get("data", {})
            task_id = task_data.get("task_id")

            if task_id:
                await self.cancel_download_task(task_id)
                self.logger.info("处理任务取消事件: task_id=%s", task_id)

        except Exception as e:
            self.logger.error("处理任务取消事件失败: %s", e)

    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息."""
        try:
            stats = {
                "total_tasks": len(self._tasks),
                "running_tasks": len(self._running_tasks),
                "status_counts": {},
                "timestamp": datetime.now().isoformat(),
            }

            # 统计各状态任务数量
            for status in TaskStatus:
                count = len(
                    [t for t in self._tasks.values() if t.status == status.value]
                )
                stats["status_counts"][status.value] = count

            return stats

        except Exception as e:
            self.logger.error("获取任务统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["DownloadService", "TaskStatus"]
