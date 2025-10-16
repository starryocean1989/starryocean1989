# -*- coding: utf-8 -*-
"""共享UI组件."""

# 基础组件
from .base_widget import BaseWidget
from .monaco_editor_widget import MonacoEditorWidget
from .symbol_search_widget import SymbolSearchWidget
from .alert_ticker import AlertTicker
from .error_feedback_widget import ErrorFeedbackWidget
from .responsive_helper import ResponsiveHelper

# 图表组件
from .charts import (
    ChartWidget,
    ChartToolbar,
    SubplotIndicatorManager,
    IndicatorPlotWidget,
)
from .chart_wizard_enhanced import ChartWizardEnhanced

# 基础监控器
from .basic_monitors import (
    OrderMonitor,
    TradeMonitor,
    PositionMonitor,
    AccountMonitor,
)

# 组合监控器
from .portfolio_monitors import (
    PortfolioMonitorWidget,
    AlgoMonitorWidget,
    OptionMonitorWidget,
)

__all__ = [
    # 基础组件
    "BaseWidget",
    "MonacoEditorWidget",
    "SymbolSearchWidget",
    "AlertTicker",
    "ErrorFeedbackWidget",
    "ResponsiveHelper",
    # 图表组件
    "ChartWidget",
    "ChartToolbar",
    "SubplotIndicatorManager",
    "IndicatorPlotWidget",
    "ChartWizardEnhanced",
    # 基础监控器
    "OrderMonitor",
    "TradeMonitor",
    "PositionMonitor",
    "AccountMonitor",
    # 组合监控器
    "PortfolioMonitorWidget",
    "AlgoMonitorWidget",
    "OptionMonitorWidget",
]

