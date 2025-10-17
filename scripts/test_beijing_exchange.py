# -*- coding: utf-8 -*-
"""
测试北京证券交易所品种数据获取
从项目的北交所品种列表中随机选取品种，验证市场代码2和数据获取
"""
import sys
from pathlib import Path
import random

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
from mootdx.quotes import Quotes


def test_beijing_stocks():
    """测试北交所品种"""
    print("\n" + "="*60)
    print("测试北京证券交易所品种数据获取")
    print("="*60)

    # 1. 从项目品种列表加载北交所品种
    print("\n步骤1: 加载北交所品种列表...")
    symbol_loader = SymbolLoader()

    # 尝试从缓存加载
    classified_stocks = symbol_loader.load_from_cache()

    if not classified_stocks or "北证A股" not in classified_stocks:
        print("  缓存不存在，重新加载品种列表...")
        result = symbol_loader.reload_and_classify()
        if not result.get("success"):
            print(f"  ❌ 加载失败: {result.get('message')}")
            return
        classified_stocks = result.get("data", {}).get("classified", {})

    beijing_stocks = classified_stocks.get("北证A股", [])

    if not beijing_stocks:
        print("  ❌ 北证A股列表为空！")
        print("  可能原因:")
        print("    1. addedcode_bj.cfg文件不存在或为空")
        print("    2. 品种分类逻辑有问题")
        return

    print(f"  ✅ 成功加载 {len(beijing_stocks)} 个北交所品种")

    # 显示前5个品种
    print(f"\n  前5个品种:")
    for stock in beijing_stocks[:5]:
        print(f"    {stock}")

    # 2. 随机选取3个品种测试
    print(f"\n步骤2: 随机选取品种测试...")
    test_count = min(3, len(beijing_stocks))
    test_stocks = random.sample(beijing_stocks, test_count)

    # 3. 创建Quotes实例并测试
    print(f"\n步骤3: 测试数据获取（市场代码=2）...")
    quotes = Quotes.factory()

    for stock in test_stocks:
        code = stock.get("code", "")
        name = stock.get("name", "")
        market = stock.get("market", 2)

        print(f"\n  测试品种: {code} - {name}")
        print(f"    市场代码: {market}")
        print(f"    代码格式: {'✅ 9开头6位' if code.startswith('9') and len(code) == 6 else '❌ 格式异常'}")

        # 测试不同频率的数据获取
        test_frequencies = [
            (4, "日线"),
            (0, "5分钟"),
        ]

        for frequency, freq_name in test_frequencies:
            print(f"\n    测试 {freq_name} (frequency={frequency}):")
            try:
                raw_data = quotes.client.get_security_bars(
                    int(frequency), int(market), str(code), 0, 5
                )

                if raw_data and len(raw_data) > 0:
                    print(f"      ✅ 成功获取 {len(raw_data)} 条数据")
                    print(f"      首条datetime: {raw_data[0].get('datetime', 'N/A')}")
                    print(f"      首条数据: open={raw_data[0].get('open')}, close={raw_data[0].get('close')}")
                else:
                    print(f"      ⚠️  API返回空数据")

            except Exception as e:
                print(f"      ❌ 调用失败: {str(e)[:100]}")

    quotes.close()

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


def verify_market_code_logic():
    """验证市场代码判断逻辑"""
    print("\n" + "="*60)
    print("验证市场代码判断逻辑")
    print("="*60)

    test_cases = [
        ("600000", 1, "上海证券交易所"),
        ("601988", 1, "上海证券交易所"),
        ("000001", 0, "深圳证券交易所"),
        ("002594", 0, "深圳证券交易所"),
        ("300750", 0, "深圳创业板"),
        ("900001", 2, "北京证券交易所"),  # 9开头6位
        ("912345", 2, "北京证券交易所"),  # 9开头6位
        ("999999", 2, "北京证券交易所"),  # 9开头6位
        ("688001", 1, "上海科创板"),
    ]

    print("\n测试市场代码判断逻辑:")
    for symbol, expected_market, market_name in test_cases:
        # 模拟判断逻辑
        if symbol.startswith("6"):
            market = 1
        elif symbol.startswith("9") and len(symbol) == 6:
            market = 2
        else:
            market = 0

        result = "✅" if market == expected_market else "❌"
        print(f"  {result} {symbol} -> 市场代码={market} (期望={expected_market}) {market_name}")


if __name__ == "__main__":
    # 验证市场代码逻辑
    verify_market_code_logic()

    # 测试北交所品种
    test_beijing_stocks()

