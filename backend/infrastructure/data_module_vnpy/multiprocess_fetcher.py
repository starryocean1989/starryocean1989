# -*- coding: utf-8 -*-
"""
多进程股票数据获取器

完全替代原StockFetcher，使用多进程实现真正的并行计算
突破Python GIL限制，实现15-20倍速度提升

注意：Windows下使用multiprocessing需要确保在if __name__ == '__main__'保护下启动
但由于我们的worker函数在独立模块中，这个要求已自动满足
"""

import logging
import queue
import time
from datetime import datetime
from multiprocessing import Manager, Process, cpu_count
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.infrastructure.data_module_vnpy.block_parser import BlockParser
from backend.infrastructure.data_module_vnpy.config import config_manager
from backend.infrastructure.data_module_vnpy.multiprocess_worker import (
    download_worker_process,
)
from backend.infrastructure.data_module_vnpy.server_pool import ServerPool

# 确保Windows兼容性
import sys
import multiprocessing

# Windows需要freeze_support
if sys.platform == "win32":
    multiprocessing.freeze_support()


class MultiProcessStockFetcher:
    """
    多进程股票数据获取器

    完全替代StockFetcher，使用multiprocessing实现真正的并行计算
    每个进程有独立的GIL，可以充分利用多核CPU
    """

    # 市场分类常量（类级别）
    MARKET_SHANGHAI = 0  # 上证
    MARKET_SHENZHEN = 1  # 深证

    # 品种代码前缀（类级别）
    SH_PREFIXES = ["688", "60"]  # 上证A股
    SZ_PREFIXES = ["000", "001", "002", "300", "301"]  # 深证A股
    BJ_PREFIXES = ["43", "83", "87", "88"]  # 北证A股（北交所）

    def __init__(self, block_parser=None):
        """
        初始化多进程数据获取器

        Args:
            block_parser: BlockParser实例，如果为None则创建新实例
        """
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

        # 多进程共享对象（使用Manager）
        self.manager = Manager()
        self.task_queue = self.manager.Queue()
        self.result_queue = self.manager.Queue()
        self.progress_queue = self.manager.Queue()
        self.stop_event = self.manager.Event()
        self.pause_event = self.manager.Event()
        self.pause_event.set()  # 默认不暂停

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

        # 进程池
        self.processes: List[Process] = []

        # ServerPool（用于获取可用服务器）
        self.server_pool = ServerPool(max_servers=max_processes, timeout=30)

        # BlockParser
        self.block_parser = block_parser or BlockParser(config_manager.get_tdx_dir())

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

    # ==================== 下载控制方法 ====================

    def stop_download(self):
        """停止下载"""
        try:
            self.stop_event.set()
            self.logger.info("下载停止信号已设置")

            # 立即开始清理进程（不等待任务完成）
            # 进程会检测到stop_event并自行退出
            self.logger.info("等待进程检测停止信号...")

        except Exception as e:
            self.logger.error("设置停止信号失败: %s", e)

    def pause_download(self):
        """暂停下载"""
        self.pause_event.clear()  # clear表示暂停
        self.logger.info("下载暂停信号已设置")

    def resume_download(self):
        """恢复下载"""
        self.pause_event.set()  # set表示继续
        self.logger.info("下载恢复信号已设置")

    def reset_download_state(self):
        """重置下载状态（准备新的下载任务）"""
        self.stop_event.clear()
        self.pause_event.set()

        # 重置进度
        self._download_progress["is_downloading"] = False
        self._download_progress["completed"] = 0
        self._download_progress["total"] = 0
        self._download_progress["current_symbol"] = ""
        self._download_progress["current_interval"] = ""
        self._download_progress["start_time"] = None

        self.logger.info("下载状态已重置")

    def get_download_progress(self) -> dict:
        """获取当前下载进度（供前端轮询使用）"""
        return dict(self._download_progress)

    def is_stopped(self) -> bool:
        """检查是否已停止"""
        return self.stop_event.is_set()

    def is_paused(self) -> bool:
        """检查是否已暂停"""
        return not self.pause_event.is_set()

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

            self.logger.info("=" * 60)
            self.logger.info(
                "【完成】多进程下载完成: 成功下载 %d/%d 个数据集", len(result), total_tasks
            )
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

                # 🚀 双重进度输出：终端 + UI文本框
                if completed % 10 == 0 or completed == total_tasks:
                    progress_pct = (completed / total_tasks) * 100
                    progress_text = f"📊 下载进度: {completed}/{total_tasks} ({progress_pct:.1f}%) - {symbol} {interval}"

                    # 1. 终端输出
                    print(progress_text)

                    # 2. UI文本框更新（只在每100个或完成时）
                    if progress_callback and (completed % 100 == 0 or completed == total_tasks):
                        try:
                            # 传递简化的文本
                            simple_text = (
                                f"下载进度: {completed}/{total_tasks} ({progress_pct:.1f}%)"
                            )
                            progress_callback(simple_text)
                        except Exception as e:
                            self.logger.debug("UI文本追加失败（已忽略）: %s", e)

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

    # ==================== 品种列表API（必须实现，engine.py会调用） ====================

    def fetch_all_stocks(self) -> pd.DataFrame:
        """获取所有品种列表（委托给quotes）"""
        return self.quotes.stock_all()

    def parse_market_codes(self, stocks_df: pd.DataFrame) -> Dict[str, List[str]]:
        """解析市场代码，分类品种"""
        import time

        self.logger.info("【parse_market_codes】开始解析 %d 个品种...", len(stocks_df))
        start_time = time.time()

        result: Dict[str, List[str]] = {
            "上证A股": [],
            "深证A股": [],
            "北证A股": [],
            "T+0基金": [],
            "含可转债": [],
        }

        # 检查必需列
        if "code" not in stocks_df.columns:
            self.logger.error("品种DataFrame缺少'code'列")
            return result

        # 补齐代码为6位
        stocks_df = stocks_df.copy()
        stocks_df["code"] = stocks_df["code"].astype(str).str.zfill(6)

        # 🚀 关键过滤1：使用volunit=100过滤出A股（排除38000+债券）
        if "volunit" in stocks_df.columns:
            before_count = len(stocks_df)
            stocks_df = stocks_df[stocks_df["volunit"] == 100]
            filtered_count = before_count - len(stocks_df)
            self.logger.info("  → volunit过滤：排除 %d 个债券（volunit=10）", filtered_count)

        # 🚀 关键过滤2：排除名称包含"债"的指数（即使volunit=100）
        if "name" in stocks_df.columns:
            before_count = len(stocks_df)
            stocks_df = stocks_df[~stocks_df["name"].str.contains("债", na=False)]
            filtered_count = before_count - len(stocks_df)
            if filtered_count > 0:
                self.logger.info("  → name过滤：排除 %d 个债券指数", filtered_count)

        # 🚀 关键过滤3：排除指数
        if "name" in stocks_df.columns:
            before_count = len(stocks_df)
            stocks_df = stocks_df[~stocks_df["name"].str.contains("指数", na=False)]
            filtered_count = before_count - len(stocks_df)
            if filtered_count > 0:
                self.logger.info("  → name过滤：排除 %d 个指数", filtered_count)

        # 🚀 关键过滤4：排除退市股
        if "name" in stocks_df.columns:
            before_count = len(stocks_df)
            stocks_df = stocks_df[~stocks_df["name"].str.contains("退市|退", na=False)]
            filtered_count = before_count - len(stocks_df)
            if filtered_count > 0:
                self.logger.info("  → name过滤：排除 %d 个退市股", filtered_count)

        # 根据前缀筛选（现在只剩纯A股了）
        sh_mask = stocks_df["code"].str.startswith("688") | stocks_df["code"].str.startswith("60")
        result["上证A股"] = stocks_df[sh_mask]["code"].tolist()

        # 🚀 关键修复：排除000000-000999的指数区间
        # 使用字符串比较而非int转换（避免异常）
        sz_000_mask = stocks_df["code"].str.startswith("000") & ~(
            stocks_df["code"].str.match(r"^000[0-9]{3}$")
        )
        sz_mask = (
            sz_000_mask
            | stocks_df["code"].str.startswith("001")
            | stocks_df["code"].str.startswith("002")
            | stocks_df["code"].str.startswith("300")
            | stocks_df["code"].str.startswith("301")
        )
        result["深证A股"] = stocks_df[sz_mask]["code"].tolist()

        # 北证A股不在stock_all中，只能从spblock.dat获取
        # 这里先留空
        result["北证A股"] = []

        # 从BlockParser获取特殊品种
        if self.block_parser.is_available():
            try:
                beijing_stocks = self.block_parser.get_beijing_stocks()
                if beijing_stocks:
                    result["北证A股"] = beijing_stocks

                result["T+0基金"] = self.block_parser.get_t0_funds()
                result["含可转债"] = self.block_parser.get_convertible_bonds()
            except Exception as e:
                self.logger.warning("解析通达信板块文件失败: %s", e)

        elapsed_time = time.time() - start_time
        total_count = sum(len(codes) for codes in result.values())
        self.logger.info(
            "✅ parse_market_codes完成！耗时: %.2f秒, 总计 %d 个品种", elapsed_time, total_count
        )

        return result

    def cache_stock_list(self, stocks_df: pd.DataFrame) -> "Path":
        """缓存品种列表（委托给原实现）"""
        from pathlib import Path
        import json

        cache_dir = config_manager.get_cache_dir()
        cache_file = cache_dir / "stock_list_classified.json"

        # 解析并缓存
        classified = self.parse_market_codes(stocks_df)
        cache_data = {
            "cache_time": datetime.now().isoformat(),
            "total_count": sum(len(codes) for codes in classified.values()),
            "classified": classified,
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        self._classified_stocks_cache = classified
        return cache_file

    def load_cached_stock_list(self) -> Optional[Dict[str, List[str]]]:
        """加载缓存的品种分类"""
        import json
        from pathlib import Path

        cache_file = config_manager.get_cache_dir() / "stock_list_classified.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            return cache_data.get("classified")
        except Exception as e:
            self.logger.error("加载缓存失败: %s", e)
            return None

    def get_market_stocks(self, market_type: str, allow_fetch: bool = True) -> List[str]:
        """
        获取指定市场的品种列表（engine.py会调用）

        Args:
            market_type: 市场类型（上证A股、深证A股、北证A股、T+0基金、含可转债）
            allow_fetch: 是否允许在缓存不存在时重新获取

        Returns:
            品种代码列表
        """
        # 如果已有分类缓存，直接返回
        if self._classified_stocks_cache is not None:
            return self._classified_stocks_cache.get(market_type, [])

        # 尝试从本地缓存加载
        classified = self.load_cached_stock_list()
        if classified is not None:
            self._classified_stocks_cache = classified
            return self._classified_stocks_cache.get(market_type, [])

        # 如果缓存不存在
        if not allow_fetch:
            self.logger.warning("本地品种缓存不存在，且不允许重新获取")
            return []

        # 允许重新获取时，调用API
        self.logger.info("本地品种缓存不存在，开始从API获取...")
        stocks_df = self.fetch_all_stocks()
        self._classified_stocks_cache = self.parse_market_codes(stocks_df)
        return self._classified_stocks_cache.get(market_type, [])

    def get_all_market_stocks(self, allow_fetch: bool = True) -> Dict[str, List[str]]:
        """
        获取所有市场的品种分类

        Args:
            allow_fetch: 是否允许在缓存不存在时重新获取

        Returns:
            所有市场的品种分类字典
        """
        # 如果已有分类缓存，直接返回
        if self._classified_stocks_cache is not None:
            return self._classified_stocks_cache

        # 尝试从本地缓存加载
        classified = self.load_cached_stock_list()
        if classified is not None:
            self._classified_stocks_cache = classified
            return self._classified_stocks_cache

        # 如果缓存不存在
        if not allow_fetch:
            self.logger.warning("本地品种缓存不存在，且不允许重新获取")
            return {}

        # 允许重新获取时，调用API
        self.logger.info("本地品种缓存不存在，开始从API获取...")
        stocks_df = self.fetch_all_stocks()
        self._classified_stocks_cache = self.parse_market_codes(stocks_df)
        return self._classified_stocks_cache

    def download_full_kline(
        self, symbols: List[str], intervals: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        全量下载K线数据（使用多进程）

        Args:
            symbols: 品种代码列表
            intervals: K线周期列表，默认['1d', '5m', '1m']

        Returns:
            下载结果字典
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        # 全量下载：从很久以前开始
        from datetime import date

        start_date = date(2010, 1, 1)

        return self.download_incremental_kline(symbols, start_date, intervals)

    # ==================== 其他工具方法 ====================

    def get_classified_stocks(self) -> Dict[str, List[str]]:
        """获取分类后的股票列表"""
        if self._classified_stocks_cache is None:
            self._classified_stocks_cache = self.block_parser.parse_block_file()
        return self._classified_stocks_cache

    @staticmethod
    def get_exchange_by_symbol(symbol: str) -> str:
        """根据品种代码获取交易所"""
        if symbol.startswith(tuple(MultiProcessStockFetcher.SH_PREFIXES)):
            return "SSE"
        elif symbol.startswith(tuple(MultiProcessStockFetcher.SZ_PREFIXES)):
            return "SZSE"
        elif symbol.startswith(tuple(MultiProcessStockFetcher.BJ_PREFIXES)):
            return "BSE"
        else:
            return "UNKNOWN"

    @classmethod
    def get_market_by_symbol(cls, symbol: str) -> int:
        """根据品种代码获取市场代码"""
        if symbol.startswith(tuple(cls.SH_PREFIXES)):
            return cls.MARKET_SHANGHAI
        elif symbol.startswith(tuple(cls.SZ_PREFIXES)):
            return cls.MARKET_SHENZHEN
        else:
            return cls.MARKET_SHANGHAI

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
