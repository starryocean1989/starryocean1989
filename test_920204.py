# -*- coding: utf-8 -*-
"""测试920204"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from tdxpy.hq import TdxHq_API
    import pandas as pd
    from backend.infrastructure.data_module_vnpy.datetime_decoder import TdxDateTimeDecoder

    server = ("139.9.133.247", 7709)

    print("测试 920204 (9开头)")
    print()

    client = TdxHq_API(heartbeat=False)
    client.connect(server[0], server[1], time_out=5)
    print("✅ 连接成功\n")

    # 测试不同市场代码
    for market_code in [0, 1, 2]:
        print(f"市场代码 {market_code}:")
        data = client.get_security_bars(9, market_code, "920204", 0, 10)

        if data and len(data) > 0:
            print(f"  ✅ 返回 {len(data)} 条数据")
            df = pd.DataFrame(data)
            print(f"  列名: {df.columns.tolist()}")

            # 解码
            df = TdxDateTimeDecoder.decode_dataframe(df, "1d")
            if "vol" in df.columns:
                df["volume"] = df["vol"]

            if "datetime" in df.columns:
                print(f"  最新日期: {df['datetime'].iloc[-1]}")
                print(f"  最新收盘: {df['close'].iloc[-1]}")
        else:
            print(f"  ❌ 返回空")
        print()

    client.close()

    print("使用mootdx测试:")
    from mootdx.quotes import Quotes

    q = Quotes.factory(server=server, heartbeat=False)
    df = q.bars(symbol="920204", frequency="1d", offset=10)

    if df is not None and not df.empty:
        print(f"  ✅ mootdx返回 {len(df)} 条")
    else:
        print(f"  ❌ mootdx返回空")
    q.close()

except Exception as e:
    print(f"错误: {e}")
    import traceback

    traceback.print_exc()
