# -*- coding: utf-8 -*-
"""
测试20年前至今的历史数据
寻找污染数据并验证日期解码器
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd


def test_long_term_historical_data():
    """测试长期历史数据（20年）"""
    print("\n" + "="*60)
    print("测试20年前至今的历史数据")
    print("="*60)
    
    quotes = Quotes.factory()
    
    # 使用一个有长期历史的老股票
    test_stocks = [
        ("000001", 0, "平安银行（深圳）"),
        ("600000", 1, "浦发银行（上海）"),
    ]
    
    for symbol, market, name in test_stocks:
        print(f"\n{'='*60}")
        print(f"测试品种: {symbol} - {name}")
        print(f"{'='*60}")
        
        # 尝试获取大量历史数据（最多800条）
        # 800个交易日大约是3-4年的数据
        # 需要多次请求才能获取20年数据
        
        # 先测试最近的数据
        print(f"\n测试1: 获取最近800条日线数据")
        try:
            raw_data = quotes.client.get_security_bars(
                4, market, symbol, 0, 800
            )
            
            if raw_data and len(raw_data) > 0:
                print(f"  ✅ 成功获取 {len(raw_data)} 条数据")
                
                # 检查字段结构
                first_record = raw_data[0]
                last_record = raw_data[-1]
                
                print(f"\n  字段列表: {list(first_record.keys())}")
                print(f"\n  最新数据 (索引0):")
                print(f"    datetime: {first_record.get('datetime', 'N/A')}")
                print(f"    date: {first_record.get('date', 'N/A')}")
                print(f"    time: {first_record.get('time', 'N/A')}")
                
                print(f"\n  最早数据 (索引{len(raw_data)-1}):")
                print(f"    datetime: {last_record.get('datetime', 'N/A')}")
                print(f"    date: {last_record.get('date', 'N/A')}")
                print(f"    time: {last_record.get('time', 'N/A')}")
                
                # 检查是否有date字段（污染数据的标志）
                has_date_field = 'date' in first_record
                has_datetime_field = 'datetime' in first_record
                
                print(f"\n  数据格式分析:")
                print(f"    包含datetime字段: {has_datetime_field}")
                print(f"    包含date字段: {has_date_field}")
                
                if has_date_field and has_datetime_field:
                    print(f"    ⚠️  同时包含date和datetime字段，可能需要解码")
                elif has_datetime_field and not has_date_field:
                    print(f"    ✅ 只有datetime字段，API已处理好")
                elif has_date_field and not has_datetime_field:
                    print(f"    ⚠️  只有date字段，需要解码器处理")
                
        except Exception as e:
            print(f"  ❌ 获取失败: {str(e)[:200]}")
        
        # 测试更早期的数据（通过start参数）
        print(f"\n测试2: 获取更早期的数据（start=3000）")
        try:
            raw_data = quotes.client.get_security_bars(
                4, market, symbol, 3000, 100
            )
            
            if raw_data and len(raw_data) > 0:
                print(f"  ✅ 成功获取 {len(raw_data)} 条数据")
                
                first_record = raw_data[0]
                print(f"\n  数据示例:")
                print(f"    datetime: {first_record.get('datetime', 'N/A')}")
                print(f"    date: {first_record.get('date', 'N/A')}")
                print(f"    time: {first_record.get('time', 'N/A')}")
                print(f"    open: {first_record.get('open')}")
                
            else:
                print(f"  ⚠️  返回空数据（可能超出历史范围）")
                
        except Exception as e:
            print(f"  ❌ 获取失败: {str(e)[:200]}")
    
    quotes.close()


def test_decode_dataframe_with_date_field():
    """测试带date字段的数据解码"""
    print("\n" + "="*60)
    print("测试decode_dataframe函数处理date字段")
    print("="*60)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import TdxDateTimeDecoder
    
    # 模拟包含date/time字段的污染数据
    # 根据通达信格式：
    # 日线：DDDD-MM-DD（DDDD是从1990-01-01开始的总天数）
    # 分钟线：YYYY-MM-DDD（DDD是年初开始的天数）
    
    print("\n测试1: 日线格式（DDDD-MM-DD）")
    # 假设12775天是从1990-01-01开始，对应约2025年
    test_daily_data = pd.DataFrame([
        {'date': '12775-10-16', 'open': 11.5, 'close': 11.6},
        {'date': '12776-10-17', 'open': 11.6, 'close': 11.7},
    ])
    
    print(f"  原始数据:")
    print(f"    {test_daily_data.to_dict('records')}")
    
    decoded = TdxDateTimeDecoder.decode_dataframe(test_daily_data, "1d")
    
    if not decoded.empty and 'datetime' in decoded.columns:
        print(f"\n  解码后:")
        for idx, row in decoded.iterrows():
            print(f"    datetime: {row.get('datetime')}")
    else:
        print(f"  ⚠️  解码失败或返回空")
    
    print("\n测试2: 分钟线格式（YYYY-MM-DDD）")
    # 假设2025-10-290（290是年初开始的天数）
    test_minute_data = pd.DataFrame([
        {'date': '2025-10-290', 'time': '14:30', 'open': 11.5, 'close': 11.6},
        {'date': '2025-10-290', 'time': '14:35', 'open': 11.6, 'close': 11.7},
    ])
    
    print(f"  原始数据:")
    print(f"    {test_minute_data.to_dict('records')}")
    
    decoded = TdxDateTimeDecoder.decode_dataframe(test_minute_data, "5m")
    
    if not decoded.empty and 'datetime' in decoded.columns:
        print(f"\n  解码后:")
        for idx, row in decoded.iterrows():
            print(f"    datetime: {row.get('datetime')}")
    else:
        print(f"  ⚠️  解码失败或返回空")
    
    print("\n测试3: 标准datetime字符串（mootdx API格式）")
    test_standard_data = pd.DataFrame([
        {'datetime': '2025-10-16 15:00', 'open': 11.5, 'close': 11.6},
        {'datetime': '2025-10-17 15:00', 'open': 11.6, 'close': 11.7},
    ])
    
    print(f"  原始数据:")
    print(f"    {test_standard_data.to_dict('records')}")
    
    decoded = TdxDateTimeDecoder.decode_dataframe(test_standard_data, "1d")
    
    if not decoded.empty and 'datetime' in decoded.columns:
        print(f"\n  解码后:")
        print(f"    datetime类型: {decoded['datetime'].dtype}")
        for idx, row in decoded.iterrows():
            print(f"    datetime: {row.get('datetime')}")
    else:
        print(f"  ⚠️  解码失败或返回空")


def test_complete_download_with_decoder():
    """测试完整的下载流程（包含解码器）"""
    print("\n" + "="*60)
    print("测试完整下载流程")
    print("="*60)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import (
        _download_single_kline_incremental
    )
    from mootdx.quotes import Quotes
    from datetime import date, timedelta
    
    quotes = Quotes.factory()
    
    # 测试获取长期历史数据
    start_date = (date.today() - timedelta(days=365*3)).strftime("%Y-%m-%d")  # 3年前
    
    test_cases = [
        ("000001", "1d", "平安银行-日线-3年"),
        ("600000", "1d", "浦发银行-日线-3年"),
    ]
    
    for symbol, interval, description in test_cases:
        print(f"\n测试: {description}")
        print(f"  开始日期: {start_date}")
        
        try:
            data = _download_single_kline_incremental(
                quotes, symbol, interval, start_date
            )
            
            if data is not None and not data.empty:
                print(f"  ✅ 成功: {len(data)}条数据")
                print(f"  列名: {list(data.columns)}")
                print(f"  datetime类型: {data['datetime'].dtype}")
                print(f"  首行datetime: {data.iloc[0].get('datetime', 'N/A')}")
                print(f"  末行datetime: {data.iloc[-1].get('datetime', 'N/A')}")
                
                # 检查datetime是否有效
                invalid_count = data['datetime'].isna().sum()
                print(f"  无效datetime数量: {invalid_count}")
                
            else:
                print(f"  ❌ 失败: 返回None或空DataFrame")
                
        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")
    
    quotes.close()


if __name__ == "__main__":
    print("\n🚀 开始测试污染数据和日期解码器")
    
    # 测试1: 获取长期历史数据，寻找污染数据
    test_long_term_historical_data()
    
    # 测试2: 测试decode_dataframe函数
    test_decode_dataframe_with_date_field()
    
    # 测试3: 测试完整下载流程
    test_complete_download_with_decoder()
    
    print("\n✅ 测试完成")

