import sys
import types

import pandas as pd
import pytest


if "native_calendar" not in sys.modules:
    stub_module = types.ModuleType("native_calendar")

    class _StubNativeCalendar:  # pragma: no cover - simple stub
        def __init__(self, *args, **kwargs):
            pass

    setattr(stub_module, "NativeCalendar", _StubNativeCalendar)
    sys.modules["native_calendar"] = stub_module


from backend.infrastructure.tdx_asyncio.utils import adjustments


def _build_sample_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime([
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
    ])

    bfq_data = pd.DataFrame(
        {
            "open": [10.0, 10.5, 10.2, 10.3],
            "high": [10.6, 10.8, 10.4, 10.5],
            "low": [9.8, 10.1, 9.9, 10.0],
            "close": [10.2, 10.6, 10.1, 10.4],
            "volume": [1000.0, 1200.0, 1100.0, 1050.0],
        },
        index=dates,
    )

    xdxr_data = pd.DataFrame(
        {
            "category": [1, 1, 1, 1],
            "fenhong": [0.0, 0.0, 0.5, 0.0],
            "peigu": [0.0, 0.0, 0.2, 0.0],
            "peigujia": [0.0, 0.0, 8.0, 0.0],
            "songzhuangu": [0.0, 0.0, 0.1, 0.0],
        },
        index=dates,
    )

    return bfq_data, xdxr_data


@pytest.mark.parametrize("adjust_type", ["qfq", "hfq"])
def test_native_adjustment_matches_python(monkeypatch, adjust_type: str) -> None:
    bfq_data, xdxr_data = _build_sample_frames()

    original_available = adjustments.NATIVE_FINANCE_AVAILABLE
    original_func = adjustments.native_apply_price_adjustments

    if not original_available or original_func is None:
        pytest.skip("native_finance_ops extension is not available")

    monkeypatch.setattr(adjustments, "NATIVE_FINANCE_AVAILABLE", False)
    monkeypatch.setattr(adjustments, "native_apply_price_adjustments", None)
    python_result = adjustments._apply_full_adjustment(bfq_data.copy(), xdxr_data.copy(), adjust_type)

    monkeypatch.setattr(adjustments, "NATIVE_FINANCE_AVAILABLE", original_available)
    monkeypatch.setattr(adjustments, "native_apply_price_adjustments", original_func)
    native_result = adjustments._apply_full_adjustment(bfq_data.copy(), xdxr_data.copy(), adjust_type)

    pd.testing.assert_frame_equal(native_result, python_result)
