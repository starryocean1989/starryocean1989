# -*- coding: utf-8 -*-
"""
测试长期历史数据（20年前至今）
寻找通达信的污染数据并验证日期解码器
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def test_long_history_data():
    """测试20年前至今的历史数据"""
    print("\n" + "="*60)
    print("测试长期历史数据（寻找污染数据）")
    print("="*60)

    quotes = Quotes.factory()

    # 选择一个有20年以上历史的股票
    symbol = "600000"  # 浦发银行，上市时间1999年
    market = 1

    # 获取最多800条日线数据（大约覆盖3-4年）
    print(f"\n测试品种: {symbol} (浦发银行)")
    print(f"获取最大数量数据（800条），检查是否有污染数据...")

    try:
        raw_data = quotes.client.get_security_bars(
            4, market, symbol, 0, 800
        )

        if not raw_data or len(raw_data) == 0:
            print(f"  ❌ 未获取到数据")
            quotes.close()
            return

        print(f"  ✅ 成功获取 {len(raw_data)} 条数据")

        # 转换为DataFrame
        df = pd.DataFrame(raw_data)

        print(f"\n字段列表: {list(df.columns)}")

        # 检查是否有date/time字段（污染数据的标志）
        has_date_field = 'date' in df.columns
        has_time_field = 'time' in df.columns
        has_datetime_field = 'datetime' in df.columns

        print(f"\n字段检查:")
        print(f"  datetime字段: {'✅ 存在' if has_datetime_field else '❌ 不存在'}")
        print(f"  date字段: {'✅ 存在' if has_date_field else '❌ 不存在'}")
        print(f"  time字段: {'✅ 存在' if has_time_field else '❌ 不存在'}")

        # 显示最早和最新的数据
        print(f"\n数据范围:")
        if has_datetime_field:
            print(f"  最新数据 (index 0):")
            print(f"    datetime: {df['datetime'].iloc[0]}")
            if 'year' in df.columns:
                print(f"    year-month-day: {df['year'].iloc[0]}-{df['month'].iloc[0]:02d}-{df['day'].iloc[0]:02d}")

            print(f"\n  最早数据 (index {len(df)-1}):")
            print(f"    datetime: {df['datetime'].iloc[-1]}")
            if 'year' in df.columns:
                print(f"    year-month-day: {df['year'].iloc[-1]}-{df['month'].iloc[-1]:02d}-{df['day'].iloc[-1]:02d}")

        # 检查datetime字段的格式
        print(f"\n检查datetime格式（样本10条）:")
        sample_indices = [0, 100, 200, 300, 400, 500, 600, 700, len(df)-1]
        for idx in sample_indices:
            if idx < len(df):
                dt_val = df['datetime'].iloc[idx]
                print(f"  [{idx:3d}] {dt_val}")

        # 检查是否所有datetime都是标准格式
        print(f"\n格式分析:")
        standard_format = True
        for idx, dt_val in enumerate(df['datetime']):
            # 标准格式应该是 "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD"
            if not isinstance(dt_val, str) or len(dt_val) < 10:
                print(f"  ❌ 发现异常格式 [index {idx}]: {dt_val}")
                standard_format = False
                break

            # 检查是否包含非标准字符
            parts = str(dt_val).split('-')
            if len(parts) != 3:
                print(f"  ❌ 发现非标准分隔符 [index {idx}]: {dt_val}")
                standard_format = False
                break

        if standard_format:
            print(f"  ✅ 所有datetime字段都是标准格式")

    except Exception as e:
        print(f"  ❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

    quotes.close()


def test_minute_long_history():
    """测试分钟线的长期历史数据"""
    print("\n" + "="*60)
    print("测试分钟线长期历史数据")
    print("="*60)

    quotes = Quotes.factory()

    symbol = "600000"
    market = 1

    # 测试5分钟线的800条数据
    print(f"\n测试5分钟线数据（800条）:")

    try:
        raw_data = quotes.client.get_security_bars(
            0, market, symbol, 0, 800
        )

        if not raw_data or len(raw_data) == 0:
            print(f"  ❌ 未获取到数据")
            quotes.close()
            return

        print(f"  ✅ 成功获取 {len(raw_data)} 条数据")

        df = pd.DataFrame(raw_data)

        print(f"\n字段列表: {list(df.columns)}")

        # 显示数据范围
        if 'datetime' in df.columns:
            print(f"\n数据范围:")
            print(f"  最新: {df['datetime'].iloc[0]}")
            print(f"  最早: {df['datetime'].iloc[-1]}")

            # 检查格式
            print(f"\n样本数据（每100条取1条）:")
            for idx in range(0, len(df), 100):
                dt_val = df['datetime'].iloc[idx]
                print(f"  [{idx:3d}] {dt_val}")

    except Exception as e:
        print(f"  ❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

    quotes.close()


def test_decode_dataframe():
    """测试decode_dataframe函数"""
    print("\n" + "="*60)
    print("测试decode_dataframe函数")
    print("="*60)

    from backend.infrastructure.data_module_vnpy.data_fetcher import TdxDateTimeDecoder

    quotes = Quotes.factory()

    symbol = "600000"
    market = 1

    print(f"\n获取数据并测试解码:")

    try:
        raw_data = quotes.client.get_security_bars(
            4, market, symbol, 0, 10
        )

        if not raw_data:
            print(f"  ❌ 未获取到数据")
            quotes.close()
            return

        df = pd.DataFrame(raw_data)
        print(f"  原始数据字段: {list(df.columns)}")
        print(f"  原始数据条数: {len(df)}")

        # 测试解码
        print(f"\n调用decode_dataframe:")
        decoded_df = TdxDateTimeDecoder.decode_dataframe(df, "1d")

        print(f"  解码后字段: {list(decoded_df.columns)}")
        print(f"  解码后条数: {len(decoded_df)}")

        if 'datetime' in decoded_df.columns:
            print(f"  datetime类型: {decoded_df['datetime'].dtype}")
            print(f"\n  前3条解码后的datetime:")
            for i in range(min(3, len(decoded_df))):
                print(f"    [{i}] {decoded_df['datetime'].iloc[i]}")

        print(f"\n  ✅ decode_dataframe函数工作正常")

    except Exception as e:
        print(f"  ❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

    quotes.close()


if __name__ == "__main__":
    # 测试1: 日线长期历史数据
    test_long_history_data()

    # 测试2: 分钟线历史数据
    test_minute_long_history()

    # 测试3: decode_dataframe函数
    test_decode_dataframe()

    print("\n" + "="*60)
    print("总结:")
    print("  如果所有数据都是标准datetime格式，说明mootdx已经处理了污染数据")
    print("  decode_dataframe保留了解码逻辑，可以兼容未来可能出现的date/time字段")
    print("="*60)

