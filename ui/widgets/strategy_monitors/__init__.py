# -*- coding: utf-8 -*-
"""
策略监控组件包.

为不同类型的策略提供定制化监控界面：
- AlgoMonitor: 算法交易监控
- OptionMonitor: 期权策略监控
- PortfolioMonitor: 组合策略监控
- DefaultMonitor: 默认监控（CTA、ScriptTrader、SpreadTrading）
"""

from .algo_monitor import AlgoMonitorWidget
from .option_monitor import OptionMonitorWidget
from .portfolio_monitor import PortfolioMonitorWidget

__all__ = [
    "AlgoMonitorWidget",
    "OptionMonitorWidget",
    "PortfolioMonitorWidget",
]
