# -*- coding: utf-8 -*-
"""
测试简化后的多进程下载功能
"""
import sys
from pathlib import Path
from datetime import date, timedelta
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher


def test_simplified_multiprocess():
    """测试简化后的多进程下载"""
    print("\n" + "="*60)
    print("测试简化后的多进程下载功能")
    print("="*60)

    # 创建下载器（使用较少的进程）
    fetcher = MultiProcessStockFetcher()
    fetcher.set_server_count(2)  # 只用2个进程

    # 简单的测试用例
    test_symbols = ["600000"]  # 只测试一个品种
    intervals = ["1d"]         # 只测试日线
    start_date = "2025-10-01"  # 固定日期

    print(f"\n测试参数:")
    print(f"  品种: {test_symbols}")
    print(f"  周期: {intervals}")
    print(f"  开始日期: {start_date}")
    print(f"  预期任务: {len(test_symbols) * len(intervals)} 个")

    # 开始测试
    start_time = time.time()

    try:
        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=intervals,
        )

        elapsed = time.time() - start_time

        print(f"\n" + "="*60)
        print("测试结果")
        print("="*60)
        print(f"耗时: {elapsed:.2f} 秒")
        print(f"返回结果数: {len(results)}")

        # 检查结果
        success_count = 0
        for key, data in results.items():
            if data is not None and not data.empty:
                success_count += 1
                print(f"✅ {key}: {len(data)} 条数据")
                if 'datetime' in data.columns and len(data) > 0:
                    print(f"   时间范围: {data['datetime'].iloc[0]} ~ {data['datetime'].iloc[-1]}")
            elif data is None:
                print(f"❌ {key}: 返回None")
            else:
                print(f"⚠️  {key}: 空数据")

        if success_count > 0:
            print(f"\n🎉 测试成功！成功获取 {success_count} 个有效数据集")
            return True
        else:
            print(f"\n❌ 测试失败：未获取到有效数据")
            return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ 异常失败 (耗时 {elapsed:.2f}秒):")
        print(f"  {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_direct_download():
    """直接测试单个下载函数"""
    print("\n" + "="*60)
    print("测试单个下载函数")
    print("="*60)

    from backend.infrastructure.data_module_vnpy.data_fetcher import _download_single_kline_incremental
    from mootdx.quotes import Quotes

    quotes = Quotes.factory()
    symbol = "600000"
    interval = "1d"
    start_date = "2025-10-01"

    print(f"\n测试: {symbol} {interval} 从 {start_date}")

    try:
        data = _download_single_kline_incremental(quotes, symbol, interval, start_date)

        if data is not None and not data.empty:
            print(f"✅ 成功: {len(data)} 条数据")
            print(f"   列: {list(data.columns)}")
            if 'datetime' in data.columns:
                print(f"   时间范围: {data['datetime'].iloc[0]} ~ {data['datetime'].iloc[-1]}")
            return True
        else:
            print(f"❌ 失败: 返回None或空数据")
            return False

    except Exception as e:
        print(f"❌ 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        quotes.close()


if __name__ == "__main__":
    print("\n🚀 开始测试简化后的多进程下载")

    # 测试1: 单个下载函数
    print("\n【测试1】单个下载函数")
    direct_result = test_direct_download()

    if direct_result:
        # 测试2: 多进程下载
        print("\n\n【测试2】多进程下载")
        multiprocess_result = test_simplified_multiprocess()
    else:
        print("\n⚠️  单个下载失败，跳过多进程测试")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

