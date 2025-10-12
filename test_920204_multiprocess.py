# -*- coding: utf-8 -*-
"""测试多进程版本获取920204"""

import sys
from pathlib import Path
import multiprocessing

if sys.platform == "win32":
    multiprocessing.freeze_support()

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("=" * 80)
    print("测试多进程版本获取920204北交所股票")
    print("=" * 80)
    print()

    try:
        from backend.infrastructure.data_module_vnpy.multiprocess_fetcher import (
            MultiProcessStockFetcher,
        )
        from datetime import date, timedelta

        fetcher = MultiProcessStockFetcher()
        print(f"创建fetcher成功，进程数: {fetcher.num_processes}")
        print()

        # 测试920204
        print("下载920204北交所股票...")
        result = fetcher.download_incremental_kline(
            symbols=["920204"],
            start_date=date.today() - timedelta(days=30),
            intervals=["1d"],
            progress_callback=lambda c, t, s, i: print(f"  进度: {c}/{t} - {s} {i}"),
        )

        print()
        if result and "920204_1d" in result:
            df = result["920204_1d"]
            print(f"✅ 成功获取920204数据:")
            print(f"   数据行数: {len(df)}")
            print(f"   数据列: {df.columns.tolist()}")
            print(f"   最新日期: {df['datetime'].iloc[-1]}")
            print(f"   最新收盘: {df['close'].iloc[-1]}")
        else:
            print(f"❌ 未获取到920204数据")
            print(f"   返回结果: {list(result.keys()) if result else '空'}")

        print()
        print("=" * 80)

    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
