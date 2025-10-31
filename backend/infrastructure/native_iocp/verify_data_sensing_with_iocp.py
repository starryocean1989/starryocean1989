# -*- coding: utf-8 -*-
"""
使用IOCP实现单线程多协程的数据感知验证

模拟真实的数据感知场景：
- 并发扫描多个品种的数据文件
- 读取Parquet文件检查数据质量
- 验证不使用线程池，纯多协程异步I/O
"""

import asyncio
import sys
import platform
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional
import tempfile
import os

# 确保在项目路径中
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 仅Windows平台支持
if platform.system() != "Windows":
    print("⚠️ 此脚本仅支持Windows平台（IOCP）")
    sys.exit(1)

# 导入依赖
try:
    import pandas as pd
    import pyarrow.parquet as pq
except ImportError:
    print("❌ 需要安装pandas和pyarrow")
    print("   请运行: pip install pandas pyarrow")
    sys.exit(1)

# 尝试导入IOCP模块
try:
    from backend.infrastructure.native_iocp import aopen, AsyncIOCPFile
    from backend.infrastructure.native_iocp.compat import is_iocp_available, get_backend
    IOCP_AVAILABLE = True
except ImportError as e:
    print(f"❌ 无法导入IOCP模块: {e}")
    print("   提示: 可能需要先编译C扩展，或使用兼容层")
    # 尝试使用兼容层
    try:
        from backend.infrastructure.native_iocp.compat import aopen
        IOCP_AVAILABLE = False
        print("⚠️ 使用兼容层（可能降级到aiofiles）")
    except ImportError:
        sys.exit(1)


class ThreadCounter:
    """线程计数器（用于验证单线程）"""

    def __init__(self):
        self.initial_count = threading.active_count()
        self.initial_threads = [t.name for t in threading.enumerate()]
        self.snapshots: List[Dict] = []

    def snapshot(self, label: str):
        """记录线程快照"""
        current_count = threading.active_count()
        current_threads = [t.name for t in threading.enumerate()]
        new_threads = [t for t in current_threads if t not in self.initial_threads]

        snapshot = {
            "label": label,
            "count": current_count,
            "new_threads": new_threads,
            "time": time.time(),
        }
        self.snapshots.append(snapshot)

        if new_threads:
            print(f"  ⚠️  [{label}] 线程数: {current_count} (新增: {new_threads})")
        else:
            print(f"  ✅ [{label}] 线程数: {current_count} (无新增)")

    def verify(self) -> bool:
        """验证线程数未增加"""
        final_count = self.snapshots[-1]["count"] if self.snapshots else self.initial_count
        return final_count == self.initial_count


async def read_parquet_file_iocp(file_path: Path) -> Optional[pd.DataFrame]:
    """
    使用IOCP异步读取Parquet文件

    Args:
        file_path: 文件路径

    Returns:
        DataFrame或None
    """
    try:
        # 读取文件数据（二进制）
        file = await aopen(file_path, 'rb')
        async with file:
            data = await file.read()

        # 从内存中解析Parquet
        import io
        buffer = io.BytesIO(data)
        df = pd.read_parquet(buffer)
        return df
    except Exception as e:
        print(f"  读取失败 {file_path.name}: {e}")
        return None


async def scan_symbol_quality_iocp(
    symbol: str,
    data_dir: Path,
    intervals: List[str],
    thread_counter: ThreadCounter
) -> Dict:
    """
    使用IOCP异步扫描单个品种的数据质量

    Args:
        symbol: 品种代码
        data_dir: 数据目录
        intervals: 周期列表
        thread_counter: 线程计数器

    Returns:
        品种质量信息
    """
    thread_counter.snapshot(f"扫描开始: {symbol}")

    interval_results = {}
    has_data = False

    for interval in intervals:
        file_path = data_dir / symbol / interval / "data.parquet"

        if not file_path.exists():
            interval_results[interval] = {
                "has_data": False,
                "error": "文件不存在",
            }
            continue

        # 使用IOCP异步读取Parquet文件
        thread_counter.snapshot(f"读取文件: {symbol}/{interval}")

        df = await read_parquet_file_iocp(file_path)

        thread_counter.snapshot(f"读取完成: {symbol}/{interval}")

        if df is None or df.empty:
            interval_results[interval] = {
                "has_data": False,
                "record_count": 0,
            }
            continue

        # 数据存在
        has_data = True
        record_count = len(df)

        # 基本质量检查
        has_datetime = "datetime" in df.columns
        errors = []
        if not has_datetime:
            errors.append("缺少datetime列")

        interval_results[interval] = {
            "has_data": True,
            "record_count": record_count,
            "is_valid": len(errors) == 0,
            "errors": errors,
        }

    thread_counter.snapshot(f"扫描完成: {symbol}")

    return {
        "symbol": symbol,
        "has_data": has_data,
        "intervals": interval_results,
    }


async def data_sensing_with_iocp(
    symbols: List[str],
    data_dir: Path,
    intervals: List[str],
    max_concurrent: int = 10,
    thread_counter: ThreadCounter = None
) -> List[Dict]:
    """
    使用IOCP进行数据感知（单线程多协程）

    Args:
        symbols: 品种列表
        data_dir: 数据目录
        intervals: 周期列表
        max_concurrent: 最大并发数
        thread_counter: 线程计数器

    Returns:
        扫描结果列表
    """
    print(f"\n🚀 开始数据感知（使用IOCP）")
    print(f"   品种数量: {len(symbols)}")
    print(f"   周期列表: {intervals}")
    print(f"   最大并发: {max_concurrent}")
    print(f"   IOCP可用: {is_iocp_available() if IOCP_AVAILABLE else 'N/A'}")
    print(f"   当前后端: {get_backend() if IOCP_AVAILABLE else 'compat'}")

    if thread_counter:
        thread_counter.snapshot("数据感知开始")

    # 使用信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    async def scan_with_semaphore(symbol: str):
        async with semaphore:
            return await scan_symbol_quality_iocp(symbol, data_dir, intervals, thread_counter or ThreadCounter())

    # 并发扫描所有品种（真正的多协程并发，不使用线程池）
    start_time = time.time()

    tasks = [scan_with_semaphore(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

    if thread_counter:
        thread_counter.snapshot("数据感知完成")

    print(f"\n✅ 数据感知完成")
    print(f"   总耗时: {elapsed:.3f}秒")
    print(f"   平均速度: {len(symbols) / elapsed:.2f} 品种/秒")

    # 统计结果
    valid_results = [r for r in results if isinstance(r, dict) and not isinstance(r, Exception)]
    success_count = sum(1 for r in valid_results if r.get("has_data", False))

    print(f"   成功扫描: {success_count}/{len(valid_results)}")

    return valid_results


def create_test_data_structure(base_dir: Path, symbols: List[str], intervals: List[str]) -> None:
    """创建测试数据目录结构"""
    print(f"\n📝 创建测试数据目录结构...")

    for symbol in symbols:
        for interval in intervals:
            symbol_dir = base_dir / symbol / interval
            symbol_dir.mkdir(parents=True, exist_ok=True)

            # 创建测试Parquet文件
            df = pd.DataFrame({
                "datetime": pd.date_range("2024-01-01", periods=100, freq="D"),
                "open": [100.0 + i * 0.1 for i in range(100)],
                "high": [101.0 + i * 0.1 for i in range(100)],
                "low": [99.0 + i * 0.1 for i in range(100)],
                "close": [100.5 + i * 0.1 for i in range(100)],
                "volume": [1000 + i * 10 for i in range(100)],
            })

            file_path = symbol_dir / "data.parquet"
            df.to_parquet(file_path, index=False)

    print(f"✅ 创建完成: {base_dir}")


async def main():
    """主函数"""
    print("=" * 70)
    print("🧪 验证单线程多协程数据感知（使用IOCP，不使用线程池）")
    print("=" * 70)

    # 检查IOCP可用性
    if IOCP_AVAILABLE:
        if not is_iocp_available():
            print("⚠️ IOCP不可用，将使用兼容层")
        else:
            backend = get_backend()
            print(f"✅ 使用后端: {backend}")
            if backend != 'iocp':
                print("⚠️ 当前后端不是IOCP，可能使用线程池")
    else:
        print("⚠️ 使用兼容层（可能使用aiofiles/线程池）")

    # 初始化线程计数器
    thread_counter = ThreadCounter()

    print(f"\n📊 初始线程状态")
    print(f"   线程数: {threading.active_count()}")
    print(f"   线程列表: {[t.name for t in threading.enumerate()]}")

    # 创建测试数据
    test_dir = Path(tempfile.mkdtemp(prefix="iocp_data_sensing_"))
    symbols = [f"00000{i}" for i in range(1, 21)]  # 20个品种
    intervals = ["1min", "5min", "day"]  # 3个周期

    try:
        create_test_data_structure(test_dir, symbols, intervals)

        # 执行数据感知
        results = await data_sensing_with_iocp(
            symbols=symbols,
            data_dir=test_dir,
            intervals=intervals,
            max_concurrent=10,
            thread_counter=thread_counter
        )

        # 验证线程数
        print("\n" + "=" * 70)
        print("📋 验证结果")
        print("=" * 70)

        initial_count = thread_counter.initial_count
        final_count = thread_counter.snapshots[-1]["count"] if thread_counter.snapshots else initial_count

        print(f"初始线程数: {initial_count}")
        print(f"最终线程数: {final_count}")

        if final_count == initial_count:
            print("✅ 验证通过: 线程数未增加")
            print("✅ 确认: 使用了纯多协程异步I/O，不使用线程池")

            # 显示线程快照摘要
            print("\n📸 线程快照摘要:")
            for snapshot in thread_counter.snapshots[:5]:  # 只显示前5个
                new_threads = snapshot.get("new_threads", [])
                if new_threads:
                    print(f"  [{snapshot['label']}] 线程数: {snapshot['count']} (⚠️ 新增: {new_threads})")
                else:
                    print(f"  [{snapshot['label']}] 线程数: {snapshot['count']} (✅ 无新增)")
        else:
            print("⚠️  警告: 线程数发生了变化")
            print(f"   增加: {final_count - initial_count} 个线程")

            # 显示新增线程
            final_threads = set([t.name for t in threading.enumerate()])
            initial_threads = set(thread_counter.initial_threads)
            new_threads = final_threads - initial_threads
            if new_threads:
                print(f"   新增线程: {new_threads}")

        # 统计扫描结果
        print(f"\n📊 扫描结果统计")
        has_data_count = sum(1 for r in results if r.get("has_data", False))
        print(f"   有数据的品种: {has_data_count}/{len(results)}")

        # 统计各周期的数据情况
        interval_stats = {}
        for r in results:
            for interval, info in r.get("intervals", {}).items():
                if interval not in interval_stats:
                    interval_stats[interval] = {"has_data": 0, "total": 0}
                interval_stats[interval]["total"] += 1
                if info.get("has_data", False):
                    interval_stats[interval]["has_data"] += 1

        for interval, stats in interval_stats.items():
            print(f"   {interval}: {stats['has_data']}/{stats['total']} 有数据")

        # 清理测试数据
        print(f"\n🧹 清理测试数据: {test_dir}")
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)
        print("✅ 清理完成")

        return 0 if final_count == initial_count else 1

    except Exception as e:
        print(f"\n❌ 验证过程发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

