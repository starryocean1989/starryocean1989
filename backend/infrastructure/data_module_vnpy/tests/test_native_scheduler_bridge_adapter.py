# -*- coding: utf-8 -*-
from __future__ import annotations

import types

import pytest

from backend.infrastructure.data_module_vnpy import native_scheduler_bridge as bridge_module


class DummyAdapter:
    def __init__(self, *, categories, auto_shutdown, executor_factory=None):
        self.categories = dict(categories)
        self.auto_shutdown = auto_shutdown
        self.executor_factory = executor_factory
        self.ensure_calls = []
        self.submit_calls = []
        self.stats_called = 0
        self.shutdown_called = []
        self.configure_args = []

    def get_categories(self):
        return dict(self.categories)

    def ensure_category(self, name, *, queue_capacity=None, max_workers=None):
        self.ensure_calls.append((name, queue_capacity, max_workers))

    def submit(self, category, func, args=None, kwargs=None):
        self.submit_calls.append((category, func, args, kwargs))
        return "future"

    def stats(self):
        self.stats_called += 1
        return {"categories": self.categories}

    def shutdown(self, *, wait=True):
        self.shutdown_called.append(wait)

    def configure(self, categories):
        self.configure_args.append(categories)
        self.categories = dict(categories)


@pytest.fixture(autouse=True)
def patch_adapter(monkeypatch):
    monkeypatch.setattr(
        bridge_module,
        "SchedulerAdapter",
        DummyAdapter,
    )


def test_bridge_initialises_with_default_categories():
    bridge = bridge_module.NativeSchedulerBridge(auto_shutdown=False)
    assert set(bridge.categories.keys()) == set(bridge_module.NativeSchedulerBridge.DEFAULT_CATEGORIES.keys())


def test_ensure_category_passthrough():
    bridge = bridge_module.NativeSchedulerBridge(auto_shutdown=False)
    bridge.ensure_category("network_download", queue_capacity=10, max_workers=20)
    adapter = bridge._adapter  # noqa: SLF001
    assert adapter.ensure_calls == [("network_download", 10, 20)]


def test_submit_and_stats_delegate():
    bridge = bridge_module.NativeSchedulerBridge(auto_shutdown=False)
    result = bridge.submit("network_download", lambda: None, args=(1,), kwargs={"a": 2})
    assert result == "future"
    assert bridge.stats() == {"categories": bridge_module.NativeSchedulerBridge.DEFAULT_CATEGORIES}


def test_reset_reconfigures_adapter():
    bridge = bridge_module.NativeSchedulerBridge(auto_shutdown=False)
    new_cfg = {"custom": {"queue_capacity": 1, "max_workers": 1}}
    bridge.reset(new_cfg)
    adapter = bridge._adapter  # noqa: SLF001
    assert adapter.configure_args[-1] == new_cfg


def test_context_manager_shutdown(monkeypatch):
    bridge = bridge_module.NativeSchedulerBridge(auto_shutdown=True)
    adapter = bridge._adapter  # noqa: SLF001
    with bridge:
        pass
    assert adapter.shutdown_called == [True]

