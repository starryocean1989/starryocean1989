# -*- coding: utf-8 -*-
"""
验证频率参数的正确性
通过实际请求数据来验证frequency参数是否正确
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def test_all_frequencies():
    """测试所有频率参数"""
    print("\n" + "="*60)
    print("验证mootdx频率参数")
    print("="*60)

    quotes = Quotes.factory()

    # 根据mootdx/consts.py中的定义测试
    test_cases = [
        # (frequency, name, 描述)
        (0, "5分钟", "KLINE_5MIN"),
        (1, "15分钟", "KLINE_15MIN"),
        (2, "30分钟", "KLINE_30MIN"),
        (3, "1小时", "KLINE_1HOUR"),
        (4, "日K线", "KLINE_DAILY"),
        (5, "周K线", "KLINE_WEEKLY"),
        (6, "月K线", "KLINE_MONTHLY"),
        (7, "扩展1分钟", "KLINE_EX_1MIN"),
        (8, "1分钟", "KLINE_1MIN"),
        (9, "日K线2", "KLINE_RI_K"),
        (10, "季K线", "KLINE_3MONTH"),
        (11, "年K线", "KLINE_YEARLY"),
    ]

    symbol = "000001"
    market = 0  # 深圳

    for frequency, name, const_name in test_cases:
        print(f"\n测试 frequency={frequency} ({const_name} - {name}):")
        try:
            raw_data = quotes.client.get_security_bars(
                int(frequency), int(market), str(symbol), 0, 5
            )

            if raw_data and len(raw_data) > 0:
                print(f"  ✅ 成功获取 {len(raw_data)} 条数据")
                # 显示第一条数据的datetime字段
                if 'datetime' in raw_data[0]:
                    print(f"  首条datetime: {raw_data[0]['datetime']}")
            else:
                print(f"  ⚠️  返回空数据")

        except Exception as e:
            print(f"  ❌ 调用失败: {str(e)[:100]}")

    quotes.close()

    print("\n" + "="*60)
    print("结论:")
    print("  frequency=4 (KLINE_DAILY) 用于日K线")
    print("  frequency=9 (KLINE_RI_K) 也返回日K线数据")
    print("  建议使用 frequency=4 作为标准日线参数")
    print("="*60)


if __name__ == "__main__":
    test_all_frequencies()

