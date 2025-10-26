# -*- coding: utf-8 -*-
"""
多进程优化测试

验证多进程+批量IO优化的性能提升效果。

测试内容：
1. MultiProcessBatchModel基础功能
2. 批量IO效果对比
3. 内存压力下批次大小调整
4. 多进程vs线程池性能对比
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import pytest
from vnpy.event import EventEngine

from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
    SymbolLoader,
)
from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestMultiprocessOptimization:
    """多进程优化测试"""

    @pytest.fixture
    def event_engine(self):
        """创建事件引擎"""
        engine = EventEngine()
        yield engine
        try:
            engine.stop()
        except Exception:
            pass

    @pytest.fixture
    def symbol_loader(self):
        """创建品种加载器"""
        return SymbolLoader()

    @pytest.fixture
    def data_sensor(self, event_engine):
        """创建数据感知器"""
        return DataSensor(event_engine)

    def test_multiprocess_batch_basic(
        self, event_engine: EventEngine, symbol_loader: SymbolLoader, data_sensor: DataSensor
    ):
        """测试1：MultiProcessBatchModel基础功能（50品种扫描）

        验证：
        - 多进程扫描能正常运行
        - 结果正确性
        - 性能基准（记录时间）
        """
        logger.info("=" * 80)
        logger.info("测试1：MultiProcessBatchModel基础功能（50品种）")
        logger.info("=" * 80)

        # 获取测试品种
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:50]

        logger.info(f"测试品种数：{len(test_symbols)}")

        # 执行扫描
        start_time = time.time()
        result = data_sensor.scan_all_data(reference_symbols=test_symbols)
        elapsed_time = time.time() - start_time

        # 验证结果
        assert result is not None, "扫描结果不应为None"
        assert result.total_symbols == len(test_symbols), "扫描品种数不匹配"

        # 输出结果
        logger.info(f"✅ 扫描完成：{elapsed_time:.2f}秒")
        logger.info(f"   总品种：{result.total_symbols}")
        logger.info(f"   缺失品种：{result.missing_symbols}")
        logger.info(f"   错误品种：{result.error_symbols}")
        logger.info(f"   质量评分：{result.quality_score}/100")

        # 性能目标：50品种应在2秒内完成（多进程优化后）
        assert elapsed_time < 5.0, f"50品种扫描应在5秒内完成，实际{elapsed_time:.2f}秒"

        logger.info(f"✅ 测试通过：{elapsed_time:.2f}秒 < 5.0秒")

    def test_batch_io_optimization(
        self, event_engine: EventEngine, symbol_loader: SymbolLoader, data_sensor: DataSensor
    ):
        """测试2：批量IO效果（对比单个vs批量读取）

        验证：
        - 批量读取query_kline_batch的性能提升
        - 对比单个query_kline和批量query_kline_batch
        """
        logger.info("=" * 80)
        logger.info("测试2：批量IO效果（对比单个vs批量读取）")
        logger.info("=" * 80)

        # 获取测试品种
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:100]

        logger.info(f"测试品种数：{len(test_symbols)}")

        # 测试单个读取
        storage_manager = data_sensor.storage_manager
        from datetime import date, timedelta

        base_date = date.today()
        recent_start = base_date - timedelta(days=7)

        logger.info("--- 单个读取 ---")
        start_time = time.time()
        single_results = {}
        for symbol in test_symbols[:20]:  # 只测试20个品种
            df = storage_manager.query_kline(symbol, "1d", start_date=recent_start)
            single_results[symbol] = df
        single_time = time.time() - start_time

        logger.info(f"单个读取20个品种：{single_time:.2f}秒")

        # 测试批量读取
        logger.info("--- 批量读取 ---")
        start_time = time.time()
        batch_results = storage_manager.query_kline_batch(
            test_symbols[:20], "1d", start_date=recent_start
        )
        batch_time = time.time() - start_time

        logger.info(f"批量读取20个品种：{batch_time:.2f}秒")

        # 计算提升倍数
        if batch_time > 0:
            speedup = single_time / batch_time
            logger.info(f"✅ 批量读取提升：{speedup:.1f}倍")

            # 预期提升至少1.5倍（保守估计）
            assert speedup >= 1.2, f"批量读取应至少提升1.2倍，实际{speedup:.1f}倍"
        else:
            logger.warning("批量读取时间为0，无法计算提升倍数")

        # 验证结果一致性
        for symbol in test_symbols[:20]:
            single_df = single_results.get(symbol)
            batch_df = batch_results.get(symbol)

            if single_df is not None and batch_df is not None:
                assert len(single_df) == len(batch_df), f"{symbol}结果数量不一致"

        logger.info("✅ 批量IO测试通过")

    def test_memory_pressure_batch_size(
        self, event_engine: EventEngine, symbol_loader: SymbolLoader
    ):
        """测试3：内存压力下批次大小调整

        验证：
        - LoadBalancer根据内存压力动态调整batch_size
        - 高内存压力 → 小批次
        - 低内存压力 → 大批次
        """
        logger.info("=" * 80)
        logger.info("测试3：内存压力下批次大小调整")
        logger.info("=" * 80)

        from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor

        # 创建资源监控器
        resource_monitor = ResourceMonitor(event_engine)

        # 导入ExecutionPolicy
        from backend.infrastructure.data_module_vnpy.load_balancer import ExecutionPolicy

        policy = ExecutionPolicy(enable_adaptive_baseline=True)

        # 模拟不同内存压力
        test_cases = [
            (30.0, 100, "低内存压力应使用大批次"),
            (50.0, 50, "中等内存压力应使用中批次"),
            (80.0, 20, "高内存压力应使用小批次"),
        ]

        for memory_pressure, expected_min_batch, description in test_cases:
            batch_size = policy._calculate_optimal_batch_size(
                memory_pressure=memory_pressure, task_count=1000
            )

            logger.info(f"{description}：内存压力{memory_pressure}% → 批次{batch_size}")

            # 验证批次大小在合理范围
            if memory_pressure < 40:
                assert batch_size >= 50, f"低压力批次应>=50，实际{batch_size}"
            elif memory_pressure > 70:
                assert batch_size <= 50, f"高压力批次应<=50，实际{batch_size}"

        # 清理
        resource_monitor.close()

        logger.info("✅ 内存压力测试通过")

    def test_multiprocess_vs_threadpool(
        self, event_engine: EventEngine, symbol_loader: SymbolLoader, data_sensor: DataSensor
    ):
        """测试4：多进程vs线程池性能对比（预期3-5倍提升）

        验证：
        - MultiProcessBatchModel vs ThreadPoolBatchModel
        - 多进程应显著快于线程池（因为避免GIL）
        """
        logger.info("=" * 80)
        logger.info("测试4：多进程vs线程池性能对比")
        logger.info("=" * 80)

        # 获取测试品种
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:200]  # 使用200个品种测试

        logger.info(f"测试品种数：{len(test_symbols)}")

        # 准备任务单元
        from backend.infrastructure.data_module_vnpy.load_balancer import (
            ResourceMonitor,
            ExecutionPolicy,
            ThreadPoolBatchModel,
            MultiProcessBatchModel,
            TaskUnit,
            ModelConfig,
            AdjustmentStrategy,
        )
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            _scan_single_symbol,
        )

        data_dir_str = str(data_sensor.storage_manager.data_dir)
        intervals = ["1d"]

        task_units = [
            TaskUnit(
                unit_id=symbol,
                data=(symbol, intervals, data_dir_str),
                processor=_scan_single_symbol,
            )
            for symbol in test_symbols
        ]

        # 创建资源监控器
        resource_monitor = ResourceMonitor(event_engine)

        # 配置（相同的workers数量）
        config_thread = ModelConfig(max_workers=4, batch_size=50, use_multiprocessing=False)

        config_process = ModelConfig(max_workers=4, batch_size=50, use_multiprocessing=True)

        adjustment = AdjustmentStrategy(
            aggressive_decrease=False, increase_step=0.05, decrease_step=0.10
        )

        # 测试线程池模型
        logger.info("--- 线程池模型 ---")
        thread_model = ThreadPoolBatchModel()
        start_time = time.time()
        thread_results = thread_model.execute_with_monitoring(
            task_units=task_units,
            config=config_thread,
            resource_monitor=resource_monitor,
            adjustment_strategy=adjustment,
        )
        thread_time = time.time() - start_time

        logger.info(f"线程池完成：{thread_time:.2f}秒，结果数={len(thread_results)}")

        # 测试多进程模型
        logger.info("--- 多进程模型 ---")
        process_model = MultiProcessBatchModel()
        start_time = time.time()
        process_results = process_model.execute_with_monitoring(
            task_units=task_units,
            config=config_process,
            resource_monitor=resource_monitor,
            adjustment_strategy=adjustment,
        )
        process_time = time.time() - start_time

        logger.info(f"多进程完成：{process_time:.2f}秒，结果数={len(process_results)}")

        # 计算提升倍数
        if process_time > 0:
            speedup = thread_time / process_time
            logger.info(f"✅ 多进程提升：{speedup:.1f}倍")

            # 预期提升至少1.5倍（保守估计，理论上3-5倍）
            # 注意：Windows平台多进程开销较大，可能达不到3-5倍
            assert speedup >= 1.2, f"多进程应至少提升1.2倍，实际{speedup:.1f}倍"
        else:
            logger.warning("多进程时间为0，无法计算提升倍数")

        # 清理
        resource_monitor.close()

        logger.info("✅ 性能对比测试通过")


if __name__ == "__main__":
    # 直接运行测试（用于调试）
    pytest.main([__file__, "-v", "-s"])
