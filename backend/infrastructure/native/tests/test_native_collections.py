# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

collections = pytest.importorskip("backend.infrastructure.native.native_collections")


@pytest.mark.skipif(
    not collections.COLLECTIONS_AVAILABLE,
    reason="native_collections 扩展不可用",
)
def test_high_perf_lru_cache_eviction_order():
    cache = collections.HighPerfLRUCache(2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1

    cache.set("c", 3)
    # 'b' should be evicted, 'a' should remain because it was recently used
    with pytest.raises(KeyError):
        cache.get("b")
    assert cache.get("a") == 1
    assert cache.get("c") == 3


@pytest.mark.skipif(
    not collections.COLLECTIONS_AVAILABLE,
    reason="native_collections 扩展不可用",
)
def test_high_perf_priority_queue_orders_by_priority():
    queue = collections.HighPerfPriorityQueue()
    queue.put("low", 1)
    queue.put("high", 10)
    queue.put("middle", 5)

    assert queue.get() == "high"
    assert queue.get() == "middle"
    assert queue.get() == "low"

