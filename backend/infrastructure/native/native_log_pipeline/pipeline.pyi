# -*- coding: utf-8 -*-
"""Type stubs for native_log_pipeline.pipeline C extension module."""

from typing import Any, Callable, Iterable, Optional

DEFAULT_BATCH_SIZE: int = 128
DEFAULT_FLUSH_MS: int = 2000

class Pipeline:
    """Native log pipeline for high-performance logging."""

    def __init__(self, *args, **kwargs) -> None: ...

    def push(self, record: dict) -> None:
        """Push a log record to the pipeline."""
        ...

    def flush_and_close(self) -> None:
        """Flush pending records and close the pipeline."""
        ...

    def set_fallback(self, fallback: Callable[[Iterable[dict]], None]) -> None:
        """Set fallback callback for failed records."""
        ...

    def stats(self) -> dict[str, Any]:
        """Get pipeline statistics."""
        ...

def install(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    flush_ms: float = DEFAULT_FLUSH_MS,
    fallback: Optional[Callable[[Iterable[dict]], None]] = None,
    event_callback: Optional[Callable[[Iterable[dict]], None]] = None,
    sqlite_path: Optional[str] = None,
    enable_logging: bool = True,
) -> Pipeline:
    """Install and return a native pipeline instance."""
    ...

def get_version() -> str:
    """Get the version of the native pipeline."""
    ...
