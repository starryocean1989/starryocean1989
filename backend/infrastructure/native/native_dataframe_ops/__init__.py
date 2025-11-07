# -*- coding: utf-8 -*-
"""native_dataframe_ops 模块导出."""

from __future__ import annotations

import platform
from typing import Any, Dict, Iterable, List, cast

import pandas as pd

__all__ = [
    "DATAFRAME_OPS_AVAILABLE",
    "dataframe_to_records",
    "dataframe_quality_counters",
    "scan_quality",
    "validate_numeric",
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


def _raise_import_error(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover - 构建失败
    raise ImportError("native_dataframe_ops extension is not compiled")


def _raise_platform_error(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover - 非Windows
    raise RuntimeError("native_dataframe_ops only supports Windows platform")


if platform.system() == "Windows":
    try:
        from . import dataframe_ops as _native_ops  # type: ignore[import]

        dataframe_quality_counters = _native_ops.dataframe_quality_counters  # type: ignore[attr-defined]
        dataframe_to_records = _native_ops.dataframe_to_records  # type: ignore[attr-defined]
        scan_quality = getattr(_native_ops, "scan_quality", _scan_quality_py)
        validate_numeric = getattr(_native_ops, "validate_numeric", _validate_numeric_py)
        DATAFRAME_OPS_AVAILABLE = True
    except ImportError:  # pragma: no cover - 构建失败
        DATAFRAME_OPS_AVAILABLE = False
        dataframe_to_records = _raise_import_error  # type: ignore[assignment]
        dataframe_quality_counters = _raise_import_error  # type: ignore[assignment]
        scan_quality = _scan_quality_py  # type: ignore[assignment]
        validate_numeric = _validate_numeric_py  # type: ignore[assignment]
else:  # pragma: no cover
    DATAFRAME_OPS_AVAILABLE = False
    dataframe_to_records = _raise_platform_error  # type: ignore[assignment]
    dataframe_quality_counters = _raise_platform_error  # type: ignore[assignment]
    scan_quality = _scan_quality_py  # type: ignore[assignment]
    validate_numeric = _validate_numeric_py  # type: ignore[assignment]


