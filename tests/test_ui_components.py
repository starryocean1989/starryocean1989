# -*- coding: utf-8 -*-
"""测试UI组件库 - 验证基础组件功能."""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from ui.components.dashboard_components import (
    MetricCard,
    MiniSparkline,
    GaugeWidget,
    StatusIndicator,
    CompactTable,
)
from ui.components.theme_system import DashboardTheme


def test_theme_module():
    """测试主题模块."""
    print("Testing DashboardTheme...")

    # 测试色板
    assert len(DashboardTheme.COLORS) > 0, "色板不能为空"
    assert "bg_primary" in DashboardTheme.COLORS, "缺少主背景色"
    assert "primary" in DashboardTheme.COLORS, "缺少主题色"
    print(f"✅ 色板包含 {len(DashboardTheme.COLORS)} 种颜色")

    # 测试字体规格
    assert len(DashboardTheme.FONTS) > 0, "字体规格不能为空"
    assert "title" in DashboardTheme.FONTS, "缺少标题字体"
    print(f"✅ 字体规格包含 {len(DashboardTheme.FONTS)} 种定义")

    # 测试样式生成器
    card_style = DashboardTheme.get_card_style()
    assert isinstance(card_style, str) and len(card_style) > 0, "卡片样式生成失败"
    print("✅ 卡片样式生成正常")

    table_style = DashboardTheme.get_compact_table_style()
    assert isinstance(table_style, str) and len(table_style) > 0, "表格样式生成失败"
    print("✅ 表格样式生成正常")

    # 测试颜色获取
    status_color = DashboardTheme.get_status_color("success")
    assert status_color == DashboardTheme.COLORS["success"], "状态颜色映射错误"
    print("✅ 状态颜色映射正常")

    metric_color = DashboardTheme.get_metric_color("cpu")
    assert metric_color == DashboardTheme.COLORS["cpu"], "指标颜色映射错误"
    print("✅ 指标颜色映射正常")

    print("✅ DashboardTheme 所有测试通过\n")


def test_components(app):
    """测试UI组件."""
    print("Testing Dashboard Components...")

    # 创建测试窗口
    window = QWidget()
    window.setWindowTitle("Dashboard Components Test")
    window.setMinimumSize(800, 600)

    layout = QVBoxLayout(window)

    # 测试MetricCard
    print("Testing MetricCard...")
    metric_card_layout = QHBoxLayout()

    cpu_card = MetricCard(
        title="CPU使用率",
        value="85",
        unit="%",
        icon="🔥",
        color=DashboardTheme.get_metric_color("cpu"),
        show_sparkline=True,
    )
    metric_card_layout.addWidget(cpu_card)
    print("✅ MetricCard 创建成功")

    # 测试更新
    cpu_card.update_value("87", 87.0)
    print("✅ MetricCard 更新成功")

    memory_card = MetricCard(
        title="内存使用率",
        value="72",
        unit="%",
        icon="💾",
        color=DashboardTheme.get_metric_color("memory"),
        show_sparkline=True,
    )
    metric_card_layout.addWidget(memory_card)

    layout.addLayout(metric_card_layout)

    # 测试GaugeWidget
    print("Testing GaugeWidget...")
    gauge_layout = QHBoxLayout()
    gauge_layout.addWidget(QLabel("压力评分:"))

    gauge = GaugeWidget(max_value=100, thresholds={"warning": 60, "critical": 80})
    gauge.set_value(68)
    gauge_layout.addWidget(gauge)
    print("✅ GaugeWidget 创建和设置值成功")

    layout.addLayout(gauge_layout)

    # 测试StatusIndicator
    print("Testing StatusIndicator...")
    status_layout = QHBoxLayout()

    status_success = StatusIndicator(status="success", text="服务正常")
    status_layout.addWidget(status_success)

    status_warning = StatusIndicator(status="warning", text="CPU使用率高")
    status_layout.addWidget(status_warning)

    status_error = StatusIndicator(status="error", text="磁盘空间不足")
    status_layout.addWidget(status_error)

    layout.addLayout(status_layout)
    print("✅ StatusIndicator 创建成功")

    # 测试CompactTable
    print("Testing CompactTable...")
    table = CompactTable(rows=5, columns=4, row_height=26)
    table.setHorizontalHeaderLabels(["指标", "当前值", "平均值", "状态"])

    # 填充示例数据
    from PySide6.QtWidgets import QTableWidgetItem

    metrics_data = [
        ("CPU使用率", 85, 75, "warning"),
        ("内存使用率", 72, 68, "normal"),
        ("磁盘I/O", 95, 80, "critical"),
        ("网络速度", 45, 50, "normal"),
        ("温度", 65, 60, "normal"),
    ]

    for row, (name, current, avg, status) in enumerate(metrics_data):
        table.setItem(row, 0, QTableWidgetItem(name))
        table.setItem(row, 1, QTableWidgetItem(f"{current}%"))
        table.setItem(row, 2, QTableWidgetItem(f"{avg}%"))
        table.setItem(row, 3, QTableWidgetItem(status))

        # 测试自动颜色
        table.auto_color_by_threshold(
            row=row, col=1, value=current, thresholds={"warning": 70, "critical": 90}
        )

    layout.addWidget(table)
    print("✅ CompactTable 创建和填充成功")

    # 显示测试窗口
    window.show()
    print("✅ 所有组件测试通过\n")
    print("测试窗口已打开，请验证以下内容：")
    print("1. 两个MetricCard卡片显示正常（CPU和内存）")
    print("2. GaugeWidget半圆仪表盘显示68分")
    print("3. 三个StatusIndicator状态指示器（绿/黄/红）")
    print("4. CompactTable表格有5行数据，部分行标红")
    print("\n按Ctrl+C或关闭窗口退出...")

    return window


if __name__ == "__main__":
    print("=" * 60)
    print("Dashboard Components 单元测试")
    print("=" * 60 + "\n")

    # 测试主题模块
    test_theme_module()

    # 创建QApplication
    app = QApplication(sys.argv)

    # 测试UI组件
    window = test_components(app)

    # 运行应用
    sys.exit(app.exec())
