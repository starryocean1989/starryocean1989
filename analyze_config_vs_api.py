# -*- coding: utf-8 -*-
"""分析来自配置文件的品种与通达信API品种的匹配情况."""

import sys
import os
import json
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def analyze_config_vs_api():
    """分析来自配置文件的品种与通达信API品种的匹配情况."""

    print("=" * 80)
    print("配置文件品种 vs 通达信API品种匹配分析")
    print("=" * 80)

    try:
        from backend.infrastructure.data_module_vnpy.config import config_manager

        cache_dir = config_manager.get_cache_dir()
        json_cache_file = cache_dir / "stock_list_classified.json"

        if not json_cache_file.exists():
            print(f"❌ 缓存文件不存在: {json_cache_file}")
            return

        # 读取品种缓存数据
        with open(json_cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        classified = cache_data.get("classified", {})

        print("📊 品种来源分析:")
        print("-" * 50)

        # 1. 分析通达信API品种（集合D）
        api_stocks = []
        for market_type, codes in classified.items():
            if market_type in ["上证A股", "深证A股", "北证A股"]:
                for code in codes:
                    if isinstance(code, dict):
                        api_stocks.append({
                            "code": code.get("code", ""),
                            "name": code.get("name", ""),
                            "market": code.get("market", ""),
                            "source": "通达信API"
                        })

        print(f"通达信API品种数量: {len(api_stocks)}")

        # 2. 分析配置文件品种（T+0基金、可转债、北证A股）
        config_stocks = []
        unmatched_stocks = []

        for market_type, codes in classified.items():
            if market_type in ["T+0基金", "可转债", "北证A股"]:
                print(f"\n📁 {market_type} 来源分析:")
                print(f"  总数量: {len(codes)}")

                for code in codes:
                    if isinstance(code, dict):
                        stock_info = {
                            "code": code.get("code", ""),
                            "name": code.get("name", ""),
                            "market": code.get("market", ""),
                            "source": f"配置文件({market_type})"
                        }
                        config_stocks.append(stock_info)

                        # 检查是否在API品种中找到匹配
                        found_in_api = False
                        for api_stock in api_stocks:
                            if (api_stock["code"] == stock_info["code"] and
                                api_stock["market"] == stock_info["market"]):
                                found_in_api = True
                                break

                        if not found_in_api:
                            unmatched_stocks.append(stock_info)
                            print(f"    ❌ 找不到API匹配: {stock_info['code']} - '{stock_info['name']}'")
                        else:
                            print(f"    ✅ 找到API匹配: {stock_info['code']} - '{stock_info['name']}'")

        print("\n📈 总体统计:")
        print("-" * 50)
        print(f"通达信API品种: {len(api_stocks)} 个")
        print(f"配置文件品种: {len(config_stocks)} 个")
        print(f"在API中找不到的品种: {len(unmatched_stocks)} 个")

        # 3. 详细分析找不到匹配的品种
        print("\n🔍 在API中找不到的品种详情:")
        print("-" * 50)

        if unmatched_stocks:
            print(f"找到 {len(unmatched_stocks)} 个在通达信API中找不到的品种:")

            # 按来源分类
            by_source = {}
            for stock in unmatched_stocks:
                source = stock["source"]
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(stock)

            for source, stocks in by_source.items():
                print(f"\n{source}: {len(stocks)} 个品种")
                for stock in stocks[:10]:  # 只显示前10个
                    print(f"  • {stock['code']} - '{stock['name']}' (市场: {stock['market']})")

                if len(stocks) > 10:
                    print(f"  ... 还有 {len(stocks) - 10} 个品种")

        # 4. 验证结论
        print("\n✅ 结论验证:")
        print("-" * 50)

        if unmatched_stocks:
            print("✓ 证实了确实存在在通达信API中找不到的品种")
            print("✓ 这些品种主要来自配置文件，且无法在API品种列表中找到对应的名称")
            print("✓ 这是正常的，因为这些品种的定义来源于其他数据源")

            # 统计来源分布
            source_stats = {}
            for stock in unmatched_stocks:
                source = stock["source"]
                source_stats[source] = source_stats.get(source, 0) + 1

            print("\n来源分布:")
            for source, count in source_stats.items():
                print(f"  • {source}: {count} 个品种")

        else:
            print("✓ 所有配置文件品种都在通达信API中找到了对应项")

        print("=" * 80)


if __name__ == "__main__":
    analyze_config_vs_api()
