# -*- coding: utf-8 -*-
"""Type stubs for native_log_pipeline.pipeline C extension module."""

from typing import Any, Callable, Iterable, Optional

DEFAULT_BATCH_SIZE: int = 128
DEFAULT_FLUSH_MS: int = 2000

class Pipeline:
    """Native log pipeline for high-performance logging."""

    def __init__(self, *_args, **_kwargs) -> None: pass
    def push(self, _record: dict) -> bool:
        """Push a log record to the pipeline."""

    def take_batch(self) -> list:
        """Take a batch of records from the pipeline."""

    def pending(self) -> int:
        """Get the number of pending records."""

    def flush(self, _force: bool = False) -> bool:
        """Flush pending records."""

    def flush_and_close(self) -> bool:
        """Flush pending records and close the pipeline."""

    def set_fallback(self, _fallback: Callable[[Iterable[dict]], None]) -> None:
        """Set fallback callback for failed records."""

    def configure(self, *, _batch_size: int, _flush_ms: float) -> None:
        """Configure the pipeline."""

    def clear(self) -> list:
        """Clear the pipeline (deprecated)."""

    def stats(self) -> dict[str, Any]:
        """Get pipeline statistics."""

    def sqlite_path(self) -> Optional[str]:
        """Get the SQLite database path."""

def install(
    *,
    _batch_size: int = DEFAULT_BATCH_SIZE,
    _flush_ms: float = DEFAULT_FLUSH_MS,
    _fallback: Optional[Callable[[Iterable[dict]], None]] = None,
    _event_callback: Optional[Callable[[Iterable[dict]], None]] = None,
    _sqlite_path: Optional[str] = None,
    _enable_logging: bool = True,
) -> Pipeline:
    """Install and return a native pipeline instance."""

def get_version() -> str:
    """Get the version of the native pipeline."""
