# -*- coding: utf-8 -*-
"""
混合异步数据质量扫描引擎

四层架构：
- Layer 1: 协程层 (1000+并发) - 小文件I/O，异步元数据扫描
- Layer 2: 线程层 (20-50并发) - 中等文件I/O
- Layer 3: 进程层 (4-16并发) - CPU密集计算，数据验证
- Layer 4: 智能调度 - 动态资源感知，任务分配，并发调节

本文件整合了8个异步组件，提供统一的混合异步架构接口。
"""

# ==================== 导入声明 ====================

import asyncio
import logging
import multiprocessing as mp
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psutil

try:
    import aiofiles
    import aiofiles.os
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    logging.warning("aiofiles未安装，将使用同步I/O降级方案")


# ==================== 数据类定义 ====================

@dataclass
class FileMetadata:
    """文件元数据"""
    path: Path
    symbol: str
    interval: str
    size: int
    mtime: float
    exists: bool
    has_data: bool
    category: str  # "small" | "medium" | "large"

    def __post_init__(self):
        """提取品种和周期信息"""
        if not self.symbol:
            # 从路径提取: data/kline/600000/1d/data.parquet
            parts = self.path.parts
            if len(parts) >= 3:
                self.symbol = parts[-3]  # 600000
                self.interval = parts[-2]  # 1d


@dataclass
class ScanTask:
    """扫描任务"""
    symbol: str
    interval: str
    file_path: Optional[str] = None
    file_size: int = 0
    cpu_intensive: bool = False  # 是否CPU密集型
    task_type: str = "validation"  # "validation" | "freshness" | "metadata"


# ==================== Layer 4: 资源监控 ====================

class ResourceMonitor:
    """实时系统资源监控器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 资源状态
        self.cpu_percent = 0.0
        self.memory_available_gb = 0.0
        self.memory_percent = 0.0
        self.disk_io_busy = False
        self.disk_read_mb_per_sec = 0.0
        self.disk_write_mb_per_sec = 0.0
        
        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # 历史记录（用于计算平均值）
        self._cpu_history = []
        self._memory_history = []
        self._max_history_size = 10

    def start_monitoring(self, interval: float = 0.5):
        """启动后台监控线程
        
        Args:
            interval: 监控间隔（秒），默认0.5秒
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            self.logger.warning("资源监控线程已在运行")
            return
        
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True,
            name="ResourceMonitorThread"
        )
        self._monitor_thread.start()
        self.logger.info(f"✅ 资源监控线程已启动（间隔{interval}秒）")

    def stop_monitoring(self):
        """停止监控线程"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._stop_event.set()
            self._monitor_thread.join(timeout=2.0)
            self.logger.info("资源监控线程已停止")

    def _monitoring_loop(self, interval: float):
        """监控循环"""
        last_disk_io = psutil.disk_io_counters()
        
        while not self._stop_event.is_set():
            try:
                # 获取CPU使用率
                cpu = psutil.cpu_percent(interval=0.1)
                
                # 获取内存信息
                memory = psutil.virtual_memory()
                memory_available = memory.available / (1024 ** 3)  # GB
                memory_percent = memory.percent
                
                # 获取磁盘I/O
                current_disk_io = psutil.disk_io_counters()
                if last_disk_io and current_disk_io:
                    read_mb = (current_disk_io.read_bytes - last_disk_io.read_bytes) / (1024 * 1024)
                    write_mb = (current_disk_io.write_bytes - last_disk_io.write_bytes) / (1024 * 1024)
                    disk_read_mb_per_sec = read_mb / interval
                    disk_write_mb_per_sec = write_mb / interval
                    # 判断磁盘是否繁忙（读写速度超过100MB/s）
                    disk_busy = (disk_read_mb_per_sec + disk_write_mb_per_sec) > 100
                else:
                    disk_read_mb_per_sec = 0
                    disk_write_mb_per_sec = 0
                    disk_busy = False
                
                last_disk_io = current_disk_io
                
                # 更新状态（线程安全）
                with self._lock:
                    self.cpu_percent = cpu
                    self.memory_available_gb = memory_available
                    self.memory_percent = memory_percent
                    self.disk_io_busy = disk_busy
                    self.disk_read_mb_per_sec = disk_read_mb_per_sec
                    self.disk_write_mb_per_sec = disk_write_mb_per_sec
                    
                    # 更新历史记录
                    self._cpu_history.append(cpu)
                    self._memory_history.append(memory_percent)
                    if len(self._cpu_history) > self._max_history_size:
                        self._cpu_history.pop(0)
                    if len(self._memory_history) > self._max_history_size:
                        self._memory_history.pop(0)
                
                # 等待下一次监控
                time.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"资源监控失败: {e}", exc_info=True)
                time.sleep(interval)

    def get_current_status(self) -> Dict:
        """获取当前资源状态快照"""
        with self._lock:
            return {
                "cpu_percent": self.cpu_percent,
                "memory_available_gb": self.memory_available_gb,
                "memory_percent": self.memory_percent,
                "disk_io_busy": self.disk_io_busy,
                "disk_read_mb_per_sec": self.disk_read_mb_per_sec,
                "disk_write_mb_per_sec": self.disk_write_mb_per_sec,
                "avg_cpu_percent": sum(self._cpu_history) / len(self._cpu_history) if self._cpu_history else 0,
                "avg_memory_percent": sum(self._memory_history) / len(self._memory_history) if self._memory_history else 0,
            }

    def get_optimal_concurrency(self) -> Dict:
        """根据当前资源状态返回最优并发配置
        
        Returns:
            Dict: 包含 async_workers, thread_workers, process_workers 的配置
        """
        with self._lock:
            cpu = self.cpu_percent
            memory_available = self.memory_available_gb
            disk_busy = self.disk_io_busy
        
        # 基础配置
        config = {
            "async_workers": 1000,
            "thread_workers": 20,
            "process_workers": 8,
        }
        
        # 根据内存调整协程数量
        if memory_available > 8:
            config["async_workers"] = 2000
        elif memory_available > 4:
            config["async_workers"] = 1000
        elif memory_available > 2:
            config["async_workers"] = 500
        else:
            config["async_workers"] = 200  # 内存紧张，降低并发
        
        # 根据CPU调整线程/进程数
        if float(cpu) < 30:
            # CPU空闲，提高并发
            config["thread_workers"] = 50
            config["process_workers"] = 12
        elif float(cpu) < 50:
            # CPU正常，使用默认配置
            config["thread_workers"] = 20
            config["process_workers"] = 8
        elif float(cpu) < 70:
            # CPU较忙，适度降低
            config["thread_workers"] = 10
            config["process_workers"] = 4
        else:
            # CPU繁忙，大幅降低
            config["thread_workers"] = 5
            config["process_workers"] = 2
        
        # 磁盘繁忙时降低I/O并发
        if disk_busy:
            config["async_workers"] = min(config["async_workers"], 500)
            config["thread_workers"] = min(config["thread_workers"], 10)
        
        return config

    def get_summary(self) -> str:
        """获取资源状态摘要（用于日志）"""
        status = self.get_current_status()
        return (
            f"CPU: {status['cpu_percent']:.1f}% (avg: {status['avg_cpu_percent']:.1f}%), "
            f"内存可用: {status['memory_available_gb']:.2f}GB ({100-status['memory_percent']:.1f}%), "
            f"磁盘I/O: {status['disk_read_mb_per_sec']:.1f}MB/s 读, "
            f"{status['disk_write_mb_per_sec']:.1f}MB/s 写"
        )

    def __del__(self):
        """析构时停止监控"""
        self.stop_monitoring()


# ==================== Layer 4: 自适应配置 ====================

class AdaptiveQualityConfig:
    """自适应数据质量配置计算器"""

    @staticmethod
    def calculate_optimal_config(
        symbols_count: int,
        enable_detailed_scan: bool = True,
        min_workers: int = 1,
        max_workers: Optional[int] = None,
        memory_per_symbol_mb: float = 0.1,  # 每个品种约0.1MB
    ) -> Dict:
        """计算最优的质量扫描配置

        Args:
            symbols_count: 品种数量
            enable_detailed_scan: 是否启用详细扫描（错误/警告检查）
            min_workers: 最小工作线程数
            max_workers: 最大工作线程数（None表示不限制）
            memory_per_symbol_mb: 每个品种的内存消耗（MB）

        Returns:
            Dict 包含：
            - scan_mode: 扫描模式 ("fast" | "balanced" | "thorough")
            - max_workers: 推荐的最大工作线程数
            - batch_size: 批量处理大小
            - enable_multiprocessing: 是否启用多进程
            - num_processes: 进程数（如果启用多进程）
            - workers_per_process: 每个进程的线程数
            - chunk_size: 每个进程处理的品种数
            - estimated_memory_mb: 预计内存消耗
            - cpu_cores: CPU核心数
            - available_memory_gb: 可用内存（GB）
            - reason: 配置选择原因
        """
        logger = logging.getLogger(__name__)

        # 1. 获取系统资源
        cpu_cores = mp.cpu_count()
        memory = psutil.virtual_memory()
        available_memory_gb = memory.available / (1024**3)

        # 2. 根据品种数量选择扫描模式
        if symbols_count < 100:
            scan_mode = "fast"
            recommended_workers = 1
            batch_size = 50
            enable_mp = False
            reason = "小数据集，单线程即可"

        elif symbols_count < 1000:
            scan_mode = "balanced"
            recommended_workers = min(10, cpu_cores)
            batch_size = 100
            enable_mp = False
            reason = "中等数据集，多线程并发"

        elif symbols_count < 3000:
            scan_mode = "balanced"
            recommended_workers = min(cpu_cores, 16)
            batch_size = 200
            enable_mp = False
            reason = "中大数据集，增强多线程"

        else:
            # 大数据集，考虑多进程
            scan_mode = "thorough"
            # 进程数：使用CPU核心数的75%，最多16个
            num_processes = min(max(4, int(cpu_cores * 0.75)), 16)
            workers_per_process = 10
            recommended_workers = num_processes * workers_per_process
            batch_size = 500
            enable_mp = True
            reason = "大数据集，多进程+多线程"

        # 3. 应用最小/最大限制
        if max_workers is not None:
            recommended_workers = min(recommended_workers, max_workers)
        recommended_workers = max(recommended_workers, min_workers)

        # 4. 内存检查
        estimated_memory_mb = symbols_count * memory_per_symbol_mb
        max_safe_memory_mb = available_memory_gb * 1024 * 0.3  # 最多使用30%可用内存

        if estimated_memory_mb > max_safe_memory_mb:
            logger.warning(
                f"预计内存消耗 {estimated_memory_mb:.2f} MB 超过安全阈值 "
                f"{max_safe_memory_mb:.2f} MB，降低并发"
            )
            recommended_workers = max(min_workers, recommended_workers // 2)
            if enable_mp:
                num_processes = max(2, num_processes // 2)
                recommended_workers = num_processes * workers_per_process
            reason += "（内存限制已降低并发）"

        # 5. 如果不启用详细扫描，可以提高并发
        if not enable_detailed_scan:
            # 不扫描错误/警告，内存消耗更低，可以提高并发
            recommended_workers = int(recommended_workers * 1.5)
            if enable_mp:
                workers_per_process = int(workers_per_process * 1.5)
                recommended_workers = num_processes * workers_per_process

        # 6. 构建配置结果
        config = {
            "scan_mode": scan_mode,
            "max_workers": recommended_workers,
            "batch_size": batch_size,
            "enable_multiprocessing": enable_mp,
            "estimated_memory_mb": estimated_memory_mb,
            "cpu_cores": cpu_cores,
            "available_memory_gb": available_memory_gb,
            "symbols_count": symbols_count,
            "enable_detailed_scan": enable_detailed_scan,
            "reason": reason,
        }

        # 7. 如果启用多进程，添加进程相关配置
        if enable_mp:
            chunk_size = (symbols_count + num_processes - 1) // num_processes
            config.update(
                {
                    "num_processes": num_processes,
                    "workers_per_process": workers_per_process,
                    "chunk_size": chunk_size,
                }
            )

        return config

    @staticmethod
    def get_config_summary(config: Dict) -> str:
        """生成配置摘要（用于日志输出）

        Args:
            config: 配置字典

        Returns:
            str: 配置摘要
        """
        lines = [
            "【自适应数据质量扫描配置】",
            f"  扫描模式: {config['scan_mode']}",
            f"  品种数量: {config['symbols_count']}",
            f"  CPU核心: {config['cpu_cores']}",
            f"  可用内存: {config['available_memory_gb']:.2f} GB",
        ]

        if config["enable_multiprocessing"]:
            lines.extend(
                [
                    f"  进程数: {config['num_processes']}",
                    f"  每进程线程: {config['workers_per_process']}",
                    f"  每进程品种: {config['chunk_size']}",
                    f"  总工作线程: {config['max_workers']}",
                ]
            )
        else:
            lines.append(f"  工作线程: {config['max_workers']}")

        lines.extend(
            [
                f"  批量大小: {config['batch_size']}",
                f"  详细扫描: {'是' if config['enable_detailed_scan'] else '否'}",
                f"  预计内存: {config['estimated_memory_mb']:.2f} MB",
                f"  配置原因: {config['reason']}",
            ]
        )

        return "\n".join(lines)


# ==================== Layer 1: 文件元数据扫描 ====================

class FileMetadataScanner:
    """异步文件元数据扫描器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._use_async = AIOFILES_AVAILABLE

    async def scan_all_files_async(
        self,
        data_dir: Path,
        max_concurrency: int = 1000
    ) -> Dict[str, FileMetadata]:
        """并发扫描所有Parquet文件元数据
        
        Args:
            data_dir: 数据目录（如 data/kline）
            max_concurrency: 最大并发数
            
        Returns:
            Dict[str, FileMetadata]: 文件元数据字典，key为 "{symbol}_{interval}"
        """
        if not data_dir.exists():
            self.logger.warning(f"数据目录不存在: {data_dir}")
            return {}

        # 收集所有需要扫描的文件路径
        file_paths = self._collect_file_paths(data_dir)
        
        if not file_paths:
            self.logger.warning(f"数据目录为空: {data_dir}")
            return {}

        self.logger.info(f"开始扫描{len(file_paths)}个文件的元数据（并发{max_concurrency}）")

        # 使用信号量控制并发度
        semaphore = asyncio.Semaphore(max_concurrency)

        async def scan_one_with_semaphore(path):
            async with semaphore:
                return await self._get_file_metadata_async(path)

        # 并发执行所有扫描任务
        tasks = [scan_one_with_semaphore(p) for p in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 构建索引
        metadata_index = {}
        for result in results:
            if isinstance(result, FileMetadata) and result.exists:
                key = f"{result.symbol}_{result.interval}"
                metadata_index[key] = result
            elif isinstance(result, Exception):
                self.logger.debug(f"扫描文件失败: {result}")

        self.logger.info(f"扫描完成，找到{len(metadata_index)}个有效文件")
        return metadata_index

    def _collect_file_paths(self, data_dir: Path) -> List[Path]:
        """收集所有Parquet文件路径
        
        目录结构: data/kline/{symbol}/{interval}/data.parquet
        """
        file_paths = []
        
        try:
            for symbol_dir in data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                
                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue
                    
                    data_file = interval_dir / "data.parquet"
                    if data_file.exists():
                        file_paths.append(data_file)
        
        except Exception as e:
            self.logger.error(f"收集文件路径失败: {e}", exc_info=True)
        
        return file_paths

    async def _get_file_metadata_async(self, file_path: Path) -> FileMetadata:
        """异步获取单个文件元数据"""
        try:
            # 使用异步I/O获取文件状态
            if self._use_async and AIOFILES_AVAILABLE:
                stat = await aiofiles.os.stat(str(file_path))
            else:
                # 降级到同步I/O
                stat = await asyncio.to_thread(file_path.stat)
            
            size = stat.st_size
            mtime = stat.st_mtime
            has_data = size > 0
            
            # 分类文件大小
            if size < 1024 * 1024:  # < 1MB
                category = "small"
            elif size < 10 * 1024 * 1024:  # < 10MB
                category = "medium"
            else:
                category = "large"
            
            # 从路径提取品种和周期
            parts = file_path.parts
            symbol = parts[-3] if len(parts) >= 3 else ""
            interval = parts[-2] if len(parts) >= 2 else ""
            
            return FileMetadata(
                path=file_path,
                symbol=symbol,
                interval=interval,
                size=size,
                mtime=mtime,
                exists=True,
                has_data=has_data,
                category=category
            )
        
        except FileNotFoundError:
            return FileMetadata(
                path=file_path,
                symbol="",
                interval="",
                size=0,
                mtime=0,
                exists=False,
                has_data=False,
                category="small"
            )
        except Exception as e:
            self.logger.debug(f"获取文件元数据失败 {file_path}: {e}")
            return FileMetadata(
                path=file_path,
                symbol="",
                interval="",
                size=0,
                mtime=0,
                exists=False,
                has_data=False,
                category="small"
            )

    def scan_all_files_sync(
        self,
        data_dir: Path,
        max_concurrency: int = 1000
    ) -> Dict[str, FileMetadata]:
        """同步包装器（向后兼容）"""
        return asyncio.run(self.scan_all_files_async(data_dir, max_concurrency))

    async def get_symbols_with_data_async(self, data_dir: Path) -> List[str]:
        """获取所有有数据的品种代码列表（异步版）
        
        这是对 StorageManager.get_local_data_index() 的异步高性能替代
        """
        metadata = await self.scan_all_files_async(data_dir, max_concurrency=1000)
        
        # 提取唯一的品种代码
        symbols = set()
        for meta in metadata.values():
            if meta.has_data and meta.symbol:
                symbols.add(meta.symbol)
        
        return sorted(list(symbols))

    def get_symbols_with_data_sync(self, data_dir: Path) -> List[str]:
        """获取所有有数据的品种代码列表（同步版）"""
        return asyncio.run(self.get_symbols_with_data_async(data_dir))


# ==================== Layer 4: 智能任务调度 ====================

class SmartScheduler:
    """智能任务调度器"""

    def __init__(
        self,
        resource_monitor: ResourceMonitor,
        small_file_threshold_kb: int = 1024,  # < 1MB用协程
        large_file_threshold_kb: int = 10240,  # > 10MB用进程
    ):
        self.logger = logging.getLogger(__name__)
        self.resource_monitor = resource_monitor
        self.small_file_threshold = small_file_threshold_kb * 1024
        self.large_file_threshold = large_file_threshold_kb * 1024

    def schedule_tasks(self, tasks: List[ScanTask]) -> Dict[str, List[ScanTask]]:
        """智能任务分配
        
        分配策略：
        1. 小文件(<1MB) + 非CPU密集 → 协程层（海量并发）
        2. 中等文件(1-10MB) + I/O密集 → 线程池（中等并发）
        3. 大文件(>10MB) 或 CPU密集 → 进程池（低并发，高CPU利用率）
        
        Args:
            tasks: 待调度的任务列表
            
        Returns:
            Dict: 调度结果，包含 "async", "thread", "process" 三个键
        """
        scheduled = {
            "async": [],  # 协程处理（快速元数据、小文件）
            "thread": [],  # 线程处理（中等I/O）
            "process": []  # 进程处理（重型计算）
        }

        # 获取当前系统资源状态
        resource_status = self.resource_monitor.get_current_status()
        cpu_percent = resource_status.get("cpu_percent", 50)
        memory_available_gb = resource_status.get("memory_available_gb", 4)

        for task in tasks:
            # 策略1：CPU密集型任务优先使用进程池
            if task.cpu_intensive:
                # 但如果CPU已经很忙，降级到线程池
                if cpu_percent > 80:
                    scheduled["thread"].append(task)
                else:
                    scheduled["process"].append(task)
                continue

            # 策略2：根据文件大小分配
            if task.file_size < self.small_file_threshold:
                # 小文件用协程（除非内存紧张）
                if memory_available_gb > 1:
                    scheduled["async"].append(task)
                else:
                    scheduled["thread"].append(task)
            
            elif task.file_size > self.large_file_threshold:
                # 大文件用进程池（如果CPU空闲）
                if cpu_percent < 60:
                    scheduled["process"].append(task)
                else:
                    scheduled["thread"].append(task)
            
            else:
                # 中等文件用线程池
                scheduled["thread"].append(task)

        # 日志统计
        self.logger.info(
            f"任务调度完成：协程{len(scheduled['async'])}个，"
            f"线程{len(scheduled['thread'])}个，"
            f"进程{len(scheduled['process'])}个"
        )

        return scheduled

    def create_validation_tasks(
        self,
        symbols: List[str],
        intervals: List[str],
        file_metadata: Dict[str, FileMetadata]
    ) -> List[ScanTask]:
        """创建数据验证任务列表
        
        Args:
            symbols: 品种列表
            intervals: 周期列表
            file_metadata: 文件元数据索引
            
        Returns:
            List[ScanTask]: 任务列表
        """
        tasks = []
        
        for symbol in symbols:
            for interval in intervals:
                key = f"{symbol}_{interval}"
                meta = file_metadata.get(key)
                
                if meta and meta.has_data:
                    # 根据文件大小判断是否CPU密集
                    # 大文件的验证需要更多CPU计算
                    cpu_intensive = meta.size > self.large_file_threshold
                    
                    task = ScanTask(
                        symbol=symbol,
                        interval=interval,
                        file_path=str(meta.path) if meta.path else None,
                        file_size=meta.size,
                        cpu_intensive=cpu_intensive,
                        task_type="validation"
                    )
                    tasks.append(task)
        
        return tasks

    def create_freshness_tasks(
        self,
        symbols: List[str],
        interval: str = "1d"
    ) -> List[ScanTask]:
        """创建数据更新检查任务列表
        
        更新检查是I/O密集型，不是CPU密集型
        """
        tasks = []
        
        for symbol in symbols:
            task = ScanTask(
                symbol=symbol,
                interval=interval,
                file_size=0,  # 未知大小
                cpu_intensive=False,  # 非CPU密集
                task_type="freshness"
            )
            tasks.append(task)
        
        return tasks

    def get_optimal_batch_size(self, task_count: int, executor_type: str) -> int:
        """计算最优批量大小
        
        Args:
            task_count: 任务总数
            executor_type: 执行器类型 ("async" | "thread" | "process")
            
        Returns:
            int: 批量大小
        """
        if executor_type == "async":
            # 协程可以处理大批量
            return min(task_count, 1000)
        elif executor_type == "thread":
            # 线程池适合中等批量
            return min(task_count, 100)
        else:  # process
            # 进程池批量较小（减少进程间通信开销）
            return min(task_count, 20)


# ==================== Layer 1: 协程执行器 ====================

class AsyncIOExecutor:
    """协程I/O执行器"""

    def __init__(self, storage_manager=None, validator=None):
        self.logger = logging.getLogger(__name__)
        self.storage_manager = storage_manager
        self.validator = validator
        self._use_async = AIOFILES_AVAILABLE

    async def batch_read_small_files_async(
        self,
        file_paths: List[Path],
        max_concurrency: int = 1000
    ) -> List[Optional[pd.DataFrame]]:
        """批量异步读取小文件
        
        优势：
        - 可以同时打开1000+个文件
        - 内存占用极低（每个协程仅KB级）
        - 完全无阻塞
        
        Args:
            file_paths: 文件路径列表
            max_concurrency: 最大并发数
            
        Returns:
            List[Optional[pd.DataFrame]]: 数据列表，失败则为None
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def read_one(path):
            async with semaphore:
                try:
                    return await self._read_parquet_async(path)
                except Exception as e:
                    self.logger.debug(f"读取文件失败 {path}: {e}")
                    return None

        tasks = [read_one(p) for p in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.debug(f"读取异常: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)
        
        return processed_results

    async def _read_parquet_async(self, file_path: Path) -> pd.DataFrame:
        """异步读取Parquet文件
        
        策略：先异步读取文件内容到内存，再在executor中解析
        """
        if self._use_async and AIOFILES_AVAILABLE:
            # 使用aiofiles异步读取
            async with aiofiles.open(file_path, 'rb') as f:
                content = await f.read()
        else:
            # 降级到线程池
            loop = asyncio.get_event_loop()
            def read_sync():
                with open(file_path, 'rb') as f:
                    return f.read()
            content = await loop.run_in_executor(None, read_sync)

        # Pandas操作在executor中执行（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,  # 使用默认ThreadPoolExecutor
            pd.read_parquet,
            BytesIO(content)
        )
        return df

    async def batch_check_freshness_async(
        self,
        symbols: List[str],
        interval: str = "1d",
        max_concurrency: int = 500
    ) -> List[Dict]:
        """异步批量检查数据更新状态
        
        阶段2使用：5760个品种，1-2秒完成（vs 当前10秒）
        
        Args:
            symbols: 品种列表
            interval: K线周期
            max_concurrency: 最大并发数
            
        Returns:
            List[Dict]: 更新状态列表
        """
        if self.validator is None:
            self.logger.warning("未提供validator，无法检查数据更新状态")
            return []

        semaphore = asyncio.Semaphore(max_concurrency)

        async def check_one(symbol):
            async with semaphore:
                try:
                    return await self._check_one_freshness_async(symbol, interval)
                except Exception as e:
                    self.logger.debug(f"检查更新状态失败 {symbol}: {e}")
                    return {
                        "symbol": symbol,
                        "has_data": False,
                        "gap_days": -1,
                        "is_up_to_date": False
                    }

        tasks = [check_one(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.debug(f"检查异常: {result}")
                processed_results.append({
                    "symbol": "",
                    "has_data": False,
                    "gap_days": -1,
                    "is_up_to_date": False
                })
            else:
                processed_results.append(result)
        
        return processed_results

    async def _check_one_freshness_async(self, symbol: str, interval: str) -> Dict:
        """异步检查单个品种的数据更新状态
        
        在线程池中执行同步的validator方法
        """
        if self.validator is None:
            return {
                "symbol": symbol,
                "has_data": False,
                "gap_days": -1,
                "is_up_to_date": False
            }
        
        loop = asyncio.get_event_loop()
        
        # 在线程池中执行同步方法
        result = await loop.run_in_executor(
            None,
            self.validator.check_data_freshness,
            symbol,
            interval
        )
        
        # 添加symbol信息
        result["symbol"] = symbol
        return result

    async def batch_validate_data_async(
        self,
        tasks: List,  # List[ScanTask]
        max_concurrency: int = 500
    ) -> List[Dict]:
        """异步批量验证数据质量
        
        用于轻量级验证（非CPU密集型）
        """
        if self.validator is None:
            self.logger.warning("未提供validator，无法验证数据质量")
            return []

        semaphore = asyncio.Semaphore(max_concurrency)

        async def validate_one(task):
            async with semaphore:
                try:
                    # 在线程池中执行验证
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        self._validate_symbol_sync,
                        task.symbol,
                        task.interval
                    )
                    return result
                except Exception as e:
                    self.logger.debug(f"验证失败 {task.symbol} {task.interval}: {e}")
                    return None

        async_tasks = [validate_one(t) for t in tasks]
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        # 过滤异常
        valid_results: List[Dict] = []
        for r in results:
            if isinstance(r, Dict) and not isinstance(r, Exception):
                valid_results.append(r)
        return valid_results

    def _validate_symbol_sync(self, symbol: str, interval: str) -> Dict:
        """同步验证方法（在线程池中执行）"""
        # 调用validator的方法
        # 这里是简化版，实际应调用完整的验证逻辑
        try:
            if self.validator is None:
                raise ValueError("Validator not set")
            freshness = self.validator.check_data_freshness(symbol, interval)
            return {
                "symbol": symbol,
                "interval": interval,
                "has_data": freshness.get("has_data", False),
                "is_up_to_date": freshness.get("is_up_to_date", False),
                "has_errors": False,
                "has_warnings": not freshness.get("is_up_to_date", True),
            }
        except Exception as e:
            self.logger.debug(f"验证失败 {symbol} {interval}: {e}")
            return {
                "symbol": symbol,
                "interval": interval,
                "has_data": False,
                "is_up_to_date": False,
                "has_errors": True,
                "has_warnings": False,
            }

    async def process_task_async(self, task) -> Optional[Dict]:
        """处理单个任务（异步）
        
        通用任务处理接口，根据task_type调用不同方法
        """
        try:
            if task.task_type == "freshness":
                return await self._check_one_freshness_async(task.symbol, task.interval)
            elif task.task_type == "validation":
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    self._validate_symbol_sync,
                    task.symbol,
                    task.interval
                )
            else:
                self.logger.warning(f"未知任务类型: {task.task_type}")
                return None
        except Exception as e:
            self.logger.debug(f"处理任务失败 {task.symbol}: {e}")
            return None

    def set_dependencies(self, storage_manager, validator):
        """设置依赖（避免循环导入）"""
        self.storage_manager = storage_manager
        self.validator = validator


# ==================== Layer 3: 进程池工作器 ====================

def _validate_chunk_worker(args: Tuple) -> List[Dict]:
    """工作进程函数：验证一批品种
    
    此函数在独立进程中运行，可以完全并行计算
    必须在模块级定义以便pickle序列化
    
    Args:
        args: (symbols, intervals, data_dir) 元组
        
    Returns:
        List[Dict]: 验证结果列表
    """
    symbols, intervals, data_dir = args
    results = []
    
    try:
        # 在工作进程中导入（避免主进程导入开销）
        from pathlib import Path
        import pandas as pd
        from datetime import date
        
        # 简化的验证逻辑（避免导入整个DataValidator造成依赖问题）
        for symbol in symbols:
            for interval in intervals:
                try:
                    file_path = Path(data_dir) / symbol / interval / "data.parquet"
                    
                    if not file_path.exists():
                        results.append({
                            "symbol": symbol,
                            "interval": interval,
                            "has_data": False,
                            "has_errors": False,
                            "has_warnings": False,
                            "is_missing": True,
                        })
                        continue
                    
                    # 读取数据
                    df = pd.read_parquet(file_path)
                    
                    if df.empty:
                        results.append({
                            "symbol": symbol,
                            "interval": interval,
                            "has_data": False,
                            "has_errors": True,
                            "has_warnings": False,
                            "is_missing": False,
                        })
                        continue
                    
                    # 基础检查
                    has_errors = False
                    has_warnings = False
                    
                    # 检查必要列
                    required_columns = ["datetime", "open", "high", "low", "close", "volume"]
                    missing_columns = [c for c in required_columns if c not in df.columns]
                    if missing_columns:
                        has_errors = True
                    
                    # 检查空值
                    if not has_errors:
                        null_counts = df[required_columns].isnull().sum()
                        if null_counts.any():
                            has_warnings = True
                    
                    # 检查数据量
                    if len(df) < 10:
                        has_warnings = True
                    
                    results.append({
                        "symbol": symbol,
                        "interval": interval,
                        "has_data": True,
                        "has_errors": has_errors,
                        "has_warnings": has_warnings,
                        "is_missing": False,
                        "row_count": len(df),
                    })
                
                except Exception as e:
                    results.append({
                        "symbol": symbol,
                        "interval": interval,
                        "has_data": False,
                        "has_errors": True,
                        "has_warnings": False,
                        "is_missing": False,
                        "error_message": str(e),
                    })
    
    except Exception as e:
        # 整个批次失败
        logging.error(f"工作进程异常: {e}")
    
    return results


class CPUIntensiveWorker:
    """CPU密集型数据验证工作进程池"""

    def __init__(self, num_processes: Optional[int] = None, data_dir: Optional[str] = None):
        """
        Args:
            num_processes: 进程数，默认为 CPU核心数-2
            data_dir: 数据目录路径
        """
        self.logger = logging.getLogger(__name__)
        
        if num_processes is None:
            num_processes = max(2, mp.cpu_count() - 2)
        
        self.num_processes = num_processes
        self.data_dir = data_dir or "data/kline"
        self.executor: Optional[ProcessPoolExecutor] = None
        
        self.logger.info(f"初始化CPU密集型进程池：{num_processes}个进程")

    def _ensure_executor(self):
        """确保进程池已创建"""
        if self.executor is None:
            self.executor = ProcessPoolExecutor(max_workers=self.num_processes)

    def validate_data_parallel(
        self,
        symbols: List[str],
        intervals: List[str]
    ) -> List[Dict]:
        """多进程并行验证数据质量
        
        每个进程独立运行，绕过GIL，充分利用多核CPU
        
        Args:
            symbols: 品种列表
            intervals: 周期列表
            
        Returns:
            List[Dict]: 验证结果列表
        """
        if not symbols:
            return []
        
        self._ensure_executor()
        
        # 分割任务到各进程
        chunk_size = max(1, len(symbols) // self.num_processes)
        chunks = []
        
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            if chunk:
                chunks.append((chunk, intervals, self.data_dir))
        
        self.logger.info(
            f"开始多进程验证：{len(symbols)}个品种，"
            f"分{len(chunks)}个批次，每批{chunk_size}个品种"
        )
        
        # 提交到进程池
        futures = []
        for chunk_args in chunks:
            if self.executor is None:
                self.logger.error("进程池未初始化")
                return []
            future = self.executor.submit(_validate_chunk_worker, chunk_args)
            futures.append(future)
        
        # 收集结果
        all_results = []
        completed = 0
        
        for future in as_completed(futures):
            try:
                chunk_results = future.result(timeout=300)  # 5分钟超时
                all_results.extend(chunk_results)
                completed += 1
                
                if completed % 2 == 0 or completed == len(futures):
                    self.logger.info(f"进程池验证进度: {completed}/{len(futures)}")
            
            except Exception as e:
                self.logger.error(f"进程任务失败: {e}", exc_info=True)
        
        self.logger.info(f"多进程验证完成：共{len(all_results)}个结果")
        return all_results

    def shutdown(self, wait: bool = True):
        """关闭进程池"""
        if self.executor:
            self.executor.shutdown(wait=wait)
            self.executor = None
            self.logger.info("进程池已关闭")

    def __del__(self):
        """析构时关闭进程池"""
        self.shutdown(wait=False)


# ==================== Layer 4: 动态并发调节 ====================

class ConcurrencyTuner:
    """动态并发调节器"""

    def __init__(self, resource_monitor: ResourceMonitor):
        self.logger = logging.getLogger(__name__)
        self.monitor = resource_monitor
        self.current_config: Dict = {}
        self.history = []

    def adjust_concurrency(self, current_load: Dict) -> Dict:
        """动态调整并发配置
        
        策略：
        - CPU使用率 < 50%: 提高并发度
        - CPU使用率 > 80%: 降低并发度
        - 内存不足: 降低协程数量
        - 磁盘I/O繁忙: 降低I/O并发
        
        Args:
            current_load: 当前负载状态
            
        Returns:
            Dict: 调整后的并发配置
        """
        cpu = current_load.get("cpu_percent", 50)
        memory_avail = current_load.get("memory_available_gb", 4)
        disk_busy = current_load.get("disk_io_busy", False)

        # 基础配置
        config = {
            "async_workers": 1000,
            "thread_workers": 20,
            "process_workers": 8
        }

        # 根据CPU负载调整
        if cpu > 80:
            # CPU繁忙，大幅降低并发
            config["process_workers"] = max(2, config["process_workers"] // 2)
            config["thread_workers"] = max(5, config["thread_workers"] // 2)
            config["async_workers"] = min(500, config["async_workers"])
            self.logger.info(f"CPU繁忙({cpu:.1f}%)，降低并发度")

        elif cpu < 30:
            # CPU空闲，提高并发
            config["process_workers"] = min(16, config["process_workers"] * 2)
            config["thread_workers"] = min(50, config["thread_workers"] * 2)
            config["async_workers"] = 2000
            self.logger.info(f"CPU空闲({cpu:.1f}%)，提高并发度")

        # 根据内存调整
        if memory_avail < 2:
            # 内存紧张，降低协程数和线程数
            config["async_workers"] = 200  # 降低协程数
            config["thread_workers"] = 10
            config["process_workers"] = max(2, config["process_workers"] // 2)
            self.logger.warning(f"内存不足({memory_avail:.2f}GB)，降低并发度")

        elif memory_avail > 8:
            # 内存充足，可以提高并发
            config["async_workers"] = min(3000, int(config["async_workers"] * 1.5))

        # 根据磁盘I/O调整
        if disk_busy:
            # 磁盘繁忙，降低I/O并发
            config["async_workers"] = min(config["async_workers"], 500)
            config["thread_workers"] = min(config["thread_workers"], 10)
            self.logger.info("磁盘I/O繁忙，降低I/O并发度")

        # 记录配置历史
        self.current_config = config
        self.history.append({
            "config": config.copy(),
            "load": current_load.copy()
        })

        # 只保留最近10次记录
        if len(self.history) > 10:
            self.history.pop(0)

        return config

    def get_current_config(self) -> Dict:
        """获取当前配置"""
        return self.current_config.copy()

    def get_recommended_config(self) -> Dict:
        """获取推荐配置（基于实时资源监控）"""
        current_status = self.monitor.get_current_status()
        return self.adjust_concurrency(current_status)


# ==================== 性能追踪 ====================

class PhaseTimer:
    """阶段计时器（上下文管理器）"""

    def __init__(self, phase_name: str, tracker: 'PerformanceTracker'):
        self.phase_name = phase_name
        self.tracker = tracker
        self.start_time = 0
        self.end_time = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        self.tracker.record_phase_timing(self.phase_name, elapsed)


class PerformanceTracker:
    """性能追踪器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.phase_timings: Dict[str, float] = {}
        self.resource_snapshots: List[Dict] = []
        
        # 并发统计
        self.max_async_workers = 0
        self.max_thread_workers = 0
        self.max_process_workers = 0
        
        # 资源占用
        self.peak_memory_mb = 0.0
        self.avg_cpu_percent = 0.0
        
        # 开始时间
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    def start_tracking(self):
        """开始追踪"""
        self.start_time = datetime.now()
        self.phase_timings.clear()
        self.resource_snapshots.clear()

    def end_tracking(self):
        """结束追踪"""
        self.end_time = datetime.now()

    @contextmanager
    def track_phase(self, phase_name: str):
        """追踪单个阶段耗时
        
        用法:
            with tracker.track_phase("phase_1"):
                # 执行阶段1的代码
                pass
        """
        timer = PhaseTimer(phase_name, self)
        with timer:
            yield timer

    def record_phase_timing(self, phase_name: str, elapsed: float):
        """记录阶段耗时"""
        self.phase_timings[phase_name] = elapsed
        self.logger.info(f"⏱️  {phase_name}: {elapsed:.3f}秒")

    def record_resource_snapshot(self, snapshot: Dict):
        """记录资源快照"""
        self.resource_snapshots.append(snapshot)
        
        # 更新峰值统计
        if "memory_mb" in snapshot:
            self.peak_memory_mb = max(self.peak_memory_mb, snapshot["memory_mb"])

    def record_concurrency(self, async_workers: int = 0, thread_workers: int = 0, process_workers: int = 0):
        """记录并发数"""
        self.max_async_workers = max(self.max_async_workers, async_workers)
        self.max_thread_workers = max(self.max_thread_workers, thread_workers)
        self.max_process_workers = max(self.max_process_workers, process_workers)

    def calculate_avg_cpu(self):
        """计算平均CPU使用率"""
        if self.resource_snapshots:
            cpu_values = [s.get("cpu_percent", 0) for s in self.resource_snapshots]
            self.avg_cpu_percent = sum(cpu_values) / len(cpu_values)

    def generate_report(self) -> str:
        """生成性能报告"""
        self.calculate_avg_cpu()
        
        total_time = sum(self.phase_timings.values())
        
        report = [
            "\n========== 性能报告 ==========",
            f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}",
            f"结束时间: {self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'N/A'}",
            "",
            "【阶段耗时】"
        ]
        
        for phase, timing in sorted(self.phase_timings.items()):
            percentage = (timing / total_time * 100) if total_time > 0 else 0
            report.append(f"  {phase}: {timing:.3f}秒 ({percentage:.1f}%)")
        
        report.extend([
            f"  总耗时: {total_time:.3f}秒",
            "",
            "【并发统计】",
            f"  协程峰值: {self.max_async_workers}",
            f"  线程峰值: {self.max_thread_workers}",
            f"  进程峰值: {self.max_process_workers}",
            "",
            "【资源占用】",
            f"  峰值内存: {self.peak_memory_mb:.2f}MB",
            f"  平均CPU: {self.avg_cpu_percent:.1f}%",
            "=============================="
        ])
        
        return "\n".join(report)

    def log_report(self):
        """输出性能报告到日志"""
        report = self.generate_report()
        self.logger.info(report)
        print(report)

