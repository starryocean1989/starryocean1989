# -*- coding: utf-8 -*-
"""native_indicator - 技术指标原生化（Python 兼容实现）.

该模块提供无依赖的 SMA/EMA/MACD/RSI 计算，优先作为 native C 扩展的占位
实现，便于在缺失二进制组件时保持一致的接口体验。
"""

from __future__ import annotations

from typing import Dict, Iterable, List

try:  # 优先使用 numpy 进行向量化计算
    import numpy as _np
except ImportError:  # pragma: no cover - numpy 始终存在于项目依赖中
    _np = None  # type: ignore


INDICATOR_AVAILABLE = _np is not None


def _ensure_array(values: Iterable[float]) -> "_np.ndarray":
    if _np is None:
        raise ImportError("numpy is required for native_indicator")
    arr = _np.asarray(list(values), dtype=_np.float64)
    if arr.ndim != 1:
        arr = arr.reshape(-1)
    return arr


def _sma(values: "_np.ndarray", period: int) -> "_np.ndarray":
    if period <= 0:
        raise ValueError("period must be positive")
    if period > values.size:
        period = values.size
    cumsum = _np.cumsum(values, dtype=_np.float64)
    cumsum[period:] = cumsum[period:] - cumsum[:-period]
    result = _np.empty_like(values, dtype=_np.float64)
    result[: period - 1] = _np.nan
    result[period - 1 :] = cumsum[period - 1 :] / period
    return result


def _ema(values: "_np.ndarray", period: int) -> "_np.ndarray":
    if period <= 0:
        raise ValueError("period must be positive")
    alpha = 2.0 / (period + 1.0)
    result = _np.empty_like(values, dtype=_np.float64)
    result[:] = _np.nan
    if values.size == 0:
        return result
    result[0] = values[0]
    for idx in range(1, values.size):
        result[idx] = alpha * values[idx] + (1 - alpha) * result[idx - 1]
    return result


def _macd(values: "_np.ndarray", fast: int, slow: int, signal: int) -> Dict[str, List[float]]:
    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return {
        "macd": macd_line.tolist(),
        "signal": signal_line.tolist(),
        "hist": hist.tolist(),
    }


def _rsi(values: "_np.ndarray", period: int) -> "_np.ndarray":
    if period <= 0:
        raise ValueError("period must be positive")
    deltas = _np.diff(values)
    rsi = _np.empty(values.size, dtype=_np.float64)
    rsi[:] = _np.nan
    if deltas.size == 0:
        return rsi

    gains = _np.where(deltas > 0, deltas, 0.0)
    losses = _np.where(deltas < 0, -deltas, 0.0)

    avg_gain = _np.empty_like(deltas, dtype=_np.float64)
    avg_loss = _np.empty_like(deltas, dtype=_np.float64)

    avg_gain[0] = gains[:period].mean() if period <= gains.size else gains.mean()
    avg_loss[0] = losses[:period].mean() if period <= losses.size else losses.mean()

    for idx in range(1, deltas.size):
        avg_gain[idx] = (avg_gain[idx - 1] * (period - 1) + gains[idx]) / period
        avg_loss[idx] = (avg_loss[idx - 1] * (period - 1) + losses[idx]) / period

    rs = _np.divide(
        avg_gain,
        avg_loss,
        out=_np.zeros_like(avg_gain),
        where=avg_loss != 0,
    )
    rsi_values = 100.0 - (100.0 / (1.0 + rs))
    rsi[period:] = rsi_values[period - 1 :]
    return rsi


def calculate_indicator(
    indicator_name: str,
    closes: Iterable[float],
    **params: float,
) -> Dict[str, List[float]] | List[float]:
    """计算单个指标."""

    if not INDICATOR_AVAILABLE:
        raise ImportError("native_indicator requires numpy")

    values = _ensure_array(closes)
    name_upper = (indicator_name or "").upper()

    if name_upper == "SMA":
        period = int(params.get("period", 5))
        return _sma(values, period).tolist()
    if name_upper == "EMA":
        period = int(params.get("period", 5))
        return _ema(values, period).tolist()
    if name_upper == "MACD":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        return _macd(values, fast, slow, signal)
    if name_upper == "RSI":
        period = int(params.get("period", 14))
        return _rsi(values, period).tolist()

    raise ValueError(f"Unsupported indicator: {indicator_name}")


def calculate_indicator_batch(
    indicator_name: str,
    datasets: Iterable[Sequence[float]],
    **params: float,
) -> List[Dict[str, List[float]] | List[float]]:
    """批量计算指定指标."""

    results: List[Dict[str, List[float]] | List[float]] = []
    for dataset in datasets:
        results.append(calculate_indicator(indicator_name, dataset, **params))
    return results


__all__ = [
    "INDICATOR_AVAILABLE",
    "calculate_indicator",
    "calculate_indicator_batch",
]
