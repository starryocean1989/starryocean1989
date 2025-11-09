# -*- coding: utf-8 -*-
"""
验证阶段3并发执行栈日志集成接入体系
"""

import logging
import time
import sys
from backend.infrastructure.native.logging_bridge import install_native_logging_bridge


class TestLogHandler(logging.Handler):
    """测试用的日志处理器"""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        """记录日志"""
        self.records.append({
            'level': record.levelno,
            'level_name': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'component': getattr(record, 'native_module', 'unknown'),
            'scenario': getattr(record, 'scenario', 'unknown'),
            'function': getattr(record, 'native_function', 'unknown'),
            'line': getattr(record, 'native_line', 0),
            'details': getattr(record, 'native_details', None),
            'log_type': getattr(record, 'log_type', 'unknown'),
        })


def test_native_threadpool():
    """测试native_threadpool日志集成"""
    print("=== 测试 native_threadpool 日志集成 ===")

    log_handler = TestLogHandler()
    test_logger = logging.getLogger("test.native.threadpool")
    test_logger.addHandler(log_handler)
    test_logger.setLevel(logging.DEBUG)

    # 安装日志桥接
    install_native_logging_bridge(logger=test_logger)

    try:
        from backend.infrastructure.native.native_threadpool import NativeThreadPool

        # 测试线程池操作
        with NativeThreadPool(max_workers=2) as pool:
            # 提交正常任务
            future1 = pool.submit(lambda: "success")
            result1 = future1.result(timeout=2.0)

            # 提交会失败的任务
            future2 = pool.submit(lambda: (_ for _ in ()).throw(RuntimeError("test error")))
            try:
                result2 = future2.result(timeout=2.0)
            except Exception:
                pass  # 预期会失败

        # 等待日志处理
        time.sleep(0.1)

        # 分析日志
        threadpool_logs = [r for r in log_handler.records if 'native_threadpool' in r['component']]

        print(f"收集到 {len(threadpool_logs)} 条 native_threadpool 日志:")
        for log in threadpool_logs:
            print(f"  [{log['level_name']}] {log['component']}.{log['function']}:{log['line']} - {log['message']}")
            if log['details']:
                print(f"    详情: {log['details']}")

        return len(threadpool_logs) > 0

    except Exception as e:
        print(f"❌ native_threadpool 测试失败: {e}")
        return False


def test_native_async():
    """测试native_async日志集成"""
    print("\n=== 测试 native_async 日志集成 ===")

    log_handler = TestLogHandler()
    test_logger = logging.getLogger("test.native.async")
    test_logger.addHandler(log_handler)
    test_logger.setLevel(logging.DEBUG)

    # 安装日志桥接
    install_native_logging_bridge(logger=test_logger)

    try:
        from backend.infrastructure.native.native_async import reduce_task_results

        # 准备测试数据
        task_results = [
            ("success", 100),
            Exception("test error"),
            ("another_success", 200)
        ]

        # 执行归约
        result = reduce_task_results(
            task_results=task_results,
            total=3,
            progress_stride=1
        )

        # 等待日志处理
        time.sleep(0.1)

        # 分析日志
        async_logs = [r for r in log_handler.records if 'native_async' in r['component']]

        print(f"收集到 {len(async_logs)} 条 native_async 日志:")
        for log in async_logs:
            print(f"  [{log['level_name']}] {log['component']}.{log['function']}:{log['line']} - {log['message']}")
            if log['details']:
                print(f"    详情: {log['details']}")

        # 验证结果
        assert result['summary']['total'] == 3
        assert result['summary']['success_count'] == 2
        assert result['summary']['error_count'] == 1

        return len(async_logs) > 0

    except Exception as e:
        print(f"❌ native_async 测试失败: {e}")
        return False


def test_native_scheduler():
    """测试native_scheduler日志集成"""
    print("\n=== 测试 native_scheduler 日志集成 ===")

    log_handler = TestLogHandler()
    test_logger = logging.getLogger("test.native.scheduler")
    test_logger.addHandler(log_handler)
    test_logger.setLevel(logging.DEBUG)

    # 安装日志桥接
    install_native_logging_bridge(logger=test_logger)

    try:
        from backend.infrastructure.native.native_scheduler import NativeScheduler
        from backend.infrastructure.native.native_threadpool import NativeThreadPool

        # 创建调度器
        executor = NativeThreadPool(max_workers=1)
        scheduler = NativeScheduler(executor_factory=lambda: executor)

        # 注册类别
        scheduler.register_category("test", queue_capacity=10, max_workers=1)

        # 提交任务
        def test_func():
            return "scheduled_success"
        future = scheduler.submit("test", test_func)
        result = future.result(timeout=3.0)

        # 等待日志处理
        time.sleep(0.1)

        # 分析日志
        scheduler_logs = [r for r in log_handler.records if 'native_scheduler' in r['component']]

        print(f"收集到 {len(scheduler_logs)} 条 native_scheduler 日志:")
        for log in scheduler_logs:
            print(f"  [{log['level_name']}] {log['component']}.{log['function']}:{log['line']} - {log['message']}")
            if log['details']:
                print(f"    详情: {log['details']}")

        # 验证结果
        assert result == "scheduled_success"

        scheduler.shutdown()
        return len(scheduler_logs) > 0

    except Exception as e:
        print(f"❌ native_scheduler 测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("开始验证阶段3并发执行栈日志集成接入体系\n")

    # 设置日志级别
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    results = []

    # 测试各个模块
    results.append(("native_threadpool", test_native_threadpool()))
    results.append(("native_async", test_native_async()))
    results.append(("native_scheduler", test_native_scheduler()))

    # 测试其他模块的基本导入（不进行详细功能测试）
    print("\n=== 测试其他模块基本导入 ===")

    try:
        from backend.infrastructure.native.native_queue import NativeQueue
        queue = NativeQueue(capacity=10)
        queue.push("test")
        item = queue.pop()
        assert item == "test"
        print("✅ native_queue: 基本功能正常")
        results.append(("native_queue", True))
    except Exception as e:
        print(f"❌ native_queue 测试失败: {e}")
        results.append(("native_queue", False))

    try:
        from backend.infrastructure.native.native_load_balancer import optimize
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
        assert isinstance(result, dict)
        assert 'processes' in result
        print("✅ native_load_balancer: 基本功能正常")
        results.append(("native_load_balancer", True))
    except Exception as e:
        print(f"❌ native_load_balancer 测试失败: {e}")
        results.append(("native_load_balancer", False))

    # 总结
    print("\n=== 接入体系验证结果 ===")
    all_passed = True
    for module, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{module}: {status}")
        if not passed:
            all_passed = False

    print(f"\n总体结果: {'✅ 所有测试通过' if all_passed else '❌ 部分测试失败'}")
    print("\n日志集成验证完成!")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
