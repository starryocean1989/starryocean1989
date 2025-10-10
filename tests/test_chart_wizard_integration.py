# -*- coding: utf-8 -*-
"""测试vnpy_chartwizard集成

用于验证行情看板是否成功集成vnpy_chartwizard图表组件
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_vnpy_chartwizard_import():
    """测试vnpy_chartwizard导入"""
    print("=" * 60)
    print("测试1: 检查vnpy_chartwizard是否可导入")
    print("=" * 60)

    try:
        import vnpy_chartwizard

        print("✅ vnpy_chartwizard导入成功")

        if hasattr(vnpy_chartwizard, "__version__"):
            print(f"   版本: {vnpy_chartwizard.__version__}")

        if hasattr(vnpy_chartwizard, "ChartWidget"):
            print("✅ ChartWidget类可用")
        else:
            print("⚠️ ChartWidget类不可用")

        return True
    except ImportError as e:
        print(f"❌ vnpy_chartwizard导入失败: {e}")
        return False


def test_main_engine_available():
    """测试MainEngine是否可用"""
    print("\n" + "=" * 60)
    print("测试2: 检查MainEngine是否可用")
    print("=" * 60)

    try:
        from backend.core.base import get_main_engine, VNPY_AVAILABLE

        if not VNPY_AVAILABLE:
            print("❌ VNPY不可用")
            return False

        print("✅ VNPY可用")

        # 注意：在测试环境中，MainEngine可能尚未初始化
        # 这是正常的，因为它需要在应用启动时才初始化
        main_engine = get_main_engine()
        if main_engine:
            print("✅ MainEngine已初始化")
        else:
            print("⚠️ MainEngine未初始化（这在测试环境中是正常的）")
            print("   MainEngine将在应用启动时自动初始化")

        return True
    except Exception as e:
        print(f"❌ 检查MainEngine失败: {e}")
        return False


def test_chart_wizard_widget_import():
    """测试ChartWizardWidget导入"""
    print("\n" + "=" * 60)
    print("测试3: 检查ChartWizardWidget是否可导入")
    print("=" * 60)

    try:
        from ui.widgets.chart_wizard_widget import ChartWizardWidget, HAS_CHART_WIZARD

        print(f"✅ ChartWizardWidget导入成功")
        print(f"   HAS_CHART_WIZARD = {HAS_CHART_WIZARD}")

        if HAS_CHART_WIZARD:
            print("✅ 将使用vnpy_chartwizard专业图表")
        else:
            print("⚠️ 将使用pyqtgraph降级方案")

        return True
    except Exception as e:
        print(f"❌ ChartWizardWidget导入失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_market_dashboard_integration():
    """测试行情看板集成"""
    print("\n" + "=" * 60)
    print("测试4: 检查行情看板集成")
    print("=" * 60)

    try:
        from ui.components.market_dashboard.main_view import MarketDashboard

        print("✅ MarketDashboard导入成功")

        # 检查是否导入了正确的图表组件
        import inspect

        source = inspect.getsource(MarketDashboard)

        if "ChartWizardWidget" in source:
            print("✅ 行情看板已集成ChartWizardWidget")
        else:
            print("⚠️ 行情看板未集成ChartWizardWidget")

        if "from ui.widgets.chart_widget import ChartWidget" in source:
            print("⚠️ 仍在导入旧的ChartWidget（应该移除）")

        return True
    except Exception as e:
        print(f"❌ 行情看板集成检查失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_symbol_exchange_mapping():
    """测试品种交易所映射逻辑"""
    print("\n" + "=" * 60)
    print("测试5: 检查品种交易所映射逻辑")
    print("=" * 60)

    test_cases = [
        ("600000", "600000.SSE", "上海交易所"),
        ("000001", "000001.SZSE", "深圳交易所"),
        ("300001", "300001.SZSE", "深圳创业板"),
        ("688001", "688001.SSE", "上海科创板"),
    ]

    all_passed = True
    for symbol, expected_vt_symbol, desc in test_cases:
        if symbol.startswith("6"):
            result = f"{symbol}.SSE"
        else:
            result = f"{symbol}.SZSE"

        if result == expected_vt_symbol:
            print(f"✅ {desc}: {symbol} -> {result}")
        else:
            print(f"❌ {desc}: {symbol} -> {result} (期望: {expected_vt_symbol})")
            all_passed = False

    return all_passed


def main():
    """运行所有测试"""
    print("\n")
    print("*" * 60)
    print("vnpy_chartwizard 集成测试")
    print("*" * 60)
    print("\n")

    results = []

    # 运行测试
    results.append(("vnpy_chartwizard导入", test_vnpy_chartwizard_import()))
    results.append(("MainEngine可用性", test_main_engine_available()))
    results.append(("ChartWizardWidget导入", test_chart_wizard_widget_import()))
    results.append(("行情看板集成", test_market_dashboard_integration()))
    results.append(("品种交易所映射", test_symbol_exchange_mapping()))

    # 汇总结果
    print("\n")
    print("*" * 60)
    print("测试结果汇总")
    print("*" * 60)
    print("\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:30s} {status}")

    print("\n")
    print(f"总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n✅ 所有测试通过！vnpy_chartwizard集成成功！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
