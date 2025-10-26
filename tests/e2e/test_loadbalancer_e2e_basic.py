# -*- coding: utf-8 -*-
"""
LoadBalancer E2E测试 - 基础框架

测试实际任务执行并收集性能数据
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class PerformanceCollector:
    """性能数据收集器"""

    def __init__(self):
        self.test_results = []
        self.output_file = project_root / "tests" / "e2e" / "performance_data.json"

    def record_test(
        self,
        test_name: str,
        task_type: str,
        config: Dict[str, Any],
        duration: float,
        success: bool,
        resource_info: Dict[str, Any],
        adjustments: List[Dict[str, Any]] = None,
    ):
        """记录测试结果"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "task_type": task_type,
            "config": config,
            "duration_seconds": duration,
            "success": success,
            "resource_info": resource_info,
            "dynamic_adjustments": adjustments or [],
        }
        self.test_results.append(result)

        # 实时保存
        self.save_results()

    def save_results(self):
        """保存结果到JSON文件"""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            print(f"✅ 性能数据已保存到: {self.output_file}")
        except Exception as e:
            print(f"⚠️  保存性能数据失败: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self.test_results:
            return {}

        by_task_type = {}
        for result in self.test_results:
            task_type = result["task_type"]
            if task_type not in by_task_type:
                by_task_type[task_type] = []
            by_task_type[task_type].append(result["duration_seconds"])

        summary = {}
        for task_type, durations in by_task_type.items():
            summary[task_type] = {
                "count": len(durations),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
            }

        return summary


# 全局性能收集器
performance_collector = PerformanceCollector()


def test_data_quality_scan_basic():
    """测试1：数据质量扫描（基础配置）"""
    print("\n" + "=" * 70)
    print("E2E测试1：数据质量扫描（基础配置）")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            DataSensor,
        )
        from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
            SymbolLoader,
        )

        # 初始化
        sensor = DataSensor(event_engine=None)
        symbol_loader = SymbolLoader()

        # 获取测试品种列表（减小到30个以加快测试速度）
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:30]  # 使用30个品种快速测试

        print(f"测试品种数量: {len(test_symbols)}")

        # 记录开始时间和资源状态
        from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor

        monitor = ResourceMonitor(event_engine=None)

        initial_pressure = monitor.get_current_pressure()
        print(f"初始资源压力: {initial_pressure.score:.1f}% ({initial_pressure.bottleneck}瓶颈)")

        # 执行扫描
        start_time = time.time()

        overview = sensor.scan_all_data_adaptive(
            reference_symbols=test_symbols,
            intervals=["1d"],
            force_refresh=True,
            progress_callback=None,
        )

        duration = time.time() - start_time

        # 最终资源状态
        final_pressure = monitor.get_current_pressure()

        # 记录结果
        performance_collector.record_test(
            test_name="data_quality_scan_basic",
            task_type="data_quality_scan",
            config={
                "symbols_count": len(test_symbols),
                "intervals": ["1d"],
                "adaptive": True,
            },
            duration=duration,
            success=overview.quality_score >= 0,
            resource_info={
                "initial_pressure": initial_pressure.score,
                "initial_bottleneck": initial_pressure.bottleneck,
                "final_pressure": final_pressure.score,
                "final_bottleneck": final_pressure.bottleneck,
            },
        )

        # 输出结果
        print(f"\n扫描结果:")
        print(f"  - 耗时: {duration:.2f}秒")
        print(f"  - 总品种: {overview.total_symbols}")
        print(f"  - 缺失品种: {overview.missing_symbols}")
        print(f"  - 错误品种: {overview.error_symbols}")
        print(f"  - 警告品种: {overview.warning_symbols}")
        print(f"  - 资源压力变化: {initial_pressure.score:.1f}% → {final_pressure.score:.1f}%")

        print("\n✅ 数据质量扫描测试通过！")
        return True

    except Exception as e:
        print(f"\n❌ 数据质量扫描测试失败: {e}")
        import traceback

        traceback.print_exc()

        performance_collector.record_test(
            test_name="data_quality_scan_basic",
            task_type="data_quality_scan",
            config={"symbols_count": 100, "intervals": ["1d"]},
            duration=0,
            success=False,
            resource_info={},
        )
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("LoadBalancer E2E测试套件 - 基础版")
    print("=" * 70)

    tests = [
        ("数据质量扫描（基础）", test_data_quality_scan_basic),
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
        print(f"\n🎉 所有{total_count}个E2E测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total_count - success_count}/{total_count} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
