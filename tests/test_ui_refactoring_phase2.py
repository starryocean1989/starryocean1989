# -*- coding: utf-8 -*-
"""测试UI重构阶段2 - 系统状态监控Tab."""
import sys
from PySide6.QtWidgets import QApplication

# 测试导入新组件
try:
    from ui.components.dashboard_components import (
        CompactTable,
        GaugeWidget,
        MetricCard,
        MiniSparkline,
        StatusIndicator,
    )
    from ui.components.theme_system import DashboardTheme

    print("✅ 所有新组件导入成功")
except Exception as e:
    print(f"❌ 组件导入失败: {e}")
    sys.exit(1)

# 测试主题配置
try:
    # 测试颜色属性访问
    assert hasattr(DashboardTheme, "cpu")
    assert hasattr(DashboardTheme, "memory")
    assert hasattr(DashboardTheme, "border_light")

    # 测试方法
    assert callable(DashboardTheme.get_title_style)
    assert callable(DashboardTheme.get_subtitle_style)
    assert callable(DashboardTheme.get_body_style)
    assert callable(DashboardTheme.get_checkbox_style)
    assert callable(DashboardTheme.get_metric_value_style)

    # 测试方法调用
    title_style = DashboardTheme.get_title_style()
    assert "font-size" in title_style

    metric_style = DashboardTheme.get_metric_value_style(size=18)
    assert "18px" in metric_style

    print("✅ DashboardTheme 所有方法正常")
except AssertionError as e:
    print(f"❌ DashboardTheme 测试失败: {e}")
    sys.exit(1)

# 测试组件实例化
try:
    app = QApplication.instance() or QApplication(sys.argv)

    # 测试MetricCard
    card = MetricCard(title="CPU使用率", unit="%", color=DashboardTheme.cpu)
    card.update_value(85.5)  # 测试数值输入
    print("✅ MetricCard 创建和更新成功")

    # 测试GaugeWidget
    gauge = GaugeWidget(max_value=100, warning=70, critical=85)
    gauge.set_value(68)
    print("✅ GaugeWidget 创建和设置值成功")

    # 测试StatusIndicator
    indicator = StatusIndicator(status="normal", text="正常")
    print("✅ StatusIndicator 创建成功")

    # 测试CompactTable
    table = CompactTable(rows=5, columns=3, row_height=26)
    print("✅ CompactTable 创建成功")

    print("\n" + "=" * 60)
    print("UI重构阶段2 - 组件测试全部通过 ✅")
    print("=" * 60)

except Exception as e:
    print(f"❌ 组件实例化失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
