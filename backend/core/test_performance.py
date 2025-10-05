# -*- coding: utf-8 -*-
"""
性能优化模块测试.

验证缓存机制、异步处理等性能优化功能。
"""

import asyncio
import sys
import time
from pathlib import Path

# 使用绝对导入避免相对导入问题
from backend.core.models import UnifiedMarketData
from backend.core.performance import (
    AsyncDataProcessor, AsyncTaskManager, Cache, DataCache,
    get_performance_optimizer
)
from backend.core.vnpy_integration import get_terminal_engine

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_cache():
    """测试缓存功能.

    验证基础缓存和数据缓存的功能。
    """
    print("=== 测试缓存功能 ===")

    # 测试基础缓存
    cache = Cache(max_size=3, ttl=5)

    # 添加缓存项
    cache.put("key1", "value1")
    cache.put("key2", "value2")
    cache.put("key3", "value3")

    # 获取缓存项
    value = cache.get("key1")
    assert value == "value1", f"期望 value1，得到 {value}"

    # 测试LRU机制
    cache.put("key4", "value4")  # 应该删除key2（最少使用）
    value = cache.get("key2")
    assert value is None, "key2应该被删除"

    print("✅ 基础缓存测试通过")

    # 测试数据缓存
    data_cache = DataCache()

    # 测试行情数据缓存
    market_data = [
        UnifiedMarketData(
            symbol="000001", exchange="SZSE", data_type="tick",
            datetime=None, timestamp=0, close_price=10.0, volume=100
        )
    ]
    data_cache.cache_market_data("000001", market_data)

    retrieved = data_cache.get_market_data("000001")
    assert len(retrieved) == 1, f"期望1条数据，得到{len(retrieved)}条"

    stats = data_cache.get_stats()
    assert stats["market_data_cache"]["size"] == 1, "缓存统计错误"

    print("✅ 数据缓存测试通过")


def test_async_task_manager():
    """测试异步任务管理器.

    验证同步和异步任务的管理功能。
    """
    print("\n=== 测试异步任务管理器 ===")

    task_manager = AsyncTaskManager(max_workers=2)
    task_manager.start_event_loop()

    # 测试同步任务
    def test_task(x, y):
        time.sleep(0.1)  # 模拟耗时操作
        return x + y

    task_id = task_manager.submit_task("test1", test_task, 5, 3)
    result = task_manager.get_task_result(task_id, timeout=5)

    assert result["success"], f"任务执行失败: {result.get('error')}"
    assert result["result"] == 8, f"期望8，得到{result['result']}"

    print("✅ 同步任务测试通过")

    # 测试异步协程任务
    async def async_test_task(x, y):
        await asyncio.sleep(0.1)
        return x * y

    task_id = task_manager.submit_asyncio_task(async_test_task, 6, 7)
    result = task_manager.get_task_result(task_id, timeout=5)

    assert result["success"], f"异步任务执行失败: {result.get('error')}"
    assert result["result"] == 42, f"期望42，得到{result['result']}"

    print("✅ 异步任务测试通过")

    task_manager.stop_event_loop()


def test_performance_optimizer():
    """测试性能优化器.

    验证缓存、异步任务和性能统计功能。
    """
    print("\n=== 测试性能优化器 ===")

    # 获取终端引擎
    engine = get_terminal_engine()
    optimizer = get_performance_optimizer(engine)

    # 测试缓存功能
    test_data = UnifiedMarketData(
        symbol="000002", exchange="SZSE", data_type="tick",
        datetime=None, timestamp=0, close_price=20.0, volume=200
    )

    optimizer.cache_data("market", "000002", [test_data])
    cached_data = optimizer.get_cached_data("market", "000002")

    assert cached_data is not None, "缓存数据获取失败"
    assert len(cached_data) == 1, f"期望1条数据，得到{len(cached_data)}条"

    print("✅ 性能优化器缓存测试通过")

    # 测试异步任务
    def cpu_intensive_task(n):
        return sum(i * i for i in range(n))

    task_id = optimizer.submit_async_task(
        "cpu_test", cpu_intensive_task, 10000
    )
    result = optimizer.get_task_result(task_id, timeout=10)

    assert result["success"], f"CPU密集任务失败: {result.get('error')}"
    expected = sum(i * i for i in range(10000))
    assert result["result"] == expected, (
        f"计算结果错误: 期望{expected}，得到{result['result']}"
    )

    print("✅ 性能优化器异步任务测试通过")

    # 测试性能统计
    stats = optimizer.get_performance_stats()
    assert "cache_stats" in stats, "性能统计缺少缓存信息"
    assert "task_manager_stats" in stats, "性能统计缺少任务管理器信息"

    print("✅ 性能统计测试通过")


def test_async_data_processor():
    """测试异步数据处理器.

    验证数据处理器的同步处理功能。
    """
    print("\n=== 测试异步数据处理器 ===")

    # 创建模拟数据
    test_data = []
    for i in range(10):
        data = UnifiedMarketData(
            symbol=f"STOCK{i}", exchange="SZSE", data_type="tick",
            datetime=None, timestamp=i, close_price=10.0 + i, volume=100 * i
        )
        test_data.append(data)

    # 获取性能优化器
    engine = get_terminal_engine()
    optimizer = get_performance_optimizer(engine)
    processor = AsyncDataProcessor(optimizer)

    # 测试同步处理
    result = processor.process_data_sync(test_data)

    assert len(result) == 10, f"期望10个股票，得到{len(result)}个"
    assert "STOCK0" in result, "第一个股票数据丢失"
    assert len(result["STOCK0"]) == 1, (
        f"STOCK0应该有1条记录，得到{len(result['STOCK0'])}条"
    )

    print("✅ 异步数据处理器测试通过")


def main():
    """主测试函数.

    运行所有性能优化模块的测试。
    """
    print("🚀 开始性能优化模块测试")
    print("=" * 50)

    # 运行所有测试
    tests = [
        test_cache,
        test_async_task_manager,
        test_performance_optimizer,
        test_async_data_processor
    ]

    results = []
    for test_func in tests:
        try:
            test_func()  # 只调用函数，不赋值返回值
            results.append(True)
        except (RuntimeError, TypeError, AttributeError) as e:
            print(f"❌ 测试失败 {test_func.__name__}: {e}")
            results.append(False)

    # 输出结果摘要
    print("\n" + "=" * 50)
    print("📊 测试结果摘要:")

    passed = sum(results)
    total = len(results)

    for i, (test_func, result) in enumerate(zip(tests, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {test_func.__name__}: {status}")

    print(f"\n总体结果: {passed}/{total} 个测试通过")

    if passed == total:
        print("🎉 所有性能优化模块测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，需要检查相关模块")
        return 1


if __name__ == "__main__":
    sys.exit(main())
