# -*- coding: utf-8 -*-
"""
简化的多进程测试 - 使用更少的品种和更短的等待时间
"""
import sys
from pathlib import Path
from datetime import date, timedelta
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher


def quick_test():
    """快速测试"""
    print("\n快速测试多进程下载（1个品种，1个周期）")
    print("="*60)

    fetcher = MultiProcessStockFetcher()
    fetcher.set_server_count(2)  # 只用2个进程加快速度

    # 最简单的测试
    test_symbols = ["600000"]
    intervals = ["1d"]
    start_date = "2025-10-01"  # 使用固定日期

    print(f"测试: {test_symbols[0]} - {intervals[0]} - 从{start_date}")

    start_time = time.time()

    try:
        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=intervals,
        )

        elapsed = time.time() - start_time

        print(f"\n结果:")
        print(f"  耗时: {elapsed:.2f}秒")
        print(f"  返回键: {list(results.keys())}")

        for key, data in results.items():
            if data is not None and not data.empty:
                print(f"  ✅ {key}: {len(data)}条数据")
                return True
            elif data is not None:
                print(f"  ⚠️  {key}: 空DataFrame")
            else:
                print(f"  ❌ {key}: None")

        return False

    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = quick_test()

    if result:
        print("\n✅ 多进程下载功能正常")
    else:
        print("\n❌ 多进程下载功能异常")

