# -*- coding: utf-8 -*-
"""
系统管理服务.

提供系统监控和运维管理功能，包括：
- 系统状态监控（CPU、内存、磁盘、网络）
- 性能指标展示（数据处理、策略执行、交易执行）
- 告警管理（规则配置、通知、处理流程）
- 服务健康检查（数据服务、策略服务、交易服务）
- 系统配置管理（参数、数据库、网络、安全）
- 日志管理（收集、查询、分析、监控）
- 系统诊断（性能诊断、错误诊断、网络诊断）
- 工具注册系统
"""

import asyncio
import gc
import json
import logging
import platform
import psutil
import sqlite3
import sys
import threading
import time
import unittest
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from backend.core.service_base import BaseService
from backend.core.models import UnifiedMarketData, get_data_model_manager
from backend.infrastructure.system_vnpy.system_monitor import SystemMonitor
from backend.infrastructure.system_vnpy.network_utils import NetworkTester, PortScanner
from backend.services.database_adapter import get_db_manager

# 事件常量
EVENT_LOG_RECORD = "eLogRecord"
EVENT_ALERT_CREATED = "eAlertCreated"
EVENT_ALERT_UPDATED = "eAlertUpdated"


# =============================================================================
# Part 1: 日志管理（从log_manager.py合并）
# =============================================================================

class LogDatabase:
    """日志数据库管理器（使用统一database_adapter）.

    提供日志记录的SQLite存储和查询功能。
    """

    def __init__(self, db_path: str = "data/terminal.db"):
        """初始化日志数据库.

        Args:
            db_path: 数据库文件路径（使用统一数据库）
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_manager = get_db_manager()
        self.logger = logging.getLogger(__name__)

        # system_logs表由DatabaseManager在_init_tables中创建
        self.logger.info("日志数据库使用统一database: %s", db_path)

    def add_log_record(self, log_data: Dict[str, Any]) -> None:
        """添加日志记录（使用统一database）.

        Args:
            log_data: 日志数据字典
        """
        try:
            # 使用database_adapter的统一接口
            self.db_manager.execute_update("""
                INSERT OR IGNORE INTO system_logs
                (timestamp, level, module, message, extra)
                VALUES (?, ?, ?, ?, ?)
            """, (
                log_data["timestamp"],
                log_data["level"],
                log_data["module"],
                log_data["message"],
                json.dumps({
                    "logger_name": log_data.get("logger_name"),
                    "function": log_data.get("function"),
                    "line": log_data.get("line"),
                    "exception": log_data.get("exception"),
                    "thread": log_data.get("thread"),
                    "filename": log_data.get("filename"),
                }),
            ))

        except Exception as e:
            # 静默失败，避免日志循环
            pass

    def query_logs(
        self,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
        logger_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询日志记录（使用统一database）.

        Args:
            level: 日志级别筛选
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            module: 模块名筛选
            logger_name: 日志记录器名筛选（注意：存在extra字段中）
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            日志记录列表
        """
        try:
            # 构建查询条件
            conditions = []
            params = []

            if level:
                conditions.append("level = ?")
                params.append(level)

            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)

            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)

            if module:
                conditions.append("module LIKE ?")
                params.append(f"%{module}%")

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 使用database_adapter查询
            query = f"""
                SELECT * FROM system_logs
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit} OFFSET {offset}
            """

            results = self.db_manager.execute_query(query, tuple(params) if params else None)

            # 解析extra字段
            for log in results:
                if log.get('extra'):
                    try:
                        extra_data = json.loads(log['extra'])
                        log.update(extra_data)
                    except:
                        pass

            return results

        except Exception as e:
            self.logger.error(f"日志查询失败: {e}")
            return []

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息（使用统一database）.

        Returns:
            统计信息字典
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=7)).isoformat()

            # 按级别统计
            level_results = self.db_manager.execute_query("""
                SELECT level, COUNT(*) as count
                FROM system_logs
                WHERE timestamp >= ?
                GROUP BY level
            """, (cutoff_time,))
            level_stats = {row["level"]: row["count"] for row in level_results}

            # 按模块统计
            module_results = self.db_manager.execute_query("""
                SELECT module, COUNT(*) as count
                FROM system_logs
                WHERE timestamp >= ? AND module IS NOT NULL
                GROUP BY module
                ORDER BY count DESC
                LIMIT 10
            """, (cutoff_time,))
            module_stats = [{"module": row["module"], "count": row["count"]} for row in module_results]

            # 总记录数
            total_results = self.db_manager.execute_query("SELECT COUNT(*) as total FROM system_logs")
            total_count = total_results[0]["total"] if total_results else 0

            return {
                "total_count": total_count,
                "level_stats": level_stats,
                "module_stats": module_stats,
                "recent_days": 7,
            }

        except Exception as e:
            self.logger.error(f"获取日志统计失败: {e}")
            return {}

    def cleanup_old_logs(self, retention_days: int = 30) -> int:
        """清理旧日志记录（使用统一database）.

        Args:
            retention_days: 保留天数

        Returns:
            删除的记录数量
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=retention_days)).isoformat()

            # 使用database_adapter删除
            deleted_count = self.db_manager.execute_update(
                "DELETE FROM system_logs WHERE timestamp < ?",
                (cutoff_time,)
            )

            self.logger.info(f"清理了 {deleted_count} 条旧日志")
            return deleted_count

        except Exception as e:
            self.logger.error(f"清理旧日志失败: {e}")
            return 0


# =============================================================================
# 日志记录处理器
# =============================================================================


class LogRecordHandler(logging.Handler):
    """自定义日志记录处理器.

    拦截所有日志记录，结构化存储并推送到事件引擎。
    """

    def __init__(self, log_manager: "LogManager"):
        """初始化日志记录处理器.

        Args:
            log_manager: 日志管理器实例
        """
        super().__init__()
        self.log_manager = log_manager
        self.setLevel(logging.DEBUG)

        # 设置格式化器
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录.

        Args:
            record: 日志记录
        """
        try:
            # 跳过日志系统本身的记录，避免递归
            if record.name.startswith('backend.services.system_manager.log_manager'):
                return

            # 增强递归检测：检查是否在日志处理过程中
            if hasattr(record, '_in_log_handler'):
                return

            # 标记当前记录正在被日志处理器处理
            record._in_log_handler = True

            # 提取异常信息
            exception_text = ""
            if record.exc_info:
                exception_text = self.formatException(record.exc_info)  # type: ignore

            # 构建日志数据
            log_data = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger_name": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "message": record.getMessage(),
                "exception": exception_text,
                "thread": record.thread,
                "thread_name": getattr(record, "threadName", ""),
                "process": record.process,
                "filename": record.filename,
            }

            # 只在非日志系统模块时才推送，避免递归
            if not record.name.startswith('backend.services.system_manager'):
                try:
                    # 推送到事件引擎（实时推送）
                    self.log_manager.publish_log_record(log_data)
                except Exception:
                    pass  # 推送失败时静默处理

            # 存储到数据库（批量插入）
            try:
                self.log_manager.add_log_record(log_data)
            except Exception:
                pass  # 存储失败时静默处理

        except Exception:
            pass  # 避免任何形式的递归记录错误
        finally:
            # 清理标记
            if hasattr(record, '_in_log_handler'):
                delattr(record, '_in_log_handler')


# =============================================================================
# 日志管理器
# =============================================================================


class LogManager:
    """日志系统管理器（使用统一database）.

    统一管理日志收集、存储和查询功能。
    """

    def __init__(
        self,
        db_path: str = "data/terminal.db",
        event_engine=None,
        retention_days: int = 30,
    ):
        """初始化日志管理器.

        Args:
            db_path: 日志数据库路径（使用统一数据库）
            event_engine: VnPy事件引擎实例
            retention_days: 日志保留天数
        """
        self.db_path = db_path
        self.event_engine = event_engine
        self.retention_days = retention_days

        # 日志记录器
        self.logger = logging.getLogger(__name__)

        # 使用统一database_adapter
        self.database = LogDatabase(db_path)

        # 批量插入缓冲区
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_lock = threading.Lock()
        self._batch_timer: Optional[threading.Timer] = None

    def initialize(self) -> bool:
        """初始化日志管理系统.

        Returns:
            是否初始化成功
        """
        try:
            init_start = time.time()

            print(f"[启动] 日志管理系统初始化开始...")

            # 创建自定义日志处理器
            log_handler = LogRecordHandler(self)

            # 添加到根日志记录器
            root_logger = logging.getLogger()
            root_logger.addHandler(log_handler)
            root_logger.setLevel(logging.DEBUG)

            total_time = time.time() - init_start
            print(f"[启动] ✅ 日志管理系统初始化完成，总耗时: {total_time:.3f}s")

            return True

        except Exception as e:
            print(f"[启动] ❌ 日志管理系统初始化异常: {e}")
            self.logger.error("日志管理系统初始化失败: %s", e)
            return False

    def shutdown(self) -> None:
        """关闭日志管理系统."""
        try:
            print(f"[DEBUG] 关闭日志管理系统...")

            # 刷新剩余的批量缓冲区
            self._flush_batch_buffer()

            # 取消所有定时器
            if self._batch_timer:
                self._batch_timer.cancel()

            # 移除日志处理器
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                if isinstance(handler, LogRecordHandler):
                    root_logger.removeHandler(handler)

            print(f"[DEBUG] ✅ 日志管理系统已关闭")
            self.logger.info("日志管理系统已关闭")

        except Exception as e:
            print(f"[DEBUG] 关闭日志管理系统失败: {e}")
            self.logger.error("关闭日志管理系统失败: %s", e)

    def add_log_record(self, log_data: Dict[str, Any]) -> None:
        """添加日志记录到缓冲区.

        Args:
            log_data: 日志数据
        """
        with self._batch_lock:
            self._batch_buffer.append(log_data)

            # 如果缓冲区达到阈值，立即刷新
            if len(self._batch_buffer) >= 10:
                self._flush_batch_buffer()

                # 重新启动批量定时器
                if self._batch_timer:
                    self._batch_timer.cancel()

                self._batch_timer = threading.Timer(1.0, self._flush_batch_buffer)
                self._batch_timer.daemon = True
                self._batch_timer.start()

    def publish_log_record(self, log_data: Dict[str, Any]) -> None:
        """发布日志记录到事件引擎.

        Args:
            log_data: 日志数据
        """
        if not self.event_engine:
            return

        try:
            # 检查事件引擎是否活跃
            if hasattr(self.event_engine, 'is_active') and not self.event_engine.is_active():
                return

            from vnpy.event import Event

            # 创建事件
            event = Event(EVENT_LOG_RECORD, log_data)

            # 发布事件
            self.event_engine.put(event)

        except Exception:
            pass  # 静默处理，避免递归

    def _flush_batch_buffer(self) -> None:
        """刷新批量缓冲区到数据库."""
        if not self._batch_buffer:
            return

        try:
            with self._batch_lock:
                # 获取当前缓冲区内容
                buffer_to_flush = self._batch_buffer.copy()
                self._batch_buffer.clear()

            # 批量插入到数据库
            for log_data in buffer_to_flush:
                try:
                    self.database.add_log_record(log_data)
                except Exception:
                    pass

        except Exception:
            pass

    def query_logs(
        self,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
        logger_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询日志记录."""
        return self.database.query_logs(
            level=level,
            start_time=start_time,
            end_time=end_time,
            module=module,
            logger_name=logger_name,
            limit=limit,
            offset=offset,
        )

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息."""
        return self.database.get_log_stats()

    def export_logs(
        self,
        file_path: str,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
    ) -> bool:
        """导出日志到文件."""
        try:
            # 查询日志记录
            logs = self.query_logs(
                level=level,
                start_time=start_time,
                end_time=end_time,
                module=module,
                limit=10000,
            )

            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                for log in logs:
                    f.write(f"[{log['timestamp']}] {log['level']} {log['module']}.{log['function_name']}:{log['line_number']} - {log['message']}\n")
                    if log['exception']:
                        f.write(f"Exception: {log['exception']}\n")

            self.logger.info("日志已导出到: %s，共 %d 条记录", file_path, len(logs))
            return True

        except Exception as e:
            self.logger.error("导出日志失败: %s", e)
            return False


# =============================================================================
# 全局实例和初始化函数
# =============================================================================

_log_manager: Optional[LogManager] = None
_log_manager_lock = threading.Lock()


def get_log_manager() -> LogManager:
    """获取全局日志管理器实例."""
    global _log_manager
    if _log_manager is None:
        with _log_manager_lock:
            if _log_manager is None:
                _log_manager = LogManager()
    return _log_manager


def initialize_logging_system(event_engine=None, config: Optional[Dict[str, Any]] = None) -> bool:
    """初始化日志系统（使用统一database）."""
    try:
        start_time = time.time()
        print(f"[启动] 日志系统初始化开始...")

        if config is None:
            config = {"db_path": "data/terminal.db", "retention_days": 30}

        global _log_manager
        with _log_manager_lock:
            _log_manager = LogManager(
                db_path=config.get("db_path", "data/terminal.db"),
                event_engine=event_engine,
                retention_days=config.get("retention_days", 30),
            )

        success = _log_manager.initialize()

        if success:
            total_time = time.time() - start_time
            print(f"[启动] ✅ 日志系统初始化成功，总耗时: {total_time:.3f}s")
            logging.info("日志系统初始化完成")
        else:
            total_time = time.time() - start_time
            print(f"[启动] ❌ 日志系统初始化失败，总耗时: {total_time:.3f}s")
            logging.error("日志系统初始化失败")

        return success

    except Exception as e:
        print(f"[启动] ❌ 初始化日志系统异常: {e}")
        logging.error("初始化日志系统失败: %s", e)
        return False


def shutdown_logging_system() -> None:
    """关闭日志系统."""
    global _log_manager
    if _log_manager:
        _log_manager.shutdown()
        _log_manager = None
        logging.info("日志系统已关闭")


__all__ = [
    "LogDatabase",
    "LogRecordHandler",
    "LogManager",
    "get_log_manager",
    "initialize_logging_system",
    "shutdown_logging_system",
    "EVENT_LOG_RECORD",
]



# =============================================================================
# Part 2: 告警管理（从alert_manager.py合并）
# =============================================================================

class AlertSeverity(Enum):
    """告警严重程度."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """告警状态."""

    NEW = "new"  # 新建
    ACKNOWLEDGED = "acknowledged"  # 已确认
    IN_PROGRESS = "in_progress"  # 处理中
    RESOLVED = "resolved"  # 已解决
    IGNORED = "ignored"  # 已忽略


class NotificationType(Enum):
    """通知类型."""

    DESKTOP = "desktop"  # 桌面通知
    EMAIL = "email"  # 邮件通知
    WEBHOOK = "webhook"  # Webhook通知
    LOG = "log"  # 日志通知


# =============================================================================
# 告警规则
# =============================================================================


class AlertRule:
    """告警规则."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        condition: str,
        severity: AlertSeverity,
        enabled: bool = True,
        priority: int = 0,
        group: str = "default",
        description: str = "",
        notification_types: Optional[List[NotificationType]] = None,
    ):
        """初始化告警规则."""
        self.rule_id = rule_id
        self.name = name
        self.condition = condition
        self.severity = severity
        self.enabled = enabled
        self.priority = priority
        self.group = group
        self.description = description
        self.notification_types = notification_types or [NotificationType.LOG]
        self.created_at = datetime.now()
        self.last_triggered: Optional[datetime] = None
        self.trigger_count = 0

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """评估规则条件."""
        if not self.enabled:
            return False

        try:
            # 使用eval评估条件（生产环境应使用更安全的方式）
            result = eval(self.condition, {"__builtins__": {}}, context)
            if result:
                self.last_triggered = datetime.now()
                self.trigger_count += 1
            return bool(result)

        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "condition": self.condition,
            "severity": self.severity.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "group": self.group,
            "description": self.description,
            "notification_types": [nt.value for nt in self.notification_types],
            "created_at": self.created_at.isoformat(),
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "trigger_count": self.trigger_count,
        }


class LogAlertRule(AlertRule):
    """日志告警规则."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        log_levels: Optional[List[str]] = None,
        modules: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        severity: AlertSeverity = AlertSeverity.ERROR,
        enabled: bool = True,
        priority: int = 0,
        group: str = "log_monitoring",
        description: str = "",
        suppression_window: int = 300,
    ):
        """初始化日志告警规则."""
        # 创建条件表达式
        conditions = []

        if log_levels:
            level_condition = " or ".join([f"level == '{level}'" for level in log_levels])
            conditions.append(f"({level_condition})")

        if modules:
            module_condition = " or ".join([f"module == '{module}'" for module in modules])
            conditions.append(f"({module_condition})")

        if keywords:
            keyword_condition = " or ".join([f"'{keyword}' in message" for keyword in keywords])
            conditions.append(f"({keyword_condition})")

        if not conditions:
            conditions.append("(level == 'ERROR' or level == 'CRITICAL')")

        condition = " and ".join(conditions)

        super().__init__(
            rule_id=rule_id,
            name=name,
            condition=condition,
            severity=severity,
            enabled=enabled,
            priority=priority,
            group=group,
            description=description,
        )

        self.log_levels = log_levels or ['ERROR', 'CRITICAL']
        self.modules = modules or []
        self.keywords = keywords or []
        self.suppression_window = suppression_window
        self._last_trigger_times: Dict[str, datetime] = {}

    def evaluate_log_record(self, log_data: Dict[str, Any]) -> bool:
        """评估日志记录是否触发告警."""
        if not self.enabled:
            return False

        try:
            # 检查日志级别
            if self.log_levels and log_data.get('level') not in self.log_levels:
                return False

            # 检查模块
            if self.modules and log_data.get('module') not in self.modules:
                return False

            # 检查关键字
            if self.keywords:
                message = log_data.get('message', '').lower()
                if not any(keyword.lower() in message for keyword in self.keywords):
                    return False

            # 检查抑制窗口
            suppression_key = f"{self.rule_id}:{log_data.get('module', '')}:{log_data.get('level', '')}"
            if suppression_key in self._last_trigger_times:
                last_time = self._last_trigger_times[suppression_key]
                if datetime.now() - last_time < timedelta(seconds=self.suppression_window):
                    return False

            # 更新抑制时间
            self._last_trigger_times[suppression_key] = datetime.now()

            return True

        except Exception:
            return False


# =============================================================================
# 告警对象
# =============================================================================


class Alert:
    """告警对象."""

    def __init__(
        self,
        alert_id: str,
        rule: AlertRule,
        message: str,
        context: Dict[str, Any],
    ):
        """初始化告警."""
        self.alert_id = alert_id
        self.rule = rule
        self.severity = rule.severity
        self.status = AlertStatus.NEW
        self.message = message
        self.context = context
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.acknowledged_at: Optional[datetime] = None
        self.resolved_at: Optional[datetime] = None
        self.notes: List[str] = []
        self.source_type: str = "unknown"
        self.source_data: Optional[Dict[str, Any]] = None

    def acknowledge(self, note: str = "") -> None:
        """确认告警."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now()
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[{self.updated_at.isoformat()}] 已确认: {note}")

    def resolve(self, note: str = "") -> None:
        """解决告警."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now()
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[{self.updated_at.isoformat()}] 已解决: {note}")

    def ignore(self, note: str = "") -> None:
        """忽略告警."""
        self.status = AlertStatus.IGNORED
        self.updated_at = datetime.now()
        if note:
            self.notes.append(f"[{self.updated_at.isoformat()}] 已忽略: {note}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule.rule_id,
            "rule_name": self.rule.name,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notes": self.notes,
        }


# =============================================================================
# 告警引擎
# =============================================================================


class AlertEngine:
    """告警引擎."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化告警引擎."""
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self.rules: Dict[str, AlertRule] = {}
        self.alerts: Dict[str, Alert] = {}
        self._lock = threading.Lock()
        self._original_evaluate_rules = None  # type: Optional[Any]

    def add_rule(self, rule: AlertRule) -> None:
        """添加告警规则."""
        with self._lock:
            self.rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> None:
        """移除告警规则."""
        with self._lock:
            self.rules.pop(rule_id, None)

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取告警规则."""
        return self.rules.get(rule_id)

    def get_all_rules(self) -> List[AlertRule]:
        """获取所有告警规则."""
        return list(self.rules.values())

    def evaluate_rules(self, context: Dict[str, Any]) -> List[Alert]:
        """评估所有规则."""
        triggered_alerts = []

        with self._lock:
            for rule in self.rules.values():
                if rule.evaluate(context):
                    alert = Alert(
                        alert_id=f"{rule.rule_id}_{int(time.time())}",
                        rule=rule,
                        message=f"{rule.name} 触发",
                        context=context,
                    )
                    self.alerts[alert.alert_id] = alert
                    triggered_alerts.append(alert)

        return triggered_alerts

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """获取告警."""
        return self.alerts.get(alert_id)

    def get_all_alerts(self) -> List[Alert]:
        """获取所有告警."""
        return list(self.alerts.values())

    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """更新告警规则."""
        with self._lock:
            rule = self.rules.get(rule_id)
            if not rule:
                return False

            # 更新规则属性
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)

            return True

    def delete_rule(self, rule_id: str) -> bool:
        """删除告警规则."""
        with self._lock:
            if rule_id in self.rules:
                del self.rules[rule_id]
                return True
            return False

    def get_alert_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[AlertSeverity] = None,
        status: Optional[AlertStatus] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """获取告警历史."""
        alerts = list(self.alerts.values())

        # 过滤时间范围
        if start_time:
            alerts = [alert for alert in alerts if alert.created_at >= start_time]
        if end_time:
            alerts = [alert for alert in alerts if alert.created_at <= end_time]

        # 过滤严重程度
        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]

        # 过滤状态
        if status:
            alerts = [alert for alert in alerts if alert.status == status]

        # 按创建时间排序并限制数量
        alerts.sort(key=lambda x: x.created_at, reverse=True)
        return alerts[:limit]

    def acknowledge_alert(self, alert_id: str, note: str = "") -> bool:
        """确认告警."""
        alert = self.get_alert(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()
        if note:
            alert.notes = getattr(alert, 'notes', []) + [f"[ACKNOWLEDGED] {note}"]

        return True

    def resolve_alert(self, alert_id: str, note: str = "") -> bool:
        """解决告警."""
        alert = self.get_alert(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()
        if note:
            alert.notes = getattr(alert, 'notes', []) + [f"[RESOLVED] {note}"]

        return True

    def configure_notifications(self, notification_type: NotificationType, config: Dict[str, Any]) -> bool:
        """配置通知设置."""
        # 这里可以添加通知配置逻辑
        # 目前只是一个占位符实现
        return True


# =============================================================================
# 告警数据库
# =============================================================================


class AlertDatabase:
    """告警数据库管理器（使用统一database_adapter）."""

    def __init__(self, db_path: str = "data/terminal.db"):
        """初始化告警数据库.

        Args:
            db_path: 数据库文件路径（使用统一数据库）
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_manager = get_db_manager()
        self.logger = logging.getLogger(__name__)

        # alert_rules和alert_records表由DatabaseManager在_init_tables中创建
        self.logger.info("告警数据库使用统一database: %s", db_path)

    def save_alert(self, alert: Alert) -> None:
        """保存告警记录（使用统一database）."""
        try:
            # 使用database_adapter保存
            self.db_manager.execute_update("""
                INSERT OR REPLACE INTO alert_records
                (alert_id, rule_id, severity, status, message, context,
                 created_at, updated_at, acknowledged_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.alert_id,
                alert.rule.rule_id,
                alert.severity.value,
                alert.status.value,
                alert.message,
                json.dumps({
                    "rule_name": alert.rule.name,
                    "context": alert.context,
                    "source_type": getattr(alert, 'source_type', 'log'),
                    "source_data": getattr(alert, 'source_data', None),
                    "notes": alert.notes,
                }) if (alert.context or alert.notes) else None,
                alert.created_at.isoformat(),
                alert.updated_at.isoformat(),
                alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                alert.resolved_at.isoformat() if alert.resolved_at else None,
            ))

        except Exception as e:
            self.logger.error(f"告警数据库保存失败: {e}")

    def get_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询告警记录（使用统一database）."""
        try:
            conditions = []
            params = []

            if status:
                conditions.append("status = ?")
                params.append(status)

            if severity:
                conditions.append("severity = ?")
                params.append(severity)

            if rule_id:
                conditions.append("rule_id = ?")
                params.append(rule_id)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT * FROM alert_records
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit} OFFSET {offset}
            """

            results = self.db_manager.execute_query(query, tuple(params) if params else None)

            # 解析context字段
            for alert in results:
                if alert.get('context'):
                    try:
                        context_data = json.loads(alert['context'])
                        alert.update(context_data)
                    except:
                        pass

            return results

        except Exception as e:
            self.logger.error(f"查询告警失败: {e}")
            return []

    def update_alert_status(self, alert_id: str, status: AlertStatus, note: str = "") -> bool:
        """更新告警状态（使用统一database）."""
        try:
            now = datetime.now().isoformat()

            if status == AlertStatus.ACKNOWLEDGED:
                self.db_manager.execute_update("""
                    UPDATE alert_records
                    SET status = ?, acknowledged_at = ?, updated_at = ?
                    WHERE alert_id = ?
                """, (status.value, now, now, alert_id))
            elif status == AlertStatus.RESOLVED:
                self.db_manager.execute_update("""
                    UPDATE alert_records
                    SET status = ?, resolved_at = ?, updated_at = ?
                    WHERE alert_id = ?
                """, (status.value, now, now, alert_id))
            else:
                self.db_manager.execute_update("""
                    UPDATE alert_records
                    SET status = ?, updated_at = ?
                    WHERE alert_id = ?
                """, (status.value, now, alert_id))

            return True

        except Exception as e:
            self.logger.error(f"更新告警状态失败: {e}")
            return False

    def get_unresolved_alerts(self) -> List[Dict[str, Any]]:
        """获取未解决的告警."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                cursor = conn.execute("""
                    SELECT * FROM alerts
                    WHERE status != 'resolved'
                    ORDER BY created_at DESC
                """)

                results = []
                for row in cursor.fetchall():
                    results.append(dict(row))

                return results

        except Exception as e:
            print(f"获取未解决告警失败: {e}")
            return []

    def delete_resolved_alerts(self, older_than_days: int = 30) -> int:
        """删除超过指定天数的已解决告警."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cutoff_time = (datetime.now().timestamp() - (older_than_days * 24 * 3600))

                    cursor = conn.execute("""
                        DELETE FROM alerts
                        WHERE status = 'resolved' AND created_at < ?
                    """, (cutoff_time,))

                    deleted_count = cursor.rowcount
                    conn.commit()

                    return deleted_count

        except Exception as e:
            print(f"删除已解决告警失败: {e}")
            return 0


# =============================================================================
# 告警事件发布器
# =============================================================================


class AlertEventPublisher:
    """告警事件发布器."""

    def __init__(self, event_engine, alert_database: AlertDatabase):
        """初始化告警事件发布器."""
        self.event_engine = event_engine
        self.alert_database = alert_database
        self._setup_alert_engine_listeners()

    def _setup_alert_engine_listeners(self) -> None:
        """设置告警引擎事件监听器."""
        try:
            alert_engine = AlertEngine()

            if hasattr(alert_engine, 'evaluate_rules') and not hasattr(alert_engine, '_original_evaluate_rules'):
                original_evaluate_rules = alert_engine.evaluate_rules

                def patched_evaluate_rules(context: Dict[str, Any]) -> List[Alert]:
                    try:
                        triggered_alerts = original_evaluate_rules(context)

                        for alert in triggered_alerts:
                            if hasattr(alert.rule, 'log_levels'):
                                alert.source_type = 'log'
                                alert.source_data = context

                                try:
                                    self.alert_database.save_alert(alert)
                                except Exception:
                                    pass

                                try:
                                    self.publish_alert_created(alert)
                                except Exception:
                                    pass

                        return triggered_alerts
                    except Exception:
                        return []

                alert_engine._original_evaluate_rules = original_evaluate_rules
                alert_engine.evaluate_rules = patched_evaluate_rules

        except Exception:
            pass

    def publish_alert_created(self, alert: Alert) -> None:
        """发布告警创建事件."""
        if not self.event_engine:
            return

        try:
            from vnpy.event import Event

            event_data = {
                "alert_id": alert.alert_id,
                "rule_id": alert.rule.rule_id,
                "rule_name": alert.rule.name,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "context": alert.context,
                "created_at": alert.created_at.isoformat(),
                "source_type": getattr(alert, 'source_type', 'unknown'),
            }

            event = Event(EVENT_ALERT_CREATED, event_data)
            self.event_engine.put(event)

        except Exception:
            pass

    def publish_alert_updated(self, alert: Alert) -> None:
        """发布告警更新事件."""
        if not self.event_engine:
            return

        try:
            from vnpy.event import Event

            event_data = {
                "alert_id": alert.alert_id,
                "rule_id": alert.rule.rule_id,
                "rule_name": alert.rule.name,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "context": alert.context,
                "updated_at": alert.updated_at.isoformat(),
                "source_type": getattr(alert, 'source_type', 'unknown'),
            }

            event = Event(EVENT_ALERT_UPDATED, event_data)
            self.event_engine.put(event)

        except Exception:
            pass


# =============================================================================
# 默认告警规则
# =============================================================================


def get_default_log_alert_rules() -> List[LogAlertRule]:
    """获取默认的日志告警规则."""
    rules = []

    # ERROR级别日志监控
    rules.append(LogAlertRule(
        rule_id="log_error_monitoring",
        name="ERROR级别日志监控",
        log_levels=["ERROR"],
        severity=AlertSeverity.ERROR,
        description="监控所有ERROR级别日志记录",
        suppression_window=60,
        enabled=True,
        priority=2,
    ))

    # CRITICAL级别日志监控
    rules.append(LogAlertRule(
        rule_id="log_critical_monitoring",
        name="CRITICAL级别日志监控",
        log_levels=["CRITICAL"],
        severity=AlertSeverity.CRITICAL,
        description="监控所有CRITICAL级别日志记录",
        suppression_window=30,
        enabled=True,
        priority=1,
    ))

    # 连接失败监控
    rules.append(LogAlertRule(
        rule_id="log_connection_failures",
        name="连接失败监控",
        keywords=["连接失败", "连接超时", "网络错误", "Connection failed", "Connection timeout"],
        severity=AlertSeverity.WARNING,
        description="监控连接相关的错误日志",
        suppression_window=120,
        enabled=True,
        priority=3,
    ))

    # 数据库错误监控
    rules.append(LogAlertRule(
        rule_id="log_database_errors",
        name="数据库错误监控",
        keywords=["数据库错误", "SQL错误", "连接池", "Database error", "SQL error"],
        severity=AlertSeverity.ERROR,
        description="监控数据库相关的错误日志",
        suppression_window=60,
        enabled=True,
        priority=2,
    ))

    return rules


def get_default_system_alert_rules() -> List[AlertRule]:
    """获取默认的系统告警规则."""
    rules = []

    rules.append(AlertRule(
        rule_id="system_cpu_high",
        name="CPU使用率过高",
        condition="cpu_percent > 90",
        severity=AlertSeverity.WARNING,
        enabled=True,
        priority=3,
        group="system_resource",
        description="CPU使用率超过90%时触发告警",
    ))

    rules.append(AlertRule(
        rule_id="system_memory_low",
        name="内存不足",
        condition="memory_percent > 85",
        severity=AlertSeverity.ERROR,
        enabled=True,
        priority=2,
        group="system_resource",
        description="内存使用率超过85%时触发告警",
    ))

    return rules


def get_default_business_alert_rules() -> List[AlertRule]:
    """获取默认的业务告警规则."""
    rules = []

    rules.append(AlertRule(
        rule_id="business_data_download_failure_rate",
        name="数据下载失败率过高",
        condition="download_failure_rate > 10",
        severity=AlertSeverity.ERROR,
        enabled=True,
        priority=3,
        group="data_quality",
        description="数据下载失败率超过10%时触发告警",
    ))

    return rules


# =============================================================================
# 全局实例和初始化函数
# =============================================================================

_alert_database: Optional[AlertDatabase] = None
_alert_database_lock = threading.Lock()


def get_alert_database() -> AlertDatabase:
    """获取全局告警数据库实例."""
    global _alert_database
    if _alert_database is None:
        with _alert_database_lock:
            if _alert_database is None:
                _alert_database = AlertDatabase()
    return _alert_database


def get_alert_engine() -> AlertEngine:
    """获取全局告警引擎实例."""
    return AlertEngine()


def initialize_alert_system(event_engine, config: Optional[Dict[str, Any]] = None) -> bool:
    """初始化扩展告警系统."""
    try:
        start_time = time.time()
        print(f"[启动] 告警系统初始化开始...")

        if config is None:
            config = {"db_path": "data/alerts.db", "suppression_window": 300}

        global _alert_database
        with _alert_database_lock:
            _alert_database = AlertDatabase(config.get("db_path", "data/alerts.db"))

        # 创建告警事件发布器
        alert_publisher = AlertEventPublisher(event_engine, _alert_database)

        # 初始化默认告警规则（延迟到后台线程）
        def _create_default_rules_async():
            time.sleep(2)
            try:
                alert_engine = AlertEngine()

                for rule in get_default_log_alert_rules():
                    alert_engine.add_rule(rule)

                print(f"[DEBUG] ✅ 默认日志告警规则创建完成")
            except Exception as e:
                print(f"[DEBUG] ❌ 创建默认告警规则失败: {e}")

        threading.Thread(target=_create_default_rules_async, daemon=True).start()

        total_time = time.time() - start_time
        print(f"[启动] ✅ 告警系统初始化完成，总耗时: {total_time:.3f}s")

        return True

    except Exception as e:
        print(f"[启动] ❌ 告警系统初始化失败，错误: {e}")
        return False


def shutdown_alert_system() -> None:
    """关闭扩展告警系统."""
    global _alert_database
    if _alert_database:
        _alert_database = None
        print("扩展告警系统已关闭")


__all__ = [
    # 枚举
    "AlertSeverity",
    "AlertStatus",
    "NotificationType",
    # 告警规则
    "AlertRule",
    "LogAlertRule",
    # 告警对象
    "Alert",
    # 告警引擎
    "AlertEngine",
    # 告警数据库
    "AlertDatabase",
    "AlertEventPublisher",
    # 默认规则
    "get_default_log_alert_rules",
    "get_default_system_alert_rules",
    "get_default_business_alert_rules",
    # 全局函数
    "get_alert_database",
    "get_alert_engine",
    "initialize_alert_system",
    "shutdown_alert_system",
    # 事件常量
    "EVENT_ALERT_CREATED",
    "EVENT_ALERT_UPDATED",
]



# =============================================================================
# Part 3: 性能监控（从performance_monitor.py合并）
# =============================================================================

class PerformanceMonitor:
    """性能监控器."""

    def __init__(self, config_service=None):
        """初始化性能监控器."""
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)

        # 监控数据
        self._metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._alerts: List[Dict[str, Any]] = []
        self._thresholds: Dict[str, float] = {}

        # 监控状态
        self._state = {
            "monitoring": False,
            "monitor_thread": None,
            "stop_event": threading.Event(),
        }

        # 初始化阈值
        self._init_thresholds()

    def _init_thresholds(self):
        """初始化监控阈值."""
        config = self.config_service.get("system", {}) if self.config_service else {}

        self._thresholds = {
            "cpu_percent": config.get("cpu_warning_threshold", 80.0),
            "memory_percent": config.get("memory_warning_threshold", 80.0),
            "response_time": config.get("response_time_threshold", 5.0),
            "error_rate": config.get("error_rate_threshold", 10.0),
            "memory_leak_threshold": config.get("memory_leak_threshold", 100.0),
        }

    def start_monitoring(self, interval: float = 5.0):
        """启动性能监控."""
        if self._state["monitoring"]:
            return

        self._state["monitoring"] = True
        self._state["stop_event"].clear()

        self._state["monitor_thread"] = threading.Thread(
            target=lambda: self._monitoring_loop(interval), daemon=True
        )
        self._state["monitor_thread"].start()
        self.logger.info("性能监控已启动，间隔: %s秒", interval)

    def stop_monitoring(self):
        """停止性能监控."""
        if not self._state["monitoring"]:
            return

        self._state["monitoring"] = False
        self._state["stop_event"].set()

        if self._state["monitor_thread"]:
            self._state["monitor_thread"].join(timeout=5)

        self.logger.info("性能监控已停止")

    def _monitoring_loop(self, interval: float):
        """监控循环."""
        while not self._state["stop_event"].is_set():
            try:
                self._collect_metrics()
                self._check_thresholds()
                self._cleanup_old_metrics()
                self._state["stop_event"].wait(interval)
            except Exception as e:
                self.logger.error("监控循环异常: %s", e)
                time.sleep(interval)

    def _collect_metrics(self):
        """收集性能指标."""
        timestamp = datetime.now()

        try:
            # 系统性能指标
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            system_metrics = {
                "timestamp": timestamp,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_mb": memory.used / (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024 * 1024 * 1024),
            }

            self._metrics["system"].append(system_metrics)

            # 应用性能指标
            app_metrics = {
                "timestamp": timestamp,
                "python_objects": len(gc.get_objects()),
                "thread_count": threading.active_count(),
                "response_time": self._measure_response_time(),
                "error_count": self._get_error_count(),
            }

            self._metrics["application"].append(app_metrics)

            # 核心模块指标
            core_metrics = self._collect_core_metrics()
            if core_metrics:
                self._metrics["core"].append(core_metrics)

        except Exception as e:
            self.logger.error("收集性能指标失败: %s", e)

    def _measure_response_time(self) -> float:
        """测量响应时间."""
        start_time = time.time()
        for _ in range(1000):
            pass
        return (time.time() - start_time) * 1000

    def _get_error_count(self) -> int:
        """获取错误计数."""
        return 0

    def _collect_core_metrics(self) -> Optional[Dict[str, Any]]:
        """收集核心模块指标."""
        try:
            metrics = {}

            data_manager = get_data_model_manager()
            if data_manager:
                stats = data_manager.get_statistics()
                metrics["data_model"] = stats

            return metrics if metrics else None

        except Exception as e:
            self.logger.error("收集核心模块指标失败: %s", e)
            return None

    def _check_thresholds(self):
        """检查阈值告警."""
        try:
            if not self._metrics["system"]:
                return

            latest = self._metrics["system"][-1]

            if latest["cpu_percent"] > self._thresholds["cpu_percent"]:
                self._add_alert(
                    "cpu_warning",
                    "高CPU使用率",
                    f"CPU使用率 {latest['cpu_percent']:.1f}% 超过阈值 {self._thresholds['cpu_percent']}%",
                )

            if latest["memory_percent"] > self._thresholds["memory_percent"]:
                self._add_alert(
                    "memory_warning",
                    "高内存使用率",
                    f"内存使用率 {latest['memory_percent']:.1f}% 超过阈值 {self._thresholds['memory_percent']}%",
                )

        except Exception as e:
            self.logger.error("检查阈值失败: %s", e)

    def _add_alert(self, alert_type: str, title: str, message: str):
        """添加告警."""
        alert = {
            "timestamp": datetime.now(),
            "type": alert_type,
            "title": title,
            "message": message,
            "resolved": False,
        }

        self._alerts.append(alert)

        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-500:]

        self.logger.warning("监控告警: %s - %s", title, message)

    def _cleanup_old_metrics(self):
        """清理旧的监控数据."""
        cutoff_time = datetime.now() - timedelta(hours=24)

        for category in self._metrics:
            if category in self._metrics:
                self._metrics[category] = [
                    m
                    for m in self._metrics[category]
                    if isinstance(m, dict) and m.get("timestamp") and m["timestamp"] >= cutoff_time
                ]

    def get_metrics(self, category: Optional[str] = None, hours: int = 1) -> Dict[str, Any]:
        """获取监控指标."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        if category:
            metrics = [
                m
                for m in self._metrics.get(category, [])
                if isinstance(m, dict) and m.get("timestamp") and m["timestamp"] >= cutoff_time
            ]
            return {category: metrics}

        result = {}
        for cat, data in self._metrics.items():
            result[cat] = [
                m
                for m in data
                if isinstance(m, dict) and m.get("timestamp") and m["timestamp"] >= cutoff_time
            ]

        return result

    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表."""
        return self._alerts[-limit:] if self._alerts else []

    def clear_alerts(self):
        """清空告警."""
        self._alerts.clear()
        self.logger.info("监控告警已清空")

    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要."""
        summary = {
            "monitoring_active": self._state["monitoring"],
            "total_alerts": len(self._alerts),
            "metrics_count": {category: len(metrics) for category, metrics in self._metrics.items()},
            "thresholds": self._thresholds.copy(),
        }

        if self._metrics["system"]:
            latest_metrics = [
                m for m in self._metrics["system"] if isinstance(m, dict) and m.get("timestamp")
            ]
            if latest_metrics:
                latest = latest_metrics[-1]
                summary["latest_system_metrics"] = {
                    "cpu_percent": latest.get("cpu_percent", 0),
                    "memory_percent": latest.get("memory_percent", 0),
                    "timestamp": latest.get("timestamp"),
                }

        return summary

    def get_all_metrics(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有指标数据（向后兼容）.

        Returns:
            所有类别的指标数据
        """
        return dict(self._metrics)

    def reset_category(self, category: str):
        """重置指定类别的指标（向后兼容）.

        Args:
            category: 类别名称
        """
        if category in self._metrics:
            self._metrics[category].clear()
            self.logger.info(f"已重置类别指标: {category}")

    def reset(self):
        """重置所有指标（向后兼容）."""
        self._metrics.clear()
        self._alerts.clear()
        self.logger.info("已重置所有监控指标")

    @property
    def is_monitoring(self) -> bool:
        """是否正在监控."""
        return self._state["monitoring"]

    @property
    def metrics_count(self) -> int:
        """指标数量."""
        return sum(len(metrics) for metrics in self._metrics.values())

    @property
    def alerts_count(self) -> int:
        """告警数量."""
        return len(self._alerts)


# =============================================================================
# 测试运行器
# =============================================================================


class TestStream:
    """测试输出流."""

    def __init__(self):
        """初始化测试输出流."""
        self.content = []

    def write(self, text):
        """写入文本到输出流."""
        self.content.append(text)

    def flush(self):
        """刷新输出流."""
        pass

    def getvalue(self):
        """获取输出流的内容."""
        return "".join(self.content)


class TestRunner:
    """测试运行器."""

    def __init__(self, config_service: Optional[Any] = None):
        """初始化测试运行器."""
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)
        self._test_results: Dict[str, Any] = {}

    def run_unit_tests(self, test_module: Optional[str] = None) -> Dict[str, Any]:
        """运行单元测试."""
        start_time = time.time()

        if test_module:
            try:
                module = __import__(test_module, fromlist=[""])
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromModule(module)
            except Exception as e:
                self.logger.error("加载测试模块失败 %s: %s", test_module, e)
                return {"success": False, "error": str(e)}
        else:
            suite = unittest.TestSuite()

        runner = unittest.TextTestRunner(verbosity=2, stream=TestStream())
        result = runner.run(suite)

        end_time = time.time()

        test_result = {
            "timestamp": datetime.now(),
            "duration": end_time - start_time,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "success": len(result.failures) == 0 and len(result.errors) == 0,
            "details": {
                "failures": [{"test": str(test), "error": error} for test, error in result.failures],
                "errors": [{"test": str(test), "error": error} for test, error in result.errors],
            },
        }

        self._test_results[datetime.now().isoformat()] = test_result
        self.logger.info(
            "单元测试完成: %s 个测试, %s 个失败, %s 个错误",
            test_result["tests_run"],
            test_result["failures"],
            test_result["errors"],
        )

        return test_result

    def get_test_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取测试结果."""
        results = list(self._test_results.values())
        results.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
        return results[:limit]

    @property
    def last_test_timestamp(self) -> Optional[datetime]:
        """最后测试时间戳."""
        if not self._test_results:
            return None
        last_key = max(self._test_results.keys())
        return self._test_results[last_key].get("timestamp")


# =============================================================================
# 监控管理器
# =============================================================================


class MonitoringManager:
    """监控管理器."""

    def __init__(self, config_service=None, terminal_engine=None):
        """初始化监控管理器."""
        self.config_service = config_service
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)

        # 初始化组件
        self.performance_monitor = PerformanceMonitor(config_service)
        self.test_runner = TestRunner(config_service)

        # 注意：health_checker在health_checker.py中
        self.health_checker = None  # 将在service.py中组合

        # 启动监控
        self.start_all_monitoring()

    def start_all_monitoring(self):
        """启动所有监控."""
        self.performance_monitor.start_monitoring()
        self.logger.info("监控管理器启动完成")

    def stop_all_monitoring(self):
        """停止所有监控."""
        self.performance_monitor.stop_monitoring()
        self.logger.info("监控管理器停止完成")

    def run_comprehensive_test(self) -> Dict[str, Any]:
        """运行综合测试."""
        self.logger.info("开始运行综合测试")

        # 健康检查（由外部提供）
        health_result = {}
        if self.health_checker:
            health_result = self.health_checker.check_system_health()

        # 性能指标
        performance_metrics = self.performance_monitor.get_metrics(hours=1)

        # 综合报告
        report = {
            "timestamp": datetime.now(),
            "health": health_result,
            "performance": performance_metrics,
            "summary": {
                "health_score": health_result.get("health_score", 0),
                "performance_ok": len(performance_metrics.get("system", [])) > 0,
            },
        }

        self.logger.info("综合测试完成 - 健康评分: %s", report["summary"]["health_score"])
        return report

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态."""
        return {
            "performance_monitor": {
                "active": self.performance_monitor.is_monitoring,
                "metrics_count": self.performance_monitor.metrics_count,
                "alerts_count": self.performance_monitor.alerts_count,
            },
            "test_runner": {"last_test": self.test_runner.last_test_timestamp},
        }


# 全局性能监控器实例（向后兼容）
performance_tracker = PerformanceMonitor()


__all__ = [
    "PerformanceMonitor",
    "TestRunner",
    "TestStream",
    "MonitoringManager",
    "performance_tracker",
]



# =============================================================================
# Part 4: 健康检查（从health_checker.py合并）
# =============================================================================

class HealthChecker:
    """健康检查器."""

    def __init__(self, main_engine: Optional[Any] = None):
        """初始化健康检查器."""
        self.main_engine = main_engine
        self.logger = logging.getLogger(__name__)
        self._check_results: Dict[str, Any] = {}

    def check_system_health(self) -> Dict[str, Any]:
        """检查系统健康状态."""
        checks = {
            "python": self._check_python_environment(),
            "memory": self._check_memory_usage(),
            "disk": self._check_disk_space(),
            "core_modules": self._check_core_modules(),
            "vnpy": self._check_vnpy_connection(),
        }

        health_score = self._calculate_health_score(checks)

        result = {
            "timestamp": datetime.now(),
            "health_score": health_score,
            "status": (
                "healthy" if health_score >= 80 else "warning" if health_score >= 60 else "critical"
            ),
            "checks": checks,
        }

        self._check_results[datetime.now().isoformat()] = result
        return result

    def _check_python_environment(self) -> Dict[str, Any]:
        """检查Python环境."""
        try:
            return {
                "status": "ok",
                "version": sys.version,
                "platform": platform.platform(),
                "python_bits": "64-bit" if sys.maxsize > 2**32 else "32-bit",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_memory_usage(self) -> Dict[str, Any]:
        """检查内存使用."""
        try:
            memory = psutil.virtual_memory()
            threshold = 80

            status = "ok" if memory.percent < threshold else "warning"

            return {
                "status": status,
                "percent": memory.percent,
                "used_mb": memory.used / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_disk_space(self) -> Dict[str, Any]:
        """检查磁盘空间."""
        try:
            disk = psutil.disk_usage("/")
            threshold = 90

            status = "ok" if disk.percent < threshold else "warning"

            return {
                "status": status,
                "percent": disk.percent,
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_core_modules(self) -> Dict[str, Any]:
        """检查核心模块."""
        checks = {}

        try:
            data_manager = get_data_model_manager()
            if data_manager:
                stats = data_manager.get_statistics()
                checks["data_manager"] = {"status": "ok", "stats": stats}
            else:
                checks["data_manager"] = {"status": "error", "error": "无法获取数据管理器"}
        except Exception as e:
            checks["data_manager"] = {"status": "error", "error": str(e)}

        return checks

    def _check_vnpy_connection(self) -> Dict[str, Any]:
        """检查VNPY连接."""
        try:
            from backend.services.vnpy_adapter.vnpy_imports import VNPY_AVAILABLE

            if not self.main_engine:
                return {"status": "error", "error": "MainEngine未初始化"}

            return {
                "status": "ok",
                "vnpy_available": VNPY_AVAILABLE,
                "main_engine_initialized": self.main_engine is not None,
                "engines": len(getattr(self.main_engine, "engines", {})),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _calculate_health_score(self, checks: Dict[str, Any]) -> float:
        """计算健康评分."""
        scores = []

        for check_name in ["python", "memory", "disk"]:
            if checks.get(check_name, {}).get("status") == "ok":
                scores.append(100)
            elif checks.get(check_name, {}).get("status") == "warning":
                scores.append(60)
            else:
                scores.append(0)

        core_modules = checks.get("core_modules", {})
        if core_modules.get("data_manager", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        if checks.get("vnpy", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        return (sum(scores) / len(scores)) if scores else 0

    def get_check_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取检查历史."""
        results = list(self._check_results.values())
        results.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
        return results[:limit]

    @property
    def last_check_timestamp(self) -> Optional[datetime]:
        """最后检查时间戳."""
        if not self._check_results:
            return None
        last_key = max(self._check_results.keys())
        return self._check_results[last_key].get("timestamp")


__all__ = [
    "HealthChecker",
]



# =============================================================================
# Part 5: 异步任务管理（从async_task_manager.py合并）
# =============================================================================

class AsyncTaskManager:
    """异步任务管理器."""

    def __init__(self, max_workers: int = 10):
        """初始化异步任务管理器."""
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.loop = None
        self.logger = logging.getLogger(__name__)
        self._tasks: Dict[str, Any] = {}
        self._results: Dict[str, Any] = {}

    def start_event_loop(self):
        """启动事件循环."""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            def run_loop():
                try:
                    if self.loop is not None:
                        self.loop.run_forever()
                except Exception as e:
                    self.logger.error("事件循环异常: %s", e)

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()
            self.logger.info("异步任务管理器启动完成")

        except Exception as e:
            self.logger.error("启动事件循环失败: %s", e)

    def stop_event_loop(self):
        """停止事件循环."""
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.executor.shutdown(wait=True)
                self.logger.info("异步任务管理器停止完成")
            except Exception as e:
                self.logger.error("停止事件循环失败: %s", e)

    def get_task_stats(self) -> Dict[str, int]:
        """获取任务统计信息."""
        return {
            "active_tasks": len(self._tasks),
            "completed_tasks": len(self._results),
            "max_workers": self.max_workers,
        }

    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        """提交异步任务."""

        def task_wrapper():
            try:
                result = func(*args, **kwargs)
                self._results[task_id] = {"success": True, "result": result}
            except Exception as e:
                self.logger.error("任务执行失败 %s: %s", task_id, e)
                self._results[task_id] = {"success": False, "error": str(e)}

        future = self.executor.submit(task_wrapper)
        self._tasks[task_id] = future
        return task_id

    def submit_asyncio_task(self, coroutine_func: Callable, *args, **kwargs) -> str:
        """提交异步协程任务."""
        if not self.loop:
            self.start_event_loop()

        task_id = f"asyncio_{len(self._tasks)}"

        async def wrapper():
            try:
                if asyncio.iscoroutinefunction(coroutine_func):
                    result = await coroutine_func(*args, **kwargs)
                else:
                    result = coroutine_func(*args, **kwargs)
                self._results[task_id] = {"success": True, "result": result}
            except Exception as e:
                self.logger.error("异步任务执行失败 %s: %s", task_id, e)
                self._results[task_id] = {"success": False, "error": str(e)}

        if self.loop is None:
            raise RuntimeError("事件循环未初始化")
        future = asyncio.run_coroutine_threadsafe(wrapper(), self.loop)
        self._tasks[task_id] = future
        return task_id

    def get_task_result(self, task_id: str, timeout: float = 10.0) -> Any:
        """获取任务结果."""
        if task_id not in self._tasks:
            return {"success": False, "error": "任务不存在"}

        future = self._tasks[task_id]

        try:
            if hasattr(future, "result"):
                result = future.result(timeout=timeout)
            else:
                result = future.get(timeout=timeout) if hasattr(future, "get") else None

            if task_id in self._results:
                task_result = self._results.pop(task_id)
                return task_result

            return {"success": True, "result": result}

        except TimeoutError as e:
            return {"success": False, "error": str(e)}
        finally:
            if task_id in self._tasks:
                del self._tasks[task_id]

    def cancel_task(self, task_id: str) -> bool:
        """取消任务."""
        if task_id not in self._tasks:
            return False

        future = self._tasks[task_id]
        cancelled = future.cancel()

        if cancelled:
            if task_id in self._results:
                del self._results[task_id]
            del self._tasks[task_id]

        return cancelled


# =============================================================================
# 异步数据处理器
# =============================================================================


class AsyncDataProcessor:
    """异步数据处理器."""

    def __init__(self, task_manager: AsyncTaskManager):
        """初始化异步数据处理器."""
        self.task_manager = task_manager
        self.logger = logging.getLogger(__name__)

    async def process_market_data_async(
        self, data_list: List["UnifiedMarketData"]
    ) -> Dict[str, Any]:
        """异步处理行情数据."""
        results = {}

        batch_size = 100
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i : i + batch_size]
            await asyncio.sleep(0.01)

            for data in batch:
                symbol = data.symbol
                if symbol not in results:
                    results[symbol] = []

                results[symbol].append(
                    {
                        "datetime": data.datetime,
                        "price": data.close_price,
                        "volume": data.volume,
                    }
                )

        return results

    def process_data_sync(self, data_list: List["UnifiedMarketData"]) -> Dict[str, Any]:
        """同步处理数据（包装为异步）."""
        try:
            future = self.task_manager.executor.submit(self._sync_process_data, data_list)
            return future.result(timeout=30)
        except Exception as e:
            self.logger.error("同步数据处理失败: %s", e)
            return {}

    def _sync_process_data(self, data_list: List["UnifiedMarketData"]) -> Dict[str, Any]:
        """实际的数据处理逻辑."""
        results = {}

        for data in data_list:
            symbol = data.symbol
            if symbol not in results:
                results[symbol] = []

            results[symbol].append(
                {
                    "datetime": data.datetime,
                    "price": data.close_price,
                    "volume": data.volume,
                }
            )

        return results


__all__ = [
    "AsyncTaskManager",
    "AsyncDataProcessor",
]



# =============================================================================
# Part 6: 系统管理服务主类
# =============================================================================


class SystemManagerService(BaseService):
    """系统管理服务.

    提供完整的系统监控和管理功能，支持8个子功能：
    1. 系统状态实时监控
    2. 性能指标展示
    3. 告警信息管理
    4. 服务健康检查
    5. 系统配置管理
    6. 日志管理
    7. 系统诊断
    8. 工具集合
    """

    def __init__(self):
        """初始化系统管理服务."""
        super().__init__()

        # 监控数据
        self.monitoring_data: Dict[str, Any] = {}

        # 告警规则
        self.alert_rules: List[Dict[str, Any]] = []

        # 告警历史
        self.alert_history: List[Dict[str, Any]] = []

        # 注册的工具
        self.registered_tools: Dict[str, Any] = {}

        # system_vnpy工具
        self.system_monitor = SystemMonitor()
        self.network_tester = NetworkTester()
        self.port_scanner = PortScanner()

        # 数据读取任务控制
        self._tdx_reader_stop_flag = False

        # ========== 新的模块化组件（从core迁移） ==========

        # 日志管理器
        self.log_manager = get_log_manager()

        # 告警引擎
        self.alert_engine = get_alert_engine()

        # 性能监控器
        self.performance_monitor = PerformanceMonitor()
        self.performance_tracker = self.performance_monitor  # 向后兼容别名

        # 健康检查器
        self.health_checker = HealthChecker(self.main_engine)

        # 测试运行器
        self.test_runner = TestRunner()

        # 新增：诊断工具
        from backend.infrastructure.system_vnpy.diagnostic_tools import (
            LogAnalyzer,
            PerformanceAnalyzer,
            AutoFixer,
        )

        self.log_analyzer = LogAnalyzer()
        self.performance_analyzer = PerformanceAnalyzer()
        self.auto_fixer = AutoFixer()

        # 新增：服务管理工具
        from backend.infrastructure.system_vnpy.service_manager import (
            ServiceHealthChecker,
            ServiceRestarter,
        )

        self.service_health_checker = ServiceHealthChecker()
        self.service_restarter = ServiceRestarter()

        # 新增：进程监控工具
        from backend.infrastructure.system_vnpy.process_monitor import (
            ProcessMonitor,
            BottleneckAnalyzer,
        )

        self.process_monitor = ProcessMonitor()
        self.bottleneck_analyzer = BottleneckAnalyzer()

        self.logger.info("系统管理服务已创建")

    def _do_initialize(self) -> bool:
        """初始化系统管理服务."""
        try:
            self.logger.info("初始化系统管理服务...")

            # 初始化监控（跳过，避免阻塞）
            self.logger.info("系统监控初始化已跳过（避免启动阻塞）")

            # ✅ 单进程多线程架构：使用线程安全的UI更新机制
            # 日志和告警系统在主进程中运行，但通过Qt信号槽确保线程安全
            self.logger.info("✅ 使用线程安全的单进程多线程架构")

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭系统管理服务."""
        try:
            # 停止监控
            self._stop_monitoring()
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "monitoring_active": len(self.monitoring_data) > 0,
            "alert_rule_count": len(self.alert_rules),
            "tool_count": len(self.registered_tools),
        }

    def _init_monitoring(self):
        """初始化监控."""
        try:
            # 跳过监控初始化，避免阻塞
            self.logger.info("系统监控初始化已跳过（避免启动阻塞）")
        except Exception as e:
            self.logger.error("系统监控初始化失败: %s", e)

    def _stop_monitoring(self):
        """停止监控."""
        self.monitoring_data.clear()

    def _init_logging_and_alert_system(self) -> None:
        """初始化日志和告警系统.

        在单进程多线程架构中，日志和告警系统在主进程中运行，
        通过线程安全的机制确保UI更新正确。
        """
        # 单进程多线程架构：日志和告警系统在主进程中运行
        self.logger.info("日志和告警系统在主进程中运行（单进程多线程架构）")

    def _load_default_alert_rules(self):
        """加载默认告警规则."""
        # 使用新的告警引擎
        try:
            # CPU使用率过高规则
            cpu_rule = AlertRule(
                rule_id="rule_cpu_high",
                name="CPU使用率过高",
                condition="cpu_percent > 90",
                severity=AlertSeverity.WARNING,
                enabled=True,
                priority=1,
                group="system_resource",
                description="CPU使用率超过90%时触发告警",
            )
            self.alert_engine.add_rule(cpu_rule)

            # 内存使用率过高规则
            memory_rule = AlertRule(
                rule_id="rule_memory_high",
                name="内存使用率过高",
                condition="memory_percent > 90",
                severity=AlertSeverity.WARNING,
                enabled=True,
                priority=1,
                group="system_resource",
                description="内存使用率超过90%时触发告警",
            )
            self.alert_engine.add_rule(memory_rule)

            # 磁盘使用率过高规则
            disk_rule = AlertRule(
                rule_id="rule_disk_high",
                name="磁盘使用率过高",
                condition="disk_percent > 85",
                severity=AlertSeverity.WARNING,
                enabled=True,
                priority=2,
                group="system_resource",
                description="磁盘使用率超过85%时触发告警",
            )
            self.alert_engine.add_rule(disk_rule)

            # 服务离线告警规则
            service_offline_rule = AlertRule(
                rule_id="rule_service_offline",
                name="服务离线告警",
                condition="service_offline",  # 特殊条件类型
                severity=AlertSeverity.CRITICAL,
                enabled=True,
                priority=1,
                group="service",
                description="当关键服务离线时触发告警",
            )
            self.alert_engine.add_rule(service_offline_rule)

            self.logger.info(
                "默认告警规则已加载（CPU、内存、磁盘、服务离线监控规则，支持特殊条件评估）"
            )
        except Exception as e:
            self.logger.error("加载默认告警规则失败: %s", str(e))

    # ==================== 性能指标展示（三维度：数据处理、策略执行、交易执行） ====================

    def get_performance_indicators(self) -> Dict[str, Any]:
        """获取三维度性能指标.

        返回数据处理、策略执行、交易执行三个维度的性能指标，
        对应需求文档链条1.2.1。

        Returns:
            Dict: 包含三维度性能指标的字典

        Example:
            >>> result = service.get_performance_indicators()
            >>> print(result["data_processing"]["avg_query_time_ms"])
        """
        try:
            all_metrics = self.performance_tracker.get_all_metrics()

            # 数据处理性能
            data_processing = self._calculate_data_processing_metrics(
                all_metrics.get("data_processing", [])
            )

            # 策略执行性能
            strategy_execution = self._calculate_strategy_execution_metrics(
                all_metrics.get("strategy_execution", [])
            )

            # 交易执行性能
            trading_execution = self._calculate_trading_execution_metrics(
                all_metrics.get("trading_execution", [])
            )

            return {
                "success": True,
                "performance_indicators": {
                    "data_processing": data_processing,
                    "strategy_execution": strategy_execution,
                    "trading_execution": trading_execution,
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self._log_error("获取性能指标", e)
            return {"success": False, "message": str(e)}

    def _calculate_data_processing_metrics(
        self, metrics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算数据处理性能指标.

        Args:
            metrics: 数据处理类别的原始指标

        Returns:
            Dict: 聚合后的数据处理性能指标
        """
        # 聚合查询时间
        query_times = []
        download_speeds = []
        cache_hits = 0
        cache_misses = 0

        for metric_data in metrics:
            metric_name = metric_data.get("name", "")
            if "query" in metric_name.lower():
                query_times.append(metric_data.get("avg_time_ms", 0))
            elif "download" in metric_name.lower():
                # 下载速度估算（基于数据量/时间）
                avg_time = metric_data.get("avg_time_ms", 0)
                if avg_time > 0:
                    # 假设平均每次下载1MB数据
                    download_speeds.append(1000 / avg_time)  # MB/s
            elif "cache" in metric_name.lower():
                total_calls = metric_data.get("total_calls", 0)
                success_rate = metric_data.get("success_rate", 100)
                cache_hits += int(total_calls * success_rate / 100)
                cache_misses += int(total_calls * (100 - success_rate) / 100)

        avg_query_time = sum(query_times) / len(query_times) if query_times else 0.0
        avg_download_speed = sum(download_speeds) / len(download_speeds) if download_speeds else 0.0
        cache_hit_rate = (
            cache_hits / (cache_hits + cache_misses) * 100
            if (cache_hits + cache_misses) > 0
            else 0.0
        )

        return {
            "avg_query_time_ms": round(avg_query_time, 2),
            "avg_download_speed_mbps": round(avg_download_speed, 2),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "total_queries": sum(m.get("total_calls", 0) for m in metrics),
            "metrics_detail": metrics,
        }

    def _calculate_strategy_execution_metrics(
        self, metrics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算策略执行性能指标.

        Args:
            metrics: 策略执行类别的原始指标

        Returns:
            Dict: 聚合后的策略执行性能指标
        """
        signal_latencies = []
        bar_processing_times = []
        error_counts = []
        total_calls_list = []

        for metric_data in metrics:
            metric_name = metric_data.get("name", "")
            avg_time = metric_data.get("avg_time_ms", 0)
            total_calls = metric_data.get("total_calls", 0)
            success_rate = metric_data.get("success_rate", 100)

            if "signal" in metric_name.lower() or "order" in metric_name.lower():
                signal_latencies.append(avg_time)
            elif "on_bar" in metric_name.lower() or "process" in metric_name.lower():
                bar_processing_times.append(avg_time)

            # 统计错误
            if total_calls > 0:
                error_count = int(total_calls * (100 - success_rate) / 100)
                error_counts.append(error_count)
                total_calls_list.append(total_calls)

        avg_signal_latency = (
            sum(signal_latencies) / len(signal_latencies) if signal_latencies else 0.0
        )
        avg_bar_processing = (
            sum(bar_processing_times) / len(bar_processing_times) if bar_processing_times else 0.0
        )

        # 计算错误率和吞吐量
        total_calls_sum = sum(total_calls_list)
        total_errors = sum(error_counts)
        error_rate = (total_errors / total_calls_sum * 100) if total_calls_sum > 0 else 0.0

        # 策略吞吐量（假设基于总调用次数）
        strategy_throughput = total_calls_sum  # 实际应该基于时间窗口计算

        return {
            "avg_signal_latency_ms": round(avg_signal_latency, 2),
            "on_bar_processing_time_ms": round(avg_bar_processing, 2),
            "strategy_throughput": strategy_throughput,  # 新增：策略吞吐量
            "error_rate": round(error_rate, 2),  # 新增：错误率
            "total_calls": total_calls_sum,
            "metrics_detail": metrics,
        }

    def _calculate_trading_execution_metrics(
        self, metrics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算交易执行性能指标.

        Args:
            metrics: 交易执行类别的原始指标

        Returns:
            Dict: 聚合后的交易执行性能指标
        """
        order_latencies = []
        order_success_rates = []
        position_update_delays = []

        for metric_data in metrics:
            metric_name = metric_data.get("name", "")
            avg_time = metric_data.get("avg_time_ms", 0)
            success_rate = metric_data.get("success_rate", 100)

            if "order" in metric_name.lower() or "send" in metric_name.lower():
                order_latencies.append(avg_time)
                order_success_rates.append(success_rate)
            elif "position" in metric_name.lower() or "update" in metric_name.lower():
                position_update_delays.append(avg_time)

        avg_order_latency = sum(order_latencies) / len(order_latencies) if order_latencies else 0.0
        avg_order_success_rate = (
            sum(order_success_rates) / len(order_success_rates) if order_success_rates else 100.0
        )
        avg_position_update_delay = (
            sum(position_update_delays) / len(position_update_delays)
            if position_update_delays
            else 0.0
        )

        return {
            "avg_order_latency_ms": round(avg_order_latency, 2),
            "order_success_rate": round(avg_order_success_rate, 2),
            "position_update_delay_ms": round(avg_position_update_delay, 2),
            "total_orders": sum(m.get("total_calls", 0) for m in metrics),
            "metrics_detail": metrics,
        }

    def reset_performance_metrics(self, category: Optional[str] = None) -> Dict[str, Any]:
        """重置性能指标.

        Args:
            category: 指标分类（data_processing/strategy_execution/trading_execution）
                     如不指定则重置所有分类

        Returns:
            Dict: 重置结果
        """
        try:
            if category:
                self.performance_tracker.reset_category(category)
                message = f"性能指标已重置: {category}"
            else:
                self.performance_tracker.reset()
                message = "所有性能指标已重置"

            self.logger.info(message)

            return {
                "success": True,
                "message": message,
            }

        except Exception as e:
            self._log_error("重置性能指标", e)
            return {"success": False, "message": str(e)}

    # ==================== 系统状态监控 ====================

    def update_system_metrics(self) -> Dict[str, Any]:
        """更新系统指标.

        Returns:
            Dict: 系统指标
        """
        try:
            # 使用system_vnpy的SystemMonitor获取系统资源使用情况
            resource_usage = self.system_monitor.get_resource_usage()

            metrics = {
                "cpu_percent": resource_usage.cpu_percent,
                "memory_percent": resource_usage.memory_percent,
                "memory_available": None,  # 可从system_info获取
                "disk_percent": resource_usage.disk_percent,
                "network_sent": resource_usage.network_sent,
                "network_recv": resource_usage.network_recv,
                "process_count": resource_usage.process_count,
                "load_average": resource_usage.load_average,
                "timestamp": resource_usage.timestamp.isoformat(),
            }

            self.monitoring_data = metrics

            # 检查告警（暂时跳过，避免阻塞）
            # self._check_alerts(metrics)

            return {
                "success": True,
                "metrics": metrics,
            }

        except Exception as e:
            self._log_error("更新系统指标", e)
            return {"success": False, "message": str(e)}

    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标.

        Returns:
            Dict: 系统指标
        """
        return {
            "success": True,
            "metrics": self.monitoring_data,
        }

    def get_enhanced_system_metrics(self) -> Dict[str, Any]:
        """获取增强的系统指标（包含磁盘I/O、网速、温度）.

        Returns:
            Dict: 增强的系统指标
        """
        try:
            # 基础系统资源
            resource_usage = self.system_monitor.get_resource_usage()

            # 磁盘I/O速度
            disk_io_speed = {}
            try:
                disk_io_speed = self.system_monitor.get_disk_io_speed()
            except Exception as e:
                self.logger.debug("获取磁盘I/O速度失败: %s", e)

            # 网络速度
            network_speed = {}
            try:
                network_speed = self.system_monitor.get_network_speed()
            except Exception as e:
                self.logger.debug("获取网络速度失败: %s", e)

            # 磁盘详细信息（各磁盘空间）
            disk_info = {}
            try:
                disk_info = self.system_monitor.get_disk_info()
            except Exception as e:
                self.logger.debug("获取磁盘信息失败: %s", e)

            metrics = {
                # 基础指标
                "cpu_percent": resource_usage.cpu_percent,
                "memory_percent": resource_usage.memory_percent,
                "disk_percent": resource_usage.disk_percent,
                "network_sent": resource_usage.network_sent,
                "network_recv": resource_usage.network_recv,
                "process_count": resource_usage.process_count,
                "load_average": resource_usage.load_average,
                "timestamp": resource_usage.timestamp.isoformat(),
                # 增强指标
                "disk_io_speed": disk_io_speed,  # 各磁盘I/O速度
                "network_speed": network_speed,  # 网络速度和带宽占用
                "disk_info": disk_info,  # 磁盘详细信息
            }

            return {
                "success": True,
                "metrics": metrics,
            }

        except Exception as e:
            self._log_error("获取增强系统指标", e)
            return {"success": False, "message": str(e)}

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统基本信息.

        Returns:
            Dict: 系统基本信息
        """
        try:
            # 使用system_vnpy的SystemMonitor获取系统信息
            system_info = self.system_monitor.get_system_info()

            info = {
                "platform": system_info.platform,
                "platform_version": system_info.platform_version,
                "architecture": system_info.architecture,
                "hostname": system_info.hostname,
                "cpu_count": system_info.cpu_count,
                "cpu_count_logical": system_info.cpu_count_logical,
                "memory_total": system_info.memory_total,
                "disk_total": system_info.disk_total,
                "network_interfaces": system_info.network_interfaces,
                "boot_time": system_info.boot_time.isoformat(),
            }

            return {
                "success": True,
                "info": info,
            }

        except Exception as e:
            self._log_error("获取系统信息", e)
            return {"success": False, "message": str(e)}

    def _check_alerts(self, metrics: Dict[str, Any]):
        """检查告警条件（使用告警引擎）.

        Args:
            metrics: 系统指标
        """
        # 跳过告警检查，避免阻塞
        self.logger.debug("告警检查已跳过（避免启动阻塞）")

    # ==================== 告警管理（链条1.3.1） ====================

    def add_alert_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加告警规则.

        Args:
            rule_data: 规则数据

        Returns:
            Dict: 添加结果
        """
        try:
            rule = AlertRule(
                rule_id=rule_data["rule_id"],
                name=rule_data["name"],
                condition=rule_data["condition"],
                severity=AlertSeverity(rule_data["severity"]),
                enabled=rule_data.get("enabled", True),
                priority=rule_data.get("priority", 0),
                group=rule_data.get("group", "default"),
                description=rule_data.get("description", ""),
            )

            success = self.alert_engine.add_rule(rule)

            return {
                "success": success,
                "message": "规则已添加" if success else "规则添加失败",
            }

        except Exception as e:
            self._log_error("添加告警规则", e)
            return {"success": False, "message": str(e)}

    def update_alert_rule(self, rule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新告警规则.

        Args:
            rule_id: 规则ID
            updates: 更新内容

        Returns:
            Dict: 更新结果
        """
        try:
            success = self.alert_engine.update_rule(rule_id, **updates)

            return {
                "success": success,
                "message": "规则已更新" if success else "规则更新失败",
            }

        except Exception as e:
            self._log_error("更新告警规则", e)
            return {"success": False, "message": str(e)}

    def delete_alert_rule(self, rule_id: str) -> Dict[str, Any]:
        """删除告警规则.

        Args:
            rule_id: 规则ID

        Returns:
            Dict: 删除结果
        """
        try:
            success = self.alert_engine.delete_rule(rule_id)

            return {
                "success": success,
                "message": "规则已删除" if success else "规则删除失败",
            }

        except Exception as e:
            self._log_error("删除告警规则", e)
            return {"success": False, "message": str(e)}

    def get_alert_rules(self, group: Optional[str] = None) -> Dict[str, Any]:
        """获取告警规则列表.

        Args:
            group: 规则分组（可选）

        Returns:
            Dict: 规则列表
        """
        try:
            rules = self.alert_engine.get_all_rules()

            # 如果指定了分组，进行过滤
            if group:
                rules = [rule for rule in rules if getattr(rule, 'group', None) == group]

            rule_list = [rule.to_dict() for rule in rules]

            return {
                "success": True,
                "rules": rule_list,
                "count": len(rule_list),
            }

        except Exception as e:
            self._log_error("获取告警规则", e)
            return {"success": False, "rules": [], "message": str(e)}

    def get_alert_history(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询告警历史.

        Args:
            start_time: 开始时间
            end_time: 结束时间
            severity: 严重程度
            status: 状态
            limit: 返回数量限制

        Returns:
            Dict: 告警历史列表
        """
        try:
            start_dt = datetime.fromisoformat(start_time) if start_time else None
            end_dt = datetime.fromisoformat(end_time) if end_time else None
            severity_enum = AlertSeverity(severity) if severity else None
            status_enum = AlertStatus(status) if status else None

            alerts = self.alert_engine.get_alert_history(
                start_dt, end_dt, severity_enum, status_enum, limit
            )

            alert_list = [alert.to_dict() for alert in alerts]

            return {
                "success": True,
                "alerts": alert_list,
                "count": len(alert_list),
            }

        except Exception as e:
            self._log_error("查询告警历史", e)
            return {"success": False, "alerts": [], "message": str(e)}


    def configure_alert_notifications(
        self, notification_type: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """配置告警通知.

        Args:
            notification_type: 通知类型 (email/webhook/desktop)
            config: 配置参数

        Returns:
            Dict: 配置结果
        """
        try:
            notif_type = NotificationType(notification_type)
            self.alert_engine.configure_notifications(notif_type, config)

            return {
                "success": True,
                "message": f"{notification_type}通知已配置",
            }

        except Exception as e:
            self._log_error("配置告警通知", e)
            return {"success": False, "message": str(e)}

    # ==================== 服务健康检查 ====================

    def check_all_services(self) -> Dict[str, Any]:
        """检查所有服务健康状态（增强版）.

        Returns:
            Dict: 服务健康状态
        """
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()

            # 使用增强的服务健康检查器
            result = self.service_health_checker.check_all_services(service_manager)

            return result

        except Exception as e:
            self._log_error("检查服务健康", e)
            return {"success": False, "message": str(e)}

    def check_service_health(self, service_name: str) -> Dict[str, Any]:
        """轻量级服务健康检查（单个服务）.

        Args:
            service_name: 服务名称

        Returns:
            Dict: 健康检查结果
        """
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()

            result = self.service_health_checker.quick_check(service_name, service_manager)

            return {
                "success": True,
                "result": result,
            }

        except Exception as e:
            self._log_error("检查服务健康", e)
            return {"success": False, "message": str(e)}

    def restart_service(self, service_name: str, graceful: bool = True) -> Dict[str, Any]:
        """重启指定服务.

        Args:
            service_name: 服务名称
            graceful: 是否优雅重启

        Returns:
            Dict: 重启结果
        """
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()

            if graceful:
                result = self.service_restarter.graceful_restart(service_name, service_manager)
            else:
                result = self.service_restarter.restart_service(service_name, service_manager)

            return result

        except Exception as e:
            self._log_error("重启服务", e)
            return {"success": False, "message": str(e)}

    # ==================== 日志管理 ====================

    def query_logs(
        self,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
        logger_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """查询日志记录（增强版）.

        Args:
            level: 日志级别筛选（DEBUG, INFO, WARNING, ERROR, CRITICAL）
            start_time: 开始时间（ISO格式）
            end_time: 结束时间（ISO格式）
            module: 模块名筛选
            logger_name: 日志记录器名筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            Dict: 日志记录列表和统计信息
        """
        try:
            # 使用内部log_manager实例
            # 查询日志记录
            logs = self.log_manager.query_logs(
                level=level,
                start_time=start_time,
                end_time=end_time,
                module=module,
                logger_name=logger_name,
                limit=limit,
                offset=offset,
            )

            # 获取统计信息
            stats = self.log_manager.get_log_stats()

            return {
                "success": True,
                "logs": logs,
                "total": len(logs),
                "stats": stats,
                "filters": {
                    "level": level,
                    "start_time": start_time,
                    "end_time": end_time,
                    "module": module,
                    "logger_name": logger_name,
                    "limit": limit,
                    "offset": offset,
                },
            }

        except Exception as e:
            self._log_error("查询日志", e)
            return {"success": False, "message": str(e), "logs": [], "total": 0, "stats": {}}

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息.

        Returns:
            Dict: 日志统计信息
        """
        try:
            # 使用内部log_manager实例
            stats = self.log_manager.get_log_stats()

            return {"success": True, "stats": stats}

        except Exception as e:
            self._log_error("获取日志统计", e)
            return {"success": False, "message": str(e), "stats": {}}

    def export_logs(
        self,
        file_path: str,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
    ) -> Dict[str, Any]:
        """导出日志到文件.

        Args:
            file_path: 导出文件路径
            level: 日志级别筛选
            start_time: 开始时间
            end_time: 结束时间
            module: 模块名筛选

        Returns:
            Dict: 导出结果
        """
        try:
            # 使用内部log_manager实例
            success = self.log_manager.export_logs(
                file_path=file_path,
                level=level,
                start_time=start_time,
                end_time=end_time,
                module=module,
            )

            return {
                "success": success,
                "message": "日志导出成功" if success else "日志导出失败",
                "file_path": file_path,
            }

        except Exception as e:
            self._log_error("导出日志", e)
            return {"success": False, "message": str(e)}

    # ==================== 系统诊断 ====================

    def run_diagnostics(self) -> Dict[str, Any]:
        """运行基础系统诊断.

        Returns:
            Dict: 诊断结果
        """
        try:
            diagnostics = {
                "timestamp": datetime.now().isoformat(),
                "performance": self._diagnose_performance(),
                "network": self._diagnose_network(),
                "database": self._diagnose_database(),
            }

            return {
                "success": True,
                "diagnostics": diagnostics,
            }

        except Exception as e:
            self._log_error("运行诊断", e)
            return {"success": False, "message": str(e)}

    def run_advanced_diagnostics(self) -> Dict[str, Any]:
        """运行高级诊断（包含日志分析和优化建议）.

        Returns:
            Dict: 高级诊断结果
        """
        try:
            # 基础诊断
            basic_diagnostics = self.run_diagnostics()

            # 性能瓶颈分析
            bottlenecks = []
            try:
                bottlenecks = self.performance_analyzer.analyze_bottlenecks()
            except Exception as e:
                self.logger.warning("分析性能瓶颈失败: %s", e)

            # 日志分析
            log_analysis = {}
            try:
                log_file = "logs/terminal_v0.50.log"
                log_analysis = self.log_analyzer.analyze_error_logs(log_file, hours=24)
            except Exception as e:
                self.logger.warning("分析日志失败: %s", e)

            # 生成优化建议
            optimization_suggestions = []
            try:
                optimization_suggestions = (
                    self.performance_analyzer.generate_optimization_suggestions(bottlenecks)
                )
            except Exception as e:
                self.logger.warning("生成优化建议失败: %s", e)

            # 生成修复建议
            fix_suggestions = []
            try:
                if log_analysis.get("success") and log_analysis.get("top_errors"):
                    for error in log_analysis["top_errors"][:5]:  # 只处理前5个
                        error_type = error["type"]
                        fixes = self.auto_fixer.suggest_fixes(error_type)
                        fix_suggestions.extend(fixes)
            except Exception as e:
                self.logger.warning("生成修复建议失败: %s", e)

            diagnostics = {
                "timestamp": datetime.now().isoformat(),
                "basic_diagnostics": basic_diagnostics.get("diagnostics", {}),
                "performance_bottlenecks": bottlenecks,
                "log_analysis": log_analysis,
                "optimization_suggestions": optimization_suggestions,
                "fix_suggestions": fix_suggestions[:10],  # 限制数量
            }

            return {
                "success": True,
                "diagnostics": diagnostics,
            }

        except Exception as e:
            self._log_error("运行高级诊断", e)
            return {"success": False, "message": str(e)}

    def _diagnose_performance(self) -> Dict[str, Any]:
        """性能诊断."""
        try:
            # 使用system_vnpy的SystemMonitor获取系统信息
            system_info = self.system_monitor.get_system_info()

            return {
                "cpu_count": system_info.cpu_count,
                "cpu_count_logical": system_info.cpu_count_logical,
                "memory_total": system_info.memory_total,
                "disk_total": system_info.disk_total,
                "architecture": system_info.architecture,
            }
        except Exception as e:
            return {"error": str(e)}

    def _diagnose_network(self) -> Dict[str, Any]:
        """网络诊断."""
        try:
            # 使用system_vnpy的NetworkTester进行网络诊断
            system_info = self.system_monitor.get_system_info()

            result = {
                "hostname": system_info.hostname,
                "network_interfaces": system_info.network_interfaces,
                "internet_accessible": False,
                "connectivity_tests": {},
            }

            # 测试多个外部服务器连通性
            test_hosts = [
                ("www.baidu.com", 80),
                ("www.google.com", 80),
                ("www.bing.com", 80),
            ]

            accessible_count = 0
            for host, port in test_hosts:
                is_accessible = self.network_tester.test_host(host, port)
                result["connectivity_tests"][host] = is_accessible
                if is_accessible:
                    accessible_count += 1

            # 如果至少有一个服务器可访问，认为网络可用
            result["internet_accessible"] = accessible_count > 0

            return result

        except Exception as e:
            return {"error": str(e)}

    def scan_ports(self, host: str, ports: Optional[List[int]] = None) -> Dict[str, Any]:
        """扫描指定主机的端口.

        Args:
            host: 主机地址
            ports: 端口列表（如不提供则扫描常用端口）

        Returns:
            Dict: 端口扫描结果
        """
        try:
            if ports is None:
                # 默认扫描常用端口
                ports = [21, 22, 23, 25, 80, 443, 3306, 3389, 5432, 6379, 8000, 8080, 9000]

            # 使用system_vnpy的PortScanner
            scan_results = self.port_scanner.scan(host, ports)

            return {
                "success": True,
                "host": host,
                "scan_results": scan_results,
            }

        except Exception as e:
            self._log_error("端口扫描", e)
            return {"success": False, "message": str(e)}

    def _diagnose_database(self) -> Dict[str, Any]:
        """数据库诊断."""
        try:
            db_file = Path("data/terminal.db")

            if not db_file.exists():
                return {
                    "exists": False,
                    "message": "数据库文件不存在",
                }

            return {
                "exists": True,
                "size": db_file.stat().st_size,
                "path": str(db_file),
            }

        except Exception as e:
            return {"error": str(e)}

    # ==================== 配置诊断 ====================

    def diagnose_config(self) -> Dict[str, Any]:
        """诊断配置文件状态.

        Returns:
            Dict: 诊断结果
        """
        try:
            from backend.core.config import get_settings
            import json
            import os

            # 🔧 修复：使用配置对象中保存的路径，或从环境变量获取
            settings = get_settings()
            if settings.config_file:
                config_file = Path(settings.config_file)
            else:
                # 从环境变量获取或使用默认值
                config_file_str = os.getenv("CONFIG_FILE") or "config/terminal_config.json"
                config_file = Path(config_file_str)
                # 如果是相对路径，转换为绝对路径
                if not config_file.is_absolute():
                    from pathlib import Path as P

                    project_root = P(__file__).parent.parent.parent
                    config_file = project_root / config_file

            diagnosis = {
                "config_file_path": str(config_file.absolute()),
                "config_file_exists": config_file.exists(),
                "config_file_content": None,
                "memory_config": None,
                "ai_service_status": None,
            }

            # 检查文件内容
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        diagnosis["config_file_content"] = json.load(f)
                except Exception as e:
                    diagnosis["config_file_error"] = str(e)

            # 检查内存配置
            settings = get_settings()
            diagnosis["memory_config"] = {
                "ai_api_key_set": bool(settings.ai.api_key),
                "ai_api_url": settings.ai.api_url,
                "ai_model": settings.ai.model,
            }

            # 检查AI服务状态
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            ai_service = service_manager.get_service("ai_assistant_service")

            if ai_service:
                # 检查初始化状态
                try:
                    initialized = (
                        ai_service.is_initialized
                        if hasattr(ai_service, "is_initialized")
                        else "unknown"
                    )
                except Exception:
                    initialized = "unknown"

                # 检查API Key配置
                try:
                    api_key_configured = (
                        bool(ai_service.api_key) if hasattr(ai_service, "api_key") else "unknown"
                    )
                except Exception:
                    api_key_configured = "unknown"

                diagnosis["ai_service_status"] = {
                    "exists": True,
                    "initialized": initialized,
                    "api_key_configured": api_key_configured,
                }
            else:
                diagnosis["ai_service_status"] = {"exists": False}

            return {
                "success": True,
                "diagnosis": diagnosis,
            }

        except Exception as e:
            self.logger.error("配置诊断失败: %s", e, exc_info=True)
            return {
                "success": False,
                "message": str(e),
            }

    # ==================== 告警管理 ====================

    def query_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """查询告警记录.

        Args:
            status: 状态筛选（NEW, ACKNOWLEDGED, RESOLVED, IGNORED）
            severity: 严重程度筛选（INFO, WARNING, ERROR, CRITICAL）
            rule_id: 规则ID筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            Dict: 告警记录列表
        """
        try:
            # get_alert_database 在本文件中定义
            alert_db = get_alert_database()

            # 查询告警记录
            alerts = alert_db.get_alerts(
                status=status,
                severity=severity,
                rule_id=rule_id,
                limit=limit,
                offset=offset,
            )

            # 转换告警对象为字典
            alert_list = [alert.to_dict() for alert in alerts]

            return {
                "success": True,
                "alerts": alert_list,
                "total": len(alert_list),
                "filters": {
                    "status": status,
                    "severity": severity,
                    "rule_id": rule_id,
                    "limit": limit,
                    "offset": offset,
                },
            }

        except Exception as e:
            self._log_error("查询告警", e)
            return {
                "success": False,
                "message": str(e),
                "alerts": [],
                "total": 0,
            }

    def get_unresolved_alerts(self) -> Dict[str, Any]:
        """获取未解决的告警.

        Returns:
            Dict: 未解决告警列表
        """
        try:
            # get_alert_database 在本文件中定义
            alert_db = get_alert_database()
            alerts = alert_db.get_unresolved_alerts()

            # alerts已经是字典列表，无需转换
            alert_list = alerts

            return {
                "success": True,
                "alerts": alert_list,
                "total": len(alert_list),
            }

        except Exception as e:
            self._log_error("获取未解决告警", e)
            return {
                "success": False,
                "message": str(e),
                "alerts": [],
                "total": 0,
            }

    def acknowledge_alert(self, alert_id: str, note: str = "") -> Dict[str, Any]:
        """确认告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            Dict: 确认结果
        """
        try:
            # get_alert_database 在本文件中定义
            alert_db = get_alert_database()

            success = alert_db.update_alert_status(
                alert_id=alert_id,
                status=AlertStatus.ACKNOWLEDGED,
                note=note,
            )

            if success:
                # 发布告警更新事件
                alert = alert_db.get_alert(alert_id)
                if alert:
                    # AlertEventPublisher 在本文件中定义
                    from backend.core.base import get_event_engine

                    event_engine = get_event_engine()
                    if event_engine:
                        publisher = AlertEventPublisher(event_engine, alert_db)
                        publisher.publish_alert_updated(alert)

            return {
                "success": success,
                "message": "告警已确认" if success else "告警确认失败",
            }

        except Exception as e:
            self._log_error("确认告警", e)
            return {"success": False, "message": str(e)}

    def resolve_alert(self, alert_id: str, note: str = "") -> Dict[str, Any]:
        """解决告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            Dict: 解决结果
        """
        try:
            # get_alert_database 在本文件中定义
            alert_db = get_alert_database()

            success = alert_db.update_alert_status(
                alert_id=alert_id,
                status=AlertStatus.RESOLVED,
                note=note,
            )

            if success:
                # 发布告警更新事件
                alert = alert_db.get_alert(alert_id)
                if alert:
                    # AlertEventPublisher 在本文件中定义
                    from backend.core.base import get_event_engine

                    event_engine = get_event_engine()
                    if event_engine:
                        publisher = AlertEventPublisher(event_engine, alert_db)
                        publisher.publish_alert_updated(alert)

            return {
                "success": success,
                "message": "告警已解决" if success else "告警解决失败",
            }

        except Exception as e:
            self._log_error("解决告警", e)
            return {"success": False, "message": str(e)}

    def clear_resolved_alerts(self, older_than_days: int = 30) -> Dict[str, Any]:
        """清理已解决的旧告警.

        Args:
            older_than_days: 超过多少天的已解决告警将被删除

        Returns:
            Dict: 清理结果
        """
        try:
            # get_alert_database 在本文件中定义
            alert_db = get_alert_database()
            deleted_count = alert_db.delete_resolved_alerts(older_than_days)

            return {
                "success": True,
                "message": f"已清理 {deleted_count} 条已解决的告警",
                "deleted_count": deleted_count,
            }

        except Exception as e:
            self._log_error("清理已解决告警", e)
            return {
                "success": False,
                "message": str(e),
                "deleted_count": 0,
            }

    def get_alert_stats(self) -> Dict[str, Any]:
        """获取告警统计信息.

        Returns:
            Dict: 告警统计信息
        """
        try:
            # get_alert_database 在本文件中定义
            alert_db = get_alert_database()

            # 按状态统计
            new_alerts = alert_db.get_alerts(status="new", limit=1000)
            acknowledged_alerts = alert_db.get_alerts(status="acknowledged", limit=1000)
            resolved_alerts = alert_db.get_alerts(status="resolved", limit=1000)

            # 按严重程度统计
            error_alerts = alert_db.get_alerts(severity="error", limit=1000)
            critical_alerts = alert_db.get_alerts(severity="critical", limit=1000)

            return {
                "success": True,
                "stats": {
                    "new_count": len(new_alerts),
                    "acknowledged_count": len(acknowledged_alerts),
                    "resolved_count": len(resolved_alerts),
                    "error_count": len(error_alerts),
                    "critical_count": len(critical_alerts),
                    "total_count": len(new_alerts)
                    + len(acknowledged_alerts)
                    + len(resolved_alerts),
                },
            }

        except Exception as e:
            self._log_error("获取告警统计", e)
            return {"success": False, "message": str(e), "stats": {}}

    # ==================== 服务重载 ====================

    def reload_ai_service(self) -> Dict[str, Any]:
        """重新加载AI助手服务.

        当AI配置更新后，需要重新初始化AI服务以应用新配置。

        Returns:
            Dict: 重载结果
        """
        try:
            from backend.core.base import get_service_manager
            from backend.core.config import init_settings, get_settings
            import os

            # 🔧 关键修复：强制重新加载配置文件，确保使用最新保存的配置
            if os.getenv("CONFIG_FILE"):
                config_file = os.getenv("CONFIG_FILE")
                self.logger.info("从环境变量重新加载配置: %s", config_file)
                init_settings(config_file)
            else:
                settings = get_settings()
                if settings.config_file:
                    self.logger.info("重新加载配置文件: %s", settings.config_file)
                    init_settings(settings.config_file)
                else:
                    self.logger.info("重新加载默认配置文件")
                    init_settings()

            # 验证配置是否已更新
            settings = get_settings()
            if settings.ai.api_key:
                masked_key = f"{settings.ai.api_key[:4]}...{settings.ai.api_key[-4:]}"
                self.logger.info("重新加载后的API Key: %s", masked_key)
            else:
                self.logger.warning("API Key未设置，AI服务重载可能失败")

            service_manager = get_service_manager()

            # 关闭旧服务
            old_service = service_manager.get_service("ai_assistant_service")
            if old_service:
                try:
                    old_service.shutdown()
                    self.logger.info("旧AI服务已关闭")
                except Exception as e:
                    self.logger.warning("关闭旧AI服务时出错: %s", e)

            # 创建新服务实例
            from backend.services.ai_assistant_service import AIAssistantService

            ai_service = AIAssistantService()
            init_success = ai_service.initialize()

            if init_success:
                # 注册新服务
                service_manager.register_service("ai_assistant_service", ai_service)
                self.logger.info("AI服务重新加载成功")
                return {
                    "success": True,
                    "message": "AI服务已重新加载并初始化成功",
                }
            else:
                self.logger.warning("AI服务重新初始化失败")
                return {
                    "success": False,
                    "message": "AI服务初始化失败，请检查API配置是否正确",
                }

        except Exception as e:
            self.logger.error("重新加载AI服务失败: %s", e, exc_info=True)
            return {
                "success": False,
                "message": f"重新加载失败: {str(e)}",
            }

    # ==================== 业务指标监控 ====================

    def get_business_metrics(self) -> Dict[str, Any]:
        """获取业务指标监控数据.

        聚合各业务服务的关键指标：
        - 数据中心：品种数量、本地数据量、下载任务进度
        - 交易网关：网关连接数、策略运行数、订单成交数
        - 组合投资：组合数量、总盈亏、风险指标

        Returns:
            Dict: 业务指标数据
        """
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            metrics = {}

            # 1. 数据中心指标
            data_center_service = service_manager.get_service("data_center_service")
            if data_center_service:
                try:
                    # 获取品种列表
                    symbol_result = data_center_service.refresh_symbol_list()
                    symbol_count = (
                        len(symbol_result.get("data", [])) if symbol_result.get("success") else 0
                    )

                    # 获取数据源状态
                    datafeed_status = data_center_service.get_all_datafeed_status()
                    connected_datafeeds = sum(
                        1
                        for df in datafeed_status.get("datafeeds", {}).values()
                        if df.get("connected")
                    )

                    metrics["data_center"] = {
                        "symbol_count": symbol_count,
                        "connected_datafeeds": connected_datafeeds,
                        "active_downloads": len(data_center_service._download_tasks),
                        "recording_enabled": datafeed_status.get("recording", {}).get(
                            "enabled", False
                        ),
                    }
                except Exception as e:
                    self.logger.warning(f"获取数据中心指标失败: {e}")
                    metrics["data_center"] = {"error": str(e)}

            # 2. 交易网关指标
            gateway_service = service_manager.get_service("trading_gateway_service")
            if gateway_service:
                try:
                    gateways = gateway_service.list_gateways()
                    connected_gateways = sum(1 for g in gateways if g.get("connected"))

                    total_strategies = sum(
                        len(strategies)
                        for strategies in gateway_service.strategy_instances.values()
                    )
                    active_strategies = sum(
                        1
                        for strategies in gateway_service.strategy_instances.values()
                        for s in strategies.values()
                        if s.get("status") == "running"
                    )

                    metrics["trading_gateway"] = {
                        "total_gateways": len(gateways),
                        "connected_gateways": connected_gateways,
                        "total_strategies": total_strategies,
                        "active_strategies": active_strategies,
                    }
                except Exception as e:
                    self.logger.warning(f"获取交易网关指标失败: {e}")
                    metrics["trading_gateway"] = {"error": str(e)}

            # 3. 组合投资指标
            portfolio_service = service_manager.get_service("portfolio_service")
            if portfolio_service:
                try:
                    portfolios_result = portfolio_service.list_portfolios()
                    if portfolios_result.get("success"):
                        portfolios = portfolios_result.get("portfolios", {})
                        auto_count = len(portfolios.get("auto_portfolios", []))
                        custom_count = len(portfolios.get("custom_portfolios", []))

                        metrics["portfolio_investment"] = {
                            "auto_portfolio_count": auto_count,
                            "custom_portfolio_count": custom_count,
                            "total_portfolio_count": auto_count + custom_count,
                        }
                    else:
                        metrics["portfolio_investment"] = {"error": "无法获取组合列表"}
                except Exception as e:
                    self.logger.warning(f"获取组合投资指标失败: {e}")
                    metrics["portfolio_investment"] = {"error": str(e)}

            # 4. 策略中心指标
            strategy_service = service_manager.get_service("strategy_center_service")
            if strategy_service:
                try:
                    strategies_result = strategy_service.get_available_strategies()
                    strategy_count = (
                        len(strategies_result.get("strategies", []))
                        if strategies_result.get("success")
                        else 0
                    )

                    metrics["strategy_center"] = {
                        "available_strategies": strategy_count,
                        "active_backtests": len(strategy_service._backtest_tasks),
                    }
                except Exception as e:
                    self.logger.warning(f"获取策略中心指标失败: {e}")
                    metrics["strategy_center"] = {"error": str(e)}

            return {
                "success": True,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self._log_error("获取业务指标", e)
            return {"success": False, "message": str(e)}

    # ==================== 配置管理 ====================

    def get_all_configs(self) -> Dict[str, Any]:
        """获取所有模块的配置项（集中展示）.

        聚合以下模块配置：
        1. 数据中心配置 (data_module_vnpy)
        2. VnPy配置
        3. AI助手配置
        4. 数据库配置
        5. 网络配置

        Returns:
            Dict: 所有配置项
        """
        try:
            configs = {}

            # 1. 数据中心配置（来自data_module_vnpy）
            try:
                from backend.infrastructure.data_module_vnpy.config import config_manager

                configs["data_center"] = {
                    "cache_dir": config_manager.get("chinastock.cache_dir"),
                    "data_dir": config_manager.get("chinastock.data_dir"),
                    "tdx_dir": config_manager.get("chinastock.tdx_dir"),
                    "base_date": config_manager.get("chinastock.base_date"),
                    "max_workers": config_manager.get("chinastock.max_workers"),
                    "timeout": config_manager.get("chinastock.timeout"),
                    "retry_times": config_manager.get("chinastock.retry_times"),
                    "enable_watcher": config_manager.get("chinastock.enable_watcher"),
                    "watcher_interval": config_manager.get("chinastock.watcher_interval"),
                }
            except Exception as e:
                self.logger.warning(f"获取数据中心配置失败: {e}")
                configs["data_center"] = {}

            # 2. VnPy配置
            try:
                from backend.core.config import get_settings

                settings = get_settings()
                configs["vnpy"] = {
                    "event_engine_timer_interval": settings.vnpy.event_engine_timer_interval,
                    "data_storage_path": settings.vnpy.data_storage_path,
                    "log_level": settings.vnpy.log_level,
                    "log_file": settings.vnpy.log_file,
                }
            except Exception as e:
                self.logger.warning(f"获取VnPy配置失败: {e}")
                configs["vnpy"] = {}

            # 3. AI助手配置
            try:
                from backend.core.config import get_settings

                settings = get_settings()
                configs["ai"] = {
                    "provider": settings.ai.provider,
                    "api_key": settings.ai.api_key if settings.ai.api_key else "",
                    "api_url": settings.ai.api_url,
                    "model": settings.ai.model,
                    "max_tokens": settings.ai.max_tokens,
                    "temperature": settings.ai.temperature,
                    "timeout": settings.ai.timeout,
                    "max_history": settings.ai.max_history,
                    "system_prompt": settings.ai.system_prompt,
                }
            except Exception as e:
                self.logger.warning(f"获取AI配置失败: {e}")
                configs["ai"] = {}

            # 4. 数据库配置
            try:
                from backend.core.config import get_settings

                settings = get_settings()
                configs["database"] = {
                    "sqlite_path": settings.database.sqlite_path,
                    "sqlite_timeout": settings.database.sqlite_timeout,
                }
            except Exception as e:
                self.logger.warning(f"获取数据库配置失败: {e}")
                configs["database"] = {}

            # 5. 网络配置（API）
            try:
                from backend.core.config import get_settings

                settings = get_settings()
                configs["network"] = {
                    "api_host": settings.api.host,
                    "api_port": settings.api.port,
                    "api_debug": settings.api.debug,
                }
            except Exception as e:
                self.logger.warning(f"获取网络配置失败: {e}")
                configs["network"] = {}

            return {
                "success": True,
                "configs": configs,
            }

        except Exception as e:
            self._log_error("获取所有配置", e)
            return {"success": False, "message": str(e)}

    def update_config(self, module: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新指定模块的配置.

        Args:
            module: 模块名称 (data_center/vnpy/ai/database/network)
            config_data: 配置数据字典

        Returns:
            Dict: 更新结果
        """
        try:
            import os

            ai_config_updated = False

            if module == "data_center":
                # 更新data_module_vnpy配置
                from backend.infrastructure.data_module_vnpy.config import config_manager

                # 转换为chinastock.前缀
                chinastock_config = {}
                for key, value in config_data.items():
                    chinastock_config[f"chinastock.{key}"] = value

                config_manager.update_config(chinastock_config)

            elif module in ["vnpy", "ai", "database", "network"]:
                # 更新backend配置
                from backend.core.config import get_settings

                settings = get_settings()

                if module == "vnpy":
                    for key, value in config_data.items():
                        if hasattr(settings.vnpy, key):
                            setattr(settings.vnpy, key, value)

                elif module == "ai":
                    # AI配置更新，需要重新加载服务
                    ai_config_updated = True
                    for key, value in config_data.items():
                        if hasattr(settings.ai, key):
                            setattr(settings.ai, key, value)
                            # 记录详细的配置更新（API Key需要遮蔽）
                            if key == "api_key" and value:
                                masked_value = (
                                    f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
                                )
                                self.logger.info("更新AI配置: %s = %s", key, masked_value)
                            else:
                                self.logger.info("更新AI配置: %s = %s", key, value)

                elif module == "database":
                    for key, value in config_data.items():
                        if hasattr(settings.database, key):
                            setattr(settings.database, key, value)

                elif module == "network":
                    # 网络配置需要更新api
                    for key, value in config_data.items():
                        if key.startswith("api_"):
                            api_key = key[4:]  # 移除api_前缀
                            if hasattr(settings.api, api_key):
                                setattr(settings.api, api_key, value)

                # 🔧 修复：保存到正确的配置文件路径
                if settings.config_file:
                    # 使用配置对象中保存的路径
                    config_file = Path(settings.config_file)
                else:
                    # 从环境变量获取或使用默认值
                    config_file_str = os.getenv("CONFIG_FILE") or "config/terminal_config.json"
                    config_file = Path(config_file_str)
                    # 如果是相对路径，转换为绝对路径
                    if not config_file.is_absolute():
                        from pathlib import Path as P

                        project_root = P(__file__).parent.parent.parent
                        config_file = project_root / config_file

                self.logger.info("保存配置到文件: %s", str(config_file.absolute()))
                settings.save_to_file(str(config_file))

            else:
                return {
                    "success": False,
                    "message": f"未知模块: {module}",
                }

            self.logger.info(f"配置已更新: {module} - {list(config_data.keys())}")

            # 如果AI配置被更新，自动重新加载AI服务
            result = {
                "success": True,
                "message": f"{module}配置已更新",
                "ai_reloaded": False,
            }

            if ai_config_updated:
                self.logger.info("AI配置已更新，正在重新加载AI服务...")
                reload_result = self.reload_ai_service()
                result["ai_reloaded"] = reload_result.get("success", False)
                result["ai_reload_message"] = reload_result.get("message", "")

                if reload_result.get("success"):
                    result["message"] = f"{module}配置已更新，AI服务已重新加载"
                else:
                    result["message"] = (
                        f"{module}配置已更新，但AI服务重载失败: {reload_result.get('message')}"
                    )

            return result

        except Exception as e:
            self._log_error(f"更新配置[{module}]", e)
            return {"success": False, "message": str(e)}

    def save_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存系统配置.

        Args:
            config_data: 配置数据字典

        Returns:
            Dict: 保存结果
        """
        try:
            import json

            # 配置文件路径
            config_file = Path("config/terminal_config.json")
            config_file.parent.mkdir(parents=True, exist_ok=True)

            # 加载现有配置（如果存在）
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            else:
                existing_config = {}

            # 合并配置
            existing_config.update(config_data)

            # 保存配置
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(existing_config, f, indent=4, ensure_ascii=False)

            self.logger.info(f"配置已保存: {list(config_data.keys())}")

            return {
                "success": True,
                "message": f"配置已保存 ({len(config_data)}项)",
                "config_file": str(config_file),
            }

        except Exception as e:
            self._log_error("保存配置", e)
            return {
                "success": False,
                "message": f"保存配置失败: {str(e)}",
            }

    def load_config(self) -> Dict[str, Any]:
        """加载系统配置.

        Returns:
            Dict: 配置数据
        """
        try:
            import json

            config_file = Path("config/terminal_config.json")

            if not config_file.exists():
                return {
                    "success": True,
                    "config": {},
                    "message": "配置文件不存在，返回空配置",
                }

            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.logger.info(f"配置已加载: {len(config)}项")

            return {
                "success": True,
                "config": config,
                "message": f"配置已加载 ({len(config)}项)",
            }

        except Exception as e:
            self._log_error("加载配置", e)
            return {
                "success": False,
                "config": {},
                "message": f"加载配置失败: {str(e)}",
            }

    # ==================== 工具注册系统 ====================

    def register_tool(self, tool_info: Dict[str, Any]) -> Dict[str, Any]:
        """注册工具.

        Args:
            tool_info: 工具信息，包含name, description, command等

        Returns:
            Dict: 注册结果
        """
        try:
            tool_name = tool_info.get("name")
            if not tool_name:
                return {
                    "success": False,
                    "message": "工具名称不能为空",
                }

            if tool_name in self.registered_tools:
                return {
                    "success": False,
                    "message": f"工具 '{tool_name}' 已经注册",
                }

            # 注册工具
            self.registered_tools[tool_name] = {
                "name": tool_name,
                "description": tool_info.get("description", ""),
                "command": tool_info.get("command", ""),
                "parameters": tool_info.get("parameters", {}),
                "registered_at": datetime.now().isoformat(),
            }

            self.logger.info(f"工具已注册: {tool_name}")

            return {
                "success": True,
                "message": f"工具 '{tool_name}' 注册成功",
            }

        except Exception as e:
            self._log_error("注册工具", e)
            return {
                "success": False,
                "message": f"注册工具失败: {str(e)}",
            }

    def get_tools(self) -> Dict[str, Any]:
        """获取所有注册的工具.

        Returns:
            Dict: 工具列表
        """
        try:
            return {
                "success": True,
                "tools": list(self.registered_tools.values()),
                "count": len(self.registered_tools),
            }

        except Exception as e:
            self._log_error("获取工具列表", e)
            return {
                "success": False,
                "tools": [],
                "message": f"获取工具列表失败: {str(e)}",
            }

    def remove_tool(self, tool_name: str) -> Dict[str, Any]:
        """移除已注册的工具.

        Args:
            tool_name: 工具名称

        Returns:
            Dict: 移除结果
        """
        try:
            if tool_name not in self.registered_tools:
                return {
                    "success": False,
                    "message": f"工具 '{tool_name}' 未注册",
                }

            del self.registered_tools[tool_name]

            self.logger.info(f"工具已移除: {tool_name}")

            return {
                "success": True,
                "message": f"工具 '{tool_name}' 已移除",
            }

        except Exception as e:
            self._log_error("移除工具", e)
            return {
                "success": False,
                "message": f"移除工具失败: {str(e)}",
            }

    # ==================== 数据标准化读取器 ====================

    def get_available_data_readers(self) -> Dict[str, Any]:
        """获取可用的数据读取器列表.

        Returns:
            Dict: 数据读取器列表
        """
        try:
            readers = [
                {
                    "id": "tdx",
                    "name": "通达信",
                    "description": "读取通达信本地二进制数据文件",
                    "supported_types": ["日线", "5分钟线", "1分钟线"],
                    "supported_markets": ["上证", "深证", "北证"],
                }
            ]

            return {
                "success": True,
                "readers": readers,
            }

        except Exception as e:
            self._log_error("获取数据读取器列表", e)
            return {
                "success": False,
                "readers": [],
                "message": f"获取失败: {str(e)}",
            }

    def read_tdx_data(self, config: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """读取通达信数据并标准化保存（多市场、多周期、多线程）.

        Args:
            config: 配置信息
                - data_types: 数据类型列表 ['day', '5min', '1min']
                - markets: 市场代码列表 ['sh', 'sz', 'bj']
                - tdx_root: 通达信根目录
                - use_symbol_cache: 是否使用品种缓存（自动获取品种列表）
                - max_workers: 最大线程数
            progress_callback: 进度回调 callback(current, total, info)

        Returns:
            Dict: 处理结果
        """
        try:
            self._log_operation("读取通达信数据")

            # 验证配置
            data_types = config.get("data_types", [])
            markets = config.get("markets", [])
            tdx_root = config.get("tdx_root")
            use_symbol_cache = config.get("use_symbol_cache", True)
            max_workers = config.get("max_workers", 4)

            if not data_types or not markets or not tdx_root:
                return {
                    "success": False,
                    "message": "缺少必要参数：数据类型、市场代码或通达信根目录",
                }

            # 验证通达信目录
            tdx_path = Path(tdx_root)
            if not tdx_path.exists():
                return {
                    "success": False,
                    "message": f"通达信目录不存在: {tdx_root}",
                }

            # 获取品种列表
            if use_symbol_cache:
                symbols_by_market = self._get_symbols_from_cache(markets)
                if not any(symbols_by_market.values()):
                    return {
                        "success": False,
                        "message": "品种缓存为空，请先在数据中心重新加载品种列表",
                    }
            else:
                return {
                    "success": False,
                    "message": "手动指定品种功能已移除，请使用品种缓存",
                }

            # 导入TdxBinaryReader
            try:
                from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
                    TdxBinaryReader,
                )
            except ImportError as e:
                self.logger.error("导入TdxBinaryReader失败: %s", e)
                return {
                    "success": False,
                    "message": f"导入读取器失败: {str(e)}",
                }

            # 创建读取器实例
            reader = TdxBinaryReader(source_path=tdx_path)

            # 计算总任务数
            total_tasks = sum(
                len(symbols_by_market.get(market, [])) * len(data_types) for market in markets
            )

            if total_tasks == 0:
                return {
                    "success": False,
                    "message": "没有找到符合条件的品种",
                }

            self.logger.info("开始批量读取: %d 个任务", total_tasks)

            # 重置停止标志
            self._tdx_reader_stop_flag = False

            # 批量处理（多市场、多周期）
            all_results = {}
            completed = 0

            for market in markets:
                # 检查停止标志
                if self._tdx_reader_stop_flag:
                    self.logger.info("检测到停止标志，中断批量读取")
                    break

                symbols = symbols_by_market.get(market, [])
                if not symbols:
                    continue

                for data_type in data_types:
                    # 检查停止标志
                    if self._tdx_reader_stop_flag:
                        self.logger.info("检测到停止标志，中断批量读取")
                        break

                    # 定义进度回调包装器
                    def wrapped_callback(current, total, symbol, success):
                        nonlocal completed
                        completed += 1
                        if progress_callback:
                            info = f"{market.upper()} {data_type} {symbol}"
                            progress_callback(completed, total_tasks, info, success)

                        # 检查停止标志
                        return not self._tdx_reader_stop_flag

                    # 批量处理
                    results = reader.process_batch(
                        symbols=symbols,
                        data_type=data_type,
                        market=market,
                        progress_callback=wrapped_callback,
                        max_workers=max_workers,
                        stop_check=lambda: self._tdx_reader_stop_flag,
                    )

                    # 合并结果
                    for symbol, success in results.items():
                        key = f"{market}_{data_type}_{symbol}"
                        all_results[key] = success

            # 统计结果
            success_count = sum(1 for v in all_results.values() if v)
            fail_count = len(all_results) - success_count
            was_stopped = self._tdx_reader_stop_flag

            if was_stopped:
                self.logger.info(
                    "批量读取已停止: 已完成 %d/%d, 成功 %d, 失败 %d",
                    len(all_results),
                    total_tasks,
                    success_count,
                    fail_count,
                )
                message = f"已停止：已完成 {len(all_results)}/{total_tasks}，成功 {success_count}，失败 {fail_count}"
            else:
                self.logger.info(
                    "批量读取完成: 成功 %d, 失败 %d",
                    success_count,
                    fail_count,
                )
                message = f"批量读取完成：成功 {success_count} 个，失败 {fail_count} 个"

            return {
                "success": True,
                "message": message,
                "results": all_results,
                "success_count": success_count,
                "fail_count": fail_count,
                "total_tasks": total_tasks,
                "was_stopped": was_stopped,
            }

        except Exception as e:
            self._log_error("读取通达信数据", e)
            return {
                "success": False,
                "message": f"读取失败: {str(e)}",
            }

    def stop_tdx_reader(self) -> Dict[str, Any]:
        """停止通达信数据读取任务.

        Returns:
            Dict: 停止结果
        """
        try:
            self._tdx_reader_stop_flag = True
            self.logger.info("已发送停止信号")

            return {
                "success": True,
                "message": "停止信号已发送，任务将在当前批次完成后停止",
            }

        except Exception as e:
            self._log_error("停止通达信读取", e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def _get_symbols_from_cache(self, markets: List[str]) -> Dict[str, List[str]]:
        """从品种缓存获取指定市场的品种列表.

        Args:
            markets: 市场代码列表 ['sh', 'sz', 'bj']

        Returns:
            Dict: 市场到品种列表的映射
        """
        try:
            # 获取服务管理器和数据中心服务
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            data_center_service = service_manager.get_service("data_center_service")

            if not data_center_service:
                self.logger.warning("数据中心服务不可用")
                return {}

            # 获取品种列表
            result = data_center_service.refresh_symbol_list()
            if not result.get("success"):
                self.logger.warning("获取品种列表失败")
                return {}

            symbols = result.get("data", [])
            if not symbols:
                return {}

            # 市场映射
            market_mapping = {
                "sh": "上交所",
                "sz": "深交所",
                "bj": "北交所",
            }

            # 按市场分类
            symbols_by_market = {market: [] for market in markets}

            for symbol_info in symbols:
                exchange = symbol_info.get("exchange", "")
                symbol_code = symbol_info.get("symbol", "")

                # 匹配市场
                for market_code, exchange_name in market_mapping.items():
                    if market_code in markets and exchange == exchange_name:
                        symbols_by_market[market_code].append(symbol_code)
                        break

            # 打印统计
            for market in markets:
                count = len(symbols_by_market.get(market, []))
                self.logger.info(
                    "市场 %s: 找到 %d 个品种",
                    market.upper(),
                    count,
                )

            return symbols_by_market

        except Exception as e:
            self.logger.error("从缓存获取品种列表失败: %s", e)
            return {}

    def get_tdx_reader_config(self) -> Dict[str, Any]:
        """获取通达信读取器的配置.

        Returns:
            Dict: 配置信息
        """
        try:
            # 从配置管理器获取通达信根目录
            try:
                from backend.infrastructure.data_module_vnpy.config import config_manager

                tdx_dir = config_manager.get_tdx_reader_root_dir()
            except Exception:
                tdx_dir = None

            config = {
                "tdx_root": str(tdx_dir) if tdx_dir else "",
                "data_types": {
                    "day": "日线",
                    "5min": "5分钟线",
                    "1min": "1分钟线",
                },
                "markets": {
                    "sh": "上证",
                    "sz": "深证",
                    "bj": "北证",
                },
            }

            return {
                "success": True,
                "config": config,
            }

        except Exception as e:
            self._log_error("获取通达信读取器配置", e)
            return {
                "success": False,
                "config": {},
                "message": f"获取配置失败: {str(e)}",
            }

    # ==================== 进程监控接口 ====================

    def get_monitored_processes(self) -> Dict[str, Any]:
        """获取所有监控中的进程列表.

        Returns:
            Dict: 进程列表
        """
        try:
            processes = self.process_monitor.identify_processes()

            return {
                "success": True,
                "processes": processes,
                "total_count": len(processes),
            }

        except Exception as e:
            self._log_error("获取进程列表", e)
            return {
                "success": False,
                "processes": [],
                "message": str(e),
            }

    def get_process_details(
        self, process_id: str, process_name: str, process_type: str
    ) -> Dict[str, Any]:
        """获取单个进程详细信息.

        Args:
            process_id: 进程ID
            process_name: 进程名称
            process_type: 进程类型

        Returns:
            Dict: 进程详细信息
        """
        try:
            # 获取进程指标
            metrics = self.process_monitor.get_process_metrics(
                process_id, process_name, process_type
            )

            if not metrics:
                return {
                    "success": False,
                    "message": f"无法获取进程指标: {process_id}",
                }

            # 获取历史数据
            history = self.process_monitor.get_metrics_history(process_id, limit=100)

            return {
                "success": True,
                "metrics": {
                    "process_id": metrics.process_id,
                    "process_name": metrics.process_name,
                    "process_type": metrics.process_type,
                    "status": metrics.status,
                    "cpu_percent": metrics.cpu_percent,
                    "memory_mb": metrics.memory_mb,
                    "memory_percent": metrics.memory_percent,
                    "disk_read_mbps": metrics.disk_read_mbps,
                    "disk_write_mbps": metrics.disk_write_mbps,
                    "network_recv_mbps": metrics.network_recv_mbps,
                    "network_send_mbps": metrics.network_send_mbps,
                    "timestamp": metrics.timestamp.isoformat(),
                },
                "history": history,
            }

        except Exception as e:
            self._log_error("获取进程详细信息", e)
            return {
                "success": False,
                "message": str(e),
            }

    def get_process_bottleneck(
        self, process_id: str, process_name: str, process_type: str
    ) -> Dict[str, Any]:
        """获取进程瓶颈分析结果.

        Args:
            process_id: 进程ID
            process_name: 进程名称
            process_type: 进程类型

        Returns:
            Dict: 瓶颈分析结果
        """
        try:
            # 获取进程指标
            metrics = self.process_monitor.get_process_metrics(
                process_id, process_name, process_type
            )

            if not metrics:
                return {
                    "success": False,
                    "message": f"无法获取进程指标: {process_id}",
                }

            # 瓶颈分析
            bottleneck_result = self.bottleneck_analyzer.analyze_by_type(metrics)

            return {
                "success": True,
                "bottleneck": {
                    "process_id": bottleneck_result.process_id,
                    "process_name": bottleneck_result.process_name,
                    "process_type": bottleneck_result.process_type,
                    "bottleneck_type": bottleneck_result.bottleneck,
                    "bottleneck_percent": bottleneck_result.bottleneck_percent,
                    "details": bottleneck_result.details,
                    "suggestion": bottleneck_result.suggestion,
                },
            }

        except Exception as e:
            self._log_error("获取进程瓶颈", e)
            return {
                "success": False,
                "message": str(e),
            }

    def set_monitoring_interval(self, interval: int) -> Dict[str, Any]:
        """设置监控推送频率.

        Args:
            interval: 推送间隔（秒），范围1-10

        Returns:
            Dict: 设置结果
        """
        try:
            # 设置ServiceHealthChecker的推送频率
            self.service_health_checker.set_monitoring_interval(interval)

            return {
                "success": True,
                "message": f"监控推送频率已设置为 {interval} 秒",
                "interval": interval,
            }

        except Exception as e:
            self._log_error("设置监控频率", e)
            return {
                "success": False,
                "message": str(e),
            }

    def scan_corrupted_files(
        self, auto_delete: bool = False, progress_callback=None
    ) -> Dict[str, Any]:
        """扫描并清理损坏的Parquet文件.

        Args:
            auto_delete: 是否自动删除损坏文件
            progress_callback: 进度回调函数

        Returns:
            Dict: 扫描结果 {"success": bool, "result": {"corrupted": [...], "deleted": [...]}}
        """
        try:
            # 直接导入并使用StorageManager
            from backend.infrastructure.data_module_vnpy.data_quality import StorageManager

            storage_manager = StorageManager()

            # 调用扫描方法，传入进度回调
            result = storage_manager.scan_and_repair_corrupted_files(
                auto_delete=auto_delete, progress_callback=progress_callback
            )

            return {
                "success": True,
                "message": "扫描完成",
                "result": result,
            }

        except Exception as e:
            self._log_error("扫描损坏文件", e)
            return {
                "success": False,
                "message": str(e),
                "result": {"corrupted": [], "deleted": []},
            }
