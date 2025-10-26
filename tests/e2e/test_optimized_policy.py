# -*- coding: utf-8 -*-
"""
验证优化后的策略决策器

快速测试新的决策矩阵是否符合预期
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_policy_decisions():
    """测试策略决策器的各种场景"""
    print("\n" + "=" * 70)
    print("测试优化后的策略决策器")
    print("=" * 70)

    from backend.infrastructure.data_module_vnpy.load_balancer import (
        ExecutionPolicy,
        ResourceMonitor,
    )
    from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
        DataQualityScanTask,
    )

    policy = ExecutionPolicy()
    monitor = ResourceMonitor(event_engine=None)

    # 创建不同的测试场景
    scenarios = [
        ("30个品种", 30),
        ("100个品种", 100),
        ("500个品种", 500),
        ("5000个品种", 5000),
    ]

    print(f"\n系统信息: CPU={policy.cpu_count}核心, 内存={policy.total_memory_gb:.1f}GB\n")

    for name, count in scenarios:
        task = DataQualityScanTask(f"test_{count}", symbols_count=count)
        pressure = monitor.get_current_pressure()

        plan = policy.select_execution_plan(task, pressure)

        print(f"【{name}】")
        print(f"  资源压力: {pressure.score:.1f}% ({pressure.bottleneck}瓶颈)")
        print(f"  执行模型: {plan.model_type}")
        print(
            f"  初始配置: {plan.initial_config.max_workers}线程, 批次{plan.initial_config.batch_size}"
        )
        print(
            f"  调整策略: +{plan.adjustment_strategy.increase_step*100:.0f}%, -{plan.adjustment_strategy.decrease_step*100:.0f}%"
        )
        print(f"  决策理由: {plan.reason}")
        print()

    print("✅ 策略决策器测试完成！\n")
    return True


def test_pressure_scenarios():
    """测试不同压力场景下的决策"""
    print("\n" + "=" * 70)
    print("测试不同资源压力场景")
    print("=" * 70)

    from backend.infrastructure.data_module_vnpy.load_balancer import ExecutionPolicy
    from backend.infrastructure.data_module_vnpy.load_balancer.monitors import ResourcePressure
    from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataQualityScanTask

    policy = ExecutionPolicy()
    task = DataQualityScanTask("test", symbols_count=100)

    # 模拟不同压力场景
    test_cases = [
        ("CPU瓶颈-低压力", "cpu", 20.0),
        ("CPU瓶颈-中压力", "cpu", 50.0),
        ("CPU瓶颈-高压力", "cpu", 80.0),
        ("磁盘瓶颈-低压力", "disk", 25.0),
        ("磁盘瓶颈-高压力", "disk", 75.0),
        ("内存瓶颈", "memory", 60.0),
        ("系统正常-低压力", "balanced", 25.0),
        ("系统正常-中压力", "balanced", 55.0),
    ]

    for name, bottleneck, score in test_cases:
        # 构造ResourcePressure对象
        pressure = ResourcePressure(
            score=score,
            bottleneck=bottleneck,
            below_low_threshold=(score < 35),
            above_high_threshold=(score > 70),
            scale_suggestion=100.0 / max(score, 1.0),  # 简化的scale计算
            cpu_score=score if bottleneck == "cpu" else 50.0,
            memory_score=score if bottleneck == "memory" else 50.0,
            disk_score=score if bottleneck == "disk" else 50.0,
            network_score=50.0,
            swap_active=False,
            emergency=False,
            reason=f"模拟{name}场景",
        )

        plan = policy.select_execution_plan(task, pressure)

        print(f"\n【{name}】压力{score:.1f}%")
        print(
            f"  配置: {plan.initial_config.max_workers}线程, 批次{plan.initial_config.batch_size}"
        )
        print(f"  理由: {plan.reason}")

    print("\n✅ 压力场景测试完成！\n")
    return True


def main():
    """主测试函数"""
    tests = [
        test_policy_decisions,
        test_pressure_scenarios,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback

            traceback.print_exc()
            results.append(False)

    if all(results):
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
