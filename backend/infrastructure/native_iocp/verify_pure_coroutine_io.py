# -*- coding: utf-8 -*-
"""
验证纯多协程异步磁盘I/O（不使用线程池）

这个脚本验证：
1. 单线程多协程的异步文件I/O
2. 不使用线程池
3. 并发读取多个文件
4. 验证线程数量（应该是1个主线程）
"""

import asyncio
import sys
import platform
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
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

# 尝试导入IOCP模块
try:
    from backend.infrastructure.native_iocp import aopen, AsyncIOCPFile
    from backend.infrastructure.native_iocp.compat import is_iocp_available, get_backend

    IOCP_AVAILABLE = True
except ImportError as e:
    print(f"❌ 无法导入IOCP模块: {e}")
    print("   提示: 可能需要先编译C扩展")
    sys.exit(1)


def get_thread_count() -> int:
    """获取当前线程数量"""
    return threading.active_count()


def get_all_threads() -> List[threading.Thread]:
    """获取所有线程"""
    return threading.enumerate()


class ThreadMonitor:
    """线程监控器"""

    def __init__(self):
        self.initial_threads: List[str] = []
        self.thread_snapshots: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def capture_initial(self):
        """捕获初始线程状态"""
        self.initial_threads = [t.name for t in threading.enumerate()]
        self.thread_snapshots.append(
            {
                "time": 0.0,
                "thread_count": threading.active_count(),
                "threads": self.initial_threads.copy(),
            }
        )

    def capture_snapshot(self, label: str = ""):
        """捕获当前线程状态快照"""
        current_threads = [t.name for t in threading.enumerate()]
        elapsed = time.time() - self.start_time

        new_threads = [t for t in current_threads if t not in self.initial_threads]

        snapshot = {
            "time": elapsed,
            "label": label,
            "thread_count": threading.active_count(),
            "threads": current_threads.copy(),
            "new_threads": new_threads,
        }
        self.thread_snapshots.append(snapshot)

        print(f"\n📸 线程快照 [{label}] (时间: {elapsed:.3f}s)")
        print(f"   总线程数: {threading.active_count()}")
        if new_threads:
            print(f"   ⚠️  新增线程: {new_threads}")
        else:
            print(f"   ✅ 无新增线程（仍然是单线程）")

    def print_summary(self):
        """打印线程监控摘要"""
        print("\n" + "=" * 70)
        print("📊 线程监控摘要")
        print("=" * 70)

        initial_count = self.thread_snapshots[0]["thread_count"]
        print(f"初始线程数: {initial_count}")

        for snapshot in self.thread_snapshots[1:]:
            print(f"\n[{snapshot['label']}] (时间: {snapshot['time']:.3f}s)")
            print(f"  线程数: {snapshot['thread_count']}")
            if snapshot.get("new_threads"):
                print(f"  新增线程: {snapshot['new_threads']}")
            else:
                print(f"  ✅ 无新增线程")

        final_count = self.thread_snapshots[-1]["thread_count"]
        if final_count == initial_count:
            print(f"\n✅ 验证通过: 线程数未增加（初始={initial_count}, 最终={final_count}）")
        else:
            print(f"\n⚠️  警告: 线程数增加（初始={initial_count}, 最终={final_count}）")


async def read_file_async(file_path: Path, monitor: ThreadMonitor) -> Dict:
    """
    异步读取单个文件

    Args:
        file_path: 文件路径
        monitor: 线程监控器

    Returns:
        读取结果字典
    """
    try:
        # 捕获读取前的线程状态
        monitor.capture_snapshot(f"读取前: {file_path.name}")

        # 异步读取文件（不使用线程池）
        file_obj = await aopen(file_path, "rb")  # type: ignore  # aopen返回awaitable
        file = file_obj

        async with file:
            data = await file.read()

        # 捕获读取后的线程状态
        monitor.capture_snapshot(f"读取后: {file_path.name}")

        return {
            "file": file_path.name,
            "success": True,
            "size": len(data),
            "preview": data[:20].decode("utf-8", errors="ignore") if len(data) > 0 else "",
        }
    except Exception as e:
        return {
            "file": file_path.name,
            "success": False,
            "error": str(e),
        }


async def simulate_data_sensing(
    file_paths: List[Path], max_concurrent: int = 10, monitor: Optional[ThreadMonitor] = None
) -> List[Dict]:
    """
    模拟数据感知场景：并发读取多个文件

    Args:
        file_paths: 文件路径列表
        max_concurrent: 最大并发数
        monitor: 线程监控器

    Returns:
        读取结果列表
    """
    print(f"\n🚀 开始数据感知模拟")
    print(f"   文件数量: {len(file_paths)}")
    print(f"   最大并发: {max_concurrent}")
    print(f"   使用IOCP: {is_iocp_available()}")
    print(f"   当前后端: {get_backend()}")

    if monitor:
        monitor.capture_snapshot("数据感知开始")

    # 使用信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    async def read_with_semaphore(file_path: Path):
        monitor_instance = monitor if monitor else ThreadMonitor()
        async with semaphore:
            return await read_file_async(file_path, monitor_instance)

    # 并发读取所有文件（真正的多协程并发，不使用线程池）
    start_time = time.time()

    tasks = [read_with_semaphore(fp) for fp in file_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

    if monitor:
        monitor.capture_snapshot("数据感知完成")

    print(f"\n✅ 数据感知完成")
    print(f"   总耗时: {elapsed:.3f}秒")
    print(f"   平均速度: {len(file_paths) / elapsed:.2f} 文件/秒")

    # 统计结果
    success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
    error_count = len(results) - success_count

    print(f"   成功: {success_count}/{len(file_paths)}")
    if error_count > 0:
        print(f"   失败: {error_count}")

    return [r for r in results if isinstance(r, dict)]


async def create_test_files(count: int = 20) -> Tuple[List[Path], Path]:
    """创建测试文件"""
    print(f"\n📝 创建 {count} 个测试文件...")

    test_dir = Path(tempfile.mkdtemp(prefix="iocp_test_"))
    file_paths = []

    for i in range(count):
        file_path = test_dir / f"test_file_{i:03d}.txt"
        content = f"测试文件 {i}\n" * 100  # 每文件约1KB
        file_path.write_text(content, encoding="utf-8")
        file_paths.append(file_path)

    print(f"✅ 创建完成: {test_dir}")
    return file_paths, test_dir


async def main():
    """主函数"""
    print("=" * 70)
    print("🧪 验证纯多协程异步磁盘I/O（不使用线程池）")
    print("=" * 70)

    # 检查IOCP可用性
    if not is_iocp_available():
        print("❌ IOCP不可用，无法进行验证")
        print("   提示: 请先编译C扩展")
        return 1

    backend = get_backend()
    if backend != "iocp":
        print(f"⚠️  当前后端: {backend} (不是IOCP)")
        print("   将使用兼容层（可能降级到aiofiles）")
    else:
        print(f"✅ 当前后端: {backend} (IOCP)")

    # 初始化线程监控
    monitor = ThreadMonitor()
    monitor.capture_initial()

    print(f"\n📊 初始线程状态")
    print(f"   线程数: {threading.active_count()}")
    print(f"   线程列表: {[t.name for t in threading.enumerate()]}")

    try:
        # 创建测试文件
        file_paths, test_dir = await create_test_files(count=20)

        # 执行数据感知模拟
        results = await simulate_data_sensing(file_paths, max_concurrent=10, monitor=monitor)

        # 打印线程监控摘要
        monitor.print_summary()

        # 验证线程数未增加
        initial_count = monitor.thread_snapshots[0]["thread_count"]
        final_count = monitor.thread_snapshots[-1]["thread_count"]

        print("\n" + "=" * 70)
        print("📋 验证结果")
        print("=" * 70)

        if final_count == initial_count:
            print("✅ 验证通过: 线程数未增加")
            print(f"   初始线程数: {initial_count}")
            print(f"   最终线程数: {final_count}")
            print("✅ 确认: 使用了纯多协程异步I/O，不使用线程池")
        else:
            print("⚠️  警告: 线程数发生了变化")
            print(f"   初始线程数: {initial_count}")
            print(f"   最终线程数: {final_count}")
            print(f"   新增线程: {final_count - initial_count}")

            # 显示新增的线程
            initial_threads = set(monitor.thread_snapshots[0]["threads"])
            final_threads = set(monitor.thread_snapshots[-1]["threads"])
            new_threads = final_threads - initial_threads
            if new_threads:
                print(f"   线程列表: {new_threads}")

        # 验证结果
        success_count = sum(1 for r in results if r.get("success", False))
        print(f"\n📊 文件读取结果")
        print(f"   成功读取: {success_count}/{len(results)}")

        if success_count == len(results):
            print("✅ 所有文件读取成功")
        else:
            print("⚠️  部分文件读取失败")
            for r in results:
                if not r.get("success", False):
                    print(f"   失败: {r.get('file')} - {r.get('error')}")

        # 清理测试文件
        print(f"\n🧹 清理测试文件: {test_dir}")
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)
        print("✅ 清理完成")

        return 0 if final_count == initial_count else 1

    except Exception as e:
        print(f"\n❌ 验证过程发生错误: {e}")
        import traceback

        traceback.print_exc()
        monitor.print_summary()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
