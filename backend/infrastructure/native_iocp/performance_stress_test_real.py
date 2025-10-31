# -*- coding: utf-8 -*-
"""
真实数据感知场景性能压力测试

使用实际的Parquet数据文件进行测试
"""

import asyncio
import sys
import platform
import time
import psutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import statistics

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
    from backend.infrastructure.native_iocp import aopen
    from backend.infrastructure.native_iocp.compat import is_iocp_available, get_backend
    IOCP_AVAILABLE = True
except ImportError as e:
    print(f"❌ 无法导入IOCP模块: {e}")
    sys.exit(1)


class PerformanceMonitor:
    """性能监控器（只关注单核CPU）"""

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
            "throughput_avg": statistics.mean(self.throughput_samples) if self.throughput_samples else 0,
            "throughput_max": max(self.throughput_samples) if self.throughput_samples else 0,
            "queue_depth_avg": statistics.mean(self.queue_depth_samples) if self.queue_depth_samples else 0,
            "queue_depth_max": max(self.queue_depth_samples) if self.queue_depth_samples else 0,
        }


class RealDataSensor:
    """真实数据感知器"""

    def __init__(self, data_dir: Path, intervals: List[str], max_concurrent: int):
        self.data_dir = data_dir
        self.intervals = intervals
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.completed_count = 0
        self.error_count = 0
        self.start_time: Optional[float] = None
        self.active_tasks = set()
        self.waiting_tasks = 0

    async def read_parquet_file(self, file_path: Path, task_id: int) -> Tuple[bool, float, int]:
        """读取单个Parquet文件"""
        start = time.time()
        try:
            self.waiting_tasks += 1

            async with self.semaphore:
                self.waiting_tasks -= 1
                self.active_tasks.add(task_id)

                # 使用IOCP异步读取Parquet文件
                file = await aopen(file_path, 'rb')
                async with file:
                    data = await file.read()

                # 从内存中解析Parquet
                import io
                buffer = io.BytesIO(data)
                df = pd.read_parquet(buffer)

                row_count = len(df)
                self.completed_count += 1
                self.active_tasks.discard(task_id)
                elapsed = time.time() - start
                return True, elapsed, row_count
        except Exception as e:
            self.error_count += 1
            self.waiting_tasks -= 1
            self.active_tasks.discard(task_id)
            elapsed = time.time() - start
            return False, elapsed, 0

    async def scan_symbol(self, symbol: str, task_id: int) -> Dict:
        """扫描单个品种的数据质量"""
        start = time.time()
        interval_results = {}
        total_rows = 0

        for interval in self.intervals:
            file_path = self.data_dir / symbol / interval / "data.parquet"

            if not file_path.exists():
                continue

            # 给每个文件的读取分配唯一的task_id
            file_task_id = task_id * 100 + len(interval_results)

            success, elapsed, row_count = await self.read_parquet_file(file_path, file_task_id)
            if success:
                interval_results[interval] = {
                    "has_data": True,
                    "record_count": row_count,
                }
                total_rows += row_count

        elapsed = time.time() - start
        return {
            "symbol": symbol,
            "has_data": len(interval_results) > 0,
            "intervals": interval_results,
            "total_rows": total_rows,
            "elapsed": elapsed,
        }

    def get_queue_depth(self) -> int:
        """获取当前队列深度"""
        return max(0, self.waiting_tasks)

    async def run_test(self, symbols: List[str], duration: float = 10.0) -> Dict:
        """运行测试"""
        self.start_time = time.time()
        end_time = self.start_time + duration

        tasks = []
        task_id_counter = 0

        async def scan_loop():
            """循环扫描品种"""
            nonlocal task_id_counter
            symbol_index = 0
            while time.time() < end_time:
                symbol = symbols[symbol_index % len(symbols)]
                task_id = task_id_counter
                task_id_counter += 1
                task = asyncio.create_task(self.scan_symbol(symbol, task_id))
                tasks.append(task)
                symbol_index += 1
                await asyncio.sleep(0)  # 让出控制权

        scan_task = asyncio.create_task(scan_loop())
        await asyncio.sleep(duration + 0.1)
        scan_task.cancel()

        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - self.start_time
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("has_data", False))

        return {
            "duration": elapsed,
            "completed": self.completed_count,
            "errors": self.error_count,
            "total_operations": len(results),
            "success_count": success_count,
            "throughput": self.completed_count / elapsed if elapsed > 0 else 0,
        }


async def run_stress_test(
    data_dir: Path,
    symbols: List[str],
    intervals: List[str],
    max_concurrent_range: List[int],
    test_duration: float = 10.0,
    sample_interval: float = 0.5
) -> List[Dict]:
    """运行压力测试"""
    results = []

    print("\n" + "=" * 80)
    print("🚀 真实数据感知性能压力测试")
    print("=" * 80)
    print(f"数据目录: {data_dir}")
    print(f"品种数量: {len(symbols)}")
    print(f"周期列表: {intervals}")
    print(f"测试时长: {test_duration}秒/测试")
    print(f"并发范围: {min(max_concurrent_range)} ~ {max(max_concurrent_range)}")
    print(f"使用IOCP: {is_iocp_available() if IOCP_AVAILABLE else 'N/A'}")
    print(f"当前后端: {get_backend() if IOCP_AVAILABLE else 'compat'}")
    print("=" * 80)

    for max_concurrent in max_concurrent_range:
        print(f"\n📊 测试并发数: {max_concurrent}")

        monitor = PerformanceMonitor(test_duration)
        sensor = RealDataSensor(data_dir, intervals, max_concurrent)

        cpu_process = psutil.Process()
        cpu_process.cpu_percent()  # 初始化

        test_task = asyncio.create_task(sensor.run_test(symbols, test_duration))

        monitor.start()

        async def monitor_loop():
            """监控循环"""
            while time.time() < monitor.end_time:
                await asyncio.sleep(sample_interval)

                # 只关注单核CPU
                cpu_single_core = cpu_process.cpu_percent(interval=0.1)
                throughput = sensor.completed_count / (time.time() - sensor.start_time) if sensor.start_time else 0
                queue_depth = sensor.get_queue_depth()

                monitor.sample(cpu_single_core, throughput, queue_depth)

        monitor_task = asyncio.create_task(monitor_loop())
        test_result = await test_task

        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        stats = monitor.get_stats()
        result = {
            "max_concurrent": max_concurrent,
            "test_result": test_result,
            "stats": stats,
        }
        results.append(result)

        # 打印结果
        cpu_single_core_avg = stats['cpu_avg']
        cpu_single_core_max = stats['cpu_max']
        saturated_mark = "✅ 满载" if cpu_single_core_max >= 95.0 else ""

        print(f"  单核CPU: 平均={cpu_single_core_avg:.1f}%, 峰值={cpu_single_core_max:.1f}% {saturated_mark}")
        print(f"  吞吐量: {stats['throughput_avg']:.2f} 文件/秒")
        print(f"  队列深度: 峰值={stats['queue_depth_max']}")
        print(f"  完成操作: {test_result['completed']}, 错误: {test_result['errors']}")

        await asyncio.sleep(1.0)

    return results


def analyze_results(results: List[Dict]) -> Dict:
    """分析测试结果"""
    print("\n" + "=" * 80)
    print("📈 性能分析")
    print("=" * 80)

    # 找出单核CPU达到满负荷的协程数
    cpu_saturated_point = None
    for r in results:
        if r["stats"]["cpu_max"] >= 95.0:
            cpu_saturated_point = r["max_concurrent"]
            break

    # 找出队列开始累积的协程数
    queue_accumulation_point = None
    for r in results:
        if r["stats"]["queue_depth_max"] > 5:
            queue_accumulation_point = r["max_concurrent"]
            break

    # 找出吞吐量峰值
    max_throughput_result = max(results, key=lambda x: x["stats"]["throughput_avg"])
    max_throughput_point = max_throughput_result["max_concurrent"]

    print(f"\n✅ 单核CPU达到满负荷（≥95%）的协程数: {cpu_saturated_point if cpu_saturated_point else '未达到'}")
    print(f"✅ 协程队列开始累积（峰值>5）的协程数: {queue_accumulation_point if queue_accumulation_point else '未累积'}")
    print(f"✅ 吞吐量峰值对应的协程数: {max_throughput_point}")

    # 打印详细数据
    print("\n📊 详细数据:")
    print(f"{'并发数':<10} {'单核CPU%':<12} {'吞吐量':<15} {'队列深度':<12} {'状态':<10}")
    print("-" * 65)
    for r in results:
        cpu_single = r['stats']['cpu_avg']
        cpu_max = r['stats']['cpu_max']
        queue_max = r['stats']['queue_depth_max']

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
    }


def find_data_files(data_dir: Path, intervals: List[str], max_symbols: int = 200) -> List[str]:
    """查找可用的数据文件"""
    symbols = []

    for symbol_dir in sorted(data_dir.iterdir()):
        if not symbol_dir.is_dir():
            continue

        symbol = symbol_dir.name
        has_data = False

        for interval in intervals:
            file_path = symbol_dir / interval / "data.parquet"
            if file_path.exists():
                has_data = True
                break

        if has_data:
            symbols.append(symbol)
            if len(symbols) >= max_symbols:
                break

    return symbols


async def main():
    """主函数"""
    print("=" * 80)
    print("🧪 真实数据感知性能压力测试")
    print("=" * 80)

    # 检查IOCP可用性
    if IOCP_AVAILABLE and is_iocp_available():
        backend = get_backend()
        print(f"✅ 使用后端: {backend}")
    else:
        print("⚠️ 使用兼容层（可能使用aiofiles/线程池）")

    # 数据目录
    data_dir = Path("data/kline")
    # 实际目录结构：1m, 5m, 1d
    intervals = ["1m", "5m", "1d"]

    if not data_dir.exists():
        print(f"❌ 数据目录不存在: {data_dir}")
        return 1

    # 查找可用的数据文件
    print(f"\n📂 查找数据文件: {data_dir}")
    symbols = find_data_files(data_dir, intervals, max_symbols=200)

    if not symbols:
        print("❌ 未找到可用的数据文件")
        return 1

    print(f"✅ 找到 {len(symbols)} 个品种的数据文件")

    try:
        # 定义并发数范围（逐步增加）
        max_concurrent_range = list(range(1, 101, 5))  # 1-100，步长5

        # 运行压力测试
        results = await run_stress_test(
            data_dir=data_dir,
            symbols=symbols,
            intervals=intervals,
            max_concurrent_range=max_concurrent_range,
            test_duration=10.0,
            sample_interval=0.2
        )

        # 分析结果
        analysis = analyze_results(results)

        # 保存结果
        import json
        result_file = Path("iocp_stress_test_real_results.json")
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
                        "queue_depth_max": r["stats"]["queue_depth_max"],
                        "completed": r["test_result"]["completed"],
                    }
                    for r in results
                ]
            }, f, indent=2, ensure_ascii=False)

        print(f"\n💾 结果已保存到: {result_file}")

        return 0

    except Exception as e:
        print(f"\n❌ 测试过程发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

