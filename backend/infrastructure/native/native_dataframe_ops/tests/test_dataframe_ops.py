# -*- coding: utf-8 -*-
"""native_dataframe_ops 单元测试."""

import platform

import pandas as pd
import pytest

from typing import List

from backend.infrastructure.native.native_dataframe_ops import (
    DATAFRAME_OPS_AVAILABLE,
    dataframe_quality_counters,
    dataframe_to_records,
    filter_symbols,
    scan_quality,
    validate_numeric,
)


WINDOWS = platform.system() == "Windows"


@pytest.mark.skipif(not (WINDOWS and DATAFRAME_OPS_AVAILABLE), reason="native_dataframe_ops 不可用")
def test_dataframe_to_records_basic():
    df = pd.DataFrame({"code": ["000001", "000002"], "name": ["平安银行", "万 科Ａ"]})
    records = dataframe_to_records(df)
    assert isinstance(records, list)
    assert len(records) == 2
    assert records[0]["code"] == "000001"
    assert records[1]["name"] == "万 科Ａ"


@pytest.mark.skipif(not (WINDOWS and DATAFRAME_OPS_AVAILABLE), reason="native_dataframe_ops 不可用")
def test_dataframe_to_records_with_index():
    df = pd.DataFrame({"value": [1, 2, 3]})
    df.index.name = "datetime"
    records = dataframe_to_records(df, include_index=True, index_field="datetime")
    assert records[0]["datetime"] == 0
    assert records[1]["value"] == 2


@pytest.mark.skipif(not (WINDOWS and DATAFRAME_OPS_AVAILABLE), reason="native_dataframe_ops 不可用")
def test_dataframe_quality_counters():
    df = pd.DataFrame(
        {
            "open": [1.0, None, 3.0],
            "high": [1.1, None, 3.1],
            "low": [0.9, None, 2.9],
            "close": [1.05, None, 3.05],
        }
    )
    df = pd.concat([df, df.iloc[[2]]], axis=0)
    df.index = [0, 1, 2, 2]
    duplicate_count, invalid_count = dataframe_quality_counters(df, ["open", "high", "low", "close"])
    assert duplicate_count == 1
    assert invalid_count == 1


@pytest.mark.skipif(not (WINDOWS and DATAFRAME_OPS_AVAILABLE), reason="native_dataframe_ops 不可用")
def test_scan_quality_returns_expected_structure():
    df = pd.DataFrame(
        {
            "open": [1.0, None, 3.0],
            "close": [1.1, 2.2, None],
        },
        index=[0, 0, 1],  # type: ignore
    )

    stats = scan_quality(df, ["open", "close"])
    assert isinstance(stats, dict)
    assert stats["duplicate_count"] == 1
    assert stats["invalid_count"] == 2
    assert stats["total"] == 3
    assert stats["missing_columns"] == []


@pytest.mark.skipif(not (WINDOWS and DATAFRAME_OPS_AVAILABLE), reason="native_dataframe_ops 不可用")
def test_validate_numeric_coerces_values_and_fills():
    df = pd.DataFrame(
        {
            "price": ["1.0", "invalid", None, "3.5"],
            "volume": ["10", "20", "oops", None],
        }
    )

    converted = validate_numeric(df, ["price", "volume"], fill_value=-1.0)
    assert converted["price"].tolist() == pytest.approx([1.0, -1.0, -1.0, 3.5])
    assert converted["volume"].tolist() == pytest.approx([10.0, 20.0, -1.0, -1.0])


