# -*- coding: utf-8 -*-
"""native_log_pipeline Python 接口."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Iterable, Optional

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
    get_alert_logger,
)
_LOGGER = bind_logger_defaults(
    logging.getLogger("backend.native.log_pipeline"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.log_pipeline",
)


# 优先使用build目录中的最新版本
import sys
import os
build_path = os.path.join(os.path.dirname(__file__), 'build', 'lib.win-amd64-cpython-310')
if build_path not in sys.path:
    sys.path.insert(0, build_path)

from pipeline import (  # type: ignore[F401]
    DEFAULT_BATCH_SIZE,
    DEFAULT_FLUSH_MS,
    Pipeline,
    get_version,
    install as _install,
)

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_FLUSH_MS",
    "Pipeline",
    "install",
    "create",
    "set_fallback",
    "flush_and_close",
    "get_version",
    "PipelineMonitor",
    "install_with_monitor",
]


class NativeLogPipelineError(RuntimeError):
    """统一的原生日志管线异常."""


class PipelineMonitor:
    """日志管道监控器，定期检查统计信息并在异常时告警."""

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        check_interval: float = 60.0,  # 每分钟检查一次
        error_threshold: int = 10,     # 错误计数阈值
        flush_failure_threshold: int = 5,  # flush失败阈值
        alert_cooldown: float = 300.0,  # 告警冷却时间（5分钟）
    ):
        """初始化监控器.

        Args:
            pipeline: 要监控的Pipeline实例
            check_interval: 检查间隔（秒）
            error_threshold: SQLite错误阈值，超过时告警
            flush_failure_threshold: 连续flush失败次数阈值
            alert_cooldown: 告警冷却时间，避免频繁告警
        """
        self.pipeline = pipeline
        self.check_interval = check_interval
        self.error_threshold = error_threshold
        self.flush_failure_threshold = flush_failure_threshold
        self.alert_cooldown = alert_cooldown

        self._alert_logger = get_alert_logger("backend.native.log_pipeline.monitor", scenario="backend.native.log_pipeline")
        self._last_stats = {}
        self._last_alert_time = 0
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """启动监控线程."""
        with self._lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                return  # 已经在运行

            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="PipelineMonitor",
                daemon=True
            )
            self._monitor_thread.start()

    def stop(self) -> None:
        """停止监控线程."""
        with self._lock:
            if self._monitor_thread:
                self._stop_event.set()
                self._monitor_thread.join(timeout=5.0)
                self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """监控循环."""
        while not self._stop_event.is_set():
            try:
                self._check_stats()
            except Exception as exc:  # noqa: BLE001
                # 监控自身异常不应该影响主进程
                try:
                    self._alert_logger.warning(
                        f"PipelineMonitor 自身异常: {exc}",
                        exc_info=True,
                        extra={"scenario": "backend.native.log_pipeline.monitor"}
                    )
                except Exception:  # noqa: BLE001
                    pass  # 避免递归错误

            self._stop_event.wait(self.check_interval)

    def _check_stats(self) -> None:
        """检查统计信息."""
        try:
            current_stats = self.pipeline.stats()
        except Exception as exc:  # noqa: BLE001
            self._alert_logger.error(
                f"无法获取Pipeline统计信息: {exc}",
                exc_info=True,
                extra={
                    "scenario": "backend.native.log_pipeline",
                    "action_required": "check_pipeline_health",
                }
            )
            return

        # 检查错误计数
        sqlite_errors = current_stats.get("sqlite_errors", 0)
        fallback_errors = current_stats.get("fallback_errors", 0)

        # 计算增量
        last_sqlite_errors = self._last_stats.get("sqlite_errors", 0)
        last_fallback_errors = self._last_stats.get("fallback_errors", 0)

        sqlite_error_delta = sqlite_errors - last_sqlite_errors
        fallback_error_delta = fallback_errors - last_fallback_errors

        # 检查是否需要告警
        now = time.time()
        should_alert = False
        alert_message = ""
        alert_details = {
            "scenario": "backend.native.log_pipeline",
            "sqlite_errors": sqlite_errors,
            "fallback_errors": fallback_errors,
            "error_delta": sqlite_error_delta + fallback_error_delta,
        }

        if sqlite_error_delta >= self.error_threshold:
            should_alert = True
            alert_message = (
                f"SQLite错误率过高: 最近{self.check_interval:.0f}秒内发生"
                f"{sqlite_error_delta}个SQLite错误，总计{sqlite_errors}个"
            )
            alert_details["error_type"] = "sqlite"
            alert_details["action_required"] = "check_sqlite_connection"

        elif fallback_error_delta >= self.error_threshold:
            should_alert = True
            alert_message = (
                f"回调错误率过高: 最近{self.check_interval:.0f}秒内发生"
                f"{fallback_error_delta}个回调错误，总计{fallback_errors}个"
            )
            alert_details["error_type"] = "callback"
            alert_details["action_required"] = "check_callback_implementation"

        # 检查连续flush失败
        total_flushed = current_stats.get("total_flushed", 0)
        total_flush_calls = current_stats.get("total_flush_calls", 0)
        last_total_flushed = self._last_stats.get("total_flushed", 0)
        last_total_flush_calls = self._last_stats.get("total_flush_calls", 0)

        if total_flush_calls > last_total_flush_calls:
            # 有新的flush调用
            flushed_delta = total_flushed - last_total_flushed
            calls_delta = total_flush_calls - last_total_flush_calls

            if calls_delta > flushed_delta and (calls_delta - flushed_delta) >= self.flush_failure_threshold:
                should_alert = True
                alert_message = (
                    f"连续flush失败: 最近{self.check_interval:.0f}秒内"
                    f"{calls_delta - flushed_delta}次flush失败"
                )
                alert_details["error_type"] = "flush_failure"
                alert_details["action_required"] = "check_flush_mechanism"

        # 发送告警（带冷却机制）
        if should_alert and (now - self._last_alert_time) >= self.alert_cooldown:
            self._alert_logger.error(
                alert_message,
                extra=alert_details
            )
            self._last_alert_time = now

        # 更新上一次统计信息
        self._last_stats = current_stats.copy()

    def __enter__(self) -> "PipelineMonitor":
        """上下文管理器入口."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口."""
        self.stop()


def install(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_ms: float = DEFAULT_FLUSH_MS,
    fallback: Optional[Callable[[Iterable[dict]], None]] = None,
    event_callback: Optional[Callable[[Iterable[dict]], None]] = None,
    sqlite_path: Optional[str] = None,
    enable_logging: bool = True,
) -> Pipeline:
    """创建并返回原生管线实例."""

    try:
        pipeline: Pipeline = _install(
            batch_size,
            flush_ms,
            fallback,
            event_callback,
            sqlite_path,
            int(enable_logging),
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error(
            "native_log_pipeline 安装失败",
            extra={
                "log_type": LogType.ALERT.value,
                "scenario": "backend.native.log_pipeline",
                "batch_size": batch_size,
                "flush_ms": flush_ms,
            },
            exc_info=True,
        )
        raise NativeLogPipelineError(str(exc)) from exc
    _LOGGER.debug(
        "native_log_pipeline 安装成功",
        extra={
            "scenario": "backend.native.log_pipeline",
            "batch_size": batch_size,
            "flush_ms": flush_ms,
            "fallback": bool(fallback),
            "event_callback": bool(event_callback),
            "sqlite_path": sqlite_path or "",
            "enable_logging": enable_logging,
        },
    )
    return pipeline


def create(**kwargs) -> Pipeline:
    """兼容旧接口，转到 :func:`install`."""
    return install(**kwargs)


def set_fallback(pipeline: Pipeline, fallback: Callable[[Iterable[dict]], None]) -> None:
    """更新原生缓冲区的兜底回调."""
    pipeline.set_fallback(fallback)


def flush_and_close(pipeline: Optional[Pipeline]) -> None:
    """安全关闭原生缓冲区."""
    if pipeline is None:
        return
    pipeline.flush_and_close()
    _LOGGER.debug(
        "native_log_pipeline 已执行 flush_and_close",
        extra={
            "scenario": "backend.native.log_pipeline",
        },
    )


def install_with_monitor(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_ms: float = DEFAULT_FLUSH_MS,
    fallback: Optional[Callable[[Iterable[dict]], None]] = None,
    event_callback: Optional[Callable[[Iterable[dict]], None]] = None,
    sqlite_path: Optional[str] = None,
    enable_logging: bool = True,
    enable_monitor: bool = True,
    monitor_check_interval: float = 60.0,
    monitor_error_threshold: int = 10,
    monitor_flush_failure_threshold: int = 5,
    monitor_alert_cooldown: float = 300.0,
) -> tuple[Pipeline, Optional[PipelineMonitor]]:
    """创建带监控功能的原生管线实例.

    Args:
        batch_size: 批量大小
        flush_ms: 刷新间隔（毫秒）
        fallback: 回退回调函数
        event_callback: 事件回调函数
        sqlite_path: SQLite数据库路径
        enable_logging: 是否启用C层日志输出
        enable_monitor: 是否启用监控功能
        monitor_check_interval: 监控检查间隔（秒）
        monitor_error_threshold: 错误阈值
        monitor_flush_failure_threshold: flush失败阈值
        monitor_alert_cooldown: 告警冷却时间（秒）

    Returns:
        (pipeline, monitor)元组，如果不启用监控则monitor为None
    """
    pipeline = install(
        batch_size=batch_size,
        flush_ms=flush_ms,
        fallback=fallback,
        event_callback=event_callback,
        sqlite_path=sqlite_path,
        enable_logging=enable_logging,
    )

    monitor = None
    if enable_monitor:
        monitor = PipelineMonitor(
            pipeline,
            check_interval=monitor_check_interval,
            error_threshold=monitor_error_threshold,
            flush_failure_threshold=monitor_flush_failure_threshold,
            alert_cooldown=monitor_alert_cooldown,
        )
        monitor.start()

    return pipeline, monitor
