import importlib

from backend.infrastructure.data_module_vnpy.native_scheduler_bridge import (
    NativeSchedulerBridge,
)


def test_bridge_registers_default_categories(monkeypatch):
    bridge = NativeSchedulerBridge(
        categories={
            "local_read": {"queue_capacity": 32, "max_workers": 2},
        }
    )

    stats = bridge.stats()
    assert "local_read" in stats

    def task(x):
        return x + 1

    future = bridge.submit("local_read", task, args=(1,), kwargs=None)
    assert future.result(timeout=1.0) == 2
    bridge.shutdown()


def test_disable_native_scheduler_env(monkeypatch):
    monkeypatch.setenv("DISABLE_NATIVE_SCHEDULER", "1")
    module = importlib.reload(importlib.import_module("backend.infrastructure.data_module_vnpy.data_acquisition"))
    assert getattr(module, "_NATIVE_SCHEDULER_BRIDGE") is None
    monkeypatch.delenv("DISABLE_NATIVE_SCHEDULER", raising=False)
    importlib.reload(module)

