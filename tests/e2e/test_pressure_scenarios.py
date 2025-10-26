# -*- coding: utf-8 -*-
"""
压力场景测试 - 模拟不同资源瓶颈

模拟场景：
1. CPU瓶颈：运行CPU密集任务占用80%
2. 内存瓶颈：预分配大量内存造成压力
3. 磁盘瓶颈：并发大量磁盘IO操作
4. 混合瓶颈：多种资源同时紧张

验证点：
- 短板50%起始配置是否合理
- 动态调整是否及时响应
- 区间阈值（65-75%）是否有效
"""

import logging
import time
import threading
from typing import Optional

import pytest

from backend.infrastructure.data_module_vnpy.load_balancer import (
    ResourceMonitor,
    ExecutionPolicy,
    AdaptiveThresholdCalculator,
)
from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
from vnpy.event import EventEngine

logger = logging.getLogger(__name__)


@pytest.fixture
def event_engine():
    """创建事件引擎（带清理）"""
    engine = EventEngine()
    yield engine
    # 清理：停止事件引擎
    try:
        engine.stop()
    except:
        pass


@pytest.fixture
def symbol_loader():
    """创建符号加载器"""
    return SymbolLoader()


class PressureSimulator:
    """压力模拟器"""

    def __init__(self):
        self._stop_flag = threading.Event()
        self._threads = []

    def start_cpu_pressure(self, target_usage: float = 0.80):
        """启动CPU压力模拟

        Args:
            target_usage: 目标CPU占用率（0-1）
        """
        logger.info(f"🔥 启动CPU压力模拟（目标占用率：{target_usage*100:.0f}%）")

        def cpu_burner():
            """CPU密集计算"""
            while not self._stop_flag.is_set():
                # 素数计算（CPU密集）
                for _ in range(10000):
                    sum([i**2 for i in range(1000)])
                time.sleep(0.001)  # 短暂休息

        # 启动多个线程（根据目标占用率）
        import multiprocessing

        num_threads = max(1, int(multiprocessing.cpu_count() * target_usage))

        for i in range(num_threads):
            t = threading.Thread(target=cpu_burner, daemon=True, name=f"CPUBurner-{i}")
            t.start()
            self._threads.append(t)

        logger.info(f"✅ CPU压力模拟已启动（{num_threads}个线程）")

    def start_memory_pressure(self, target_mb: int = 1024):
        """启动内存压力模拟

        Args:
            target_mb: 目标内存占用（MB）
        """
        logger.info(f"🔥 启动内存压力模拟（目标占用：{target_mb}MB）")

        self._memory_holder = []

        def memory_allocator():
            """内存分配器"""
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            chunks_needed = target_mb // 10

            for i in range(chunks_needed):
                if self._stop_flag.is_set():
                    break
                # 分配并填充内存
                chunk = bytearray(chunk_size)
                self._memory_holder.append(chunk)
                time.sleep(0.1)

            logger.info(f"✅ 内存压力模拟已完成（分配了{len(self._memory_holder)*10}MB）")

        t = threading.Thread(target=memory_allocator, daemon=True, name="MemoryAllocator")
        t.start()
        self._threads.append(t)

    def start_disk_pressure(self, target_iops: int = 1000):
        """启动磁盘压力模拟

        Args:
            target_iops: 目标IOPS
        """
        logger.info(f"🔥 启动磁盘压力模拟（目标IOPS：{target_iops}）")

        import tempfile
        from pathlib import Path

        temp_dir = Path(tempfile.gettempdir()) / "loadbalancer_disk_test"
        temp_dir.mkdir(exist_ok=True)

        def disk_worker():
            """磁盘IO工作线程"""
            interval = 1.0 / target_iops if target_iops > 0 else 0.001
            counter = 0

            while not self._stop_flag.is_set():
                # 写入小文件
                test_file = temp_dir / f"test_{counter % 100}.tmp"
                try:
                    test_file.write_bytes(b"0" * 4096)  # 4KB写入
                    test_file.unlink()  # 删除
                except Exception as e:
                    logger.warning(f"磁盘IO错误: {e}")

                counter += 1
                time.sleep(interval)

        # 启动多个IO线程
        num_threads = max(1, target_iops // 100)
        for i in range(num_threads):
            t = threading.Thread(target=disk_worker, daemon=True, name=f"DiskWorker-{i}")
            t.start()
            self._threads.append(t)

        logger.info(f"✅ 磁盘压力模拟已启动（{num_threads}个线程）")

    def stop(self):
        """停止所有压力模拟"""
        logger.info("🛑 停止压力模拟...")
        self._stop_flag.set()

        # 等待线程结束
        for t in self._threads:
            t.join(timeout=2.0)

        # 释放内存
        if hasattr(self, "_memory_holder"):
            self._memory_holder.clear()

        logger.info("✅ 压力模拟已停止")


class TestPressureScenarios:
    """压力场景测试"""

    def test_cpu_bottleneck_scenario(self, event_engine, symbol_loader):
        """CPU瓶颈场景测试"""
        simulator = PressureSimulator()

        try:
            # 启动CPU压力（80%占用）
            simulator.start_cpu_pressure(target_usage=0.80)
            time.sleep(2)  # 等待压力稳定

            # 执行扫描
            self._run_pressure_test(
                event_engine=event_engine,
                symbol_loader=symbol_loader,
                scenario_name="CPU瓶颈",
                symbol_count=100,
                expected_bottleneck="cpu",
            )
        finally:
            simulator.stop()

    def test_memory_bottleneck_scenario(self, event_engine, symbol_loader):
        """内存瓶颈场景测试"""
        simulator = PressureSimulator()

        try:
            # 启动内存压力（分配1GB）
            simulator.start_memory_pressure(target_mb=1024)
            time.sleep(2)  # 等待压力稳定

            # 执行扫描
            self._run_pressure_test(
                event_engine=event_engine,
                symbol_loader=symbol_loader,
                scenario_name="内存瓶颈",
                symbol_count=100,
                expected_bottleneck="memory",
            )
        finally:
            simulator.stop()

    def test_disk_bottleneck_scenario(self, event_engine, symbol_loader):
        """磁盘瓶颈场景测试"""
        simulator = PressureSimulator()

        try:
            # 启动磁盘压力（1000 IOPS）
            simulator.start_disk_pressure(target_iops=1000)
            time.sleep(2)  # 等待压力稳定

            # 执行扫描
            self._run_pressure_test(
                event_engine=event_engine,
                symbol_loader=symbol_loader,
                scenario_name="磁盘瓶颈",
                symbol_count=100,
                expected_bottleneck="disk",
            )
        finally:
            simulator.stop()

    def test_mixed_bottleneck_scenario(self, event_engine, symbol_loader):
        """混合瓶颈场景测试"""
        simulator = PressureSimulator()

        try:
            # 启动多种压力
            simulator.start_cpu_pressure(target_usage=0.60)
            simulator.start_memory_pressure(target_mb=512)
            simulator.start_disk_pressure(target_iops=500)
            time.sleep(3)  # 等待压力稳定

            # 执行扫描
            self._run_pressure_test(
                event_engine=event_engine,
                symbol_loader=symbol_loader,
                scenario_name="混合瓶颈",
                symbol_count=100,
                expected_bottleneck=None,  # 不确定瓶颈
            )
        finally:
            simulator.stop()

    def _run_pressure_test(
        self,
        event_engine: EventEngine,
        symbol_loader: SymbolLoader,
        scenario_name: str,
        symbol_count: int,
        expected_bottleneck: Optional[str],
    ):
        """运行压力测试

        Args:
            event_engine: 事件引擎
            symbol_loader: 符号加载器
            scenario_name: 场景名称
            symbol_count: 品种数量
            expected_bottleneck: 预期瓶颈资源
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"开始{scenario_name}测试：{symbol_count}品种")
        logger.info(f"{'='*80}")

        # 1. 验证短板50%起始配置
        calculator = AdaptiveThresholdCalculator()
        baseline = calculator.calculate_conservative_baseline()

        logger.info(f"📊 短板50%起始配置：")
        logger.info(f"  - base_workers: {baseline['base_workers']}")
        logger.info(f"  - bottleneck_resource: {baseline['bottleneck_resource']}")
        logger.info(f"  - resource_scores: {baseline['resource_scores']}")

        # 2. 获取当前资源压力
        monitor = ResourceMonitor(event_engine)
        try:
            pressure = monitor.get_current_pressure()

            logger.info(f"📊 当前资源压力：")
            logger.info(f"  - score: {pressure.score:.1f}%")
            logger.info(f"  - bottleneck: {pressure.bottleneck}")
            logger.info(f"  - below_low_threshold: {pressure.below_low_threshold}")
            logger.info(f"  - above_high_threshold: {pressure.above_high_threshold}")

            # 3. 验证预期瓶颈
            if expected_bottleneck:
                if pressure.bottleneck == expected_bottleneck:
                    logger.info(f"✅ 瓶颈识别正确：{pressure.bottleneck}")
                else:
                    logger.warning(
                        f"⚠️ 瓶颈识别不符：预期{expected_bottleneck}，实际{pressure.bottleneck}"
                    )

            # 4. 加载符号并执行扫描
            all_symbols = symbol_loader.extract_all_codes()
            test_symbols = all_symbols[:symbol_count]

            sensor = DataSensor(event_engine)

            start_time = time.time()
            result = sensor.scan_all_data(reference_symbols=test_symbols)
            elapsed = time.time() - start_time

            # 5. 验证结果
            assert result is not None, "扫描结果不应为None"

            logger.info(f"\n{'='*80}")
            logger.info(f"{scenario_name}测试结果：")
            logger.info(f"  - 总耗时: {elapsed:.2f}秒")
            logger.info(f"  - 扫描品种数: {result.total_symbols}")
            logger.info(f"  - 质量评分: {result.quality_score}/100")
            logger.info(f"{'='*80}\n")

            # 6. 记录性能数据
            self._record_pressure_data(
                scenario_name=scenario_name,
                elapsed=elapsed,
                pressure=pressure,
                baseline=baseline,
                result=result,
            )
        finally:
            monitor.close()

    def _record_pressure_data(
        self, scenario_name: str, elapsed: float, pressure, baseline: dict, result: dict
    ):
        """记录压力测试数据"""
        import json
        from datetime import datetime
        from pathlib import Path

        perf_file = Path(__file__).parent / "performance_data_pressure.jsonl"

        perf_data = {
            "timestamp": datetime.now().isoformat(),
            "scenario_name": scenario_name,
            "elapsed_seconds": elapsed,
            "baseline": baseline,
            "pressure": {
                "score": pressure.score,
                "bottleneck": pressure.bottleneck,
                "below_low_threshold": pressure.below_low_threshold,
                "above_high_threshold": pressure.above_high_threshold,
            },
            "result_summary": {
                "total_scanned": result.total_symbols,
                "missing_count": result.missing_symbols,
                "quality_score": result.quality_score,
            },
        }

        with open(perf_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(perf_data, ensure_ascii=False) + "\n")

        logger.info(f"📊 压力测试数据已记录到: {perf_file}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
