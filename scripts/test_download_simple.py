# -*- coding: utf-8 -*-
"""简单的下载诊断脚本."""
import sys
import logging
from pathlib import Path
from datetime import date, timedelta

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    """主函数."""
    logger.info("=" * 80)
    logger.info("开始诊断下载功能")
    logger.info("=" * 80)

    try:
        # 导入模块
        from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
        from backend.infrastructure.data_module_vnpy.config import config_manager

        # 1. 检查品种列表缓存
        logger.info("步骤1: 检查品种列表缓存...")
        symbol_loader = SymbolLoader()
        classified = symbol_loader.load_from_cache()

        if not classified:
            logger.error("❌ 品种缓存为空")
            return

        logger.info(f"✓ 品种缓存加载成功，类型: {type(classified)}")
        logger.info(f"✓ 缓存keys: {list(classified.keys())}")

        # 2. 提取品种代码
        logger.info("步骤2: 提取品种代码...")
        all_symbols = []
        market_types = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]

        for market_type in market_types:
            stocks = classified.get(market_type, [])
            logger.info(f"  {market_type}: {len(stocks)} 条数据")

            if stocks and len(stocks) > 0:
                first_item = stocks[0]
                logger.info(f"    第一条数据: {first_item}")

                if isinstance(first_item, dict) and "code" in first_item:
                    codes = [s.get("code") for s in stocks if isinstance(s, dict) and s.get("code")]
                    all_symbols.extend(codes)
                    logger.info(f"    提取到 {len(codes)} 个代码")

        logger.info(f"✓ 总品种数: {len(all_symbols)}")
        logger.info(f"✓ 前5个品种: {all_symbols[:5]}")

        if not all_symbols:
            logger.error("❌ 提取品种代码失败，all_symbols为空")
            return

        # 3. 测试下载单个品种
        logger.info("步骤3: 测试下载单个品种...")
        test_symbol = all_symbols[0]
        start_date = date.today() - timedelta(days=5)

        logger.info(f"  测试品种: {test_symbol}")
        logger.info(f"  开始日期: {start_date}")

        from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher

        fetcher = MultiProcessStockFetcher()
        logger.info(f"  下载器创建成功，进程数: {fetcher.num_processes}")

        # 下载单个品种
        result = fetcher.download_incremental_kline(
            symbols=[test_symbol], start_date=start_date, intervals=["1d"]
        )

        logger.info("=" * 80)
        logger.info(f"下载结果: {len(result)} 个数据集")
        for key, df in result.items():
            if df is not None and not df.empty:
                logger.info(f"  ✓ {key}: {len(df)} 条记录")
            elif df is None:
                logger.warning(f"  ✗ {key}: 下载失败")
            else:
                logger.warning(f"  ✗ {key}: 空数据")

        logger.info("=" * 80)
        logger.info("✅ 诊断完成")

    except Exception as e:
        logger.error(f"❌ 诊断失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()
