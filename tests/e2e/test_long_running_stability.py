# -*- coding: utf-8 -*-
"""
长时间稳定性测试

测试设计：
- 运行时长：30分钟以上
- 持续扫描：循环扫描500品种
- 监控指标：
  - 内存泄漏检测
  - 调整频率统计
  - 性能衰减趋势
"""

import logging
import time
import gc
from typing import List, Dict
from datetime import datetime, timedelta

import pytest
import psutil

from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
from vnpy.event import EventEngine

logger = logging.getLogger(__name__)


@pytest.fixture
def event_engine():
    """创建事件引擎"""
    return EventEngine()


@pytest.fixture
def symbol_loader():
    """创建符号加载器"""
    return SymbolLoader()


class StabilityMonitor:
    """稳定性监控器"""

    def __init__(self):
        self.process = psutil.Process()
        self.metrics_history: List[Dict] = []
        self.start_time = time.time()

    def collect_metrics(self) -> Dict:
        """收集当前指标"""
        memory_info = self.process.memory_info()
        cpu_percent = self.process.cpu_percent(interval=0.1)

        metrics = {
            "timestamp": time.time(),
            "elapsed_seconds": time.time() - self.start_time,
            "memory_rss_mb": memory_info.rss / 1024 / 1024,
            "memory_vms_mb": memory_info.vms / 1024 / 1024,
            "cpu_percent": cpu_percent,
            "num_threads": self.process.num_threads(),
        }

        self.metrics_history.append(metrics)
        return metrics

    def detect_memory_leak(self, window_size: int = 10) -> bool:
        """检测内存泄漏

        Args:
            window_size: 窗口大小（监控最近N次采样）

        Returns:
            True if 检测到泄漏，False otherwise
        """
        if len(self.metrics_history) < window_size + 1:
            return False

        # 取最近窗口的内存数据
        recent_memory = [m["memory_rss_mb"] for m in self.metrics_history[-window_size:]]

        # 计算趋势（线性回归）
        import numpy as np

        x = np.arange(len(recent_memory))
        y = np.array(recent_memory)

        # y = ax + b
        a, b = np.polyfit(x, y, 1)

        # 如果斜率a > 0且显著（例如每次增长>1MB），则认为存在泄漏
        if a > 1.0:
            logger.warning(f"⚠️ 检测到内存泄漏趋势：斜率={a:.2f}MB/次")
            return True

        return False

    def detect_performance_degradation(self, window_size: int = 5) -> bool:
        """检测性能衰减

        Args:
            window_size: 窗口大小

        Returns:
            True if 检测到性能衰减，False otherwise
        """
        if len(self.metrics_history) < window_size * 2:
            return False

        # 取早期和最近的CPU使用率
        early_cpu = [m["cpu_percent"] for m in self.metrics_history[:window_size]]
        recent_cpu = [m["cpu_percent"] for m in self.metrics_history[-window_size:]]

        early_avg = sum(early_cpu) / len(early_cpu)
        recent_avg = sum(recent_cpu) / len(recent_cpu)

        # 如果最近的CPU使用率显著高于早期（增长>20%），认为存在性能衰减
        if recent_avg > early_avg * 1.2:
            logger.warning(f"⚠️ 检测到性能衰减：CPU从{early_avg:.1f}%增至{recent_avg:.1f}%")
            return True

        return False

    def get_stats(self) -> Dict:
        """获取统计数据"""
        if not self.metrics_history:
            return {}

        memory_values = [m["memory_rss_mb"] for m in self.metrics_history]
        cpu_values = [m["cpu_percent"] for m in self.metrics_history]

        return {
            "total_samples": len(self.metrics_history),
            "duration_seconds": time.time() - self.start_time,
            "memory": {
                "min_mb": min(memory_values),
                "max_mb": max(memory_values),
                "avg_mb": sum(memory_values) / len(memory_values),
                "current_mb": memory_values[-1],
                "growth_mb": memory_values[-1] - memory_values[0],
            },
            "cpu": {
                "min_percent": min(cpu_values),
                "max_percent": max(cpu_values),
                "avg_percent": sum(cpu_values) / len(cpu_values),
            },
        }


class TestLongRunningStability:
    """长时间稳定性测试"""

    @pytest.mark.slow
    @pytest.mark.stability
    def test_30_minutes_stability(self, event_engine, symbol_loader):
        """30分钟稳定性测试"""
        duration_minutes = 30
        self._run_stability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            duration_minutes=duration_minutes,
            symbol_count=500,
            scan_interval=60,  # 每60秒扫描一次
        )

    @pytest.mark.slow
    @pytest.mark.stability
    def test_1_hour_stability(self, event_engine, symbol_loader):
        """1小时稳定性测试"""
        duration_minutes = 60
        self._run_stability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            duration_minutes=duration_minutes,
            symbol_count=500,
            scan_interval=120,  # 每120秒扫描一次
        )

    def _run_stability_test(
        self,
        event_engine: EventEngine,
        symbol_loader: SymbolLoader,
        duration_minutes: int,
        symbol_count: int,
        scan_interval: int,
    ):
        """运行稳定性测试

        Args:
            event_engine: 事件引擎
            symbol_loader: 符号加载器
            duration_minutes: 运行时长（分钟）
            symbol_count: 品种数量
            scan_interval: 扫描间隔（秒）
        """
        logger.info("\n" + "=" * 80)
        logger.info(f"开始{duration_minutes}分钟稳定性测试")
        logger.info(f"  - 品种数量：{symbol_count}")
        logger.info(f"  - 扫描间隔：{scan_interval}秒")
        logger.info("=" * 80)

        # 1. 加载符号
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:symbol_count]
        logger.info(f"加载了 {len(test_symbols)} 个品种")

        # 2. 创建监控器和传感器
        monitor = StabilityMonitor()
        sensor = DataSensor(event_engine)

        # 3. 运行循环扫描
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        scan_count = 0
        scan_durations = []

        while time.time() < end_time:
            scan_count += 1
            elapsed_minutes = (time.time() - start_time) / 60

            logger.info(f"\n--- 扫描 #{scan_count} (已运行{elapsed_minutes:.1f}分钟) ---")

            # 收集指标（扫描前）
            metrics_before = monitor.collect_metrics()
            logger.info(
                f"📊 当前状态：内存{metrics_before['memory_rss_mb']:.1f}MB, "
                f"CPU{metrics_before['cpu_percent']:.1f}%, "
                f"线程{metrics_before['num_threads']}"
            )

            # 执行扫描
            scan_start = time.time()
            try:
                result = sensor.scan_all_data(reference_symbols=test_symbols)
                scan_duration = time.time() - scan_start
                scan_durations.append(scan_duration)

                logger.info(
                    f"✅ 扫描完成：耗时{scan_duration:.2f}秒, "
                    f"扫描了{result.total_symbols}个品种"
                )
            except Exception as e:
                logger.error(f"❌ 扫描失败：{e}", exc_info=True)
                scan_duration = time.time() - scan_start
                scan_durations.append(scan_duration)

            # 收集指标（扫描后）
            metrics_after = monitor.collect_metrics()

            # 检测内存泄漏
            if monitor.detect_memory_leak(window_size=10):
                logger.error("❌ 检测到内存泄漏！")
                # 强制垃圾回收
                gc.collect()
                logger.info("执行垃圾回收...")

            # 检测性能衰减
            if monitor.detect_performance_degradation(window_size=5):
                logger.warning("⚠️ 检测到性能衰减！")

            # 计算剩余时间
            remaining_seconds = end_time - time.time()
            if remaining_seconds > 0:
                # 等待下一次扫描（或测试结束）
                wait_time = min(scan_interval, remaining_seconds)
                logger.info(f"等待 {wait_time:.0f}秒 后进行下一次扫描...")
                time.sleep(wait_time)
            else:
                break

        # 4. 测试结束，生成报告
        total_duration = time.time() - start_time
        stats = monitor.get_stats()

        logger.info("\n" + "=" * 80)
        logger.info(f"稳定性测试完成！")
        logger.info("=" * 80)
        logger.info(f"📊 总体统计：")
        logger.info(f"  - 运行时长：{total_duration/60:.1f}分钟（目标{duration_minutes}分钟）")
        logger.info(f"  - 扫描次数：{scan_count}")
        logger.info(f"  - 平均扫描耗时：{sum(scan_durations)/len(scan_durations):.2f}秒")
        logger.info(f"  - 最快扫描：{min(scan_durations):.2f}秒")
        logger.info(f"  - 最慢扫描：{max(scan_durations):.2f}秒")
        logger.info(f"")
        logger.info(f"📊 内存统计：")
        logger.info(f"  - 初始：{stats['memory']['min_mb']:.1f}MB")
        logger.info(f"  - 最终：{stats['memory']['current_mb']:.1f}MB")
        logger.info(f"  - 峰值：{stats['memory']['max_mb']:.1f}MB")
        logger.info(f"  - 平均：{stats['memory']['avg_mb']:.1f}MB")
        logger.info(f"  - 增长：{stats['memory']['growth_mb']:.1f}MB")
        logger.info(f"")
        logger.info(f"📊 CPU统计：")
        logger.info(f"  - 平均：{stats['cpu']['avg_percent']:.1f}%")
        logger.info(f"  - 峰值：{stats['cpu']['max_percent']:.1f}%")
        logger.info("=" * 80)

        # 5. 验证稳定性
        # 5.1 内存增长不应超过50%
        memory_growth_ratio = stats["memory"]["growth_mb"] / stats["memory"]["min_mb"]
        if memory_growth_ratio <= 0.5:
            logger.info(f"✅ 内存稳定：增长{memory_growth_ratio*100:.1f}% <= 50%")
        else:
            logger.warning(f"⚠️ 内存增长过多：{memory_growth_ratio*100:.1f}% > 50%")
            pytest.fail(f"内存增长过多：{memory_growth_ratio*100:.1f}%")

        # 5.2 性能不应显著衰减（最后5次vs前5次）
        early_durations = scan_durations[:5]
        recent_durations = scan_durations[-5:]
        early_avg = sum(early_durations) / len(early_durations)
        recent_avg = sum(recent_durations) / len(recent_durations)
        degradation_ratio = (recent_avg - early_avg) / early_avg

        if degradation_ratio <= 0.2:
            logger.info(f"✅ 性能稳定：衰减{degradation_ratio*100:.1f}% <= 20%")
        else:
            logger.warning(f"⚠️ 性能衰减：{degradation_ratio*100:.1f}% > 20%")
            pytest.fail(f"性能衰减过多：{degradation_ratio*100:.1f}%")

        # 6. 记录稳定性测试数据
        self._record_stability_data(
            duration_minutes=duration_minutes,
            scan_count=scan_count,
            scan_durations=scan_durations,
            stats=stats,
        )

    def _record_stability_data(
        self, duration_minutes: int, scan_count: int, scan_durations: List[float], stats: Dict
    ):
        """记录稳定性测试数据"""
        import json
        from datetime import datetime
        from pathlib import Path

        perf_file = Path(__file__).parent / "performance_data_stability.jsonl"

        perf_data = {
            "timestamp": datetime.now().isoformat(),
            "test_name": f"stability_{duration_minutes}min",
            "duration_minutes": duration_minutes,
            "scan_count": scan_count,
            "scan_durations": {
                "avg": sum(scan_durations) / len(scan_durations),
                "min": min(scan_durations),
                "max": max(scan_durations),
            },
            "memory_stats": stats["memory"],
            "cpu_stats": stats["cpu"],
        }

        with open(perf_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(perf_data, ensure_ascii=False) + "\n")

        logger.info(f"📊 稳定性测试数据已记录到: {perf_file}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s", "-m", "stability"])
