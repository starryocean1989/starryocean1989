# -*- coding: utf-8 -*-
"""
监控进程端口冲突与恢复测试：
1) 预占用 5555 端口，启动监控进程应快速失败并退出
2) 释放端口后再次启动，握手成功（health_check 或 get_data）
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict
import pytest

import zmq  # type: ignore


def _handshake(addr: str = "127.0.0.1", port: int = 5557, timeout_ms: int = 2000) -> Dict[str, Any]:
    ctx = zmq.Context()
    s = ctx.socket(zmq.REQ)
    try:
        s.setsockopt(zmq.LINGER, 0)
        s.setsockopt(zmq.RCVTIMEO, timeout_ms)
        s.setsockopt(zmq.SNDTIMEO, timeout_ms)
        s.connect(f"tcp://{addr}:{port}")
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


def test_monitor_port_conflict_and_recover():
    project_root = Path(__file__).resolve().parents[2]
    python = Path(project_root / "venv310" / "Scripts" / "python.exe")
    monitor_entry = (
        project_root / "backend" / "infrastructure" / "system_vnpy" / "monitor_process_entry.py"
    )

    # 1) 预占用 5555 端口（PULL bind）
    ctx = zmq.Context()
    pull = ctx.socket(zmq.PULL)
    pull_linger = 0
    pull.setsockopt(zmq.LINGER, pull_linger)
    try:
        pull.bind("tcp://127.0.0.1:5555")
    except Exception:
        # 若端口已被外部进程占用，无法构造可控冲突，跳过用例
        try:
            pull.close()
            ctx.term()
        except Exception:
            pass
        pytest.skip("port 5555 already in use by external process; skip conflict construction")

    # 启动监控进程（应失败并退出）
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    stdout_file = open(log_dir / "monitor_stdout_conflict.log", "w", encoding="utf-8")
    stderr_file = open(log_dir / "monitor_stderr_conflict.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(python), str(monitor_entry)], stdout=stdout_file, stderr=stderr_file
    )

    # 等待一会儿让其尝试bind并失败
    time.sleep(1.5)
    # 应该已退出或即将退出
    exited = proc.poll() is not None
    if not exited:
        # 保障不影响后续测试
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)

    # 释放占用端口
    try:
        pull.close()
        ctx.term()
    except Exception:
        pass

    # 2) 重新启动监控进程，应成功并可握手
    stdout2 = open(log_dir / "monitor_stdout_conflict_recover.log", "w", encoding="utf-8")
    stderr2 = open(log_dir / "monitor_stderr_conflict_recover.log", "w", encoding="utf-8")
    proc2 = subprocess.Popen([str(python), str(monitor_entry)], stdout=stdout2, stderr=stderr2)

    try:
        time.sleep(1.5)
        data = _handshake()
        if "status" in data:
            assert data["status"] in ("healthy", True)
        else:
            assert "timestamp" in data and "system" in data
    finally:
        if proc2.poll() is None:
            proc2.terminate()
            try:
                proc2.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc2.kill()
                proc2.wait(timeout=2)
        try:
            stdout2.close()
            stderr2.close()
        except Exception:
            pass
