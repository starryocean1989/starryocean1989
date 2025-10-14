# -*- coding: utf-8 -*-
"""
品种格式测试脚本

验证品种数据格式是否符合前端要求。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from backend.infrastructure.data_module_vnpy.stock_fetcher import StockFetcher
from backend.infrastructure.data_module_vnpy.config import config_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def test_symbol_format():
    """测试品种数据格式"""
    print("=" * 60)
    print("品种格式测试")
    print("=" * 60)

    try:
        # 创建StockFetcher实例
        print("正在初始化StockFetcher...")
        stock_fetcher = StockFetcher()

        # 获取品种分类
        print("\n获取品种分类...")
        market_stocks = stock_fetcher.get_all_market_stocks()

        if not market_stocks:
            print("✗ 获取品种分类失败")
            return

        print(f"✓ 获取到 {len(market_stocks)} 个市场分类")

        # 检查每个市场的品种格式
        print("\n检查品种数据格式...")
        total_symbols = 0

        for market_name, stock_list in market_stocks.items():
            print(f"\n{market_name}: {len(stock_list)} 个品种")

            if len(stock_list) > 0:
                # 检查第一个品种的数据结构
                first_stock = stock_list[0]
                print(f"  第一个品种: {first_stock}")

                # 检查必需字段
                required_fields = ["code", "name", "market"]
                missing_fields = []
                for field in required_fields:
                    if field not in first_stock:
                        missing_fields.append(field)

                if missing_fields:
                    print(f"  ✗ 缺少字段: {missing_fields}")
                else:
                    print("  ✓ 字段完整")
                    print(f"    - 代码: {first_stock['code']}")
                    print(f"    - 名称: {first_stock['name']}")
                    print(f"    - 市场: {first_stock['market']}")

                total_symbols += len(stock_list)

        print(f"\n总计品种数: {total_symbols}")

        # 检查品种展示的预期格式
        print("\n前端展示预期格式验证...")
        expected_markets = ["上证A股", "深证A股", "北证A股", "T+0基金", "含可转债"]

        for market in expected_markets:
            if market in market_stocks:
                count = len(market_stocks[market])
                print(f"  ✓ {market}: {count} 个品种")
            else:
                print(f"  ✗ 缺少市场: {market}")

        print("\n" + "=" * 60)
        print("品种格式测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        logger.exception("测试过程中发生异常")
        sys.exit(1)


if __name__ == "__main__":
    test_symbol_format()
