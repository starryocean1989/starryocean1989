# -*- coding: utf-8 -*-
"""
质量扫描多进程+多协程性能测试脚本

测试目标：
1. 验证多进程+多协程架构能否达到性能峰值
2. 对比不同进程数和协程数的性能表现
3. 评估CPU、内存和磁盘I/O利用率
4. 检测是否存在资源瓶颈或死锁
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from multiprocessing import Manager, Process
from pathlib import Path
from typing import Dict, List, Optional

import psutil

# 添加项目根目录到路径
# 脚本在 backend/infrastructure/data_module_vnpy/ 目录下
# 需要向上5级到达项目根目录
current_file = Path(__file__).resolve()
# 向上遍历找到包含 'terminal_v0.50' 的目录
project_root = current_file.parent
while project_root.parent != project_root and project_root.name != "terminal_v0.50":
    project_root = project_root.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_quality import (
    _configure_subprocess_logging,
    _quality_scan_worker_async_multiprocess,
    _run_quality_scan_worker_multiprocess,
)

# ==================== 配置日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("quality_scan_test")

# ==================== 测试配置 ====================

TEST_CONFIGS = [
    # (进程数, 每进程协程数, 描述)
    (2, 10, "低并发测试"),
    (4, 20, "中等并发测试"),
    (6, 30, "高并发测试"),
    (8, 40, "极高并发测试"),
]

# 测试品种数（增加到2000以验证真实瓶颈）
TEST_SYMBOL_LIMIT = 2000

DATA_DIR = Path(project_root) / "data" / "kline"


def find_test_symbols(limit: int = 100) -> List[str]:
    """查找测试用的品种代码"""
    if not DATA_DIR.exists():
        logger.error(f"数据目录不存在: {DATA_DIR}")
        return []

    symbols = []
    for symbol_dir in DATA_DIR.iterdir():
        if symbol_dir.is_dir() and not symbol_dir.name.startswith("cache"):
            symbols.append(symbol_dir.name)
            if len(symbols) >= limit:
                break

    logger.info(f"找到 {len(symbols)} 个测试品种")
    return symbols


def run_performance_test(
    num_processes: int,
    connections_per_worker: int,
    symbols: List[str],
    intervals: List[str],
) -> Dict:
    """运行性能测试

    Args:
        num_processes: 进程数
        connections_per_worker: 每进程协程数
        symbols: 品种代码列表
        intervals: K线周期列表

    Returns:
        性能测试结果字典
    """
    logger.info("=" * 80)
    logger.info(
        f"开始测试: {num_processes}进程 × {connections_per_worker}协程 = "
        f"{num_processes * connections_per_worker}总并发"
    )
    logger.info("=" * 80)

    # 1. 初始化多进程对象
    manager = Manager()
    task_queue = manager.Queue()
    result_queue = manager.Queue()
    metrics_queue = manager.Queue()
    progress_queue = manager.Queue()
    stop_event = manager.Event()
    pause_event = manager.Event()
    pause_event.set()  # 默认不暂停

    # 2. 填充任务队列
    for symbol in symbols:
        task_queue.put(symbol)

    # 3. 记录初始资源状态
    start_time = time.time()
    initial_cpu = psutil.cpu_percent(interval=0.1)
    initial_memory = psutil.virtual_memory().percent

    # 4. 启动worker进程池
    processes = []
    try:
        for i in range(num_processes):
            p = Process(
                target=_run_quality_scan_worker_multiprocess,
                args=(
                    i,
                    task_queue,
                    result_queue,
                    metrics_queue,
                    progress_queue,
                    stop_event,
                    pause_event,
                    connections_per_worker,
                    str(DATA_DIR),
                    intervals,
                ),
            )
            p.start()
            processes.append(p)
            logger.debug(f"启动进程 {i} (PID: {p.pid})")
            time.sleep(0.1)

        logger.info(f"已启动 {len(processes)} 个工作进程")

        # 5. 监控进度并收集结果
        total_symbols = len(symbols)
        completed = 0
        timeout_count = 0
        max_timeout_count = 600  # 60秒超时
        results_dict = {}

        # 资源监控数据
        cpu_samples = []
        memory_samples = []
        io_read_samples = []
        io_write_samples = []
        lag_samples = []  # 🆕 协程延迟样本
        pending_tasks_samples = []  # 🆕 待处理任务样本

        # 🆕 导入LagMonitor
        from backend.infrastructure.data_module_vnpy.load_balancer import LagMonitor

        logger.info("开始监控进度和资源使用情况...")

        while completed < total_symbols:
            # 收集进度
            try:
                progress_data = progress_queue.get(timeout=0.1)
                if len(progress_data) == 2:
                    completed += 1
                    timeout_count = 0

                    # 每10%输出一次进度
                    if completed % max(1, total_symbols // 10) == 0 or completed == total_symbols:
                        elapsed = time.time() - start_time
                        current_cpu = psutil.cpu_percent(interval=0)
                        current_memory = psutil.virtual_memory().percent
                        throughput = completed / elapsed if elapsed > 0 else 0
                        percent = int((completed / total_symbols) * 100) if total_symbols > 0 else 0

                        # 🆕 计算协程延迟统计
                        avg_lag = sum(lag_samples[-10:]) / len(lag_samples[-10:]) if len(lag_samples) > 0 else 0
                        max_lag = max(lag_samples) if lag_samples else 0
                        avg_pending = sum(pending_tasks_samples[-10:]) / len(pending_tasks_samples[-10:]) if len(pending_tasks_samples) > 0 else 0

                        logger.info(
                            f"进度: {percent}% ({completed}/{total_symbols}) | "
                            f"CPU={current_cpu:.1f}% | 内存={current_memory:.1f}% | "
                            f"吞吐={throughput:.1f}品种/秒 | "
                            f"延迟={avg_lag:.1f}ms(max={max_lag:.1f}) | 待处理={avg_pending:.0f}"
                        )

                        # 记录资源使用情况
                        cpu_samples.append(current_cpu)
                        memory_samples.append(current_memory)

            except Exception:
                timeout_count += 1
                if timeout_count >= max_timeout_count:
                    logger.warning(f"进度监控超时，已完成: {completed}/{total_symbols}")
                    alive_processes = [p for p in processes if p.is_alive()]
                    if not alive_processes:
                        logger.warning("所有进程已结束，强制退出监控")
                        break
                    timeout_count = 0

            # 🆕 处理监控指标（从独立的metrics_queue）收集协程延迟
            try:
                msg = metrics_queue.get_nowait()
                if LagMonitor.process_lag_message(msg, None, logger):
                    # 提取lag数据
                    _, worker_id, lag_data = msg
                    lag_ms = lag_data.get("lag_ms", 0)
                    pending_tasks = lag_data.get("pending_tasks", 0)
                    lag_samples.append(lag_ms)
                    pending_tasks_samples.append(pending_tasks)
            except Exception:
                pass

            # 收集结果（非阻塞）
            try:
                msg = result_queue.get_nowait()
                symbol, quality_dict = msg
                if quality_dict:
                    results_dict[symbol] = quality_dict
            except Exception:
                pass

            # 定期记录磁盘I/O
            if completed % 50 == 0:
                try:
                    io_counters = psutil.disk_io_counters()
                    if io_counters and hasattr(io_counters, "read_bytes"):
                        io_read_samples.append(io_counters.read_bytes / 1024 / 1024)  # type: ignore  # MB
                        io_write_samples.append(io_counters.write_bytes / 1024 / 1024)  # type: ignore  # MB
                except Exception:
                    pass

        # 6. 最后收集剩余的结果和监控指标
        logger.info("收集剩余结果...")
        while True:
            try:
                msg = metrics_queue.get_nowait()
                if LagMonitor.process_lag_message(msg, None, logger):
                    # 提取lag数据
                    _, worker_id, lag_data = msg
                    lag_ms = lag_data.get("lag_ms", 0)
                    pending_tasks = lag_data.get("pending_tasks", 0)
                    lag_samples.append(lag_ms)
                    pending_tasks_samples.append(pending_tasks)
            except Exception:
                break

        while True:
            try:
                msg = result_queue.get_nowait()
                symbol, quality_dict = msg
                if quality_dict:
                    results_dict[symbol] = quality_dict
            except Exception:
                break

        logger.info(f"收集到 {len(results_dict)} 个结果")

        # 7. 清理进程
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)
        processes.clear()

        # 8. 收集最终统计
        end_time = time.time()
        total_elapsed = end_time - start_time
        final_cpu = psutil.cpu_percent(interval=0.1)
        final_memory = psutil.virtual_memory().percent

        # 计算统计指标
        avg_cpu: float = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
        max_cpu: float = max(cpu_samples) if cpu_samples else 0.0
        avg_memory: float = sum(memory_samples) / len(memory_samples) if memory_samples else 0.0
        max_memory: float = max(memory_samples) if memory_samples else 0.0

        # 🆕 计算协程延迟统计
        avg_lag: float = sum(lag_samples) / len(lag_samples) if lag_samples else 0.0
        max_lag: float = max(lag_samples) if lag_samples else 0.0
        avg_pending: float = sum(pending_tasks_samples) / len(pending_tasks_samples) if pending_tasks_samples else 0.0
        max_pending: float = max(pending_tasks_samples) if pending_tasks_samples else 0.0

        throughput = completed / total_elapsed if total_elapsed > 0 else 0

        result = {
            "config": {
                "num_processes": num_processes,
                "connections_per_worker": connections_per_worker,
                "total_concurrency": num_processes * connections_per_worker,
            },
            "performance": {
                "total_symbols": total_symbols,
                "completed": completed,
                "success_rate": completed / total_symbols if total_symbols > 0 else 0,
                "elapsed_time": round(total_elapsed, 2),
                "throughput_symbols_per_sec": round(throughput, 2),
            },
            "resources": {
                "cpu": {
                    "initial": round(float(initial_cpu), 1),  # type: ignore
                    "final": round(float(final_cpu), 1),  # type: ignore
                    "avg": round(float(avg_cpu), 1),  # type: ignore
                    "max": round(float(max_cpu), 1),  # type: ignore
                },
                "memory": {
                    "initial": round(float(initial_memory), 1),  # type: ignore
                    "final": round(float(final_memory), 1),  # type: ignore
                    "avg": round(float(avg_memory), 1),  # type: ignore
                    "max": round(float(max_memory), 1),  # type: ignore
                },
                "coroutine": {  # 🆕 协程延迟指标
                    "avg_lag_ms": round(float(avg_lag), 1),  # type: ignore
                    "max_lag_ms": round(float(max_lag), 1),  # type: ignore
                    "avg_pending_tasks": round(float(avg_pending), 1),  # type: ignore
                    "max_pending_tasks": round(float(max_pending), 1),  # type: ignore
                },
            },
        }

        logger.info("=" * 80)
        logger.info("测试结果汇总:")
        logger.info(f"  配置: {num_processes}进程 × {connections_per_worker}协程")
        logger.info(f"  完成: {completed}/{total_symbols} ({completed/total_symbols*100:.1f}%)")
        logger.info(f"  耗时: {total_elapsed:.2f}秒")
        logger.info(f"  吞吐: {throughput:.2f}品种/秒")
        logger.info(f"  CPU: 平均={avg_cpu:.1f}%, 峰值={max_cpu:.1f}%")
        logger.info(f"  内存: 平均={avg_memory:.1f}%, 峰值={max_memory:.1f}%")
        logger.info(f"  🆕 协程延迟: 平均={avg_lag:.1f}ms, 峰值={max_lag:.1f}ms")
        logger.info(f"  🆕 待处理任务: 平均={avg_pending:.0f}, 峰值={max_pending:.0f}")
        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)

        # 强制清理进程
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)

        raise


def main():
    """主测试函数"""
    logger.info("🚀 开始质量扫描多进程+多协程性能测试")

    # 查找测试品种
    symbols = find_test_symbols(limit=TEST_SYMBOL_LIMIT)
    if not symbols:
        logger.error("未找到测试品种，请检查数据目录")
        return

    intervals = ["1d", "5m", "1m"]

    # 运行多组测试
    all_results = []
    for num_processes, connections_per_worker, description in TEST_CONFIGS:
        try:
            logger.info(f"\n>>> 测试: {description}")
            result = run_performance_test(
                num_processes=num_processes,
                connections_per_worker=connections_per_worker,
                symbols=symbols,
                intervals=intervals,
            )
            result["description"] = description
            all_results.append(result)

            # 测试间隔
            time.sleep(2)

        except Exception as e:
            logger.error(f"测试失败: {e}", exc_info=True)

    # 生成报告
    logger.info("\n" + "=" * 80)
    logger.info("📊 性能测试完整报告")
    logger.info("=" * 80)

    for result in all_results:
        config = result["config"]
        perf = result["performance"]
        resources = result["resources"]
        coroutine = resources.get("coroutine", {})

        logger.info(f"\n{result['description']}:")
        logger.info(f"  配置: {config['num_processes']}进程 × {config['connections_per_worker']}协程")
        logger.info(f"  吞吐: {perf['throughput_symbols_per_sec']:.2f}品种/秒")
        logger.info(f"  CPU: 平均={resources['cpu']['avg']:.1f}%, 峰值={resources['cpu']['max']:.1f}%")
        logger.info(
            f"  内存: 平均={resources['memory']['avg']:.1f}%, 峰值={resources['memory']['max']:.1f}%"
        )
        logger.info(
            f"  🆕 协程延迟: 平均={coroutine.get('avg_lag_ms', 0):.1f}ms, "
            f"峰值={coroutine.get('max_lag_ms', 0):.1f}ms"
        )
        logger.info(
            f"  🆕 待处理任务: 平均={coroutine.get('avg_pending_tasks', 0):.0f}, "
            f"峰值={coroutine.get('max_pending_tasks', 0):.0f}"
        )

    # 保存JSON报告
    report_file = project_root / "quality_scan_performance_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "test_time": datetime.now().isoformat(),
                "results": all_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info(f"\n📄 详细报告已保存: {report_file}")

    # 性能分析
    if len(all_results) >= 2:
        logger.info("\n" + "=" * 80)
        logger.info("📈 性能分析")
        logger.info("=" * 80)

        best_result = max(all_results, key=lambda x: x["performance"]["throughput_symbols_per_sec"])
        logger.info(f"\n🏆 最佳配置: {best_result['description']}")
        logger.info(f"  吞吐: {best_result['performance']['throughput_symbols_per_sec']:.2f}品种/秒")
        logger.info(
            f"  配置: {best_result['config']['num_processes']}进程 × "
            f"{best_result['config']['connections_per_worker']}协程"
        )

        # 计算性能提升
        first_throughput = all_results[0]["performance"]["throughput_symbols_per_sec"]
        best_throughput = best_result["performance"]["throughput_symbols_per_sec"]
        improvement = (best_throughput / first_throughput - 1) * 100 if first_throughput > 0 else 0
        logger.info(f"  相对提升: {improvement:.1f}%")

        # CPU利用率分析
        best_cpu_avg = best_result["resources"]["cpu"]["avg"]
        if best_cpu_avg < 50:
            logger.info("⚠️  CPU利用率偏低，建议增加并发数")
        elif best_cpu_avg > 80:
            logger.info("⚠️  CPU利用率偏高，可能达到性能瓶颈")


if __name__ == "__main__":
    main()

