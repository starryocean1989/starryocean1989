# -*- coding: utf-8 -*-
"""
调试测试组件 - 验证各个组件是否正常工作
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)8s] %(message)s")

logger = logging.getLogger(__name__)


def test_imports():
    """测试1：验证所有导入是否正常"""
    logger.info("=" * 60)
    logger.info("测试1：验证导入")
    logger.info("=" * 60)

    try:
        from vnpy.event import EventEngine

        logger.info("✅ vnpy.event.EventEngine 导入成功")

        from backend.infrastructure.data_module_vnpy.load_balancer import (
            ResourceMonitor,
            ExecutionPolicy,
            AdaptiveThresholdCalculator,
        )

        logger.info("✅ LoadBalancer组件导入成功")

        from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
            SymbolLoader,
        )

        logger.info("✅ SymbolLoader导入成功")

        from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor

        logger.info("✅ DataSensor导入成功")

        return True
    except Exception as e:
        logger.error(f"❌ 导入失败: {e}", exc_info=True)
        return False


def test_event_engine():
    """测试2：验证EventEngine是否正常"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2：验证EventEngine")
    logger.info("=" * 60)

    try:
        from vnpy.event import EventEngine

        event_engine = EventEngine()
        logger.info("✅ EventEngine创建成功")
        return event_engine
    except Exception as e:
        logger.error(f"❌ EventEngine创建失败: {e}", exc_info=True)
        return None


def test_adaptive_calculator():
    """测试3：验证AdaptiveThresholdCalculator"""
    logger.info("\n" + "=" * 60)
    logger.info("测试3：验证AdaptiveThresholdCalculator")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import (
            AdaptiveThresholdCalculator,
        )

        calculator = AdaptiveThresholdCalculator()
        logger.info("✅ AdaptiveThresholdCalculator创建成功")

        baseline = calculator.calculate_conservative_baseline()
        logger.info(f"✅ 短板50%计算成功:")
        logger.info(f"  - base_workers: {baseline['base_workers']}")
        logger.info(f"  - bottleneck_resource: {baseline['bottleneck_resource']}")
        logger.info(f"  - resource_scores: {baseline['resource_scores']}")

        return True
    except Exception as e:
        logger.error(f"❌ AdaptiveThresholdCalculator测试失败: {e}", exc_info=True)
        return False


def test_execution_policy(event_engine):
    """测试4：验证ExecutionPolicy"""
    logger.info("\n" + "=" * 60)
    logger.info("测试4：验证ExecutionPolicy")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import ExecutionPolicy

        policy = ExecutionPolicy(enable_adaptive_baseline=True)
        logger.info("✅ ExecutionPolicy创建成功")
        logger.info(f"  - SAFE_ZONE_LOWER: {policy.SAFE_ZONE_LOWER}%")
        logger.info(f"  - SAFE_ZONE_UPPER: {policy.SAFE_ZONE_UPPER}%")
        logger.info(f"  - INCREASE_STEP: {policy.INCREASE_STEP*100:.0f}%")
        logger.info(f"  - DECREASE_STEP: {policy.DECREASE_STEP*100:.0f}%")

        return True
    except Exception as e:
        logger.error(f"❌ ExecutionPolicy测试失败: {e}", exc_info=True)
        return False


def test_resource_monitor(event_engine):
    """测试5：验证ResourceMonitor"""
    logger.info("\n" + "=" * 60)
    logger.info("测试5：验证ResourceMonitor")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor

        monitor = ResourceMonitor(event_engine)
        logger.info("✅ ResourceMonitor创建成功")

        pressure = monitor.get_current_pressure()
        logger.info(f"✅ 获取当前压力成功:")
        logger.info(f"  - score: {pressure.score:.1f}%")
        logger.info(f"  - bottleneck: {pressure.bottleneck}")
        logger.info(f"  - below_low_threshold: {pressure.below_low_threshold}")
        logger.info(f"  - above_high_threshold: {pressure.above_high_threshold}")

        return True
    except Exception as e:
        logger.error(f"❌ ResourceMonitor测试失败: {e}", exc_info=True)
        return False


def test_symbol_loader():
    """测试6：验证SymbolLoader（不加载API，只检查缓存）"""
    logger.info("\n" + "=" * 60)
    logger.info("测试6：验证SymbolLoader（只读缓存）")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
            SymbolLoader,
        )

        symbol_loader = SymbolLoader()
        logger.info("✅ SymbolLoader创建成功")

        # 只尝试从缓存加载，不调用API
        logger.info("尝试从缓存加载符号列表...")
        classified = symbol_loader.load_from_cache()

        if classified:
            total_count = sum(len(stocks) for stocks in classified.values())
            logger.info(f"✅ 从缓存加载成功，共{total_count}个品种")
            logger.info(f"  - 上证A股: {len(classified.get('上证A股', []))}")
            logger.info(f"  - 深证A股: {len(classified.get('深证A股', []))}")
            logger.info(f"  - 北证A股: {len(classified.get('北证A股', []))}")

            # 提取代码
            all_codes = symbol_loader.extract_all_codes()
            logger.info(f"✅ 提取品种代码成功，共{len(all_codes)}个")
            logger.info(f"  - 前10个: {all_codes[:10]}")

            return True
        else:
            logger.warning("⚠️ 缓存为空，需要先下载品种列表")
            logger.info("提示：可以手动运行以下命令下载：")
            logger.info(
                '  python -c "from backend.infrastructure.data_module_vnpy import SymbolLoader; sl = SymbolLoader(); sl.load_from_api()"'
            )
            return False

    except Exception as e:
        logger.error(f"❌ SymbolLoader测试失败: {e}", exc_info=True)
        return False


def test_data_sensor_creation(event_engine):
    """测试7：验证DataSensor创建（不执行扫描）"""
    logger.info("\n" + "=" * 60)
    logger.info("测试7：验证DataSensor创建")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor

        sensor = DataSensor(event_engine)
        logger.info("✅ DataSensor创建成功")

        return True
    except Exception as e:
        logger.error(f"❌ DataSensor创建失败: {e}", exc_info=True)
        return False


def main():
    """运行所有调试测试"""
    logger.info("\n" + "=" * 80)
    logger.info("开始调试测试组件")
    logger.info("=" * 80)

    results = {}

    # 测试1：导入
    results["imports"] = test_imports()
    if not results["imports"]:
        logger.error("❌ 导入失败，无法继续测试")
        return

    # 测试2：EventEngine
    event_engine = test_event_engine()
    results["event_engine"] = event_engine is not None
    if not results["event_engine"]:
        logger.error("❌ EventEngine创建失败，无法继续测试")
        return

    # 测试3：AdaptiveThresholdCalculator
    results["adaptive_calculator"] = test_adaptive_calculator()

    # 测试4：ExecutionPolicy
    results["execution_policy"] = test_execution_policy(event_engine)

    # 测试5：ResourceMonitor
    results["resource_monitor"] = test_resource_monitor(event_engine)

    # 测试6：SymbolLoader（只读缓存）
    results["symbol_loader"] = test_symbol_loader()

    # 测试7：DataSensor创建
    results["data_sensor"] = test_data_sensor_creation(event_engine)

    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试结果总结")
    logger.info("=" * 80)

    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        logger.info(f"{test_name:30s}: {status}")

    # 最终建议
    logger.info("\n" + "=" * 80)
    logger.info("建议：")
    logger.info("=" * 80)

    if not results.get("symbol_loader", False):
        logger.info("1. SymbolLoader缓存为空，请先运行以下命令初始化：")
        logger.info(
            '   python -c "from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader; sl = SymbolLoader(); sl.load_from_api()"'
        )

    if all(results.values()):
        logger.info("✅ 所有组件测试通过！可以运行完整测试")
    else:
        logger.warning("⚠️ 部分组件测试失败，请先修复问题")


if __name__ == "__main__":
    main()
