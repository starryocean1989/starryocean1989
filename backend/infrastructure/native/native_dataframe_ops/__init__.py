# -*- coding: utf-8 -*-
"""native_dataframe_ops 模块导出."""

from __future__ import annotations

import platform
from typing import Any, Dict, Iterable, List, cast

import pandas as pd

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    log_from_native,
    native_call_guard,
)

_COMPONENT_WRAPPER = "backend.native.dataframe_ops.wrapper"
_COMPONENT_FALLBACK = "backend.native.dataframe_ops.fallback"

__all__ = [
    "DATAFRAME_OPS_AVAILABLE",
    "dataframe_to_records",
    "dataframe_quality_counters",
    "scan_quality",
    "validate_numeric",
    "filter_symbols",
]


def _scan_quality_py(df: pd.DataFrame, columns: Iterable[str]) -> Dict[str, Any]:
    """纯 Python 兜底实现：统计重复与无效数据."""

    duplicate_count = int(df.index.duplicated().sum())

    missing_columns = [col for col in columns if col not in df.columns]
    if missing_columns:
        invalid_count = len(df)
    else:
        invalid_mask = df.loc[:, list(columns)].isna().any(axis=1)
        invalid_count = int(invalid_mask.sum())

    return {
        "duplicate_count": duplicate_count,
        "invalid_count": invalid_count,
        "total": len(df),
        "missing_columns": missing_columns,
    }


def _validate_numeric_py(
    df: pd.DataFrame,
    columns: Iterable[str],
    *,
    fill_value: float = 0.0,
) -> pd.DataFrame:
    """纯 Python 兜底实现：将指定列转为数值并填充缺失."""

    if not columns:
        return df

    converted = df.copy()
    for column in columns:
        if column not in converted.columns:
            continue
        numeric_array = pd.to_numeric(converted[column], errors="coerce")
        numeric_series = pd.Series(numeric_array, index=converted.index)
        converted[column] = numeric_series.fillna(fill_value)
    return converted


def _filter_symbols_py(
    records: Iterable[Dict[str, Any]],
    *,
    deduplicate: bool = True,
    drop_empty_code: bool = True,
    require_name: bool = False,
) -> List[Dict[str, Any]]:
    """纯 Python 兜底实现：过滤与去重品种列表。"""

    seen_codes: set[str] = set()
    filtered: List[Dict[str, Any]] = []

    for symbol in records:
        if not isinstance(symbol, dict):
            continue

        raw_code = symbol.get("code")
        if raw_code is None:
            continue

        code_text = str(raw_code).strip()
        if drop_empty_code and not code_text:
            continue

        if require_name:
            raw_name = symbol.get("name")
            if raw_name is None or str(raw_name).strip() == "":
                continue

        if deduplicate:
            if code_text in seen_codes:
                continue
            seen_codes.add(code_text)

        filtered.append(symbol)

    return filtered


def _raise_import_error(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover - 构建失败
    raise ImportError("native_dataframe_ops extension is not compiled")


def _raise_platform_error(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover - 非Windows
    raise RuntimeError("native_dataframe_ops only supports Windows platform")


if platform.system() == "Windows":
    try:
        from . import dataframe_ops as _native_ops  # type: ignore[import]

        @native_call_guard(component=_COMPONENT_WRAPPER)
        def dataframe_to_records(  # type: ignore[override]
            df: pd.DataFrame,
            include_index: bool = False,
            index_field: str | None = None,
        ) -> Any:
            return _native_ops.dataframe_to_records(df, include_index, index_field)  # type: ignore[attr-defined]

        @native_call_guard(component=_COMPONENT_WRAPPER)
        def dataframe_quality_counters(  # type: ignore[override]
            df: pd.DataFrame, columns: Iterable[str]
        ) -> Any:
            """调用原生实现，遇到 pandas any 参数兼容问题时回退到 Python 逻辑."""

            try:
                return _native_ops.dataframe_quality_counters(df, list(columns))  # type: ignore[attr-defined]
            except TypeError as error:
                # 兼容 pandas.DataFrame.any 新签名（额外位置参数会触发 TypeError）
                if "DataFrame.any" in str(error):
                    stats = _scan_quality_py(df, columns)
                    log_from_native(
                        NativeLogLevel.WARNING,
                        _COMPONENT_WRAPPER,
                        "dataframe_quality_counters",
                        0,
                        "fallback to python implementation due to pandas API change",
                        details="pandas.DataFrame.any signature mismatch",
                    )
                    return stats["duplicate_count"], stats["invalid_count"]
                raise

        _native_scan_quality = getattr(_native_ops, "scan_quality", None)
        if _native_scan_quality is not None:
            @native_call_guard(component=_COMPONENT_WRAPPER)
            def scan_quality(  # type: ignore[override]
                df: pd.DataFrame, columns: Iterable[str]
            ) -> Dict[str, Any]:
                return cast(Dict[str, Any], _native_scan_quality(df, list(columns)))
        else:
            scan_quality = _scan_quality_py  # type: ignore[assignment]

        _native_validate_numeric = getattr(_native_ops, "validate_numeric", None)
        if _native_validate_numeric is not None:
            @native_call_guard(component=_COMPONENT_WRAPPER)
            def validate_numeric(  # type: ignore[override]
                df: pd.DataFrame,
                columns: Iterable[str],
                *,
                fill_value: float = 0.0,
            ) -> pd.DataFrame:
                return cast(
                    pd.DataFrame,
                    _native_validate_numeric(df, list(columns), fill_value=fill_value),
                )
        else:
            validate_numeric = _validate_numeric_py  # type: ignore[assignment]

        _native_filter_symbols = getattr(_native_ops, "filter_symbols", None)
        if _native_filter_symbols is not None:
            @native_call_guard(component=_COMPONENT_WRAPPER)
            def filter_symbols(  # type: ignore[override]
                records: Iterable[Dict[str, Any]],
                *,
                deduplicate: bool = True,
                drop_empty_code: bool = True,
                require_name: bool = False,
            ) -> List[Dict[str, Any]]:
                return cast(
                    List[Dict[str, Any]],
                    _native_filter_symbols(
                        list(records),
                        deduplicate=deduplicate,
                        drop_empty_code=drop_empty_code,
                        require_name=require_name,
                    ),
                )
        else:
            filter_symbols = _filter_symbols_py  # type: ignore[assignment]

        DATAFRAME_OPS_AVAILABLE = True
    except ImportError:  # pragma: no cover - 构建失败
        DATAFRAME_OPS_AVAILABLE = False
        log_from_native(
            NativeLogLevel.ERROR,
            _COMPONENT_FALLBACK,
            "import_dataframe_ops",
            0,
            "native_dataframe_ops extension not available; falling back to Python implementation",
        )
        dataframe_to_records = _raise_import_error  # type: ignore[assignment]
        dataframe_quality_counters = _raise_import_error  # type: ignore[assignment]
        scan_quality = _scan_quality_py  # type: ignore[assignment]
        validate_numeric = _validate_numeric_py  # type: ignore[assignment]
        filter_symbols = _filter_symbols_py  # type: ignore[assignment]
else:  # pragma: no cover
    DATAFRAME_OPS_AVAILABLE = False
    log_from_native(
        NativeLogLevel.WARNING,
        _COMPONENT_FALLBACK,
        "platform_guard",
        0,
        "native_dataframe_ops only supports Windows; Python fallback in use",
        details=f"current_platform={platform.system()}",
    )
    dataframe_to_records = _raise_platform_error  # type: ignore[assignment]
    dataframe_quality_counters = _raise_platform_error  # type: ignore[assignment]
    scan_quality = _scan_quality_py  # type: ignore[assignment]
    validate_numeric = _validate_numeric_py  # type: ignore[assignment]
    filter_symbols = _filter_symbols_py  # type: ignore[assignment]


