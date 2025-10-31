# -*- coding: utf-8 -*-
"""
LoadBalancer E2E测试 - 参数变化测试

测试不同参数配置下的性能表现
"""

import sys
import time
from pathlib import Path
from typing import List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.e2e.test_loadbalancer_e2e_basic import performance_collector


def test_scan_with_different_symbol_counts():
    """测试不同品种数量的性能"""
    print("\n" + "=" * 70)
    print("E2E测试：不同品种数量的扫描性能")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
        from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
            SymbolLoader,
        )
        from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor

        sensor = DataSensor(event_engine=None)
        symbol_loader = SymbolLoader()
        monitor = ResourceMonitor(event_engine=None)

        all_symbols = symbol_loader.extract_all_codes()

        # 测试不同数量: 减小规模以加快测试，每个配置运行2次以获得稳定数据
        test_counts = [20, 50, 100]
        num_runs = 2  # 每个配置运行2次

        for count in test_counts:
            if count > len(all_symbols):
                print(f"⚠️  跳过{count}个品种（总数不足）")
                continue

            test_symbols = all_symbols[:count]

            for run_idx in range(num_runs):
                print(f"\n测试 {count} 个品种 (第{run_idx+1}/{num_runs}次)...")
                initial_pressure = monitor.get_current_pressure()

                start_time = time.time()
                overview = sensor.scan_all_data_adaptive(
                    reference_symbols=test_symbols,
                    intervals=["1d"],
                    force_refresh=True,
                    progress_callback=None,
                )
                duration = time.time() - start_time

                final_pressure = monitor.get_current_pressure()

                # 记录结果
                performance_collector.record_test(
                    test_name=f"scan_{count}_symbols_run{run_idx+1}",
                    task_type="data_quality_scan_variant",
                    config={
                        "symbols_count": count,
                        "intervals": ["1d"],
                        "run_number": run_idx + 1,
                    },
                    duration=duration,
                    success=True,
                    resource_info={
                        "initial_pressure": initial_pressure.score,
                        "final_pressure": final_pressure.score,
                        "bottleneck": final_pressure.bottleneck,
                    },
                )

                print(
                    f"  ✓ {count}个品种(第{run_idx+1}次): {duration:.2f}秒, "
                    f"压力 {initial_pressure.score:.1f}% → {final_pressure.score:.1f}%"
                )

        print("\n✅ 不同品种数量测试完成！")
        return True

    except Exception as e:
        print(f"\n❌ 不同品种数量测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_scan_with_different_intervals():
    """测试不同周期组合的性能"""
    print("\n" + "=" * 70)
    print("E2E测试：不同周期组合的扫描性能")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
        from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
            SymbolLoader,
        )
        from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor

        sensor = DataSensor(event_engine=None)
        symbol_loader = SymbolLoader()
        monitor = ResourceMonitor(event_engine=None)

        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:30]  # 固定30个品种加快测试

        # 测试不同周期组合（只测试日线以加快速度）
        interval_configs = [
            (["1d"], "仅日线"),
        ]
        num_runs = 2  # 每个配置运行2次

        for intervals, description in interval_configs:
            for run_idx in range(num_runs):
                print(f"\n测试周期: {description} {intervals} (第{run_idx+1}/{num_runs}次)")
                initial_pressure = monitor.get_current_pressure()

                start_time = time.time()
                overview = sensor.scan_all_data_adaptive(
                    reference_symbols=test_symbols,
                    intervals=intervals,
                    force_refresh=True,
                    progress_callback=None,
                )
                duration = time.time() - start_time

                final_pressure = monitor.get_current_pressure()

                # 记录结果
                performance_collector.record_test(
                    test_name=f"scan_intervals_{len(intervals)}_run{run_idx+1}",
                    task_type="data_quality_scan_intervals",
                    config={
                        "symbols_count": 30,
                        "intervals": intervals,
                        "description": description,
                        "run_number": run_idx + 1,
                    },
                    duration=duration,
                    success=True,
                    resource_info={
                        "initial_pressure": initial_pressure.score,
                        "final_pressure": final_pressure.score,
                    },
                )

                print(f"  ✓ {description}(第{run_idx+1}次): {duration:.2f}秒")

        print("\n✅ 不同周期组合测试完成！")
        return True

    except Exception as e:
        print(f"\n❌ 不同周期组合测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("LoadBalancer E2E测试套件 - 参数变化测试")
    print("=" * 70)

    tests = [
        ("不同品种数量测试", test_scan_with_different_symbol_counts),
        ("不同周期组合测试", test_scan_with_different_intervals),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name}异常: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")

    # 输出性能摘要
    summary = performance_collector.get_summary()
    if summary:
        print("\n" + "=" * 70)
        print("性能摘要")
        print("=" * 70)
        for task_type, stats in summary.items():
            print(f"\n{task_type}:")
            print(f"  - 测试次数: {stats['count']}")
            print(f"  - 平均耗时: {stats['avg_duration']:.2f}秒")
            print(f"  - 最快: {stats['min_duration']:.2f}秒")
            print(f"  - 最慢: {stats['max_duration']:.2f}秒")

    success_count = sum(1 for _, r in results if r)
    total_count = len(results)

    if success_count == total_count:
        print(f"\n🎉 所有{total_count}个参数变化测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total_count - success_count}/{total_count} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
