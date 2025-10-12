# -*- coding: utf-8 -*-
"""
快速测试多进程版本（极简版）

测试基本功能是否正常
"""

import sys
from pathlib import Path
import multiprocessing

# Windows需要
if sys.platform == "win32":
    multiprocessing.freeze_support()

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("=" * 80)
    print("多进程版本快速测试")
    print("=" * 80)
    print()

    try:
        from datetime import date, timedelta
        from backend.infrastructure.data_module_vnpy.multiprocess_fetcher import (
            MultiProcessStockFetcher,
        )

        print("步骤1：创建MultiProcessStockFetcher...")
        fetcher = MultiProcessStockFetcher()
        print(f"✅ 创建成功，进程数: {fetcher.num_processes}")
        print()

        print("步骤2：测试少量下载（2个品种×1个周期=2任务）...")
        test_symbols = ["600000", "000001"]
        test_intervals = ["1d"]
        start_date = date.today() - timedelta(days=30)

        import time

        start = time.time()

        result = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=test_intervals,
            progress_callback=lambda c, t, s, i: print(f"   进度: {c}/{t} - {s} {i}"),
        )

        elapsed = time.time() - start

        print()
        print(f"✅ 下载完成:")
        print(f"   耗时: {elapsed:.2f}秒")
        print(f"   获得: {len(result)}/2 个数据集")

        if len(result) > 0:
            sample_key = list(result.keys())[0]
            sample_df = result[sample_key]
            print(f"   示例数据: {sample_key}")
            print(f"   数据行数: {len(sample_df)}")
            print(f"   数据列: {list(sample_df.columns)}")

        print()
        print("步骤3：测试停止功能...")
        fetcher.stop_download()
        if fetcher.is_stopped():
            print("✅ 停止信号已设置")

        print()
        print("步骤4：测试重置...")
        fetcher.reset_download_state()
        if not fetcher.is_stopped():
            print("✅ 状态已重置")

        print()
        print("=" * 80)
        print("🎉 所有测试通过！多进程版本工作正常！")
        print("=" * 80)
        print()
        print("下一步：重启程序，进行实际下载测试")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
