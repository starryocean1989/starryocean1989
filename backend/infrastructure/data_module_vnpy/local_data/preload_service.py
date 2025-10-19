# -*- coding: utf-8 -*-
"""预加载服务."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, Optional, Set, Tuple, TYPE_CHECKING

import pandas as pd

from ..config import config_manager

if TYPE_CHECKING:  # pragma: no cover
    from ..core import ChinaStockEngine


class PreloadService:
    """基于后台线程的数据预加载与缓存服务."""

    QUEUE_WAIT_SECONDS = 1.0

    def __init__(self, engine: "ChinaStockEngine") -> None:
        self.engine = engine
        self.logger = logging.getLogger(__name__)
        self._queue: Deque[Tuple[str, Optional[Tuple[str, ...]]]] = deque()
        self._queue_lock = threading.Lock()
        self._pending: Set[str] = set()
        self._running = False
        self._worker: Optional[threading.Thread] = None
        self._cache_lock = threading.Lock()
        self._cache: Dict[str, Dict[str, pd.DataFrame]] = {}
        self._cache_meta: Dict[str, Dict[str, datetime]] = {}
        self._cache_order: Deque[str] = deque()
        self._max_cache_symbols = config_manager.get_preload_max_cache_symbols()
        self._default_intervals = tuple(config_manager.get_preload_intervals())
        self._stats = {
            "total_preloaded": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_preload": None,
        }

    # ------------------------------------------------------------------
    def start(self, prime: bool = True) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run, name="DataPreloadWorker", daemon=True)
        self._worker.start()
        self.logger.info("预加载服务已启动")
        if prime:
            self.prime_with_frequently_used()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        self.logger.info("预加载服务已停止")

    # ------------------------------------------------------------------
    def enqueue(
        self, symbol: str, *, intervals: Optional[Iterable[str]] = None, priority: bool = False
    ) -> None:
        if not symbol:
            return
        canonical = symbol.strip()
        if not canonical:
            return
        req_intervals = tuple(str(it).strip() for it in intervals) if intervals else None
        with self._queue_lock:
            if canonical in self._pending:
                return
            if priority:
                self._queue.appendleft((canonical, req_intervals))
            else:
                self._queue.append((canonical, req_intervals))
            self._pending.add(canonical)

    # ------------------------------------------------------------------
    def preload_now(self, symbol: str, *, intervals: Optional[Iterable[str]] = None) -> None:
        self.enqueue(symbol, intervals=intervals, priority=True)

    # ------------------------------------------------------------------
    def prime_with_frequently_used(self) -> None:
        symbols = config_manager.get_preload_frequently_used_symbols()
        for symbol in symbols:
            self.enqueue(symbol, priority=False)

    # ------------------------------------------------------------------
    def get_cached_dataframe(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        key = symbol.strip()
        if not key:
            return None
        interval_key = interval.strip()
        with self._cache_lock:
            interval_map = self._cache.get(key)
            if not interval_map:
                self._stats["cache_misses"] += 1
                return None
            frame = interval_map.get(interval_key)
            if frame is None or frame.empty:
                self._stats["cache_misses"] += 1
                return None
            self._stats["cache_hits"] += 1
            return frame.copy(deep=False)

    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        with self._cache_lock, self._queue_lock:
            return {
                **self._stats,
                "cached_symbols": len(self._cache),
                "queue_size": len(self._queue),
                "max_cache_symbols": self._max_cache_symbols,
            }

    # ------------------------------------------------------------------
    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._cache_meta.clear()
            self._cache_order.clear()

    # ------------------------------------------------------------------
    def _run(self) -> None:
        while self._running:
            task = self._next_task()
            if not task:
                time.sleep(self.QUEUE_WAIT_SECONDS)
                continue
            symbol, intervals = task
            try:
                self._execute(symbol, intervals or self._default_intervals)
            except Exception as exc:  # pragma: no cover
                self.logger.error("预加载 %s 失败: %s", symbol, exc, exc_info=True)

    # ------------------------------------------------------------------
    def _next_task(self) -> Optional[Tuple[str, Optional[Tuple[str, ...]]]]:
        with self._queue_lock:
            if not self._queue:
                return None
            symbol, intervals = self._queue.popleft()
            self._pending.discard(symbol)
            return symbol, intervals

    # ------------------------------------------------------------------
    def _execute(self, symbol: str, intervals: Tuple[str, ...]) -> None:
        loaded_any = False
        for interval in intervals:
            interval_key = interval.strip()
            if not interval_key:
                continue
            frame = self.engine.storage_manager.query_kline(symbol, interval_key)
            if frame is None or frame.empty:
                continue
            loaded_any = True
            self._store(symbol, interval_key, frame)

        if loaded_any:
            self._stats["total_preloaded"] += 1
            self._stats["last_preload"] = datetime.now().isoformat()

    # ------------------------------------------------------------------
    def _store(self, symbol: str, interval: str, frame: pd.DataFrame) -> None:
        with self._cache_lock:
            if symbol not in self._cache:
                if len(self._cache) >= self._max_cache_symbols:
                    self._evict_oldest()
                self._cache[symbol] = {}
                self._cache_meta[symbol] = {}
                self._cache_order.append(symbol)
            self._cache[symbol][interval] = frame.copy(deep=False)
            self._cache_meta[symbol][interval] = datetime.now()

    # ------------------------------------------------------------------
    def _evict_oldest(self) -> None:
        while self._cache_order:
            candidate = self._cache_order.popleft()
            if candidate in self._cache:
                del self._cache[candidate]
                del self._cache_meta[candidate]
                break
