# -*- coding: utf-8 -*-
"""
单独测试_download_single_kline_incremental函数
"""
import sys
from pathlib import Path
from datetime import date, timedelta
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_direct_api_call():
    """直接测试API调用"""
    print("\n" + "="*60)
    print("测试直接API调用")
    print("="*60)

    # 测试数据
    test_cases = [
        ("600000", 1, 4, "1d", "上海-浦发银行-日线"),
        ("000001", 0, 4, "1d", "深圳-平安银行-日线"),
        ("600000", 1, 0, "5m", "上海-浦发银行-5分钟"),
        ("000001", 0, 0, "5m", "深圳-平安银行-5分钟"),
        ("600000", 1, 8, "1m", "上海-浦发银行-1分钟"),
        ("000001", 0, 8, "1m", "深圳-平安银行-1分钟"),
    ]

    # 创建Quotes实例
    quotes = Quotes.factory()

    for symbol, market, frequency, interval, description in test_cases:
        print(f"\n测试: {description}")
        print(f"  参数: symbol={symbol}, market={market}, frequency={frequency}")

        try:
            # 调用API
            raw_data = quotes.client.get_security_bars(
                int(frequency), int(market), str(symbol), 0, 10
            )

            if raw_data:
                print(f"  ✅ 成功: 获取{len(raw_data)}条数据")
                if len(raw_data) > 0:
                    print(f"  首条: {raw_data[0]}")
            else:
                print(f"  ❌ 失败: 返回None或空列表")
                print(f"  raw_data类型: {type(raw_data)}")

        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")
            logger.error(f"调用失败", exc_info=True)

    quotes.close()


def test_with_date_calculation():
    """测试带日期计算的完整逻辑"""
    print("\n" + "="*60)
    print("测试带日期计算的完整下载逻辑")
    print("="*60)

    from backend.infrastructure.data_module_vnpy.data_fetcher import (
        _download_single_kline_incremental
    )
    import traceback

    quotes = Quotes.factory()

    # 测试数据
    start_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")

    test_cases = [
        ("600000", "1d", "上海-浦发银行-日线"),
        ("000001", "1d", "深圳-平安银行-日线"),
        ("600000", "5m", "上海-浦发银行-5分钟"),
        ("000001", "5m", "深圳-平安银行-5分钟"),
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
                if len(data) > 0:
                    print(f"  首行datetime: {data.iloc[0].get('datetime', 'N/A')}")
            else:
                print(f"  ❌ 失败: 返回None或空DataFrame")
                print(f"  data类型: {type(data)}")
                if data is not None:
                    print(f"  data.empty: {data.empty}")

        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")
            print("  完整错误堆栈:")
            traceback.print_exc()

    quotes.close()


def test_offset_calculation():
    """测试offset计算逻辑"""
    print("\n" + "="*60)
    print("测试offset计算逻辑")
    print("="*60)

    from datetime import datetime

    start_date_str = "2025-10-06"
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    days_diff = (date.today() - start_date).days

    print(f"\n开始日期: {start_date}")
    print(f"天数差: {days_diff}天")

    # 计算各周期的offset
    intervals = {
        "1d": min(int(days_diff * 1.5), 800),
        "5m": min(int(days_diff * 50), 800),
        "1m": min(int(days_diff * 250), 800),
    }

    for interval, offset in intervals.items():
        print(f"\n{interval}:")
        print(f"  计算公式: {interval} -> days_diff * 系数")
        print(f"  计算结果: offset = {offset}")
        print(f"  是否合理: {'✅' if 0 < offset <= 800 else '❌'}")


if __name__ == "__main__":
    print("\n🚀 开始单元测试")

    # 测试1: offset计算
    test_offset_calculation()

    # 测试2: 直接API调用
    test_direct_api_call()

    # 测试3: 完整下载逻辑
    test_with_date_calculation()

    print("\n✅ 测试完成")

