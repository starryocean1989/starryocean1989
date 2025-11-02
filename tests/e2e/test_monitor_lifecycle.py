# -*- coding: utf-8 -*-
"""
监控进程生命周期端到端测试：
1) 启动独立监控进程
2) ZMQ握手（health_check 优先，回退 get_data）
3) 清理监控进程
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict

import zmq  # type: ignore


def _handshake(addr: str = "127.0.0.1", port: int = 5557, timeout_ms: int = 2000) -> Dict[str, Any]:
    ctx = zmq.Context()
    s = ctx.socket(zmq.REQ)
    try:
        s.setsockopt(zmq.LINGER, 0)
        s.setsockopt(zmq.RCVTIMEO, timeout_ms)
        s.setsockopt(zmq.SNDTIMEO, timeout_ms)
        s.connect(f"tcp://{addr}:{port}")
        # try health_check first
        try:
            s.send_json({"action": "health_check"})
            resp = s.recv_json()
            if isinstance(resp, dict) and resp.get("status") in ("healthy", True):
                return resp
        except Exception:
            pass

        s.send_json({"action": "get_data"})
        resp = s.recv_json()
        if not isinstance(resp, dict):
            raise AssertionError("monitor response is not a dict")
        return resp
    finally:
        try:
            s.close()
            ctx.term()
        except Exception:
            pass


def test_monitor_lifecycle():
    project_root = Path(__file__).resolve().parents[2]
    python = Path(project_root / "venv310" / "Scripts" / "python.exe")
    monitor_entry = (
        project_root / "backend" / "infrastructure" / "system_vnpy" / "monitor_system.py"
    )

    # 1) 启动监控进程（stdout/stderr → 文件，避免PIPE阻塞）
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    stdout_file = open(log_dir / "monitor_stdout_test.log", "w", encoding="utf-8")
    stderr_file = open(log_dir / "monitor_stderr_test.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(python), str(monitor_entry)], stdout=stdout_file, stderr=stderr_file
    )

    try:
        # 等待进程初始化
        time.sleep(1.5)

        # 2) 握手
        data = _handshake()
        # 允许 health_check 或 get_data 两种返回结构
        if "status" in data:
            assert data["status"] in ("healthy", True)
        else:
            assert "timestamp" in data and "system" in data
            assert "cpu_percent" in data["system"]
            assert "memory_percent" in data["system"]

    finally:
        try:
            # 3) 清理监控进程
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
        finally:
            try:
                stdout_file.close()
                stderr_file.close()
            except Exception:
                pass
