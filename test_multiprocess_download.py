# -*- coding: utf-8 -*-
"""
测试多进程下载功能

对比多线程vs多进程的性能差异
"""

import sys
from pathlib import Path
from datetime import date, timedelta
import time

# Windows multiprocessing需要freeze_support
import multiprocessing

if sys.platform == "win32":
    multiprocessing.freeze_support()

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("=" * 80)
    print("多进程下载功能测试")
    print("=" * 80)
    print()

    try:
        print("步骤1：导入模块...")
        from backend.infrastructure.data_module_vnpy.multiprocess_fetcher import (
            MultiProcessStockFetcher,
        )
        from backend.infrastructure.data_module_vnpy.stock_fetcher import StockFetcher

        print("✅ 模块导入成功")

        # 测试数据
        test_symbols = ["600000", "000001", "600036", "000002"]  # 4个品种
        test_intervals = ["1d", "5m"]  # 2个周期
        start_date = date.today() - timedelta(days=30)
        total_tasks = len(test_symbols) * len(test_intervals)

        print(f"\n测试数据:")
        print(f"  品种: {test_symbols}")
        print(f"  周期: {test_intervals}")
        print(f"  总任务: {total_tasks}")
        print(f"  开始日期: {start_date}")
        print()

        # 测试1：多线程版本（原版）
        print("=" * 80)
        print("测试1：多线程版本（原版）")
        print("=" * 80)
        print()

        fetcher_thread = StockFetcher()
        print(f"创建StockFetcher成功，服务器数: {fetcher_thread.server_pool.max_servers}")

        start = time.time()
        result_thread = fetcher_thread.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=test_intervals,
            progress_callback=lambda c, t, s, i: print(f"  线程版进度: {c}/{t}"),
        )
        elapsed_thread = time.time() - start

        print(f"\n✅ 多线程下载完成:")
        print(f"   耗时: {elapsed_thread:.2f}秒")
        print(f"   获得: {len(result_thread)}/{total_tasks} 个数据集")
        print(f"   速度: {len(result_thread)/elapsed_thread:.1f}个/秒")
        print()

        # 测试2：多进程版本（新版）
        print("=" * 80)
        print("测试2：多进程版本（新版）")
        print("=" * 80)
        print()

        fetcher_process = MultiProcessStockFetcher()
        print(f"创建MultiProcessStockFetcher成功，进程数: {fetcher_process.num_processes}")

        start = time.time()
        result_process = fetcher_process.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=test_intervals,
            progress_callback=lambda c, t, s, i: print(f"  进程版进度: {c}/{t}"),
        )
        elapsed_process = time.time() - start

        print(f"\n✅ 多进程下载完成:")
        print(f"   耗时: {elapsed_process:.2f}秒")
        print(f"   获得: {len(result_process)}/{total_tasks} 个数据集")
        print(f"   速度: {len(result_process)/elapsed_process:.1f}个/秒")
        print()

        # 性能对比
        print("=" * 80)
        print("性能对比")
        print("=" * 80)
        print()

        speedup = elapsed_thread / elapsed_process if elapsed_process > 0 else 0

        print(f"多线程版本: {elapsed_thread:.2f}秒")
        print(f"多进程版本: {elapsed_process:.2f}秒")
        print(f"提速倍数: {speedup:.2f}x")
        print()

        if speedup >= 1.5:
            print(f"🎉 多进程版本快 {speedup:.1f}倍！性能提升显著！")
        elif speedup >= 1.0:
            print(f"✅ 多进程版本稍快 {speedup:.1f}倍")
        else:
            print(f"⚠️ 多进程版本反而慢了（可能是进程创建开销）")
            print("   建议：任务数少时使用线程，任务数多时使用进程")

        print()
        print("=" * 80)
        print("🎉 测试完成！")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
