# -*- coding: utf-8 -*-
"""
深度扫描1分钟线数据，寻找污染数据
1分钟线数据深度：20000根
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def check_1min_data_pollution(df, symbol, start_idx):
    """检查1分钟线数据的污染"""

    for idx in range(len(df)):
        datetime_str = df['datetime'].iloc[idx]
        year_val = df['year'].iloc[idx]
        month_val = df['month'].iloc[idx]
        day_val = df['day'].iloc[idx]
        hour_val = df['hour'].iloc[idx]
        minute_val = df['minute'].iloc[idx]

        try:
            # datetime格式: "YYYY-MM-DD HH:MM"
            if ' ' in datetime_str:
                date_part, time_part = datetime_str.split(' ')
            else:
                print(f"  ⚠️  异常格式 [index {start_idx + idx}]: 无时间部分 '{datetime_str}'")
                return True

            # 检查日期部分
            dt_parts = date_part.split('-')
            if len(dt_parts) == 3:
                dt_year = int(dt_parts[0])
                dt_month = int(dt_parts[1])
                dt_day = int(dt_parts[2])

                # 检查时间部分
                time_parts = time_part.split(':')
                if len(time_parts) >= 2:
                    dt_hour = int(time_parts[0])
                    dt_minute = int(time_parts[1])
                else:
                    print(f"  ⚠️  时间格式异常 [index {start_idx + idx}]: '{time_part}'")
                    return True

                # 检查数值一致性
                if (dt_year != year_val or dt_month != month_val or dt_day != day_val or
                    dt_hour != hour_val or dt_minute != minute_val):
                    print(f"  🔍 发现数值不一致! [index {start_idx + idx}]")
                    print(f"     datetime显示: {datetime_str}")
                    print(f"     解析结果: {dt_year}-{dt_month:02d}-{dt_day:02d} {dt_hour:02d}:{dt_minute:02d}")
                    print(f"     字段实际值: {year_val}-{month_val:02d}-{day_val:02d} {hour_val:02d}:{minute_val:02d}")

                    # 显示周围数据
                    print(f"     周围数据:")
                    for j in range(max(0, idx-2), min(len(df), idx+3)):
                        dt = df['datetime'].iloc[j]
                        y, m, d, h, mi = df['year'].iloc[j], df['month'].iloc[j], df['day'].iloc[j], df['hour'].iloc[j], df['minute'].iloc[j]
                        print(f"       [{start_idx+j}] {dt} vs {y}-{m:02d}-{d:02d} {h:02d}:{mi:02d}")

                    return True

        except Exception as e:
            print(f"  ❌ 解析失败 [index {start_idx + idx}]: {datetime_str}, error: {e}")
            return True

    return False


def scan_1min_data_deep(symbol, market, symbol_name):
    """深度扫描1分钟线数据"""
    print(f"\n{'='*60}")
    print(f"扫描1分钟线: {symbol} - {symbol_name} (市场代码={market})")
    print(f"{'='*60}")

    quotes = Quotes.factory()

    batch_size = 800
    # 测试策略：扫描不同深度的数据
    # 0-1000: 最新数据
    # 5000-6000: 中期数据
    # 10000-11000: 较早数据
    # 15000-16000: 很早数据
    # 19000-20000: 最早数据
    test_ranges = [
        (0, 2, "最新"),
        (5000//800, 5000//800 + 2, "中期"),
        (10000//800, 10000//800 + 2, "较早"),
        (15000//800, 15000//800 + 2, "很早"),
        (19000//800, 19000//800 + 2, "最早"),
    ]

    for start_batch, end_batch, desc in test_ranges:
        print(f"\n{desc}数据 (批次 {start_batch}-{end_batch}):")

        for batch_idx in range(start_batch, end_batch):
            start = batch_idx * batch_size

            print(f"\n  批次: start={start}, count={batch_size}")

            try:
                raw_data = quotes.client.get_security_bars(
                    8, market, symbol, start, batch_size  # frequency=8 是1分钟
                )

                if not raw_data or len(raw_data) == 0:
                    print(f"    ⚠️  无数据")
                    continue

                actual_count = len(raw_data)
                print(f"    获取 {actual_count} 条数据")

                df = pd.DataFrame(raw_data)

                # 检查字段
                print(f"    字段: {list(df.columns)}")

                # 显示范围
                if 'datetime' in df.columns:
                    print(f"    时间范围: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")

                # 检查是否有date/time字段
                if 'date' in df.columns or 'time' in df.columns:
                    print(f"    🔍 发现date/time字段！")
                    print(f"      date存在: {'date' in df.columns}")
                    print(f"      time存在: {'time' in df.columns}")

                    # 显示样本
                    print(f"\n      前5条样本:")
                    for i in range(min(5, len(df))):
                        info = f"      [{start+i}] "
                        if 'datetime' in df.columns:
                            info += f"datetime='{df['datetime'].iloc[i]}' "
                        if 'date' in df.columns:
                            info += f"date='{df['date'].iloc[i]}' "
                        if 'time' in df.columns:
                            info += f"time='{df['time'].iloc[i]}'"
                        print(info)

                    quotes.close()
                    return True

                # 检查数值污染
                if check_1min_data_pollution(df, symbol, start):
                    print(f"\n    🔍 发现污染数据！")
                    quotes.close()
                    return True

            except Exception as e:
                print(f"    ❌ 失败: {str(e)}")
                if "timed out" not in str(e):
                    import traceback
                    traceback.print_exc()
                break

    quotes.close()
    print(f"\n  ✅ 扫描完成，未发现污染")
    return False


def test_multiple_symbols_1min():
    """测试多个品种的1分钟线"""
    print("\n" + "="*60)
    print("深度扫描多个品种的1分钟线数据")
    print("="*60)

    test_symbols = [
        ("600000", 1, "浦发银行"),
        ("000001", 0, "平安银行"),
        ("600519", 1, "贵州茅台"),
        ("000002", 0, "万科A"),
    ]

    polluted_found = []

    for symbol, market, name in test_symbols:
        if scan_1min_data_deep(symbol, market, name):
            polluted_found.append((symbol, name))

    # 总结
    print("\n" + "="*60)
    print("扫描总结")
    print("="*60)

    if polluted_found:
        print(f"\n发现污染数据的品种:")
        for symbol, name in polluted_found:
            print(f"  - {symbol} ({name})")
    else:
        print(f"\n✅ 所有1分钟线数据都正常")
        print(f"   datetime数值与year/month/day/hour/minute完全一致")


if __name__ == "__main__":
    test_multiple_symbols_1min()

    print("\n" + "="*60)
    print("结论:")
    print("  如果发现date/time字段，说明需要解码器处理")
    print("  如果只有datetime字段且数值正确，说明API已处理污染数据")
    print("="*60)

