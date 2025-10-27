# -*- coding: utf-8 -*-
"""
规则缓存模块

提供LRU缓存+TTL管理，优化路由决策性能
"""

import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from threading import Lock


@dataclass
class CachedRule:
    """缓存的路由规则"""

    targets: List[str]
    timestamp: float
    hit_count: int = 0


class RuleCache:
    """路由规则缓存（线程安全，LRU+TTL）

    功能：
    - LRU缓存机制
    - TTL过期管理（默认5秒）
    - 统计信息（命中率、缓存大小等）
    - 线程安全

    性能指标：
    - 缓存命中率目标: >95%
    - 内存占用: <10KB
    - 查询耗时: <0.01ms
    """

    def __init__(self, ttl_seconds: int = 5, max_size: int = 500):
        """初始化缓存

        Args:
            ttl_seconds: 缓存生存时间（秒），默认5秒
            max_size: 最大缓存条目数，默认500
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[Tuple, CachedRule] = {}
        self._lock = Lock()

        # 统计信息
        self._hits = 0
        self._misses = 0
        self._evictions = 0  # LRU淘汰次数

    def get(self, key: Tuple) -> Optional[List[str]]:
        """获取缓存的路由目标

        Args:
            key: 缓存键 (log_type, level, module, scenario, stage)

        Returns:
            路由目标列表，如果缓存未命中或已过期返回None
        """
        with self._lock:
            cached = self._cache.get(key)

            if cached is None:
                self._misses += 1
                return None

            # 检查是否过期
            if time.time() - cached.timestamp > self.ttl:
                del self._cache[key]
                self._misses += 1
                return None

            # 缓存命中
            cached.hit_count += 1
            self._hits += 1
            return cached.targets.copy()  # 返回副本，避免外部修改

    def set(self, key: Tuple, targets: List[str]):
        """设置缓存

        Args:
            key: 缓存键 (log_type, level, module, scenario, stage)
            targets: 路由目标列表
        """
        with self._lock:
            # LRU淘汰：如果缓存已满，删除最少使用的项
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            self._cache[key] = CachedRule(
                targets=targets.copy(), timestamp=time.time()  # 存储副本，避免外部修改
            )

    def _evict_lru(self):
        """淘汰最少使用的缓存项（LRU）"""
        if not self._cache:
            return

        # 找到hit_count最小的项
        lru_key = min(self._cache.items(), key=lambda x: x[1].hit_count)[0]
        del self._cache[lru_key]
        self._evictions += 1

    def clear(self):
        """清空缓存（阶段切换时调用）"""
        with self._lock:
            self._cache.clear()

    def remove_expired(self):
        """清理过期缓存（定期调用）"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key
                for key, cached in self._cache.items()
                if current_time - cached.timestamp > self.ttl
            ]
            for key in expired_keys:
                del self._cache[key]

    def get_statistics(self) -> Dict:
        """获取缓存统计信息

        Returns:
            统计信息字典，包含：
            - size: 当前缓存大小
            - hits: 命中次数
            - misses: 未命中次数
            - hit_rate: 命中率（百分比）
            - evictions: LRU淘汰次数
            - ttl: 缓存TTL（秒）
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0

            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "evictions": self._evictions,
                "ttl": self.ttl,
                "max_size": self.max_size,
            }

    def reset_statistics(self):
        """重置统计信息（不清空缓存）"""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
