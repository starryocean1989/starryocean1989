# -*- coding: utf-8 -*-
"""
详细调试_download_single_kline_incremental函数
"""
import sys
from pathlib import Path
from datetime import date, timedelta, datetime
import logging
import traceback

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes
import pandas as pd

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_step_by_step():
    """逐步测试每个环节"""
    print("\n" + "="*60)
    print("逐步调试_download_single_kline_incremental")
    print("="*60)

    symbol = "600000"
    interval = "1d"
    start_date_str = "2025-10-06"
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

    print(f"\n参数:")
    print(f"  symbol: {symbol}")
    print(f"  interval: {interval}")
    print(f"  start_date: {start_date}")

    # 创建quotes实例
    quotes = Quotes.factory()

    # 步骤1: 计算天数差
    days_diff = (date.today() - start_date).days
    print(f"\n步骤1: 计算天数差")
    print(f"  days_diff: {days_diff}")

    # 步骤2: 确定频率参数
    frequency_map = {
        "1d": 4,
        "5m": 0,
        "1m": 8,
    }
    frequency = frequency_map.get(interval, 4)
    print(f"\n步骤2: 确定频率参数")
    print(f"  frequency: {frequency}")

    # 步骤3: 计算offset
    if interval == "1d":
        offset = min(int(days_diff * 1.5), 800)
    elif interval == "5m":
        offset = min(int(days_diff * 50), 800)
    elif interval == "1m":
        offset = min(int(days_diff * 250), 800)
    else:
        offset = 800
    print(f"\n步骤3: 计算offset")
    print(f"  offset: {offset}")

    # 步骤4: 确定市场代码
    if symbol.startswith("6"):
        market = 1
    elif any(symbol.startswith(prefix) for prefix in ["43", "83", "87", "88"]):
        market = 2
    else:
        market = 0
    print(f"\n步骤4: 确定市场代码")
    print(f"  market: {market}")

    # 步骤5: 调用API
    print(f"\n步骤5: 调用API")
    print(f"  调用: quotes.client.get_security_bars({frequency}, {market}, '{symbol}', 0, {offset})")
    try:
        raw_data = quotes.client.get_security_bars(
            int(frequency), int(market), str(symbol), 0, int(offset)
        )
        print(f"  ✅ API调用成功")
        print(f"  返回数据条数: {len(raw_data) if raw_data else 0}")
        if raw_data and len(raw_data) > 0:
            print(f"  首条数据: {raw_data[0]}")
    except Exception as e:
        print(f"  ❌ API调用失败: {e}")
        traceback.print_exc()
        quotes.close()
        return

    if not raw_data:
        print(f"  ⚠️ API返回空数据")
        quotes.close()
        return

    # 步骤6: 转换为DataFrame
    print(f"\n步骤6: 转换为DataFrame")
    try:
        data = pd.DataFrame(raw_data)
        print(f"  ✅ DataFrame创建成功")
        print(f"  shape: {data.shape}")
        print(f"  columns: {list(data.columns)}")
        print(f"  dtypes:\n{data.dtypes}")
    except Exception as e:
        print(f"  ❌ DataFrame创建失败: {e}")
        traceback.print_exc()
        quotes.close()
        return

    # 步骤7: 解码日期
    print(f"\n步骤7: 解码日期 (decode_dataframe)")
    try:
        # 导入decode函数
        from backend.infrastructure.data_module_vnpy.data_fetcher import TdxDateTimeDecoder

        data_decoded = TdxDateTimeDecoder.decode_dataframe(data, interval)
        print(f"  ✅ 解码成功")
        print(f"  shape: {data_decoded.shape}")
        print(f"  columns: {list(data_decoded.columns)}")
        if not data_decoded.empty:
            print(f"  首行datetime: {data_decoded['datetime'].iloc[0]}")
            print(f"  datetime类型: {data_decoded['datetime'].dtype}")
    except Exception as e:
        print(f"  ❌ 解码失败: {e}")
        traceback.print_exc()
        quotes.close()
        return

    # 步骤8: 设置index
    print(f"\n步骤8: 设置index")
    try:
        if not data_decoded.empty and "datetime" in data_decoded.columns:
            data_indexed = data_decoded.set_index("datetime", drop=False)
            print(f"  ✅ index设置成功")
            print(f"  index类型: {data_indexed.index.dtype}")
        else:
            data_indexed = data_decoded
            print(f"  ⚠️ 数据为空或无datetime列，跳过index设置")
    except Exception as e:
        print(f"  ❌ index设置失败: {e}")
        traceback.print_exc()
        quotes.close()
        return

    # 步骤9: 标准化列名
    print(f"\n步骤9: 标准化列名 (_standardize_columns)")
    try:
        from backend.infrastructure.data_module_vnpy.data_fetcher import _standardize_columns

        data_std = _standardize_columns(data_indexed, symbol, interval)
        print(f"  ✅ 标准化成功")
        print(f"  shape: {data_std.shape}")
        print(f"  columns: {list(data_std.columns)}")
    except Exception as e:
        print(f"  ❌ 标准化失败: {e}")
        traceback.print_exc()
        quotes.close()
        return

    # 步骤10: 过滤日期
    print(f"\n步骤10: 过滤日期 (_filter_by_date)")
    try:
        from backend.infrastructure.data_module_vnpy.data_fetcher import _filter_by_date

        data_filtered = _filter_by_date(data_std, start_date)
        print(f"  ✅ 过滤成功")
        print(f"  shape: {data_filtered.shape}")
        if not data_filtered.empty:
            print(f"  首行datetime: {data_filtered['datetime'].iloc[0]}")
            print(f"  末行datetime: {data_filtered['datetime'].iloc[-1]}")
    except Exception as e:
        print(f"  ❌ 过滤失败: {e}")
        traceback.print_exc()
        quotes.close()
        return

    quotes.close()
    print(f"\n✅ 全部步骤完成！")


if __name__ == "__main__":
    test_step_by_step()

