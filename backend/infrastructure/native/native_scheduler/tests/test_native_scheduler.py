import importlib
import time

import pytest

native_scheduler_module = importlib.import_module("backend.infrastructure.native.native_scheduler")
NativeScheduler = getattr(native_scheduler_module, "NativeScheduler")


@pytest.mark.timeout(5)
def test_scheduler_submit_and_stats():
    scheduler = NativeScheduler()
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
    scheduler = NativeScheduler()
    with pytest.raises(KeyError):
        scheduler.submit("missing", lambda: None)

