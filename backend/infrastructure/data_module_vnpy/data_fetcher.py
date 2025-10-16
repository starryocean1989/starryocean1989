# -*- coding: utf-8 -*-
"""
数据获取模块

负责股票数据的获取、下载和解码，包括：
- 股票数据获取器基类和多进程版本
- 服务器池管理
- 数据解码器
- 工作进程函数

合并来源：stock_fetcher.py + multiprocess_fetcher.py + multiprocess_worker.py + server_pool.py + datetime_decoder.py
"""

# ==================== 导入声明 ====================
import logging
import signal
import threading
import time
import queue
from datetime import date, datetime
from multiprocessing import Manager, Process, cpu_count
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pandas as pd

from mootdx.quotes import Quotes

from .config import config_manager

# ==================== 工具类和异常 ====================


class NetworkTimeoutError(Exception):
    """网络超时异常"""

    def __init__(self, message="操作超时"):
        self.message = message
        super().__init__(self.message)


def timeout_handler(signum, frame):
    """超时处理器"""
    raise NetworkTimeoutError("操作超时")


class timeout_context:
    """超时上下文管理器（仅用于Unix系统，Windows使用其他方式）"""

    def __init__(self, seconds):
        self.seconds = seconds

    def __enter__(self):
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.seconds)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)


# ==================== 日期时间解码器 ====================


class TdxDateTimeDecoder:
    """通达信日期时间解码器"""

    DAILY_BASE_DATE = datetime(1990, 1, 1)

    @staticmethod
    def decode_minute_datetime(date_str: str, time_str: str = "00:00") -> Optional[datetime]:
        """解码分钟线日期时间"""
        try:
            parts = date_str.split("-")
            if len(parts) != 3:
                return None

            year = int(parts[0])
            day = int(parts[2])

            # 分钟线格式：YYYY-MM-DDD，DDD是年初开始的天数
            if day > 366:  # 无效天数
                return None

            # 计算实际日期
            base_date = datetime(year, 1, 1)
            timedelta_result = base_date + pd.Timedelta(days=day - 1)

            # 转换为datetime对象
            actual_date: datetime
            if isinstance(timedelta_result, datetime):
                actual_date = timedelta_result
            else:
                # 如果是Timestamp或其他类型，尝试转换为datetime
                try:
                    if hasattr(timedelta_result, "to_pydatetime") and callable(
                        timedelta_result.to_pydatetime
                    ):
                        converted = timedelta_result.to_pydatetime()
                        if not isinstance(converted, datetime):
                            return None
                        actual_date = converted
                    else:
                        year_val = int(timedelta_result.year)
                        month_val = int(timedelta_result.month)
                        day_val = int(timedelta_result.day)
                        actual_date = datetime(year_val, month_val, day_val)
                except (ValueError, TypeError, AttributeError):
                    return None

            # 解析时间
            time_parts = time_str.split(":")
            if len(time_parts) >= 2:
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                replaced_date = actual_date.replace(hour=hour, minute=minute)
                if not isinstance(replaced_date, datetime):
                    return None
                actual_date = replaced_date

            return actual_date

        except (ValueError, IndexError, OverflowError):
            return None

    @staticmethod
    def decode_daily_datetime(date_str: str) -> Optional[datetime]:
        """解码日线日期时间"""
        try:
            # 日线格式：DDDD-MM-DD，DDDD是从1990-01-01开始的总天数
            parts = date_str.split("-")
            if len(parts) != 3:
                return None

            total_days = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])

            # 从基准日期计算实际日期
            timedelta_result = TdxDateTimeDecoder.DAILY_BASE_DATE + pd.Timedelta(
                days=total_days - 1
            )

            # 转换为datetime对象
            actual_date: datetime
            if isinstance(timedelta_result, datetime):
                actual_date = timedelta_result
            else:
                # 如果是Timestamp或其他类型，尝试转换为datetime
                try:
                    if hasattr(timedelta_result, "to_pydatetime") and callable(
                        timedelta_result.to_pydatetime
                    ):
                        converted = timedelta_result.to_pydatetime()
                        if not isinstance(converted, datetime):
                            return None
                        actual_date = converted
                    else:
                        year_val = int(timedelta_result.year)
                        month_val = int(timedelta_result.month)
                        day_val = int(timedelta_result.day)
                        actual_date = datetime(year_val, month_val, day_val)
                except (ValueError, TypeError, AttributeError):
                    return None

            replaced_date = actual_date.replace(month=month, day=day)
            if not isinstance(replaced_date, datetime):
                return None
            actual_date = replaced_date

            return actual_date

        except (ValueError, IndexError, OverflowError):
            return None

    @staticmethod
    def decode_dataframe(data: pd.DataFrame, interval: str) -> pd.DataFrame:
        """解码DataFrame中的日期时间"""
        data = data.copy()

        if data.empty:
            return data

        # 根据周期选择解码函数
        if interval in ["1m", "5m"]:
            decode_func = TdxDateTimeDecoder.decode_minute_datetime
        else:
            decode_func = TdxDateTimeDecoder.decode_daily_datetime

        decoded_datetimes = []

        for _, row in data.iterrows():
            if "date" in row and "time" in row:
                # 分钟线格式：date="YYYY-MM-DDD", time="HH:MM"
                if interval in ["1m", "5m"]:
                    decoded = TdxDateTimeDecoder.decode_minute_datetime(
                        str(row["date"]), str(row["time"])
                    )
                else:
                    decoded = decode_func(str(row["date"]))
            elif "date" in row:
                # 日线格式：date="DDDD-MM-DD"
                decoded = decode_func(str(row["date"]))
            else:
                decoded = None

            decoded_datetimes.append(decoded)

        data["datetime"] = decoded_datetimes
        mask = data["datetime"].notna()
        filtered_data = data[mask]

        # 确保返回DataFrame类型
        if isinstance(filtered_data, pd.DataFrame):
            result = filtered_data.copy()
        else:
            result = pd.DataFrame(filtered_data)

        return result


# ==================== 服务器池管理 ====================


class QuotesWrapper:
    """包装TdxHq_API，提供与Quotes兼容的接口"""

    def __init__(self, client, server_info):
        self.client = client
        self.server = server_info

    def close(self):
        try:
            if hasattr(self.client, "close"):
                self.client.close()
        except Exception:
            pass


class ServerPool:
    """服务器池管理器"""

    def __init__(self, max_servers: int = 5, timeout: int = 5):
        """
        初始化服务器池

        Args:
            max_servers: 最多测试的服务器数量
            timeout: 每个服务器的连接超时时间（秒），默认5秒
        """
        self.max_servers = max_servers
        self.timeout = timeout  # 从15秒减少到5秒，加快发现速度
        self.available_servers: List[Tuple[str, int]] = []
        self.quotes_instances: Dict[Tuple[str, int], Quotes] = {}
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

    def discover_servers(self, force_check: bool = False) -> List[Tuple[str, int]]:
        """发现可用的mootdx服务器"""
        print(f">>> [SERVER_POOL] discover_servers 被调用，force_check={force_check}", flush=True)

        if not force_check and self.available_servers:
            print(f">>> [SERVER_POOL] 使用缓存的服务器列表: {len(self.available_servers)} 个", flush=True)
            return self.available_servers

        # 清空现有列表
        self.available_servers.clear()

        # mootdx内置服务器列表（从源码中提取）
        builtin_servers = [
            ("119.147.212.81", 7709),
            ("61.152.107.141", 7709),
            ("47.116.66.204", 7709),
            ("119.147.171.188", 7709),
            ("218.6.170.47", 7709),
            ("218.6.170.55", 7709),
            ("47.116.66.205", 7709),
            ("47.116.66.206", 7709),
        ]

        print(f">>> [SERVER_POOL] 准备测试最多 {min(self.max_servers, len(builtin_servers))} 个服务器", flush=True)
        print(f">>> [SERVER_POOL] 每个服务器超时时间: {self.timeout} 秒", flush=True)
        print(f">>> [SERVER_POOL] 早停策略: 找到3个可用服务器即停止", flush=True)

        # 测试服务器可用性（早停策略：找到3个可用服务器即可）
        available_servers = []
        min_servers_needed = min(3, self.max_servers)  # 至少需要3个，或max_servers

        for idx, server in enumerate(builtin_servers[: self.max_servers], 1):
            print(f">>> [SERVER_POOL] [{idx}/{self.max_servers}] 测试服务器 {server[0]}:{server[1]}...", flush=True)
            if self._test_server_connection(server):
                available_servers.append(server)
                print(f">>> [SERVER_POOL] ✓ 服务器 {server[0]}:{server[1]} 可用 ({len(available_servers)}/{min_servers_needed})", flush=True)
                self.logger.info("✅ 服务器 %s:%d 可用", server[0], server[1])

                # 早停：如果已经找到足够的服务器，就不再测试剩余的
                if len(available_servers) >= min_servers_needed:
                    print(f">>> [SERVER_POOL] ✓ 已找到 {len(available_servers)} 个可用服务器，提前停止测试", flush=True)
                    break
            else:
                print(f">>> [SERVER_POOL] ✗ 服务器 {server[0]}:{server[1]} 不可用", flush=True)

        self.available_servers = available_servers
        print(f">>> [SERVER_POOL] ✓ 总共发现 {len(available_servers)} 个可用服务器", flush=True)
        self.logger.info("发现 %d 个可用服务器", len(available_servers))

        return available_servers

    def _test_server_connection(self, server: Tuple[str, int]) -> bool:
        """测试服务器连接"""
        import time
        test_start = time.time()

        try:
            print(f">>> [SERVER_POOL] 正在连接 {server[0]}:{server[1]}...", flush=True)
            quotes = Quotes.factory(server=server, timeout=self.timeout)
            # 简单的连接测试：获取一个品种的基本信息
            # 使用client API直接测试连接
            test_result = hasattr(quotes, "client") or hasattr(quotes, "close")
            quotes.close()

            test_elapsed = time.time() - test_start
            print(f">>> [SERVER_POOL] 连接测试完成，耗时 {test_elapsed:.2f}秒，结果: {test_result}", flush=True)
            return test_result

        except Exception as e:
            test_elapsed = time.time() - test_start
            print(f">>> [SERVER_POOL] 连接测试失败，耗时 {test_elapsed:.2f}秒，错误: {str(e)[:100]}", flush=True)
            self.logger.debug("服务器 %s:%d 测试失败: %s", server[0], server[1], e)
            return False

    def get_server_pool(self, num_servers: int) -> List[Tuple[str, int]]:
        """获取服务器池"""
        if not self.available_servers:
            self.discover_servers()

        return self.available_servers[:num_servers]

    def create_quotes_for_server(self, server: Tuple[str, int]):
        """为指定服务器创建独立的Quotes实例"""
        quotes = Quotes.factory(server=server, timeout=self.timeout)
        return quotes


# ==================== 工作进程函数 ====================


def download_worker_process(
    worker_id: int,
    server: Tuple[str, int],
    task_queue,
    result_queue,
    progress_queue,
    stop_event,
    pause_event,
):
    """工作进程函数"""
    logger = logging.getLogger(f"Worker-{worker_id}")
    logger.setLevel(logging.INFO)

    quotes = None
    processed_count = 0

    # 强制输出，确保能看到
    print(f">>> [WORKER-{worker_id}] 工作进程启动，服务器: {server[0]}:{server[1]}", flush=True)

    try:
        # 创建独立的mootdx连接
        print(f">>> [WORKER-{worker_id}] 正在连接服务器...", flush=True)
        logger.info("进程 %d 正在连接服务器 %s:%d", worker_id, server[0], server[1])

        try:
            from mootdx.quotes import Quotes

            quotes = Quotes.factory(server=server, timeout=5, heartbeat=False)
            print(f">>> [WORKER-{worker_id}] ✓ 使用mootdx连接成功", flush=True)
            logger.info(
                "✅ 进程 %d 使用mootdx.Quotes连接成功: %s:%d", worker_id, server[0], server[1]
            )
        except Exception as e:
            print(f">>> [WORKER-{worker_id}] mootdx连接失败，尝试TdxHq_API: {str(e)[:50]}", flush=True)
            logger.warning("进程 %d mootdx.Quotes连接失败: %s，尝试TdxHq_API降级", worker_id, e)
            # 降级方案：使用TdxHq_API
            try:
                from tdxpy.hq import TdxHq_API

                client = TdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)
                client.connect(server[0], server[1], time_out=5)
                quotes = QuotesWrapper(client, server)
                print(f">>> [WORKER-{worker_id}] ✓ 使用TdxHq_API连接成功", flush=True)
                logger.info(
                    "✅ 进程 %d 使用TdxHq_API连接成功: %s:%d", worker_id, server[0], server[1]
                )
            except Exception as e2:
                print(f">>> [WORKER-{worker_id}] ❌ 两种连接方式都失败: {str(e2)[:50]}", flush=True)
                logger.error("进程 %d TdxHq_API连接也失败: %s", worker_id, e2)
                return

        # 主循环：从队列获取任务并执行
        print(f">>> [WORKER-{worker_id}] 开始任务循环...", flush=True)
        empty_count = 0  # 连续空队列计数
        task_count = 0  # 记录处理的任务数

        while not stop_event.is_set():
            try:
                # 等待暂停信号
                pause_event.wait()

                # 获取任务（非阻塞）
                try:
                    task = task_queue.get_nowait()
                    empty_count = 0  # 重置空计数
                    task_count += 1

                    symbol, interval, start_date = task

                    # 每处理100个任务输出一次
                    if task_count % 100 == 1:
                        print(f">>> [WORKER-{worker_id}] 已处理 {task_count} 个任务，当前: {symbol} {interval}", flush=True)

                    logger.debug("进程 %d 处理任务: %s %s", worker_id, symbol, interval)

                    # 执行下载
                    data = _download_single_kline_incremental(quotes, symbol, interval, start_date)

                    if data is not None and not data.empty:
                        # 发送进度
                        progress_queue.put((symbol, interval))

                        # 发送结果（转换为字典格式）
                        data_dict = data.to_dict("records")
                        result_key = f"{symbol}_{interval}"
                        result_queue.put((result_key, data_dict))

                        processed_count += 1
                        logger.debug("进程 %d 完成: %s %s", worker_id, symbol, interval)
                    else:
                        # 下载失败或空数据也要报告进度，否则监控线程会卡住
                        if task_count <= 10:  # 只输出前10个失败的详情
                            if data is None:
                                print(f">>> [WORKER-{worker_id}] ⚠️ 下载失败（返回None）: {symbol} {interval}", flush=True)
                            else:
                                print(f">>> [WORKER-{worker_id}] ⚠️ 下载空数据: {symbol} {interval}", flush=True)
                        logger.debug("进程 %d 跳过空数据: %s %s", worker_id, symbol, interval)
                        # 即使失败也发送进度，确保监控线程不卡住
                        progress_queue.put((symbol, interval))

                except queue.Empty:
                    empty_count += 1
                    if empty_count >= 10:  # 连续10次空队列则退出
                        print(f">>> [WORKER-{worker_id}] 队列空，退出 (连续空{empty_count}次)", flush=True)
                        logger.info("进程 %d 队列空，退出 (连续空%d次)", worker_id, empty_count)
                        break
                    time.sleep(0.5)  # 短暂等待

            except Exception as e:
                logger.error("进程 %d 处理任务异常: %s", worker_id, e)

        print(f">>> [WORKER-{worker_id}] 正常退出，已处理 {processed_count} 个任务", flush=True)
        logger.info("进程 %d 正常退出，已处理 %d 个任务", worker_id, processed_count)

    finally:
        # 确保连接被关闭
        if quotes and hasattr(quotes, "close"):
            try:
                quotes.close()
            except Exception as e:
                logger.debug("关闭连接异常: %s", e)


def _download_single_kline_incremental(
    quotes, symbol: str, interval: str, start_date: Union[str, date]
) -> Optional[pd.DataFrame]:
    """下载单个品种的增量K线数据"""
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

        # 确定市场代码
        market = 1 if symbol.startswith("6") else 0

        # 调用底层API获取原始数据
        try:
            raw_data = quotes.client.get_security_bars(
                int(frequency), int(market), str(symbol), 0, int(offset)
            )
        except Exception as api_error:
            print(f">>> [DOWNLOAD] API调用失败 {symbol} {interval}: {str(api_error)[:100]}", flush=True)
            logging.getLogger(__name__).error("API调用失败 %s %s: %s", symbol, interval, api_error)
            return None

        if not raw_data:
            # 只输出前3个空数据的情况
            import random
            if random.random() < 0.01:  # 1%概率输出
                print(f">>> [DOWNLOAD] API返回空数据: {symbol} {interval}", flush=True)
            return None

        # 转换为DataFrame
        data = pd.DataFrame(raw_data)

        # 解码日期
        data = TdxDateTimeDecoder.decode_dataframe(data, interval)

        # 设置index
        if not data.empty and "datetime" in data.columns:
            data = data.set_index("datetime", drop=False)

        # 标准化列名
        if "vol" in data.columns:
            data["volume"] = data["vol"]

        # 标准化列名
        data = _standardize_columns(data, symbol, interval)

        if data is not None and not data.empty:
            # 过滤日期
            data = _filter_by_date(data, start_date)

        return data

    except Exception as e:
        logging.getLogger(__name__).error("下载 %s %s 增量数据失败: %s", symbol, interval, e)
        return None


def _standardize_columns(data: pd.DataFrame, symbol: str, interval: str) -> pd.DataFrame:
    """标准化DataFrame列名和格式"""
    data = data.copy()

    # 重命名列
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
    if "datetime" in data.columns and not data.empty:
        # 确保datetime列是可序列化的类型
        datetime_col = data["datetime"]
        if isinstance(datetime_col, pd.Series) and len(datetime_col) > 0:
            data["datetime"] = pd.to_datetime(datetime_col, errors="coerce")
            # 过滤掉无效的datetime
            filtered_data = data[data["datetime"].notna()]
            data = (
                filtered_data.copy()
                if isinstance(filtered_data, pd.DataFrame)
                else pd.DataFrame(filtered_data)
            )

    # 确保数值列是float类型
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    return data


def _filter_by_date(data: pd.DataFrame, start_date: date) -> pd.DataFrame:
    """按日期过滤数据"""
    try:
        if data.empty:
            return data

        data = data.copy()

        if pd.api.types.is_datetime64_any_dtype(data.index):
            start_datetime = pd.Timestamp(start_date)
            filtered = data[data.index >= start_datetime]
            result_df: pd.DataFrame = (
                filtered if isinstance(filtered, pd.DataFrame) else pd.DataFrame(filtered)
            )
            return result_df

        if "datetime" not in data.columns:
            return data

        if not pd.api.types.is_datetime64_any_dtype(data["datetime"]):
            datetime_series = data["datetime"]
            # 添加类型检查
            if isinstance(datetime_series, pd.Series) and len(datetime_series) > 0:
                datetime_series = pd.to_datetime(datetime_series, errors="coerce")
            else:
                return data
        else:
            datetime_series = data["datetime"]

        valid_mask = datetime_series.notna()
        # 检查是否有任何有效值
        has_valid_values = bool(valid_mask.sum() > 0)
        if not has_valid_values:
            return pd.DataFrame()

        start_datetime = pd.Timestamp(start_date)
        date_mask = valid_mask & (datetime_series >= start_datetime)

        filtered_result = data[date_mask]
        final_result: pd.DataFrame = (
            filtered_result.copy()
            if isinstance(filtered_result, pd.DataFrame)
            else pd.DataFrame(filtered_result)
        )
        return final_result

    except Exception as e:
        logging.getLogger(__name__).error("按日期过滤失败: %s，返回原始数据", e)
        return data


# ==================== 基础数据获取器 ====================


class StockFetcher:
    """股票数据获取器基类"""

    MARKET_SHANGHAI = 0
    MARKET_SHENZHEN = 1

    SH_PREFIXES = ["688", "60"]
    SZ_PREFIXES = ["000", "001", "002", "300", "301"]
    BJ_PREFIXES = ["43", "83", "87", "88"]

    def __init__(self, block_parser=None):  # pylint: disable=unused-argument
        # block_parser 参数为向后兼容性保留，目前未使用
        # 异步下载控制
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

        # 下载进度跟踪
        self._download_progress = {
            "is_downloading": False,
            "completed": 0,
            "total": 0,
            "current_symbol": "",
            "current_interval": "",
            "start_time": None,
        }

        # 服务器池
        server_pool_size = config_manager.get("chinastock.server_pool_size", 5)
        self.server_pool = ServerPool(max_servers=server_pool_size, timeout=5)
        self.logger = logging.getLogger(__name__)

        # 保留quotes用于向后兼容
        self._quotes = None

    @property
    def quotes(self):
        """向后兼容：延迟初始化单一Quotes实例"""
        if self._quotes is None:
            self._quotes = Quotes.factory()
            self.logger.info("延迟初始化默认Quotes实例（向后兼容）")
        return self._quotes

    # 下载控制方法
    def stop_download(self):
        self._stop_event.set()
        self.logger.info("下载停止信号已设置")

    def pause_download(self):
        self._pause_event.clear()
        self.logger.info("下载暂停信号已设置")

    def resume_download(self):
        self._pause_event.set()
        self.logger.info("下载恢复信号已设置")

    def reset_download_state(self):
        self._stop_event.clear()
        self._pause_event.set()
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
        return self._download_progress.copy()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date: Union[str, date],
        intervals: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """增量下载K线数据

        基类方法，多线程并行下载架构已取消。
        只保留MultiProcessStockFetcher类中的多进程版本实现。
        """
        raise NotImplementedError(
            "StockFetcher基类的download_incremental_kline()方法已取消多线程实现。"
            "请使用MultiProcessStockFetcher类中的多进程版本。"
        )

    def get_all_market_stocks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有市场的股票列表

        Returns:
            分类后的股票字典，格式：
            {
                "上证A股": [{"code": "600000", "name": "浦发银行", "market": 1}, ...],
                "深证A股": [{"code": "000001", "name": "平安银行", "market": 0}, ...],
                "北证A股": [...],
                "T+0基金": [...],
                "可转债": [...]
            }
        """
        from .symbol_management import SymbolLoader

        try:
            # 使用SymbolLoader获取分类后的股票列表
            symbol_loader = SymbolLoader()

            # 优先从缓存加载
            stocks_dict = symbol_loader.load_from_cache()
            if stocks_dict is None:
                # 缓存不存在，从API加载
                stocks_dict = symbol_loader.load_from_api()

            return stocks_dict

        except Exception as e:
            self.logger.error("获取所有市场股票失败: %s", e)
            # 返回空的分类字典
            return {"上证A股": [], "深证A股": [], "北证A股": [], "T+0基金": [], "可转债": []}


# ==================== 多进程数据获取器 ====================


class MultiProcessStockFetcher(StockFetcher):
    """多进程股票数据获取器（集成异步下载管理，从download_manager.py合并）"""

    def __init__(self, block_parser=None, event_engine=None):
        # 先调用父类初始化
        super().__init__(block_parser)

        self.logger = logging.getLogger(__name__)

        # 获取进程数配置
        pool_size = config_manager.get("chinastock.server_pool_size", 5)
        cpu_cores = cpu_count()
        max_processes = min(pool_size, cpu_cores * 2, 30)
        self.num_processes = max_processes

        self.logger.info(
            "初始化多进程下载器: %d个进程（CPU核心数: %d，配置: %d）",
            self.num_processes,
            cpu_cores,
            pool_size,
        )

        # 多进程共享对象
        self.manager = None
        self.task_queue = None
        self.result_queue = None
        self.progress_queue = None
        self.stop_event = None
        self.pause_event = None
        self._pause_set = True

        self.processes: List[Process] = []

        # ServerPool
        self.server_pool = ServerPool(max_servers=max_processes, timeout=5)

        # 事件发布器（从download_manager.py合并）
        self.event_engine = event_engine
        if event_engine:
            from .events import DownloadEventPublisher, EventPublisher

            self.download_publisher = DownloadEventPublisher(event_engine)
            self.log_publisher = EventPublisher(event_engine)
        else:
            self.download_publisher = None
            self.log_publisher = None

        # 异步下载管理（从download_manager.py合并）
        self._download_thread = None
        self._download_lock = threading.Lock()

    def _init_multiprocess_objects(self):
        """延迟初始化多进程对象"""
        if self.manager is None:
            self.manager = Manager()
            self.task_queue = self.manager.Queue()
            self.result_queue = self.manager.Queue()
            self.progress_queue = self.manager.Queue()
            self.stop_event = self.manager.Event()
            self.pause_event = self.manager.Event()
            if self._pause_set:
                self.pause_event.set()

            self._download_progress = self.manager.dict(
                {
                    "is_downloading": False,
                    "completed": 0,
                    "total": 0,
                    "current_symbol": "",
                    "current_interval": "",
                    "start_time": None,
                }
            )

    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date,
        intervals: Optional[List[str]] = None,
        progress_callback=None,
    ) -> Dict[str, pd.DataFrame]:
        """增量下载K线数据（多进程版本）"""
        result = {}
        import time as time_module
        download_start_time = time_module.time()

        # 强制输出，确保能看到
        print(f">>> [FETCHER] download_incremental_kline 被调用", flush=True)
        print(f">>> [FETCHER] 品种数量: {len(symbols)}", flush=True)
        print(f">>> [FETCHER] 开始日期: {start_date}", flush=True)

        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        print(f">>> [FETCHER] 周期列表: {intervals}", flush=True)
        print(f">>> [FETCHER] 进程数: {self.num_processes}", flush=True)

        self.logger.info("=" * 60)
        self.logger.info("【多进程并行下载】开始增量下载K线数据")
        self.logger.info("  开始时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.logger.info("  品种数量: %d", len(symbols))
        self.logger.info("  周期列表: %s", intervals)
        self.logger.info("  起始日期: %s", start_date)
        self.logger.info("  进程数: %d", self.num_processes)

        # 🔧 诊断：检查symbols参数
        if not symbols or len(symbols) == 0:
            print(f">>> [FETCHER] ❌ 品种列表为空，无法下载！", flush=True)
            self.logger.error("❌ 品种列表为空，无法下载！")
            self.logger.error("  symbols参数: %s", symbols)
            return result

        self.logger.info("  品种样例（前5个）: %s", symbols[:5])
        self.logger.info("=" * 60)

        try:
            # 步骤1：发现可用服务器
            print(f">>> [FETCHER] 步骤1: 开始发现可用服务器...", flush=True)
            available_servers = self.server_pool.discover_servers()[: self.num_processes]
            print(f">>> [FETCHER] 发现 {len(available_servers)} 个可用服务器", flush=True)

            if not available_servers:
                self.logger.error("❌ 没有可用服务器，无法下载")
                return result

            num_servers = len(available_servers)
            self.logger.info("✅ 发现 %d 个可用服务器", num_servers)

            # 步骤2：构建任务列表
            print(f">>> [FETCHER] 步骤2: 构建任务列表...", flush=True)
            tasks = [(symbol, interval, start_date) for symbol in symbols for interval in intervals]
            total_tasks = len(tasks)

            print(f">>> [FETCHER] 任务列表构建完成: {total_tasks} 个任务", flush=True)
            self.logger.info("✅ 任务列表构建完成: 总计 %d 个任务", total_tasks)

            # 初始化多进程对象
            print(f">>> [FETCHER] 初始化多进程对象...", flush=True)
            self._init_multiprocess_objects()

            # 清空队列
            print(f">>> [FETCHER] 清空队列...", flush=True)
            self._clear_queues()

            # 填充任务队列
            print(f">>> [FETCHER] 填充任务队列...", flush=True)
            if self.task_queue is not None:
                for task in tasks:
                    self.task_queue.put(task)
                print(f">>> [FETCHER] 任务队列已填充: {total_tasks} 个任务", flush=True)

            # 初始化进度
            print(f">>> [FETCHER] 设置 is_downloading = True", flush=True)
            self._download_progress["is_downloading"] = True
            self._download_progress["completed"] = 0
            self._download_progress["total"] = total_tasks
            self._download_progress["start_time"] = datetime.now().isoformat()
            print(f">>> [FETCHER] ✓ 进度状态已初始化: is_downloading=True, total={total_tasks}", flush=True)

            # 步骤3：启动工作进程
            print(f">>> [FETCHER] 步骤3: 启动工作进程...", flush=True)
            self._start_worker_processes(available_servers)
            print(f">>> [FETCHER] ✓ 工作进程已启动", flush=True)

            # 步骤4：监控进度并收集结果
            print(f">>> [FETCHER] 步骤4: 开始监控进度并收集结果...", flush=True)
            result = self._monitor_progress_and_collect_results(total_tasks, progress_callback)
            print(f">>> [FETCHER] ✓ 监控完成，收集到 {len(result)} 个结果", flush=True)

            # 等待进程自动退出
            time.sleep(6.0)

            # 步骤5：清理进程
            self._cleanup_processes()

            valid_count = sum(1 for v in result.values() if v is not None and not v.empty)
            empty_count = len(result) - valid_count
            download_elapsed = time_module.time() - download_start_time

            self.logger.info("=" * 60)
            self.logger.info("【完成】多进程下载完成")
            self.logger.info("  结束时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.logger.info("  总耗时: %.2f 秒", download_elapsed)
            self.logger.info("  总任务数: %d", total_tasks)
            self.logger.info("  下载结果数: %d", len(result))
            self.logger.info("  有效数据: %d", valid_count)
            self.logger.info("  空数据: %d", empty_count)
            self.logger.info("  平均速度: %.2f 任务/秒", total_tasks / download_elapsed if download_elapsed > 0 else 0)

        except Exception as e:
            download_elapsed = time_module.time() - download_start_time
            self.logger.error("多进程下载异常 (耗时: %.2f秒): %s", download_elapsed, e, exc_info=True)
            self._download_progress["is_downloading"] = False
            self._cleanup_processes()
            return result
        finally:
            self._download_progress["is_downloading"] = False

        return result

    def _start_worker_processes(self, servers: List[Tuple[str, int]]):
        """启动工作进程"""
        for i, server in enumerate(servers):
            try:
                p = Process(
                    target=download_worker_process,
                    args=(
                        i,
                        server,
                        self.task_queue,
                        self.result_queue,
                        self.progress_queue,
                        self.stop_event,
                        self.pause_event,
                    ),
                )
                p.start()
                self.processes.append(p)
                self.logger.info(
                    "✅ 进程 %d 已启动，PID: %d，服务器: %s:%d", i, p.pid, server[0], server[1]
                )
            except Exception as e:
                self.logger.error("启动进程 %d 失败: %s", i, e)

        self.logger.info("总计启动 %d 个工作进程", len(self.processes))

    def _monitor_progress_and_collect_results(
        self, total_tasks: int, progress_callback
    ) -> Dict[str, pd.DataFrame]:
        """监控进度并收集结果"""
        results = {}
        completed = 0

        while completed < total_tasks:
            if self.stop_event is not None and self.stop_event.is_set():
                break

            # 收集进度
            try:
                if self.progress_queue is None:
                    break
                symbol, interval = self.progress_queue.get(timeout=0.1)
                completed += 1
                self._download_progress["completed"] = completed
                self._download_progress["current_symbol"] = symbol
                self._download_progress["current_interval"] = interval

                if completed % 10 == 0 or completed == total_tasks:
                    progress_pct = (completed / total_tasks) * 100
                    self.logger.info(
                        "📊 进度: [%d/%d (%.1f%%)] - %s %s",
                        completed,
                        total_tasks,
                        progress_pct,
                        symbol,
                        interval,
                    )

                if progress_callback:
                    progress_callback(completed, total_tasks, symbol, interval)

            except queue.Empty:
                if all(not p.is_alive() for p in self.processes):
                    self._drain_queues(results)
                    completed = len(results)
                    break

            # 收集结果
            try:
                if self.result_queue is not None:
                    key, data_dict = self.result_queue.get_nowait()
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        if "datetime" in df.columns:
                            try:
                                # 确保datetime列是可转换的类型
                                if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                                    df["datetime"] = pd.to_datetime(df["datetime"], errors='coerce')
                            except Exception as e:
                                # 转换失败时记录错误但不影响其他数据
                                self.logger.error("datetime列转换失败 %s: %s", key, str(e))
                        results[key] = df
            except queue.Empty:
                pass

        return results

    def _drain_queues(self, results: Dict):
        """排空队列"""
        if self.result_queue is not None:
            while True:
                try:
                    key, data_dict = self.result_queue.get_nowait()
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        if "datetime" in df.columns:
                            try:
                                # 确保datetime列是可转换的类型
                                if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                                    df["datetime"] = pd.to_datetime(df["datetime"], errors='coerce')
                            except Exception as e:
                                # 转换失败时记录错误但不影响其他数据
                                self.logger.error("datetime列转换失败 %s: %s", key, str(e))
                        results[key] = df
                except queue.Empty:
                    break

        extra_progress = 0
        if self.progress_queue is not None:
            while True:
                try:
                    self.progress_queue.get_nowait()
                    extra_progress += 1
                except queue.Empty:
                    break

        if extra_progress > 0:
            self.logger.info("从队列中收集到额外 %d 个进度", extra_progress)

    def _cleanup_processes(self):
        """清理所有工作进程"""
        if not self.processes:
            return

        for p in self.processes:
            if p.is_alive():
                try:
                    p.join(timeout=2)
                except Exception:
                    pass

            if p.is_alive():
                try:
                    p.terminate()
                    p.join(timeout=1)
                except Exception:
                    pass

        self.processes.clear()
        self.logger.info("✅ 进程清理完成")

    def _clear_queues(self):
        """清空所有队列"""
        queues = [self.task_queue, self.result_queue, self.progress_queue]
        for q in queues:
            if q is not None:
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

    def set_server_count(self, num_servers: int) -> None:
        """
        动态设置服务器数量（从core.py迁移的功能）

        Args:
            num_servers: 服务器数量（1-30）
        """
        cpu_cores = cpu_count()
        self.num_processes = min(num_servers, cpu_cores * 2, 30)
        self.server_pool = ServerPool(max_servers=self.num_processes, timeout=5)
        self.logger.info("服务器数量已更新: %d", self.num_processes)

    # ==================== 异步下载管理（从download_manager.py合并） ====================

    def start_incremental_download_async(
        self,
        start_date,
        symbol_loader,
        storage_manager,
        market_types=None,
    ) -> bool:
        """
        启动增量下载（异步执行，立即返回，从download_manager.py合并）

        Args:
            start_date: 开始日期
            symbol_loader: SymbolLoader实例
            storage_manager: StorageManager实例
            market_types: 市场类型列表

        Returns:
            是否成功启动下载任务
        """
        with self._download_lock:
            # 检查是否有正在运行的下载任务
            if self._download_thread and self._download_thread.is_alive():
                self.logger.warning("已有下载任务正在运行")
                return False

            # 重置下载状态
            self.reset_download_state()

            # 创建并启动后台下载线程
            self._download_thread = threading.Thread(
                target=self._do_download_async,
                args=(start_date, symbol_loader, storage_manager, market_types),
                daemon=True,
                name="IncrementalDownloadThread",
            )
            self._download_thread.start()

            self.logger.info("✅ 增量下载任务已启动（后台线程）")
            return True

    def _do_download_async(self, start_date, symbol_loader, storage_manager, market_types=None):
        """
        实际执行增量下载的后台方法（从download_manager.py合并）

        Args:
            start_date: 开始日期
            symbol_loader: SymbolLoader实例
            storage_manager: StorageManager实例
            market_types: 市场类型列表
        """
        try:
            # 定义进度回调（事件推送）
            def progress_callback(completed: int, total: int, symbol: str, interval: str):
                should_push = completed % 100 == 0 or completed == 1 or completed == total
                if should_push and self.download_publisher:
                    progress_pct = (completed / total) * 100
                    self.download_publisher.push_download_progress_event(
                        "incremental_kline", progress_pct, completed, total, f"{symbol} {interval}"
                    )

            # 调用统一下载接口
            num_servers = config_manager.get("chinastock.server_pool_size", 5)

            result = download_incremental_unified(
                symbols=[],  # 空列表，让函数自动从symbol_loader提取
                start_date=start_date,
                symbol_loader=symbol_loader,
                market_types=market_types,
                intervals=None,
                num_servers=num_servers,
                storage_callback=storage_manager.save_kline,
                progress_callback=progress_callback,
                event_callback=self.download_publisher.push_download_event if self.download_publisher else None,
            )

            # 推送最终事件
            if result["success"]:
                if self.download_publisher:
                    self.download_publisher.push_download_event(
                        "incremental_kline", "success", result["saved_count"]
                    )
                if self.log_publisher:
                    self.log_publisher.push_log_event(result["message"])
            else:
                if self.download_publisher:
                    self.download_publisher.push_download_event(
                        "incremental_kline", "error", 0, result["message"]
                    )
                if self.log_publisher:
                    self.log_publisher.push_log_event(result["message"], "ERROR")

        except Exception as e:
            self.logger.error("增量下载失败: %s", e, exc_info=True)
            if self.download_publisher:
                self.download_publisher.push_download_event("incremental_kline", "error", 0, str(e))
            if self.log_publisher:
                self.log_publisher.push_log_event(f"增量下载失败: {e}", "ERROR")


# ==================== 统一下载接口（从core.py迁移） ====================


def download_incremental_unified(
    symbols: List[str],
    start_date: Union[str, date],
    intervals: Optional[List[str]] = None,
    num_servers: int = 5,
    symbol_loader=None,
    market_types: Optional[List[str]] = None,
    storage_callback: Optional[Callable[[str, str, pd.DataFrame], Optional[Any]]] = None,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    event_callback: Optional[Callable[[str, str, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    统一增量下载接口 - 封装所有下载业务逻辑（从core.py迁移，完全增强版）

    功能：
    1. 自动品种提取（如果传入symbol_loader）
    2. 日期验证和天数计算
    3. Bar数量自动计算（在_download_single_kline_incremental中）
    4. 多进程任务分配
    5. 数据下载和解码
    6. 自动存储（通过回调）
    7. 进度和事件推送（通过回调）

    Args:
        symbols: 品种代码列表（如为空且提供symbol_loader，则自动提取）
        start_date: 开始日期（字符串或date对象）
        intervals: 周期列表（默认["1d", "5m", "1m"]）
        num_servers: 并行服务器数量（1-30，默认5）
        symbol_loader: SymbolLoader实例（可选，用于自动提取品种）
        market_types: 市场类型列表（配合symbol_loader使用）
        storage_callback: 存储回调函数 callback(symbol, interval, data) -> Optional[Path]
        progress_callback: 进度回调函数 callback(completed, total, symbol, interval)
        event_callback: 事件回调函数 callback(event_type, status, count, message)

    Returns:
        Dict {
            "success": bool,
            "total_tasks": int,
            "completed": int,
            "saved_count": int,
            "skipped_count": int,
            "failed_count": int,
            "message": str
        }
    """
    import time
    from datetime import datetime, date as date_type

    logger = logging.getLogger(__name__)

    # 1. 自动提取品种（如果传入symbol_loader）
    if symbol_loader and (not symbols or len(symbols) == 0):
        logger.info("未提供品种列表，尝试从symbol_loader自动提取...")

        # 首先尝试从缓存加载
        classified_stocks = symbol_loader.load_from_cache() or {}

        if not classified_stocks:
            logger.warning("本地品种缓存为空，尝试重新加载品种列表")
            reload_result = symbol_loader.reload_and_classify()

            if not reload_result.get("success"):
                error_msg = "无法获取品种列表，请先在【品种列表】界面点击【重新加载品种】按钮"
                logger.error(error_msg)
                if event_callback:
                    event_callback("incremental_kline", "error", 0, error_msg)
                return {
                    "success": False,
                    "total_tasks": 0,
                    "completed": 0,
                    "saved_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "message": error_msg,
                }

        # 提取品种代码
        symbols = symbol_loader.extract_codes_by_market(market_types)

        if not symbols:
            error_msg = "品种列表为空，无法下载"
            logger.error(error_msg)
            if event_callback:
                event_callback("incremental_kline", "error", 0, error_msg)
            return {
                "success": False,
                "total_tasks": 0,
                "completed": 0,
                "saved_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "message": error_msg,
            }

        logger.info("✓ 从symbol_loader提取到 %d 个品种", len(symbols))

    logger.info("=" * 60)
    logger.info("【统一下载接口】开始增量下载K线数据")
    logger.info("  开始时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("  品种数量: %d", len(symbols))
    logger.info("  起始日期: %s", start_date)
    logger.info("  服务器数: %d", num_servers)
    logger.info("=" * 60)

    # 验证参数
    if not symbols or len(symbols) == 0:
        error_msg = "品种列表为空，无法下载"
        logger.error(error_msg)
        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)
        return {
            "success": False,
            "total_tasks": 0,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    if intervals is None:
        intervals = ["1d", "5m", "1m"]

    # 日期验证
    today = date_type.today()
    actual_start_date: date_type

    if isinstance(start_date, str):
        try:
            actual_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError as e:
            error_msg = f"日期格式错误: {e}"
            logger.error(error_msg)
            if event_callback:
                event_callback("incremental_kline", "error", 0, error_msg)
            return {
                "success": False,
                "total_tasks": 0,
                "completed": 0,
                "saved_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "message": error_msg,
            }
    elif isinstance(start_date, date_type):
        actual_start_date = start_date
    else:
        actual_start_date = today

    days_diff = (today - actual_start_date).days

    logger.info("📅 增量下载日期范围:")
    logger.info("  • 开始日期: %s", actual_start_date)
    logger.info("  • 结束日期: %s", today)
    logger.info("  • 天数差: %d 天", days_diff)

    # 检查日期范围合理性
    if days_diff <= 0:
        error_msg = f"日期范围无效：开始日期{actual_start_date}晚于或等于今天{today}"
        logger.error(error_msg)
        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)
        return {
            "success": False,
            "total_tasks": 0,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    if days_diff > 100:
        logger.warning("⚠️ 日期范围超过100天，可能导致下载大量历史数据")

    # 创建下载器并设置服务器数量
    fetcher = MultiProcessStockFetcher()
    fetcher.set_server_count(num_servers)

    total_tasks = len(symbols) * len(intervals)
    logger.info("✅ 日期范围验证通过，准备调用下载器...")
    logger.info("即将下载参数:")
    logger.info("  • 品种数量: %d", len(symbols))
    logger.info("  • 起始日期: %s", start_date)
    logger.info("  • 周期列表: %s", intervals)
    logger.info("  • 预计任务数: %d", total_tasks)

    # 定义内部进度回调（限制事件推送频率）
    def internal_progress_callback(completed: int, total: int, symbol: str, interval: str):
        """内部进度回调：通过外部回调推送进度"""
        if progress_callback:
            progress_callback(completed, total, symbol, interval)

        # 限制事件推送频率
        if event_callback:
            should_push = (
                completed % 100 == 0 or completed == 1 or completed == total
            )
            if should_push:
                progress_pct = (completed / total) * 100
                event_callback(
                    "incremental_kline_progress",
                    "running",
                    completed,
                    f"{symbol} {interval} ({progress_pct:.1f}%)",
                )

    # 下载增量K线数据
    download_start = time.time()

    try:
        logger.info("=" * 60)
        logger.info("🚀 开始调用 download_incremental_kline()...")
        logger.info("  调用时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("=" * 60)

        download_results = fetcher.download_incremental_kline(
            symbols, start_date, intervals=intervals, progress_callback=internal_progress_callback
        )

        download_elapsed = time.time() - download_start

        logger.info("=" * 60)
        logger.info("✅ download_incremental_kline() 调用完成")
        logger.info("  完成时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("  总耗时: %.2f 秒", download_elapsed)
        logger.info("  返回结果数: %d", len(download_results) if download_results else 0)
        logger.info("=" * 60)

    except Exception as download_error:
        download_elapsed = time.time() - download_start
        error_msg = f"下载异常: {str(download_error)}"
        logger.error("=" * 60)
        logger.error("❌ download_incremental_kline() 调用异常")
        logger.error("  异常时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.error("  已耗时: %.2f 秒", download_elapsed)
        logger.error("  异常信息: %s", str(download_error), exc_info=True)
        logger.error("=" * 60)

        if event_callback:
            event_callback("incremental_kline", "error", 0, error_msg)

        return {
            "success": False,
            "total_tasks": total_tasks,
            "completed": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": error_msg,
        }

    # 检查是否被停止
    if fetcher.is_stopped():
        logger.warning("⛔ 下载被停止")
        if event_callback:
            event_callback("incremental_kline", "stopped", len(download_results), "下载已停止")
        return {
            "success": False,
            "total_tasks": total_tasks,
            "completed": len(download_results),
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": "下载已停止",
        }

    # 保存数据（如果提供了存储回调）
    saved_count = 0
    skipped_count = 0
    failed_count = 0

    if storage_callback:
        # 统计下载结果的详细状态
        none_count = sum(1 for v in download_results.values() if v is None)
        empty_count = sum(1 for v in download_results.values() if v is not None and v.empty)

        logger.info("=" * 60)
        logger.info("开始保存下载结果...")
        logger.info("📊 下载结果分析:")
        logger.info("  • 下载结果总数: %d", len(download_results))
        logger.info("  • 下载返回None: %d (下载失败)", none_count)
        logger.info("  • 下载返回空数据: %d (品种无数据/停牌等)", empty_count)
        logger.info(
            "  • 下载返回有效数据: %d (待保存)",
            len(download_results) - none_count - empty_count,
        )

        for key, data in download_results.items():
            parts = key.split("_", 1)
            if len(parts) != 2:
                continue
            symbol, interval = parts

            # 检查数据有效性
            if data is None:
                logger.debug("跳过保存（下载失败）: %s %s", symbol, interval)
                skipped_count += 1
            elif data.empty or len(data) == 0:
                logger.debug("跳过保存（空数据）: %s %s", symbol, interval)
                skipped_count += 1
            else:
                # 有数据，尝试保存
                try:
                    result_path = storage_callback(symbol, interval, data)
                    if result_path is not None:
                        saved_count += 1
                        logger.debug("✓ 保存成功: %s %s (%d行)", symbol, interval, len(data))
                    else:
                        failed_count += 1
                        logger.error("✗ 保存失败: %s %s", symbol, interval)
                except Exception as e:
                    logger.error("保存 %s %s 异常: %s", symbol, interval, e)
                    failed_count += 1

        # 统计汇总
        logger.info("=" * 60)
        logger.info("📊 保存统计:")
        logger.info("  • 下载结果总数: %d", len(download_results))
        logger.info("  • 成功保存: %d", saved_count)
        logger.info("  • 跳过（下载失败/空数据）: %d", skipped_count)
        logger.info("  • 保存失败: %d", failed_count)
        if (saved_count + failed_count) > 0:
            logger.info(
                "  • 保存成功率: %.1f%%",
                (saved_count / (saved_count + failed_count) * 100),
            )
        logger.info("=" * 60)

    # 推送完成事件
    if event_callback:
        event_callback("incremental_kline", "success", saved_count, f"成功保存{saved_count}个数据集")

    return {
        "success": True,
        "total_tasks": total_tasks,
        "completed": len(download_results),
        "saved_count": saved_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "message": f"成功保存{saved_count}个数据集（跳过{skipped_count}个空数据）",
    }
