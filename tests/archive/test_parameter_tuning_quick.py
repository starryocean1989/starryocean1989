# -*- coding: utf-8 -*-
"""
参数调优快速测试 (快速版本，用于验证功能)

简化版本：
- 减少任务数量
- 减少迭代次数
- 只测试综合场景
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


def create_quick_test_workload(param_set: ParameterSet) -> dict:
    """创建快速测试工作负载（减少规模）

    Args:
        param_set: 参数组合

    Returns:
        测试结果字典
    """
    import time
    import random

    # 减少任务数量到10个
    task_count = 10

    # 模拟执行时间（基于参数）
    base_time = 0.001  # 减少基础时间到1ms
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

    # 模拟动态调整次数
    expected_adjustments = int((task_count * base_time) / param_set.min_adjustment_interval)
    adjustment_count = max(0, expected_adjustments + random.randint(-1, 1))

    return {
        "task_count": task_count,
        "adjustment_count": adjustment_count,
    }


# ==================== 主测试 ====================


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("LoadBalancer参数调优快速测试")
    logger.info("=" * 80)

    try:
        tuner = ParameterTuner()
        param_sets = get_default_parameter_sets()

        # 只运行1次迭代
        logger.info("\n测试%d个参数组合（每个1次迭代）...", len(param_sets))
        results = tuner.run_tuning(param_sets, create_quick_test_workload, iterations=1)

        # 获取最佳参数
        best = tuner.get_best_parameters(results)

        # 生成报告
        report = tuner.generate_report(results)

        # 保存报告
        report_path = Path(__file__).parent / "parameter_tuning_report_quick.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info("\n📊 报告已保存到: %s", report_path)

        logger.info("\n" + "=" * 80)
        logger.info("✅ 快速测试完成")
        logger.info("=" * 80)
        logger.info("\n最佳参数组合: %s", best.name)
        logger.info("建议使用最佳参数配置（已保存到报告）")

    except Exception as e:
        logger.error("测试失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
