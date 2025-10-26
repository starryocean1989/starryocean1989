# -*- coding: utf-8 -*-
"""
最简单的扫描测试 - 验证DataSensor.scan_quality()是否会卡住
"""

import logging
import time

from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
from vnpy.event import EventEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)8s] %(message)s")

logger = logging.getLogger(__name__)


def test_simple_scan():
    """最简单的扫描测试：只扫描10个品种"""
    logger.info("=" * 80)
    logger.info("开始简单扫描测试（10品种）")
    logger.info("=" * 80)

    # 1. 创建EventEngine
    logger.info("步骤1：创建EventEngine...")
    event_engine = EventEngine()
    logger.info("✅ EventEngine创建成功")

    # 2. 创建SymbolLoader并加载符号
    logger.info("\n步骤2：加载符号列表...")
    symbol_loader = SymbolLoader()
    all_symbols = symbol_loader.extract_all_codes()
    test_symbols = all_symbols[:10]  # 只取前10个
    logger.info(f"✅ 加载了{len(test_symbols)}个品种: {test_symbols}")

    # 3. 创建DataSensor
    logger.info("\n步骤3：创建DataSensor...")
    sensor = DataSensor(event_engine)
    logger.info("✅ DataSensor创建成功")

    # 4. 执行扫描
    logger.info("\n步骤4：开始扫描...")
    logger.info("⏱️  计时开始...")

    start_time = time.time()

    try:
        result = sensor.scan_all_data(reference_symbols=test_symbols)
        elapsed = time.time() - start_time

        logger.info(f"✅ 扫描完成！耗时: {elapsed:.2f}秒")
        logger.info(f"\n扫描结果：")
        logger.info(f"  - total_symbols: {result.total_symbols}")
        logger.info(f"  - missing_symbols: {result.missing_symbols}")
        logger.info(f"  - outdated_symbols: {result.outdated_symbols}")
        logger.info(f"  - error_symbols: {result.error_symbols}")
        logger.info(f"  - quality_score: {result.quality_score}")

        logger.info("\n=" * 80)
        logger.info("✅ 测试通过！DataSensor.scan_quality()工作正常")
        logger.info("=" * 80)

        return True

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ 扫描失败（耗时{elapsed:.2f}秒）: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_simple_scan()
    exit(0 if success else 1)
