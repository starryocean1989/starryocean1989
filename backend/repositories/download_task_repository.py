# -*- coding: utf-8 -*-
"""
下载任务仓库.

提供下载任务的数据库操作功能。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta

from .base_repository import InMemoryRepository

if TYPE_CHECKING:
    from backend.core.models import DownloadTask

logger = logging.getLogger(__name__)


class DownloadTaskRepository(InMemoryRepository["DownloadTask"]):
    """下载任务仓库."""

    def __init__(self):
        """初始化下载任务仓库."""
        super().__init__("download_tasks")

    async def get_by_symbol_exchange(
        self, symbol: str, exchange: str
    ) -> List["DownloadTask"]:
        """根据品种代码和交易所获取下载任务列表."""
        try:
            tasks = [
                t
                for t in self._data.values()
                if t.symbol == symbol and t.exchange == exchange
            ]
            self._log_operation(
                "get_by_symbol_exchange",
                symbol=symbol,
                exchange=exchange,
                count=len(tasks),
            )
            return tasks

        except Exception as e:
            self._log_error(
                "get_by_symbol_exchange", e, symbol=symbol, exchange=exchange
            )
            raise

    async def get_by_status(self, status: str) -> List["DownloadTask"]:
        """根据状态获取下载任务列表."""
        try:
            tasks = [t for t in self._data.values() if t.status == status]
            self._log_operation("get_by_status", status=status, count=len(tasks))
            return tasks

        except Exception as e:
            self._log_error("get_by_status", e, status=status)
            raise

    async def get_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> List["DownloadTask"]:
        """根据日期范围获取下载任务列表."""
        try:
            tasks = []
            for task in self._data.values():
                if (task.start_date >= start_date and task.start_date <= end_date) or (
                    task.end_date >= start_date and task.end_date <= end_date
                ):
                    tasks.append(task)

            self._log_operation(
                "get_by_date_range",
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                count=len(tasks),
            )
            return tasks

        except Exception as e:
            self._log_error(
                "get_by_date_range", e, start_date=start_date, end_date=end_date
            )
            raise

    async def get_running_tasks(self) -> List["DownloadTask"]:
        """获取运行中的任务列表."""
        try:
            tasks = [t for t in self._data.values() if t.status == "running"]
            self._log_operation("get_running_tasks", count=len(tasks))
            return tasks

        except Exception as e:
            self._log_error("get_running_tasks", e)
            raise

    async def get_pending_tasks(self) -> List["DownloadTask"]:
        """获取待处理的任务列表."""
        try:
            tasks = [t for t in self._data.values() if t.status == "pending"]
            self._log_operation("get_pending_tasks", count=len(tasks))
            return tasks

        except Exception as e:
            self._log_error("get_pending_tasks", e)
            raise

    async def get_completed_tasks(self) -> List["DownloadTask"]:
        """获取已完成的任务列表."""
        try:
            tasks = [t for t in self._data.values() if t.status == "completed"]
            self._log_operation("get_completed_tasks", count=len(tasks))
            return tasks

        except Exception as e:
            self._log_error("get_completed_tasks", e)
            raise

    async def get_failed_tasks(self) -> List["DownloadTask"]:
        """获取失败的任务列表."""
        try:
            tasks = [t for t in self._data.values() if t.status == "failed"]
            self._log_operation("get_failed_tasks", count=len(tasks))
            return tasks

        except Exception as e:
            self._log_error("get_failed_tasks", e)
            raise

    async def get_recent_tasks(self, limit: int = 10) -> List["DownloadTask"]:
        """获取最近的任务列表."""
        try:
            tasks = sorted(
                self._data.values(), key=lambda x: x.created_at, reverse=True
            )[:limit]
            self._log_operation("get_recent_tasks", limit=limit, count=len(tasks))
            return tasks

        except Exception as e:
            self._log_error("get_recent_tasks", e, limit=limit)
            raise

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Optional["DownloadTask"]:
        """更新任务状态."""
        try:
            task = await self.get_by_id(task_id)
            if not task:
                self.logger.warning("任务不存在: %s", task_id)
                return None

            # 更新状态
            task.status = status
            task.updated_at = datetime.now()

            if progress is not None:
                task.progress = progress

            if error_message is not None:
                task.error_message = error_message

            # 保存更新
            updated_task = await self.update(task)

            self._log_operation(
                "update_task_status", task_id=task_id, status=status, progress=progress
            )
            return updated_task

        except Exception as e:
            self._log_error("update_task_status", e, task_id=task_id, status=status)
            raise

    async def update_task_progress(
        self,
        task_id: str,
        progress: float,
        total_count: Optional[int] = None,
        downloaded_count: Optional[int] = None,
    ) -> Optional["DownloadTask"]:
        """更新任务进度."""
        try:
            task = await self.get_by_id(task_id)
            if not task:
                self.logger.warning("任务不存在: %s", task_id)
                return None

            # 更新进度信息
            task.progress = progress
            task.updated_at = datetime.now()

            if total_count is not None:
                task.total_count = total_count

            if downloaded_count is not None:
                task.downloaded_count = downloaded_count

            # 保存更新
            updated_task = await self.update(task)

            self._log_operation(
                "update_task_progress", task_id=task_id, progress=progress
            )
            return updated_task

        except Exception as e:
            self._log_error(
                "update_task_progress", e, task_id=task_id, progress=progress
            )
            raise

    async def cancel_task(self, task_id: str) -> Optional["DownloadTask"]:
        """取消任务."""
        try:
            task = await self.get_by_id(task_id)
            if not task:
                self.logger.warning("任务不存在: %s", task_id)
                return None

            # 只有运行中或待处理的任务可以取消
            if task.status not in ["pending", "running"]:
                self.logger.warning(
                    "任务状态不允许取消: %s, 状态=%s", task_id, task.status
                )
                return None

            # 更新状态
            task.status = "cancelled"
            task.updated_at = datetime.now()

            # 保存更新
            updated_task = await self.update(task)

            self._log_operation("cancel_task", task_id=task_id)
            return updated_task

        except Exception as e:
            self._log_error("cancel_task", e, task_id=task_id)
            raise

    async def get_tasks_by_filter(
        self, filters: Dict[str, Any], limit: int = 100, offset: int = 0
    ) -> List["DownloadTask"]:
        """根据过滤条件获取任务列表."""
        try:
            filtered_tasks = []

            for task in self._data.values():
                match = True
                for key, value in filters.items():
                    if hasattr(task, key):
                        task_value = getattr(task, key)
                        if task_value != value:
                            match = False
                            break
                    else:
                        match = False
                        break

                if match:
                    filtered_tasks.append(task)

            # 按创建时间倒序排序
            filtered_tasks.sort(key=lambda x: x.created_at, reverse=True)

            # 分页
            result = filtered_tasks[offset : offset + limit]
            self._log_operation(
                "get_tasks_by_filter", filters=filters, count=len(result)
            )
            return result

        except Exception as e:
            self._log_error("get_tasks_by_filter", e, filters=filters)
            raise

    async def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息."""
        try:
            total_tasks = len(self._data)

            # 统计各状态任务数量
            status_counts = {}
            for task in self._data.values():
                status = task.status
                if status not in status_counts:
                    status_counts[status] = 0
                status_counts[status] += 1

            # 统计品种数量
            symbols = len(
                set(f"{task.symbol}.{task.exchange}" for task in self._data.values())
            )

            # 统计数据类型
            data_types = len(set(task.data_type for task in self._data.values()))

            # 统计频率类型
            frequencies = len(set(task.frequency for task in self._data.values()))

            stats = {
                "total_tasks": total_tasks,
                "status_counts": status_counts,
                "symbols_count": symbols,
                "data_types_count": data_types,
                "frequencies_count": frequencies,
                "timestamp": datetime.now().isoformat(),
            }

            self._log_operation("get_task_statistics", stats=stats)
            return stats

        except Exception as e:
            self._log_error("get_task_statistics", e)
            raise

    async def cleanup_old_tasks(self, days: int = 30) -> int:
        """清理旧任务."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            tasks_to_delete = []

            for task in self._data.values():
                if task.created_at < cutoff_date and task.status in [
                    "completed",
                    "failed",
                    "cancelled",
                ]:
                    tasks_to_delete.append(task.task_id)

            # 删除旧任务
            deleted_count = 0
            for task_id in tasks_to_delete:
                if await self.delete(task_id):
                    deleted_count += 1

            self._log_operation(
                "cleanup_old_tasks", days=days, deleted_count=deleted_count
            )
            self.logger.info("清理旧任务完成: %d 个", deleted_count)
            return deleted_count

        except Exception as e:
            self._log_error("cleanup_old_tasks", e, days=days)
            raise


# 导出公共接口
__all__ = ["DownloadTaskRepository"]
