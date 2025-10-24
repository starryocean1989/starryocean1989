# -*- coding: utf-8 -*-
"""
监控进程 ZMQ 握手与数据通路测试（REQ/REP on 5557）.

说明：
- 优先发送 health_check；如果服务当前不支持该动作，回退 get_data。
- 断言返回结构包含关键字段，作为通路可用性的证明。
"""

import zmq  # type: ignore

from typing import Any, Dict


def _query_monitor(
    addr: str = "127.0.0.1", port: int = 5557, timeout_ms: int = 1500
) -> Dict[str, Any]:
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
        # 强制为dict，若非dict抛出异常以便测试失败标识
        if not isinstance(resp, dict):
            raise AssertionError("monitor response is not a dict")
        return resp
    finally:
        try:
            s.close()
            ctx.term()
        except Exception:
            pass


def test_monitor_req_rep_path():
    """验证监控进程REQ/REP通路可用并返回合理结构。"""
    data = _query_monitor()

    # 如果是 health_check 返回
    if isinstance(data, dict) and "status" in data:
        assert data["status"] in ("healthy", True)
        return

    # 否则为 get_data 返回，检查关键字段
    assert isinstance(data, dict)
    assert "timestamp" in data
    assert "system" in data
    assert isinstance(data["system"], dict)
    # 关键指标字段存在
    assert "cpu_percent" in data["system"]
    assert "memory_percent" in data["system"]  # end
