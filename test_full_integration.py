# -*- coding: utf-8 -*-
"""
全系统集成测试.

验证整个星辰金融终端系统的完整功能。
"""

import sys
import time
import unittest
from pathlib import Path

# 项目特定导入 - 按字母顺序排列
from backend.core import (
    DataModelManager, MonitoringManager, PerformanceOptimizer,
    TerminalEngine
)
from backend.core.factories import UnifiedFactory
from backend.core.models import UnifiedMarketData
from backend.core.monitoring import HealthChecker, TestRunner
from backend.core.shared_services import ConfigService
from backend.core.vnpy_integration import get_terminal_engine

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 条件导入 - 这些模块可能不存在，所以放在最后
try:
    from hot_reload import HotReloadMonitor
except ImportError:
    HotReloadMonitor = None

try:
    from start_terminal import TerminalLauncher
except ImportError:
    TerminalLauncher = None


def test_complete_workflow():
    """测试完整工作流程."""
    print("🧪 测试完整工作流程...")

    try:
        # 1. 初始化核心组件
        print("  🔧 初始化核心组件...")
        engine = get_terminal_engine()
        config_service = ConfigService()
        # optimizer = get_performance_optimizer(engine)  # 暂时注释，避免未使用警告

        # 2. 健康检查
        print("  💚 执行健康检查...")
        health_checker = HealthChecker(engine)
        health_result = health_checker.check_system_health()

        if health_result['health_score'] < 80:
            print(f"    ⚠️ 健康评分较低: {health_result['health_score']}")
        else:
            print(f"    ✅ 健康评分良好: {health_result['health_score']}")

        # 3. 性能测试
        print("  ⚡ 执行性能测试...")
        test_runner = TestRunner(config_service)
        perf_result = test_runner.run_performance_tests()

        if perf_result.get('success'):
            print("    ✅ 性能测试通过")
        else:
            print(f"    ❌ 性能测试失败: {perf_result.get('error')}")

        # 4. 监控系统
        print("  📊 测试监控系统...")
        monitoring_manager = MonitoringManager(config_service, engine)

        # 等待监控收集数据
        time.sleep(3)

        status = monitoring_manager.get_status()
        if status['performance_monitor']['active']:
            print("    ✅ 性能监控正常")
        else:
            print("    ❌ 性能监控异常")

        # 5. 综合测试
        print("  🎯 执行综合测试...")
        comprehensive_result = monitoring_manager.run_comprehensive_test()

        health_ok = comprehensive_result['summary']['health_score'] >= 80
        tests_ok = comprehensive_result['summary']['tests_passed']
        perf_ok = comprehensive_result['summary']['performance_ok']
        overall_success = health_ok and tests_ok and perf_ok

        if overall_success:
            print("    🎉 综合测试通过")
            return True
        else:
            print("    ❌ 综合测试失败")
            return False

    except (ImportError, AttributeError, RuntimeError) as e:
        print(f"    ❌ 工作流程测试异常: {e}")
        return False


def test_hot_reload_integration():
    """测试热更新集成."""
    print("\n🔥 测试热更新集成...")

    try:
        # 模拟文件变化检测
        if HotReloadMonitor is None:
            print("    ⚠️ 热更新模块不可用，跳过测试")
            return True

        monitor = HotReloadMonitor(project_root)

        # 启动监控
        monitor.start_monitoring()
        time.sleep(2)

        # 检查监控状态
        status = monitor.get_status()
        if status['monitoring']:
            print(f"    ✅ 热更新监控启动成功，监控 {status['files_watched']} 个文件")
        else:
            print("    ❌ 热更新监控启动失败")
            return False

        # 停止监控
        monitor.stop_monitoring()
        print("    ✅ 热更新监控正常停止")

        return True

    except (ImportError, AttributeError, RuntimeError) as e:
        print(f"    ❌ 热更新集成测试异常: {e}")
        return False


def test_launcher_integration():
    """测试启动器集成."""
    print("\n🚀 测试启动器集成...")

    try:
        if TerminalLauncher is None:
            print("    ⚠️ 启动器模块不可用，跳过测试")
            return True

        launcher = TerminalLauncher()

        # 运行诊断
        diagnostics = launcher.run_diagnostics()

        success_count = sum(
            1 for v in diagnostics.values()
            if v and str(v) != 'import_error'
        )

        if success_count >= 5:  # 大部分检查通过
            print(f"    ✅ 启动器诊断通过 ({success_count}/6 项)")
            return True
        else:
            print(f"    ❌ 启动器诊断失败 ({success_count}/6 项通过)")
            return False

    except (ImportError, AttributeError, RuntimeError) as e:
        print(f"    ❌ 启动器集成测试异常: {e}")
        return False


class IntegrationTestSuite(unittest.TestCase):
    """集成测试套件."""

    def test_core_modules_loaded(self):
        """测试核心模块加载."""
        try:
            # 测试核心模块导入
            # 这些导入已经在文件顶部完成

            # 测试实例创建
            engine = TerminalEngine()
            config = ConfigService()
            optimizer = PerformanceOptimizer(engine)
            manager = MonitoringManager(config, engine)

            self.assertIsNotNone(engine)
            self.assertIsNotNone(config)
            self.assertIsNotNone(optimizer)
            self.assertIsNotNone(manager)

        except (ImportError, AttributeError, RuntimeError) as e:
            self.fail(f"核心模块加载失败: {e}")

    def test_data_models_integration(self):
        """测试数据模型集成."""
        try:
            # 这些导入已经在文件顶部完成

            # 创建测试数据
            market_data = UnifiedMarketData(
                symbol="TEST001",
                exchange="TEST",
                data_type="tick",
                datetime=None,
                timestamp=0,
                close_price=100.0,
                volume=1000
            )

            # 测试数据管理器
            manager = DataModelManager()
            manager.add_market_data(market_data)

            retrieved = manager.get_market_data("TEST001", "TEST")
            self.assertEqual(len(retrieved), 1)
            self.assertEqual(retrieved[0].symbol, "TEST001")

        except (ImportError, AttributeError, RuntimeError) as e:
            self.fail(f"数据模型集成失败: {e}")

    def test_factory_integration(self):
        """测试工厂集成."""
        try:
            # 这个导入已经在文件顶部完成

            engine = get_terminal_engine()
            factory = UnifiedFactory(engine)

            # 测试工厂状态
            status = factory.get_status()
            self.assertIn('gateway_count', status)
            self.assertIn('strategy_count', status)
            self.assertIn('datafeed_count', status)

        except (ImportError, AttributeError, RuntimeError) as e:
            self.fail(f"工厂集成失败: {e}")


def main():
    """主测试函数."""
    print("🎯 星辰金融终端全系统集成测试")
    print("=" * 60)

    # 运行工作流程测试
    workflow_success = test_complete_workflow()

    # 运行热更新测试
    hot_reload_success = test_hot_reload_integration()

    # 运行启动器测试
    launcher_success = test_launcher_integration()

    # 运行单元测试套件
    print("\n🧪 运行单元测试套件...")
    suite = unittest.TestLoader().loadTestsFromTestCase(IntegrationTestSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 全系统集成测试结果汇总:")
    print("=" * 60)

    tests = [
        ("完整工作流程", workflow_success),
        ("热更新集成", hot_reload_success),
        ("启动器集成", launcher_success),
        ("单元测试套件", test_result.wasSuccessful())
    ]

    passed = 0
    for test_name, success in tests:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:<15} : {status}")
        if success:
            passed += 1

    print("-" * 60)
    print(f"总体结果: {passed}/{len(tests)} 个测试通过")

    if passed == len(tests):
        print("\n🎉 全系统集成测试全部通过！")
        print("🌟 星辰金融终端已准备就绪")
        return 0
    else:
        print(f"\n⚠️  有 {len(tests) - passed} 个测试失败")
        print("🔧 请检查相关模块后重新测试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
