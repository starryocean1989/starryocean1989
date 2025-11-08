import importlib
import time

import pytest

native_threadpool_module = importlib.import_module("backend.infrastructure.native.native_threadpool")
NativeThreadPool = getattr(native_threadpool_module, "NativeThreadPool")


def test_threadpool_executes_tasks():
    results = []

    def worker(x):
        time.sleep(0.01)
        results.append(x * 2)
        return x * 2

    with NativeThreadPool(max_workers=4) as pool:
        futures = [pool.submit(worker, i) for i in range(10)]
        values = [f.result(timeout=2.0) for f in futures]

    assert values == [i * 2 for i in range(10)]
    assert sorted(results) == [i * 2 for i in range(10)]


def test_threadpool_propagates_exceptions():

    def faulty():
        raise ValueError("boom")

    with NativeThreadPool(max_workers=1) as pool:
        future = pool.submit(faulty)
        with pytest.raises(ValueError):
            future.result(timeout=2.0)

