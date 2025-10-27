# -*- coding: utf-8 -*-
# cython: language_level=3
import asyncio
import functools
import logging
import time
from typing import Dict, Optional

import sys

# 确保stdout使用UTF-8编码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ✅ 不手动创建handler，依赖LoggingHub统一管理
logger = logging.getLogger("tdx_asyncio")
logger_perf = logging.getLogger("metric.tdx_asyncio")  # 性能专用logger


def async_timeit(func):
    """
    异步性能计时装饰器

    装饰异步函数，自动记录执行时间并输出到日志。

    用法：
    @async_timeit
    async def my_async_function():
        await asyncio.sleep(1)
        return "result"
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()  # ✅ 使用perf_counter更精确
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start

        # ✅ 使用性能logger，DEBUG级别
        if elapsed > 1:
            logger_perf.debug("函数=%s, 耗时=%.2fs", func.__name__, elapsed)
        else:
            logger_perf.debug("函数=%s, 耗时=%.2fms", func.__name__, elapsed * 1000)

        # ✅ 慢查询告警（>5s）
        if elapsed > 5:
            logger.warning("TDX慢查询: 函数=%s, 耗时=%.2fs", func.__name__, elapsed)

        return result

    return wrapper


def sync_timeit(func):
    """
    同步性能计时装饰器（优化版）

    装饰同步函数，自动记录执行时间并输出到日志。
    使用perf_counter进行更精确的计时，自动选择合适的时间单位。

    用法：
    @sync_timeit
    def my_sync_function():
        time.sleep(1)
        return "result"
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()  # 使用perf_counter获取更精确的计时
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start

        # ✅ 使用性能logger，DEBUG级别
        if elapsed > 1:
            logger_perf.debug("函数=%s, 耗时=%.2fs", func.__name__, elapsed)
        else:
            logger_perf.debug("函数=%s, 耗时=%.2fms", func.__name__, elapsed * 1000)

        # ✅ 慢查询告警（>5s）
        if elapsed > 5:
            logger.warning("TDX慢查询: 函数=%s, 耗时=%.2fs", func.__name__, elapsed)

        return result

    return wrapper


class PerformanceMonitor:
    """
    性能监控工具类

    用于监控异步函数的执行时间和调用频率。
    """

    def __init__(self):
        self.stats = {}  # {function_name: {'count': int, 'total_time': float, 'avg_time': float}}

    def record(self, func_name: str, elapsed: float):
        """记录函数执行统计"""
        if func_name not in self.stats:
            self.stats[func_name] = {"count": 0, "total_time": 0.0, "avg_time": 0.0}

        stats = self.stats[func_name]
        stats["count"] += 1
        stats["total_time"] += elapsed
        stats["avg_time"] = stats["total_time"] / stats["count"]

    def get_stats(self, func_name: Optional[str] = None) -> dict:
        """获取统计信息"""
        if func_name:
            return self.stats.get(func_name, {})
        return self.stats.copy()

    def reset(self, func_name: Optional[str] = None):
        """重置统计信息"""
        if func_name:
            if func_name in self.stats:
                del self.stats[func_name]
        else:
            self.stats.clear()

    def print_summary(self):
        """打印统计摘要"""
        if not self.stats:
            logger_perf.debug("无性能统计数据")
            return

        logger_perf.info("=== TDX性能统计摘要 ===")
        for func_name, stats in sorted(self.stats.items()):
            # ✅ 使用%格式化
            logger_perf.info(
                "函数=%s, 调用=%d次, 总耗时=%.3fs, 平均=%.3fs",
                func_name,
                stats["count"],
                stats["total_time"],
                stats["avg_time"],
            )


# 全局性能监控实例
performance_monitor = PerformanceMonitor()


def async_timeit_with_stats(func):
    """
    带统计的异步性能计时装饰器

    除了计时外，还收集性能统计信息。

    用法：
    @async_timeit_with_stats
    async def my_function():
        await asyncio.sleep(0.1)
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()  # ✅ 使用perf_counter更精确
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start

        # 记录统计
        performance_monitor.record(func.__name__, elapsed)

        # ✅ 使用性能logger，DEBUG级别
        if elapsed > 1:
            logger_perf.debug("函数=%s, 耗时=%.2fs", func.__name__, elapsed)
        else:
            logger_perf.debug("函数=%s, 耗时=%.2fms", func.__name__, elapsed * 1000)

        # ✅ 慢查询告警（>5s）
        if elapsed > 5:
            logger.warning("TDX慢查询: 函数=%s, 耗时=%.2fs", func.__name__, elapsed)

        return result

    return wrapper
