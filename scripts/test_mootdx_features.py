# -*- coding: utf-8 -*-
"""
测试 mootdx 迁移功能

测试从mootdx迁移到tdx_asyncio的各项功能：
1. 股票市场智能识别
2. 数据转换工具
3. 缓存系统
4. 性能监控装饰器
5. 复权调整功能

作者：[项目名称]
版本：2.0
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.infrastructure.tdx_asyncio import (
    # 核心功能
    get_stock_market, get_stock_markets,
    to_dataframe, to_file_async, to_csv, to_json,
    async_file_cache, AsyncDataCache,
    async_timeit, performance_monitor,
    apply_adjustment,
    AsyncTdxHq_API
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_market_identification():
    """测试股票市场智能识别"""
    print("\n=== 测试股票市场智能识别 ===")

    try:
        # 测试单个股票识别
        test_cases = [
            ("600000", 1, "sh"),  # 上海A股
            ("000001", 0, "sz"),  # 深圳A股
            ("sh600000", 1, "sh"),  # 上海带前缀
            ("sz000001", 0, "sz"),  # 深圳带前缀
            ("688001", 1, "sh"),  # 科创板
            ("002001", 0, "sz"),  # 中小板
        ]

        for symbol, expected_num, expected_str in test_cases:
            result_num = get_stock_market(symbol, string=False)
            result_str = get_stock_market(symbol, string=True)

            if result_num == expected_num and result_str == expected_str:
                print(f"✓ {symbol} -> 数字:{result_num}, 字符:{result_str}")
            else:
                print(f"✗ {symbol} -> 期望数字:{expected_num},字符:{expected_str}, 实际数字:{result_num},字符:{result_str}")
                return False

        # 测试批量识别
        symbols = ["600000", "000001", "sh600000", "sz000001"]
        markets = get_stock_markets(symbols)

        expected_markets = [(1, "600000"), (0, "000001"), (1, "sh600000"), (0, "sz000001")]
        if markets == expected_markets:
            print(f"✓ 批量识别成功: {markets}")
        else:
            print(f"✗ 批量识别失败，期望: {expected_markets}, 实际: {markets}")
            return False

        print("✓ 股票市场智能识别测试通过")
        return True

    except Exception as e:
        print(f"✗ 股票市场智能识别测试失败: {e}")
        return False


async def test_data_converters():
    """测试数据转换工具"""
    print("\n=== 测试数据转换工具 ===")

    try:
        # 测试数据
        data = [
            {'code': '600000', 'price': 10.5, 'vol': 1000, 'datetime': '2023-01-01 09:30:00'},
            {'code': '000001', 'price': 20.5, 'vol': 2000, 'datetime': '2023-01-01 09:31:00'},
        ]

        # 测试 to_dataframe
        df = to_dataframe(data)
        if df is not None and len(df) == 2 and 'volume' in df.columns:
            print(f"✓ to_dataframe 成功: 形状{df.shape}, 列{df.columns.tolist()}")
        else:
            print(f"✗ to_dataframe 失败: {df}")
            return False

        # 测试异步文件保存
        with tempfile.TemporaryDirectory() as temp_dir:
            # CSV保存
            csv_path = Path(temp_dir) / 'test.csv'
            success = await to_file_async(df, str(csv_path))
            if success and csv_path.exists():
                print(f"✓ CSV异步保存成功: {csv_path}")
            else:
                print(f"✗ CSV异步保存失败")
                return False

            # JSON保存
            json_path = Path(temp_dir) / 'test.json'
            success = await to_file_async(df, str(json_path))
            if success and json_path.exists():
                print(f"✓ JSON异步保存成功: {json_path}")
            else:
                print(f"✗ JSON异步保存失败")
                return False

        # 测试同步保存
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / 'sync_test.csv'
            success = to_csv(df, str(csv_path))
            if success and csv_path.exists():
                print(f"✓ 同步CSV保存成功: {csv_path}")
            else:
                print(f"✗ 同步CSV保存失败")
                return False

        print("✓ 数据转换工具测试通过")
        return True

    except Exception as e:
        print(f"✗ 数据转换工具测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_caching_system():
    """测试缓存系统"""
    print("\n=== 测试缓存系统 ===")

    try:
        # 测试内存缓存
        cache = AsyncDataCache(default_ttl=2)  # 2秒TTL

        # 设置缓存
        await cache.set('test_key', 'test_value', ttl=1)  # 1秒TTL
        value = await cache.get('test_key')

        if value == 'test_value':
            print("✓ 内存缓存设置和获取成功")
        else:
            print(f"✗ 内存缓存失败，期望 'test_value'，实际 {value}")
            return False

        # 等待过期
        await asyncio.sleep(2)
        expired_value = await cache.get('test_key')
        if expired_value is None:
            print("✓ 缓存过期机制正常")
        else:
            print(f"✗ 缓存过期机制失败，期望 None，实际 {expired_value}")
            return False

        # 测试缓存清理
        await cache.set('key1', 'value1')
        await cache.set('key2', 'value2')

        size_before = await cache.size()
        cleaned = await cache.cleanup()
        size_after = await cache.size()

        if size_before == 2 and size_after == 0 and cleaned == 2:
            print("✓ 缓存清理功能正常")
        else:
            print(f"✗ 缓存清理失败，清理前: {size_before}, 清理后: {size_after}, 清理数量: {cleaned}")
            return False

        print("✓ 缓存系统测试通过")
        return True

    except Exception as e:
        print(f"✗ 缓存系统测试失败: {e}")
        return False


async def test_performance_monitor():
    """测试性能监控装饰器"""
    print("\n=== 测试性能监控装饰器 ===")

    try:
        @async_timeit
        async def test_function():
            await asyncio.sleep(0.1)  # 100ms
            return "test_result"

        # 执行函数（自动记录性能）
        result = await test_function()

        if result == "test_result":
            print("✓ 装饰器函数执行成功")
        else:
            print(f"✗ 装饰器函数执行失败，期望 'test_result'，实际 {result}")
            return False

        # 检查性能统计
        stats = performance_monitor.get_stats('test_function')
        if stats and stats['count'] == 1 and stats['total_time'] > 0.09:
            print(f"✓ 性能统计正常: 调用{stats['count']}次, 总耗时{stats['total_time']:.3f}s")
        else:
            print(f"✗ 性能统计异常: {stats}")
            return False

        # 执行多次测试平均值
        for _ in range(3):
            await test_function()

        stats = performance_monitor.get_stats('test_function')
        if stats['count'] == 4 and stats['avg_time'] > 0.09:
            print(f"✓ 多轮执行统计正常: 平均耗时{stats['avg_time']:.3f}s")
        else:
            print(f"✗ 多轮执行统计异常: {stats}")
            return False

        print("✓ 性能监控装饰器测试通过")
        return True

    except Exception as e:
        print(f"✗ 性能监控装饰器测试失败: {e}")
        return False


async def test_adjustment_function():
    """测试复权调整功能"""
    print("\n=== 测试复权调整功能 ===")

    try:
        # 创建测试数据
        data = [
            {'date': '2023-01-01', 'price': 10.0, 'vol': 1000},
            {'date': '2023-01-02', 'price': 10.5, 'vol': 1100},
        ]

        df = pd.DataFrame(data)

        # 测试不复权（应该返回原数据）
        no_adjust_df = await apply_adjustment(df, '600000', adjust_type=None)
        if no_adjust_df is not None:
            print("✓ 不复权功能正常")
        else:
            print("✗ 不复权功能异常")
            return False

        # 测试前复权（由于无法获取实际除权信息，会返回原数据）
        qfq_df = await apply_adjustment(df, '600000', adjust_type='qfq')
        if qfq_df is not None:
            print("✓ 前复权功能正常（无除权信息时返回原数据）")
        else:
            print("✗ 前复权功能异常")
            return False

        # 测试后复权
        hfq_df = await apply_adjustment(df, '600000', adjust_type='hfq')
        if hfq_df is not None:
            print("✓ 后复权功能正常（无除权信息时返回原数据）")
        else:
            print("✗ 后复权功能异常")
            return False

        # 测试复权判断
        need_adjust = await asyncio.get_event_loop().run_in_executor(
            None, lambda: __import__('backend.infrastructure.tdx_asyncio.adjustments', fromlist=['is_adjustment_needed']).is_adjustment_needed('600000')
        )
        print(f"✓ 复权判断功能正常: {need_adjust}")

        print("✓ 复权调整功能测试通过")
        return True

    except Exception as e:
        print(f"✗ 复权调整功能测试失败: {e}")
        return False


async def test_integration():
    """集成测试：组合使用各项功能"""
    print("\n=== 集成测试 ===")

    try:
        # 模拟完整工作流程
        symbols = ["600000", "000001", "sh600000"]

        # 1. 市场识别
        markets = get_stock_markets(symbols)
        print(f"✓ 市场识别: {markets}")

        # 2. 数据转换
        data = [
            {'symbol': symbol, 'price': 10.0, 'vol': 1000}
            for symbol in symbols
        ]
        df = to_dataframe(data)
        print(f"✓ 数据转换: {df.shape}")

        # 3. 缓存使用
        cache = AsyncDataCache(default_ttl=30)

        @async_file_cache('cache/test_data.pkl', refresh_time=60)
        async def get_cached_data():
            return df

        # 第一次调用（缓存）
        cached_df1 = await get_cached_data()
        print(f"✓ 缓存调用成功: {cached_df1.shape}")

        # 第二次调用（使用缓存）
        cached_df2 = await get_cached_data()
        print(f"✓ 缓存命中成功: {cached_df2.shape}")

        # 4. 性能监控
        @async_timeit
        async def monitored_function():
            await asyncio.sleep(0.05)
            return "monitored"

        result = await monitored_function()
        stats = performance_monitor.get_stats('monitored_function')

        if result == "monitored" and stats['count'] == 1:
            print(f"✓ 性能监控正常: {stats}")
        else:
            print(f"✗ 性能监控异常: {result}, {stats}")
            return False

        print("✓ 集成测试通过")
        return True

    except Exception as e:
        print(f"✗ 集成测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("=" * 60)
    print("🔍 mootdx 迁移功能测试")
    print("=" * 60)

    # 设置快速超时，避免测试时间过长
    import asyncio
    asyncio.get_event_loop().slow_callback_duration = 30.0

    test_results = []

    # 1. 股票市场智能识别测试
    test_results.append(await test_market_identification())

    # 2. 数据转换工具测试
    test_results.append(await test_data_converters())

    # 3. 缓存系统测试
    test_results.append(await test_caching_system())

    # 4. 性能监控装饰器测试
    test_results.append(await test_performance_monitor())

    # 5. 复权调整功能测试
    test_results.append(await test_adjustment_function())

    # 6. 集成测试
    test_results.append(await test_integration())

    # 汇总结果
    passed = sum(test_results)
    total = len(test_results)

    print("\n" + "=" * 60)
    print(f"📊 测试结果汇总: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有mootdx迁移功能测试通过！")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查实现")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
