# -*- coding: utf-8 -*-
"""
性能数据分析和优化建议生成器

分析E2E测试收集的性能数据，生成优化建议
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.data = self.load_data()

    def load_data(self) -> List[Dict[str, Any]]:
        """加载性能数据"""
        if not self.data_file.exists():
            print(f"⚠️  性能数据文件不存在: {self.data_file}")
            return []

        with open(self.data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def analyze_by_task_type(self) -> Dict[str, Dict[str, Any]]:
        """按任务类型分析"""
        by_type = defaultdict(list)

        for result in self.data:
            task_type = result.get("task_type", "unknown")
            by_type[task_type].append(result)

        analysis = {}
        for task_type, results in by_type.items():
            durations = [r["duration_seconds"] for r in results if r["success"]]

            if not durations:
                continue

            analysis[task_type] = {
                "count": len(results),
                "success_count": sum(1 for r in results if r["success"]),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "samples": results,
            }

        return analysis

    def analyze_symbol_count_scaling(self) -> Dict[str, Any]:
        """分析品种数量扩展性"""
        # 筛选数据质量扫描任务
        scan_results = [r for r in self.data if "scan" in r.get("task_type", "") and r["success"]]

        if not scan_results:
            return {}

        # 按品种数量分组
        by_count = defaultdict(list)
        for result in scan_results:
            count = result["config"].get("symbols_count", 0)
            duration = result["duration_seconds"]
            by_count[count].append(duration)

        # 计算每个品种数量的平均耗时
        scaling_data = {}
        for count, durations in sorted(by_count.items()):
            avg_duration = sum(durations) / len(durations)
            per_symbol = avg_duration / count if count > 0 else 0

            scaling_data[count] = {
                "avg_duration": avg_duration,
                "per_symbol_time": per_symbol,
                "samples": len(durations),
            }

        return scaling_data

    def analyze_bottlenecks(self) -> Dict[str, Any]:
        """分析资源瓶颈分布"""
        bottleneck_counts = defaultdict(int)
        pressure_levels = []

        for result in self.data:
            resource_info = result.get("resource_info", {})

            bottleneck = resource_info.get("bottleneck") or resource_info.get("final_bottleneck")
            if bottleneck:
                bottleneck_counts[bottleneck] += 1

            final_pressure = resource_info.get("final_pressure")
            if final_pressure is not None:
                pressure_levels.append(final_pressure)

        return {
            "bottleneck_distribution": dict(bottleneck_counts),
            "avg_pressure": sum(pressure_levels) / len(pressure_levels) if pressure_levels else 0,
            "max_pressure": max(pressure_levels) if pressure_levels else 0,
            "min_pressure": min(pressure_levels) if pressure_levels else 0,
        }

    def generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []

        # 分析任务类型
        by_type = self.analyze_by_task_type()

        # 分析扩展性
        scaling = self.analyze_symbol_count_scaling()

        # 分析瓶颈
        bottlenecks = self.analyze_bottlenecks()

        # 建议1：基于扩展性
        if scaling:
            counts = sorted(scaling.keys())
            if len(counts) >= 2:
                small_count = counts[0]
                large_count = counts[-1]

                small_per_symbol = scaling[small_count]["per_symbol_time"]
                large_per_symbol = scaling[large_count]["per_symbol_time"]

                if large_per_symbol > small_per_symbol * 1.5:
                    recommendations.append(
                        f"⚠️  扩展性问题：大数据集({large_count}品种)的单品种耗时"
                        f"({large_per_symbol:.4f}秒)比小数据集({small_count}品种)"
                        f"({small_per_symbol:.4f}秒)高50%以上。"
                        f"建议：增加批处理大小或优化缓存策略。"
                    )
                else:
                    recommendations.append(
                        f"✅ 扩展性良好：单品种耗时保持稳定"
                        f"(小数据集{small_per_symbol:.4f}秒 vs "
                        f"大数据集{large_per_symbol:.4f}秒)"
                    )

        # 建议2：基于瓶颈分布
        if bottlenecks.get("bottleneck_distribution"):
            most_common = max(bottlenecks["bottleneck_distribution"].items(), key=lambda x: x[1])
            bottleneck_type, count = most_common

            if bottleneck_type == "disk":
                recommendations.append(
                    f"⚠️  磁盘瓶颈频繁({count}次)。"
                    f"建议：增大批处理大小，减少磁盘IO次数；"
                    f"或考虑使用SSD加速。"
                )
            elif bottleneck_type == "memory":
                recommendations.append(
                    f"⚠️  内存瓶颈频繁({count}次)。"
                    f"建议：减小批处理大小，降低并发线程数；"
                    f"或增加系统内存。"
                )
            elif bottleneck_type == "cpu":
                recommendations.append(
                    f"⚠️  CPU瓶颈频繁({count}次)。"
                    f"建议：降低并发线程数到CPU核心数以下；"
                    f"或优化计算密集型代码。"
                )

        # 建议3：基于平均压力
        avg_pressure = bottlenecks.get("avg_pressure", 0)
        if avg_pressure > 70:
            recommendations.append(
                f"⚠️  平均资源压力过高({avg_pressure:.1f}%)。"
                f"建议：降低初始并发配置，让动态调整有更多空间。"
            )
        elif avg_pressure < 35:
            recommendations.append(
                f"✅ 资源利用率偏低({avg_pressure:.1f}%)，可以提升。"
                f"建议：增加初始并发配置，充分利用系统资源。"
            )

        # 建议4：基于任务成功率
        for task_type, stats in by_type.items():
            success_rate = stats["success_count"] / stats["count"] if stats["count"] > 0 else 0
            if success_rate < 0.95:
                recommendations.append(
                    f"⚠️  {task_type}任务成功率偏低({success_rate*100:.1f}%)。"
                    f"建议：检查错误日志，优化错误处理逻辑。"
                )

        return recommendations

    def print_report(self):
        """打印分析报告"""
        print("\n" + "=" * 70)
        print("性能分析报告")
        print("=" * 70)

        # 1. 任务类型分析
        print("\n【1. 任务类型分析】")
        by_type = self.analyze_by_task_type()
        for task_type, stats in by_type.items():
            print(f"\n{task_type}:")
            print(f"  - 测试次数: {stats['count']}")
            print(f"  - 成功次数: {stats['success_count']}")
            print(f"  - 成功率: {stats['success_count']/stats['count']*100:.1f}%")
            print(f"  - 平均耗时: {stats['avg_duration']:.2f}秒")
            print(f"  - 耗时范围: {stats['min_duration']:.2f}秒 ~ {stats['max_duration']:.2f}秒")

        # 2. 扩展性分析
        print("\n【2. 品种数量扩展性分析】")
        scaling = self.analyze_symbol_count_scaling()
        if scaling:
            print("\n品种数量 | 平均耗时 | 单品种耗时 | 样本数")
            print("-" * 60)
            for count, data in sorted(scaling.items()):
                print(
                    f"{count:8d} | {data['avg_duration']:8.2f}秒 | "
                    f"{data['per_symbol_time']:11.4f}秒 | {data['samples']:6d}"
                )
        else:
            print("  暂无扩展性数据")

        # 3. 资源瓶颈分析
        print("\n【3. 资源瓶颈分析】")
        bottlenecks = self.analyze_bottlenecks()
        if bottlenecks.get("bottleneck_distribution"):
            print("\n瓶颈类型分布:")
            for bottleneck, count in bottlenecks["bottleneck_distribution"].items():
                print(f"  - {bottleneck}: {count}次")

            print(f"\n资源压力统计:")
            print(f"  - 平均压力: {bottlenecks['avg_pressure']:.1f}%")
            print(f"  - 最高压力: {bottlenecks['max_pressure']:.1f}%")
            print(f"  - 最低压力: {bottlenecks['min_pressure']:.1f}%")
        else:
            print("  暂无瓶颈数据")

        # 4. 优化建议
        print("\n【4. 优化建议】")
        recommendations = self.generate_recommendations()
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"\n{i}. {rec}")
        else:
            print("  暂无优化建议")

        print("\n" + "=" * 70)


def main():
    """主函数"""
    data_file = project_root / "tests" / "e2e" / "performance_data.json"

    print(f"正在加载性能数据: {data_file}")

    analyzer = PerformanceAnalyzer(data_file)

    if not analyzer.data:
        print("\n⚠️  没有可分析的性能数据")
        print("请先运行E2E测试:")
        print("  python tests/e2e/test_loadbalancer_e2e_basic.py")
        print("  python tests/e2e/test_loadbalancer_e2e_variants.py")
        return 1

    print(f"已加载 {len(analyzer.data)} 条测试记录\n")

    analyzer.print_report()

    return 0


if __name__ == "__main__":
    exit(main())
