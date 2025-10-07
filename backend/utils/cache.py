# -*- coding: utf-8 -*-
"""
缓存管理工具.

提供内存缓存、TTL缓存和缓存策略管理功能。
"""

import logging
import time
import threading
from typing import Any, Dict, List, Optional, Callable, Union
from datetime import datetime, timedelta
from collections import OrderedDict

logger = logging.getLogger(__name__)


class CacheItem:
    """缓存项."""

    def __init__(self, key: str, value: Any, ttl: Optional[int] = None):
        """初始化缓存项."""
        self.key = key
        self.value = value
        self.created_at = time.time()
        self.last_accessed = self.created_at
        self.access_count = 0
        self.ttl = ttl
        self.expires_at = time.time() + ttl if ttl else None

    def is_expired(self) -> bool:
        """检查是否过期."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """更新访问时间."""
        self.last_accessed = time.time()
        self.access_count += 1

    def get_value(self) -> Any:
        """获取值并更新访问信息."""
        self.touch()
        return self.value


class TTLCache:
    """TTL缓存."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """初始化TTL缓存."""
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheItem] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expired_cleanups": 0}

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值."""
        with self._lock:
            if key in self._cache:
                item = self._cache[key]

                if item.is_expired():
                    # 过期项删除
                    del self._cache[key]
                    self._stats["expired_cleanups"] += 1
                    self._stats["misses"] += 1
                    return default

                # 移动到末尾（LRU）
                self._cache.move_to_end(key)
                self._stats["hits"] += 1
                return item.get_value()

            self._stats["misses"] += 1
            return default

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值."""
        with self._lock:
            if ttl is None:
                ttl = self.default_ttl

            item = CacheItem(key, value, ttl)

            if key in self._cache:
                # 更新现有项
                self._cache[key] = item
                self._cache.move_to_end(key)
            else:
                # 添加新项
                if len(self._cache) >= self.max_size:
                    # 删除最旧的项
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                    self._stats["evictions"] += 1

                self._cache[key] = item

    def delete(self, key: str) -> bool:
        """删除缓存项."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """清空缓存."""
        with self._lock:
            self._cache.clear()

    def exists(self, key: str) -> bool:
        """检查键是否存在且未过期."""
        with self._lock:
            if key in self._cache:
                item = self._cache[key]
                if item.is_expired():
                    del self._cache[key]
                    self._stats["expired_cleanups"] += 1
                    return False
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests * 100 if total_requests > 0 else 0
            )

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 2),
                "evictions": self._stats["evictions"],
                "expired_cleanups": self._stats["expired_cleanups"],
            }

    def cleanup_expired(self) -> int:
        """清理过期项."""
        with self._lock:
            expired_keys = []
            for key, item in self._cache.items():
                if item.is_expired():
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]
                self._stats["expired_cleanups"] += 1

            return len(expired_keys)


class MemoryCache:
    """内存缓存."""

    def __init__(self, max_size: int = 1000):
        """初始化内存缓存."""
        self.max_size = max_size
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值."""
        with self._lock:
            if key in self._cache:
                # 移动到末尾（LRU）
                self._cache.move_to_end(key)
                self._stats["hits"] += 1
                return self._cache[key]

            self._stats["misses"] += 1
            return default

    def set(self, key: str, value: Any) -> None:
        """设置缓存值."""
        with self._lock:
            if key in self._cache:
                # 更新现有项
                self._cache[key] = value
                self._cache.move_to_end(key)
            else:
                # 添加新项
                if len(self._cache) >= self.max_size:
                    # 删除最旧的项
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                    self._stats["evictions"] += 1

                self._cache[key] = value

    def delete(self, key: str) -> bool:
        """删除缓存项."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """清空缓存."""
        with self._lock:
            self._cache.clear()

    def exists(self, key: str) -> bool:
        """检查键是否存在."""
        with self._lock:
            return key in self._cache

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests * 100 if total_requests > 0 else 0
            )

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 2),
                "evictions": self._stats["evictions"],
            }


class CacheManager:
    """缓存管理器."""

    def __init__(self):
        """初始化缓存管理器."""
        self._caches: Dict[str, Union[TTLCache, MemoryCache]] = {}
        self._lock = threading.RLock()

    def create_ttl_cache(
        self, name: str, max_size: int = 1000, default_ttl: int = 3600
    ) -> TTLCache:
        """创建TTL缓存."""
        with self._lock:
            if name in self._caches:
                raise ValueError(f"缓存已存在: {name}")

            cache = TTLCache(max_size, default_ttl)
            self._caches[name] = cache
            logger.info(
                "创建TTL缓存: %s (max_size=%d, ttl=%d)", name, max_size, default_ttl
            )
            return cache

    def create_memory_cache(self, name: str, max_size: int = 1000) -> MemoryCache:
        """创建内存缓存."""
        with self._lock:
            if name in self._caches:
                raise ValueError(f"缓存已存在: {name}")

            cache = MemoryCache(max_size)
            self._caches[name] = cache
            logger.info("创建内存缓存: %s (max_size=%d)", name, max_size)
            return cache

    def get_cache(self, name: str) -> Optional[Union[TTLCache, MemoryCache]]:
        """获取缓存."""
        with self._lock:
            return self._caches.get(name)

    def delete_cache(self, name: str) -> bool:
        """删除缓存."""
        with self._lock:
            if name in self._caches:
                del self._caches[name]
                logger.info("删除缓存: %s", name)
                return True
            return False

    def clear_all_caches(self) -> None:
        """清空所有缓存."""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()
            logger.info("清空所有缓存")

    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有缓存统计信息."""
        with self._lock:
            stats = {}
            for name, cache in self._caches.items():
                stats[name] = cache.get_stats()
            return stats

    def cleanup_all_expired(self) -> Dict[str, int]:
        """清理所有过期项."""
        with self._lock:
            results = {}
            for name, cache in self._caches.items():
                if isinstance(cache, TTLCache):
                    results[name] = cache.cleanup_expired()
            return results


class CacheDecorator:
    """缓存装饰器."""

    def __init__(
        self,
        cache: Union[TTLCache, MemoryCache],
        key_func: Optional[Callable] = None,
        ttl: Optional[int] = None,
    ):
        """初始化缓存装饰器."""
        self.cache = cache
        self.key_func = key_func
        self.ttl = ttl

    def __call__(self, func: Callable) -> Callable:
        """装饰函数."""

        def wrapper(*args, **kwargs):
            # 生成缓存键
            if self.key_func:
                key = self.key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"

            # 尝试从缓存获取
            if isinstance(self.cache, TTLCache):
                result = self.cache.get(key)
            else:
                result = self.cache.get(key)

            if result is not None:
                logger.debug("缓存命中: %s", key)
                return result

            # 执行函数
            result = func(*args, **kwargs)

            # 存入缓存
            if isinstance(self.cache, TTLCache):
                self.cache.set(key, result, self.ttl)
            else:
                self.cache.set(key, result)

            logger.debug("缓存存储: %s", key)
            return result

        return wrapper


# 全局缓存管理器实例
_cache_manager = CacheManager()


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器."""
    return _cache_manager


def cached(
    cache_name: str, key_func: Optional[Callable] = None, ttl: Optional[int] = None
):
    """缓存装饰器工厂."""
    cache = _cache_manager.get_cache(cache_name)
    if not cache:
        raise ValueError(f"缓存不存在: {cache_name}")

    return CacheDecorator(cache, key_func, ttl)


# 导出公共接口
__all__ = [
    "CacheItem",
    "TTLCache",
    "MemoryCache",
    "CacheManager",
    "CacheDecorator",
    "get_cache_manager",
    "cached",
]
