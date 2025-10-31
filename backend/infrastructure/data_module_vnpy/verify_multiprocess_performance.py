# -*- coding: utf-8 -*-
"""
多进程性能优化验证脚本

验证目标：
1. CPU使用率监控和优化
2. 内存使用率监控
3. 进程数动态调整验证
4. 任务排队和吞吐量监控
5. 性能峰值验证

使用方法：
    python backend/infrastructure/data_module_vnpy/verify_multiprocess_performance.py
"""

import sys
import os
import time
import threading
import multiprocessing
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️ psutil未安装，部分监控功能将不可用")

try:
    import pandas as pd
except ImportError:
    print("⚠️ pandas未安装，数据质量扫描功能将不可用")
    pd = None

from backend.infrastructure.data_module_vnpy.load_balancer import (
    ResourceMonitor,
    ExecutionPolicy,
    MultiProcessBatchModel,
    TaskUnit,
    TaskResult,
)
from backend.infrastructure.data_module_vnpy.data_quality import (
    DataQualityScanTask,
    _scan_symbol_quality_multiprocess,
)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    process_count: int
    active_threads: int
    completed_tasks: int
    total_tasks: int
    throughput_tasks_per_sec: float
    queue_size: int = 0
    adjustment_count: int = 0
    current_workers: int = 0


@dataclass
class PerformanceReport:
    """性能报告"""
    test_name: str
    start_time: float
    end_time: float
    total_duration: float
    metrics_history: List[PerformanceMetrics] = field(default_factory=list)
    peak_cpu: float = 0.0
    peak_memory: float = 0.0
    peak_throughput: float = 0.0
    avg_cpu: float = 0.0
    avg_memory: float = 0.0
    avg_throughput: float = 0.0
    total_adjustments: int = 0
    final_workers: int = 0
    peak_workers: int = 0
    min_workers: int = 0


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, monitor_interval: float = 0.5):
        """初始化性能监控器

        Args:
            monitor_interval: 监控采样间隔（秒）
        """
        self.monitor_interval = monitor_interval
        self.monitoring = False
        self.metrics_history: List[PerformanceMetrics] = []
        self.monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # 外部状态回调
        self.get_completed_tasks = lambda: 0
        self.get_total_tasks = lambda: 0
        self.get_queue_size = lambda: 0
        self.get_current_workers = lambda: 0
        self.get_adjustment_count = lambda: 0

    def register_callbacks(
        self,
        get_completed_tasks=None,
        get_total_tasks=None,
        get_queue_size=None,
        get_current_workers=None,
        get_adjustment_count=None,
    ):
        """注册状态获取回调函数"""
        if get_completed_tasks:
            self.get_completed_tasks = get_completed_tasks
        if get_total_tasks:
            self.get_total_tasks = get_total_tasks
        if get_queue_size:
            self.get_queue_size = get_queue_size
        if get_current_workers:
            self.get_current_workers = get_current_workers
        if get_adjustment_count:
            self.get_adjustment_count = get_adjustment_count

    def start(self):
        """启动监控"""
        if self.monitoring:
            return

        self.monitoring = True
        self._stop_event.clear()
        self.metrics_history.clear()

        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop, name="PerformanceMonitor", daemon=True
        )
        self.monitor_thread.start()
        print("✅ 性能监控已启动")

    def stop(self):
        """停止监控"""
        if not self.monitoring:
            return

        self.monitoring = False
        self._stop_event.set()

        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)

        print("✅ 性能监控已停止")

    def _monitoring_loop(self):
        """监控循环"""
        last_completed = 0
        last_time = time.time()

        while not self._stop_event.is_set():
            try:
                current_time = time.time()

                # 收集系统指标
                if HAS_PSUTIL:
                    cpu_percent = psutil.cpu_percent(interval=None)
                    memory = psutil.virtual_memory()
                    memory_percent = memory.percent
                    memory_used_mb = memory.used / (1024 * 1024)
                    process_count = len(psutil.pids())
                    active_threads = threading.active_count()
                else:
                    cpu_percent = 0.0
                    memory_percent = 0.0
                    memory_used_mb = 0.0
                    process_count = 0
                    active_threads = 0

                # 收集任务指标
                completed = self.get_completed_tasks()
                total = self.get_total_tasks()
                queue_size = self.get_queue_size()
                current_workers = self.get_current_workers()
                adjustment_count = self.get_adjustment_count()

                # 计算吞吐量
                elapsed = current_time - last_time
                if elapsed > 0:
                    throughput = (completed - last_completed) / elapsed
                else:
                    throughput = 0.0

                # 创建指标记录
                metrics = PerformanceMetrics(
                    timestamp=current_time,
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_used_mb=memory_used_mb,
                    process_count=process_count,
                    active_threads=active_threads,
                    completed_tasks=completed,
                    total_tasks=total,
                    throughput_tasks_per_sec=throughput,
                    queue_size=queue_size,
                    adjustment_count=adjustment_count,
                    current_workers=current_workers,
                )

                with self._lock:
                    self.metrics_history.append(metrics)

                last_completed = completed
                last_time = current_time

                # 等待下一次采样
                self._stop_event.wait(self.monitor_interval)

            except Exception as e:
                print(f"❌ 监控循环异常: {e}")
                time.sleep(self.monitor_interval)

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """获取当前指标"""
        with self._lock:
            if self.metrics_history:
                return self.metrics_history[-1]
        return None

    def get_metrics_snapshot(self) -> List[PerformanceMetrics]:
        """获取指标快照"""
        with self._lock:
            return self.metrics_history.copy()

    def generate_report(self, test_name: str) -> PerformanceReport:
        """生成性能报告"""
        with self._lock:
            if not self.metrics_history:
                return PerformanceReport(
                    test_name=test_name,
                    start_time=0,
                    end_time=0,
                    total_duration=0,
                )

            start_time = self.metrics_history[0].timestamp
            end_time = self.metrics_history[-1].timestamp
            total_duration = end_time - start_time

            cpu_values = [m.cpu_percent for m in self.metrics_history]
            memory_values = [m.memory_percent for m in self.metrics_history]
            throughput_values = [m.throughput_tasks_per_sec for m in self.metrics_history]
            worker_values = [m.current_workers for m in self.metrics_history]

            report = PerformanceReport(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                total_duration=total_duration,
                metrics_history=self.metrics_history.copy(),
                peak_cpu=max(cpu_values) if cpu_values else 0.0,
                peak_memory=max(memory_values) if memory_values else 0.0,
                peak_throughput=max(throughput_values) if throughput_values else 0.0,
                avg_cpu=sum(cpu_values) / len(cpu_values) if cpu_values else 0.0,
                avg_memory=sum(memory_values) / len(memory_values) if memory_values else 0.0,
                avg_throughput=sum(throughput_values) / len(throughput_values)
                if throughput_values
                else 0.0,
                total_adjustments=self.metrics_history[-1].adjustment_count
                if self.metrics_history
                else 0,
                final_workers=self.metrics_history[-1].current_workers
                if self.metrics_history
                else 0,
                peak_workers=max(worker_values) if worker_values else 0,
                min_workers=min(worker_values) if worker_values else 0,
            )

            return report


class MultiProcessPerformanceVerifier:
    """多进程性能验证器"""

    def __init__(self, data_dir: Optional[Path] = None):
        """初始化验证器

        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = data_dir or Path(project_root) / "data"
        self.monitor = PerformanceMonitor(monitor_interval=0.5)

        # 任务状态
        self._completed_tasks = 0
        self._total_tasks = 0
        self._queue_size = 0
        self._current_workers = 0
        self._adjustment_count = 0
        self._lock = threading.Lock()

        # 注册回调
        self.monitor.register_callbacks(
            get_completed_tasks=lambda: self._completed_tasks,
            get_total_tasks=lambda: self._total_tasks,
            get_queue_size=lambda: self._queue_size,
            get_current_workers=lambda: self._current_workers,
            get_adjustment_count=lambda: self._adjustment_count,
        )

    def _update_status(
        self,
        completed: int = None,
        total: int = None,
        queue_size: int = None,
        workers: int = None,
        adjustments: int = None,
    ):
        """更新状态"""
        with self._lock:
            if completed is not None:
                self._completed_tasks = completed
            if total is not None:
                self._total_tasks = total
            if queue_size is not None:
                self._queue_size = queue_size
            if workers is not None:
                self._current_workers = workers
            if adjustments is not None:
                self._adjustment_count = adjustments

    def verify_multiprocess_scan(
        self,
        symbols: List[str],
        intervals: List[str] = None,
        test_name: str = "多进程扫描验证",
    ) -> PerformanceReport:
        """验证多进程扫描性能

        Args:
            symbols: 品种列表
            intervals: K线周期列表
            test_name: 测试名称

        Returns:
            性能报告
        """
        if intervals is None:
            intervals = ["1d"]

        print(f"\n{'='*80}")
        print(f"🚀 开始验证: {test_name}")
        print(f"{'='*80}")
        print(f"📊 测试参数:")
        print(f"  - 品种数量: {len(symbols)}")
        print(f"  - K线周期: {intervals}")
        print(f"  - CPU核心数: {multiprocessing.cpu_count()}")
        print(f"  - 数据目录: {self.data_dir}")
        print(f"{'='*80}\n")

        # 初始化状态
        self._update_status(completed=0, total=len(symbols), workers=0, adjustments=0)

        # 启动监控
        self.monitor.start()

        try:
            # 创建ResourceMonitor和ExecutionPolicy
            resource_monitor = ResourceMonitor(event_engine=None)
            execution_policy = ExecutionPolicy()

            # 创建任务
            task = DataQualityScanTask("performance_verification", len(symbols))
            pressure = resource_monitor.get_current_pressure()
            plan = execution_policy.select_execution_plan(task, pressure)

            print(f"🎯 LoadBalancer执行计划:")
            print(f"  - 模型类型: {plan.model_type}")
            print(f"  - 初始进程数: {plan.initial_config.max_workers}")
            print(f"  - 批次大小: {plan.initial_config.batch_size}")
            print(f"  - 调整策略: {plan.adjustment_strategy}")
            print(f"  - 决策原因: {plan.reason}")
            print()

            # 准备TaskUnit列表
            data_dir_str = str(self.data_dir)
            task_units = [
                TaskUnit(
                    unit_id=symbol,
                    data=(symbol, intervals, data_dir_str),
                    processor=_scan_symbol_quality_multiprocess,
                )
                for symbol in symbols
            ]

            # 创建MultiProcessBatchModel
            model = MultiProcessBatchModel()

            # 进度回调（更新状态）
            def progress_callback(completed: int, total: int):
                self._update_status(completed=completed, total=total)
                # 尝试获取当前进程数（通过反射）
                try:
                    if hasattr(model, "_current_processes"):
                        self._update_status(workers=model._current_processes)
                    if hasattr(model, "_adjustment_count"):
                        self._update_status(adjustments=model._adjustment_count)
                except Exception:
                    pass

            # 记录开始时间
            start_time = time.time()

            # 执行任务
            print("⏳ 开始执行任务...\n")
            results = model.execute_with_monitoring(
                task_units=task_units,
                config=plan.initial_config,
                resource_monitor=resource_monitor,
                adjustment_strategy=plan.adjustment_strategy,
                progress_callback=progress_callback,
            )

            # 记录结束时间
            end_time = time.time()

            # 更新最终状态
            self._update_status(completed=len(results), total=len(symbols))
            try:
                if hasattr(model, "_current_processes"):
                    self._update_status(workers=model._current_processes)
                if hasattr(model, "_adjustment_count"):
                    self._update_status(adjustments=model._adjustment_count)
            except Exception:
                pass

            # 等待监控线程完成最后采样
            time.sleep(0.6)

            # 关闭资源监控器
            resource_monitor.close()

            # 统计结果
            success_count = sum(1 for r in results if r.success)
            failed_count = len(results) - success_count

            print(f"\n{'='*80}")
            print(f"✅ 任务执行完成")
            print(f"{'='*80}")
            print(f"📊 执行统计:")
            print(f"  - 总任务数: {len(results)}")
            print(f"  - 成功: {success_count}")
            print(f"  - 失败: {failed_count}")
            print(f"  - 总耗时: {end_time - start_time:.2f}秒")
            print(f"  - 平均吞吐: {len(results) / (end_time - start_time):.2f} 任务/秒")
            print(f"{'='*80}\n")

        finally:
            # 停止监控
            self.monitor.stop()

        # 生成报告
        report = self.monitor.generate_report(test_name)
        return report

    def print_report(self, report: PerformanceReport):
        """打印性能报告"""
        print(f"\n{'='*80}")
        print(f"📊 性能报告: {report.test_name}")
        print(f"{'='*80}")
        print(f"⏱️  时间统计:")
        print(f"  - 开始时间: {datetime.fromtimestamp(report.start_time).strftime('%H:%M:%S')}")
        print(f"  - 结束时间: {datetime.fromtimestamp(report.end_time).strftime('%H:%M:%S')}")
        print(f"  - 总耗时: {report.total_duration:.2f}秒")
        print()

        print(f"💻 CPU使用率:")
        print(f"  - 峰值: {report.peak_cpu:.1f}%")
        print(f"  - 平均值: {report.avg_cpu:.1f}%")
        print()

        print(f"🧠 内存使用率:")
        print(f"  - 峰值: {report.peak_memory:.1f}%")
        print(f"  - 平均值: {report.avg_memory:.1f}%")
        print()

        print(f"⚡ 吞吐量:")
        print(f"  - 峰值: {report.peak_throughput:.2f} 任务/秒")
        print(f"  - 平均值: {report.avg_throughput:.2f} 任务/秒")
        print()

        print(f"🔄 进程数调整:")
        print(f"  - 初始进程数: {report.min_workers}")
        print(f"  - 峰值进程数: {report.peak_workers}")
        print(f"  - 最终进程数: {report.final_workers}")
        print(f"  - 总调整次数: {report.total_adjustments}")
        print()

        # 验证性能峰值
        print(f"🎯 性能峰值验证:")
        cpu_utilization = report.peak_cpu
        memory_utilization = report.peak_memory
        throughput = report.peak_throughput

        cpu_ok = cpu_utilization >= 50.0  # CPU使用率应该至少达到50%
        memory_ok = memory_utilization < 90.0  # 内存使用率不应超过90%
        throughput_ok = throughput > 10.0  # 吞吐量应该至少10任务/秒

        print(f"  - CPU利用率 {'✅' if cpu_ok else '❌'}: {cpu_utilization:.1f}%")
        print(f"  - 内存利用率 {'✅' if memory_ok else '❌'}: {memory_utilization:.1f}%")
        print(f"  - 吞吐量 {'✅' if throughput_ok else '❌'}: {throughput:.2f} 任务/秒")

        if cpu_ok and memory_ok and throughput_ok:
            print(f"\n✅ 性能峰值验证通过！")
        else:
            print(f"\n⚠️ 性能峰值验证未完全通过，需要进一步优化")
        print(f"{'='*80}\n")

    def save_report_json(self, report: PerformanceReport, filepath: Path):
        """保存报告为JSON"""
        report_dict = {
            "test_name": report.test_name,
            "start_time": report.start_time,
            "end_time": report.end_time,
            "total_duration": report.total_duration,
            "peak_cpu": report.peak_cpu,
            "peak_memory": report.peak_memory,
            "peak_throughput": report.peak_throughput,
            "avg_cpu": report.avg_cpu,
            "avg_memory": report.avg_memory,
            "avg_throughput": report.avg_throughput,
            "total_adjustments": report.total_adjustments,
            "final_workers": report.final_workers,
            "peak_workers": report.peak_workers,
            "min_workers": report.min_workers,
            "metrics_history": [
                {
                    "timestamp": m.timestamp,
                    "cpu_percent": m.cpu_percent,
                    "memory_percent": m.memory_percent,
                    "memory_used_mb": m.memory_used_mb,
                    "process_count": m.process_count,
                    "active_threads": m.active_threads,
                    "completed_tasks": m.completed_tasks,
                    "total_tasks": m.total_tasks,
                    "throughput_tasks_per_sec": m.throughput_tasks_per_sec,
                    "queue_size": m.queue_size,
                    "adjustment_count": m.adjustment_count,
                    "current_workers": m.current_workers,
                }
                for m in report.metrics_history
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        print(f"✅ 报告已保存到: {filepath}")


def main():
    """主函数"""
    print("=" * 80)
    print("多进程性能优化验证脚本")
    print("=" * 80)
    print()

    # 检查依赖
    if not HAS_PSUTIL:
        print("❌ 错误: psutil未安装，无法进行性能监控")
        print("   请运行: pip install psutil")
        return 1

    # 获取测试品种列表（使用实际数据目录中的品种）
    data_dir = Path(project_root) / "data"
    if not data_dir.exists():
        print(f"❌ 错误: 数据目录不存在: {data_dir}")
        return 1

    # 查找品种列表
    symbols = []
    symbol_dirs = [d for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith("cache")]
    symbols = [d.name for d in symbol_dirs[:200]]  # 限制200个品种用于测试

    if not symbols or len(symbols) < 10:
        print(f"⚠️ 警告: 数据目录中未找到足够的品种数据（找到{len(symbols)}个）")
        print(f"   使用模拟品种列表进行测试...")
        # 生成更多模拟品种用于测试
        base_symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600001.SH", "600519.SH"]
        symbols = [f"{base}{i:03d}.{'SZ' if i % 2 == 0 else 'SH'}"
                   for base in ["000", "002", "300", "600", "688"]
                   for i in range(1, 41)]  # 200个模拟品种

    print(f"📋 测试品种数量: {len(symbols)}")
    print(f"📋 前5个品种: {symbols[:5]}")
    print()

    # 创建验证器
    verifier = MultiProcessPerformanceVerifier(data_dir=data_dir)

    # 执行验证
    try:
        report = verifier.verify_multiprocess_scan(
            symbols=symbols,
            intervals=["1d"],
            test_name="多进程数据质量扫描性能验证",
        )

        # 打印报告
        verifier.print_report(report)

        # 保存报告
        report_file = Path(project_root) / "performance_report.json"
        verifier.save_report_json(report, report_file)

        return 0

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断测试")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

