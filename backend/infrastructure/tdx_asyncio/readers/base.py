# -*- coding: utf-8 -*-
"""
读取器基类
"""

import logging
from typing import Callable, Dict, List, Optional

import pandas as pd


class BaseReader:
    """数据读取器基类"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def read_single(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """读取单个品种的数据

        Args:
            symbol: 品种代码
            data_type: 数据类型（day/5min/1min）
            market: 市场（sh/sz/bj）

        Returns:
            DataFrame
        """
        raise NotImplementedError

    def process_batch(
        self,
        symbols: List[str],
        data_type: str,
        market: str,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, pd.DataFrame]:
        """批量处理多个品种

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场
            progress_callback: 进度回调函数

        Returns:
            {symbol: DataFrame}
        """
        raise NotImplementedError

