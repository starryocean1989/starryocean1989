# -*- coding: utf-8 -*-
"""
数据管理模块 - 极限合并版

本模块是data_module_vnpy的核心数据管理中枢，完成极限合并：
将原4个独立文件合并为1个统一文件data_management.py

合并前文件清单：
1. intelligent_adaptive_tuner.py (138行) - 智能自适应调优器
2. cache_and_memory.py (452行) - LRU缓存管理器、共享内存管理器
3. validators.py (998行) - 无状态验证器、GPU验证器、增量扫描器
4. unified_data_manager.py (1990行) - 统一数据管理器、数据源、预加载服务

合并后：data_management.py (~3,578行)

负责数据管理的所有核心功能：
- 智能调优：基于多维压力评分的动态并发调节
- 缓存优化：LRU缓存、共享内存管理
- 数据验证：无状态验证器、GPU加速、增量扫描
- 统一管理：TDX数据源、虚拟数据源、预加载服务、外部网关适配

API兼容性：100%向后兼容，所有导入路径保持有效

合并日期：2025-10-29
"""

from __future__ import annotations

# ==============================================================================
# 第1部分：智能自适应调优器（原intelligent_adaptive_tuner.py）
# ==============================================================================
"""
Intelligent Adaptive Tuner

多维压力评分 + 趋势分析 + 抖动保护 的并发调节器。

说明：
- 保持零依赖，不引入重型ML库；趋势用EMA与P95近似；
- 输入来自监控进程 system 字段的新增四类子系统指标；
- 输出包含并发建议与理由摘要；
"""

import time
from collections import deque
from typing import Any, Deque, Dict, Optional


class IntelligentAdaptiveTuner:
    def __init__(
        self,
        base_async_workers: int = 2000,
        base_thread_workers: int = 50,
        base_process_workers: int = 16,
        weights: Optional[Dict[str, float]] = None,
        ema_alpha: float = 0.2,
        adjust_step_max: float = 0.25,  # 单步最大调整比例
        deadband: float = 0.05,  # 死区，避免小抖动
        cooldown_sec: float = 2.0,  # 调整冷却时间
    ) -> None:
        self.base_async_workers = base_async_workers
        self.base_thread_workers = base_thread_workers
        self.base_process_workers = base_process_workers

        self.weights = weights or {
            "cpu": 0.35,
            "memory": 0.25,
            "storage": 0.25,
            "network": 0.15,
        }

        self.ema_alpha = ema_alpha
        self.adjust_step_max = adjust_step_max
        self.deadband = deadband
        self.cooldown_sec = cooldown_sec

        self._pressure_ema: Optional[float] = None
        self._history: Deque[float] = deque(maxlen=60)  # 约一分钟窗口
        self._last_scale: float = 1.0
        self._last_adjust_ts: float = 0.0

    def _norm(self, value: Optional[float], hi: float) -> float:
        if value is None:
            return 0.0
        if hi <= 0:
            return 0.0
        return max(0.0, min(1.0, value / hi))

    def _score_cpu(self, sys_data: Dict[str, Any]) -> float:
        cpu_percent = float(sys_data.get("cpu_percent", 0.0))
        cpu_load = self._norm(cpu_percent, 100.0)

        detailed = sys_data.get("cpu_detailed", {}) or {}
        ctx = detailed.get("context_switches_per_sec")
        intr = detailed.get("interrupts_per_sec")
        # 经验上大于几万/秒说明系统调度压力大，做归一近似
        ctx_load = self._norm(ctx, 50000.0)
        intr_load = self._norm(intr, 20000.0)

        # 木桶理论：只看最短的板
        return min(cpu_load, ctx_load, intr_load)

    def _score_memory(self, sys_data: Dict[str, Any]) -> float:
        mem_percent = float(sys_data.get("memory_percent", 0.0))
        mem_load = self._norm(mem_percent, 100.0)
        mem_sub = sys_data.get("memory_subsystem", {}) or {}
        swap_in = mem_sub.get("swap_in_kbps")
        swap_out = mem_sub.get("swap_out_kbps")
        swap_load = max(self._norm(swap_in, 256000.0), self._norm(swap_out, 256000.0))  # 250MB/s
        return min(mem_load, swap_load)

    def _score_storage(self, sys_data: Dict[str, Any]) -> float:
        st = sys_data.get("storage_subsystem", {}) or {}
        disks = st.get("disks", {}) or {}
        latency_scores = []
        for info in disks.values():
            lat = info.get("average_io_latency_ms")
            if lat is not None:
                latency_scores.append(self._norm(lat, 50.0))  # 50ms 为高风险上限
        return max(latency_scores) if latency_scores else 0.0

    def _score_network(self, sys_data: Dict[str, Any]) -> float:
        net = sys_data.get("network_subsystem", {}) or {}
        loss_in = float(net.get("packet_loss_rate_in", 0.0))
        loss_out = float(net.get("packet_loss_rate_out", 0.0))
        # 1% 丢包即高危
        return max(self._norm(loss_in, 1.0), self._norm(loss_out, 1.0))

    def _calc_pressure(self, sys_data: Dict[str, Any]) -> float:
        cpu = self._score_cpu(sys_data)
        mem = self._score_memory(sys_data)
        sto = self._score_storage(sys_data)
        net = self._score_network(sys_data)

        pressure = (
            cpu * self.weights["cpu"]
            + mem * self.weights["memory"]
            + sto * self.weights["storage"]
            + net * self.weights["network"]
        )

        # EMA 平滑
        self._pressure_ema = (
            pressure
            if self._pressure_ema is None
            else (self.ema_alpha * pressure + (1 - self.ema_alpha) * self._pressure_ema)
        )
        self._history.append(pressure)
        return max(0.0, min(1.0, self._pressure_ema))

    def _suggest_scale(self, pressure: float) -> float:
        # 简单策略曲线：压力低→放大，压力高→缩小
        if pressure < 0.2:
            target = 1.4
        elif pressure < 0.4:
            target = 1.2
        elif pressure < 0.6:
            target = 1.0
        elif pressure < 0.8:
            target = 0.8
        else:
            target = 0.6

        # 死区与最大步长限制
        delta = target - self._last_scale
        if abs(delta) < self.deadband:
            target = self._last_scale
        else:
            step = max(-self.adjust_step_max, min(self.adjust_step_max, delta))
            target = self._last_scale + step

        # 冷却时间限制
        now = time.time()
        if now - self._last_adjust_ts < self.cooldown_sec:
            target = self._last_scale

        return max(0.3, min(1.6, target))

    def suggest(self, system_metrics: Dict[str, Any]) -> Dict[str, Any]:
        pressure = self._calc_pressure(system_metrics or {})
        scale = self._suggest_scale(pressure)

        self._last_adjust_ts = time.time()
        self._last_scale = scale

        return {
            "scale_factor": round(scale, 2),
            "async_workers": max(100, int(self.base_async_workers * scale)),
            "thread_workers": max(5, int(self.base_thread_workers * scale)),
            "process_workers": max(2, int(self.base_process_workers * scale)),
            "pressure_score": round(float(pressure), 3),
        }


# ==============================================================================
# 第2部分：LRU缓存和共享内存管理（原cache_and_memory.py）
# ==============================================================================
"""
缓存和内存管理

合并来源：
1. cache_manager.py (266行) - LRU缓存管理器（装饰器和直接调用）
2. shared_memory_manager.py (230行) - 共享内存管理器（进程间数据共享）

负责缓存和内存管理：
- LRU缓存：基于时间和大小的自动淘汰策略
- 共享内存：多进程间共享数据结构（ValidationContext等）
- 装饰器支持：@lru_cache 装饰器用于函数级缓存
- 统计功能：缓存命中率、淘汰统计等
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, Generic, Optional, TypeVar
import multiprocessing
from datetime import date
from multiprocessing import managers
from typing import Set

K = TypeVar("K")
V = TypeVar("V")


# ==================== 第2.1节：LRU缓存管理器数据类 ====================


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


# ==================== 第2.2节：LRU缓存管理器 ====================


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


# ==================== 第2.3节：便捷函数和装饰器 ====================


def create_lru_cache(capacity: int = 1000, ttl: Optional[float] = None) -> LRUCacheManager:
    """便捷函数：创建LRU缓存管理器

    Args:
        capacity: 容量限制
        ttl: 过期时间（秒）

    Returns:
        LRUCacheManager实例
    """
    return LRUCacheManager(capacity=capacity, ttl=ttl)


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


# ==================== 第2.4节：共享内存管理器 ====================


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
        start_time = time.time()

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

        elapsed = time.time() - start_time
        self.logger.info("✅ 共享数据准备完成，耗时: %.3f秒", elapsed)

    def get_validation_context(self):  # -> ValidationContext (稍后定义)
        """获取验证上下文

        Returns:
            ValidationContext: 包含共享数据的验证上下文
        """
        if not self._is_initialized:
            raise RuntimeError("共享数据未准备，请先调用prepare_shared_data()")

        # 注意：ValidationContext将在第3部分定义，这里使用延迟引用
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


# ==================== 第2.5节：便捷函数 ====================


def create_shared_validation_context(
    ipo_dates: Dict[str, date],
    trading_days: Set[date],
    latest_trading_day: date,
    base_date: date,
):  # -> tuple[SharedMemoryManager, ValidationContext]
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


# ==============================================================================
# 第3部分：数据验证器（原validators.py）
# ==============================================================================
# -*- coding: utf-8 -*-
"""
数据验证器模块 - 极限合并版

本模块已完成极限合并：将原3个独立文件合并为1个统一文件validators.py

合并前文件清单：
1. stateless_validator.py (461行) - 无状态验证器（快速批量验证）
2. gpu_validator.py (285行) - GPU加速验证器（CUDA/OpenCL加速）
3. incremental_scan.py (265行) - 增量扫描器（监控文件变化）

合并后：validators.py (~1,011行)

负责数据质量验证：
- 无状态验证器：快速批量验证数据完整性和质量
- GPU加速验证：利用GPU并行计算加速大规模数据验证
- 增量扫描：监控数据文件变化，触发增量验证

API兼容性：100%向后兼容，所有导入路径保持有效

合并日期：2025-10-26
"""


# ==============================================================================
# 第1部分：无状态验证器（原stateless_validator.py）
# ==============================================================================


from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd


# ==================== 数据类 ====================


@dataclass
class StatelessValidationResult:
    """无状态验证结果"""

    symbol: str
    interval: str
    check_time: datetime
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    record_count: int
    date_range: Tuple[Optional[date], Optional[date]]
    missing_dates: List[date]
    logic_errors: List[Dict[str, Any]]
    format_errors: List[Dict[str, Any]]
    freshness_score: float  # 数据新鲜度得分 (0-100)
    completeness_score: float  # 数据完整性得分 (0-100)


@dataclass
class ValidationContext:
    """验证上下文（共享数据）

    包含验证所需的所有静态数据，通过共享内存传递给子进程。
    """

    # IPO日期字典 {symbol: date}
    ipo_dates: Dict[str, date]

    # 交易日集合
    trading_days: Set[date]

    # 最新交易日
    latest_trading_day: date

    # 基准日期（用于计算有效起始日期）
    base_date: date

    # 验证规则配置
    min_records_threshold: int = 100  # 最小记录数阈值
    freshness_days_warning: int = 7  # 数据滞后警告阈值（天）
    freshness_days_error: int = 30  # 数据滞后错误阈值（天）


# ==================== 无状态验证器 ====================


class StatelessValidator:
    """无状态验证器（纯函数验证器）

    所有方法都是静态方法，不依赖实例状态，完全可序列化。

    使用示例：
        # 准备验证上下文（一次性）
        context = ValidationContext(
            ipo_dates=ipo_dates_dict,
            trading_days=trading_days_set,
            latest_trading_day=latest_day,
            base_date=base_date
        )

        # 验证单个品种（可在多进程中执行）
        result = StatelessValidator.validate_symbol(
            symbol="000001",
            interval="1d",
            df=df,
            context=context
        )
    """

    # ==================== 核心验证方法 ====================

    @staticmethod
    def validate_symbol(
        symbol: str, interval: str, df: pd.DataFrame, context: ValidationContext
    ) -> StatelessValidationResult:
        """验证单个品种的数据（纯函数，完全无状态）

        Args:
            symbol: 品种代码
            interval: 时间间隔
            df: 数据DataFrame
            context: 验证上下文

        Returns:
            StatelessValidationResult: 验证结果
        """
        check_time = datetime.now()

        # 数据为空检查
        if df is None or df.empty:
            return StatelessValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=check_time,
                is_valid=False,
                errors=["数据不存在或为空"],
                warnings=[],
                record_count=0,
                date_range=(None, None),
                missing_dates=[],
                logic_errors=[],
                format_errors=[],
                freshness_score=0.0,
                completeness_score=0.0,
            )

        # 执行各项验证
        errors = []
        warnings = []

        # 1. 格式验证
        format_errors = StatelessValidator.validate_format(df)
        if format_errors:
            errors.extend([err["message"] for err in format_errors])

        # 2. 逻辑验证
        logic_errors = StatelessValidator.validate_logic(df)
        if logic_errors:
            warnings.extend([err["message"] for err in logic_errors])

        # 3. 计算日期范围
        date_range = StatelessValidator.calculate_date_range(df)

        # 4. 完整性验证
        missing_dates, completeness_warnings = StatelessValidator.validate_completeness(
            df=df,
            symbol=symbol,
            date_range=date_range,
            context=context,
        )
        warnings.extend(completeness_warnings)

        # 5. 新鲜度验证
        freshness_warnings = StatelessValidator.validate_freshness(
            df=df, date_range=date_range, context=context
        )
        warnings.extend(freshness_warnings)

        # 6. 计算质量得分
        freshness_score = StatelessValidator.calculate_freshness_score(
            date_range=date_range, context=context
        )
        completeness_score = StatelessValidator.calculate_completeness_score(
            df=df, missing_dates=missing_dates, date_range=date_range, context=context
        )

        # 判断是否有效
        is_valid = len(errors) == 0

        return StatelessValidationResult(
            symbol=symbol,
            interval=interval,
            check_time=check_time,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            record_count=len(df),
            date_range=date_range,
            missing_dates=missing_dates,
            logic_errors=logic_errors,
            format_errors=format_errors,
            freshness_score=freshness_score,
            completeness_score=completeness_score,
        )

    # ==================== 子验证方法 ====================

    @staticmethod
    def validate_format(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """格式验证（纯函数）

        检查：
        - 必需列是否存在
        - 数据类型是否正确
        - 是否有NaN值

        Args:
            df: 数据DataFrame

        Returns:
            格式错误列表
        """
        errors = []

        # 检查必需列
        required_columns = ["datetime", "open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            errors.append(
                {
                    "type": "missing_columns",
                    "message": f"缺少必需列: {', '.join(missing_columns)}",
                    "details": {"missing": missing_columns},
                }
            )

        # 检查数值列是否有NaN
        if not errors:  # 只有在列存在时才检查
            numeric_columns = ["open", "high", "low", "close", "volume"]
            for col in numeric_columns:
                if col in df.columns:
                    nan_count = df[col].isna().sum()
                    if nan_count > 0:
                        errors.append(
                            {
                                "type": "nan_values",
                                "message": f"列 {col} 包含 {nan_count} 个NaN值",
                                "details": {"column": col, "nan_count": int(nan_count)},
                            }
                        )

        return errors

    @staticmethod
    def validate_logic(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """逻辑验证（纯函数）

        检查：
        - high >= low
        - high >= open, close
        - low <= open, close
        - volume >= 0

        Args:
            df: 数据DataFrame

        Returns:
            逻辑错误列表
        """
        errors = []

        if df.empty:
            return errors

        try:
            # 检查价格逻辑
            if all(col in df.columns for col in ["high", "low", "open", "close"]):
                # high < low
                invalid_high_low = df[df["high"] < df["low"]]
                if not invalid_high_low.empty:
                    errors.append(
                        {
                            "type": "invalid_high_low",
                            "message": f"{len(invalid_high_low)}行数据 high < low",
                            "details": {"count": len(invalid_high_low)},
                        }
                    )

                # high < open or high < close
                invalid_high = df[(df["high"] < df["open"]) | (df["high"] < df["close"])]
                if not invalid_high.empty:
                    errors.append(
                        {
                            "type": "invalid_high",
                            "message": f"{len(invalid_high)}行数据 high 小于 open/close",
                            "details": {"count": len(invalid_high)},
                        }
                    )

                # low > open or low > close
                invalid_low = df[(df["low"] > df["open"]) | (df["low"] > df["close"])]
                if not invalid_low.empty:
                    errors.append(
                        {
                            "type": "invalid_low",
                            "message": f"{len(invalid_low)}行数据 low 大于 open/close",
                            "details": {"count": len(invalid_low)},
                        }
                    )

            # 检查成交量
            if "volume" in df.columns:
                invalid_volume = df[df["volume"] < 0]
                if not invalid_volume.empty:
                    errors.append(
                        {
                            "type": "negative_volume",
                            "message": f"{len(invalid_volume)}行数据成交量为负",
                            "details": {"count": len(invalid_volume)},
                        }
                    )

        except Exception as e:
            errors.append(
                {
                    "type": "logic_check_error",
                    "message": f"逻辑验证失败: {str(e)}",
                    "details": {"error": str(e)},
                }
            )

        return errors

    @staticmethod
    def calculate_date_range(
        df: pd.DataFrame,
    ) -> Tuple[Optional[date], Optional[date]]:
        """计算数据日期范围（纯函数）

        Args:
            df: 数据DataFrame

        Returns:
            (起始日期, 结束日期) 或 (None, None)
        """
        if df.empty:
            return (None, None)

        try:
            # 尝试从索引获取
            if pd.api.types.is_datetime64_any_dtype(df.index):
                min_val = df.index.min()
                max_val = df.index.max()
                if pd.notna(min_val) and pd.notna(max_val):  # type: ignore
                    min_ts = pd.Timestamp(min_val)  # type: ignore
                    max_ts = pd.Timestamp(max_val)  # type: ignore
                    return (min_ts.date(), max_ts.date())

            # 尝试从datetime列获取
            if "datetime" in df.columns:
                datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                if not datetime_series.isna().all():  # type: ignore
                    min_val = datetime_series.min()
                    max_val = datetime_series.max()
                    if pd.notna(min_val) and pd.notna(max_val):  # type: ignore
                        min_ts = pd.Timestamp(min_val)  # type: ignore
                        max_ts = pd.Timestamp(max_val)  # type: ignore
                        return (min_ts.date(), max_ts.date())  # type: ignore

        except Exception:
            pass

        return (None, None)

    @staticmethod
    def validate_completeness(
        df: pd.DataFrame,
        symbol: str,
        date_range: Tuple[Optional[date], Optional[date]],
        context: ValidationContext,
    ) -> Tuple[List[date], List[str]]:
        """完整性验证（纯函数）

        检查数据是否覆盖所有交易日。

        Args:
            df: 数据DataFrame
            symbol: 品种代码
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            (缺失日期列表, 警告列表)
        """
        warnings = []
        missing_dates = []

        if date_range[0] is None or date_range[1] is None:
            warnings.append("无法计算日期范围，跳过完整性检查")
            return (missing_dates, warnings)

        start_date, end_date = date_range

        # 获取IPO日期
        ipo_date = context.ipo_dates.get(symbol)

        # 计算有效起始日期
        effective_start = StatelessValidator.compute_effective_start_date(
            ipo_date=ipo_date, data_start=start_date, base_date=context.base_date
        )

        # 计算应该存在的交易日
        expected_days = {
            d
            for d in context.trading_days
            if effective_start <= d <= min(end_date, context.latest_trading_day)  # type: ignore
        }

        # 从DataFrame获取实际存在的日期
        actual_days: set = set()
        try:
            if pd.api.types.is_datetime64_any_dtype(df.index):
                actual_days = {pd.Timestamp(d).date() for d in df.index}  # type: ignore
            elif "datetime" in df.columns:
                datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                actual_days = {pd.Timestamp(d).date() for d in datetime_series if pd.notna(d)}  # type: ignore
        except Exception:
            pass

        # 计算缺失日期
        missing_dates = sorted(list(expected_days - actual_days))  # type: ignore

        if missing_dates:
            warnings.append(f"缺失 {len(missing_dates)} 个交易日数据")

        return (missing_dates, warnings)

    @staticmethod
    def validate_freshness(
        df: pd.DataFrame,  # noqa: ARG004
        date_range: Tuple[Optional[date], Optional[date]],
        context: ValidationContext,
    ) -> List[str]:
        """新鲜度验证（纯函数）

        检查数据是否及时更新。

        Args:
            df: 数据DataFrame
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            警告列表
        """
        warnings = []

        if date_range[1] is None:
            warnings.append("无法计算最新日期，跳过新鲜度检查")
            return warnings

        end_date = date_range[1]
        latest_trading_day = context.latest_trading_day

        # 计算滞后天数
        lag_days = (latest_trading_day - end_date).days

        if lag_days > context.freshness_days_error:
            warnings.append(f"数据严重滞后: {lag_days}天（> {context.freshness_days_error}天）")
        elif lag_days > context.freshness_days_warning:
            warnings.append(f"数据滞后: {lag_days}天（> {context.freshness_days_warning}天）")

        return warnings

    @staticmethod
    def calculate_freshness_score(
        date_range: Tuple[Optional[date], Optional[date]], context: ValidationContext
    ) -> float:
        """计算新鲜度得分（纯函数）

        Args:
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            新鲜度得分 (0-100)
        """
        if date_range[1] is None:
            return 0.0

        end_date = date_range[1]
        latest_trading_day = context.latest_trading_day

        lag_days = (latest_trading_day - end_date).days

        # 计算得分：无滞后=100分，每滞后1天扣3分，最低0分
        score = max(0.0, 100.0 - lag_days * 3.0)

        return score

    @staticmethod
    def calculate_completeness_score(
        df: pd.DataFrame,  # noqa: ARG004
        missing_dates: List[date],
        date_range: Tuple[Optional[date], Optional[date]],
        context: ValidationContext,
    ) -> float:
        """计算完整性得分（纯函数）

        Args:
            df: 数据DataFrame
            missing_dates: 缺失日期列表
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            完整性得分 (0-100)
        """
        if date_range[0] is None or date_range[1] is None:
            return 0.0

        start_date, end_date = date_range

        # 计算应该存在的交易日数量
        expected_days_count = len([d for d in context.trading_days if start_date <= d <= end_date])  # type: ignore

        if expected_days_count == 0:
            return 100.0  # 没有应该存在的交易日，认为是完整的

        # 计算缺失率
        missing_rate = len(missing_dates) / expected_days_count

        # 计算得分：无缺失=100分，缺失率每增加1%扣1分，最低0分
        score = max(0.0, 100.0 - missing_rate * 100.0)

        return score

    # ==================== 辅助方法 ====================

    @staticmethod
    def compute_effective_start_date(
        ipo_date: Optional[date], data_start: Optional[date], base_date: Optional[date]
    ) -> date:
        """计算有效起始日期（纯函数）

        Args:
            ipo_date: IPO日期
            data_start: 数据起始日期
            base_date: 基准日期

        Returns:
            有效起始日期
        """
        candidates: list = []

        if ipo_date:
            candidates.append(ipo_date)

        if data_start:
            candidates.append(data_start)

        if base_date:
            candidates.append(base_date)

        if candidates:
            return max(candidates)  # type: ignore  # 使用最近的日期
        else:
            return date(2020, 1, 1)  # 默认值


# ==================== 顶层函数（用于multiprocessing） ====================


def validate_symbol_stateless(task_data: Dict[str, Any]) -> StatelessValidationResult:
    """顶层函数：无状态验证单个品种（用于multiprocessing.Pool.map）

    Args:
        task_data: 任务数据字典，包含：
            - symbol: 品种代码
            - interval: 时间间隔
            - df: 数据DataFrame
            - context: ValidationContext对象

    Returns:
        StatelessValidationResult: 验证结果
    """
    return StatelessValidator.validate_symbol(
        symbol=task_data["symbol"],
        interval=task_data["interval"],
        df=task_data["df"],
        context=task_data["context"],
    )


# ==============================================================================
# 第2部分：GPU加速验证器（原gpu_validator.py）
# ==============================================================================


import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# 尝试导入GPU库
try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

try:
    from numba import cuda

    HAS_NUMBA_CUDA = True
except ImportError:
    HAS_NUMBA_CUDA = False
    cuda = None


# ==================== GPU检测器 ====================


class GPUDetector:
    """GPU检测器

    检测系统GPU可用性和性能。
    """

    @staticmethod
    def detect_gpu() -> Dict[str, Any]:
        """检测GPU可用性

        Returns:
            GPU信息字典
        """
        info = {
            "has_gpu": False,
            "has_cupy": HAS_CUPY,
            "has_numba_cuda": HAS_NUMBA_CUDA,
            "gpu_count": 0,
            "gpu_names": [],
            "total_memory_gb": 0.0,
            "recommended": False,
        }

        # 检测CuPy
        if HAS_CUPY:
            try:
                # 测试GPU访问
                _ = cp.cuda.Device(0)  # type: ignore
                info["has_gpu"] = True
                info["gpu_count"] = cp.cuda.runtime.getDeviceCount()  # type: ignore
                info["gpu_names"] = [cp.cuda.Device(i).name for i in range(info["gpu_count"])]

                # 获取GPU内存
                meminfo = cp.cuda.Device(0).mem_info
                info["total_memory_gb"] = meminfo[1] / (1024**3)

                # 推荐使用GPU：内存>4GB
                info["recommended"] = info["total_memory_gb"] > 4.0

            except Exception as e:
                logging.warning("CuPy GPU检测失败: %s", e)

        # 检测Numba CUDA
        elif HAS_NUMBA_CUDA:
            try:
                if cuda.is_available():  # type: ignore
                    info["has_gpu"] = True
                    info["gpu_count"] = len(cuda.gpus)  # type: ignore
                    info["gpu_names"] = [str(gpu) for gpu in cuda.gpus]  # type: ignore
                    # Numba不提供详细内存信息
                    info["recommended"] = True
            except Exception as e:
                logging.warning("Numba CUDA检测失败: %s", e)

        return info

    @staticmethod
    def log_gpu_info():
        """打印GPU信息到日志"""
        logger = logging.getLogger(__name__)
        info = GPUDetector.detect_gpu()

        if info["has_gpu"]:
            logger.info("=" * 60)
            logger.info("🚀 检测到GPU支持")
            logger.info("  - GPU数量: %d", info["gpu_count"])
            logger.info("  - GPU名称: %s", ", ".join(info["gpu_names"]))
            if info["total_memory_gb"] > 0:
                logger.info("  - GPU内存: %.1f GB", info["total_memory_gb"])
            logger.info("  - 推荐使用GPU: %s", "是" if info["recommended"] else "否（内存<4GB）")
            logger.info("=" * 60)
        else:
            logger.info("ℹ️  未检测到GPU支持，将使用CPU模式")

        return info


# ==================== GPU加速验证器 ====================


class GPUValidator:
    """GPU加速验证器

    自动检测GPU并使用最佳加速方式。

    使用示例：
        validator = GPUValidator()

        if validator.is_gpu_available:
            # GPU加速验证
            result = validator.validate_dataframe_gpu(df)
        else:
            # CPU验证
            result = validator.validate_dataframe_cpu(df)
    """

    def __init__(self, force_cpu: bool = False):
        """初始化GPU验证器

        Args:
            force_cpu: 是否强制使用CPU（即使GPU可用）
        """
        self.logger = logging.getLogger(__name__)
        self.force_cpu = force_cpu

        # 检测GPU
        self.gpu_info = GPUDetector.detect_gpu()
        self.is_gpu_available = self.gpu_info["has_gpu"] and not force_cpu

        if self.is_gpu_available:
            self.logger.info("✅ GPU验证器初始化完成（GPU模式）")
        else:
            self.logger.info("✅ GPU验证器初始化完成（CPU模式）")

    # ==================== 逻辑验证（GPU加速） ====================

    def validate_price_logic_gpu(self, df: pd.DataFrame) -> Dict[str, int]:
        """GPU加速价格逻辑验证

        验证：
        - high >= low
        - high >= open, close
        - low <= open, close

        Args:
            df: 数据DataFrame

        Returns:
            错误统计字典
        """
        if not self.is_gpu_available or not HAS_CUPY:
            # 降级到CPU
            return self._validate_price_logic_cpu(df)

        try:
            # 转换到GPU
            high_gpu = cp.asarray(df["high"].values)  # type: ignore
            low_gpu = cp.asarray(df["low"].values)  # type: ignore
            open_gpu = cp.asarray(df["open"].values)  # type: ignore
            close_gpu = cp.asarray(df["close"].values)  # type: ignore

            # GPU并行计算
            invalid_high_low = cp.sum(high_gpu < low_gpu)  # type: ignore
            invalid_high_open = cp.sum(high_gpu < open_gpu)  # type: ignore
            invalid_high_close = cp.sum(high_gpu < close_gpu)  # type: ignore
            invalid_low_open = cp.sum(low_gpu > open_gpu)  # type: ignore
            invalid_low_close = cp.sum(low_gpu > close_gpu)  # type: ignore

            # 转换回CPU
            return {
                "invalid_high_low": int(invalid_high_low.get()),  # type: ignore
                "invalid_high_open": int(invalid_high_open.get()),  # type: ignore
                "invalid_high_close": int(invalid_high_close.get()),  # type: ignore
                "invalid_low_open": int(invalid_low_open.get()),  # type: ignore
                "invalid_low_close": int(invalid_low_close.get()),  # type: ignore
            }

        except Exception as e:
            self.logger.warning("GPU验证失败，降级到CPU: %s", e)
            return self._validate_price_logic_cpu(df)

    def _validate_price_logic_cpu(self, df: pd.DataFrame) -> Dict[str, int]:
        """CPU价格逻辑验证（降级版本）"""
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        open_price = df["open"].to_numpy()
        close = df["close"].to_numpy()

        return {
            "invalid_high_low": int(np.sum(high < low)),
            "invalid_high_open": int(np.sum(high < open_price)),
            "invalid_high_close": int(np.sum(high < close)),
            "invalid_low_open": int(np.sum(low > open_price)),
            "invalid_low_close": int(np.sum(low > close)),
        }

    # ==================== 统计计算（GPU加速） ====================

    def calculate_statistics_gpu(self, df: pd.DataFrame, column: str) -> Dict[str, float]:
        """GPU加速统计计算

        计算：均值、标准差、最小值、最大值

        Args:
            df: 数据DataFrame
            column: 列名

        Returns:
            统计结果字典
        """
        if not self.is_gpu_available or not HAS_CUPY:
            return self._calculate_statistics_cpu(df, column)

        try:
            # 转换到GPU
            data_gpu = cp.asarray(df[column].values)  # type: ignore

            # GPU并行计算统计量
            mean_val = float(cp.mean(data_gpu).get())  # type: ignore
            std_val = float(cp.std(data_gpu).get())  # type: ignore
            min_val = float(cp.min(data_gpu).get())  # type: ignore
            max_val = float(cp.max(data_gpu).get())  # type: ignore

            return {
                "mean": mean_val,
                "std": std_val,
                "min": min_val,
                "max": max_val,
            }

        except Exception as e:
            self.logger.warning("GPU统计计算失败，降级到CPU: %s", e)
            return self._calculate_statistics_cpu(df, column)

    def _calculate_statistics_cpu(self, df: pd.DataFrame, column: str) -> Dict[str, float]:
        """CPU统计计算（降级版本）"""
        data = df[column].to_numpy()

        return {
            "mean": float(np.mean(data)),
            "std": float(np.std(data)),
            "min": float(np.min(data)),
            "max": float(np.max(data)),
        }

    # ==================== 批量验证 ====================

    def validate_batch_gpu(self, dataframes: List[pd.DataFrame]) -> List[Dict[str, Any]]:
        """GPU批量验证

        Args:
            dataframes: DataFrame列表

        Returns:
            验证结果列表
        """
        results = []

        for i, df in enumerate(dataframes):
            try:
                # 价格逻辑验证
                logic_errors = self.validate_price_logic_gpu(df)

                # 统计计算
                close_stats = self.calculate_statistics_gpu(df, "close")

                results.append(
                    {
                        "index": i,
                        "success": True,
                        "logic_errors": logic_errors,
                        "close_stats": close_stats,
                    }
                )

            except Exception as e:
                results.append({"index": i, "success": False, "error": str(e)})

        return results

    # ==================== 性能基准测试 ====================

    def benchmark(self, df: pd.DataFrame, iterations: int = 100) -> Dict[str, float]:
        """性能基准测试

        对比GPU和CPU性能。

        Args:
            df: 测试数据
            iterations: 迭代次数

        Returns:
            性能对比结果
        """
        import time

        self.logger.info("开始性能基准测试：%d次迭代", iterations)

        # CPU测试
        start = time.time()
        for _ in range(iterations):
            self._validate_price_logic_cpu(df)
        cpu_time = time.time() - start

        # GPU测试
        if self.is_gpu_available:
            start = time.time()
            for _ in range(iterations):
                self.validate_price_logic_gpu(df)
            gpu_time = time.time() - start

            speedup = cpu_time / gpu_time if gpu_time > 0 else 0.0

            self.logger.info("CPU时间: %.3f秒", cpu_time)
            self.logger.info("GPU时间: %.3f秒", gpu_time)
            self.logger.info("GPU加速比: %.2fx", speedup)

            return {
                "cpu_time": cpu_time,
                "gpu_time": gpu_time,
                "speedup": speedup,
                "gpu_available": True,
            }
        else:
            self.logger.info("CPU时间: %.3f秒", cpu_time)
            self.logger.info("GPU不可用，无法测试GPU性能")

            return {"cpu_time": cpu_time, "gpu_available": False}


# ==================== 便捷函数 ====================


def create_gpu_validator(force_cpu: bool = False) -> GPUValidator:
    """便捷函数：创建GPU验证器

    Args:
        force_cpu: 是否强制使用CPU

    Returns:
        GPUValidator实例
    """
    return GPUValidator(force_cpu=force_cpu)


def detect_and_log_gpu():
    """便捷函数：检测并打印GPU信息"""
    return GPUDetector.log_gpu_info()


# ==============================================================================
# 第3部分：增量扫描器（原incremental_scan.py）
# ==============================================================================


import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ==================== 数据类 ====================


@dataclass
class ScanRecord:
    """扫描记录"""

    symbol: str
    interval: str
    last_scan_time: datetime
    file_mtime: float  # 文件修改时间（Unix时间戳）
    file_size: int  # 文件大小（字节）
    checksum: Optional[str] = None  # 文件校验和（可选）


@dataclass
class ScanMetadata:
    """扫描元数据"""

    last_full_scan: datetime  # 上次全量扫描时间
    last_incremental_scan: Optional[datetime] = None  # 上次增量扫描时间
    total_symbols: int = 0  # 总品种数
    scan_count: int = 0  # 扫描次数


# ==================== 增量扫描管理器 ====================


class IncrementalScanManager:
    """增量扫描管理器

    维护扫描历史，识别需要扫描的品种。

    使用示例：
        manager = IncrementalScanManager(cache_dir="./cache")

        # 首次全量扫描
        all_symbols = get_all_symbols()
        manager.mark_full_scan(all_symbols, interval="1d")

        # 后续增量扫描（只扫描变化的）
        changed_symbols = manager.get_changed_symbols(
            all_symbols,
            interval="1d",
            data_dir="/path/to/data"
        )

        # 扫描后更新记录
        for symbol in changed_symbols:
            manager.update_scan_record(symbol, interval="1d", file_path=file_path)
    """

    def __init__(self, cache_dir: str = "./cache", metadata_file: str = "scan_metadata.json"):
        """初始化增量扫描管理器

        Args:
            cache_dir: 缓存目录
            metadata_file: 元数据文件名
        """
        self.logger = logging.getLogger(__name__)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_file = self.cache_dir / metadata_file
        self.records_file = self.cache_dir / "scan_records.json"

        # 扫描记录 {f"{symbol}_{interval}": ScanRecord}
        self._records: Dict[str, ScanRecord] = {}

        # 扫描元数据
        self._metadata: Optional[ScanMetadata] = None

        # 加载缓存
        self._load_cache()

    # ==================== 核心方法 ====================

    def get_changed_symbols(
        self, all_symbols: List[str], interval: str, data_dir: str
    ) -> List[str]:
        """获取变化的品种列表

        对比文件修改时间，识别需要扫描的品种。

        Args:
            all_symbols: 所有品种列表
            interval: 时间间隔
            data_dir: 数据目录

        Returns:
            变化的品种列表
        """
        changed_symbols = []
        data_path = Path(data_dir)

        for symbol in all_symbols:
            key = f"{symbol}_{interval}"
            record = self._records.get(key)

            # 构建文件路径（根据实际存储结构调整）
            file_path = self._build_file_path(symbol, interval, data_path)

            if not file_path.exists():
                # 文件不存在，跳过
                continue

            # 获取文件状态
            file_stat = os.stat(file_path)
            file_mtime = file_stat.st_mtime
            file_size = file_stat.st_size

            # 判断是否变化
            if record is None:
                # 无记录，需要扫描
                changed_symbols.append(symbol)
            elif file_mtime > record.file_mtime:
                # 文件修改时间晚于上次扫描，需要扫描
                changed_symbols.append(symbol)
            elif file_size != record.file_size:
                # 文件大小变化，需要扫描
                changed_symbols.append(symbol)

        self.logger.info(
            f"增量扫描检测: {len(all_symbols)}个品种中 {len(changed_symbols)}个需要扫描 "
            f"(减少{(1 - len(changed_symbols)/len(all_symbols))*100:.1f}%)"
        )

        return changed_symbols

    def mark_full_scan(self, all_symbols: List[str], interval: str, data_dir: Optional[str] = None):
        """标记全量扫描完成

        Args:
            all_symbols: 所有品种列表
            interval: 时间间隔
            data_dir: 数据目录（可选）
        """
        scan_time = datetime.now()

        # 更新所有品种的扫描记录
        if data_dir:
            data_path = Path(data_dir)
            for symbol in all_symbols:
                file_path = self._build_file_path(symbol, interval, data_path)
                if file_path.exists():
                    self.update_scan_record(symbol, interval, str(file_path))

        # 更新元数据
        if self._metadata is None:
            self._metadata = ScanMetadata(
                last_full_scan=scan_time, total_symbols=len(all_symbols), scan_count=1
            )
        else:
            self._metadata.last_full_scan = scan_time
            self._metadata.total_symbols = len(all_symbols)
            self._metadata.scan_count += 1

        # 保存缓存
        self._save_cache()

        self.logger.info(f"✅ 全量扫描标记完成: {len(all_symbols)}个品种, 时间: {scan_time}")

    def update_scan_record(self, symbol: str, interval: str, file_path: str):
        """更新单个品种的扫描记录

        Args:
            symbol: 品种代码
            interval: 时间间隔
            file_path: 文件路径
        """
        key = f"{symbol}_{interval}"
        path = Path(file_path)

        if not path.exists():
            self.logger.warning(f"文件不存在，无法更新扫描记录: {file_path}")
            return

        # 获取文件状态
        file_stat = os.stat(path)

        # 创建或更新记录
        self._records[key] = ScanRecord(
            symbol=symbol,
            interval=interval,
            last_scan_time=datetime.now(),
            file_mtime=file_stat.st_mtime,
            file_size=file_stat.st_size,
        )

    def clear_records(self):
        """清除所有扫描记录（强制下次全量扫描）"""
        self._records.clear()
        self._metadata = None
        self._save_cache()
        self.logger.info("✅ 扫描记录已清除")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_records": len(self._records),
            "metadata": asdict(self._metadata) if self._metadata else None,
            "cache_file": str(self.records_file),
        }

    # ==================== 辅助方法 ====================

    def _build_file_path(self, symbol: str, interval: str, data_dir: Path) -> Path:
        """构建文件路径

        根据实际存储结构构建文件路径。

        Args:
            symbol: 品种代码
            interval: 时间间隔
            data_dir: 数据目录

        Returns:
            文件路径
        """
        # 示例：data_dir/interval/symbol.parquet
        # 根据实际存储结构调整
        return data_dir / interval / f"{symbol}.parquet"

    def _load_cache(self):
        """加载缓存"""
        # 加载扫描记录
        if self.records_file.exists():
            try:
                with open(self.records_file, "r", encoding="utf-8") as f:
                    records_data = json.load(f)

                for key, data in records_data.items():
                    # 反序列化datetime
                    data["last_scan_time"] = datetime.fromisoformat(data["last_scan_time"])
                    self._records[key] = ScanRecord(**data)

                self.logger.info(f"✅ 加载扫描记录: {len(self._records)}条")
            except Exception as e:
                self.logger.warning(f"加载扫描记录失败: {e}")

        # 加载元数据
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    metadata_data = json.load(f)

                # 反序列化datetime
                metadata_data["last_full_scan"] = datetime.fromisoformat(
                    metadata_data["last_full_scan"]
                )
                if metadata_data.get("last_incremental_scan"):
                    metadata_data["last_incremental_scan"] = datetime.fromisoformat(
                        metadata_data["last_incremental_scan"]
                    )

                self._metadata = ScanMetadata(**metadata_data)
                self.logger.info(f"✅ 加载扫描元数据: {self._metadata}")
            except Exception as e:
                self.logger.warning(f"加载扫描元数据失败: {e}")

    def _save_cache(self):
        """保存缓存"""
        # 保存扫描记录
        try:
            records_data = {}
            for key, record in self._records.items():
                data = asdict(record)
                # 序列化datetime
                data["last_scan_time"] = data["last_scan_time"].isoformat()
                records_data[key] = data

            with open(self.records_file, "w", encoding="utf-8") as f:
                json.dump(records_data, f, ensure_ascii=False, indent=2)

            self.logger.debug(f"✅ 保存扫描记录: {len(self._records)}条")
        except Exception as e:
            self.logger.error(f"保存扫描记录失败: {e}")

        # 保存元数据
        if self._metadata:
            try:
                metadata_data = asdict(self._metadata)
                # 序列化datetime
                metadata_data["last_full_scan"] = metadata_data["last_full_scan"].isoformat()
                if metadata_data.get("last_incremental_scan"):
                    metadata_data["last_incremental_scan"] = metadata_data[
                        "last_incremental_scan"
                    ].isoformat()

                with open(self.metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata_data, f, ensure_ascii=False, indent=2)

                self.logger.debug(f"✅ 保存扫描元数据")
            except Exception as e:
                self.logger.error(f"保存扫描元数据失败: {e}")


# ==================== 便捷函数 ====================


def create_incremental_scan_manager(cache_dir: str = "./cache") -> IncrementalScanManager:
    """便捷函数：创建增量扫描管理器

    Args:
        cache_dir: 缓存目录

    Returns:
        IncrementalScanManager实例
    """
    return IncrementalScanManager(cache_dir=cache_dir)


# ==============================================================================
# 第4部分：统一数据管理器（原unified_data_manager.py）
# ==============================================================================

import asyncio
import logging
import random
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from threading import Lock, Thread
from typing import (
    Any,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TYPE_CHECKING,
    Union,
    cast,
)

import pandas as pd
from pandas import Timestamp

from vnpy.event import EventEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    BarData,
    CancelRequest,
    ContractData,
    OrderRequest,
    SubscribeRequest,
    TickData,
)
from vnpy.trader.constant import Interval, Product

from backend.infrastructure.tdx_asyncio.async_hq import AsyncTdxHq_API
from backend.infrastructure.data_module_vnpy.load_balancer import ServerPoolManager

from .data_module import config_manager
from .load_balancer import (
    NetworkTask,
    LocalProcessingTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)

if TYPE_CHECKING:  # pragma: no cover
    from .data_module import ChinaStockEngine


# ==================== LoadBalancer任务类定义 ====================


class RealtimePollingTask(NetworkTask):
    """实时行情轮询任务"""

    def __init__(self, name: str, subscribed_count: int = 0):
        """初始化实时行情轮询任务

        Args:
            name: 任务名称
            subscribed_count: 订阅的品种数量
        """
        super().__init__(name)
        self.subscribed_count = subscribed_count
        # 更新预估连接数：通常1个连接可以查询多个品种
        self.metrics.estimated_connections = max(1, subscribed_count // 100)

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="realtime_polling",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=[
                "network_speed",
                "packet_loss_rate",
                "event_queue_depth",
                "websocket_message_backlog",
            ],
            estimated_duration=0,  # 持续运行
            estimated_memory_mb=50,  # 约50MB
            estimated_connections=1,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行实时轮询（占位方法）

        实际轮询由TdxDataSource._polling_loop执行。
        """
        return None


class VirtualReplayTask(LocalProcessingTask):
    """虚拟推送回放任务"""

    def __init__(self, name: str, replay_speed: float = 1.0):
        """初始化虚拟推送回放任务

        Args:
            name: 任务名称
            replay_speed: 回放速度倍数
        """
        super().__init__(name)
        self.replay_speed = replay_speed
        # 更新预估工作数：根据回放速度
        self.metrics.estimated_workers = min(4, max(1, int(replay_speed)))

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="virtual_replay",
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.MIXED,  # 内存+CPU
            critical_metrics=[
                "memory_percent",
                "event_queue_depth",
                "cpu_percent",
            ],
            estimated_duration=0,  # 持续运行
            estimated_memory_mb=200,  # 约200MB（历史数据缓存）
            estimated_workers=1,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行虚拟回放（占位方法）

        实际回放由VirtualDataSource的推送线程执行。
        """
        return None


class PreloadTask(LocalProcessingTask):
    """数据预加载任务"""

    def __init__(self, name: str, symbols_count: int = 0):
        """初始化数据预加载任务

        Args:
            name: 任务名称
            symbols_count: 待预加载的品种数量
        """
        super().__init__(name)
        self.symbols_count = symbols_count
        # 更新预估工作数：根据品种数量
        if symbols_count < 10:
            self.metrics.estimated_workers = 1
        elif symbols_count < 50:
            self.metrics.estimated_workers = 2
        else:
            self.metrics.estimated_workers = 4

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="data_preload",
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.MIXED,  # 磁盘I/O + 内存
            critical_metrics=[
                "disk_io_speed",
                "memory_percent",
                "average_io_latency_ms",
            ],
            estimated_duration=30,  # 预计30秒
            estimated_memory_mb=100,  # 约100MB
            estimated_workers=1,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行数据预加载（占位方法）

        实际预加载由PreloadService._run执行。
        """
        return None


# ==================== 数据源适配器（TDX数据源） ====================


class TdxDataSource(BaseGateway):
    """TDX数据源 - 请求/推送双模式（集成ServerPoolManager和真实tdx_asyncio API）

    职责：
    - 集成ServerPoolManager获取最优服务器
    - 使用AsyncTdxHq_API获取真实行情数据
    - 权重轮询负载均衡
    - tick数据推送

    特点：
    - 智能服务器选择（权重轮询）
    - 交易时间自动轮询
    - 真实API调用（get_security_quotes）
    - 支持推送和请求双模式
    """

    default_name = "TDX"
    default_setting = {
        "轮询间隔（秒）": 3,
        "品种列表": "",  # 逗号分隔的品种代码，留空表示使用配置文件
        "最大服务器数": 5,  # 使用的最优服务器数量
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]  # 支持上交所和深交所

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """
        初始化TDX数据源

        Args:
            event_engine: 事件引擎
            gateway_name: 网关名称
        """
        super().__init__(event_engine, gateway_name)

        self.logger = logging.getLogger(__name__)

        # 服务器池管理器（单例）
        self.server_pool_manager = ServerPoolManager()

        # AsyncTdxHq_API连接池（对应多个服务器）
        self._api_connections: Dict[str, AsyncTdxHq_API] = {}  # {server_key: api}
        self._server_weights: List[float] = []  # 服务器权重（基于响应时间）

        # 订阅管理
        self._subscribed_symbols: Set[str] = set()
        self._polling_interval = 3.0  # 轮询间隔（秒）
        self._polling_thread: Optional[Thread] = None
        self._polling_stop = False

        # 事件循环（用于异步调用）
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[Thread] = None

        self.logger.info("TDX数据源初始化完成")

    @classmethod
    def create_and_start(
        cls, event_engine: EventEngine, setting: Optional[dict] = None
    ) -> "TdxDataSource":
        """
        创建并启动TDX数据源（工厂方法）

        Args:
            event_engine: 事件引擎
            setting: 网关设置（可选）

        Returns:
            已启动的TDX数据源实例
        """
        gateway = cls(event_engine, cls.default_name)
        gateway.connect(setting or {})
        return gateway

    def connect(self, setting: Optional[dict] = None) -> None:
        """
        连接TDX数据源

        Args:
            setting: 网关设置
                - polling_interval: 轮询间隔（秒）
                - symbols: 预订阅品种列表
                - max_servers: 最大使用服务器数量
        """
        if setting is None:
            setting = {}

        if self.server_pool_manager._running and self._api_connections:
            self.logger.info("TDX数据源已连接")
            return

        # 启动服务器池管理器
        if not self.server_pool_manager.start():
            self.logger.error("服务器池启动失败")
            return

        # 获取最优服务器列表（已排序）
        try:
            max_servers = setting.get("max_servers", 5)
            if "最大服务器数" in setting:
                max_servers = int(setting["最大服务器数"])

            sorted_servers = self.server_pool_manager.get_servers(
                count=max_servers, pool_type="ipv4"
            )
            if not sorted_servers:
                self.logger.error("无可用IPv4服务器")
                return

            # 转换为包含响应时间的格式（假设响应时间为索引的倍数）
            top_servers = [
                (host, port, 0.05 + idx * 0.01)  # 假设响应时间从0.05秒递增
                for idx, (host, port) in enumerate(sorted_servers)
            ]
        except Exception as e:
            self.logger.error("获取服务器列表失败: %s", e)
            return

        # 计算服务器权重（基于响应时间的倒数）
        self._calculate_server_weights(top_servers)

        # 启动异步事件循环线程
        self._start_event_loop()

        # 创建API连接（每个服务器一个）
        if self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._create_api_connections(top_servers), self._loop
                )
                future.result(timeout=10)
            except Exception as e:
                self.logger.error("创建API连接失败: %s", e)
                return
        else:
            self.logger.error("事件循环未启动")
            return

        # 更新配置
        if "轮询间隔（秒）" in setting:
            self._polling_interval = float(setting["轮询间隔（秒）"])
        elif "polling_interval" in setting:
            self._polling_interval = float(setting["polling_interval"])

        # 获取订阅品种
        symbols_str = setting.get("品种列表", "")
        if symbols_str:
            self._subscribed_symbols = set(
                symbol.strip() for symbol in symbols_str.split(",") if symbol.strip()
            )
        elif "symbols" in setting and setting["symbols"]:
            self._subscribed_symbols = set(setting["symbols"])
        else:
            # 从配置获取
            symbols = config_manager.get("chinastock.tdx_source.symbols", [])
            if not symbols:
                # 兼容旧配置
                symbols = config_manager.get("chinastock.polling_gateway.symbols", [])
            self._subscribed_symbols = set(symbols) if symbols else set()

        # 启动轮询线程（如果有订阅品种）
        if self._subscribed_symbols:
            self._start_polling()

        self.logger.info(
            "TDX数据源已连接，使用%d个服务器，订阅%d个品种",
            len(top_servers),
            len(self._subscribed_symbols),
        )

    def close(self) -> None:
        """关闭TDX数据源"""
        try:
            self._stop_polling()

            # 关闭所有API连接
            if self._loop:
                future = asyncio.run_coroutine_threadsafe(self._close_api_connections(), self._loop)
                future.result(timeout=5)

            # 停止事件循环
            self._stop_event_loop()

            self.logger.info("TDX数据源已关闭")
        except Exception as e:
            self.logger.error("关闭TDX数据源失败: %s", e)

    def _start_event_loop(self) -> None:
        """启动异步事件循环线程"""
        if self._loop_thread and self._loop_thread.is_alive():
            return

        def run_event_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = Thread(target=run_event_loop, daemon=True, name="TdxEventLoop")
        self._loop_thread.start()

        # 等待事件循环启动
        while self._loop is None:
            time.sleep(0.01)

        self.logger.info("异步事件循环线程已启动")

    def _stop_event_loop(self) -> None:
        """停止异步事件循环线程"""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread:
                self._loop_thread.join(timeout=3)
            self.logger.info("异步事件循环线程已停止")

    def _calculate_server_weights(self, servers: List[Tuple[str, int, float]]) -> None:
        """
        计算服务器权重（基于响应时间）

        权重计算公式：weight = 1 / response_time
        最快服务器权重最高，被选中概率最大
        """
        if not servers:
            return

        # 提取响应时间
        response_times = [s[2] for s in servers]

        # 计算权重（响应时间的倒数）
        raw_weights = [1.0 / (rt + 0.001) for rt in response_times]  # +0.001防止除零

        # 归一化权重（和为1）
        total = sum(raw_weights)
        self._server_weights = [w / total for w in raw_weights]

        self.logger.info("服务器权重: %s", [f"{w:.3f}" for w in self._server_weights])

    def _weighted_round_robin_select(self) -> Optional[str]:
        """
        权重轮询选择服务器

        采用加权轮询算法：
        - 最快服务器有更高概率被选中
        - 保证所有服务器都能被使用（负载均衡）
        """
        if not self._api_connections or not self._server_weights:
            return None

        # 使用累积权重选择
        rand = random.random()
        cumulative = 0.0

        server_keys = list(self._api_connections.keys())
        for i, weight in enumerate(self._server_weights):
            cumulative += weight
            if rand <= cumulative:
                return server_keys[i]

        # 兜底返回最后一个
        return server_keys[-1]

    async def _create_api_connections(self, servers: List[Tuple[str, int, float]]) -> None:
        """创建多个AsyncTdxHq_API连接"""
        for server in servers:
            host, port, response_time = server
            server_key = f"{host}:{port}"

            try:
                api = AsyncTdxHq_API()
                await api.connect(host, port, time_out=5.0)
                await api.setup()

                self._api_connections[server_key] = api
                self.logger.info("已连接服务器: %s (响应时间: %.3fs)", server_key, response_time)
            except Exception as e:
                self.logger.warning("连接服务器失败: %s, %s", server_key, e)

    async def _close_api_connections(self) -> None:
        """关闭所有API连接"""
        for server_key, api in self._api_connections.items():
            try:
                await api.close()
                self.logger.debug("已关闭服务器连接: %s", server_key)
            except Exception as e:
                self.logger.warning("关闭服务器连接失败: %s, %s", server_key, e)
        self._api_connections.clear()

    def _start_polling(self) -> None:
        """启动轮询线程"""
        if self._polling_thread and self._polling_thread.is_alive():
            return

        self._polling_stop = False
        self._polling_thread = Thread(target=self._polling_loop, daemon=True, name="TdxPolling")
        self._polling_thread.start()

        self.logger.info("TDX轮询线程已启动，间隔: %s秒", self._polling_interval)

    def _stop_polling(self) -> None:
        """停止轮询线程"""
        if not self._polling_thread:
            return

        self._polling_stop = True
        if self._polling_thread.is_alive():
            self._polling_thread.join(timeout=5)

        self.logger.info("TDX轮询线程已停止")

    def _polling_loop(self) -> None:
        """轮询循环（在独立线程中运行）"""
        self.logger.info("TDX轮询循环开始")

        while not self._polling_stop:
            try:
                # 检查是否在交易时间
                if not self._is_trading_time():
                    time.sleep(60)  # 非交易时间每分钟检查一次
                    continue

                # 权重轮询选择服务器
                server_key = self._weighted_round_robin_select()
                if not server_key:
                    self.logger.warning("无可用服务器")
                    time.sleep(self._polling_interval)
                    continue

                api = self._api_connections.get(server_key)
                if not api:
                    time.sleep(self._polling_interval)
                    continue

                # 异步调用 get_security_quotes
                if self._loop is not None:
                    future = asyncio.run_coroutine_threadsafe(
                        self._fetch_realtime_data(api, server_key), self._loop
                    )
                    future.result(timeout=5.0)
                else:
                    self.logger.error("事件循环未启动")

            except Exception as e:
                self.logger.error("轮询失败: %s", e)

            # 等待下一次轮询
            time.sleep(self._polling_interval)

        self.logger.info("TDX轮询循环结束")

    def _is_trading_time(self) -> bool:
        """检查是否在交易时间"""
        now = datetime.now().time()

        # 交易时间段：9:30-11:30, 13:00-15:00
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()

        # 周末不交易
        if datetime.now().weekday() >= 5:
            return False

        # 检查是否在交易时间段内
        if (morning_start <= now <= morning_end) or (afternoon_start <= now <= afternoon_end):
            return True

        return False

    async def _fetch_realtime_data(self, api: AsyncTdxHq_API, server_key: str) -> None:
        """
        从tdx获取实时行情数据

        使用 get_security_quotes() 批量获取（最多80只）
        """
        if not self._subscribed_symbols:
            return

        # 转换品种格式：000001.SZ → (0, "000001")
        stocks = []
        for symbol in self._subscribed_symbols:
            try:
                if "." in symbol:
                    code, exchange_str = symbol.split(".")
                    market = 0 if exchange_str.upper() in ("SZ", "SZSE") else 1  # 0=深圳, 1=上海
                else:
                    # 如果没有交易所后缀，根据代码推断
                    code = symbol
                    if code.startswith("6"):
                        market = 1  # 上海
                    else:
                        market = 0  # 深圳
                stocks.append((market, code))
            except Exception as e:
                self.logger.error("解析品种格式失败: %s, %s", symbol, e)

        if not stocks:
            return

        try:
            # 调用真实API（最多80只）
            quotes = await api.get_security_quotes(stocks[:80])

            # 检查返回值
            if quotes is None:
                self.logger.warning("从 %s 获取行情返回 None", server_key)
                return

            # 转换为TickData并推送
            for quote in quotes:
                tick = self._convert_to_tick(quote)
                if tick:
                    self.on_tick(tick)

            self.logger.debug("从 %s 获取 %d 个行情", server_key, len(quotes))

        except Exception as e:
            self.logger.error("获取实时数据失败 (%s): %s", server_key, e)
            # 自动切换到下一个服务器（轮询会自动处理）

    def _convert_to_tick(self, quote: dict) -> Optional[TickData]:
        """
        将tdx行情数据转换为vnpy TickData

        tdx字段：code, price, open, high, low, last_close, vol, amount,
                bid1-bid5, ask1-ask5, bid_vol1-bid_vol5, ask_vol1-ask_vol5
        """
        try:
            code = quote["code"]
            # 推断交易所
            if code.startswith(("0", "3")):
                exchange = Exchange.SZSE
            elif code.startswith("6"):
                exchange = Exchange.SSE
            else:
                exchange = Exchange.SZSE  # 默认深圳

            symbol = code

            tick = TickData(
                gateway_name=self.gateway_name,
                symbol=symbol,
                exchange=exchange,
                datetime=datetime.now(),
                # 价格字段
                last_price=quote.get("price", 0),
                open_price=quote.get("open", 0),
                high_price=quote.get("high", 0),
                low_price=quote.get("low", 0),
                pre_close=quote.get("last_close", 0),
                # 成交量字段
                volume=quote.get("vol", 0),
                turnover=quote.get("amount", 0),
                # 盘口字段
                bid_price_1=quote.get("bid1", 0),
                bid_price_2=quote.get("bid2", 0),
                bid_price_3=quote.get("bid3", 0),
                bid_price_4=quote.get("bid4", 0),
                bid_price_5=quote.get("bid5", 0),
                ask_price_1=quote.get("ask1", 0),
                ask_price_2=quote.get("ask2", 0),
                ask_price_3=quote.get("ask3", 0),
                ask_price_4=quote.get("ask4", 0),
                ask_price_5=quote.get("ask5", 0),
                bid_volume_1=quote.get("bid_vol1", 0),
                bid_volume_2=quote.get("bid_vol2", 0),
                bid_volume_3=quote.get("bid_vol3", 0),
                bid_volume_4=quote.get("bid_vol4", 0),
                bid_volume_5=quote.get("bid_vol5", 0),
                ask_volume_1=quote.get("ask_vol1", 0),
                ask_volume_2=quote.get("ask_vol2", 0),
                ask_volume_3=quote.get("ask_vol3", 0),
                ask_volume_4=quote.get("ask_vol4", 0),
                ask_volume_5=quote.get("ask_vol5", 0),
            )

            return tick

        except Exception as e:
            self.logger.error("转换TickData失败: %s, quote=%s", e, quote)
            return None

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅实时数据"""
        symbol = req.symbol

        if symbol in self._subscribed_symbols:
            return

        self._subscribed_symbols.add(symbol)
        self.logger.info("订阅: %s", symbol)

        # 启动轮询（如果未启动）
        if not self._polling_thread or not self._polling_thread.is_alive():
            self._start_polling()

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅"""
        symbol = req.symbol
        self._subscribed_symbols.discard(symbol)
        self.logger.info("取消订阅: %s", symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送订单（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """取消订单（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")

    def query_account(self) -> None:
        """查询账户信息（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")

    def query_position(self) -> None:
        """查询持仓信息（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")


# ==================== 数据源适配器（虚拟数据源） ====================


class VirtualDataSource(BaseGateway):
    """虚拟数据源（原VirtualGateway）- 回测模拟

    职责：
    - 加载历史数据
    - 模拟实时推送
    - 回测数据提供

    特点：
    - 可配置起始时间
    - 可调节推送速度
    - 支持历史回放
    """

    default_name = "VIRTUAL"
    default_setting = {
        "起始时间": "",  # 格式：YYYY-MM-DD HH:MM:SS
        "推送速度": 1.0,  # 1.0=实时，2.0=2倍速
        "品种列表": "",  # 逗号分隔的品种代码，留空表示使用配置文件
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]  # 支持上交所和深交所

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """
        初始化虚拟数据源

        Args:
            event_engine: 事件引擎
            gateway_name: 网关名称
        """
        super().__init__(event_engine, gateway_name)

        self.logger = logging.getLogger(__name__)

        # 推送配置
        self.start_datetime: Optional[datetime] = None
        self.push_speed = 1.0  # 推送速度倍数
        self.subscribed_symbols: Set[str] = set()

        # 历史数据缓存
        self.historical_data: Dict[str, pd.DataFrame] = {}

        # 推送线程
        self.push_thread: Optional[threading.Thread] = None
        self.push_active = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()  # 暂停事件

        # 当前推送位置（每个品种的索引）
        self.push_positions: Dict[str, int] = {}

        # 当前时间（用于回放控制）
        self._current_datetime: Optional[datetime] = None

        # 存储管理器（延迟导入）
        self.storage_manager = None

        # 暂停状态
        self._is_paused = False

        self.logger.info("虚拟数据源初始化完成")

    @classmethod
    def create_and_start(
        cls,
        event_engine: EventEngine,
        start_datetime: str,
        speed: float = 1.0,
        symbols: Optional[List[str]] = None,
    ) -> "VirtualDataSource":
        """
        创建并启动虚拟数据源（工厂方法）

        Args:
            event_engine: 事件引擎
            start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS）
            speed: 推送速度倍数
            symbols: 品种列表（可选）

        Returns:
            已启动的虚拟数据源实例
        """
        gateway = cls(event_engine, cls.default_name)
        setting = {
            "起始时间": start_datetime,
            "推送速度": speed,
            "品种列表": ",".join(symbols) if symbols else "",
        }
        gateway.connect(setting)
        return gateway

    def connect(self, setting: dict) -> None:
        """
        连接虚拟数据源

        Args:
            setting: 网关设置
        """
        try:
            # 延迟导入StorageManager
            if self.storage_manager is None:
                from .data_quality import StorageManager

                self.storage_manager = StorageManager()

            # 更新配置
            start_time_str = setting.get("起始时间", "")
            if start_time_str:
                self.start_datetime = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            else:
                self.start_datetime = datetime.now() - timedelta(days=1)  # 默认昨天

            self.push_speed = float(setting.get("推送速度", 1.0))

            # 获取订阅品种
            symbols_str = setting.get("品种列表", "")
            if symbols_str:
                self.subscribed_symbols = set(
                    symbol.strip() for symbol in symbols_str.split(",") if symbol.strip()
                )
            else:
                # 从配置获取
                symbols = config_manager.get("chinastock.virtual_source.symbols", [])
                if not symbols:
                    # 兼容旧配置
                    symbols = config_manager.get("chinastock.virtual_gateway.symbols", [])
                self.subscribed_symbols = set(symbols) if symbols else set()

            # 加载历史数据
            self._load_historical_data()

            # 启动推送线程
            self._start_pushing()

            self.logger.info("虚拟数据源连接成功，起始时间: %s", self.start_datetime)

        except Exception as e:
            self.logger.error("虚拟数据源连接失败: %s", e)
            raise

    def close(self) -> None:
        """关闭虚拟数据源"""
        try:
            self._stop_pushing()
            self.logger.info("虚拟数据源已关闭")
        except Exception as e:
            self.logger.error("关闭虚拟数据源失败: %s", e)

    def _load_historical_data(self) -> None:
        """加载历史数据"""
        if not self.subscribed_symbols:
            return

        try:
            self.logger.info("加载历史数据用于虚拟推送...")

            for symbol in self.subscribed_symbols:
                try:
                    # 查询1分钟历史数据
                    if self.storage_manager is not None:
                        df = self.storage_manager.query_kline(symbol, "1m")
                        if df is not None and not df.empty:
                            self.historical_data[symbol] = df
                            self.push_positions[symbol] = 0
                            self.logger.debug("加载 %s 的历史数据: %d条", symbol, len(df))
                        else:
                            self.logger.warning("未找到 %s 的历史数据", symbol)
                    else:
                        self.logger.warning("StorageManager未初始化")

                except Exception as e:
                    self.logger.error("加载 %s 历史数据失败: %s", symbol, e)

            self.logger.info("历史数据加载完成，共 %d 个品种", len(self.historical_data))

        except Exception as e:
            self.logger.error("加载历史数据失败: %s", e)

    def _start_pushing(self) -> None:
        """启动推送线程"""
        if self.push_thread and self.push_thread.is_alive():
            self.logger.warning("推送线程已在运行")
            return

        self.push_active = True
        self._stop_event.clear()

        self.push_thread = threading.Thread(
            target=self._pushing_loop,
            daemon=True,
            name="VirtualDataSourceThread",
        )
        self.push_thread.start()

        self.logger.info("虚拟推送线程已启动，速度倍数: %.1f", self.push_speed)

    def _stop_pushing(self) -> None:
        """停止推送线程"""
        if not self.push_active:
            return

        self.push_active = False
        self._stop_event.set()

        if self.push_thread and self.push_thread.is_alive():
            self.push_thread.join(timeout=5)

        self.logger.info("虚拟推送线程已停止")

    def _pushing_loop(self) -> None:
        """推送主循环"""
        self.logger.info("虚拟推送循环开始")

        while not self._stop_event.is_set():
            try:
                # 检查暂停状态
                if self._is_paused:
                    self._pause_event.wait(timeout=0.1)
                    continue

                # 执行推送
                self._do_pushing()

                # 根据速度倍数计算等待时间
                wait_time = 60 / self.push_speed  # 1分钟数据，实时为60秒
                time.sleep(wait_time)

            except Exception as e:
                self.logger.error("虚拟推送异常: %s", e)
                time.sleep(10)  # 异常后等待10秒再试

        self.logger.info("虚拟推送循环结束")

    def _do_pushing(self) -> None:
        """执行一次推送"""
        try:
            # 确保起始时间已设置
            if self.start_datetime is None:
                self.logger.warning("起始时间未设置，使用当前时间")
                self.start_datetime = datetime.now()

            current_time = self.start_datetime

            for symbol in list(self.subscribed_symbols):
                if symbol not in self.historical_data:
                    continue

                df = self.historical_data[symbol]
                if df.empty:
                    continue

                # 获取当前推送位置
                position = self.push_positions.get(symbol, 0)

                if position >= len(df):
                    # 推送完成，重置位置
                    self.push_positions[symbol] = 0
                    position = 0

                # 获取当前数据行
                if position < len(df):
                    row = df.iloc[position]

                    # 创建TickData
                    tick = TickData(
                        gateway_name=self.gateway_name,
                        symbol=symbol,
                        exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
                        datetime=current_time,
                        name=f"股票{symbol}",
                        volume=float(row.get("volume", 0)),
                        last_price=float(row.get("close", 0)),
                        open_price=float(row.get("open", 0)),
                        high_price=float(row.get("high", 0)),
                        low_price=float(row.get("low", 0)),
                        pre_close=float(row.get("close", 0)),  # 简化处理
                    )

                    # 发送tick数据
                    self.on_tick(tick)

                    # 更新推送位置
                    self.push_positions[symbol] = position + 1

            # 更新起始时间
            self.start_datetime += timedelta(minutes=1)

        except Exception as e:
            self.logger.error("虚拟推送执行失败: %s", e)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.subscribed_symbols.add(req.symbol)
        self.logger.info("订阅品种: %s", req.symbol)

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅"""
        self.subscribed_symbols.discard(req.symbol)
        self.logger.info("取消订阅品种: %s", req.symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送订单（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """取消订单（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")

    def query_account(self) -> None:
        """查询账户信息（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")

    def query_position(self) -> None:
        """查询持仓信息（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")

    # ===== 回放控制功能 =====

    def pause(self) -> None:
        """暂停推送"""
        if not self._is_paused:
            self._is_paused = True
            self._pause_event.clear()
            self.logger.info("虚拟数据源已暂停")

    def resume(self) -> None:
        """恢复推送"""
        if self._is_paused:
            self._is_paused = False
            self._pause_event.set()
            self.logger.info("虚拟数据源已恢复")

    def set_speed(self, speed: float) -> None:
        """
        设置推送速度

        Args:
            speed: 速度倍率（1.0=实时，10.0=10倍速，100.0=100倍速）
        """
        self.push_speed = max(0.1, min(1000.0, speed))  # 限制在0.1x到1000x之间
        self.logger.info("虚拟数据源速度已设置为: %sx", self.push_speed)

    def jump_to_datetime(self, target_datetime: datetime) -> None:
        """
        跳转到指定时间

        Args:
            target_datetime: 目标时间
        """
        if target_datetime:
            self.start_datetime = target_datetime
            self._current_datetime = target_datetime

            # 重置推送位置
            for symbol in self.push_positions:
                self.push_positions[symbol] = 0

            self.logger.info("虚拟数据源已跳转到: %s", target_datetime)

    def get_current_datetime(self) -> Optional[datetime]:
        """获取当前回放时间"""
        return self._current_datetime or self.start_datetime


# ==================== 统一数据管理器（核心类） ====================


class UnifiedDataManager:
    """统一数据管理中枢

    核心职责：
    1. 数据源管理（TDX、虚拟、外部网关）
    2. 数据融合（本地存储 + 录制 + 实时）
    3. 查询式服务（给行情看板、策略中心）
    4. 订阅式服务（给交易策略）
    5. 预加载优化

    数据流向：
    - 外部实时数据网关（TDX数据源、虚拟数据源、CTP/IB等）
    - 内部本地数据（StorageManager）
    - Recording录制数据
    - 对外提供统一接口（查询式、订阅式）
    """

    _VIRTUAL_MODULES = {"backtest", "replay", "virtual_gateway", "virtual"}

    def __init__(
        self,
        engine: "ChinaStockEngine",
        *,
        preload_service: Optional["PreloadService"] = None,
    ) -> None:
        """初始化统一数据管理器

        Args:
            engine: ChinaStockEngine引擎实例
            preload_service: 预加载服务实例（可选）
        """
        self.engine = engine
        self.logger = logging.getLogger(__name__)

        # === 数据源管理 ===
        self.tdx_source: Optional[TdxDataSource] = None  # TDX数据源
        self.virtual_source: Optional[VirtualDataSource] = None  # 虚拟数据源
        self.external_gateways: Dict[str, BaseGateway] = {}  # 外部交易网关

        # === 本地数据管理 ===
        self.storage_manager = engine.storage_manager  # 本地存储管理器
        self.recording_manager = None  # 录制数据管理器（预留）

        # === 预加载服务 ===
        self.preload_service = preload_service

        # === 订阅管理（vnpy事件驱动） ===
        self.event_engine = engine.event_engine
        self._module_subscriptions: Dict[str, Set[str]] = {}  # 模块订阅映射
        self._module_gateways: Dict[str, str] = {}  # 模块使用的网关
        self._gateway_symbols: Dict[str, Set[str]] = {
            "tdx": set(),
            "virtual": set(),
            "polling": set(),  # 兼容旧代码
        }
        self._lock = Lock()

        # === 防止日志刷屏的标志位 ===
        self._cache_warning_shown = False  # 股票列表缓存缺失warning只显示一次

    # ==================== 对外接口：查询式 ====================

    def get_kline_data(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        check_gaps: bool = True,
        use_preload: bool = True,
    ) -> Optional[pd.DataFrame]:
        """查询K线数据（自动融合多数据源）

        数据融合顺序：
        1. 预加载缓存（如果use_preload=True）
        2. 本地存储（StorageManager）
        3. 录制数据（RecordingManager）
        4. 实时数据（当前活跃的数据源）

        Args:
            symbol: 品种代码
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            check_gaps: 是否检查缺口并触发自动下载
            use_preload: 是否使用预加载缓存

        Returns:
            DataFrame: K线数据，None表示无数据
        """
        frames = []

        # 1. 预加载缓存
        if use_preload and self.preload_service:
            cached = self.preload_service.get_cached_dataframe(symbol, interval)
            if cached is not None and not cached.empty:
                frames.append(cached)

        # 2. 本地存储
        storage_frame = self.engine.storage_manager.query_kline(
            symbol, interval, start_date, end_date
        )
        if storage_frame is not None and not storage_frame.empty:
            frames.append(storage_frame)

        # 3. 录制数据
        recording_frame = self._query_recording_layer(symbol, interval)
        if recording_frame is not None and not recording_frame.empty:
            frames.append(recording_frame)

        # 4. 实时数据
        realtime_frame = self._query_realtime_layer(symbol, interval)
        if realtime_frame is not None and not realtime_frame.empty:
            frames.append(realtime_frame)

        # 5. 融合去重
        merged = self._merge_frames(frames, interval)

        # 6. 缺口检查和自动下载
        if check_gaps and (merged is None or merged.empty):
            if config_manager.is_unified_manager_auto_download_enabled():
                self._trigger_backfill(symbol, start_date)
                storage_frame = self.engine.storage_manager.query_kline(
                    symbol, interval, start_date, end_date
                )
                merged = self._merge_frames(
                    [storage_frame] if storage_frame is not None else [], interval
                )

        if merged is None or merged.empty:
            return None

        # 7. 裁剪到指定范围
        trimmed = self._trim_range(merged, start_date, end_date)

        # 8. 触发预加载
        if check_gaps and config_manager.is_unified_manager_auto_download_enabled():
            self._enqueue_preload_if_needed(symbol, interval, trimmed)

        return trimmed

    def get_multi_kline_data(
        self,
        symbols: Sequence[str],
        *,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        check_gaps: bool = True,
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """批量查询K线数据

        Args:
            symbols: 品种代码列表
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            check_gaps: 是否检查缺口

        Returns:
            Dict: {品种代码: DataFrame}
        """
        result: Dict[str, Optional[pd.DataFrame]] = {}
        for symbol in symbols:
            result[symbol] = self.get_kline_data(
                symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )
        return result

    def query_unified(
        self,
        symbol: Optional[str] = None,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        **kwargs,
    ) -> Optional[Union[pd.DataFrame, Dict]]:
        """
        统一查询接口（兼容旧代码）

        自动判断单品种还是多品种查询，返回适当的格式。

        Args:
            symbol: 单品种代码（可选）
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            **kwargs: 其他参数
                - symbols: 多品种列表（与symbol互斥）
                - frequency: 周期别名（优先级低于interval）
                - check_gaps: 是否检查缺口（默认True）

        Returns:
            单品种：DataFrame 或 None
            多品种：Dict {"success": bool, "data": {symbol: []}, "interval": str, "message": str}
        """
        symbols_param = kwargs.get("symbols")
        frequency = kwargs.get("frequency") or interval
        check_gaps = kwargs.get("check_gaps", True)

        # 多品种查询路径
        if symbols_param is not None:
            symbols_list = (
                [symbols_param] if isinstance(symbols_param, str) else list(symbols_param)
            )
            if not symbols_list:
                return {"success": True, "data": {}, "interval": frequency, "message": None}

            # 调用多品种查询
            datasets = self.get_multi_kline_data(
                symbols_list,
                interval=frequency,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )

            # 转换为字典格式
            payload = {
                sym: (df.to_dict("records") if df is not None else [])
                for sym, df in datasets.items()
            }

            success = any(payload.values())
            return {
                "success": success,
                "data": payload,
                "interval": frequency,
                "message": None if success else "未查询到数据",
            }

        # 单品种查询路径
        target_symbol = symbol or kwargs.get("symbols")

        # 类型缩窄：处理 list/tuple 情况
        if isinstance(target_symbol, (list, tuple)):
            if len(target_symbol) > 0:
                target_symbol = target_symbol[0]
            else:
                target_symbol = None

        # 类型检查：确保是字符串类型
        if target_symbol is None or not isinstance(target_symbol, str):
            return None

        try:
            data = self.get_kline_data(
                target_symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )

            if data is not None and hasattr(data, "__len__"):
                self.logger.info(
                    "查询数据成功: %s %s, %d 条记录", target_symbol, interval, len(data)
                )
            else:
                self.logger.warning("未找到数据: %s %s", target_symbol, interval)

            return data

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", target_symbol, interval, e)
            return None

    # ==================== 对外接口：订阅式 ====================

    def subscribe(self, module: str, symbols: Iterable[str]) -> bool:
        """订阅实时数据（推送模式）

        根据模块类型自动路由到合适的数据源：
        - backtest/replay/virtual → 虚拟数据源
        - trading/strategy → TDX数据源或外部网关
        - 其他 → TDX数据源

        Args:
            module: 调用模块标识（用于路由）
            symbols: 品种列表

        Returns:
            bool: 是否订阅成功
        """
        gateway_name = self._resolve_gateway(module)
        gateway = self._get_gateway(gateway_name)
        if gateway is None:
            self.logger.warning("网关未初始化: %s", gateway_name)
            return False

        normalized = {s.strip() for s in symbols if s.strip()}
        if not normalized:
            return True

        with self._lock:
            module_symbols = self._module_subscriptions.get(module, set())
            new_symbols = normalized - module_symbols
            if not new_symbols:
                return True

            module_symbols.update(new_symbols)
            self._module_subscriptions[module] = module_symbols
            self._module_gateways[module] = gateway_name

            attach_set = self._gateway_symbols.setdefault(gateway_name, set())
            for symbol in sorted(new_symbols):
                if symbol in attach_set:
                    continue
                req = self._build_subscribe_request(symbol)
                if req is None:
                    continue
                try:
                    gateway.subscribe(req)
                    attach_set.add(symbol)
                    self.logger.info("订阅成功: %s → %s", symbol, gateway_name)
                except Exception as exc:  # pragma: no cover
                    self.logger.error("订阅 %s 失败: %s", symbol, exc, exc_info=True)
            return True

    def unsubscribe(self, module: str, symbols: Optional[Iterable[str]] = None) -> None:
        """取消订阅

        Args:
            module: 调用模块标识
            symbols: 品种列表（None表示取消该模块的所有订阅）
        """
        with self._lock:
            if module not in self._module_subscriptions:
                return

            gateway_name = self._module_gateways.get(module, "tdx")
            module_symbols = self._module_subscriptions[module]

            if symbols is None:
                removed = set(module_symbols)
                module_symbols.clear()
            else:
                targets = {s.strip() for s in symbols if s.strip()}
                removed = module_symbols & targets
                module_symbols.difference_update(targets)

            if not module_symbols:
                self._module_subscriptions.pop(module, None)
                self._module_gateways.pop(module, None)

            self._reconcile_gateway(gateway_name, removed)

    # ==================== 数据源管理接口 ====================

    def start_tdx_source(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """启动TDX数据源

        Args:
            config: 配置字典，包含：
                - interval/polling_interval: 轮询间隔（秒）
                - symbols: 订阅品种列表
                - max_servers: 最大使用服务器数量

        Returns:
            bool: 是否启动成功
        """
        try:
            if self.tdx_source is not None:
                self.logger.warning("TDX数据源已启动")
                return True

            setting = {}
            if config:
                if "interval" in config:
                    setting["轮询间隔（秒）"] = config["interval"]
                elif "polling_interval" in config:
                    setting["轮询间隔（秒）"] = config["polling_interval"]
                if "symbols" in config:
                    symbols_list = config["symbols"]
                    setting["品种列表"] = (
                        ",".join(symbols_list) if isinstance(symbols_list, list) else symbols_list
                    )
                if "max_servers" in config:
                    setting["最大服务器数"] = config["max_servers"]

            self.tdx_source = TdxDataSource.create_and_start(self.event_engine, setting)
            self.logger.info("✅ TDX数据源已启动")
            return True

        except Exception as e:
            self.logger.error("启动TDX数据源失败: %s", e, exc_info=True)
            self.tdx_source = None
            return False

    def stop_tdx_source(self) -> bool:
        """停止TDX数据源

        Returns:
            bool: 是否停止成功
        """
        try:
            if self.tdx_source is None:
                self.logger.warning("TDX数据源未运行")
                return True

            self.tdx_source.close()
            self.tdx_source = None
            self.logger.info("✅ TDX数据源已停止")
            return True

        except Exception as e:
            self.logger.error("停止TDX数据源失败: %s", e)
            return False

    def start_virtual_source(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """启动虚拟数据源

        Args:
            config: 配置字典，包含：
                - start_datetime: 起始时间（字符串格式：YYYY-MM-DD HH:MM:SS）
                - speed: 推送速度倍数
                - symbols: 订阅品种列表

        Returns:
            bool: 是否启动成功
        """
        try:
            if self.virtual_source is not None:
                self.logger.warning("虚拟数据源已启动")
                return True

            # 准备配置
            start_datetime = ""
            speed = 1.0
            symbols = None

            if config:
                start_datetime = config.get("start_datetime", "")
                speed = config.get("speed", 1.0)
                symbols = config.get("symbols")

            # 默认起始时间为昨天
            if not start_datetime:
                start_datetime = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

            self.virtual_source = VirtualDataSource.create_and_start(
                self.event_engine, start_datetime, speed, symbols
            )
            self.logger.info("✅ 虚拟数据源已启动")
            return True

        except Exception as e:
            self.logger.error("启动虚拟数据源失败: %s", e, exc_info=True)
            self.virtual_source = None
            return False

    def stop_virtual_source(self) -> bool:
        """停止虚拟数据源

        Returns:
            bool: 是否停止成功
        """
        try:
            if self.virtual_source is None:
                self.logger.warning("虚拟数据源未运行")
                return True

            self.virtual_source.close()
            self.virtual_source = None
            self.logger.info("✅ 虚拟数据源已停止")
            return True

        except Exception as e:
            self.logger.error("停止虚拟数据源失败: %s", e)
            return False

    def connect_external_gateway(self, gateway_name: str, gateway_instance: BaseGateway) -> bool:
        """连接外部交易网关（CTP、IB等）

        Args:
            gateway_name: 网关名称标识
            gateway_instance: vnpy网关实例

        Returns:
            bool: 是否连接成功
        """
        try:
            if gateway_name in self.external_gateways:
                self.logger.warning("外部网关 %s 已连接", gateway_name)
                return True

            self.external_gateways[gateway_name] = gateway_instance
            self.logger.info("✅ 外部网关 %s 已连接", gateway_name)
            return True

        except Exception as e:
            self.logger.error("连接外部网关 %s 失败: %s", gateway_name, e)
            return False

    def disconnect_external_gateway(self, gateway_name: str) -> bool:
        """断开外部交易网关

        Args:
            gateway_name: 网关名称标识

        Returns:
            bool: 是否断开成功
        """
        try:
            if gateway_name not in self.external_gateways:
                self.logger.warning("外部网关 %s 未连接", gateway_name)
                return True

            self.external_gateways.pop(gateway_name)
            # vnpy网关的关闭由外部管理
            self.logger.info("✅ 外部网关 %s 已断开", gateway_name)
            return True

        except Exception as e:
            self.logger.error("断开外部网关 %s 失败: %s", gateway_name, e)
            return False

    # ==================== 辅助方法（兼容旧代码） ====================

    def refresh_preload(self, symbols: Iterable[str], priority: bool = False) -> None:
        """刷新预加载缓存

        Args:
            symbols: 品种列表
            priority: 是否优先处理
        """
        if not self.preload_service:
            return
        for symbol in symbols:
            self.preload_service.enqueue(symbol, priority=priority)

    # ==================== 内部实现方法 ====================

    def _resolve_gateway(self, module: str) -> str:
        """根据模块确定数据源

        路由规则：
        - backtest/replay/virtual → virtual（虚拟数据源）
        - 其他 → tdx（TDX数据源）
        """
        return "virtual" if module.lower() in self._VIRTUAL_MODULES else "tdx"

    def _get_gateway(self, gateway_name: str) -> Optional[BaseGateway]:
        """获取网关实例（按需启动）

        Args:
            gateway_name: 网关名称（"tdx", "virtual", 或外部网关名称）

        Returns:
            BaseGateway实例或None
        """
        # 虚拟数据源
        if gateway_name == "virtual":
            if self.virtual_source is None:
                if not self.start_virtual_source():
                    return None
            return self.virtual_source

        # TDX数据源
        if gateway_name == "tdx" or gateway_name == "polling":  # polling为兼容旧代码
            if self.tdx_source is None:
                if not self.start_tdx_source():
                    return None
            return self.tdx_source

        # 外部网关
        return self.external_gateways.get(gateway_name)

    def _reconcile_gateway(self, gateway_name: str, removed: Set[str]) -> None:
        """协调网关订阅（取消不再需要的订阅）

        Args:
            gateway_name: 网关名称
            removed: 已移除的品种集合
        """
        gateway = self._get_gateway(gateway_name)
        if gateway is None:
            return

        # 计算仍需要的品种
        required: Set[str] = set()
        for module, module_symbols in self._module_subscriptions.items():
            if self._module_gateways.get(module, "tdx") == gateway_name:
                required.update(module_symbols)

        attach_set = self._gateway_symbols.setdefault(gateway_name, set())
        obsolete = (attach_set - required) & removed if removed else attach_set - required
        for symbol in sorted(obsolete):
            req = self._build_subscribe_request(symbol)
            if req is None:
                continue
            try:
                if hasattr(gateway, "unsubscribe"):
                    gateway.unsubscribe(req)  # type: ignore[attr-defined]
                    self.logger.info("取消订阅: %s ← %s", symbol, gateway_name)
            except Exception as exc:  # pragma: no cover
                self.logger.error("取消订阅 %s 失败: %s", symbol, exc, exc_info=True)
            attach_set.discard(symbol)

    def _build_subscribe_request(self, symbol: str) -> Optional[SubscribeRequest]:
        """构建订阅请求

        Args:
            symbol: 品种代码

        Returns:
            SubscribeRequest或None
        """
        exchange = self._infer_exchange(symbol)
        if exchange is None:
            self.logger.debug("无法识别交易所: %s", symbol)
            return None
        return SubscribeRequest(symbol=symbol, exchange=exchange)

    def _infer_exchange(self, symbol: str) -> Optional[Exchange]:
        """推断交易所

        Args:
            symbol: 品种代码

        Returns:
            Exchange或None
        """
        if not symbol:
            return None
        code = symbol.strip()
        if code.startswith("6") or code.startswith("9"):
            return Exchange.SSE
        if code.startswith("0") or code.startswith("3"):
            return Exchange.SZSE
        if code.startswith("8"):
            # 北交所暂映射为深交所对象，后续可扩展
            return Exchange.SZSE
        return None

    def _merge_frames(
        self, frames: Iterable[Optional[pd.DataFrame]], interval: str  # noqa: ARG002
    ) -> Optional[pd.DataFrame]:
        """融合多个数据帧（保持现有实现）

        Args:
            frames: 数据帧列表
            interval: 周期（预留参数，用于未来扩展）

        Returns:
            融合后的DataFrame或None
        """
        _ = interval  # 预留参数
        normalized = []
        for frame in frames:
            prepared = self._normalize_frame(frame)
            if prepared is not None and not prepared.empty:
                normalized.append(prepared)

        if not normalized:
            return None

        merged = pd.concat(normalized, ignore_index=True)  # type: ignore[arg-type]
        if "datetime" in merged.columns:
            merged["datetime"] = pd.to_datetime(merged["datetime"])
            merged = merged.drop_duplicates(subset="datetime", keep="last")
            merged = merged.sort_values("datetime")
        return merged.reset_index(drop=True)

    def _normalize_frame(self, frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """规范化数据帧格式

        Args:
            frame: 原始数据帧

        Returns:
            规范化后的DataFrame或None
        """
        if frame is None or frame.empty:
            return None
        df = frame.copy()
        if "datetime" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                index_name = df.index.name or "index"
                df = df.reset_index().rename(columns={index_name: "datetime"})
            else:
                df = df.reset_index(drop=False)
                if "datetime" not in df.columns and df.columns.size > 0:
                    candidate = str(df.columns[0])
                    if candidate != "datetime":
                        df = df.rename(columns={candidate: "datetime"})
        if "datetime" not in df.columns:
            return df
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])
        return df

    def _trim_range(
        self,
        frame: pd.DataFrame,
        start_date: Optional[Union[str, date]],
        end_date: Optional[Union[str, date]],
    ) -> pd.DataFrame:
        """裁剪数据到指定日期范围

        Args:
            frame: 数据帧
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            裁剪后的DataFrame
        """
        if "datetime" not in frame.columns:
            return frame

        series = frame["datetime"]
        start = self._to_timestamp(start_date) if start_date else None
        end = self._to_timestamp(end_date) if end_date else None

        mask = pd.Series([True] * len(frame))
        if start is not None:
            mask &= series >= start
        if end is not None:
            mask &= series <= end
        return frame.loc[mask].reset_index(drop=True)

    def _to_timestamp(self, value: Union[str, date, datetime]) -> Timestamp:
        """转换为Timestamp

        Args:
            value: 日期值

        Returns:
            Timestamp
        """
        if isinstance(value, datetime):
            return cast(Timestamp, pd.Timestamp(value))
        if isinstance(value, date):
            return cast(Timestamp, pd.Timestamp(datetime.combine(value, datetime.min.time())))
        return cast(Timestamp, pd.to_datetime(value))

    def _trigger_backfill(self, symbol: str, start_date: Optional[Union[str, date]]) -> None:
        """触发数据回填（自动下载）

        Args:
            symbol: 品种代码
            start_date: 开始日期
        """
        if start_date is None:
            return
        if isinstance(start_date, str):
            start = start_date
        elif isinstance(start_date, datetime):
            start = start_date.strftime("%Y-%m-%d")
        else:
            start = start_date.strftime("%Y-%m-%d")
        self.logger.info("触发自动增量下载: %s 从 %s", symbol, start)
        try:
            self.engine.download_incremental(start)
        except Exception as exc:  # pragma: no cover
            self.logger.error("自动下载失败: %s", exc, exc_info=True)

    def _enqueue_preload_if_needed(
        self,
        symbol: str,
        interval: str,
        frame: Optional[pd.DataFrame],
    ) -> None:
        """如果需要，触发预加载

        Args:
            symbol: 品种代码
            interval: 周期
            frame: 数据帧
        """
        if not self.preload_service:
            return
        if frame is None or frame.empty:
            self.preload_service.enqueue(symbol, intervals=[interval], priority=True)

    def _query_recording_layer(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """查询录制数据层（vnpy_datarecorder）

        Args:
            symbol: 品种代码
            interval: 周期

        Returns:
            DataFrame或None
        """
        try:
            # 检查是否有可用的引擎
            if not hasattr(self, "engine") or not self.engine:
                return None

            # 尝试获取DataRecorder引擎
            try:
                from vnpy_datarecorder import DataRecorderEngine  # noqa: F401
            except ImportError:
                self.logger.debug("vnpy_datarecorder未安装，跳过录制数据查询")
                return None

            # 从engine获取main_engine（ChinaStockEngine继承自BaseEngine）
            main_engine = getattr(self.engine, "main_engine", None)
            if not main_engine:
                return None

            recorder = main_engine.get_engine("DataRecorder")
            if not recorder:
                return None

            # 转换周期格式
            interval_map = {
                "1d": "1d",
                "1h": "1h",
                "30m": "30m",
                "15m": "15m",
                "5m": "5m",
                "1m": "1m",
            }

            vnpy_interval = interval_map.get(interval)
            if not vnpy_interval:
                return None

            # 查询录制的K线数据
            from vnpy.trader.object import Exchange
            from datetime import datetime, timedelta

            # 查询最近一年的数据
            end = datetime.now()
            start = end - timedelta(days=365)

            # 构造vt_symbol（需要交易所后缀）
            # 根据代码判断交易所
            if symbol.startswith("6"):
                exchange = Exchange.SSE
            elif symbol.startswith(("0", "3")):
                exchange = Exchange.SZSE
            elif symbol.startswith(("8", "4")):
                exchange = Exchange.BSE
            else:
                exchange = Exchange.SSE

            vt_symbol = f"{symbol}.{exchange.value}"

            # 查询K线数据
            bars = recorder.query_bar_data(
                vt_symbol=vt_symbol, interval=vnpy_interval, start=start, end=end
            )

            if not bars:
                return None

            # 转换为DataFrame
            data = pd.DataFrame(
                [
                    {
                        "datetime": bar.datetime,
                        "open": bar.open_price,
                        "high": bar.high_price,
                        "low": bar.low_price,
                        "close": bar.close_price,
                        "volume": bar.volume,
                        "turnover": getattr(bar, "turnover", 0),
                    }
                    for bar in bars
                ]
            )

            self.logger.debug(f"从录制数据查询到 {len(data)} 条K线: {symbol} {interval}")
            return data

        except Exception as e:
            self.logger.warning(f"查询录制数据失败: {symbol} {interval} - {e}")
            return None

    def _query_realtime_layer(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """查询实时推送缓存数据

        Args:
            symbol: 品种代码
            interval: 周期

        Returns:
            DataFrame或None
        """
        try:
            import time

            # 检查是否有实时数据缓存
            if not hasattr(self, "_realtime_cache"):
                self._realtime_cache = {}

            # 构造缓存键
            cache_key = f"{symbol}_{interval}"

            # 从内存缓存中获取
            if cache_key in self._realtime_cache:
                cached_data = self._realtime_cache[cache_key]

                # 检查缓存是否过期（5分钟）
                cache_time = cached_data.get("timestamp", 0)
                if time.time() - cache_time < 300:  # 5分钟内有效
                    data = cached_data.get("data")
                    if data is not None and not data.empty:
                        self.logger.debug(
                            f"从实时缓存获取到 {len(data)} 条K线: {symbol} {interval}"
                        )
                        return data.copy()

            # 缓存未命中或过期
            return None

        except Exception as e:
            self.logger.warning(f"查询实时推送数据失败: {symbol} {interval} - {e}")
            return None

    def _update_realtime_cache(self, symbol: str, interval: str, data: pd.DataFrame):
        """更新实时数据缓存（由数据推送回调调用）

        Args:
            symbol: 品种代码
            interval: 周期
            data: K线数据
        """
        import time

        if not hasattr(self, "_realtime_cache"):
            self._realtime_cache = {}

        cache_key = f"{symbol}_{interval}"
        self._realtime_cache[cache_key] = {"data": data.copy(), "timestamp": time.time()}

        # 限制缓存大小（最多保留100个品种×周期）
        if len(self._realtime_cache) > 100:
            # 删除最旧的缓存
            oldest_key = min(
                self._realtime_cache.keys(), key=lambda k: self._realtime_cache[k]["timestamp"]
            )
            del self._realtime_cache[oldest_key]

    # ==================== vnpy 标准接口（供 vnpy_chartwizard 使用）====================

    def get_all_contracts(self) -> List[ContractData]:
        """获取所有合约信息（vnpy标准接口）

        从缓存的股票列表转换为 vnpy ContractData 格式
        供 vnpy_chartwizard 显示代码联想

        Returns:
            List[ContractData]: 合约信息列表
        """
        try:
            # 读取股票列表缓存
            cache_file = config_manager.get_cache_dir() / "stock_list_classified.json"

            if not cache_file.exists():
                # 只在首次缺失时warning，避免刷屏
                if not self._cache_warning_shown:
                    self.logger.warning("股票列表缓存文件不存在: %s（后续将静默）", cache_file)
                    self._cache_warning_shown = True
                else:
                    self.logger.debug("股票列表缓存文件不存在: %s", cache_file)
                return []

            import json

            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            contracts = []
            classified_data = cache_data.get("data", {}).get("classified", {})

            # 遍历所有分类
            for _category, stocks in classified_data.items():
                for stock in stocks:
                    code = stock.get("code", "")
                    name = stock.get("name", "")
                    market = stock.get("market", 0)

                    # 判断交易所
                    if market == 1:  # 上交所
                        exchange = Exchange.SSE
                    elif market == 0:  # 深交所
                        exchange = Exchange.SZSE
                    elif market == 2:  # 北交所
                        exchange = Exchange.BSE
                    else:
                        exchange = Exchange.SSE  # 默认

                    # 创建 ContractData 对象
                    contract = ContractData(
                        symbol=code,
                        exchange=exchange,
                        name=name,
                        product=Product.EQUITY,
                        size=100,  # A股标准手数
                        pricetick=0.01,  # A股最小变动价位
                        gateway_name="UnifiedDataManager",
                    )
                    contracts.append(contract)

            self.logger.info("已加载 %d 个合约信息", len(contracts))
            return contracts

        except Exception as e:
            self.logger.error("获取合约信息失败: %s", e, exc_info=True)
            return []

    def load_bar_data(
        self, symbol: str, exchange: Exchange, interval: Interval, start: datetime, end: datetime
    ) -> List[BarData]:
        """加载历史K线数据（vnpy标准接口）

        调用现有的 get_kline_data() 方法，转换为 vnpy BarData 格式
        供 vnpy_chartwizard 绘制K线图

        Args:
            symbol: 品种代码（如 "000001"）
            exchange: 交易所
            interval: 周期
            start: 开始时间
            end: 结束时间

        Returns:
            List[BarData]: K线数据列表
        """
        try:
            # 转换周期格式
            interval_str = self._convert_interval_to_string(interval)

            # 转换日期格式
            start_date = start.strftime("%Y-%m-%d")
            end_date = end.strftime("%Y-%m-%d")

            # 调用现有方法获取数据
            df = self.get_kline_data(
                symbol=symbol,
                interval=interval_str,
                start_date=start_date,
                end_date=end_date,
                check_gaps=False,
                use_preload=True,
            )

            if df is None or df.empty:
                self.logger.warning("未找到品种 %s 的K线数据", symbol)
                return []

            # 转换为 BarData 列表
            bars = []
            for idx, row in df.iterrows():
                # 确保 datetime 是 datetime 对象
                if isinstance(idx, Timestamp):
                    dt = idx.to_pydatetime()
                elif isinstance(idx, datetime):
                    dt = idx
                else:
                    try:
                        dt = pd.to_datetime(str(idx)).to_pydatetime()
                    except Exception:
                        continue

                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=dt,
                    interval=interval,
                    volume=float(row.get("volume") or 0),
                    turnover=float(row.get("amount") or 0),
                    open_interest=0,
                    open_price=float(row.get("open") or 0),
                    high_price=float(row.get("high") or 0),
                    low_price=float(row.get("low") or 0),
                    close_price=float(row.get("close") or 0),
                    gateway_name="UnifiedDataManager",
                )
                bars.append(bar)

            self.logger.info("加载了 %d 根K线数据：%s %s", len(bars), symbol, interval_str)
            return bars

        except Exception as e:
            self.logger.error("加载K线数据失败: %s", e, exc_info=True)
            return []

    def _convert_interval_to_string(self, interval: Interval) -> str:
        """将 vnpy Interval 枚举转换为项目使用的周期字符串

        Args:
            interval: vnpy Interval 枚举

        Returns:
            str: 周期字符串（如 "1d", "1m", "5m"）
        """
        mapping = {
            Interval.MINUTE: "1m",
            Interval.HOUR: "60m",
            Interval.DAILY: "1d",
            Interval.WEEKLY: "1w",
            Interval.TICK: "tick",
        }
        return mapping.get(interval, "1d")


# ==================== 预加载服务 ====================


class PreloadService:
    """数据预加载服务（整合优化版）

    增强功能：
    - 智能预加载策略
    - 多级缓存管理
    - 异步加载优化
    - 与数据源联动
    """

    QUEUE_WAIT_SECONDS = 1.0

    def __init__(self, engine: "ChinaStockEngine") -> None:
        """初始化预加载服务

        Args:
            engine: ChinaStockEngine引擎实例
        """
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

    def start(self, prime: bool = True) -> None:
        """启动预加载服务

        Args:
            prime: 是否预加载常用品种
        """
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run, name="DataPreloadWorker", daemon=True)
        self._worker.start()
        self.logger.info("预加载服务已启动")
        if prime:
            self.prime_with_frequently_used()

    def stop(self) -> None:
        """停止预加载服务"""
        if not self._running:
            return
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        self.logger.info("预加载服务已停止")

    def enqueue(
        self, symbol: str, *, intervals: Optional[Iterable[str]] = None, priority: bool = False
    ) -> None:
        """将品种加入预加载队列

        Args:
            symbol: 品种代码
            intervals: 周期列表（可选）
            priority: 是否优先处理
        """
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

    def preload_now(self, symbol: str, *, intervals: Optional[Iterable[str]] = None) -> None:
        """立即预加载（高优先级）

        Args:
            symbol: 品种代码
            intervals: 周期列表（可选）
        """
        self.enqueue(symbol, intervals=intervals, priority=True)

    def prime_with_frequently_used(self) -> None:
        """预加载常用品种"""
        symbols = config_manager.get_preload_frequently_used_symbols()
        for symbol in symbols:
            self.enqueue(symbol, priority=False)

    def get_cached_dataframe(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """获取缓存的数据帧

        Args:
            symbol: 品种代码
            interval: 周期

        Returns:
            DataFrame或None
        """
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

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计字典
        """
        with self._cache_lock, self._queue_lock:
            return {
                **self._stats,
                "cached_symbols": len(self._cache),
                "queue_size": len(self._queue),
                "max_cache_symbols": self._max_cache_symbols,
            }

    def clear_cache(self) -> None:
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()
            self._cache_meta.clear()
            self._cache_order.clear()

    def _run(self) -> None:
        """预加载工作线程主循环"""
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

    def _next_task(self) -> Optional[Tuple[str, Optional[Tuple[str, ...]]]]:
        """获取下一个任务

        Returns:
            (品种代码, 周期元组)或None
        """
        with self._queue_lock:
            if not self._queue:
                return None
            symbol, intervals = self._queue.popleft()
            self._pending.discard(symbol)
            return symbol, intervals

    def _execute(self, symbol: str, intervals: Tuple[str, ...]) -> None:
        """执行预加载任务

        Args:
            symbol: 品种代码
            intervals: 周期元组
        """
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

    def _store(self, symbol: str, interval: str, frame: pd.DataFrame) -> None:
        """存储到缓存

        Args:
            symbol: 品种代码
            interval: 周期
            frame: 数据帧
        """
        with self._cache_lock:
            if symbol not in self._cache:
                if len(self._cache) >= self._max_cache_symbols:
                    self._evict_oldest()
                self._cache[symbol] = {}
                self._cache_meta[symbol] = {}
                self._cache_order.append(symbol)
            self._cache[symbol][interval] = frame.copy(deep=False)
            self._cache_meta[symbol][interval] = datetime.now()

    def _evict_oldest(self) -> None:
        """驱逐最旧的缓存项"""
        while self._cache_order:
            candidate = self._cache_order.popleft()
            if candidate in self._cache:
                del self._cache[candidate]
                del self._cache_meta[candidate]
                break


# ==================== 向后兼容导出 ====================

# 为了兼容旧代码，提供别名
PollingGateway = TdxDataSource
VirtualGateway = VirtualDataSource


# ==============================================================================
# 导出列表
# ==============================================================================

__all__ = [
    # 第1部分：智能调优器
    "IntelligentAdaptiveTuner",
    # 第2部分：缓存和内存管理
    "CacheEntry",
    "CacheStats",
    "LRUCacheManager",
    "create_lru_cache",
    "lru_cache",
    "SharedMemoryManager",
    "create_shared_validation_context",
    # 第3部分：数据验证器
    "StatelessValidationResult",
    "ValidationContext",
    "StatelessValidator",
    "validate_symbol_stateless",
    "GPUDetector",
    "GPUValidator",
    "IncrementalScanManager",
    # 第4部分：统一数据管理器
    "UnifiedDataManager",
    "TdxDataSource",
    "VirtualDataSource",
    "PreloadService",
]
