# -*- coding: utf-8 -*-
"""
缓存和内存管理模块 - 极限合并版

本模块已完成极限合并：将原2个独立文件合并为1个统一文件cache_and_memory.py

合并前文件清单：
1. cache_manager.py (266行) - LRU缓存管理器（装饰器和直接调用）
2. shared_memory_manager.py (230行) - 共享内存管理器（进程间数据共享）

合并后：cache_and_memory.py (~496行)

负责缓存和内存管理：
- LRU缓存：基于时间和大小的自动淘汰策略
- 共享内存：多进程间共享数据结构（ValidationContext等）
- 装饰器支持：@lru_cache 装饰器用于函数级缓存
- 统计功能：缓存命中率、淘汰统计等

API兼容性：100%向后兼容，所有导入路径保持有效

合并日期：2025-10-26
"""


# ==============================================================================
# 第1部分：LRU缓存管理器（原cache_manager.py）
# ==============================================================================


import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


# ==================== 数据类 ====================


@dataclass
class CacheEntry(Generic[V]):
    """缓存条目"""

    value: V
    timestamp: float  # 创建/更新时间
    access_count: int = 0  # 访问次数


@dataclass
class CacheStats:
    """缓存统计"""

    size: int  # 当前大小
    capacity: int  # 容量
    hits: int  # 命中次数
    misses: int  # 未命中次数
    evictions: int  # 淘汰次数
    hit_rate: float  # 命中率


# ==================== LRU缓存管理器 ====================


class LRUCacheManager(Generic[K, V]):
    """LRU缓存管理器

    使用示例：
        cache = LRUCacheManager[str, dict](capacity=1000, ttl=3600)

        # 设置值
        cache.set("key1", {"data": "value"})

        # 获取值
        value = cache.get("key1")

        # 检查是否存在
        if cache.exists("key1"):
            ...

        # 获取统计
        stats = cache.get_stats()
    """

    def __init__(
        self,
        capacity: int = 1000,
        ttl: Optional[float] = None,
        on_evict: Optional[Callable[[K, V], None]] = None,
    ):
        """初始化LRU缓存管理器

        Args:
            capacity: 容量限制
            ttl: 过期时间（秒），None表示永不过期
            on_evict: 淘汰回调函数
        """
        self.capacity = capacity
        self.ttl = ttl
        self.on_evict = on_evict

        self.logger = logging.getLogger(__name__)

        # 缓存数据（使用OrderedDict实现LRU）
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = Lock()

        # 统计信息
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """获取缓存值

        Args:
            key: 键
            default: 默认值

        Returns:
            缓存值或默认值
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return default

            entry = self._cache[key]

            # 检查是否过期
            if self._is_expired(entry):
                del self._cache[key]
                self._misses += 1
                return default

            # 更新访问信息
            entry.access_count += 1

            # 移到末尾（最近使用）
            self._cache.move_to_end(key)

            self._hits += 1
            return entry.value

    def set(self, key: K, value: V):
        """设置缓存值

        Args:
            key: 键
            value: 值
        """
        with self._lock:
            # 如果键已存在，更新值
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.timestamp = time.time()
                self._cache.move_to_end(key)
                return

            # 检查容量
            if len(self._cache) >= self.capacity:
                self._evict_lru()

            # 添加新条目
            entry = CacheEntry(value=value, timestamp=time.time())
            self._cache[key] = entry

    def exists(self, key: K) -> bool:
        """检查键是否存在

        Args:
            key: 键

        Returns:
            是否存在
        """
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache[key]
            if self._is_expired(entry):
                del self._cache[key]
                return False

            return True

    def delete(self, key: K) -> bool:
        """删除缓存值

        Args:
            key: 键

        Returns:
            是否删除成功
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def keys(self) -> list:
        """获取所有键列表

        Returns:
            键列表
        """
        with self._lock:
            # 清理过期条目
            self.cleanup_expired()
            return list(self._cache.keys())

    def __len__(self) -> int:
        """获取缓存大小

        Returns:
            缓存条目数量
        """
        with self._lock:
            return len(self._cache)

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self.logger.info("缓存已清空")

    def _evict_lru(self):
        """淘汰最少使用的条目"""
        if not self._cache:
            return

        # 移除第一个（最久未使用）
        key, entry = self._cache.popitem(last=False)
        self._evictions += 1

        # 触发回调
        if self.on_evict:
            try:
                self.on_evict(key, entry.value)
            except Exception as e:
                self.logger.error("淘汰回调失败: %s", e, exc_info=True)

    def _is_expired(self, entry: CacheEntry[V]) -> bool:
        """检查条目是否过期

        Args:
            entry: 缓存条目

        Returns:
            是否过期
        """
        if self.ttl is None:
            return False

        return (time.time() - entry.timestamp) > self.ttl

    def cleanup_expired(self) -> int:
        """清理过期条目

        Returns:
            清理数量
        """
        if self.ttl is None:
            return 0

        with self._lock:
            expired_keys = [key for key, entry in self._cache.items() if self._is_expired(entry)]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                self.logger.info("清理%d个过期条目", len(expired_keys))

            return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """获取缓存统计

        Returns:
            缓存统计
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return CacheStats(
                size=len(self._cache),
                capacity=self.capacity,
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                hit_rate=hit_rate,
            )

    def get_or_compute(self, key: K, compute_fn: Callable[[], V], cache_result: bool = True) -> V:
        """获取缓存值或计算

        Args:
            key: 键
            compute_fn: 计算函数
            cache_result: 是否缓存计算结果

        Returns:
            缓存值或计算结果
        """
        value = self.get(key)
        if value is not None:
            return value

        # 计算新值
        value = compute_fn()

        # 缓存结果
        if cache_result:
            self.set(key, value)

        return value


# ==================== 便捷函数 ====================


def create_lru_cache(capacity: int = 1000, ttl: Optional[float] = None) -> LRUCacheManager:
    """便捷函数：创建LRU缓存管理器

    Args:
        capacity: 容量限制
        ttl: 过期时间（秒）

    Returns:
        LRUCacheManager实例
    """
    return LRUCacheManager(capacity=capacity, ttl=ttl)


# ==================== 缓存装饰器 ====================


def lru_cache(capacity: int = 128, ttl: Optional[float] = None):
    """LRU缓存装饰器

    使用示例:
        @lru_cache(capacity=100, ttl=3600)
        def expensive_function(arg1, arg2):
            # ...
            return result
    """

    def decorator(func: Callable):
        cache = LRUCacheManager(capacity=capacity, ttl=ttl)

        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = (args, tuple(sorted(kwargs.items())))

            # 获取或计算
            return cache.get_or_compute(cache_key, lambda: func(*args, **kwargs), cache_result=True)

        # 添加缓存管理方法
        wrapper.cache = cache
        wrapper.cache_clear = cache.clear
        wrapper.cache_stats = cache.get_stats

        return wrapper

    return decorator



# ==============================================================================
# 第2部分：共享内存管理器（原shared_memory_manager.py）
# ==============================================================================


import logging
import multiprocessing
from datetime import date
from multiprocessing import managers
from typing import Any, Dict, Optional, Set

from .validators import ValidationContext


# ==================== 共享内存管理器 ====================


class SharedMemoryManager:
    """共享内存管理器

    使用multiprocessing.Manager()创建共享数据结构，供多进程访问。

    使用示例：
        with SharedMemoryManager() as manager:
            # 准备共享数据
            manager.prepare_shared_data(
                ipo_dates=ipo_dates_dict,
                trading_days=trading_days_set,
                latest_trading_day=latest_day,
                base_date=base_date
            )

            # 获取验证上下文（包含共享代理对象）
            context = manager.get_validation_context()

            # 在多进程中使用（自动共享）
            with multiprocessing.Pool(16) as pool:
                results = pool.map(validate_func, task_data)
    """

    def __init__(self):
        """初始化共享内存管理器"""
        self.logger = logging.getLogger(__name__)
        self._manager: Optional[managers.SyncManager] = None
        self._shared_data: Dict[str, Any] = {}
        self._is_initialized = False

    def __enter__(self):
        """上下文管理器：进入"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：退出"""
        self.stop()
        return False

    def start(self):
        """启动共享内存管理器"""
        if self._manager is None:
            self._manager = multiprocessing.Manager()
            self.logger.info("✅ 共享内存管理器已启动")

    def stop(self):
        """停止共享内存管理器"""
        if self._manager is not None:
            try:
                self._manager.shutdown()
                self.logger.info("✅ 共享内存管理器已停止")
            except Exception as e:
                self.logger.warning(f"停止共享内存管理器时出错: {e}")
            finally:
                self._manager = None
                self._shared_data.clear()
                self._is_initialized = False

    def prepare_shared_data(
        self,
        ipo_dates: Dict[str, date],
        trading_days: Set[date],
        latest_trading_day: date,
        base_date: date,
        min_records_threshold: int = 100,
        freshness_days_warning: int = 7,
        freshness_days_error: int = 30,
    ):
        """准备共享数据

        将Python原生数据结构转换为共享代理对象。

        Args:
            ipo_dates: IPO日期字典 {symbol: date}
            trading_days: 交易日集合
            latest_trading_day: 最新交易日
            base_date: 基准日期
            min_records_threshold: 最小记录数阈值
            freshness_days_warning: 数据滞后警告阈值（天）
            freshness_days_error: 数据滞后错误阈值（天）
        """
        if self._manager is None:
            raise RuntimeError("共享内存管理器未启动，请先调用start()或使用上下文管理器")

        self.logger.info("📦 准备共享数据...")
        start_time = __import__("time").time()

        # 创建共享字典（IPO日期）
        self.logger.info("  - 共享IPO日期: %d个品种", len(ipo_dates))
        shared_ipo_dates = self._manager.dict(ipo_dates)

        # 创建共享集合（交易日）- Manager不直接支持set，使用list替代
        self.logger.info("  - 共享交易日: %d个日期", len(trading_days))
        shared_trading_days_list = self._manager.list(sorted(trading_days))

        # 存储共享数据引用
        self._shared_data = {
            "ipo_dates": shared_ipo_dates,
            "trading_days_list": shared_trading_days_list,
            "trading_days_set": set(trading_days),  # 保留原始set用于快速查找（只读，不需要共享）
            "latest_trading_day": latest_trading_day,
            "base_date": base_date,
            "min_records_threshold": min_records_threshold,
            "freshness_days_warning": freshness_days_warning,
            "freshness_days_error": freshness_days_error,
        }

        self._is_initialized = True

        elapsed = __import__("time").time() - start_time
        self.logger.info("✅ 共享数据准备完成，耗时: %.3f秒", elapsed)

    def get_validation_context(self) -> ValidationContext:
        """获取验证上下文

        Returns:
            ValidationContext: 包含共享数据的验证上下文
        """
        if not self._is_initialized:
            raise RuntimeError("共享数据未准备，请先调用prepare_shared_data()")

        # 注意：trading_days使用原始set（只读），ipo_dates使用共享代理
        return ValidationContext(
            ipo_dates=self._shared_data["ipo_dates"],  # 共享字典代理
            trading_days=self._shared_data["trading_days_set"],  # 使用原始set（只读，性能更好）
            latest_trading_day=self._shared_data["latest_trading_day"],
            base_date=self._shared_data["base_date"],
            min_records_threshold=self._shared_data["min_records_threshold"],
            freshness_days_warning=self._shared_data["freshness_days_warning"],
            freshness_days_error=self._shared_data["freshness_days_error"],
        )

    def get_shared_data_info(self) -> Dict[str, Any]:
        """获取共享数据信息

        Returns:
            共享数据的统计信息
        """
        if not self._is_initialized:
            return {"initialized": False}

        try:
            return {
                "initialized": True,
                "ipo_dates_count": len(self._shared_data["ipo_dates"]),
                "trading_days_count": len(self._shared_data["trading_days_set"]),
                "latest_trading_day": str(self._shared_data["latest_trading_day"]),
                "base_date": str(self._shared_data["base_date"]),
            }
        except Exception:
            return {"initialized": False, "error": "failed to get info"}


# ==================== 便捷函数 ====================


def create_shared_validation_context(
    ipo_dates: Dict[str, date],
    trading_days: Set[date],
    latest_trading_day: date,
    base_date: date,
) -> tuple[SharedMemoryManager, ValidationContext]:
    """便捷函数：创建共享内存管理器和验证上下文

    Args:
        ipo_dates: IPO日期字典
        trading_days: 交易日集合
        latest_trading_day: 最新交易日
        base_date: 基准日期

    Returns:
        (SharedMemoryManager, ValidationContext): 管理器和上下文

    使用示例：
        manager, context = create_shared_validation_context(
            ipo_dates=ipo_dates_dict,
            trading_days=trading_days_set,
            latest_trading_day=latest_day,
            base_date=base_date
        )

        try:
            # 使用context进行多进程验证
            ...
        finally:
            manager.stop()
    """
    manager = SharedMemoryManager()
    manager.start()
    manager.prepare_shared_data(
        ipo_dates=ipo_dates,
        trading_days=trading_days,
        latest_trading_day=latest_trading_day,
        base_date=base_date,
    )
    context = manager.get_validation_context()
    return manager, context

