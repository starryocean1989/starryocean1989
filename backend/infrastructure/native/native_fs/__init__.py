# -*- coding: utf-8 -*-
"""native_fs 文件系统原生加速模块接口.

阶段11埋点：记录关键文件系统调用的参数与返回码，便于排查权限/资源问题
"""

from __future__ import annotations

import platform
from typing import Callable, Optional

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    log_from_native,
    native_call_guard,
)

_COMPONENT_WRAPPER = "backend.native.fs.wrapper"
_COMPONENT_FALLBACK = "backend.native.fs.fallback"

__all__ = [
    "FS_WATCH_AVAILABLE",
    "DirectoryWatcher",
    "watch_directory",
]

if platform.system() == "Windows":
    try:
        from .fs_watcher import DirectoryWatcher, watch_directory as _watch_directory  # type: ignore[import]

        FS_WATCH_AVAILABLE: bool = True

        @native_call_guard(component=_COMPONENT_WRAPPER)
        def watch_directory(  # type: ignore[override]
            path: str,
            callback: Callable[[dict], None],
            *,
            recursive: bool = True,
            buffer_size: int = 64 * 1024,
            coalesce_interval_ms: Optional[int] = None,
        ) -> DirectoryWatcher:
            return _watch_directory(
                path,
                callback,
                recursive=recursive,
                buffer_size=buffer_size,
                coalesce_interval_ms=coalesce_interval_ms,
            )
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
            # 阶段11埋点：记录native_fs扩展未编译的情况
            log_from_native(
                NativeLogLevel.ERROR,
                _COMPONENT_FALLBACK,
                "watch_directory",
                0,
                "native_fs extension not compiled; raising ImportError",
                details=f"path={path}, recursive={recursive}, buffer_size={buffer_size}",
            )
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
        # 阶段11埋点：记录平台不支持的情况
        log_from_native(
            NativeLogLevel.WARNING,
            _COMPONENT_FALLBACK,
            "watch_directory",
            0,
            "native_fs only supports Windows; raising RuntimeError",
            details=f"platform={platform.system()}, path={path}, recursive={recursive}, buffer_size={buffer_size}",
        )
        raise RuntimeError("native_fs only supports Windows platform")


