# -*- coding: utf-8 -*-
"""
测试北交所股票数据获取
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("北交所股票数据测试")
print("=" * 80)
print()

try:
    from tdxpy.hq import TdxHq_API
    import pandas as pd
    from backend.infrastructure.data_module_vnpy.datetime_decoder import TdxDateTimeDecoder
    
    server = ("139.9.133.247", 7709)
    
    print(f"连接服务器: {server}")
    client = TdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)
    client.connect(server[0], server[1], time_out=5)
    print("✅ 连接成功\n")
    
    # 测试北交所股票
    test_symbols = [
        ("430047", "北交所"),  # 4开头
        ("832580", "北交所"),  # 8开头  
        ("900957", "北交所"),  # 9开头
        ("600000", "上交所"),  # 6开头
        ("000001", "深交所"),  # 0开头
    ]
    
    for symbol, exchange in test_symbols:
        print(f"测试 {symbol} ({exchange})...")
        
        # 确定市场代码
        if symbol.startswith(("6", "688")):
            market = 1  # 上海
        elif symbol.startswith(("8", "9", "4")):
            market = 2  # 北交所
        else:
            market = 0  # 深圳
        
        print(f"  市场代码: {market}")
        
        # 获取日线数据
        data = client.get_security_bars(9, market, symbol, 0, 10)
        
        if data:
            df = pd.DataFrame(data)
            print(f"  ✅ 获取成功: {len(df)}条数据")
            print(f"  列名: {df.columns.tolist()}")
            
            # 解码
            df = TdxDateTimeDecoder.decode_dataframe(df, "1d")
            if "vol" in df.columns:
                df["volume"] = df["vol"]
            
            if not df.empty and "datetime" in df.columns:
                print(f"  最新日期: {df['datetime'].iloc[-1]}")
        else:
            print(f"  ❌ 返回空数据")
        
        print()
    
    client.close()
    
    print("=" * 80)
    print("🎉 测试完成")
    print("=" * 80)
    
except Exception as e:
    print(f"\n❌ 失败: {e}")
    import traceback
    traceback.print_exc()

