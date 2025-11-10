# -*- coding: utf-8 -*-
import pytest

from backend.infrastructure.scheduling import native_scheduler_adapter as adapter_module


class DummyScheduler:
    def __init__(self, *, executor_factory):
        self.executor_factory = executor_factory
        self.categories = {}
        self.submissions = []
        self.shutdown_calls = []

    def register_category(self, name, *, queue_capacity, max_workers):
        self.categories[name] = (queue_capacity, max_workers)

    def submit(self, category, func, *, call_args=(), call_kwargs=None):
        result = object()
        self.submissions.append((category, func, call_args, call_kwargs or {}))
        return result

    def stats(self):
        return {"categories": self.categories}

    def shutdown(self, *, wait=True):
        self.shutdown_calls.append(wait)


@pytest.fixture(autouse=True)
def patch_native_scheduler(monkeypatch):
    monkeypatch.setattr(adapter_module, "NativeScheduler", DummyScheduler)
    monkeypatch.setattr(adapter_module, "NativeThreadPool", object)


def test_configure_registers_categories():
    adapter = adapter_module.SchedulerAdapter(
        categories={"alpha": {"queue_capacity": 10, "max_workers": 2}},
        executor_factory=lambda mw: {"max_workers": mw},
    )
    assert adapter.stats()["categories"]["alpha"] == (10, 2)


def test_submit_delegates_and_returns_future():
    adapter = adapter_module.SchedulerAdapter(executor_factory=lambda mw: {"max_workers": mw})
    adapter.ensure_category("alpha", queue_capacity=10, max_workers=1)
    future = adapter.submit("alpha", lambda x: x + 1, args=(1,), kwargs={"y": 2})
    assert future is not None
    # 直接访问被monkeypatch的DummyScheduler类创建的实例
    scheduler = adapter._scheduler
    assert isinstance(scheduler, adapter_module.NativeScheduler)
    assert scheduler.submissions[0][0] == "alpha"  # type: ignore[attr-defined]
    assert scheduler.submissions[0][2] == (1,)  # type: ignore[attr-defined]
    assert scheduler.submissions[0][3] == {"y": 2}  # type: ignore[attr-defined]


def test_context_manager_triggers_shutdown():
    adapter = adapter_module.SchedulerAdapter(executor_factory=lambda mw: {"max_workers": mw})
    with adapter:
        adapter.ensure_category("alpha", queue_capacity=1, max_workers=1)
    # 直接访问被monkeypatch的DummyScheduler类创建的实例
    scheduler = adapter._scheduler
    assert isinstance(scheduler, adapter_module.NativeScheduler)
    assert scheduler.shutdown_calls == [True]  # type: ignore[attr-defined]

