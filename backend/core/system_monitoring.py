# -*- coding: utf-8 -*-
"""
统一系统监控和性能优化模块 - 合并版本.

整合了以下模块的功能：
- monitoring.py: 性能监控、测试运行、健康检查
- performance.py: 缓存机制、异步处理、性能优化
- utils.py: 性能相关工具（PerformanceMetrics, PerformanceTracker）

提供完整的系统监控、性能优化和健康检查功能。
"""

import asyncio
import functools
import gc
import io
import logging
import platform
import sys
import threading
import time
import unittest
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

# 第三方库导入
import psutil

# 本地模块导入
from .models import get_data_model_manager
from .base import VNPY_AVAILABLE

if TYPE_CHECKING:
    from .models import UnifiedMarketData


# =============================================================================
# Part 1: 缓存系统
# =============================================================================


class Cache:
    """通用缓存类（LRU + TTL）."""

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
                key
                for key, timestamp in self._timestamps.items()
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
        self.order_cache = Cache(max_size=1000, ttl=600)  # 10分钟过期
        self.position_cache = Cache(max_size=1000, ttl=300)  # 5分钟过期
        self.logger = logging.getLogger(__name__)

        # 启动定期清理线程
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_thread.start()

    def _cleanup_loop(self):
        """定期清理过期缓存."""
        while True:
            try:
                time.sleep(60)  # 每分钟清理一次
                self.market_data_cache.cleanup_expired()
                self.order_cache.cleanup_expired()
                self.position_cache.cleanup_expired()
            except Exception as e:
                self.logger.error("缓存清理失败: %s", e)

    def cache_market_data(self, symbol: str, data: List["UnifiedMarketData"]):
        """缓存行情数据."""
        key = f"market_{symbol}"
        self.market_data_cache.put(key, data)

    def get_market_data(self, symbol: str) -> Optional[List["UnifiedMarketData"]]:
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
                "max_size": self.market_data_cache.max_size,
            },
            "order_cache": {
                "size": self.order_cache.size(),
                "max_size": self.order_cache.max_size,
            },
            "position_cache": {
                "size": self.position_cache.size(),
                "max_size": self.position_cache.max_size,
            },
        }


# =============================================================================
# Part 2: 异步任务管理
# =============================================================================


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

            def run_loop():
                try:
                    if self.loop is not None:
                        self.loop.run_forever()
                except Exception as e:
                    self.logger.error("事件循环异常: %s", e)

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()
            self.logger.info("异步任务管理器启动完成")

        except Exception as e:
            self.logger.error("启动事件循环失败: %s", e)

    def stop_event_loop(self):
        """停止事件循环."""
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.executor.shutdown(wait=True)
                self.logger.info("异步任务管理器停止完成")
            except Exception as e:
                self.logger.error("停止事件循环失败: %s", e)

    def get_task_stats(self) -> Dict[str, int]:
        """获取任务统计信息."""
        return {
            "active_tasks": len(self._tasks),
            "completed_tasks": len(self._results),
            "max_workers": self.max_workers,
        }

    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        """提交异步任务."""

        def task_wrapper():
            try:
                result = func(*args, **kwargs)
                self._results[task_id] = {"success": True, "result": result}
            except Exception as e:
                self.logger.error("任务执行失败 %s: %s", task_id, e)
                self._results[task_id] = {"success": False, "error": str(e)}

        future = self.executor.submit(task_wrapper)
        self._tasks[task_id] = future
        return task_id

    def submit_asyncio_task(self, coroutine_func: Callable, *args, **kwargs) -> str:
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
            except Exception as e:
                self.logger.error("异步任务执行失败 %s: %s", task_id, e)
                self._results[task_id] = {"success": False, "error": str(e)}

        if self.loop is None:
            raise RuntimeError("事件循环未初始化")
        future = asyncio.run_coroutine_threadsafe(wrapper(), self.loop)
        self._tasks[task_id] = future
        return task_id

    def get_task_result(self, task_id: str, timeout: float = 10.0) -> Any:
        """获取任务结果."""
        if task_id not in self._tasks:
            return {"success": False, "error": "任务不存在"}

        future = self._tasks[task_id]

        try:
            if hasattr(future, "result"):
                result = future.result(timeout=timeout)
            else:
                result = future.get(timeout=timeout) if hasattr(future, "get") else None

            if task_id in self._results:
                task_result = self._results.pop(task_id)
                return task_result

            return {"success": True, "result": result}

        except TimeoutError as e:
            return {"success": False, "error": str(e)}
        finally:
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


# =============================================================================
# Part 3: 性能优化器
# =============================================================================


class PerformanceOptimizer:
    """性能优化器."""

    def __init__(self, terminal_engine: Any):
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

    def submit_async_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        """提交异步任务."""
        return self.task_manager.submit_task(task_id, func, *args, **kwargs)

    def submit_asyncio_task(self, coroutine_func: Callable, *args, **kwargs) -> str:
        """提交异步协程任务."""
        return self.task_manager.submit_asyncio_task(coroutine_func, *args, **kwargs)

    def get_task_result(self, task_id: str, timeout: float = 10.0) -> Any:
        """获取异步任务结果."""
        return self.task_manager.get_task_result(task_id, timeout)

    @staticmethod
    def memoize(func: Callable) -> Callable:
        """记忆化装饰器."""
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]

        return wrapper

    def optimize_data_processing(self, data_processor: Callable, data: Any) -> Any:
        """优化数据处理."""

        def process_with_cache():
            return data_processor(data)

        task_id = self.submit_async_task(f"data_process_{time.time()}", process_with_cache)
        return self.get_task_result(task_id)

    def batch_process(
        self, items: List[Any], processor: Callable, batch_size: int = 10
    ) -> List[Any]:
        """批量处理数据."""
        results = []

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            def process_batch(batch=batch):
                return [processor(item) for item in batch]

            task_id = self.submit_async_task(f"batch_{i}", process_batch)
            result = self.get_task_result(task_id)

            if result.get("success"):
                results.extend(result.get("result", []))
            else:
                self.logger.error("批处理失败: %s", result.get("error"))

        return results

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计."""
        return {
            "cache_stats": self.data_cache.get_stats(),
            "task_manager_stats": self.task_manager.get_task_stats(),
            "optimization_enabled": self._optimization_enabled,
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

        batch_size = 100
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i : i + batch_size]
            await asyncio.sleep(0.01)

            for data in batch:
                symbol = data.symbol
                if symbol not in results:
                    results[symbol] = []

                results[symbol].append(
                    {
                        "datetime": data.datetime,
                        "price": data.close_price,
                        "volume": data.volume,
                    }
                )

        return results

    def process_data_sync(self, data_list: List["UnifiedMarketData"]) -> Dict[str, Any]:
        """同步处理数据（包装为异步）."""
        try:
            future = self.optimizer.task_manager.executor.submit(self._sync_process_data, data_list)
            return future.result(timeout=30)
        except Exception as e:
            self.logger.error("同步数据处理失败: %s", e)
            return {}

    def _sync_process_data(self, data_list: List["UnifiedMarketData"]) -> Dict[str, Any]:
        """实际的数据处理逻辑."""
        results = {}

        for data in data_list:
            symbol = data.symbol
            if symbol not in results:
                results[symbol] = []

            results[symbol].append(
                {
                    "datetime": data.datetime,
                    "price": data.close_price,
                    "volume": data.volume,
                }
            )

        return results


# =============================================================================
# Part 4: 性能监控
# =============================================================================


class PerformanceMonitor:
    """性能监控器."""

    def __init__(self, config_service=None):
        """初始化性能监控器."""
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)

        # 监控数据
        self._metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._alerts: List[Dict[str, Any]] = []
        self._thresholds: Dict[str, float] = {}

        # 监控状态
        self._state = {
            "monitoring": False,
            "monitor_thread": None,
            "stop_event": threading.Event(),
        }

        # 初始化阈值
        self._init_thresholds()

    def _init_thresholds(self):
        """初始化监控阈值."""
        config = self.config_service.get("system", {}) if self.config_service else {}

        self._thresholds = {
            "cpu_percent": config.get("cpu_warning_threshold", 80.0),
            "memory_percent": config.get("memory_warning_threshold", 80.0),
            "response_time": config.get("response_time_threshold", 5.0),
            "error_rate": config.get("error_rate_threshold", 10.0),
            "memory_leak_threshold": config.get("memory_leak_threshold", 100.0),
        }

    def start_monitoring(self, interval: float = 5.0):
        """启动性能监控."""
        if self._state["monitoring"]:
            return

        self._state["monitoring"] = True
        self._state["stop_event"].clear()

        self._state["monitor_thread"] = threading.Thread(
            target=lambda: self._monitoring_loop(interval), daemon=True
        )
        self._state["monitor_thread"].start()
        self.logger.info("性能监控已启动，间隔: %s秒", interval)

    def stop_monitoring(self):
        """停止性能监控."""
        if not self._state["monitoring"]:
            return

        self._state["monitoring"] = False
        self._state["stop_event"].set()

        if self._state["monitor_thread"]:
            self._state["monitor_thread"].join(timeout=5)

        self.logger.info("性能监控已停止")

    def _monitoring_loop(self, interval: float):
        """监控循环."""
        while not self._state["stop_event"].is_set():
            try:
                self._collect_metrics()
                self._check_thresholds()
                self._cleanup_old_metrics()
                self._state["stop_event"].wait(interval)
            except Exception as e:
                self.logger.error("监控循环异常: %s", e)
                time.sleep(interval)

    def _collect_metrics(self):
        """收集性能指标."""
        timestamp = datetime.now()

        try:
            # 系统性能指标
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            system_metrics = {
                "timestamp": timestamp,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_mb": memory.used / (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024 * 1024 * 1024),
            }

            self._metrics["system"].append(system_metrics)

            # 应用性能指标
            app_metrics = {
                "timestamp": timestamp,
                "python_objects": len(gc.get_objects()),
                "thread_count": threading.active_count(),
                "response_time": self._measure_response_time(),
                "error_count": self._get_error_count(),
            }

            self._metrics["application"].append(app_metrics)

            # 核心模块指标
            core_metrics = self._collect_core_metrics()
            if core_metrics:
                self._metrics["core"].append(core_metrics)

        except Exception as e:
            self.logger.error("收集性能指标失败: %s", e)

    def _measure_response_time(self) -> float:
        """测量响应时间."""
        start_time = time.time()
        for _ in range(1000):
            pass
        return (time.time() - start_time) * 1000

    def _get_error_count(self) -> int:
        """获取错误计数."""
        return 0

    def _collect_core_metrics(self) -> Optional[Dict[str, Any]]:
        """收集核心模块指标."""
        try:
            metrics = {}

            data_manager = get_data_model_manager()
            if data_manager:
                stats = data_manager.get_statistics()
                metrics["data_model"] = stats

            try:
                from .base import get_main_engine

                main_engine = get_main_engine()
                optimizer = get_performance_optimizer(main_engine)
                if optimizer:
                    perf_stats = optimizer.get_performance_stats()
                    metrics["performance"] = perf_stats
            except Exception:
                pass

            return metrics if metrics else None

        except Exception as e:
            self.logger.error("收集核心模块指标失败: %s", e)
            return None

    def _check_thresholds(self):
        """检查阈值告警."""
        try:
            if not self._metrics["system"]:
                return

            latest = self._metrics["system"][-1]

            if latest["cpu_percent"] > self._thresholds["cpu_percent"]:
                self._add_alert(
                    "cpu_warning",
                    "高CPU使用率",
                    f"CPU使用率 {latest['cpu_percent']:.1f}% 超过阈值 {self._thresholds['cpu_percent']}%",
                )

            if latest["memory_percent"] > self._thresholds["memory_percent"]:
                self._add_alert(
                    "memory_warning",
                    "高内存使用率",
                    f"内存使用率 {latest['memory_percent']:.1f}% 超过阈值 {self._thresholds['memory_percent']}%",
                )

        except Exception as e:
            self.logger.error("检查阈值失败: %s", e)

    def _add_alert(self, alert_type: str, title: str, message: str):
        """添加告警."""
        alert = {
            "timestamp": datetime.now(),
            "type": alert_type,
            "title": title,
            "message": message,
            "resolved": False,
        }

        self._alerts.append(alert)

        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-500:]

        self.logger.warning("监控告警: %s - %s", title, message)

    def _cleanup_old_metrics(self):
        """清理旧的监控数据."""
        cutoff_time = datetime.now() - timedelta(hours=24)

        for category in self._metrics:
            if category in self._metrics:
                self._metrics[category] = [
                    m
                    for m in self._metrics[category]
                    if isinstance(m, dict) and m.get("timestamp") and m["timestamp"] >= cutoff_time
                ]

    def get_metrics(self, category: Optional[str] = None, hours: int = 1) -> Dict[str, Any]:
        """获取监控指标."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        if category:
            metrics = [
                m
                for m in self._metrics.get(category, [])
                if isinstance(m, dict) and m.get("timestamp") and m["timestamp"] >= cutoff_time
            ]
            return {category: metrics}

        result = {}
        for cat, data in self._metrics.items():
            result[cat] = [
                m
                for m in data
                if isinstance(m, dict) and m.get("timestamp") and m["timestamp"] >= cutoff_time
            ]

        return result

    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表."""
        return self._alerts[-limit:] if self._alerts else []

    def clear_alerts(self):
        """清空告警."""
        self._alerts.clear()
        self.logger.info("监控告警已清空")

    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要."""
        summary = {
            "monitoring_active": self._state["monitoring"],
            "total_alerts": len(self._alerts),
            "metrics_count": {category: len(metrics) for category, metrics in self._metrics.items()},
            "thresholds": self._thresholds.copy(),
        }

        if self._metrics["system"]:
            latest_metrics = [
                m for m in self._metrics["system"] if isinstance(m, dict) and m.get("timestamp")
            ]
            if latest_metrics:
                latest = latest_metrics[-1]
                summary["latest_system_metrics"] = {
                    "cpu_percent": latest.get("cpu_percent", 0),
                    "memory_percent": latest.get("memory_percent", 0),
                    "timestamp": latest.get("timestamp"),
                }

        return summary

    def get_all_metrics(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有指标数据（向后兼容）.
        
        Returns:
            所有类别的指标数据
        """
        return dict(self._metrics)
    
    def reset_category(self, category: str):
        """重置指定类别的指标（向后兼容）.
        
        Args:
            category: 类别名称
        """
        if category in self._metrics:
            self._metrics[category].clear()
            self.logger.info(f"已重置类别指标: {category}")
    
    def reset(self):
        """重置所有指标（向后兼容）."""
        self._metrics.clear()
        self._alerts.clear()
        self.logger.info("已重置所有监控指标")

    @property
    def is_monitoring(self) -> bool:
        """是否正在监控."""
        return self._state["monitoring"]

    @property
    def metrics_count(self) -> int:
        """指标数量."""
        return sum(len(metrics) for metrics in self._metrics.values())

    @property
    def alerts_count(self) -> int:
        """告警数量."""
        return len(self._alerts)


# =============================================================================
# Part 5: 测试运行器
# =============================================================================


class TestStream:
    """测试输出流."""

    def __init__(self):
        """初始化测试输出流."""
        self.content = []

    def write(self, text):
        """写入文本到输出流."""
        self.content.append(text)

    def flush(self):
        """刷新输出流."""
        pass

    def getvalue(self):
        """获取输出流的内容."""
        return "".join(self.content)


class TestRunner:
    """测试运行器."""

    def __init__(self, config_service: Optional[Any] = None):
        """初始化测试运行器."""
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)
        self._test_results: Dict[str, Any] = {}

    def run_unit_tests(self, test_module: Optional[str] = None) -> Dict[str, Any]:
        """运行单元测试."""
        start_time = time.time()

        if test_module:
            try:
                module = __import__(test_module, fromlist=[""])
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromModule(module)
            except Exception as e:
                self.logger.error("加载测试模块失败 %s: %s", test_module, e)
                return {"success": False, "error": str(e)}
        else:
            suite = unittest.TestSuite()

        runner = unittest.TextTestRunner(verbosity=2, stream=TestStream())
        result = runner.run(suite)

        end_time = time.time()

        test_result = {
            "timestamp": datetime.now(),
            "duration": end_time - start_time,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "success": len(result.failures) == 0 and len(result.errors) == 0,
            "details": {
                "failures": [{"test": str(test), "error": error} for test, error in result.failures],
                "errors": [{"test": str(test), "error": error} for test, error in result.errors],
            },
        }

        self._test_results[datetime.now().isoformat()] = test_result
        self.logger.info(
            "单元测试完成: %s 个测试, %s 个失败, %s 个错误",
            test_result["tests_run"],
            test_result["failures"],
            test_result["errors"],
        )

        return test_result

    def get_test_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取测试结果."""
        results = list(self._test_results.values())
        results.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
        return results[:limit]

    @property
    def last_test_timestamp(self) -> Optional[datetime]:
        """最后测试时间戳."""
        if not self._test_results:
            return None
        last_key = max(self._test_results.keys())
        return self._test_results[last_key].get("timestamp")


# =============================================================================
# Part 6: 健康检查器
# =============================================================================


class HealthChecker:
    """健康检查器."""

    def __init__(self, main_engine: Optional[Any] = None):
        """初始化健康检查器."""
        self.main_engine = main_engine
        self.logger = logging.getLogger(__name__)
        self._check_results: Dict[str, Any] = {}

    def check_system_health(self) -> Dict[str, Any]:
        """检查系统健康状态."""
        checks = {
            "python": self._check_python_environment(),
            "memory": self._check_memory_usage(),
            "disk": self._check_disk_space(),
            "core_modules": self._check_core_modules(),
            "vnpy": (
                self._check_vnpy_connection()
                if VNPY_AVAILABLE
                else {"status": "unavailable", "message": "VNPY不可用"}
            ),
        }

        health_score = self._calculate_health_score(checks)

        result = {
            "timestamp": datetime.now(),
            "health_score": health_score,
            "status": (
                "healthy" if health_score >= 80 else "warning" if health_score >= 60 else "critical"
            ),
            "checks": checks,
        }

        self._check_results[datetime.now().isoformat()] = result
        return result

    def _check_python_environment(self) -> Dict[str, Any]:
        """检查Python环境."""
        try:
            return {
                "status": "ok",
                "version": sys.version,
                "platform": platform.platform(),
                "python_bits": "64-bit" if sys.maxsize > 2**32 else "32-bit",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_memory_usage(self) -> Dict[str, Any]:
        """检查内存使用."""
        try:
            memory = psutil.virtual_memory()
            threshold = 80

            status = "ok" if memory.percent < threshold else "warning"

            return {
                "status": status,
                "percent": memory.percent,
                "used_mb": memory.used / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_disk_space(self) -> Dict[str, Any]:
        """检查磁盘空间."""
        try:
            disk = psutil.disk_usage("/")
            threshold = 90

            status = "ok" if disk.percent < threshold else "warning"

            return {
                "status": status,
                "percent": disk.percent,
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_core_modules(self) -> Dict[str, Any]:
        """检查核心模块."""
        checks = {}

        try:
            data_manager = get_data_model_manager()
            if data_manager:
                stats = data_manager.get_statistics()
                checks["data_manager"] = {"status": "ok", "stats": stats}
            else:
                checks["data_manager"] = {"status": "error", "error": "无法获取数据管理器"}
        except Exception as e:
            checks["data_manager"] = {"status": "error", "error": str(e)}

        try:
            if self.main_engine:
                optimizer = get_performance_optimizer(self.main_engine)
            else:
                optimizer = None
            if optimizer:
                stats = optimizer.get_performance_stats()
                checks["performance_optimizer"] = {"status": "ok", "stats": stats}
            else:
                checks["performance_optimizer"] = {"status": "error", "error": "无法获取性能优化器"}
        except Exception as e:
            checks["performance_optimizer"] = {"status": "error", "error": str(e)}

        return checks

    def _check_vnpy_connection(self) -> Dict[str, Any]:
        """检查VNPY连接."""
        try:
            if not self.main_engine:
                return {"status": "error", "error": "MainEngine未初始化"}

            return {
                "status": "ok",
                "vnpy_available": VNPY_AVAILABLE,
                "main_engine_initialized": self.main_engine is not None,
                "engines": len(getattr(self.main_engine, "engines", {})),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _calculate_health_score(self, checks: Dict[str, Any]) -> float:
        """计算健康评分."""
        scores = []

        for check_name in ["python", "memory", "disk"]:
            if checks.get(check_name, {}).get("status") == "ok":
                scores.append(100)
            elif checks.get(check_name, {}).get("status") == "warning":
                scores.append(60)
            else:
                scores.append(0)

        core_modules = checks.get("core_modules", {})
        if core_modules.get("data_manager", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        if core_modules.get("performance_optimizer", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        if checks.get("vnpy", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        return (sum(scores) / len(scores)) if scores else 0

    def get_check_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取检查历史."""
        results = list(self._check_results.values())
        results.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
        return results[:limit]

    @property
    def last_check_timestamp(self) -> Optional[datetime]:
        """最后检查时间戳."""
        if not self._check_results:
            return None
        last_key = max(self._check_results.keys())
        return self._check_results[last_key].get("timestamp")


# =============================================================================
# Part 7: 监控管理器
# =============================================================================


class MonitoringManager:
    """监控管理器."""

    def __init__(self, config_service=None, terminal_engine=None):
        """初始化监控管理器."""
        self.config_service = config_service
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)

        # 初始化组件
        self.performance_monitor = PerformanceMonitor(config_service)
        self.test_runner = TestRunner(config_service)
        self.health_checker = HealthChecker(terminal_engine)

        # 启动监控
        self.start_all_monitoring()

    def start_all_monitoring(self):
        """启动所有监控."""
        self.performance_monitor.start_monitoring()
        self.logger.info("监控管理器启动完成")

    def stop_all_monitoring(self):
        """停止所有监控."""
        self.performance_monitor.stop_monitoring()
        self.logger.info("监控管理器停止完成")

    def run_comprehensive_test(self) -> Dict[str, Any]:
        """运行综合测试."""
        self.logger.info("开始运行综合测试")

        # 健康检查
        health_result = self.health_checker.check_system_health()

        # 性能指标
        performance_metrics = self.performance_monitor.get_metrics(hours=1)

        # 综合报告
        report = {
            "timestamp": datetime.now(),
            "health": health_result,
            "performance": performance_metrics,
            "summary": {
                "health_score": health_result.get("health_score", 0),
                "performance_ok": len(performance_metrics.get("system", [])) > 0,
            },
        }

        self.logger.info("综合测试完成 - 健康评分: %s", report["summary"]["health_score"])
        return report

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态."""
        return {
            "performance_monitor": {
                "active": self.performance_monitor.is_monitoring,
                "metrics_count": self.performance_monitor.metrics_count,
                "alerts_count": self.performance_monitor.alerts_count,
            },
            "health_checker": {"last_check": self.health_checker.last_check_timestamp},
            "test_runner": {"last_test": self.test_runner.last_test_timestamp},
        }


# =============================================================================
# Part 8: 全局注册表和工厂函数
# =============================================================================


class _PerformanceOptimizerRegistry:
    """性能优化器注册表."""

    def __init__(self):
        """初始化性能优化器注册表."""
        self._optimizer: Optional["PerformanceOptimizer"] = None

    def get_performance_optimizer(self, terminal_engine: Any) -> "PerformanceOptimizer":
        """获取性能优化器实例."""
        if self._optimizer is None:
            self._optimizer = PerformanceOptimizer(terminal_engine)
        return self._optimizer

    def reset_optimizer(self):
        """重置性能优化器（用于测试）."""
        if self._optimizer:
            self._optimizer.stop_optimization()
            self._optimizer = None


# 全局注册表实例
_performance_registry: _PerformanceOptimizerRegistry = _PerformanceOptimizerRegistry()


def get_performance_optimizer(terminal_engine: Any) -> "PerformanceOptimizer":
    """获取全局性能优化器实例."""
    return _performance_registry.get_performance_optimizer(terminal_engine)


def reset_performance_optimizer():
    """重置性能优化器（用于测试）."""
    _performance_registry.reset_optimizer()


# =============================================================================
# Part 9: 全局实例（向后兼容）
# =============================================================================

# 创建全局性能监控器实例（向后兼容）
performance_tracker = PerformanceMonitor()


# 导出公共接口
__all__ = [
    "Cache",
    "DataCache",
    "AsyncTaskManager",
    "PerformanceOptimizer",
    "AsyncDataProcessor",
    "PerformanceMonitor",
    "TestRunner",
    "TestStream",
    "HealthChecker",
    "MonitoringManager",
    "get_performance_optimizer",
    "reset_performance_optimizer",
    "performance_tracker",  # 全局实例
]

