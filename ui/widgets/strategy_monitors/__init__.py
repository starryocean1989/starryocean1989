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

# VnPy核心监控组件
from .order_monitor import OrderMonitor
from .trade_monitor import TradeMonitor
from .position_monitor import PositionMonitor
from .account_monitor import AccountMonitor

__all__ = [
    "AlgoMonitorWidget",
    "OptionMonitorWidget",
    "PortfolioMonitorWidget",
    # VnPy核心监控组件
    "OrderMonitor",
    "TradeMonitor",
    "PositionMonitor",
    "AccountMonitor",
]
