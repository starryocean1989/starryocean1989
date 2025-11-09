# -*- coding: utf-8 -*-
"""
Unified DataConverter wrapper

- Uses native `native_dataconverter` (pybind11 C++) to convert list-of-dicts records
  into standardized bar field dicts that match vnpy.BarData constructor names.
- Provides helper to construct vnpy.BarData objects with best-effort field mapping
  without changing existing architecture.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Iterable, List, Optional

from backend.services.vnpy_imports import BarData, VNPY_AVAILABLE  # type: ignore

# Try to import native dataconverter; if not on sys.path, attempt local loading
try:
    import native_dataconverter  # type: ignore
    _NATIVE_AVAILABLE = True
except Exception:
    native_dataconverter = None  # type: ignore
    _NATIVE_AVAILABLE = False
    try:
        import importlib.util
        from pathlib import Path
        base = Path(__file__).resolve().parents[1] / "native" / "native_dataconverter"
        candidates = list(base.glob("native_dataconverter*.pyd"))
        if candidates:
            spec = importlib.util.spec_from_file_location("native_dataconverter", str(candidates[0]))
            if spec and spec.loader:
                native_dataconverter = importlib.util.module_from_spec(spec)  # type: ignore
                spec.loader.exec_module(native_dataconverter)  # type: ignore
                _NATIVE_AVAILABLE = True
    except Exception:
        native_dataconverter = None  # type: ignore
        _NATIVE_AVAILABLE = False


def records_to_bar_fields(
    records: Iterable[Dict[str, Any]],
    symbol: str,
    exchange: str,
) -> List[Dict[str, Any]]:
    """Convert raw records (list of dicts) to unified bar field dicts.

    Returns list of dicts keyed as:
      symbol, exchange, datetime(str), open_price, high_price, low_price, close_price, volume, turnover
    """
    if _NATIVE_AVAILABLE:
        return list(native_dataconverter.convert_records_to_bar_fields(list(records), symbol, exchange))  # type: ignore

    # Fallback pure Python implementation (slower)
    out: List[Dict[str, Any]] = []
    for r in records:
        dt = r.get("datetime") or (
            f"{r.get('date','')} {r.get('time','')}".strip()
        ) or r.get("timestamp", "")
        out.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "datetime": dt,
                "open_price": r.get("open", r.get("open_price", 0.0)),
                "high_price": r.get("high", r.get("high_price", 0.0)),
                "low_price": r.get("low", r.get("low_price", 0.0)),
                "close_price": r.get("close", r.get("close_price", 0.0)),
                "volume": r.get("volume", r.get("vol", 0)) or 0,
                "turnover": r.get("turnover", r.get("amount", 0.0)) or 0.0,
            }
        )
    return out


def _parse_datetime(dt: Any) -> Optional[_dt.datetime]:
    if isinstance(dt, _dt.datetime):
        return dt
    if isinstance(dt, (int, float)):
        try:
            return _dt.datetime.fromtimestamp(float(dt))
        except Exception:
            return None
    if isinstance(dt, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
            try:
                return _dt.datetime.strptime(dt, fmt)
            except Exception:
                continue
    return None


def bar_fields_to_vnpy_bars(
    fields_list: Iterable[Dict[str, Any]],
    interval: Optional[str] = None,
) -> List[Any]:
    """Construct vnpy.BarData objects from unified bar field dicts.

    Best-effort: tries `BarData(**fields)` then falls back to common constructor params.
    If vnpy is not available, returns the input dicts unchanged.
    """
    if not VNPY_AVAILABLE or BarData is None:
        return list(fields_list)  # pass-through for environments without vnpy

    bars: List[Any] = []
    for f in fields_list:
        dt_obj = _parse_datetime(f.get("datetime"))
        base = {
            "symbol": f.get("symbol"),
            "exchange": f.get("exchange"),
            "datetime": dt_obj or f.get("datetime"),
            "open_price": f.get("open_price", 0.0),
            "high_price": f.get("high_price", 0.0),
            "low_price": f.get("low_price", 0.0),
            "close_price": f.get("close_price", 0.0),
            "volume": f.get("volume", 0),
            "turnover": f.get("turnover", 0.0),
        }
        if interval is not None:
            base["interval"] = interval

        # Try direct dataclass-style init
        try:
            bar = BarData(**base)  # type: ignore
            bars.append(bar)
            continue
        except Exception:
            pass

        # Fallback: attribute assignment after empty init (if supported)
        try:
            bar = BarData()  # type: ignore
            for k, v in base.items():
                try:
                    setattr(bar, k, v)
                except Exception:
                    pass
            bars.append(bar)
            continue
        except Exception:
            # Final fallback: return dict
            bars.append(base)
    return bars


def convert_records_to_vnpy_bars(
    records: Iterable[Dict[str, Any]],
    symbol: str,
    exchange: str,
    interval: Optional[str] = None,
) -> List[Any]:
    """Convenience: records -> unified fields (native) -> vnpy.BarData list."""
    fields = records_to_bar_fields(records, symbol, exchange)
    return bar_fields_to_vnpy_bars(fields, interval=interval)
