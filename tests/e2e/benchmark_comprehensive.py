# -*- coding: utf-8 -*-
"""
综合基准测试 (Comprehensive Benchmark)

包含基础、高级和压力测试场景
"""

import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from benchmark_suite import BenchmarkConfig, BenchmarkRunner

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 测试场景 ====================


def test_small_dataset(iteration: int) -> dict:
    """小数据集测试（100个任务）"""
    task_count = 100
    for i in range(task_count):
        # 模拟轻量级计算
        _ = sum(range(1000))

    return {"task_count": task_count, "dataset_size": "small"}


def test_medium_dataset(iteration: int) -> dict:
    """中等数据集测试（1000个任务）"""
    task_count = 1000
    for i in range(task_count):
        _ = sum(range(1000))

    return {"task_count": task_count, "dataset_size": "medium"}


def test_large_dataset(iteration: int) -> dict:
    """大数据集测试（5000个任务）"""
    task_count = 5000
    for i in range(task_count):
        _ = sum(range(1000))

    return {"task_count": task_count, "dataset_size": "large"}


def test_stress(iteration: int) -> dict:
    """压力测试（10000个任务）"""
    task_count = 10000
    for i in range(task_count):
        _ = sum(range(500))

    return {"task_count": task_count, "dataset_size": "stress"}


# ==================== 主测试 ====================


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("LoadBalancer综合基准测试")
    logger.info("=" * 80)

    runner = BenchmarkRunner()

    # 注册测试
    runner.register(
        "small_dataset",
        BenchmarkConfig(
            name="小数据集",
            description="100个任务的基础性能测试",
            iterations=3,
            warmup_iterations=1,
        ),
        test_small_dataset,
    )

    runner.register(
        "medium_dataset",
        BenchmarkConfig(
            name="中等数据集",
            description="1000个任务的常规性能测试",
            iterations=3,
            warmup_iterations=1,
        ),
        test_medium_dataset,
    )

    runner.register(
        "large_dataset",
        BenchmarkConfig(
            name="大数据集",
            description="5000个任务的大规模性能测试",
            iterations=2,
            warmup_iterations=1,
        ),
        test_large_dataset,
    )

    runner.register(
        "stress_test",
        BenchmarkConfig(
            name="压力测试",
            description="10000个任务的极限压力测试",
            iterations=1,
            warmup_iterations=0,
        ),
        test_stress,
    )

    # 运行所有测试
    results = runner.run_all()

    # 生成报告
    report = runner.generate_report(results)

    # 保存报告
    report_path = Path(__file__).parent / "benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("\n📊 报告已保存到: %s", report_path)

    logger.info("\n" + "=" * 80)
    logger.info("✅ 所有测试完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
