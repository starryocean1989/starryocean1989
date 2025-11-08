# -*- coding: utf-8 -*-
"""
native_async - 异步任务结果归约模块。

提供 `reduce_task_results`，在 C++ 层完成批量统计，并在不可用时自动回退到 Python 实现。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from .async_reduce import reduce_task_results  # type: ignore

    ASYNC_REDUCE_AVAILABLE = True
except ImportError:
    ASYNC_REDUCE_AVAILABLE = False

    def reduce_task_results(  # type: ignore[misc]
        task_results: Iterable[Any],
        *,
        total: int,
        progress_stride: int = 0,
        progress_callback: Optional[Any] = None,
        symbols: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        """Python 回退实现."""

        items: List[Tuple[Any, Any]] = []
        errors: List[str] = []
        milestones: List[Tuple[int, int, int, int]] = []
        error_symbols: List[Any] = []

        completed = 0
        success_count = 0
        null_count = 0
        error_count = 0
        stride = max(0, int(progress_stride))

        symbol_list: List[Any] = list(symbols) if symbols is not None else []

        for entry in task_results:
            completed += 1
            symbol: Any = None
            value = None
            if symbol_list and completed - 1 < len(symbol_list):
                symbol = symbol_list[completed - 1]

            if isinstance(entry, Exception):
                error_count += 1
                errors.append(f"{symbol or 'Unknown'}: {entry}")
                error_symbols.append(symbol)
            elif isinstance(entry, tuple) and len(entry) == 2:
                symbol, value = entry
                if isinstance(value, Exception):
                    error_count += 1
                    errors.append(f"{symbol}: {value}")
                    error_symbols.append(symbol)
                    value = None
                    items.append((symbol, value))
                    null_count += 1
                    if stride > 0 and (completed % stride == 0 or completed == total):
                        milestones.append((completed, success_count, null_count, error_count))
                    continue
                items.append((symbol, value))

                if value is not None:
                    success_count += 1
                else:
                    null_count += 1

                if progress_callback is not None:
                    try:
                        progress_callback(completed, total, symbol)
                    except Exception as callback_err:  # noqa: BLE001
                        errors.append(f"[progress-callback] {callback_err}")
                        error_symbols.append(symbol)
            else:
                error_count += 1
                errors.append(repr(entry))
                error_symbols.append(symbol)

            if stride > 0 and (completed % stride == 0 or completed == total):
                milestones.append((completed, success_count, null_count, error_count))

        summary = {
            "total": completed,
            "success_count": success_count,
            "null_count": null_count,
            "error_count": error_count,
        }

        return {
            "summary": summary,
            "items": items,
            "errors": errors,
            "error_symbols": error_symbols,
            "milestones": milestones,
        }

__all__ = ["reduce_task_results", "ASYNC_REDUCE_AVAILABLE"]


