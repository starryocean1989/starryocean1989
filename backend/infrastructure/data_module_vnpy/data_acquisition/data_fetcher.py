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
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd

from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

from ..load_balancer.server_pool_manager import (
    server_pool_manager,
    AdaptiveDownloadConfig,
)
from ..load_balancer import (
    NetworkTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)

# ==================== (ServerManager 已删除，使用 tdx_asyncio.AsyncSmartIPPool) ====================
# ==================== (TdxDateTimeDecoder 已删除，tdx_asyncio 协议层已自动处理) ====================


# ==================== 负载均衡任务类 ====================


class KlineDownloadTask(NetworkTask):
    """K线批量下载任务

    用于批量下载股票K线数据，支持多周期（日线、5分钟、1分钟）。
    """

    def __init__(self, name: str, task_count: int):
        """初始化K线下载任务

        Args:
            name: 任务名称
            task_count: 预计任务数量（品种数×周期数）
        """
        super().__init__(name)
        self.task_count = task_count
        # 更新预估连接数
        self.metrics.estimated_connections = min(task_count * 2, 640)

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="kline_batch_download",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.MIXED,  # 网络+磁盘
            critical_metrics=[
                "network_speed",
                "disk_io_speed",
                "average_io_latency_ms",
                "concurrent_task_count",
            ],
            estimated_duration=300,  # 预计5分钟
            estimated_memory_mb=320,  # 640连接×0.5MB
            estimated_connections=640,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行K线下载（占位方法）

        实际下载由MultiProcessStockFetcher.download_incremental_kline执行。
        """
        # 这个方法不会被直接调用
        return {}


class IPODownloadTask(NetworkTask):
    """IPO日期批量下载任务

    用于批量下载股票IPO日期信息。
    """

    def __init__(self, name: str, task_count: int):
        """初始化IPO下载任务

        Args:
            name: 任务名称
            task_count: 预计任务数量（品种数）
        """
        super().__init__(name)
        self.task_count = task_count
        # IPO请求比K线轻量，连接数更少
        self.metrics.estimated_connections = min(task_count, 200)

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="ipo_batch_download",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=[
                "network_speed",
                "concurrent_task_count",
            ],
            estimated_duration=60,  # 预计1分钟
            estimated_memory_mb=50,  # 200连接×0.25MB（轻量级请求）
            estimated_connections=200,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行IPO下载（占位方法）

        实际下载由MultiProcessStockFetcher.download_ipo_dates执行。
        """
        # 这个方法不会被直接调用
        return {}


# ==================== 工作进程函数（已废弃，使用异步版本） ====================
# download_worker_pooled 已废弃，不再使用同步 mootdx


# ==================== 异步工作进程函数 ====================


async def download_worker_two_phase_async(
    worker_id,
    task_queue,
    result_queue,
    progress_queue,
    regular_servers,
    standby_servers,
    broker_map,
    threshold,
    timeout,
    stop_event,
    pause_event,
    connections_per_worker=30,
):
    """两段式异步Worker - 先用regular服务器，剩余任务用standby服务器

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        progress_queue: 进度队列
        regular_servers: 乱序服务器列表
        standby_servers: 热备服务器列表
        broker_map: 服务器到券商的映射
        threshold: 任务剩余阈值（切换到第二阶段的触发点）
        timeout: 连接超时时间
        stop_event: 停止事件
        pause_event: 暂停事件
        connections_per_worker: 每个worker的异步连接数
    """
    logger = logging.getLogger(f"TwoPhaseWorker-{worker_id}")
    logger.info("两段式Worker %s 启动，PID：%s", worker_id, os.getpid())

    # ========== 第一阶段：使用regular服务器 ==========
    logger.info(
        "[Phase1] Worker %s 正在第一阶段，使用 %s 个regular连接", worker_id, connections_per_worker
    )

    phase1_connections = {}
    phase1_servers = []

    try:
        # 建立regular连接
        for i in range(min(connections_per_worker, len(regular_servers))):
            if i >= len(regular_servers):
                break
            server = regular_servers[i]
            try:
                client = await AsyncTdxHq_API.factory(
                    server=server, timeout=timeout, heartbeat=False, raise_exception=False
                )
                if client:
                    phase1_connections[server] = client
                    phase1_servers.append(server)
                    broker = broker_map.get(server, "未知")
                    logger.debug(
                        "[Phase1] Worker %s 连接成功: %s %s:%s",
                        worker_id,
                        broker,
                        server[0],
                        server[1],
                    )
            except Exception:
                logger.debug("[Phase1] Worker %s 连接失败：%s:%s", worker_id, server[0], server[1])

        logger.info("[Phase1] Worker %s 建立 %s 个连接", worker_id, len(phase1_connections))

        if not phase1_connections:
            logger.error("[Phase1] Worker %s 无可用连接，退出", worker_id)
            return

        # 第一阶段下载逻辑
        async def phase1_download_loop(conn_id, client, _server):
            processed = 0
            failed = 0

            while not stop_event.is_set():
                # 检查任务队列大小
                try:
                    queue_size = task_queue.qsize()
                    if queue_size <= threshold:
                        logger.info(
                            "[Phase1] Worker %s 连接 %s 达到阈值（剩余%s），停止",
                            worker_id,
                            conn_id,
                            queue_size,
                        )
                        break
                except Exception:
                    pass  # qsize() 可能在某些平台不可用

                # 等待暂停
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    break
                except Exception as e:
                    logger.debug("[Phase1] Worker %s 获取任务失败：%s", worker_id, e)
                    break

                symbol, interval, start_date = task

                try:
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
                        "[Phase1] Worker %s 下载失败 %s_%s: %s", worker_id, symbol, interval, e
                    )
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
                    failed += 1

            return processed, failed

        # 并发执行第一阶段
        results = await asyncio.gather(
            *[
                phase1_download_loop(idx, phase1_connections[server], server)
                for idx, server in enumerate(phase1_servers)
            ],
            return_exceptions=True,
        )

        total_phase1 = sum(r[0] for r in results if isinstance(r, tuple))
        logger.info("[Phase1] Worker %s 完成，下载：%s", worker_id, total_phase1)

    finally:
        # 关闭所有phase1连接
        for server, client in phase1_connections.items():
            try:
                if client and not client.closed:
                    await client.close()
            except Exception:
                pass
        logger.debug("[Phase1] Worker %s 所有连接已关闭", worker_id)

    # ========== 预热阶段：连接standby服务器 ==========
    logger.info("[Warmup] Worker %s 开始预热热备服务器...", worker_id)

    phase2_connections = {}
    phase2_servers = []
    failed_standby = []
    warmup_timeout = 1.5

    # 为每个worker分配standby服务器
    worker_standby_start = worker_id * connections_per_worker
    worker_standby_servers = standby_servers[
        worker_standby_start : worker_standby_start + connections_per_worker
    ]

    # 连接standby服务器
    for server in worker_standby_servers:
        try:
            client = await asyncio.wait_for(
                AsyncTdxHq_API.factory(
                    server=server, timeout=warmup_timeout, heartbeat=False, raise_exception=False
                ),
                timeout=warmup_timeout,
            )
            if client:
                phase2_connections[server] = client
                phase2_servers.append(server)
                broker = broker_map.get(server, "未知")
                logger.debug(
                    "[Warmup] Worker %s 热备连接成功: %s %s:%s",
                    worker_id,
                    broker,
                    server[0],
                    server[1],
                )
            else:
                failed_standby.append(server)
                broker = broker_map.get(server, "未知")
                logger.warning(
                    "[Warmup] Worker %s 热备连接失败: %s %s:%s",
                    worker_id,
                    broker,
                    server[0],
                    server[1],
                )
        except asyncio.TimeoutError:
            failed_standby.append(server)
            broker = broker_map.get(server, "未知")
            logger.warning(
                "[Warmup] Worker %s 热备连接超时: %s %s:%s", worker_id, broker, server[0], server[1]
            )
        except Exception as e:
            failed_standby.append(server)
            logger.debug(
                "[Warmup] Worker %s 热备连接异常: %s:%s - %s", worker_id, server[0], server[1], e
            )

    # 尝试从regular池替换失败的standby
    if failed_standby:
        logger.info(
            "[Warmup] Worker %s 尝试替换 %s 个失败的热备服务器...", worker_id, len(failed_standby)
        )
        used_brokers = set(broker_map.get(s, "未知") for s in phase2_servers)

        for failed_server in failed_standby:
            failed_broker = broker_map.get(failed_server, "未知")
            # 从regular服务器中找不同券商的替换
            for regular_server in regular_servers:
                if regular_server in phase2_servers:
                    continue
                regular_broker = broker_map.get(regular_server, "未知")
                if regular_broker != failed_broker and regular_broker not in used_brokers:
                    try:
                        client = await asyncio.wait_for(
                            AsyncTdxHq_API.factory(
                                server=regular_server,
                                timeout=warmup_timeout,
                                heartbeat=False,
                                raise_exception=False,
                            ),
                            timeout=warmup_timeout,
                        )
                        if client:
                            phase2_connections[regular_server] = client
                            phase2_servers.append(regular_server)
                            used_brokers.add(regular_broker)
                            logger.info(
                                "[Warmup] Worker %s 替换成功: %s %s:%s",
                                worker_id,
                                regular_broker,
                                regular_server[0],
                                regular_server[1],
                            )
                            break
                    except Exception:
                        continue

    logger.info("[Warmup] Worker %s 预热完成，热备连接: %s 个", worker_id, len(phase2_connections))

    # 降级检查
    if len(phase2_connections) < 10:
        logger.warning("[Warmup] Worker %s 热备连接不足10个，但继续执行", worker_id)

    # ========== 第二阶段：使用standby服务器 ==========
    if not phase2_connections:
        logger.error("[Phase2] Worker %s 无可用热备连接，跳过第二阶段", worker_id)
        return

    logger.info(
        "[Phase2] Worker %s 开始第二阶段，使用 %s 个热备连接", worker_id, len(phase2_connections)
    )

    try:
        # 第二阶段下载逻辑
        async def phase2_download_loop(conn_id, client, _server):
            processed = 0
            failed = 0

            while not stop_event.is_set():
                # 等待暂停
                while not pause_event.is_set():
                    if stop_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                if stop_event.is_set():
                    break

                # 获取任务
                try:
                    task = await asyncio.to_thread(task_queue.get, timeout=0.5)
                except queue.Empty:
                    logger.debug("[Phase2] Worker %s 连接 %s 队列为空", worker_id, conn_id)
                    break
                except Exception as e:
                    logger.debug("[Phase2] Worker %s 获取任务失败: %s", worker_id, e)
                    break

                symbol, interval, start_date = task

                try:
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
                        "[Phase2] Worker %s 下载失败 %s_%s: %s", worker_id, symbol, interval, e
                    )
                    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
                    failed += 1

            return processed, failed

        # 并发执行第二阶段
        results = await asyncio.gather(
            *[
                phase2_download_loop(idx, phase2_connections[server], server)
                for idx, server in enumerate(phase2_servers)
            ],
            return_exceptions=True,
        )

        total_phase2 = sum(r[0] for r in results if isinstance(r, tuple))
        logger.info("[Phase2] Worker %s 完成，下载: %s", worker_id, total_phase2)

    finally:
        # 关闭所有phase2连接
        for server, client in phase2_connections.items():
            try:
                if client and not client.closed:
                    await client.close()
            except Exception:
                pass
        logger.info("[Phase2] Worker %s 所有热备连接已关闭", worker_id)


def _run_two_phase_worker(*args):
    """在进程中运行两段式异步事件循环的辅助函数"""
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")
    asyncio.run(download_worker_two_phase_async(*args))


async def download_worker_async(
    worker_id,
    task_queue,
    result_queue,
    progress_queue,
    server_list,
    server_index,
    timeout,
    _retry_times,
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
                logger.warning("Worker %s 连接 建立异常: %s", worker_id, e)

        logger.info(
            "Worker %s 成功建立 %s 个连接（每个连接使用不同服务器）", worker_id, len(connections)
        )

        if not connections:
            logger.error("Worker %s 无可用连接，退出", worker_id)
            return

        # 为每个连接创建下载协程
        async def download_loop(conn_id, client, _server):
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
                    logger.debug("Worker %s 连接 %s 队列为空", worker_id, conn_id)
                    break
                except Exception as e:
                    logger.debug("Worker %s 连接 %s 获取任务失败: %s", worker_id, conn_id, e)
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
            except (ConnectionError, BrokenPipeError, OSError):
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


# ==================== IPO日期下载函数 ====================


async def _download_single_ipo_async(
    client: AsyncTdxHq_API, symbol: str, market: int
) -> tuple[Optional[date], int, dict]:
    """下载单个品种的IPO日期和行业代码（异步版本）

    Args:
        client: tdx_asyncio客户端
        symbol: 品种代码
        market: 市场代码（0=深圳, 1=上海, 2=北京）

    Returns:
        (IPO日期或None, 行业代码, 完整finance_info)
        - (None, 0, {}): 服务器问题，需要重试
        - (None, >0, {...}): 未上市品种，不重试
        - (date, >0, {...}): 已上市品种
    """
    import logging

    local_logger = logging.getLogger(__name__)

    try:
        finance_info = await client.get_finance_info(market, symbol)

        # 如果finance_info为None，视为服务器问题
        if finance_info is None:
            return None, 0, {}

        # 类型断言：此时finance_info一定是dict类型
        assert isinstance(finance_info, dict)

        ipo_timestamp = finance_info.get("ipo_date", 0)
        industry = finance_info.get("industry", 0)

        if ipo_timestamp and ipo_timestamp > 0:
            ipo_str = str(int(ipo_timestamp)).zfill(8)
            if len(ipo_str) == 8:
                return datetime.strptime(ipo_str, "%Y%m%d").date(), industry, finance_info

        # ipo_date=0，返回None、industry和完整数据
        return None, industry, finance_info
    except Exception as e:
        local_logger.debug("查询IPO失败 %s: %s", symbol, e)
        # 异常视为服务器问题
        return None, 0, {}


async def download_ipo_dates_simple(
    tasks_list: list[tuple[str, int]],
    num_coroutines: int = 100,
    progress_callback=None,
) -> tuple[dict, list, list]:
    """单进程多协程IPO下载（简化版）

    Args:
        tasks_list: 任务列表 [(symbol, market), ...]
        num_coroutines: 协程数量（默认100）
        progress_callback: 进度回调函数 callback(current, total, status)

    Returns:
        (results, unlisted_data, failed_tasks)
        - results: {symbol: ipo_date} 已上市品种
        - unlisted_data: [{'symbol': str, 'finance_info': dict}, ...] 未上市品种
        - failed_tasks: [(symbol, market), ...] 失败的任务
    """
    import asyncio
    import logging
    from ..load_balancer.server_pool_manager import get_random_servers

    local_logger = logging.getLogger(__name__)

    if not tasks_list:
        return {}, [], []

    local_logger.info(
        "开始单进程多协程IPO下载: %s个品种, %s个协程", len(tasks_list), num_coroutines
    )

    # 1. 准备连接池
    servers = get_random_servers(count=num_coroutines)
    local_logger.info("获取到 %s 个服务器", len(servers))

    # 2. 创建异步连接（并发连接以提速）
    async def connect_single_server(server):
        """并发连接单个服务器"""
        server_ip = None
        server_port = None
        try:
            client = AsyncTdxHq_API(heartbeat=True, auto_retry=False, raise_exception=False)
            # server 可能是元组 (ip, port) 或字典 {'ip': ..., 'port': ...}
            if isinstance(server, tuple):
                server_ip, server_port = server
            elif isinstance(server, dict):
                server_ip = server.get("ip", "")
                server_port = server.get("port", 0)
            else:
                return None

            await client.connect(server_ip, server_port, time_out=5)  # 缩短超时到5秒
            return client
        except Exception as e:
            local_logger.debug(f"连接服务器 {server_ip}:{server_port} 失败: {e}")
            return None

    # 并发连接所有服务器
    local_logger.info(f"开始并发连接 {len(servers)} 个服务器...")
    connection_tasks = [connect_single_server(server) for server in servers]
    connected_clients = await asyncio.gather(*connection_tasks, return_exceptions=True)

    # 过滤成功的连接
    clients: List[AsyncTdxHq_API] = []
    for c in connected_clients:
        if isinstance(c, AsyncTdxHq_API):
            clients.append(c)

    if not clients:
        local_logger.error("无法连接任何服务器")
        return {}, [], tasks_list

    local_logger.info("成功连接 %s 个服务器", len(clients))

    # 3. 结果收集
    results = {}  # {symbol: ipo_date}
    unlisted_data = []  # [{'symbol': str, 'finance_info': dict}, ...]
    failed_tasks = []  # [(symbol, market), ...]
    completed_count = 0
    total_count = len(tasks_list)

    # 4. 并发下载
    async def download_single_task(task, client):
        nonlocal completed_count
        symbol, market = task

        try:
            ipo_date, industry, finance_info = await _download_single_ipo_async(
                client, symbol, market
            )

            if ipo_date is not None:
                # 已上市
                results[symbol] = ipo_date
                status = "success"
            elif industry > 0:
                # 检查是否是数据异常的品种（有industry但其他财务数据全为0）
                # 判断关键字段：zongzichan, liudongzichan, zhuyingshouru
                is_data_valid = (
                    finance_info.get("zongzichan", 0) > 0
                    or finance_info.get("liudongzichan", 0) > 0
                    or finance_info.get("zhuyingshouru", 0) > 0
                )

                if is_data_valid:
                    # 真正的未上市品种（有完整财务数据）
                    unlisted_data.append(
                        {"symbol": symbol, "market": market, "finance_info": finance_info}
                    )
                    status = "unlisted"
                else:
                    # 数据异常（只有industry但无其他财务数据），视为失败重试
                    local_logger.debug(
                        f"品种 {symbol} 财务数据异常，仅有industry={industry}，其他字段为0"
                    )
                    failed_tasks.append(task)
                    status = "retry"
            else:
                # 服务器问题，稍后重试
                failed_tasks.append(task)
                status = "retry"

            completed_count += 1

            # 动态延时机制
            remaining = total_count - completed_count
            if remaining <= 30:
                await asyncio.sleep(0.2)
            elif remaining <= 100:
                await asyncio.sleep(0.1)
            elif remaining <= 200:
                await asyncio.sleep(0.05)

            # 进度回调
            if progress_callback:
                progress_callback(completed_count, total_count, status)

            # 输出进度
            if completed_count % 100 == 0:
                print(
                    f"进度: {completed_count}/{total_count} ({completed_count/total_count*100:.1f}%)"
                )

        except Exception as e:
            local_logger.debug("下载 %s 失败: %s", symbol, e)
            failed_tasks.append(task)
            completed_count += 1

    # 5. 分批并发执行（每批1000个）
    for batch_start in range(0, len(tasks_list), 1000):
        batch_end = min(batch_start + 1000, len(tasks_list))
        batch_tasks = tasks_list[batch_start:batch_end]

        # 使用asyncio.gather并发执行
        tasks_coroutines = []
        for i, task in enumerate(batch_tasks):
            client = clients[i % len(clients)]  # 轮询分配客户端
            tasks_coroutines.append(download_single_task(task, client))

        await asyncio.gather(*tasks_coroutines, return_exceptions=True)

    # 6. 重试失败的品种（最多5次，使用现有连接）
    for retry_round in range(5):
        if not failed_tasks:
            break

        local_logger.info("第%s次重试: %s个品种", retry_round + 1, len(failed_tasks))
        print(f"⚠️ 重试 {len(failed_tasks)} 个失败品种 (第{retry_round + 1}/5次)")

        # 不关闭连接，直接使用现有的clients进行重试
        # 如果失败次数过多（>=3次）或连接数不足，则切换服务器
        if retry_round >= 3 or len(clients) < 10:
            local_logger.info("第%s次重试：切换服务器...", retry_round + 1)
            print("   → 切换服务器以提升成功率")

            # 关闭旧连接
            for client in clients:
                try:
                    await client.close()
                except Exception:
                    pass

            # 重新获取服务器并创建新连接
            retry_servers = get_random_servers(count=min(num_coroutines, len(failed_tasks) * 2))
            local_logger.info("重试获取到 %s 个新服务器", len(retry_servers))

            clients = []
            for i, server in enumerate(retry_servers):
                server_ip = None
                server_port = None
                try:
                    client = AsyncTdxHq_API(heartbeat=True, auto_retry=False, raise_exception=False)
                    if isinstance(server, tuple):
                        server_ip, server_port = server
                    elif isinstance(server, dict):
                        server_ip = server.get("ip", "")
                        server_port = server.get("port", 0)
                    else:
                        continue

                    await client.connect(server_ip, server_port, time_out=10)
                    clients.append(client)
                except Exception as e:
                    local_logger.debug("重试连接服务器 %s:%s 失败: %s", server_ip, server_port, e)

            if not clients:
                local_logger.warning("第%s次重试：无法连接任何服务器，停止重试", retry_round + 1)
                break

        # 使用现有或新建的连接进行重试
        retry_batch = failed_tasks[:]
        failed_tasks.clear()

        tasks_coroutines = []
        for i, task in enumerate(retry_batch):
            client = clients[i % len(clients)]
            tasks_coroutines.append(download_single_task(task, client))

        await asyncio.gather(*tasks_coroutines, return_exceptions=True)

    # 7. 关闭连接
    for client in clients:
        try:
            await client.close()
        except Exception:
            pass

    local_logger.info(
        f"下载完成: 已上市{len(results)}个, 未上市{len(unlisted_data)}个, 失败{len(failed_tasks)}个"
    )

    return results, unlisted_data, failed_tasks


async def download_worker_ipo_async(
    worker_id,
    task_queue,
    result_queue,
    progress_queue,
    server_list,
    _server_index,
    timeout,
    _retry_times,
    stop_event,
    pause_event,
    connections_per_worker=30,
    unlisted_debug_queue=None,
):
    """IPO下载Worker（异步版本，复用K线下载架构）

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
        unlisted_debug_queue: 用于收集unlisted品种的完整数据（调试用）
    """
    worker_logger = logging.getLogger(__name__)
    worker_logger.info("Worker %s 启动 (IPO模式)", worker_id)

    try:
        # 从共享服务器列表中获取N个服务器（每个协程1个）
        server_list_local = list(server_list)[:connections_per_worker]

        if not server_list_local:
            worker_logger.error("Worker %s 无可用服务器，退出", worker_id)
            return

        # 为每个服务器创建客户端连接
        connections = {}
        for server in server_list_local:
            try:
                client = await AsyncTdxHq_API.factory(server, timeout=timeout)
                if client:
                    connections[server] = client
                    worker_logger.debug(
                        "Worker %s 连接到服务器 %s:%s", worker_id, server[0], server[1]
                    )
            except Exception as e:
                worker_logger.debug("Worker %s 连接失败 %s: %s", worker_id, server, e)

        if not connections:
            worker_logger.error("Worker %s 无可用连接，退出", worker_id)
            return

        # 为每个连接创建下载协程
        async def download_loop(conn_id, client, _server):
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
                    worker_logger.debug("Worker %s 连接 %s 队列为空", worker_id, conn_id)
                    break
                except Exception as e:
                    worker_logger.debug("Worker %s 连接 %s 获取任务失败: %s", worker_id, conn_id, e)
                    break

                symbol, market = task

                try:
                    # 异步下载IPO日期和行业代码
                    ipo_date, industry, finance_info = await _download_single_ipo_async(
                        client, symbol, market
                    )

                    if ipo_date is not None:
                        # 已上市，成功
                        await asyncio.to_thread(result_queue.put, (symbol, ipo_date, "listed"))
                        await asyncio.to_thread(progress_queue.put, (symbol, "success"))
                        processed += 1
                    elif industry > 0:
                        # 未上市品种（ipo_date=0 但 industry>0）
                        await asyncio.to_thread(result_queue.put, (symbol, None, "unlisted"))
                        await asyncio.to_thread(progress_queue.put, (symbol, "unlisted"))

                        # 🔧 保存unlisted品种的完整finance_info数据用于调试
                        if unlisted_debug_queue is not None:
                            debug_data = {
                                "symbol": symbol,
                                "market": market,
                                "finance_info": finance_info,
                                "worker_id": worker_id,
                                "conn_id": conn_id,
                            }
                            await asyncio.to_thread(unlisted_debug_queue.put, debug_data)

                        processed += 1
                    else:
                        # 服务器问题（ipo_date=0 且 industry=0），重试
                        await asyncio.to_thread(task_queue.put, (symbol, market))
                        await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
                        failed += 1

                except Exception as e:
                    worker_logger.debug(
                        f"Worker {worker_id} 连接 {conn_id} 下载 {symbol} IPO失败: {e}"
                    )
                    # 异常也视为服务器问题，重试
                    await asyncio.to_thread(task_queue.put, (symbol, market))
                    await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
                    failed += 1

                # 🔧 动态延时机制：根据队列剩余量调整延时，降低服务器压力
                try:
                    queue_size = task_queue.qsize()
                    if queue_size <= 30:
                        # 剩余30个以下：延时0.2秒
                        await asyncio.sleep(0.2)
                    elif queue_size <= 100:
                        # 剩余30-100个：延时0.1秒
                        await asyncio.sleep(0.1)
                    elif queue_size <= 200:
                        # 剩余100-200个：延时0.05秒
                        await asyncio.sleep(0.05)
                    # 队列>200个：不延时，全速运行
                except Exception:
                    # 获取队列大小失败时，使用默认延时
                    pass

            worker_logger.info(
                f"Worker {worker_id} 连接 {conn_id} 完成, 成功: {processed}, 失败: {failed}"
            )
            return processed, failed

        # N个协程并发工作
        tasks = []
        for idx, server in enumerate(server_list_local):
            if server in connections:
                tasks.append(download_loop(idx, connections[server], server))

        if not tasks:
            worker_logger.warning("Worker %s 没有可用连接，退出", worker_id)
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计总数
        total_processed = sum((r[0] for r in results if isinstance(r, tuple)), 0)
        total_failed = sum((r[1] for r in results if isinstance(r, tuple)), 0)
        worker_logger.info(
            "Worker %s 总计完成, 成功: %s, 失败: %s", worker_id, total_processed, total_failed
        )

    finally:
        # 关闭所有连接
        for server, client in connections.items():
            try:
                if client and not client.closed:
                    await client.close()
                    worker_logger.debug(
                        "Worker %s 连接 %s:%s 已关闭", worker_id, server[0], server[1]
                    )
            except Exception as e:
                worker_logger.debug("Worker %s 关闭连接失败 %s: %s", worker_id, server, e)


def _run_async_worker_ipo(*args):
    """在进程中运行IPO异步worker的辅助函数"""
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning, message=".*socket.*")
    asyncio.run(download_worker_ipo_async(*args))


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
            from ..events import DownloadEventPublisher, EventPublisher

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
        use_adaptive: bool = True,
        use_two_phase: bool = True,
    ) -> Union[Dict[str, pd.DataFrame], Dict[str, str]]:
        """主下载方法 - 使用进程池+动态任务分配

        Args:
            symbols: 品种代码列表
            start_date: 起始日期
            intervals: 周期列表（默认["1d", "5m", "1m"]）
            progress_callback: 进度回调函数
            use_adaptive: 是否使用自适应配置（默认True，企业级推荐）
            use_two_phase: 是否使用两段式下载（默认True，热备服务器优化）
        """
        if not symbols:
            self.logger.error("品种列表为空")
            return {}

        intervals = intervals or ["1d", "5m", "1m"]
        total_tasks = len(symbols) * len(intervals)

        self.logger.info(
            f"开始多进程下载: {len(symbols)}品种 × {len(intervals)}周期 = {total_tasks}任务"
        )

        try:
            # 1. 获取服务器列表（统一使用服务器池缓存）
            # 两段式下载：获取分层服务器（热备 + 乱序）
            standby_servers = []
            regular_servers = []
            broker_map = {}
            threshold = 0

            try:
                if use_two_phase:
                    # 两段式模式：获取分层服务器
                    self.logger.info("使用两段式下载模式")
                    server_layers = server_pool_manager.get_servers_with_standby(standby_count=30)
                    standby_servers = server_layers["standby"]
                    regular_servers = server_layers["regular"]
                    broker_map = server_layers["broker_map"]
                    available_servers = regular_servers  # 第一阶段使用regular服务器

                    # 计算阈值：min(100, total_tasks * 5%)
                    threshold = min(100, int(total_tasks * 0.05))
                    self.logger.info(
                        f"两段式下载阈值: {threshold} 任务（剩余任务低于此值时切换到热备服务器）"
                    )
                else:
                    # 单段式模式：获取打乱的服务器
                    available_servers = server_pool_manager.get_servers_shuffled()

                self.logger.info("✅ 使用缓存的服务器池: %s个可用服务器", len(available_servers))
            except RuntimeError as e:
                # ❌ 缓存不可用，阻止下载
                error_msg = (
                    "服务器池缓存不可用，无法下载数据！\n\n"
                    f"原因：{str(e)}\n\n"
                    "请按以下步骤操作：\n"
                    "1. 打开'系统管理'模块\n"
                    "2. 点击'测速服务器'按钮\n"
                    "3. 等待测速完成（约7秒）\n"
                    "4. 重新尝试下载"
                )
                self.logger.error(error_msg)

                # 返回失败结果（供UI处理）
                return {"error": error_msg, "action_required": "test_servers"}

            if use_adaptive:
                # ===== 自适应模式（企业级） =====
                self.logger.info("=" * 60)
                self.logger.info("【企业级自适应下载】启动")

                # 计算自适应配置（传入任务数量以优化小任务场景）
                adaptive_cfg = AdaptiveDownloadConfig.calculate_optimal_config(
                    task_count=total_tasks
                )

                # 从缓存服务器中选取需要的数量
                available_servers = available_servers[: adaptive_cfg["total_connections"]]

                # 使用自适应配置
                self.num_processes = adaptive_cfg["processes"]
                self.async_connections_per_process = adaptive_cfg["coroutines_per_process"]

                self.logger.info("【配置信息】")
                self.logger.info("  CPU核心: %d", adaptive_cfg["cpu_cores"])
                self.logger.info("  可用内存: %.2f GB", adaptive_cfg["available_memory_gb"])
                self.logger.info("  可用服务器: %d", adaptive_cfg["available_servers"])
                self.logger.info("  进程数: %d", self.num_processes)
                self.logger.info("  每进程协程: %d", self.async_connections_per_process)
                self.logger.info("  总连接数: %d", adaptive_cfg["total_connections"])
                self.logger.info("  预计内存: %.2f MB", adaptive_cfg["estimated_memory_mb"])
                self.logger.info("  服务器来源: 服务器池缓存 (打乱顺序)")
                self.logger.info("  配置原因: %s", adaptive_cfg["reason"])
                self.logger.info("=" * 60)
            else:
                # ===== 传统模式 =====
                self.logger.info(
                    "使用服务器池缓存（打乱顺序）: %s 个服务器", len(available_servers)
                )
                # 打印前5个服务器（已打乱）
                top5 = available_servers[:5]
                self.logger.info("前5个服务器（打乱后）: %s", top5)

                # 动态计算进程数：服务器数/30向上取整
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
            if use_two_phase:
                # 使用两段式worker
                self._start_two_phase_worker_pool(
                    regular_servers, standby_servers, broker_map, threshold
                )
            else:
                # 使用单段式worker
                self._start_worker_pool(server_list, server_index)

            # 7. 监控进度并收集结果
            results = self._monitor_progress_and_collect_results(total_tasks, progress_callback)

            # 8. 清理资源
            self._cleanup_processes()
            if self._download_progress:
                self._download_progress["is_downloading"] = False

            # 统计结果
            valid_count = sum(1 for v in results.values() if v is not None and not v.empty)
            self.logger.info("下载完成: %s/%s 有效任务", valid_count, total_tasks)

            return results

        except Exception as e:
            self.logger.error("多进程下载异常: %s", e, exc_info=True)
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

    def _start_two_phase_worker_pool(self, regular_servers, standby_servers, broker_map, threshold):
        """启动两段式异步worker进程池

        Args:
            regular_servers: 乱序服务器列表
            standby_servers: 热备服务器列表
            broker_map: 服务器到券商的映射
            threshold: 任务剩余阈值
        """
        # 为manager创建共享对象
        assert self.manager is not None, "Manager未初始化"
        shared_regular_servers = self.manager.list(regular_servers)  # type: ignore
        shared_standby_servers = self.manager.list(standby_servers)  # type: ignore
        shared_broker_map = self.manager.dict(broker_map)  # type: ignore

        for i in range(self.num_processes):
            try:
                # 使用两段式异步worker
                p = Process(
                    target=_run_two_phase_worker,
                    args=(
                        i,
                        self.task_queue,
                        self.result_queue,
                        self.progress_queue,
                        shared_regular_servers,
                        shared_standby_servers,
                        shared_broker_map,
                        threshold,
                        self.timeout,
                        self.stop_event,
                        self.pause_event,
                        self.async_connections_per_process,  # 传递异步连接数
                    ),
                )

                p.start()
                self.processes.append(p)
                self.logger.debug(f"启动两段式进程 {i} (PID: {p.pid})")

                # 给进程一点启动时间
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"启动两段式进程{i}失败: {e}")

        self.logger.info(f"启动{len(self.processes)}个两段式工作进程")

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
            try:
                if self.progress_queue is not None:
                    progress_data = self.progress_queue.get(timeout=0.1)
                    # 兼容新格式：(symbol, interval, status) 或旧格式：(symbol, interval)
                    if len(progress_data) == 3:
                        symbol, interval, _ = progress_data
                    else:
                        symbol, interval = progress_data

                    completed += 1
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
        use_adaptive: bool = True,
    ) -> bool:
        """
        启动增量下载（异步执行，立即返回，从download_manager.py合并）

        Args:
            start_date: 开始日期
            symbol_loader: SymbolLoader实例
            storage_manager: StorageManager实例
            market_types: 市场类型列表
            use_adaptive: 是否使用自适应配置（默认True，企业级推荐）

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
                args=(start_date, symbol_loader, storage_manager, market_types, use_adaptive),
                daemon=True,
                name="IncrementalDownloadThread",
            )
            self._download_thread.start()

            self.logger.info("✅ 增量下载任务已启动（后台线程）")
            return True

    def _do_download_async(
        self,
        start_date,
        symbol_loader,
        storage_manager,
        market_types=None,
        use_adaptive: bool = True,
    ):
        """
        实际执行增量下载的后台方法（从download_manager.py合并）

        Args:
            start_date: 开始日期
            symbol_loader: SymbolLoader实例
            storage_manager: StorageManager实例
            market_types: 市场类型列表
            use_adaptive: 是否使用自适应配置（默认True）
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
                    use_adaptive=use_adaptive,
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
    use_adaptive: bool = True,
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
    4. 多进程任务分配（支持自适应配置）
    5. 数据下载和解码
    6. 自动存储（通过回调）
    7. 进度和事件推送（通过回调）

    Args:
        symbols: 品种代码列表（如为空且提供symbol_loader，则自动提取）
        start_date: 开始日期（字符串或date对象）
        intervals: 周期列表（默认["1d", "5m", "1m"]）
        use_adaptive: 是否使用自适应配置（默认True，企业级推荐）
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
    logger.info("  配置模式: %s", "自适应配置（企业级）" if use_adaptive else "固定配置")
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

    # 创建下载器（使用自适应配置）
    fetcher = MultiProcessStockFetcher()

    total_tasks = len(symbols) * len(intervals)
    logger.info("✅ 日期范围验证通过，准备调用下载器...")
    logger.info("即将下载参数:")
    logger.info("  • 品种数量: %d", len(symbols))
    logger.info("  • 起始日期: %s", start_date)
    logger.info("  • 周期列表: %s", intervals)
    logger.info("  • 预计任务数: %d", total_tasks)
    logger.info("  • 配置模式: %s", "自适应（企业级）" if use_adaptive else "固定")

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
            symbols,
            start_date,
            intervals=intervals,
            progress_callback=internal_progress_callback,
            use_adaptive=use_adaptive,
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

    # 检查download_results是否为错误字典
    if isinstance(download_results, dict) and "error" in download_results:
        error_msg = str(download_results.get("error", "未知错误"))
        logger.error(f"❌ 下载失败: {error_msg}")
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
        empty_count = sum(
            1
            for v in download_results.values()
            if v is not None and isinstance(v, pd.DataFrame) and v.empty
        )

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

        # pylint: disable=no-member
        for key, data in download_results.items():
            parts = key.split("_", 1)
            if len(parts) != 2:
                continue
            symbol, interval = parts

            # 检查数据有效性
            if data is None:
                logger.debug("跳过保存（下载失败）: %s %s", symbol, interval)
                skipped_count += 1
                continue

            if not isinstance(data, pd.DataFrame):
                logger.debug("跳过保存（无效数据类型）: %s %s", symbol, interval)
                skipped_count += 1
                continue

            # 此时data确定是DataFrame类型
            if data.empty or len(data) == 0:  # pylint: disable=no-member
                logger.debug("跳过保存（空数据）: %s %s", symbol, interval)
                skipped_count += 1
                continue

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


# ==================== IPO日期批量下载接口 ====================


def download_ipo_dates(
    symbols: List[str],
    force_refresh: bool = False,
    progress_callback: Optional[Callable] = None,
    event_callback: Optional[Callable] = None,
    _use_adaptive: bool = True,
    _use_two_phase: bool = True,
) -> Dict[str, Any]:
    """批量下载IPO日期

    Args:
        symbols: 品种代码列表
        force_refresh: 是否强制刷新（False=跳过已缓存）
        progress_callback: 进度回调函数 callback(symbol, status)
        event_callback: 事件回调函数 callback(event_type, status, count, message)
        use_adaptive: 是否使用自适应配置
        use_two_phase: 是否使用两段式下载（默认True，热备服务器优化）

    Returns:
        {
            "success": bool,
            "total": int,
            "cached": int,        # 跳过的缓存数
            "downloaded": int,    # 实际下载数
            "succeeded": int,     # 成功获取IPO的数量
            "failed": int,        # 失败数量
            "data": {symbol: ipo_date, ...}
        }
    """
    from ..local_data.data_quality import IPODateCache
    import time

    local_logger = logging.getLogger(__name__)
    local_logger.info(f"开始IPO批量下载: {len(symbols)}个品种")

    # 1. 增量过滤
    ipo_cache = IPODateCache()

    if not force_refresh:
        uncached = []
        for symbol in symbols:
            _cached_date, is_cached = ipo_cache.get(symbol)
            if not is_cached:
                uncached.append(symbol)

        local_logger.info(
            f"增量模式: {len(symbols)}个品种 → 跳过{len(symbols)-len(uncached)}个已缓存 → 下载{len(uncached)}个"
        )
        symbols_to_download = uncached
        cached_count = len(symbols) - len(uncached)
    else:
        symbols_to_download = symbols
        cached_count = 0

    if not symbols_to_download:
        local_logger.info("所有品种均已缓存，无需下载")
        return {
            "success": True,
            "total": len(symbols),
            "cached": cached_count,
            "downloaded": 0,
            "succeeded": 0,
            "failed": 0,
            "data": {},
        }

    # 2. 准备任务列表（从品种列表缓存获取市场代码）
    # 🆕 从品种列表缓存中获取市场代码映射
    local_logger.info("从品种列表缓存中加载市场代码...")
    symbol_market_map = {}
    try:
        from .symbol_management import SymbolLoader

        symbol_loader = SymbolLoader()
        classified = symbol_loader.get_all_classified()

        # 构建 code -> market 映射
        for _category, stocks in classified.items():
            for stock in stocks:
                if isinstance(stock, dict):
                    code = stock.get("code")
                    market = stock.get("market")
                    if code and market is not None:
                        symbol_market_map[code] = market

        local_logger.info(f"✓ 成功加载 {len(symbol_market_map)} 个品种的市场代码")
    except Exception as e:
        local_logger.warning(f"加载品种市场代码失败，将使用代码前缀判断: {e}")

    # 构建任务列表
    tasks = []
    fallback_count = 0  # 使用默认判断的数量

    for symbol in symbols_to_download:
        # 优先从缓存获取市场代码
        if symbol in symbol_market_map:
            market = symbol_market_map[symbol]
        else:
            # 兜底：使用代码前缀判断（兼容性）
            if symbol.startswith("6"):
                market = 1  # 上海
            elif symbol.startswith("8") or symbol.startswith("4"):
                market = 2  # 北交所
            else:
                market = 0  # 深圳
            fallback_count += 1

        tasks.append((symbol, market))

    if fallback_count > 0:
        local_logger.info(f"⚠️ {fallback_count}个品种使用代码前缀判断市场")

    task_count = len(tasks)

    # 3. 使用简化的单进程多协程架构
    print("✓ 使用单进程多协程架构（100个协程）")
    local_logger.info("开始单进程多协程IPO下载")

    start_time = time.time()

    # 执行异步下载
    import asyncio

    def simple_progress_callback(_current, _total, status):
        """简化的进度回调"""
        if progress_callback:
            # 模拟品种名称（实际可从任务列表获取）
            progress_callback("", status)

    results, unlisted_data, failed_tasks = asyncio.run(
        download_ipo_dates_simple(
            tasks, num_coroutines=100, progress_callback=simple_progress_callback
        )
    )

    # 4. 处理结果和调试数据
    # 将unlisted_data转换为简单的symbol列表用于后续统计
    unlisted_symbols = [item["symbol"] for item in unlisted_data]

    # 保存调试数据到JSON文件
    import json
    from pathlib import Path

    # 使用配置管理器获取正确的缓存目录
    try:
        from backend.infrastructure.data_module_vnpy.config import config_manager

        cache_dir = config_manager.get_cache_dir()
        debug_file_path = cache_dir / "unlisted_symbols_debug.json"
    except Exception:
        # 兜底方案：直接指定绝对路径
        debug_file_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "data"
            / "cache"
            / "unlisted_symbols_debug.json"
        )
    debug_file_path.parent.mkdir(parents=True, exist_ok=True)

    if unlisted_data:
        with open(debug_file_path, "w", encoding="utf-8") as f:
            json.dump(unlisted_data, f, ensure_ascii=False, indent=2, default=str)

        local_logger.info(
            f"✓ 已保存 {len(unlisted_data)} 个unlisted品种的调试数据到: {debug_file_path}"
        )
        print(f"✓ 已保存 {len(unlisted_data)} 个unlisted品种的调试数据到: {debug_file_path}")

    # 输出详细分析
    print("\n" + "=" * 70)
    print("【Unlisted品种详细分析】")
    print(f"  - 通过worker标记的unlisted品种数: {len(unlisted_data)}")
    print(f"  - unlisted_symbols列表长度: {len(unlisted_symbols)}")

    # 检查重复
    unlisted_set = set(unlisted_symbols)
    if len(unlisted_set) != len(unlisted_symbols):
        print(f"  ⚠️ 发现重复！去重后: {len(unlisted_set)} 个")
        from collections import Counter

        duplicates = [item for item, count in Counter(unlisted_symbols).items() if count > 1]
        print(f"  重复的品种: {duplicates}")

    # 检查results和unlisted_symbols的交集
    results_set = set(results.keys())
    intersection = unlisted_set & results_set
    if intersection:
        print(f"\n  🚨 发现关键问题：{len(intersection)}个品种同时在results和unlisted_symbols中！")
        print("  这些品种被重复计数（既标记为已上市，又标记为未上市）：")
        intersection_list = sorted(list(intersection))
        for i in range(0, len(intersection_list), 10):
            batch = intersection_list[i : i + 10]
            print(f"    {', '.join(batch)}")

        # 分析这些重复品种
        duplicate_bonds = [s for s in intersection_list if s.startswith(("11", "12", "13"))]
        duplicate_stocks = [s for s in intersection_list if not s.startswith(("11", "12", "13"))]
        print(f"\n  其中可转债{len(duplicate_bonds)}个, 股票{len(duplicate_stocks)}个")

    # 输出完整列表
    if unlisted_symbols:
        print(f"\n  完整unlisted品种列表（共{len(unlisted_symbols)}个）")
        for i in range(0, len(unlisted_symbols), 10):
            batch = unlisted_symbols[i : i + 10]
            print(f"    {', '.join(batch)}")

    # 对比debug数据
    if unlisted_data:
        debug_symbols = [item["symbol"] for item in unlisted_data]
        print(f"\n  Debug队列中的品种（共{len(debug_symbols)}个）")
        for i in range(0, len(debug_symbols), 10):
            batch = debug_symbols[i : i + 10]
            print(f"    {', '.join(batch)}")

        # 找出差异（这在单进程架构中不应该存在）
        missing_from_debug = set(unlisted_symbols) - set(debug_symbols)
        if missing_from_debug:
            print(
                f"\n  ⚠️ 在unlisted_symbols中但不在debug数据中的品种（{len(missing_from_debug)}个）"
            )
            missing_list = sorted(list(missing_from_debug))
            for i in range(0, len(missing_list), 10):
                batch = missing_list[i : i + 10]
                print(f"    {', '.join(batch)}")

    print("=" * 70 + "\n")

    total_time = time.time() - start_time
    local_logger.info(f"IPO下载完成，总耗时: {total_time:.2f}秒")

    # 5. 统计结果
    succeeded = len(results)  # 已上市品种数
    unlisted_count = len(unlisted_symbols)  # 未上市品种数
    failed = len(failed_tasks)  # 失败数
    initial_task_count = task_count
    total_retry_count = 0  # 新架构中重试次数由函数内部管理

    # 收集失败品种
    failed_symbols = [task[0] for task in failed_tasks]

    # 6. 统计结果（跳过旧的多进程监控代码）
    # 以下代码直接使用简化版函数的返回结果

    # 7. 输出三个集合的详细统计
    print("\n" + "=" * 70)
    print("【三个集合详细统计】")
    print(f"  初始任务总数: {initial_task_count}")
    print(f"  已上市品种数 (results): {succeeded}")
    print(f"  未上市品种数 (unlisted_symbols): {unlisted_count}")
    print(f"  失败品种数 (计算得出): {failed}")
    print(
        f"  总和验证: {succeeded} + {unlisted_count} + {failed} = {succeeded + unlisted_count + failed}"
    )
    if succeeded + unlisted_count + failed != initial_task_count:
        print(f"  ⚠️ 总和不匹配！差异: {initial_task_count - (succeeded + unlisted_count + failed)}")

    # 真实去重统计
    results_set = set(results.keys())
    unlisted_set = set(unlisted_symbols)
    intersection = results_set & unlisted_set
    unique_succeeded = len(results_set - intersection)
    unique_unlisted = len(unlisted_set - intersection)
    unique_total = unique_succeeded + unique_unlisted + failed

    print("\n  【去重后的真实统计】")
    print(f"  去重后已上市品种: {unique_succeeded} (原{succeeded}, 去除{len(intersection)}个重复)")
    print(
        f"  去重后未上市品种: {unique_unlisted} (原{unlisted_count}, 去除{len(intersection)}个重复)"
    )
    print(f"  失败品种: {failed}")
    print(f"  去重后总计: {unique_succeeded} + {unique_unlisted} + {failed} = {unique_total}")

    if unique_total == initial_task_count:
        print("  ✓ 去重后总和正确！")
    else:
        print(f"  ⚠️ 去重后总和仍不匹配！差异: {initial_task_count - unique_total}")

    print("=" * 70 + "\n")

    # 8. 更新品种列表缓存（合并IPO数据并删除未上市品种）
    if results or unlisted_symbols:
        local_logger.info("=" * 60)
        local_logger.info("【更新品种列表缓存】")

        # 去重：只删除真正的未上市品种（不在results中的）
        results_set = set(results.keys())
        unlisted_set = set(unlisted_symbols)
        true_unlisted = list(unlisted_set - results_set)  # 真正的未上市品种

        local_logger.info(f"  - 已上市品种: {succeeded} 个（将写入IPO日期）")
        local_logger.info(f"  - 原未上市品种数: {unlisted_count} 个")
        if len(true_unlisted) != unlisted_count:
            local_logger.warning(
                f"  - 发现重复标记: {unlisted_count - len(true_unlisted)} 个品种同时被标记为已上市和未上市"
            )
            local_logger.info(f"  - 真正未上市品种: {len(true_unlisted)} 个（将从列表中删除）")
            print(
                f"\n   🔧 去重修正：实际删除 {len(true_unlisted)} 个未上市品种（而非原来的 {unlisted_count} 个）"
            )
        else:
            local_logger.info(f"  - 未上市品种: {unlisted_count} 个（将从列表中删除）")

        try:
            from .symbol_management import SymbolLoader

            symbol_loader = SymbolLoader()
            success = symbol_loader.update_ipo_dates_and_remove_unlisted(results, true_unlisted)
            if success:
                local_logger.info("✓ 品种列表缓存已更新（包含IPO日期，已删除未上市品种）")
            else:
                local_logger.warning("⚠️ 品种列表缓存更新失败")
        except Exception as e:
            local_logger.error(f"更新品种列表缓存时出错: {e}", exc_info=True)
        local_logger.info("=" * 60)

    # 9. 输出最终统计
    local_logger.info("=" * 60)
    local_logger.info("IPO批量下载统计:")
    local_logger.info(f"  总品种数: {len(symbols)}")
    local_logger.info(f"  跳过缓存: {cached_count}")
    local_logger.info(f"  实际下载: {task_count}")
    local_logger.info(f"  已上市品种: {succeeded}")
    local_logger.info(f"  未上市品种: {unlisted_count}")
    local_logger.info(f"  失败/无数据: {failed}")
    local_logger.info(f"  总重试次数: {total_retry_count}")
    if task_count > 0:
        local_logger.info(f"  成功率: {(succeeded + unlisted_count)/task_count*100:.1f}%")
        if total_retry_count > 0:
            local_logger.info(f"  平均重试: {total_retry_count/task_count:.2f}次/品种")

    # 输出失败品种详情（前10个）
    if failed_symbols:
        local_logger.warning("  失败品种示例（前10个）: %s", ", ".join(failed_symbols[:10]))
        if len(failed_symbols) > 10:
            local_logger.warning("    ... 还有%d个失败品种", len(failed_symbols) - 10)

    local_logger.info("=" * 60)

    # 10. 添加terminal输出
    import sys

    print("\n   IPO下载完成：")
    print(f"   - 总品种数: {len(symbols)}")
    print(f"   - 跳过缓存: {cached_count}")
    print(f"   - 实际下载: {task_count}")
    print(f"   - 已上市品种: {succeeded}")
    print(f"   - 未上市品种: {unlisted_count}")

    # 如果存在重复，显示去重后的真实数据
    if intersection:
        print(f"   ⚠️ 发现{len(intersection)}个品种被重复计数")
        print(f"   - 去重后已上市: {unique_succeeded}")
        print(f"   - 去重后未上市: {unique_unlisted}")

    print(f"   - 失败/无数据: {failed}")
    print(f"   - 总重试次数: {total_retry_count}")
    if total_retry_count > 0 and task_count > 0:
        print(f"   - 平均重试: {total_retry_count/task_count:.2f}次/品种")
    if task_count > 0:
        print(f"   - 成功率: {(succeeded + unlisted_count)/task_count*100:.1f}%")

    if failed_symbols:
        print(f"   - 失败品种（前5个）: {', '.join(failed_symbols[:5])}")
        print(f"\n   ⚠️ 完整失败品种列表（共{len(failed_symbols)}个）:")
        # 每行10个品种
        for i in range(0, len(failed_symbols), 10):
            batch = failed_symbols[i : i + 10]
            print(f"      {', '.join(batch)}")

        # 将完整失败品种列表保存到文件（用于分析）
        try:
            from pathlib import Path
            from backend.infrastructure.data_module_vnpy.config import config_manager

            cache_dir = config_manager.get_cache_dir()
            failed_file = cache_dir / "ipo_failed_symbols.json"

            import json

            with open(failed_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp": str(datetime.now()),
                        "total_failed": len(failed_symbols),
                        "failed_symbols": failed_symbols,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            local_logger.info(f"✓ 失败品种列表已保存到: {failed_file}")
        except Exception as e:
            local_logger.warning(f"保存失败品种列表失败: {e}")

    sys.stdout.flush()

    # 11. 推送事件
    if event_callback:
        # 使用去重后的真实数据
        true_succeeded = len(results)  # results本身是字典，已去重
        true_unlisted_list = list(set(unlisted_symbols) - set(results.keys()))
        event_callback(
            "ipo_download",
            "success",
            true_succeeded + len(true_unlisted_list),
            f"成功处理{true_succeeded + len(true_unlisted_list)}个品种（已上市{true_succeeded}个，未上市{len(true_unlisted_list)}个）",
        )

    return {
        "success": True,
        "total": len(symbols),
        "cached": cached_count,
        "downloaded": task_count,
        "succeeded": succeeded,
        "unlisted": unlisted_symbols,  # 保持原始数据供调试
        "failed": failed,
        "data": results,
        "duplicate_count": (len(intersection) if "intersection" in locals() else 0),  # 添加重复计数
        "true_unlisted": (
            true_unlisted if "true_unlisted" in locals() else unlisted_symbols
        ),  # 真正的未上市品种
    }
