# -*- coding: utf-8 -*-
"""
路由引擎性能测试

测试路由耗时、缓存命中率、高频场景压力测试
"""

import logging
import time
import unittest

from backend.infrastructure.system_vnpy.routing_engine import RoutingRuleEngine
from backend.infrastructure.system_vnpy.unified_logging import UnifiedLogRecord, LogType


class TestRoutingPerformance(unittest.TestCase):
    """路由引擎性能测试"""

    def setUp(self):
        """测试前准备"""
        self.engine = RoutingRuleEngine()

    def test_routing_latency(self):
        """测试路由耗时（性能目标: <0.1ms）"""
        record = UnifiedLogRecord(
            type=LogType.SYSTEM, level=logging.INFO, module="test", message="性能测试"
        )

        # 预热（建立缓存）
        for _ in range(10):
            self.engine.route(record)

        # 测试10000次路由
        start_time = time.perf_counter()
        for _ in range(10000):
            self.engine.route(record)
        elapsed = time.perf_counter() - start_time

        avg_time = elapsed / 10000 * 1000  # 转为毫秒
        print(f"\n平均路由耗时: {avg_time:.4f}ms")

        # 性能目标: <0.1ms（缓存后<0.01ms）
        self.assertLess(avg_time, 0.1, f"路由耗时 {avg_time:.4f}ms 超过性能目标 0.1ms")

    def test_cache_hit_rate(self):
        """测试缓存命中率（性能目标: >95%）"""
        record = UnifiedLogRecord(
            type=LogType.SYSTEM, level=logging.INFO, module="test", message="缓存测试"
        )

        # 路由1000次（应全部命中缓存）
        for _ in range(1000):
            self.engine.route(record)

        stats = self.engine.get_statistics()
        hit_rate = stats["cache_stats"]["hit_rate"]
        print(f"\n缓存命中率: {hit_rate:.2f}%")

        # 性能目标: >95%
        self.assertGreater(hit_rate, 95, f"缓存命中率 {hit_rate:.2f}% 低于性能目标 95%")

    def test_high_frequency_scenario(self):
        """测试高频场景压力（模拟下载15000任务）"""
        # 模拟批量下载场景
        record = UnifiedLogRecord(
            type=LogType.PROGRESS,
            level=logging.INFO,
            module="DataCenterService",
            message="下载进度",
            details={"scenario": "bulk_download"},
        )

        start_time = time.perf_counter()

        # 模拟15000次日志
        for i in range(15000):
            self.engine.route(record)

        elapsed = time.perf_counter() - start_time
        throughput = 15000 / elapsed

        print(f"\n高频场景吞吐量: {throughput:.0f} 条/秒")
        print(f"总耗时: {elapsed:.2f} 秒")

        # 性能目标: >10000条/秒
        self.assertGreater(
            throughput, 10000, f"吞吐量 {throughput:.0f} 条/秒低于性能目标 10000 条/秒"
        )

    def test_cache_memory_usage(self):
        """测试缓存内存占用"""
        # 创建多种不同的日志记录
        log_types = [LogType.SYSTEM, LogType.PROGRESS, LogType.NOTIFICATION]
        levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
        modules = ["Module1", "Module2", "Module3"]
        stages = ["startup", "downloading", "trading"]

        # 生成组合，填充缓存
        for log_type in log_types:
            for level in levels:
                for module in modules:
                    for stage in stages:
                        self.engine.set_stage(stage)
                        record = UnifiedLogRecord(
                            type=log_type, level=level, module=module, message="测试"
                        )
                        self.engine.route(record)

        stats = self.engine.get_statistics()
        cache_size = stats["cache_stats"]["size"]
        print(f"\n缓存大小: {cache_size} 个条目")

        # 性能目标: <500个条目（<10KB）
        self.assertLess(cache_size, 500, f"缓存大小 {cache_size} 超过性能目标 500")

    def test_stage_switching_overhead(self):
        """测试阶段切换开销"""
        record = UnifiedLogRecord(
            type=LogType.SYSTEM, level=logging.INFO, module="test", message="阶段切换测试"
        )

        # 测试频繁切换阶段
        start_time = time.perf_counter()

        for _ in range(1000):
            self.engine.set_stage("startup")
            self.engine.route(record)
            self.engine.set_stage("downloading")
            self.engine.route(record)

        elapsed = time.perf_counter() - start_time
        avg_time = elapsed / 2000 * 1000  # 2000次操作（1000次切换+1000次路由）

        print(f"\n阶段切换+路由平均耗时: {avg_time:.4f}ms")

        # 性能目标: <1ms
        self.assertLess(avg_time, 1.0, f"阶段切换+路由耗时 {avg_time:.4f}ms 超过性能目标 1ms")


class TestCachePerformance(unittest.TestCase):
    """缓存性能测试"""

    def test_cache_lru_eviction(self):
        """测试LRU淘汰性能"""
        from backend.infrastructure.system_vnpy.rule_cache import RuleCache

        # 创建小缓存（max_size=10）
        cache = RuleCache(ttl_seconds=60, max_size=10)

        # 填充缓存
        for i in range(10):
            key = (f"TYPE{i}", "INFO", "test", None, "startup")
            cache.set(key, ["file", "console"])

        # 再添加1个，应触发LRU淘汰
        new_key = ("TYPE10", "INFO", "test", None, "startup")
        cache.set(new_key, ["file"])

        stats = cache.get_statistics()
        print(f"\nLRU淘汰次数: {stats['evictions']}")

        # 应该有1次淘汰
        self.assertEqual(stats["evictions"], 1)


if __name__ == "__main__":
    # 运行性能测试
    unittest.main(verbosity=2)
