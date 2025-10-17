# -*- coding: utf-8 -*-
"""
测试历史数据的日期格式
验证长期历史数据是否包含需要解码的污染日期
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def test_historical_data_format():
    """测试不同时期的历史数据格式"""
    print("\n" + "="*60)
    print("测试历史数据的日期格式")
    print("="*60)

    quotes = Quotes.factory()

    symbol = "000001"  # 平安银行
    market = 0

    # 测试不同起始位置的数据（获取不同时期的历史数据）
    test_cases = [
        (0, 10, "最新10条数据（近期）"),
        (100, 10, "往前100条开始的10条数据"),
        (500, 10, "往前500条开始的10条数据"),
        (700, 10, "往前700条开始的10条数据（长期历史）"),
    ]

    for start, count, description in test_cases:
        print(f"\n{description} (start={start}, count={count}):")

        try:
            # 获取日线数据
            raw_data = quotes.client.get_security_bars(
                4, market, symbol, start, count
            )

            if not raw_data or len(raw_data) == 0:
                print(f"  ⚠️  返回空数据")
                continue

            print(f"  获取 {len(raw_data)} 条数据")

            # 检查第一条数据的字段
            first_record = raw_data[0]
            print(f"  字段列表: {list(first_record.keys())}")

            # 检查日期相关字段
            if 'datetime' in first_record:
                print(f"  datetime字段存在: '{first_record['datetime']}' (类型: {type(first_record['datetime']).__name__})")

            if 'date' in first_record:
                print(f"  date字段存在: '{first_record['date']}' (类型: {type(first_record['date']).__name__})")

            if 'time' in first_record:
                print(f"  time字段存在: '{first_record['time']}' (类型: {type(first_record['time']).__name__})")

            # 显示前3条的datetime/date字段
            print(f"  前3条数据的日期信息:")
            for i, record in enumerate(raw_data[:3]):
                datetime_val = record.get('datetime', 'N/A')
                date_val = record.get('date', 'N/A')
                time_val = record.get('time', 'N/A')
                print(f"    [{i}] datetime='{datetime_val}', date='{date_val}', time='{time_val}'")

        except Exception as e:
            print(f"  ❌ 调用失败: {str(e)[:200]}")

    quotes.close()

    print("\n" + "="*60)
    print("结论:")
    print("  如果所有数据的datetime都是标准格式字符串，说明API已经处理好了")
    print("  如果存在date/time字段且格式特殊，说明需要解码器处理污染数据")
    print("="*60)


def test_minute_data_format():
    """测试分钟线数据格式"""
    print("\n" + "="*60)
    print("测试分钟线数据的日期格式")
    print("="*60)

    quotes = Quotes.factory()

    symbol = "000001"
    market = 0

    # 测试1分钟和5分钟数据
    test_cases = [
        (8, "1分钟"),
        (0, "5分钟"),
    ]

    for frequency, name in test_cases:
        print(f"\n{name}线 (frequency={frequency}):")

        try:
            raw_data = quotes.client.get_security_bars(
                frequency, market, symbol, 0, 5
            )

            if not raw_data or len(raw_data) == 0:
                print(f"  ⚠️  返回空数据")
                continue

            print(f"  获取 {len(raw_data)} 条数据")

            # 检查第一条数据
            first_record = raw_data[0]
            print(f"  字段: {list(first_record.keys())}")

            datetime_val = first_record.get('datetime', 'N/A')
            date_val = first_record.get('date', 'N/A')
            time_val = first_record.get('time', 'N/A')

            print(f"  datetime: '{datetime_val}'")
            print(f"  date: '{date_val}'")
            print(f"  time: '{time_val}'")

        except Exception as e:
            print(f"  ❌ 调用失败: {str(e)[:200]}")

    quotes.close()


if __name__ == "__main__":
    # 测试日线历史数据
    test_historical_data_format()

    # 测试分钟线数据
    test_minute_data_format()

