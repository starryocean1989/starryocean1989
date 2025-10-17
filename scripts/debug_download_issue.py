# -*- coding: utf-8 -*-
"""
调试多进程下载问题
"""
import sys
from pathlib import Path
from datetime import date, timedelta, datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes


def test_offset_calculation():
    """测试offset计算逻辑"""
    print("\n" + "="*60)
    print("测试offset计算")
    print("="*60)

    test_dates = [
        ("2025-10-13", 3, "3天前"),
        ("2025-10-10", 6, "6天前"),
        ("2025-10-06", 10, "10天前"),
        ("2025-09-16", 30, "30天前"),
    ]

    for start_date_str, expected_days, desc in test_dates:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        days_diff = (date.today() - start_date).days

        print(f"\n{desc} ({start_date_str}):")
        print(f"  实际天数差: {days_diff} 天")

        # 计算各周期的offset
        offset_1d = min(int(days_diff * 1.5), 800)
        offset_5m = min(int(days_diff * 50), 800)
        offset_1m = min(int(days_diff * 250), 800)

        print(f"  1d offset: {offset_1d} (公式: min(int({days_diff} * 1.5), 800))")
        print(f"  5m offset: {offset_5m} (公式: min(int({days_diff} * 50), 800))")
        print(f"  1m offset: {offset_1m} (公式: min(int({days_diff} * 250), 800))")

        # 检查是否合理
        if offset_1d < 5:
            print(f"  ⚠️  1d offset 太小: {offset_1d}")


def test_direct_api_call():
    """直接测试API调用"""
    print("\n" + "="*60)
    print("直接测试API调用")
    print("="*60)

    quotes = Quotes.factory()

    symbol = "600000"
    market = 1
    frequency = 4  # 日线
    start_date_str = "2025-10-13"

    # 计算offset
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    days_diff = (date.today() - start_date).days
    offset = min(int(days_diff * 1.5), 800)

    print(f"\n测试参数:")
    print(f"  symbol: {symbol}")
    print(f"  market: {market}")
    print(f"  frequency: {frequency}")
    print(f"  start_date: {start_date_str}")
    print(f"  days_diff: {days_diff}")
    print(f"  offset: {offset}")

    print(f"\n调用: quotes.client.get_security_bars({frequency}, {market}, '{symbol}', 0, {offset})")

    try:
        raw_data = quotes.client.get_security_bars(
            int(frequency), int(market), str(symbol), 0, int(offset)
        )

        if raw_data:
            print(f"  ✅ 成功: 获取 {len(raw_data)} 条数据")
            if len(raw_data) > 0:
                print(f"  首条: {raw_data[0]}")
        else:
            print(f"  ⚠️  返回None或空列表")
            print(f"  raw_data: {raw_data}")

    except Exception as e:
        print(f"  ❌ 调用失败: {str(e)}")
        import traceback
        traceback.print_exc()

    quotes.close()


def test_download_function_directly():
    """直接测试_download_single_kline_incremental函数"""
    print("\n" + "="*60)
    print("直接测试_download_single_kline_incremental函数")
    print("="*60)

    from backend.infrastructure.data_module_vnpy.data_fetcher import (
        _download_single_kline_incremental
    )

    quotes = Quotes.factory()

    symbol = "600000"
    interval = "1d"
    start_date = "2025-10-13"

    print(f"\n测试参数:")
    print(f"  symbol: {symbol}")
    print(f"  interval: {interval}")
    print(f"  start_date: {start_date}")

    try:
        result = _download_single_kline_incremental(
            quotes, symbol, interval, start_date
        )

        if result is not None and not result.empty:
            print(f"\n✅ 成功:")
            print(f"  返回类型: {type(result)}")
            print(f"  数据条数: {len(result)}")
            print(f"  列: {list(result.columns)}")
            if 'datetime' in result.columns:
                print(f"  时间范围: {result['datetime'].iloc[0]} ~ {result['datetime'].iloc[-1]}")
        elif result is not None:
            print(f"\n⚠️  返回空DataFrame")
            print(f"  类型: {type(result)}")
            print(f"  列: {list(result.columns) if hasattr(result, 'columns') else 'N/A'}")
        else:
            print(f"\n❌ 返回None")

    except Exception as e:
        print(f"\n❌ 调用失败: {str(e)}")
        import traceback
        traceback.print_exc()

    quotes.close()


def test_with_larger_offset():
    """测试使用更大的offset"""
    print("\n" + "="*60)
    print("测试使用固定的较大offset")
    print("="*60)

    from backend.infrastructure.data_module_vnpy.data_fetcher import (
        _download_single_kline_incremental
    )

    quotes = Quotes.factory()

    # 使用更早的日期来获得更大的offset
    symbol = "600000"
    interval = "1d"
    start_date = "2025-09-01"  # 更早的日期

    print(f"\n测试参数:")
    print(f"  symbol: {symbol}")
    print(f"  interval: {interval}")
    print(f"  start_date: {start_date}")

    try:
        result = _download_single_kline_incremental(
            quotes, symbol, interval, start_date
        )

        if result is not None and not result.empty:
            print(f"\n✅ 成功:")
            print(f"  数据条数: {len(result)}")
            if 'datetime' in result.columns:
                print(f"  时间范围: {result['datetime'].iloc[0]} ~ {result['datetime'].iloc[-1]}")
        else:
            print(f"\n⚠️  返回None或空")

    except Exception as e:
        print(f"\n❌ 失败: {str(e)}")
        import traceback
        traceback.print_exc()

    quotes.close()


if __name__ == "__main__":
    # 测试1: offset计算
    test_offset_calculation()

    # 测试2: 直接API调用
    test_direct_api_call()

    # 测试3: 测试_download_single_kline_incremental函数
    test_download_function_directly()

    # 测试4: 使用更大的offset
    test_with_larger_offset()

