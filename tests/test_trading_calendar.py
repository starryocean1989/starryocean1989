import pytest
from datetime import date
from backend.infrastructure.tdx_asyncio.utils.trading_calendar import (
    is_trading_day_global,
    get_next_trading_day_global,
    get_previous_trading_day_global,
    get_trading_days_in_range_global,
)

def test_is_trading_day():
    # 假设 2024-01-01 是交易日, 2024-01-06 是周六，非交易日
    assert is_trading_day_global(date(2024, 1, 2)) is True
    assert is_trading_day_global(date(2024, 1, 6)) is False

def test_get_next_trading_day():
    # 假设 2024-01-05 之后是 2024-01-08
    assert get_next_trading_day_global(date(2024, 1, 5)) == date(2024, 1, 8)
    assert get_next_trading_day_global(date(2024, 1, 5), include_self=True) == date(2024, 1, 5)


def test_get_previous_trading_day():
    # 假设 2024-01-08 之前是 2024-01-05
    assert get_previous_trading_day_global(date(2024, 1, 8)) == date(2024, 1, 5)
    assert get_previous_trading_day_global(date(2024, 1, 8), include_self=True) == date(2024, 1, 8)

def test_get_trading_days_in_range():
    days = get_trading_days_in_range_global(date(2024, 1, 1), date(2024, 1, 10))
    expected_days = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
    ]
    assert days == expected_days