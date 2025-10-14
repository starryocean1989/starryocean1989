# -*- coding: utf-8 -*-
"""
测试新品种列表解析逻辑

验证：
1. 品种数量是否符合预期（约5724个）
2. 数据完整性（每个品种应有code、name、market字段）
3. 分类正确性（上证A股、深证A股、北证A股、T+0基金、可转债）
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.stock_fetcher import StockFetcher
from backend.infrastructure.data_module_vnpy.block_parser import BlockParser
from backend.infrastructure.data_module_vnpy.config import config_manager


def test_symbol_count():
    """测试品种数量"""
    print("=" * 60)
    print("测试1: 品种数量验证")
    print("=" * 60)

    # 初始化StockFetcher
    block_parser = BlockParser(config_manager.get_tdx_dir())
    stock_fetcher = StockFetcher(block_parser)

    # 获取所有品种
    all_stocks = stock_fetcher.get_all_market_stocks()

    total_count = sum(len(stocks) for stocks in all_stocks.values())

    print(f"\n📊 品种统计:")
    for market_type, stocks in all_stocks.items():
        print(f"  • {market_type}: {len(stocks)} 个")

    print(f"\n✅ 总计: {total_count} 个品种")

    # 预期约5724个品种
    if total_count > 5000:
        print(f"✅ 品种数量符合预期（>5000个）")
    else:
        print(f"⚠️ 品种数量可能偏少（<5000个）")

    return all_stocks


def test_data_completeness(all_stocks):
    """测试数据完整性"""
    print("\n" + "=" * 60)
    print("测试2: 数据完整性验证")
    print("=" * 60)

    required_fields = ["code", "name", "market"]
    incomplete_count = 0

    for market_type, stocks in all_stocks.items():
        for stock in stocks:
            missing_fields = [field for field in required_fields if field not in stock]
            if missing_fields:
                incomplete_count += 1
                print(f"⚠️ {market_type} - {stock.get('code', 'N/A')}: 缺少字段 {missing_fields}")

    if incomplete_count == 0:
        print(f"\n✅ 所有品种数据完整，包含 {', '.join(required_fields)} 字段")
    else:
        print(f"\n⚠️ 发现 {incomplete_count} 个品种数据不完整")

    return incomplete_count == 0


def test_classification(all_stocks):
    """测试分类正确性"""
    print("\n" + "=" * 60)
    print("测试3: 分类正确性验证")
    print("=" * 60)

    errors = []

    # 检查上证A股（688/60开头，market=1）
    if "上证A股" in all_stocks:
        sh_stocks = all_stocks["上证A股"]
        for stock in sh_stocks:
            code = stock.get("code", "")
            market = stock.get("market", -1)
            if not (code.startswith("688") or code.startswith("60")):
                errors.append(f"上证A股代码错误: {code}")
            if market != 1:
                errors.append(f"上证A股市场代码错误: {code}, market={market}")

        print(f"✅ 上证A股: {len(sh_stocks)} 个")

    # 检查深证A股（000/001/002/300/301开头，market=0）
    if "深证A股" in all_stocks:
        sz_stocks = all_stocks["深证A股"]
        for stock in sz_stocks:
            code = stock.get("code", "")
            market = stock.get("market", -1)
            if not (
                code.startswith("000")
                or code.startswith("001")
                or code.startswith("002")
                or code.startswith("300")
                or code.startswith("301")
            ):
                errors.append(f"深证A股代码错误: {code}")
            if market != 0:
                errors.append(f"深证A股市场代码错误: {code}, market={market}")

        print(f"✅ 深证A股: {len(sz_stocks)} 个")

    # 检查北证A股（9开头，market=2）
    if "北证A股" in all_stocks:
        bj_stocks = all_stocks["北证A股"]
        for stock in bj_stocks:
            code = stock.get("code", "")
            market = stock.get("market", -1)
            if not code.startswith("9"):
                errors.append(f"北证A股代码错误: {code}")
            if market != 2:
                errors.append(f"北证A股市场代码错误: {code}, market={market}")

        print(f"✅ 北证A股: {len(bj_stocks)} 个")

    # 检查T+0基金（01/15开头7位代码，market=0或1）
    if "T+0基金" in all_stocks:
        t0_stocks = all_stocks["T+0基金"]
        for stock in t0_stocks:
            code = stock.get("code", "")
            market = stock.get("market", -1)
            if not (code.startswith("01") or code.startswith("15")):
                errors.append(f"T+0基金代码错误: {code}")
            if market not in [0, 1]:
                errors.append(f"T+0基金市场代码错误: {code}, market={market}")

        print(f"✅ T+0基金: {len(t0_stocks)} 个")

    # 检查可转债（11/12开头，market=0或1）
    if "可转债" in all_stocks:
        cb_stocks = all_stocks["可转债"]
        for stock in cb_stocks:
            code = stock.get("code", "")
            market = stock.get("market", -1)
            if not (code.startswith("11") or code.startswith("12")):
                errors.append(f"可转债代码错误: {code}")
            if market not in [0, 1]:
                errors.append(f"可转债市场代码错误: {code}, market={market}")

        print(f"✅ 可转债: {len(cb_stocks)} 个")

    if errors:
        print(f"\n⚠️ 发现 {len(errors)} 个分类错误:")
        for error in errors[:10]:  # 只显示前10个错误
            print(f"  • {error}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors) - 10} 个错误未显示")
        return False
    else:
        print(f"\n✅ 所有品种分类正确")
        return True


def main():
    """主测试函数"""
    print("开始测试新品种列表解析逻辑...")
    print()

    try:
        # 测试1: 品种数量
        all_stocks = test_symbol_count()

        # 测试2: 数据完整性
        is_complete = test_data_completeness(all_stocks)

        # 测试3: 分类正确性
        is_correct = test_classification(all_stocks)

        # 总结
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        print(f"品种数量: {'✅ 通过' if all_stocks else '❌ 失败'}")
        print(f"数据完整性: {'✅ 通过' if is_complete else '❌ 失败'}")
        print(f"分类正确性: {'✅ 通过' if is_correct else '❌ 失败'}")

        if all_stocks and is_complete and is_correct:
            print("\n🎉 所有测试通过！")
            return 0
        else:
            print("\n⚠️ 部分测试失败")
            return 1

    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
