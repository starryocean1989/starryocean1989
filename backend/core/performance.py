# -*- coding: utf-8 -*-
"""
性能优化模块.

提供缓存机制、异步处理、性能监控等优化功能
"""

import asyncio
import functools
import logging
import threading
import time
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import UnifiedMarketData
    from .vnpy_integration import TerminalEngine


class Cache:
    """通用缓存类."""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """初始化缓存.

        Args:
            max_size: 最大缓存大小
            ttl: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

    def get(self, key: str) -> Any:
        """获取缓存项."""
        with self._lock:
            if key not in self._cache:
                return None

            # 检查是否过期
            if time.time() - self._timestamps[key] > self.ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None

            # 移动到最近使用位置（LRU）
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: Any):
        """添加缓存项."""
        with self._lock:
            # 如果已存在，先删除
            if key in self._cache:
                del self._cache[key]
                del self._timestamps[key]

            # 检查是否超过最大大小
            if len(self._cache) >= self.max_size:
                # 删除最老的项
                oldest_key, _ = self._cache.popitem(last=False)
                del self._timestamps[oldest_key]

            # 添加新项
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def clear(self):
        """清空缓存."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def size(self) -> int:
        """获取缓存大小."""
        with self._lock:
            return len(self._cache)

    def cleanup_expired(self):
        """清理过期项."""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in self._timestamps.items()
                if current_time - timestamp > self.ttl
            ]

            for key in expired_keys:
                del self._cache[key]
                del self._timestamps[key]

            if expired_keys:
                self.logger.debug("清理过期缓存项: %s 个", len(expired_keys))


class DataCache:
    """数据缓存管理器."""

    def __init__(self):
        """初始化数据缓存管理器."""
        self.market_data_cache = Cache(max_size=5000, ttl=300)  # 5分钟过期
        self.order_cache = Cache(max_size=1000, ttl=600)       # 10分钟过期
        self.position_cache = Cache(max_size=1000, ttl=300)    # 5分钟过期
        self.logger = logging.getLogger(__name__)

        # 启动定期清理线程
        cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        cleanup_thread.start()

    def _cleanup_loop(self):
        """定期清理过期缓存."""
        while True:
            try:
                time.sleep(60)  # 每分钟清理一次
                self.market_data_cache.cleanup_expired()
                self.order_cache.cleanup_expired()
                self.position_cache.cleanup_expired()
            except (RuntimeError, AttributeError, KeyError) as e:
                self.logger.error("缓存清理失败: %s", e)

    def cache_market_data(self, symbol: str, data: List["UnifiedMarketData"]):
        """缓存行情数据."""
        key = f"market_{symbol}"
        self.market_data_cache.put(key, data)

    def get_market_data(
        self, symbol: str
    ) -> Optional[List["UnifiedMarketData"]]:
        """获取缓存的行情数据."""
        key = f"market_{symbol}"
        return self.market_data_cache.get(key)

    def cache_order(self, order_id: str, order: Any):
        """缓存订单."""
        key = f"order_{order_id}"
        self.order_cache.put(key, order)

    def get_order(self, order_id: str) -> Any:
        """获取缓存的订单."""
        key = f"order_{order_id}"
        return self.order_cache.get(key)

    def cache_position(self, symbol: str, position: Any):
        """缓存持仓."""
        key = f"position_{symbol}"
        self.position_cache.put(key, position)

    def get_position(self, symbol: str) -> Any:
        """获取缓存的持仓."""
        key = f"position_{symbol}"
        return self.position_cache.get(key)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        return {
            "market_data_cache": {
                "size": self.market_data_cache.size(),
                "max_size": self.market_data_cache.max_size
            },
            "order_cache": {
                "size": self.order_cache.size(),
                "max_size": self.order_cache.max_size
            },
            "position_cache": {
                "size": self.position_cache.size(),
                "max_size": self.position_cache.max_size
            }
        }


class AsyncTaskManager:
    """异步任务管理器."""

    def __init__(self, max_workers: int = 10):
        """初始化异步任务管理器."""
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.loop = None
        self.logger = logging.getLogger(__name__)
        self._tasks: Dict[str, Any] = {}
        self._results: Dict[str, Any] = {}

    def start_event_loop(self):
        """启动事件循环."""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # 在线程中运行事件循环
            def run_loop():
                try:
                    self.loop.run_forever()
                except (RuntimeError, KeyboardInterrupt) as e:
                    self.logger.error("事件循环异常: %s", e)

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()
            self.logger.info("异步任务管理器启动完成")

        except (RuntimeError, OSError) as e:
            self.logger.error("启动事件循环失败: %s", e)

    def stop_event_loop(self):
        """停止事件循环."""
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.executor.shutdown(wait=True)
                self.logger.info("异步任务管理器停止完成")
            except (RuntimeError, AttributeError) as e:
                self.logger.error("停止事件循环失败: %s", e)

    def get_task_stats(self) -> Dict[str, int]:
        """获取任务统计信息."""
        return {
            "active_tasks": len(self._tasks),
            "completed_tasks": len(self._results),
            "max_workers": self.max_workers
        }

    def submit_task(
        self, task_id: str, func: Callable, *args, **kwargs
    ) -> str:
        """提交异步任务."""
        def task_wrapper():
            try:
                result = func(*args, **kwargs)
                self._results[task_id] = {"success": True, "result": result}
            except (RuntimeError, TypeError, ValueError, AttributeError) as e:
                self.logger.error("任务执行失败 %s: %s", task_id, e)
                self._results[task_id] = {"success": False, "error": str(e)}

        future = self.executor.submit(task_wrapper)
        self._tasks[task_id] = future
        return task_id

    def submit_asyncio_task(
        self, coroutine_func: Callable, *args, **kwargs
    ) -> str:
        """提交异步协程任务."""
        if not self.loop:
            self.start_event_loop()

        task_id = f"asyncio_{len(self._tasks)}"

        async def wrapper():
            try:
                if asyncio.iscoroutinefunction(coroutine_func):
                    result = await coroutine_func(*args, **kwargs)
                else:
                    result = coroutine_func(*args, **kwargs)
                self._results[task_id] = {"success": True, "result": result}
            except (RuntimeError, TypeError, ValueError, AttributeError) as e:
                self.logger.error("异步任务执行失败 %s: %s", task_id, e)
                self._results[task_id] = {"success": False, "error": str(e)}

        future = asyncio.run_coroutine_threadsafe(wrapper(), self.loop)
        self._tasks[task_id] = future
        return task_id

    def get_task_result(self, task_id: str, timeout: float = 10.0) -> Any:
        """获取任务结果."""
        if task_id not in self._tasks:
            return {"success": False, "error": "任务不存在"}

        future = self._tasks[task_id]

        try:
            # 等待任务完成
            if hasattr(future, 'result'):
                result = future.result(timeout=timeout)
            else:
                # asyncio future
                result = (
                    future.get(timeout=timeout)
                    if hasattr(future, 'get') else None
                )

            # 获取结果
            if task_id in self._results:
                task_result = self._results.pop(task_id)
                return task_result

            return {"success": True, "result": result}

        except (TimeoutError, RuntimeError) as e:
            return {"success": False, "error": str(e)}
        finally:
            # 清理任务
            if task_id in self._tasks:
                del self._tasks[task_id]

    def cancel_task(self, task_id: str) -> bool:
        """取消任务."""
        if task_id not in self._tasks:
            return False

        future = self._tasks[task_id]
        cancelled = future.cancel()

        if cancelled:
            if task_id in self._results:
                del self._results[task_id]
            del self._tasks[task_id]

        return cancelled


class PerformanceOptimizer:
    """性能优化器."""

    def __init__(self, terminal_engine: "TerminalEngine"):
        """初始化性能优化器."""
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)

        # 初始化组件
        self.data_cache = DataCache()
        self.task_manager = AsyncTaskManager()

        # 性能监控
        self._performance_stats = defaultdict(list)
        self._optimization_enabled = True

        # 启动优化
        self.start_optimization()

    def start_optimization(self):
        """启动性能优化."""
        self.task_manager.start_event_loop()
        self.logger.info("性能优化器启动完成")

    def stop_optimization(self):
        """停止性能优化."""
        self.task_manager.stop_event_loop()
        self.logger.info("性能优化器停止完成")

    def cache_data(self, data_type: str, key: str, data: Any):
        """缓存数据."""
        if data_type == "market":
            if isinstance(data, list):
                self.data_cache.cache_market_data(key, data)
            else:
                # 单条数据，转为列表
                self.data_cache.cache_market_data(key, [data])
        elif data_type == "order":
            self.data_cache.cache_order(key, data)
        elif data_type == "position":
            self.data_cache.cache_position(key, data)

    def get_cached_data(self, data_type: str, key: str) -> Any:
        """获取缓存数据."""
        if data_type == "market":
            return self.data_cache.get_market_data(key)
        elif data_type == "order":
            return self.data_cache.get_order(key)
        elif data_type == "position":
            return self.data_cache.get_position(key)
        return None

    def submit_async_task(
        self, task_id: str, func: Callable, *args, **kwargs
    ) -> str:
        """提交异步任务."""
        return self.task_manager.submit_task(task_id, func, *args, **kwargs)

    def submit_asyncio_task(
        self, coroutine_func: Callable, *args, **kwargs
    ) -> str:
        """提交异步协程任务."""
        return self.task_manager.submit_asyncio_task(
            coroutine_func, *args, **kwargs
        )

    def get_task_result(self, task_id: str, timeout: float = 10.0) -> Any:
        """获取异步任务结果."""
        return self.task_manager.get_task_result(task_id, timeout)

    @staticmethod
    def memoize(func: Callable) -> Callable:
        """记忆化装饰器."""
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 创建缓存键
            key = str(args) + str(sorted(kwargs.items()))

            if key not in cache:
                cache[key] = func(*args, **kwargs)

            return cache[key]

        return wrapper

    def optimize_data_processing(
        self, data_processor: Callable, data: Any
    ) -> Any:
        """优化数据处理."""
        def process_with_cache():
            # 这里可以实现数据处理的缓存逻辑
            return data_processor(data)

        task_id = self.submit_async_task(
            f"data_process_{time.time()}", process_with_cache
        )
        return self.get_task_result(task_id)

    def batch_process(
        self, items: List[Any], processor: Callable,
        batch_size: int = 10
    ) -> List[Any]:
        """批量处理数据."""
        results = []

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]

            def process_batch(batch=batch):
                return [processor(item) for item in batch]

            task_id = self.submit_async_task(f"batch_{i}", process_batch)
            result = self.get_task_result(task_id)

            if result.get("success"):
                results.extend(result.get("result", []))
            else:
                self.logger.error("批处理失败: %s", result.get('error'))

        return results

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计."""
        return {
            "cache_stats": self.data_cache.get_stats(),
            "task_manager_stats": self.task_manager.get_task_stats(),
            "optimization_enabled": self._optimization_enabled
        }

    def enable_optimization(self):
        """启用优化."""
        self._optimization_enabled = True
        self.logger.info("性能优化已启用")

    def disable_optimization(self):
        """禁用优化."""
        self._optimization_enabled = False
        self.logger.info("性能优化已禁用")


class AsyncDataProcessor:
    """异步数据处理器."""

    def __init__(self, optimizer: "PerformanceOptimizer"):
        """初始化异步数据处理器."""
        self.optimizer = optimizer
        self.logger = logging.getLogger(__name__)

    async def process_market_data_async(
        self, data_list: List["UnifiedMarketData"]
    ) -> Dict[str, Any]:
        """异步处理行情数据."""
        results = {}

        # 分批处理
        batch_size = 100
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]

            # 模拟异步处理
            await asyncio.sleep(0.01)

            # 处理批次数据
            for data in batch:
                symbol = data.symbol
                if symbol not in results:
                    results[symbol] = []

                results[symbol].append({
                    "datetime": data.datetime,
                    "price": data.close_price,
                    "volume": data.volume
                })

        return results

    def process_data_sync(
        self, data_list: List["UnifiedMarketData"]
    ) -> Dict[str, Any]:
        """同步处理数据（包装为异步）."""
        try:
            # 使用线程池执行
            future = self.optimizer.task_manager.executor.submit(
                self._sync_process_data, data_list
            )
            return future.result(timeout=30)
        except (TimeoutError, RuntimeError, AttributeError) as e:
            self.logger.error("同步数据处理失败: %s", e)
            return {}

    def _sync_process_data(
        self, data_list: List["UnifiedMarketData"]
    ) -> Dict[str, Any]:
        """实际的数据处理逻辑."""
        results = {}

        for data in data_list:
            symbol = data.symbol
            if symbol not in results:
                results[symbol] = []

            results[symbol].append({
                "datetime": data.datetime,
                "price": data.close_price,
                "volume": data.volume
            })

        return results


# 全局性能优化器管理类
class _PerformanceOptimizerRegistry:
    """性能优化器注册表."""

    def __init__(self):
        """初始化性能优化器注册表."""
        self._optimizer: Optional["PerformanceOptimizer"] = None

    def get_performance_optimizer(
        self, terminal_engine: "TerminalEngine"
    ) -> "PerformanceOptimizer":
        """获取性能优化器实例."""
        if self._optimizer is None:
            self._optimizer = PerformanceOptimizer(terminal_engine)
        return self._optimizer

    def reset_optimizer(self):
        """重置性能优化器（用于测试）."""
        if self._optimizer:
            self._optimizer.stop_optimization()
            self._optimizer = None

    def get_optimizer_instance(
        self, terminal_engine: "TerminalEngine"
    ) -> "PerformanceOptimizer":
        """获取性能优化器实例（别名方法）."""
        return self.get_performance_optimizer(terminal_engine)


# 全局注册表实例
_performance_registry: _PerformanceOptimizerRegistry = (
    _PerformanceOptimizerRegistry()
)


def get_performance_optimizer(
    terminal_engine: "TerminalEngine"
) -> "PerformanceOptimizer":
    """获取全局性能优化器实例."""
    return _performance_registry.get_optimizer_instance(terminal_engine)


def reset_performance_optimizer():
    """重置性能优化器（用于测试）."""
    _performance_registry.reset_optimizer()


# 导出公共接口
__all__ = [
    'Cache', 'DataCache', 'AsyncTaskManager',
    'PerformanceOptimizer', 'AsyncDataProcessor',
    'get_performance_optimizer', 'reset_performance_optimizer'
]
