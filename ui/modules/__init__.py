# -*- coding: utf-8 -*-
"""UI功能模块."""

from .system_manager_view import SystemManager
from .data_center_view import DataCenter
from .market_board_view import MarketDashboard
from .strategy_center_view import StrategyCenter
from .trading_gateway_view import TradingGateway
from .portfolio_view import PortfolioInvestment

__all__ = [
    "SystemManager",
    "DataCenter",
    "MarketDashboard",
    "StrategyCenter",
    "TradingGateway",
    "PortfolioInvestment",
]

