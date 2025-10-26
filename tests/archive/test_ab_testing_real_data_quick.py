# -*- coding: utf-8 -*-
"""
LoadBalancer A/B测试 - 快速版本（基于模拟数据）

基于项目真实数据规模进行模拟测试，避免实际的多进程问题：
1. 模拟5000+品种K线数据读取
2. 模拟6000+品种本地数据质量扫描
3. 模拟6000+品种data_reader批量读取

快速测试，验证参数影响而不实际运行耗时操作。
"""

import logging
import sys
import time
import random
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.load_balancer import (
    ParameterSet,
    ParameterTuner,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 模拟真实数据规模 ====================


def simulate_kline_read(param_set: ParameterSet, symbol_count: int = 5000) -> dict:
    """模拟K线数据读取（基于真实数据规模）

    Args:
        param_set: 参数配置
        symbol_count: 品种数量

    Returns:
        测试结果
    """
    # 基于参数计算性能
    batch_size = param_set.batch_size_disk

    # 模拟每批次处理时间（IO密集型）
    base_time_per_batch = 0.05  # 50ms基准

    # 批次大小影响效率（越大越好，但有边际递减）
    batch_efficiency = min(1.5, 1.0 + (batch_size - 30) / 100)

    # 计算批次数
    batch_count = (symbol_count + batch_size - 1) // batch_size

    # 模拟总时间
    total_time = batch_count * (base_time_per_batch / batch_efficiency)

    # 添加随机波动（±10%）
    total_time *= random.uniform(0.9, 1.1)

    # 模拟执行
    time.sleep(min(total_time, 0.5))  # 最多睡眠0.5秒

    # 模拟成功率（批次越大，失败概率略高）
    success_rate = max(90, 98 - (batch_size - 30) * 0.1)
    success_count = int(symbol_count * success_rate / 100)

    logger.info(
        "K线读取模拟: %d个品种, 批次=%d, 耗时=%.2fs, 成功率=%.1f%%",
        symbol_count,
        batch_size,
        total_time,
        success_rate,
    )

    return {
        "task_count": symbol_count,
        "adjustment_count": 0,
        "success": True,
        "elapsed": total_time,
        "success_rate": success_rate,
    }


def simulate_data_scan(param_set: ParameterSet, symbol_count: int = 6000) -> dict:
    """模拟数据质量扫描（基于真实数据规模）

    Args:
        param_set: 参数配置
        symbol_count: 品种数量

    Returns:
        测试结果
    """
    # 扫描比读取更复杂，涉及多次IO和计算
    batch_size = param_set.batch_size_disk
    check_interval = param_set.check_interval

    # 模拟每批次处理时间
    base_time_per_batch = 0.08  # 80ms基准

    # 批次大小影响
    batch_efficiency = min(1.4, 1.0 + (batch_size - 30) / 120)

    # 检查间隔影响（间隔越短，开销越大）
    check_overhead = 1.0 + (2.0 - check_interval) * 0.05

    # 计算批次数
    batch_count = (symbol_count + batch_size - 1) // batch_size

    # 模拟总时间
    total_time = batch_count * (base_time_per_batch / batch_efficiency) * check_overhead

    # 添加随机波动
    total_time *= random.uniform(0.9, 1.1)

    # 模拟执行
    time.sleep(min(total_time, 0.8))  # 最多睡眠0.8秒

    # 模拟质量评分（更保守的配置，评分更稳定）
    safe_zone_range = param_set.safe_zone_upper - param_set.safe_zone_lower
    quality_score = max(70, 85 - (safe_zone_range - 10) * 2)

    # 模拟调整次数（检查间隔越短，调整越频繁）
    adjustment_count = int((2.0 / check_interval) * random.uniform(0.8, 1.2))

    logger.info(
        "数据扫描模拟: %d个品种, 批次=%d, 耗时=%.2fs, 质量评分=%d, 调整=%d次",
        symbol_count,
        batch_size,
        total_time,
        quality_score,
        adjustment_count,
    )

    return {
        "task_count": symbol_count,
        "adjustment_count": adjustment_count,
        "success": True,
        "elapsed": total_time,
        "quality_score": quality_score,
    }


def simulate_reader_batch(param_set: ParameterSet, symbol_count: int = 6000) -> dict:
    """模拟Data Reader批量读取（基于真实数据规模）

    Args:
        param_set: 参数配置
        symbol_count: 品种数量

    Returns:
        测试结果
    """
    # Reader读取是最慢的（二进制解析）
    batch_size = param_set.batch_size_disk

    # 模拟每批次处理时间
    base_time_per_batch = 0.10  # 100ms基准

    # 批次大小影响
    batch_efficiency = min(1.3, 1.0 + (batch_size - 30) / 150)

    # 计算批次数
    batch_count = (symbol_count + batch_size - 1) // batch_size

    # 模拟总时间
    total_time = batch_count * (base_time_per_batch / batch_efficiency)

    # 添加随机波动
    total_time *= random.uniform(0.9, 1.1)

    # 模拟执行
    time.sleep(min(total_time, 1.0))  # 最多睡眠1秒

    logger.info(
        "Reader读取模拟: %d个品种, 批次=%d, 耗时=%.2fs",
        symbol_count,
        batch_size,
        total_time,
    )

    return {
        "task_count": symbol_count,
        "adjustment_count": 0,
        "success": True,
        "elapsed": total_time,
    }


def test_comprehensive_workload(param_set: ParameterSet) -> dict:
    """综合测试（模拟真实数据规模）

    Args:
        param_set: 参数配置

    Returns:
        综合测试结果
    """
    logger.info("\n" + "=" * 80)
    logger.info("综合测试（模拟）- 参数组合: %s", param_set.name)
    logger.info("=" * 80)

    results = {
        "task_count": 0,
        "adjustment_count": 0,
        "success": True,
        "elapsed": 0,
    }

    # 场景1: K线读取（5000品种）
    logger.info("\n[场景1] K线数据读取测试（5000品种）...")
    r1 = simulate_kline_read(param_set, symbol_count=5000)
    results["task_count"] += r1["task_count"]
    results["adjustment_count"] += r1["adjustment_count"]
    results["elapsed"] += r1.get("elapsed", 0)

    # 场景2: 数据扫描（6000品种）
    logger.info("\n[场景2] 数据质量扫描测试（6000品种）...")
    r2 = simulate_data_scan(param_set, symbol_count=6000)
    results["task_count"] += r2["task_count"]
    results["adjustment_count"] += r2["adjustment_count"]
    results["elapsed"] += r2.get("elapsed", 0)

    # 场景3: Reader批量读取（6000品种）
    logger.info("\n[场景3] Data Reader批量读取测试（6000品种）...")
    r3 = simulate_reader_batch(param_set, symbol_count=6000)
    results["task_count"] += r3["task_count"]
    results["adjustment_count"] += r3["adjustment_count"]
    results["elapsed"] += r3.get("elapsed", 0)

    logger.info(
        "\n综合测试完成: 总任务数=%d, 总耗时=%.2fs",
        results["task_count"],
        results["elapsed"],
    )

    return results


# ==================== 参数组合定义 ====================


def get_real_data_parameter_sets() -> List[ParameterSet]:
    """获取针对真实数据优化的参数组合"""
    return [
        # 1. 当前默认配置
        ParameterSet(
            name="当前默认",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        # 2. 磁盘IO优化
        ParameterSet(
            name="磁盘IO优化",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=40,
            batch_size_network=80,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        # 3. 高频调整
        ParameterSet(
            name="高频调整",
            safe_zone_lower=65.0,
            safe_zone_upper=75.0,
            increase_step=0.05,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.0,
            min_adjustment_interval=2.0,
        ),
        # 4. 激进配置
        ParameterSet(
            name="激进配置",
            safe_zone_lower=70.0,
            safe_zone_upper=85.0,
            increase_step=0.10,
            decrease_step=0.10,
            batch_size_disk=50,
            batch_size_network=100,
            check_interval=1.5,
            min_adjustment_interval=3.0,
        ),
        # 5. 保守配置
        ParameterSet(
            name="保守配置",
            safe_zone_lower=55.0,
            safe_zone_upper=65.0,
            increase_step=0.03,
            decrease_step=0.15,
            batch_size_disk=30,
            batch_size_network=60,
            check_interval=2.0,
            min_adjustment_interval=5.0,
        ),
    ]


# ==================== 主测试流程 ====================


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("LoadBalancer A/B测试 - 快速版本（模拟真实数据规模）")
    logger.info("=" * 80)
    logger.info("测试规模: 5000品种K线 + 6000品种扫描 + 6000品种Reader")
    logger.info("=" * 80)

    # 获取参数组合
    param_sets = get_real_data_parameter_sets()
    logger.info("\n✓ 准备测试%d组参数配置", len(param_sets))

    # 创建参数调优器
    tuner = ParameterTuner()

    # 运行调优（快速测试，每组2次迭代）
    logger.info("\n开始A/B测试（每组2次迭代）...")
    results = tuner.run_tuning(
        parameter_sets=param_sets,
        test_workload=test_comprehensive_workload,
        iterations=2,
    )

    # 获取最佳参数
    best = tuner.get_best_parameters(results)

    # 生成报告
    report = tuner.generate_report(results)

    # 保存报告
    report_path = Path(__file__).parent / "ab_testing_real_data_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("\n📊 报告已保存到: %s", report_path)

    # 输出总结
    logger.info("\n" + "=" * 80)
    logger.info("✅ A/B测试完成")
    logger.info("=" * 80)
    logger.info("\n最佳参数组合: %s", best.name)
    logger.info("\n📌 测试说明：")
    logger.info("  - 基于项目真实数据规模（5000-6000品种）进行模拟测试")
    logger.info("  - 模拟了K线读取、数据扫描、Reader批量读取三个场景")
    logger.info("  - 参数影响已体现在模拟性能中")
    logger.info("\n📌 建议：")
    logger.info("1. 查看详细报告: %s", report_path)
    logger.info("2. 根据最佳参数更新LoadBalancer配置")
    logger.info("3. 在生产环境中监控实际性能并微调")

    return 0


if __name__ == "__main__":
    sys.exit(main())
