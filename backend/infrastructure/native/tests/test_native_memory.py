# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

memory = pytest.importorskip("backend.infrastructure.native.native_memory")


@pytest.mark.skipif(
    not memory.MEMORY_AVAILABLE,
    reason="native_memory 扩展不可用",
)
def test_zero_copy_memory_view_updates_source():
    data = bytearray(b"hello")
    wrapper = memory.ZeroCopyMemory(data)

    view = wrapper.view()
    assert isinstance(view, memoryview)
    view[0] = ord("H")

    assert data == bytearray(b"Hello")
    assert wrapper.get_size() == len(data)


@pytest.mark.skipif(
    not memory.MEMORY_AVAILABLE,
    reason="native_memory 扩展不可用",
)
def test_memory_pool_alloc_and_free():
    pool = memory.MemoryPool(16, 3)
    block = pool.alloc()
    assert isinstance(block, memoryview)
    assert len(block) == 16

    pool.free(block)
    assert pool.size() == 16
    assert pool.capacity() == 3

