# -*- coding: utf-8 -*-
"""
数据获取模块 - 极限合并版

本模块已完成极限合并：将原3个独立文件合并为1个统一文件data_acquisition.py

包含远程数据源相关的功能：
- 品种列表获取和管理
- 增量K线下载
- 实时数据源（已迁移到unified_data_manager.py）
- 服务器池管理
- 自适应下载配置
- K线下载任务详细日志记录

合并说明：
- 合并前：3个文件（task_logger.py, symbol_management.py, data_fetcher.py）
- 合并后：1个文件（data_acquisition.py）
- API兼容性：100%向后兼容
"""

from .data_acquisition import (
    # 任务日志记录器
    TaskDetailLogger,
    get_task_logger,
    close_task_logger,
    # 品种管理
    BlockParser,
    SymbolLoader,
    # 数据获取
    MultiProcessStockFetcher,
    KlineDownloadTask,
    IPODownloadTask,
    download_ipo_dates,
)

# 向后兼容：PollingGateway 和 VirtualGateway 已迁移到 unified_data_manager.py
# 从新位置重新导出以保持兼容性
from ..local_data.unified_data_manager import (
    TdxDataSource as PollingGateway,
    VirtualDataSource as VirtualGateway,
)

__all__ = [
    # 任务日志
    "TaskDetailLogger",
    "get_task_logger",
    "close_task_logger",
    # 品种管理
    "BlockParser",
    "SymbolLoader",
    # 数据获取
    "MultiProcessStockFetcher",
    "KlineDownloadTask",
    "IPODownloadTask",
    "download_ipo_dates",
    # 向后兼容
    "PollingGateway",
    "VirtualGateway",
]
