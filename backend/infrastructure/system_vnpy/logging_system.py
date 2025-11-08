# -*- coding: utf-8 -*-
"""
简化日志系统 - 重构版本 v6.0

设计目标：
1. 大幅简化路由规则（硬编码，不使用配置文件）
2. 合并文件输出（统一到 logs/ 目录）
3. 压缩文件数量（所有代码合并到一个文件）
4. 确保多进程多线程日志都能被拦截和有序输出

作者：系统重构团队
日期：2025-01-XX
版本：v6.0 (简化重构版)
"""

import base64
import json
import logging
import time
import asyncio
import multiprocessing
import threading
import heapq
import os
import pickle
import queue
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Dict, List, Optional, Callable, Tuple, Union
from logging.handlers import QueueHandler, QueueListener, MemoryHandler
from multiprocessing.managers import SyncManager

from vnpy.event import Event, EventEngine

# 可选：native 优先队列和LRU缓存（仅 Windows 支持）
try:
    from backend.infrastructure.native.native_collections import (
        HighPerfPriorityQueue,
        HighPerfLRUCache,
        COLLECTIONS_AVAILABLE as NATIVE_COLLECTIONS_AVAILABLE,
    )
except Exception:
    HighPerfPriorityQueue = None  # type: ignore
    HighPerfLRUCache = None  # type: ignore
    NATIVE_COLLECTIONS_AVAILABLE = False  # type: ignore

# 可选的native序列化（Windows C扩展，存在则用于批量写库打包）
try:
    from backend.infrastructure.native.native_serialization import (
        zero_copy_serialize,
    )
    NATIVE_SERIALIZATION_AVAILABLE = True
except Exception:
    zero_copy_serialize = None  # type: ignore
    NATIVE_SERIALIZATION_AVAILABLE = False

# 日志配置
logger = logging.getLogger("backend.infrastructure.system_vnpy.logging_system")

# 子进程通过环境变量接收日志队列代理
LOGGING_QUEUE_TOKEN_ENV = "LOGGING_QUEUE_TOKEN"

# =============================================================================
# Part 1: 数据结构定义
# =============================================================================


class LogType(Enum):
    """日志类型枚举."""

    SYSTEM = "system"
    PROGRESS = "progress"
    NOTIFICATION = "notification"
    ALERT = "alert"
    USER_FEEDBACK = "user_feedback"
    DEBUG = "debug"
    STAGE_NODE = "stage_node"


class AsyncLoggingHandler(logging.Handler):
    """异步日志处理器
    
    将日志记录放入队列中，由后台线程处理，避免阻塞主线程。
    """
    
    def __init__(self, target_handler: logging.Handler, max_queue_size: int = 10000, 
                 worker_count: int = 1, drop_when_full: bool = False):
        """初始化异步日志处理器
        
        Args:
            target_handler: 目标日志处理器，实际处理日志的处理器
            max_queue_size: 最大队列大小，超过此大小会根据drop_when_full决定是阻塞还是丢弃
            worker_count: 工作线程数
            drop_when_full: 当队列满时是否丢弃日志（True=丢弃，False=阻塞）
        """
        super().__init__()
        self.target_handler = target_handler
        self.max_queue_size = max_queue_size
        self.worker_count = worker_count
        self.drop_when_full = drop_when_full
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="AsyncLoggingWorker"
        )
        self._running = True
        self._workers = []
        
        # 启动工作线程
        for i in range(worker_count):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"AsyncLoggingWorker-{i}",
                daemon=True
            )
            t.start()
    
    def _worker_loop(self):
        """工作线程主循环"""
        while self._running or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            except Exception as exc:  # pragma: no cover
                print(f"Unexpected error in async logging worker (fetch): {exc}", file=sys.stderr)
                continue

            try:
                self.target_handler.handle(record)
            except Exception as exc:  # pragma: no cover
                # 避免递归调用，直接打印错误
                print(f"Error in async logging handler: {exc}", file=sys.stderr)
            finally:
                self._queue.task_done()
    
    def emit(self, record):
        """发送日志记录到队列"""
        if not self._running:
            return
            
        try:
            if self.drop_when_full:
                # 如果队列已满，尝试非阻塞放入
                try:
                    self._queue.put_nowait(record)
                except queue.Full:
                    # 队列已满，丢弃日志
                    pass
            else:
                # 阻塞直到队列有空间
                self._queue.put(record, block=True)
        except Exception as e:
            # 避免递归调用，直接打印错误
            print(f"Error in async logging emit: {e}", file=sys.stderr)
    
    def flush(self):
        """刷新日志"""
        self.target_handler.flush()
    
    def close(self):
        """关闭处理器"""
        self._running = False
        
        # 等待队列中的日志处理完成
        self._queue.join()
        
        # 关闭线程池
        self._executor.shutdown(wait=True)
        
        # 关闭目标处理器
        self.target_handler.close()
        
        super().close()
    
    def __getattr__(self, name):
        """将未定义的属性调用委托给目标处理器"""
        return getattr(self.target_handler, name)


# 排除字段集合（类级别常量，避免每次重新创建）
_EXCLUDED_FIELDS = frozenset(
    [
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
    ]
)


# 常用场景前缀映射（全部使用小写，以logger名称前缀匹配）
_SCENARIO_PREFIX_RULES: Tuple[Tuple[str, str], ...] = (
    # 任务类阶段日志
    ("task.manual_speedtest", "manual_speedtest"),
    ("task.refresh_symbol_list", "refresh_symbol_list"),
    ("task.strategy_generation", "strategy_generation"),
    ("task.strategy_optimization", "strategy_optimization"),
    ("task.strategy_explanation", "strategy_explanation"),
    ("task.strategy_debugging", "strategy_debugging"),
    ("task.data_download", "data_download"),
    ("task.manual_data_scan", "manual_data_scan"),
    ("task.portfolio_pnl_calculation", "portfolio_pnl_calculation"),
    ("task.tdx_data_read", "tdx_data_read"),
    ("task.optional_services_init", "optional_services_init"),
    # 启动流程
    ("backend.startup", "application_startup"),
    ("startup", "application_startup"),
    # 后端服务
    ("backend.services.system_manager", "system_manager"),
    ("backend.system_manager", "system_manager"),
    ("backend.services.data_center", "data_center"),
    ("backend.data_center", "data_center"),
    ("backend.services.database_adapter", "database_adapter"),
    ("backend.services.ai_assistant", "ai_assistant"),
    ("backend.services", "backend_services"),
    # 数据模块
    ("backend.data_module", "data_module_vnpy"),
    ("backend.infrastructure.data_module_vnpy", "data_module_vnpy"),
    # 系统模块
    ("backend.system", "system_manager"),
    ("backend.infrastructure.system_vnpy", "system_vnpy"),
    # 原生扩展
    ("backend.infrastructure.native", "native_infrastructure"),
    # 投资组合
    ("backend.portfolio", "portfolio"),
    # 核心与进程
    ("backend.core", "core_services"),
    ("data_process", "data_process_init"),
    # UI 模块
    ("ui.modules", "ui"),
    # 市场数据
    ("backend.market", "market_data"),
    # 策略模块
    ("backend.strategy", "strategy"),
)


def _infer_scenario_from_logger(logger_name: str) -> Optional[str]:
    """基于logger名称推断场景标识."""

    lower_name = logger_name.lower()

    # task.<scenario>.stage -> 取scenario作为场景名
    if lower_name.startswith("task.") and ".stage" in lower_name:
        scenario_part = lower_name[len("task.") : lower_name.index(".stage")]
        if scenario_part:
            return scenario_part.replace(".", "_")

    # startup.stage.* 默认归类为启动流程
    if lower_name.startswith("startup.stage"):
        return "application_startup"

    for prefix, scenario in _SCENARIO_PREFIX_RULES:
        if lower_name.startswith(prefix):
            return scenario

    return None


def get_configured_logger(
    name: str,
    *,
    log_type: str = "SYSTEM",
    scenario: Optional[str] = None,
) -> logging.Logger:
    """获取已绑定默认log_type与场景的logger."""

    return bind_logger_defaults(logging.getLogger(name), log_type=log_type, scenario=scenario)


def get_stage_logger(name: str, *, scenario: str = "application_startup") -> logging.Logger:
    """获取阶段节点日志logger."""

    return get_configured_logger(name, log_type="STAGE_NODE", scenario=scenario)


def get_alert_logger(name: str, *, scenario: Optional[str] = None) -> logging.Logger:
    """获取告警日志logger."""

    return get_configured_logger(name, log_type="ALERT", scenario=scenario)


def get_progress_logger(name: str, *, scenario: Optional[str] = None) -> logging.Logger:
    """获取进度日志logger."""

    return get_configured_logger(name, log_type="PROGRESS", scenario=scenario)


def _coerce_logger(
    logger: Optional[logging.Logger],
    *,
    default_name: str,
    log_type: str,
    scenario: Optional[str],
) -> logging.Logger:
    """确保返回的logger带有统一日志所需的默认字段."""

    if logger is None:
        if log_type == "STAGE_NODE":
            return get_stage_logger(default_name, scenario=scenario or "application_startup")
        if log_type == "ALERT":
            return get_alert_logger(default_name, scenario=scenario)
        if log_type == "PROGRESS":
            return get_progress_logger(default_name, scenario=scenario)
        return get_configured_logger(default_name, log_type=log_type, scenario=scenario)

    return bind_logger_defaults(logger, log_type=log_type, scenario=scenario)


def stage_log(
    message: str,
    *,
    logger: Optional[logging.Logger] = None,
    name: str = "startup.stage",
    scenario: Optional[str] = None,
    level: int = logging.INFO,
    extra: Optional[Dict[str, Any]] = None,
    stacklevel: int = 2,
    **kwargs: Any,
) -> None:
    """输出阶段节点日志，自动补齐 ``log_type`` / ``scenario`` 信息."""

    target_logger = _coerce_logger(logger, default_name=name, log_type="STAGE_NODE", scenario=scenario)
    payload = dict(extra) if extra else {}
    if scenario and "scenario" not in payload:
        payload["scenario"] = scenario
    target_logger.log(level, message, extra=payload or None, stacklevel=stacklevel, **kwargs)


def alert_log(
    message: str,
    *,
    logger: Optional[logging.Logger] = None,
    name: str = "backend.alert",
    scenario: Optional[str] = None,
    level: int = logging.WARNING,
    extra: Optional[Dict[str, Any]] = None,
    stacklevel: int = 2,
    **kwargs: Any,
) -> None:
    """输出告警日志，统一 ``log_type`` 与可选场景."""

    target_logger = _coerce_logger(logger, default_name=name, log_type="ALERT", scenario=scenario)
    payload = dict(extra) if extra else {}
    if scenario and "scenario" not in payload:
        payload["scenario"] = scenario
    target_logger.log(level, message, extra=payload or None, stacklevel=stacklevel, **kwargs)


def progress_log(
    message: str,
    *,
    logger: Optional[logging.Logger] = None,
    name: str = "backend.progress",
    scenario: Optional[str] = None,
    progress: Optional[float] = None,
    level: int = logging.INFO,
    extra: Optional[Dict[str, Any]] = None,
    stacklevel: int = 2,
    **kwargs: Any,
) -> None:
    """输出进度日志，自动补全进度与场景字段."""

    target_logger = _coerce_logger(logger, default_name=name, log_type="PROGRESS", scenario=scenario)
    payload = dict(extra) if extra else {}
    if progress is not None:
        payload.setdefault("progress", progress)
    if scenario and "scenario" not in payload:
        payload["scenario"] = scenario
    target_logger.log(level, message, extra=payload or None, stacklevel=stacklevel, **kwargs)


@dataclass
class UnifiedLogRecord:
    """统一日志记录
    
    扩展字段说明：
    - type: 日志类型（LogType枚举）
    - level: 日志级别（logging.INFO等）
    - module: 模块名
    - message: 日志消息
    - details: 详细信息（字典）
    - timestamp: 时间戳
    - logger_name: 记录器名称
    - function: 函数名
    - line: 行号
    - filename: 文件名
    - thread: 线程ID
    - thread_name: 线程名称
    - exception: 异常信息
    - request_id: 请求ID（用于跟踪请求链路）
    - session_id: 会话ID（用于关联用户会话）
    - user_id: 用户ID（如果适用）
    - component: 组件名称（如模块名）
    - operation: 操作名称（如函数名）
    - duration: 操作耗时（毫秒）
    - extra: 额外自定义字段（字典）
    """

    type: LogType
    level: int
    module: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    logger_name: str = ""
    function: str = ""
    line: int = 0
    filename: str = ""
    thread: int = 0
    thread_name: str = ""
    exception: str = ""
    
    # 请求和会话信息
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # 组件和操作信息
    component: str = ""
    operation: str = ""
    
    # 性能指标
    duration: Optional[float] = None  # 毫秒
    
    # 额外自定义字段
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # 如果未设置component，使用logger_name
        if not self.component and self.logger_name:
            self.component = self.logger_name
            
        # 如果未设置operation，使用function
        if not self.operation and self.function:
            self.operation = self.function
    
    def to_dict(self) -> Dict[str, Any]:
        """将日志记录转换为字典格式"""
        result = {
            'timestamp': self.timestamp.isoformat(),
            'level': logging.getLevelName(self.level),
            'levelno': self.level,
            'logger': self.logger_name,
            'message': self.message,
            'type': self.type.name if hasattr(self.type, 'name') else str(self.type),
            'module': self.module,
            'function': self.function,
            'filename': self.filename,
            'line': self.line,
            'thread': self.thread,
            'thread_name': self.thread_name,
            'request_id': self.request_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'component': self.component,
            'operation': self.operation,
            'duration': self.duration,
        }
        
        # 添加异常信息
        if self.exception:
            result['exception'] = self.exception
            
        # 添加详细信息
        if self.details:
            result['details'] = self.details
            
        # 添加额外字段
        if self.extra:
            result.update(self.extra)
            
        return result
    
    def to_json(self, **kwargs) -> str:
        """将日志记录转换为JSON字符串
        
        Args:
            **kwargs: 传递给json.dumps的参数
            
        Returns:
            JSON格式的字符串
        """
        import json
        default_kwargs = {
            'ensure_ascii': False,
            'default': str,
            'indent': None,
            'separators': (',', ':')
        }
        default_kwargs.update(kwargs)
        return json.dumps(self.to_dict(), **default_kwargs)


def bind_logger_defaults(
    logger: logging.Logger,
    *,
    log_type: str = "SYSTEM",
    scenario: Optional[str] = None,
) -> logging.Logger:
    """为指定 logger 绑定默认的日志类型与场景元数据.

    由于大量模块在迁移过程中逐步补充埋点，部分调用缺失 ``extra`` 参数。
    该辅助函数会在 logger 的常用方法上自动注入 ``extra``，确保统一日志系统
    能正确路由到对应的 LogType/场景，同时保留调用方已经显式指定的 ``extra``。

    Args:
        logger: 需要绑定默认属性的 ``logging.Logger`` 实例。
        log_type: 默认的 ``log_type``，例如 ``"SYSTEM"``、``"ALERT"`` 等。
        scenario: 可选的 ``scenario`` 标识，便于统一日志系统做精细化路由。

    Returns:
        同一个 logger 实例，便于链式调用。
    """

    signature = (log_type, scenario)
    if getattr(logger, "_log_defaults_signature", None) == signature:
        return logger

    def _prepare_extra(extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base: Dict[str, Any]
        if extra is None:
            base = {}
        elif isinstance(extra, dict):
            base = dict(extra)
        else:
            # 避免修改原对象，尽力转换为dict
            base = dict(extra)

        base.setdefault("log_type", log_type)
        if scenario and "scenario" not in base:
            base["scenario"] = scenario
        return base

    def _wrap(method_name: str, expects_level: bool = False):
        original = getattr(logger, method_name)

        if expects_level:

            @wraps(original)
            def wrapper(level, msg, *args, **kwargs):  # type: ignore[override]
                kwargs["extra"] = _prepare_extra(kwargs.get("extra"))
                return original(level, msg, *args, **kwargs)

        else:

            @wraps(original)
            def wrapper(msg, *args, **kwargs):  # type: ignore[override]
                kwargs["extra"] = _prepare_extra(kwargs.get("extra"))
                if method_name == "exception":
                    kwargs.setdefault("exc_info", True)
                return original(msg, *args, **kwargs)

        return wrapper

    for name in ("debug", "info", "warning", "error", "critical", "exception"):
        setattr(logger, name, _wrap(name))

    setattr(logger, "log", _wrap("log", expects_level=True))
    logger._log_defaults_signature = signature  # type: ignore[attr-defined]
    return logger


# =============================================================================
# Part 2: 事件类型定义
# =============================================================================

EVENT_LOG_SYSTEM = "eLogSystem"
EVENT_LOG_PROGRESS = "eLogProgress"
EVENT_LOG_NOTIFICATION = "eLogNotification"
EVENT_LOG_ALERT = "eLogAlert"
EVENT_UI_STATUSBAR = "eUIStatusBar"
EVENT_UI_DIALOG = "eUIDialog"

# 支持的事件名称（硬编码）
SUPPORTED_EVENTS = {
    "application_startup",
    "manual_speedtest",
    "tdx_data_read",
    "refresh_symbol_list",
    "data_download",
    "manual_data_scan",
    "backtest_run",
}


# =============================================================================
# Part 3: 有序日志队列（确保terminal和数据库输出有序）
# =============================================================================


class OrderedLogQueue:
    """有序日志队列 - 确保并发场景时日志按执行时间顺序展示

    支持：
    - 按执行时间排序（而非序列号）
    - 并发场景时日志按时间顺序展示
    - 日志滞后处理（可以滞后但不能丢失）
    """

    def __init__(self, max_wait_seconds: int = 30):
        """初始化有序日志队列

        Args:
            max_wait_seconds: 最大等待时间（秒），超过此时间即使前面的日志未到也输出
        """
        # 根据系统环境选择实现：native 优先队列或 Python heapq
        self._use_native = bool(NATIVE_COLLECTIONS_AVAILABLE and HighPerfPriorityQueue)
        self.queue: List[Tuple[float, Any]] = []  # [(timestamp, record), ...]（回退实现）
        self._pq = HighPerfPriorityQueue() if self._use_native else None  # type: ignore
        self.lock = threading.Lock()
        self.max_wait_seconds = max_wait_seconds
        self.logger = logging.getLogger(
            "backend.infrastructure.system_vnpy.logging_system.ordered_queue"
        )

        # 记录日志的时间戳（用于超时检测）
        self._record_timestamps: Dict[float, float] = {}
        self._output_callback: Optional[Callable[[Any], None]] = None

        # 后台线程：定期检查并输出超时的日志
        self._running = True
        self._check_thread = threading.Thread(target=self._check_timeout_logs, daemon=True)
        self._check_thread.start()

    def set_output_callback(self, callback: Callable[[Any], None]):
        """设置输出回调函数

        Args:
            callback: 回调函数，接收 UnifiedLogRecord 作为参数
        """
        self._output_callback = callback

    def add_log(self, record: Any, sequence: int):
        """添加日志到队列（按执行时间排序）

        Args:
            record: 日志记录（UnifiedLogRecord）
            sequence: 日志序列号（用于兼容性，实际按时间排序）
        """
        with self.lock:
            # 使用记录的时间戳作为排序键（更准确的时间顺序）
            timestamp = (
                record.timestamp.timestamp()
                if hasattr(record.timestamp, "timestamp")
                else record.timestamp
            )
            if not isinstance(timestamp, (int, float)):
                timestamp = time.time()
            record.sequence = sequence

            if self._use_native and self._pq is not None:
                # native 优先队列为"高优先级先出"，为了最早时间先出，使用负数优先级
                try:
                    self._pq.put(record, -float(timestamp))  # type: ignore
                except Exception:
                    # 发生异常时回退到 Python 实现
                    self._use_native = False
                    self.queue.append((timestamp, record))
                    heapq.heapify(self.queue)
                self._record_timestamps[timestamp] = time.time()
            else:
                heapq.heappush(self.queue, (timestamp, record))
                self._record_timestamps[timestamp] = time.time()

            self._try_flush()

    def _try_flush(self):
        """尝试输出队列中已准备好的日志（按时间顺序）"""
        if self._use_native and self._pq is not None:
            try:
                # 按时间顺序输出所有日志
                while self._pq.size() > 0:  # type: ignore
                    record = self._pq.get()  # type: ignore
                    # 重新获取时间戳用于清理
                    ts = (
                        record.timestamp.timestamp()
                        if hasattr(record.timestamp, "timestamp")
                        else record.timestamp
                    )
                    if not isinstance(ts, (int, float)):
                        ts = time.time()
                    self._output_log(record)
                    self._record_timestamps.pop(float(ts), None)
            except Exception:
                # 任意异常回退到 Python 实现
                self._use_native = False
                # 无法直接获取 native 队列剩余元素，保持现有状态
                # 后续 add_log 将使用 Python heapq 路径
        else:
            # 按时间顺序输出所有日志
            while self.queue:
                timestamp, record = heapq.heappop(self.queue)
                # 输出日志
                self._output_log(record)
                # 清理时间戳
                self._record_timestamps.pop(timestamp, None)

    def _output_log(self, record: Any):
        """输出日志到回调函数

        Args:
            record: 日志记录（UnifiedLogRecord）
        """
        if self._output_callback:
            try:
                self._output_callback(record)
            except Exception as e:
                self.logger.exception(f"输出日志回调失败: {e}")

    def _check_timeout_logs(self):
        """后台线程：定期检查并输出超时的日志"""
        while self._running:
            time.sleep(0.5)  # 每0.5秒检查一次

            with self.lock:
                if not self.queue:
                    continue

                # 检查是否有超时的日志
                current_time = time.time()
                timeout_timestamps = [
                    timestamp
                    for timestamp, added_time in self._record_timestamps.items()
                    if current_time - added_time > self.max_wait_seconds
                ]

                # 输出超时的日志（按时间顺序）
                if timeout_timestamps:
                    # 对超时的日志按时间排序
                    timeout_timestamps.sort()

                    if self._use_native and self._pq is not None:
                        try:
                            # 将所有元素取出，输出超时的，保留未超时的
                            remaining: List[Tuple[float, Any]] = []
                            while self._pq.size() > 0:  # type: ignore
                                rec = self._pq.get()  # type: ignore
                                ts = (
                                    rec.timestamp.timestamp()
                                    if hasattr(rec.timestamp, "timestamp")
                                    else rec.timestamp
                                )
                                if not isinstance(ts, (int, float)):
                                    ts = time.time()
                                fts = float(ts)
                                if fts in timeout_timestamps:
                                    self._output_log(rec)
                                    self._record_timestamps.pop(fts, None)
                                else:
                                    remaining.append((fts, rec))
                            # 重新插回未超时的
                            for fts, rec in remaining:
                                self._pq.put(rec, -fts)  # type: ignore
                        except Exception:
                            # 回退到 Python 路径
                            self._use_native = False
                            # 无法恢复 native 队列内容，后续由 add_log 填充
                    else:
                        for timeout_ts in timeout_timestamps:
                            # 找到对应的日志记录
                            for i, (q_ts, q_record) in enumerate(self.queue):
                                if q_ts == timeout_ts:
                                    # 输出日志
                                    self._output_log(q_record)
                                    # 从队列中移除
                                    self.queue.pop(i)
                                    heapq.heapify(self.queue)
                                    # 清理时间戳
                                    self._record_timestamps.pop(timeout_ts, None)
                                    break

                # 继续尝试正常输出
                self._try_flush()

    def close(self):
        """关闭队列"""
        self._running = False
        if self._check_thread.is_alive():
            self._check_thread.join(timeout=1.0)


# =============================================================================
# Part 4: 持久化缓冲Handler（日志系统初始化前的日志拦截）
# =============================================================================


class PersistentBufferHandler(logging.Handler):
    """持久化缓冲Handler - 防止进程崩溃导致日志丢失

    在日志系统初始化前，将日志写入临时文件。
    日志系统就绪后，重放临时文件中的日志。
    """

    def __init__(self, buffer_dir: str = "logs/buffer", capacity: int = 10000):
        """初始化持久化缓冲Handler.

        Args:
            buffer_dir: 缓冲文件目录
            capacity: 内存缓冲容量（超过此容量后写入文件）
        """
        super().__init__()
        self.setLevel(logging.DEBUG)

        self.buffer_dir = Path(buffer_dir)
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.capacity = capacity

        # 内存缓冲（快速）
        self._memory_buffer: List[logging.LogRecord] = []
        self._lock = Lock()

        # 持久化文件
        self._buffer_file: Optional[Path] = None
        self._file_handle: Optional[Any] = None
        self._init_buffer_file()

        self.logger = logging.getLogger(
            "backend.infrastructure.system_vnpy.logging_system.persistent_buffer"
        )

    def _init_buffer_file(self):
        """初始化缓冲文件."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"init_buffer_{timestamp}.log"
            self._buffer_file = self.buffer_dir / filename
            self._file_handle = open(self._buffer_file, "w", encoding="utf-8")
            self.logger.debug(f"持久化缓冲文件已创建: {self._buffer_file}")
        except Exception as e:
            self.logger.error(f"创建持久化缓冲文件失败: {e}", exc_info=True)
            self._buffer_file = None
            self._file_handle = None

    def emit(self, record: logging.LogRecord):
        """处理日志记录."""
        try:
            with self._lock:
                # 添加到内存缓冲
                self._memory_buffer.append(record)

                # 如果内存缓冲超过容量，写入文件
                if len(self._memory_buffer) >= self.capacity:
                    self._flush_to_file()
        except Exception:
            pass

    def _flush_to_file(self):
        """将内存缓冲刷新到文件."""
        if not self._file_handle or not self._memory_buffer:
            return

        try:
            for record in self._memory_buffer:
                # 序列化日志记录
                record_dict = {
                    "name": record.name,
                    "levelno": record.levelno,
                    "levelname": record.levelname,
                    "pathname": record.pathname,
                    "lineno": record.lineno,
                    "msg": record.getMessage(),
                    "created": record.created,
                    "funcName": record.funcName,
                    "exc_info": str(record.exc_info) if record.exc_info else None,
                    "exc_text": record.exc_text if hasattr(record, "exc_text") else None,
                }
                line = json.dumps(record_dict, ensure_ascii=False, default=str) + "\n"
                self._file_handle.write(line)

            self._file_handle.flush()
            self._memory_buffer.clear()
            self.logger.debug(f"已刷新 {self.capacity} 条日志到缓冲文件")
        except Exception as e:
            self.logger.error(f"刷新日志到文件失败: {e}", exc_info=True)

    def replay_to_logging_hub(self, logging_hub: "LoggingHub"):
        """重放缓冲日志到LoggingHub.

        Args:
            logging_hub: LoggingHub实例
        """
        try:
            with self._lock:
                # 重放内存缓冲
                for record in self._memory_buffer:
                    # 恢复日志记录的时间戳
                    record.created = record.created if hasattr(record, "created") else time.time()
                    logging_hub.emit(record)

                self._memory_buffer.clear()

                # 重放文件缓冲
                if self._buffer_file and self._buffer_file.exists():
                    self.logger.info(f"开始重放持久化缓冲文件: {self._buffer_file}")
                    with open(self._buffer_file, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                record_dict = json.loads(line.strip())
                                # 重建LogRecord
                                record = logging.LogRecord(
                                    name=record_dict["name"],
                                    level=record_dict["levelno"],
                                    pathname=record_dict["pathname"],
                                    lineno=record_dict["lineno"],
                                    msg=record_dict["msg"],
                                    args=(),
                                    exc_info=None,
                                )
                                record.created = record_dict["created"]
                                record.funcName = record_dict.get("funcName", "")
                                logging_hub.emit(record)
                            except Exception as e:
                                self.logger.warning(f"重放日志记录失败: {e}")

                    # 删除缓冲文件
                    try:
                        self._buffer_file.unlink()
                        self.logger.info(f"缓冲文件已删除: {self._buffer_file}")
                    except Exception:
                        pass

                self.logger.info("持久化缓冲日志重放完成")
        except Exception as e:
            self.logger.error(f"重放缓冲日志失败: {e}", exc_info=True)

    def close(self):
        """关闭Handler."""
        try:
            with self._lock:
                # 刷新剩余内存缓冲
                self._flush_to_file()

                # 关闭文件
                if self._file_handle:
                    self._file_handle.close()
                    self._file_handle = None
        except Exception:
            pass
        super().close()


# =============================================================================
# Part 5: 多进程日志收集器
# =============================================================================


class MultiProcessLogCollector:
    """多进程日志收集器。

    使用 ``multiprocessing.managers.SyncManager`` 托管跨进程队列，并在主进程中
    启动 ``QueueListener`` 将子进程日志统一路由到 ``LoggingHub``。收集器会：

    1. 在 ``start()`` 时构建 SyncManager 与 QueueListener；
    2. 通过 ``get_queue()`` 暴露 QueueProxy，供主进程直接写入启动阶段日志；
    3. 通过 ``get_bridge_token()`` 生成 Base64 token，便于子进程通过环境变量复用；
    4. 当子进程无法还原队列时，记录 WARNING 并让子进程回退到本地日志，确保启动流程不中断。
    """

    def __init__(self, logging_hub: "LoggingHub", queue: Optional[multiprocessing.Queue] = None):
        """初始化多进程日志收集器.

        Args:
            logging_hub: 主进程的LoggingHub实例
            queue: 共享队列（如果为None，自动创建）
        """
        self.logging_hub = logging_hub
        self._manager: Optional[SyncManager] = None
        self._queue_token: Optional[str] = None
        self._ring: Optional["SharedLogRing"] = None
        self._ring_consumer: Optional["SharedRingConsumer"] = None
        self.queue = queue
        if self.queue is None:
            if not self._try_create_shared_ring():
                self.queue = self._create_managed_queue()
        self.queue_listener: Optional[QueueListener] = None
        self._running = False
        self._lock = Lock()
        self.logger = logging.getLogger(
            "backend.infrastructure.system_vnpy.logging_system.multiprocess_collector"
        )

    def _try_create_shared_ring(self) -> bool:
        if self._ring is not None:
            return True
        try:
            from backend.infrastructure.system_vnpy.native_log_bridge import (
                SharedLogRing,
                SharedRingConsumer,
                create_shared_log_ring,
            )
        except Exception:
            return False

        ring = create_shared_log_ring()
        if not ring:
            return False

        try:
            token_payload = {
                "version": 3,
                "mode": "shared_ring",
                "ring": ring.export_token(),
            }
            raw_token = json.dumps(token_payload).encode("utf-8")
            self._queue_token = base64.b64encode(raw_token).decode("ascii")
        except Exception:
            ring.close(unlink=True)
            return False

        self._ring = ring
        self._ring_consumer = None  # 延迟在 start() 中创建
        self.logger.info(
            "原生日志共享环缓存已启用 (capacity=%d)",
            ring.capacity,
            extra={"log_type": "SYSTEM"},
        )
        return True

    def _create_managed_queue(self) -> Any:
        """创建由 SyncManager 托管的队列，并序列化代理供子进程复用."""
        authkey = secrets.token_bytes(32)
        manager = SyncManager(address=("127.0.0.1", 0), authkey=authkey)
        manager.start()

        queue_proxy = manager.Queue(-1)
        # 将队列代理序列化为 Base64，便于通过环境变量传递
        try:
            queue_pickled = base64.b64encode(pickle.dumps(queue_proxy)).decode("ascii")
            token_payload = {
                "version": 2,
                "queue_pickled": queue_pickled,
                "authkey": base64.b64encode(authkey).decode("ascii"),
                "address": manager.address,
            }
            token_bytes = json.dumps(token_payload).encode("utf-8")
            self._queue_token = base64.b64encode(token_bytes).decode("ascii")
        except Exception as exc:
            manager.shutdown()
            raise RuntimeError(f"无法序列化日志队列代理: {exc}")

        self._manager = manager
        return queue_proxy

    def start(self):
        """启动日志收集."""
        if self._running:
            return

        try:
            with self._lock:
                if self._ring is not None:
                    from backend.infrastructure.system_vnpy.native_log_bridge import SharedRingConsumer

                    consumer = SharedRingConsumer(
                        self._ring,
                        self._handle_ring_record,
                        poll_interval=0.001,
                        name="shared-log-consumer",
                    )
                    consumer.start()
                    self._ring_consumer = consumer
                    self._running = True
                    self.logger.info("多进程日志收集器已启动 (shared ring)")
                    return

                # 创建QueueListener，将所有日志转发到LoggingHub
                self.queue_listener = QueueListener(
                    self.queue,
                    self.logging_hub,
                    respect_handler_level=True,
                )
                self.queue_listener.start()
                self._running = True
                self.logger.info("多进程日志收集器已启动")
        except Exception as e:
            self.logger.error(f"启动多进程日志收集器失败: {e}", exc_info=True)

    def _handle_ring_record(self, payload: Any) -> None:
        try:
            if isinstance(payload, logging.LogRecord):
                record = payload
            elif isinstance(payload, dict):
                record = logging.makeLogRecord(payload)
            else:
                record = logging.makeLogRecord(getattr(payload, "__dict__", {}))
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("共享日志环解析失败: %s", exc, exc_info=True)
            return
        try:
            self.logging_hub.handle(record)
        except Exception:  # noqa: BLE001
            self.logger.error("shared ring record dispatch failed", exc_info=True)

    def stop(self):
        """停止日志收集."""
        if not self._running:
            return

        try:
            with self._lock:
                if self._ring_consumer is not None:
                    self._ring_consumer.stop()
                    self._ring_consumer = None
                if self._ring is not None:
                    self._ring.close(unlink=True)
                    self._ring = None
                if self.queue_listener:
                    self.queue_listener.stop()
                    self.queue_listener = None
                self._running = False
                self.logger.info("多进程日志收集器已停止")
                if self._manager:
                    try:
                        self._manager.shutdown()
                    except Exception as shutdown_error:
                        self.logger.debug(
                            "关闭日志队列管理器失败: %s", shutdown_error, extra={"log_type": "SYSTEM"}
                        )
                    finally:
                        self._manager = None
        except Exception as e:
            self.logger.error(f"停止多进程日志收集器失败: {e}", exc_info=True)

    def get_queue(self) -> Any:
        """获取共享队列（供子进程使用）.

        Returns:
            multiprocessing.Queue实例
        """
        return self.queue

    def get_bridge_token(self) -> Optional[str]:
        """返回可序列化的队列代理，供子进程通过环境变量复用."""

        return self._queue_token


def setup_subprocess_logging(queue: multiprocessing.Queue, level: int = logging.DEBUG, process_name: str = None):
    """配置子进程日志（子进程调用）

    Args:
        queue: 共享的multiprocessing.Queue
        level: 日志级别
        process_name: 进程名称，用于日志标识
    """
    import os
    import socket
    import getpass
    from typing import Dict, Any, Optional
    
    # 获取进程信息
    process_name = process_name or multiprocessing.current_process().name
    hostname = socket.gethostname()
    username = getpass.getuser()
    pid = os.getpid()
    
    # 创建日志记录工厂函数
    old_factory = logging.getLogRecordFactory()
    
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        # 添加进程上下文信息
        record.process_name = process_name
        record.hostname = hostname
        record.username = username
        record.pid = pid
        
        # 确保extra字典存在
        if not hasattr(record, 'extra'):
            record.extra = {}
            
        # 添加追踪ID（如果存在）
        if hasattr(record, 'trace_id'):
            record.extra['trace_id'] = record.trace_id
            
        return record
    
    # 设置日志记录工厂
    logging.setLogRecordFactory(record_factory)
    
    # 创建根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 移除所有现有handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 添加QueueHandler
    queue_handler = QueueHandler(queue)
    queue_handler.setLevel(level)
    
    # 优化日志格式，包含进程信息
    formatter = logging.Formatter(
        '%(asctime)s [%(process_name)s:%(pid)s] [%(levelname)-8s] %(name)-40s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    queue_handler.setFormatter(formatter)
    root_logger.addHandler(queue_handler)
    
    # 配置常见库的日志级别
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    
    # 记录启动信息
    logger = logging.getLogger(__name__)
    # 🔧 修复：避免在extra中使用process_name（与LogRecord内置属性冲突），改用格式化字符串
    logger.info(
        "子进程日志系统已初始化 (process=%s, pid=%d, host=%s, user=%s)",
        process_name, pid, hostname, username
    )


def restore_queue_from_token(token: str) -> Optional[multiprocessing.Queue]:
    """根据token还原队列代理（供子进程使用）。"""

    try:
        raw_bytes = base64.b64decode(token.encode("ascii"))
    except Exception as exc:
        logger.error("日志队列token解码失败: %s", exc, exc_info=True)
        return None

    expected_auth: Optional[bytes] = None
    expected_address: Optional[Any] = None
    queue: Optional[multiprocessing.Queue] = None

    payload: Optional[Any] = None
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        payload = None

    if isinstance(payload, dict) and payload.get("mode") == "shared_ring":
        ring_token = payload.get("ring")
        if not ring_token:
            logger.error("共享日志环 token 缺失")
            return None
        try:
            from backend.infrastructure.system_vnpy.native_log_bridge import attach_shared_log_ring

            adapter = attach_shared_log_ring(ring_token)
        except Exception as exc:
            logger.error("共享日志环恢复失败: %s", exc, exc_info=True)
            return None
        if adapter is None:
            logger.error("共享日志环不可用")
        return adapter

    if isinstance(payload, dict) and "queue_pickled" in payload:
        try:
            queue_pickled_b64 = payload.get("queue_pickled")
            authkey_b64 = payload.get("authkey")
            expected_address = payload.get("address")

            if authkey_b64:
                try:
                    expected_auth = base64.b64decode(authkey_b64.encode("ascii"))
                    multiprocessing.current_process().authkey = expected_auth  # type: ignore[attr-defined]
                except Exception as auth_exc:
                    logger.debug(
                        "无法设置当前进程authkey: %s",
                        auth_exc,
                        extra={"log_type": "SYSTEM"},
                    )

            if not queue_pickled_b64:
                raise ValueError("队列代理缺失")

            queue_bytes = base64.b64decode(queue_pickled_b64.encode("ascii"))
            queue = pickle.loads(queue_bytes)
        except Exception:
            queue = None

    # 兼容旧版pickle格式（v1）
    if queue is None:
        try:
            legacy_payload = pickle.loads(raw_bytes)
            queue = legacy_payload.get("queue")
            if queue is None:
                raise ValueError("队列代理缺失")
            expected_auth = legacy_payload.get("authkey")
            expected_address = legacy_payload.get("address")
        except Exception as exc:
            logger.error("无法还原日志队列代理: %s", exc, exc_info=True)
            return None

    if hasattr(queue, "_authkey") and expected_auth and queue._authkey != expected_auth:  # type: ignore[attr-defined]
        logger.debug("子进程日志队列authkey不一致，使用队列内置值", extra={"log_type": "SYSTEM"})
    if hasattr(queue, "_address") and expected_address and queue._address != tuple(expected_address):  # type: ignore[attr-defined]
        logger.debug("子进程日志队列address不一致，使用队列内置值", extra={"log_type": "SYSTEM"})

    return queue


def load_queue_from_env() -> Optional[multiprocessing.Queue]:
    """从预定义环境变量中恢复日志队列代理."""

    token = os.environ.get(LOGGING_QUEUE_TOKEN_ENV)
    if not token:
        return None
    return restore_queue_from_token(token)


# =============================================================================
# Part 6: 进度节流器
# =============================================================================


class ProgressThrottler:
    """进度日志节流器（500ms聚合窗口）."""

    def __init__(self, interval_ms: int = 500):
        """初始化节流器."""
        self.interval_ms = interval_ms
        self._last_emit_time = 0
        self._pending_record: Optional[UnifiedLogRecord] = None
        self._pending_count = 0

    def add(self, record: UnifiedLogRecord):
        """添加进度记录."""
        self._pending_record = record
        self._pending_count += 1

    def get_if_ready(self) -> Optional[UnifiedLogRecord]:
        """检查是否可以发送."""
        current_time = time.time() * 1000
        if current_time - self._last_emit_time >= self.interval_ms:
            if self._pending_record:
                result = self._pending_record
                if result.details is None:
                    result.details = {}
                result.details["_throttled_count"] = self._pending_count

                self._pending_record = None
                self._pending_count = 0
                self._last_emit_time = current_time
                return result
        return None

    def has_pending(self) -> bool:
        """是否有待发送记录."""
        return self._pending_record is not None


# =============================================================================
# Part 7: 事件日志文件Handler（替代AILogFileHandler）
# =============================================================================


class EventLogFileHandler(logging.Handler):
    """事件日志文件Handler - 为每个事件创建独立的日志文件

    事件日志输出统一位于 logs/ 目录，文件命名格式：
    logs/{event_name}_YYYYMMDD_HHMMSS.log
    """

    def __init__(self, base_dir: str = "logs", encoding: str = "utf-8"):
        """初始化事件日志Handler."""
        super().__init__()
        self.setLevel(logging.DEBUG)

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.encoding = encoding

        # 当前事件日志文件
        self._current_event: Optional[str] = None
        self._current_event_file: Optional[Any] = None
        self._current_event_file_path: Optional[Path] = None
        self._event_ref_count: Dict[str, int] = {}  # 事件引用计数（用于嵌套调用）
        self._event_metadata: Dict[str, List[Dict[str, Any]]] = {}  # 事件元数据列表（用于合并）
        self._lock = Lock()

        # 统计
        self._event_count = 0
        self._total_logs = 0
        self._level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

        # 格式化器
        self.setFormatter(
            logging.Formatter(
                fmt="[%(asctime)s] [%(levelname)-8s] [%(name)-40s] [%(funcName)s:%(lineno)d]\n    %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def start_event(self, event_name: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """开始新事件日志（支持同一事件的复用和元数据合并）

        Args:
            event_name: 事件名称（必须为SUPPORTED_EVENTS中的一个）
            metadata: 事件元数据（可选）

        Returns:
            事件日志文件路径
        """
        if event_name not in SUPPORTED_EVENTS:
            raise ValueError(f"不支持的事件名称: {event_name}，支持的事件: {SUPPORTED_EVENTS}")

        try:
            with self._lock:
                # 检查是否已有同名事件正在进行
                if self._current_event == event_name and self._current_event_file and self._current_event_file_path:
                    # 复用现有文件，增加引用计数并合并元数据
                    self._event_ref_count[event_name] = self._event_ref_count.get(event_name, 0) + 1
                    if metadata:
                        if event_name not in self._event_metadata:
                            self._event_metadata[event_name] = []
                        self._event_metadata[event_name].append(metadata)
                        # 追加元数据到文件
                        metadata_section = self._build_metadata_section(metadata, is_additional=True)
                        self._current_event_file.write(metadata_section)
                        self._current_event_file.flush()

                    logger.debug(
                        f"[EventLogFileHandler] 复用事件日志文件: {event_name}, "
                        f"引用计数: {self._event_ref_count[event_name]}"
                    )
                    return self._current_event_file_path  # type: ignore

                # 关闭当前事件文件（如果存在且事件名称不同）
                if self._current_event and self._current_event != event_name:
                    self._close_current_event_file()

                # 创建新事件日志文件
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{event_name}_{timestamp}.log"
                file_path = self.base_dir / filename

                self._current_event_file = open(file_path, "w", encoding=self.encoding, buffering=1)
                self._current_event_file_path = file_path
                self._current_event = event_name
                self._event_count += 1

                # 初始化引用计数和元数据
                self._event_ref_count[event_name] = 1
                if metadata:
                    self._event_metadata[event_name] = [metadata]
                else:
                    self._event_metadata[event_name] = []

                # 写入文件头（包含所有元数据）
                all_metadata = self._event_metadata.get(event_name, [])
                header = self._build_file_header(event_name, file_path, all_metadata)
                self._current_event_file.write(header)
                self._current_event_file.flush()

                # 重置级别统计
                self._level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

                logger.info(f"[EventLogFileHandler] 事件日志文件已创建: {file_path.absolute()}")
                return file_path
        except Exception as e:
            logger.error(f"[EventLogFileHandler] 启动事件日志失败: {event_name}, 错误: {e}", exc_info=True)
            raise

    def _build_file_header(
        self, event_name: str, file_path: Path, metadata_list: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """构建文件头字符串（支持多个元数据）."""
        header = f"""{'=' * 80}
事件日志文件 - {event_name}
{'=' * 80}
事件名称: {event_name}
开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
文件路径: {file_path}
日志级别: DEBUG及以上所有级别
"""
        if metadata_list:
            header += "\n事件元数据:\n"
            for idx, metadata in enumerate(metadata_list, 1):
                if len(metadata_list) > 1:
                    header += f"\n  [元数据 {idx}]\n"
                for key, value in metadata.items():
                    header += f"  - {key}: {value}\n"

        header += f"\n{'=' * 80}\n\n"
        return header

    def _build_metadata_section(self, metadata: Dict[str, Any], is_additional: bool = False) -> str:
        """构建元数据部分字符串（用于追加到现有文件）."""
        section = f"\n{'=' * 80}\n"
        if is_additional:
            section += f"追加元数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            section += f"{'=' * 80}\n"
        section += "\n事件元数据:\n"
        for key, value in metadata.items():
            section += f"  - {key}: {value}\n"
        section += f"\n{'=' * 80}\n\n"
        return section

    def end_event(self, success: bool = True, summary: Optional[str] = None):
        """结束事件日志（使用引用计数，只有引用计数为0时才真正结束）."""
        with self._lock:
            if not self._current_event_file_path or not self._current_event:
                return

            event_name = self._current_event

            # 减少引用计数
            if event_name in self._event_ref_count:
                self._event_ref_count[event_name] -= 1
                if self._event_ref_count[event_name] <= 0:
                    # 引用计数为0，真正结束事件
                    del self._event_ref_count[event_name]
                    if event_name in self._event_metadata:
                        del self._event_metadata[event_name]

                    footer = f"""
{'=' * 80}
事件结束 - {event_name}
{'=' * 80}
结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
执行结果: {'成功' if success else '失败'}
"""
                    if summary:
                        footer += f"\n执行摘要:\n{summary}\n"

                    # 显示各级别日志统计
                    footer += f"\n日志统计:\n"
                    footer += f"  - 总日志条数: {self._total_logs}\n"
                    footer += f"  - DEBUG: {self._level_counts['DEBUG']} 条\n"
                    footer += f"  - INFO: {self._level_counts['INFO']} 条\n"
                    footer += f"  - WARNING: {self._level_counts['WARNING']} 条\n"
                    footer += f"  - ERROR: {self._level_counts['ERROR']} 条\n"
                    footer += f"  - CRITICAL: {self._level_counts['CRITICAL']} 条\n"
                    footer += f"\n{'=' * 80}\n"

                    if self._current_event_file:
                        self._current_event_file.write(footer)
                        self._current_event_file.flush()

                    self._close_current_event_file()
                else:
                    # 引用计数 > 0，只记录嵌套结束，不关闭文件
                    logger.debug(
                        f"[EventLogFileHandler] 嵌套事件结束: {event_name}, "
                        f"剩余引用计数: {self._event_ref_count[event_name]}"
                    )

    def _close_current_event_file(self):
        """关闭当前事件文件."""
        if self._current_event_file:
            try:
                self._current_event_file.flush()
                self._current_event_file.close()
            except Exception:
                pass
            finally:
                self._current_event_file = None
                self._current_event_file_path = None
                self._current_event = None

    def emit(self, record: logging.LogRecord):
        """处理日志记录."""
        with self._lock:
            try:
                # 统计日志级别
                level_name = logging.getLevelName(record.levelno)
                if level_name in self._level_counts:
                    self._level_counts[level_name] += 1

                # 格式化日志消息
                level_markers = {
                    logging.DEBUG: "🔍",
                    logging.INFO: "ℹ️",
                    logging.WARNING: "⚠️",
                    logging.ERROR: "❌",
                    logging.CRITICAL: "🔥",
                }
                marker = level_markers.get(record.levelno, "")
                msg = self.format(record)

                # 为WARNING及以上级别添加分隔线
                if record.levelno >= logging.WARNING:
                    msg = f"\n{'─' * 80}\n{marker} {msg}\n{'─' * 80}"
                else:
                    msg = f"{marker} {msg}"

                # 异常信息特殊处理
                if record.exc_info:
                    import traceback

                    exc_text = "".join(traceback.format_exception(*record.exc_info))
                    msg += f"\n\n异常堆栈跟踪:\n{exc_text}\n{'═' * 80}"
                elif hasattr(record, "exc_text") and record.exc_text:
                    msg += f"\n\n异常堆栈跟踪:\n{record.exc_text}\n{'═' * 80}"

                message_with_newline = msg + "\n"

                # 写入当前事件日志文件（如果存在）
                if self._current_event_file:
                    try:
                        self._current_event_file.write(message_with_newline)
                        self._current_event_file.flush()
                    except Exception:
                        # 静默处理，避免污染terminal输出
                        pass
                # 如果_current_event_file为None，静默处理

                self._total_logs += 1
            except Exception:
                # 静默处理，避免污染terminal输出
                pass
                # 原有的错误处理（可能会造成递归）
                # logger.error(f"[EventLogFileHandler] 日志写入失败: {e}", exc_info=True)

    def get_current_event_file_path(self) -> Optional[Path]:
        """获取当前事件日志文件路径."""
        with self._lock:
            return self._current_event_file_path

    def get_current_event(self) -> Optional[str]:
        """获取当前活动的事件名称."""
        with self._lock:
            return self._current_event

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._lock:
            return {
                "event_count": self._event_count,
                "total_logs": self._total_logs,
                "level_counts": self._level_counts.copy(),
                "current_event": self._current_event,
                "current_event_file": str(self._current_event_file_path) if self._current_event_file_path else None,
            }

    def close(self):
        """关闭Handler."""
        with self._lock:
            self._close_current_event_file()
        super().close()


# =============================================================================
# Part 8: LoggingHub核心类（简化路由规则）
# =============================================================================


class LoggingHub(logging.Handler):
    """统一日志中心（拦截所有日志并按简化的硬编码规则分发）."""

    @contextmanager
    def log_context(self, **context):
        """日志上下文管理器，用于在代码块中添加上下文信息到日志记录中。
        
        Args:
            **context: 要添加到日志记录中的上下文信息，如 request_id, user_id, component 等
            
        Example:
            with logging_hub.log_context(request_id=request_id, user_id=user_id):
                logger.info("Processing request")
        """
        # 获取当前线程的上下文变量
        current_context = getattr(threading.current_thread(), '_log_context', {})
        
        # 更新上下文
        new_context = {**current_context, **context}
        
        # 设置新的上下文
        thread = threading.current_thread()
        original_context = getattr(thread, '_log_context', {})
        thread._log_context = new_context
        
        try:
            yield
        finally:
            # 恢复原始上下文
            thread._log_context = original_context
    
    def _get_current_context(self):
        """获取当前线程的日志上下文"""
        return getattr(threading.current_thread(), '_log_context', {})
    
    def __init__(self):
        """初始化LoggingHub."""
        super().__init__()
        self.setLevel(logging.DEBUG)

        # 外部依赖
        self.event_engine: Optional[EventEngine] = None
        self.db_manager: Optional[Any] = None

        # 托管Handler
        self._console_handler: Optional[logging.StreamHandler] = None
        self._event_log_handler: Optional["EventLogFileHandler"] = None

        # 节流器
        self._throttler = ProgressThrottler(interval_ms=500)

        # 有序日志队列（terminal和数据库输出使用）
        self._ordered_log_queue: Optional["OrderedLogQueue"] = None
        self._ordered_queue_enabled = False
        self._sequence_counter = 0
        self._sequence_lock = Lock()
        self._emit_lock = RLock()
        
        # 批量处理相关
        self._batch_buffer: List[UnifiedLogRecord] = []
        self._batch_size = 100  # 每100条批量处理一次
        self._batch_lock = threading.Lock()
        self._last_flush = time.time()
        self._flush_interval = 1.0  # 最多1秒刷新一次
        self._batch_processor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LogBatchProcessor")

        # 统计
        self._total_logs = 0
        self._throttled_logs = 0
        self._db_writes = 0
        self._console_writes = 0
        self._file_writes = 0

        # 递归检测
        self._in_emit = False

        # 数据库批量写入
        self._db_batch_cache: List[Dict] = []
        self._db_batch_size = 10
        self._db_last_flush = time.time()
        self._db_flush_interval = 5.0

        # 当前阶段（用于判断是否在启动阶段）
        self._current_stage = "startup"
        self._startup_stages = {
            "startup",
            "logging_init",
            "qt_init",
            "backend_init",
            "ui_init",
            "vnpy_core",
            "cache_validation_step1",
            "cache_validation_step2",
            "cache_validation_step3",
            "cache_validation_step4",
            "cache_validation_step5",
            "cache_validation_step6",
            "cache_validation_step7",
            "cache_validation_step8",
        }

        # 🚀 性能优化：使用native HighPerfLRUCache替代@lru_cache装饰器
        # 日志类型分类缓存（最大1000项，与原来的@lru_cache(maxsize=1000)一致）
        # 如果native不可用，使用Python标准库的functools.lru_cache作为降级方案
        if NATIVE_COLLECTIONS_AVAILABLE and HighPerfLRUCache is not None:
            self._log_type_cache: Any = HighPerfLRUCache(1000)  # type: ignore
            self._use_native_cache = True
        else:
            # 降级方案：使用简单的字典缓存（带大小限制）
            from functools import lru_cache
            # 创建一个简单的LRU缓存包装器
            class SimpleLRUCache:
                def __init__(self, maxsize: int):
                    self._cache: Dict[Any, Any] = {}
                    self._maxsize = maxsize
                    self._access_order: List[Any] = []

                def get(self, key: Any) -> Optional[Any]:
                    if key in self._cache:
                        # 更新访问顺序
                        if key in self._access_order:
                            self._access_order.remove(key)
                        self._access_order.append(key)
                        return self._cache[key]
                    return None

                def set(self, key: Any, value: Any):
                    # 如果超过最大大小，删除最旧的项
                    if len(self._cache) >= self._maxsize and key not in self._cache:
                        if self._access_order:
                            oldest_key = self._access_order.pop(0)
                            self._cache.pop(oldest_key, None)
                    self._cache[key] = value
                    if key in self._access_order:
                        self._access_order.remove(key)
                    self._access_order.append(key)

            self._log_type_cache = SimpleLRUCache(1000)
            self._use_native_cache = False
            logger.warning(
                "HighPerfLRUCache不可用，使用降级缓存方案",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

    def set_event_engine(self, event_engine: EventEngine):
        """注入EventEngine."""
        self.event_engine = event_engine

    def set_db_manager(self, db_manager: Any):
        """注入数据库管理器."""
        self.db_manager = db_manager

    def set_console_handler(self, handler: logging.StreamHandler):
        """注入控制台Handler."""
        self._console_handler = handler

    def set_event_log_handler(self, handler: "EventLogFileHandler"):
        """注入事件日志Handler."""
        self._event_log_handler = handler

    def set_ordered_log_queue(self, ordered_queue: "OrderedLogQueue"):
        """设置有序日志队列（terminal和数据库输出使用）

        Args:
            ordered_queue: OrderedLogQueue实例
        """
        self._ordered_log_queue = ordered_queue
        if ordered_queue:
            ordered_queue.set_output_callback(self._output_ordered_log)

    def enable_ordered_queue(self):
        """启用有序队列（启动阶段使用）"""
        with self._sequence_lock:
            self._ordered_queue_enabled = True
            logger.debug("有序队列已启用")

    def disable_ordered_queue(self):
        """禁用有序队列（正常运行阶段）"""
        with self._sequence_lock:
            self._ordered_queue_enabled = False
            logger.debug("有序队列已禁用")

    def set_stage(self, stage: str):
        """切换日志阶段."""
        self._current_stage = stage

    def get_current_stage(self) -> str:
        """获取当前阶段."""
        return self._current_stage

    def _is_startup_phase(self) -> bool:
        """判断是否处于启动阶段

        Returns:
            bool: 是否处于启动阶段
        """
        return self._current_stage in self._startup_stages

    def emit(self, record: logging.LogRecord) -> None:
        """拦截日志输出."""
        # 添加上下文信息
        context = self._get_current_context()
        if context:
            for key, value in context.items():
                if not hasattr(record, key):
                    setattr(record, key, value)
        
        emit_start = time.perf_counter()
        try:
            if self._in_emit:
                return

            if hasattr(record, "_unified_hub_processed"):
                return

            self._in_emit = True
            setattr(record, "_unified_hub_processed", True)

            if self._should_skip(record):
                return

            self._total_logs += 1
            unified_record = self._convert_to_unified(record)
            targets = self._get_targets(unified_record)
            
            # 检查是否需要批量处理
            if self._should_batch_process(record):
                self._add_to_batch(unified_record, targets)
            else:
                # 直接处理高优先级日志
                self._dispatch(targets, unified_record)
                
            self._check_throttler()
            self._maybe_flush_batch()

        except RecursionError as e:
            # 使用print直接输出到stderr，避免触发日志系统导致递归
            import sys
            import traceback
            print(f"[LoggingHub] ❌ 日志处理递归错误: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        except Exception as e:
            # 使用print直接输出到stderr，避免触发日志系统导致递归
            import sys
            import traceback
            print(f"[LoggingHub] ❌ 日志处理异常: {e}, logger={record.name}, level={record.levelno}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        finally:
            self._in_emit = False
            
    def _should_batch_process(self, record: logging.LogRecord) -> bool:
        """判断是否应该批量处理日志"""
        # 高优先级的日志（如ERROR、CRITICAL）立即处理
        if record.levelno >= logging.ERROR:
            return False
            
        # 检查是否在启动阶段
        if self._is_startup_phase():
            return False
            
        # 检查日志类型
        log_type = getattr(record, 'log_type', '')
        if log_type in ['ALERT', 'NOTIFICATION']:
            return False
            
        return True
        
    def _add_to_batch(self, record, targets):
        """将日志添加到批量处理队列"""
        with self._batch_lock:
            self._batch_buffer.append((record, targets))
            
            # 检查是否达到批量大小或超时
            current_time = time.time()
            if (len(self._batch_buffer) >= self._batch_size or 
                (current_time - self._last_flush) >= self._flush_interval):
                self._flush_batch()
                self._last_flush = current_time
                
    def _maybe_flush_batch(self):
        """检查是否需要刷新批量日志"""
        with self._batch_lock:
            current_time = time.time()
            if self._batch_buffer and (current_time - self._last_flush) >= self._flush_interval:
                self._flush_batch()
                self._last_flush = current_time
    
    def _flush_batch(self):
        """处理批量日志"""
        if not self._batch_buffer:
            return
            
        # 获取当前批次的日志
        with self._batch_lock:
            batch = self._batch_buffer
            self._batch_buffer = []
            
        if not batch:
            return
            
        # 按目标分组
        target_records = {}
        for record, targets in batch:
            for target in targets:
                if target not in target_records:
                    target_records[target] = []
                target_records[target].append(record)
        
        # 批量处理每个目标
        for target, records in target_records.items():
            if not records:
                continue
                
            try:
                if target == 'console':
                    for record in records:
                        self._to_console(record)
                elif target == 'file' and self._event_log_handler:
                    self._batch_to_file(records)
                elif target == 'database':
                    self._batch_to_database(records)
                elif target == 'event':
                    for record in records:
                        self._to_event(record)
                elif target == 'event_throttled':
                    for record in records:
                        self._to_event_throttled(record)
            except Exception as e:
                import sys
                print(f"批量处理日志到 {target} 失败: {e}", file=sys.stderr)
                
    def _batch_to_file(self, records):
        """批量写入文件"""
        if not self._event_log_handler:
            return
            
        try:
            for record in records:
                self._to_file(record)
        except Exception as e:
            import sys
            print(f"批量写入文件失败: {e}", file=sys.stderr)
            
    def _batch_to_database(self, records):
        """批量写入数据库"""
        if not self.db_manager or not records:
            return
            
        try:
            # 转换为数据库记录
            db_records = []
            for record in records:
                db_record = {
                    'timestamp': record.timestamp,
                    'level': record.levelname,
                    'logger': record.logger_name,
                    'message': record.message,
                    'process': getattr(record, 'process_name', None),
                    'pid': getattr(record, 'pid', None),
                    'hostname': getattr(record, 'hostname', None),
                    'extra': json.dumps(record.extra) if hasattr(record, 'extra') and record.extra else None
                }
                db_records.append(db_record)
                
            # 批量插入数据库
            if db_records:
                self.db_manager.bulk_insert('logs', db_records)
                self._db_writes += len(db_records)
                
        except Exception as e:
            import sys
            import traceback
            print(f"批量写入数据库失败: {e}", file=sys.stderr)
            traceback.print_exc()

    def _should_skip(self, record: logging.LogRecord) -> bool:
        """判断是否应跳过.

        注意：此方法仅用于防止无限递归和过滤系统内部日志，
        不应该在这里过滤业务日志！业务日志的过滤应该由路由规则控制。
        """
        # 防止日志系统自身的日志造成无限递归
        if record.name.startswith("backend.infrastructure.system_vnpy.logging_system"):
            return True
        if "log_manager" in record.name.lower():
            return True

        return False

    def _convert_to_unified(self, record: logging.LogRecord) -> UnifiedLogRecord:
        """转换为UnifiedLogRecord."""
        exception_text = ""
        if record.exc_info:
            import traceback

            exception_text = "".join(traceback.format_exception(*record.exc_info))

        log_type = self._classify_log_type(record)
        details: Dict[str, Any] = {}
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in _EXCLUDED_FIELDS:
                    details[key] = value

        # 自动补充场景信息（仅在未显式提供时）
        if not details.get("scenario"):
            inferred_scenario = _infer_scenario_from_logger(record.name)
            if inferred_scenario:
                details["scenario"] = inferred_scenario

        details_payload = details if details else None

        return UnifiedLogRecord(
            type=log_type,
            level=record.levelno,
            module=record.module,
            message=record.getMessage(),
            details=details_payload,
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

    def _classify_log_type_cached(
        self,
        logger_name_lower: str,
        message_lower: str,
        levelno: int,
        log_type_attr_str: Optional[str],
    ) -> LogType:
        """缓存的日志类型分类（辅助方法）.

        🚀 性能优化：使用native HighPerfLRUCache替代@lru_cache装饰器
        """
        # 生成缓存键
        cache_key = (logger_name_lower, message_lower, levelno, log_type_attr_str)

        # 从缓存获取
        # 🔧 修复：HighPerfLRUCache.get()在键不存在时会抛出KeyError，而不是返回None
        try:
            cached_result = self._log_type_cache.get(cache_key)  # type: ignore
            if cached_result is not None:
                return cached_result
        except KeyError:
            # 键不存在，继续计算
            pass

        # 计算日志类型
        result = self._classify_log_type_impl(
            logger_name_lower, message_lower, levelno, log_type_attr_str
        )

        # 存入缓存
        self._log_type_cache.set(cache_key, result)  # type: ignore

        return result

    def _classify_log_type_impl(
        self,
        logger_name_lower: str,
        message_lower: str,
        levelno: int,
        log_type_attr_str: Optional[str],
    ) -> LogType:
        """日志类型分类实现（无缓存）."""
        # 优先检查extra参数中的log_type（显式指定）
        if log_type_attr_str:
            try:
                log_type_str = log_type_attr_str.upper()
                if log_type_str == "STAGE_NODE":
                    return LogType.STAGE_NODE
                elif log_type_str == "PROGRESS":
                    return LogType.PROGRESS
                elif log_type_str == "NOTIFICATION":
                    return LogType.NOTIFICATION
                elif log_type_str == "ALERT":
                    return LogType.ALERT
                elif log_type_str == "USER_FEEDBACK":
                    return LogType.USER_FEEDBACK
                elif log_type_str == "DEBUG":
                    return LogType.DEBUG
                elif log_type_str == "SYSTEM":
                    return LogType.SYSTEM
            except Exception:
                pass
                
        # 增强错误和异常检测
        error_keywords = [
            "error", "exception", "failed", "failure", "error occurred",
            "unhandled exception", "traceback", "crash", "fatal", "critical",
            "unexpected error", "operation failed", "unable to", "could not",
            "failed to", "unable to process", "processing failed", "invalid",
            "not found", "timeout", "timed out", "connection lost", "disconnected"
        ]
        if any(word in message_lower for word in error_keywords):
            return LogType.ALERT if levelno >= logging.ERROR else LogType.SYSTEM

        # 增强警告检测
        warning_keywords = [
            "warning", "warn", "caution", "attention", "notice",
            "deprecated", "deprecation", "obsolete", "legacy", "outdated",
            "retry", "retrying", "fallback", "falling back", "slow", "performance"
        ]
        if any(word in message_lower for word in warning_keywords):
            return LogType.ALERT if levelno >= logging.WARNING else LogType.SYSTEM

        # 增强进度检测
        progress_keywords = [
            "progress", "processing", "handling", "loading", "saving",
            "downloading", "uploading", "exporting", "importing", "generating",
            "calculating", "analyzing", "validating", "initializing", "starting",
            "stopping", "restarting", "updating", "refreshing", "synchronizing"
        ]
        progress_indicators = ["%", "complete", "done", "finish", "completed", "success"]
        if any(word in message_lower for word in progress_keywords):
            if any(word in message_lower for word in progress_indicators):
                return LogType.PROGRESS

        # 增强阶段节点检测
        stage_keywords = ["stage", "phase", "step", "task", "job", "process", "workflow"]
        stage_indicators = ["start", "begin", "end", "complete", "finish", "initializing", "finalizing"]
        if any(word in message_lower for word in stage_indicators):
            if any(word in message_lower for word in stage_keywords):
                return LogType.STAGE_NODE

        # 增强通知检测
        notification_keywords = [
            "notify", "notification", "alert", "notice", "info", "information",
            "message", "announcement", "update", "status", "summary", "report",
            "success", "completed", "finished", "ready", "available", "done"
        ]
        if any(word in message_lower for word in notification_keywords):
            return LogType.NOTIFICATION

        # 流程节点：阶段日志器优先处理
        # 规则：阶段日志器的WARNING/ERROR/CRITICAL升级为ALERT；否则为STAGE_NODE
        if ".stage" in logger_name_lower:
            if levelno >= logging.WARNING:
                return LogType.ALERT
            return LogType.STAGE_NODE

        if levelno == logging.INFO:
            stage_identifiers = ["📍", "阶段", "流程", "步骤", "stage", "phase", "step"]
            status_words = [
                "开始",
                "完成",
                "结束",
                "启动",
                "进入",
                "start",
                "complete",
                "finish",
                "end",
            ]
            has_stage_id = any(word in message_lower for word in stage_identifiers)
            has_status = any(word in message_lower for word in status_words)
            if (
                has_stage_id
                and has_status
                and "%" not in message_lower
                and "进度" not in message_lower
            ):
                return LogType.STAGE_NODE

        # 告警
        if "alert" in logger_name_lower or "monitor" in logger_name_lower:
            if levelno >= logging.WARNING:
                return LogType.ALERT

        # 基于内容的告警标记（强标记，直接判定为ALERT）
        # 注意：这些标记通常用于UI或系统关键故障提示
        strong_alert_markers = [
            "❌",
            "🔥",
            "⚠️",
            "崩溃",
            "宕机",
            "致命",
            "fatal",
            "panic",
            "超时",
            "卡死",
            "不可恢复",
            "数据损坏",
        ]
        if any(marker in message_lower for marker in strong_alert_markers):
            return LogType.ALERT

        # 基于内容的弱告警标记：仅当等级达到WARNING及以上才提升为ALERT
        weak_alert_markers = [
            "失败",
            "异常",
            "错误",
            "严重",
            "warning",
            "error",
            "exception",
            "fail",
        ]
        if levelno >= logging.WARNING:
            if any(marker in message_lower for marker in weak_alert_markers):
                return LogType.ALERT

        # 进度
        if "download" in logger_name_lower or "progress" in logger_name_lower:
            if "进度" in message_lower or "%" in message_lower or "progress" in message_lower:
                return LogType.PROGRESS

        if "quality" in logger_name_lower or "scan" in logger_name_lower:
            if "扫描" in message_lower or "%" in message_lower:
                return LogType.PROGRESS

        # 通知（严格）
        if levelno == logging.INFO:
            notification_markers = [
                "✅ 任务完成",
                "✅ 下载完成",
                "✅ 扫描完成",
                "✅ 验证完成",
                "download completed",
                "scan completed",
                "task completed",
            ]
            is_notification_logger = (
                "notification" in logger_name_lower or "notifier" in logger_name_lower
            )
            import re

            task_completion_pattern = re.compile(
                r"(完成|已完成|finished|completed)\s*\d+\s*(个|项|条|次)", re.IGNORECASE
            )
            has_completion_report = task_completion_pattern.search(message_lower) is not None

            if (
                is_notification_logger
                or has_completion_report
                or any(marker in message_lower for marker in notification_markers)
            ):
                return LogType.NOTIFICATION

        # DEBUG
        if levelno == logging.DEBUG:
            return LogType.DEBUG

        return LogType.SYSTEM

    def _classify_log_type(self, record: logging.LogRecord) -> LogType:
        """根据logger名称和消息判断日志类型."""
        # 优先检查extra参数中的log_type（显式指定）
        log_type_attr = getattr(record, "log_type", None)
        log_type_attr_str = None
        if log_type_attr is not None:
            if isinstance(log_type_attr, LogType):
                return log_type_attr
            elif isinstance(log_type_attr, str):
                log_type_attr_str = log_type_attr

        logger_name = record.name.lower()
        message = record.getMessage().lower()

        # 使用缓存的分类方法
        return self._classify_log_type_cached(
            logger_name, message, record.levelno, log_type_attr_str
        )

    def _get_targets(self, record: UnifiedLogRecord) -> List[str]:
        """获取路由目标（优化版）

        路由规则（优化后）：
        - 文件输出：所有日志都写入文件（全量）
        - 控制台输出：WARNING/ERROR/CRITICAL + STAGE_NODE.INFO + ALERT + 自定义规则
        - 数据库输出：与控制台一致，或根据自定义规则
        - 事件引擎：NOTIFICATION和ALERT类型（用于内部通知）
        - 节流事件：PROGRESS类型（500ms聚合）
        
        动态路由规则：
        1. 支持通过 extra 参数动态指定目标
        2. 支持通过日志级别、类型、来源等条件进行路由
        3. 支持自定义路由规则
        """
        # 使用集合自动去重
        targets = {"file"}
        
        # 1. 检查是否有显式指定的目标
        if hasattr(record, 'targets') and isinstance(record.targets, (list, tuple, set)):
            targets.update(record.targets)
            return list(targets)
            
        # 2. 应用内置路由规则
        
        # 控制台和数据库输出条件
        needs_console = (
            record.level >= logging.WARNING or  # WARNING及以上级别
            record.type in (LogType.ALERT, LogType.NOTIFICATION) or  # 告警和通知类型
            (record.type == LogType.STAGE_NODE and record.level == logging.INFO) or  # 阶段节点信息
            (record.level == logging.INFO and hasattr(record, 'show_in_console') and record.show_in_console)  # 显式指定显示在控制台
        )

        # 数据库输出条件（可以单独控制）
        needs_database = (
            needs_console or  # 默认与控制台一致
            (hasattr(record, 'save_to_database') and record.save_to_database)  # 显式指定保存到数据库
        )

        # 添加控制台和数据库目标
        if needs_console:
            targets.add("console")
        if needs_database and self.db_manager is not None:  # 只有在数据库管理器可用时才添加数据库目标
            targets.add("database")

        # 事件引擎：NOTIFICATION和ALERT类型
        if record.type in (LogType.NOTIFICATION, LogType.ALERT):
            targets.add("event")

        # 节流事件：PROGRESS类型
        if record.type == LogType.PROGRESS:
            targets.add("event_throttled")
            
        # 3. 应用自定义路由规则
        if hasattr(self, '_custom_routing_rules') and self._custom_routing_rules:
            for rule in self._custom_routing_rules:
                if self._match_rule(rule, record):
                    targets.update(rule.get('targets', []))

        # 4. 调试模式：所有DEBUG日志输出到控制台
        if record.level == logging.DEBUG and getattr(self, "debug_mode", False):
            targets.add("console")

        return list(targets)
        
    def _match_rule(self, rule: Dict, record: UnifiedLogRecord) -> bool:
        """检查日志记录是否匹配自定义路由规则"""
        # 检查日志级别
        if 'min_level' in rule and record.levelno < getattr(logging, rule['min_level']):
            return False
            
        # 检查日志类型
        if 'log_types' in rule and record.type.name not in rule['log_types']:
            return False
            
        # 检查记录器名称模式
        if 'logger_patterns' in rule:
            if not any(pattern in record.name for pattern in rule['logger_patterns']):
                return False
                
        # 检查消息内容模式
        if 'message_patterns' in rule:
            message = record.getMessage().lower()
            if not any(pattern.lower() in message for pattern in rule['message_patterns']):
                return False
                
        return True
        
    def add_routing_rule(self, rule: Dict) -> None:
        """添加自定义路由规则
        
        Args:
            rule: 路由规则字典，包含以下可选键：
                - targets: 目标列表，如 ["console", "database", "event"]
                - min_level: 最小日志级别（如 "WARNING"）
                - log_types: 日志类型列表，如 ["ALERT", "NOTIFICATION"]
                - logger_patterns: 记录器名称模式列表，如 ["backend.services", "data_module"]
                - message_patterns: 消息内容模式列表，如 ["error", "failed"]
        """
        if not hasattr(self, '_custom_routing_rules'):
            self._custom_routing_rules = []
            
        if 'targets' not in rule or not rule['targets']:
            raise ValueError("路由规则必须包含 'targets' 字段")
            
        self._custom_routing_rules.append(rule)

    def _dispatch(self, targets: List[str], record: UnifiedLogRecord):
        """分发日志."""
        # 🔧 修复：文件输出应该始终直接处理，不经过有序队列
        # 文件输出直接处理（所有日志都写入文件，不等待有序队列）
        if "file" in targets:
            try:
                self._to_file(record)
            except Exception as e:
                # 文件输出失败时，静默处理，避免污染terminal输出
                import sys
                print(f"[LoggingHub] 文件输出失败: {e}", file=sys.stderr)

        # 如果启用了有序队列，且目标是console或database，添加到有序队列
        if self._ordered_queue_enabled and self._ordered_log_queue is not None:
            needs_ordered_output = any(target in ("console", "database") for target in targets)
            if needs_ordered_output:
                with self._sequence_lock:
                    sequence = self._sequence_counter
                    self._sequence_counter += 1
                self._ordered_log_queue.add_log(record, sequence)
                # 对于其他目标（event等），直接处理（不经过有序队列）
                for target in targets:
                    if target not in ("console", "database", "file"):
                        try:
                            if target == "event":
                                self._to_event(record)
                            elif target == "event_throttled":
                                self._to_event_throttled(record)
                        except Exception:
                            pass
                return  # 已处理，直接返回
            else:
                # 如果没有需要有序输出的目标，但启用了有序队列，仍然需要处理event等目标
                for target in targets:
                    if target not in ("file",):  # file已经处理过了
                        try:
                            if target == "event":
                                self._to_event(record)
                            elif target == "event_throttled":
                                self._to_event_throttled(record)
                        except Exception:
                            pass
                return  # 已处理，直接返回

        # 未启用有序队列，直接分发
        for target in targets:
            try:
                if target == "console":
                    self._to_console(record)
                elif target == "file":
                    self._to_file(record)
                elif target == "database":
                    self._to_database_batched(record)
                elif target == "event":
                    self._to_event(record)
                elif target == "event_throttled":
                    self._to_event_throttled(record)
            except Exception:
                pass

    def _output_ordered_log(self, record: UnifiedLogRecord):
        """输出有序日志（回调函数）

        Args:
            record: UnifiedLogRecord实例
        """
        # 🔧 注意：文件输出已经在_dispatch中直接处理，这里不再重复处理
        # 有序队列只负责console和database的输出顺序

        # 根据路由目标输出（console和database）
        if record.level >= logging.WARNING or (
            record.type == LogType.STAGE_NODE and record.level == logging.INFO
        ):
            # Terminal输出
            self._to_console_direct(record)
            # 数据库输出
            self._to_database_batched(record)

    def _to_console(self, record: UnifiedLogRecord):
        """输出到控制台（Terminal）- 简洁输出

        核心原则：Terminal只显示关键信息，不影响日志文件。
        输出规则：
          1. WARNING及以上级别的日志（WARNING, ERROR, CRITICAL）
          2. STAGE_NODE.INFO（阶段节点）
        """
        if not self._console_handler:
            return

        # 启动阶段：使用有序队列确保日志按顺序输出
        if self._ordered_queue_enabled and self._is_startup_phase():
            ordered_queue = self._ordered_log_queue
            if ordered_queue is not None:
                with self._sequence_lock:
                    sequence = self._sequence_counter
                    self._sequence_counter += 1
                ordered_queue.add_log(record, sequence)
                return
        else:
            # 非启动阶段：直接输出
            self._to_console_direct(record)

    def _to_console_direct(self, record: UnifiedLogRecord):
        """直接输出到控制台（不经过有序队列）

        Args:
            record: UnifiedLogRecord实例
        """
        if not self._console_handler:
            return

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
        self._console_handler.emit(log_record)
        self._console_writes += 1

    def _to_file(self, record: UnifiedLogRecord):
        """输出到文件（通过EventLogFileHandler）"""
        if not self._event_log_handler:
            return

        # 🔧 验证EventLogFileHandler是否有当前事件文件
        if not hasattr(self._event_log_handler, '_current_event_file') or not self._event_log_handler._current_event_file:
            # 如果当前事件文件不存在，尝试重新启动事件
            try:
                current_event = self._event_log_handler.get_current_event()
                if not current_event:
                    # 事件未启动，尝试启动默认事件
                    try:
                        from backend.infrastructure.system_vnpy.logging_system import start_event_process
                        start_event_process("application_startup")
                    except Exception:
                        pass  # 静默处理，避免污染terminal输出
            except Exception:
                pass  # 静默处理，避免污染terminal输出

        # 🔧 修复：直接调用EventLogFileHandler的emit方法，但需要标记记录已处理，避免被LoggingHub再次处理
        # 创建LogRecord并通过EventLogFileHandler写入
        exc_info = None
        if record.exception:
            exc_info = None  # 保持None，但设置exc_text

        log_record = logging.LogRecord(
            name=record.logger_name,
            level=record.level,
            pathname=record.filename,
            lineno=record.line,
            msg=record.message,
            args=(),
            exc_info=exc_info,
        )
        log_record.created = record.timestamp.timestamp()
        log_record.funcName = record.function

        if record.exception:
            log_record.exc_text = record.exception

        # 🔧 关键修复：标记记录已处理，避免被LoggingHub再次处理（防止无限递归）
        setattr(log_record, "_unified_hub_processed", True)

        try:
            # 检查EventLogFileHandler的状态
            if not hasattr(self._event_log_handler, '_current_event_file'):
                return

            # 使用锁保护，检查_current_event_file状态
            with self._event_log_handler._lock:
                current_file = self._event_log_handler._current_event_file
                if current_file is None or current_file.closed:
                    return

            # 调用emit方法（emit方法内部会使用锁）
            # 🔧 注意：EventLogFileHandler.emit方法会检查_unified_hub_processed标记，如果存在则跳过
            # 但我们需要直接写入文件，所以需要绕过LoggingHub
            # 实际上，EventLogFileHandler不是LoggingHub的子类，所以不会触发LoggingHub
            self._event_log_handler.emit(log_record)
            self._file_writes += 1
        except Exception:
            # 静默处理，避免污染terminal输出
            pass

    def _to_database_batched(self, record: UnifiedLogRecord):
        """批量输出到数据库"""
        if not self.db_manager:
            return

        # 构造数据库记录
        db_record = {
            "timestamp": record.timestamp.isoformat(),
            "level": logging.getLevelName(record.level),
            "type": record.type.value,
            "module": record.module,
            "logger_name": record.logger_name,
            "message": record.message,
            "function": record.function,
            "line": record.line,
            "filename": record.filename,
            "thread": record.thread,
            "thread_name": record.thread_name,
            "exception": record.exception,
            "details": record.details,
        }

        self._db_batch_cache.append(db_record)
        self._db_writes += 1

    def _to_event(self, record: UnifiedLogRecord):
        """发送到EventEngine（NOTIFICATION和ALERT）"""
        if not self.event_engine:
            return

        if record.type == LogType.NOTIFICATION:
            event_type = EVENT_LOG_NOTIFICATION
        elif record.type == LogType.ALERT:
            event_type = EVENT_LOG_ALERT
        else:
            return

        event_data = {
            "timestamp": record.timestamp.isoformat(),
            "level": logging.getLevelName(record.level),
            "type": record.type.value,
            "module": record.module,
            "message": record.message,
            "details": record.details,
            "exception": record.exception,
        }
        event = Event(event_type, event_data)
        self.event_engine.put(event)

    def _to_event_throttled(self, record: UnifiedLogRecord):
        """发送节流事件（PROGRESS类型）"""
        if not self.event_engine or record.type != LogType.PROGRESS:
            return

        self._throttler.add(record)

    def _check_throttler(self):
        """检查节流器是否有可发送的记录"""
        if not self.event_engine:
            return

        throttled_record = self._throttler.get_if_ready()
        if throttled_record:
            event_data = {
                "timestamp": throttled_record.timestamp.isoformat(),
                "level": logging.getLevelName(throttled_record.level),
                "type": throttled_record.type.value,
                "module": throttled_record.module,
                "message": throttled_record.message,
                "details": throttled_record.details,
                "throttled_count": (
                    throttled_record.details.get("_throttled_count", 1)
                    if throttled_record.details
                    else 1
                ),
            }
            event = Event(EVENT_LOG_PROGRESS, event_data)
            self.event_engine.put(event)
            self._throttled_logs += 1

    def _maybe_flush_db_batch(self):
        """检查是否需要刷新数据库批量写入"""
        current_time = time.time()
        if (
            len(self._db_batch_cache) >= self._db_batch_size
            or current_time - self._db_last_flush >= self._db_flush_interval
        ):
            self._flush_db_batch()

    def _flush_db_batch(self):
        """刷新数据库批量写入"""
        if not self.db_manager or not self._db_batch_cache:
            return

        try:
            # 优先使用native序列化打包，减少Python层传递开销
            if NATIVE_SERIALIZATION_AVAILABLE and hasattr(self.db_manager, "batch_insert_logs_serialized"):
                try:
                    payload = zero_copy_serialize(self._db_batch_cache)  # type: ignore
                    self.db_manager.batch_insert_logs_serialized(payload)
                except Exception:
                    # native路径失败则回退普通批量
                    if hasattr(self.db_manager, "batch_insert_logs"):
                        self.db_manager.batch_insert_logs(self._db_batch_cache)
                    else:
                        for record in self._db_batch_cache:
                            if hasattr(self.db_manager, "insert_log"):
                                self.db_manager.insert_log(record)
            else:
                # 普通批量接口或逐条降级
                if hasattr(self.db_manager, "batch_insert_logs"):
                    self.db_manager.batch_insert_logs(self._db_batch_cache)
                else:
                    for record in self._db_batch_cache:
                        if hasattr(self.db_manager, "insert_log"):
                            self.db_manager.insert_log(record)

            self._db_batch_cache.clear()
            self._db_last_flush = time.time()
        except Exception as e:
            logger.error(f"数据库批量写入失败: {e}", exc_info=True)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息."""
        return {
            "total_logs": self._total_logs,
            "throttled_logs": self._throttled_logs,
            "console_writes": self._console_writes,
            "file_writes": self._file_writes,
            "db_writes": self._db_writes,
            "db_batch_pending": len(self._db_batch_cache),
            "current_stage": self._current_stage,
            "ordered_queue_enabled": self._ordered_queue_enabled,
        }

    def close(self):
        """关闭LoggingHub."""
        self._flush_db_batch()
        super().close()


# =============================================================================
# Part 9: 全局单例和便捷API
# =============================================================================


_hub_instance: Optional[LoggingHub] = None
_event_log_handler_instance: Optional[EventLogFileHandler] = None
_ordered_log_queue_instance: Optional[OrderedLogQueue] = None
_multi_process_collector_instance: Optional[MultiProcessLogCollector] = None


def get_logging_hub() -> LoggingHub:
    """获取LoggingHub全局单例."""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = LoggingHub()
    return _hub_instance


def get_event_log_handler() -> "EventLogFileHandler":
    """获取EventLogFileHandler全局单例."""
    global _event_log_handler_instance
    if _event_log_handler_instance is None:
        _event_log_handler_instance = EventLogFileHandler()
    return _event_log_handler_instance


def get_ordered_log_queue() -> "OrderedLogQueue":
    """获取OrderedLogQueue全局单例."""
    global _ordered_log_queue_instance
    if _ordered_log_queue_instance is None:
        _ordered_log_queue_instance = OrderedLogQueue()
    return _ordered_log_queue_instance


def get_multi_process_collector() -> Optional["MultiProcessLogCollector"]:
    """获取MultiProcessLogCollector实例."""
    return _multi_process_collector_instance


# =============================================================================
# Part 10: 事件日志上下文管理器和便捷API
# =============================================================================


@contextmanager
def event_log_process(event_name: str, metadata: Optional[Dict[str, Any]] = None):
    """事件日志流程上下文管理器

    Args:
        event_name: 事件名称（必须为SUPPORTED_EVENTS中的一个）
        metadata: 事件元数据（可选）
    """
    handler = get_event_log_handler()
    file_path = handler.start_event(event_name, metadata)

    success = False
    exception_info = None

    try:
        yield file_path
        success = True
    except Exception as e:
        exception_info = e
        raise
    finally:
        summary = None
        if not success and exception_info:
            summary = f"流程异常终止: {exception_info}"

        handler.end_event(success, summary)


def event_log_process_decorator(
    event_name: str, metadata_func: Optional[Callable[..., Dict[str, Any]]] = None
):
    """事件日志流程装饰器

    Args:
        event_name: 事件名称
        metadata_func: 元数据函数（可选）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            metadata = None
            if metadata_func:
                try:
                    metadata = metadata_func(*args, **kwargs)
                except Exception:
                    pass

            with event_log_process(event_name, metadata):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# =============================================================================
# Part 11: 便捷API函数
# =============================================================================


def log_progress(module: str, message: str, progress: float, **details):
    """记录进度日志（自动节流）."""
    payload = dict(details)
    scenario = payload.pop("scenario", None)
    logger = get_configured_logger(f"backend.{module}", log_type="PROGRESS", scenario=scenario)
    progress_log(
        message,
        logger=logger,
        scenario=scenario,
        progress=progress,
        extra=payload,
        stacklevel=3,
    )


def notify_complete(module: str, message: str, **details):
    """任务完成通知."""
    payload = dict(details)
    scenario = payload.pop("scenario", None)
    logger = get_configured_logger(f"backend.{module}", log_type="NOTIFICATION", scenario=scenario)
    logger.info(message, extra=payload or None, stacklevel=3)


def alert(severity: str, module: str, message: str, **details):
    """发送告警."""
    payload = dict(details)
    scenario = payload.pop("scenario", None)
    logger = get_configured_logger(f"backend.{module}", log_type="ALERT", scenario=scenario)
    level = getattr(logging, severity.upper(), logging.WARNING)
    alert_log(message, logger=logger, scenario=scenario, level=level, extra=payload, stacklevel=3)


def log_system(level: str, module: str, message: str, **details):
    """记录系统日志."""
    payload = dict(details)
    scenario = payload.pop("scenario", None)
    logger = get_configured_logger(f"backend.{module}", log_type="SYSTEM", scenario=scenario)
    log_level = getattr(logging, level.upper(), logging.INFO)
    extra = payload or None
    if extra is not None and scenario and "scenario" not in extra:
        extra["scenario"] = scenario
    logger.log(log_level, message, extra=extra, stacklevel=3)


def stage_node(module: str, message: str, **details):
    """记录阶段节点日志."""
    payload = dict(details)
    scenario = payload.pop("scenario", None)
    logger = get_configured_logger(f"backend.{module}", log_type="STAGE_NODE", scenario=scenario)
    stage_log(message, logger=logger, scenario=scenario, extra=payload, stacklevel=3)


def debug_log(module: str, message: str, **details):
    """记录调试日志."""
    payload = dict(details)
    scenario = payload.pop("scenario", None)
    logger = get_configured_logger(f"backend.{module}", log_type="DEBUG", scenario=scenario)
    extra = payload or None
    if extra is not None and scenario and "scenario" not in extra:
        extra["scenario"] = scenario
    logger.debug(message, extra=extra, stacklevel=3)


# =============================================================================
# Part 12: 初始化和配置函数
# =============================================================================


def setup_logging_system(
    event_engine: Optional[EventEngine] = None,
    db_manager: Optional[Any] = None,
    enable_ordered_queue: bool = True,
    enable_multi_process: bool = True,
) -> LoggingHub:
    """设置日志系统

    Args:
        event_engine: EventEngine实例
        db_manager: 数据库管理器
        enable_ordered_queue: 是否启用有序队列
        enable_multi_process: 是否启用多进程支持

    Returns:
        LoggingHub实例
    """
    hub = get_logging_hub()
    handler = get_event_log_handler()

    # 设置依赖
    if event_engine:
        hub.set_event_engine(event_engine)
    if db_manager:
        hub.set_db_manager(db_manager)

    # 设置Handler
    hub.set_event_log_handler(handler)

    # 设置有序队列
    if enable_ordered_queue:
        ordered_queue = get_ordered_log_queue()
        hub.set_ordered_log_queue(ordered_queue)
        hub.enable_ordered_queue()

    # 设置多进程收集器
    if enable_multi_process:
        global _multi_process_collector_instance
        collector = MultiProcessLogCollector(hub)
        collector.start()
        _multi_process_collector_instance = collector

    # 将LoggingHub添加到root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(hub)
    root_logger.setLevel(logging.DEBUG)

    logger.info("日志系统初始化完成")
    return hub


def start_event_process(event_name: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
    """开始事件日志流程

    Args:
        event_name: 事件名称
        metadata: 元数据

    Returns:
        事件日志文件路径
    """
    handler = get_event_log_handler()
    return handler.start_event(event_name, metadata)


def end_event_process(success: bool = True, summary: Optional[str] = None):
    """结束事件日志流程

    Args:
        success: 是否成功
        summary: 摘要信息
    """
    handler = get_event_log_handler()
    handler.end_event(success, summary)


# =============================================================================
# Part 14: 完整初始化函数（从logging_init.py迁移）
# =============================================================================


def setup_memory_logging() -> tuple[MemoryHandler, PersistentBufferHandler]:
    """设置MemoryHandler和PersistentBufferHandler缓冲日志系统初始化前的日志

    Returns:
        tuple[MemoryHandler, PersistentBufferHandler]: MemoryHandler和PersistentBufferHandler实例
    """
    import sys
    logger = logging.getLogger("backend.infrastructure.system_vnpy.logging_system")

    # DEBUG日志
    logger.debug(
        "[LOG-SETUP] 开始设置MemoryHandler",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    # 修复编码问题：确保stdout/stderr使用UTF-8编码
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
            logger.debug(
                "[LOG-SETUP] stdout已重新配置为UTF-8编码",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except (OSError, ValueError) as e:
            logger.debug(
                f"[LOG-SETUP] stdout重新配置失败: {e}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore
            logger.debug(
                "[LOG-SETUP] stderr已重新配置为UTF-8编码",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
        except (OSError, ValueError) as e:
            logger.debug(
                f"[LOG-SETUP] stderr重新配置失败: {e}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

    # 配置root logger
    root_logger = logging.getLogger()
    old_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)  # 接收所有级别的日志
    logger.debug(
        f"[LOG-SETUP] root logger级别已设置: {logging.getLevelName(old_level)} -> DEBUG",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    # 创建MemoryHandler作为临时缓冲（容量10000条）
    # target先设为None，LoggingHub初始化后再设置
    memory_handler = MemoryHandler(capacity=10000, target=None)
    memory_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(memory_handler)
    logger.debug(
        f"[LOG-SETUP] MemoryHandler已创建: 容量={memory_handler.capacity}条",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    # 创建持久化缓冲Handler（防止进程崩溃导致日志丢失）
    persistent_buffer = PersistentBufferHandler(buffer_dir="logs/buffer", capacity=10000)
    persistent_buffer.setLevel(logging.DEBUG)
    root_logger.addHandler(persistent_buffer)
    logger.debug(
        "[LOG-SETUP] PersistentBufferHandler已创建",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    # 创建启动logger
    from backend.core.base import setup_logging as base_setup_logging

    startup_logger = base_setup_logging(name="StartupOptimized", level="INFO")
    logger.debug(
        "[LOG-SETUP] 启动logger已创建",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    # 关键修复：移除logger自己的handlers，避免绕过LoggingHub
    removed_handlers_count = 0
    for handler in startup_logger.handlers[:]:
        startup_logger.removeHandler(handler)
        handler.close()
        removed_handlers_count += 1
    logger.debug(
        f"[LOG-SETUP] 已移除启动logger的{removed_handlers_count}个handlers",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    # 设置propagate=True，让日志传播到root logger，经过LoggingHub处理
    startup_logger.propagate = True
    logger.debug(
        "[LOG-SETUP] 启动logger已设置为传播到root logger",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    return memory_handler, persistent_buffer


async def initialize_logging_hub_complete(
    memory_handler: MemoryHandler,
    scenario: str = "application_startup",
) -> Optional[LoggingHub]:
    """完整初始化LoggingHub并重放缓冲日志

    Args:
        memory_handler: MemoryHandler实例
        scenario: 场景名称（默认：application_startup）

    Returns:
        LoggingHub实例或None
    """
    import sys
    logger = logging.getLogger("backend.infrastructure.system_vnpy.logging_system")

    try:
        root_logger = logging.getLogger()
        stage_logger = logging.getLogger("startup.stage")
        t0 = time.time()

        # 1. 初始化LoggingHub
        logger.debug(
            "[LOG-SETUP] 开始获取LoggingHub实例",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        logging_hub = get_logging_hub()
        logger.debug(
            "[LOG-SETUP] LoggingHub实例已获取",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 2. 创建并注入handlers
        logger.debug(
            "[LOG-SETUP] 开始创建并注入handlers",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)  # LoggingHub内部会根据规则过滤
        # 终端仅显示消息内容
        console_formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_formatter)
        logging_hub.set_console_handler(console_handler)
        logger.debug(
            "[LOG-SETUP] ConsoleHandler已创建并注入",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 注意：文件输出已通过EventLogFileHandler处理，无需单独设置file_handler
        logger.debug(
            "[LOG-SETUP] 文件输出已通过EventLogFileHandler处理",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 3. 获取事件日志Handler并注入到LoggingHub
        logger.debug(
            "[LOG-SETUP] 开始获取事件日志Handler",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        event_handler = get_event_log_handler()
        if not event_handler:
            logger.error(
                "[LOG-SETUP] ❌ EventLogFileHandler获取失败",
                extra={"log_type": "ALERT", "scenario": scenario}
            )
        else:
            logging_hub.set_event_log_handler(event_handler)
            # 🔧 验证注入是否成功
            if logging_hub._event_log_handler != event_handler:
                logger.error(
                    "[LOG-SETUP] ❌ EventLogFileHandler注入失败",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
            else:
                logger.debug(
                    "[LOG-SETUP] EventLogFileHandler已获取并注入",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )

        # 4. 启动事件日志流程（application_startup）
        logger.debug(
            "[LOG-SETUP] 开始启动事件日志流程",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        event_log_file = start_event_process(
            "application_startup",
            metadata={
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": sys.platform,
            },
        )
        logger.debug(
            f"[LOG-SETUP] 事件日志流程已启动: {event_log_file}",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 验证事件日志文件是否创建成功
        if not event_log_file or not event_log_file.exists():
            logger.warning(
                f"[LOG-SETUP] ⚠️ 事件日志文件创建失败: {event_log_file}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
        else:
            logger.debug(
                f"[LOG-SETUP] 事件日志文件已创建: {event_log_file.absolute()}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

        # 5. 集成多进程日志收集器
        logger.debug(
            "[LOG-SETUP] 开始创建多进程日志收集器",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        global _multi_process_collector_instance
        multiprocess_collector = MultiProcessLogCollector(logging_hub)
        multiprocess_collector.start()
        _multi_process_collector_instance = multiprocess_collector
        logger.debug(
            "[LOG-SETUP] 多进程日志收集器已启动",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 6. 集成有序日志队列（启动阶段）
        logger.debug(
            "[LOG-SETUP] 开始创建有序日志队列",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        ordered_queue = get_ordered_log_queue()
        logging_hub.set_ordered_log_queue(ordered_queue)
        logging_hub.enable_ordered_queue()
        logger.debug(
            f"[LOG-SETUP] 有序日志队列已创建并启用: 最大等待时间={ordered_queue.max_wait_seconds}秒",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        stage_logger.info(
            "✅ 有序日志队列初始化完成",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )

        # 7. 将LoggingHub添加到root logger
        root_logger.addHandler(logging_hub)
        logger.debug(
            "[LOG-SETUP] LoggingHub已添加到root logger",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 8. 设置MemoryHandler的target为LoggingHub
        memory_handler.setTarget(logging_hub)
        logger.debug(
            "[LOG-SETUP] MemoryHandler的target已设置为LoggingHub",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 9. 直接刷新MemoryHandler（重放启动前的日志）
        buffered_count = len(memory_handler.buffer)
        logger.debug(
            f"[LOG-SETUP] 开始刷新MemoryHandler: 已缓冲{buffered_count}条日志",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        memory_handler.flush()
        logger.debug(
            f"[LOG-SETUP] MemoryHandler已刷新: {buffered_count}条日志已重放",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 9. 移除MemoryHandler（已完成使命）
        root_logger.removeHandler(memory_handler)
        memory_handler.close()
        logger.debug(
            "[LOG-SETUP] MemoryHandler已移除并关闭",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 10. 全局清理：移除所有logger的StreamHandler，确保所有日志都经过LoggingHub
        logger.debug(
            "[LOG-SETUP] 开始全局清理logger handlers",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        cleaned_count = cleanup_all_logger_handlers()
        logger.debug(
            f"[LOG-SETUP] 全局清理完成: 已清理{cleaned_count}个handlers",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        # 11. 阶段1标题与分隔（此时LoggingHub已就绪）
        stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": scenario})
        stage_logger.info("【阶段1: 日志系统初始化】 (5-10%)", extra={"log_type": "STAGE_NODE", "scenario": scenario})
        stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": scenario})
        stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": scenario})

        # 添加阶段1开始标记
        stage_logger.info("📍 阶段1: 日志系统初始化开始", extra={"log_type": "STAGE_NODE", "scenario": scenario})

        # 使用logger输出（此时已经过LoggingHub）
        stage_logger.info(
            "✅ LoggingHub创建完成",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )

        # 注意：新架构使用硬编码路由规则，不再有路由引擎和配置文件
        stage_logger.info(
            "✅ 路由规则系统初始化完成（硬编码规则）",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )
        stage_logger.info(
            "   - 路由规则: 硬编码（简化架构）",
            extra={"log_type": "STAGE_NODE", "scenario": scenario},
        )

        # 事件日志Handler信息
        stage_logger.info(
            "✅ 事件日志Handler初始化完成",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )
        stage_logger.info(
            f"  - 基础目录: {Path('logs').absolute()}",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )

        # MemoryHandler日志重放信息
        stage_logger.info(
            f"✅ MemoryHandler日志重放完成 ({buffered_count}条)",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )

        # 有序日志队列信息（如果已启用）
        if ordered_queue:
            stage_logger.info(
                "✅ 有序日志队列已启用（启动阶段日志将按顺序输出）",
                extra={"log_type": "STAGE_NODE", "scenario": scenario},
            )

        # 初始化阶段完成耗时
        t_ms = int((time.time() - t0) * 1000)
        logger.info(
            f"[LOG-SETUP] 日志系统初始化完成: 总耗时={t_ms}ms",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        stage_logger.info(
            f"✅ 日志系统就绪 ({t_ms}ms)",
            extra={"log_type": "STAGE_NODE", "scenario": scenario}
        )

        # 设置初始阶段为startup
        logging_hub.set_stage("startup")
        logger.debug(
            "[LOG-SETUP] 日志系统阶段已设置为startup",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        return logging_hub

    except Exception as e:
        logger.critical(
            f"[LOG-SETUP] 🔥 LoggingHub初始化失败，使用降级日志输出: {e}",
            extra={"log_type": "ALERT", "scenario": scenario},
            exc_info=True
        )
        print(f"[日志系统] ❌ LoggingHub初始化失败: {e}")
        import traceback
        traceback.print_exc()

        # 添加简单的StreamHandler作为降级
        root_logger = logging.getLogger()
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            fallback = logging.StreamHandler(sys.stdout)
            fallback.setLevel(logging.INFO)
            root_logger.addHandler(fallback)
            logger.warning(
                "[LOG-SETUP] ⚠️ 已添加降级StreamHandler",
                extra={"log_type": "ALERT", "scenario": scenario}
            )

        # 刷新MemoryHandler到降级handler
        memory_handler.setTarget(fallback)
        memory_handler.flush()
        logger.debug(
            "[LOG-SETUP] MemoryHandler已刷新到降级handler",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )

        return None


def cleanup_all_logger_handlers() -> int:
    """清理所有logger的handlers，确保所有日志都经过LoggingHub

    这个函数会：
    1. 移除所有logger的StreamHandler（避免绕过LoggingHub直接输出）
    2. 设置所有logger的propagate=True（让日志传播到root logger）

    Returns:
        int: 清理的handler数量
    """
    logger = logging.getLogger("backend.infrastructure.system_vnpy.logging_system")

    # 尝试获取 LoggingHub 类型，用于避免误删
    try:
        _LoggingHub = LoggingHub
        logger.debug(
            "[LOG-SETUP] LoggingHub类型已获取，用于避免误删",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )
    except Exception as e:
        _LoggingHub = None
        logger.debug(
            f"[LOG-SETUP] 无法获取LoggingHub类型: {e}",
            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
        )

    # 获取所有已创建的logger
    logger_dict = getattr(logging.root.manager, "loggerDict", {})
    all_loggers = [logging.getLogger(name) for name in logger_dict]
    # 包含root logger在清理范围内
    all_loggers.append(logging.root)

    logger.debug(
        f"[LOG-SETUP] 找到{len(all_loggers)}个logger需要清理",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    cleaned_count = 0
    propagate_set_count = 0

    for lgr in all_loggers:
        # 移除所有StreamHandler（这些会直接输出到stdout，绕过LoggingHub）
        handlers_to_remove = []
        for handler in lgr.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                # 保留LoggingHub（不是StreamHandler的子类），移除其他StreamHandler
                if _LoggingHub is not None and isinstance(handler, _LoggingHub):
                    continue
                handlers_to_remove.append(handler)

        for handler in handlers_to_remove:
            lgr.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
            cleaned_count += 1

        # 设置propagate=True，让日志传播到root logger
        if not lgr.propagate:
            lgr.propagate = True
            propagate_set_count += 1

    logger.debug(
        f"[LOG-SETUP] 清理完成: 移除{cleaned_count}个handlers, 设置{propagate_set_count}个logger的propagate=True",
        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
    )

    return cleaned_count


# =============================================================================
# Part 13: 向后兼容API（保持旧代码兼容）
# =============================================================================


def start_ai_process(process_name: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
    """开始AI日志流程（向后兼容别名）

    注意：此函数已弃用，请使用 start_event_process
    为了保持向后兼容，保留此函数作为别名

    Args:
        process_name: 进程名称（事件名称）
        metadata: 元数据

    Returns:
        事件日志文件路径
    """
    return start_event_process(process_name, metadata)


def end_ai_process(success: bool = True, summary: Optional[str] = None):
    """结束AI日志流程（向后兼容别名）

    注意：此函数已弃用，请使用 end_event_process
    为了保持向后兼容，保留此函数作为别名

    Args:
        success: 是否成功
        summary: 摘要信息
    """
    end_event_process(success, summary)


def get_ai_log_handler() -> "EventLogFileHandler":
    """获取AI日志Handler（向后兼容别名）

    注意：此函数已弃用，请使用 get_event_log_handler
    为了保持向后兼容，保留此函数作为别名

    Returns:
        EventLogFileHandler实例
    """
    return get_event_log_handler()


def ai_log_process(event_name: str, metadata: Optional[Dict[str, Any]] = None):
    """AI日志流程上下文管理器（向后兼容别名）

    注意：此函数已弃用，请使用 event_log_process
    为了保持向后兼容，保留此函数作为别名

    Args:
        event_name: 事件名称
        metadata: 事件元数据（可选）
    """
    return event_log_process(event_name, metadata)


# =============================================================================
# 日志实用工具函数
# =============================================================================

@contextmanager
def log_process_context(
    process_name: str, 
    logger_name: str = "process",
    log_level: int = logging.INFO,
    **metadata
):
    """记录流程开始和结束的上下文管理器。
    
    Args:
        process_name: 流程名称
        logger_name: 记录器名称，默认为"process"
        log_level: 日志级别，默认为INFO
        **metadata: 额外的元数据
    """
    logger = logging.getLogger(f"{logger_name}.{process_name}")
    start_time = time.time()
    
    # 记录开始
    logger.log(
        log_level,
        f"🚀 开始: {process_name}",
        extra={
            "log_type": "STAGE_NODE",
            "action": "start",
            "timestamp": start_time,
            **metadata
        }
    )
    
    try:
        yield
        # 记录成功完成
        duration = time.time() - start_time
        logger.log(
            log_level,
            f"✅ 完成: {process_name} (耗时: {duration:.2f}s)",
            extra={
                "log_type": "STAGE_NODE",
                "action": "complete",
                "duration": duration,
                "status": "success",
                "timestamp": time.time(),
                **metadata
            }
        )
    except Exception as e:
        # 记录失败
        duration = time.time() - start_time
        logger.error(
            f"❌ 失败: {process_name} (错误: {str(e)})",
            extra={
                "log_type": "ALERT",
                "action": "error",
                "duration": duration,
                "status": "failed",
                "error": str(e),
                "timestamp": time.time(),
                **metadata
            },
            exc_info=True
        )
        raise


def log_progress(
    message: str,
    progress: Optional[float] = None,
    logger_name: str = "progress",
    **details
):
    """记录进度日志。
    
    Args:
        message: 进度消息
        progress: 进度值 (0.0 到 1.0)
        logger_name: 记录器名称
        **details: 额外的详情信息
    """
    logger = logging.getLogger(logger_name)
    extra = {
        "log_type": "PROGRESS",
        **details
    }
    if progress is not None:
        extra["progress"] = max(0.0, min(1.0, float(progress)))
    
    logger.info(
        f"⏳ {message}" + (f" ({progress*100:.1f}%)" if progress is not None else ""),
        extra=extra
    )


def log_alert(
    message: str,
    severity: str = "WARNING",
    logger_name: str = "alert",
    **details
):
    """记录告警日志。
    
    Args:
        message: 告警消息
        severity: 严重程度 (WARNING, ERROR, CRITICAL)
        logger_name: 记录器名称
        **details: 额外的详情信息
    """
    logger = logging.getLogger(logger_name)
    severity = severity.upper()
    level = getattr(logging, severity, logging.WARNING)
    
    emoji = "⚠️"
    if severity == "ERROR":
        emoji = "❌"
    elif severity == "CRITICAL":
        emoji = "🔥"
    
    logger.log(
        level,
        f"{emoji} {message}",
        extra={
            "log_type": "ALERT",
            "severity": severity,
            **details
        }
    )


def log_system(
    message: str,
    level: str = "INFO",
    logger_name: str = "system",
    **details
):
    """记录系统日志。
    
    Args:
        message: 系统消息
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_name: 记录器名称
        **details: 额外的详情信息
    """
    logger = logging.getLogger(logger_name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logger.log(
        log_level,
        message,
        extra={
            "log_type": "SYSTEM",
            **details
        }
    )


# =============================================================================
# 进程名称常量（向后兼容）
class ProcessNames:
    """预定义的流程名称常量（向后兼容）"""
    STARTUP = "application_startup"
    SHUTDOWN = "shutdown"
    SYMBOL_REFRESH = "refresh_symbol_list"
    SYMBOL_LOAD = "symbol_load"
    DOWNLOAD_KLINE = "data_download"
    DOWNLOAD_TICK = "data_download"
    QUALITY_SCAN = "manual_data_scan"
    QUALITY_REPAIR = "quality_repair"
    STRATEGY_BACKTEST = "strategy_backtest"
    STRATEGY_OPTIMIZE = "strategy_optimize"
    STRATEGY_DEPLOY = "strategy_deploy"
    TRADING_START = "trading_start"
    TRADING_STOP = "trading_stop"
    ORDER_EXECUTION = "order_execution"
    CONFIG_UPDATE = "config_update"
    DATABASE_BACKUP = "database_backup"
    LOG_CLEANUP = "log_cleanup"
    NETWORK_SPEEDTEST_PING = "manual_speedtest"
    NETWORK_SPEEDTEST_BANDWIDTH = "manual_speedtest"


# =============================================================================
# 导出
# =============================================================================


__all__ = [
    # 数据结构
    "LogType",
    "UnifiedLogRecord",
    "bind_logger_defaults",
    "get_configured_logger",
    "get_stage_logger",
    "get_alert_logger",
    "get_progress_logger",
    "stage_log",
    "alert_log",
    "progress_log",
    # 核心类
    "LoggingHub",
    "OrderedLogQueue",
    "PersistentBufferHandler",
    "MultiProcessLogCollector",
    "ProgressThrottler",
    "EventLogFileHandler",
    # 事件名称常量
    "SUPPORTED_EVENTS",
    # 事件类型
    "EVENT_LOG_SYSTEM",
    "EVENT_LOG_PROGRESS",
    "EVENT_LOG_NOTIFICATION",
    "EVENT_LOG_ALERT",
    "EVENT_UI_STATUSBAR",
    "EVENT_UI_DIALOG",
    # 上下文管理器
    "event_log_process",
    "event_log_process_decorator",
    # 全局单例
    "get_logging_hub",
    "get_event_log_handler",
    "get_ordered_log_queue",
    "get_multi_process_collector",
    # 便捷API
    "log_progress",
    "notify_complete",
    "alert",
    "log_system",
    "stage_node",
    "debug_log",
    # 初始化函数
    "setup_logging_system",
    "start_event_process",
    "end_event_process",
    # 完整初始化函数（从logging_init.py迁移）
    "setup_memory_logging",
    "initialize_logging_hub_complete",
    "cleanup_all_logger_handlers",
    # 子进程日志设置
    "setup_subprocess_logging",
    "restore_queue_from_token",
    "load_queue_from_env",
    "LOGGING_QUEUE_TOKEN_ENV",
    # 向后兼容API
    "start_ai_process",
    "end_ai_process",
    "get_ai_log_handler",
    "ai_log_process",
    "ProcessNames",
]
