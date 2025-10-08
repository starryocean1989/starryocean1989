# -*- coding: utf-8 -*-
"""
mootdx数据获取封装模块

负责通过mootdx接口获取中国A股数据，包括：
- 品种列表获取：调用stock_all()获取所有品种
- 市场分类：上证A股、深证A股、北证A股、T+0基金、含可转债
- K线数据下载：全量下载和增量下载
- 数据缓存：将获取的数据缓存到本地
"""

from __future__ import annotations

import logging
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path  # noqa: TC003
from typing import Dict, List, Optional, Union

import pandas as pd

from mootdx.quotes import Quotes

from .block_parser import BlockParser
from .config import config_manager


# 自定义超时异常（避免与内置TimeoutError冲突，但在Python 3.3+中TimeoutError已经是内置的）
class NetworkTimeoutError(Exception):
    """网络超时异常"""

    def __init__(self, message="操作超时"):
        self.message = message
        super().__init__(self.message)


def timeout_handler(signum, frame):  # noqa: ARG001
    """超时处理器"""
    raise NetworkTimeoutError("操作超时")


class timeout_context:  # noqa: D101
    """超时上下文管理器（仅用于Unix系统，Windows使用其他方式）"""

    def __init__(self, seconds):
        """初始化超时上下文"""
        self.seconds = seconds

    def __enter__(self):
        """进入上下文"""
        # Windows不支持signal.alarm，跳过
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.seconds)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):  # noqa: ARG002
        """退出上下文"""
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)


class StockFetcher:
    """股票数据获取器"""

    # 市场分类常量（类级别）
    MARKET_SHANGHAI = 0  # 上证
    MARKET_SHENZHEN = 1  # 深证

    # 品种代码前缀（类级别）
    SH_PREFIXES = ["688", "60"]  # 上证A股
    SZ_PREFIXES = ["000", "001", "002", "300", "301"]  # 深证A股
    BJ_PREFIXES = ["43", "83", "87", "88"]  # 北证A股（北交所）

    def __init__(self, block_parser=None):
        """
        初始化数据获取器

        Args:
            block_parser: BlockParser实例，如果为None则创建新实例
        """
        # 配置超时参数（注意：mootdx 的 factory 方法不直接支持 timeout 参数）
        # 我们需要在调用时通过其他方式控制超时
        self.quotes = Quotes.factory()
        self.block_parser = block_parser or BlockParser(config_manager.get_tdx_dir())
        self.logger = logging.getLogger(__name__)

        # 超时配置
        self.network_timeout = 10  # 网络请求超时时间（秒）

    def fetch_all_stocks(self) -> pd.DataFrame:
        """
        获取所有品种列表（带超时和重试机制）

        Returns:
            包含所有品种信息的DataFrame

        Raises:
            TimeoutError: 网络请求超时
            ConnectionError: 网络连接错误
            ValueError: 数据格式错误
        """
        max_retries = 1  # 最多重试1次
        retry_delay = 2  # 重试延迟（秒）

        for attempt in range(max_retries + 1):
            try:
                self.logger.info(
                    "开始获取所有品种列表... (尝试 %d/%d)", attempt + 1, max_retries + 1
                )

                # 使用线程池执行，以便能够控制超时
                from concurrent.futures import (
                    ThreadPoolExecutor,
                    TimeoutError as FutureTimeoutError,
                )
                import time

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.quotes.stock_all)  # type: ignore[attr-defined]
                    try:
                        # 等待结果，设置超时
                        stocks_df = future.result(timeout=self.network_timeout)
                    except FutureTimeoutError as exc:
                        self.logger.error("获取品种列表超时 (>%d秒)", self.network_timeout)
                        raise NetworkTimeoutError(
                            f"网络请求超时 (>{self.network_timeout}秒)"
                        ) from exc

                # 验证返回数据
                if (
                    stocks_df is not None
                    and isinstance(stocks_df, pd.DataFrame)
                    and not stocks_df.empty
                ):
                    self.logger.info("成功获取 %s 个品种", len(stocks_df))
                    return stocks_df
                else:
                    self.logger.error("获取品种列表失败: 返回数据为空或类型不正确")
                    raise ValueError("stock_all() 返回的数据无效或为空")

            except (NetworkTimeoutError, TimeoutError):
                # 超时不重试，直接抛出
                raise

            except OSError as e:
                # 网络错误，可以重试
                self.logger.warning(
                    "网络连接错误 (尝试 %d/%d): %s", attempt + 1, max_retries + 1, e
                )
                if attempt < max_retries:
                    self.logger.info("等待 %d 秒后重试...", retry_delay)
                    import time

                    time.sleep(retry_delay)
                else:
                    self.logger.error("获取品种列表失败: 已达到最大重试次数")
                    raise ConnectionError(f"网络连接失败: {e}") from e

            except (ValueError, KeyError, AttributeError, TypeError) as e:
                # 数据解析错误，不重试
                self.logger.error("获取品种列表失败: 数据解析错误 - %s", e)
                raise ValueError(f"数据解析错误: {e}") from e

            except Exception as e:
                # 其他未知错误
                self.logger.error("获取品种列表失败: 未知错误 - %s", e, exc_info=True)
                raise RuntimeError(f"未知错误: {e}") from e

        # 理论上不会到这里
        raise RuntimeError("获取品种列表失败: 未知原因")

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
            "北证A股": [],  # 从API数据中按前缀筛选
            "T+0基金": [],  # 从spblock.dat获取
            "含可转债": [],  # 从spblock.dat获取
        }

        # 检查必需列是否存在
        if "code" not in stocks_df.columns:
            self.logger.error("品种DataFrame缺少'code'列")
            return result

        for _, row in stocks_df.iterrows():
            code = str(row["code"]).zfill(6)  # 补齐6位

            # 如果market列存在，使用market字段
            if "market" in stocks_df.columns:
                market = row["market"]

                # 上证A股：market=0, 代码以688或60开头
                if market == self.MARKET_SHANGHAI and any(
                    code.startswith(prefix) for prefix in self.SH_PREFIXES
                ):
                    result["上证A股"].append(code)

                # 深证A股：market=1, 代码以000/001/002/300/301开头
                elif market == self.MARKET_SHENZHEN and any(
                    code.startswith(prefix) for prefix in self.SZ_PREFIXES
                ):
                    result["深证A股"].append(code)
            else:
                # 如果market列不存在，根据代码前缀推断
                if any(code.startswith(prefix) for prefix in self.SH_PREFIXES):
                    result["上证A股"].append(code)
                elif any(code.startswith(prefix) for prefix in self.SZ_PREFIXES):
                    result["深证A股"].append(code)
                elif any(code.startswith(prefix) for prefix in self.BJ_PREFIXES):
                    result["北证A股"].append(code)

        # 从通达信板块文件获取特殊品种
        # spblock.dat中的7位代码格式：第1位是市场代码，后6位是股票代码
        # 29xxxxx表示北证A股（市场代码2，股票代码9xxxxx）
        if self.block_parser.is_available():
            try:
                beijing_stocks_from_spblock = self.block_parser.get_beijing_stocks()

                # 优先使用spblock.dat的北证A股数据（更准确）
                if beijing_stocks_from_spblock:
                    result["北证A股"] = beijing_stocks_from_spblock
                    self.logger.info(
                        "从spblock.dat的融资融券板块获取北证A股: %d 个",
                        len(beijing_stocks_from_spblock),
                    )
                # 否则使用API数据按前缀筛选的北证A股作为备份

                result["T+0基金"] = self.block_parser.get_t0_funds()
                result["含可转债"] = self.block_parser.get_convertible_bonds()

                self.logger.info(
                    "从spblock.dat获取特殊品种: 北证A股 %d 个, T+0基金 %d 个, 含可转债 %d 个",
                    len(result["北证A股"]),
                    len(result["T+0基金"]),
                    len(result["含可转债"]),
                )
            except Exception as e:
                self.logger.warning("解析通达信板块文件失败: %s，将仅使用API筛选的品种", e)

        return result

    def cache_stock_list(self, stocks_df: pd.DataFrame) -> "Path":
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
            stocks_df["cache_time"] = datetime.now()
            stocks_df.to_parquet(cache_file, index=False)
            self.logger.info("品种列表已缓存到: %s", cache_file)
            return cache_file
        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            self.logger.error("缓存品种列表失败: %s", e)
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
                self.logger.info("成功加载缓存的品种列表: %s 个品种", len(df))
                return df
            except (OSError, ValueError, KeyError) as e:
                self.logger.error("加载缓存品种列表失败: %s", e)

        return None

    def download_full_kline(
        self, symbols: List[str], intervals: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        全量下载K线数据

        Args:
            symbols: 品种代码列表
            intervals: K线周期列表，默认['1d', '5m', '1m']

        Returns:
            下载结果字典
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        result = {}
        max_workers = config_manager.get_max_workers()

        self.logger.info("开始全量下载K线数据: %s 个品种, %s 周期", len(symbols), intervals)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_symbol = {}

            for symbol in symbols:
                for interval in intervals:
                    future = executor.submit(self._download_single_kline, symbol, interval)
                    future_to_symbol[future] = (symbol, interval)

            # 收集结果
            for future in as_completed(future_to_symbol):
                symbol, interval = future_to_symbol[future]
                try:
                    data = future.result()
                    if data is not None and not data.empty:
                        key = f"{symbol}_{interval}"
                        result[key] = data
                        self.logger.info("成功下载 %s %s 数据: %s 条", symbol, interval, len(data))
                except (OSError, ValueError, KeyError) as e:
                    self.logger.error("下载 %s %s 失败: %s", symbol, interval, e)

        self.logger.info("全量下载完成: %s 个数据集", len(result))
        return result

    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date: Union[str, date],
        intervals: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
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
            intervals = ["1d", "5m", "1m"]

        result = {}
        max_workers = config_manager.get_max_workers()

        self.logger.info("开始增量下载K线数据: %s 个品种, 从 %s 开始", len(symbols), start_date)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {}

            for symbol in symbols:
                for interval in intervals:
                    future = executor.submit(
                        self._download_single_kline_incremental,
                        symbol,
                        interval,
                        start_date,
                    )
                    future_to_symbol[future] = (symbol, interval)

            for future in as_completed(future_to_symbol):
                symbol, interval = future_to_symbol[future]
                try:
                    data = future.result()
                    if data is not None and not data.empty:
                        key = f"{symbol}_{interval}"
                        result[key] = data
                        self.logger.info(
                            "成功下载 %s %s 增量数据: %s 条",
                            symbol,
                            interval,
                            len(data),
                        )
                except (OSError, ValueError, KeyError) as e:
                    self.logger.error("下载 %s %s 增量数据失败: %s", symbol, interval, e)

        self.logger.info("增量下载完成: %s 个数据集", len(result))
        return result

    def _download_single_kline(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """
        下载单个品种的K线数据

        Args:
            symbol: 品种代码
            interval: K线周期

        Returns:
            K线数据DataFrame
        """
        try:
            # 转换周期格式
            frequency_map = {
                "1d": 9,  # 日线
                "5m": 5,  # 5分钟
                "1m": 8,  # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 设置下载数量
            offset_map = {
                "1d": 8000,  # 日线8000根
                "5m": 20000,  # 5分钟20000根
                "1m": 20000,  # 1分钟20000根
            }

            offset = offset_map.get(interval, 8000)

            # 调用mootdx接口
            data = self.quotes.bars(
                symbol=symbol,
                frequency=frequency,  # type: ignore[arg-type]
                start=0,
                offset=offset,
            )

            if data is not None and not data.empty:
                # 标准化列名
                data = self._standardize_columns(data, symbol, interval)
                return data

        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            self.logger.error("下载 %s %s 失败: %s", symbol, interval, e)

        return None

    def _download_single_kline_incremental(
        self, symbol: str, interval: str, start_date: Union[str, date]
    ) -> Optional[pd.DataFrame]:
        """
        下载单个品种的增量K线数据

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期

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
                "1d": 9,  # 日线
                "5m": 5,  # 5分钟
                "1m": 8,  # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 根据周期设置下载数量
            if interval == "1d":
                offset = min(days_diff, 8000)
            else:
                # 分钟线按天数估算
                offset = min(days_diff * 240, 20000)  # 假设每天240个分钟

            # 调用mootdx接口
            data = self.quotes.bars(
                symbol=symbol,
                frequency=frequency,  # type: ignore[arg-type]
                start=0,
                offset=offset,
            )

            if data is not None and not data.empty:
                # 过滤开始日期之后的数据
                data = self._filter_by_date(data, start_date)
                data = self._standardize_columns(data, symbol, interval)
                return data

        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            self.logger.error("下载 %s %s 增量数据失败: %s", symbol, interval, e)

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
        # 重命名列（如果必要）
        column_mapping = {
            "date": "datetime",
            "time": "datetime",
            "open_price": "open",
            "high_price": "high",
            "low_price": "low",
            "close_price": "close",
            "vol": "volume",
            "amount": "turnover",
        }

        data = data.rename(columns=column_mapping)

        # 添加品种和周期信息
        data["symbol"] = symbol
        data["interval"] = interval

        # 确保datetime列是datetime类型
        if "datetime" in data.columns:
            data["datetime"] = pd.to_datetime(data["datetime"])

        # 确保数值列是float类型
        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

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
        if "datetime" in data.columns:
            data["date"] = pd.to_datetime(data["datetime"]).dt.date
            filtered_data = data[data["date"] >= start_date].copy()
            if isinstance(filtered_data, pd.DataFrame):
                filtered_data = filtered_data.drop("date", axis=1)
                return filtered_data

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
