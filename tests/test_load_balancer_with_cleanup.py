# -*- coding: utf-8 -*-
"""
LoadBalancer集成测试（启动时先清理监控进程）

在测试开始前：
1. 清理可能存在的监控进程
2. 确保干净的测试环境
3. 然后运行LoadBalancer测试
"""

import time
import psutil
import logging
from unittest.mock import patch
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


# 模拟监控数据
MOCK_METRICS = {
    "system": {
        "cpu_percent": 30.0,
        "memory_percent": 40.0,
        "cpu_detailed": {
            "context_switches_per_sec": 5000,
        },
        "memory_subsystem": {
            "swap_in_kbps": 0,
            "swap_out_kbps": 0,
        },
        "storage_subsystem": {
            "disks": {
                "C:": {
                    "average_io_latency_ms": 5.0,
                }
            }
        },
        "network_subsystem": {
            "packet_loss_rate_in": 0.001,
        },
    }
}


def cleanup_monitoring_processes():
    """清理监控进程"""
    logger.info("\n" + "=" * 60)
    logger.info("🧹 开始清理监控进程...")
    logger.info("=" * 60)

    killed_count = 0

    try:
        # 查找并终止监控相关进程
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                proc_info = proc.as_dict(attrs=["pid", "cmdline"])
                cmdline = proc_info.get("cmdline")
                if cmdline:
                    cmdline_str = " ".join(cmdline).lower()

                    # 查找监控进程关键字
                    if any(
                        keyword in cmdline_str
                        for keyword in [
                            "monitor_core.py",
                            "monitoring_process",
                            "system_monitor",
                            "monitoringprocessv2",
                        ]
                    ):
                        logger.info(f"🔍 发现监控进程: PID={proc_info['pid']}, CMD={cmdline}")
                        proc.terminate()
                        proc.wait(timeout=3)
                        killed_count += 1
                        logger.info(f"✅ 已终止进程 PID={proc_info['pid']}")

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass

        # 等待进程完全退出
        time.sleep(1)

        # 清理可能占用的端口（ZMQ端口5555, 5556, 5557）
        logger.info("\n🔍 检查ZMQ端口占用情况...")
        for port in [5555, 5556, 5557]:
            for conn in psutil.net_connections():
                if conn.laddr.port == port:
                    try:
                        proc = psutil.Process(conn.pid)
                        logger.info(f"🔍 端口{port}被占用: PID={conn.pid}, 进程={proc.name()}")
                        proc.terminate()
                        proc.wait(timeout=3)
                        killed_count += 1
                        logger.info(f"✅ 已终止占用端口{port}的进程 PID={conn.pid}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                        pass

        if killed_count > 0:
            logger.info(f"\n✅ 清理完成，共终止了 {killed_count} 个进程")
        else:
            logger.info("\n✅ 未发现需要清理的监控进程")

    except Exception as e:
        logger.error(f"❌ 清理过程出错: {e}")

    logger.info("=" * 60 + "\n")


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
        return config


def test_loadbalancer_basic():
    """测试LoadBalancer基本功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试1: LoadBalancer基本功能")
    logger.info("=" * 60)

    # 清理单例
    LoadBalancer._instance = None

    with patch(
        "backend.infrastructure.data_module_vnpy.load_balancer.monitors.SystemMetricsMonitor.get_metrics"
    ) as mock_get_metrics:
        mock_get_metrics.return_value = MOCK_METRICS

        # 初始化LoadBalancer
        load_balancer = LoadBalancer()
        logger.info("✅ LoadBalancer初始化成功")

        # 测试网络任务
        task = TestNetworkTask("test_network", connections=200)
        config = load_balancer.get_optimal_config(task)

        logger.info(f"网络任务配置: {config}")
        assert "processes" in config
        assert "pressure_score" in config
        logger.info("✅ 网络任务配置获取成功")

        # 测试本地任务
        task2 = TestLocalTask("test_local", workers=8)
        config2 = load_balancer.get_optimal_config(task2)

        logger.info(f"本地任务配置: {config2}")
        assert "max_workers" in config2
        logger.info("✅ 本地任务配置获取成功")


def test_cache_and_realtime():
    """测试缓存和强制实时"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 缓存机制和强制实时")
    logger.info("=" * 60)

    LoadBalancer._instance = None

    with patch(
        "backend.infrastructure.data_module_vnpy.load_balancer.monitors.SystemMetricsMonitor.get_metrics"
    ) as mock_get_metrics:
        mock_get_metrics.return_value = MOCK_METRICS

        load_balancer = LoadBalancer()
        task = TestNetworkTask("test_cache", connections=100)

        # 第一次请求
        load_balancer.get_optimal_config(task)
        call_count_1 = mock_get_metrics.call_count
        logger.info(f"第一次请求，调用次数: {call_count_1}")

        # 第二次请求（应该使用缓存）
        load_balancer.get_optimal_config(task)
        call_count_2 = mock_get_metrics.call_count
        logger.info(f"第二次请求，调用次数: {call_count_2}")

        # 强制实时请求
        load_balancer.get_optimal_config(task, force_realtime=True)
        call_count_3 = mock_get_metrics.call_count
        logger.info(f"强制实时请求，调用次数: {call_count_3}")

        assert call_count_2 == call_count_1, "第二次应该使用缓存"
        assert call_count_3 > call_count_2, "强制实时应该重新查询"
        logger.info("✅ 缓存和强制实时机制正常")


def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "#" * 60)
    logger.info("# LoadBalancer集成测试（带监控进程清理）")
    logger.info("#" * 60)

    # 第一步：清理监控进程
    cleanup_monitoring_processes()

    # 第二步：运行测试
    try:
        test_loadbalancer_basic()
        test_cache_and_realtime()

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
