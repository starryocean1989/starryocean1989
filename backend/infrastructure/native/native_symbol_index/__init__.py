# -*- coding: utf-8 -*-
"""
native_symbol_index 模块。

提供基于原生能力的品种索引构建能力，并在扩展不可用时回退到纯 Python 实现。
"""

from __future__ import annotations

import logging
import os
from types import MappingProxyType
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

try:
    from backend.infrastructure.native.native_gil import LockFreeHashMap

    LOCKFREE_HASHMAP_AVAILABLE = True
except Exception as exc:  # noqa: BLE001 - 捕获所有导入异常
    LockFreeHashMap = None  # type: ignore
    LOCKFREE_HASHMAP_AVAILABLE = False
    logger.debug("LockFreeHashMap 导入失败: %s", exc)

try:
    from .symbol_index import SymbolIndex as _NativeSymbolIndex  # type: ignore

    SYMBOL_INDEX_AVAILABLE = True
except ImportError as exc:
    _NativeSymbolIndex = None  # type: ignore
    SYMBOL_INDEX_AVAILABLE = False
    logger.debug("native_symbol_index C 扩展导入失败: %s", exc)


def _next_power_of_two(value: int) -> int:
    return 1 << (value - 1).bit_length() if value > 0 else 16


class PythonSymbolIndex:
    """纯 Python 实现的索引（用于回退或测试场景）。"""

    IS_NATIVE = False
    ENGINE = "python"

    def __init__(self) -> None:
        self._code_index: Dict[str, Dict[str, object]] = {}
        self._market_index: Dict[str, List[str]] = {}
        self._sorted_codes: List[str] = []

    def build(self, records: Iterable[Dict[str, object]]) -> None:
        self._code_index.clear()
        self._market_index.clear()

        for record in records:
            code = str(record.get("code", "")).zfill(6)
            if not code:
                continue
            market = str(record.get("market", record.get("market_name", "")))
            normalised = dict(record)
            normalised["code"] = code
            normalised.setdefault("market", market)
            self._code_index[code] = normalised
            self._market_index.setdefault(market, []).append(code)

        self._sorted_codes = sorted(self._code_index.keys())

    def get_symbol(self, code: str) -> Optional[Dict[str, object]]:
        return self._code_index.get(code.zfill(6))

    def get_codes_by_market(self, market: str) -> List[str]:
        return sorted(self._market_index.get(market, []))

    def all_codes(self) -> List[str]:
        return list(self._sorted_codes)

    def size(self) -> int:
        return len(self._code_index)


if LOCKFREE_HASHMAP_AVAILABLE:

    class LockFreeSymbolIndex:
        """基于 LockFreeHashMap 的索引实现."""

        IS_NATIVE = True
        ENGINE = "lockfree"

        def __init__(self, *, capacity_hint: int = 16384) -> None:
            if LockFreeHashMap is None:
                raise RuntimeError("LockFreeHashMap is not available")

            self._capacity_hint = max(32, _next_power_of_two(capacity_hint))
            self._code_index = LockFreeHashMap(self._capacity_hint)
            self._market_index = LockFreeHashMap(max(32, self._capacity_hint // 2))
            self._python_code_index: Dict[str, MappingProxyType] = {}
            self._python_market_index: Dict[str, List[str]] = {}
            self._sorted_codes: List[str] = []

        def build(self, records: Iterable[Dict[str, object]]) -> None:
            materialised = []
            for record in records:
                if not record:
                    continue
                code = str(record.get("code", "")).zfill(6)
                if not code:
                    continue
                market = str(record.get("market", record.get("market_name", "")))
                normalised = dict(record)
                normalised["code"] = code
                normalised.setdefault("market", market)
                materialised.append((code, market, normalised))

            capacity = max(len(materialised) * 2, 16)
            self._code_index = LockFreeHashMap(max(32, _next_power_of_two(capacity)))
            self._market_index = LockFreeHashMap(max(32, _next_power_of_two(max(16, capacity // 2))))

            self._python_code_index.clear()
            self._python_market_index.clear()

            for code, market, payload in materialised:
                self._code_index.set(code, payload)
                self._python_code_index[code] = MappingProxyType(payload)
                bucket = self._python_market_index.setdefault(market, [])
                bucket.append(code)

            for market, codes in self._python_market_index.items():
                deduped = sorted(set(codes))
                self._market_index.set(market, tuple(deduped))
                self._python_market_index[market] = deduped

            self._sorted_codes = sorted(self._python_code_index.keys())

        def get_symbol(self, code: str) -> Optional[Dict[str, object]]:
            key = code.zfill(6)
            try:
                result = self._code_index.get(key)
            except Exception:  # noqa: BLE001 - KeyError 或其他异常
                result = None

            if result is not None:
                return dict(result)

            cached = self._python_code_index.get(key)
            return dict(cached) if cached is not None else None

        def get_codes_by_market(self, market: str) -> List[str]:
            try:
                result = self._market_index.get(market)
            except Exception:  # noqa: BLE001
                result = None

            if result is not None:
                return list(result)

            return list(self._python_market_index.get(market, []))

        def all_codes(self) -> List[str]:
            return list(self._sorted_codes)

        def size(self) -> int:
            return len(self._sorted_codes)

else:  # pragma: no cover - LockFreeHashMap 不可用
    LockFreeSymbolIndex = None  # type: ignore

LOCKFREE_INDEX_AVAILABLE = LOCKFREE_HASHMAP_AVAILABLE and LockFreeSymbolIndex is not None


if SYMBOL_INDEX_AVAILABLE and _NativeSymbolIndex is not None:

    class NativeSymbolIndex(_NativeSymbolIndex):  # type: ignore[misc]
        """为原生扩展添加 IS_NATIVE 属性。"""

        IS_NATIVE = True
        ENGINE = "cpp"

else:  # pragma: no cover - 原生扩展缺失时
    NativeSymbolIndex = None  # type: ignore


def _resolve_impl(preferred: Optional[str]) -> str:
    value = (preferred or "auto").strip().lower()
    if value not in {"auto", "lockfree", "cpp", "python"}:
        return "auto"
    return value


def create_symbol_index(*, use_native: bool = True, impl: Optional[str] = None):
    """创建索引实例。

    Args:
        use_native: 是否优先使用原生实现。
        impl: 指定实现，可选值为 auto/lockfree/cpp/python。
              若未指定，则使用环境变量 `SYMBOL_INDEX_IMPL`，默认 auto。
    """

    selected_impl = _resolve_impl(impl or os.getenv("SYMBOL_INDEX_IMPL"))

    if use_native:
        if selected_impl in {"auto", "lockfree"} and LOCKFREE_INDEX_AVAILABLE:
            return LockFreeSymbolIndex()

        if selected_impl in {"auto", "cpp"} and SYMBOL_INDEX_AVAILABLE and NativeSymbolIndex is not None:
            return NativeSymbolIndex()

        if selected_impl == "python":
            return PythonSymbolIndex()

    return PythonSymbolIndex()


__all__ = [
    "LOCKFREE_HASHMAP_AVAILABLE",
    "LOCKFREE_INDEX_AVAILABLE",
    "SYMBOL_INDEX_AVAILABLE",
    "LockFreeSymbolIndex",
    "NativeSymbolIndex",
    "PythonSymbolIndex",
    "create_symbol_index",
]


