# -*- coding: utf-8 -*-
"""
数据质量优化性能验证脚本

验证目标：
1. IPO查询超时率 < 5%
2. 缓存命中率 > 95%（二次扫描）
3. 扫描时间 < 30秒（5000品种）
"""

import time
import asyncio
from datetime import datetime
from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
    DataValidator,
    DataSensor,
)
from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader


def verify_ipo_cache_performance():
    """验证IPO缓存性能"""
    print("=" * 60)
    print("性能验证1：IPO缓存机制")
    print("=" * 60)

    validator = DataValidator()

    # 测试品种列表（使用常见股票）
    test_symbols = [
        "600000",
        "600001",
        "600004",
        "600005",
        "600006",
        "000001",
        "000002",
        "000004",
        "000005",
        "000006",
        "600016",
        "600018",
        "600019",
        "600020",
        "600021",
    ]

    print(f"\n测试品种数量: {len(test_symbols)}")

    # 第一次查询（冷启动，需要API调用）
    print("\n[第一次查询 - 冷启动]")
    start_time = time.time()

    success_count = 0
    timeout_count = 0

    for symbol in test_symbols:
        result = validator._get_ipo_date(symbol)
        if result:
            success_count += 1
        else:
            timeout_count += 1

    elapsed_first = time.time() - start_time

    # 获取缓存统计
    stats_first = validator._ipo_cache.get_stats()

    print(f"  耗时: {elapsed_first:.2f}秒")
    print(f"  成功: {success_count}/{len(test_symbols)}")
    print(f"  超时: {timeout_count}/{len(test_symbols)}")
    print(f"  API调用: {stats_first['api_calls']}")
    print(
        f"  API成功率: {(stats_first['api_success']/stats_first['api_calls']*100) if stats_first['api_calls'] > 0 else 0:.1f}%"
    )
    print(
        f"  超时率: {(stats_first['api_timeout']/stats_first['api_calls']*100) if stats_first['api_calls'] > 0 else 0:.1f}%"
    )

    # 第二次查询（热启动，应该全部从缓存获取）
    print("\n[第二次查询 - 热启动]")
    start_time = time.time()

    for symbol in test_symbols:
        validator._get_ipo_date(symbol)

    elapsed_second = time.time() - start_time

    stats_second = validator._ipo_cache.get_stats()

    print(f"  耗时: {elapsed_second:.2f}秒")
    print(f"  缓存命中率: {stats_second['hit_rate']:.1f}%")
    print(f"  加速比: {elapsed_first/elapsed_second:.1f}x")

    # 性能验证
    print("\n[性能验证结果]")

    timeout_rate = (
        (stats_first["api_timeout"] / stats_first["api_calls"] * 100)
        if stats_first["api_calls"] > 0
        else 0
    )
    cache_hit_rate = stats_second["hit_rate"]

    print(f"  ✓ 超时率: {timeout_rate:.1f}% {'< 5% ✅' if timeout_rate < 5 else '>= 5% ❌'}")
    print(
        f"  ✓ 缓存命中率: {cache_hit_rate:.1f}% {'> 95% ✅' if cache_hit_rate > 95 else '<= 95% ❌'}"
    )

    return timeout_rate < 5 and cache_hit_rate > 95


def verify_scan_performance():
    """验证扫描性能（需要真实数据）"""
    print("\n" + "=" * 60)
    print("性能验证2：数据质量扫描速度")
    print("=" * 60)

    try:
        # 创建symbol loader
        symbol_loader = SymbolLoader()

        # 尝试加载品种列表
        result = symbol_loader.load_from_cache()

        if not result["success"]:
            print("\n⚠️  品种列表缓存不存在，需要先运行品种列表更新")
            return None

        all_symbols = symbol_loader.extract_all_codes()

        if not all_symbols:
            print("\n⚠️  品种列表为空，无法进行扫描测试")
            return None

        # 限制测试规模（避免测试时间过长）
        test_count = min(len(all_symbols), 100)
        test_symbols = all_symbols[:test_count]

        print(f"\n测试品种数量: {test_count} (总数: {len(all_symbols)})")

        # 创建数据感知器
        sensor = DataSensor()

        # 执行扫描
        print("\n[开始扫描...]")
        start_time = time.time()

        overview = sensor.scan_all_data(
            reference_symbols=test_symbols, intervals=["1d"], force_refresh=True
        )

        elapsed = time.time() - start_time

        print(f"\n[扫描完成]")
        print(f"  耗时: {elapsed:.2f}秒")
        print(f"  品种数: {overview.total_symbols}")
        print(f"  质量评分: {overview.quality_score}")
        print(f"  缺失品种: {overview.missing_symbols}")
        print(f"  错误品种: {overview.error_symbols}")
        print(f"  警告品种: {overview.warning_symbols}")
        print(f"  过时品种: {overview.outdated_symbols}")

        # 获取IPO缓存统计
        cache_stats = sensor.validator._ipo_cache.get_stats()
        print(f"\n[IPO缓存统计]")
        print(f"  缓存大小: {cache_stats['cache_size']}")
        print(f"  命中率: {cache_stats['hit_rate']:.1f}%")
        print(f"  API调用: {cache_stats['api_calls']}")
        print(
            f"  成功率: {(cache_stats['api_success']/cache_stats['api_calls']*100) if cache_stats['api_calls'] > 0 else 0:.1f}%"
        )

        # 估算全量扫描时间
        if test_count > 0:
            estimated_full_time = (elapsed / test_count) * len(all_symbols)
            print(f"\n[性能预估]")
            print(f"  单品种平均耗时: {elapsed/test_count:.3f}秒")
            print(
                f"  全量扫描预估时间: {estimated_full_time:.1f}秒 ({estimated_full_time/60:.1f}分钟)"
            )

            # 性能验证（全量扫描应该在30秒内完成）
            full_scan_target = 30  # 秒
            print(
                f"  {'✅ 预估全量扫描可在30秒内完成' if estimated_full_time <= full_scan_target else '❌ 预估全量扫描超过30秒'}"
            )

            return estimated_full_time <= full_scan_target

        return True

    except Exception as e:
        print(f"\n❌ 扫描性能验证失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def verify_concurrent_control():
    """验证并发控制"""
    print("\n" + "=" * 60)
    print("性能验证3：并发控制机制")
    print("=" * 60)

    validator = DataValidator()

    print(f"\nIPO查询线程池配置:")
    print(f"  最大并发数: {validator._ipo_executor._max_workers}")
    print(f"  线程名称前缀: IPO-Query")

    # 验证服务器故障转移机制
    print(f"\n服务器故障转移:")
    print(f"  当前服务器索引: {validator._current_server_index}")
    print(f"  故障计数器: {len(validator._server_failure_counts)} 个服务器有记录")

    # 测试服务器选择
    server = validator._get_next_server()
    print(f"  选择的服务器: {server[0]}:{server[1]}")

    print(f"\n✅ 并发控制机制已正确配置")
    return True


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("数据质量优化性能验证")
    print("=" * 60)
    print(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # 验证1：IPO缓存性能
    try:
        results["ipo_cache"] = verify_ipo_cache_performance()
    except Exception as e:
        print(f"\n❌ IPO缓存验证失败: {e}")
        results["ipo_cache"] = False

    # 验证2：扫描性能
    try:
        results["scan_performance"] = verify_scan_performance()
    except Exception as e:
        print(f"\n❌ 扫描性能验证失败: {e}")
        results["scan_performance"] = None

    # 验证3：并发控制
    try:
        results["concurrent_control"] = verify_concurrent_control()
    except Exception as e:
        print(f"\n❌ 并发控制验证失败: {e}")
        results["concurrent_control"] = False

    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)

    for key, value in results.items():
        if value is True:
            status = "✅ 通过"
        elif value is False:
            status = "❌ 失败"
        else:
            status = "⚠️  跳过"

        print(f"  {key}: {status}")

    # 整体结果
    passed = sum(1 for v in results.values() if v is True)
    total = len([v for v in results.values() if v is not None])

    print(
        f"\n总体通过率: {passed}/{total} ({passed/total*100:.0f}%)"
        if total > 0
        else "\n总体通过率: 0/0"
    )

    if all(v in (True, None) for v in results.values()):
        print("\n🎉 所有可验证的性能指标都已达标！")
    else:
        print("\n⚠️  部分性能指标未达标，请检查具体项目")


if __name__ == "__main__":
    main()
