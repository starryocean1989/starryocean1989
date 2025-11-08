# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

finance = pytest.importorskip("backend.infrastructure.native.native_finance_ops")


@pytest.mark.skipif(
    not finance.FINANCE_OPS_AVAILABLE,
    reason="native_finance_ops 扩展不可用",
)
def test_aggregate_daily_pnl_merges_same_day_entries():
    dates = [20240101, 20240101, 20240102]
    pnl = [100.0, -30.0, 50.0]

    result = finance.aggregate_daily_pnl(dates, pnl, initial_equity=1_000_000)

    assert result["dates"] == [20240101, 20240102]
    assert result["daily_returns"][0] == pytest.approx(70.0)
    assert result["daily_returns"][1] == pytest.approx(50.0)
    assert len(result["cumulative_equity"]) == len(result["dates"])


@pytest.mark.skipif(
    not finance.FINANCE_OPS_AVAILABLE,
    reason="native_finance_ops 扩展不可用",
)
def test_compute_return_metrics_contains_core_fields():
    pnl_series = [10.0, -5.0, 12.0, -7.0]
    equity_series = [1_000_000 + sum(pnl_series[:i + 1]) for i in range(len(pnl_series))]

    metrics = finance.compute_return_metrics(pnl_series, equity_series, trading_days_per_year=252)

    required_keys = {"total_return", "annualized_return", "volatility", "sharpe_ratio", "max_drawdown"}
    assert required_keys.issubset(metrics.keys())
    assert isinstance(metrics["max_drawdown"], float)


@pytest.mark.skipif(
    not finance.FINANCE_OPS_AVAILABLE,
    reason="native_finance_ops 扩展不可用",
)
def test_bucketize_period_returns_labels_and_returns():
    dates = [20240101, 20240108, 20240115]
    equity = [1_000_000, 1_001_000, 1_002_500]

    result = finance.bucketize_period(equity, dates, mode="weekly")
    assert "period_labels" in result
    assert "period_returns" in result
    assert len(result["period_labels"]) == len(result["period_returns"]) == 3


@pytest.mark.skipif(
    not finance.FINANCE_OPS_AVAILABLE,
    reason="native_finance_ops 扩展不可用",
)
def test_compute_period_statistics_summary_matches_total_pnl():
    dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-08"]
    pnl = [1000.0, -500.0, 300.0, 800.0]

    result = finance.compute_period_statistics(dates, pnl, initial_equity=1_000_000)
    assert result["success"] is True
    assert result["summary"]["total_pnl"] == pytest.approx(sum(pnl))
    assert "equity_curve" in result
    assert len(result["daily"]) == len(dates)


@pytest.mark.skipif(
    not finance.FINANCE_OPS_AVAILABLE,
    reason="native_finance_ops 扩展不可用",
)
def test_compute_risk_profile_includes_var_series():
    returns = [0.01, -0.005, 0.007, -0.012, 0.004, 0.009, -0.003]

    profile = finance.compute_risk_profile(returns, scale=1_000_000, confidence_levels=[0.90, 0.99])

    assert "var" in profile
    assert set(profile["var"].keys()) == {"0.90", "0.99"}
    for level in profile["var"].values():
        assert "var_value" in level and "cvar_value" in level
    assert len(profile["equity_curve"]) == len(returns) + 1

