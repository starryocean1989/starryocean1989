# -*- coding: utf-8 -*-
"""
Backend功能模块.

按6个功能界面组织的业务服务模块。
"""

from .system_manager.service import SystemManagerService
from .data_center.service import DataCenterService
from .market_board.service import MarketBoardService
from .strategy_center.service import StrategyCenterService
from .trading_gateway.service import TradingGatewayService
from .portfolio.service import PortfolioService

__all__ = [
    "SystemManagerService",
    "DataCenterService",
    "MarketBoardService",
    "StrategyCenterService",
    "TradingGatewayService",
    "PortfolioService",
]

