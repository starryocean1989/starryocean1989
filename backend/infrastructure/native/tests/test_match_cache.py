# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from backend.infrastructure.native.match_cache import PythonMatchCache


@dataclass
class _DummyPosition:
    gateway_name: str
    vt_symbol: str
    direction: str
    volume: float = 0.0
    pnl: float = 0.0


@dataclass
class _DummyAccount:
    gateway_name: str
    accountid: str
    balance: float = 0.0
    available: float = 0.0


@dataclass
class _DummyTrade:
    gateway_name: str
    vt_tradeid: str
    vt_symbol: str
    direction: str
    price: float
    volume: float


def test_python_match_cache_basic_flow():
    cache = PythonMatchCache()

    pos = _DummyPosition("CTP", "rb2405.SHFE", "LONG", volume=10, pnl=100)
    cache.upsert_position(pos)
    assert cache.has_positions("CTP")
    assert cache.get_positions("CTP")[0] is pos

    acc = _DummyAccount("CTP", "001", balance=1_000_000, available=900_000)
    cache.upsert_account(acc)
    assert cache.has_accounts("CTP")
    assert cache.get_accounts("CTP")[0] is acc

    trade_open = _DummyTrade("CTP", "T1", "rb2405.SHFE", "LONG", price=3800, volume=1)
    trade_close = _DummyTrade("CTP", "T2", "rb2405.SHFE", "SHORT", price=3820, volume=1)
    cache.upsert_trade(trade_open)
    cache.upsert_trade(trade_close)

    stats = cache.get_trade_stats("CTP", "rb2405.SHFE")
    assert stats["buy_volume"] == 1
    assert stats["sell_volume"] == 1
    assert stats["buy_value"] == 3800
    assert stats["sell_value"] == 3820
    assert stats["trade_count"] == 2

    # 更新已有成交应覆盖统计
    trade_close_2 = _DummyTrade("CTP", "T2", "rb2405.SHFE", "SHORT", price=3830, volume=1)
    cache.upsert_trade(trade_close_2)
    stats_after = cache.get_trade_stats("CTP", "rb2405.SHFE")
    assert stats_after["sell_value"] == 3830
    assert stats_after["trade_count"] == 2


