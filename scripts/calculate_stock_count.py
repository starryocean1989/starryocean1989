#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算品种总数脚本
"""

import sys
import os
import logging

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
backend_path = os.path.join(project_root, "backend")
sys.path.insert(0, backend_path)

try:
    from backend.infrastructure.data_module_vnpy.stock_fetcher import StockFetcher
    from backend.infrastructure.data_module_vnpy.block_parser import BlockParser
    from backend.infrastructure.data_module_vnpy.config import config_manager
    import pandas as pd

    # 设置日志级别避免过多输出
    logging.basicConfig(level=logging.WARNING)

    print("开始计算品种总数...")

    # 初始化股票获取器
    try:
        stock_fetcher = StockFetcher()
        print("✓ StockFetcher初始化成功")

        # 获取所有股票
        print("调用 fetch_all_stocks()...")
        stocks_df = stock_fetcher.fetch_all_stocks()
        print(f"API返回品种总数: {len(stocks_df)}")

        if stocks_df is not None and not stocks_df.empty:
            print(f"品种DataFrame形状: {stocks_df.shape}")
            print(f"列名: {list(stocks_df.columns)}")

            # 解析分类
            print("开始解析品种分类...")
            classified = stock_fetcher.parse_market_codes(stocks_df)

            # 统计各分类数量
            total_count = 0
            for category, stocks in classified.items():
                count = len(stocks)
                total_count += count
                print(f"{category}: {count} 个")

            print(f"分类后总品种数: {total_count}")

            # 打印前几个品种示例
            print("\n各分类前3个品种示例:")
            for category, stocks in classified.items():
                if stocks:
                    print(f"{category}: {stocks[:3]}")

        else:
            print("❌ 获取的品种数据为空")

    except Exception as e:
        print(f"❌ 计算过程中出错: {e}")
        import traceback

        traceback.print_exc()

except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保在正确的项目目录中运行此脚本")
except Exception as e:
    print(f"❌ 脚本执行失败: {e}")
    import traceback

    traceback.print_exc()
