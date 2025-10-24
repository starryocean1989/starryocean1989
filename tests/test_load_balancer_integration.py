# -*- coding: utf-8 -*-
"""
LoadBalancer集成测试

验证LoadBalancer在不同场景下的功能和性能。
"""

import time
import logging
from backend.infrastructure.data_module_vnpy.load_balancer import (
    LoadBalancer,
    NetworkTask,
    LocalProcessingTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TestNetworkTask(NetworkTask):
    """测试用网络任务"""

    def __init__(self, name: str, connections: int = 100):
        super().__init__(name)
        self.metrics.estimated_connections = connections

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name=self.name,
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=["network_speed", "packet_loss_rate"],
            estimated_duration=60,
            estimated_memory_mb=50,
            estimated_connections=100,
        )

    def execute(self, config):
        logger.info(f"执行网络任务: {self.name}")
        logger.info(f"配置: {config}")
        return config


class TestLocalTask(LocalProcessingTask):
    """测试用本地处理任务"""

    def __init__(self, name: str, workers: int = 4):
        super().__init__(name)
        self.metrics.estimated_workers = workers

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name=self.name,
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.DISK_IO_INTENSIVE,
            critical_metrics=["disk_io_speed", "cpu_percent"],
            estimated_duration=60,
            estimated_memory_mb=100,
            estimated_workers=4,
        )

    def execute(self, config):
        logger.info(f"执行本地任务: {self.name}")
        logger.info(f"配置: {config}")
        return config


def test_loadbalancer_singleton():
    """测试LoadBalancer单例模式"""
    logger.info("\n" + "=" * 60)
    logger.info("测试1: LoadBalancer单例模式")
    logger.info("=" * 60)

    lb1 = LoadBalancer()
    lb2 = LoadBalancer()

    assert lb1 is lb2, "LoadBalancer应该是单例"
    logger.info("✅ 单例模式测试通过")


def test_network_task_config():
    """测试网络任务配置"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 网络任务配置")
    logger.info("=" * 60)

    load_balancer = LoadBalancer()
    task = TestNetworkTask("test_network", connections=200)

    start_time = time.time()
    config = load_balancer.get_optimal_config(task)
    elapsed_ms = (time.time() - start_time) * 1000

    logger.info(f"配置评估耗时: {elapsed_ms:.2f}ms")
    logger.info(f"获取的配置: {config}")

    # 验证配置包含必要字段
    assert "processes" in config, "配置应包含processes"
    assert "coroutines_per_process" in config, "配置应包含coroutines_per_process"
    assert "pressure_score" in config, "配置应包含pressure_score"
    assert "scale_factor" in config, "配置应包含scale_factor"
    assert "bottleneck" in config, "配置应包含bottleneck"

    assert elapsed_ms < 100, f"配置评估应该<100ms，实际{elapsed_ms:.2f}ms"

    logger.info("✅ 网络任务配置测试通过")


def test_local_task_config():
    """测试本地处理任务配置"""
    logger.info("\n" + "=" * 60)
    logger.info("测试3: 本地处理任务配置")
    logger.info("=" * 60)

    load_balancer = LoadBalancer()
    task = TestLocalTask("test_local", workers=8)

    start_time = time.time()
    config = load_balancer.get_optimal_config(task)
    elapsed_ms = (time.time() - start_time) * 1000

    logger.info(f"配置评估耗时: {elapsed_ms:.2f}ms")
    logger.info(f"获取的配置: {config}")

    # 验证配置包含必要字段
    assert "max_workers" in config, "配置应包含max_workers"
    assert "batch_size" in config, "配置应包含batch_size"
    assert "pressure_score" in config, "配置应包含pressure_score"
    assert "scale_factor" in config, "配置应包含scale_factor"

    assert elapsed_ms < 100, f"配置评估应该<100ms，实际{elapsed_ms:.2f}ms"

    logger.info("✅ 本地任务配置测试通过")


def test_cache_mechanism():
    """测试缓存机制"""
    logger.info("\n" + "=" * 60)
    logger.info("测试4: 缓存机制")
    logger.info("=" * 60)

    load_balancer = LoadBalancer()
    task = TestNetworkTask("test_cache", connections=100)

    # 第一次请求（无缓存）
    start_time1 = time.time()
    config1 = load_balancer.get_optimal_config(task)
    elapsed_ms1 = (time.time() - start_time1) * 1000

    # 第二次请求（应该使用缓存）
    start_time2 = time.time()
    config2 = load_balancer.get_optimal_config(task)
    elapsed_ms2 = (time.time() - start_time2) * 1000

    logger.info(f"第一次评估耗时: {elapsed_ms1:.2f}ms")
    logger.info(f"第二次评估耗时: {elapsed_ms2:.2f}ms（缓存）")

    # 第二次应该更快（使用缓存）
    assert elapsed_ms2 < elapsed_ms1, "缓存应该加快配置获取速度"
    assert elapsed_ms2 < 1.0, "缓存命中应该<1ms"

    logger.info("✅ 缓存机制测试通过")


def test_multiple_tasks():
    """测试多任务并发"""
    logger.info("\n" + "=" * 60)
    logger.info("测试5: 多任务并发")
    logger.info("=" * 60)

    load_balancer = LoadBalancer()

    tasks = [
        TestNetworkTask("network1", connections=100),
        TestNetworkTask("network2", connections=200),
        TestLocalTask("local1", workers=4),
        TestLocalTask("local2", workers=8),
    ]

    for task in tasks:
        start_time = time.time()
        config = load_balancer.get_optimal_config(task)
        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(f"任务 {task.name}: {elapsed_ms:.2f}ms, 配置: {config}")

    logger.info("✅ 多任务并发测试通过")


def test_force_realtime():
    """测试强制实时评估"""
    logger.info("\n" + "=" * 60)
    logger.info("测试6: 强制实时评估")
    logger.info("=" * 60)

    load_balancer = LoadBalancer()
    task = TestNetworkTask("test_realtime", connections=150)

    # 普通请求（可能使用缓存）
    start_time1 = time.time()
    config1 = load_balancer.get_optimal_config(task, force_realtime=False)
    elapsed_ms1 = (time.time() - start_time1) * 1000

    # 强制实时请求（不使用缓存）
    start_time2 = time.time()
    config2 = load_balancer.get_optimal_config(task, force_realtime=True)
    elapsed_ms2 = (time.time() - start_time2) * 1000

    logger.info(f"普通请求耗时: {elapsed_ms1:.2f}ms")
    logger.info(f"强制实时请求耗时: {elapsed_ms2:.2f}ms")

    logger.info("✅ 强制实时评估测试通过")


def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "#" * 60)
    logger.info("# LoadBalancer集成测试开始")
    logger.info("#" * 60)

    try:
        test_loadbalancer_singleton()
        test_network_task_config()
        test_local_task_config()
        test_cache_mechanism()
        test_multiple_tasks()
        test_force_realtime()

        logger.info("\n" + "#" * 60)
        logger.info("# ✅ 所有测试通过！")
        logger.info("#" * 60)
        return True

    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
