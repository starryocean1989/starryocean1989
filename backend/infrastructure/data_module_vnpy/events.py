# -*- coding: utf-8 -*-
"""
事件工具模块

提供vnpy事件推送的通用工具类和方法，从core.py迁移
"""

from datetime import datetime
from typing import Any, Dict, Optional
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
                "missing_symbols": overview.missing_symbols,
                "error_symbols": overview.error_symbols,
                "warning_symbols": overview.warning_symbols,
                "last_scan_time": overview.last_scan_time.isoformat(),
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_DATA_QUALITY_UPDATE, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送数据质量事件失败: %s", e)

