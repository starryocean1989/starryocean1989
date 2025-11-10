# -*- coding: utf-8 -*-
"""native_fs 模块测试."""

import platform
import threading
import time
from pathlib import Path

import pytest

from backend.infrastructure.native.native_fs import (
    FS_WATCH_AVAILABLE,
    DirectoryWatcher,
    watch_directory,
)


WINDOWS = platform.system() == "Windows"


@pytest.mark.skipif(not (WINDOWS and FS_WATCH_AVAILABLE), reason="native_fs 扩展不可用")
def test_watch_directory_receives_events(tmp_path: Path) -> None:
    events = []
    event_set = threading.Event()

    def _callback(event: dict) -> None:
        events.append(event)
        event_set.set()

    watcher = watch_directory(
        str(tmp_path),
        _callback,
        recursive=False,
        buffer_size=64 * 1024,
    )
    try:
        target = tmp_path / "demo.parquet"
        target.write_text("hello", encoding="utf-8")

        # 等待事件回调到达（最多等待 3 秒）
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if event_set.wait(0.1):
                break
        assert events, "native_fs 未捕获到文件事件"
        assert any(
            isinstance(evt, dict)
            and evt.get("event") in {"created", "modified", "renamed_new"}
            and Path(str(evt.get("name", ""))).name == "demo.parquet"
            for evt in events
        ), f"回调事件缺少预期内容: {events!r}"
    finally:
        watcher.stop()

