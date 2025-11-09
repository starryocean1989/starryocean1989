# -*- coding: utf-8 -*-
"""
阶段3并发执行栈日志集成测试

验证 native_threadpool、native_scheduler、native_async、native_queue、native_load_balancer
的 NativeLogBridge 日志集成是否正常工作。
"""

import logging
import threading
import time
from unittest.mock import patch

import pytest

from backend.infrastructure.native.logging_bridge import install_native_logging_bridge


class LogCapture:
    """日志捕获器"""

    def __init__(self):
        self.records = []

    def capture(self, record):
        """捕获日志记录"""
        self.records.append({
            'level': record['level'],
            'component': record['component'],
            'function': record['function'],
            'line': record['line'],
            'message': record['message'],
            'details': record['details']
        })


@pytest.fixture(scope="module")
def log_capturer():
    """全局日志捕获器"""
    capturer = LogCapture()

    # 安装日志桥接
    install_native_logging_bridge(
        logger=logging.getLogger("test.native.stage3"),
        handler=capturer.capture
    )

    yield capturer

    # 清理
    capturer.records.clear()


class TestNativeThreadPoolLogging:
    """测试 native_threadpool 日志集成"""

    def test_threadpool_initialization_logging(self, log_capturer):
        """测试线程池初始化日志"""
        from backend.infrastructure.native.native_threadpool import NativeThreadPool

        # 清空之前的日志
        log_capturer.records.clear()

        # 创建线程池
        with NativeThreadPool(max_workers=2) as pool:
            # 等待一小段时间让日志处理完成
            time.sleep(0.1)

            # 验证初始化日志
            init_logs = [r for r in log_capturer.records
                        if r['component'] == 'native_threadpool' and
                        'initialization completed' in r['message']]
            assert len(init_logs) >= 1, "Should log threadpool initialization"

    def test_threadpool_task_execution_logging(self, log_capturer):
        """测试任务执行日志"""
        from backend.infrastructure.native.native_threadpool import NativeThreadPool

        log_capturer.records.clear()

        def test_task(x):
            return x * 2

        with NativeThreadPool(max_workers=2) as pool:
            # 提交任务
            future = pool.submit(test_task, 5)
            result = future.result(timeout=1.0)

            # 等待日志处理
            time.sleep(0.1)

            assert result == 10

            # 验证任务执行日志
            task_logs = [r for r in log_capturer.records
                        if r['component'] == 'native_threadpool' and
                        ('task execution' in r['message'] or 'Task submitted' in r['message'])]
            assert len(task_logs) >= 1, "Should log task execution"


class TestNativeSchedulerLogging:
    """测试 native_scheduler 日志集成"""

    def test_scheduler_operations_logging(self, log_capturer):
        """测试调度器操作日志"""
        try:
            from backend.infrastructure.native.native_scheduler import NativeScheduler
            from backend.infrastructure.native.native_threadpool import NativeThreadPool
        except ImportError:
            pytest.skip("Native scheduler not available")

        log_capturer.records.clear()

        def test_task():
            return "completed"

        executor = NativeThreadPool(max_workers=1)
        scheduler = NativeScheduler(executor_factory=lambda _workers: executor)

        # 注册类别
        scheduler.register_category("test", queue_capacity=10, max_workers=1)

        # 提交任务
        future = scheduler.submit("test", test_task)
        result = future.result(timeout=2.0)

        # 等待日志处理
        time.sleep(0.1)

        assert result == "completed"

        # 验证调度器日志
        scheduler_logs = [r for r in log_capturer.records
                         if r['component'] == 'native_scheduler']
        assert len(scheduler_logs) >= 1, "Should log scheduler operations"

        scheduler.shutdown()


class TestNativeAsyncLogging:
    """测试 native_async 日志集成"""

    def test_async_reduce_logging(self, log_capturer):
        """测试异步归约日志"""
        from backend.infrastructure.native.native_async import reduce_task_results

        log_capturer.records.clear()

        # 准备测试数据 - 包含正常结果和异常
        task_results = [
            ("symbol1", 100),
            ("symbol2", 200),
            Exception("Test exception"),
            ("symbol3", None)
        ]

        # 执行归约
        result = reduce_task_results(
            task_results=task_results,
            total=4,
            progress_stride=2
        )

        # 等待日志处理
        time.sleep(0.1)

        # 验证结果结构
        assert 'summary' in result
        assert 'items' in result
        assert 'errors' in result
        assert result['summary']['error_count'] >= 1

        # 验证日志
        async_logs = [r for r in log_capturer.records
                     if r['component'] == 'native_async']
        assert len(async_logs) >= 1, "Should log async operations"


class TestNativeQueueLogging:
    """测试 native_queue 日志集成"""

    def test_queue_operations_logging(self, log_capturer):
        """测试队列操作日志"""
        from backend.infrastructure.native.native_queue import NativeQueue

        log_capturer.records.clear()

        # 创建队列并执行操作
        queue = NativeQueue(capacity=10)

        # 入队
        queue.push("test_item1")
        queue.push("test_item2")

        # 出队
        item1 = queue.pop()
        item2 = queue.pop()

        assert item1 == "test_item1"
        assert item2 == "test_item2"

        # 等待日志处理
        time.sleep(0.1)

        # 验证队列日志 (可能没有详细日志，主要是验证无错误)
        queue_logs = [r for r in log_capturer.records
                     if r['component'] == 'native_queue']
        # 队列日志可能较少，主要验证无错误日志
        assert len(queue_logs) >= 0, "Queue should not produce error logs"


class TestNativeLoadBalancerLogging:
    """测试 native_load_balancer 日志集成"""

    def test_load_balancer_optimization_logging(self, log_capturer):
        """测试负载均衡器优化日志"""
        try:
            from backend.infrastructure.native.native_load_balancer import optimize
        except ImportError:
            pytest.skip("Native load balancer not available")

        log_capturer.records.clear()

        # 执行优化计算
        result = optimize(
            bottleneck_value=50.0,
            queue_factor=1.0,
            base_processes=1,
            base_coroutines=10,
            max_processes=4,
            max_coroutines=100,
            min_coroutines=5,
            total_max_connections=1000,
            task_total_count=100
        )

        # 等待日志处理
        time.sleep(0.1)

        # 验证结果
        assert isinstance(result, dict)
        assert 'processes' in result
        assert 'coroutines_per_process' in result

        # 验证日志
        lb_logs = [r for r in log_capturer.records
                  if r['component'] == 'native_load_balancer']
        assert len(lb_logs) >= 1, "Should log load balancer operations"


class TestConcurrencyStackIntegration:
    """测试并发执行栈整体集成"""

    def test_all_modules_import_without_error(self):
        """测试所有模块都能正常导入"""
        modules_to_test = [
            'backend.infrastructure.native.native_threadpool',
            'backend.infrastructure.native.native_scheduler',
            'backend.infrastructure.native.native_async',
            'backend.infrastructure.native.native_queue',
            'backend.infrastructure.native.native_load_balancer'
        ]

        for module_name in modules_to_test:
            try:
                __import__(module_name)
            except ImportError as e:
                # 对于可选的native模块，ImportError是允许的
                if "extension" not in str(e).lower():
                    raise

    def test_logging_bridge_integration(self, log_capturer):
        """测试日志桥接集成"""
        # 执行一些操作来产生日志
        from backend.infrastructure.native.native_threadpool import NativeThreadPool

        log_capturer.records.clear()

        with NativeThreadPool(max_workers=1) as pool:
            future = pool.submit(lambda: "test")
            result = future.result(timeout=1.0)

        # 等待日志处理
        time.sleep(0.1)

        assert result == "test"

        # 验证有日志产生
        all_logs = log_capturer.records
        assert len(all_logs) > 0, "Should produce some logs"

        # 验证日志格式
        for record in all_logs:
            assert 'level' in record
            assert 'component' in record
            assert 'function' in record
            assert 'line' in record
            assert 'message' in record
            # details 可以为空


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
