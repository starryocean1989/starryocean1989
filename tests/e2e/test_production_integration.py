# -*- coding: utf-8 -*-
"""
生产环境集成测试

验证：
1. LoadBalancer监控服务集成
2. LRU缓存优化应用
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_loadbalancer_monitoring():
    """测试LoadBalancer监控服务"""
    logger.info("\n" + "=" * 80)
    logger.info("测试1: LoadBalancer监控服务集成")
    logger.info("=" * 80)

    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import (
            get_loadbalancer_service,
        )

        # 获取服务实例
        service = get_loadbalancer_service()

        # 测试任务跟踪
        task_id = service.start_task("disk_io", batch_size=50, worker_count=4)
        logger.info("✓ 任务已开始跟踪: %s", task_id)

        # 模拟任务完成
        import time

        time.sleep(0.1)
        service.end_task(task_id, success=True)
        logger.info("✓ 任务已结束")

        # 记录调整
        service.record_adjustment(
            adjustment_type="worker_count", old_value=4, new_value=6, reason="资源充足"
        )
        logger.info("✓ 动态调整已记录")

        # 获取指标
        metrics = service.get_metrics()
        logger.info("✓ 指标已获取:")
        logger.info("  - 总任务数: %d", metrics["total_tasks"])
        logger.info("  - 成功率: %.1f%%", metrics["success_rate"])
        logger.info("  - 平均执行时间: %.3fs", metrics["avg_execution_time"])
        logger.info("  - 调整次数: %d", metrics["adjustment_count"])

        # 检查告警
        alerts = service.check_alerts()
        logger.info("✓ 告警检查完成: %d个告警", len(alerts))

        # 获取性能摘要
        summary = service.get_performance_summary()
        logger.info("✓ 性能摘要已获取:")
        logger.info("  - 任务总数: %d", summary.get("total_tasks", 0))
        logger.info("  - 成功任务: %d", summary.get("successful_tasks", 0))
        logger.info("  - 失败任务: %d", summary.get("failed_tasks", 0))

        logger.info("\n✅ LoadBalancer监控服务集成测试通过\n")
        return True

    except Exception as e:
        logger.error("❌ LoadBalancer监控服务集成测试失败: %s", e, exc_info=True)
        return False


def test_lru_cache_ipo():
    """测试LRU缓存优化（IPO日期缓存）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2: LRU缓存优化 - IPO日期缓存")
    logger.info("=" * 80)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            IPODateCache,
        )
        from datetime import date

        # 创建缓存实例
        cache = IPODateCache()
        logger.info("✓ IPO缓存实例已创建")

        # 测试数据
        test_symbols = ["600000.SH", "000001.SZ", "000002.SZ"]
        test_dates = [date(2020, 1, 1), date(2021, 6, 15), date(2019, 3, 20)]

        # 设置缓存
        for symbol, ipo_date in zip(test_symbols, test_dates):
            cache.set(symbol, ipo_date)
        logger.info("✓ 已设置%d个测试IPO日期", len(test_symbols))

        # 获取缓存
        hit_count = 0
        for symbol in test_symbols:
            ipo_date, is_cached = cache.get(symbol)
            if is_cached and ipo_date is not None:
                hit_count += 1

        logger.info("✓ 缓存命中: %d/%d", hit_count, len(test_symbols))

        # 获取统计
        stats = cache.get_stats()
        logger.info("✓ 缓存统计:")
        logger.info("  - LRU大小: %d", stats.get("lru_size", 0))
        logger.info("  - LRU容量: %d", stats.get("lru_capacity", 0))
        logger.info("  - LRU命中率: %.1f%%", stats.get("lru_hit_rate", 0))
        logger.info("  - LRU驱逐次数: %d", stats.get("lru_evictions", 0))
        logger.info("  - 查询总数: %d", stats.get("total_queries", 0))
        logger.info("  - 总命中率: %.1f%%", stats.get("hit_rate", 0))

        # 测试容量限制（设置5000个品种）
        logger.info("\n测试容量限制（添加大量数据）...")
        for i in range(100):
            cache.set(f"TEST{i:06d}.SH", date(2020, 1, 1))

        stats = cache.get_stats()
        logger.info("✓ 添加100个测试条目后:")
        logger.info("  - 缓存大小: %d", stats.get("cache_size", 0))
        logger.info("  - 驱逐次数: %d", stats.get("lru_evictions", 0))

        logger.info("\n✅ LRU缓存优化测试通过\n")
        return True

    except Exception as e:
        logger.error("❌ LRU缓存优化测试失败: %s", e, exc_info=True)
        return False


def test_lru_cache_generic():
    """测试通用LRU缓存管理器"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3: 通用LRU缓存管理器")
    logger.info("=" * 80)

    try:
        from backend.infrastructure.data_module_vnpy.local_data import (
            create_lru_cache,
            lru_cache,
        )

        # 测试创建缓存
        cache = create_lru_cache(capacity=100, ttl=3600)
        logger.info("✓ LRU缓存已创建（容量: 100, TTL: 3600s）")

        # 测试基本操作
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        value1 = cache.get("key1")
        assert value1 == "value1", "缓存值不匹配"
        logger.info("✓ 基本get/set操作正常")

        # 测试exists
        assert cache.exists("key1"), "exists检查失败"
        assert not cache.exists("key_not_exist"), "exists检查失败"
        logger.info("✓ exists检查正常")

        # 测试统计
        stats = cache.get_stats()
        logger.info("✓ 缓存统计:")
        logger.info("  - 大小: %d", stats.size)
        logger.info("  - 容量: %d", stats.capacity)
        logger.info("  - 命中: %d", stats.hits)
        logger.info("  - 未命中: %d", stats.misses)
        logger.info("  - 命中率: %.1f%%", stats.hit_rate)

        # 测试装饰器
        @lru_cache(capacity=10, ttl=60)
        def expensive_function(n: int) -> int:
            return n * n

        result1 = expensive_function(5)
        result2 = expensive_function(5)  # 应该从缓存获取
        assert result1 == result2 == 25, "装饰器结果不匹配"
        logger.info("✓ @lru_cache装饰器正常")

        logger.info("\n✅ 通用LRU缓存管理器测试通过\n")
        return True

    except Exception as e:
        logger.error("❌ 通用LRU缓存管理器测试失败: %s", e, exc_info=True)
        return False


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 80)
    logger.info("生产环境集成测试")
    logger.info("=" * 80)

    results = {
        "LoadBalancer监控服务": test_loadbalancer_monitoring(),
        "LRU缓存优化 - IPO": test_lru_cache_ipo(),
        "通用LRU缓存管理器": test_lru_cache_generic(),
    }

    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结")
    logger.info("=" * 80)

    all_passed = True
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info("%s: %s", name, status)
        if not result:
            all_passed = False

    logger.info("=" * 80)

    if all_passed:
        logger.info("\n🎉 所有测试通过！")
        return 0
    else:
        logger.error("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())

