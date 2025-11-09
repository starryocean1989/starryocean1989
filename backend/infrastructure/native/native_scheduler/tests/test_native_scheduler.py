import time

import pytest

from backend.infrastructure.native.native_scheduler import NativeScheduler
from backend.infrastructure.native.native_scheduler import USING_NATIVE_CORE
from backend.infrastructure.native.native_threadpool import NativeThreadPool


def _make_factory():
    calls = []

    def factory(max_workers: int):
        calls.append(max_workers)
        return NativeThreadPool(max_workers=max_workers)

    return factory, calls


@pytest.mark.timeout(5)
def test_scheduler_submit_and_stats():
    scheduler = NativeScheduler(executor_factory=NativeThreadPool)
    scheduler.register_category("download", queue_capacity=8, max_workers=2)

    results = []

    def task(x):
        time.sleep(0.01)
        results.append(x)
        return x

    futures = [
        scheduler.submit("download", task, (i,), {})
        for i in range(6)
    ]
    stats = scheduler.stats()
    assert "download" in stats
    assert stats["download"]["max_workers"] == 2
    assert stats["download"]["queue_size"] >= 0

    values = [future.result(timeout=2.0) for future in futures]
    scheduler.shutdown()

    assert sorted(values) == list(range(6))
    assert sorted(results) == list(range(6))


def test_scheduler_unknown_category():
    scheduler = NativeScheduler(executor_factory=NativeThreadPool)
    with pytest.raises(KeyError):
        scheduler.submit("missing", lambda: None)


def test_executor_factory_called_per_category():
    factory, calls = _make_factory()
    scheduler = NativeScheduler(executor_factory=factory)
    scheduler.register_category("alpha", max_workers=3)
    scheduler.register_category("beta", max_workers=5)
    assert calls == [3, 5]
    scheduler.shutdown()


@pytest.mark.skipif(not USING_NATIVE_CORE, reason="Only relevant when native core is enabled")
def test_missing_executor_factory_raises():
    with pytest.raises(ValueError):
        NativeScheduler()  # type: ignore[call-arg]

