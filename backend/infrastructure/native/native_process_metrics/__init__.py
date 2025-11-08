# -*- coding: utf-8 -*-
"""native_process_metrics Python 接口."""

from __future__ import annotations

import json
import platform
import time
from typing import Any, Dict, Iterable, Optional

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
        raise NativeProcessMetricsError(
            "native_process_metrics extension is unavailable"
        ) from _NATIVE_IMPORT_ERROR


def _fallback_system_metrics() -> Dict[str, Any]:
    if psutil is None:
        raise NativeProcessMetricsError("psutil is required for fallback metrics")

    now = time.time()
    try:
        cpu_percent = psutil.cpu_percent(interval=None)
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
            load = psutil.getloadavg()  # type: ignore[attr-defined]
            load_average = [float(load[0]), float(load[1]), float(load[2])]
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


def _fallback_process_snapshot(pid: int) -> Dict[str, Any]:
    if psutil is None:
        raise NativeProcessMetricsError("psutil is required for fallback metrics")

    if pid <= 0:
        process_ids = psutil.pids()
        thread_count = 0
        try:
            for proc in psutil.process_iter(attrs=["num_threads"]):
                thread_count += int(proc.info.get("num_threads", 0))
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


def _fallback_enumerate_processes(limit: int, sort_key: str) -> Dict[str, Any]:
    if psutil is None:
        raise NativeProcessMetricsError("psutil is required for fallback metrics")

    if limit <= 0:
        limit = 50

    entries = []
    now = time.time()
    attrs = ["pid", "name", "cpu_percent", "memory_percent", "status", "num_threads"]
    try:
        iterator = psutil.process_iter(attrs=attrs)
    except Exception as exc:  # pragma: no cover
        raise NativeProcessMetricsError(str(exc)) from exc

    for proc in iterator:
        info = proc.info
        try:
            mem_info = proc.memory_info()
        except Exception:
            mem_info = None

        entry = {
            "pid": info.get("pid"),
            "name": info.get("name") or f"pid_{info.get('pid')}",
            "cpu_percent": float(info.get("cpu_percent", 0.0) or 0.0),
            "memory_percent": float(info.get("memory_percent", 0.0) or 0.0),
            "memory_rss": int(getattr(mem_info, "rss", 0) or 0),
            "memory_vms": int(getattr(mem_info, "vms", 0) or 0),
            "num_threads": int(info.get("num_threads", 0) or 0),
            "status": info.get("status", "unknown"),
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
