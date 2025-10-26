# -*- coding: utf-8 -*-
"""
LoadBalancer A/B测试 - 真实数据小样本测试

使用真实数据的小样本进行测试，避免长时间等待：
- 100个品种K线读取
- 50个品种数据扫描
- 外推到5000/6000品种的实际性能
"""

import logging
import sys
import time
from pathlib import Path
from typing import List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.load_balancer import ParameterSet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_sample_symbols() -> List[str]:
    """获取真实的本地品种列表样本"""
    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            StorageManager,
        )

        storage = StorageManager()
        all_symbols = storage.get_local_data_index()
        
        if not all_symbols:
            logger.warning("无本地品种，使用模拟数据")
            return []
        
        # 均匀采样100个品种
        step = max(1, len(all_symbols) // 100)
        sample = all_symbols[::step][:100]
        
        logger.info("从%d个品种中采样%d个用于测试", len(all_symbols), len(sample))
        return sample
        
    except Exception as e:
        logger.error("获取品种列表失败: %s", e)
        return []


def test_single_config_real_data(param_set: ParameterSet) -> dict:
    """使用真实数据测试单个参数配置
    
    Args:
        param_set: 参数配置
        
    Returns:
        测试结果
    """
    logger.info("\n" + "=" * 80)
    logger.info("测试参数: %s", param_set.name)
    logger.info("  批次大小: disk=%d, network=%d", 
                param_set.batch_size_disk, param_set.batch_size_network)
    logger.info("  安全区间: %.0f-%.0f%%", 
                param_set.safe_zone_lower, param_set.safe_zone_upper)
    logger.info("=" * 80)
    
    results = {
        "kline_time": 0,
        "scan_time": 0,
        "total_symbols": 0,
    }
    
    # 获取测试样本
    symbols = get_sample_symbols()
    if not symbols:
        logger.warning("没有可用的测试品种")
        return results
    
    results["total_symbols"] = len(symbols)
    
    # 场景1: K线读取测试
    logger.info("\n[场景1] K线读取测试 - %d个品种", len(symbols))
    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            StorageManager,
        )
        
        storage = StorageManager()
        start = time.time()
        
        # 限制worker数量
        max_workers = min(param_set.batch_size_disk, 50)
        
        results_data = storage.query_kline_batch(
            symbols=symbols,
            interval="1d",
            max_workers=max_workers,
        )
        
        elapsed = time.time() - start
        results["kline_time"] = elapsed
        
        success_count = sum(1 for df in results_data.values() if df is not None)
        success_rate = success_count / len(symbols) * 100
        
        logger.info("✓ K线读取完成: %.2fs, 成功率%.1f%% (%d/%d)", 
                   elapsed, success_rate, success_count, len(symbols))
        
        # 外推到5000品种
        estimated_5000 = elapsed * (5000 / len(symbols))
        logger.info("  → 外推到5000品种: 预计%.1f秒 (%.1f分钟)", 
                   estimated_5000, estimated_5000 / 60)
        
    except Exception as e:
        logger.error("K线读取测试失败: %s", e)
    
    # 场景2: 数据扫描测试（更小样本）
    logger.info("\n[场景2] 数据扫描测试 - %d个品种", min(50, len(symbols)))
    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            DataSensor,
        )
        
        # 只测试前50个品种（扫描更慢）
        scan_symbols = symbols[:50]
        
        sensor = DataSensor()
        start = time.time()
        
        overview = sensor.scan_all_data_adaptive(
            reference_symbols=scan_symbols,
            intervals=["1d"],  # 只扫描日线
            force_refresh=True,
        )
        
        elapsed = time.time() - start
        results["scan_time"] = elapsed
        
        logger.info("✓ 数据扫描完成: %.2fs, 质量评分%d", 
                   elapsed, overview.quality_score)
        
        # 外推到6000品种
        estimated_6000 = elapsed * (6000 / len(scan_symbols))
        logger.info("  → 外推到6000品种: 预计%.1f秒 (%.1f分钟)", 
                   estimated_6000, estimated_6000 / 60)
        
    except Exception as e:
        logger.error("数据扫描测试失败: %s", e)
    
    # 总结
    total_time = results["kline_time"] + results["scan_time"]
    logger.info("\n" + "=" * 80)
    logger.info("测试完成: 总耗时%.2fs", total_time)
    logger.info("=" * 80)
    
    return results


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("LoadBalancer A/B测试 - 真实数据小样本测试")
    logger.info("=" * 80)
    
    # 定义要测试的配置
    configs = [
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
    
    # 测试每个配置
    all_results = {}
    for config in configs:
        results = test_single_config_real_data(config)
        all_results[config.name] = results
        
        # 休息一下，避免资源争抢影响下一个测试
        logger.info("\n等待3秒后继续下一个配置...\n")
        time.sleep(3)
    
    # 生成对比报告
    logger.info("\n" + "=" * 80)
    logger.info("对比分析")
    logger.info("=" * 80)
    
    for name, results in all_results.items():
        logger.info("\n%s:", name)
        logger.info("  K线读取时间: %.2fs", results.get("kline_time", 0))
        logger.info("  扫描时间: %.2fs", results.get("scan_time", 0))
        logger.info("  样本品种数: %d", results.get("total_symbols", 0))
    
    # 保存详细报告
    report_path = Path(__file__).parent / "real_sample_test_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("LoadBalancer真实数据测试报告\n")
        f.write("=" * 80 + "\n\n")
        for name, results in all_results.items():
            f.write(f"{name}:\n")
            f.write(f"  K线读取: {results.get('kline_time', 0):.2f}秒\n")
            f.write(f"  数据扫描: {results.get('scan_time', 0):.2f}秒\n")
            f.write(f"  样本数: {results.get('total_symbols', 0)}\n\n")
    
    logger.info("\n📊 详细报告已保存到: %s", report_path)
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ 真实数据测试完成")
    logger.info("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

