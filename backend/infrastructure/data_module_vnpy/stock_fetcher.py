# -*- coding: utf-8 -*-
"""
mootdx数据获取封装模块

负责通过mootdx接口获取中国A股数据，包括：
- 品种列表获取：调用stock_all()获取所有品种
- 市场分类：上证A股、深证A股、北证A股、T+0基金、含可转债
- K线数据下载：全量下载和增量下载
- 数据缓存：将获取的数据缓存到本地
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

from mootdx.quotes import Quotes
from mootdx.consts import MARKET_SH, MARKET_SZ

from .config import config_manager
from .block_parser import BlockParser


class StockFetcher:
    """股票数据获取器"""

    def __init__(self):
        """初始化数据获取器"""
        self.quotes = Quotes.factory()
        self.block_parser = BlockParser(config_manager.get_tdx_dir())
        self.logger = logging.getLogger(__name__)

        # 市场分类常量
        self.MARKET_SHANGHAI = 0  # 上证
        self.MARKET_SHENZHEN = 1  # 深证

        # 品种代码前缀
        self.SH_PREFIXES = ['688', '60']  # 上证A股
        self.SZ_PREFIXES = ['000', '001', '002', '300', '301']  # 深证A股

    def fetch_all_stocks(self) -> pd.DataFrame:
        """
        获取所有品种列表

        Returns:
            包含所有品种信息的DataFrame
        """
        try:
            self.logger.info("开始获取所有品种列表...")
            stocks_df = self.quotes.stock_all()
            self.logger.info(f"成功获取 {len(stocks_df)} 个品种")
            return stocks_df
        except Exception as e:
            self.logger.error(f"获取品种列表失败: {e}")
            raise

    def parse_market_codes(self, stocks_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        解析市场代码，分类品种

        Args:
            stocks_df: 品种列表DataFrame

        Returns:
            分类后的品种代码字典
        """
        result = {
            "上证A股": [],
            "深证A股": [],
            "北证A股": [],
            "T+0基金": [],
            "含可转债": []
        }

        for _, row in stocks_df.iterrows():
            code = str(row['code']).zfill(6)  # 补齐6位
            market = row['market']

            # 上证A股：market=0, 代码以688或60开头
            if market == self.MARKET_SHANGHAI:
                if any(code.startswith(prefix) for prefix in self.SH_PREFIXES):
                    result["上证A股"].append(code)

            # 深证A股：market=1, 代码以000/001/002/300/301开头
            elif market == self.MARKET_SHENZHEN:
                if any(code.startswith(prefix) for prefix in self.SZ_PREFIXES):
                    result["深证A股"].append(code)

        # 从通达信板块文件获取特殊品种
        if self.block_parser.is_available():
            try:
                result["北证A股"] = self.block_parser.get_beijing_stocks()
                result["T+0基金"] = self.block_parser.get_t0_funds()
                result["含可转债"] = self.block_parser.get_convertible_bonds()
            except Exception as e:
                self.logger.warning(f"解析通达信板块文件失败: {e}")

        return result

    def cache_stock_list(self, stocks_df: pd.DataFrame) -> Path:
        """
        缓存品种列表到本地

        Args:
            stocks_df: 品种列表DataFrame

        Returns:
            缓存文件路径
        """
        cache_dir = config_manager.get_cache_dir()
        cache_file = cache_dir / "stock_list.parquet"

        try:
            # 添加缓存时间戳
            stocks_df['cache_time'] = datetime.now()
            stocks_df.to_parquet(cache_file, index=False)
            self.logger.info(f"品种列表已缓存到: {cache_file}")
            return cache_file
        except Exception as e:
            self.logger.error(f"缓存品种列表失败: {e}")
            raise

    def load_cached_stock_list(self) -> Optional[pd.DataFrame]:
        """
        加载缓存的品种列表

        Returns:
            缓存的品种列表DataFrame，如果不存在则返回None
        """
        cache_dir = config_manager.get_cache_dir()
        cache_file = cache_dir / "stock_list.parquet"

        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                self.logger.info(f"成功加载缓存的品种列表: {len(df)} 个品种")
                return df
            except Exception as e:
                self.logger.error(f"加载缓存品种列表失败: {e}")

        return None

    def download_full_kline(self, symbols: List[str], intervals: List[str] = None) -> Dict[str, pd.DataFrame]:
        """
        全量下载K线数据

        Args:
            symbols: 品种代码列表
            intervals: K线周期列表，默认['1d', '5m', '1m']

        Returns:
            下载结果字典
        """
        if intervals is None:
            intervals = ['1d', '5m', '1m']

        result = {}
        max_workers = config_manager.get_max_workers()
        timeout = config_manager.get_timeout()

        self.logger.info(f"开始全量下载K线数据: {len(symbols)} 个品种, {intervals} 周期")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_symbol = {}

            for symbol in symbols:
                for interval in intervals:
                    future = executor.submit(
                        self._download_single_kline,
                        symbol, interval, timeout
                    )
                    future_to_symbol[future] = (symbol, interval)

            # 收集结果
            for future in as_completed(future_to_symbol):
                symbol, interval = future_to_symbol[future]
                try:
                    data = future.result()
                    if data is not None and not data.empty:
                        key = f"{symbol}_{interval}"
                        result[key] = data
                        self.logger.info(f"成功下载 {symbol} {interval} 数据: {len(data)} 条")
                except Exception as e:
                    self.logger.error(f"下载 {symbol} {interval} 失败: {e}")

        self.logger.info(f"全量下载完成: {len(result)} 个数据集")
        return result

    def download_incremental_kline(self, symbols: List[str], start_date: Union[str, date],
                                 intervals: List[str] = None) -> Dict[str, pd.DataFrame]:
        """
        增量下载K线数据

        Args:
            symbols: 品种代码列表
            start_date: 开始日期
            intervals: K线周期列表

        Returns:
            下载结果字典
        """
        if intervals is None:
            intervals = ['1d', '5m', '1m']

        result = {}
        max_workers = config_manager.get_max_workers()
        timeout = config_manager.get_timeout()

        self.logger.info(f"开始增量下载K线数据: {len(symbols)} 个品种, 从 {start_date} 开始")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {}

            for symbol in symbols:
                for interval in intervals:
                    future = executor.submit(
                        self._download_single_kline_incremental,
                        symbol, interval, start_date, timeout
                    )
                    future_to_symbol[future] = (symbol, interval)

            for future in as_completed(future_to_symbol):
                symbol, interval = future_to_symbol[future]
                try:
                    data = future.result()
                    if data is not None and not data.empty:
                        key = f"{symbol}_{interval}"
                        result[key] = data
                        self.logger.info(f"成功下载 {symbol} {interval} 增量数据: {len(data)} 条")
                except Exception as e:
                    self.logger.error(f"下载 {symbol} {interval} 增量数据失败: {e}")

        self.logger.info(f"增量下载完成: {len(result)} 个数据集")
        return result

    def _download_single_kline(self, symbol: str, interval: str, timeout: int) -> Optional[pd.DataFrame]:
        """
        下载单个品种的K线数据

        Args:
            symbol: 品种代码
            interval: K线周期
            timeout: 超时时间

        Returns:
            K线数据DataFrame
        """
        try:
            # 转换周期格式
            frequency_map = {
                '1d': 9,    # 日线
                '5m': 5,    # 5分钟
                '1m': 8,    # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 设置下载数量
            offset_map = {
                '1d': 8000,    # 日线8000根
                '5m': 20000,   # 5分钟20000根
                '1m': 20000,   # 1分钟20000根
            }

            offset = offset_map.get(interval, 8000)

            # 调用mootdx接口
            data = self.quotes.bars(
                symbol=symbol,
                frequency=frequency,
                start=0,
                offset=offset
            )

            if data is not None and not data.empty:
                # 标准化列名
                data = self._standardize_columns(data, symbol, interval)
                return data

        except Exception as e:
            self.logger.error(f"下载 {symbol} {interval} 失败: {e}")

        return None

    def _download_single_kline_incremental(self, symbol: str, interval: str,
                                         start_date: Union[str, date], timeout: int) -> Optional[pd.DataFrame]:
        """
        下载单个品种的增量K线数据

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期
            timeout: 超时时间

        Returns:
            K线数据DataFrame
        """
        try:
            # 转换日期格式
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

            # 计算从开始日期到现在的天数
            days_diff = (date.today() - start_date).days

            # 转换周期格式
            frequency_map = {
                '1d': 9,    # 日线
                '5m': 5,    # 5分钟
                '1m': 8,    # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 根据周期设置下载数量
            if interval == '1d':
                offset = min(days_diff, 8000)
            else:
                # 分钟线按天数估算
                offset = min(days_diff * 240, 20000)  # 假设每天240个分钟

            # 调用mootdx接口
            data = self.quotes.bars(
                symbol=symbol,
                frequency=frequency,
                start=0,
                offset=offset
            )

            if data is not None and not data.empty:
                # 过滤开始日期之后的数据
                data = self._filter_by_date(data, start_date)
                data = self._standardize_columns(data, symbol, interval)
                return data

        except Exception as e:
            self.logger.error(f"下载 {symbol} {interval} 增量数据失败: {e}")

        return None

    def _standardize_columns(self, data: pd.DataFrame, symbol: str, interval: str) -> pd.DataFrame:
        """
        标准化DataFrame列名和格式

        Args:
            data: 原始数据
            symbol: 品种代码
            interval: K线周期

        Returns:
            标准化后的DataFrame
        """
        # 确保有必要的列
        required_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']

        # 重命名列（如果必要）
        column_mapping = {
            'date': 'datetime',
            'time': 'datetime',
            'open_price': 'open',
            'high_price': 'high',
            'low_price': 'low',
            'close_price': 'close',
            'vol': 'volume',
            'amount': 'turnover'
        }

        data = data.rename(columns=column_mapping)

        # 添加品种和周期信息
        data['symbol'] = symbol
        data['interval'] = interval

        # 确保datetime列是datetime类型
        if 'datetime' in data.columns:
            data['datetime'] = pd.to_datetime(data['datetime'])

        # 确保数值列是float类型
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')

        return data

    def _filter_by_date(self, data: pd.DataFrame, start_date: date) -> pd.DataFrame:
        """
        按日期过滤数据

        Args:
            data: 原始数据
            start_date: 开始日期

        Returns:
            过滤后的数据
        """
        if 'datetime' in data.columns:
            data['date'] = pd.to_datetime(data['datetime']).dt.date
            data = data[data['date'] >= start_date]
            data = data.drop('date', axis=1)

        return data

    def get_market_stocks(self, market_type: str) -> List[str]:
        """
        获取指定市场的品种列表

        Args:
            market_type: 市场类型（上证A股、深证A股、北证A股、T+0基金、含可转债）

        Returns:
            品种代码列表
        """
        # 先尝试从缓存加载
        cached_df = self.load_cached_stock_list()
        if cached_df is not None:
            classified = self.parse_market_codes(cached_df)
            return classified.get(market_type, [])

        # 如果缓存不存在，重新获取
        stocks_df = self.fetch_all_stocks()
        classified = self.parse_market_codes(stocks_df)
        return classified.get(market_type, [])

    def get_all_market_stocks(self) -> Dict[str, List[str]]:
        """
        获取所有市场的品种分类

        Returns:
            所有市场的品种分类字典
        """
        # 先尝试从缓存加载
        cached_df = self.load_cached_stock_list()
        if cached_df is not None:
            return self.parse_market_codes(cached_df)

        # 如果缓存不存在，重新获取
        stocks_df = self.fetch_all_stocks()
        return self.parse_market_codes(stocks_df)
