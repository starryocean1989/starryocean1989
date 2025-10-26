# -*- coding: utf-8 -*-
"""
参数调优测试

测试内容：
1. 测试安全区间：60-70% vs 65-75% vs 70-80%
2. 测试步长：5%/10% vs 10%/15% vs 5%/15%
3. 测试批次基线：30/50/100 vs 50/100/150
4. 测试检查间隔：1.0s vs 1.5s vs 2.0s
5. 测试防抖间隔：2s vs 3s vs 5s
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.load_balancer import (
    ParameterSet,
    ParameterTuner,
    get_default_parameter_sets,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 模拟工作负载 ====================


def create_test_workload(param_set: ParameterSet) -> dict:
    """创建测试工作负载

    Args:
        param_set: 参数组合

    Returns:
        测试结果字典
    """
    import time
    import random

    # 模拟任务数量
    task_count = 100

    # 模拟执行时间（基于参数）
    base_time = 0.01  # 基础时间
    batch_factor = (param_set.batch_size_disk + param_set.batch_size_network) / 200
    interval_factor = param_set.check_interval / 1.5

    # 批次越大，效率越高（但有上限）
    batch_efficiency = min(1.5, batch_factor)

    # 检查间隔越短，调整越频繁，可能效率略低
    interval_efficiency = 1 / interval_factor if interval_factor > 0 else 1.0

    total_efficiency = batch_efficiency * interval_efficiency

    # 模拟执行
    for _ in range(task_count):
        time.sleep(base_time / total_efficiency)

    # 模拟动态调整次数（基于检查间隔和防抖间隔）
    expected_adjustments = int((task_count * base_time) / param_set.min_adjustment_interval)
    adjustment_count = max(0, expected_adjustments + random.randint(-2, 2))

    return {
        "task_count": task_count,
        "adjustment_count": adjustment_count,
    }


# ==================== 测试场景 ====================


def test_safe_zone_variants():
    """测试安全区间变体"""
    logger.info("\n" + "=" * 80)
    logger.info("测试场景1: 安全区间变体")
    logger.info("=" * 80)

    tuner = ParameterTuner()

    param_sets = [
        ParameterSet(
            name="安全区间 60-70%",
            safe_zone_lower=60.0,
            safe_zone_upper=70.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="安全区间 65-75%",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="安全区间 70-80%",
            safe_zone_lower=70.0,
            safe_zone_upper=80.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
    ]

    results = tuner.run_tuning(param_sets, create_test_workload, iterations=2)
    best = tuner.get_best_parameters(results)

    logger.info("\n最佳安全区间: %.0f-%.0f%%", best.safe_zone_lower, best.safe_zone_upper)


def test_step_variants():
    """测试步长变体"""
    logger.info("\n" + "=" * 80)
    logger.info("测试场景2: 步长变体")
    logger.info("=" * 80)

    tuner = ParameterTuner()

    param_sets = [
        ParameterSet(
            name="步长 5%/10%",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="步长 10%/15%",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.10,
            decrease_step=0.15,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="步长 5%/15%",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.15,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
    ]

    results = tuner.run_tuning(param_sets, create_test_workload, iterations=2)
    best = tuner.get_best_parameters(results)

    logger.info("\n最佳步长: +%.0f%% / -%.0f%%", best.increase_step * 100, best.decrease_step * 100)


def test_batch_size_variants():
    """测试批次基线变体"""
    logger.info("\n" + "=" * 80)
    logger.info("测试场景3: 批次基线变体")
    logger.info("=" * 80)

    tuner = ParameterTuner()

    param_sets = [
        ParameterSet(
            name="批次 30/50/100",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=30,
            batch_size_network=50,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="批次 50/100/150",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="批次 100/150/200",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=100,
            batch_size_network=150,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
    ]

    results = tuner.run_tuning(param_sets, create_test_workload, iterations=2)
    best = tuner.get_best_parameters(results)

    logger.info(
        "\n最佳批次基线: disk=%d, network=%d", best.batch_size_disk, best.batch_size_network
    )


def test_interval_variants():
    """测试间隔变体"""
    logger.info("\n" + "=" * 80)
    logger.info("测试场景4: 间隔变体")
    logger.info("=" * 80)

    tuner = ParameterTuner()

    param_sets = [
        ParameterSet(
            name="间隔 1.0s/2s",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.0,
            min_adjustment_interval=2.0,
        ),
        ParameterSet(
            name="间隔 1.5s/3s",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        ParameterSet(
            name="间隔 2.0s/5s",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=2.0,
            min_adjustment_interval=5.0,
        ),
    ]

    results = tuner.run_tuning(param_sets, create_test_workload, iterations=2)
    best = tuner.get_best_parameters(results)

    logger.info(
        "\n最佳间隔: check=%.1fs, adjustment=%.1fs",
        best.check_interval,
        best.min_adjustment_interval,
    )


def test_comprehensive():
    """综合测试：所有预定义参数组合"""
    logger.info("\n" + "=" * 80)
    logger.info("测试场景5: 综合对比")
    logger.info("=" * 80)

    tuner = ParameterTuner()
    param_sets = get_default_parameter_sets()

    results = tuner.run_tuning(param_sets, create_test_workload, iterations=3)
    best = tuner.get_best_parameters(results)

    # 生成报告
    report = tuner.generate_report(results)

    # 保存报告
    report_path = Path(__file__).parent / "parameter_tuning_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("\n📊 报告已保存到: %s", report_path)

    return best


# ==================== 主测试 ====================


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("LoadBalancer参数调优测试")
    logger.info("=" * 80)

    try:
        # 运行所有测试场景
        test_safe_zone_variants()
        test_step_variants()
        test_batch_size_variants()
        test_interval_variants()

        # 综合对比
        best_params = test_comprehensive()

        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有测试完成")
        logger.info("=" * 80)
        logger.info("\n建议使用最佳参数配置（已保存到报告）")

    except Exception as e:
        logger.error("测试失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
