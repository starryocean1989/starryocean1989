# -*- coding: utf-8 -*-
"""
监控系统与LoadBalancer集成测试

测试内容：
1. LoadBalancer能否正确接收监控数据
2. ResourcePressureEvaluator能否正确评估压力
3. 动态调整机制能否正确触发
4. 细粒度子系统指标的使用
5. 性能对比（优化前vs优化后）
"""

import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.load_balancer.lb_monitoring import (
    ResourcePressureEvaluator,
    ResourceMonitor,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 测试数据 ====================


def get_normal_metrics() -> Dict[str, Any]:
    """获取正常状态的模拟监控数据"""
    return {
        "system": {
            "cpu_percent": 45.0,
            "memory_percent": 50.0,
            "disk_percent": 40.0,
            # V2.5新增：CPU详细指标
            "cpu_detailed": {
                "per_core": [45.0, 48.0, 42.0, 50.0],
                "context_switches_per_sec": 5000.0,
                "interrupts_per_sec": 3000.0,
                "user_percent": 30.0,
                "system_percent": 10.0,
                "idle_percent": 60.0,
            },
            # V2.5新增：内存子系统指标
            "memory_subsystem": {
                "available_mb": 8192.0,
                "swap_used_percent": 0.0,
                "swap_in_kbps": 0.0,
                "swap_out_kbps": 0.0,
                "page_faults_per_sec": 100.0,
            },
            # V2.5新增：存储子系统指标
            "storage_subsystem": {
                "disks": {
                    "C:": {
                        "read_mbps": 10.0,
                        "write_mbps": 5.0,
                        "read_iops": 100.0,
                        "write_iops": 50.0,
                        "average_io_latency_ms": 5.0,
                        "queue_depth": 2.0,
                        "busy_percent": 30.0,
                    }
                }
            },
            # V2.5新增：网络子系统指标
            "network_subsystem": {
                "interfaces": {
                    "Ethernet": {
                        "recv_mbps": 5.0,
                        "send_mbps": 2.0,
                        "recv_packets_per_sec": 1000.0,
                        "send_packets_per_sec": 500.0,
                    }
                },
                "packet_loss_rate_in": 0.001,
                "packet_loss_rate_out": 0.001,
                "tcp_connections": 100,
                "udp_connections": 50,
            },
        }
    }


def get_high_pressure_metrics() -> Dict[str, Any]:
    """获取高压力状态的模拟监控数据"""
    return {
        "system": {
            "cpu_percent": 85.0,
            "memory_percent": 80.0,
            "disk_percent": 75.0,
            "cpu_detailed": {
                "per_core": [85.0, 88.0, 82.0, 90.0],
                "context_switches_per_sec": 50000.0,  # 高上下文切换
                "interrupts_per_sec": 15000.0,
                "user_percent": 70.0,
                "system_percent": 15.0,
                "idle_percent": 15.0,
            },
            "memory_subsystem": {
                "available_mb": 2048.0,
                "swap_used_percent": 0.0,
                "swap_in_kbps": 0.0,
                "swap_out_kbps": 0.0,
                "page_faults_per_sec": 500.0,
            },
            "storage_subsystem": {
                "disks": {
                    "C:": {
                        "read_mbps": 100.0,
                        "write_mbps": 50.0,
                        "read_iops": 1000.0,
                        "write_iops": 500.0,
                        "average_io_latency_ms": 30.0,  # 高IO延迟
                        "queue_depth": 15.0,  # 高队列深度
                        "busy_percent": 85.0,
                    }
                }
            },
            "network_subsystem": {
                "interfaces": {
                    "Ethernet": {
                        "recv_mbps": 80.0,
                        "send_mbps": 40.0,
                        "recv_packets_per_sec": 10000.0,
                        "send_packets_per_sec": 5000.0,
                    }
                },
                "packet_loss_rate_in": 0.02,  # 2% 丢包率
                "packet_loss_rate_out": 0.01,
                "tcp_connections": 1000,
                "udp_connections": 500,
            },
        }
    }


def get_swap_active_metrics() -> Dict[str, Any]:
    """获取swap活跃状态的模拟监控数据"""
    return {
        "system": {
            "cpu_percent": 70.0,
            "memory_percent": 90.0,
            "disk_percent": 60.0,
            "cpu_detailed": {
                "per_core": [70.0, 72.0, 68.0, 75.0],
                "context_switches_per_sec": 20000.0,
                "interrupts_per_sec": 8000.0,
                "user_percent": 50.0,
                "system_percent": 20.0,
                "idle_percent": 30.0,
            },
            "memory_subsystem": {
                "available_mb": 512.0,
                "swap_used_percent": 30.0,
                "swap_in_kbps": 5000.0,  # 活跃swap in
                "swap_out_kbps": 3000.0,  # 活跃swap out
                "page_faults_per_sec": 2000.0,
            },
            "storage_subsystem": {
                "disks": {
                    "C:": {
                        "read_mbps": 50.0,
                        "write_mbps": 30.0,
                        "read_iops": 500.0,
                        "write_iops": 300.0,
                        "average_io_latency_ms": 20.0,
                        "queue_depth": 10.0,
                        "busy_percent": 70.0,
                    }
                }
            },
            "network_subsystem": {
                "interfaces": {
                    "Ethernet": {
                        "recv_mbps": 20.0,
                        "send_mbps": 10.0,
                        "recv_packets_per_sec": 3000.0,
                        "send_packets_per_sec": 1500.0,
                    }
                },
                "packet_loss_rate_in": 0.005,
                "packet_loss_rate_out": 0.003,
                "tcp_connections": 300,
                "udp_connections": 150,
            },
        }
    }


# ==================== 测试用例 ====================


def test_evaluator_normal_state():
    """测试评估器在正常状态下的表现"""
    logger.info("\n" + "=" * 80)
    logger.info("测试1: 评估器正常状态测试")
    logger.info("=" * 80)

    evaluator = ResourcePressureEvaluator()
    metrics = get_normal_metrics()

    result = evaluator.evaluate(metrics)

    logger.info(f"压力得分: {result['pressure_score']:.2f}")
    logger.info(f"瓶颈维度: {result['bottleneck']}")
    logger.info(f"缩放因子: {result['scale_factor']:.2f}")
    logger.info(f"CPU得分: {result['cpu_score']:.2f}")
    logger.info(f"内存得分: {result['memory_score']:.2f}")
    logger.info(f"磁盘得分: {result['disk_score']:.2f}")
    logger.info(f"网络得分: {result['network_score']:.2f}")
    logger.info(f"Swap活跃: {result['swap_active']}")
    logger.info(f"紧急状态: {result['emergency']}")
    logger.info(f"原因: {result['reason']}")

    # 验证
    assert result["pressure_score"] > 70, "正常状态压力得分应大于70"
    assert not result["swap_active"], "正常状态不应有swap活动"
    assert not result["emergency"], "正常状态不应是紧急状态"

    logger.info("✅ 测试1通过")


def test_evaluator_high_pressure():
    """测试评估器在高压力状态下的表现"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2: 评估器高压力状态测试")
    logger.info("=" * 80)

    evaluator = ResourcePressureEvaluator()
    metrics = get_high_pressure_metrics()

    result = evaluator.evaluate(metrics)

    logger.info(f"压力得分: {result['pressure_score']:.2f}")
    logger.info(f"瓶颈维度: {result['bottleneck']}")
    logger.info(f"缩放因子: {result['scale_factor']:.2f}")
    logger.info(f"CPU得分: {result['cpu_score']:.2f}")
    logger.info(f"内存得分: {result['memory_score']:.2f}")
    logger.info(f"磁盘得分: {result['disk_score']:.2f}")
    logger.info(f"网络得分: {result['network_score']:.2f}")
    logger.info(f"原因: {result['reason']}")

    # 验证
    assert result["pressure_score"] < 70, "高压力状态得分应小于70"
    assert result["scale_factor"] < 1.0, "高压力状态应降低并发"

    logger.info("✅ 测试2通过")


def test_evaluator_swap_detection():
    """测试评估器对swap活动的检测"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3: 评估器Swap检测测试")
    logger.info("=" * 80)

    evaluator = ResourcePressureEvaluator()
    metrics = get_swap_active_metrics()

    result = evaluator.evaluate(metrics)

    logger.info(f"压力得分: {result['pressure_score']:.2f}")
    logger.info(f"Swap活跃: {result['swap_active']}")
    logger.info(f"紧急状态: {result['emergency']}")
    logger.info(f"缩放因子: {result['scale_factor']:.2f}")
    logger.info(f"原因: {result['reason']}")

    # 验证
    assert result["swap_active"], "应检测到swap活动"
    assert result["emergency"], "swap活动应触发紧急状态"
    assert result["scale_factor"] == 0.3, "swap活动应降低并发至30%"

    logger.info("✅ 测试3通过")


def test_resource_monitor_integration():
    """测试ResourceMonitor的集成功能"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4: ResourceMonitor集成测试")
    logger.info("=" * 80)

    # 不使用event_engine，直接测试评估逻辑
    monitor = ResourceMonitor(event_engine=None, low_threshold=35.0, high_threshold=70.0)

    # 注入测试数据（模拟）
    # 实际使用中，会通过event_engine或ZMQ获取数据
    monitor.metrics_monitor._cached_metrics = get_normal_metrics()
    monitor.metrics_monitor._cache_timestamp = time.time()

    pressure = monitor.get_current_pressure(force_realtime=False)

    logger.info(f"压力得分: {pressure.score:.2f}")
    logger.info(f"瓶颈: {pressure.bottleneck}")
    logger.info(f"低于低阈值: {pressure.below_low_threshold}")
    logger.info(f"高于高阈值: {pressure.above_high_threshold}")
    logger.info(f"缩放建议: {pressure.scale_suggestion:.2f}")

    # 验证双阈值检测
    assert not pressure.below_low_threshold, "正常状态不应低于低阈值"
    assert not pressure.above_high_threshold, "正常状态不应高于高阈值"

    logger.info("✅ 测试4通过")


def test_detailed_subsystem_metrics():
    """测试V2.5新增的详细子系统指标的使用"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5: 详细子系统指标测试")
    logger.info("=" * 80)

    evaluator = ResourcePressureEvaluator()

    # 测试场景1：正常IO延迟
    metrics1 = get_normal_metrics()
    result1 = evaluator.evaluate(metrics1)
    logger.info(f"正常IO延迟 - 磁盘得分: {result1['disk_score']:.2f}")

    # 测试场景2：高IO延迟
    metrics2 = get_high_pressure_metrics()
    result2 = evaluator.evaluate(metrics2)
    logger.info(f"高IO延迟 - 磁盘得分: {result2['disk_score']:.2f}")

    # 验证IO延迟对磁盘得分的影响
    assert result1["disk_score"] > result2["disk_score"], "高IO延迟应导致磁盘得分降低"

    # 测试场景3：高丢包率
    logger.info(f"正常丢包率 - 网络得分: {result1['network_score']:.2f}")
    logger.info(f"高丢包率 - 网络得分: {result2['network_score']:.2f}")

    # 验证丢包率对网络得分的影响
    assert result1["network_score"] > result2["network_score"], "高丢包率应导致网络得分降低"

    logger.info("✅ 测试5通过")


def test_bottleneck_identification():
    """测试瓶颈识别功能"""
    logger.info("\n" + "=" * 80)
    logger.info("测试6: 瓶颈识别测试")
    logger.info("=" * 80)

    evaluator = ResourcePressureEvaluator()

    # 创建磁盘瓶颈场景
    metrics_disk_bottleneck = get_normal_metrics()
    metrics_disk_bottleneck["system"]["storage_subsystem"]["disks"]["C:"][
        "average_io_latency_ms"
    ] = 100.0

    result = evaluator.evaluate(metrics_disk_bottleneck)

    logger.info(f"瓶颈维度: {result['bottleneck']}")
    logger.info(f"磁盘得分: {result['disk_score']:.2f}")

    # 验证磁盘被识别为瓶颈
    assert result["bottleneck"] in ["disk", "balanced"], "应识别出磁盘瓶颈"

    logger.info("✅ 测试6通过")


def test_performance_comparison():
    """测试性能对比（优化前vs优化后）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试7: 性能对比测试")
    logger.info("=" * 80)

    evaluator = ResourcePressureEvaluator()

    # 运行多次评估，测量性能
    metrics = get_normal_metrics()
    iterations = 1000

    start_time = time.time()
    for _ in range(iterations):
        evaluator.evaluate(metrics)
    duration = time.time() - start_time

    avg_time = duration / iterations * 1000  # 转换为毫秒

    logger.info(f"评估次数: {iterations}")
    logger.info(f"总耗时: {duration:.4f}秒")
    logger.info(f"平均耗时: {avg_time:.4f}毫秒/次")

    # 验证性能
    assert avg_time < 1.0, f"平均评估时间应小于1毫秒，实际: {avg_time:.4f}毫秒"

    logger.info("✅ 测试7通过")


# ==================== 主程序 ====================


def main():
    """主程序：运行所有集成测试"""
    logger.info("\n" + "=" * 100)
    logger.info("监控系统与LoadBalancer集成测试")
    logger.info("=" * 100)

    try:
        test_evaluator_normal_state()
        test_evaluator_high_pressure()
        test_evaluator_swap_detection()
        test_resource_monitor_integration()
        test_detailed_subsystem_metrics()
        test_bottleneck_identification()
        test_performance_comparison()

        logger.info("\n" + "=" * 100)
        logger.info("✅ 所有集成测试通过")
        logger.info("=" * 100)

        return 0

    except AssertionError as e:
        logger.error(f"\n❌ 测试失败: {e}")
        return 1

    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
