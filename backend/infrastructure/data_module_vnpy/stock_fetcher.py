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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path  # noqa: TC003
from typing import Callable, Dict, List, Optional, Union

import pandas as pd

from mootdx.quotes import Quotes

from .block_parser import BlockParser
from .config import config_manager
from .datetime_decoder import TdxDateTimeDecoder
from .server_pool import ServerPool


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
        # 🔧 异步下载控制
        self._stop_event = threading.Event()  # 停止信号
        self._pause_event = threading.Event()  # 暂停信号
        self._pause_event.set()  # 默认不暂停（set表示可以继续）

        # 🔧 下载进度跟踪（用于前端轮询）
        self._download_progress = {
            "is_downloading": False,
            "completed": 0,
            "total": 0,
            "current_symbol": "",
            "current_interval": "",
            "start_time": None,
        }
        # 🚀 新架构：使用服务器池管理多个连接
        # 获取配置的服务器池大小（默认5个）
        server_pool_size = config_manager.get("chinastock.server_pool_size", 5)
        self.server_pool = ServerPool(max_servers=server_pool_size, timeout=30)
        self.logger = logging.getLogger(__name__)

        # 保留quotes用于向后兼容（延迟初始化）
        self._quotes = None

        self.block_parser = block_parser or BlockParser(config_manager.get_tdx_dir())

        # 超时配置
        self.network_timeout = 30  # 网络请求超时时间（秒），从10秒改为30秒

        # 品种分类缓存：避免重复解析spblock.dat
        self._classified_stocks_cache: Optional[Dict[str, List[str]]] = None

    @property
    def quotes(self):
        """向后兼容：延迟初始化单一Quotes实例"""
        if self._quotes is None:
            self._quotes = Quotes.factory()
            self.logger.info("延迟初始化默认Quotes实例（向后兼容）")
        return self._quotes

    # ==================== 下载控制方法 ====================

    def stop_download(self):
        """停止下载"""
        self._stop_event.set()
        self.logger.info("下载停止信号已设置")

    def pause_download(self):
        """暂停下载"""
        self._pause_event.clear()  # clear表示暂停（wait会阻塞）
        self.logger.info("下载暂停信号已设置")

    def resume_download(self):
        """恢复下载"""
        self._pause_event.set()  # set表示继续（wait立即返回）
        self.logger.info("下载恢复信号已设置")

    def reset_download_state(self):
        """重置下载状态（准备新的下载任务）"""
        self._stop_event.clear()
        self._pause_event.set()
        # 重置进度
        self._download_progress = {
            "is_downloading": False,
            "completed": 0,
            "total": 0,
            "current_symbol": "",
            "current_interval": "",
            "start_time": None,
        }
        self.logger.info("下载状态已重置")

    def get_download_progress(self) -> dict:
        """获取当前下载进度（供前端轮询使用）"""
        return self._download_progress.copy()

    def is_stopped(self) -> bool:
        """检查是否已停止"""
        return self._stop_event.is_set()

    def is_paused(self) -> bool:
        """检查是否已暂停"""
        return not self._pause_event.is_set()

    # ==================== 品种列表获取 ====================

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
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        增量下载K线数据（多服务器并行架构）

        Args:
            symbols: 品种代码列表
            start_date: 开始日期
            intervals: K线周期列表
            progress_callback: 进度回调函数，参数为(completed, total, symbol, interval)

        Returns:
            下载结果字典，如果被停止则返回部分结果
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        result = {}

        # 🚀 新架构：多服务器并行下载
        # ============================================================
        # 【架构说明】：
        #   1. 发现可用服务器（mootdx内置服务器池）
        #   2. 为每个服务器创建独立Quotes实例（独立TCP连接）
        #   3. 将任务按品种+周期分配给多个服务器
        #   4. 每个服务器内部串行处理（避免单连接限流）
        #   5. 多个服务器之间并行执行（ThreadPoolExecutor）
        #
        # 【性能提升】：
        #   - 理论提速：N倍（N=服务器数量，考虑网络延迟实际约0.7N）
        #   - 降低空数据率：多服务器分散压力，单点故障影响小
        #   - 提升稳定性：服务器级别负载均衡
        # ============================================================

        self.logger.info("=" * 60)
        self.logger.info("【多服务器并行下载】开始增量下载K线数据")
        self.logger.info("  品种数量: %d", len(symbols))
        self.logger.info("  周期列表: %s", intervals)
        self.logger.info("  起始日期: %s", start_date)
        self.logger.info("=" * 60)

        try:
            # 步骤1：发现可用服务器
            self.logger.info("【步骤1】发现可用服务器...")
            available_servers = self.server_pool.discover_servers()

            if not available_servers:
                self.logger.error("❌ 没有可用服务器，无法下载")
                return result

            num_servers = len(available_servers)
            self.logger.info("✅ 发现 %d 个可用服务器", num_servers)

            # 步骤2：分配任务到服务器
            self.logger.info("【步骤2】分配任务到服务器...")
            tasks_per_server = self._split_tasks_by_server(symbols, intervals, num_servers)

            if not tasks_per_server:
                self.logger.error("❌ 任务分配失败")
                return result

            # 计算总任务数
            total_tasks = len(symbols) * len(intervals)
            self.logger.info("✅ 任务分配完成: 总计 %d 个任务", total_tasks)

            # 预估时间（多服务器并行）
            estimated_time = total_tasks * 1.5 / 60 / num_servers
            self.logger.info("⏰ 预计耗时: %.1f 分钟（%d服务器并行）", estimated_time, num_servers)

            # 初始化进度跟踪
            from datetime import datetime

            self._download_progress = {
                "is_downloading": True,
                "completed": 0,
                "total": total_tasks,
                "current_symbol": "",
                "current_interval": "",
                "start_time": datetime.now(),
            }

            # 步骤3：并行执行下载任务
            self.logger.info("【步骤3】启动 %d 个并行下载线程...", num_servers)
            self.logger.info("=" * 60)

            # 性能监控：记录开始时间
            parallel_start_time = time.time()

            completed_lock = threading.Lock()
            completed_tasks = [0]  # 使用列表以便在闭包中修改

            # 性能监控：各服务器完成时间
            server_completion_times = {}

            def wrapped_progress_callback(
                local_completed, local_total, symbol, interval
            ):  # noqa: ARG001
                """包装的进度回调，用于聚合多个服务器的进度"""
                with completed_lock:
                    completed_tasks[0] += 1
                    progress_pct = (completed_tasks[0] / total_tasks) * 100

                    # 更新进度信息
                    self._download_progress.update(
                        {
                            "completed": completed_tasks[0],
                            "current_symbol": symbol,
                            "current_interval": interval,
                        }
                    )

                    # 每100个打印一次进度
                    if completed_tasks[0] % 100 == 0:
                        self.logger.info(
                            "📊 进度: [%d/%d (%.1f%%)]",
                            completed_tasks[0],
                            total_tasks,
                            progress_pct,
                        )

                    # 🚀 性能优化：大幅降低UI回调频率
                    # 调用外部回调（UI更新）- 根据服务器数量动态调整频率
                    # 服务器越多，UI更新越少，避免事件队列阻塞
                    if progress_callback:
                        # 动态计算更新间隔
                        if num_servers >= 20:
                            update_interval = 50  # 20+服务器：每50个任务更新一次
                        elif num_servers >= 15:
                            update_interval = 30  # 15-19服务器：每30个任务
                        elif num_servers >= 10:
                            update_interval = 20  # 10-14服务器：每20个任务
                        else:
                            update_interval = 10  # <10服务器：每10个任务

                        # 只在达到间隔或完成时才回调UI
                        if (
                            completed_tasks[0] % update_interval == 0
                            or completed_tasks[0] == total_tasks
                        ):
                            try:
                                progress_callback(completed_tasks[0], total_tasks, symbol, interval)
                            except Exception as e:
                                self.logger.error("进度回调失败: %s", e)

            # 🚀 关键修复：使用as_completed实现真正的并行等待
            # 而不是串行等待每个future按顺序完成
            executor = None  # 初始化为None

            try:
                executor = ThreadPoolExecutor(max_workers=num_servers)
                futures = []

                # 提交所有任务到线程池
                for server, tasks in tasks_per_server.items():
                    try:
                        # 为每个服务器创建独立的Quotes实例
                        quotes_instance = self.server_pool.create_quotes_for_server(server)

                        # 提交任务
                        future = executor.submit(
                            self._download_tasks_for_server,
                            quotes_instance,
                            tasks,
                            start_date,
                            wrapped_progress_callback,
                        )
                        futures.append((future, server))

                    except Exception as e:
                        self.logger.error(
                            "为服务器 %s:%d 创建连接失败: %s，跳过该服务器", server[0], server[1], e
                        )
                        # 继续下一个服务器
                        continue

                if not futures:
                    self.logger.error("❌ 所有服务器连接失败，无法下载")
                    return result

                # 🚀 使用as_completed实现并行等待
                # 谁先完成就先处理谁，不会按顺序等待
                future_to_server = {future: server for future, server in futures}
                completed_servers = 0

                try:
                    for future in as_completed(future_to_server.keys()):
                        # 检查停止信号
                        if self.is_stopped():
                            self.logger.warning("⛔ 检测到停止信号，等待当前任务完成后退出...")

                            # 🚀 关键修复：不尝试取消future（会导致异常）
                            # future.cancel()对已运行的任务无效，且可能引发异常
                            # 改为：等待当前正在处理的future完成，然后退出循环
                            # 后台线程会检查self.is_stopped()并自行中断

                            self.logger.info("等待当前服务器任务完成...")
                            break

                        server = future_to_server[future]
                        completed_servers += 1

                        # 🔍 性能监控：记录服务器完成时间
                        server_elapsed = time.time() - parallel_start_time
                        server_completion_times[server] = server_elapsed

                        try:
                            server_results = future.result(timeout=300)  # 5分钟超时

                            if server_results and isinstance(server_results, dict):
                                result.update(server_results)

                                # 🔍 性能监控：显示服务器完成时间和速度
                                tasks_count = len(tasks_per_server.get(server, []))
                                avg_time_per_task = (
                                    server_elapsed / tasks_count if tasks_count > 0 else 0
                                )

                                self.logger.info(
                                    "✅ 服务器 %s:%d 完成 [%d/%d]: %d/%d 个数据集, "
                                    "耗时 %.1f秒, 平均 %.2f秒/任务",
                                    server[0],
                                    server[1],
                                    completed_servers,
                                    num_servers,
                                    len(server_results),
                                    tasks_count,
                                    server_elapsed,
                                    avg_time_per_task,
                                )
                            else:
                                self.logger.warning(
                                    "⚠️ 服务器 %s:%d 返回无效结果", server[0], server[1]
                                )
                        except TimeoutError:
                            self.logger.error(
                                "❌ 服务器 %s:%d 超时（>300秒）", server[0], server[1]
                            )
                        except Exception as e:
                            self.logger.error(
                                "❌ 服务器 %s:%d 执行失败: %s",
                                server[0],
                                server[1],
                                e,
                                exc_info=True,
                            )

                except Exception as loop_error:
                    self.logger.error("处理future结果时异常: %s", loop_error, exc_info=True)

            finally:
                # 🚀 关键修复：确保executor正确关闭
                # 检查executor是否已创建
                if executor is not None:
                    try:
                        if self.is_stopped():
                            self.logger.info("停止状态，快速关闭executor（不等待未完成任务）")
                            # Python 3.9+支持cancel_futures参数
                            try:
                                executor.shutdown(wait=False, cancel_futures=True)
                            except TypeError:
                                # Python 3.8及以下版本不支持cancel_futures参数
                                executor.shutdown(wait=False)
                        else:
                            self.logger.debug("正常完成，关闭executor")
                            executor.shutdown(wait=True)
                    except Exception as shutdown_err:
                        self.logger.error("关闭executor失败: %s", shutdown_err, exc_info=True)

            # 🔍 性能监控：分析并行性能
            total_parallel_time = time.time() - parallel_start_time

            self.logger.info("=" * 60)
            self.logger.info(
                "【完成】增量下载完成: 成功下载 %d/%d 个数据集", len(result), total_tasks
            )
            self.logger.info("总耗时: %.1f 秒", total_parallel_time)

            # 分析并行效率
            if server_completion_times:
                min_time = min(server_completion_times.values())
                max_time = max(server_completion_times.values())
                avg_time = sum(server_completion_times.values()) / len(server_completion_times)

                self.logger.info("【性能分析】")
                self.logger.info("  最快服务器: %.1f 秒", min_time)
                self.logger.info("  最慢服务器: %.1f 秒", max_time)
                self.logger.info("  平均完成时间: %.1f 秒", avg_time)
                self.logger.info(
                    "  负载均衡度: %.1f%% （理想100%%）",
                    (min_time / max_time * 100) if max_time > 0 else 0,
                )

                # 检查是否真正并行
                if max_time < total_parallel_time * 1.1:  # 允许10%误差
                    self.logger.info("  ✅ 确认：服务器真正并行执行")
                else:
                    self.logger.warning(
                        "  ⚠️ 警告：可能存在串行化！最慢服务器 %.1fs < 总时间 %.1fs",
                        max_time,
                        total_parallel_time,
                    )

            self.logger.info("=" * 60)

        except KeyboardInterrupt:
            self.logger.warning("下载被用户中断（KeyboardInterrupt）")
            # 标记下载完成
            self._download_progress["is_downloading"] = False
            return result

        except Exception as e:
            self.logger.error("增量下载异常: %s", e, exc_info=True)
            # 标记下载完成
            self._download_progress["is_downloading"] = False
            return result

        finally:
            # 确保无论如何都标记下载完成
            self._download_progress["is_downloading"] = False

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
                "5m": 0,  # 5分钟 (修正：mootdx中frequency=0才是5分钟线，frequency=5是周线)
                "1m": 8,  # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 🔧 修复：设置下载数量（mootdx限制最大800）
            offset_map = {
                "1d": 800,  # 日线最大800根
                "5m": 800,  # 5分钟最大800根
                "1m": 800,  # 1分钟最大800根
            }

            offset = offset_map.get(interval, 800)

            # 🔧 修复：添加重试机制，避免API限流和无效日期导致的失败
            max_retries = 3
            retry_delay = 0.5  # 500毫秒
            data = None

            for retry in range(max_retries):
                # 🔧 限流机制发现：基于并发连接数，不是QPS
                # 串行请求无需延迟，重试时才延迟
                if retry > 0:
                    time.sleep(retry_delay)

                # 🔧 调用底层API，绕过mootdx的自动日期解析
                self.logger.debug(
                    "调用mootdx API (尝试 %d/%d): symbol=%s, frequency=%s, offset=%d",
                    retry + 1,
                    max_retries,
                    symbol,
                    frequency,
                    offset,
                )

                try:
                    # 确定市场代码
                    market = 1 if symbol.startswith("6") else 0

                    # 调用底层API
                    raw_data = self.quotes.client.get_security_bars(
                        int(frequency), int(market), str(symbol), 0, int(offset)  # start
                    )

                    if not raw_data:
                        data = None
                    else:
                        # 手动转换为DataFrame并解码
                        data = pd.DataFrame(raw_data)
                        data = TdxDateTimeDecoder.decode_dataframe(data, interval)

                        # 设置index
                        if not data.empty and "datetime" in data.columns:
                            data.index = data["datetime"]

                        # 标准化列名
                        if "vol" in data.columns:
                            data["volume"] = data["vol"]

                except Exception as api_error:
                    self.logger.warning(
                        "底层API调用失败: %s, 错误: %s", symbol, str(api_error)[:50]
                    )
                    data = None

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
                "5m": 0,  # 5分钟 (修正：mootdx中frequency=0才是5分钟线，frequency=5是周线)
                "1m": 8,  # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 🔧 修复：根据周期设置合理的下载数量
            # ⚠️ 关键发现：mootdx API的offset最大值是800，超过返回空数据！
            if interval == "1d":
                # 日线：每天1条，但要考虑节假日，实际交易日约70%
                offset = min(int(days_diff * 1.5), 800)  # 最大800
            elif interval == "5m":
                # 5分钟线：每天48条（4小时交易时间 = 240分钟 / 5）
                offset = min(int(days_diff * 50), 800)  # 最大800
            elif interval == "1m":
                # 1分钟线：每天240条
                offset = min(int(days_diff * 250), 800)  # 最大800
            else:
                offset = 800  # 默认值

            # 🔧 修复：添加重试机制，避免API限流导致的空数据
            max_retries = 3
            retry_delay = 0.5  # 500毫秒
            data = None

            for retry in range(max_retries):
                # 🔧 限流机制发现：基于并发连接数，不是QPS
                # 串行请求无需延迟，重试时才延迟
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

                try:
                    # 🔧 关键修复：直接调用底层API，绕过mootdx的自动日期解析
                    # 确定市场代码（0=深圳，1=上海）
                    market = 1 if symbol.startswith("6") else 0

                    # 🔧 调试日志
                    self.logger.debug(
                        "底层API参数: frequency=%d, market=%d, symbol=%s, start=0, offset=%d",
                        frequency,
                        market,
                        symbol,
                        offset,
                    )

                    # 调用底层API获取原始数据（不经过to_data处理）
                    raw_data = self.quotes.client.get_security_bars(
                        int(frequency), int(market), str(symbol), 0, int(offset)
                    )

                    self.logger.debug(
                        "底层API返回: raw_data is None=%s, len=%s",
                        raw_data is None,
                        len(raw_data) if raw_data else 0,
                    )

                    if not raw_data:
                        data = None
                    else:
                        # 手动转换为DataFrame
                        data = pd.DataFrame(raw_data)
                        self.logger.debug("转换为DataFrame: %d 行", len(data))

                        # 🔧 使用通达信解码器解码日期（关键！）
                        data = TdxDateTimeDecoder.decode_dataframe(data, interval)
                        self.logger.debug("解码后: %d 行", len(data) if data is not None else 0)

                        # 设置index为datetime（解码后的）
                        if not data.empty and "datetime" in data.columns:
                            data.index = data["datetime"]

                        # 标准化列名（volume列）
                        if "vol" in data.columns:
                            data["volume"] = data["vol"]

                except (ValueError, pd.errors.ParserError) as e:
                    # 🔧 捕获其他解析错误
                    self.logger.error(
                        "下载 %s %s 数据处理失败: %s",
                        symbol,
                        interval,
                        str(e)[:100],
                    )
                    data = None
                except Exception as e:
                    # 捕获所有其他异常
                    self.logger.error(
                        "下载 %s %s 发生异常: %s",
                        symbol,
                        interval,
                        str(e)[:100],
                    )
                    import traceback

                    self.logger.error("异常详情:\n%s", traceback.format_exc())
                    data = None

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
        按日期过滤数据（优化版：使用index而不是datetime列）

        Args:
            data: 原始数据（index已设置为datetime）
            start_date: 开始日期

        Returns:
            过滤后的数据
        """
        try:
            # 检查数据是否为空
            if data.empty:
                return data

            # 创建副本
            data = data.copy()

            # 🔧 优先使用index进行过滤（decode_dataframe已设置index为datetime）
            if pd.api.types.is_datetime64_any_dtype(data.index):
                # index已经是datetime类型，直接过滤
                start_datetime = pd.Timestamp(start_date)
                filtered = data[data.index >= start_datetime]

                self.logger.debug(
                    "使用index过滤: %d条 → %d条 (start_date=%s)",
                    len(data),
                    len(filtered),
                    start_date,
                )
                return filtered

            # 🔧 备用：如果index不是datetime，尝试使用datetime列
            if "datetime" not in data.columns:
                self.logger.warning("数据没有datetime列也没有datetime index，无法过滤")
                return data

            # 转换datetime列（可能已经是datetime类型）
            if not pd.api.types.is_datetime64_any_dtype(data["datetime"]):
                datetime_series = pd.to_datetime(data["datetime"], errors="coerce")
            else:
                datetime_series = data["datetime"]

            # 过滤掉NaT值
            valid_mask = datetime_series.notna()
            if not valid_mask.any():
                self.logger.warning("所有日期数据无效，返回空DataFrame")
                return pd.DataFrame()

            # 过滤日期
            start_datetime = pd.Timestamp(start_date)
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

    # ==================== 多服务器并行下载方法 ====================

    def _split_tasks_by_server(
        self, symbols: List[str], intervals: List[str], num_servers: int
    ) -> Dict[tuple, List[tuple]]:
        """
        将下载任务按服务器分组

        Args:
            symbols: 品种代码列表
            intervals: K线周期列表
            num_servers: 服务器数量

        Returns:
            服务器到任务列表的映射 {(ip, port): [(symbol, interval), ...]}
        """
        # 生成所有任务
        all_tasks = [(s, i) for s in symbols for i in intervals]

        # 获取服务器列表
        servers = self.server_pool.get_server_pool(num_servers)

        if not servers:
            self.logger.error("没有可用服务器")
            return {}

        # 按服务器数量分组（轮询分配）
        tasks_per_server = {}
        for idx, task in enumerate(all_tasks):
            server_idx = idx % len(servers)
            server = servers[server_idx]
            if server not in tasks_per_server:
                tasks_per_server[server] = []
            tasks_per_server[server].append(task)

        # 打印任务分配统计
        self.logger.info("任务分配统计:")
        for server, tasks in tasks_per_server.items():
            self.logger.info("  服务器 %s:%d -> %d 个任务", server[0], server[1], len(tasks))

        return tasks_per_server

    def _download_tasks_for_server(
        self,
        quotes_instance: Quotes,
        tasks: List[tuple],
        start_date: Union[str, date],
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        在单个服务器连接上串行处理所有分配的任务

        Args:
            quotes_instance: 该服务器的独立Quotes实例
            tasks: 该服务器负责的任务列表 [(symbol, interval), ...]
            start_date: 开始日期
            progress_callback: 进度回调函数

        Returns:
            下载结果字典 {f"{symbol}_{interval}": DataFrame}
        """
        results = {}
        server_info = "未知"

        try:
            # 获取服务器信息用于日志
            if hasattr(quotes_instance, "server"):
                server_info = f"{quotes_instance.server[0]}:{quotes_instance.server[1]}"

            # 🔍 性能监控：记录此服务器的开始时间
            server_start_time = time.time()
            current_thread = threading.current_thread()

            self.logger.info(
                "🚀 服务器 %s 开始处理 %d 个任务 (线程: %s)",
                server_info,
                len(tasks),
                current_thread.name,
            )

            for idx, (symbol, interval) in enumerate(tasks):
                # 检查停止信号
                if self.is_stopped():
                    self.logger.warning("服务器 %s 检测到停止信号，中断处理", server_info)
                    break

                # 检查暂停信号
                self._pause_event.wait()

                # 下载单个品种数据
                try:
                    data = self._download_single_with_quotes(
                        quotes_instance, symbol, interval, start_date
                    )

                    if data is not None and not data.empty:
                        key = f"{symbol}_{interval}"
                        results[key] = data
                        self.logger.debug(
                            "服务器 %s: ✅ %s %s (%d条) [%d/%d]",
                            server_info,
                            symbol,
                            interval,
                            len(data),
                            idx + 1,
                            len(tasks),
                        )
                    else:
                        self.logger.debug(
                            "服务器 %s: ⚠️ %s %s 返回空数据 [%d/%d]",
                            server_info,
                            symbol,
                            interval,
                            idx + 1,
                            len(tasks),
                        )

                    # 调用进度回调（如果提供）
                    # 🚀 优化：只在每10个任务回调一次，减少锁竞争
                    if progress_callback and ((idx + 1) % 10 == 0 or (idx + 1) == len(tasks)):
                        # 注意：这里的进度是针对这个服务器的，总进度由上层聚合
                        progress_callback(idx + 1, len(tasks), symbol, interval)

                except Exception as e:
                    self.logger.error(
                        "服务器 %s 下载 %s %s 失败: %s", server_info, symbol, interval, str(e)[:100]
                    )

            # 🔍 性能监控：此服务器总耗时
            server_total_time = time.time() - server_start_time
            successful_rate = len(results) / len(tasks) * 100 if len(tasks) > 0 else 0

            self.logger.info(
                "🏁 服务器 %s 完成: 成功 %d/%d 个任务 (%.1f%%), " "总耗时 %.1f秒, 平均 %.2f秒/任务",
                server_info,
                len(results),
                len(tasks),
                successful_rate,
                server_total_time,
                server_total_time / len(tasks) if len(tasks) > 0 else 0,
            )

        except KeyboardInterrupt:
            self.logger.warning("服务器 %s 被用户中断", server_info)

        except Exception as e:
            self.logger.error("服务器 %s 处理异常: %s", server_info, e, exc_info=True)

        finally:
            # 🚀 关键修复：确保连接总是被关闭，避免资源泄漏
            try:
                if hasattr(quotes_instance, "close"):
                    quotes_instance.close()
                    self.logger.debug("服务器 %s 连接已关闭", server_info)
            except Exception as close_err:
                # 忽略关闭错误，不影响返回
                self.logger.debug("关闭服务器 %s 连接时出错（已忽略）: %s", server_info, close_err)

        return results

    def _download_single_with_quotes(
        self,
        quotes_instance: Quotes,
        symbol: str,
        interval: str,
        start_date: Union[str, date],
    ) -> Optional[pd.DataFrame]:
        """
        使用指定Quotes实例下载单个品种的增量K线数据

        Args:
            quotes_instance: Quotes实例
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
                "5m": 0,  # 5分钟
                "1m": 8,  # 1分钟
            }

            frequency = frequency_map.get(interval, 9)

            # 根据周期设置合理的下载数量
            if interval == "1d":
                offset = min(int(days_diff * 1.5), 800)
            elif interval == "5m":
                offset = min(int(days_diff * 50), 800)
            elif interval == "1m":
                offset = min(int(days_diff * 250), 800)
            else:
                offset = 800

            # 添加重试机制
            max_retries = 3
            retry_delay = 0.5
            data = None

            for retry in range(max_retries):
                if retry > 0:
                    time.sleep(retry_delay)

                try:
                    # 确定市场代码
                    market = 1 if symbol.startswith("6") else 0

                    # 调用底层API（使用传入的quotes_instance）
                    raw_data = quotes_instance.client.get_security_bars(
                        int(frequency), int(market), str(symbol), 0, int(offset)
                    )

                    if not raw_data:
                        data = None
                    else:
                        # 转换为DataFrame并解码
                        data = pd.DataFrame(raw_data)
                        data = TdxDateTimeDecoder.decode_dataframe(data, interval)

                        # 设置index
                        if not data.empty and "datetime" in data.columns:
                            data.index = data["datetime"]

                        # 标准化列名
                        if "vol" in data.columns:
                            data["volume"] = data["vol"]

                except Exception as api_error:
                    self.logger.debug("API调用失败: %s, 错误: %s", symbol, str(api_error)[:50])
                    data = None

                # 如果成功获取到数据，跳出重试循环
                if data is not None and not data.empty:
                    break

                # 如果数据为空，准备重试
                if retry < max_retries - 1:
                    retry_delay *= 2

            if data is not None and not data.empty:
                # 标准化列名并过滤
                data = self._standardize_columns(data, symbol, interval)

                if data is not None and not data.empty:
                    # 过滤日期
                    data = self._filter_by_date(data, start_date)

                    if data is not None and not data.empty:
                        return data

        except Exception as e:
            self.logger.error("下载 %s %s 增量数据失败: %s", symbol, interval, e)

        return None
