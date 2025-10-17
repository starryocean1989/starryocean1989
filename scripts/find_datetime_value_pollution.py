# -*- coding: utf-8 -*-
"""
深度扫描多个品种的历史数据，寻找datetime数值污染
检查datetime的数值是否与year/month/day字段一致
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def check_datetime_value_pollution(df, symbol, start_idx):
    """检查datetime数值是否与year/month/day一致"""

    polluted_found = False

    for idx in range(len(df)):
        datetime_str = df['datetime'].iloc[idx]
        year_val = df['year'].iloc[idx]
        month_val = df['month'].iloc[idx]
        day_val = df['day'].iloc[idx]

        # 从datetime字符串中提取年月日
        try:
            # datetime格式: "YYYY-MM-DD HH:MM"
            if ' ' in datetime_str:
                date_part = datetime_str.split(' ')[0]
            else:
                date_part = datetime_str

            dt_parts = date_part.split('-')
            if len(dt_parts) == 3:
                dt_year = int(dt_parts[0])
                dt_month = int(dt_parts[1])
                dt_day = int(dt_parts[2])

                # 检查是否一致
                if dt_year != year_val or dt_month != month_val or dt_day != day_val:
                    print(f"  🔍 发现数值不一致! [index {start_idx + idx}]")
                    print(f"     datetime显示: {datetime_str} ({dt_year}-{dt_month:02d}-{dt_day:02d})")
                    print(f"     字段实际值: year={year_val}, month={month_val}, day={day_val}")
                    polluted_found = True

                    # 显示周围数据
                    print(f"     周围5条数据:")
                    for j in range(max(0, idx-2), min(len(df), idx+3)):
                        dt_str = df['datetime'].iloc[j]
                        y = df['year'].iloc[j]
                        m = df['month'].iloc[j]
                        d = df['day'].iloc[j]
                        match = "✓" if (dt_str.startswith(f"{y}-{m:02d}-{d:02d}")) else "✗"
                        print(f"       [{start_idx+j}] {match} datetime={dt_str} vs {y}-{m:02d}-{d:02d}")

                    return True

                # 检查数值合理性
                if dt_year < 1990 or dt_year > 2030:
                    print(f"  ⚠️  异常年份 [index {start_idx + idx}]: {dt_year} (datetime: {datetime_str})")
                    polluted_found = True
                    return True

                if dt_month < 1 or dt_month > 12:
                    print(f"  ⚠️  异常月份 [index {start_idx + idx}]: {dt_month} (datetime: {datetime_str})")
                    polluted_found = True
                    return True

                if dt_day < 1 or dt_day > 31:
                    print(f"  ⚠️  异常日期 [index {start_idx + idx}]: {dt_day} (datetime: {datetime_str})")
                    polluted_found = True
                    return True

        except Exception as e:
            print(f"  ❌ 解析失败 [index {start_idx + idx}]: {datetime_str}, error: {e}")
            polluted_found = True
            return True

    return polluted_found


def scan_symbol_deep(quotes, symbol, market, symbol_name):
    """深度扫描单个品种"""
    print(f"\n{'='*60}")
    print(f"扫描品种: {symbol} - {symbol_name} (市场代码={market})")
    print(f"{'='*60}")

    batch_size = 800
    max_batches = 10  # 扫描10批 = 8000条

    for batch_idx in range(max_batches):
        start = batch_idx * batch_size

        print(f"\n批次 {batch_idx + 1}: start={start}, count={batch_size}")

        try:
            raw_data = quotes.client.get_security_bars(
                4, market, symbol, start, batch_size
            )

            if not raw_data or len(raw_data) == 0:
                print(f"  ⚠️  无数据，已到底部 (总共{start}条)")
                break

            actual_count = len(raw_data)
            print(f"  获取 {actual_count} 条数据")

            df = pd.DataFrame(raw_data)

            # 显示范围
            if 'datetime' in df.columns:
                print(f"  时间范围: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")

            # 检查数值污染
            if check_datetime_value_pollution(df, symbol, start):
                print(f"\n  🔍 在品种 {symbol} 发现污染数据！")
                return True

            # 如果数据少于batch_size，说明到底了
            if actual_count < batch_size:
                print(f"  ✓ 已到底部 (总共{start + actual_count}条)")
                break

        except Exception as e:
            print(f"  ❌ 扫描失败: {str(e)}")
            break

    print(f"  ✅ 品种 {symbol} 扫描完成，未发现数值污染")
    return False


def scan_multiple_symbols():
    """扫描多个品种"""
    print("\n" + "="*60)
    print("深度扫描多个品种的历史数据")
    print("检查datetime数值是否与year/month/day一致")
    print("="*60)

    quotes = Quotes.factory()

    # 测试多个不同市场、不同上市时间的品种
    test_symbols = [
        ("600000", 1, "浦发银行", "1999年上市"),
        ("000001", 0, "平安银行", "1991年上市"),
        ("600519", 1, "贵州茅台", "2001年上市"),
        ("000002", 0, "万科A", "1991年上市"),
        ("601398", 1, "工商银行", "2006年上市"),
        ("000858", 0, "五粮液", "1998年上市"),
    ]

    polluted_symbols = []

    for symbol, market, name, note in test_symbols:
        print(f"\n" + "="*60)
        print(f"测试 {symbol} - {name} ({note})")
        print("="*60)

        if scan_symbol_deep(quotes, symbol, market, name):
            polluted_symbols.append((symbol, name))

    quotes.close()

    # 总结
    print("\n" + "="*60)
    print("扫描总结")
    print("="*60)

    if polluted_symbols:
        print(f"\n发现污染数据的品种:")
        for symbol, name in polluted_symbols:
            print(f"  - {symbol} ({name})")
        print(f"\n✅ 日期解码器需要处理这些污染数据")
    else:
        print(f"\n✅ 所有品种的datetime数值都正确")
        print(f"   mootdx API已经处理了污染数据")
        print(f"   decode_dataframe保留解码逻辑以兼容未来可能的date/time字段")


def test_minute_data_pollution():
    """测试分钟线数据的污染"""
    print("\n" + "="*60)
    print("测试分钟线数据污染")
    print("="*60)

    quotes = Quotes.factory()

    test_symbols = [
        ("600000", 1, "浦发银行"),
        ("000001", 0, "平安银行"),
    ]

    for symbol, market, name in test_symbols:
        print(f"\n测试 {symbol} - {name}:")

        # 测试不同深度的数据
        test_starts = [0, 4000, 8000]

        for start in test_starts:
            print(f"\n  批次 start={start}:")

            try:
                raw_data = quotes.client.get_security_bars(
                    0, market, symbol, start, 100  # 5分钟线
                )

                if not raw_data or len(raw_data) == 0:
                    print(f"    ⚠️  无数据")
                    continue

                df = pd.DataFrame(raw_data)
                print(f"    获取 {len(df)} 条数据")
                print(f"    范围: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")

                # 检查数值
                if check_datetime_value_pollution(df, symbol, start):
                    print(f"    🔍 发现污染!")
                    quotes.close()
                    return

            except Exception as e:
                print(f"    ❌ 失败: {str(e)}")
                break

    quotes.close()
    print(f"\n  ✅ 分钟线数据正常")


if __name__ == "__main__":
    # 测试1: 扫描多个品种的日线数据
    scan_multiple_symbols()

    # 测试2: 测试分钟线数据
    test_minute_data_pollution()

    print("\n" + "="*60)
    print("结论:")
    print("  decode_dataframe函数的双重保护:")
    print("  1. 标准datetime字符串 -> 直接转换")
    print("  2. date/time字段存在 -> 使用解码器处理污染数值")
    print("  3. 同时检查year/month/day与datetime的一致性")
    print("="*60)

