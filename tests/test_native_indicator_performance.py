# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import random
import time
from typing import Iterable, List

import pytest

from backend.infrastructure.native.native_indicator import (
    CORE_AVAILABLE,
    calculate_indicator,
)


def _python_rsi(values: Iterable[float], period: int) -> List[float]:
    data = list(values)
    if len(data) < 2:
        return [float("nan")] * len(data)

    deltas = [b - a for a, b in zip(data[:-1], data[1:])]
    rsi = [float("nan")] * len(data)
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rs = avg_gain / avg_loss if avg_loss else 0.0
    rsi_value = 100.0 - (100.0 / (1.0 + rs)) if avg_loss else 100.0
    if period < len(rsi):
        rsi[period] = rsi_value

    for idx in range(period + 1, len(data)):
        gain = gains[idx - 1]
        loss = losses[idx - 1]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        if avg_loss == 0:
            rsi[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[idx] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


@pytest.mark.skipif(
    not CORE_AVAILABLE,
    reason="native_indicator_core 未编译，跳过性能基准",
)
@pytest.mark.skipif(
    os.getenv("RUN_NATIVE_INDICATOR_PERF") not in {"1", "true", "TRUE"},
    reason="未设置 RUN_NATIVE_INDICATOR_PERF 环境变量，默认跳过性能测试",
)
def test_native_indicator_rsi_performance(capsys):
    random.seed(42)
    dataset = [random.uniform(80, 120) for _ in range(1000)]
    period = 14
    iterations = 200

    # 预热
    calculate_indicator("RSI", dataset, period=period)
    _python_rsi(dataset, period)

    start_native = time.perf_counter()
    for _ in range(iterations):
        calculate_indicator("RSI", dataset, period=period)
    native_elapsed = time.perf_counter() - start_native

    start_py = time.perf_counter()
    for _ in range(iterations):
        _python_rsi(dataset, period)
    python_elapsed = time.perf_counter() - start_py

    speedup = python_elapsed / native_elapsed if native_elapsed else float("inf")

    print(
        f"native RSI elapsed={native_elapsed:.6f}s, "
        f"python elapsed={python_elapsed:.6f}s, "
        f"speedup={speedup:.2f}x"
    )

    captured = capsys.readouterr().out.strip()
    assert captured  # 确保输出存在，便于记录

