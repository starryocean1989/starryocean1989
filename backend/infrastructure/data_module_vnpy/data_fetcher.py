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
import asyncio
import logging
import os
import threading
import time
import queue
from datetime import date, datetime
from multiprocessing import Manager, Process, cpu_count
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from backend.infrastructure.tdx_asyncio import (
    AsyncTdxHq_API,
    AsyncSmartIPPool,
    HQ_HOSTS_ALL,
)

from .config import config_manager
from .server_pool_manager import server_pool_manager

# ==================== (ServerManager 已删除，使用 tdx_asyncio.AsyncSmartIPPool) ====================
# ==================== (TdxDateTimeDecoder 已删除，tdx_asyncio 协议层已自动处理) ====================


# ==================== 工作进程函数（已废弃，使用异步版本） ====================
# download_worker_pooled 已废弃，不再使用同步 mootdx


# ==================== 异步工作进程函数 ====================


async def download_worker_async(
    worker_id,
    task_queue,
    result_queue,
    progress_queue,
    server_list,
    server_index,
    timeout,
    retry_times,
    stop_event,
    pause_event,
    connections_per_worker=30,
):
    """异步Worker - 每个进程维护多个 tdx_asyncio 连接

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        progress_queue: 进度队列
        server_list: 共享的可用服务器列表
        server_index: 共享的服务器索引（用于轮询）
        timeout: 连接超时时间
        retry_times: 重试次数（暂未使用）
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数（默认30）
    """
    logger = logging.getLogger(f"AsyncWorker-{worker_id}")
    logger.info(
        f"异步Worker {worker_id} 启动，PID: {os.getpid()}，连接数: {connections_per_worker}"
    )

    if not server_list:
        logger.error("无可用服务器")
        return

    # 创建多个 tdx_asyncio 连接 - 使用字典管理（服务器地址为键）
    # 关键原则：严格保证每个服务器只有1个连接（跨所有worker）
    connections = {}  # 字典：{(ip, port): client}
    server_list_local = []  # 本Worker的服务器列表（用于轮询）

    # 检查：确保不会对同一服务器建立多个连接
    # server_index 是全局共享计数器，所有worker共用
    # 如果 server_index 达到或超过服务器总数，说明服务器会被重复使用
    max_safe_connections = len(server_list)
    logger.info(
        f"Worker {worker_id}: 期望 {connections_per_worker} 个连接，"
        f"可用服务器 {len(server_list)} 个"
    )

    try:
        for i in range(connections_per_worker):
            # 原子操作：获取并递增全局服务器索引
            # 注意：不能在异步函数中使用 with lock，会阻塞事件循环
            # Manager.Value 的 get_lock() 是同步的，改为原子递增

            # 原子读取和递增（虽然不完美，但避免阻塞）
            current_idx = server_index.value

            # 关键检查：如果索引已经达到服务器总数，停止创建连接
            # 这样确保不会对同一服务器建立第二个连接
            if current_idx >= max_safe_connections:
                logger.warning(
                    f"Worker {worker_id}: 已达到服务器上限（{max_safe_connections}个），"
                    f"停止创建更多连接（当前{i}个）"
                )
                break

            # 递增索引（原子操作）
            server_index.value += 1
            idx = current_idx % len(server_list)
            server = server_list[idx]

            # 创建 tdx_asyncio 异步连接
            try:
                client = await AsyncTdxHq_API.factory(
                    server=server, timeout=timeout, heartbeat=False, raise_exception=False
                )
                if client:
                    # 使用服务器地址作为键存储连接
                    connections[server] = client
                    server_list_local.append(server)
                    logger.debug(
                        f"Worker {worker_id} 连接 → 服务器{server[0]}:{server[1]} "
                        f"（全局索引{current_idx}，本Worker第{len(connections)}个）"
                    )
                else:
                    logger.debug(
                        f"Worker {worker_id} 连接 建立失败: {server[0]}:{server[1]} (正常现象，会尝试其他服务器)"
                    )
            except Exception as e:
                logger.warning(f"Worker {worker_id} 连接 建立异常: {e}")

        logger.info(
            f"Worker {worker_id} 成功建立 {len(connections)} 个连接" f"（每个连接使用不同服务器）"
        )

        if not connections:
            logger.error(f"Worker {worker_id} 无可用连接，退出")
            return

        # 为每个连接创建下载协程
        async def download_loop(conn_id, client, server):
            processed = 0
            failed = 0

            while not stop_event.is_set():
                # 等待暂停事件
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 从队列获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    logger.debug(f"Worker {worker_id} 连接 {conn_id} 队列为空")
                    break
                except Exception as e:
                    logger.debug(f"Worker {worker_id} 连接 {conn_id} 获取任务失败: {e}")
                    break

                symbol, interval, start_date = task

                try:
                    # 纯异步下载（使用 tdx_asyncio）
                    data = await _download_single_kline_async(client, symbol, interval, start_date)

                    if data is not None and not data.empty:
                        await asyncio.to_thread(
                            result_queue.put, (f"{symbol}_{interval}", data.to_dict("records"))
                        )
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
                        processed += 1
                    else:
                        await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
                        failed += 1

                except Exception as e:
                    logger.debug(
                        f"Worker {worker_id} 连接 {conn_id} 下载 {symbol}_{interval} 失败: {e}"
                    )
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
                    failed += 1

            logger.info(
                f"Worker {worker_id} 连接 {conn_id} 完成, 成功: {processed}, 失败: {failed}"
            )
            return processed, failed

        # N个协程并发工作（字典方案：遍历服务器列表和字典）
        results = await asyncio.gather(
            *[
                download_loop(idx, connections[server], server)
                for idx, server in enumerate(server_list_local)
            ],
            return_exceptions=True,
        )

        # 统计总数
        total_processed = sum(r[0] for r in results if isinstance(r, tuple))
        total_failed = sum(r[1] for r in results if isinstance(r, tuple))
        logger.info(f"Worker {worker_id} 总计完成, 成功: {total_processed}, 失败: {total_failed}")

    finally:
        # 关闭所有连接（字典方案）
        for server, client in connections.items():
            try:
                # 🔧 检查连接是否还存在且未关闭
                if client and not client.closed:
                    await client.close()
                    logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 已关闭")
                else:
                    logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 已经关闭，跳过")
            except (ConnectionError, BrokenPipeError, OSError) as e:
                # 🔧 捕获常见的连接关闭异常，避免输出警告
                logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 关闭时连接已断开")
            except Exception as e:
                logger.debug(f"Worker {worker_id} 连接 {server[0]}:{server[1]} 关闭失败: {e}")


def _run_async_worker(*args):
    """在进程中运行异步事件循环的辅助函数"""
    import warnings

    # 🔧 抑制 socket.send() 相关的 ResourceWarning
    # 这些警告通常在连接已断开时尝试关闭连接时出现，不影响功能
    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")

    asyncio.run(download_worker_async(*args))


async def _download_single_kline_async(
    client: AsyncTdxHq_API, symbol: str, interval: str, start_date: Union[str, date]
) -> Optional[pd.DataFrame]:
    """下载单个品种的K线数据（异步版本，使用 tdx_asyncio）"""
    try:
        # 参数验证和转换
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        days_diff = (date.today() - start_date).days

        # 频率映射（tdx_asyncio 使用 category 参数）
        category_map = {"1d": 9, "5m": 5, "1m": 8}  # 9=日K, 5=5分钟, 8=1分钟
        category = category_map.get(interval, 9)

        # 计算下载数量
        offset_multipliers = {"1d": 1.5, "5m": 50, "1m": 250}
        multiplier = offset_multipliers.get(interval, 1.5)
        count = min(int(days_diff * multiplier), 800)

        # 市场代码判断
        if symbol.startswith("6"):
            market = 1  # 上海
        elif symbol.startswith("9") and len(symbol) == 6:
            market = 2  # 北交所
        else:
            market = 0  # 深圳

        # 调用 tdx_asyncio API
        try:
            raw_data = await client.get_security_bars(
                category=category, market=market, code=symbol, start=0, count=count
            )
            if not raw_data:
                return None
        except Exception as e:
            logging.getLogger(__name__).error(f"API调用失败 {symbol} {interval}: {e}")
            return None

        # 数据处理（tdx_asyncio 已自动处理日期格式）
        data = pd.DataFrame(raw_data)

        if data.empty or "datetime" not in data.columns:
            return None

        # 设置索引
        data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
        data = data.dropna(subset=["datetime"])

        if data.empty:
            return None

        data = data.set_index("datetime", drop=False)

        # 列名标准化
        column_mapping = {"vol": "volume", "amount": "turnover"}
        data = data.rename(columns=column_mapping)

        # 添加元数据
        data["symbol"] = symbol
        data["interval"] = interval

        # 数值类型转换
        for col in ["open", "high", "low", "close", "volume"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        # 日期过滤
        if pd.api.types.is_datetime64_any_dtype(data.index):
            start_timestamp = pd.Timestamp(start_date)
            filtered_data = data[data.index >= start_timestamp]
            data = filtered_data if isinstance(filtered_data, pd.DataFrame) else pd.DataFrame()

        return data if not data.empty else None

    except Exception as e:
        logging.getLogger(__name__).error(f"下载失败 {symbol} {interval}: {e}", exc_info=True)
        return None


# ==================== (旧StockSymbolManager已删除，使用symbol_management.SymbolLoader替代) ====================


# ==================== 多进程数据获取器 ====================


class MultiProcessStockFetcher:
    """多进程股票数据获取器（进程池+动态任务分配模式）"""

    def __init__(self, event_engine=None):
        self.logger = logging.getLogger(__name__)
        self.event_engine = event_engine

        # 使用 tdx_asyncio 的智能IP池（延迟初始化）
        self.ip_pool = None  # 将在下载时初始化

        # 进程池配置（动态计算，在download时根据服务器数量确定）
        self.num_processes = 1  # 初始值，将在下载时动态计算

        # 硬编码超时和重试参数（优化后的快速失败策略）
        self.timeout = 2  # 连接超时2秒
        self.retry_times = 0  # 不重试，直接换热备服务器

        # 异步连接配置
        self.async_connections_per_process = 30  # 每个进程30个异步连接

        self.logger.info(
            "初始化异步下载器: 超时=%d秒, 重试=%d次, 每进程连接数=%d",
            self.timeout,
            self.retry_times,
            self.async_connections_per_process,
        )

        # 多进程共享对象
        self.manager = None
        self.task_queue: Optional[queue.Queue] = None
        self.result_queue: Optional[queue.Queue] = None
        self.progress_queue: Optional[queue.Queue] = None
        self.stop_event = None
        self.pause_event = None

        self.processes: List[Process] = []

        # 事件发布器
        if event_engine:
            from .events import DownloadEventPublisher, EventPublisher

            self.download_publisher = DownloadEventPublisher(event_engine)
            self.log_publisher = EventPublisher(event_engine)
        else:
            self.download_publisher = None
            self.log_publisher = None

        # 异步下载管理
        self._download_thread = None
        self._download_lock = threading.Lock()
        self._download_progress = None  # 将在_init_multiprocess_objects中初始化

    def _init_multiprocess_objects(self):
        """初始化多进程对象"""
        if self.manager is None:
            self.manager = Manager()
            self.task_queue = self.manager.Queue()
            self.result_queue = self.manager.Queue()
            self.progress_queue = self.manager.Queue()
            self.stop_event = self.manager.Event()
            self.pause_event = self.manager.Event()
            self.pause_event.set()

        # 每次调用都重新初始化_download_progress
        if self.manager:
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
        """主下载方法 - 使用进程池+动态任务分配"""
        if not symbols:
            self.logger.error("品种列表为空")
            return {}

        intervals = intervals or ["1d", "5m", "1m"]
        total_tasks = len(symbols) * len(intervals)

        self.logger.info(
            f"开始多进程下载: {len(symbols)}品种 × {len(intervals)}周期 = {total_tasks}任务"
        )

        try:
            # 1. 从服务器池管理器获取排序后的最优服务器列表
            # 如果服务器池未运行，get_servers() 会抛出 RuntimeError，阻止下载
            available_servers = server_pool_manager.get_servers()
            self.logger.info(f"使用智能服务器池（已排序）: {len(available_servers)} 个服务器")
            # 打印最快的前5个服务器
            top5 = available_servers[:5]
            self.logger.info(f"最快的5个服务器: {top5}")

            # 1.5 动态计算进程数：服务器数/30向上取整
            import math

            optimal_processes = math.ceil(len(available_servers) / 30)
            self.num_processes = optimal_processes
            self.logger.info(
                f"动态计算进程数: {len(available_servers)}个服务器 / 30 = {optimal_processes}个进程"
            )
            self.logger.info(
                f"预计总并发: 进程1~{optimal_processes-1}各30连接, "
                f"进程{optimal_processes}有{len(available_servers) % 30 or 30}连接 "
                f"(总计{len(available_servers)}连接)"
            )

            # 2. 初始化Manager和队列
            self._init_multiprocess_objects()
            self._clear_queues()

            # 3. 创建共享服务器列表和索引
            assert self.manager is not None, "Manager未初始化"
            server_list = self.manager.list(available_servers)  # type: ignore
            server_index = self.manager.Value("i", 0)  # type: ignore

            # 4. 填充任务队列
            tasks = [(symbol, interval, start_date) for symbol in symbols for interval in intervals]
            assert self.task_queue is not None
            for task in tasks:
                self.task_queue.put(task)

            # 5. 设置进度状态
            if self._download_progress:
                self._download_progress.update(
                    {
                        "is_downloading": True,
                        "completed": 0,
                        "total": total_tasks,
                        "start_time": datetime.now().isoformat(),
                    }
                )

            # 6. 启动worker进程池
            self._start_worker_pool(server_list, server_index)

            # 7. 监控进度并收集结果
            results = self._monitor_progress_and_collect_results(total_tasks, progress_callback)

            # 8. 清理资源
            self._cleanup_processes()
            if self._download_progress:
                self._download_progress["is_downloading"] = False

            # 统计结果
            valid_count = sum(1 for v in results.values() if v is not None and not v.empty)
            self.logger.info(f"下载完成: {valid_count}/{total_tasks} 有效任务")

            return results

        except Exception as e:
            self.logger.error(f"多进程下载异常: {e}", exc_info=True)
            if self._download_progress:
                self._download_progress["is_downloading"] = False
            self._cleanup_processes()
            return {}

    def _start_worker_pool(self, server_list, server_index):
        """启动异步worker进程池

        Args:
            server_list: Manager.list()共享的服务器列表
            server_index: Manager.Value()共享的服务器索引
        """
        for i in range(self.num_processes):
            try:
                # 使用异步worker
                p = Process(
                    target=_run_async_worker,
                    args=(
                        i,
                        self.task_queue,
                        self.result_queue,
                        self.progress_queue,
                        server_list,
                        server_index,
                        self.timeout,
                        self.retry_times,
                        self.stop_event,
                        self.pause_event,
                        self.async_connections_per_process,  # 传递异步连接数
                    ),
                )

                p.start()
                self.processes.append(p)
                self.logger.debug(f"启动异步进程 {i} (PID: {p.pid})")

                # 给进程一点启动时间
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"启动进程{i}失败: {e}")

        self.logger.info(f"启动{len(self.processes)}个工作进程（进程池模式）")

        # 等待所有进程启动完成
        time.sleep(0.5)

    def _monitor_progress_and_collect_results(
        self, total_tasks: int, progress_callback
    ) -> Dict[str, pd.DataFrame]:
        """改进的监控和结果收集"""
        results = {}
        completed = 0
        timeout_count = 0
        max_timeout_count = 600  # ✅ 增加到60秒（600 * 0.1秒），给足时间下载

        self.logger.info(
            f"开始异步下载监控: {self.num_processes}进程 × {self.async_connections_per_process}连接 = "
            f"{self.num_processes * self.async_connections_per_process}并发, 总任务数: {total_tasks}"
        )

        while completed < total_tasks:
            if self.stop_event and self.stop_event.is_set():
                self.logger.info("检测到停止信号，退出监控")
                break

            # 收集进度
            progress_received = False
            try:
                if self.progress_queue is not None:
                    progress_data = self.progress_queue.get(timeout=0.1)
                    # 兼容新格式：(symbol, interval, status) 或旧格式：(symbol, interval)
                    if len(progress_data) == 3:
                        symbol, interval, status = progress_data
                    else:
                        symbol, interval = progress_data
                        status = "unknown"

                    completed += 1
                    progress_received = True
                    timeout_count = 0  # 重置超时计数

                    if self._download_progress:
                        self._download_progress["completed"] = completed
                        self._download_progress["current_symbol"] = symbol
                        self._download_progress["current_interval"] = interval

                    if progress_callback:
                        progress_callback(completed, total_tasks, symbol, interval)

                    self.logger.debug(f"收到进度: {symbol} {interval} ({completed}/{total_tasks})")
            except queue.Empty:
                timeout_count += 1
                if timeout_count >= max_timeout_count:
                    self.logger.warning(
                        f"进度监控超时（{max_timeout_count * 0.1}秒），已完成: {completed}/{total_tasks}"
                    )
                    # ✅ 检查所有进程状态并诊断
                    alive_processes = [p for p in self.processes if p.is_alive()]
                    self.logger.warning(f"存活进程数: {len(alive_processes)}/{len(self.processes)}")

                    # ✅ 检查队列状态
                    try:
                        task_qsize = self.task_queue.qsize() if self.task_queue else 0
                        progress_qsize = self.progress_queue.qsize() if self.progress_queue else 0
                        result_qsize = self.result_queue.qsize() if self.result_queue else 0
                        self.logger.warning(
                            f"队列状态 - 任务: {task_qsize}, 进度: {progress_qsize}, 结果: {result_qsize}"
                        )
                    except Exception as e:
                        self.logger.debug(f"检查队列状态失败: {e}")

                    if not alive_processes:
                        self.logger.warning("所有进程已结束，但任务未完成！强制退出监控")
                        break

                    # ✅ 重置超时计数，继续等待（进程还在工作）
                    timeout_count = 0
                    self.logger.info("进程仍在运行，重置超时计数器，继续等待...")

            # 收集结果（非阻塞）
            try:
                if self.result_queue:
                    key, data_dict = self.result_queue.get_nowait()
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        results[key] = df
                        self.logger.debug(f"收到结果: {key} ({len(df)} 条数据)")
            except queue.Empty:
                pass

        # 最后收集剩余的结果
        self.logger.info("收集剩余结果...")
        remaining_results = 0
        while True:
            try:
                if self.result_queue:
                    key, data_dict = self.result_queue.get_nowait()
                    if data_dict is not None:
                        df = pd.DataFrame(data_dict)
                        results[key] = df
                        remaining_results += 1
                        self.logger.debug(f"收集剩余结果: {key} ({len(df)} 条数据)")
            except queue.Empty:
                break

        if remaining_results > 0:
            self.logger.info(f"收集到 {remaining_results} 个剩余结果")

        self.logger.info(f"监控完成: 收到 {len(results)} 个结果，完成 {completed} 个任务")
        return results

    def _cleanup_processes(self):
        """清理所有工作进程"""
        if not self.processes:
            return

        for p in self.processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)

        self.processes.clear()
        self.logger.info("进程清理完成")

    def _clear_queues(self):
        """清空所有队列"""
        for q in [self.task_queue, self.result_queue, self.progress_queue]:
            if q is not None:
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

    def set_server_count(self, num_servers: int) -> None:
        """
        动态设置进程池大小

        Args:
            num_servers: 进程数量（1-30）
        """
        cpu_cores = cpu_count()
        self.num_processes = min(num_servers, cpu_cores * 2, 30)
        self.logger.info("进程池大小已更新: %d", self.num_processes)

    def get_download_progress(self) -> Dict[str, Any]:
        """
        获取下载进度（供外部查询）

        Returns:
            进度信息字典
        """
        if self._download_progress is None:
            return {
                "is_downloading": False,
                "completed": 0,
                "total": 0,
                "current_symbol": "",
                "current_interval": "",
                "start_time": None,
            }

        # 返回进度字典的副本
        return dict(self._download_progress)

    def stop_download(self):
        """停止当前下载任务"""
        if self.stop_event:
            self.stop_event.set()
            self.logger.info("已发送停止信号")
        else:
            self.logger.warning("停止事件未初始化")

    def pause_download(self):
        """暂停当前下载任务"""
        if self.pause_event:
            self.pause_event.clear()
            self.logger.info("已发送暂停信号")
        else:
            self.logger.warning("暂停事件未初始化")

    def resume_download(self):
        """恢复暂停的下载任务"""
        if self.pause_event:
            self.pause_event.set()
            self.logger.info("已发送恢复信号")
        else:
            self.logger.warning("恢复事件未初始化")

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

            # 初始化多进程对象（如果还没初始化）
            self._init_multiprocess_objects()

            # 重置下载状态
            if self._download_progress:
                self._download_progress.update(
                    {
                        "is_downloading": False,
                        "completed": 0,
                        "total": 0,
                        "current_symbol": "",
                        "current_interval": "",
                        "start_time": None,
                    }
                )

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
            # 定义进度回调（限制频率，避免UI崩溃）
            def progress_callback(completed: int, total: int, symbol: str, interval: str):
                # ✅ 方案2：严格限制UI更新频率
                should_push = (
                    completed == 1  # 第一个任务
                    or completed == total  # 最后一个任务
                    or completed % 200 == 0  # 每200个任务更新一次（降低频率）
                )

                # ✅ 使用日志输出，避免UI更新
                if completed % 500 == 0 or completed == 1 or completed == total:
                    self.logger.info(
                        f"下载进度: {completed}/{total} ({completed*100/total:.1f}%) - {symbol} {interval}"
                    )

                # ✅ 方案1：添加异常保护，使用信号传递
                if should_push and self.download_publisher:
                    try:
                        progress_pct = (completed / total) * 100
                        self.download_publisher.push_download_progress_event(
                            "incremental_kline",
                            progress_pct,
                            completed,
                            total,
                            f"{symbol} {interval}",
                        )
                    except Exception as e:
                        # 捕获异常避免崩溃
                        self.logger.debug(f"推送进度事件失败: {e}")

            # 🔧 修复：直接使用当前实例的download_incremental_kline，而不是创建新实例
            # 获取品种列表
            if market_types:
                symbols = symbol_loader.extract_codes_by_market(market_types)
            else:
                symbols = symbol_loader.extract_all_codes()

            if not symbols:
                result = {
                    "success": False,
                    "total_tasks": 0,
                    "completed": 0,
                    "saved_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "message": "未找到可下载的品种",
                }
            else:
                # 直接调用当前实例的方法，确保_download_progress被正确更新
                download_results = self.download_incremental_kline(
                    symbols=symbols,
                    start_date=start_date,
                    intervals=["1d", "5m", "1m"],
                    progress_callback=progress_callback,
                )

                # 🔍 诊断日志：检查下载结果
                self.logger.info("=" * 60)
                self.logger.info("🔍 下载结果诊断")
                self.logger.info(f"download_results类型: {type(download_results)}")
                self.logger.info(f"download_results键数量: {len(download_results)}")
                if download_results:
                    # 统计数据状态
                    none_count = sum(1 for v in download_results.values() if v is None)
                    empty_count = sum(
                        1
                        for v in download_results.values()
                        if v is not None and (not isinstance(v, pd.DataFrame) or v.empty)
                    )
                    valid_count = len(download_results) - none_count - empty_count
                    self.logger.info(f"  - None数据: {none_count}")
                    self.logger.info(f"  - 空DataFrame: {empty_count}")
                    self.logger.info(f"  - 有效数据: {valid_count}")

                    # 显示前3个结果的详情
                    for i, (key, data) in enumerate(list(download_results.items())[:3]):
                        if data is not None:
                            if isinstance(data, pd.DataFrame):
                                self.logger.info(f"  示例{i+1}: {key} -> DataFrame({len(data)}行)")
                            else:
                                self.logger.info(f"  示例{i+1}: {key} -> {type(data).__name__}")
                        else:
                            self.logger.info(f"  示例{i+1}: {key} -> None")
                else:
                    self.logger.critical("❌ download_results为空字典！")
                self.logger.info("=" * 60)

                # 存储数据
                saved_count = 0
                for key, data_records in download_results.items():
                    # 🔧 修复DataFrame判断问题
                    # data_records可能是list/dict/DataFrame/None，需要安全判断
                    if data_records is not None:
                        symbol, interval = key.split("_", 1)
                        # 如果已经是DataFrame，直接使用；否则转换
                        if isinstance(data_records, pd.DataFrame):
                            data_df = data_records
                        else:
                            data_df = pd.DataFrame(data_records)

                        if not data_df.empty:
                            self.logger.info(f"💾 正在保存: {symbol} {interval} ({len(data_df)}行)")
                            result_path = storage_manager.save_kline(symbol, interval, data_df)
                            if result_path:
                                saved_count += 1
                                self.logger.info(f"✅ 保存成功: {result_path}")
                            else:
                                self.logger.error(f"❌ 保存失败: {symbol} {interval}")

                # 🔍 保存统计日志
                self.logger.info("=" * 60)
                self.logger.info("📊 保存统计")
                self.logger.info(f"总任务数: {len(symbols) * 3}")
                self.logger.info(f"下载结果数: {len(download_results)}")
                self.logger.info(f"✅ 保存成功: {saved_count}")
                self.logger.info(f"❌ 保存失败/跳过: {len(download_results) - saved_count}")
                self.logger.info("=" * 60)

                result = {
                    "success": True,
                    "total_tasks": len(symbols) * 3,  # 3个周期
                    "completed": len(download_results),
                    "saved_count": saved_count,
                    "skipped_count": 0,
                    "failed_count": len(download_results) - saved_count,
                    "message": f"下载完成，保存了 {saved_count} 个品种的数据",
                }

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
            should_push = completed % 100 == 0 or completed == 1 or completed == total
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
    if fetcher.stop_event and fetcher.stop_event.is_set():
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
        event_callback(
            "incremental_kline", "success", saved_count, f"成功保存{saved_count}个数据集"
        )

    return {
        "success": True,
        "total_tasks": total_tasks,
        "completed": len(download_results),
        "saved_count": saved_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "message": f"成功保存{saved_count}个数据集（跳过{skipped_count}个空数据）",
    }
