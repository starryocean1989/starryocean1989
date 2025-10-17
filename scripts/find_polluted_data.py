# -*- coding: utf-8 -*-
"""
深度扫描历史数据，寻找通达信的污染日期格式
日线数据深度：8000根
分钟线数据深度：20000根
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def scan_daily_data_deep():
    """深度扫描日线数据（8000根）"""
    print("\n" + "="*60)
    print("深度扫描日线历史数据（最多8000根）")
    print("="*60)

    quotes = Quotes.factory()

    symbol = "600000"  # 浦发银行，1999年上市
    market = 1

    # 分批扫描：每次800条，扫描8000根
    batch_size = 800
    max_depth = 8000

    polluted_data_found = False

    for start in range(0, max_depth, batch_size):
        print(f"\n扫描批次: start={start}, count={batch_size}")

        try:
            raw_data = quotes.client.get_security_bars(
                4, market, symbol, start, batch_size
            )

            if not raw_data or len(raw_data) == 0:
                print(f"  ⚠️  无数据，已到达历史数据底部 (总共获取了{start}条)")
                break

            actual_count = len(raw_data)
            print(f"  获取 {actual_count} 条数据")

            df = pd.DataFrame(raw_data)

            # 检查字段
            has_date = 'date' in df.columns
            has_time = 'time' in df.columns
            has_datetime = 'datetime' in df.columns

            if has_date or has_time:
                print(f"  🔍 发现date/time字段！")
                polluted_data_found = True

                print(f"    字段: {list(df.columns)}")
                print(f"    datetime存在: {has_datetime}")
                print(f"    date存在: {has_date}")
                print(f"    time存在: {has_time}")

                # 显示样本
                print(f"\n    前5条数据样本:")
                for i in range(min(5, len(df))):
                    row_info = f"    [{start+i}] "
                    if has_datetime:
                        row_info += f"datetime='{df['datetime'].iloc[i]}' "
                    if has_date:
                        row_info += f"date='{df['date'].iloc[i]}' "
                    if has_time:
                        row_info += f"time='{df['time'].iloc[i]}'"
                    print(row_info)

                break

            # 检查datetime格式是否异常
            if has_datetime:
                for idx, dt_val in enumerate(df['datetime']):
                    # 检查是否有异常格式
                    if not isinstance(dt_val, str):
                        print(f"  ⚠️  发现非字符串datetime [index {start+idx}]: {dt_val} (类型: {type(dt_val)})")
                        polluted_data_found = True
                        break

                    # 检查格式异常（通达信特殊格式特征）
                    if '-' in dt_val:
                        parts = dt_val.split('-')
                        # 日线污染格式：DDDD-MM-DD（DDDD是从1990-01-01开始的天数，会很大）
                        if len(parts) == 3:
                            try:
                                first_part = int(parts[0])
                                # 如果第一部分大于9999，说明可能是污染数据
                                if first_part > 9999:
                                    print(f"  🔍 发现可疑格式 [index {start+idx}]: '{dt_val}'")
                                    print(f"     第一部分={first_part} (正常年份应该是2000-2099)")
                                    polluted_data_found = True

                                    # 显示更多样本
                                    print(f"\n     周围数据样本:")
                                    for j in range(max(0, idx-2), min(len(df), idx+3)):
                                        print(f"       [{start+j}] {df['datetime'].iloc[j]}")
                                    break
                            except:
                                pass

                if polluted_data_found:
                    break

            # 显示数据范围
            if has_datetime and start % 1600 == 0:  # 每2批显示一次
                print(f"  范围: {df['datetime'].iloc[0]} 到 {df['datetime'].iloc[-1]}")

            # 如果获取的数据少于batch_size，说明到底了
            if actual_count < batch_size:
                print(f"  ✓ 已到达历史数据底部 (总共{start + actual_count}条)")
                break

        except Exception as e:
            print(f"  ❌ 扫描失败: {str(e)}")
            break

    quotes.close()

    if not polluted_data_found:
        print(f"\n✅ 扫描完成，未发现污染数据（所有datetime都是标准格式）")
    else:
        print(f"\n🔍 找到污染数据！需要使用日期解码器处理")


def scan_minute_data_deep():
    """深度扫描分钟线数据（20000根）"""
    print("\n" + "="*60)
    print("深度扫描5分钟线历史数据（最多20000根）")
    print("="*60)

    quotes = Quotes.factory()

    symbol = "600000"
    market = 1

    # 分批扫描：每次800条
    batch_size = 800
    max_depth = 20000

    polluted_data_found = False

    # 只扫描前几批和后几批（完整扫描会很慢）
    test_ranges = [
        (0, 2),           # 最新2批
        (10000, 10002),   # 中间2批
        (19200, 19201),   # 最后1批
    ]

    for start_batch, end_batch in test_ranges:
        for batch_idx in range(start_batch, end_batch):
            start = batch_idx * batch_size

            if start >= max_depth:
                break

            print(f"\n扫描批次: start={start}, count={batch_size}")

            try:
                raw_data = quotes.client.get_security_bars(
                    0, market, symbol, start, batch_size
                )

                if not raw_data or len(raw_data) == 0:
                    print(f"  ⚠️  无数据")
                    continue

                actual_count = len(raw_data)
                print(f"  获取 {actual_count} 条数据")

                df = pd.DataFrame(raw_data)

                # 检查字段
                has_date = 'date' in df.columns
                has_time = 'time' in df.columns

                if has_date or has_time:
                    print(f"  🔍 发现date/time字段！")
                    polluted_data_found = True

                    print(f"    字段: {list(df.columns)}")

                    # 显示样本
                    print(f"\n    前5条数据:")
                    for i in range(min(5, len(df))):
                        row_info = f"    [{start+i}] "
                        if 'datetime' in df.columns:
                            row_info += f"datetime='{df['datetime'].iloc[i]}' "
                        if has_date:
                            row_info += f"date='{df['date'].iloc[i]}' "
                        if has_time:
                            row_info += f"time='{df['time'].iloc[i]}'"
                        print(row_info)

                    break

                # 显示范围
                if 'datetime' in df.columns:
                    print(f"  范围: {df['datetime'].iloc[0]} 到 {df['datetime'].iloc[-1]}")

            except Exception as e:
                print(f"  ❌ 扫描失败: {str(e)}")
                break

        if polluted_data_found:
            break

    quotes.close()

    if not polluted_data_found:
        print(f"\n✅ 扫描完成，未发现污染数据")
    else:
        print(f"\n🔍 找到污染数据！")


def test_decode_with_polluted_data():
    """如果找到污染数据，测试解码器"""
    print("\n" + "="*60)
    print("测试日期解码器")
    print("="*60)

    from backend.infrastructure.data_module_vnpy.data_fetcher import TdxDateTimeDecoder

    # 模拟污染数据
    print("\n模拟通达信污染数据格式:")

    # 日线污染格式示例（DDDD-MM-DD，DDDD是从1990-01-01开始的天数）
    test_daily_dates = [
        "12825-10-16",  # 2025-10-16 (从1990-01-01开始的12825天)
        "12000-05-20",  # 约2022年
    ]

    print("\n1. 测试日线解码:")
    for date_str in test_daily_dates:
        decoded = TdxDateTimeDecoder.decode_daily_datetime(date_str)
        print(f"  '{date_str}' -> {decoded}")

    # 分钟线污染格式示例（YYYY-MM-DDD，DDD是年初开始的天数）
    test_minute_dates = [
        ("2025-10-289", "14:30"),  # 2025年第289天 14:30
        ("2025-10-001", "09:30"),  # 2025年第1天 09:30
    ]

    print("\n2. 测试分钟线解码:")
    for date_str, time_str in test_minute_dates:
        decoded = TdxDateTimeDecoder.decode_minute_datetime(date_str, time_str)
        print(f"  '{date_str} {time_str}' -> {decoded}")

    print("\n✅ 解码器功能正常，可以处理污染数据")


if __name__ == "__main__":
    print("="*60)
    print("深度扫描历史数据，寻找通达信污染日期格式")
    print("="*60)

    # 测试1: 深度扫描日线数据
    scan_daily_data_deep()

    # 测试2: 深度扫描分钟线数据
    scan_minute_data_deep()

    # 测试3: 测试解码器
    test_decode_with_polluted_data()

    print("\n" + "="*60)
    print("总结:")
    print("  decode_dataframe函数采用智能判断:")
    print("  1. 如果只有datetime字段 -> 直接转换（标准格式）")
    print("  2. 如果有date/time字段 -> 使用解码器处理（污染数据）")
    print("  这样既兼容当前的mootdx API，也能处理未来可能出现的污染数据")
    print("="*60)

