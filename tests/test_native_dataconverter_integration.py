import pytest
import pandas as pd
from datetime import datetime
from backend.infrastructure.data_module_vnpy.data_converter import records_to_bar_fields, bar_fields_to_vnpy_bars

def test_records_to_bar_fields():
    """测试原生数据转换功能"""
    # 准备测试数据
    records = [
        {"datetime": "2023-01-01 09:30:00", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000},
        {"datetime": "2023-01-01 09:31:00", "open": 10.2, "high": 10.8, "low": 10.1, "close": 10.5, "volume": 1200}
    ]
    
    # 执行转换
    symbol = "000001.SZ"
    exchange = "SZSE"
    result = records_to_bar_fields(records, symbol, exchange)
    
    # 验证结果
    assert len(result) == 2
    assert result[0]["symbol"] == symbol
    assert result[0]["exchange"] == exchange
    assert result[0]["open_price"] == 10.0
    assert result[1]["close_price"] == 10.5

def test_bar_fields_to_vnpy_bars():
    """测试转换为vnpy的BarData对象"""
    fields = [
        {"symbol": "000001.SZ", "exchange": "SZSE", "datetime": "2023-01-01 09:30:00", 
         "open_price": 10.0, "high_price": 10.5, "low_price": 9.8, "close_price": 10.2, "volume": 1000},
    ]
    
    # 执行转换
    bars = bar_fields_to_vnpy_bars(fields)
    
    # 验证结果
    assert len(bars) == 1
    bar = bars[0]
    assert bar.symbol == "000001.SZ"
    assert bar.exchange == "SZSE"
    assert bar.open_price == 10.0
    assert bar.close_price == 10.2
