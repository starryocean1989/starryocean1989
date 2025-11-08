import importlib

import pytest

native_queue_module = importlib.import_module("backend.infrastructure.native.native_queue")
NativeQueue = getattr(native_queue_module, "NativeQueue")


def test_queue_push_pop_roundtrip():
    queue = NativeQueue(capacity=4)

    for i in range(10):
        queue.push(i)

    assert queue.size() == 10

    values = [queue.pop() for _ in range(10)]
    assert values == list(range(10))
    assert queue.pop() is None
    assert queue.size() == 0


def test_queue_clear():
    queue = NativeQueue()
    for i in range(5):
        queue.push(i)
    queue.clear()
    assert queue.size() == 0
    assert queue.pop() is None

