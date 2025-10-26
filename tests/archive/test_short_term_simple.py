# -*- coding: utf-8 -*-
"""
短期优化简化测试

简化版测试，专注于验证核心功能集成，避免multiprocessing复杂性。
"""

import logging
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_persistent_pool_initialization():
    """测试1：持久化进程池初始化"""
    logger.info("=" * 80)
    logger.info("测试1：持久化进程池初始化")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        PersistentProcessPool,
        get_process_pool,
    )

    # 测试单例模式
    pool1 = PersistentProcessPool.get_instance()
    pool2 = get_process_pool()
    assert pool1 is pool2, "进程池应该是单例"
    logger.info("✅ 单例模式正常")

    # 测试初始化
    success = pool1.initialize(processes=4)
    assert success, "进程池初始化失败"
    assert pool1.is_initialized(), "进程池未正确初始化"
    assert pool1.get_size() == 4, "进程池大小不正确"
    logger.info(f"✅ 进程池初始化成功: {pool1.get_size()}进程")

    # 测试动态调整
    success = pool1.resize(8)
    assert success, "进程池调整失败"
    assert pool1.get_size() == 8, "进程池调整后大小不正确"
    logger.info(f"✅ 进程池动态调整成功: 4 → {pool1.get_size()}进程")


def test_adaptive_batch_calculator():
    """测试2：自适应批次大小计算器"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2：自适应批次大小计算器")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        AdaptiveBatchSizeCalculator,
        calculate_adaptive_batch_size,
    )

    calculator = AdaptiveBatchSizeCalculator()

    # 测试不同IO类型
    test_cases = [
        ("disk", 5000, 50.0, "磁盘IO"),
        ("network", 5000, 50.0, "网络IO"),
        ("memory", 5000, 50.0, "内存受限"),
        ("cpu", 5000, 50.0, "CPU密集"),
    ]

    for io_type, task_count, memory_pressure, desc in test_cases:
        batch_size = calculator.calculate(
            task_count=task_count, io_type=io_type, memory_pressure=memory_pressure
        )
        logger.info(f"  {desc:10s}: 批次大小 = {batch_size}")
        assert 10 <= batch_size <= 200, f"{desc}批次大小{batch_size}超出范围"

    logger.info("✅ 不同IO类型批次大小计算正确")

    # 测试不同内存压力
    for memory_pressure in [30.0, 50.0, 80.0]:
        batch_size = calculator.calculate(
            task_count=5000, io_type="disk", memory_pressure=memory_pressure
        )
        logger.info(f"  内存压力{memory_pressure:5.1f}%: 批次 = {batch_size}")

    logger.info("✅ 不同内存压力批次大小计算正确")

    # 测试便捷函数
    batch_size = calculate_adaptive_batch_size(task_count=1000, io_type="disk")
    assert 10 <= batch_size <= 200
    logger.info(f"✅ 便捷函数正常: 批次 = {batch_size}")


def test_execution_policy_integration():
    """测试3：ExecutionPolicy集成自适应批次"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3：ExecutionPolicy集成自适应批次")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        ExecutionPolicy,
        ResourceMonitor,
    )

    resource_monitor = ResourceMonitor(event_engine=None)
    execution_policy = ExecutionPolicy()

    logger.info(
        f"策略初始化完成: CPU={execution_policy.cpu_count}, "
        f"内存={execution_policy.total_memory_gb:.1f}GB"
    )

    # 测试不同任务规模的批次大小
    test_cases = [("disk", 50), ("disk", 500), ("disk", 5000)]

    for io_type, task_count in test_cases:

        class TempTask:
            resource_profile = type(
                "obj", (object,), {"io_type": io_type, "estimated_count": task_count}
            )()

        pressure = resource_monitor.get_current_pressure()
        plan = execution_policy.select_execution_plan(TempTask(), pressure)

        logger.info(
            f"  任务规模{task_count:5d}: 批次={plan.initial_config.batch_size}, "
            f"进程={plan.initial_config.max_workers}"
        )

        assert 10 <= plan.initial_config.batch_size <= 200
        assert plan.initial_config.batch_size <= task_count

    logger.info("✅ ExecutionPolicy自适应批次集成正常")


def test_multiprocess_batch_model_integration():
    """测试4：MultiProcessBatchModel集成持久化进程池"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4：MultiProcessBatchModel集成持久化进程池")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        MultiProcessBatchModel,
    )

    model = MultiProcessBatchModel()
    logger.info(f"✅ MultiProcessBatchModel创建成功")
    logger.info(f"  - 持久化进程池已集成: {model._process_pool is not None}")
    logger.info(f"  - 支持动态调整: {hasattr(model, '_try_increase_processes')}")

    assert model._process_pool is not None, "持久化进程池未集成"
    logger.info("✅ MultiProcessBatchModel集成验证通过")


def test_exports():
    """测试5：验证新模块导出"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5：验证新模块导出")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy import load_balancer

    # 验证持久化进程池导出
    assert hasattr(load_balancer, "PersistentProcessPool")
    assert hasattr(load_balancer, "get_process_pool")
    assert hasattr(load_balancer, "initialize_process_pool")
    assert hasattr(load_balancer, "shutdown_process_pool")
    logger.info("✅ 持久化进程池模块导出正确")

    # 验证自适应批次导出
    assert hasattr(load_balancer, "AdaptiveBatchSizeCalculator")
    assert hasattr(load_balancer, "get_adaptive_batch_calculator")
    assert hasattr(load_balancer, "calculate_adaptive_batch_size")
    logger.info("✅ 自适应批次模块导出正确")


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("短期优化简化测试套件")
    logger.info("=" * 80)

    try:
        test_exports()
        test_persistent_pool_initialization()
        test_adaptive_batch_calculator()
        test_execution_policy_integration()
        test_multiprocess_batch_model_integration()

        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有短期优化集成测试通过！")
        logger.info("=" * 80)
        logger.info(
            "\n短期优化功能验证：\n"
            "1. ✅ 持久化进程池（PersistentProcessPool）\n"
            "2. ✅ 自适应批次大小（AdaptiveBatchSizeCalculator）\n"
            "3. ✅ ExecutionPolicy集成\n"
            "4. ✅ MultiProcessBatchModel集成\n"
            "5. ✅ 模块导出正确\n"
            "\n后续步骤：\n"
            "- 使用实际数据进行性能测试\n"
            "- 验证10-20%性能提升（进程池复用）\n"
            "- 验证5-10%性能提升（自适应批次）"
        )

    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        raise

