# -*- coding: utf-8 -*-
"""native_process_metrics - 进程/系统指标原生封装（Python 兼容实现）."""

from __future__ import annotations

import platform
import time
from typing import Any, Dict, Optional

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - 项目依赖已包含 psutil
    psutil = None  # type: ignore


IS_WINDOWS = platform.system() == "Windows"
PROCESS_METRICS_AVAILABLE = psutil is not None
SYSTEM_METRICS_AVAILABLE = psutil is not None

_process_snapshots: Dict[int, Dict[str, Any]] = {}


def _get_load_average() -> Dict[str, float]:
    if hasattr(psutil, "getloadavg"):
        try:
            load1, load5, load15 = psutil.getloadavg()  # type: ignore[attr-defined]
            return {"load1": float(load1), "load5": float(load5), "load15": float(load15)}
        except Exception:
            pass
    try:
        import os

        load1, load5, load15 = os.getloadavg()  # type: ignore[attr-defined]
        return {"load1": float(load1), "load5": float(load5), "load15": float(load15)}
    except Exception:
        return {"load1": 0.0, "load5": 0.0, "load15": 0.0}


def get_system_metrics() -> Dict[str, Any]:
    """聚合系统级资源指标."""

    if psutil is None:
        raise ImportError("psutil is required for native_process_metrics")

    now = time.time()
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk_percent = psutil.disk_usage("/").percent if hasattr(psutil, "disk_usage") else 0.0
    net_counters = psutil.net_io_counters()

    load_avg = _get_load_average()

    return {
        "timestamp": now,
        "cpu_percent": float(cpu_percent),
        "memory_percent": float(memory.percent),
        "disk_percent": float(disk_percent),
        "net_sent_bytes": int(getattr(net_counters, "bytes_sent", 0)),
        "net_recv_bytes": int(getattr(net_counters, "bytes_recv", 0)),
        "process_count": len(psutil.pids()),
        "load_average": [
            load_avg["load1"],
            load_avg["load5"],
            load_avg["load15"],
        ],
    }


def get_process_snapshot(pid: int) -> Dict[str, Any]:
    """返回指定进程的快照指标."""

    if psutil is None:
        raise ImportError("psutil is required for native_process_metrics")

    process = psutil.Process(pid)

    with process.oneshot():
        cpu_percent = process.cpu_percent(interval=None)
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        name = process.name()
        status = process.status()
        create_time = process.create_time()
        io_counters = None
        try:
            io_counters = process.io_counters()
        except Exception:
            io_counters = None

    now = time.time()
    prev = _process_snapshots.get(pid)
    disk_read_mbps = 0.0
    disk_write_mbps = 0.0

    if io_counters is not None and prev and "io" in prev:
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
        "cpu_percent": float(cpu_percent),
        "memory_percent": float(memory_percent),
        "memory_rss": float(getattr(memory_info, "rss", 0)),
        "disk_read_mbps": float(disk_read_mbps),
        "disk_write_mbps": float(disk_write_mbps),
        "network_recv_mbps": 0.0,
        "network_send_mbps": 0.0,
        "create_time": float(create_time),
    }

    _process_snapshots[pid] = {
        "timestamp": now,
        "io": io_counters,
    }

    return snapshot


__all__ = [
    "PROCESS_METRICS_AVAILABLE",
    "SYSTEM_METRICS_AVAILABLE",
    "get_system_metrics",
    "get_process_snapshot",
]
