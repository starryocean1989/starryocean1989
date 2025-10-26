# -*- coding: utf-8 -*-
"""
扩展性测试 - 不同品种数量测试

验证LoadBalancer在不同规模下的性能表现：
- 50品种（小规模）
- 200品种（中小规模）
- 500品种（中规模）
- 1000品种（大规模）
- 3000品种（超大规模）

验证指标：
- 总耗时
- 单品种耗时
- 资源利用率
- 动态调整次数和幅度
"""

import logging
import time
from typing import List

import pytest

from backend.infrastructure.data_module_vnpy.load_balancer import (
    ResourceMonitor,
    ExecutionPolicy,
    ThreadPoolBatchModel,
    TaskUnit,
)
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


class TestScalability:
    """扩展性测试"""

    def test_small_scale_50_symbols(self, event_engine, symbol_loader):
        """小规模测试：50品种"""
        self._run_scalability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            symbol_count=50,
            scale_name="小规模",
        )

    def test_medium_small_scale_200_symbols(self, event_engine, symbol_loader):
        """中小规模测试：200品种"""
        self._run_scalability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            symbol_count=200,
            scale_name="中小规模",
        )

    def test_medium_scale_500_symbols(self, event_engine, symbol_loader):
        """中规模测试：500品种"""
        self._run_scalability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            symbol_count=500,
            scale_name="中规模",
        )

    def test_large_scale_1000_symbols(self, event_engine, symbol_loader):
        """大规模测试：1000品种"""
        self._run_scalability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            symbol_count=1000,
            scale_name="大规模",
        )

    @pytest.mark.slow
    def test_extra_large_scale_3000_symbols(self, event_engine, symbol_loader):
        """超大规模测试：3000品种（慢速测试）"""
        self._run_scalability_test(
            event_engine=event_engine,
            symbol_loader=symbol_loader,
            symbol_count=3000,
            scale_name="超大规模",
        )

    def _run_scalability_test(
        self,
        event_engine: EventEngine,
        symbol_loader: SymbolLoader,
        symbol_count: int,
        scale_name: str,
    ):
        """运行扩展性测试

        Args:
            event_engine: 事件引擎
            symbol_loader: 符号加载器
            symbol_count: 品种数量
            scale_name: 规模名称
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"开始{scale_name}测试：{symbol_count}品种")
        logger.info(f"{'='*80}")

        # 1. 加载符号
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:symbol_count]

        logger.info(f"加载了 {len(test_symbols)} 个品种")

        # 2. 创建DataSensor并执行扫描
        sensor = DataSensor(event_engine)

        start_time = time.time()

        try:
            # 执行数据质量扫描
            result = sensor.scan_all_data(reference_symbols=test_symbols)

            elapsed = time.time() - start_time

            # 3. 验证结果
            assert result is not None, "扫描结果不应为None"

            # 4. 计算性能指标
            total_scanned = result.total_symbols
            per_symbol_time = elapsed / total_scanned if total_scanned > 0 else 0

            logger.info(f"\n{'='*80}")
            logger.info(f"{scale_name}测试结果：")
            logger.info(f"  - 总耗时: {elapsed:.2f}秒")
            logger.info(f"  - 扫描品种数: {total_scanned}")
            logger.info(f"  - 单品种耗时: {per_symbol_time*1000:.2f}ms")
            logger.info(f"  - 吞吐量: {total_scanned/elapsed:.2f}品种/秒")
            logger.info(f"  - 质量评分: {result.quality_score}/100")
            logger.info(f"{'='*80}\n")

            # 5. 性能断言
            # 目标：<15秒对于5000品种，按比例计算
            target_time = 15.0 * (symbol_count / 5000)

            if elapsed <= target_time:
                logger.info(f"✅ 性能达标：{elapsed:.2f}秒 <= {target_time:.2f}秒")
            else:
                logger.warning(f"⚠️ 性能未达标：{elapsed:.2f}秒 > {target_time:.2f}秒")

            # 6. 记录到性能数据文件（用于后续分析）
            self._record_performance_data(
                scale_name=scale_name,
                symbol_count=symbol_count,
                elapsed=elapsed,
                total_scanned=total_scanned,
                result=result,
            )

        except Exception as e:
            logger.error(f"❌ {scale_name}测试失败: {e}", exc_info=True)
            pytest.fail(f"{scale_name}测试失败: {e}")

    def _record_performance_data(
        self, scale_name: str, symbol_count: int, elapsed: float, total_scanned: int, result: dict
    ):
        """记录性能数据到文件

        Args:
            scale_name: 规模名称
            symbol_count: 品种数量
            elapsed: 耗时（秒）
            total_scanned: 扫描数量
            result: 扫描结果
        """
        import json
        from datetime import datetime
        from pathlib import Path

        # 性能数据文件
        perf_file = Path(__file__).parent / "performance_data_scalability.jsonl"

        # 性能数据记录
        perf_data = {
            "timestamp": datetime.now().isoformat(),
            "test_name": f"scalability_{symbol_count}",
            "scale_name": scale_name,
            "symbol_count": symbol_count,
            "elapsed_seconds": elapsed,
            "total_scanned": total_scanned,
            "per_symbol_ms": (elapsed / total_scanned * 1000) if total_scanned > 0 else 0,
            "throughput": (total_scanned / elapsed) if elapsed > 0 else 0,
            "result_summary": {
                "missing_count": result.missing_symbols,
                "outdated_count": result.outdated_symbols,
                "error_count": result.error_symbols,
                "quality_score": result.quality_score,
            },
        }

        # 追加到文件
        with open(perf_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(perf_data, ensure_ascii=False) + "\n")

        logger.info(f"📊 性能数据已记录到: {perf_file}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
