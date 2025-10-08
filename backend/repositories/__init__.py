# -*- coding: utf-8 -*-
"""
数据访问层包.

提供数据库操作和持久化功能。
"""

# 导入所有仓库类
from .base_repository import BaseRepository, InMemoryRepository
from .data_repositories import (
    SymbolRepository,
    DataSourceRepository,
    DownloadTaskRepository,
)
from .trading_repositories import (
    GatewayRepository,
    StrategyRepository,
    BacktestRepository,
)
from .system_repositories import (
    AlertRepository,
    LogRepository,
    ConfigRepository,
    PortfolioRepository,
)

# 导出所有仓库类
__all__ = [
    "BaseRepository",
    "InMemoryRepository",
    "SymbolRepository",
    "DataSourceRepository",
    "DownloadTaskRepository",
    "GatewayRepository",
    "StrategyRepository",
    "BacktestRepository",
    "AlertRepository",
    "LogRepository",
    "ConfigRepository",
    "PortfolioRepository",
]
