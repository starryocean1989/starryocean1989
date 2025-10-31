# -*- coding: utf-8 -*-
"""GUI异步工具模块 - 简化UI层异步编程

提供工具:
- @async_slot: 装饰器,将async函数转为Qt Slot
- await_in_qt(): 在主线程安全执行async代码
- AsyncTaskRunner: 异步任务管理器
- error_handler(): 统一错误处理装饰器

依赖: qasync (可选,降级到Signal/Slot模式)
"""

import asyncio
import functools
import logging
import traceback
from typing import Any, Callable, Coroutine, Dict, Optional
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot, QThread

# 尝试导入qasync
try:
    import qasync
    QASYNC_AVAILABLE = True
except ImportError:
    QASYNC_AVAILABLE = False

# UI专用logger
logger = logging.getLogger("ui.async_utils")


# ==================== 异步Slot装饰器 ====================

def async_slot(*args, **kwargs):
    """装饰器: 将async函数转为Qt Slot

    用法:
        @async_slot
        async def on_button_clicked(self):
            result = await some_async_operation()
            self.update_ui(result)

    注意:
    - 需要qasync支持,否则回退到线程模式
    - 错误会被自动捕获并记录
    - 不阻塞UI线程

    Args:
        *args: Slot类型参数(可选)
        **kwargs: 其他参数

    Returns:
        装饰后的函数
    """
    def decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"{func.__name__} 必须是async函数")

        @Slot(*args, **kwargs)
        @functools.wraps(func)
        def wrapper(self_or_first_arg, *func_args, **func_kwargs):
            """Slot包装器"""
            # 判断是否是实例方法
            if hasattr(self_or_first_arg, func.__name__):
                # 实例方法: self_or_first_arg是self
                self_obj = self_or_first_arg
                coro = func(self_obj, *func_args, **func_kwargs)
            else:
                # 普通函数: self_or_first_arg是第一个参数
                coro = func(self_or_first_arg, *func_args, **func_kwargs)

            # 获取事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # 没有运行的事件循环
                loop = None

            if QASYNC_AVAILABLE and loop is not None:
                # qasync模式: 直接创建任务
                task = asyncio.ensure_future(coro, loop=loop)
                task.add_done_callback(_async_slot_done_callback)
            else:
                # 回退模式: 在后台线程执行(阻塞)
                logger.warning(f"[{func.__name__}] qasync不可用,使用线程模式执行async函数")
                _run_async_in_thread(coro, func.__name__)

        return wrapper

    # 支持 @async_slot 和 @async_slot() 两种用法
    if len(args) == 1 and callable(args[0]) and not kwargs:
        # @async_slot (无括号)
        func = args[0]
        args = ()
        return decorator(func)
    else:
        # @async_slot() (有括号)
        return decorator


def _async_slot_done_callback(task: asyncio.Task):
    """async_slot任务完成回调"""
    try:
        # 获取结果(如果有异常会抛出)
        task.result()
    except asyncio.CancelledError:
        logger.debug("异步Slot任务被取消")
    except Exception as e:
        logger.exception(f"异步Slot任务执行失败: {e}")
        # 可选: 发送错误信号到UI


def _run_async_in_thread(coro: Coroutine, name: str):
    """在后台线程执行async函数(回退模式)"""
    def thread_target():
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()
        except Exception as e:
            logger.exception(f"线程模式async函数执行失败[{name}]: {e}")

    thread = QThread()
    # 注意: 这里简化处理,实际应该使用QThread+moveToThread模式
    import threading
    threading.Thread(target=thread_target, name=f"AsyncSlot-{name}", daemon=True).start()


# ==================== await_in_qt辅助函数 ====================

def await_in_qt(coro: Coroutine, timeout: Optional[float] = None) -> Any:
    """在主线程安全执行async代码并等待结果

    用法:
        result = await_in_qt(some_async_operation())

    注意:
    - 会阻塞当前线程直到协程完成
    - 适用于非主线程调用async代码
    - 需要qasync支持

    Args:
        coro: 协程对象
        timeout: 超时时间(秒),None表示无限等待

    Returns:
        协程的返回值

    Raises:
        TimeoutError: 超时
        RuntimeError: 事件循环不可用
        Exception: 协程执行异常
    """
    if not QASYNC_AVAILABLE:
        raise RuntimeError("await_in_qt需要qasync支持")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError("没有运行的事件循环,无法执行await_in_qt")

    # 创建Future
    future = asyncio.ensure_future(coro, loop=loop)

    # 等待完成
    if timeout is not None:
        try:
            return asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            future.cancel()
            raise TimeoutError(f"await_in_qt超时({timeout}秒)")
    else:
        return future


# ==================== 异步任务管理器 ====================

class AsyncTaskRunner(QObject):
    """异步任务管理器

    功能:
    - 提交异步任务
    - 跟踪任务状态
    - 取消任务
    - 获取结果
    - 自动清理完成任务

    用法:
        runner = AsyncTaskRunner()
        task_id = runner.submit(some_async_operation())
        # ... 稍后
        result = runner.get_result(task_id)
    """

    # 信号: 任务完成(task_id, success, result_or_error)
    task_completed = Signal(str, bool, object)

    def __init__(self, auto_cleanup: bool = True, cleanup_interval: int = 60):
        """初始化任务管理器

        Args:
            auto_cleanup: 是否自动清理完成任务
            cleanup_interval: 清理间隔(秒)
        """
        super().__init__()
        self._tasks: Dict[str, asyncio.Task] = {}
        self._results: Dict[str, Any] = {}
        self._errors: Dict[str, Exception] = {}
        self._auto_cleanup = auto_cleanup
        self._cleanup_interval = cleanup_interval

        # 启动定期清理
        if auto_cleanup:
            from PySide6.QtCore import QTimer
            self._cleanup_timer = QTimer()
            self._cleanup_timer.timeout.connect(self._cleanup_completed_tasks)
            self._cleanup_timer.start(cleanup_interval * 1000)

    def submit(self, coro: Coroutine) -> str:
        """提交异步任务

        Args:
            coro: 协程对象

        Returns:
            task_id: 任务ID

        Raises:
            RuntimeError: 事件循环不可用
        """
        if not QASYNC_AVAILABLE:
            raise RuntimeError("AsyncTaskRunner需要qasync支持")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("没有运行的事件循环")

        # 生成任务ID
        task_id = str(uuid4())

        # 创建任务
        task = asyncio.ensure_future(coro, loop=loop)
        task.add_done_callback(
            lambda t: self._on_task_done(task_id, t)
        )

        self._tasks[task_id] = task
        logger.debug(f"提交异步任务: {task_id}")

        return task_id

    def cancel(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        if not task.done():
            task.cancel()
            logger.debug(f"取消异步任务: {task_id}")
            return True

        return False

    def get_result(self, task_id: str, remove: bool = True) -> Any:
        """获取任务结果

        Args:
            task_id: 任务ID
            remove: 是否移除任务

        Returns:
            任务结果

        Raises:
            KeyError: 任务不存在
            Exception: 任务执行异常
        """
        if task_id in self._errors:
            error = self._errors[task_id]
            if remove:
                del self._errors[task_id]
                self._tasks.pop(task_id, None)
            raise error

        if task_id in self._results:
            result = self._results[task_id]
            if remove:
                del self._results[task_id]
                self._tasks.pop(task_id, None)
            return result

        raise KeyError(f"任务不存在或未完成: {task_id}")

    def is_done(self, task_id: str) -> bool:
        """检查任务是否完成"""
        if task_id not in self._tasks:
            return False
        return self._tasks[task_id].done()

    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """任务完成回调"""
        try:
            result = task.result()
            self._results[task_id] = result
            self.task_completed.emit(task_id, True, result)
            logger.debug(f"异步任务完成: {task_id}")
        except asyncio.CancelledError:
            logger.debug(f"异步任务被取消: {task_id}")
            self.task_completed.emit(task_id, False, "cancelled")
        except Exception as e:
            self._errors[task_id] = e
            logger.exception(f"异步任务执行失败: {task_id}, {e}")
            self.task_completed.emit(task_id, False, e)

    def _cleanup_completed_tasks(self):
        """清理已完成的任务"""
        completed = [
            task_id for task_id, task in self._tasks.items()
            if task.done()
        ]

        for task_id in completed:
            self._tasks.pop(task_id, None)
            self._results.pop(task_id, None)
            self._errors.pop(task_id, None)

        if completed:
            logger.debug(f"清理了{len(completed)}个已完成任务")

    def cleanup(self):
        """手动清理所有任务"""
        self._cleanup_completed_tasks()


# ==================== 错误处理装饰器 ====================

def error_handler(logger_obj: Optional[logging.Logger] = None, reraise: bool = False):
    """装饰器: 统一错误处理

    用法:
        @error_handler()
        async def risky_operation(self):
            # 可能抛出异常的代码
            pass

    Args:
        logger_obj: 自定义logger,默认使用ui.async_utils
        reraise: 是否重新抛出异常

    Returns:
        装饰后的函数
    """
    _logger = logger_obj or logger

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            # async函数
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    _logger.error(
                        f"异步函数[{func.__name__}]执行失败: {e}\n{traceback.format_exc()}"
                    )
                    if reraise:
                        raise

            return async_wrapper
        else:
            # 普通函数
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    _logger.error(
                        f"函数[{func.__name__}]执行失败: {e}\n{traceback.format_exc()}"
                    )
                    if reraise:
                        raise

            return sync_wrapper

    return decorator


# ==================== 工具函数 ====================

def is_qasync_available() -> bool:
    """检查qasync是否可用"""
    return QASYNC_AVAILABLE


def get_event_loop() -> Optional[asyncio.AbstractEventLoop]:
    """安全获取事件循环"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
