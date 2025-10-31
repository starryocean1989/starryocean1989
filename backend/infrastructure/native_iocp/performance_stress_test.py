# -*- coding: utf-8 -*-
"""
单线程多协程性能压力测试

测试目标：
1. 找出单核CPU达到满负荷时的协程数量
2. 找出协程队列开始累积时的协程数量
3. 测量不同并发数下的吞吐量
"""

import asyncio
import sys
import platform
import threading
import time
import psutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import tempfile
from collections import deque
import statistics

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
    sys.exit(1)


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, test_duration: float = 5.0):
        self.test_duration = test_duration
        self.cpu_samples: List[float] = []
        self.throughput_samples: List[float] = []
        self.queue_depth_samples: List[int] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self):
        """开始监控"""
        self.start_time = time.time()
        self.end_time = self.start_time + self.test_duration

    def sample(self, cpu_percent: float, throughput: float, queue_depth: int):
        """采样性能数据"""
        self.cpu_samples.append(cpu_percent)
        self.throughput_samples.append(throughput)
        self.queue_depth_samples.append(queue_depth)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "cpu_avg": statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
            "cpu_max": max(self.cpu_samples) if self.cpu_samples else 0,
            "cpu_min": min(self.cpu_samples) if self.cpu_samples else 0,
            "throughput_avg": statistics.mean(self.throughput_samples) if self.throughput_samples else 0,
            "throughput_max": max(self.throughput_samples) if self.throughput_samples else 0,
            "queue_depth_avg": statistics.mean(self.queue_depth_samples) if self.queue_depth_samples else 0,
            "queue_depth_max": max(self.queue_depth_samples) if self.queue_depth_samples else 0,
        }


class ConcurrentFileReader:
    """并发文件读取器"""

    def __init__(self, file_paths: List[Path], max_concurrent: int):
        self.file_paths = file_paths
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.completed_count = 0
        self.error_count = 0
        self.start_time: Optional[float] = None
        self.queue_depth = 0
        self.pending_count = 0
        self.active_tasks = set()  # 正在执行的任务集合
        self.waiting_tasks = 0  # 等待信号量的任务数

    async def read_file(self, file_path: Path, task_id: int) -> Tuple[bool, float]:
        """读取单个文件"""
        start = time.time()
        task = asyncio.current_task()
        try:
            # 记录等待开始
            self.waiting_tasks += 1

            async with self.semaphore:
                # 进入信号量，开始执行
                self.waiting_tasks -= 1
                self.active_tasks.add(task_id)

                file = await aopen(file_path, 'rb')
                async with file:
                    data = await file.read()

                self.completed_count += 1
                self.active_tasks.discard(task_id)
                elapsed = time.time() - start
                return True, elapsed
        except Exception as e:
            self.error_count += 1
            self.waiting_tasks -= 1
            self.active_tasks.discard(task_id)
            elapsed = time.time() - start
            return False, elapsed

    def get_queue_depth(self) -> int:
        """获取当前队列深度（等待信号量的任务数）"""
        # 返回等待信号量的任务数
        return max(0, self.waiting_tasks)

    def get_active_count(self) -> int:
        """获取当前活跃任务数"""
        return len(self.active_tasks)

    async def run_test(self, duration: float = 5.0) -> Dict:
        """运行测试"""
        self.start_time = time.time()
        end_time = self.start_time + duration

        # 创建循环读取任务
        tasks = []

        task_id_counter = 0

        async def read_loop():
            """循环读取文件"""
            nonlocal task_id_counter
            file_index = 0
            while time.time() < end_time:
                file_path = self.file_paths[file_index % len(self.file_paths)]
                task_id = task_id_counter
                task_id_counter += 1
                task = asyncio.create_task(self.read_file(file_path, task_id))
                tasks.append(task)
                file_index += 1
                # 不延迟，尽可能快地提交任务，以检测队列累积
                await asyncio.sleep(0)  # 让出控制权，但不延迟

        # 启动读取循环
        read_task = asyncio.create_task(read_loop())

        # 等待测试完成
        await asyncio.sleep(duration + 0.1)
        read_task.cancel()

        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - self.start_time
        success_count = sum(1 for r in results if isinstance(r, tuple) and r[0])
        error_count = len(results) - success_count

        return {
            "duration": elapsed,
            "completed": self.completed_count,
            "errors": self.error_count,
            "total_operations": len(results),
            "success_rate": success_count / len(results) if results else 0,
            "throughput": self.completed_count / elapsed if elapsed > 0 else 0,
        }


async def run_stress_test(
    file_paths: List[Path],
    max_concurrent_range: List[int],
    test_duration: float = 5.0,
    sample_interval: float = 0.5
) -> List[Dict]:
    """运行压力测试"""
    results = []

    print("\n" + "=" * 80)
    print("🚀 单线程多协程性能压力测试")
    print("=" * 80)
    print(f"测试文件数: {len(file_paths)}")
    print(f"测试时长: {test_duration}秒/测试")
    print(f"并发范围: {min(max_concurrent_range)} ~ {max(max_concurrent_range)}")
    print(f"使用IOCP: {is_iocp_available() if IOCP_AVAILABLE else 'N/A'}")
    print(f"当前后端: {get_backend() if IOCP_AVAILABLE else 'compat'}")
    print("=" * 80)

    for max_concurrent in max_concurrent_range:
        print(f"\n📊 测试并发数: {max_concurrent}")

        # 创建监控器
        monitor = PerformanceMonitor(test_duration)

        # 创建读取器
        reader = ConcurrentFileReader(file_paths, max_concurrent)

        # 启动CPU监控（使用系统级别监控，更准确）
        cpu_process = psutil.Process()
        # 预先调用一次以初始化
        cpu_process.cpu_percent()

        # 启动测试
        test_task = asyncio.create_task(reader.run_test(test_duration))

        # 监控循环
        monitor.start()
        last_sample_time = time.time()

        async def monitor_loop():
            """监控循环"""
            while time.time() < monitor.end_time:
                await asyncio.sleep(sample_interval)

                # 采样（只关注单核CPU）
                cpu_process = psutil.Process()
                # 获取进程CPU使用率（单线程时就是单核使用率）
                cpu_single_core = cpu_process.cpu_percent(interval=0.1)

                throughput = reader.completed_count / (time.time() - reader.start_time) if reader.start_time else 0
                queue_depth = reader.get_queue_depth()

                monitor.sample(cpu_single_core, throughput, queue_depth)

        monitor_task = asyncio.create_task(monitor_loop())

        # 等待测试完成
        test_result = await test_task

        # 停止监控
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # 获取统计信息
        stats = monitor.get_stats()

        result = {
            "max_concurrent": max_concurrent,
            "test_result": test_result,
            "stats": stats,
            "cpu_peak": stats["cpu_max"],
            "throughput_peak": stats["throughput_max"],
            "queue_depth_peak": stats["queue_depth_max"],
        }

        results.append(result)

        # 打印结果（只关注单核）
        cpu_single_core_avg = stats['cpu_avg']
        cpu_single_core_max = stats['cpu_max']

        # 判断是否满载（单核≥95%）
        saturated_mark = "✅ 满载" if cpu_single_core_max >= 95.0 else ""

        print(f"  单核CPU: 平均={cpu_single_core_avg:.1f}%, 峰值={cpu_single_core_max:.1f}% {saturated_mark}")
        print(f"  吞吐量: {stats['throughput_avg']:.2f} 文件/秒")
        print(f"  队列深度: 峰值={stats['queue_depth_max']}")

        # 短暂休息，避免测试之间相互影响
        await asyncio.sleep(1.0)

    return results


def analyze_results(results: List[Dict]) -> Dict:
    """分析测试结果"""
    print("\n" + "=" * 80)
    print("📈 性能分析")
    print("=" * 80)

    # 找出单核CPU达到满负荷的协程数（单核CPU使用率 ≥ 95%）
    cpu_saturated_point = None
    for r in results:
        # 单核CPU使用率
        cpu_single_core = r["stats"]["cpu_avg"]
        if cpu_single_core >= 95.0:
            cpu_saturated_point = r["max_concurrent"]
            break

    # 找出队列开始累积的协程数（队列深度峰值 > 5）
    queue_accumulation_point = None
    for r in results:
        if r["stats"]["queue_depth_max"] > 5:
            queue_accumulation_point = r["max_concurrent"]
            break

    # 找出吞吐量峰值
    max_throughput_result = max(results, key=lambda x: x["stats"]["throughput_avg"])
    max_throughput_point = max_throughput_result["max_concurrent"]

    # 找出最佳性能点（吞吐量高且CPU利用率合理）
    best_performance = None
    best_score = 0
    for r in results:
        # 评分：吞吐量 * CPU利用率（避免CPU空闲）
        score = r["stats"]["throughput_avg"] * r["stats"]["cpu_avg"] / 100.0
        if score > best_score:
            best_score = score
            best_performance = r

    print(f"\n✅ 单核CPU达到满负荷（≥95%）的协程数: {cpu_saturated_point if cpu_saturated_point else '未达到'}")
    print(f"✅ 协程队列开始累积（峰值>5）的协程数: {queue_accumulation_point if queue_accumulation_point else '未累积'}")
    print(f"✅ 吞吐量峰值对应的协程数: {max_throughput_point}")

    if best_performance:
        print(f"✅ 最佳性能点: {best_performance['max_concurrent']} 协程")
        print(f"   吞吐量: {best_performance['stats']['throughput_avg']:.2f} 文件/秒")
        print(f"   单核CPU: {best_performance['stats']['cpu_avg']:.1f}%")

    # 打印详细数据（只关注单核和关键指标）
    print("\n📊 详细数据:")
    print(f"{'并发数':<10} {'单核CPU%':<12} {'吞吐量':<15} {'队列深度':<12} {'状态':<10}")
    print("-" * 65)
    for r in results:
        cpu_single = r['stats']['cpu_avg']
        cpu_max = r['stats']['cpu_max']
        queue_max = r['stats']['queue_depth_max']

        # 状态标记
        status = ""
        if cpu_max >= 95.0:
            status = "✅ 满载"
        elif queue_max > 5:
            status = "⚠️ 队列累积"

        print(f"{r['max_concurrent']:<10} "
              f"{cpu_single:<12.1f} "
              f"{r['stats']['throughput_avg']:<15.2f} "
              f"{queue_max:<12} "
              f"{status:<10}")

    return {
        "cpu_saturated_point": cpu_saturated_point,
        "queue_accumulation_point": queue_accumulation_point,
        "max_throughput_point": max_throughput_point,
        "best_performance": best_performance,
    }


async def create_test_files(count: int = 100, size_kb: int = 10) -> Tuple[List[Path], Path]:
    """创建测试文件"""
    print(f"\n📝 创建 {count} 个测试文件（每个 {size_kb}KB）...")

    test_dir = Path(tempfile.mkdtemp(prefix="iocp_stress_test_"))
    file_paths = []

    # 创建文件内容（随机数据）
    import random
    content = bytes(random.randint(0, 255) for _ in range(size_kb * 1024))

    for i in range(count):
        file_path = test_dir / f"test_file_{i:06d}.dat"
        file_path.write_bytes(content)
        file_paths.append(file_path)

    print(f"✅ 创建完成: {test_dir}")
    return file_paths, test_dir


async def main():
    """主函数"""
    print("=" * 80)
    print("🧪 单线程多协程性能压力测试")
    print("=" * 80)

    # 检查IOCP可用性
    if IOCP_AVAILABLE:
        if not is_iocp_available():
            print("⚠️ IOCP不可用，将使用兼容层")
        else:
            backend = get_backend()
            print(f"✅ 使用后端: {backend}")
    else:
        print("⚠️ 使用兼容层（可能使用aiofiles/线程池）")

    # 创建测试文件（使用更大的文件以增加I/O负载）
    # 使用更少的文件但更大的文件大小，以增加每个I/O操作的时间
    file_paths, test_dir = await create_test_files(count=20, size_kb=1000)  # 20个文件，每个1MB

    try:
        # 定义并发数范围（逐步增加）
        # 从1开始，逐步增加到200，每次增加5（更精细的步长）
        max_concurrent_range = list(range(1, 201, 5))

        # 运行压力测试
        results = await run_stress_test(
            file_paths=file_paths,
            max_concurrent_range=max_concurrent_range,
            test_duration=10.0,  # 每个测试10秒（更长以获取更准确的CPU数据）
            sample_interval=0.2  # 每0.2秒采样一次
        )

        # 分析结果
        analysis = analyze_results(results)

        # 保存结果
        import json
        result_file = Path("iocp_stress_test_results.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": {
                    "cpu_saturated_point": analysis["cpu_saturated_point"],
                    "queue_accumulation_point": analysis["queue_accumulation_point"],
                    "max_throughput_point": analysis["max_throughput_point"],
                },
                "results": [
                    {
                        "max_concurrent": r["max_concurrent"],
                        "cpu_avg": r["stats"]["cpu_avg"],
                        "cpu_max": r["stats"]["cpu_max"],
                        "throughput_avg": r["stats"]["throughput_avg"],
                        "throughput_max": r["stats"]["throughput_max"],
                        "queue_depth_max": r["stats"]["queue_depth_max"],
                        "completed": r["test_result"]["completed"],
                    }
                    for r in results
                ]
            }, f, indent=2, ensure_ascii=False)

        print(f"\n💾 结果已保存到: {result_file}")

        # 清理测试文件
        print(f"\n🧹 清理测试文件: {test_dir}")
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)
        print("✅ 清理完成")

        return 0

    except Exception as e:
        print(f"\n❌ 测试过程发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

