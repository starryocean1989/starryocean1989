# -*- coding: utf-8 -*-
# cython: language_level=3
import asyncio
import functools
import logging
import time
from typing import Dict, Optional

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(formatter)

logger = logging.getLogger("tdx_asyncio")
logger.addHandler(console)
logger.setLevel(logging.INFO)


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
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start

        # 根据执行时间选择合适的单位
        if elapsed > 1:
            logger.debug(f"{func.__name__} 耗时: {elapsed:.2f}s")
        else:
            logger.debug(f"{func.__name__} 耗时: {elapsed*1000:.2f}ms")

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
        delta = time.perf_counter() - start

        # 自动选择合适的时间单位（参考mootdx）
        if delta > 1:
            time_str = f'{delta:.1f}s'
        else:
            time_str = f'{delta*1000:.1f}ms'

        # 优化输出格式
        logger.debug(f'Function {func.__name__} time: {time_str}')

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
            self.stats[func_name] = {'count': 0, 'total_time': 0.0, 'avg_time': 0.0}

        stats = self.stats[func_name]
        stats['count'] += 1
        stats['total_time'] += elapsed
        stats['avg_time'] = stats['total_time'] / stats['count']

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
            logger.info("无性能统计数据")
            return

        logger.info("=== 性能统计摘要 ===")
        for func_name, stats in sorted(self.stats.items()):
            logger.info(
                f"{func_name}: 调用{stats['count']}次, "
                f"总耗时{stats['total_time']:.3f}s, "
                f"平均{stats['avg_time']:.3f}s"
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
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start

        # 记录统计
        performance_monitor.record(func.__name__, elapsed)

        # 根据执行时间选择合适的单位
        if elapsed > 1:
            logger.debug(f"{func.__name__} 耗时: {elapsed:.2f}s")
        else:
            logger.debug(f"{func.__name__} 耗时: {elapsed*1000:.2f}ms")

        return result

    return wrapper

