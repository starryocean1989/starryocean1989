# -*- coding: utf-8 -*-
"""
统一日志和告警系统 - 合并版本.

整合了以下模块的功能：
- logging_system.py: 日志管理系统
- alert_system.py: 告警管理系统
- logging_mixin.py: 日志混入类
- default_alert_rules.py: 默认告警规则
- utils.py: 日志告警相关工具

提供完整的日志收集、存储、查询和告警功能，支持实时推送和历史查询。
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# =============================================================================
# Part 1: 事件类型定义
# =============================================================================

# 日志和告警系统事件
EVENT_LOG_RECORD = "eLogRecord"  # 日志记录事件
EVENT_ALERT_CREATED = "eAlertCreated"  # 告警创建事件
EVENT_ALERT_UPDATED = "eAlertUpdated"  # 告警更新事件


# =============================================================================
# Part 2: 枚举类
# =============================================================================

from enum import Enum


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
# Part 3: LoggerMixin 基础类
# =============================================================================


class LoggerMixin:
    """日志记录器混入类.
    
    为类提供标准化的日志记录功能，包括：
    - 自动创建命名日志记录器
    - 标准化的日志输出方法
    - 上下文信息传递
    - 性能日志记录
    
    使用方法:
        class MyService(LoggerMixin):
            def __init__(self):
                super().__init__()
                self.logger.info("服务已创建")
    """
    
    def __init__(self):
        """初始化日志记录器混入."""
        # 创建以类名命名的日志记录器
        self._logger = logging.getLogger(self.__class__.__name__)
    
    @property
    def logger(self) -> logging.Logger:
        """获取日志记录器.
        
        Returns:
            日志记录器实例
        """
        return self._logger
    
    def log_with_context(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ) -> None:
        """记录带上下文信息的日志.
        
        Args:
            level: 日志级别（logging.DEBUG, INFO, WARNING, ERROR, CRITICAL）
            message: 日志消息
            extra: 额外的上下文信息
            exc_info: 是否包含异常信息
        """
        log_extra = extra or {}
        self._logger.log(level, message, extra=log_extra, exc_info=exc_info)
    
    def log_performance(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录性能日志.
        
        Args:
            operation: 操作名称
            duration_ms: 操作耗时（毫秒）
            success: 操作是否成功
            extra: 额外的上下文信息
        """
        log_extra = extra or {}
        log_extra.update({
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
        })
        
        if success:
            message = f"[性能] {operation} 完成，耗时: {duration_ms:.2f}ms"
            self._logger.debug(message, extra=log_extra)
        else:
            message = f"[性能] {operation} 失败，耗时: {duration_ms:.2f}ms"
            self._logger.warning(message, extra=log_extra)
    
    def log_operation_start(self, operation: str, **kwargs) -> None:
        """记录操作开始日志.
        
        Args:
            operation: 操作名称
            **kwargs: 操作参数
        """
        params_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        message = f"[开始] {operation}"
        if params_str:
            message += f" ({params_str})"
        self._logger.info(message)
    
    def log_operation_success(self, operation: str, **kwargs) -> None:
        """记录操作成功日志.
        
        Args:
            operation: 操作名称
            **kwargs: 结果信息
        """
        result_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        message = f"[成功] {operation}"
        if result_str:
            message += f" ({result_str})"
        self._logger.info(message)
    
    def log_operation_failure(
        self,
        operation: str,
        error: Exception,
        **kwargs
    ) -> None:
        """记录操作失败日志.
        
        Args:
            operation: 操作名称
            error: 错误异常
            **kwargs: 错误上下文
        """
        context_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        message = f"[失败] {operation}: {str(error)}"
        if context_str:
            message += f" ({context_str})"
        self._logger.error(message, exc_info=True)


# =============================================================================
# Part 4: 日志系统
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
            if record.name.startswith('backend.core.logging_alert'):
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
            if not record.name.startswith('backend.core.logging_alert'):
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


class LogDatabase:
    """日志数据库管理器.

    提供日志记录的SQLite存储和查询功能。
    """

    def __init__(self, db_path: str = "data/logs.db"):
        """初始化日志数据库.

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._needs_index_creation = False
        self._db_error = False

        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库（快速模式）
        self._init_database()
        
    def _create_remaining_indexes(self) -> None:
        """创建剩余索引（延迟执行）."""
        if not self._needs_index_creation or self._db_error:
            return
            
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_module ON logs(module)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_logger_name ON logs(logger_name)")
                conn.commit()
            
            self._needs_index_creation = False
            print("[后台] 日志数据库索引创建完成")
        except Exception as e:
            print(f"[后台] 创建日志索引失败: {e}")

    def _init_database(self) -> None:
        """初始化数据库表结构（延迟初始化模式）."""
        db_path = Path(self.db_path)
        db_exists = db_path.exists()
        
        if db_exists:
            print(f"[启动] 日志数据库已存在: {self.db_path}")
            return
        
        print(f"[启动] 初始化日志数据库: {self.db_path}")
        db_init_start = time.time()

        try:
            # 快速创建数据库文件和基础表结构
            with sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        logger_name TEXT,
                        module TEXT,
                        function_name TEXT,
                        line_number INTEGER,
                        message TEXT NOT NULL,
                        exception TEXT,
                        thread INTEGER,
                        thread_name TEXT,
                        process INTEGER,
                        filename TEXT,
                        created_at REAL NOT NULL
                    )
                """)
                
                # 创建关键索引（其他索引延迟创建）
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
                
                conn.commit()

            total_time = time.time() - db_init_start
            print(f"[启动] ✅ 日志数据库初始化完成，耗时: {total_time:.3f}s")
            
            # 标记需要延迟创建其他索引
            self._needs_index_creation = True

        except Exception as e:
            total_time = time.time() - db_init_start
            print(f"[启动] ⚠️ 日志数据库初始化失败，耗时: {total_time:.3f}s，错误: {e}")
            self._db_error = True

    def add_log_record(self, log_data: Dict[str, Any]) -> None:
        """添加日志记录（批量插入优化）.

        Args:
            log_data: 日志数据字典
        """
        if self._db_error:
            return
            
        # 首次写入时创建剩余索引
        if self._needs_index_creation:
            threading.Thread(target=self._create_remaining_indexes, daemon=True).start()
            
        try:
            with self._lock:
                with sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False) as conn:
                    conn.execute("""
                        INSERT OR IGNORE INTO logs
                        (timestamp, level, logger_name, module, function_name, line_number,
                         message, exception, thread, thread_name, process, filename, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        log_data["timestamp"],
                        log_data["level"],
                        log_data["logger_name"],
                        log_data["module"],
                        log_data["function"],
                        log_data["line"],
                        log_data["message"],
                        log_data["exception"],
                        log_data["thread"],
                        log_data["thread_name"],
                        log_data["process"],
                        log_data["filename"],
                        time.time(),
                    ))
                    conn.commit()

        except Exception as e:
            if not self._db_error:
                print(f"[日志] 数据库插入失败: {e}")
                self._db_error = True

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
        """查询日志记录.

        Args:
            level: 日志级别筛选
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            module: 模块名筛选
            logger_name: 日志记录器名筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            日志记录列表
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row

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

                if logger_name:
                    conditions.append("logger_name LIKE ?")
                    params.append(f"%{logger_name}%")

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                # 执行查询
                cursor = conn.execute(f"""
                    SELECT * FROM logs
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])

                # 转换结果
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "level": row["level"],
                        "logger_name": row["logger_name"],
                        "module": row["module"],
                        "function_name": row["function_name"],
                        "line_number": row["line_number"],
                        "message": row["message"],
                        "exception": row["exception"],
                        "thread": row["thread"],
                        "thread_name": row["thread_name"],
                        "process": row["process"],
                        "filename": row["filename"],
                    })

                return results

        except Exception as e:
            print(f"日志查询失败: {e}")
            return []

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息.

        Returns:
            统计信息字典
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                
                # 按级别统计
                cursor = conn.execute("""
                    SELECT level, COUNT(*) as count
                    FROM logs
                    WHERE timestamp >= ?
                    GROUP BY level
                """, ((datetime.now() - timedelta(days=7)).isoformat(),))

                level_stats = {row["level"]: row["count"] for row in cursor.fetchall()}

                # 按模块统计
                cursor = conn.execute("""
                    SELECT module, COUNT(*) as count
                    FROM logs
                    WHERE timestamp >= ? AND module IS NOT NULL
                    GROUP BY module
                    ORDER BY count DESC
                    LIMIT 10
                """, ((datetime.now() - timedelta(days=7)).isoformat(),))

                module_stats = [
                    {"module": row["module"], "count": row["count"]}
                    for row in cursor.fetchall()
                ]

                # 总记录数
                cursor = conn.execute("SELECT COUNT(*) as total FROM logs")
                row = cursor.fetchone()
                total_count = row[0] if isinstance(row, (tuple, list)) else row["total"]

                return {
                    "total_count": total_count,
                    "level_stats": level_stats,
                    "module_stats": module_stats,
                    "recent_days": 7,
                }

        except Exception as e:
            print(f"获取日志统计失败: {e}")
            return {}

    def cleanup_old_logs(self, retention_days: int = 30) -> int:
        """清理旧日志记录.

        Args:
            retention_days: 保留天数

        Returns:
            删除的记录数量
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=retention_days)).isoformat()

            with self._lock:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        "DELETE FROM logs WHERE timestamp < ?",
                        (cutoff_time,)
                    )
                    deleted_count = cursor.rowcount
                    conn.commit()

                    return deleted_count

        except Exception as e:
            print(f"清理旧日志失败: {e}")
            return 0


class LogManager:
    """日志系统管理器.

    统一管理日志收集、存储和查询功能。
    """

    def __init__(
        self,
        db_path: str = "data/logs.db",
        event_engine=None,
        retention_days: int = 30,
    ):
        """初始化日志管理器.

        Args:
            db_path: 日志数据库路径
            event_engine: VnPy事件引擎实例
            retention_days: 日志保留天数
        """
        self.db_path = db_path
        self.event_engine = event_engine
        self.retention_days = retention_days

        # 日志记录器
        self.logger = logging.getLogger(__name__)

        # 初始化数据库
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
# Part 5: 告警系统
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


class AlertDatabase:
    """告警数据库管理器."""

    def __init__(self, db_path: str = "data/alerts.db"):
        """初始化告警数据库."""
        self.db_path = db_path
        self._lock = threading.Lock()
        self._needs_index_creation = False
        self._db_error = False

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        
    def _create_remaining_indexes(self) -> None:
        """创建剩余索引（延迟执行）."""
        if not self._needs_index_creation or self._db_error:
            return
            
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id)")
                conn.commit()
            
            self._needs_index_creation = False
            print("[后台] 告警数据库索引创建完成")
        except Exception as e:
            print(f"[后台] 创建告警索引失败: {e}")

    def _init_database(self) -> None:
        """初始化数据库表结构."""
        db_path = Path(self.db_path)
        db_exists = db_path.exists()
        
        if db_exists:
            print(f"[启动] 告警数据库已存在: {self.db_path}")
            return
            
        print(f"[启动] 初始化告警数据库: {self.db_path}")
        db_init_start = time.time()

        try:
            with sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alert_id TEXT UNIQUE NOT NULL,
                        rule_id TEXT NOT NULL,
                        rule_name TEXT,
                        severity TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message TEXT NOT NULL,
                        context TEXT,
                        source_type TEXT DEFAULT 'log',
                        source_data TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        acknowledged_at REAL,
                        resolved_at REAL,
                        notes TEXT
                    )
                """)
                
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at)")
                
                conn.commit()

            total_time = time.time() - db_init_start
            print(f"[启动] ✅ 告警数据库初始化完成，耗时: {total_time:.3f}s")
            
            self._needs_index_creation = True

        except Exception as e:
            total_time = time.time() - db_init_start
            print(f"[启动] ⚠️ 告警数据库初始化失败，耗时: {total_time:.3f}s，错误: {e}")
            self._db_error = True

    def save_alert(self, alert: Alert) -> None:
        """保存告警记录."""
        if self._db_error:
            return
            
        if self._needs_index_creation:
            threading.Thread(target=self._create_remaining_indexes, daemon=True).start()
            
        try:
            with self._lock:
                with sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO alerts
                        (alert_id, rule_id, rule_name, severity, status, message, context,
                         source_type, source_data, created_at, updated_at, acknowledged_at,
                         resolved_at, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        alert.alert_id,
                        alert.rule.rule_id,
                        alert.rule.name,
                        alert.severity.value,
                        alert.status.value,
                        alert.message,
                        json.dumps(alert.context) if alert.context else None,
                        getattr(alert, 'source_type', 'log'),
                        getattr(alert, 'source_data', None),
                        alert.created_at.timestamp(),
                        alert.updated_at.timestamp(),
                        alert.acknowledged_at.timestamp() if alert.acknowledged_at else None,
                        alert.resolved_at.timestamp() if alert.resolved_at else None,
                        json.dumps(alert.notes) if alert.notes else None,
                    ))
                    conn.commit()

        except Exception as e:
            if not self._db_error:
                print(f"[告警] 数据库保存失败: {e}")
                self._db_error = True

    def get_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询告警记录."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

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

                cursor = conn.execute(f"""
                    SELECT * FROM alerts
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])

                results = []
                for row in cursor.fetchall():
                    results.append(dict(row))

                return results

        except Exception as e:
            print(f"查询告警失败: {e}")
            return []

    def update_alert_status(self, alert_id: str, status: AlertStatus, note: str = "") -> bool:
        """更新告警状态."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    now = datetime.now().timestamp()

                    if status == AlertStatus.ACKNOWLEDGED:
                        conn.execute("""
                            UPDATE alerts
                            SET status = ?, acknowledged_at = ?, updated_at = ?
                            WHERE alert_id = ?
                        """, (status.value, now, now, alert_id))
                    elif status == AlertStatus.RESOLVED:
                        conn.execute("""
                            UPDATE alerts
                            SET status = ?, resolved_at = ?, updated_at = ?
                            WHERE alert_id = ?
                        """, (status.value, now, now, alert_id))
                    else:
                        conn.execute("""
                            UPDATE alerts
                            SET status = ?, updated_at = ?
                            WHERE alert_id = ?
                        """, (status.value, now, alert_id))

                    if note:
                        conn.execute("""
                            UPDATE alerts
                            SET notes = COALESCE(notes, '[]') || ?
                            WHERE alert_id = ?
                        """, (f', "[{status.value}] {note}"', alert_id))

                    conn.commit()
                    return True

        except Exception as e:
            print(f"更新告警状态失败: {e}")
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

            # 使用合适的事件类型
            event_type = "alert_updated"  # 或者使用现有的常量
            event = Event(event_type, event_data)
            self.event_engine.put(event)

        except Exception:
            pass


# =============================================================================
# Part 6: 默认告警规则
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
# Part 7: 初始化和关闭函数
# =============================================================================

# 全局实例
_log_manager: Optional[LogManager] = None
_log_manager_lock = threading.Lock()
_alert_database: Optional[AlertDatabase] = None
_alert_database_lock = threading.Lock()


def get_log_manager() -> LogManager:
    """获取全局日志管理器实例."""
    global _log_manager
    if _log_manager is None:
        with _log_manager_lock:
            if _log_manager is None:
                _log_manager = LogManager()
    return _log_manager


def get_alert_database() -> AlertDatabase:
    """获取全局告警数据库实例."""
    global _alert_database
    if _alert_database is None:
        with _alert_database_lock:
            if _alert_database is None:
                _alert_database = AlertDatabase()
    return _alert_database


def initialize_logging_system(event_engine=None, config: Optional[Dict[str, Any]] = None) -> bool:
    """初始化日志系统."""
    try:
        start_time = time.time()
        print(f"[启动] 日志系统初始化开始...")

        if config is None:
            config = {"db_path": "data/logs.db", "retention_days": 30}

        global _log_manager
        with _log_manager_lock:
            _log_manager = LogManager(
                db_path=config.get("db_path", "data/logs.db"),
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


def shutdown_logging_system() -> None:
    """关闭日志系统."""
    global _log_manager
    if _log_manager:
        _log_manager.shutdown()
        _log_manager = None
        logging.info("日志系统已关闭")


def shutdown_alert_system() -> None:
    """关闭扩展告警系统."""
    global _alert_database
    if _alert_database:
        _alert_database = None
        print("扩展告警系统已关闭")


# 导出全局告警引擎实例（向后兼容utils.py）
alert_engine = AlertEngine()
