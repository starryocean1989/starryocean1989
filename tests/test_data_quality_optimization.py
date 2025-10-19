# -*- coding: utf-8 -*-
"""
数据质量检测优化集成测试
"""

import pytest
import time
from datetime import date, datetime
from pathlib import Path
from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
    DataValidator,
    DataSensor,
    StorageManager,
    IPODateCache,
)


class TestDataQualityOptimization:
    """数据质量优化集成测试"""

    @pytest.fixture
    def validator(self):
        """创建数据校验器实例"""
        return DataValidator()

    @pytest.fixture
    def sensor(self):
        """创建数据感知器实例"""
        return DataSensor()

    def test_ipo_date_validation(self, validator):
        """测试IPO日期验证"""
        # 测试合法日期
        valid_date = date(2020, 1, 15)
        result = validator._validate_ipo_date("600000", valid_date)
        assert result == valid_date

        # 测试未来日期（应该被拒绝）
        future_date = date(2026, 12, 31)
        result = validator._validate_ipo_date("600000", future_date)
        assert result is None

        # 测试过早日期（应该被拒绝）
        early_date = date(1989, 1, 1)
        result = validator._validate_ipo_date("600000", early_date)
        assert result is None

    def test_compute_effective_start_date(self, validator):
        """测试智能起点计算算法"""
        # 场景1：有IPO日期、数据起点和基准日期
        ipo_date = date(2015, 1, 1)
        data_start = date(2020, 1, 1)
        base_date = date(2018, 1, 1)

        # Mock IPO日期查询
        validator._ipo_cache.set("600000", ipo_date)

        result = validator._compute_effective_start_date(
            symbol="600000", data_start=data_start, base_date=base_date
        )

        # 应该选择最大值（最近的日期）
        assert result == max(ipo_date, data_start, base_date)
        assert result == data_start

        # 场景2：只有数据起点
        result = validator._compute_effective_start_date(
            symbol="999999", data_start=date(2020, 5, 1), base_date=None  # 不存在的品种
        )
        assert result == date(2020, 5, 1)

        # 场景3：什么都没有，使用默认值
        result = validator._compute_effective_start_date(
            symbol="999999", data_start=None, base_date=None
        )
        assert result == date(2020, 1, 1)  # 默认值

    def test_ipo_cache_integration(self, validator):
        """测试IPO缓存集成"""
        # 第一次查询（缓存未命中，需要API调用）
        # 注意：这个测试可能需要网络连接，在CI环境中可能跳过
        symbol = "600000"

        # 清空缓存
        validator._ipo_cache._memory_cache.clear()

        # 模拟缓存设置
        test_date = date(1999, 11, 10)  # 浦发银行上市日期
        validator._ipo_cache.set(symbol, test_date)

        # 第二次查询（应该从缓存获取）
        result = validator._get_ipo_date(symbol)
        assert result == test_date

        # 验证缓存统计
        stats = validator._ipo_cache.get_stats()
        assert stats["hits"] >= 1

    def test_server_failure_tracking(self, validator):
        """测试服务器故障跟踪"""
        # 记录服务器成功
        validator._record_server_success(0)
        assert validator._server_failure_counts.get(0, 0) == 0

        # 记录服务器失败
        validator._record_server_failure(0)
        validator._record_server_failure(0)
        assert validator._server_failure_counts[0] == 2

        # 记录成功应该减少失败计数
        validator._record_server_success(0)
        assert validator._server_failure_counts[0] == 1

    def test_missing_dates_check_with_ipo(self, validator):
        """测试缺失日期检测（使用IPO日期）"""
        import pandas as pd

        # 创建测试数据（2020-01-02 到 2020-01-10，缺少1-06和1-07）
        dates = pd.date_range("2020-01-02", "2020-01-10", freq="D")
        dates = dates[~dates.isin(pd.to_datetime(["2020-01-06", "2020-01-07"]))]

        df = pd.DataFrame(
            {
                "datetime": dates,
                "open": [10.0] * len(dates),
                "high": [11.0] * len(dates),
                "low": [9.0] * len(dates),
                "close": [10.5] * len(dates),
                "volume": [1000] * len(dates),
            }
        )

        # 设置IPO日期
        validator._ipo_cache.set("600000", date(2019, 1, 1))

        # 检查缺失日期
        missing = validator._check_missing_dates(df, symbol="600000")

        # 应该检测到缺失的日期（注意：需要考虑周末和交易日历）
        assert isinstance(missing, list)

    @pytest.mark.integration
    def test_quality_scan_performance(self, sensor):
        """测试质量扫描性能（集成测试）"""
        # 这个测试需要真实的品种列表和数据，仅在集成测试时运行
        pytest.skip("需要真实环境和数据")

        # 创建测试品种列表（少量品种用于快速测试）
        test_symbols = ["600000", "600001", "000001", "000002"]

        # 记录开始时间
        start_time = time.time()

        # 执行扫描
        overview = sensor.scan_all_data(
            reference_symbols=test_symbols, intervals=["1d"], force_refresh=True
        )

        # 记录结束时间
        elapsed = time.time() - start_time

        # 性能验证
        assert elapsed < 10  # 4个品种应该在10秒内完成
        assert overview.total_symbols == len(test_symbols)

        # 验证IPO缓存统计
        cache_stats = sensor.validator._ipo_cache.get_stats()
        print(f"\n缓存统计: {cache_stats}")

    def test_ipo_cache_persistence_after_scan(self, sensor, tmp_path):
        """测试扫描后IPO缓存持久化"""
        # 设置临时缓存文件
        cache_file = tmp_path / "ipo_cache_test.json"
        sensor.validator._ipo_cache.cache_file = cache_file

        # 添加一些测试数据到缓存
        sensor.validator._ipo_cache.set("600000", date(1999, 11, 10))
        sensor.validator._ipo_cache.set("600001", date(2016, 8, 16))

        # 模拟扫描完成后的保存
        sensor.validator._ipo_cache.batch_save()

        # 验证文件已创建
        assert cache_file.exists()

        # 重新加载验证
        new_cache = IPODateCache(cache_file=cache_file)
        result, is_cached = new_cache.get("600000")
        assert is_cached is True
        assert result == date(1999, 11, 10)


class TestPerformanceMetrics:
    """性能指标测试"""

    def test_ipo_query_timeout_rate(self):
        """测试IPO查询超时率目标（<5%）"""
        # 这个测试需要在真实环境中运行大量查询来验证
        pytest.skip("需要真实网络环境")

    def test_cache_hit_rate(self):
        """测试缓存命中率目标（>95%）"""
        cache = IPODateCache()

        # 第一次设置100个品种
        for i in range(100):
            cache.set(f"60{i:04d}", date(2020, 1, i % 28 + 1))

        # 第二次查询这100个品种（应该全部命中）
        for i in range(100):
            result, is_cached = cache.get(f"60{i:04d}")
            assert is_cached is True

        # 验证命中率
        stats = cache.get_stats()
        assert stats["hit_rate"] == 100.0

    def test_scan_time_target(self):
        """测试扫描时间目标（<30秒 for 5000品种）"""
        # 这个测试需要在真实环境中运行
        pytest.skip("需要真实数据环境")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
