# -*- coding: utf-8 -*-
"""
测试IPO批量下载功能和自适应配置优化

测试场景：
1. 小任务（5个品种）- 验证自适应配置是否正确缩减worker数
2. 中等任务（100个品种）- 验证动态调整
3. 大任务（全量品种）- 验证增量模式和批量性能
"""
import asyncio
import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.infrastructure.data_module_vnpy.data_acquisition.data_fetcher import download_ipo_dates
from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.local_data.data_quality import IPODateCache

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_small_task():
    """测试小任务（5个品种）"""
    print("\n" + "=" * 80)
    print("测试1：小任务优化（5个品种）")
    print("=" * 80)

    # 选择5个测试品种
    test_symbols = ["000001", "000002", "600000", "600519", "300750"]

    print(f"测试品种: {test_symbols}")
    print(f"预期配置: 1进程 × 5协程")
    print()

    start_time = time.time()

    result = download_ipo_dates(
        symbols=test_symbols, force_refresh=True, use_adaptive=True  # 强制刷新以测试性能
    )

    elapsed = time.time() - start_time

    print("\n" + "-" * 80)
    print("测试结果:")
    print(f"  总品种数: {result['total']}")
    print(f"  成功获取: {result['succeeded']}")
    print(f"  失败数: {result['failed']}")
    print(f"  总耗时: {elapsed:.2f}秒")
    print(f"  平均速度: {result['total']/elapsed:.2f}个/秒")
    print("-" * 80)

    # 显示获取到的IPO日期
    if result["data"]:
        print("\nIPO日期详情:")
        for symbol, ipo_date in result["data"].items():
            print(f"  {symbol}: {ipo_date}")

    return result


def test_medium_task():
    """测试中等任务（100个品种）"""
    print("\n" + "=" * 80)
    print("测试2：中等任务优化（100个品种）")
    print("=" * 80)

    # 获取前100个品种
    loader = SymbolLoader()
    classified = loader.load_from_cache()

    if not classified:
        print("品种列表缓存为空，重新加载...")
        loader.reload_and_classify()
        classified = loader.load_from_cache()

    test_symbols = []
    for market_name in ["上证A股", "深证A股"]:
        if market_name in classified:
            symbols = [item["code"] for item in classified[market_name]]
            test_symbols.extend(symbols)

    test_symbols = test_symbols[:100]

    print(f"测试品种数: {len(test_symbols)}")
    print(f"预期配置: 动态调整（约3-4进程）")
    print()

    start_time = time.time()

    result = download_ipo_dates(
        symbols=test_symbols, force_refresh=False, use_adaptive=True  # 使用增量模式
    )

    elapsed = time.time() - start_time

    print("\n" + "-" * 80)
    print("测试结果:")
    print(f"  总品种数: {result['total']}")
    print(f"  跳过缓存: {result['cached']}")
    print(f"  实际下载: {result['downloaded']}")
    print(f"  成功获取: {result['succeeded']}")
    print(f"  失败数: {result['failed']}")
    print(f"  总耗时: {elapsed:.2f}秒")
    if result["downloaded"] > 0:
        print(f"  下载速度: {result['downloaded']/elapsed:.2f}个/秒")
    print("-" * 80)

    return result


def test_large_task_incremental():
    """测试大任务增量模式（全量品种）"""
    print("\n" + "=" * 80)
    print("测试3：大任务增量模式（全量品种）")
    print("=" * 80)

    # 获取所有品种
    loader = SymbolLoader()
    all_symbols = loader.extract_all_codes()

    if not all_symbols:
        print("品种列表为空，重新加载...")
        loader.reload_and_classify()
        all_symbols = loader.extract_all_codes()

    print(f"测试品种数: {len(all_symbols)}")
    print(f"模式: 增量（跳过已缓存）")
    print()

    start_time = time.time()

    result = download_ipo_dates(
        symbols=all_symbols, force_refresh=False, use_adaptive=True  # 增量模式
    )

    elapsed = time.time() - start_time

    print("\n" + "-" * 80)
    print("测试结果:")
    print(f"  总品种数: {result['total']}")
    print(f"  跳过缓存: {result['cached']}")
    print(f"  实际下载: {result['downloaded']}")
    print(f"  成功获取: {result['succeeded']}")
    print(f"  失败数: {result['failed']}")
    print(f"  总耗时: {elapsed:.2f}秒 ({elapsed/60:.2f}分钟)")
    if result["downloaded"] > 0:
        print(f"  下载速度: {result['downloaded']/elapsed:.2f}个/秒")
    if result["total"] > 0:
        print(f"  缓存命中率: {result['cached']/result['total']*100:.1f}%")
    print("-" * 80)

    return result


def test_cache_persistence():
    """测试缓存持久化"""
    print("\n" + "=" * 80)
    print("测试4：缓存持久化验证")
    print("=" * 80)

    # 创建新的缓存实例
    cache1 = IPODateCache()
    stats1 = cache1.get_stats()

    print(f"缓存统计:")
    print(f"  缓存大小: {stats1['cache_size']}")
    print(f"  总查询数: {stats1['total_queries']}")
    print(f"  命中率: {stats1['hit_rate']:.1f}%")
    print(f"  API调用: {stats1['api_calls']}")
    print(f"  API成功: {stats1['api_success']}")
    print(f"  API超时: {stats1['api_timeout']}")

    # 测试读取
    test_symbols = ["000001", "600519"]
    print(f"\n读取测试品种: {test_symbols}")
    for symbol in test_symbols:
        ipo_date, is_cached = cache1.get(symbol)
        print(f"  {symbol}: {ipo_date} (缓存={'命中' if is_cached else '未命中'})")

    return stats1


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("IPO批量下载功能测试套件")
    print("=" * 80)
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = {}

    try:
        # 测试1：小任务
        results["small"] = test_small_task()
        time.sleep(2)

        # 测试2：中等任务
        results["medium"] = test_medium_task()
        time.sleep(2)

        # 测试3：大任务增量
        results["large"] = test_large_task_incremental()
        time.sleep(2)

        # 测试4：缓存持久化
        results["cache"] = test_cache_persistence()

    except KeyboardInterrupt:
        print("\n\n用户中断测试")
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback

        traceback.print_exc()

    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    if "small" in results:
        print(f"小任务测试: ✓ 成功 ({results['small']['succeeded']}/{results['small']['total']})")

    if "medium" in results:
        print(
            f"中等任务测试: ✓ 成功 ({results['medium']['succeeded']}/{results['medium']['total']})"
        )

    if "large" in results:
        print(f"大任务测试: ✓ 成功 ({results['large']['succeeded']}/{results['large']['total']})")

    if "cache" in results:
        print(f"缓存测试: ✓ 成功 (缓存大小: {results['cache']['cache_size']})")

    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试IPO批量下载功能")
    parser.add_argument(
        "--test",
        choices=["small", "medium", "large", "cache", "all"],
        default="all",
        help="选择测试类型",
    )

    args = parser.parse_args()

    if args.test == "small":
        test_small_task()
    elif args.test == "medium":
        test_medium_task()
    elif args.test == "large":
        test_large_task_incremental()
    elif args.test == "cache":
        test_cache_persistence()
    else:
        run_all_tests()
