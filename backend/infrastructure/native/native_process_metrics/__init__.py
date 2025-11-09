# -*- coding: utf-8 -*-
"""native_process_metrics Python 接口."""

from __future__ import annotations

import json
import logging
import platform
import time
from typing import Any, Dict, Iterable, Optional, Sequence, cast

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    log_from_native,
    native_call_guard,
)
from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.process_metrics"),
    log_type=LogType.SYSTEM.value,
    scenario="native.process_metrics",
)

_fallback_logged = False
_native_import_logged = False


def _log_native_event(message: str, *, level: int = NativeLogLevel.INFO, details: Optional[str] = None) -> None:
    """通过统一日志桥输出原生指标相关事件."""

    try:
        log_from_native(
            level,
            "backend.native.process_metrics",
            "python_bridge",
            0,
            message,
            details,
        )
    except Exception:  # noqa: BLE001 - 兜底避免日志失败影响主流程
        extra = {"log_type": LogType.SYSTEM.value, "scenario": "native.process_metrics"}
        if details:
            extra["native_details"] = details
        # logging.getLevelName(level) 可能返回 str，这里确保转换为 int
        python_level = level if isinstance(level, int) else logging.INFO
        _logger.log(python_level, message, extra=extra)


try:  # pragma: no cover - 编译失败时自动回退
    from .process_metrics import (  # type: ignore[F401]
        LAST_ERROR as _NATIVE_LAST_ERROR,
        PROCESS_METRICS_AVAILABLE,
        enumerate_processes as _native_enumerate_processes,
        get_last_error as _native_get_last_error,
        get_process_snapshot as _native_get_process_snapshot,
        get_system_metrics as _native_get_system_metrics,
    )
except Exception as exc:  # pragma: no cover
    PROCESS_METRICS_AVAILABLE = False  # type: ignore[assignment]
    _NATIVE_IMPORT_ERROR: Optional[Exception] = exc
    _native_get_system_metrics = None  # type: ignore[assignment]
    _native_get_process_snapshot = None  # type: ignore[assignment]
    _native_get_last_error = None  # type: ignore[assignment]
    _native_enumerate_processes = None  # type: ignore[assignment]
    _NATIVE_LAST_ERROR = None  # type: ignore[assignment]
else:
    _NATIVE_IMPORT_ERROR = None
    _log_native_event("native_process_metrics extension loaded", level=NativeLogLevel.INFO)

try:  # pragma: no cover - 运行时依赖
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

IS_WINDOWS = platform.system() == "Windows"

_PROCESS_CACHE: Dict[int, Dict[str, Any]] = {}


class NativeProcessMetricsError(RuntimeError):
    """原生进程指标扩展异常."""


def _ensure_native_available() -> None:
    if not PROCESS_METRICS_AVAILABLE or _native_get_system_metrics is None:
        global _native_import_logged
        if not _native_import_logged:
            _log_native_event(
                "native_process_metrics extension unavailable, falling back to psutil",
                level=NativeLogLevel.WARNING,
                details=str(_NATIVE_IMPORT_ERROR) if _NATIVE_IMPORT_ERROR else None,
            )
            _native_import_logged = True
        raise NativeProcessMetricsError(
            "native_process_metrics extension is unavailable"
        ) from _NATIVE_IMPORT_ERROR


@native_call_guard(component="backend.native.process_metrics")
def _fallback_system_metrics() -> Dict[str, Any]:
    global _fallback_logged
    if not _fallback_logged:
        _log_native_event(
            "collecting system metrics via Python fallback",
            level=NativeLogLevel.WARNING,
        )
        _fallback_logged = True
    if psutil is None:
        raise NativeProcessMetricsError("psutil is required for fallback metrics")

    now = time.time()
    try:
        cpu_raw = psutil.cpu_percent(interval=None)
        if isinstance(cpu_raw, list):
            cpu_percent = float(sum(cpu_raw) / len(cpu_raw)) if cpu_raw else 0.0
        else:
            cpu_percent = float(cpu_raw)
    except Exception:  # pragma: no cover - 极端场景忽略
        cpu_percent = 0.0

    try:
        memory = psutil.virtual_memory()
        memory_percent = float(memory.percent)
    except Exception:
        memory_percent = 0.0

    try:
        disk_percent = float(psutil.disk_usage("/").percent)  # type: ignore[arg-type]
    except Exception:
        disk_percent = 0.0

    try:
        net = psutil.net_io_counters()
        net_sent = int(getattr(net, "bytes_sent", 0))
        net_recv = int(getattr(net, "bytes_recv", 0))
    except Exception:
        net_sent = 0
        net_recv = 0

    load_average = [0.0, 0.0, 0.0]
    if hasattr(psutil, "getloadavg"):
        try:
            load_seq = cast(Sequence[float], psutil.getloadavg())  # type: ignore[attr-defined]
            load_average = [float(load_seq[0]), float(load_seq[1]), float(load_seq[2])]
        except Exception:  # pragma: no cover
            pass

    return {
        "timestamp": now,
        "cpu_percent": float(cpu_percent),
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
        "net_sent_bytes": net_sent,
        "net_recv_bytes": net_recv,
        "process_count": len(psutil.pids()) if psutil else 0,
        "load_average": load_average,
    }


@native_call_guard(component="backend.native.process_metrics")
def _fallback_process_snapshot(pid: int) -> Dict[str, Any]:
    if psutil is None:
        raise NativeProcessMetricsError("psutil is required for fallback metrics")

    if pid <= 0:
        process_ids = psutil.pids()
        thread_count = 0
        try:
            for proc in psutil.process_iter(attrs=["num_threads"]):
                proc_info = getattr(proc, "info", {})
                raw_threads = proc_info.get("num_threads", 0)
                thread_count += int(raw_threads) if isinstance(raw_threads, (int, float)) else 0
        except Exception:
            pass
        return {
            "aggregate": {
                "process_count": len(process_ids),
                "thread_count": thread_count,
                "timestamp": time.time() * 1000,
            },
            "processes": [],
        }

    process = psutil.Process(pid)
    with process.oneshot():
        cpu_percent = float(process.cpu_percent(interval=None))
        memory_percent = float(process.memory_percent())
        mem_info = process.memory_info()
        name = process.name()
        status = process.status()
        create_time = float(process.create_time())
        io_counters = None
        try:
            io_counters = process.io_counters()
        except Exception:
            io_counters = None

    now = time.time()
    prev = _PROCESS_CACHE.get(pid)
    disk_read_mbps = 0.0
    disk_write_mbps = 0.0
    if prev and io_counters is not None and prev.get("io") is not None:
        elapsed = max(now - prev.get("timestamp", now), 1e-3)
        prev_io = prev["io"]
        read_delta = getattr(io_counters, "read_bytes", 0) - getattr(prev_io, "read_bytes", 0)
        write_delta = getattr(io_counters, "write_bytes", 0) - getattr(prev_io, "write_bytes", 0)
        disk_read_mbps = max(read_delta / elapsed / (1024 * 1024), 0.0)
        disk_write_mbps = max(write_delta / elapsed / (1024 * 1024), 0.0)

    snapshot = {
        "timestamp": now,
        "pid": pid,
        "name": name,
        "status": status,
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "memory_rss": int(getattr(mem_info, "rss", 0)),
        "memory_vms": int(getattr(mem_info, "vms", 0)),
        "io_read_bytes": int(getattr(io_counters, "read_bytes", 0)) if io_counters else 0,
        "io_write_bytes": int(getattr(io_counters, "write_bytes", 0)) if io_counters else 0,
        "create_time": create_time,
        "disk_read_mbps": disk_read_mbps,
        "disk_write_mbps": disk_write_mbps,
    }

    _PROCESS_CACHE[pid] = {"timestamp": now, "io": io_counters}
    return snapshot


@native_call_guard(component="backend.native.process_metrics")
def _fallback_enumerate_processes(limit: int, sort_key: str) -> Dict[str, Any]:
    if psutil is None:
        raise NativeProcessMetricsError("psutil is required for fallback metrics")

    if limit <= 0:
        limit = 50

    entries: list[Dict[str, Any]] = []
    now = time.time()
    attrs = ["pid", "name", "cpu_percent", "memory_percent", "status", "num_threads"]
    try:
        iterator = psutil.process_iter(attrs=attrs)
    except Exception as exc:  # pragma: no cover
        raise NativeProcessMetricsError(str(exc)) from exc

    for proc in iterator:
        info = getattr(proc, "info", {})
        try:
            mem_info = proc.memory_info()
        except Exception:
            mem_info = None

        pid_value = info.get("pid")
        name_value = info.get("name") or f"pid_{pid_value}"
        cpu_raw = info.get("cpu_percent", 0.0)
        mem_raw = info.get("memory_percent", 0.0)
        thread_raw = info.get("num_threads", 0)
        status_value = info.get("status", "unknown")

        cpu_percent = float(cpu_raw) if isinstance(cpu_raw, (int, float)) else 0.0
        memory_percent = float(mem_raw) if isinstance(mem_raw, (int, float)) else 0.0
        num_threads = int(thread_raw) if isinstance(thread_raw, (int, float)) else 0

        entry = {
            "pid": pid_value,
            "name": name_value,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_rss": int(getattr(mem_info, "rss", 0) or 0),
            "memory_vms": int(getattr(mem_info, "vms", 0) or 0),
            "num_threads": num_threads,
            "status": status_value,
            "timestamp": now,
        }
        entries.append(entry)

    entries.sort(key=lambda item: item.get(sort_key, 0) or 0, reverse=True)
    total = len(entries)
    limited = entries[:limit]
    return {
        "processes": limited,
        "total": total,
        "limit": limit,
        "sort_key": sort_key,
        "timestamp": now,
    }


def get_system_metrics(*, use_native: bool = True) -> Dict[str, Any]:
    """返回系统级指标，默认优先使用原生扩展。"""
    if use_native and PROCESS_METRICS_AVAILABLE and _native_get_system_metrics:
        try:
            return _native_get_system_metrics()
        except Exception as exc:  # pragma: no cover - 捕获异常用于回退
            _log_native_event(
                "native system metrics failed; switching to fallback",
                level=NativeLogLevel.WARNING,
                details=str(exc),
            )
            raise NativeProcessMetricsError(str(exc)) from exc
    return _fallback_system_metrics()


def get_process_snapshot(pid: int, *, use_native: bool = True) -> Dict[str, Any]:
    """返回指定进程快照."""
    if use_native and PROCESS_METRICS_AVAILABLE and _native_get_process_snapshot:
        try:
            return _native_get_process_snapshot(pid)
        except (PermissionError, NotImplementedError):
            raise
        except Exception as exc:  # pragma: no cover
            _log_native_event(
                f"native process snapshot failed (pid={pid}); switching to fallback",
                level=NativeLogLevel.WARNING,
                details=str(exc),
            )
            raise NativeProcessMetricsError(str(exc)) from exc
    return _fallback_process_snapshot(pid)


def enumerate_processes(
    *,
    limit: int = 50,
    sort_key: str = "memory_rss",
    use_native: bool = True,
) -> Dict[str, Any]:
    """返回按指标排序的进程列表."""

    if use_native and PROCESS_METRICS_AVAILABLE and _native_enumerate_processes:
        try:
            return _native_enumerate_processes(limit, sort_key)
        except Exception as exc:  # pragma: no cover
            _log_native_event(
                "native enumerate_processes failed; switching to fallback",
                level=NativeLogLevel.WARNING,
                details=str(exc),
            )
            raise NativeProcessMetricsError(str(exc)) from exc
    return _fallback_enumerate_processes(limit, sort_key)


def get_last_error() -> Optional[Iterable[Any]]:
    """获取最近一次 native 调用的 Windows 错误信息."""
    if _native_get_last_error is None:
        return None
    try:
        return _native_get_last_error()
    except Exception:
        return _NATIVE_LAST_ERROR


def cli_export(*, fmt: str = "json", pid: Optional[int] = None) -> str:
    """命令行导出工具，fmt 支持 json / pretty-json。"""
    metrics = {
        "system": get_system_metrics(),
        "process": get_process_snapshot(pid or 0),
        "last_error": get_last_error(),
    }
    if fmt == "pretty-json":
        return json.dumps(metrics, indent=2, ensure_ascii=False)
    if fmt == "json":
        return json.dumps(metrics, ensure_ascii=False)
    raise ValueError(f"unsupported format: {fmt}")


__all__ = [
    "PROCESS_METRICS_AVAILABLE",
    "NativeProcessMetricsError",
    "get_system_metrics",
    "get_process_snapshot",
    "enumerate_processes",
    "get_last_error",
    "cli_export",
]
