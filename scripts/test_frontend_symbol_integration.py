# -*- coding: utf-8 -*-
"""
前端品种集成测试脚本

模拟前端数据中心服务获取品种数据的完整流程。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from backend.infrastructure.data_module_vnpy.stock_fetcher import StockFetcher
from backend.infrastructure.data_module_vnpy.config import config_manager


# 模拟前端数据中心服务的数据处理逻辑
class MockDataCenterService:
    """模拟前端数据中心服务"""

    def __init__(self):
        self.china_stock_engine = MockChinaStockEngine()

    def _map_market_to_exchange_and_type(self, market_type: str):
        """模拟市场名称到交易所和品种类型的映射"""
        mapping = {
            "上证A股": ("上交所", "股票"),
            "深证A股": ("深交所", "股票"),
            "北证A股": ("北交所", "股票"),
            "T+0基金": ("全部", "基金"),
            "含可转债": ("全部", "可转债"),
        }
        return mapping.get(market_type, ("未知", "未知"))

    def _fetch_symbols_from_china_stock(self):
        """模拟从ChinaStockEngine获取品种列表"""
        try:
            # 调用ChinaStockEngine的reload_stock_list方法
            success = self.china_stock_engine.reload_stock_list()
            if not success:
                return []

            # 调用get_all_market_stocks获取分类后的品种字典
            market_stocks = self.china_stock_engine.get_all_market_stocks()

            if not market_stocks:
                return []

            # 转换为前端需要的格式
            symbols = []

            # 如果market_stocks是市场分类的字典，需要扁平化处理
            if isinstance(market_stocks, dict) and len(market_stocks) > 0:
                # 检查第一个市场的第一个品种的数据结构
                first_market = next(iter(market_stocks))
                first_stock = market_stocks[first_market][0] if market_stocks[first_market] else {}

                if isinstance(first_stock, dict) and "code" in first_stock:
                    # 新格式：市场分类字典，品种是字典列表
                    for market_name, stock_list in market_stocks.items():
                        # 映射市场名称到交易所和品种类型
                        exchange, product_type = self._map_market_to_exchange_and_type(market_name)

                        for stock_info in stock_list:
                            # stock_info是一个字典，包含 code, name, market
                            stock_code = stock_info.get("code", "")
                            stock_name = stock_info.get("name", "")
                            market_code = stock_info.get("market", -1)

                            # 根据market_code映射交易所（如果exchange为"全部"，使用market_code）
                            if exchange == "全部":
                                if market_code == 0:
                                    exchange_name = "深交所"
                                elif market_code == 1:
                                    exchange_name = "上交所"
                                elif market_code == 2:
                                    exchange_name = "北交所"
                                else:
                                    exchange_name = "未知"
                            else:
                                exchange_name = exchange

                            symbols.append(
                                {
                                    "symbol": stock_code,  # 使用symbol字段（与前端期望一致）
                                    "code": stock_code,  # 同时保留code字段
                                    "name": stock_name,  # 使用品种名称
                                    "exchange": exchange_name,  # 使用映射后的交易所名称
                                    "product_type": product_type,  # 使用映射后的品种类型
                                    "market": market_code,  # 保留市场代码（供后端使用）
                                }
                            )

            return symbols

        except Exception as e:
            print(f"获取品种列表失败: {e}")
            return []


class MockChinaStockEngine:
    """模拟ChinaStockEngine"""

    def __init__(self):
        self.stock_fetcher = StockFetcher()

    def reload_stock_list(self) -> bool:
        """模拟reload_stock_list"""
        try:
            # 这里应该重新加载品种缓存
            return True
        except Exception:
            return False

    def get_all_market_stocks(self):
        """模拟get_all_market_stocks"""
        return self.stock_fetcher.get_all_market_stocks()


def test_frontend_symbol_integration():
    """测试前端品种集成"""
    print("=" * 60)
    print("前端品种集成测试")
    print("=" * 60)

    try:
        # 创建模拟前端数据中心服务
        print("正在初始化模拟前端数据中心服务...")
        service = MockDataCenterService()

        # 获取品种列表
        print("\n获取品种列表...")
        symbols = service._fetch_symbols_from_china_stock()

        if not symbols:
            print("✗ 获取品种列表失败")
            return

        print(f"✓ 成功获取 {len(symbols)} 个品种")

        # 检查品种数据格式
        print("\n检查品种数据格式...")
        sample_symbols = symbols[:5]

        for i, symbol in enumerate(sample_symbols):
            print(f"  品种 {i+1}: {symbol}")

            # 检查必需字段
            required_fields = ["symbol", "code", "name", "exchange", "product_type", "market"]
            missing_fields = []
            for field in required_fields:
                if field not in symbol:
                    missing_fields.append(field)

            if missing_fields:
                print(f"    ✗ 缺少字段: {missing_fields}")
            else:
                print("    ✓ 字段完整")
        # 统计各市场的品种数量
        print("\n统计各市场品种数量...")
        market_stats = {}
        for symbol in symbols:
            market = symbol.get("exchange", "未知")
            if market not in market_stats:
                market_stats[market] = 0
            market_stats[market] += 1

        for market, count in market_stats.items():
            print(f"  {market}: {count} 个品种")

        # 验证总数
        total_count = sum(market_stats.values())
        print(f"\n总计品种数: {total_count}")

        # 验证预期品种数
        expected_total = 6339  # 从之前的测试中获取的总数
        if total_count == expected_total:
            print(f"✓ 品种总数正确: {total_count}")
        else:
            print(f"⚠ 品种总数异常: {total_count}，预期: {expected_total}")

        print("\n" + "=" * 60)
        print("前端品种集成测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_frontend_symbol_integration()
