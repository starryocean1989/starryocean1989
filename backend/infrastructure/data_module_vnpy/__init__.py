# -*- coding: utf-8 -*-
"""
data_module_vnpy - 中国A股数据管理模块

基于vnpy架构的量化交易数据管理模块，集成mootdx接口获取中国A股数据，
支持品种列表获取、K线数据下载、数据存储、数据感知等功能。

主要功能：
- 品种列表获取：支持上证A股、深证A股、北证A股、T+0基金、含可转债
- K线数据下载：全量下载和增量下载
- 数据存储：Parquet列式压缩格式
- 数据感知：品种缺失、历史缺失、逻辑错误、格式错误检查
- 文件监控：实时监控数据变化并推送结果
"""

from pathlib import Path
from vnpy.trader.app import BaseApp

from .engine import APP_NAME, ChinaStockEngine

__all__ = [
    "APP_NAME",
    "ChinaStockEngine",
    "ChinaStockApp",
]

__version__ = "1.0.0"


class ChinaStockApp(BaseApp):
    """中国A股数据管理应用"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "中国A股数据管理"
    engine_class: type[ChinaStockEngine] = ChinaStockEngine
    widget_name: str = "ChinaStockWidget"
    icon_name: str = str(app_path.joinpath("ui", "chinastock.ico"))
