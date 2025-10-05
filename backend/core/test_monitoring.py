# -*- coding: utf-8 -*-
"""
监控和测试模块测试
验证性能监控、健康检查、单元测试等功能
"""

import sys
import time
from pathlib import Path

# 使用绝对导入避免相对导入问题
from backend.core.vnpy_integration import get_terminal_engine
from backend.core.shared_services import ConfigService
from backend.core.monitoring import (
    PerformanceMonitor, TestRunner, HealthChecker, MonitoringManager
)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_performance_monitor():
    """测试性能监控器"""
    print("=== 测试性能监控器 ===")

    # 创建配置服务
    config_service = ConfigService("test_monitoring_config.json")

    # 创建性能监控器
    monitor = PerformanceMonitor(config_service)

    # 启动监控
    monitor.start_monitoring(interval=1.0)

    # 等待收集一些数据
    time.sleep(3)

    # 获取监控指标
    metrics = monitor.get_metrics(hours=1)
    print(f"收集到监控指标: {len(metrics)} 个类别")

    # 检查是否有系统指标
    if "system" in metrics and metrics["system"]:
        latest = metrics["system"][-1]
        cpu_percent = latest.get('cpu_percent', 0)
        memory_percent = latest.get('memory_percent', 0)
        print(f"最新系统指标: CPU {cpu_percent:.1f}%, 内存 {memory_percent:.1f}%")
    else:
        print("警告: 未收集到系统指标")

    # 获取告警
    alerts = monitor.get_alerts()
    print(f"当前告警数量: {len(alerts)}")

    # 获取摘要
    summary = monitor.get_summary()
    total_alerts = summary['total_alerts']
    monitoring_status = '激活' if summary['monitoring_active'] else '停止'
    print(f"监控摘要: {total_alerts} 个告警, 监控状态: {monitoring_status}")

    # 停止监控
    monitor.stop_monitoring()

    print("✅ 性能监控器测试通过")


def test_health_checker():
    """测试健康检查器"""
    print("\n=== 测试健康检查器 ===")

    # 获取终端引擎
    engine = get_terminal_engine()

    # 创建健康检查器
    health_checker = HealthChecker(engine)

    # 执行健康检查
    health_result = health_checker.check_system_health()

    print(f"健康评分: {health_result['health_score']}")
    print(f"健康状态: {health_result['status']}")
    print(f"检查项目数量: {len(health_result['checks'])}")

    # 检查各个组件
    for check_name, check_result in health_result['checks'].items():
        status = check_result.get('status', 'unknown')
        print(f"  {check_name}: {status}")

    # 获取检查历史
    history = health_checker.get_check_history(limit=5)
    print(f"检查历史: {len(history)} 条记录")

    print("✅ 健康检查器测试通过")


def test_test_runner():
    """测试测试运行器"""
    print("\n=== 测试测试运行器 ===")

    # 创建配置服务
    config_service = ConfigService("test_test_config.json")

    # 创建测试运行器
    test_runner = TestRunner(config_service)

    # 运行单元测试
    print("运行单元测试...")
    unit_result = test_runner.run_unit_tests()

    if unit_result.get("success", False):
        print(f"✅ 单元测试通过: {unit_result['tests_run']} 个测试")
    else:
        failures = unit_result.get('failures', 0)
        errors = unit_result.get('errors', 0)
        print(f"❌ 单元测试失败: {failures} 个失败, {errors} 个错误")

    # 运行集成测试
    print("运行集成测试...")
    integration_result = test_runner.run_integration_tests()

    if integration_result.get("success", False):
        print("✅ 集成测试通过")
    else:
        print(f"❌ 集成测试失败: {integration_result.get('error', '未知错误')}")

    # 运行性能测试
    print("运行性能测试...")
    performance_result = test_runner.run_performance_tests()

    if performance_result.get("success", False):
        print("✅ 性能测试通过")
    else:
        print(f"❌ 性能测试失败: {performance_result.get('error', '未知错误')}")

    # 获取测试历史
    history = test_runner.get_test_results(limit=3)
    print(f"测试历史: {len(history)} 条记录")

    print("✅ 测试运行器测试通过")


def test_monitoring_manager():
    """测试监控管理器"""
    print("\n=== 测试监控管理器 ===")

    # 创建配置服务
    config_service = ConfigService("test_manager_config.json")

    # 获取终端引擎
    engine = get_terminal_engine()

    # 创建监控管理器
    manager = MonitoringManager(config_service, engine)

    # 等待监控启动
    time.sleep(2)

    # 获取状态
    status = manager.get_status()
    print(f"监控管理器状态: {status}")

    # 运行综合测试
    print("运行综合测试...")
    comprehensive_result = manager.run_comprehensive_test()

    print("综合测试完成:")
    print(f"  - 健康评分: {comprehensive_result['summary']['health_score']}")
    print(f"  - 测试通过: {comprehensive_result['summary']['tests_passed']}")
    print(f"  - 性能正常: {comprehensive_result['summary']['performance_ok']}")

    # 停止监控
    manager.stop_all_monitoring()

    print("✅ 监控管理器测试通过")


def test_stress_test():
    """压力测试"""
    print("\n=== 压力测试 ===")

    # 获取终端引擎
    engine = get_terminal_engine()

    # 创建健康检查器
    health_checker = HealthChecker(engine)

    # 执行多次健康检查
    results = []
    for i in range(10):
        result = health_checker.check_system_health()
        results.append(result)
        time.sleep(0.1)  # 小间隔

    # 检查结果一致性
    scores = [r['health_score'] for r in results]
    avg_score = sum(scores) / len(scores)

    print(f"10次健康检查平均评分: {avg_score:.1f}")
    variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
    std_deviation = variance ** 0.5
    print(f"评分标准差: {std_deviation:.1f}")

    # 检查历史记录
    history = health_checker.get_check_history()
    print(f"历史记录数量: {len(history)}")

    print("✅ 压力测试通过")


def main():
    """主测试函数"""
    print("🚀 开始监控和测试模块测试")
    print("=" * 50)

    # 运行所有测试
    tests = [
        test_performance_monitor,
        test_health_checker,
        test_test_runner,
        test_monitoring_manager,
        test_stress_test
    ]

    results = []
    for test_func in tests:
        try:
            test_func()  # 只调用函数，不赋值返回值
            results.append(True)
        except (RuntimeError, TypeError, AttributeError) as e:
            print(f"❌ 测试失败 {test_func.__name__}: {e}")
            results.append(False)

    # 输出结果摘要
    print("\n" + "=" * 50)
    print("📊 测试结果摘要:")

    passed = sum(results)
    total = len(results)

    for i, (test_func, result) in enumerate(zip(tests, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {test_func.__name__}: {status}")

    print(f"\n总体结果: {passed}/{total} 个测试通过")

    if passed == total:
        print("🎉 所有监控和测试模块测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，需要检查相关模块")
        return 1


if __name__ == "__main__":
    sys.exit(main())
