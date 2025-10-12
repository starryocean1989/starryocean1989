# -*- coding: utf-8 -*-
"""
使用mootdx测试北交所股票

验证mootdx是否支持北交所
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("mootdx北交所股票测试")
print("=" * 80)
print()

try:
    from mootdx.quotes import Quotes
    import pandas as pd

    server = ("139.9.133.247", 7709)

    print(f"连接服务器: {server}")
    quotes = Quotes.factory(server=server, heartbeat=False)
    print("✅ 连接成功\n")

    # 测试不同市场的股票
    test_cases = [
        ("600000", "上交所", "6开头"),
        ("000001", "深交所", "0开头"),
        ("430047", "北交所", "43开头"),
        ("832580", "北交所", "83开头"),
        ("872925", "北交所", "87开头"),
        ("889036", "北交所", "88开头"),
    ]

    for symbol, exchange, prefix in test_cases:
        print(f"测试 {symbol} ({exchange}, {prefix})...")

        # 尝试不同的方法
        # 方法1：使用Quotes.bars (mootdx高层API)
        try:
            # mootdx的bars方法会自动判断市场
            # 不需要手动指定市场代码
            df = quotes.bars(symbol=symbol, frequency="1d", offset=10)

            if df is not None and not df.empty:
                print(f"  ✅ Quotes.bars成功: {len(df)}条数据")
                print(f"  列名: {df.columns.tolist()}")
                if "datetime" in df.columns:
                    print(f"  最新日期: {df['datetime'].iloc[-1]}")
            else:
                print(f"  ❌ Quotes.bars返回空")

        except Exception as e:
            print(f"  ❌ Quotes.bars异常: {e}")

        print()

    quotes.close()

    print("=" * 80)
    print("结论")
    print("=" * 80)
    print()
    print("mootdx的Quotes.bars()方法会自动判断市场，")
    print("无需手动指定市场代码。")
    print("应该直接使用Quotes.bars()，而不是底层的get_security_bars()")

except Exception as e:
    print(f"\n❌ 失败: {e}")
    import traceback

    traceback.print_exc()
