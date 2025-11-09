# -*- coding: utf-8 -*-
"""native_indicator - 技术指标原生化实现."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Sequence

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
    get_alert_logger,
)

if TYPE_CHECKING:
    from numpy import ndarray as _NDArrayFloat  # pragma: no cover
else:
    _NDArrayFloat = Any  # type: ignore[misc]

try:
    from . import native_indicator_core as _native_core  # type: ignore
except ImportError:
    _native_core = None  # type: ignore

CORE_AVAILABLE = bool(
    getattr(_native_core, "INDICATOR_AVAILABLE", False) if _native_core else False
)

_LOGGER = bind_logger_defaults(
    logging.getLogger("backend.native.indicator"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.indicator",
)
_ALERT_LOGGER = get_alert_logger(
    "backend.native.indicator.alert",
    scenario="backend.native.indicator",
)

if CORE_AVAILABLE:
    _LOGGER.debug(
        "native_indicator_core 加载完成",
        extra={
            "scenario": "backend.native.indicator",
            "native_module": "backend.native.indicator.core",
        },
    )
else:
    _LOGGER.warning(
        "native_indicator_core 未编译，将触发运行时降级",
        extra={
            "log_type": LogType.SYSTEM.value,
            "scenario": "backend.native.indicator",
            "native_module": "backend.native.indicator.core",
            "action_required": "compile_extension",
        },
    )

def _ensure_core_available() -> None:
    if not CORE_AVAILABLE or _native_core is None:
        _ALERT_LOGGER.error(
            "native_indicator_core 未加载，已降级到纯 Python 实现",
            extra={
                "log_type": LogType.ALERT.value,
                "scenario": "backend.native.indicator",
                "action_required": "compile_extension",
                "fallback": "python_indicator",
            },
        )
        raise RuntimeError(
            "native_indicator_core 未加载，无法执行技术指标计算。"
        )


def calculate_indicator(
    indicator_name: str,
    closes: Iterable[float],
    **params: float,
) -> Dict[str, List[float]] | List[float]:
    _ensure_core_available()
    return _native_core.calculate_indicator(indicator_name, closes, **params)  # type: ignore[arg-type]


def calculate_indicator_batch(
    indicator_name: str,
    datasets: Iterable[Sequence[float]],
    **params: float,
) -> List[Dict[str, List[float]] | List[float]]:
    _ensure_core_available()
    return _native_core.calculate_indicator_batch(  # type: ignore[arg-type]
        indicator_name, datasets, **params
    )


def sma(closes: Iterable[float], period: int = 5) -> List[float]:
    _ensure_core_available()
    return _native_core.sma(closes, period)  # type: ignore[arg-type]


def ema(closes: Iterable[float], period: int = 5) -> List[float]:
    _ensure_core_available()
    return _native_core.ema(closes, period)  # type: ignore[arg-type]


def macd(
    closes: Iterable[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Dict[str, List[float]]:
    _ensure_core_available()
    return _native_core.macd(closes, fast, slow, signal)  # type: ignore[arg-type]


def rsi(closes: Iterable[float], period: int = 14) -> List[float]:
    _ensure_core_available()
    return _native_core.rsi(closes, period)  # type: ignore[arg-type]


INDICATOR_AVAILABLE = CORE_AVAILABLE


__all__ = [
    "CORE_AVAILABLE",
    "INDICATOR_AVAILABLE",
    "calculate_indicator",
    "calculate_indicator_batch",
    "sma",
    "ema",
    "macd",
    "rsi",
]
