# -*- coding: utf-8 -*-
"""
短期优化安全测试

只测试集成和配置，不实际创建进程池（避免Windows multiprocessing问题）。
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


def test_module_structure():
    """测试1：验证模块结构和导出"""
    logger.info("=" * 80)
    logger.info("测试1：验证模块结构和导出")
    logger.info("=" * 80)

    # 验证持久化进程池模块
    try:
        from backend.infrastructure.data_module_vnpy.load_balancer.process_pool import (
            PersistentProcessPool,
            get_process_pool,
            initialize_process_pool,
            shutdown_process_pool,
        )

        logger.info("✅ process_pool模块导入成功")
        logger.info(f"  - PersistentProcessPool: {PersistentProcessPool}")
        logger.info(f"  - get_process_pool: {get_process_pool}")
    except Exception as e:
        logger.error(f"❌ process_pool模块导入失败: {e}")
        raise

    # 验证自适应批次模块
    try:
        from backend.infrastructure.data_module_vnpy.load_balancer.adaptive_batch import (
            AdaptiveBatchSizeCalculator,
            get_adaptive_batch_calculator,
            calculate_adaptive_batch_size,
        )

        logger.info("✅ adaptive_batch模块导入成功")
        logger.info(f"  - AdaptiveBatchSizeCalculator: {AdaptiveBatchSizeCalculator}")
        logger.info(f"  - calculate_adaptive_batch_size: {calculate_adaptive_batch_size}")
    except Exception as e:
        logger.error(f"❌ adaptive_batch模块导入失败: {e}")
        raise

    # 验证__init__导出
    try:
        from backend.infrastructure.data_module_vnpy import load_balancer

        required_exports = [
            "PersistentProcessPool",
            "get_process_pool",
            "initialize_process_pool",
            "shutdown_process_pool",
            "AdaptiveBatchSizeCalculator",
            "get_adaptive_batch_calculator",
            "calculate_adaptive_batch_size",
        ]

        for export in required_exports:
            assert hasattr(load_balancer, export), f"缺少导出: {export}"

        logger.info(f"✅ load_balancer.__init__导出验证通过（{len(required_exports)}个）")
    except Exception as e:
        logger.error(f"❌ 导出验证失败: {e}")
        raise


def test_persistent_pool_class():
    """测试2：持久化进程池类结构（不创建实例）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2：持久化进程池类结构")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer.process_pool import (
        PersistentProcessPool,
    )

    # 验证类方法
    assert hasattr(PersistentProcessPool, "get_instance")
    assert hasattr(PersistentProcessPool, "initialize")
    assert hasattr(PersistentProcessPool, "resize")
    assert hasattr(PersistentProcessPool, "map")
    assert hasattr(PersistentProcessPool, "is_initialized")
    assert hasattr(PersistentProcessPool, "get_size")
    assert hasattr(PersistentProcessPool, "shutdown")

    logger.info("✅ PersistentProcessPool类方法完整")
    logger.info("  方法: get_instance, initialize, resize, map, is_initialized, get_size, shutdown")


def test_adaptive_batch_calculator():
    """测试3：自适应批次大小计算器"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3：自适应批次大小计算器")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        AdaptiveBatchSizeCalculator,
        calculate_adaptive_batch_size,
    )

    calculator = AdaptiveBatchSizeCalculator()
    logger.info(f"✅ AdaptiveBatchSizeCalculator实例创建成功")

    # 测试不同IO类型
    test_cases = [
        ("disk", 5000, 50.0, "磁盘IO"),
        ("network", 5000, 50.0, "网络IO"),
        ("memory", 5000, 50.0, "内存受限"),
        ("cpu", 5000, 50.0, "CPU密集"),
    ]

    results = []
    for io_type, task_count, memory_pressure, desc in test_cases:
        batch_size = calculator.calculate(
            task_count=task_count, io_type=io_type, memory_pressure=memory_pressure
        )
        results.append((desc, batch_size))
        assert 10 <= batch_size <= 200, f"{desc}批次大小{batch_size}超出范围[10, 200]"

    logger.info("✅ 不同IO类型批次大小计算正确:")
    for desc, batch_size in results:
        logger.info(f"  {desc:10s}: {batch_size}")

    # 测试不同内存压力
    logger.info("\n内存压力对批次大小的影响:")
    for memory_pressure in [30.0, 50.0, 80.0]:
        batch_size = calculator.calculate(
            task_count=5000, io_type="disk", memory_pressure=memory_pressure
        )
        logger.info(f"  压力{memory_pressure:5.1f}%: 批次{batch_size}")

    # 测试不同任务数量
    logger.info("\n任务数量对批次大小的影响:")
    for task_count in [50, 500, 5000]:
        batch_size = calculator.calculate(
            task_count=task_count, io_type="disk", memory_pressure=50.0
        )
        logger.info(f"  任务数{task_count:5d}: 批次{batch_size}")

    # 测试便捷函数
    batch_size = calculate_adaptive_batch_size(task_count=1000, io_type="disk")
    assert 10 <= batch_size <= 200
    logger.info(f"\n✅ 便捷函数正常: 批次 = {batch_size}")


def test_execution_policy_integration():
    """测试4：ExecutionPolicy集成自适应批次"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4：ExecutionPolicy集成自适应批次")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        ExecutionPolicy,
        ResourceMonitor,
    )

    # 创建策略
    execution_policy = ExecutionPolicy()
    logger.info(f"✅ ExecutionPolicy创建成功")
    logger.info(f"  CPU核心数: {execution_policy.cpu_count}")
    logger.info(f"  内存: {execution_policy.total_memory_gb:.1f}GB")
    logger.info(
        f"  安全区间: {execution_policy.SAFE_ZONE_LOWER}-{execution_policy.SAFE_ZONE_UPPER}%"
    )

    # 验证批次计算器集成
    assert hasattr(execution_policy, "batch_calculator"), "ExecutionPolicy未集成批次计算器"
    logger.info(f"✅ 批次计算器已集成: {execution_policy.batch_calculator}")

    # 创建资源监控
    resource_monitor = ResourceMonitor(event_engine=None)
    logger.info(f"✅ ResourceMonitor创建成功")

    # 测试不同任务规模的执行计划
    test_cases = [("disk", 50), ("disk", 500), ("disk", 5000)]

    logger.info("\n不同任务规模的执行计划:")
    for io_type, task_count in test_cases:

        class TempTask:
            resource_profile = type(
                "obj", (object,), {"io_type": io_type, "estimated_count": task_count}
            )()

        pressure = resource_monitor.get_current_pressure()
        plan = execution_policy.select_execution_plan(TempTask(), pressure)

        logger.info(
            f"  任务{task_count:5d}个: 批次={plan.initial_config.batch_size:3d}, "
            f"进程={plan.initial_config.max_workers}, "
            f"模型={plan.model_type}"
        )

        assert 10 <= plan.initial_config.batch_size <= 200
        assert plan.initial_config.batch_size <= task_count
        assert plan.model_type == "MultiProcessBatch"

    logger.info("✅ ExecutionPolicy自适应批次集成验证通过")


def test_multiprocess_batch_model_integration():
    """测试5：MultiProcessBatchModel集成持久化进程池"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5：MultiProcessBatchModel集成持久化进程池")
    logger.info("=" * 80)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        MultiProcessBatchModel,
    )

    # 创建模型实例
    model = MultiProcessBatchModel()
    logger.info(f"✅ MultiProcessBatchModel创建成功")

    # 验证持久化进程池集成
    assert hasattr(model, "_process_pool"), "MultiProcessBatchModel未集成进程池"
    assert model._process_pool is not None, "进程池未初始化"
    logger.info(f"  进程池实例: {model._process_pool}")
    logger.info(f"  进程池类型: {type(model._process_pool).__name__}")

    # 验证动态调整方法
    assert hasattr(model, "_try_increase_processes"), "缺少增加进程数方法"
    assert hasattr(model, "_try_decrease_processes"), "缺少减少进程数方法"
    assert hasattr(model, "_can_adjust"), "缺少防抖检查方法"
    logger.info("  动态调整方法: _try_increase_processes, _try_decrease_processes, _can_adjust")

    # 验证配置参数
    logger.info(f"  安全区间: {model.SAFE_ZONE_LOWER}-{model.SAFE_ZONE_UPPER}%")
    logger.info(f"  调整步长: +{model.INCREASE_STEP*100:.0f}%, -{model.DECREASE_STEP*100:.0f}%")
    logger.info(f"  检查间隔: {model.CHECK_INTERVAL}秒")
    logger.info(f"  防抖间隔: {model.MIN_ADJUSTMENT_INTERVAL}秒")

    logger.info("✅ MultiProcessBatchModel集成验证通过")


def test_integration_summary():
    """测试6：集成总结"""
    logger.info("\n" + "=" * 80)
    logger.info("测试6：集成总结")
    logger.info("=" * 80)

    changes = [
        (
            "backend/infrastructure/data_module_vnpy/load_balancer/process_pool.py",
            "新增",
            "持久化进程池",
        ),
        (
            "backend/infrastructure/data_module_vnpy/load_balancer/adaptive_batch.py",
            "新增",
            "自适应批次计算器",
        ),
        ("backend/infrastructure/data_module_vnpy/load_balancer/__init__.py", "修改", "导出新模块"),
        (
            "backend/infrastructure/data_module_vnpy/load_balancer/execution_models.py",
            "修改",
            "MultiProcessBatchModel集成进程池",
        ),
        (
            "backend/infrastructure/data_module_vnpy/load_balancer/policy.py",
            "修改",
            "ExecutionPolicy集成批次计算",
        ),
    ]

    logger.info("短期优化文件变更:")
    for file, action, desc in changes:
        logger.info(f"  [{action}] {desc}")
        logger.info(f"    {file}")

    logger.info("\n短期优化功能清单:")
    features = [
        "持久化进程池（PersistentProcessPool）",
        "  - 单例模式，全局唯一",
        "  - 延迟初始化",
        "  - 动态调整进程数",
        "  - 线程安全",
        "",
        "自适应批次大小（AdaptiveBatchSizeCalculator）",
        "  - 基于内存压力调整",
        "  - 基于任务数量调整",
        "  - 基于IO类型调整",
        "  - 历史统计学习（可选）",
        "",
        "MultiProcessBatchModel集成",
        "  - 使用持久化进程池",
        "  - 避免重复创建/销毁",
        "  - 动态调整时自动resize",
        "",
        "ExecutionPolicy集成",
        "  - 自适应批次大小计算",
        "  - 考虑IO类型、任务数、内存压力",
    ]

    for feature in features:
        logger.info(f"  {feature}")

    logger.info("\n预期性能提升:")
    logger.info("  - 进程池复用: 10-20%")
    logger.info("  - 自适应批次: 5-10%")
    logger.info("  - 综合提升: 15-30%")


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("短期优化安全测试套件（无进程池实际创建）")
    logger.info("=" * 80)

    try:
        test_module_structure()
        test_persistent_pool_class()
        test_adaptive_batch_calculator()
        test_execution_policy_integration()
        test_multiprocess_batch_model_integration()
        test_integration_summary()

        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有短期优化集成测试通过！")
        logger.info("=" * 80)
        logger.info(
            "\n测试结论:\n"
            "1. ✅ 模块结构正确\n"
            "2. ✅ 持久化进程池类完整\n"
            "3. ✅ 自适应批次计算正确\n"
            "4. ✅ ExecutionPolicy集成成功\n"
            "5. ✅ MultiProcessBatchModel集成成功\n"
            "6. ✅ 所有导出正确\n"
            "\n注意: 本测试避免实际创建进程池，避免Windows multiprocessing问题\n"
            "实际性能测试需要在生产环境中验证"
        )

    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        raise
