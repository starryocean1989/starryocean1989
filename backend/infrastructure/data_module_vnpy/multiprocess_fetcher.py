# -*- coding: utf-8 -*-
"""
多进程股票数据获取器

继承StockFetcher，使用多进程实现真正的并行计算
突破Python GIL限制，实现15-20倍速度提升

注意：Windows下使用multiprocessing需要确保在if __name__ == '__main__'保护下启动
但由于我们的worker函数在独立模块中，这个要求已自动满足
"""

import logging
import queue
import time
from datetime import datetime
from multiprocessing import Manager, Process, cpu_count
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.infrastructure.data_module_vnpy.block_parser import BlockParser
from backend.infrastructure.data_module_vnpy.config import config_manager
from backend.infrastructure.data_module_vnpy.multiprocess_worker import (
    download_worker_process,
)
from backend.infrastructure.data_module_vnpy.server_pool import ServerPool
from backend.infrastructure.data_module_vnpy.stock_fetcher import StockFetcher

# 确保Windows兼容性
import sys
import multiprocessing

# Windows需要freeze_support
if sys.platform == "win32":
    multiprocessing.freeze_support()


class MultiProcessStockFetcher(StockFetcher):
    """
    多进程股票数据获取器

    继承StockFetcher，使用multiprocessing实现真正的并行计算
    每个进程有独立的GIL，可以充分利用多核CPU

    品种列表获取逻辑：继承父类StockFetcher的新逻辑（集合A-G）
    数据下载逻辑：使用多进程实现高性能下载
    """

    def __init__(self, block_parser=None):
        """
        初始化多进程数据获取器

        Args:
            block_parser: BlockParser实例，如果为None则创建新实例
        """
        # 先调用父类初始化（会初始化block_parser、config_parser等）
        super().__init__(block_parser)

        self.logger = logging.getLogger(__name__)

        # 获取进程数配置（使用现有的server_pool_size）
        pool_size = config_manager.get("chinastock.server_pool_size", 5)

        # 限制进程数（不超过CPU核心数的2倍，避免过度竞争）
        cpu_cores = cpu_count()
        max_processes = min(pool_size, cpu_cores * 2, 30)  # 最多30个
        self.num_processes = max_processes

        self.logger.info(
            "初始化多进程下载器: %d个进程（CPU核心数: %d，配置: %d）",
            self.num_processes,
            cpu_cores,
            pool_size,
        )

        # 多进程共享对象（延迟初始化，避免启动时多进程问题）
        self.manager = None
        self.task_queue = None
        self.result_queue = None
        self.progress_queue = None
        self.stop_event = None
        self.pause_event = None
        self._pause_set = True  # 默认不暂停

        # 进度跟踪（延迟初始化）
        self._download_progress = None

        # 进程池相关
        self.processes: List[Process] = []

        # ServerPool（用于获取可用服务器）
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
                self.pause_event.set()  # 默认不暂停
            else:
                self.pause_event.clear()  # 暂停状态

            # 进度跟踪（进程安全）
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

        # BlockParser（父类StockFetcher已经初始化，这里不需要重复初始化）
        # 父类在__init__中已经初始化了block_parser和config_parser

        # 超时配置
        self.network_timeout = 30

        # 品种分类缓存
        self._classified_stocks_cache: Optional[Dict[str, List[str]]] = None

        # 保留quotes用于向后兼容（延迟初始化）
        self._quotes = None

    @property
    def quotes(self):
        """向后兼容：延迟初始化单一Quotes实例"""
        if self._quotes is None:
            from mootdx.quotes import Quotes

            self._quotes = Quotes.factory()
            self.logger.info("延迟初始化默认Quotes实例（向后兼容）")
        return self._quotes

    # ==================== 下载控制方法（继承自父类）====================
    # stop_download(), pause_download(), resume_download等方法继承自StockFetcher

    # ==================== 核心下载方法 ====================

    def download_incremental_kline(
        self,
        symbols: List[str],
        start_date,
        intervals: Optional[List[str]] = None,
        progress_callback=None,
    ) -> Dict[str, pd.DataFrame]:
        """
        增量下载K线数据（多进程版本）

        Args:
            symbols: 品种代码列表
            start_date: 开始日期
            intervals: 周期列表
            progress_callback: 进度回调函数

        Returns:
            下载结果字典 {f"{symbol}_{interval}": DataFrame}
        """
        result = {}

        # 设置默认周期
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
            self.logger.info("【步骤1】发现可用服务器...")
            available_servers = self.server_pool.discover_servers()[: self.num_processes]

            if not available_servers:
                self.logger.error("❌ 没有可用服务器，无法下载")
                return result

            num_servers = len(available_servers)
            self.logger.info("✅ 发现 %d 个可用服务器", num_servers)

            # 步骤2：构建任务列表
            self.logger.info("【步骤2】构建任务列表...")

            # 不过滤北交所股票（使用TdxHq_API可以获取，市场代码2）
            tasks = [(symbol, interval, start_date) for symbol in symbols for interval in intervals]
            total_tasks = len(tasks)

            self.logger.info("✅ 任务列表构建完成: 总计 %d 个任务", total_tasks)

            # 清空队列（防止上次残留）
            self._clear_queues()

            # 填充任务队列
            for task in tasks:
                self.task_queue.put(task)

            # 预估时间
            estimated_time = total_tasks * 1.0 / 60 / num_servers
            self.logger.info("⏰ 预计耗时: %.1f 分钟（%d进程真并行）", estimated_time, num_servers)

            # 初始化进度
            self._download_progress["is_downloading"] = True
            self._download_progress["completed"] = 0
            self._download_progress["total"] = total_tasks
            self._download_progress["start_time"] = datetime.now()

            # 步骤3：启动工作进程
            self.logger.info("【步骤3】启动 %d 个工作进程...", num_servers)
            self.logger.info("=" * 60)

            parallel_start_time = time.time()

            self._start_worker_processes(available_servers)

            # 步骤4：监控进度并收集结果
            self.logger.info("【步骤4】监控进度...")
            result = self._monitor_progress_and_collect_results(total_tasks, progress_callback)

            # 🚀 不设置stop_event！让工作进程检测到队列空后自动退出
            # 工作进程会在连续10次(5秒)队列空后自动退出
            # stop_event只用于手动停止
            self.logger.info("所有任务完成，等待进程自动退出...")
            time.sleep(6.0)  # 等待工作进程检测到队列空（至少5秒）并退出

            # 步骤5：清理进程
            self._cleanup_processes()

            # 性能统计
            total_time = time.time() - parallel_start_time

            # 🚀 统计有效数据和空数据
            valid_count = sum(1 for v in result.values() if v is not None and not v.empty)
            empty_count = len(result) - valid_count

            self.logger.info("=" * 60)
            self.logger.info("【完成】多进程下载完成")
            self.logger.info("  总任务数: %d", total_tasks)
            self.logger.info("  下载结果数: %d", len(result))
            self.logger.info("  有效数据: %d", valid_count)
            self.logger.info("  空数据: %d", empty_count)
            self.logger.info("  总耗时: %.1f秒 (%.1f分钟)", total_time, total_time / 60)
            self.logger.info(
                "  平均速度: %.1f个/秒", len(result) / total_time if total_time > 0 else 0
            )
            self.logger.info("=" * 60)

        except KeyboardInterrupt:
            self.logger.warning("下载被用户中断（KeyboardInterrupt）")
            self._download_progress["is_downloading"] = False
            try:
                self._cleanup_processes()
            except Exception as cleanup_err:
                self.logger.error("清理进程失败: %s", cleanup_err)
            return result

        except Exception as e:
            self.logger.error("多进程下载异常: %s", e, exc_info=True)
            self._download_progress["is_downloading"] = False
            try:
                self._cleanup_processes()
            except Exception as cleanup_err:
                self.logger.error("清理进程失败: %s", cleanup_err)
            return result

        finally:
            # 确保标记下载完成
            try:
                self._download_progress["is_downloading"] = False
            except:
                pass

            # 确保进程被清理（如果还没清理）
            try:
                if self.processes:
                    self._cleanup_processes()
            except:
                pass

        return result

    def _start_worker_processes(self, servers: List[Tuple[str, int]]):
        """
        启动工作进程

        Args:
            servers: 服务器列表
        """
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
        """
        监控进度并收集结果

        Args:
            total_tasks: 总任务数
            progress_callback: 进度回调函数

        Returns:
            结果字典
        """
        results = {}
        completed = 0
        last_callback_time = time.time()

        self.logger.info("开始监控 %d 个任务的进度...", total_tasks)

        # 等待所有任务完成或超时
        timeout_seconds = 3600  # 1小时总超时（避免大任务被误判超时）
        start_monitor_time = time.time()

        while completed < total_tasks:
            # 检查总超时
            if time.time() - start_monitor_time > timeout_seconds:
                self.logger.error("监控超时（%d秒），退出", timeout_seconds)
                break

            # 检查停止信号
            if self.stop_event.is_set():
                self.logger.warning("检测到停止信号，退出监控")
                break

            # 收集进度（优先级高，先收集进度）
            progress_collected = False
            try:
                symbol, interval = self.progress_queue.get(timeout=0.1)
                completed += 1
                progress_collected = True

                # 更新共享进度
                self._download_progress["completed"] = completed
                self._download_progress["current_symbol"] = symbol
                self._download_progress["current_interval"] = interval

                # 每10个打印一次（更频繁，便于调试）
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

                # 🚀 调用进度回调（传递给engine.py，再推送vnpy事件到UI）
                if progress_callback:
                    try:
                        # 调用回调函数（每个进度都调用，engine.py会推送事件到UI）
                        progress_callback(completed, total_tasks, symbol, interval)
                    except Exception as e:
                        self.logger.debug("进度回调失败（已忽略）: %s", e)

                # 🚀 终端进度输出（每10个打印一次）
                if completed % 10 == 0 or completed == total_tasks:
                    progress_pct = (completed / total_tasks) * 100
                    progress_text = f"📊 下载进度: {completed}/{total_tasks} ({progress_pct:.1f}%) - {symbol} {interval}"
                    print(progress_text)

            except queue.Empty:
                # 队列空，检查是否所有进程都退出了
                if not progress_collected and all(not p.is_alive() for p in self.processes):
                    self.logger.info("所有进程已退出，排空剩余队列...")
                    self._drain_queues(results)
                    # 更新completed以匹配实际收集的数据
                    completed = len(results)
                    break
            except Exception as e:
                self.logger.error("收集进度失败: %s", e)

            # 收集结果（非阻塞）
            try:
                key, data_dict = self.result_queue.get_nowait()

                # 将dict转回DataFrame
                if data_dict is not None:
                    df = pd.DataFrame(data_dict)
                    if "datetime" in df.columns:
                        df["datetime"] = pd.to_datetime(df["datetime"])
                    results[key] = df
                    self.logger.debug("收集结果: %s - %d行", key, len(df))

            except queue.Empty:
                # 结果队列暂时为空，继续
                pass
            except Exception as e:
                self.logger.error("收集结果失败: %s", e)

        self.logger.info("进度监控完成，已收集 %d/%d 个结果", len(results), completed)

        return results

    def _drain_queues(self, results: Dict):
        """
        排空队列中的剩余数据

        Args:
            results: 结果字典（会被修改）
        """
        # 排空结果队列
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
            except Exception as e:
                self.logger.error("排空结果队列失败: %s", e)
                break

        # 排空进度队列
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

        self.logger.info("清理 %d 个工作进程...", len(self.processes))

        try:
            # 先等待所有进程正常退出（短超时）
            for p in self.processes:
                if p.is_alive():
                    try:
                        p.join(timeout=2)
                    except Exception as e:
                        self.logger.debug("等待进程退出异常: %s", e)

            # 强制终止未响应的进程
            alive_count = 0
            for p in self.processes:
                if p.is_alive():
                    alive_count += 1
                    try:
                        self.logger.warning("进程 PID=%d 未响应，强制终止", p.pid)
                        p.terminate()
                        p.join(timeout=1)
                    except Exception as e:
                        self.logger.error("终止进程失败: %s", e)

            if alive_count > 0:
                self.logger.warning("强制终止了 %d 个未响应进程", alive_count)

            self.processes.clear()
            self.logger.info("✅ 进程清理完成")

        except Exception as e:
            self.logger.error("清理进程时异常: %s", e, exc_info=True)
            # 确保列表被清空
            self.processes.clear()

    def _clear_queues(self):
        """清空所有队列（防止上次残留）"""
        queues = [self.task_queue, self.result_queue, self.progress_queue]
        for q in queues:
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    # ==================== 向后兼容的API ====================

    def stop(self):
        """停止下载（兼容旧API）"""
        self.stop_download()

    def is_stopped(self) -> bool:
        """检查是否已停止（兼容旧API）"""
        return self.stop_event.is_set()

    def is_paused(self) -> bool:
        """检查是否已暂停（兼容旧API）"""
        return not self.pause_event.is_set()

    # ==================== 品种列表相关方法已迁移到symbol_loader.py ====================
    # 此类不再负责品种列表的获取和缓存，只负责K线数据下载

    def shutdown(self):
        """主动关闭（释放资源）"""
        try:
            # 设置停止事件
            self.stop_event.set()

            # 清理进程
            if self.processes:
                self._cleanup_processes()

            # 关闭Manager（重要！）
            if hasattr(self, "manager"):
                try:
                    self.manager.shutdown()
                    self.logger.info("✅ Manager已关闭")
                except Exception as e:
                    self.logger.warning("关闭Manager失败: %s", e)

        except Exception as e:
            self.logger.error("shutdown失败: %s", e)

    def __del__(self):
        """析构函数：确保进程被清理"""
        try:
            # 设置停止事件
            if hasattr(self, "stop_event"):
                try:
                    self.stop_event.set()
                except:
                    pass

            # 清理进程
            if hasattr(self, "processes") and self.processes:
                try:
                    self._cleanup_processes()
                except:
                    pass

            # 关闭Manager
            if hasattr(self, "manager"):
                try:
                    self.manager.shutdown()
                except:
                    pass

        except Exception as e:
            # 析构函数中的异常不要抛出
            try:
                if hasattr(self, "logger"):
                    self.logger.debug("析构清理异常: %s", e)
            except:
                pass
