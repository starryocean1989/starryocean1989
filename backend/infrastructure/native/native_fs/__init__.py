# -*- coding: utf-8 -*-
"""native_fs 文件系统原生加速模块接口."""

from __future__ import annotations

import platform
from typing import Callable, Optional

__all__ = [
    "FS_WATCH_AVAILABLE",
    "DirectoryWatcher",
    "watch_directory",
]

if platform.system() == "Windows":
    try:
        from .fs_watcher import DirectoryWatcher, watch_directory  # type: ignore[import]

        FS_WATCH_AVAILABLE: bool = True
    except ImportError:  # pragma: no cover - 构建失败时降级
        FS_WATCH_AVAILABLE = False

        class DirectoryWatcher:  # type: ignore[no-redef]
            """占位 DirectoryWatcher，提示扩展未编译."""

            def __init__(self, *_args, **_kwargs) -> None:
                raise ImportError("native_fs extension is not compiled")

        def watch_directory(  # type: ignore[override]
            path: str,
            callback: Callable[[dict], None],
            *,
            recursive: bool = True,
            buffer_size: int = 64 * 1024,
            coalesce_interval_ms: Optional[int] = None,
        ) -> DirectoryWatcher:
            raise ImportError("native_fs extension is not compiled")

else:  # pragma: no cover - 非Windows平台降级
    FS_WATCH_AVAILABLE = False

    class DirectoryWatcher:  # type: ignore[no-redef]
        """占位 DirectoryWatcher，提示平台不支持."""

        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("native_fs only supports Windows platform")

    def watch_directory(  # type: ignore[override]
        path: str,
        callback: Callable[[dict], None],
        *,
        recursive: bool = True,
        buffer_size: int = 64 * 1024,
        coalesce_interval_ms: Optional[int] = None,
    ) -> DirectoryWatcher:
        raise RuntimeError("native_fs only supports Windows platform")


