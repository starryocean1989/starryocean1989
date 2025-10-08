# -*- coding: utf-8 -*-
"""
下载服务 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道下载服务的具体问题。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.shared_services import ErrorSeverity, get_service_manager

logger = logging.getLogger(__name__)


class DownloadTask:
    """下载任务"""

    def __init__(self, task_id: str, task_type: str, symbol: str, exchange: str, **kwargs):
        """初始化下载任务

        Args:
            task_id: 任务ID
            task_type: 任务类型
            symbol: 品种代码
            exchange: 交易所代码
            **kwargs: 其他任务参数
        """
        self.task_id: str = task_id
        self.task_type: str = task_type
        self.symbol: str = symbol
        self.exchange: str = exchange
        self.status: str = "pending"
        self.progress: int = 0
        self.created_time: datetime = datetime.now()
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.kwargs: Dict[str, Any] = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "status": self.status,
            "progress": self.progress,
            "created_time": self.created_time.isoformat(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_message": self.error_message,
            "result": self.result,
        }


class DownloadService:
    """下载服务 - 专注于错误追踪和详细报告"""

    def __init__(self):
        """初始化下载服务"""
        self.service_manager = get_service_manager()
        self.logger = logging.getLogger(self.__class__.__name__)

        self._tasks: Dict[str, DownloadTask] = {}
        self._initialization_successful = False

        # 尝试初始化
        self._attempt_initialization()

    def _attempt_initialization(self):
        """尝试初始化下载服务"""
        try:
            self.service_manager.record_error(
                "DownloadService",
                "INITIALIZATION_START",
                "开始初始化下载服务",
                severity=ErrorSeverity.INFO,
            )

            # 初始化任务队列
            self._tasks.clear()

            self._initialization_successful = True
            self.service_manager.record_error(
                "DownloadService",
                "INITIALIZATION_SUCCESS",
                "下载服务初始化成功",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"下载服务初始化失败: {str(e)}"
            self.service_manager.record_error(
                "DownloadService",
                "INITIALIZATION_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )

    async def create_download_task(
        self,
        task_type: str,
        symbol: str,
        exchange: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """创建下载任务"""
        try:
            # 生成唯一任务ID
            task_id = f"task_{uuid.uuid4().hex[:8]}"

            self.service_manager.record_error(
                "DownloadService",
                "CREATE_TASK_START",
                f"开始创建下载任务: {task_id}, 类型={task_type}, 品种={symbol}.{exchange}",
                severity=ErrorSeverity.INFO,
            )

            # 创建任务对象
            task = DownloadTask(
                task_id=task_id,
                task_type=task_type,
                symbol=symbol,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                **kwargs,
            )

            # 保存任务
            self._tasks[task_id] = task

            # 模拟任务处理
            await self._process_task(task)

            self.service_manager.record_error(
                "DownloadService",
                "CREATE_TASK_SUCCESS",
                f"下载任务创建成功: {task_id}",
                severity=ErrorSeverity.INFO,
            )

            return task.to_dict()

        except Exception as e:
            error_msg = f"创建下载任务失败: {str(e)}"
            self.service_manager.record_error(
                "DownloadService",
                "CREATE_TASK_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return {"task_id": None, "status": "failed", "error_message": str(e)}

    async def _process_task(self, task: DownloadTask):
        """处理下载任务"""
        try:
            task.status = "running"
            task.start_time = datetime.now()

            # 模拟下载过程
            for progress in [25, 50, 75, 100]:
                task.progress = progress
                if progress == 100:
                    task.status = "completed"
                    task.end_time = datetime.now()
                    task.result = {
                        "downloaded_records": 1000,
                        "file_size": "2.5MB",
                        "download_time": "3.2s",
                    }

            self.service_manager.record_error(
                "DownloadService",
                "PROCESS_TASK_SUCCESS",
                f"任务处理完成: {task.task_id}",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.end_time = datetime.now()

            self.service_manager.record_error(
                "DownloadService",
                "PROCESS_TASK_EXCEPTION",
                f"任务处理失败: {task.task_id}, 错误: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    async def get_download_tasks(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取下载任务列表"""
        try:
            self.service_manager.record_error(
                "DownloadService",
                "GET_TASKS_START",
                f"开始获取任务列表，过滤条件: status={status}, task_type={task_type}",
                severity=ErrorSeverity.INFO,
            )

            # 过滤任务
            filtered_tasks = []
            for task in self._tasks.values():
                if status and task.status != status:
                    continue
                if task_type and task.task_type != task_type:
                    continue

                filtered_tasks.append(task.to_dict())

            # 按创建时间排序，最新的在前
            filtered_tasks.sort(key=lambda x: x["created_time"], reverse=True)

            # 限制数量
            if limit:
                filtered_tasks = filtered_tasks[:limit]

            self.service_manager.record_error(
                "DownloadService",
                "GET_TASKS_SUCCESS",
                f"获取任务列表成功，返回{len(filtered_tasks)}个任务",
                severity=ErrorSeverity.INFO,
            )

            return filtered_tasks

        except Exception as e:
            error_msg = f"获取任务列表失败: {str(e)}"
            self.service_manager.record_error(
                "DownloadService",
                "GET_TASKS_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return []

    async def get_task_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务详情"""
        try:
            task = self._tasks.get(task_id)

            if task:
                self.service_manager.record_error(
                    "DownloadService",
                    "GET_TASK_DETAIL_SUCCESS",
                    f"获取任务详情成功: {task_id}",
                    severity=ErrorSeverity.INFO,
                )
                return task.to_dict()

            self.service_manager.record_error(
                "DownloadService",
                "TASK_NOT_FOUND",
                f"任务不存在: {task_id}",
                severity=ErrorSeverity.WARNING,
            )
            return None

        except Exception as e:
            error_msg = f"获取任务详情失败: {str(e)}"
            self.service_manager.record_error(
                "DownloadService",
                "GET_TASK_DETAIL_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return None

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            task = self._tasks.get(task_id)

            if not task:
                self.service_manager.record_error(
                    "DownloadService",
                    "CANCEL_TASK_NOT_FOUND",
                    f"要取消的任务不存在: {task_id}",
                    severity=ErrorSeverity.WARNING,
                )
                return False

            if task.status in ["completed", "failed", "cancelled"]:
                self.service_manager.record_error(
                    "DownloadService",
                    "CANCEL_TASK_INVALID_STATUS",
                    f"任务状态不允许取消: {task_id}, 当前状态={task.status}",
                    severity=ErrorSeverity.WARNING,
                )
                return False

            task.status = "cancelled"
            task.end_time = datetime.now()

            self.service_manager.record_error(
                "DownloadService",
                "CANCEL_TASK_SUCCESS",
                f"任务取消成功: {task_id}",
                severity=ErrorSeverity.INFO,
            )
            return True

        except Exception as e:
            error_msg = f"取消任务失败: {str(e)}"
            self.service_manager.record_error(
                "DownloadService",
                "CANCEL_TASK_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        status_counts = {}
        for task in self._tasks.values():
            status = task.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "initialization_successful": self._initialization_successful,
            "total_tasks": len(self._tasks),
            "status_counts": status_counts,
        }

    def get_detailed_status_report(self) -> str:
        """获取详细状态报告"""
        report_lines = []
        report_lines.append("🔍 下载服务状态报告")
        report_lines.append("=" * 50)

        # 基本状态
        status_icon = "✅" if self._initialization_successful else "❌"
        report_lines.append(
            f"📊 初始化状态: {status_icon} {'成功' if self._initialization_successful else '失败'}"
        )

        # 任务统计
        report_lines.append(f"📋 总任务数: {len(self._tasks)}")

        if self._tasks:
            status_counts = {}
            for task in self._tasks.values():
                status = task.status
                status_counts[status] = status_counts.get(status, 0) + 1

            report_lines.append("📊 任务状态统计:")
            for status, count in status_counts.items():
                status_icons = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "failed": "❌",
                    "cancelled": "🚫",
                }
                icon = status_icons.get(status, "❓")
                report_lines.append(f"  {icon} {status}: {count}")
        else:
            report_lines.append("📋 暂无任务")

        return "\n".join(report_lines)


# 导出公共接口
__all__ = ["DownloadService", "DownloadTask"]
