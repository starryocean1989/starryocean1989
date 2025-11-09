# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def force_python_scheduler(monkeypatch):
    monkeypatch.setenv("NATIVE_SCHEDULER_FORCE_PY", "1")
    monkeypatch.delenv("NATIVE_SCHEDULER_FORCE_NATIVE", raising=False)
    import backend.infrastructure.native.native_scheduler as native_scheduler

    import backend.infrastructure.scheduling.native_scheduler_adapter as adapter

    import backend.infrastructure.data_module_vnpy.native_scheduler_bridge as bridge

    importlib.reload(native_scheduler)
    importlib.reload(adapter)
    importlib.reload(bridge)
    yield
    importlib.reload(native_scheduler)
    importlib.reload(adapter)
    importlib.reload(bridge)


def test_bridge_end_to_end():
    from backend.infrastructure.data_module_vnpy.native_scheduler_bridge import NativeSchedulerBridge

    bridge = NativeSchedulerBridge(
        categories={"demo": {"queue_capacity": 8, "max_workers": 2}},
        auto_shutdown=False,
    )

    results = []

    def task(x):
        results.append(x)
        return x

    futures = [bridge.submit("demo", task, args=(i,)) for i in range(4)]
    values = [future.result(timeout=2.0) for future in futures]

    assert sorted(values) == [0, 1, 2, 3]
    assert sorted(results) == [0, 1, 2, 3]

    stats = bridge.stats()
    assert "demo" in stats

    bridge.shutdown()

    with pytest.raises(Exception):
        bridge.submit("demo", lambda: None)

