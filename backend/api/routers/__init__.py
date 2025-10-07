# -*- coding: utf-8 -*-
"""
API路由包.

包含所有功能模块的API路由定义。
"""

from . import (
    data_center,
    market_board,
    portfolio,
    strategy_center,
    system_manager,
    trading_gateway,
)

# 导出所有路由模块
__all__ = [
    "data_center",
    "market_board",
    "portfolio",
    "strategy_center",
    "system_manager",
    "trading_gateway",
]
