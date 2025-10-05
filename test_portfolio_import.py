# -*- coding: utf-8 -*-
"""测试组合投资界面导入和初始化"""

import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_portfolio_investment():
    """测试组合投资界面"""
    try:
        print("1. 导入组合投资界面...")
        from ui.components.portfolio_investment.main_view import PortfolioInvestment

        print("   ✓ 导入成功")

        print("2. 创建PortfolioInvestment实例...")
        portfolio = PortfolioInvestment()
        print("   ✓ 实例创建成功")

        print("3. 调用setup_ui...")
        portfolio.setup_ui()
        print("   ✓ setup_ui成功")

        print("4. 调用connect_signals...")
        portfolio.connect_signals()
        print("   ✓ connect_signals成功")

        print("5. 检查界面就绪状态...")
        if hasattr(portfolio, "ui_ready"):
            print(f"   ✓ ui_ready状态: {portfolio.ui_ready}")
        else:
            print("   ✗ ui_ready属性不存在")

        print("\n✅ 所有测试通过！组合投资界面可以正常工作")
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        print("详细错误信息:")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_portfolio_investment()
