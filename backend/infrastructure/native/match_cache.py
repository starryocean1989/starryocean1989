# -*- coding: utf-8 -*-
"""
组合撮合缓存统一入口。

优先返回 C 扩展 `HighPerfMatchCache`，若不可用则退化到 Python 实现。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple, overload

try:
    from backend.infrastructure.native.native_collections import (  # type: ignore
        HighPerfMatchCache as _NativeMatchCache,
        COLLECTIONS_AVAILABLE as _COLLECTIONS_AVAILABLE,
    )
except Exception:  # pragma: no cover - 平台不支持或扩展未编译
    _NativeMatchCache = None  # type: ignore
    _COLLECTIONS_AVAILABLE = False

__all__ = [
    "create_match_cache",
    "PythonMatchCache",
    "MATCH_CACHE_NATIVE_AVAILABLE",
]

MATCH_CACHE_NATIVE_AVAILABLE: bool = bool(_COLLECTIONS_AVAILABLE and _NativeMatchCache)


class PythonMatchCache:
    """Python fallback 实现，接口对齐原生扩展。"""

    __slots__ = (
        "_lock",
        "_positions",
        "_accounts",
        "_trades",
        "_trade_stats",
    )

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._positions: Dict[str, Dict[Tuple[str, str], Any]] = {}
        self._accounts: Dict[str, Dict[str, Any]] = {}
        self._trades: Dict[str, Dict[str, Any]] = {}
        self._trade_stats: Dict[str, Dict[str, Dict[str, float]]] = {}

    # -------------------- 工具方法 --------------------
    @staticmethod
    def _ensure_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _direction_key(direction: Any) -> str:
        if direction is None:
            return "UNKNOWN"
        name = getattr(direction, "name", None)
        if isinstance(name, str):
            return name.upper()
        value = getattr(direction, "value", None)
        if isinstance(value, str):
            return value.upper()
        return str(direction).upper()

    # -------------------- Position --------------------
    def upsert_position(self, position: Any) -> None:
        gateway = self._ensure_text(getattr(position, "gateway_name", None))
        symbol = self._ensure_text(
            getattr(position, "vt_symbol", getattr(position, "symbol", None))
        )
        direction_key = self._direction_key(getattr(position, "direction", None))
        if not gateway or not symbol:
            return

        with self._lock:
            gateway_positions = self._positions.setdefault(gateway, {})
            gateway_positions[(symbol, direction_key)] = position

    def get_positions(self, gateway: Optional[str] = None) -> List[Any]:
        with self._lock:
            if gateway is None:
                return [
                    position
                    for gateway_positions in self._positions.values()
                    for position in gateway_positions.values()
                ]
            return list(self._positions.get(gateway, {}).values())

    def has_positions(self, gateway: str) -> bool:
        with self._lock:
            return bool(self._positions.get(gateway))

    def gateway_with_positions(self) -> List[str]:
        with self._lock:
            return [gw for gw, items in self._positions.items() if items]

    # -------------------- Account --------------------
    def upsert_account(self, account: Any) -> None:
        gateway = self._ensure_text(getattr(account, "gateway_name", None))
        account_id = self._ensure_text(
            getattr(account, "accountid", getattr(account, "account_id", None))
        )
        if not gateway or not account_id:
            return

        with self._lock:
            gateway_accounts = self._accounts.setdefault(gateway, {})
            gateway_accounts[account_id] = account

    def get_accounts(self, gateway: Optional[str] = None) -> List[Any]:
        with self._lock:
            if gateway is None:
                return [
                    account
                    for gateway_accounts in self._accounts.values()
                    for account in gateway_accounts.values()
                ]
            return list(self._accounts.get(gateway, {}).values())

    def has_accounts(self, gateway: str) -> bool:
        with self._lock:
            return bool(self._accounts.get(gateway))

    def gateway_with_accounts(self) -> List[str]:
        with self._lock:
            return [gw for gw, items in self._accounts.items() if items]

    # -------------------- Trade --------------------
    def upsert_trade(self, trade: Any) -> None:
        gateway = self._ensure_text(getattr(trade, "gateway_name", None))
        trade_id = self._ensure_text(
            getattr(trade, "vt_tradeid", getattr(trade, "tradeid", None))
        )
        if not gateway or not trade_id:
            return

        with self._lock:
            gateway_trades = self._trades.setdefault(gateway, {})
            existing = gateway_trades.get(trade_id)
            if existing is not None:
                self._update_trade_stats(existing, gateway, factor=-1)
            gateway_trades[trade_id] = trade
            self._update_trade_stats(trade, gateway, factor=1)

    def _update_trade_stats(self, trade: Any, gateway: str, factor: int) -> None:
        symbol = self._ensure_text(
            getattr(trade, "vt_symbol", getattr(trade, "symbol", None))
        )
        if not symbol:
            return

        direction_key = self._direction_key(getattr(trade, "direction", None))
        price = float(getattr(trade, "price", 0.0) or 0.0)
        volume = float(getattr(trade, "volume", 0.0) or 0.0)

        stats_by_symbol = self._trade_stats.setdefault(gateway, {})
        if factor < 0 and symbol not in stats_by_symbol:
            return

        stats = stats_by_symbol.setdefault(
            symbol,
            {
                "buy_value": 0.0,
                "sell_value": 0.0,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "trade_count": 0,
            },
        )

        turnover = price * volume * factor
        volume_delta = volume * factor
        stats["trade_count"] += factor

        if direction_key in {"LONG", "BUY", "BID"}:
            stats["buy_value"] += turnover
            stats["buy_volume"] += volume_delta
        else:
            stats["sell_value"] += turnover
            stats["sell_volume"] += volume_delta

    def get_trades(self, gateway: Optional[str] = None) -> List[Any]:
        with self._lock:
            if gateway is None:
                return [
                    trade
                    for gateway_trades in self._trades.values()
                    for trade in gateway_trades.values()
                ]
            return list(self._trades.get(gateway, {}).values())

    def get_trade_stats(self, gateway: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            stats = self._trade_stats.get(gateway, {})
            if symbol is None:
                return {sym: dict(values) for sym, values in stats.items()}
            symbol_key = self._ensure_text(symbol)
            symbol_stats = stats.get(symbol_key)
            if not symbol_stats:
                return {}
            return dict(symbol_stats)


def create_match_cache() -> Tuple[Any, bool]:
    """创建撮合缓存实例，返回 (实例, 是否为原生实现)。"""
    if MATCH_CACHE_NATIVE_AVAILABLE:
        try:
            return _NativeMatchCache(), True  # type: ignore[call-arg]
        except Exception:  # pragma: no cover - 构造失败时降级
            pass
    return PythonMatchCache(), False


