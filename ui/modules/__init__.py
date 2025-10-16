# -*- coding: utf-8 -*-
"""UI功能模块."""

from .system_manager.view import SystemManager
from .data_center.view import DataCenter
from .market_board.view import MarketDashboard
from .strategy_center.view import StrategyCenter
from .trading_gateway.view import TradingGateway
from .portfolio.view import PortfolioInvestment

__all__ = [
    "SystemManager",
    "DataCenter",
    "MarketDashboard",
    "StrategyCenter",
    "TradingGateway",
    "PortfolioInvestment",
]

