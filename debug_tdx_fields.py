# -*- coding: utf-8 -*-
"""
调试TdxHq_API返回的字段结构
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("调试TdxHq_API字段结构")
print("=" * 80)
print()

try:
    from tdxpy.hq import TdxHq_API
    import pandas as pd
    from datetime import datetime

    # 连接一个服务器
    server = ("139.9.133.247", 7709)

    print(f"连接服务器: {server}")
    client = TdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)
    client.connect(server[0], server[1], time_out=5)
    print("✅ 连接成功")
    print()

    # 测试获取数据
    print("测试1：获取600000日线数据...")
    data = client.get_security_bars(9, 0, "600000", 0, 10)

    if data:
        print(f"✅ 返回数据类型: {type(data)}")
        print(f"✅ 数据条数: {len(data)}")

        if len(data) > 0:
            print(f"\n第一条数据:")
            first_row = data[0]
            print(f"  类型: {type(first_row)}")
            print(f"  内容: {first_row}")

            if isinstance(first_row, dict):
                print(f"\n字段列表:")
                for key, value in first_row.items():
                    print(f"  - {key}: {value} (类型: {type(value).__name__})")

        # 转换为DataFrame
        print(f"\n转换为DataFrame...")
        df = pd.DataFrame(data)
        print(f"✅ DataFrame形状: {df.shape}")
        print(f"✅ DataFrame列名: {df.columns.tolist()}")
        print(f"\nDataFrame前3行:")
        print(df.head(3))

        # 检查字段
        print(f"\n字段检查:")
        has_vol = "vol" in df.columns
        has_volume = "volume" in df.columns
        has_datetime = "datetime" in df.columns

        print(f"  - 有'vol': {has_vol}")
        print(f"  - 有'volume': {has_volume}")
        print(f"  - 有'datetime': {has_datetime}")

    else:
        print("❌ 返回None或空")

    print()
    print("测试2：使用mootdx Quotes.bars...")
    from mootdx.quotes import Quotes
    from datetime import date

    quotes = Quotes.factory(server=server)
    df2 = quotes.bars(symbol="600000", frequency="1d", start=date(2024, 10, 1), end=date.today())

    if df2 is not None and not df2.empty:
        print(f"✅ Quotes.bars返回: {df2.shape}")
        print(f"✅ 列名: {df2.columns.tolist()}")
        print(f"\n前3行:")
        print(df2.head(3))
    else:
        print("❌ Quotes.bars返回空")

    client.close()

    print()
    print("=" * 80)
    print("🎉 调试完成")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ 失败: {e}")
    import traceback

    traceback.print_exc()
