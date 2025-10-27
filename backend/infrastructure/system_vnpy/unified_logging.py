# -*- coding: utf-8 -*-
"""
统一日志系统 - 拦截所有日志输出并按规则分发.

架构：
    现有logger → LoggingHub (拦截) → 分级路由 → 多渠道输出
                                        ├─ Terminal (DEBUG)
                                        ├─ Log文件 (所有级别)
                                        ├─ 数据库 (WARNING+)
                                        ├─ EventEngine (进度/告警/通知)
                                        └─ UI (状态栏/弹窗)

作者：系统重构团队
日期：2025-10-27
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from vnpy.event import Event, EventEngine

# 导入路由引擎（四层路由架构）
from .routing_engine import RoutingRuleEngine


# =============================================================================
# Part 1: 数据结构定义
# =============================================================================


class LogType(Enum):
    """日志类型枚举."""

    SYSTEM = "system"  # 系统运行日志
    PROGRESS = "progress"  # 进度更新（高频）
    NOTIFICATION = "notification"  # 任务完成通知
    ALERT = "alert"  # 告警
    USER_FEEDBACK = "user_feedback"  # 用户交互反馈
    DEBUG = "debug"  # 调试信息


@dataclass
class UnifiedLogRecord:
    """统一日志记录."""

    type: LogType
    level: int  # logging.DEBUG/INFO/WARNING/ERROR/CRITICAL
    module: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    # 原始logging.LogRecord的元数据
    logger_name: str = ""
    function: str = ""
    line: int = 0
    filename: str = ""
    thread: int = 0
    thread_name: str = ""
    exception: str = ""


# =============================================================================
# Part 2: 事件类型定义
# =============================================================================

# 沿用现有命名风格（EVENT_前缀）
EVENT_LOG_SYSTEM = "eLogSystem"
EVENT_LOG_PROGRESS = "eLogProgress"
EVENT_LOG_NOTIFICATION = "eLogNotification"
EVENT_LOG_ALERT = "eLogAlert"
EVENT_UI_STATUSBAR = "eUIStatusBar"
EVENT_UI_DIALOG = "eUIDialog"


# =============================================================================
# Part 3: ProgressThrottler节流器
# =============================================================================


class ProgressThrottler:
    """进度日志节流器.

    功能：
    - 500ms聚合窗口
    - 只保留最新进度值
    - get_if_ready()判断是否可发送
    """

    def __init__(self, interval_ms: int = 500):
        """初始化节流器.

        Args:
            interval_ms: 节流间隔（毫秒）
        """
        self.interval_ms = interval_ms
        self._last_emit_time = 0
        self._pending_record: Optional[UnifiedLogRecord] = None
        self._pending_count = 0  # 聚合的日志数量

    def add(self, record: UnifiedLogRecord):
        """添加进度记录（只保留最新的）.

        Args:
            record: 统一日志记录
        """
        self._pending_record = record
        self._pending_count += 1

    def get_if_ready(self) -> Optional[UnifiedLogRecord]:
        """如果距离上次发送超过interval_ms，返回待发送记录.

        Returns:
            待发送的日志记录，如果未到时间则返回None
        """
        current_time = time.time() * 1000  # 转为毫秒

        if current_time - self._last_emit_time >= self.interval_ms:
            if self._pending_record:
                result = self._pending_record

                # 在details中添加聚合信息
                if result.details is None:
                    result.details = {}
                result.details["_throttled_count"] = self._pending_count

                # 重置
                self._pending_record = None
                self._pending_count = 0
                self._last_emit_time = current_time

                return result

        return None

    def has_pending(self) -> bool:
        """是否有待发送的记录.

        Returns:
            是否有待发送记录
        """
        return self._pending_record is not None


# =============================================================================
# Part 4: LoggingHub核心类
# =============================================================================


class LoggingHub(logging.Handler):
    """统一日志中心.

    作为logging.Handler拦截所有日志输出，根据规则分发到不同目标。

    架构特点：
    1. 继承logging.Handler，无缝集成现有日志系统
    2. 分级路由：根据日志类型和级别决定输出目标
    3. 节流机制：高频进度日志自动聚合
    4. 事件驱动：通过EventEngine推送到UI
    """

    def __init__(self):
        """初始化LoggingHub."""
        super().__init__()
        self.setLevel(logging.DEBUG)  # 拦截所有级别

        # 外部依赖（后续注入）
        self.event_engine: Optional[EventEngine] = None
        self.db_manager: Optional[Any] = None

        # 🆕 托管的Handler（控制台和文件）
        self._console_handler: Optional[logging.StreamHandler] = None
        self._file_handler: Optional[logging.FileHandler] = None
        self._console_enabled_types: set = {
            LogType.SYSTEM,
            LogType.NOTIFICATION,
            LogType.ALERT,
        }  # 可配置：哪些类型输出到控制台

        # 节流器
        self._throttler = ProgressThrottler(interval_ms=500)

        # 🆕 创建内部logger（不经过LoggingHub，防止循环）
        self._internal_logger = logging.getLogger("_internal.logging_hub")
        self._internal_logger.propagate = False  # 防止向上传播
        if not self._internal_logger.handlers:
            # 添加简单的StreamHandler用于内部错误
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[LoggingHub] %(levelname)s: %(message)s"))
            self._internal_logger.addHandler(handler)
            self._internal_logger.addHandler(logging.NullHandler())

        # 🔄 路由规则引擎（四层路由架构）
        try:
            self._routing_engine = RoutingRuleEngine()
            # 验证配置
            if not self._routing_engine.validate_config():
                self._internal_logger.warning("路由规则配置验证失败，回退到默认规则")
        except FileNotFoundError as e:
            self._internal_logger.error("路由配置文件不存在: %s，回退到硬编码规则", e)
            self._routing_engine = None
        except Exception as e:
            self._internal_logger.exception("路由引擎初始化失败，回退到硬编码规则: %s", e)
            self._routing_engine = None

        # 兼容性：保留硬编码路由规则作为备选
        self._routing_rules = self._init_routing_rules()

        # 统计信息
        self._total_logs = 0
        self._throttled_logs = 0
        self._db_writes = 0
        self._console_writes = 0  # 🆕
        self._file_writes = 0  # 🆕

        # 递归检测（避免日志循环）
        self._in_emit = False

        # 数据库批量写入缓存
        self._db_batch_cache: List[Dict] = []
        self._db_batch_size = 10
        self._db_last_flush = time.time()
        self._db_flush_interval = 5.0  # 5秒强制刷新

        logging.getLogger(__name__).debug("LoggingHub initialized")

    def set_event_engine(self, event_engine: EventEngine):
        """注入EventEngine.

        Args:
            event_engine: VNPY事件引擎
        """
        self.event_engine = event_engine
        logging.getLogger(__name__).info("✅ EventEngine已注入LoggingHub")

    def set_db_manager(self, db_manager: Any):
        """注入数据库管理器.

        Args:
            db_manager: 数据库管理器实例
        """
        self.db_manager = db_manager
        logging.getLogger(__name__).info("✅ DatabaseManager已注入LoggingHub")

    def set_console_handler(self, handler: logging.StreamHandler):
        """注入控制台Handler.

        Args:
            handler: StreamHandler实例（由LoggingHub托管）
        """
        self._console_handler = handler
        logging.getLogger(__name__).info("✅ ConsoleHandler已注入LoggingHub托管")

    def set_file_handler(self, handler: logging.FileHandler):
        """注入文件Handler.

        Args:
            handler: FileHandler实例（由LoggingHub托管）
        """
        self._file_handler = handler
        logging.getLogger(__name__).info("✅ FileHandler已注入LoggingHub托管")

    def configure_console_output(self, enabled_types: set):
        """配置控制台输出的日志类型.

        Args:
            enabled_types: 允许输出到控制台的日志类型集合
        """
        self._console_enabled_types = enabled_types
        logging.getLogger(__name__).info("✅ 控制台输出配置: %s", [t.value for t in enabled_types])

    def emit(self, record: logging.LogRecord) -> None:
        """拦截日志输出（logging.Handler接口）.

        Args:
            record: Python标准日志记录
        """
        try:
            # 递归检测
            if self._in_emit:
                return

            # 检查是否已被其他handler处理过（避免重复）
            if hasattr(record, "_unified_hub_processed"):
                return

            # 标记正在处理
            self._in_emit = True
            setattr(record, "_unified_hub_processed", True)

            # 过滤：跳过自身和某些系统模块
            if self._should_skip(record):
                return

            # 统计
            self._total_logs += 1

            # 1. 转换为UnifiedLogRecord
            unified_record = self._convert_to_unified(record)

            # 2. 获取路由规则
            targets = self._get_targets(unified_record)

            # 3. 分发到各目标
            self._dispatch(targets, unified_record)

            # 4. 检查节流器（定期发送待处理的进度日志）
            self._check_throttler()

            # 5. 定期刷新数据库批量缓存
            self._maybe_flush_db_batch()

        except RecursionError:
            # 防止循环调用，静默处理
            pass
        except Exception as e:
            # 使用内部logger记录错误（不经过LoggingHub）
            try:
                self._internal_logger.error("日志处理失败: %s", e, exc_info=True)
            except Exception:
                pass  # 如果内部logger也失败，完全静默
            # 不向上抛出异常，避免日志系统崩溃
        finally:
            self._in_emit = False

    def _should_skip(self, record: logging.LogRecord) -> bool:
        """判断是否应跳过该日志.

        Args:
            record: 日志记录

        Returns:
            是否应跳过
        """
        # 跳过自身模块
        if record.name.startswith("backend.infrastructure.system_vnpy.unified_logging"):
            return True

        # 跳过LogManager模块（避免递归）
        if "system_manager_service" in record.name and "log_manager" in record.name.lower():
            return True

        # 跳过第三方库的DEBUG日志（减少噪音）
        if record.levelno == logging.DEBUG:
            # 只处理项目内的DEBUG日志
            if not record.name.startswith("backend") and not record.name.startswith("ui"):
                return True

        return False

    def _convert_to_unified(self, record: logging.LogRecord) -> UnifiedLogRecord:
        """将logging.LogRecord转换为UnifiedLogRecord.

        Args:
            record: Python标准日志记录

        Returns:
            统一日志记录
        """
        # 提取异常信息
        exception_text = ""
        if record.exc_info:
            import traceback

            exception_text = "".join(traceback.format_exception(*record.exc_info))

        # 判断日志类型
        log_type = self._classify_log_type(record)

        # 提取详情（从extra字段）
        details = {}
        if hasattr(record, "__dict__"):
            # 提取自定义字段
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                ]:
                    details[key] = value

        return UnifiedLogRecord(
            type=log_type,
            level=record.levelno,
            module=record.module,
            message=record.getMessage(),
            details=details if details else None,
            timestamp=datetime.fromtimestamp(record.created),
            logger_name=record.name,
            function=record.funcName,
            line=record.lineno,
            filename=record.filename,
            thread=record.thread if record.thread is not None else 0,
            thread_name=(
                record.threadName if hasattr(record, "threadName") and record.threadName else ""
            ),
            exception=exception_text,
        )

    def _classify_log_type(self, record: logging.LogRecord) -> LogType:
        """根据logger名称和消息内容判断日志类型.

        分类规则：
        1. logger名称包含"alert"或"monitor" → ALERT
        2. logger名称包含"download"或消息包含"进度"/"%" → PROGRESS
        3. 消息包含"完成"/"成功"且级别=INFO → NOTIFICATION
        4. 级别=DEBUG → DEBUG
        5. 其他 → SYSTEM

        Args:
            record: 日志记录

        Returns:
            日志类型
        """
        logger_name = record.name.lower()
        message = record.getMessage().lower()

        # 1. 告警
        if "alert" in logger_name or "monitor" in logger_name:
            if record.levelno >= logging.WARNING:
                return LogType.ALERT

        # 2. 进度
        if "download" in logger_name or "progress" in logger_name:
            if "进度" in message or "%" in message or "progress" in message:
                return LogType.PROGRESS

        # 数据质量扫描也算进度
        if "quality" in logger_name or "scan" in logger_name:
            if "扫描" in message or "%" in message:
                return LogType.PROGRESS

        # 3. 通知
        if record.levelno == logging.INFO:
            if any(
                keyword in message
                for keyword in ["完成", "成功", "已完成", "finished", "completed", "success"]
            ):
                return LogType.NOTIFICATION

        # 4. DEBUG
        if record.levelno == logging.DEBUG:
            return LogType.DEBUG

        # 5. 默认：SYSTEM
        return LogType.SYSTEM

    def _init_routing_rules(self) -> Dict:
        """初始化路由规则.

        Returns:
            路由规则字典 {(LogType, level): [targets]}
        """
        return {
            # SYSTEM日志：所有级别到文件和控制台，WARNING+到数据库和事件
            (LogType.SYSTEM, logging.DEBUG): ["console", "file"],
            (LogType.SYSTEM, logging.INFO): ["console", "file"],
            (LogType.SYSTEM, logging.WARNING): ["console", "file", "database", "event"],
            (LogType.SYSTEM, logging.ERROR): ["console", "file", "database", "event"],
            (LogType.SYSTEM, logging.CRITICAL): [
                "console",
                "file",
                "database",
                "event",
                "ui_dialog",
            ],
            # PROGRESS日志：INFO级别不输出到控制台，只到文件和事件（节流）
            (LogType.PROGRESS, logging.DEBUG): [],
            (LogType.PROGRESS, logging.INFO): ["file", "event_throttled"],
            (LogType.PROGRESS, logging.WARNING): ["console", "file", "event"],
            (LogType.PROGRESS, logging.ERROR): ["console", "file", "database", "event"],
            # NOTIFICATION日志：到控制台、文件、事件、状态栏
            (LogType.NOTIFICATION, logging.INFO): ["console", "file", "event", "ui_statusbar"],
            (LogType.NOTIFICATION, logging.WARNING): ["console", "file", "database", "event"],
            # ALERT日志：全部输出
            (LogType.ALERT, logging.WARNING): [
                "console",
                "file",
                "database",
                "event",
                "ui_statusbar",
            ],
            (LogType.ALERT, logging.ERROR): ["console", "file", "database", "event", "ui_dialog"],
            (LogType.ALERT, logging.CRITICAL): [
                "console",
                "file",
                "database",
                "event",
                "ui_dialog",
            ],
            # USER_FEEDBACK日志：仅UI
            (LogType.USER_FEEDBACK, logging.INFO): ["ui_statusbar"],
            (LogType.USER_FEEDBACK, logging.ERROR): ["ui_dialog"],
            # DEBUG日志：仅文件，不输出到控制台
            (LogType.DEBUG, logging.DEBUG): ["file"],
        }

    def _get_targets(self, record: UnifiedLogRecord) -> List[str]:
        """获取日志应路由到的目标列表（四层路由决策）.

        Args:
            record: 统一日志记录

        Returns:
            目标列表
        """
        # 优先使用路由引擎（四层路由）
        if self._routing_engine:
            try:
                return self._routing_engine.route(record)
            except Exception as e:
                # 路由引擎出错，回退到硬编码规则
                self._internal_logger.error("路由引擎失败: %s，使用硬编码规则", e)

        # 回退方案：硬编码规则（兼容性）
        key = (record.type, record.level)
        if key in self._routing_rules:
            return self._routing_rules[key]

        # 找不到规则，使用默认
        if record.level >= logging.WARNING:
            return ["logger_file", "database"]
        else:
            return ["logger_file"]

    def _dispatch(self, targets: List[str], record: UnifiedLogRecord):
        """分发日志到目标.

        Args:
            targets: 目标列表
            record: 统一日志记录
        """
        for target in targets:
            try:
                if target == "console":  # 🆕
                    self._to_console(record)
                elif target == "file":  # 🆕
                    self._to_logger_file(record)
                elif target == "logger_file":  # 向后兼容（旧的）
                    self._to_logger_file(record)
                elif target == "database":
                    self._to_database_batched(record)
                elif target == "event":
                    self._to_event(record)
                elif target == "event_throttled":
                    self._to_event_throttled(record)
                elif target == "ui_statusbar":
                    self._to_ui_statusbar(record)
                elif target == "ui_dialog":
                    self._to_ui_dialog(record)
            except Exception:
                # 单个目标失败不影响其他目标
                pass

    def _to_logger_file(self, record: UnifiedLogRecord):
        """输出到日志文件（通过托管的FileHandler）.

        Args:
            record: 统一日志记录
        """
        if not self._file_handler:
            return

        # 转换回logging.LogRecord
        log_record = logging.LogRecord(
            name=record.logger_name,
            level=record.level,
            pathname=record.filename,
            lineno=record.line,
            msg=record.message,
            args=(),
            exc_info=None,
        )
        log_record.created = record.timestamp.timestamp()

        # 通过FileHandler输出
        self._file_handler.emit(log_record)
        self._file_writes += 1

    def _to_console(self, record: UnifiedLogRecord):
        """输出到控制台（通过托管的StreamHandler）.

        Args:
            record: 统一日志记录
        """
        if not self._console_handler:
            return

        # 检查该日志类型是否允许输出到控制台
        if record.type not in self._console_enabled_types:
            return

        # 转换回logging.LogRecord
        log_record = logging.LogRecord(
            name=record.logger_name,
            level=record.level,
            pathname=record.filename,
            lineno=record.line,
            msg=record.message,
            args=(),
            exc_info=None,
        )
        log_record.created = record.timestamp.timestamp()

        # 通过ConsoleHandler输出
        self._console_handler.emit(log_record)
        self._console_writes += 1

    def _to_database_batched(self, record: UnifiedLogRecord):
        """写入数据库（批量模式）.

        Args:
            record: 统一日志记录
        """
        # 只记录WARNING及以上级别
        if record.level < logging.WARNING:
            return

        if not self.db_manager:
            return

        # 添加到批量缓存
        self._db_batch_cache.append(
            {
                "timestamp": record.timestamp.isoformat(),
                "level": logging.getLevelName(record.level),
                "module": record.module,
                "message": record.message,
                "extra": (
                    json.dumps(
                        {
                            "logger_name": record.logger_name,
                            "function": record.function,
                            "line": record.line,
                            "filename": record.filename,
                            "thread": record.thread,
                            "thread_name": record.thread_name,
                            "exception": record.exception,
                            "details": record.details,
                        },
                        ensure_ascii=False,
                    )
                    if record.exception or record.details
                    else None
                ),
            }
        )

        # 达到批量大小时刷新
        if len(self._db_batch_cache) >= self._db_batch_size:
            self._flush_db_batch()

    def _flush_db_batch(self):
        """刷新数据库批量缓存（带降级处理）."""
        if not self._db_batch_cache:
            return

        if not self.db_manager:
            self._db_batch_cache.clear()
            return

        try:
            # 批量插入
            for log_data in self._db_batch_cache:
                self.db_manager.execute_update(
                    """
                    INSERT INTO system_logs
                    (timestamp, level, module, message, extra)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        log_data["timestamp"],
                        log_data["level"],
                        log_data["module"],
                        log_data["message"],
                        log_data["extra"],
                    ),
                )

            self._db_writes += len(self._db_batch_cache)
            self._db_batch_cache.clear()
            self._db_last_flush = time.time()

        except Exception as e:
            # 降级处理：批量写入失败时，尝试逐条写入
            self._internal_logger.warning("批量写入失败: %s, 降级为逐条写入", e)

            success_count = 0
            batch_copy = self._db_batch_cache.copy()  # 复制列表避免修改原始列表
            self._db_batch_cache.clear()  # 清空原始缓存

            for log_data in batch_copy:
                try:
                    self.db_manager.execute_update(
                        """
                        INSERT INTO system_logs
                        (timestamp, level, module, message, extra)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            log_data["timestamp"],
                            log_data["level"],
                            log_data["module"],
                            log_data["message"],
                            log_data["extra"],
                        ),
                    )
                    success_count += 1
                except Exception:
                    pass  # 静默失败，避免日志系统崩溃

            self._db_writes += success_count
            self._db_last_flush = time.time()
            self._internal_logger.info("逐条写入完成: 成功=%d/%d", success_count, len(batch_copy))

    def _maybe_flush_db_batch(self):
        """定期刷新数据库批量缓存."""
        if time.time() - self._db_last_flush >= self._db_flush_interval:
            self._flush_db_batch()

    def _to_event(self, record: UnifiedLogRecord):
        """发送到EventEngine（立即）.

        Args:
            record: 统一日志记录
        """
        if not self.event_engine:
            return

        # 根据日志类型选择事件类型
        event_type_map = {
            LogType.SYSTEM: EVENT_LOG_SYSTEM,
            LogType.PROGRESS: EVENT_LOG_PROGRESS,
            LogType.NOTIFICATION: EVENT_LOG_NOTIFICATION,
            LogType.ALERT: EVENT_LOG_ALERT,
            LogType.DEBUG: EVENT_LOG_SYSTEM,
            LogType.USER_FEEDBACK: EVENT_UI_STATUSBAR,
        }

        event_type = event_type_map.get(record.type, EVENT_LOG_SYSTEM)

        event_data = {
            "type": record.type.value,
            "level": logging.getLevelName(record.level),
            "module": record.module,
            "message": record.message,
            "details": record.details,
            "timestamp": record.timestamp.isoformat(),
            "logger_name": record.logger_name,
        }

        event = Event(event_type, event_data)
        self.event_engine.put(event)

    def _to_event_throttled(self, record: UnifiedLogRecord):
        """发送到EventEngine（节流）.

        Args:
            record: 统一日志记录
        """
        # 添加到节流器
        self._throttler.add(record)
        self._throttled_logs += 1

        # 检查是否可以发送
        aggregated = self._throttler.get_if_ready()
        if aggregated:
            self._to_event(aggregated)

    def _check_throttler(self):
        """检查节流器，发送待处理的日志."""
        if self._throttler.has_pending():
            aggregated = self._throttler.get_if_ready()
            if aggregated:
                self._to_event(aggregated)

    def _to_ui_statusbar(self, record: UnifiedLogRecord):
        """发送到UI状态栏.

        Args:
            record: 统一日志记录
        """
        if not self.event_engine:
            return

        event_data = {
            "message": record.message,
            "level": logging.getLevelName(record.level),
            "timestamp": record.timestamp.isoformat(),
            "type": record.type.value,
        }

        event = Event(EVENT_UI_STATUSBAR, event_data)
        self.event_engine.put(event)

    def _to_ui_dialog(self, record: UnifiedLogRecord):
        """发送到UI模态对话框.

        Args:
            record: 统一日志记录
        """
        if not self.event_engine:
            return

        event_data = {
            "title": logging.getLevelName(record.level),
            "message": record.message,
            "details": record.details,
            "timestamp": record.timestamp.isoformat(),
            "exception": record.exception,
        }

        event = Event(EVENT_UI_DIALOG, event_data)
        self.event_engine.put(event)

    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息.

        Returns:
            统计信息字典
        """
        stats = {
            "total_logs": self._total_logs,
            "throttled_logs": self._throttled_logs,
            "console_writes": self._console_writes,  # 🆕
            "file_writes": self._file_writes,  # 🆕
            "db_writes": self._db_writes,
            "db_batch_pending": len(self._db_batch_cache),
        }

        # 添加路由引擎统计
        if self._routing_engine:
            stats["routing_engine"] = self._routing_engine.get_statistics()

        return stats

    def set_stage(self, stage: str):
        """切换日志阶段（路由引擎功能）.

        Args:
            stage: 阶段名称（startup/downloading/trading等）
        """
        if self._routing_engine:
            self._routing_engine.set_stage(stage)

    def set_run_mode(self, mode: str):
        """切换运行模式（路由引擎功能）.

        Args:
            mode: 运行模式（dev/prod/ops）
        """
        if self._routing_engine:
            self._routing_engine.set_run_mode(mode)

    def reload_routing_rules(self):
        """热更新路由规则（路由引擎功能）."""
        if self._routing_engine:
            self._routing_engine.reload_rules()

    def close(self):
        """关闭LoggingHub，刷新所有缓存."""
        self._flush_db_batch()
        super().close()


# =============================================================================
# Part 5: MonitorLogProxy（监控进程日志代理）
# =============================================================================


class MonitorLogProxy:
    """监控进程日志代理.

    通过ZMQ PUSH socket发送日志到主进程。
    """

    def __init__(self, zmq_context, push_address: str = "tcp://127.0.0.1:5558"):
        """初始化日志代理.

        Args:
            zmq_context: ZMQ上下文
            push_address: PUSH socket地址（主进程PULL监听）
        """
        import zmq

        self.socket = zmq_context.socket(zmq.PUSH)
        self.socket.connect(push_address)
        self.socket.setsockopt(zmq.SNDTIMEO, 1000)  # 1秒发送超时

        # 统计
        self._sent_count = 0
        self._failed_count = 0

    def send_log(self, log_dict: Dict):
        """发送日志到主进程.

        Args:
            log_dict: 日志字典，包含level、module、message、timestamp等
        """
        try:
            self.socket.send_json({"type": "monitor_log", "data": log_dict}, flags=0)  # 非阻塞发送
            self._sent_count += 1
        except Exception:
            self._failed_count += 1
            # 静默失败

    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息.

        Returns:
            统计信息字典
        """
        return {
            "sent": self._sent_count,
            "failed": self._failed_count,
        }


class MonitorProxyHandler(logging.Handler):
    """监控进程日志Handler.

    将日志通过MonitorLogProxy发送到主进程。
    """

    def __init__(self, proxy: MonitorLogProxy):
        """初始化Handler.

        Args:
            proxy: MonitorLogProxy实例
        """
        super().__init__()
        self.proxy = proxy
        self.setLevel(logging.INFO)  # 只发送INFO及以上级别

    def emit(self, record: logging.LogRecord):
        """处理日志记录.

        Args:
            record: 日志记录
        """
        try:
            self.proxy.send_log(
                {
                    "level": record.levelname,
                    "module": record.module,
                    "message": record.getMessage(),
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "logger_name": record.name,
                    "function": record.funcName,
                    "line": record.lineno,
                }
            )
        except Exception:
            # 静默失败
            pass


# =============================================================================
# Part 6: 便捷API
# =============================================================================

# 全局单例
_hub_instance: Optional[LoggingHub] = None


def get_logging_hub() -> LoggingHub:
    """获取LoggingHub全局单例.

    Returns:
        LoggingHub实例
    """
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = LoggingHub()
    return _hub_instance


def log_progress(module: str, message: str, progress: float, **details):
    """记录进度日志（自动节流）.

    Args:
        module: 模块名称
        message: 日志消息
        progress: 进度值（0-100）
        **details: 额外详情

    Example:
        log_progress("data_center", "下载中", progress=45.2, completed=452, total=1000)
    """
    details["progress"] = progress

    # 使用标准logger（会被LoggingHub拦截）
    logger = logging.getLogger("backend.%s" % module)
    logger.info(message, extra=details)


def notify_complete(module: str, message: str, **details):
    """任务完成通知.

    Args:
        module: 模块名称
        message: 通知消息
        **details: 额外详情

    Example:
        notify_complete("data_center", "下载完成", count=1000, duration=120)
    """
    logger = logging.getLogger("backend.%s" % module)
    logger.info(message, extra=details)


def alert(severity: str, module: str, message: str, **details):
    """发送告警.

    Args:
        severity: 严重级别（WARNING/ERROR/CRITICAL）
        module: 模块名称
        message: 告警消息
        **details: 额外详情

    Example:
        alert("WARNING", "monitor", "CPU使用率超过80%", current=85.3, threshold=80)
    """
    logger = logging.getLogger("backend.%s" % module)
    level = getattr(logging, severity.upper(), logging.WARNING)
    logger.log(level, message, extra=details)


def log_system(level: str, module: str, message: str, **details):
    """记录系统日志.

    Args:
        level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        module: 模块名称
        message: 日志消息
        **details: 额外详情

    Example:
        log_system("INFO", "data_center", "数据下载开始", task_count=1000)
    """
    logger = logging.getLogger("backend.%s" % module)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(log_level, message, extra=details)


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 数据结构
    "LogType",
    "UnifiedLogRecord",
    # 核心类
    "LoggingHub",
    "ProgressThrottler",
    # 监控进程代理
    "MonitorLogProxy",
    "MonitorProxyHandler",
    # 事件类型
    "EVENT_LOG_SYSTEM",
    "EVENT_LOG_PROGRESS",
    "EVENT_LOG_NOTIFICATION",
    "EVENT_LOG_ALERT",
    "EVENT_UI_STATUSBAR",
    "EVENT_UI_DIALOG",
    # 便捷API
    "get_logging_hub",
    "log_progress",
    "notify_complete",
    "alert",
    "log_system",
]
