# -*- coding: utf-8 -*-
"""测试功能界面初始化."""

import os
import sys
from pathlib import Path

# 设置项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置环境变量
if not os.environ.get("PYTHONEXECUTABLE"):
    os.environ["PYTHONEXECUTABLE"] = sys.executable
if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
    os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")


def test_interfaces():
    """测试所有功能界面是否能成功初始化."""
    print("=" * 70)
    print("测试功能界面初始化")
    print("=" * 70)

    # 初始化Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 初始化配置
    from backend.config import init_settings

    init_settings(os.environ["CONFIG_FILE"])

    # 初始化后端服务
    from backend.core.base import initialize_services

    print("\n步骤1: 初始化后端服务...")
    result = initialize_services()
    if result.get("success"):
        print("✅ 后端服务初始化成功")
    else:
        print(f"❌ 后端服务初始化失败: {result.get('message')}")
        return False

    # 测试各个界面
    interfaces = [
        ("SystemManager", "ui.components.system_manager.main_view"),
        ("DataCenter", "ui.components.data_center.main_view"),
        ("MarketDashboard", "ui.components.market_dashboard.main_view"),
        ("StrategyCenter", "ui.components.strategy_center.main_view"),
        ("TradingGateway", "ui.components.trading_gateway.main_view"),
        ("PortfolioInvestment", "ui.components.portfolio_investment.main_view"),
    ]

    print("\n步骤2: 测试界面初始化...")
    print("-" * 70)

    success_count = 0
    for idx, (class_name, module_name) in enumerate(interfaces, 1):
        try:
            print(f"\n[{idx}/6] 测试 {class_name}...")

            # 动态导入模块
            module = __import__(module_name, fromlist=[class_name])
            interface_class = getattr(module, class_name)

            # 创建实例
            interface = interface_class()
            print(f"    ✅ {class_name} 初始化成功")

            # 验证基本属性
            if hasattr(interface, "logger"):
                print(f"    ✅ logger 属性存在")
            if hasattr(interface, "title"):
                print(f"    ✅ title = '{interface.title}'")

            success_count += 1

            # 清理
            interface.deleteLater()

        except Exception as e:
            print(f"    ❌ {class_name} 初始化失败")
            print(f"    错误: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"测试结果: {success_count}/6 个界面初始化成功")
    print("=" * 70)

    return success_count == 6


if __name__ == "__main__":
    try:
        success = test_interfaces()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试过程发生异常: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
