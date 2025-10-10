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
import time
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
        self.network_timeout = 30  # 网络请求超时时间（秒），从10秒改为30秒

        # 品种分类缓存：避免重复解析spblock.dat
        self._classified_stocks_cache: Optional[Dict[str, List[str]]] = None

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
                self.logger.info("=" * 60)
                self.logger.info(
                    "【fetch_all_stocks】开始获取所有品种列表... (尝试 %d/%d)",
                    attempt + 1,
                    max_retries + 1,
                )
                self.logger.info("  使用超时时间: %d秒", self.network_timeout)

                # 使用线程池执行，以便能够控制超时
                from concurrent.futures import (
                    ThreadPoolExecutor,
                    TimeoutError as FutureTimeoutError,
                )
                import time

                self.logger.info("  → 准备调用 mootdx quotes.stock_all() API...")

                with ThreadPoolExecutor(max_workers=1) as executor:
                    start_time = time.time()
                    future = executor.submit(self.quotes.stock_all)  # type: ignore[attr-defined]
                    self.logger.info("  → API调用已提交，等待响应...")

                    try:
                        # 等待结果，设置超时
                        stocks_df = future.result(timeout=self.network_timeout)
                        elapsed_time = time.time() - start_time
                        self.logger.info("  ← API调用完成！耗时: %.2f秒", elapsed_time)

                    except FutureTimeoutError as exc:
                        elapsed_time = time.time() - start_time
                        self.logger.error(
                            "获取品种列表超时 (>%d秒，实际等待%.2f秒)",
                            self.network_timeout,
                            elapsed_time,
                        )
                        raise NetworkTimeoutError(
                            f"网络请求超时 (>{self.network_timeout}秒)"
                        ) from exc

                # 验证返回数据
                self.logger.info("  → 验证返回数据...")
                if (
                    stocks_df is not None
                    and isinstance(stocks_df, pd.DataFrame)
                    and not stocks_df.empty
                ):
                    self.logger.info("  ← 数据验证通过！")
                    self.logger.info("✅ 成功获取 %s 个品种", len(stocks_df))
                    self.logger.info("=" * 60)
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
        解析市场代码，分类品种（优化版：使用向量化操作）

        Args:
            stocks_df: 品种列表DataFrame

        Returns:
            分类后的品种代码字典
        """
        self.logger.info("【parse_market_codes】开始解析 %d 个品种...", len(stocks_df))
        start_time = time.time()

        result: Dict[str, List[str]] = {
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

        # 向量化操作：补齐所有代码为6位
        self.logger.info("  → 补齐代码位数...")
        stocks_df = stocks_df.copy()
        stocks_df["code"] = stocks_df["code"].astype(str).str.zfill(6)

        # 向量化操作：根据前缀筛选品种
        if "market" in stocks_df.columns:
            self.logger.info("  → 使用market字段分类...")
            # 上证A股：market=0, 代码以688或60开头
            sh_mask = (stocks_df["market"] == self.MARKET_SHANGHAI) & (
                stocks_df["code"].str.startswith("688") | stocks_df["code"].str.startswith("60")
            )
            result["上证A股"] = stocks_df[sh_mask]["code"].tolist()

            # 深证A股：market=1, 代码以000/001/002/300/301开头
            sz_mask = (stocks_df["market"] == self.MARKET_SHENZHEN) & (
                stocks_df["code"].str.startswith("000")
                | stocks_df["code"].str.startswith("001")
                | stocks_df["code"].str.startswith("002")
                | stocks_df["code"].str.startswith("300")
                | stocks_df["code"].str.startswith("301")
            )
            result["深证A股"] = stocks_df[sz_mask]["code"].tolist()
        else:
            self.logger.info("  → 使用代码前缀分类...")
            # 如果market列不存在，根据代码前缀推断
            sh_mask = stocks_df["code"].str.startswith("688") | stocks_df["code"].str.startswith(
                "60"
            )
            result["上证A股"] = stocks_df[sh_mask]["code"].tolist()

            sz_mask = (
                stocks_df["code"].str.startswith("000")
                | stocks_df["code"].str.startswith("001")
                | stocks_df["code"].str.startswith("002")
                | stocks_df["code"].str.startswith("300")
                | stocks_df["code"].str.startswith("301")
            )
            result["深证A股"] = stocks_df[sz_mask]["code"].tolist()

            bj_mask = (
                stocks_df["code"].str.startswith("82")
                | stocks_df["code"].str.startswith("83")
                | stocks_df["code"].str.startswith("87")
                | stocks_df["code"].str.startswith("43")
            )
            result["北证A股"] = stocks_df[bj_mask]["code"].tolist()

        self.logger.info(
            "  ← API筛选完成: 上证%d个, 深证%d个, 北证%d个",
            len(result["上证A股"]),
            len(result["深证A股"]),
            len(result["北证A股"]),
        )

        # 从通达信板块文件获取特殊品种
        # spblock.dat中的7位代码格式：第1位是市场代码，后6位是股票代码
        # 29xxxxx表示北证A股（市场代码2，股票代码9xxxxx）
        self.logger.info("  → 从spblock.dat获取特殊品种...")
        if self.block_parser.is_available():
            try:
                beijing_stocks_from_spblock = self.block_parser.get_beijing_stocks()

                # 优先使用spblock.dat的北证A股数据（更准确）
                if beijing_stocks_from_spblock:
                    result["北证A股"] = beijing_stocks_from_spblock
                    self.logger.info(
                        "    从spblock.dat的融资融券板块获取北证A股: %d 个",
                        len(beijing_stocks_from_spblock),
                    )
                # 否则使用API数据按前缀筛选的北证A股作为备份

                result["T+0基金"] = self.block_parser.get_t0_funds()
                result["含可转债"] = self.block_parser.get_convertible_bonds()

                self.logger.info(
                    "    从spblock.dat获取特殊品种: 北证A股 %d 个, T+0基金 %d 个, 含可转债 %d 个",
                    len(result["北证A股"]),
                    len(result["T+0基金"]),
                    len(result["含可转债"]),
                )
            except Exception as e:
                self.logger.warning("解析通达信板块文件失败: %s，将仅使用API筛选的品种", e)
        else:
            self.logger.warning("  BlockParser不可用，跳过spblock.dat解析")

        elapsed_time = time.time() - start_time
        total_count = sum(len(codes) for codes in result.values())
        self.logger.info(
            "✅ parse_market_codes完成！耗时: %.2f秒, 总计 %d 个品种", elapsed_time, total_count
        )

        return result

    def cache_stock_list(self, stocks_df: pd.DataFrame) -> "Path":
        """
        缓存品种列表到本地（已解析分类，加载时无需再解析）

        Args:
            stocks_df: 品种列表DataFrame

        Returns:
            缓存文件路径
        """
        self.logger.info("【cache_stock_list】开始缓存 %d 个品种到本地...", len(stocks_df))
        start_time = time.time()

        cache_dir = config_manager.get_cache_dir()
        cache_file = cache_dir / "stock_list_classified.json"

        try:
            # 先解析分类（只解析一次，保存解析结果）
            self.logger.info("  → 解析品种分类...")
            classified = self.parse_market_codes(stocks_df)

            # 构建缓存数据
            cache_data = {
                "cache_time": datetime.now().isoformat(),
                "total_count": sum(len(codes) for codes in classified.values()),
                "classified": classified,  # 保存已解析的分类结果
            }

            # 保存为JSON格式（更适合存储字典数据）
            self.logger.info("  → 写入JSON文件: %s", cache_file)
            import json

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            # 更新内存缓存
            self._classified_stocks_cache = classified
            self.logger.info("  → 已更新内存缓存")

            elapsed_time = time.time() - start_time
            self.logger.info("✅ 品种列表已缓存！耗时: %.2f秒, 文件: %s", elapsed_time, cache_file)
            self.logger.info("   - 上证A股: %d 个", len(classified.get("上证A股", [])))
            self.logger.info("   - 深证A股: %d 个", len(classified.get("深证A股", [])))
            self.logger.info("   - 北证A股: %d 个", len(classified.get("北证A股", [])))
            self.logger.info("   - T+0基金: %d 个", len(classified.get("T+0基金", [])))
            self.logger.info("   - 含可转债: %d 个", len(classified.get("含可转债", [])))

            return cache_file

        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            elapsed_time = time.time() - start_time
            self.logger.error("❌ 缓存品种列表失败（耗时%.2f秒）: %s", elapsed_time, e)
            raise

    def load_cached_stock_list(self) -> Optional[Dict[str, List[str]]]:
        """
        加载缓存的品种分类（已解析，无需再次解析）

        Returns:
            缓存的品种分类字典，如果不存在则返回None
        """
        cache_dir = config_manager.get_cache_dir()
        cache_file = cache_dir / "stock_list_classified.json"

        # 兼容旧格式：如果JSON文件不存在，尝试加载parquet文件
        if not cache_file.exists():
            old_cache_file = cache_dir / "stock_list.parquet"
            if old_cache_file.exists():
                self.logger.info("检测到旧格式缓存文件，正在迁移...")
                try:
                    # 加载旧格式
                    df = pd.read_parquet(old_cache_file)
                    # 解析分类
                    classified = self.parse_market_codes(df)
                    # 保存为新格式
                    cache_data = {
                        "cache_time": datetime.now().isoformat(),
                        "total_count": sum(len(codes) for codes in classified.values()),
                        "classified": classified,
                    }
                    import json

                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                    self.logger.info("✅ 已迁移到新格式")
                    # 删除旧文件
                    old_cache_file.unlink()
                    return classified
                except Exception as e:
                    self.logger.error("迁移旧格式失败: %s", e)
                    return None

        if cache_file.exists():
            try:
                import json

                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

                classified = cache_data.get("classified", {})
                total_count = sum(len(codes) for codes in classified.values())
                self.logger.info("✅ 成功加载缓存的品种分类: %d 个品种", total_count)
                return classified
            except (OSError, ValueError, KeyError) as e:
                self.logger.error("加载缓存品种分类失败: %s", e)

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
        # 🔧 修复：进一步降低并发数避免API限流（从10降到1，串行下载）
        # mootdx API 对并发请求限流很严格，使用串行下载更稳定
        max_workers = 1

        self.logger.info(
            "开始全量下载K线数据: %s 个品种, %s 周期 (串行下载，更稳定)",
            len(symbols),
            intervals,
        )

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
                    else:
                        self.logger.debug("下载 %s %s 返回空数据", symbol, interval)
                except (OSError, ValueError, KeyError) as e:
                    self.logger.error("下载 %s %s 失败: %s", symbol, interval, e)
                except Exception as e:
                    self.logger.error(
                        "下载 %s %s 发生未知错误: %s", symbol, interval, e, exc_info=True
                    )

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
        # 🔧 修复：进一步降低并发数避免API限流（从10降到1，串行下载）
        # mootdx API 对并发请求限流很严格，使用串行下载更稳定
        max_workers = 1

        self.logger.info(
            "开始增量下载K线数据: %s 个品种, 从 %s 开始 (串行下载，更稳定)",
            len(symbols),
            start_date,
        )

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
                    else:
                        self.logger.debug("下载 %s %s 返回空数据", symbol, interval)
                except (OSError, ValueError, KeyError) as e:
                    self.logger.error("下载 %s %s 增量数据失败: %s", symbol, interval, e)
                except Exception as e:
                    self.logger.error(
                        "下载 %s %s 发生未知错误: %s", symbol, interval, e, exc_info=True
                    )

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

            # 🔧 修复：添加重试机制，避免API限流和无效日期导致的失败
            max_retries = 3
            retry_delay = 0.5  # 500毫秒
            data = None

            for retry in range(max_retries):
                # 🔧 在每次请求前添加小延迟，避免API限流（首次请求除外）
                if retry > 0:
                    time.sleep(retry_delay)

                # 调用mootdx接口
                self.logger.debug(
                    "调用mootdx API (尝试 %d/%d): symbol=%s, frequency=%s, offset=%d",
                    retry + 1,
                    max_retries,
                    symbol,
                    frequency,
                    offset,
                )
                data = self.quotes.bars(
                    symbol=symbol,
                    frequency=frequency,  # type: ignore[arg-type]
                    start=0,
                    offset=offset,
                )

                # 如果成功获取到数据，跳出重试循环
                if data is not None and not data.empty:
                    break

                # 如果数据为空，准备重试（延迟时间翻倍）
                if retry < max_retries - 1:
                    self.logger.warning(
                        "获取数据为空，%s秒后重试 %s %s", retry_delay, symbol, interval
                    )
                    retry_delay *= 2

            if data is not None and not data.empty:
                # 标准化列名（会自动过滤无效日期）
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

            # 🔧 修复：添加重试机制，避免API限流导致的空数据
            max_retries = 3
            retry_delay = 0.5  # 500毫秒
            data = None

            for retry in range(max_retries):
                # 🔧 在每次请求前添加小延迟，避免API限流（首次请求除外）
                if retry > 0:
                    time.sleep(retry_delay)

                # 调用mootdx接口
                self.logger.debug(
                    "调用mootdx API (尝试 %d/%d): symbol=%s, frequency=%s, offset=%d",
                    retry + 1,
                    max_retries,
                    symbol,
                    frequency,
                    offset,
                )
                data = self.quotes.bars(
                    symbol=symbol,
                    frequency=frequency,  # type: ignore[arg-type]
                    start=0,
                    offset=offset,
                )

                self.logger.debug(
                    "mootdx返回: symbol=%s, data is None=%s, data.empty=%s",
                    symbol,
                    data is None,
                    data.empty if data is not None else "N/A",
                )

                # 如果成功获取到数据，跳出重试循环
                if data is not None and not data.empty:
                    break

                # 如果数据为空，准备重试（延迟时间翻倍）
                if retry < max_retries - 1:
                    self.logger.warning(
                        "获取数据为空，%s秒后重试 %s %s", retry_delay, symbol, interval
                    )
                    retry_delay *= 2  # 指数退避

            if data is not None and not data.empty:
                # 验证datetime列是否存在
                if "datetime" not in data.columns and "date" not in data.columns:
                    self.logger.warning("下载的数据缺少datetime/date列: %s %s", symbol, interval)
                    return None

                try:
                    # 🔧 修复：先标准化列名和格式（包括datetime类型转换）
                    self.logger.debug("标准化前数据量 %s %s: %d条", symbol, interval, len(data))
                    data = self._standardize_columns(data, symbol, interval)

                    # 检查标准化后的数据
                    if data is None or data.empty:
                        self.logger.warning("标准化后数据为空（日期无效）: %s %s", symbol, interval)
                        return None

                    self.logger.debug("标准化后数据量 %s %s: %d条", symbol, interval, len(data))

                    # 然后过滤开始日期之后的数据
                    data = self._filter_by_date(data, start_date)

                    # 检查过滤后的数据是否为空
                    if data is None or data.empty:
                        self.logger.warning(
                            "过滤后数据为空 %s %s (起始日期: %s)", symbol, interval, start_date
                        )
                        return None

                    self.logger.debug("过滤后数据量 %s %s: %d条", symbol, interval, len(data))

                    return data

                except Exception as e:
                    self.logger.error("处理数据失败 %s %s: %s", symbol, interval, e, exc_info=True)
                    return None

        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            self.logger.error("下载 %s %s 增量数据失败: %s", symbol, interval, e, exc_info=True)

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
        # 🔧 修复：创建数据副本，避免修改原始数据
        data = data.copy()

        # 🔧 修复：重置索引（mootdx返回的数据可能以datetime为索引）
        if data.index.name == "datetime" or (
            hasattr(data.index, "dtype") and "datetime" in str(data.index.dtype)
        ):
            # 如果索引名为datetime且列中也有datetime，先删除列，保留索引
            if "datetime" in data.columns:
                data = data.drop(columns=["datetime"])

            # 🔧 修复：在reset_index前过滤无效日期索引
            # 某些品种的数据可能包含无效日期（如 0-00-00），需要先过滤
            try:
                # 检查索引是否有无效值（NaT）
                valid_index = data.index.notna()
                if not valid_index.all():
                    self.logger.warning(
                        "检测到 %d 个无效日期索引，已过滤: %s %s",
                        (~valid_index).sum(),
                        symbol,
                        interval,
                    )
                    data = data[valid_index]
            except Exception as e:
                self.logger.debug("检查索引有效性时出错: %s", e)

            data = data.reset_index(drop=False)

        # 🔧 修复：先处理重复列问题 - 如果存在 volume 列，先删除它（保留 vol 列用于重命名）
        # mootdx 返回的数据可能同时包含 vol 和 volume 列，需要去重
        if "vol" in data.columns and "volume" in data.columns:
            self.logger.debug("检测到重复的 volume 列，删除原始 volume 列，保留 vol 列")
            data = data.drop(columns=["volume"])

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

        # 🔧 修复：删除重复列（如果重命名后仍存在重复列）
        if data.columns.duplicated().any():
            self.logger.warning(
                "检测到重复列名: %s", data.columns[data.columns.duplicated()].tolist()
            )
            # 保留第一个出现的列，删除后续重复列
            data = data.loc[:, ~data.columns.duplicated(keep="first")]

        # 添加品种和周期信息
        data["symbol"] = symbol
        data["interval"] = interval

        # 确保datetime列是datetime类型（使用errors='coerce'处理无效日期）
        if "datetime" in data.columns:
            data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
            # 删除无效日期的行，避免后续处理出错
            data = data[data["datetime"].notna()].copy()

        # 🔧 修复：确保数值列是float类型，并增强错误处理
        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in data.columns:
                try:
                    # 确保列是 Series 类型（防止重复列导致的 DataFrame）
                    if isinstance(data[col], pd.DataFrame):
                        self.logger.warning("列 %s 是 DataFrame，取第一列", col)
                        data[col] = data[col].iloc[:, 0]

                    data[col] = pd.to_numeric(data[col], errors="coerce")
                except Exception as e:
                    self.logger.error("转换列 %s 为数值类型失败: %s", col, e)
                    # 如果转换失败，尝试强制转换
                    try:
                        data[col] = pd.to_numeric(data[col].values, errors="coerce")
                    except Exception as e2:
                        self.logger.error("强制转换列 %s 仍然失败: %s，跳过该列", col, e2)

        return data

    def _filter_by_date(self, data: pd.DataFrame, start_date: date) -> pd.DataFrame:
        """
        按日期过滤数据（增强版：添加错误处理和数据验证）

        Args:
            data: 原始数据
            start_date: 开始日期

        Returns:
            过滤后的数据
        """
        try:
            # 检查datetime列是否存在
            if "datetime" not in data.columns:
                self.logger.warning("数据缺少datetime列，无法按日期过滤")
                return data

            # 检查数据是否为空
            if data.empty:
                return data

            # 使用errors='coerce'处理无效日期，避免抛出异常
            data = data.copy()

            # 先转换为datetime类型，无效值会变成NaT
            datetime_series = pd.to_datetime(data["datetime"], errors="coerce")

            # 过滤掉NaT值
            valid_mask = datetime_series.notna()
            if not valid_mask.any():
                self.logger.warning("所有日期数据无效，返回空DataFrame")
                return pd.DataFrame()

            # 保持datetime64类型进行比较，避免转为date对象导致类型错误
            # 将start_date转为datetime64以便比较
            start_datetime = pd.Timestamp(start_date)

            # 直接使用datetime64进行比较（不转为date对象）
            # 这样可以避免"arg must be a list, tuple, 1-d array, or Series"错误
            date_mask = valid_mask & (datetime_series >= start_datetime)

            # 过滤数据
            filtered_data = data[date_mask].copy()

            return filtered_data

        except Exception as e:
            self.logger.error("按日期过滤失败: %s，返回原始数据", e, exc_info=True)
            return data

    def get_market_stocks(self, market_type: str, allow_fetch: bool = True) -> List[str]:
        """
        获取指定市场的品种列表（优先使用缓存，无需解析）

        Args:
            market_type: 市场类型（上证A股、深证A股、北证A股、T+0基金、含可转债）
            allow_fetch: 是否允许在缓存不存在时重新获取（默认True）
                        如果为False且缓存不存在，则返回空列表

        Returns:
            品种代码列表，如果缓存不存在且不允许重新获取，返回空列表
        """
        # 如果已有分类缓存，直接返回
        if self._classified_stocks_cache is not None:
            return self._classified_stocks_cache.get(market_type, [])

        # 尝试从本地缓存加载（已解析的分类，无需再解析）
        classified = self.load_cached_stock_list()
        if classified is not None:
            # 直接使用缓存结果
            self._classified_stocks_cache = classified
            return self._classified_stocks_cache.get(market_type, [])

        # 如果缓存不存在
        if not allow_fetch:
            # 不允许重新获取，返回空列表
            self.logger.warning("本地品种缓存不存在，且不允许重新获取")
            return []

        # 允许重新获取时，调用API
        self.logger.info("本地品种缓存不存在，开始从API获取...")
        stocks_df = self.fetch_all_stocks()
        # 解析一次并缓存结果
        self._classified_stocks_cache = self.parse_market_codes(stocks_df)
        return self._classified_stocks_cache.get(market_type, [])

    def get_all_market_stocks(self, allow_fetch: bool = True) -> Dict[str, List[str]]:
        """
        获取所有市场的品种分类（优先使用缓存，无需解析）

        Args:
            allow_fetch: 是否允许在缓存不存在时重新获取（默认True）
                        如果为False且缓存不存在，则返回空字典

        Returns:
            所有市场的品种分类字典，如果缓存不存在且不允许重新获取，返回空字典
        """
        # 如果已有分类缓存，直接返回
        if self._classified_stocks_cache is not None:
            return self._classified_stocks_cache

        # 尝试从本地缓存加载（已解析的分类，无需再解析）
        classified = self.load_cached_stock_list()
        if classified is not None:
            # 直接使用缓存结果
            self._classified_stocks_cache = classified
            return self._classified_stocks_cache

        # 如果缓存不存在
        if not allow_fetch:
            # 不允许重新获取，返回空字典
            self.logger.warning("本地品种缓存不存在，且不允许重新获取")
            return {}

        # 允许重新获取时，调用API
        self.logger.info("本地品种缓存不存在，开始从API获取...")
        stocks_df = self.fetch_all_stocks()
        # 解析一次并缓存结果
        self._classified_stocks_cache = self.parse_market_codes(stocks_df)
        return self._classified_stocks_cache
