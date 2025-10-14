# -*- coding: utf-8 -*-
"""
测试品种重新加载修复

验证market列缺失问题已解决
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.core.base import get_china_stock_engine
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_reload_stock_list():
    """测试重新加载品种列表"""
    logger.info("=" * 60)
    logger.info("开始测试品种重新加载功能")
    logger.info("=" * 60)

    try:
        # 获取ChinaStockEngine
        engine = get_china_stock_engine()
        if not engine:
            logger.error("❌ ChinaStockEngine不可用")
            return False

        logger.info("✅ ChinaStockEngine可用")

        # 执行重新加载品种列表
        logger.info("\n开始重新加载品种列表...")
        success = engine.reload_stock_list()

        if success:
            logger.info("\n✅ 品种列表重新加载成功!")

            # 验证品种分类
            logger.info("\n验证品种分类...")
            all_markets = engine.get_all_market_stocks()

            if all_markets:
                logger.info("✅ 品种分类获取成功")
                for market_type, stocks in all_markets.items():
                    logger.info(f"  • {market_type}: {len(stocks)} 个品种")
                    # 检查market列是否存在
                    if stocks and isinstance(stocks[0], dict):
                        sample_stock = stocks[0]
                        if "market" in sample_stock:
                            logger.info(f"    ✓ 包含market列: {sample_stock.get('market')}")
                        else:
                            logger.error(f"    ✗ 缺少market列!")
                            return False
            else:
                logger.error("❌ 品种分类为空")
                return False

            return True
        else:
            logger.error("❌ 品种列表重新加载失败")
            return False

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_reload_stock_list()
    sys.exit(0 if success else 1)
