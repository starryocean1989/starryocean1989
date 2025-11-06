# -*- coding: utf-8 -*-
"""
TDX数据读取器（v3.1版本）

基于TdxBinaryReader，增强以下特性：
- 多进程+多协程批量读取
- native_iocp异步文件I/O
- 队列压力监控和自适应调整

设计原则：
- 复用TdxBinaryReader的解码逻辑
- 采用与K线下载相同的worker模式
- 支持最大2000并发（受限于文件句柄）
"""

import asyncio
import logging
import time
from multiprocessing import Manager, Process
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from .binary_reader import TdxBinaryReader


logger = logging.getLogger("TdxDataReader")


class TdxDataReader:
    """TDX数据读取器（v3.1版本）

    基于TdxBinaryReader，增强以下特性：
    - 多进程+多协程批量读取
    - native_iocp异步文件I/O
    - 队列压力监控和自适应调整

    设计原则：
    - 复用TdxBinaryReader的解码逻辑
    - 采用与K线下载相同的worker模式
    - 支持最大2000并发（受限于文件句柄）
    """

    def __init__(self, tdx_root_path: Optional[Path] = None):
        """初始化TDX数据读取器

        Args:
            tdx_root_path: 通达信软件根目录
        """
        self.logger = logging.getLogger("TdxDataReader")

        # 初始化二进制读取器（复用解码逻辑）
        self.binary_reader = TdxBinaryReader(tdx_root_path)
        self.tdx_root = self.binary_reader.tdx_root

        self.logger.info(
            f"✅ TdxDataReader初始化完成，TDX根目录: {self.tdx_root}",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )

    async def fetch_async(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """异步读取单个TDX文件（使用native_iocp）

        Args:
            symbol: 品种代码
            data_type: 数据类型（day/5min/1min）
            market: 市场（sh/sz/bj）

        Returns:
            DataFrame
        """
        # 直接调用TdxBinaryReader的异步方法
        return await self.binary_reader.read_single_async(symbol, data_type, market)

    def fetch_batch_multiprocess(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        num_processes: Optional[int] = None,
        max_coroutines: Optional[int] = None,
    ) -> Dict[str, pd.DataFrame]:
        """多进程+多协程批量读取TDX文件

        Args:
            symbols: 品种代码列表
            data_type: 数据类型（day/5min/1min）
            market: 市场（sh/sz/bj），如果为None则自动判断
            progress_callback: 进度回调函数 callback(completed, total, msg)
            num_processes: 进程数（如果为None，默认4）
            max_coroutines: 每个进程的协程数（如果为None，默认1000）

        Returns:
            {symbol: DataFrame}
        """
        if not symbols:
            self.logger.warning("品种列表为空", extra={"log_type": "SYSTEM"})
            return {}

        total_tasks = len(symbols)
        self.logger.info(
            f"🚀 开始TDX批量读取: 品种数={total_tasks}, 类型={data_type}",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )

        # 使用默认配置（如果未提供）
        if num_processes is None:
            num_processes = 4
        if max_coroutines is None:
            max_coroutines = 1000

        self.logger.info(
            f"📊 TDX读取配置: 进程={num_processes}, 协程={max_coroutines}",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )

        # 初始化多进程对象
        manager = Manager()
        task_queue = manager.Queue()
        result_queue = manager.Queue()

        # 填充任务队列
        for symbol in symbols:
            # 自动判断市场（如果未指定）
            if market is None:
                symbol_market = self._get_market_from_symbol(symbol)
            else:
                symbol_market = market

            task_queue.put((symbol, data_type, symbol_market))

        # 启动worker进程
        processes = []
        for i in range(num_processes):
            p = Process(
                target=_tdx_reader_worker,
                args=(
                    i,
                    task_queue,
                    result_queue,
                    str(self.tdx_root),  # 转为字符串传递
                    max_coroutines,
                ),
            )
            p.start()
            processes.append(p)

        # 收集结果
        results = {}
        completed = 0

        while completed < total_tasks:
            try:
                symbol, df = result_queue.get(timeout=1)
                results[symbol] = df
                completed += 1

                if progress_callback:
                    try:
                        progress_callback(completed, total_tasks, f"已读取: {symbol}")
                    except Exception as e:
                        self.logger.warning(
                            f"⚠️ [TdxDataReader] 进度回调执行失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                        )
                        pass

            except Exception as e:
                # 检查进程状态
                self.logger.warning(
                    f"⚠️ [TdxDataReader] 批量读取过程异常: {e}",
                    extra={"log_type": "ALERT", "scenario": "tdx_data_read"},
                )
                if not any(p.is_alive() for p in processes):
                    self.logger.warning(
                        "⚠️ [TdxDataReader] 所有进程已退出",
                        extra={"log_type": "ALERT", "scenario": "tdx_data_read"},
                    )
                    break

        # 清理进程
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)

        self.logger.info(
            f"✅ TDX批量读取完成: {len(results)}/{total_tasks}",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )
        return results

    @staticmethod
    def _get_market_from_symbol(symbol: str) -> str:
        """根据品种代码判断市场

        Args:
            symbol: 品种代码

        Returns:
            市场代码（sh/sz/bj）
        """
        if symbol.startswith(("60", "68", "11")):
            return "sh"
        elif symbol.startswith(("00", "30", "12")):
            return "sz"
        elif symbol.startswith(("43", "83", "87", "4", "8")):
            return "bj"
        else:
            return "sz"  # 默认深证


def _tdx_reader_worker(
    worker_id: int,
    task_queue,
    result_queue,
    tdx_root_path: str,
    max_coroutines: int,
):
    """TDX读取器worker进程

    Args:
        worker_id: Worker ID
        task_queue: 任务队列
        result_queue: 结果队列
        tdx_root_path: TDX根目录
        max_coroutines: 最大协程数
    """
    # 配置子进程日志
    worker_logger = logging.getLogger(f"TdxDataReader.worker.{worker_id}")
    worker_logger.setLevel(logging.DEBUG)

    # 运行异步事件循环
    asyncio.run(
        _tdx_reader_worker_async(
            worker_id, task_queue, result_queue, tdx_root_path, max_coroutines, worker_logger
        )
    )


async def _tdx_reader_worker_async(
    worker_id: int,
    task_queue,
    result_queue,
    tdx_root_path: str,
    max_coroutines: int,
    logger,
):
    """TDX读取器异步worker

    Args:
        worker_id: Worker ID
        task_queue: 任务队列
        result_queue: 结果队列
        tdx_root_path: TDX根目录
        max_coroutines: 最大协程数
        logger: 日志记录器
    """
    # 创建TDX读取器实例
    reader = TdxBinaryReader(Path(tdx_root_path))

    # 创建协程池（限制并发）
    semaphore = asyncio.Semaphore(max_coroutines)

    async def process_task():
        """处理单个任务"""
        while True:
            try:
                # 从队列获取任务（非阻塞）
                symbol, data_type, market = task_queue.get_nowait()
            except Exception:
                break

            async with semaphore:
                scenario = "tdx_data_read"
                task_start_time = time.time()
                try:
                    logger.debug(
                        f"[TDX-READER-WORKER] 开始读取: symbol={symbol}, data_type={data_type}, market={market}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    # 读取TDX文件（使用native_iocp）
                    df = await reader.read_single_async(symbol, data_type, market)
                    task_elapsed = time.time() - task_start_time

                    # 记录读取成功
                    record_count = len(df) if df is not None and hasattr(df, "__len__") else 0
                    logger.debug(
                        f"[TDX-READER-WORKER] 读取成功: symbol={symbol}, data_type={data_type}, market={market}, "
                        f"记录数={record_count}, 耗时={task_elapsed:.3f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    if record_count == 0:
                        logger.warning(
                            f"[TDX-READER-WORKER] ⚠️ 读取结果为空: symbol={symbol}, data_type={data_type}, market={market}",
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )

                    # 返回结果
                    result_queue.put((symbol, df))

                except Exception as e:
                    task_elapsed = time.time() - task_start_time
                    logger.debug(
                        f"[TDX-READER-WORKER] 读取异常详情: symbol={symbol}, data_type={data_type}, market={market}, "
                        f"异常类型={type(e).__name__}, 异常消息={str(e)}, 耗时={task_elapsed:.3f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    logger.error(
                        f"[TDX-READER-WORKER] ❌ 读取失败: symbol={symbol}, data_type={data_type}, market={market}, "
                        f"错误={e}, 耗时={task_elapsed:.3f}s",
                        exc_info=True,
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )
                    result_queue.put((symbol, pd.DataFrame()))

    # 启动多个协程任务
    scenario = "tdx_data_read"
    logger.debug(
        f"[TDX-READER-WORKER] Worker {worker_id} 启动协程池: 协程数={min(max_coroutines, 100)}",
        extra={"log_type": "SYSTEM", "scenario": scenario},
    )
    logger.info(
        f"[TDX-READER-WORKER] ℹ️ Worker {worker_id} 开始处理任务，协程数={min(max_coroutines, 100)}",
        extra={"log_type": "SYSTEM", "scenario": scenario},
    )
    tasks = [process_task() for _ in range(min(max_coroutines, 100))]  # 限制初始协程数
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.debug(
        f"[TDX-READER-WORKER] Worker {worker_id} 所有协程任务已完成",
        extra={"log_type": "SYSTEM", "scenario": scenario},
    )
    logger.info(
        f"[TDX-READER-WORKER] ✅ Worker {worker_id} 完成",
        extra={"log_type": "SYSTEM", "scenario": scenario},
    )

