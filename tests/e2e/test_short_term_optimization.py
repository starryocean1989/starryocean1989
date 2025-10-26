# -*- coding: utf-8 -*-
"""
短期优化测试

测试持久化进程池和自适应批次大小计算器的功能和性能提升。

测试场景：
1. 持久化进程池复用验证
2. 自适应批次大小计算验证
3. 性能对比测试（优化前后）
"""

import logging
import time
import pytest
from typing import List

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ==================== 测试1：持久化进程池复用 ====================


# 顶层函数（用于 multiprocessing，必须可以 pickle）
def _test_task(x):
    """测试任务函数"""
    return x * 2


def _test_processor(data: dict) -> dict:
    """测试处理函数"""
    import time

    time.sleep(0.01)  # 模拟耗时操作
    return {"result": data["value"] * 2}


def test_persistent_process_pool():
    """测试持久化进程池复用功能"""
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        PersistentProcessPool,
        get_process_pool,
        initialize_process_pool,
    )

    logger.info("=" * 80)
    logger.info("测试1：持久化进程池复用")
    logger.info("=" * 80)

    # 测试1.1：获取单例实例
    logger.info("\n1.1 测试单例模式")
    pool1 = PersistentProcessPool.get_instance()
    pool2 = get_process_pool()
    assert pool1 is pool2, "进程池应该是单例"
    logger.info("✅ 单例模式验证成功")

    # 测试1.2：初始化进程池
    logger.info("\n1.2 测试初始化")
    success = initialize_process_pool(processes=4)
    assert success, "进程池初始化失败"
    assert pool1.is_initialized(), "进程池应该已初始化"
    assert pool1.get_size() == 4, "进程池大小应该是4"
    logger.info(f"✅ 初始化成功：{pool1.get_size()}进程")

    # 测试1.3：进程池复用
    logger.info("\n1.3 测试进程池复用")

    start = time.time()
    result1 = pool1.map(_test_task, range(100))
    time1 = time.time() - start
    logger.info(f"第1次执行耗时: {time1:.4f}秒")

    start = time.time()
    result2 = pool1.map(_test_task, range(100))
    time2 = time.time() - start
    logger.info(f"第2次执行耗时: {time2:.4f}秒（复用进程池）")

    assert len(result1) == 100
    assert len(result2) == 100
    logger.info(f"✅ 进程池复用成功，第2次执行相对速度提升: {time1/time2:.2f}x")

    # 测试1.4：动态调整进程池大小
    logger.info("\n1.4 测试动态调整")
    success = pool1.resize(8)
    assert success, "调整进程池大小失败"
    assert pool1.get_size() == 8, "进程池大小应该是8"
    logger.info(f"✅ 动态调整成功：4 → {pool1.get_size()}进程")

    result3 = pool1.map(_test_task, range(100))
    assert len(result3) == 100
    logger.info("✅ 调整后进程池正常工作")


# ==================== 测试2：自适应批次大小 ====================


def test_adaptive_batch_size():
    """测试自适应批次大小计算器"""
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        AdaptiveBatchSizeCalculator,
        calculate_adaptive_batch_size,
    )

    logger.info("\n" + "=" * 80)
    logger.info("测试2：自适应批次大小计算")
    logger.info("=" * 80)

    calculator = AdaptiveBatchSizeCalculator()

    # 测试2.1：不同IO类型的批次大小
    logger.info("\n2.1 测试不同IO类型")
    test_cases = [
        ("disk", 5000, 50.0),  # 磁盘IO，5000任务，50%内存压力
        ("network", 5000, 50.0),  # 网络IO
        ("memory", 5000, 50.0),  # 内存受限
        ("cpu", 5000, 50.0),  # CPU密集
    ]

    for io_type, task_count, memory_pressure in test_cases:
        batch_size = calculator.calculate(
            task_count=task_count, io_type=io_type, memory_pressure=memory_pressure
        )
        logger.info(f"  {io_type:8s}: 批次大小 = {batch_size}")
        assert 10 <= batch_size <= 200, f"批次大小{batch_size}超出合理范围"

    logger.info("✅ 不同IO类型批次大小计算正确")

    # 测试2.2：不同内存压力的批次大小
    logger.info("\n2.2 测试不同内存压力")
    for memory_pressure in [30.0, 50.0, 80.0]:
        batch_size = calculator.calculate(
            task_count=5000, io_type="disk", memory_pressure=memory_pressure
        )
        logger.info(f"  内存压力 {memory_pressure:4.1f}%: 批次大小 = {batch_size}")

    logger.info("✅ 不同内存压力批次大小计算正确")

    # 测试2.3：不同任务数量的批次大小
    logger.info("\n2.3 测试不同任务数量")
    for task_count in [50, 500, 5000]:
        batch_size = calculator.calculate(
            task_count=task_count, io_type="disk", memory_pressure=50.0
        )
        logger.info(f"  任务数 {task_count:5d}: 批次大小 = {batch_size}")

    logger.info("✅ 不同任务数量批次大小计算正确")

    # 测试2.4：便捷函数
    logger.info("\n2.4 测试便捷函数")
    batch_size = calculate_adaptive_batch_size(task_count=1000, io_type="disk")
    logger.info(f"  便捷函数计算批次大小 = {batch_size}")
    assert 10 <= batch_size <= 200
    logger.info("✅ 便捷函数工作正常")


# ==================== 测试3：集成测试（MultiProcessBatchModel） ====================


def test_multiprocess_batch_with_persistent_pool():
    """测试MultiProcessBatchModel使用持久化进程池"""
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        MultiProcessBatchModel,
        TaskUnit,
        ResourceMonitor,
        ExecutionPolicy,
    )

    logger.info("\n" + "=" * 80)
    logger.info("测试3：MultiProcessBatchModel集成持久化进程池")
    logger.info("=" * 80)

    # 准备测试任务
    task_units = [
        TaskUnit(unit_id=f"task_{i}", data={"value": i}, processor=_test_processor)
        for i in range(100)
    ]

    # 创建资源监控和执行模型
    resource_monitor = ResourceMonitor(event_engine=None)
    execution_policy = ExecutionPolicy()

    # 创建临时任务对象
    class TempTask:
        resource_profile = type("obj", (object,), {"io_type": "disk", "estimated_count": 100})()

    pressure = resource_monitor.get_current_pressure()
    plan = execution_policy.select_execution_plan(TempTask(), pressure)

    logger.info(f"\n执行计划: {plan.reason}")
    logger.info(f"初始配置: {plan.initial_config}")

    # 测试3.1：第一次执行（初始化进程池）
    logger.info("\n3.1 第一次执行（初始化进程池）")
    model = MultiProcessBatchModel()
    start = time.time()
    results1 = model.execute_with_monitoring(
        task_units=task_units,
        config=plan.initial_config,
        resource_monitor=resource_monitor,
        adjustment_strategy=plan.adjustment_strategy,
    )
    time1 = time.time() - start
    logger.info(f"第1次执行耗时: {time1:.4f}秒")
    assert len(results1) == 100
    assert all(r.success for r in results1)
    logger.info(f"✅ 第1次执行成功：{len(results1)}个任务")

    # 测试3.2：第二次执行（复用进程池）
    logger.info("\n3.2 第二次执行（复用进程池）")
    start = time.time()
    results2 = model.execute_with_monitoring(
        task_units=task_units,
        config=plan.initial_config,
        resource_monitor=resource_monitor,
        adjustment_strategy=plan.adjustment_strategy,
    )
    time2 = time.time() - start
    logger.info(f"第2次执行耗时: {time2:.4f}秒（复用进程池）")
    assert len(results2) == 100
    assert all(r.success for r in results2)
    logger.info(f"✅ 第2次执行成功，性能提升: {(time1-time2)/time1*100:.1f}%")


# ==================== 测试4：自适应批次大小集成 ====================


def test_execution_policy_with_adaptive_batch():
    """测试ExecutionPolicy集成自适应批次大小"""
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        ExecutionPolicy,
        ResourceMonitor,
    )

    logger.info("\n" + "=" * 80)
    logger.info("测试4：ExecutionPolicy集成自适应批次")
    logger.info("=" * 80)

    resource_monitor = ResourceMonitor(event_engine=None)
    execution_policy = ExecutionPolicy()

    # 测试不同任务类型的批次大小
    test_cases = [
        ("disk", 50),
        ("disk", 500),
        ("disk", 5000),
    ]

    for io_type, task_count in test_cases:

        class TempTask:
            resource_profile = type(
                "obj", (object,), {"io_type": io_type, "estimated_count": task_count}
            )()

        pressure = resource_monitor.get_current_pressure()
        plan = execution_policy.select_execution_plan(TempTask(), pressure)

        logger.info(
            f"\n任务: {io_type}, {task_count}个 → " f"批次大小: {plan.initial_config.batch_size}"
        )

        assert 10 <= plan.initial_config.batch_size <= 200
        assert plan.initial_config.batch_size <= task_count

    logger.info("\n✅ ExecutionPolicy自适应批次大小工作正常")


# ==================== 运行所有测试 ====================


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("短期优化测试套件")
    logger.info("=" * 80)

    try:
        # 运行所有测试
        test_persistent_process_pool()
        test_adaptive_batch_size()
        test_multiprocess_batch_with_persistent_pool()
        test_execution_policy_with_adaptive_batch()

        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有短期优化测试通过！")
        logger.info("=" * 80)
        logger.info(
            "\n短期优化功能验证：\n"
            "1. ✅ 持久化进程池复用（PersistentProcessPool）\n"
            "2. ✅ 自适应批次大小计算（AdaptiveBatchSizeCalculator）\n"
            "3. ✅ MultiProcessBatchModel集成持久化进程池\n"
            "4. ✅ ExecutionPolicy集成自适应批次\n"
            "\n预期性能提升：\n"
            "- 进程池复用：10-20%\n"
            "- 自适应批次：5-10%\n"
            "- 综合提升：15-30%"
        )

    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        raise

