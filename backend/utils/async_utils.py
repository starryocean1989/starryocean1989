# -*- coding: utf-8 -*-
"""
异步工具函数.

提供异步操作、并发控制和任务管理功能。
"""

import logging
import asyncio
import time
from contextlib import suppress
from typing import Any, Callable, Coroutine, Dict, List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

logger = logging.getLogger(__name__)


class AsyncTaskManager:
    """异步任务管理器."""

    def __init__(self, max_concurrent_tasks: int = 100):
        """初始化异步任务管理器."""
        self.max_concurrent_tasks = max_concurrent_tasks
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._task_stats: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def run_task(
        self,
        task_id: str,
        coro: Coroutine,
        timeout: Optional[float] = None,
        auto_cleanup: bool = True,
    ) -> Any:
        """运行异步任务."""
        async with self._semaphore:
            async with self._lock:
                if task_id in self._running_tasks:
                    raise ValueError(f"任务已存在: {task_id}")

                # 创建任务
                task = asyncio.create_task(coro)
                self._running_tasks[task_id] = task
                self._task_stats[task_id] = {
                    "started_at": datetime.now(),
                    "status": "running",
                }

            try:
                # 执行任务
                if timeout:
                    result = await asyncio.wait_for(task, timeout=timeout)
                else:
                    result = await task

                async with self._lock:
                    self._task_stats[task_id]["status"] = "completed"
                    self._task_stats[task_id]["completed_at"] = datetime.now()
                    if auto_cleanup:
                        self._cleanup_task(task_id)

                return result

            except asyncio.TimeoutError:
                async with self._lock:
                    self._task_stats[task_id]["status"] = "timeout"
                    self._task_stats[task_id]["completed_at"] = datetime.now()
                    if auto_cleanup:
                        self._cleanup_task(task_id)
                raise

            except Exception as e:
                async with self._lock:
                    self._task_stats[task_id]["status"] = "error"
                    self._task_stats[task_id]["error"] = str(e)
                    self._task_stats[task_id]["completed_at"] = datetime.now()
                    if auto_cleanup:
                        self._cleanup_task(task_id)
                raise

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务."""
        async with self._lock:
            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]
                task.cancel()
                self._task_stats[task_id]["status"] = "cancelled"
                self._task_stats[task_id]["completed_at"] = datetime.now()
                self._cleanup_task(task_id)
                return True
            return False

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态."""
        async with self._lock:
            return self._task_stats.get(task_id)

    async def list_tasks(self) -> Dict[str, Dict[str, Any]]:
        """列出所有任务."""
        async with self._lock:
            return self._task_stats.copy()

    async def cleanup_completed_tasks(self, max_age_hours: int = 24) -> int:
        """清理已完成的任务."""
        async with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            tasks_to_remove = []

            for task_id, stats in self._task_stats.items():
                if (
                    stats.get("completed_at")
                    and stats["completed_at"] < cutoff_time
                    and task_id not in self._running_tasks
                ):
                    tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                self._cleanup_task(task_id)

            return len(tasks_to_remove)

    def _cleanup_task(self, task_id: str) -> None:
        """清理任务."""
        self._running_tasks.pop(task_id, None)
        self._task_stats.pop(task_id, None)

    async def shutdown(self) -> None:
        """关闭任务管理器."""
        async with self._lock:
            # 取消所有运行中的任务
            for task in self._running_tasks.values():
                task.cancel()

            # 等待所有任务完成或取消
            if self._running_tasks:
                await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

            self._running_tasks.clear()
            self._task_stats.clear()


class AsyncRateLimiter:
    """异步限流器."""

    def __init__(self, rate: int, per: float):
        """初始化限流器.

        Args:
            rate: 允许的请求数
            per: 时间窗口（秒）
        """
        self.rate = rate
        self.per = per
        self._tokens = rate
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """获取令牌."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_update

            # 添加新令牌
            self._tokens = min(self.rate, self._tokens + elapsed * (self.rate / self.per))
            self._last_update = now

            # 检查是否有足够的令牌
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def wait_for_token(self, tokens: int = 1) -> None:
        """等待令牌可用."""
        while not await self.acquire(tokens):
            await asyncio.sleep(0.1)


class AsyncRetry:
    """异步重试装饰器."""

    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff_factor: float = 2.0,
        exceptions: tuple = (Exception,),
    ):
        """初始化重试配置."""
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions

    def __call__(self, func: Callable) -> Callable:
        """装饰函数."""

        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = self.delay

            for attempt in range(self.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except self.exceptions as e:
                    last_exception = e

                    if attempt == self.max_attempts - 1:
                        # 最后一次尝试失败，抛出异常
                        logger.error("重试失败，已达到最大尝试次数: %s", func.__name__)
                        raise

                    logger.warning("重试第 %d 次: %s - %s", attempt + 1, func.__name__, str(e))

                    await asyncio.sleep(current_delay)
                    current_delay *= self.backoff_factor

            # 不应该到达这里，但为了类型安全
            if last_exception:
                raise last_exception

        return wrapper


class AsyncPool:
    """异步池."""

    def __init__(self, max_workers: int = 4, pool_type: str = "thread"):
        """初始化异步池."""
        self.max_workers = max_workers
        self.pool_type = pool_type

        if pool_type == "thread":
            self._executor = ThreadPoolExecutor(max_workers=max_workers)
        elif pool_type == "process":
            self._executor = ProcessPoolExecutor(max_workers=max_workers)
        else:
            raise ValueError("pool_type 必须是 'thread' 或 'process'")

    async def run(self, func: Callable, *args, **kwargs) -> Any:
        """在线程池中运行函数."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args, **kwargs)

    async def run_batch(
        self,
        func: Callable,
        args_list: List[tuple],
        kwargs_list: Optional[List[dict]] = None,
    ) -> List[Any]:
        """批量运行函数."""
        if kwargs_list is None:
            kwargs_list = [{}] * len(args_list)

        if len(args_list) != len(kwargs_list):
            raise ValueError("args_list 和 kwargs_list 长度必须相同")

        tasks = []
        for args, kwargs in zip(args_list, kwargs_list):
            task = self.run(func, *args, **kwargs)
            tasks.append(task)

        return await asyncio.gather(*tasks, return_exceptions=True)

    def shutdown(self, wait: bool = True) -> None:
        """关闭池."""
        self._executor.shutdown(wait=wait)


class AsyncBatchProcessor:
    """异步批量处理器."""

    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        processor_func: Optional[Callable] = None,
    ):
        """初始化批量处理器."""
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.processor_func = processor_func
        self._batch: List[Any] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """启动批量处理器."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """停止批量处理器."""
        if not self._running:
            return

        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._flush_task

        # 处理剩余的批次
        await self.flush()

    async def add_item(self, item: Any) -> None:
        """添加项目到批次."""
        async with self._lock:
            self._batch.append(item)

            if len(self._batch) >= self.batch_size:
                await self._process_batch()

    async def flush(self) -> None:
        """立即处理当前批次."""
        async with self._lock:
            if self._batch:
                await self._process_batch()

    async def _flush_loop(self) -> None:
        """定期刷新循环."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("批量处理刷新循环错误: %s", e)

    async def _process_batch(self) -> None:
        """处理批次."""
        if not self._batch:
            return

        batch_to_process = self._batch.copy()
        self._batch.clear()

        try:
            if self.processor_func:
                if asyncio.iscoroutinefunction(self.processor_func):
                    await self.processor_func(batch_to_process)
                else:
                    # 在线程池中运行同步函数
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.processor_func, batch_to_process)
        except Exception as e:
            logger.error("批量处理错误: %s", e)


class AsyncTimeout:
    """异步超时装饰器."""

    def __init__(self, timeout: float):
        """初始化超时装饰器."""
        self.timeout = timeout

    def __call__(self, func: Callable) -> Callable:
        """装饰函数."""

        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
            except asyncio.TimeoutError:
                logger.error("函数执行超时: %s (timeout=%s)", func.__name__, self.timeout)
                raise

        return wrapper


# 导出公共接口
__all__ = [
    "AsyncTaskManager",
    "AsyncRateLimiter",
    "AsyncRetry",
    "AsyncPool",
    "AsyncBatchProcessor",
    "AsyncTimeout",
]
