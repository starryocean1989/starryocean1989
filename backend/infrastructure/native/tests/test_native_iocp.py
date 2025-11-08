# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

native_iocp = pytest.importorskip("backend.infrastructure.native.native_iocp")


@pytest.mark.skipif(
    not native_iocp.IOCP_AVAILABLE,
    reason="native_iocp 扩展不可用",
)
def test_aopen_supports_async_read(tmp_path: Path):
    sample_file = tmp_path / "iocp.txt"
    sample_file.write_bytes(b"hello iocp")

    async def runner() -> bytes:
        async with await native_iocp.aopen(sample_file, "rb") as handle:
            return await handle.read()

    data = asyncio.run(runner())
    assert data == b"hello iocp"


@pytest.mark.skipif(
    not (native_iocp.IOCP_AVAILABLE and getattr(native_iocp, "BATCH_AVAILABLE", False)),
    reason="native_iocp 批量接口不可用",
)
def test_batch_file_exists_reports_presence(tmp_path: Path):
    present = tmp_path / "exists.bin"
    missing = tmp_path / "missing.bin"
    present.write_bytes(b"batch")

    results = native_iocp.batch_file_exists([str(present), str(missing)])
    assert results == [True, False]

