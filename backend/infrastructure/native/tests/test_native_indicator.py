# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from typing import Iterable, List, cast

import pytest

from backend.infrastructure.native.native_indicator import (
    CORE_AVAILABLE,
    INDICATOR_AVAILABLE,
    calculate_indicator,
    calculate_indicator_batch,
    ema,
    macd,
    rsi,
    sma,
)


def _ref_sma(values: Iterable[float], period: int) -> List[float]:
    data = list(values)
    out: List[float] = []
    running = 0.0
    for idx, value in enumerate(data):
        running += value
        if idx >= period:
            running -= data[idx - period]
        if idx + 1 < period:
            out.append(math.nan)
        else:
            out.append(running / period)
    return out


@pytest.mark.skipif(not INDICATOR_AVAILABLE, reason="native_indicator 不可用")
def test_sma_matches_reference():
    values = [1.0, 3.0, 5.0, 7.0, 9.0, 11.0]
    period = 3
    expected = _ref_sma(values, period)
    result = sma(values, period)
    assert len(result) == len(expected)
    for actual, exp in zip(result, expected):
        if math.isnan(exp):
            assert math.isnan(actual)
        else:
            assert pytest.approx(actual, rel=1e-9, abs=1e-9) == exp


@pytest.mark.skipif(not INDICATOR_AVAILABLE, reason="native_indicator 不可用")
def test_macd_output_structure():
    values = [float(i) for i in range(1, 21)]
    macd_result = macd(values)
    assert set(macd_result.keys()) == {"macd", "signal", "hist"}
    assert len(macd_result["macd"]) == len(values)
    assert len(macd_result["signal"]) == len(values)
    assert len(macd_result["hist"]) == len(values)


@pytest.mark.skipif(not INDICATOR_AVAILABLE, reason="native_indicator 不可用")
def test_calculate_indicator_batch_rsi():
    batch = [
        [1.0, 2.0, 3.0, 2.0, 1.0],
        [10.0, 11.0, 13.0, 15.0, 14.0, 16.0],
    ]
    results = calculate_indicator_batch("RSI", batch, period=3)
    assert len(results) == len(batch)
    for dataset, result in zip(batch, results):
        assert isinstance(result, list)
        result_list: List[float] = cast(List[float], result)
        assert len(result_list) == len(dataset)
        assert any(not math.isnan(x) for x in result_list)


@pytest.mark.skipif(not INDICATOR_AVAILABLE, reason="native_indicator 不可用")
def test_calculate_indicator_aliases():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    ema_result = calculate_indicator("ema", values, period=3)
    assert ema_result == ema(values, period=3)


def test_core_available_flag_type():
    assert isinstance(CORE_AVAILABLE, bool)

