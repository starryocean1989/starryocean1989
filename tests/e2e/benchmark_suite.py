# -*- coding: utf-8 -*-
"""
性能基准测试套件 (Benchmark Suite)

统一的基准测试运行器，支持：
- 标准化测试场景（50/500/2000品种）
- 性能指标采集（时间、内存、CPU、吞吐量）
- 性能基线建立和对比
- 结果对比和可视化
"""

import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入性能监控模块
try:
    from tests.performance_monitoring import PerformanceMonitor, TestRecord

    PERFORMANCE_MONITOR_AVAILABLE = True
except ImportError:
    PERFORMANCE_MONITOR_AVAILABLE = False
    logging.warning("性能监控模块不可用，将跳过基线功能")


# ==================== 数据类 ====================


@dataclass
class BenchmarkConfig:
    """基准测试配置"""

    name: str  # 测试名称
    description: str  # 测试描述
    iterations: int = 3  # 迭代次数
    warmup_iterations: int = 1  # 预热迭代次数


@dataclass
class BenchmarkMetrics:
    """基准测试指标"""

    name: str  # 测试名称
    execution_time: float  # 执行时间（秒）
    memory_used_mb: float  # 内存使用（MB）
    cpu_usage_percent: float  # CPU使用率（%）
    throughput: float  # 吞吐量（任务/秒）
    custom_metrics: Dict[str, Any] = field(default_factory=dict)  # 自定义指标


@dataclass
class BenchmarkResult:
    """基准测试结果"""

    config: BenchmarkConfig
    metrics: BenchmarkMetrics
    iterations_data: List[Dict[str, Any]]  # 每次迭代的详细数据


# ==================== 基准测试运行器 ====================


class BenchmarkRunner:
    """基准测试运行器

    使用示例：
        runner = BenchmarkRunner()

        # 注册测试
        runner.register("test_name", config, test_function)

        # 运行所有测试
        results = runner.run_all()

        # 生成报告
        report = runner.generate_report(results)
    """

    def __init__(self):
        """初始化基准测试运行器"""
        self.logger = logging.getLogger(__name__)
        self.tests: Dict[str, tuple] = {}  # name -> (config, function)

    def register(
        self,
        name: str,
        config: BenchmarkConfig,
        test_function: Callable[[int], Dict[str, Any]],
    ):
        """注册测试

        Args:
            name: 测试名称
            config: 测试配置
            test_function: 测试函数，参数为迭代编号，返回自定义指标
        """
        self.tests[name] = (config, test_function)
        self.logger.info("注册测试: %s", name)

    def run_all(self) -> List[BenchmarkResult]:
        """运行所有测试

        Returns:
            测试结果列表
        """
        self.logger.info("=" * 80)
        self.logger.info("开始运行%d个基准测试", len(self.tests))
        self.logger.info("=" * 80)

        results = []
        for name, (config, test_function) in self.tests.items():
            result = self.run_single(name, config, test_function)
            results.append(result)

        self.logger.info("\n" + "=" * 80)
        self.logger.info("所有基准测试完成")
        self.logger.info("=" * 80)

        return results

    def run_single(
        self,
        name: str,
        config: BenchmarkConfig,
        test_function: Callable[[int], Dict[str, Any]],
    ) -> BenchmarkResult:
        """运行单个测试

        Args:
            name: 测试名称
            config: 测试配置
            test_function: 测试函数

        Returns:
            测试结果
        """
        self.logger.info("\n" + "-" * 80)
        self.logger.info("测试: %s", config.name)
        self.logger.info("描述: %s", config.description)
        self.logger.info("-" * 80)

        # 预热
        if config.warmup_iterations > 0:
            self.logger.info("预热中 (%d次)...", config.warmup_iterations)
            for i in range(config.warmup_iterations):
                try:
                    test_function(i)
                except Exception as e:
                    self.logger.warning("预热迭代%d失败: %s", i, e)

        # 正式测试
        iterations_data = []
        for i in range(config.iterations):
            self.logger.info("迭代 %d/%d...", i + 1, config.iterations)

            # 记录起始状态
            start_time = time.time()
            process = psutil.Process()
            start_memory = process.memory_info().rss / 1024 / 1024  # MB
            start_cpu = psutil.cpu_percent(interval=0.1)

            # 运行测试
            try:
                custom_metrics = test_function(i)
            except Exception as e:
                self.logger.error("迭代%d失败: %s", i, e, exc_info=True)
                custom_metrics = {"error": str(e)}

            # 记录结束状态
            end_time = time.time()
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            end_cpu = psutil.cpu_percent(interval=0.1)

            # 计算指标
            execution_time = end_time - start_time
            memory_used = end_memory - start_memory
            cpu_usage = (start_cpu + end_cpu) / 2
            throughput = (
                custom_metrics.get("task_count", 0) / execution_time if execution_time > 0 else 0
            )

            iteration_data = {
                "execution_time": execution_time,
                "memory_used_mb": memory_used,
                "cpu_usage_percent": cpu_usage,
                "throughput": throughput,
                "custom_metrics": custom_metrics,
            }
            iterations_data.append(iteration_data)

            self.logger.info(
                "  时间: %.2fs, 内存: %.2fMB, CPU: %.1f%%, 吞吐: %.2f任务/秒",
                execution_time,
                memory_used,
                cpu_usage,
                throughput,
            )

        # 计算平均指标
        avg_time = sum(d["execution_time"] for d in iterations_data) / len(iterations_data)
        avg_memory = sum(d["memory_used_mb"] for d in iterations_data) / len(iterations_data)
        avg_cpu = sum(d["cpu_usage_percent"] for d in iterations_data) / len(iterations_data)
        avg_throughput = sum(d["throughput"] for d in iterations_data) / len(iterations_data)

        # 聚合自定义指标
        aggregated_custom = {}
        if iterations_data:
            custom_keys = set()
            for d in iterations_data:
                custom_keys.update(d["custom_metrics"].keys())

            for key in custom_keys:
                values = [d["custom_metrics"].get(key, 0) for d in iterations_data]
                if all(isinstance(v, (int, float)) for v in values):
                    aggregated_custom[key] = sum(values) / len(values)
                else:
                    aggregated_custom[key] = values[0]  # 取第一个

        metrics = BenchmarkMetrics(
            name=name,
            execution_time=avg_time,
            memory_used_mb=avg_memory,
            cpu_usage_percent=avg_cpu,
            throughput=avg_throughput,
            custom_metrics=aggregated_custom,
        )

        result = BenchmarkResult(config=config, metrics=metrics, iterations_data=iterations_data)

        self.logger.info(
            "\n平均指标: 时间=%.2fs, 内存=%.2fMB, CPU=%.1f%%, 吞吐=%.2f任务/秒",
            avg_time,
            avg_memory,
            avg_cpu,
            avg_throughput,
        )

        return result

    def generate_report(self, results: List[BenchmarkResult]) -> str:
        """生成基准测试报告

        Args:
            results: 测试结果列表

        Returns:
            Markdown格式的报告
        """
        report = ["# 性能基准测试报告\n\n"]
        report.append(f"测试日期: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # 概览表
        report.append("## 测试概览\n\n")
        report.append("| 测试名称 | 执行时间 | 内存使用 | CPU使用 | 吞吐量 |\n")
        report.append("|---------|---------|---------|---------|--------|\n")

        for result in results:
            m = result.metrics
            report.append(
                f"| {m.name} | {m.execution_time:.2f}s | {m.memory_used_mb:.2f}MB | "
                f"{m.cpu_usage_percent:.1f}% | {m.throughput:.2f} |\n"
            )

        # 详细结果
        report.append("\n## 详细结果\n\n")
        for result in results:
            report.append(f"### {result.config.name}\n\n")
            report.append(f"{result.config.description}\n\n")

            report.append("**平均指标：**\n\n")
            report.append(f"- 执行时间: {result.metrics.execution_time:.2f}秒\n")
            report.append(f"- 内存使用: {result.metrics.memory_used_mb:.2f}MB\n")
            report.append(f"- CPU使用率: {result.metrics.cpu_usage_percent:.1f}%\n")
            report.append(f"- 吞吐量: {result.metrics.throughput:.2f}任务/秒\n\n")

            if result.metrics.custom_metrics:
                report.append("**自定义指标：**\n\n")
                for key, value in result.metrics.custom_metrics.items():
                    if isinstance(value, float):
                        report.append(f"- {key}: {value:.2f}\n")
                    else:
                        report.append(f"- {key}: {value}\n")
                report.append("\n")

        return "".join(report)


# ==================== 标准化测试场景 ====================


class StandardBenchmarks:
    """标准化基准测试场景

    提供三种标准测试场景：
    - 小规模（50品种）：快速验证，适用于CI/CD
    - 中规模（500品种）：日常性能测试
    - 大规模（2000品种）：完整压力测试
    """

    def __init__(self, project_root: Optional[Path] = None):
        """初始化标准测试场景"""
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent

        self.project_root = project_root
        self.logger = logging.getLogger(__name__)

        # 尝试加载性能监控模块
        self.performance_monitor = None
        if PERFORMANCE_MONITOR_AVAILABLE:
            try:
                self.performance_monitor = PerformanceMonitor()
                self.logger.info("✅ 性能监控模块已加载")
            except Exception as e:
                self.logger.warning(f"性能监控模块加载失败: {e}")

    def run_50_symbols_test(self, with_baseline: bool = True) -> Dict[str, Any]:
        """运行50品种快速测试

        Args:
            with_baseline: 是否与基线对比

        Returns:
            测试结果字典
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("开始50品种快速测试")
        self.logger.info("=" * 80)

        # 这里应该调用实际的LoadBalancer测试
        # 简化示例：模拟测试
        start_time = time.time()

        # TODO: 实际测试逻辑
        # from backend.infrastructure.data_module_vnpy.load_balancer import LoadBalancer
        # balancer = LoadBalancer(event_engine)
        # result = balancer.execute_batch(symbols[:50])

        # 模拟测试
        time.sleep(0.5)  # 模拟执行时间

        execution_time = time.time() - start_time

        result = {
            "test_type": "50_symbols",
            "execution_time": execution_time,
            "throughput": 50 / execution_time if execution_time > 0 else 0,
            "success_rate": 100.0,
            "cpu_avg": 45.0,
            "memory_avg": 250.0,
        }

        # 记录到性能监控系统
        if self.performance_monitor and PERFORMANCE_MONITOR_AVAILABLE:
            test_record = TestRecord(
                test_id=f"50_symbols_{int(time.time())}",
                test_date=time.strftime("%Y-%m-%d %H:%M:%S"),
                test_type="50_symbols",
                config={"symbol_count": 50},
                duration=execution_time,
                cpu_avg=result["cpu_avg"],
                memory_avg=result["memory_avg"],
                throughput=result["throughput"],
                score=self._calculate_score(result),
                notes="50品种快速测试",
            )

            try:
                self.performance_monitor.record_test_result(test_record)
                self.logger.info("✅ 测试结果已记录到性能监控系统")

                # 对比基线
                if with_baseline:
                    comparison = self.performance_monitor.compare_with_baseline(test_record)
                    result["baseline_comparison"] = comparison
                    self.logger.info(f"基线对比: {comparison.get('message', 'N/A')}")

            except Exception as e:
                self.logger.warning(f"记录测试结果失败: {e}")

        self.logger.info(
            f"\n✅ 50品种测试完成: 耗时={execution_time:.2f}s, 吞吐={result['throughput']:.1f}品种/秒"
        )
        return result

    def run_500_symbols_test(self, with_baseline: bool = True) -> Dict[str, Any]:
        """运行500品种中等测试

        Args:
            with_baseline: 是否与基线对比

        Returns:
            测试结果字典
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("开始500品种中等测试")
        self.logger.info("=" * 80)

        start_time = time.time()

        # TODO: 实际测试逻辑
        time.sleep(2.0)  # 模拟执行时间

        execution_time = time.time() - start_time

        result = {
            "test_type": "500_symbols",
            "execution_time": execution_time,
            "throughput": 500 / execution_time if execution_time > 0 else 0,
            "success_rate": 99.5,
            "cpu_avg": 65.0,
            "memory_avg": 450.0,
        }

        # 记录到性能监控系统
        if self.performance_monitor and PERFORMANCE_MONITOR_AVAILABLE:
            test_record = TestRecord(
                test_id=f"500_symbols_{int(time.time())}",
                test_date=time.strftime("%Y-%m-%d %H:%M:%S"),
                test_type="500_symbols",
                config={"symbol_count": 500},
                duration=execution_time,
                cpu_avg=result["cpu_avg"],
                memory_avg=result["memory_avg"],
                throughput=result["throughput"],
                score=self._calculate_score(result),
                notes="500品种中等测试",
            )

            try:
                self.performance_monitor.record_test_result(test_record)

                if with_baseline:
                    comparison = self.performance_monitor.compare_with_baseline(test_record)
                    result["baseline_comparison"] = comparison
                    self.logger.info(f"基线对比: {comparison.get('message', 'N/A')}")

            except Exception as e:
                self.logger.warning(f"记录测试结果失败: {e}")

        self.logger.info(
            f"\n✅ 500品种测试完成: 耗时={execution_time:.2f}s, 吞吐={result['throughput']:.1f}品种/秒"
        )
        return result

    def run_2000_symbols_test(self, with_baseline: bool = True) -> Dict[str, Any]:
        """运行2000品种大规模测试

        Args:
            with_baseline: 是否与基线对比

        Returns:
            测试结果字典
        """
        self.logger.info("\n" + "=" * 80)
        self.logger.info("开始2000品种大规模测试")
        self.logger.info("=" * 80)

        start_time = time.time()

        # TODO: 实际测试逻辑
        time.sleep(5.0)  # 模拟执行时间

        execution_time = time.time() - start_time

        result = {
            "test_type": "2000_symbols",
            "execution_time": execution_time,
            "throughput": 2000 / execution_time if execution_time > 0 else 0,
            "success_rate": 99.0,
            "cpu_avg": 80.0,
            "memory_avg": 800.0,
        }

        # 记录到性能监控系统
        if self.performance_monitor and PERFORMANCE_MONITOR_AVAILABLE:
            test_record = TestRecord(
                test_id=f"2000_symbols_{int(time.time())}",
                test_date=time.strftime("%Y-%m-%d %H:%M:%S"),
                test_type="2000_symbols",
                config={"symbol_count": 2000},
                duration=execution_time,
                cpu_avg=result["cpu_avg"],
                memory_avg=result["memory_avg"],
                throughput=result["throughput"],
                score=self._calculate_score(result),
                notes="2000品种大规模测试",
            )

            try:
                self.performance_monitor.record_test_result(test_record)

                if with_baseline:
                    comparison = self.performance_monitor.compare_with_baseline(test_record)
                    result["baseline_comparison"] = comparison
                    self.logger.info(f"基线对比: {comparison.get('message', 'N/A')}")

            except Exception as e:
                self.logger.warning(f"记录测试结果失败: {e}")

        self.logger.info(
            f"\n✅ 2000品种测试完成: 耗时={execution_time:.2f}s, 吞吐={result['throughput']:.1f}品种/秒"
        )
        return result

    def run_all_standard_tests(self, with_baseline: bool = True) -> Dict[str, Any]:
        """运行所有标准测试

        Args:
            with_baseline: 是否与基线对比

        Returns:
            所有测试结果
        """
        self.logger.info("\n" + "=" * 100)
        self.logger.info("开始运行所有标准化基准测试")
        self.logger.info("=" * 100)

        results = {
            "50_symbols": self.run_50_symbols_test(with_baseline),
            "500_symbols": self.run_500_symbols_test(with_baseline),
            "2000_symbols": self.run_2000_symbols_test(with_baseline),
        }

        self.logger.info("\n" + "=" * 100)
        self.logger.info("所有标准化基准测试完成")
        self.logger.info("=" * 100)

        return results

    def establish_baselines(self, runs_per_test: int = 10):
        """建立性能基线

        Args:
            runs_per_test: 每种测试运行次数
        """
        if not self.performance_monitor or not PERFORMANCE_MONITOR_AVAILABLE:
            self.logger.error("性能监控模块不可用，无法建立基线")
            return

        self.logger.info(f"\n开始建立性能基线（每个测试运行{runs_per_test}次）...")

        for test_type in ["50_symbols", "500_symbols", "2000_symbols"]:
            self.logger.info(f"\n建立 {test_type} 基线...")

            for i in range(runs_per_test):
                self.logger.info(f"  运行 {i + 1}/{runs_per_test}...")

                if test_type == "50_symbols":
                    self.run_50_symbols_test(with_baseline=False)
                elif test_type == "500_symbols":
                    self.run_500_symbols_test(with_baseline=False)
                elif test_type == "2000_symbols":
                    self.run_2000_symbols_test(with_baseline=False)

                # 间隔一下，让系统稳定
                time.sleep(2)

            # 建立基线
            try:
                baseline = self.performance_monitor.establish_baseline(
                    test_type, sample_count=runs_per_test
                )
                self.logger.info(
                    f"✅ {test_type} 基线已建立: 耗时={baseline.avg_duration:.2f}s, 得分={baseline.avg_score:.2f}"
                )
            except Exception as e:
                self.logger.error(f"建立 {test_type} 基线失败: {e}")

        self.logger.info("\n✅ 所有基线建立完成")

    def _calculate_score(self, result: Dict[str, Any]) -> float:
        """计算综合得分

        Args:
            result: 测试结果

        Returns:
            综合得分（0-100）
        """
        # 简单的得分模型：基于执行时间、成功率、资源使用
        time_score = min(100, (10 / result["execution_time"]) * 100) * 0.4
        success_score = result["success_rate"] * 0.3
        cpu_score = (100 - result["cpu_avg"]) * 0.15
        memory_score = max(0, 100 - result["memory_avg"] / 10) * 0.15

        return time_score + success_score + cpu_score + memory_score


# ==================== 便捷函数 ====================


def create_benchmark_runner() -> BenchmarkRunner:
    """便捷函数：创建基准测试运行器

    Returns:
        BenchmarkRunner实例
    """
    return BenchmarkRunner()


def create_standard_benchmarks(project_root: Optional[Path] = None) -> StandardBenchmarks:
    """便捷函数：创建标准化基准测试

    Args:
        project_root: 项目根目录

    Returns:
        StandardBenchmarks实例
    """
    return StandardBenchmarks(project_root)


# ==================== 主程序示例 ====================


def main():
    """主程序：运行标准化基准测试"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 创建标准测试
    benchmarks = create_standard_benchmarks()

    # 运行所有标准测试
    results = benchmarks.run_all_standard_tests(with_baseline=True)

    # 打印摘要
    print("\n" + "=" * 80)
    print("测试摘要")
    print("=" * 80)
    for test_type, result in results.items():
        print(f"\n{test_type}:")
        print(f"  耗时: {result['execution_time']:.2f}秒")
        print(f"  吞吐量: {result['throughput']:.1f} 品种/秒")
        print(f"  成功率: {result['success_rate']:.1f}%")

        if "baseline_comparison" in result:
            comp = result["baseline_comparison"]
            if comp.get("has_baseline"):
                print(f"  基线对比: {comp['message']}")


if __name__ == "__main__":
    main()
