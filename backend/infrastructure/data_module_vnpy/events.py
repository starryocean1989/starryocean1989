# -*- coding: utf-8 -*-
"""
事件工具模块

提供vnpy事件推送的通用工具类和方法，从core.py迁移
"""

from datetime import datetime
from typing import Optional
import logging

from vnpy.event import Event, EventEngine


# ==================== 事件类型常量 ====================

EVENT_CHINASTOCK_LOG = "eChinaStockLog"
EVENT_CHINASTOCK_VALIDATION = "eChinaStockValidation"
EVENT_CHINASTOCK_FILE_CHANGE = "eChinaStockFileChange"
EVENT_CHINASTOCK_DOWNLOAD = "eChinaStockDownload"
EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"
EVENT_DATA_SCAN_COMPLETE = "eDataScanComplete"
EVENT_LOCAL_DATA_INDEX_READY = "eLocalDataIndexReady"  # 🆕 本地数据索引就绪事件

# 🆕 数据质量感知阶段性推送事件
EVENT_QUALITY_SCAN_PHASE = "eQualityScanPhase"  # 阶段完成事件
EVENT_QUALITY_METRIC_UPDATE = "eQualityMetricUpdate"  # 单个指标更新事件

# 🆕 协程性能监控事件
EVENT_ASYNCIO_METRICS = "eAsyncioMetrics"  # 协程性能指标事件

# 应用名称
APP_NAME = "ChinaStock"


# ==================== 事件发布器基类 ====================


class EventPublisher:
    """通用事件发布器基类"""

    def __init__(self, event_engine: Optional[EventEngine] = None, app_name: str = APP_NAME):
        """
        初始化事件发布器

        Args:
            event_engine: vnpy事件引擎
            app_name: 应用名称
        """
        self.event_engine = event_engine
        self.app_name = app_name
        self.logger = logging.getLogger(__name__)

    def push_log_event(self, message: str, level: str = "INFO") -> None:
        """
        推送日志事件（从core.py迁移）

        Args:
            message: 日志消息
            level: 日志级别
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "message": message,
                "level": level,
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_LOG, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送日志事件失败: %s", e)


# ==================== 校验事件发布器 ====================


class ValidationEventPublisher(EventPublisher):
    """校验事件发布器"""

    def push_validation_event(self, summary) -> None:
        """
        推送校验事件（从core.py迁移）

        Args:
            summary: 校验汇总对象（ValidationSummary）
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "summary": {
                    "total_symbols": summary.total_symbols,
                    "valid_symbols": summary.valid_symbols,
                    "invalid_symbols": summary.invalid_symbols,
                    "total_errors": summary.total_errors,
                    "total_warnings": summary.total_warnings,
                    "check_time": summary.check_time.isoformat(),
                    "base_date": summary.base_date.isoformat(),
                },
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_VALIDATION, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送校验事件失败: %s", e)


# ==================== 下载事件发布器 ====================


class DownloadEventPublisher(EventPublisher):
    """下载事件发布器"""

    def push_download_event(
        self, download_type: str, status: str, count: int, error: Optional[str] = None
    ) -> None:
        """
        推送下载事件（从core.py迁移）

        Args:
            download_type: 下载类型
            status: 状态
            count: 数量
            error: 错误信息
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "download_type": download_type,
                "status": status,
                "count": count,
                "error": error,
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_DOWNLOAD, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送下载事件失败: %s", e)

    def push_download_progress_event(
        self, download_type: str, progress_pct: float, completed: int, total: int, current_item: str
    ) -> None:
        """
        推送下载进度事件（从core.py迁移）

        Args:
            download_type: 下载类型
            progress_pct: 进度百分比
            completed: 已完成数量
            total: 总数量
            current_item: 当前项目
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "download_type": download_type,
                "status": "progress",
                "progress": progress_pct,
                "completed": completed,
                "total": total,
                "current_item": current_item,
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_DOWNLOAD, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送下载进度事件失败: %s", e)


# ==================== 数据质量事件发布器 ====================


class QualityEventPublisher(EventPublisher):
    """数据质量事件发布器"""

    def push_quality_update_event(self, overview) -> None:
        """
        推送数据质量更新事件

        Args:
            overview: 质量概览对象（QualityOverview）
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "quality_score": overview.quality_score,
                "total_symbols": overview.total_symbols,
                "local_symbols": overview.total_symbols - overview.missing_symbols,
                "missing_symbols": overview.missing_symbols,
                "error_symbols": overview.error_symbols,
                "warning_symbols": overview.warning_symbols,
                "last_scan_time": overview.last_scan_time.isoformat(),
                "timestamp": datetime.now(),
                "engine": self.app_name,
                # 🔧 修复：添加所有必要字段
                "outdated_symbols": getattr(overview, "outdated_symbols", 0),
                "avg_gap_days": getattr(overview, "avg_gap_days", 0),
                "data_missing_symbols": getattr(overview, "data_missing_symbols", 0),
                "data_lagging_days": getattr(overview, "data_lagging_days", 0),
                "details": getattr(overview, "details", []),
            }

            event = Event(EVENT_DATA_QUALITY_UPDATE, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送数据质量事件失败: %s", e)


# ==================== 协程性能监控发布器 ====================


class AsyncioMetricsPublisher(EventPublisher):
    """协程性能指标发布器

    用于测量和上报 asyncio 事件循环延迟，帮助判断协程是否排队。
    """

    async def measure_and_publish_lag(self, source: str, threshold_ms: float = 5.0) -> float:
        """测量事件循环延迟并在超过阈值时上报

        v3.4 改进：综合测量协程排队情况
        1. 测量调度延迟（schedule lag）
        2. 统计pending tasks数量（真正的排队指标）
        3. 测量事件循环响应时间

        Args:
            source: 指标来源（模块名）
            threshold_ms: 上报阈值（毫秒），只在延迟超过此值时上报

        Returns:
            测量的延迟值（毫秒）
        """
        import time
        import asyncio

        # 1. 测量调度延迟（原有逻辑）
        start = time.perf_counter()
        await asyncio.sleep(0)
        schedule_lag_ms = (time.perf_counter() - start) * 1000

        # 2. 统计pending tasks数量（真正的排队指标）
        try:
            loop = asyncio.get_running_loop()
            all_tasks = asyncio.all_tasks(loop)

            # 统计各状态的task
            pending_count = 0
            running_count = 0
            done_count = 0

            for task in all_tasks:
                if task.done():
                    done_count += 1
                elif task.cancelled():
                    pass
                else:
                    # 未完成且未取消的任务
                    pending_count += 1
                    # 检查是否正在运行（通过coroutine状态）
                    try:
                        # 如果协程正在等待，pending_count递增
                        pass
                    except:
                        pass

            # 3. 测量事件循环响应时间（通过回调延迟）
            callback_start = time.perf_counter()
            callback_done = asyncio.Future()

            def callback_measure():
                if not callback_done.done():
                    callback_done.set_result(time.perf_counter() - callback_start)

            loop.call_soon(callback_measure)

            try:
                callback_lag_s = await asyncio.wait_for(callback_done, timeout=1.0)
                callback_lag_ms = callback_lag_s * 1000
            except asyncio.TimeoutError:
                callback_lag_ms = 1000.0  # 超时，说明事件循环严重阻塞

            # 计算综合延迟指标
            # 公式：调度延迟 + 回调延迟 + (pending_count / 100) * 调整因子
            # pending_count越多，说明协程排队越严重
            queue_pressure_ms = (pending_count / 100) * 10  # 每100个pending任务贡献10ms
            lag_ms = max(schedule_lag_ms, callback_lag_ms) + queue_pressure_ms

            # 只在延迟超过阈值时上报，避免刷屏
            if lag_ms > threshold_ms and self.event_engine:
                try:
                    event_data = {
                        "event_loop_lag_ms": round(lag_ms, 3),
                        "schedule_lag_ms": round(schedule_lag_ms, 3),
                        "callback_lag_ms": round(callback_lag_ms, 3),
                        "pending_tasks": pending_count,
                        "done_tasks": done_count,
                        "total_tasks": len(all_tasks),
                        "queue_pressure_ms": round(queue_pressure_ms, 3),
                        "source": source,
                        "timestamp": datetime.now().isoformat(),
                        "engine": self.app_name,
                    }
                    event = Event(EVENT_ASYNCIO_METRICS, event_data)
                    self.event_engine.put(event)
                except Exception as e:
                    self.logger.error("推送协程性能指标失败: %s", e)

            return lag_ms

        except Exception as e:
            self.logger.error("测量事件循环延迟失败: %s", e)
            # 降级到简单测量
            return schedule_lag_ms


# ==================== 导出 ====================

__all__ = [
    # 事件类型常量
    "EVENT_CHINASTOCK_LOG",
    "EVENT_CHINASTOCK_VALIDATION",
    "EVENT_CHINASTOCK_FILE_CHANGE",
    "EVENT_CHINASTOCK_DOWNLOAD",
    "EVENT_DATA_QUALITY_UPDATE",
    "EVENT_DATA_SCAN_COMPLETE",
    "EVENT_LOCAL_DATA_INDEX_READY",
    "EVENT_QUALITY_SCAN_PHASE",
    "EVENT_QUALITY_METRIC_UPDATE",
    "EVENT_ASYNCIO_METRICS",
    # 应用名称
    "APP_NAME",
    # 事件发布器
    "EventPublisher",
    "ValidationEventPublisher",
    "DownloadEventPublisher",
    "QualityEventPublisher",
    "AsyncioMetricsPublisher",
]
