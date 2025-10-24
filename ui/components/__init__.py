# -*- coding: utf-8 -*-
"""UI组件库 - 统一的共享组件和主题系统.

本模块整合了原 shared_widgets 和 themes 文件夹的所有内容：
- 基础组件
- 图表组件
- Dashboard组件
- 监控组件
- Monaco编辑器
- 主题系统
"""

# 主题系统
from .theme_system import DashboardTheme, ThemeManager

# 基础组件和Dashboard组件（从widgets.py导入）
from .widgets import (
    # 枚举类
    ErrorCategory,
    ErrorSeverity,
    # 基础组件
    BaseWidget,
    MonacoEditorWidget,
    # Dashboard组件
    MetricCard,
    MiniSparkline,
    GaugeWidget,
    StatusIndicator,
    CompactTable,
)

# 图表组件
from .charts import (
    ChartWidget,
    ChartToolbar,
    SubplotIndicatorManager,
    IndicatorPlotWidget,
)

# 基础监控器
from .basic_monitors import (
    OrderMonitor,
    TradeMonitor,
    PositionMonitor,
    AccountMonitor,
)

__all__ = [
    # 主题系统
    "DashboardTheme",
    "ThemeManager",
    # 枚举类
    "ErrorCategory",
    "ErrorSeverity",
    # 基础组件
    "BaseWidget",
    "MonacoEditorWidget",
    # 图表组件
    "ChartWidget",
    "ChartToolbar",
    "SubplotIndicatorManager",
    "IndicatorPlotWidget",
    # 基础监控器
    "OrderMonitor",
    "TradeMonitor",
    "PositionMonitor",
    "AccountMonitor",
    # Dashboard组件
    "MetricCard",
    "MiniSparkline",
    "GaugeWidget",
    "StatusIndicator",
    "CompactTable",
]
