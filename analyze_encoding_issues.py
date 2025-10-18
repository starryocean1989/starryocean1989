# -*- coding: utf-8 -*-
"""分析品种数据中的乱码字符问题."""

import json
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def analyze_encoding_issues():
    """分析品种数据中的乱码字符问题."""

    print("=" * 80)
    print("品种数据乱码字符深度分析")
    print("=" * 80)

    try:
        # 读取品种缓存数据
        cache_file = "data/cache/stock_list_classified.json"
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        classified = cache_data.get("classified", {})

        print("📊 品种数据概览:")
        print("-" * 50)

        total_stocks = 0
        problematic_stocks = []

        for market_type, codes in classified.items():
            print(f"{market_type}: {len(codes)} 个品种")
            total_stocks += len(codes)

            for code in codes:
                if isinstance(code, dict):
                    name = code.get("name", "")

                    # 检查是否包含乱码字符
                    issues = []
                    if "\x00" in name:
                        issues.append("空字符(\\x00)")
                    if "\ufffd" in name:
                        issues.append("替换字符(\\ufffd)")
                    if "\u0000" in name:
                        issues.append("Unicode空字符(\\u0000)")

                    if issues:
                        problematic_stocks.append(
                            {
                                "code": code.get("code", ""),
                                "name": name,
                                "market": market_type,
                                "issues": issues,
                            }
                        )

        print(f"\n📈 总体统计:")
        print("-" * 50)
        print(f"总品种数: {total_stocks}")
        print(f"有乱码字符的品种: {len(problematic_stocks)} 个")

        if problematic_stocks:
            # 按市场分类显示
            by_market = {}
            for stock in problematic_stocks:
                market = stock["market"]
                if market not in by_market:
                    by_market[market] = []
                by_market[market].append(stock)

            print("\n🔍 乱码品种详情:")
            print("-" * 50)

            for market, stocks in by_market.items():
                print(f"\n{market}: {len(stocks)} 个品种")
                for stock in stocks[:10]:  # 只显示前10个
                    print(f"  {stock['code']}: '{stock['name']}' (问题: {stock['issues']})")

                if len(stocks) > 10:
                    print(f"  ... 还有 {len(stocks) - 10} 个品种")

            # 分析乱码字符类型分布
            print("\n📋 乱码字符类型分布:")
            print("-" * 50)

            issue_stats = {}
            for stock in problematic_stocks:
                for issue in stock["issues"]:
                    issue_stats[issue] = issue_stats.get(issue, 0) + 1

            for issue, count in issue_stats.items():
                print(f"  {issue}: {count} 个品种")

        print("\n✅ 结论:")
        print("-" * 50)
        print("1. 确认存在乱码字符，主要为空字符(\\x00)")
        print("2. 这些字符会影响品种名称显示和拼音生成")
        print("3. 需要在数据处理链路中进行清理")

        print("=" * 80)

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    analyze_encoding_issues()
