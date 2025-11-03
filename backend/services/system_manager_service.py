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
import os
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Union

from backend.core.service_base import BaseService
from backend.core.models import UnifiedMarketData, get_data_model_manager
from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor
from backend.infrastructure.system_vnpy import NetworkTester, PortScanner
from backend.services.database_adapter import get_db_manager
from backend.core.config import get_settings

# 专用logger - 日志埋点v4.0
logger_monitor = logging.getLogger("backend.system.monitor")
logger_alert = logging.getLogger("backend.system.alert")

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
        self.logger.info("日志数据库使用统一database：%s", db_path)

    def add_log_record(self, log_data: Dict[str, Any]) -> None:
        """添加日志记录（使用统一database）.

        Args:
            log_data: 日志数据字典
        """
        try:
            # 使用database_adapter的统一接口
            self.db_manager.execute_update(
                """
                INSERT OR IGNORE INTO system_logs
                (timestamp, level, module, message, extra)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    log_data["timestamp"],
                    log_data["level"],
                    log_data["module"],
                    log_data["message"],
                    json.dumps(
                        {
                            "logger_name": log_data.get("logger_name"),
                            "function": log_data.get("function"),
                            "line": log_data.get("line"),
                            "exception": log_data.get("exception"),
                            "thread": log_data.get("thread"),
                            "filename": log_data.get("filename"),
                        }
                    ),
                ),
            )

        except Exception:
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
                if log.get("extra"):
                    try:
                        extra_data = json.loads(log["extra"])
                        log.update(extra_data)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

            return results

        except Exception as e:
            self.logger.error("日志查询失败：%s", e)
            return []

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息（使用统一database）.

        Returns:
            统计信息字典
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=7)).isoformat()

            # 按级别统计
            level_results = self.db_manager.execute_query(
                """
                SELECT level, COUNT(*) as count
                FROM system_logs
                WHERE timestamp >= ?
                GROUP BY level
            """,
                (cutoff_time,),
            )
            level_stats = {row["level"]: row["count"] for row in level_results}

            # 按模块统计
            module_results = self.db_manager.execute_query(
                """
                SELECT module, COUNT(*) as count
                FROM system_logs
                WHERE timestamp >= ? AND module IS NOT NULL
                GROUP BY module
                ORDER BY count DESC
                LIMIT 10
            """,
                (cutoff_time,),
            )
            module_stats = [
                {"module": row["module"], "count": row["count"]} for row in module_results
            ]

            # 总记录数
            total_results = self.db_manager.execute_query(
                "SELECT COUNT(*) as total FROM system_logs"
            )
            total_count = total_results[0]["total"] if total_results else 0

            return {
                "total_count": total_count,
                "level_stats": level_stats,
                "module_stats": module_stats,
                "recent_days": 7,
            }

        except Exception as e:
            self.logger.error("获取日志统计失败：%s", e)
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
                "DELETE FROM system_logs WHERE timestamp < ?", (cutoff_time,)
            )

            self.logger.info("清理了 %d 条旧日志", deleted_count)
            return deleted_count

        except Exception as e:
            self.logger.error("清理旧日志失败：%s", e)
            return 0

    def delete_all_logs(self) -> int:
        """删除所有日志记录（使用统一database）.

        Returns:
            删除的记录数量
        """
        with self._lock:
            try:
                # 先获取总数
                count_results = self.db_manager.execute_query(
                    "SELECT COUNT(*) as total FROM system_logs"
                )
                count = count_results[0]["total"] if count_results else 0

                # 删除所有记录
                self.db_manager.execute_update("DELETE FROM system_logs")
                self.logger.info("已删除所有日志记录，共 %d 条", count)
                return count

            except Exception as e:
                self.logger.error("删除所有日志失败：%s", e)
                raise

    def delete_logs_by_ids(self, log_ids: List[int]) -> int:
        """根据ID列表删除日志（使用统一database）.

        Args:
            log_ids: 日志ID列表

        Returns:
            删除的记录数量
        """
        if not log_ids:
            return 0

        with self._lock:
            try:
                placeholders = ",".join("?" * len(log_ids))
                sql = f"DELETE FROM system_logs WHERE id IN ({placeholders})"
                deleted_count = self.db_manager.execute_update(sql, tuple(log_ids))
                self.logger.info("已删除 %d 条日志记录", deleted_count)
                return deleted_count

            except Exception as e:
                self.logger.error("批量删除日志失败：%s", e)
                raise


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
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录.

        Args:
            record: 日志记录
        """
        try:
            # 跳过日志系统本身的记录，避免递归
            if record.name.startswith("backend.services.system_manager.log_manager"):
                return

            # 增强递归检测：检查是否在日志处理过程中
            if hasattr(record, "_in_log_handler"):
                return

            # 标记当前记录正在被日志处理器处理
            record._in_log_handler = True

            # 提取异常信息
            exception_text = ""
            if record.exc_info:
                exception_text = (
                    self.formatter.formatException(record.exc_info) if self.formatter else ""
                )

            # 原始消息
            original_message = record.getMessage()
            message_to_store = original_message

            # 🔥 周期性错误计数处理（对DEBUG、WARNING、ERROR和CRITICAL级别）
            if record.levelno >= logging.DEBUG:
                try:
                    from backend.infrastructure.system_vnpy import get_error_counter

                    error_counter = get_error_counter()
                    exc_type_name = (
                        record.exc_info[0].__name__
                        if record.exc_info and record.exc_info[0]
                        else record.levelname
                    )

                    # 记录错误并获取计数信息
                    need_detail, count, is_milestone = error_counter.record_error(
                        exc_type_name, original_message, exception_text
                    )

                    # 如果是重复错误（非首次且非里程碑），修改消息
                    if not need_detail and not is_milestone:
                        message_to_store = f"[重复错误×{count}] {original_message}"

                    # Terminal输出处理（仅首次或里程碑时详细输出）
                    if need_detail or is_milestone:
                        # 保持原始详细输出
                        pass
                    else:
                        # 简化Terminal输出（通过修改record.msg）
                        # 注意：这不会影响数据库存储，因为我们已经提取了message_to_store
                        pass

                except Exception:
                    # 错误计数器失败不影响日志记录
                    pass

            # 构建日志数据
            log_data = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger_name": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "message": message_to_store,  # 使用处理后的消息
                "exception": exception_text,
                "thread": record.thread,
                "thread_name": getattr(record, "threadName", ""),
                "process": record.process,
                "filename": record.filename,
            }

            # 只在非日志系统模块时才推送，避免递归
            if not record.name.startswith("backend.services.system_manager"):
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
            if hasattr(record, "_in_log_handler"):
                delattr(record, "_in_log_handler")


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
        self._batch_lock = threading.RLock()  # 使用可重入锁，避免死锁
        self._batch_timer: Optional[threading.Timer] = None

        # 处理器注册标志
        self._handler_registered: bool = False

    def initialize(self) -> bool:
        """初始化日志管理系统.

        Returns:
            是否初始化成功
        """
        try:
            init_start = time.time()

            print("[启动] 日志管理系统初始化开始...")

            # 创建自定义日志处理器
            log_handler = LogRecordHandler(self)

            # 添加到根日志记录器
            root_logger = logging.getLogger()
            root_logger.addHandler(log_handler)
            root_logger.setLevel(logging.DEBUG)

            # 🔧 修复：启动定期刷新定时器，确保少量日志也能写入数据库
            # 之前只有缓冲区>=10条才刷新，导致少量日志永远不会写入
            self._start_batch_flush_timer()

            total_time = time.time() - init_start
            print(f"[启动] ✅ 日志管理系统初始化完成，总耗时: {total_time:.3f}s")

            return True

        except Exception as e:
            print(f"[启动] ❌ 日志管理系统初始化异常: {e}")
            self.logger.error("日志管理系统初始化失败：%s", e)
            return False

    def _start_batch_flush_timer(self) -> None:
        """启动批量刷新定时器（定期刷新，确保日志不会积压）."""
        if self._batch_timer:
            self._batch_timer.cancel()

        self._batch_timer = threading.Timer(2.0, self._batch_flush_loop)
        self._batch_timer.daemon = True
        self._batch_timer.start()

    def _batch_flush_loop(self) -> None:
        """批量刷新循环（每2秒刷新一次）."""
        try:
            self._flush_batch_buffer()
        except Exception:
            pass
        finally:
            # 重新启动定时器
            if not hasattr(self, "_is_shutting_down") or not self._is_shutting_down:
                self._start_batch_flush_timer()

    def shutdown(self) -> None:
        """关闭日志管理系统."""
        try:
            print("[DEBUG] 关闭日志管理系统...")

            # 标记正在关闭，停止定时器循环
            self._is_shutting_down = True

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

            print("[DEBUG] ✅ 日志管理系统已关闭")
            self.logger.info("日志管理系统已关闭")

        except Exception as e:
            print(f"[DEBUG] 关闭日志管理系统失败: {e}")
            self.logger.error("关闭日志管理系统失败：%s", e)

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
            if hasattr(self.event_engine, "is_active") and not self.event_engine.is_active():
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
                    pass  # 静默处理，避免日志循环

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
                    f.write(
                        f"[{log['timestamp']}] {log['level']} {log['module']}.{log['function_name']}:{log['line_number']} - {log['message']}\n"
                    )
                    if log["exception"]:
                        f.write(f"Exception: {log['exception']}\n")

            self.logger.info("日志已导出到：%s，共 %d 条记录", file_path, len(logs))
            return True

        except Exception as e:
            self.logger.error("导出日志失败：%s", e)
            return False

    def delete_all_logs(self) -> int:
        """删除所有日志记录.

        Returns:
            删除的记录数量
        """
        return self.database.delete_all_logs()

    def delete_logs_by_ids(self, log_ids: List[int]) -> int:
        """根据ID列表删除日志记录.

        Args:
            log_ids: 日志ID列表

        Returns:
            删除的记录数量
        """
        return self.database.delete_logs_by_ids(log_ids)


# =============================================================================
# 全局实例和初始化函数
# =============================================================================

_log_manager: Optional[LogManager] = None
_log_manager_lock = threading.Lock()


def get_log_manager(event_engine=None, force_reinit: bool = False) -> LogManager:
    """获取全局日志管理器实例.

    Args:
        event_engine: VnPy事件引擎实例（可选）
        force_reinit: 是否强制重新初始化（用于注入event_engine）

    Returns:
        LogManager实例
    """
    global _log_manager
    if _log_manager is None:
        with _log_manager_lock:
            if _log_manager is None:
                _log_manager = LogManager()
                # 🔧 关键修复：创建后立即初始化，确保LogRecordHandler被注册
                # 否则日志永远不会写入数据库
                _log_manager.initialize()
                _log_manager._handler_registered = True

    # 如果需要注入event_engine
    if event_engine is not None and _log_manager.event_engine is None:
        with _log_manager_lock:
            _log_manager.event_engine = event_engine

    return _log_manager


def initialize_logging_system(event_engine=None, config: Optional[Dict[str, Any]] = None) -> bool:
    """初始化日志系统（使用统一database）."""
    try:
        start_time = time.time()
        print("[启动] 日志系统初始化开始...")

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

        self.log_levels = log_levels or ["ERROR", "CRITICAL"]
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
            if self.log_levels and log_data.get("level") not in self.log_levels:
                return False

            # 检查模块
            if self.modules and log_data.get("module") not in self.modules:
                return False

            # 检查关键字
            if self.keywords:
                message = log_data.get("message", "").lower()
                if not any(keyword.lower() in message for keyword in self.keywords):
                    return False

            # 检查抑制窗口
            suppression_key = (
                f"{self.rule_id}:{log_data.get('module', '')}:{log_data.get('level', '')}"
            )
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
        if hasattr(self, "_initialized"):
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
            alert.notes = getattr(alert, "notes", []) + [f"[ACKNOWLEDGED] {note}"]

        return True

    def resolve_alert(self, alert_id: str, note: str = "") -> bool:
        """解决告警."""
        alert = self.get_alert(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()
        if note:
            alert.notes = getattr(alert, "notes", []) + [f"[RESOLVED] {note}"]

        return True

    def configure_notifications(
        self, notification_type: NotificationType, config: Dict[str, Any]
    ) -> bool:
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
        self.logger.info("告警数据库使用统一database：%s", db_path)

    def save_alert(self, alert: Alert) -> None:
        """保存告警记录（使用统一database）."""
        try:
            # 使用database_adapter保存
            self.db_manager.execute_update(
                """
                INSERT OR REPLACE INTO alert_records
                (alert_id, rule_id, severity, status, message, context,
                 created_at, updated_at, acknowledged_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    alert.alert_id,
                    alert.rule.rule_id,
                    alert.severity.value,
                    alert.status.value,
                    alert.message,
                    (
                        json.dumps(
                            {
                                "rule_name": alert.rule.name,
                                "context": alert.context,
                                "source_type": getattr(alert, "source_type", "log"),
                                "source_data": getattr(alert, "source_data", None),
                                "notes": alert.notes,
                            }
                        )
                        if (alert.context or alert.notes)
                        else None
                    ),
                    alert.created_at.isoformat(),
                    alert.updated_at.isoformat(),
                    alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    alert.resolved_at.isoformat() if alert.resolved_at else None,
                ),
            )

        except Exception as e:
            self.logger.error("告警数据库保存失败：%s", e)

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
                if alert.get("context"):
                    try:
                        context_data = json.loads(alert["context"])
                        alert.update(context_data)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

            return results

        except Exception as e:
            self.logger.error("查询告警失败：%s", e)
            return []

    def update_alert_status(self, alert_id: str, status: AlertStatus, note: str = "") -> bool:
        """更新告警状态（使用统一database）."""
        try:
            now = datetime.now().isoformat()

            if status == AlertStatus.ACKNOWLEDGED:
                self.db_manager.execute_update(
                    """
                    UPDATE alert_records
                    SET status = ?, acknowledged_at = ?, updated_at = ?
                    WHERE alert_id = ?
                """,
                    (status.value, now, now, alert_id),
                )
            elif status == AlertStatus.RESOLVED:
                self.db_manager.execute_update(
                    """
                    UPDATE alert_records
                    SET status = ?, resolved_at = ?, updated_at = ?
                    WHERE alert_id = ?
                """,
                    (status.value, now, now, alert_id),
                )
            else:
                self.db_manager.execute_update(
                    """
                    UPDATE alert_records
                    SET status = ?, updated_at = ?
                    WHERE alert_id = ?
                """,
                    (status.value, now, alert_id),
                )

            return True

        except Exception as e:
            self.logger.error("更新告警状态失败：%s", e)
            return False

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """根据告警ID获取单个告警记录.

        Args:
            alert_id: 告警ID

        Returns:
            告警记录字典，如果不存在则返回None
        """
        try:
            query = """
                SELECT * FROM alert_records
                WHERE alert_id = ?
            """

            results = self.db_manager.execute_query(query, (alert_id,))

            if results:
                alert = results[0]
                # 解析context字段
                if alert.get("context"):
                    try:
                        context_data = json.loads(alert["context"])
                        alert.update(context_data)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                return alert
            return None

        except Exception as e:
            self.logger.error("获取告警失败：%s", e)
            return None

    def get_unresolved_alerts(self) -> List[Dict[str, Any]]:
        """获取未解决的告警."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                cursor = conn.execute(
                    """
                    SELECT * FROM alerts
                    WHERE status != 'resolved'
                    ORDER BY created_at DESC
                """
                )

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
                    cutoff_time = datetime.now().timestamp() - (older_than_days * 24 * 3600)

                    cursor = conn.execute(
                        """
                        DELETE FROM alerts
                        WHERE status = 'resolved' AND created_at < ?
                    """,
                        (cutoff_time,),
                    )

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

            if hasattr(alert_engine, "evaluate_rules") and not hasattr(
                alert_engine, "_original_evaluate_rules"
            ):
                original_evaluate_rules = alert_engine.evaluate_rules

                def patched_evaluate_rules(context: Dict[str, Any]) -> List[Alert]:
                    try:
                        triggered_alerts = original_evaluate_rules(context)

                        for alert in triggered_alerts:
                            if hasattr(alert.rule, "log_levels"):
                                alert.source_type = "log"
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
                "source_type": getattr(alert, "source_type", "unknown"),
            }

            event = Event(EVENT_ALERT_CREATED, event_data)
            self.event_engine.put(event)

        except Exception:
            pass

    def publish_alert_updated(self, alert: Union[Alert, Dict[str, Any]]) -> None:
        """发布告警更新事件.

        Args:
            alert: Alert对象或告警字典
        """
        if not self.event_engine:
            return

        try:
            from vnpy.event import Event

            # 处理字典类型
            if isinstance(alert, dict):
                event_data = {
                    "alert_id": alert.get("alert_id"),
                    "rule_id": alert.get("rule_id"),
                    "rule_name": alert.get("rule_name"),
                    "severity": alert.get("severity"),
                    "status": alert.get("status"),
                    "message": alert.get("message"),
                    "context": alert.get("context"),
                    "updated_at": alert.get("updated_at"),
                    "source_type": alert.get("source_type", "unknown"),
                }
            # 处理Alert对象
            else:
                event_data = {
                    "alert_id": alert.alert_id,
                    "rule_id": alert.rule.rule_id,
                    "rule_name": alert.rule.name,
                    "severity": alert.severity.value,
                    "status": alert.status.value,
                    "message": alert.message,
                    "context": alert.context,
                    "updated_at": alert.updated_at.isoformat(),
                    "source_type": getattr(alert, "source_type", "unknown"),
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
    rules.append(
        LogAlertRule(
            rule_id="log_error_monitoring",
            name="ERROR级别日志监控",
            log_levels=["ERROR"],
            severity=AlertSeverity.ERROR,
            description="监控所有ERROR级别日志记录",
            suppression_window=60,
            enabled=True,
            priority=2,
        )
    )

    # CRITICAL级别日志监控
    rules.append(
        LogAlertRule(
            rule_id="log_critical_monitoring",
            name="CRITICAL级别日志监控",
            log_levels=["CRITICAL"],
            severity=AlertSeverity.CRITICAL,
            description="监控所有CRITICAL级别日志记录",
            suppression_window=30,
            enabled=True,
            priority=1,
        )
    )

    # 连接失败监控
    rules.append(
        LogAlertRule(
            rule_id="log_connection_failures",
            name="连接失败监控",
            keywords=[
                "连接失败",
                "连接超时",
                "网络错误",
                "Connection failed",
                "Connection timeout",
            ],
            severity=AlertSeverity.WARNING,
            description="监控连接相关的错误日志",
            suppression_window=120,
            enabled=True,
            priority=3,
        )
    )

    # 数据库错误监控
    rules.append(
        LogAlertRule(
            rule_id="log_database_errors",
            name="数据库错误监控",
            keywords=["数据库错误", "SQL错误", "连接池", "Database error", "SQL error"],
            severity=AlertSeverity.ERROR,
            description="监控数据库相关的错误日志",
            suppression_window=60,
            enabled=True,
            priority=2,
        )
    )

    return rules


def get_default_system_alert_rules() -> List[AlertRule]:
    """获取默认的系统告警规则."""
    rules = []

    rules.append(
        AlertRule(
            rule_id="system_cpu_high",
            name="CPU使用率过高",
            condition="cpu_percent > 90",
            severity=AlertSeverity.WARNING,
            enabled=True,
            priority=3,
            group="system_resource",
            description="CPU使用率超过90%时触发告警",
        )
    )

    rules.append(
        AlertRule(
            rule_id="system_memory_low",
            name="内存不足",
            condition="memory_percent > 85",
            severity=AlertSeverity.ERROR,
            enabled=True,
            priority=2,
            group="system_resource",
            description="内存使用率超过85%时触发告警",
        )
    )

    return rules


def get_default_business_alert_rules() -> List[AlertRule]:
    """获取默认的业务告警规则."""
    rules = []

    rules.append(
        AlertRule(
            rule_id="business_data_download_failure_rate",
            name="数据下载失败率过高",
            condition="download_failure_rate > 10",
            severity=AlertSeverity.ERROR,
            enabled=True,
            priority=3,
            group="data_quality",
            description="数据下载失败率超过10%时触发告警",
        )
    )

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
        print("[启动] 告警系统初始化开始...")

        if config is None:
            config = {"db_path": "data/alerts.db", "suppression_window": 300}

        global _alert_database
        with _alert_database_lock:
            _alert_database = AlertDatabase(config.get("db_path", "data/alerts.db"))

        # 创建告警事件发布器（在构造函数中注册事件监听器）
        _alert_publisher = AlertEventPublisher(event_engine, _alert_database)  # noqa: F841

        # 初始化默认告警规则（延迟到后台线程）
        def _create_default_rules_async():
            time.sleep(2)
            try:
                alert_engine = AlertEngine()

                for rule in get_default_log_alert_rules():
                    alert_engine.add_rule(rule)

                print("[DEBUG] ✅ 默认日志告警规则创建完成")
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
        self.logger.info("性能监控已启动，间隔：%s秒", interval)

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
                self.logger.error("监控循环异常：%s", e)
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
            self.logger.error("收集性能指标失败：%s", e)

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
            self.logger.error("收集核心模块指标失败：%s", e)
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
            self.logger.error("检查阈值失败：%s", e)

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

        self.logger.warning("监控告警：%s - %s", title, message)

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
            "metrics_count": {
                category: len(metrics) for category, metrics in self._metrics.items()
            },
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
            self.logger.info("已重置类别指标：%s", category)

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
                self.logger.error("加载测试模块失败 %s：%s", test_module, e)
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
                "failures": [
                    {"test": str(test), "error": error} for test, error in result.failures
                ],
                "errors": [{"test": str(test), "error": error} for test, error in result.errors],
            },
        }

        self._test_results[datetime.now().isoformat()] = test_result
        self.logger.info(
            "单元测试完成：%s 个测试, %s 个失败, %s 个错误",
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
        self.logger.info("正在运行综合测试")

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

        self.logger.info("综合测试完成 - 健康评分：%s", report["summary"]["health_score"])
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
                    self.logger.error("事件循环异常：%s", e)

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()
            self.logger.info("异步任务管理器启动完成")

        except Exception as e:
            self.logger.error("启动事件循环失败：%s", e)

    def stop_event_loop(self):
        """停止事件循环."""
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.executor.shutdown(wait=True)
                self.logger.info("异步任务管理器停止完成")
            except Exception as e:
                self.logger.error("停止事件循环失败：%s", e)

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
                self.logger.error("任务执行失败 %s：%s", task_id, e)
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
                self.logger.error("异步任务执行失败 %s：%s", task_id, e)
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
            self.logger.error("同步数据处理失败：%s", e)
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

        # ========== 🆕 托管模式统一日志系统 ==========

        # 获取LoggingHub实例（已在启动时配置好handlers）
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
        from backend.services.database_adapter import get_db_manager

        self.logging_hub = get_logging_hub()

        # 只配置EventEngine和DatabaseManager（handlers已在启动时配置）
        if hasattr(self.main_engine, "event_engine") and self.main_engine.event_engine:
            self.logging_hub.set_event_engine(self.main_engine.event_engine)
            self.logger.info("✅ LoggingHub已注入EventEngine")

        self.logging_hub.set_db_manager(get_db_manager())
        self.logger.info("✅ LoggingHub已注入DatabaseManager")

        self.logger.info("✅ LoggingHub配置完成（handlers已在启动时配置）")

        # 日志管理器（保留查询功能）
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
        from backend.infrastructure.system_vnpy import (
            LogAnalyzer,
            PerformanceAnalyzer,
        )

        self.log_analyzer = LogAnalyzer()
        self.performance_analyzer = PerformanceAnalyzer()
        # AutoFixer 在新架构中未实现，移除引用
        # self.auto_fixer = AutoFixer()

        # 新增：服务管理工具
        from backend.infrastructure.system_vnpy import (
            ServiceHealthChecker,
            ServiceRestarter,
        )

        self.service_health_checker = ServiceHealthChecker()
        self.service_restarter = ServiceRestarter()

        # 新增：进程监控工具
        from backend.infrastructure.system_vnpy.monitor_system import (
            ProcessMonitor,
            ProcessBottleneckAnalyzer,
        )

        self.process_monitor = ProcessMonitor()
        self.bottleneck_analyzer = ProcessBottleneckAnalyzer()

        # IPC模式和权限检查
        self._ipc_mode = "disabled"  # disabled, native, fallback
        self._admin_privileges = self._check_admin_privileges()

        # native_ipc通信管道（连接到独立监控进程）
        try:
            from backend.infrastructure.native_ipc import AsyncIPCPipe, IPC_AVAILABLE

            if IPC_AVAILABLE and self._admin_privileges:
                self._query_pipe = None  # 客户端：查询监控数据
                self._status_pipe = None  # 客户端：推送服务状态到监控进程
                self._alerts_pipe = None  # 服务端：接收监控进程推送的告警
                self._ipc_available = True
                self.logger.info("✅ Native IPC可用，管理员权限已获得")
            else:
                self._query_pipe = None
                self._status_pipe = None
                self._alerts_pipe = None
                self._ipc_available = False
                if not IPC_AVAILABLE:
                    self.logger.warning("⚠️ Native IPC扩展不可用，将使用降级模式")
                elif not self._admin_privileges:
                    self.logger.warning("⚠️ 未获得管理员权限，Native IPC不可用，将使用降级模式")
        except ImportError:
            self._query_pipe = None
            self._status_pipe = None
            self._alerts_pipe = None
            self._ipc_available = False
            self.logger.warning("⚠️ native_ipc模块不可用，将使用降级模式")

        self._monitoring_interval = 2  # 默认2秒
        self._ipc_loop = None  # asyncio事件循环（用于native_ipc）
        self._ipc_tasks = []  # 后台IPC任务

        # 监控数据缓存（避免频繁跨进程查询）
        self._monitor_data_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._last_query_time = 0.0
        self._cache_ttl = 1.0  # 缓存1秒

        # 告警缓存（接收监控进程推送的告警）- 新增
        self._alert_cache: List[Dict[str, Any]] = []
        self._alert_cache_lock = threading.Lock()

        # 监控数据推送线程（事件驱动架构）
        self._monitoring_push_running = False
        self._monitoring_push_thread: Optional[threading.Thread] = None
        self._max_alert_cache_size = 1000  # 最多缓存1000条告警

        # 服务状态推送定时器（QTimer在主线程）
        self._status_push_timer = None

        # 告警接收线程
        self._alert_receiver_thread = None
        self._alert_receiver_running = False

        # 🔄 设置日志阶段为启动阶段
        self.logging_hub.set_stage("startup")
        self.logger.info("📍 日志阶段切换: startup（启动阶段）")

        self.logger.info("系统管理服务已创建")

    def _check_admin_privileges(self) -> bool:
        """检查是否有管理员权限."""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    def _do_initialize(self) -> bool:
        """初始化系统管理服务（无后台线程，Qt线程安全）."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("正在初始化系统管理服务...")
            self.logger.info("=" * 60)

            # 检查 EventEngine 是否可用
            if not self.event_engine:
                self.logger.error("❌ EventEngine不可用")
                self.logger.error("这通常意味着VNPy核心初始化失败")
                self.logger.error("SystemManagerService需要EventEngine用于事件通信")
                # 🎯 不再尝试创建，因为EventEngine应该已在主线程创建
                return False

            self.logger.info("✅ EventEngine可用")

            # 初始化日志管理系统（注入EventEngine）
            try:
                self.logger.info("正在初始化日志管理系统...")
                self.log_manager = get_log_manager(
                    event_engine=self.event_engine, force_reinit=True
                )
                self.logger.info("✅ 日志管理系统初始化完成（已注入EventEngine）")
            except Exception as e:
                self.logger.error("❌ 日志管理系统初始化失败：%s", e, exc_info=True)
                # 不中断启动流程

            # 初始化native_ipc通信管道
            if not self._ipc_available:
                self.logger.error("❌ native_ipc不可用，监控功能将受限")
                return False

            from PySide6.QtCore import QTimer

            # 等待监控进程就绪（读取就绪信号文件）
            max_wait = 15.0
            wait_start = time.time()
            signal_file = Path("logs/monitor_ready.signal")

            while not signal_file.exists() and (time.time() - wait_start) < max_wait:
                time.sleep(0.5)

            if not signal_file.exists():
                self.logger.warning("⚠️ 监控进程未就绪（未找到就绪信号文件），将继续尝试初始化")

            # 启动asyncio事件循环（在后台线程中）
            self._start_ipc_event_loop()

            # 初始化native_ipc管道（异步）
            # 使用run_coroutine_threadsafe在线程中运行
            loop = self._ipc_loop
            if loop:
                # 创建monitor_alerts服务端（等待监控进程连接）
                alerts_task = asyncio.run_coroutine_threadsafe(
                    self._initialize_alerts_server(), loop
                )

                # 创建monitor_query客户端（连接到监控进程）
                query_task = asyncio.run_coroutine_threadsafe(self._initialize_query_client(), loop)

                # 创建monitor_status客户端（连接到监控进程）
                status_task = asyncio.run_coroutine_threadsafe(
                    self._initialize_status_client(), loop
                )

                # 等待管道初始化（最多等待5秒）
                try:
                    alerts_task.result(timeout=5.0)
                    query_task.result(timeout=5.0)
                    status_task.result(timeout=5.0)
                    self.logger.info("✅ native_ipc管道初始化完成")
                    self._ipc_mode = "native"
                except Exception as e:
                    self.logger.warning("⚠️ native_ipc管道初始化失败，降级到基础模式: %s", e)
                    self._ipc_mode = "fallback"
                    self._ipc_available = False
            else:
                self.logger.warning("⚠️ asyncio事件循环未启动，降级到基础模式")
                self._ipc_mode = "fallback"
                self._ipc_available = False

            # 使用QTimer在主线程定时推送服务状态
            self._status_push_timer = QTimer()
            self._status_push_timer.timeout.connect(self._push_service_status)
            self._status_push_timer.start(self._monitoring_interval * 1000)
            self.logger.info("✅ 服务状态推送定时器已启动（Qt主线程）")

            # 启动监控数据推送线程（事件驱动架构）
            self._start_monitoring_push_thread()

            self.logger.info("=" * 60)
            self.logger.info("✅ 系统管理服务初始化完成（native_ipc通信已就绪）")
            self.logger.info("=" * 60)

            # 🔄 启动完成，切换日志阶段到数据感知阶段
            self.logging_hub.set_stage("sensing")
            self.logger.info("📍 日志阶段切换: sensing（数据感知阶段）")

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _start_ipc_event_loop(self):
        """启动asyncio事件循环（在后台线程中）."""
        if self._ipc_loop is not None:
            return

        def run_loop():
            """在后台线程中运行事件循环."""
            import platform

            if platform.system() == "Windows":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._ipc_loop = loop
            self.logger.info("✅ IPC事件循环已启动（后台线程）")
            loop.run_forever()

        loop_thread = threading.Thread(target=run_loop, name="IPCEventLoopThread", daemon=True)
        loop_thread.start()

        # 等待事件循环创建
        max_wait = 3.0
        wait_start = time.time()
        while self._ipc_loop is None and (time.time() - wait_start) < max_wait:
            time.sleep(0.1)

    async def _initialize_alerts_server(self):
        """初始化monitor_alerts服务端（接收监控进程推送的告警）."""
        try:
            from backend.infrastructure.native_ipc import AsyncIPCPipe

            self._alerts_pipe = await AsyncIPCPipe.server("monitor_alerts")
            self.logger.info("[IPC] ✅ 告警服务端管道已创建: monitor_alerts")

            # 启动告警接收协程
            task = asyncio.create_task(self._alerts_server_loop())
            self._ipc_tasks.append(task)

        except Exception as e:
            self.logger.error("[IPC] ❌ 创建告警服务端管道失败: %s", e, exc_info=True)
            raise

    async def _initialize_query_client(self):
        """初始化monitor_query客户端（查询监控数据）."""
        try:
            from backend.infrastructure.native_ipc import AsyncIPCPipe

            # 等待监控进程创建服务端（最多等待10秒）
            max_wait = 10.0
            wait_start = time.time()

            while (time.time() - wait_start) < max_wait:
                try:
                    self._query_pipe = await AsyncIPCPipe.client("monitor_query")
                    self.logger.info("[IPC] ✅ 查询客户端管道已创建: monitor_query")
                    return
                except FileNotFoundError:
                    # 服务端未创建，等待后重试
                    await asyncio.sleep(0.5)
                    continue
                except Exception as e:
                    # 其他异常，记录但继续重试（可能是临时网络问题）
                    self.logger.warning("[IPC] 创建查询客户端管道失败，继续重试: %s", e)
                    await asyncio.sleep(0.5)
                    continue

            raise RuntimeError("监控进程服务端未就绪（超时10秒）")

        except Exception as e:
            self.logger.error("[IPC] ❌ 初始化查询客户端失败: %s", e, exc_info=True)
            raise

    async def _initialize_status_client(self):
        """初始化monitor_status客户端（推送服务状态）."""
        try:
            from backend.infrastructure.native_ipc import AsyncIPCPipe

            # 等待监控进程创建服务端（最多等待10秒）
            max_wait = 10.0
            wait_start = time.time()

            while (time.time() - wait_start) < max_wait:
                try:
                    self._status_pipe = await AsyncIPCPipe.client("monitor_status")
                    self.logger.info("[IPC] ✅ 状态客户端管道已创建: monitor_status")
                    return
                except FileNotFoundError:
                    # 服务端未创建，等待后重试
                    await asyncio.sleep(0.5)
                    continue
                except Exception as e:
                    # 其他异常，记录但继续重试（可能是临时网络问题）
                    self.logger.warning("[IPC] 创建状态客户端管道失败，继续重试: %s", e)
                    await asyncio.sleep(0.5)
                    continue

            raise RuntimeError("监控进程服务端未就绪（超时10秒）")

        except Exception as e:
            self.logger.error("[IPC] ❌ 初始化状态客户端失败: %s", e, exc_info=True)
            raise

    async def _alerts_server_loop(self):
        """告警服务端循环（接收监控进程推送的告警）."""
        if not self._alerts_pipe:
            return

        self.logger.info("[IPC] 告警服务端循环启动...")

        try:
            while True:
                try:
                    # 读取告警数据（使用更大的缓冲区）
                    alert_data = await self._alerts_pipe.read(size=65536)
                    alert = json.loads(alert_data.decode())

                    # 验证告警格式
                    if not isinstance(alert, dict):
                        self.logger.warning("[IPC] 收到无效告警格式：%s", type(alert))
                        continue

                    if alert.get("type") != "alert":
                        self.logger.debug("[IPC] 收到非告警消息：%s", alert.get("type"))
                        continue

                    # 添加到缓存（线程安全）
                    with self._alert_cache_lock:
                        self._alert_cache.append(alert)

                        # 限制缓存大小（FIFO）
                        if len(self._alert_cache) > self._max_alert_cache_size:
                            self._alert_cache.pop(0)

                    # 记录告警
                    severity = alert.get("severity", "unknown")
                    message = alert.get("message", "")

                    if severity == "critical":
                        self.logger.error("[ALERT-CRITICAL] %s", message)
                    elif severity == "warning":
                        self.logger.warning("[ALERT-WARNING] %s", message)
                    else:
                        self.logger.info("[ALERT-INFO] %s", message)

                    # 发送事件到EventEngine（UI可以监听）
                    if self.event_engine:
                        from vnpy.event import Event
                        from backend.infrastructure.system_vnpy import (
                            EVENT_ALERT_CREATED,
                        )

                        event_data = {
                            "alert": alert,
                            "timestamp": alert.get("timestamp"),
                            "severity": severity,
                            "message": message,
                        }
                        event = Event(EVENT_ALERT_CREATED, event_data)
                        self.event_engine.put(event)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    # 🔧 修复：客户端未连接时，降低日志级别到DEBUG，避免频繁输出错误
                    # WinError 536表示管道另一端尚未打开，这是正常情况（监控进程可能还在初始化）
                    error_str = str(e)
                    if "WinError 536" in error_str:
                        self.logger.debug("[IPC] 告警客户端未连接: %s", error_str)
                    else:
                        self.logger.warning("[IPC] 接收告警失败：%s", e)
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error("[IPC] 告警服务端循环异常: %s", e, exc_info=True)

    def _test_ipc_connection(self) -> bool:
        """测试native_ipc连接是否可用，如果失败则尝试重新连接.

        Returns:
            bool: 连接是否成功
        """
        if not self._ipc_loop:
            return False

        try:
            # 首先测试现有连接
            if self._query_pipe:
                future = asyncio.run_coroutine_threadsafe(self._test_query_pipe(), self._ipc_loop)
                try:
                    result = future.result(timeout=3.0)
                    if result:
                        return True
                except Exception:
                    pass  # 测试失败，继续尝试重连

            # 现有连接失败，尝试重新创建连接
            self.logger.info("[IPC] 现有连接失败，尝试重新创建IPC连接...")

            # 关闭旧连接
            if self._query_pipe:
                try:
                    asyncio.run_coroutine_threadsafe(self._close_pipe(self._query_pipe), self._ipc_loop)
                except Exception:
                    pass
                self._query_pipe = None

            if self._status_pipe:
                try:
                    asyncio.run_coroutine_threadsafe(self._close_pipe(self._status_pipe), self._ipc_loop)
                except Exception:
                    pass
                self._status_pipe = None

            # 重新创建连接
            future = asyncio.run_coroutine_threadsafe(self._reconnect_ipc_pipes(), self._ipc_loop)
            result = future.result(timeout=10.0)  # 给重连更多时间

            if result:
                self.logger.info("[IPC] ✅ IPC连接重新创建成功")
                return True
            else:
                self.logger.warning("[IPC] ❌ IPC连接重新创建失败")
                return False

        except Exception as e:
            self.logger.error("[IPC] IPC重连过程异常: %s", e, exc_info=True)
            return False

    async def _reconnect_ipc_pipes(self) -> bool:
        """重新创建IPC管道连接（异步）."""
        try:
            self.logger.info("[IPC] 开始重新创建IPC管道连接...")

            # 重新创建查询客户端
            try:
                await self._initialize_query_client()
            except Exception as e:
                self.logger.error("[IPC] 重新创建查询客户端失败: %s", e)
                return False

            # 重新创建状态客户端
            try:
                await self._initialize_status_client()
            except Exception as e:
                self.logger.error("[IPC] 重新创建状态客户端失败: %s", e)
                # 状态客户端失败不影响查询功能，继续

            # 测试新连接
            if await self._test_query_pipe():
                self.logger.info("[IPC] ✅ IPC管道重连成功")
                return True
            else:
                self.logger.warning("[IPC] ❌ IPC管道重连后测试失败")
                return False

        except Exception as e:
            self.logger.error("[IPC] IPC管道重连异常: %s", e, exc_info=True)
            return False

    async def _test_query_pipe(self) -> bool:
        """测试查询管道（异步）."""
        try:
            if not self._query_pipe:
                return False

            # 发送测试请求
            request = json.dumps({"action": "get_data"}).encode()
            await self._query_pipe.write(request)

            # 读取响应（最多等待2秒，使用更大的缓冲区）
            response_data = await asyncio.wait_for(self._query_pipe.read(size=65536), timeout=2.0)
            response = json.loads(response_data.decode())

            # 检查响应
            if isinstance(response, dict):
                if (
                    "timestamp" in response
                    or "cpu_percent" in response
                    or response.get("status") == "ok"
                ):
                    self.logger.debug("✅ IPC连接测试成功")
                    return True
                elif "error" in response:
                    self.logger.warning("⚠️ IPC响应包含错误: %s", response.get("error"))
                    return False

            return False
        except asyncio.TimeoutError:
            self.logger.warning("⚠️ IPC连接测试超时（监控进程未响应）")
            return False
        except Exception as e:
            self.logger.warning("⚠️ IPC连接测试失败: %s", e)
            return False

    def _push_service_status(self):
        """推送服务状态（在主线程通过QTimer调用）."""
        try:
            from backend.core.base import get_service_manager

            if not self._status_pipe or not self._ipc_loop:
                return

            # 调试信息：检查ServiceHealthChecker实例
            self.logger.debug("ServiceHealthChecker类型: %s", type(self.service_health_checker))
            self.logger.debug("ServiceHealthChecker方法: %s", [m for m in dir(self.service_health_checker) if not m.startswith('_')])
            
            # 采集服务状态
            service_manager = get_service_manager()
            result = self.service_health_checker.check_all_services(service_manager)

            # 推送到监控进程（异步，非阻塞）
            if self._ipc_loop and self._status_pipe:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._push_status_async(result), self._ipc_loop
                    )
                except Exception as e:
                    self.logger.debug("推送服务状态失败：%s", e)

        except Exception as e:
            self.logger.error("推送服务状态失败：%s", e)

    async def _push_status_async(self, status_data: Dict[str, Any]):
        """异步推送服务状态."""
        try:
            if not self._status_pipe:
                return

            status_json = json.dumps(status_data).encode()
            await self._status_pipe.write(status_json)
        except Exception as e:
            self.logger.debug("异步推送服务状态失败：%s", e)

    def trigger_smart_collection(self) -> bool:
        """触发监控进程执行SMART数据采集.

        用于UI界面按需触发SMART数据采集，而非持续轮询。

        Returns:
            bool: 是否成功发送触发命令
        """
        try:
            if not self._query_pipe or not self._ipc_loop:
                logger_monitor.warning("IPC连接不可用，无法触发SMART采集")
                return False

            # 使用run_coroutine_threadsafe在线程中运行异步请求
            future = asyncio.run_coroutine_threadsafe(self._trigger_smart_async(), self._ipc_loop)

            # 等待响应（最多3秒）
            result = future.result(timeout=3.0)
            return result

        except Exception as e:
            logger_monitor.error("触发SMART采集失败: %s", e)
            return False

    async def _trigger_smart_async(self) -> bool:
        """异步触发SMART采集."""
        try:
            if not self._query_pipe:
                return False

            request = json.dumps({"action": "trigger_smart"}).encode()
            await self._query_pipe.write(request)

            # 等待响应（最多2秒，使用更大的缓冲区）
            response_data = await asyncio.wait_for(self._query_pipe.read(size=65536), timeout=2.0)
            response = json.loads(response_data.decode())

            if isinstance(response, dict) and response.get("status") == "success":
                logger_monitor.info("✅ SMART采集触发成功")
                return True

            logger_monitor.warning("SMART采集触发失败")
            return False
        except asyncio.TimeoutError:
            logger_monitor.warning("SMART采集触发超时")
            return False
        except Exception as e:
            logger_monitor.error("触发SMART采集异常: %s", e)
            return False

    def get_alert_cache(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取缓存的告警（供UI查询）.

        Args:
            limit: 返回的最大告警数量（默认100条）

        Returns:
            List[Dict]: 告警列表，按时间倒序
        """
        with self._alert_cache_lock:
            # 返回最新的limit条告警（副本）
            return list(reversed(self._alert_cache[-limit:]))

    def clear_alert_cache(self):
        """清空告警缓存."""
        with self._alert_cache_lock:
            self._alert_cache.clear()
        self.logger.info("告警缓存已清空")

    # ========== 事件驱动监控数据推送 ==========

    def _start_monitoring_push_thread(self):
        """启动监控数据推送线程（事件驱动架构核心）."""
        self._monitoring_push_running = True
        self._monitoring_push_thread = threading.Thread(
            target=self._monitoring_push_loop, name="MonitoringPushThread", daemon=True
        )
        self._monitoring_push_thread.start()
        self.logger.info("✅ 监控数据推送线程已启动（事件驱动模式，10秒间隔，CPU优化）")

    def _monitoring_push_loop(self):
        """监控数据推送循环（替代UI轮询）

        推送频率优化：
        - 启动阶段（前30秒）：3秒间隔（降低CPU负载，减少上下文切换）
        - 正常运行：1秒间隔
        - 降级模式：3秒间隔
        """
        import time

        self.logger.info(
            "[MonitoringPush] 监控数据推送循环已启动（启动阶段10秒间隔，30秒后切换为10秒）- CPU优化版"
        )

        # 🔧 新增：启动阶段检测（降低启动时CPU负载）
        start_time = time.time()
        startup_phase_duration = 30  # 启动阶段30秒

        # 🔧 新增：连续失败计数器和降级模式
        consecutive_failures = 0
        max_consecutive_failures = 5
        degraded_mode = False

        # 🔧 新增：IPC重连计数器
        ipc_retry_interval = 5  # 每5次失败尝试重连一次
        ipc_retry_counter = 0

        while self._monitoring_push_running:
            try:
                # 1. 查询监控数据（支持降级模式）
                if self._ipc_mode == "native":
                    data = self._query_monitoring_data_safe()
                elif self._ipc_mode == "fallback":
                    data = self._get_basic_system_data()
                else:
                    data = self._get_minimal_system_data()

                # 日志已删除：循环输出过于频繁

                if not data:
                    consecutive_failures += 1
                    ipc_retry_counter += 1

                    if consecutive_failures >= max_consecutive_failures and not degraded_mode:
                        self.logger.warning(
                            "[MonitoringPush] 连续%d次查询失败，进入降级模式（降低查询频率）",
                            consecutive_failures,
                        )
                        degraded_mode = True

                    # 🔧 关键修复：仅在native模式下尝试重连IPC
                    if self._ipc_mode == "native" and ipc_retry_counter >= ipc_retry_interval:
                        self.logger.info("[MonitoringPush] 尝试重新连接监控进程...")
                        ipc_retry_counter = 0

                        # 使用改进的重连逻辑
                        if self._test_ipc_connection():
                            self.logger.info("[MonitoringPush] ✅ IPC重连成功")
                            consecutive_failures = 0
                            degraded_mode = False
                            # 重连成功后，立即尝试查询数据
                            continue
                        else:
                            self.logger.warning("[MonitoringPush] ❌ IPC重连失败，将在下次循环继续重试")
                    elif self._ipc_mode == "native":
                        ipc_retry_counter += 1
                    # 非native模式下不进行IPC重连

                    # 降级模式下延长等待时间
                    elapsed = time.time() - start_time
                    if elapsed < startup_phase_duration:
                        wait_time = 10  # 启动阶段：10秒间隔
                    else:
                        wait_time = 15 if degraded_mode else 10  # 正常模式：10秒，降级模式：15秒
                    time.sleep(wait_time)
                    continue

                # 2. 查询成功，重置失败计数器
                if consecutive_failures > 0:
                    if degraded_mode:
                        self.logger.info("[MonitoringPush] 监控数据恢复，退出降级模式")
                        degraded_mode = False
                    consecutive_failures = 0

                # 3. 分发事件（解耦关键）
                self._dispatch_monitoring_events(data)

                # 4. 间隔时间优化：大幅降低频率以减少CPU负载
                elapsed = time.time() - start_time
                if elapsed < startup_phase_duration:
                    wait_time = 10  # 启动阶段：10秒间隔
                else:
                    wait_time = 15 if degraded_mode else 10  # 正常模式：10秒，降级模式：15秒
                time.sleep(wait_time)

            except Exception as e:
                consecutive_failures += 1
                self.logger.error(
                    "[MonitoringPush] 推送失败（%d/%d）：%s",
                    consecutive_failures,
                    max_consecutive_failures,
                    e,
                )
                elapsed = time.time() - start_time
                if elapsed < startup_phase_duration:
                    wait_time = 10  # 启动阶段：10秒间隔
                else:
                    wait_time = 15 if degraded_mode else 10  # 正常模式：10秒，降级模式：15秒
                time.sleep(wait_time)

        self.logger.info("[MonitoringPush] 推送线程已停止")

    def _query_monitoring_data_safe(self) -> Dict[str, Any]:
        """安全查询监控数据（内部使用）."""
        try:
            # 检查缓存
            with self._cache_lock:
                current_time = time.time()
                if (
                    self._monitor_data_cache
                    and (current_time - self._last_query_time) < self._cache_ttl
                ):
                    return self._monitor_data_cache

            # 检查IPC连接
            if not self._query_pipe or not self._ipc_loop:
                return {}

            # 使用run_coroutine_threadsafe在线程中运行异步查询
            future = asyncio.run_coroutine_threadsafe(
                self._query_data_async({"action": "get_data"}), self._ipc_loop
            )

            # 等待响应（最多3秒）
            data = future.result(timeout=3.0)

            # 更新缓存
            if isinstance(data, dict):
                with self._cache_lock:
                    self._monitor_data_cache = data
                    self._last_query_time = time.time()

            return data if isinstance(data, dict) else {}

        except asyncio.TimeoutError:
            self.logger.debug("查询监控数据超时（3秒无响应）")
            return {}
        except Exception as e:
            # 检查是否是管道关闭错误
            error_str = str(e)
            if "WinError 109" in error_str or "管道已结束" in error_str or "pipe" in error_str.lower():
                self.logger.warning("IPC管道连接已断开: %s", e)
            else:
                self.logger.error("查询监控数据失败：%s", e)
            return {}

    async def _query_data_async(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """异步查询数据."""
        try:
            if not self._query_pipe:
                return {}

            # 发送请求
            request_json = json.dumps(request).encode()
            await self._query_pipe.write(request_json)

            # 读取响应（最多等待2秒，使用更大的缓冲区）
            response_data = await asyncio.wait_for(self._query_pipe.read(size=65536), timeout=2.0)
            response = json.loads(response_data.decode())

            return response if isinstance(response, dict) else {}
        except asyncio.TimeoutError:
            self.logger.debug("异步查询超时（2秒无响应）")
            return {}
        except json.JSONDecodeError as e:
            self.logger.error("异步查询JSON解析失败：%s，数据长度：%d", e, len(response_data) if 'response_data' in locals() else 0)
            if 'response_data' in locals():
                self.logger.debug("原始数据前100字符：%s", response_data[:100])
            return {}
        except Exception as e:
            # 检查是否是管道关闭错误
            error_str = str(e)
            if "WinError 109" in error_str or "管道已结束" in error_str or "pipe" in error_str.lower():
                self.logger.debug("IPC管道连接已断开: %s", e)
            else:
                self.logger.error("异步查询失败：%s", e)
            return {}

    def get_current_monitoring_data(self) -> Dict[str, Any]:
        """获取当前监控数据（供UI初始化使用）.

        Returns:
            Dict: 完整的监控数据，包含system, process, service等字段
        """
        if self._ipc_mode == "native":
            return self._query_monitoring_data_safe()
        elif self._ipc_mode == "fallback":
            return self._get_basic_system_data()
        else:
            return self._get_minimal_system_data()

    def get_bandwidth_info(self) -> Dict[str, Any]:
        """获取带宽信息（包含完整测试和延迟测试结果）.

        Returns:
            Dict: {
                "full_test": {"download_mbps": float, "upload_mbps": float, "ping_ms": float, "status": str},
                "ping_test": {"ping_ms": float, "status": str}
            }
        """
        try:
            # 检查IPC连接
            if not self._query_pipe or not self._ipc_loop:
                self.logger.debug("IPC未初始化，无法获取带宽信息")
                return {
                    "full_test": {
                        "download_mbps": None,
                        "upload_mbps": None,
                        "ping_ms": None,
                        "status": "IPC未初始化",
                    },
                    "ping_test": {"ping_ms": None, "status": "IPC未初始化"},
                }

            # 使用run_coroutine_threadsafe在线程中运行异步查询
            future = asyncio.run_coroutine_threadsafe(
                self._query_data_async({"action": "get_bandwidth"}), self._ipc_loop
            )

            # 等待响应（最多3秒）
            result = future.result(timeout=3.0)

            if isinstance(result, dict) and result.get("status") == "success":
                data = result.get("data", {})
                if isinstance(data, dict):
                    self.logger.debug(f"成功从监控进程获取带宽信息: {data}")
                    return data
                else:
                    self.logger.warning("监控进程返回的数据格式错误: %s", type(data))
                    return {
                        "full_test": {
                            "download_mbps": None,
                            "upload_mbps": None,
                            "ping_ms": None,
                            "status": "数据格式错误",
                        },
                        "ping_test": {"ping_ms": None, "status": "数据格式错误"},
                    }
            else:
                # 监控进程返回错误状态
                error_msg = (
                    result.get("message", "未知错误")
                    if isinstance(result, dict)
                    else "响应格式错误"
                )
                self.logger.warning("监控进程返回错误: %s", error_msg)
                self.logger.warning("完整响应内容: %s", result)
                return {
                    "full_test": {
                        "download_mbps": None,
                        "upload_mbps": None,
                        "ping_ms": None,
                        "status": f"监控进程错误: {error_msg}",
                    },
                    "ping_test": {"ping_ms": None, "status": f"监控进程错误: {error_msg}"},
                }

        except asyncio.TimeoutError:
            self.logger.warning("获取带宽信息IPC超时")
            return {
                "full_test": {
                    "download_mbps": None,
                    "upload_mbps": None,
                    "ping_ms": None,
                    "status": "IPC超时",
                },
                "ping_test": {"ping_ms": None, "status": "IPC超时"},
            }
        except Exception as e:
            self.logger.error("获取带宽信息失败：%s", e, exc_info=True)
            return {
                "full_test": {
                    "download_mbps": None,
                    "upload_mbps": None,
                    "ping_ms": None,
                    "status": f"异常: {str(e)}",
                },
                "ping_test": {"ping_ms": None, "status": f"异常: {str(e)}"},
            }

    def _dispatch_monitoring_events(self, data: Dict[str, Any]):
        """分发监控事件到EventEngine（解耦核心）."""
        if not self.event_engine:
            self.logger.warning("[DispatchEvents] EventEngine不可用，跳过事件分发")
            return

        from vnpy.event import Event
        from backend.infrastructure.system_vnpy import (
            EVENT_SYSTEM_METRICS,
            EVENT_HARDWARE_SENSORS,
            EVENT_BOTTLENECK_ANALYSIS,
            EVENT_SCENARIO_ANALYSIS,
            EVENT_PROCESS_MONITORING,
            EVENT_SERVICE_MONITORING,
            EVENT_SMART_DATA,
        )

        # 🔍 诊断日志（仅记录一次）
        if not hasattr(self, "_dispatch_engine_id_logged"):
            self.logger.info(
                f"[分发EventEngine] ID={id(self.event_engine)}, 类型={type(self.event_engine)}"
            )
            self._dispatch_engine_id_logged = True

        # 事件1：系统指标
        if "system" in data and data["system"]:
            event = Event(EVENT_SYSTEM_METRICS, data["system"])
            self.event_engine.put(event)
            # 日志已删除：循环输出过于频繁

        # 事件2：硬件传感器
        if "hardware" in data and data["hardware"]:
            event = Event(EVENT_HARDWARE_SENSORS, data["hardware"])
            self.event_engine.put(event)
            # 日志已删除：循环输出过于频繁

        # 事件3：分析数据（独立）
        if "analysis" in data and data["analysis"]:
            analysis = data["analysis"]
            if "bottleneck" in analysis and analysis["bottleneck"]:
                event = Event(EVENT_BOTTLENECK_ANALYSIS, analysis["bottleneck"])
                self.event_engine.put(event)
            if "scenario" in analysis and analysis["scenario"]:
                event = Event(EVENT_SCENARIO_ANALYSIS, analysis["scenario"])
                self.event_engine.put(event)

        # 事件4：进程信息
        if "process" in data and data["process"]:
            event = Event(EVENT_PROCESS_MONITORING, data["process"])
            self.event_engine.put(event)

        # 事件5：服务状态
        if "service" in data and data["service"]:
            event = Event(EVENT_SERVICE_MONITORING, data["service"])
            self.event_engine.put(event)

        # 事件6：SMART数据
        if "smart" in data and data["smart"]:
            event = Event(EVENT_SMART_DATA, data["smart"])
            self.event_engine.put(event)

    # ========== 旧API已移除，请使用事件订阅 ==========
    # 旧的 get_monitoring_data()、get_bottleneck_analysis()、get_scenario_analysis()
    # 已完全移除，UI组件应订阅相应的事件类型

    def get_performance_summary(self, scenario: Optional[str] = None) -> Dict[str, Any]:
        """获取性能指标摘要（按场景）.

        Args:
            scenario: 指定场景（可选），None则使用当前检测到的场景

        Returns:
            {
                "current_scenario": "backtest",
                "scenario_name": "策略回测",
                "bottleneck": {...},
                "key_metrics": {
                    "cpu_percent": 85,
                    "memory_percent": 70,
                    ...
                },
                "adaptive_suggestion": {
                    "scale_factor": 0.8,
                    "reason": "CPU负载过高"
                },
                "scenario_details": {
                    "data_download": {...},
                    "realtime_quote": {...},
                    ...
                }
            }
        """
        try:
            data = self._query_monitoring_data_safe()
            system_metrics = data.get("system", {})
            analysis = data.get("analysis", {})
            bottleneck = analysis.get("bottleneck", {})
            scenario_analysis = analysis.get("scenario", {})

            # 使用指定场景或当前检测到的场景
            current_scenario = scenario or scenario_analysis.get("scenario", "unknown")
            scenario_name = scenario_analysis.get("scenario_name", "未知")

            # 提取关键指标
            key_metrics = {
                "cpu_percent": system_metrics.get("cpu_percent", 0),
                "memory_percent": system_metrics.get("memory_percent", 0),
                "disk_percent": system_metrics.get("disk_percent", 0),
            }

            # 获取自适应建议
            adaptive_suggestion = self.get_adaptive_concurrency_suggestion()

            # 构造所有场景的详细信息（使用当前场景数据填充）
            scenario_details = {}

            # 将当前场景的分析结果放入对应的键中
            if current_scenario and scenario_analysis:
                # 场景名称映射
                scenario_key_map = {
                    "data_download": "data_download",
                    "realtime_market": "realtime_quote",
                    "backtest": "strategy_backtest",
                    "live_trading": "realtime_trading",
                    "idle": "system_monitor",
                }

                scenario_key = scenario_key_map.get(current_scenario, current_scenario)
                scenario_details[scenario_key] = scenario_analysis

                # 为其他场景填充默认数据（避免UI出错）
                default_scenario_data = {
                    "current_values": system_metrics,
                    "bottleneck_analysis": {"is_bottleneck": False},
                }

                for key in scenario_key_map.values():
                    if key not in scenario_details:
                        scenario_details[key] = default_scenario_data.copy()

            return {
                "current_scenario": current_scenario,
                "scenario_name": scenario_name,
                "bottleneck": bottleneck,
                "key_metrics": key_metrics,
                "adaptive_suggestion": adaptive_suggestion,
                "scenario_details": scenario_details,
            }
        except Exception as e:
            self.logger.error("获取性能摘要失败：%s", e)
            return {}

    def get_adaptive_concurrency_suggestion(self) -> Dict[str, Any]:
        """获取自适应并发调优建议.

        Returns:
            {
                "scale_factor": 0.8,
                "reason": "CPU负载85%, 建议降低并发",
                "suggested_concurrency": {
                    "async_workers": 64,
                    "thread_workers": 8,
                    "process_workers": 2
                },
                "status": "auto_applied"  # 已自动应用 / not_applied / manual
            }
        """
        try:
            data = self._query_monitoring_data_safe()
            system_metrics = data.get("system", {})

            cpu_percent = system_metrics.get("cpu_percent", 0)
            memory_percent = system_metrics.get("memory_percent", 0)

            # 计算缩放因子
            if cpu_percent > 85 or memory_percent > 85:
                scale_factor = 0.7
                reason = f"CPU {cpu_percent:.1f}% 或内存 {memory_percent:.1f}% 负载过高"
            elif cpu_percent > 70 or memory_percent > 70:
                scale_factor = 0.9
                reason = f"CPU {cpu_percent:.1f}% 或内存 {memory_percent:.1f}% 负载偏高"
            elif cpu_percent < 40 and memory_percent < 50:
                scale_factor = 1.3
                reason = f"CPU {cpu_percent:.1f}% 和内存 {memory_percent:.1f}% 负载较低，可提升并发"
            elif cpu_percent < 60 and memory_percent < 65:
                scale_factor = 1.1
                reason = "系统负载适中，可小幅提升并发"
            else:
                scale_factor = 1.0
                reason = "系统负载正常，保持当前并发"

            # 从配置读取基准并发数
            from backend.core.config import get_settings

            config = get_settings()
            base_async = config.adaptive.baseline_async_concurrency
            base_thread = config.adaptive.baseline_thread_concurrency
            base_process = config.adaptive.baseline_process_concurrency

            suggested_concurrency = {
                "async_workers": int(base_async * scale_factor),
                "thread_workers": int(base_thread * scale_factor),
                "process_workers": max(1, int(base_process * scale_factor)),
            }

            # 从LoadBalancer获取真实自适应状态
            status = "auto_applied"  # 默认值
            try:
                from backend.infrastructure.data_module_vnpy.load_balancer import LoadBalancer
                from backend.infrastructure.data_module_vnpy import ConfigManager
                from backend.core.base import get_event_engine

                event_engine = get_event_engine()
                if event_engine:
                    lb = (
                        LoadBalancer.get_instance(event_engine)
                        if hasattr(LoadBalancer, "get_instance")
                        else LoadBalancer(ConfigManager.get_instance())
                    )
                else:
                    lb = LoadBalancer(ConfigManager.get_instance())
                if hasattr(lb, "get_stats"):
                    lb_stats = lb.get_stats()
                    # 根据LoadBalancer的运行状态确定状态
                    is_running = lb_stats.get("running", False)
                    available_servers = lb_stats.get("available", 0)
                    
                    if is_running and available_servers > 0:
                        status = "auto_applied"
                    elif is_running:
                        status = "applying"
                    else:
                        status = "not_applied"
            except Exception as e:
                self.logger.warning("获取LoadBalancer状态失败，使用默认值: %s", e)

            return {
                "scale_factor": round(scale_factor, 2),
                "reason": reason,
                "suggested_concurrency": suggested_concurrency,
                "status": status,
            }
        except Exception as e:
            self.logger.error("获取自适应建议失败：%s", e)
            return {
                "scale_factor": 1.0,
                "reason": "获取建议失败",
                "suggested_concurrency": {},
                "status": "error",
            }

    def _do_shutdown(self) -> bool:
        """关闭系统管理服务."""
        try:
            self.logger.info("正在关闭系统管理服务...")

            # 停止QTimer
            if self._status_push_timer:
                self._status_push_timer.stop()
                self.logger.info("服务状态推送定时器已停止")

            # 停止监控推送线程
            if hasattr(self, "_monitoring_push_running"):
                self._monitoring_push_running = False
            if hasattr(self, "_monitoring_push_thread") and self._monitoring_push_thread:
                self._monitoring_push_thread.join(timeout=2)
                self.logger.info("监控推送线程已停止")

            # 关闭native_ipc管道
            if self._ipc_loop:
                # 取消所有IPC任务
                for task in self._ipc_tasks:
                    task.cancel()

                # 关闭管道
                if self._query_pipe:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self._close_pipe(self._query_pipe), self._ipc_loop
                        )
                    except Exception:
                        pass
                if self._status_pipe:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self._close_pipe(self._status_pipe), self._ipc_loop
                        )
                    except Exception:
                        pass
                if self._alerts_pipe:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self._close_pipe(self._alerts_pipe), self._ipc_loop
                        )
                    except Exception:
                        pass

                # 停止事件循环
                try:
                    self._ipc_loop.call_soon_threadsafe(self._ipc_loop.stop)
                except Exception:
                    pass

            # 清空监控数据
            self.monitoring_data.clear()

            self.logger.info("✅ 系统管理服务关闭完成")
            return True

        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _get_basic_system_data(self) -> Dict[str, Any]:
        """获取基础系统数据（降级模式，优化CPU使用率）."""
        try:
            import psutil

            # 🔧 优化：减少psutil调用频率和开销
            # 使用更短的CPU采样间隔，减少阻塞时间
            system_data = {
                "cpu_percent": psutil.cpu_percent(interval=0.01),  # 减少采样时间从0.1秒到0.01秒
                "memory_percent": psutil.virtual_memory().percent,
                # 移除磁盘使用率查询（较耗时）
                "boot_time": psutil.boot_time(),
            }

            # 🔧 优化：简化进程信息，减少系统调用
            try:
                current_proc = psutil.Process()
                process_data = {
                    "process_count": len(psutil.pids()),
                    "current_process": {
                        "pid": os.getpid(),
                        "memory_percent": current_proc.memory_percent(),
                        # 移除进程CPU查询（较耗时）
                    }
                }
            except Exception:
                # 如果进程查询失败，使用最小信息
                process_data = {
                    "process_count": 0,
                    "current_process": {"pid": os.getpid()}
                }

            return {
                "system": system_data,
                "process": process_data,
                "timestamp": time.time(),
                "mode": "fallback_optimized",
                "source": "psutil_lightweight"
            }

        except Exception as e:
            self.logger.error("获取基础系统数据失败: %s", e)
            return self._get_minimal_system_data()

    def _get_minimal_system_data(self) -> Dict[str, Any]:
        """获取最小系统数据（完全降级模式）."""
        try:
            import platform

            return {
                "system": {
                    "platform": platform.system(),
                    "platform_version": platform.version(),
                    "python_version": platform.python_version(),
                    "cpu_count": os.cpu_count() or 1,
                },
                "timestamp": time.time(),
                "mode": "minimal",
                "source": "platform_basic",
                "message": "监控功能受限：需要管理员权限以启用完整功能"
            }

        except Exception as e:
            self.logger.error("获取最小系统数据失败: %s", e)
            return {
                "timestamp": time.time(),
                "mode": "error",
                "error": str(e)
            }

    async def _close_pipe(self, pipe):
        """异步关闭管道."""
        try:
            if pipe:
                await pipe.close()
        except Exception:
            pass

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "monitoring_active": (
                self._status_push_timer.isActive() if self._status_push_timer else False
            ),
            "ipc_connected": (
                self._query_pipe is not None
                and self._status_pipe is not None
                and self._alerts_pipe is not None
            ),
            "monitoring_interval": self._monitoring_interval,
            "cache_size": len(self._monitor_data_cache),
            "alert_rule_count": len(self.alert_rules),
            "tool_count": len(self.registered_tools),
        }

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
            self.logger.error("加载默认告警规则失败：%s", str(e))

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

    def _calculate_data_processing_metrics(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
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

    def _calculate_trading_execution_metrics(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                self.logger.debug("获取磁盘I/O速度失败：%s", e)

            # 网络速度
            network_speed = {}
            try:
                network_speed = self.system_monitor.get_network_speed()
            except Exception as e:
                self.logger.debug("获取网络速度失败：%s", e)

            # 磁盘详细信息（各磁盘空间）
            disk_info = {}
            try:
                disk_info = self.system_monitor.get_disk_info()
            except Exception as e:
                self.logger.debug("获取磁盘信息失败：%s", e)

            # 🌡️ 硬件温度监控（CPU、GPU、硬盘）
            temperature_info = {}
            try:
                from backend.infrastructure.system_vnpy.hardware_temp import (
                    get_pure_hardware_monitor,
                )

                temp_monitor = get_pure_hardware_monitor()
                temperature_info = temp_monitor.get_all_temperatures()
                self.logger.debug(
                    "获取温度监控数据成功: %d 个设备",
                    len(temperature_info) if temperature_info else 0,
                )
            except Exception as e:
                self.logger.debug("获取温度监控数据失败: %s", e)

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
                "temperature": temperature_info,  # 🌡️ 硬件温度（CPU、GPU、硬盘）
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

            self.alert_engine.add_rule(rule)  # pylint: disable=assignment-from-no-return

            return {
                "success": True,
                "message": "规则已添加",
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
                rules = [rule for rule in rules if getattr(rule, "group", None) == group]

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

    def delete_all_logs(self) -> Dict[str, Any]:
        """删除所有日志记录.

        Returns:
            Dict: 包含success和deleted_count的字典
        """
        try:
            count = self.log_manager.delete_all_logs()
            return {"success": True, "deleted_count": count}
        except Exception as e:
            self.logger.error("删除所有日志失败: %s", e)
            return {"success": False, "message": str(e)}

    def delete_logs_by_ids(self, log_ids: List[int]) -> Dict[str, Any]:
        """根据ID列表删除日志记录.

        Args:
            log_ids: 日志ID列表

        Returns:
            Dict: 包含success和deleted_count的字典
        """
        try:
            count = self.log_manager.delete_logs_by_ids(log_ids)
            return {"success": True, "deleted_count": count}
        except Exception as e:
            self.logger.error("批量删除日志失败: %s", e)
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
            from backend.infrastructure.data_module_vnpy import ConfigManager

            config_manager = ConfigManager.get_instance()
            db_file = config_manager.get_db_file()

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

            # get_alerts已经返回字典列表，无需转换
            alert_list = alerts

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
                    self.logger.warning("获取数据中心指标失败: %s", e)
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
                    self.logger.warning("获取交易网关指标失败: %s", e)
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
                    self.logger.warning("获取组合投资指标失败: %s", e)
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
                    self.logger.warning("获取策略中心指标失败: %s", e)
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
                from backend.infrastructure.data_module_vnpy import ConfigManager
                from pathlib import Path

                config_manager = ConfigManager.get_instance()

                # 🔧 获取项目根目录
                def get_root() -> Path:
                    """获取项目根目录"""
                    current_file = Path(__file__)
                    # system_manager_service.py 位于 backend/services/
                    # 需要向上2级到达项目根目录
                    return current_file.parent.parent.parent

                root_dir = get_root()

                # 🔧 获取配置值（可能包含相对或绝对路径）
                cache_dir_config = config_manager.get("paths.cache_dir", "data/cache")
                data_dir_config = config_manager.get("paths.data_dir", "data/kline")
                tdx_dir_config = config_manager.get("paths.tdx_dir", "")

                # 🔧 非用户配置项：转换为相对路径显示（相对于项目根目录）
                cache_dir_path = Path(cache_dir_config)
                if cache_dir_path.is_absolute():
                    try:
                        cache_dir = str(cache_dir_path.relative_to(root_dir)).replace("\\", "/")
                    except ValueError:
                        # 无法转换为相对路径，保持绝对路径（向后兼容）
                        cache_dir = cache_dir_config
                else:
                    cache_dir = cache_dir_config.replace("\\", "/")

                data_dir_path = Path(data_dir_config)
                if data_dir_path.is_absolute():
                    try:
                        data_dir = str(data_dir_path.relative_to(root_dir)).replace("\\", "/")
                    except ValueError:
                        # 无法转换为相对路径，保持绝对路径（向后兼容）
                        data_dir = data_dir_config
                else:
                    data_dir = data_dir_config.replace("\\", "/")

                # 🔧 用户配置项：tdx_dir 保持绝对路径
                tdx_dir = tdx_dir_config if tdx_dir_config else ""

                configs["data_center"] = {
                    "cache_dir": cache_dir,  # 相对路径（基于项目根目录）
                    "data_dir": data_dir,  # 相对路径（基于项目根目录）
                    "tdx_dir": tdx_dir,  # 绝对路径（用户配置项）
                    "base_date": config_manager.get("chinastock.base_date"),
                    "max_workers": config_manager.get("chinastock.max_workers"),
                    "timeout": config_manager.get("chinastock.timeout"),
                    "retry_times": config_manager.get("chinastock.retry_times"),
                    "enable_watcher": config_manager.get("chinastock.enable_watcher"),
                    "watcher_interval": config_manager.get("chinastock.watcher_interval"),
                }
            except Exception as e:
                self.logger.warning("获取数据中心配置失败: %s", e)
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
                self.logger.warning("获取VnPy配置失败: %s", e)
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
                self.logger.warning("获取AI配置失败: %s", e)
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
                self.logger.warning("获取数据库配置失败: %s", e)
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
                self.logger.warning("获取网络配置失败: %s", e)
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
                from backend.infrastructure.data_module_vnpy import ConfigManager
                from pathlib import Path

                config_manager = ConfigManager.get_instance()

                # 🔧 获取项目根目录
                def get_root() -> Path:
                    """获取项目根目录"""
                    current_file = Path(__file__)
                    # system_manager_service.py 位于 backend/services/
                    # 需要向上2级到达项目根目录
                    return current_file.parent.parent.parent

                root_dir = get_root()

                # 🔧 处理路径配置：区分用户配置项和非用户配置项
                processed_config = {}

                for key, value in config_data.items():
                    if key == "tdx_dir":
                        # 🔧 用户配置项：通达信路径保存绝对路径
                        if value:
                            tdx_path = Path(str(value))
                            if not tdx_path.is_absolute():
                                # 如果是相对路径，转换为绝对路径（基于当前工作目录）
                                tdx_path = Path.cwd() / tdx_path
                            processed_config["paths.tdx_dir"] = str(tdx_path.resolve())
                        else:
                            processed_config["paths.tdx_dir"] = ""

                    elif key in ["cache_dir", "data_dir"]:
                        # 🔧 非用户配置项：缓存目录和数据目录保存相对路径（基于项目根目录）
                        if value:
                            config_path = Path(str(value))
                            if config_path.is_absolute():
                                # 如果是绝对路径，尝试转换为相对路径
                                try:
                                    rel_path = config_path.relative_to(root_dir)
                                    processed_config[f"paths.{key}"] = str(rel_path).replace(
                                        "\\", "/"
                                    )
                                except ValueError:
                                    # 无法转换为相对路径，保存绝对路径（向后兼容）
                                    processed_config[f"paths.{key}"] = str(config_path.resolve())
                            else:
                                # 已经是相对路径，直接保存（确保使用正斜杠）
                                processed_config[f"paths.{key}"] = str(value).replace("\\", "/")
                        else:
                            # 空值使用默认值
                            default_value = "data/cache" if key == "cache_dir" else "data/kline"
                            processed_config[f"paths.{key}"] = default_value

                    else:
                        # 其他配置项（非路径）使用 chinastock. 前缀
                        processed_config[f"chinastock.{key}"] = value

                # 批量更新配置
                for key, value in processed_config.items():
                    config_manager.set(key, value)

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

            self.logger.info("配置已更新: %s - %s", module, list(config_data.keys()))

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
            from backend.infrastructure.data_module_vnpy import ConfigManager

            config_manager = ConfigManager.get_instance()
            # 配置文件路径（使用绝对路径）
            config_file = config_manager.get_config_file()

            # 加载现有配置（如果存在）
            if config_file and config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            else:
                existing_config = {}

            # 合并配置
            existing_config.update(config_data)

            # 保存配置
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(existing_config, f, indent=4, ensure_ascii=False)

            self.logger.info("配置已保存: %s", list(config_data.keys()))

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
            from backend.infrastructure.data_module_vnpy import ConfigManager

            config_manager = ConfigManager.get_instance()
            config_file = config_manager.get_config_file()

            if not config_file or not config_file.exists():
                return {
                    "success": True,
                    "config": {},
                    "message": "配置文件不存在，返回空配置",
                }

            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.logger.info("配置已加载: %d项", len(config))

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

            self.logger.info("工具已注册: %s", tool_name)

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

            self.logger.info("工具已移除: %s", tool_name)

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
        """读取通达信数据并标准化保存（多市场、多周期、自适应多线程）.

        Args:
            config: 配置信息
                - data_types: 数据类型列表 ['day', '5min', '1min']
                - markets: 市场代码列表 ['sh', 'sz', 'bj']
                - tdx_root: 通达信根目录
                - use_symbol_cache: 是否使用品种缓存（自动获取品种列表）
            progress_callback: 进度回调 callback(current, total, info)

        Returns:
            Dict: 处理结果

        Note:
            线程数将根据以下因素自适应计算：
            - CPU核心数
            - 可用内存
            - 任务总数（小任务<50，中任务<500，大任务>=500）
        """
        try:
            self._log_operation("读取通达信数据")

            # 验证配置
            data_types = config.get("data_types", [])
            markets = config.get("markets", [])
            tdx_root = config.get("tdx_root")
            use_symbol_cache = config.get("use_symbol_cache", True)

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

                # 🔍 DEBUG: 强制打印品种获取统计到控制台
                total_symbols = sum(len(symbols) for symbols in symbols_by_market.values())
                print("\n" + "=" * 60)
                print("📊 品种缓存获取结果:")
                for market_code, symbols in symbols_by_market.items():
                    print(f"  - 市场 {market_code.upper()}: {len(symbols)} 个品种")
                print(f"  - 总计: {total_symbols} 个品种")
                print("=" * 60 + "\n")

                self.logger.info("=" * 60)
                self.logger.info("📊 品种缓存获取结果:")
                for market_code, symbols in symbols_by_market.items():
                    self.logger.info("  - 市场 %s: %d 个品种", market_code.upper(), len(symbols))
                self.logger.info("  - 总计: %d 个品种", total_symbols)
                self.logger.info("=" * 60)

                if not any(symbols_by_market.values()):
                    self.logger.error("❌ 品种缓存为空！请先在数据中心重新加载品种列表")
                    return {
                        "success": False,
                        "message": "品种缓存为空，请先在数据中心重新加载品种列表",
                    }
            else:
                return {
                    "success": False,
                    "message": "手动指定品种功能已移除，请使用品种缓存",
                }

            # 导入TdxDynamicExecutor（替代TdxBinaryReader.process_batch）
            try:
                from backend.infrastructure.data_module_vnpy.data_acquisition import (
                    TdxDynamicExecutor,
                )
            except ImportError as e:
                self.logger.error("导入TdxDynamicExecutor失败: %s", e)
                return {
                    "success": False,
                    "message": f"导入执行器失败: {str(e)}",
                }

            # 创建动态执行器实例
            executor = TdxDynamicExecutor(tdx_dir=tdx_path, logger=self.logger)

            # 计算总任务数
            total_tasks = sum(
                len(symbols_by_market.get(market, [])) * len(data_types) for market in markets
            )

            if total_tasks == 0:
                self.logger.error("❌ 没有找到符合条件的品种，无法开始处理")
                return {
                    "success": False,
                    "message": "没有找到符合条件的品种",
                }

            # ==================== 动态执行器配置 ====================
            # TdxDynamicExecutor内部已集成LoadBalancer，会根据实时资源压力动态调整
            # 这里只需设置初始配置
            import os

            cpu_cores = os.cpu_count() or 4

            # 根据任务规模设置初始进程数和协程数
            if total_tasks < 50:
                initial_processes = min(2, cpu_cores // 2)
                initial_coroutines = 20
                strategy = "小任务模式"
            elif total_tasks < 500:
                initial_processes = min(4, cpu_cores)
                initial_coroutines = 40
                strategy = "中等任务模式"
            else:
                initial_processes = min(8, cpu_cores)
                initial_coroutines = 60
                strategy = "大任务模式"

            # 🔍 DEBUG: 打印详细的任务分组信息
            self.logger.info("=" * 60)
            self.logger.info("📋 批量读取任务详情（TdxDynamicExecutor）:")
            self.logger.info("  - 总任务数: %d", total_tasks)
            self.logger.info("  - 数据类型: %s", ", ".join(data_types))
            self.logger.info(f"  - 市场: {', '.join([m.upper() for m in markets])}")
            self.logger.info("  - 系统资源:")
            self.logger.info(f"    • CPU核心数: {cpu_cores}")
            self.logger.info("  - 动态执行器配置:")
            self.logger.info(f"    • 初始进程数: {initial_processes}")
            self.logger.info(f"    • 初始协程数/进程: {initial_coroutines}")
            self.logger.info(f"    • 策略: {strategy}")
            self.logger.info("    • 动态调整: 每0.3秒根据资源压力自动调整并发")
            self.logger.info("  - 任务分组:")
            for market in markets:
                symbols = symbols_by_market.get(market, [])
                if symbols:
                    tasks_per_market = len(symbols) * len(data_types)
                    self.logger.info(
                        f"    • {market.upper()}: {len(symbols)} 个品种 × {len(data_types)} 种数据类型 = {tasks_per_market} 个任务"
                    )
            self.logger.info("=" * 60)
            self.logger.info("🚀 开始批量读取（使用动态负载均衡）...")

            # 重置停止标志
            self._tdx_reader_stop_flag = False

            # 批量处理（多市场、多周期）- 使用TdxDynamicExecutor
            all_results = {}
            completed = 0

            import asyncio

            async def run_batch_processing():
                """异步批量处理函数"""
                nonlocal completed

                for market in markets:
                    # 检查停止标志
                    if self._tdx_reader_stop_flag:
                        self.logger.info("检测到停止标志，中断批量读取")
                        break

                    symbols = symbols_by_market.get(market, [])
                    if not symbols:
                        self.logger.warning(f"⚠️  市场 {market.upper()} 没有品种，跳过")
                        continue

                    for data_type in data_types:
                        # 检查停止标志
                        if self._tdx_reader_stop_flag:
                            self.logger.info("检测到停止标志，中断批量读取")
                            break

                        # 🔍 DEBUG: 打印开始处理的信息
                        self.logger.info("")
                        self.logger.info("─" * 60)
                        self.logger.info(
                            f"📂 开始处理: 市场={market.upper()}, 数据类型={data_type}, 品种数={len(symbols)}"
                        )
                        self.logger.info("─" * 60)

                        # 使用TdxDynamicExecutor批量处理
                        try:
                            results = await executor.execute_batch(
                                symbols=symbols,
                                data_type=data_type,
                                market=market,
                                initial_processes=initial_processes,
                                initial_coroutines=initial_coroutines,
                            )

                            # 处理结果和进度
                            for symbol, success, error_msg, duration in results:
                                completed += 1
                                key = f"{market}_{data_type}_{symbol}"
                                all_results[key] = success

                                # 进度回调
                                if progress_callback:
                                    info = f"{market.upper()} {data_type} {symbol}"
                                    progress_callback(completed, total_tasks, info, success)

                                # 检查停止标志
                                if self._tdx_reader_stop_flag:
                                    self.logger.info("检测到停止标志，中断批量读取")
                                    return

                        except Exception as e:
                            self.logger.error(
                                f"处理 {market.upper()} {data_type} 失败: {e}", exc_info=True
                            )
                            # 标记所有品种为失败
                            for symbol in symbols:
                                key = f"{market}_{data_type}_{symbol}"
                                all_results[key] = False
                                completed += 1

            # 在同步方法中运行异步函数
            try:
                asyncio.run(run_batch_processing())
            except Exception as e:
                self.logger.error(f"批量处理执行失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"批量处理执行失败: {str(e)}",
                }

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

            # 🔍 DEBUG: 打印获取到的原始品种数量
            self.logger.info(f"🔍 从品种缓存获取到 {len(symbols)} 个品种")

            if not symbols:
                self.logger.warning("⚠️  品种缓存中没有任何品种数据")
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
                # 优先使用 "symbol" 字段，如果没有则使用 "code" 字段
                symbol_code = symbol_info.get("symbol") or symbol_info.get("code", "")

                # 跳过空的 symbol_code
                if not symbol_code:
                    self.logger.warning(f"跳过无效品种: {symbol_info}")
                    continue

                # 确保 symbol_code 是字符串
                if not isinstance(symbol_code, str):
                    self.logger.warning(
                        f"品种代码不是字符串类型: {symbol_code}, 类型: {type(symbol_code)}"
                    )
                    continue

                # 匹配市场
                for market_code, exchange_name in market_mapping.items():
                    if market_code in markets and exchange == exchange_name:
                        symbols_by_market[market_code].append(symbol_code)
                        break

            # 🔍 DEBUG: 打印详细的市场分类统计
            self.logger.info("─" * 60)
            self.logger.info("🏢 市场品种分类统计:")
            for market in markets:
                market_symbols = symbols_by_market.get(market, [])
                count = len(market_symbols)
                self.logger.info(f"  • 市场 {market.upper()}: {count} 个品种")

                # 输出前10个品种示例（如果有的话）
                if count > 0:
                    sample_symbols = market_symbols[:10]
                    self.logger.info(f"    示例: {', '.join(sample_symbols)}")
                    if count > 10:
                        self.logger.info(f"    ... 还有 {count - 10} 个品种")
            self.logger.info("─" * 60)

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
                from backend.infrastructure.data_module_vnpy import ConfigManager

                config_manager = ConfigManager.get_instance()
                tdx_dir = config_manager.get_tdx_dir()
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

    def get_data_source_connectivity(self) -> Dict[str, Any]:
        """获取数据源连通性状态.

        Returns:
            {
                "tdx_servers": {
                    "total": 132,
                    "available": 54,
                    "connectivity_rate": 40.9
                },
                "trading_gateways": {
                    "ctp": "disconnected",
                    "ib": "disconnected"
                }
            }
        """
        result = {}

        # TDX服务器连通性
        try:
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                ServerPoolManager,
            )

            pool_manager = ServerPoolManager()
            stats = pool_manager.get_stats()

            result["tdx_servers"] = {
                "total": stats.get("total", 0),
                "available": stats.get("available", 0),
                "connectivity_rate": round(
                    (stats.get("available", 0) / max(stats.get("total", 1), 1)) * 100, 1
                ),
            }
        except Exception as e:
            self.logger.debug("获取TDX服务器状态失败: %s", e)
            result["tdx_servers"] = {"total": 0, "available": 0, "connectivity_rate": 0}

        # 交易网关连通性（占位，待交易模块实现）
        result["trading_gateways"] = {"ctp": "not_configured", "ib": "not_configured"}

        return result

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
            # 验证参数
            interval = max(1, min(10, interval))
            self._monitoring_interval = interval

            # 设置ServiceHealthChecker的推送频率
            self.service_health_checker.set_monitoring_interval(interval)

            # 更新QTimer的间隔
            if self._status_push_timer:
                self._status_push_timer.setInterval(interval * 1000)

            self.logger.info("监控推送频率已更新为 %d 秒", interval)

            return {
                "success": True,
                "message": f"监控推送频率已设置为 {interval} 秒",
                "interval": interval,
            }

        except Exception as e:
            return {"success": False, "message": str(e)}

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
            from backend.infrastructure.data_module_vnpy.data_quality import (
                StorageManager,
            )

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

    def get_system_summary(self) -> Dict[str, Any]:
        """提供给UI的简要系统摘要（便于最小改动展示新指标）。

        Returns:
            Dict[str, Any]:
                {
                  "cpu_percent": float,
                  "memory_percent": float,
                  "storage_avg_latency_ms": float|None,
                  "network_packet_loss_in": float|None,
                  "network_packet_loss_out": float|None,
                }
        """
        try:
            data = self._query_monitoring_data_safe() or {}
            sysd = data.get("system", {}) or {}

            cpu_percent = float(sysd.get("cpu_percent", 0.0))
            memory_percent = float(sysd.get("memory_percent", 0.0))

            storage = sysd.get("storage_subsystem", {}) or {}
            disks = storage.get("disks", {}) or {}
            latencies = []
            for info in disks.values():
                lat = info.get("average_io_latency_ms")
                if isinstance(lat, (int, float)):
                    latencies.append(float(lat))
            storage_avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None

            net = sysd.get("network_subsystem", {}) or {}
            loss_in = net.get("packet_loss_rate_in")
            loss_out = net.get("packet_loss_rate_out")
            loss_in = float(loss_in) if isinstance(loss_in, (int, float)) else None
            loss_out = float(loss_out) if isinstance(loss_out, (int, float)) else None

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_percent": round(memory_percent, 2),
                "storage_avg_latency_ms": storage_avg_latency,
                "network_packet_loss_in": loss_in,
                "network_packet_loss_out": loss_out,
            }
        except Exception as e:
            self.logger.error("获取系统摘要失败: %s", e)
            return {}
