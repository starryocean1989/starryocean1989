# -*- coding: utf-8 -*-
"""
路由引擎单元测试

测试四层路由逻辑、缓存、阶段切换等功能
"""

import logging
import unittest
from pathlib import Path

from backend.infrastructure.system_vnpy.routing_engine import RoutingRuleEngine
from backend.infrastructure.system_vnpy.unified_logging import UnifiedLogRecord, LogType


class TestRoutingEngine(unittest.TestCase):
    """路由引擎测试"""

    def setUp(self):
        """测试前准备"""
        # 使用测试配置目录
        self.engine = RoutingRuleEngine("backend/infrastructure/system_vnpy/config")

    def test_global_rules(self):
        """测试全局规则"""
        # 设置一个不存在的阶段，确保使用全局规则
        self.engine.set_stage("nonexistent_stage_for_test")

        record = UnifiedLogRecord(
            type=LogType.SYSTEM, level=logging.INFO, module="test_module", message="测试消息"
        )
        targets = self.engine.route(record)

        # SYSTEM.INFO应输出到file和console（全局规则）
        self.assertIn("file", targets)
        self.assertIn("console", targets)

        # 恢复默认阶段
        self.engine.set_stage("startup")

    def test_stage_switching(self):
        """测试阶段切换"""
        # 启动阶段：DEBUG也输出到控制台
        self.engine.set_stage("startup")
        record = UnifiedLogRecord(
            type=LogType.SYSTEM, level=logging.DEBUG, module="test", message="启动日志"
        )
        targets = self.engine.route(record)
        self.assertIn("console", targets)

        # 正常阶段：DEBUG不输出到控制台
        self.engine.set_stage("sensing")
        self.engine.cache.clear()  # 清空缓存
        targets = self.engine.route(record)
        self.assertNotIn("console", targets)

    def test_module_rules(self):
        """测试模块规则"""
        # 交易网关模块：INFO也入库
        record = UnifiedLogRecord(
            type=LogType.SYSTEM,
            level=logging.INFO,
            module="TradingGatewayService",
            message="订单提交",
        )
        targets = self.engine.route(record)
        self.assertIn("database", targets)

    def test_scenario_rules(self):
        """测试场景规则"""
        # 批量下载场景：PROGRESS不输出到控制台
        record = UnifiedLogRecord(
            type=LogType.PROGRESS,
            level=logging.INFO,
            module="DataCenterService",
            message="下载进度",
            details={"scenario": "bulk_download"},
        )
        targets = self.engine.route(record)
        self.assertNotIn("console", targets)
        self.assertIn("event_throttled", targets)

    def test_cache_performance(self):
        """测试缓存性能"""
        record = UnifiedLogRecord(
            type=LogType.SYSTEM, level=logging.INFO, module="test", message="缓存测试"
        )

        # 第一次路由（缓存未命中）
        targets1 = self.engine.route(record)

        # 后续路由（应命中缓存）
        for _ in range(100):
            targets2 = self.engine.route(record)
            self.assertEqual(targets1, targets2)

        # 检查缓存命中率
        stats = self.engine.get_statistics()
        hit_rate = stats["cache_stats"]["hit_rate"]
        self.assertGreater(hit_rate, 95)

    def test_run_mode_switching(self):
        """测试运行模式切换"""
        # 切换到开发模式
        self.engine.set_run_mode("dev")
        self.assertEqual(self.engine.run_mode, "dev")

        # 切换到生产模式
        self.engine.set_run_mode("prod")
        self.assertEqual(self.engine.run_mode, "prod")

    def test_config_validation(self):
        """测试配置验证"""
        # 配置应该有效
        result = self.engine.validate_config()
        self.assertTrue(result)


class TestRuleCache(unittest.TestCase):
    """规则缓存测试"""

    def setUp(self):
        """测试前准备"""
        from backend.infrastructure.system_vnpy.rule_cache import RuleCache

        self.cache = RuleCache(ttl_seconds=1)

    def test_cache_basic(self):
        """测试缓存基本功能"""
        key = ("SYSTEM", "INFO", "test", None, "startup")
        targets = ["file", "console"]

        # 设置缓存
        self.cache.set(key, targets)

        # 获取缓存
        cached = self.cache.get(key)
        self.assertEqual(cached, targets)

    def test_cache_miss(self):
        """测试缓存未命中"""
        key = ("SYSTEM", "INFO", "test", None, "startup")

        # 未设置缓存，应返回None
        cached = self.cache.get(key)
        self.assertIsNone(cached)

    def test_cache_ttl(self):
        """测试缓存TTL"""
        import time

        key = ("SYSTEM", "INFO", "test", None, "startup")
        targets = ["file", "console"]

        # 设置缓存
        self.cache.set(key, targets)

        # 立即获取，应命中
        cached = self.cache.get(key)
        self.assertEqual(cached, targets)

        # 等待TTL过期（1秒）
        time.sleep(1.1)

        # 再次获取，应未命中
        cached = self.cache.get(key)
        self.assertIsNone(cached)

    def test_cache_statistics(self):
        """测试缓存统计"""
        key = ("SYSTEM", "INFO", "test", None, "startup")
        targets = ["file", "console"]

        self.cache.set(key, targets)

        # 命中2次
        self.cache.get(key)
        self.cache.get(key)

        # 未命中1次
        self.cache.get(("OTHER", "INFO", "test", None, "startup"))

        stats = self.cache.get_statistics()
        self.assertEqual(stats["hits"], 2)
        self.assertEqual(stats["misses"], 1)


class TestLoggingContext(unittest.TestCase):
    """日志上下文测试"""

    def test_stage_context(self):
        """测试阶段上下文"""
        from backend.infrastructure.system_vnpy.logging_context import get_logging_context

        ctx = get_logging_context()
        original_stage = ctx.get_current_stage()

        # 使用阶段上下文
        with ctx.stage("downloading"):
            self.assertEqual(ctx.get_current_stage(), "downloading")

        # 退出后恢复
        self.assertEqual(ctx.get_current_stage(), original_stage)

    def test_scenario_context(self):
        """测试场景上下文"""
        from backend.infrastructure.system_vnpy.logging_context import get_logging_context
        import logging

        ctx = get_logging_context()
        logger = logging.getLogger("test")

        # 使用场景上下文
        with ctx.scenario("bulk_download"):
            # 日志应包含scenario信息
            # （实际验证需要检查LogRecord的details）
            logger.info("测试场景日志")


if __name__ == "__main__":
    unittest.main()
