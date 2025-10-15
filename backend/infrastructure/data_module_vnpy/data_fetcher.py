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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from multiprocessing import Manager, Process, cpu_count
from typing import Callable, Dict, List, Optional, Tuple, Union

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
            actual_date = base_date + pd.Timedelta(days=day - 1)

            # 解析时间
            time_parts = time_str.split(":")
            if len(time_parts) >= 2:
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                actual_date = actual_date.replace(hour=hour, minute=minute)

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
            actual_date = TdxDateTimeDecoder.DAILY_BASE_DATE + pd.Timedelta(days=total_days - 1)
            actual_date = actual_date.replace(month=month, day=day)

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
                decoded = decode_func(str(row["date"]), str(row["time"]))
            elif "date" in row:
                # 日线格式：date="DDDD-MM-DD"
                decoded = decode_func(str(row["date"]))
            else:
                decoded = None

            decoded_datetimes.append(decoded)

        data["datetime"] = decoded_datetimes
        data = data[data["datetime"].notna()].copy()

        return data


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

    def __init__(self, max_servers: int = 5, timeout: int = 15):
        self.max_servers = max_servers
        self.timeout = timeout
        self.available_servers: List[Tuple[str, int]] = []
        self.quotes_instances: Dict[Tuple[str, int], Quotes] = {}
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

    def discover_servers(self, force_check: bool = False) -> List[Tuple[str, int]]:
        """发现可用的mootdx服务器"""
        if not force_check and self.available_servers:
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

        # 测试服务器可用性
        available_servers = []
        for server in builtin_servers[: self.max_servers]:
            if self._test_server_connection(server):
                available_servers.append(server)
                self.logger.info("✅ 服务器 %s:%d 可用", server[0], server[1])

        self.available_servers = available_servers
        self.logger.info("发现 %d 个可用服务器", len(available_servers))

        return available_servers

    def _test_server_connection(self, server: Tuple[str, int]) -> bool:
        """测试服务器连接"""
        try:
            quotes = Quotes.factory(server=server, timeout=self.timeout)
            # 简单的连接测试：获取一个品种的基本信息
            stocks = quotes.stocks(0)  # 上海市场
            quotes.close()

            if stocks is not None and not stocks.empty:
                return True
            return False

        except Exception as e:
            self.logger.debug("服务器 %s:%d 测试失败: %s", server[0], server[1], e)
            return False

    def get_server_pool(self, num_servers: int) -> List[Tuple[str, int]]:
        """获取服务器池"""
        if not self.available_servers:
            self.discover_servers()

        return self.available_servers[:num_servers]

    def create_quotes_for_server(self, server: Tuple[str, int]) -> Quotes:
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

    try:
        # 创建独立的mootdx连接
        logger.info("进程 %d 正在连接服务器 %s:%d", worker_id, server[0], server[1])

        try:
            from mootdx.quotes import Quotes

            quotes = Quotes.factory(server=server, timeout=5, heartbeat=False)
            logger.info(
                "✅ 进程 %d 使用mootdx.Quotes连接成功: %s:%d", worker_id, server[0], server[1]
            )
        except Exception as e:
            logger.warning("进程 %d mootdx.Quotes连接失败: %s，尝试TdxHq_API降级", worker_id, e)
            # 降级方案：使用TdxHq_API
            try:
                from tdxpy.hq import TdxHq_API

                client = TdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)
                client.connect(server[0], server[1], time_out=5)
                quotes = QuotesWrapper(client, server)
                logger.info(
                    "✅ 进程 %d 使用TdxHq_API连接成功: %s:%d", worker_id, server[0], server[1]
                )
            except Exception as e2:
                logger.error("进程 %d TdxHq_API连接也失败: %s", worker_id, e2)
                return

        # 主循环：从队列获取任务并执行
        empty_count = 0  # 连续空队列计数

        while not stop_event.is_set():
            try:
                # 等待暂停信号
                pause_event.wait()

                # 获取任务（非阻塞）
                try:
                    task = task_queue.get_nowait()
                    empty_count = 0  # 重置空计数

                    symbol, interval, start_date = task
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
                        logger.debug("进程 %d 跳过空数据: %s %s", worker_id, symbol, interval)

                except queue.Empty:
                    empty_count += 1
                    if empty_count >= 10:  # 连续10次空队列则退出
                        logger.info("进程 %d 队列空，退出 (连续空%d次)", worker_id, empty_count)
                        break
                    time.sleep(0.5)  # 短暂等待

            except Exception as e:
                logger.error("进程 %d 处理任务异常: %s", worker_id, e)

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
        raw_data = quotes.client.get_security_bars(
            int(frequency), int(market), str(symbol), 0, int(offset)
        )

        if not raw_data:
            return None

        # 转换为DataFrame
        data = pd.DataFrame(raw_data)

        # 解码日期
        data = TdxDateTimeDecoder.decode_dataframe(data, interval)

        # 设置index
        if not data.empty and "datetime" in data.columns:
            data.index = data["datetime"]

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
    if "datetime" in data.columns:
        data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
        data = data[data["datetime"].notna()].copy()

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
            return filtered

        if "datetime" not in data.columns:
            return data

        if not pd.api.types.is_datetime64_any_dtype(data["datetime"]):
            datetime_series = pd.to_datetime(data["datetime"], errors="coerce")
        else:
            datetime_series = data["datetime"]

        valid_mask = datetime_series.notna()
        if not valid_mask.any():
            return pd.DataFrame()

        start_datetime = pd.Timestamp(start_date)
        date_mask = valid_mask & (datetime_series >= start_datetime)

        return data[date_mask].copy()

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
        self.server_pool = ServerPool(max_servers=server_pool_size, timeout=30)
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


    def get_all_market_stocks(self) -> Dict[str, List[Dict[str, any]]]:
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
    """多进程股票数据获取器"""

    def __init__(self, block_parser=None):
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
        self.server_pool = ServerPool(max_servers=max_processes, timeout=30)

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

        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        self.logger.info("=" * 60)
        self.logger.info("【多进程并行下载】开始增量下载K线数据")
        self.logger.info("  品种数量: %d", len(symbols))
        self.logger.info("  周期列表: %s", intervals)
        self.logger.info("  起始日期: %s", start_date)
        self.logger.info("  进程数: %d", self.num_processes)
        self.logger.info("=" * 60)

        try:
            # 步骤1：发现可用服务器
            available_servers = self.server_pool.discover_servers()[: self.num_processes]

            if not available_servers:
                self.logger.error("❌ 没有可用服务器，无法下载")
                return result

            num_servers = len(available_servers)
            self.logger.info("✅ 发现 %d 个可用服务器", num_servers)

            # 步骤2：构建任务列表
            tasks = [(symbol, interval, start_date) for symbol in symbols for interval in intervals]
            total_tasks = len(tasks)

            self.logger.info("✅ 任务列表构建完成: 总计 %d 个任务", total_tasks)

            # 清空队列
            self._clear_queues()

            # 填充任务队列
            for task in tasks:
                self.task_queue.put(task)

            # 初始化进度
            self._download_progress["is_downloading"] = True
            self._download_progress["completed"] = 0
            self._download_progress["total"] = total_tasks
            self._download_progress["start_time"] = datetime.now()

            # 步骤3：启动工作进程
            self._start_worker_processes(available_servers)

            # 步骤4：监控进度并收集结果
            result = self._monitor_progress_and_collect_results(total_tasks, progress_callback)

            # 等待进程自动退出
            time.sleep(6.0)

            # 步骤5：清理进程
            self._cleanup_processes()

            valid_count = sum(1 for v in result.values() if v is not None and not v.empty)
            empty_count = len(result) - valid_count

            self.logger.info("=" * 60)
            self.logger.info("【完成】多进程下载完成")
            self.logger.info("  总任务数: %d", total_tasks)
            self.logger.info("  下载结果数: %d", len(result))
            self.logger.info("  有效数据: %d", valid_count)
            self.logger.info("  空数据: %d", empty_count)

        except Exception as e:
            self.logger.error("多进程下载异常: %s", e, exc_info=True)
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
            if self.stop_event.is_set():
                break

            # 收集进度
            try:
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
                key, data_dict = self.result_queue.get_nowait()
                if data_dict is not None:
                    df = pd.DataFrame(data_dict)
                    if "datetime" in df.columns:
                        df["datetime"] = pd.to_datetime(df["datetime"])
                    results[key] = df
            except queue.Empty:
                pass

        return results

    def _drain_queues(self, results: Dict):
        """排空队列"""
        while True:
            try:
                key, data_dict = self.result_queue.get_nowait()
                if data_dict is not None:
                    df = pd.DataFrame(data_dict)
                    if "datetime" in df.columns:
                        df["datetime"] = pd.to_datetime(df["datetime"])
                    results[key] = df
            except queue.Empty:
                break

        extra_progress = 0
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
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
