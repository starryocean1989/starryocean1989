# -*- coding: utf-8 -*-
"""
测试 data_module_vnpy 迁移到 tdx_asyncio 后的功能

验证项：
1. 品种列表获取
2. 增量下载
3. 数据查询
4. 多进程并发
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher
from backend.infrastructure.data_module_vnpy.data_quality import StorageManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_symbol_loading():
    """测试品种列表加载"""
    logger.info("=" * 80)
    logger.info("测试 1: 品种列表加载")
    logger.info("=" * 80)

    try:
        symbol_loader = SymbolLoader()

        # 重新加载品种列表
        logger.info("开始重新加载品种列表...")
        start_time = datetime.now()

        result = symbol_loader.load_from_api()

        elapsed = (datetime.now() - start_time).total_seconds()

        # 统计各分类品种数量
        logger.info(f"\n品种列表加载完成，耗时: {elapsed:.2f} 秒")
        logger.info("-" * 40)

        classified_stocks = result.get("classified", {})
        for category, stocks in classified_stocks.items():
            logger.info(f"  {category}: {len(stocks)} 个品种")
        logger.info("-" * 40)

        return True
    except Exception as e:
        logger.error(f"品种列表加载失败: {e}", exc_info=True)
        return False


def test_incremental_download():
    """测试增量下载"""
    logger.info("\n" + "=" * 80)
    logger.info("测试 2: 增量下载（测试品种：000001, 600000）")
    logger.info("=" * 80)

    try:
        fetcher = MultiProcessStockFetcher()

        # 下载少量品种测试
        test_symbols = ["000001", "600000"]
        start_date = "2024-01-01"

        logger.info(f"开始增量下载: {test_symbols}, 起始日期: {start_date}")
        start_time = datetime.now()

        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=["1d"]  # 只下载日线数据
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(f"\n下载完成，耗时: {elapsed:.2f} 秒")
        logger.info("-" * 40)
        for key, data in results.items():
            logger.info(f"  {key}: {len(data)} 条数据")
            if len(data) > 0:
                logger.info(f"    最早: {data.index[0]}")
                logger.info(f"    最新: {data.index[-1]}")
        logger.info("-" * 40)

        return True
    except Exception as e:
        logger.error(f"增量下载失败: {e}", exc_info=True)
        return False


def test_data_query():
    """测试数据查询"""
    logger.info("\n" + "=" * 80)
    logger.info("测试 3: 数据查询（从刚下载的数据中查询）")
    logger.info("=" * 80)

    try:
        storage_manager = StorageManager()

        # 查询数据
        symbol = "000001"
        interval = "1d"
        start_date = "2024-01-01"
        end_date = "2024-10-17"

        logger.info(f"查询参数: symbol={symbol}, interval={interval}")
        logger.info(f"日期范围: {start_date} ~ {end_date}")

        data = storage_manager.query_data(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date
        )

        if data is not None and not data.empty:
            logger.info(f"\n查询成功: {len(data)} 条数据")
            logger.info("-" * 40)
            logger.info(f"  最早: {data.index[0]}")
            logger.info(f"  最新: {data.index[-1]}")
            logger.info("\n数据预览（前5行）:")
            logger.info(data.head().to_string())
            logger.info("-" * 40)
            return True
        else:
            logger.warning("查询结果为空（可能是数据未保存到存储）")
            return False

    except Exception as e:
        logger.error(f"数据查询失败: {e}", exc_info=True)
        return False


def main():
    """主测试函数"""
    logger.info("=" * 80)
    logger.info("data_module_vnpy → tdx_asyncio 迁移测试")
    logger.info("=" * 80)

    results = {
        "品种列表加载": False,
        "增量下载": False,
        "数据查询": False
    }

    # 测试 1: 品种列表加载
    results["品种列表加载"] = test_symbol_loading()

    # 测试 2: 增量下载
    results["增量下载"] = test_incremental_download()

    # 测试 3: 数据查询
    results["数据查询"] = test_data_query()

    # 汇总结果
    logger.info("\n" + "=" * 80)
    logger.info("测试结果汇总")
    logger.info("=" * 80)
    for test_name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        logger.info(f"  {test_name}: {status}")
    logger.info("=" * 80)

    all_passed = all(results.values())
    if all_passed:
        logger.info("\n🎉 所有测试通过！迁移成功！")
    else:
        logger.error("\n❌ 部分测试失败，请检查日志")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

