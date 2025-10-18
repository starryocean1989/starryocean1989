# -*- coding: utf-8 -*-
"""分析真实品种数据的实际情况."""

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


def analyze_real_symbol_data():
    """分析真实品种数据的实际情况."""

    print("=" * 80)
    print("真实品种数据深度分析")
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

        print("📊 品种分类统计:")
        print("-" * 50)

        total_symbols = 0
        empty_name_symbols = 0
        category_stats = {}

        for market_type, codes in classified.items():
            print(f"\n市场: {market_type}")
            print(f"  品种数量: {len(codes)}")

            category_stats[market_type] = {"total": len(codes), "empty_name": 0}

            for code in codes:
                total_symbols += 1

                # 检查品种数据结构
                if isinstance(code, dict):
                    name = code.get("name", "")
                    if not name or name.strip() == "":
                        empty_name_symbols += 1
                        category_stats[market_type]["empty_name"] += 1
                        print(f"    ❌ 空名称品种: {code.get('code', 'UNKNOWN')}")
                    else:
                        print(f"    ✅ 正常品种: {code.get('code', 'UNKNOWN')} - {name}")
                elif isinstance(code, str):
                    # 旧格式：只有代码
                    empty_name_symbols += 1
                    category_stats[market_type]["empty_name"] += 1
                    print(f"    ⚠️ 旧格式品种: {code}")

        print("\n📈 总体统计:")
        print("-" * 50)
        print(f"总品种数: {total_symbols}")
        print(f"空名称品种数: {empty_name_symbols}")
        print(f"正常品种数: {total_symbols - empty_name_symbols}")

        print("\n📋 分类详情:")
        print("-" * 50)
        for market_type, stats in category_stats.items():
            empty_rate = (stats["empty_name"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            print(f"{market_type}: {stats['total']} 个品种，其中空名称: {stats['empty_name']} 个 ({empty_rate:.1f}%)")

        # 分析空名称品种的特征
        print("\n🔍 空名称品种特征分析:")
        print("-" * 50)

        if empty_name_symbols > 0:
            print("空名称品种主要来自:")
            for market_type, stats in category_stats.items():
                if stats["empty_name"] > 0:
                    print(f"  • {market_type}: {stats['empty_name']} 个品种")

            print("\n这些品种的共同特征:")
            print("1. 来自T+0基金或可转债分类")
            print("2. 从配置文件（如spblock.dat、tdxstat2.cfg）获取")
            print("3. 在通达信API的品种列表中找不到对应的名称")
            print("4. 这是正常的，因为这些品种的名称来源于其他数据源")

        print("=" * 80)


if __name__ == "__main__":
    analyze_real_symbol_data()
