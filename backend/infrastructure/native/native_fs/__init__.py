"""native_fs 文件系统原生加速模块接口."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from . import fs_watcher as _native_fs  # type: ignore
except Exception as exc:  # pragma: no cover - C 扩展缺失或加载失败时触发
    raise ImportError(
        "native_fs extension could not be imported. Please ensure it is built via "
        "`python setup.py build_ext --inplace` and that fs_watcher.pyd is present."
    ) from exc

FS_WATCH_AVAILABLE = getattr(_native_fs, "FS_WATCH_AVAILABLE", True)
if not FS_WATCH_AVAILABLE:
    raise ImportError("native_fs extension reported unavailable. Please rebuild the module.")

DirectoryWatcher = _native_fs.DirectoryWatcher  # type: ignore[misc,assignment]
watch_directory = _native_fs.watch_directory  # type: ignore[misc,assignment]
__version__ = getattr(_native_fs, "__version__", "1.0.0")

__all__ = ["FS_WATCH_AVAILABLE", "DirectoryWatcher", "watch_directory"]

