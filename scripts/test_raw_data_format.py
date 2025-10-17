# -*- coding: utf-8 -*-
"""
测试原始API返回的数据格式
"""
import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes


def test_raw_data_format():
    """测试原始数据格式"""
    print("\n" + "="*60)
    print("测试原始API返回的数据格式")
    print("="*60)

    quotes = Quotes.factory()

    test_cases = [
        ("600000", 1, 4, "日线"),
        ("600000", 1, 0, "5分钟"),
        ("600000", 1, 8, "1分钟"),
    ]

    for symbol, market, frequency, description in test_cases:
        print(f"\n{description} (frequency={frequency}):")

        # 获取原始数据
        raw_data = quotes.client.get_security_bars(
            int(frequency), int(market), str(symbol), 0, 3
        )

        if raw_data and len(raw_data) > 0:
            print(f"  数据条数: {len(raw_data)}")
            print(f"  数据类型: {type(raw_data)}")
            print(f"  首条数据类型: {type(raw_data[0])}")
            print(f"  首条数据键: {list(raw_data[0].keys())}")
            print(f"  首条数据:")
            for key, value in raw_data[0].items():
                print(f"    {key}: {value} (类型: {type(value).__name__})")

            # 转换为DataFrame
            df = pd.DataFrame(raw_data)
            print(f"\n  DataFrame列: {list(df.columns)}")
            print(f"  DataFrame dtypes:")
            for col in df.columns:
                print(f"    {col}: {df[col].dtype}")

            # 检查datetime/date/time字段
            if 'datetime' in df.columns:
                print(f"\n  datetime字段存在!")
                print(f"    首个值: {df['datetime'].iloc[0]}")
                print(f"    类型: {type(df['datetime'].iloc[0])}")

            if 'date' in df.columns:
                print(f"\n  date字段存在!")
                print(f"    首个值: {df['date'].iloc[0]}")
                print(f"    类型: {type(df['date'].iloc[0])}")

            if 'time' in df.columns:
                print(f"\n  time字段存在!")
                print(f"    首个值: {df['time'].iloc[0]}")
                print(f"    类型: {type(df['time'].iloc[0])}")
        else:
            print(f"  ❌ 未获取到数据")

    quotes.close()


if __name__ == "__main__":
    test_raw_data_format()

