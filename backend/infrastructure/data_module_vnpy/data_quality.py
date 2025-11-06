"""
数据质量管理模块 - 架构v3.6重构版

本模块负责数据质量管理，包括：
- 数据质量感知（DataSensor）
- 数据验证器（StatelessValidator）
- 文件监控（DataFileWatcher）
- 健康检查（HealthChecker）
- IPO日期缓存（IPODateCache）

架构特性：
- native_iocp集成：质量扫描时文件异步读取，性能提升50-80%
- native_ipc集成：多进程验证结果汇总，文件监控事件跨进程推送
- 混合异步扫描：协程+线程+进程，最大2000并发
- 增量推送：500ms最小间隔
- 性能优化：集成 native C 扩展，优化关键性能路径
- 100% API向后兼容

v3.6 更新：
- 工具函数迁移：configure_subprocess_logging 已迁移到 tdx_asyncio.utils.helper
- 性能优化：集成 native_compute，优化数值计算部分
- 引用链更新：所有引用已更新，从 tdx_asyncio 导入

重构日期：2025年
作者：AI Assistant (基于v2.1重构)
"""

import asyncio
import json
import logging
import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd

# 导入native_iocp（支持降级）
try:
    from backend.infrastructure.native.native_iocp.compat import aopen as compat_aopen

    IOCP_AVAILABLE = True
except ImportError:
    try:
        import aiofiles

        async def compat_aopen(file, mode="r", **kwargs):
            return aiofiles.open(file, mode, **kwargs)

        IOCP_AVAILABLE = False
    except ImportError:
        compat_aopen = None
        IOCP_AVAILABLE = False

# 导入native_iocp批量目录遍历（支持降级）
try:
    from backend.infrastructure.native.native_iocp import fast_dir_walk, BATCH_AVAILABLE

    NATIVE_IOCP_AVAILABLE = BATCH_AVAILABLE
except ImportError:
    fast_dir_walk = None  # type: ignore
    NATIVE_IOCP_AVAILABLE = False

# 导入native_ipc（支持降级）
try:
    from backend.infrastructure.native.native_ipc import AsyncIPCPipe

    IPC_AVAILABLE = True
except ImportError:
    IPC_AVAILABLE = False
    AsyncIPCPipe = None

# 导入native_collections（支持降级）
try:
    from backend.infrastructure.native.native_collections import (
        HighPerfLRUCache,
        COLLECTIONS_AVAILABLE,
    )

    NATIVE_COLLECTIONS_AVAILABLE = COLLECTIONS_AVAILABLE
except ImportError:
    HighPerfLRUCache = None
    NATIVE_COLLECTIONS_AVAILABLE = False

# 导入native_compute（支持降级）
try:
    from backend.infrastructure.native.native_compute import (
        batch_compute,
        COMPUTE_AVAILABLE,
    )

    NATIVE_COMPUTE_AVAILABLE = COMPUTE_AVAILABLE
except ImportError:
    batch_compute = None
    NATIVE_COMPUTE_AVAILABLE = False

# 导入核心模块
from .core_engine import (
    ConfigManager,
    DailyCacheManager,
    NetworkTimeSync,
)

# 导入存储管理
from .data_storage import StorageManager

# ==================== 日志配置 ====================
logger = logging.getLogger("backend.data_module.quality")
logger_alert = logging.getLogger("backend.data_module.alert")


# ==============================================================================
# 全局配置和常量
# ==============================================================================


# 数据质量级别
class DataQualityLevel(Enum):
    """数据质量级别枚举"""

    UNKNOWN = 0  # 未知
    EXCELLENT = 1  # 优秀（>99%完整性）
    GOOD = 2  # 良好（95-99%完整性）
    FAIR = 3  # 一般（90-95%完整性）
    POOR = 4  # 差（80-90%完整性）
    CRITICAL = 5  # 严重（<80%完整性）


# 验证状态
class ValidationStatus(Enum):
    """验证状态枚举"""

    PENDING = auto()  # 待验证
    RUNNING = auto()  # 验证中
    PASSED = auto()  # 通过
    FAILED = auto()  # 失败
    SKIPPED = auto()  # 跳过


# ==============================================================================
# Part 1: 数据质量感知（DataSensor）
# ==============================================================================


@dataclass
class QualityScanResult:
    """质量扫描结果"""

    symbol: str
    interval: str
    total_bars: int = 0
    missing_bars: int = 0
    duplicate_bars: int = 0
    invalid_bars: int = 0
    completeness: float = 0.0  # 完整性百分比
    quality_level: DataQualityLevel = DataQualityLevel.UNKNOWN
    last_update: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)
    scan_time: datetime = field(default_factory=datetime.now)


class DataSensor:
    """数据质量感知器

    负责全方位数据质量监控，支持：
    - 混合异步扫描（协程+线程+进程）
    - 最大2000并发
    - 增量推送：500ms最小间隔
    - native_iocp集成：质量扫描时文件异步读取
    - native_ipc集成：多进程验证结果汇总
    """

    def __init__(self, event_engine=None, config_manager: Optional[ConfigManager] = None):
        """初始化数据感知器

        Args:
            event_engine: VnPy EventEngine（用于事件通知）
            config_manager: 配置管理器
        """
        self.event_engine = event_engine
        self.config_manager = config_manager or ConfigManager()
        self.storage_manager = StorageManager()

        # 扫描状态
        self._scanning = False
        self._scan_lock = threading.Lock()

        # 扫描结果缓存
        self._scan_results: Dict[Tuple[str, str], QualityScanResult] = {}
        self._results_lock = threading.Lock()

        # 进度回调
        self._progress_callbacks = []

        # 增量推送控制
        self._last_push_time = 0
        self._push_interval = 0.5  # 500ms最小间隔

        # 统计信息
        self._stats = {
            "total_scanned": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_warnings": 0,
            "last_scan_time": None,
        }

    def register_progress_callback(self, callback: Callable):
        """注册进度回调函数

        Args:
            callback: 回调函数，签名为 callback(completed, total, message)
        """
        self._progress_callbacks.append(callback)

    def _notify_progress(self, completed: int, total: int, message: str = ""):
        """通知进度更新（带增量推送控制）

        Args:
            completed: 已完成数量
            total: 总数量
            message: 进度消息
        """
        # 增量推送控制
        current_time = time.time()
        if current_time - self._last_push_time < self._push_interval:
            # 未达到推送间隔，跳过
            return

        self._last_push_time = current_time

        # 执行回调
        for callback in self._progress_callbacks:
            try:
                callback(completed, total, message)
            except Exception as e:
                logger.warning(
                    f"⚠️ 进度回调执行失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

    def scan_quality(
        self,
        symbols: List[str],
        intervals: List[str] = None,
        use_async: bool = True,
        max_workers: int = None,  # v3.1：改为可选，由LoadBalancer决定
        max_concurrent: int = None,  # v3.1：改为可选，由LoadBalancer决定
    ) -> Dict[Tuple[str, str], QualityScanResult]:
        """扫描数据质量（主入口）

        Args:
            symbols: 品种代码列表
            intervals: 周期列表，默认 ["1d", "5m", "1m"]
            use_async: 是否使用异步扫描
            max_workers: 最大进程数（v3.1：由LoadBalancer决定）
            max_concurrent: 最大并发数（v3.1：由LoadBalancer决定）

        Returns:
            扫描结果字典 {(symbol, interval): QualityScanResult}
        """
        import time
        from contextlib import suppress

        start_time = time.time()

        # 设置日志上下文
        try:
            from backend.infrastructure.system_vnpy.logging_system import (
                get_logging_hub,
                ai_log_process,
            )

            hub = get_logging_hub()
        except ImportError:
            hub = None

        stage_logger = logging.getLogger("task.manual_data_scan.stage")

        # 使用ai_log_process创建独立日志文件
        # 注意：场景信息通过日志记录的extra参数传递，无需全局设置
        try:
            context_manager = ai_log_process("manual_data_scan") if hub else suppress()
        except Exception:
            context_manager = suppress()

        with context_manager:
            with self._scan_lock:
                if self._scanning:
                    logger.warning(
                        "[DATA-SENSOR] ⚠️ 质量扫描正在进行中",
                        extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                    )
                    logger.debug(
                        "[DATA-SENSOR] 扫描状态: _scanning=True",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    return self._scan_results.copy()

                self._scanning = True

            try:
                # 阶段节点（输出到Terminal）
                stage_logger.info(
                    f"📍 手动数据扫描开始: 品种数={len(symbols)}, 周期={intervals or ['1d', '5m', '1m']}",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                )

                intervals = intervals or ["1d", "5m", "1m"]
                total_tasks = len(symbols) * len(intervals)

                logger.debug(
                    f"[DATA-SENSOR] 开始数据质量扫描: symbols={len(symbols)}, intervals={intervals}, "
                    f"total_tasks={total_tasks}, use_async={use_async}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.info(
                    f"[DATA-SENSOR] ℹ️ 开始数据质量扫描: 品种数={len(symbols)}, 周期={intervals}, "
                    f"总任务数={total_tasks}, 异步模式={use_async}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                # v3.1：使用LoadBalancer获取最优配置
                if max_workers is None or max_concurrent is None:
                    logger.debug(
                        "[DATA-SENSOR] 开始获取LoadBalancer最优配置...",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    logger.info(
                        "[DATA-SENSOR] ℹ️ 开始获取LoadBalancer最优配置...",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    lb_config_start_time = time.time()
                    optimal_config = self._get_optimal_config_from_lb(total_tasks=total_tasks)
                    lb_config_elapsed = time.time() - lb_config_start_time
                    max_workers = max_workers or optimal_config.get("processes", 4)
                    max_concurrent = max_concurrent or optimal_config.get(
                        "coroutines_per_process", 100
                    )
                    logger.debug(
                        f"[DATA-SENSOR] LoadBalancer配置获取完成: processes={max_workers}, "
                        f"coroutines_per_process={max_concurrent}, 耗时={lb_config_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    logger.info(
                        f"[DATA-SENSOR] ✅ LoadBalancer配置获取完成: processes={max_workers}, "
                        f"coroutines_per_process={max_concurrent}, 耗时={lb_config_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                else:
                    logger.debug(
                        f"[DATA-SENSOR] 使用手动配置: processes={max_workers}, coroutines_per_process={max_concurrent}",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    logger.info(
                        f"[DATA-SENSOR] ℹ️ 使用手动配置: processes={max_workers}, coroutines_per_process={max_concurrent}",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )

                logger.info(
                    f"[DATA-SENSOR] 🔍 开始数据质量扫描: 品种数={len(symbols)}, 周期={intervals}, "
                    f"异步模式={use_async}, 进程数={max_workers}, 最大并发={max_concurrent}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                scan_start_time = time.time()
                if use_async:
                    # 异步扫描
                    logger.debug(
                        "[DATA-SENSOR] 使用异步扫描模式",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    logger.info(
                        "[DATA-SENSOR] ℹ️ 使用异步扫描模式",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    results = self._scan_async(symbols, intervals, max_concurrent)
                else:
                    # 多进程扫描
                    logger.debug(
                        "[DATA-SENSOR] 使用多进程扫描模式",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    logger.info(
                        "[DATA-SENSOR] ℹ️ 使用多进程扫描模式",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )
                    results = self._scan_multiprocess(symbols, intervals, max_workers)
                scan_elapsed = time.time() - scan_start_time
                logger.debug(
                    f"[DATA-SENSOR] 扫描完成: 结果数={len(results)}, 耗时={scan_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.info(
                    f"[DATA-SENSOR] ✅ 扫描完成: 结果数={len(results)}, 耗时={scan_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                # 更新缓存
                logger.debug(
                    "[DATA-SENSOR] 开始更新扫描结果缓存...",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                cache_update_start_time = time.time()
                with self._results_lock:
                    self._scan_results.update(results)
                cache_update_elapsed = time.time() - cache_update_start_time
                logger.debug(
                    f"[DATA-SENSOR] 扫描结果缓存更新完成: 耗时={cache_update_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                # 更新统计
                logger.debug(
                    "[DATA-SENSOR] 开始更新统计信息...",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                stats_update_start_time = time.time()
                self._update_stats(results)
                stats_update_elapsed = time.time() - stats_update_start_time
                logger.debug(
                    f"[DATA-SENSOR] 统计信息更新完成: 耗时={stats_update_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                total_elapsed = time.time() - start_time
                logger.info(
                    f"[DATA-SENSOR] ✅ 数据质量扫描完成: 扫描{len(results)}个任务, "
                    f"扫描耗时={scan_elapsed:.2f}s, 总耗时={total_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.debug(
                    f"[DATA-SENSOR] 扫描完成详情: results_count={len(results)}, scan_elapsed={scan_elapsed:.2f}s, "
                    f"cache_update_elapsed={cache_update_elapsed:.2f}s, stats_update_elapsed={stats_update_elapsed:.2f}s, "
                    f"total_elapsed={total_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                # 阶段节点（输出到Terminal）
                passed_count = sum(
                    1
                    for r in results.values()
                    if r.quality_level in [DataQualityLevel.EXCELLENT, DataQualityLevel.GOOD]
                )
                failed_count = sum(
                    1 for r in results.values() if r.quality_level == DataQualityLevel.POOR
                )
                critical_count = sum(
                    1 for r in results.values() if r.quality_level == DataQualityLevel.CRITICAL
                )
                avg_completeness = (
                    sum(r.completeness for r in results.values()) / len(results) if results else 0.0
                )

                logger.debug(
                    f"[DATA-SENSOR] 扫描结果统计: 总计={len(results)}, 通过={passed_count}, "
                    f"失败={failed_count}, 严重={critical_count}, 平均完整性={avg_completeness:.2f}%",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.info(
                    f"[DATA-SENSOR] ✅ 扫描结果统计: 总计={len(results)}, 通过={passed_count}, "
                    f"失败={failed_count}, 严重={critical_count}, 平均完整性={avg_completeness:.2f}%",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                if failed_count > 0 or critical_count > 0:
                    logger.warning(
                        f"[DATA-SENSOR] ⚠️ 扫描发现质量问题: 失败={failed_count}, 严重={critical_count}",
                        extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                    )

                stage_logger.info(
                    f"✅ 手动数据扫描完成: 耗时={total_elapsed:.2f}s, 任务数={len(results)}, "
                    f"通过={passed_count}, 失败={failed_count}, 严重={critical_count}, "
                    f"平均完整性={avg_completeness:.2f}%",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                )

                return results

            except Exception as e:
                total_elapsed = time.time() - start_time
                logger.debug(
                    f"[DATA-SENSOR] 数据质量扫描异常详情: {type(e).__name__}: {str(e)}, 耗时={total_elapsed:.2f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.error(
                    f"[DATA-SENSOR] ❌ 数据质量扫描失败: {e}, 耗时={total_elapsed:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                )
                logger.critical(
                    f"[DATA-SENSOR] 🔥 数据质量扫描严重失败，可能影响数据质量评估: {e}, 耗时={total_elapsed:.2f}s",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                )

                # 阶段节点（输出到Terminal）
                stage_logger.error(
                    f"❌ 手动数据扫描失败: {e}, 耗时={total_elapsed:.2f}s",
                    extra={"log_type": "STAGE_NODE", "scenario": "manual_data_scan"},
                )

                raise
            finally:
                with self._scan_lock:
                    self._scanning = False
                    logger.debug(
                        "[DATA-SENSOR] 扫描状态已重置: _scanning=False",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )

    def _get_optimal_config_from_lb(self, total_tasks: int) -> Dict[str, Any]:
        """从 LoadBalancer 获取最优配置（v3.1新增）

        Args:
            total_tasks: 总任务数

        Returns:
            最优配置
        """
        try:
            from .load_balancer import LoadBalancer, TaskConfig, TaskCategory

            # 创建任务配置
            task = TaskConfig(
                name="quality_scan",
                category=TaskCategory.LOCAL_SCAN,
                total_count=total_tasks,
                is_io_intensive=True,
                is_cpu_intensive=False,
                estimated_memory_mb=500.0,
                estimated_duration_sec=total_tasks * 0.1,
            )

            # 获取LoadBalancer最优配置
            lb = LoadBalancer()
            config = lb.get_optimal_config(task=task, queue_metrics=None)

            logger.debug(
                f"📊 LoadBalancer配置: 进程={config.get('processes')}, "
                f"协程={config.get('coroutines_per_process')}, "
                f"瓶颈={config.get('resource_bottleneck')}, "
                f"压力评分={config.get('pressure_score', 0)}/100",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )

            return config
        except Exception as e:
            logger.warning(
                f"⚠️ 获取LoadBalancer配置失败，使用默认值: {e}", extra={"log_type": "SYSTEM"}
            )
            return {"processes": 4, "coroutines_per_process": 100}

    def _scan_async(
        self,
        symbols: List[str],
        intervals: List[str],
        max_concurrent: int,
    ) -> Dict[Tuple[str, str], QualityScanResult]:
        """异步扫描（协程版本）

        Args:
            symbols: 品种代码列表
            intervals: 周期列表
            max_concurrent: 最大并发数

        Returns:
            扫描结果字典
        """
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            results = loop.run_until_complete(
                self._scan_async_coroutine(symbols, intervals, max_concurrent)
            )
            return results
        finally:
            loop.close()

    async def _scan_async_coroutine(
        self,
        symbols: List[str],
        intervals: List[str],
        max_concurrent: int,
    ) -> Dict[Tuple[str, str], QualityScanResult]:
        """异步扫描协程

        Args:
            symbols: 品种代码列表
            intervals: 周期列表
            max_concurrent: 最大并发数

        Returns:
            扫描结果字典
        """
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        # 创建任务列表
        tasks = []
        for symbol in symbols:
            for interval in intervals:
                task = self._scan_single_async(symbol, interval, semaphore)
                tasks.append((symbol, interval, task))

        total = len(tasks)
        completed = 0

        # 并发执行
        scan_start_time = time.time()
        last_progress_log_time = time.time()

        for symbol, interval, task in tasks:
            try:
                task_start_time = time.time()
                result = await task
                task_elapsed = time.time() - task_start_time

                results[(symbol, interval)] = result

                # DEBUG日志（记录每个任务的扫描结果）
                logger.debug(
                    f"[SCAN-ASYNC] 扫描完成: symbol={symbol}, interval={interval}, "
                    f"total_bars={result.total_bars}, completeness={result.completeness:.2f}%, "
                    f"quality_level={result.quality_level.name}, elapsed={task_elapsed:.3f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                # 每100个任务记录一次进度
                if completed % 100 == 0:
                    elapsed = time.time() - scan_start_time
                    speed = completed / elapsed if elapsed > 0 else 0
                    remaining = total - completed
                    estimated_remaining = remaining / speed if speed > 0 else 0
                    logger.debug(
                        f"[SCAN-ASYNC] 进度更新: 已完成 {completed}/{total} ({completed*100//total}%), "
                        f"速度={speed:.2f}任务/秒, 预计剩余={estimated_remaining:.0f}秒",
                        extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                    )

            except Exception as e:
                logger.debug(
                    f"[SCAN-ASYNC] 扫描异常: symbol={symbol}, interval={interval}, "
                    f"异常类型={type(e).__name__}, 异常详情={str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.warning(
                    f"⚠️ 扫描失败: {symbol}/{interval}, 错误: {e}",
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                )
                results[(symbol, interval)] = QualityScanResult(
                    symbol=symbol,
                    interval=interval,
                    errors=[str(e)],
                )

            completed += 1
            self._notify_progress(completed, total, f"已扫描: {symbol}/{interval}")

            # 每10秒记录一次汇总进度
            current_time = time.time()
            if current_time - last_progress_log_time >= 10:
                elapsed = time.time() - scan_start_time
                speed = completed / elapsed if elapsed > 0 else 0
                remaining = total - completed
                estimated_remaining = remaining / speed if speed > 0 else 0
                logger.info(
                    f"[SCAN-ASYNC] 扫描进度: {completed}/{total} ({completed*100//total}%), "
                    f"速度={speed:.2f}任务/秒, 预计剩余={estimated_remaining:.0f}秒",
                    extra={"log_type": "PROGRESS", "scenario": "manual_data_scan"},
                )
                last_progress_log_time = current_time

        scan_elapsed = time.time() - scan_start_time
        logger.debug(
            f"[SCAN-ASYNC] 异步扫描完成: 总任务数={total}, 完成={len(results)}, 耗时={scan_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )

        return results

    async def _scan_single_async(
        self,
        symbol: str,
        interval: str,
        semaphore: asyncio.Semaphore,
    ) -> QualityScanResult:
        """异步扫描单个品种（使用native_iocp）

        Args:
            symbol: 品种代码
            interval: 周期
            semaphore: 信号量（控制并发）

        Returns:
            扫描结果
        """
        async with semaphore:
            try:
                logger.debug(
                    f"[SCAN-SINGLE] 开始扫描单个品种: symbol={symbol}, interval={interval}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                load_start_time = time.time()

                # 异步读取数据
                df = await self.storage_manager.load_data_async(symbol, interval)
                load_elapsed = time.time() - load_start_time

                logger.debug(
                    f"[SCAN-SINGLE] 数据加载完成: symbol={symbol}, interval={interval}, "
                    f"rows={len(df) if df is not None and not df.empty else 0}, 耗时={load_elapsed:.3f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                # 验证数据质量
                validate_start_time = time.time()
                result = self._validate_dataframe(
                    symbol, interval, df if df is not None else pd.DataFrame()
                )
                validate_elapsed = time.time() - validate_start_time

                logger.debug(
                    f"[SCAN-SINGLE] 质量验证完成: symbol={symbol}, interval={interval}, "
                    f"completeness={result.completeness:.2f}%, quality_level={result.quality_level.name}, "
                    f"耗时={validate_elapsed:.3f}s",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )

                return result

            except Exception as e:
                logger.debug(
                    f"[SCAN-SINGLE] 扫描单个品种异常: symbol={symbol}, interval={interval}, "
                    f"异常类型={type(e).__name__}, 异常详情={str(e)}",
                    extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
                )
                logger.warning(
                    f"[SCAN-SINGLE] ⚠️ 扫描单个品种失败: symbol={symbol}, interval={interval}, 错误={e}",
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                )
                logger.error(
                    f"[SCAN-SINGLE] ❌ 扫描单个品种失败: {symbol}/{interval}, {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "manual_data_scan"},
                )
                return QualityScanResult(
                    symbol=symbol,
                    interval=interval,
                    errors=[str(e)],
                )

    def _scan_multiprocess(
        self,
        symbols: List[str],
        intervals: List[str],
        max_workers: int,
    ) -> Dict[Tuple[str, str], QualityScanResult]:
        """多进程扫描

        Args:
            symbols: 品种代码列表
            intervals: 周期列表
            max_workers: 最大进程数

        Returns:
            扫描结果字典
        """
        results = {}

        # 创建任务列表
        tasks = [(symbol, interval) for symbol in symbols for interval in intervals]
        total = len(tasks)

        scenario = "manual_data_scan"
        import time

        scan_start_time = time.time()

        logger.debug(
            f"[SCAN-MULTIPROCESS] 开始多进程扫描: 任务数={total}, 进程数={max_workers}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SCAN-MULTIPROCESS] ℹ️ 开始多进程扫描: 任务数={total}, 进程数={max_workers}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 使用进程池
        try:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_scan_single_worker, symbol, interval): (symbol, interval)
                    for symbol, interval in tasks
                }

                logger.debug(
                    f"[SCAN-MULTIPROCESS] 所有任务已提交: 任务数={len(futures)}, 进程数={max_workers}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.info(
                    f"[SCAN-MULTIPROCESS] ✅ 所有任务已提交到进程池: 任务数={len(futures)}, 进程数={max_workers}",
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

                completed = 0
                for future in as_completed(futures):
                    symbol, interval = futures[future]
                    try:
                        result = future.result()
                        results[(symbol, interval)] = result
                        logger.debug(
                            f"[SCAN-MULTIPROCESS] 任务完成: symbol={symbol}, interval={interval}, "
                            f"quality_level={result.quality_level.name}, completeness={result.completeness:.2f}%",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                    except Exception as e:
                        logger.debug(
                            f"[SCAN-MULTIPROCESS] 扫描异常详情: symbol={symbol}, interval={interval}, "
                            f"异常类型={type(e).__name__}, 异常消息={str(e)}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        logger.warning(
                            f"[SCAN-MULTIPROCESS] ⚠️ 扫描失败: {symbol}/{interval}, 错误: {e}",
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )
                        logger.error(
                            f"[SCAN-MULTIPROCESS] ❌ 扫描任务失败: {symbol}/{interval}, 错误: {e}",
                            exc_info=True,
                            extra={"log_type": "ALERT", "scenario": scenario},
                        )
                        results[(symbol, interval)] = QualityScanResult(
                            symbol=symbol,
                            interval=interval,
                            errors=[str(e)],
                        )

                    completed += 1
                    self._notify_progress(completed, total, f"已扫描: {symbol}/{interval}")

                    # 每100个任务记录一次进度
                    if completed % 100 == 0:
                        elapsed = time.time() - scan_start_time
                        speed = completed / elapsed if elapsed > 0 else 0
                        remaining = total - completed
                        estimated_remaining = remaining / speed if speed > 0 else 0
                        logger.debug(
                            f"[SCAN-MULTIPROCESS] 扫描进度详情: {completed}/{total} ({completed/total*100:.1f}%), "
                            f"速度={speed:.2f}任务/秒, 预计剩余={estimated_remaining:.0f}秒",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        logger.info(
                            f"[SCAN-MULTIPROCESS] 扫描进度: {completed}/{total} ({completed/total*100:.1f}%), "
                            f"速度={speed:.2f}任务/秒, 预计剩余={estimated_remaining:.0f}秒",
                            extra={"log_type": "PROGRESS", "scenario": scenario},
                        )

        except Exception as e:
            scan_elapsed = time.time() - scan_start_time
            logger.debug(
                f"[SCAN-MULTIPROCESS] 多进程扫描异常详情: 异常类型={type(e).__name__}, 异常消息={str(e)}, 耗时={scan_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                f"[SCAN-MULTIPROCESS] ❌ 多进程扫描失败: {e}, 耗时={scan_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.critical(
                f"[SCAN-MULTIPROCESS] 🔥 多进程扫描严重失败，可能影响数据质量评估: {e}, 耗时={scan_elapsed:.2f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            raise

        scan_elapsed = time.time() - scan_start_time
        logger.debug(
            f"[SCAN-MULTIPROCESS] 多进程扫描完成: 总任务数={total}, 完成数={len(results)}, 耗时={scan_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        logger.info(
            f"[SCAN-MULTIPROCESS] ✅ 多进程扫描完成: 总任务数={total}, 完成数={len(results)}, 耗时={scan_elapsed:.2f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        return results

    def _validate_dataframe(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
    ) -> QualityScanResult:
        """验证DataFrame数据质量

        Args:
            symbol: 品种代码
            interval: 周期
            df: 数据DataFrame

        Returns:
            扫描结果
        """
        result = QualityScanResult(symbol=symbol, interval=interval)

        logger.debug(
            f"[VALIDATE] 开始验证数据质量: symbol={symbol}, interval={interval}, "
            f"df_empty={df is None or df.empty}",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )

        if df is None or df.empty:
            result.errors.append("数据为空")
            result.quality_level = DataQualityLevel.CRITICAL
            logger.debug(
                f"[VALIDATE] 数据为空: symbol={symbol}, interval={interval}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )
            return result

        # 统计信息
        result.total_bars = len(df)
        logger.debug(
            f"[VALIDATE] 数据统计: symbol={symbol}, interval={interval}, total_bars={result.total_bars}",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )

        # 检查重复数据
        if df.index.duplicated().any():
            result.duplicate_bars = df.index.duplicated().sum()
            result.errors.append(f"发现重复数据: {result.duplicate_bars}条")
            logger.debug(
                f"[VALIDATE] 发现重复数据: symbol={symbol}, interval={interval}, duplicate_bars={result.duplicate_bars}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )

        # 检查无效数据
        invalid_mask = df["open"].isna() | df["high"].isna() | df["low"].isna() | df["close"].isna()
        result.invalid_bars = invalid_mask.sum()
        if result.invalid_bars > 0:
            result.errors.append(f"发现无效数据: {result.invalid_bars}条")
            logger.debug(
                f"[VALIDATE] 发现无效数据: symbol={symbol}, interval={interval}, invalid_bars={result.invalid_bars}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )

        # 计算完整性
        # 注意：单个数值计算使用 Python 已经足够快，native_compute 主要用于批量操作
        # 这里保持原样，因为除法运算 native_compute 不支持，且单个计算使用 C 扩展可能反而增加开销
        expected_bars = self._calculate_expected_bars(symbol, interval, df)
        logger.debug(
            f"[VALIDATE] 预期数据条数: symbol={symbol}, interval={interval}, expected_bars={expected_bars}",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )
        if expected_bars > 0:
            result.completeness = (result.total_bars / expected_bars) * 100.0
        else:
            result.completeness = 100.0

        # 计算缺失数据
        result.missing_bars = max(0, expected_bars - result.total_bars)
        if result.missing_bars > 0:
            logger.debug(
                f"[VALIDATE] 发现缺失数据: symbol={symbol}, interval={interval}, missing_bars={result.missing_bars}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )

        # 最后更新时间
        if not df.empty:
            result.last_update = df.index[-1].to_pydatetime()
            logger.debug(
                f"[VALIDATE] 最后更新时间: symbol={symbol}, interval={interval}, last_update={result.last_update}",
                extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
            )

        # 确定质量级别
        result.quality_level = self._determine_quality_level(result.completeness)
        logger.debug(
            f"[VALIDATE] 质量评估完成: symbol={symbol}, interval={interval}, "
            f"completeness={result.completeness:.2f}%, quality_level={result.quality_level.name}, "
            f"errors={len(result.errors)}",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )

        return result

    def _calculate_expected_bars(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
    ) -> int:
        """计算预期数据条数

        Args:
            symbol: 品种代码
            interval: 周期
            df: 数据DataFrame

        Returns:
            预期条数
        """
        if df.empty:
            return 0

        # 简化实现：基于时间范围估算
        start_date = df.index[0]
        end_date = df.index[-1]

        if interval == "1d":
            # 日线：按交易日估算（约250天/年）
            days = (end_date - start_date).days
            return int(days * 250 / 365)
        elif interval == "5m":
            # 5分钟：每天48根（4小时交易）
            days = (end_date - start_date).days
            return days * 48
        elif interval == "1m":
            # 1分钟：每天240根（4小时交易）
            days = (end_date - start_date).days
            return days * 240
        else:
            return len(df)

    def _determine_quality_level(self, completeness: float) -> DataQualityLevel:
        """确定质量级别

        Args:
            completeness: 完整性百分比

        Returns:
            质量级别
        """
        if completeness >= 99.0:
            return DataQualityLevel.EXCELLENT
        elif completeness >= 95.0:
            return DataQualityLevel.GOOD
        elif completeness >= 90.0:
            return DataQualityLevel.FAIR
        elif completeness >= 80.0:
            return DataQualityLevel.POOR
        else:
            return DataQualityLevel.CRITICAL

    def _update_stats(self, results: Dict[Tuple[str, str], QualityScanResult]):
        """更新统计信息

        Args:
            results: 扫描结果字典
        """
        logger.debug(
            "[STATS] 开始更新统计信息", extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"}
        )

        passed = sum(
            1
            for r in results.values()
            if r.quality_level in [DataQualityLevel.EXCELLENT, DataQualityLevel.GOOD]
        )
        failed = sum(1 for r in results.values() if r.quality_level == DataQualityLevel.CRITICAL)
        warnings = sum(
            1
            for r in results.values()
            if r.quality_level in [DataQualityLevel.FAIR, DataQualityLevel.POOR]
        )
        critical = sum(1 for r in results.values() if r.quality_level == DataQualityLevel.CRITICAL)

        # 计算平均完整性
        avg_completeness = (
            sum(r.completeness for r in results.values()) / len(results) if results else 0.0
        )

        # 统计总K线数
        total_bars = sum(r.total_bars for r in results.values())
        total_missing = sum(r.missing_bars for r in results.values())
        total_duplicate = sum(r.duplicate_bars for r in results.values())
        total_invalid = sum(r.invalid_bars for r in results.values())

        logger.debug(
            f"[STATS] 统计详情: total_scanned={len(results)}, passed={passed}, failed={failed}, "
            f"warnings={warnings}, critical={critical}, avg_completeness={avg_completeness:.2f}%, "
            f"total_bars={total_bars}, total_missing={total_missing}, "
            f"total_duplicate={total_duplicate}, total_invalid={total_invalid}",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )

        self._stats.update(
            {
                "total_scanned": len(results),
                "total_passed": passed,
                "total_failed": failed,
                "total_warnings": warnings,
                "last_scan_time": datetime.now(),
            }
        )

        logger.info(
            f"[STATS] ✅ 统计信息更新完成: 总计={len(results)}, 通过={passed}, 失败={failed}, "
            f"警告={warnings}, 严重={critical}, 平均完整性={avg_completeness:.2f}%",
            extra={"log_type": "SYSTEM", "scenario": "manual_data_scan"},
        )

    def get_scan_results(self) -> Dict[Tuple[str, str], QualityScanResult]:
        """获取扫描结果

        Returns:
            扫描结果字典
        """
        with self._results_lock:
            return self._scan_results.copy()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return self._stats.copy()

    def clear_cache(self):
        """清空缓存"""
        with self._results_lock:
            self._scan_results.clear()


def _scan_single_worker(symbol: str, interval: str) -> QualityScanResult:
    """扫描单个品种（Worker函数，用于多进程）

    Args:
        symbol: 品种代码
        interval: 周期

    Returns:
        扫描结果
    """
    scenario = "manual_data_scan"
    # 设置子进程日志接入loghub
    try:
        from backend.infrastructure.tdx_asyncio import configure_subprocess_logging

        worker_id = hash(f"{symbol}_{interval}") % 1000  # 使用symbol和interval的hash作为worker_id
        worker_logger = configure_subprocess_logging(
            worker_id=worker_id, task_type="data_scan", scenario=scenario
        )
    except Exception:
        worker_logger = logger

    try:
        worker_logger.debug(
            f"[SCAN-WORKER] 开始扫描: symbol={symbol}, interval={interval}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 创建存储管理器
        storage_manager = StorageManager()

        # 同步读取数据
        load_start_time = time.time()
        df = storage_manager.load_data(symbol, interval)
        load_elapsed = time.time() - load_start_time

        worker_logger.debug(
            f"[SCAN-WORKER] 数据加载完成: symbol={symbol}, interval={interval}, "
            f"rows={len(df) if df is not None and not df.empty else 0}, 耗时={load_elapsed:.3f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 创建临时DataSensor进行验证
        sensor = DataSensor()
        validate_start_time = time.time()
        result = sensor._validate_dataframe(
            symbol, interval, df if df is not None else pd.DataFrame()
        )
        validate_elapsed = time.time() - validate_start_time

        total_elapsed = time.time() - load_start_time
        worker_logger.debug(
            f"[SCAN-WORKER] 扫描完成: symbol={symbol}, interval={interval}, "
            f"quality_level={result.quality_level.name}, completeness={result.completeness:.2f}%, "
            f"total_bars={result.total_bars}, missing_bars={result.missing_bars}, "
            f"duplicate_bars={result.duplicate_bars}, invalid_bars={result.invalid_bars}, "
            f"errors={len(result.errors)}, 加载耗时={load_elapsed:.3f}s, 验证耗时={validate_elapsed:.3f}s, 总耗时={total_elapsed:.3f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        # 检查数据质量级别，记录警告
        if result.quality_level == DataQualityLevel.CRITICAL:
            worker_logger.warning(
                f"[SCAN-WORKER] ⚠️ 扫描发现严重质量问题: symbol={symbol}, interval={interval}, "
                f"quality_level={result.quality_level.name}, errors={len(result.errors)}",
                extra={"log_type": "ALERT", "scenario": scenario},
            )
        elif result.quality_level == DataQualityLevel.POOR:
            worker_logger.debug(
                f"[SCAN-WORKER] 扫描发现质量问题: symbol={symbol}, interval={interval}, "
                f"quality_level={result.quality_level.name}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        worker_logger.info(
            f"[SCAN-WORKER] ✅ 扫描完成: symbol={symbol}, interval={interval}, "
            f"quality_level={result.quality_level.name}, completeness={result.completeness:.2f}%, 总耗时={total_elapsed:.3f}s",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        return result
    except Exception as e:
        worker_logger.debug(
            f"[SCAN-WORKER] Worker扫描失败详情: symbol={symbol}, interval={interval}, "
            f"异常类型={type(e).__name__}, 异常消息={str(e)}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        worker_logger.error(
            f"❌ [SCAN-WORKER] 扫描失败: {symbol}/{interval}, 错误: {e}",
            exc_info=True,
            extra={"log_type": "ALERT", "scenario": scenario},
        )
        return QualityScanResult(
            symbol=symbol,
            interval=interval,
            errors=[str(e)],
        )


# ==============================================================================
# Part 2: 数据验证器（StatelessValidator）
# ==============================================================================


@dataclass
class ValidationResult:
    """验证结果"""

    status: ValidationStatus
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    validation_time: datetime = field(default_factory=datetime.now)


class StatelessValidator:
    """无状态数据验证器

    支持多进程、纯函数验证，包括：
    - 格式验证
    - 逻辑验证
    - 完整性验证
    - 新鲜度验证
    """

    @staticmethod
    def validate_format(df: pd.DataFrame) -> ValidationResult:
        """验证数据格式

        Args:
            df: 数据DataFrame

        Returns:
            验证结果
        """
        result = ValidationResult(status=ValidationStatus.RUNNING, passed=True)

        if df is None or df.empty:
            result.status = ValidationStatus.FAILED
            result.passed = False
            result.errors.append("数据为空")
            return result

        # 检查必需列
        required_columns = ["open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            result.passed = False
            result.errors.append(f"缺少必需列: {missing_columns}")

        # 检查索引类型
        if not isinstance(df.index, pd.DatetimeIndex):
            result.warnings.append("索引不是 DatetimeIndex 类型")

        # 检查数据类型
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    result.passed = False
                    result.errors.append(f"列 '{col}' 不是数值类型")

        # 检查数据长度
        if len(df) == 0:
            result.warnings.append("数据长度为0")

        result.status = ValidationStatus.PASSED if result.passed else ValidationStatus.FAILED
        result.metrics["total_rows"] = len(df)
        result.metrics["total_columns"] = len(df.columns)

        return result

    @staticmethod
    def validate_logic(df: pd.DataFrame) -> ValidationResult:
        """验证数据逻辑

        Args:
            df: 数据DataFrame

        Returns:
            验证结果
        """
        result = ValidationResult(status=ValidationStatus.RUNNING, passed=True)

        if df is None or df.empty:
            result.status = ValidationStatus.SKIPPED
            result.passed = True
            return result

        # 检查价格逻辑
        if (
            "open" in df.columns
            and "high" in df.columns
            and "low" in df.columns
            and "close" in df.columns
        ):
            # high >= max(open, close)
            invalid_high = df["high"] < df[["open", "close"]].max(axis=1)
            if invalid_high.any():
                count = invalid_high.sum()
                result.warnings.append(f"最高价低于开盘收盘价: {count}条")
                result.metrics["invalid_high"] = int(count)

            # low <= min(open, close)
            invalid_low = df["low"] > df[["open", "close"]].min(axis=1)
            if invalid_low.any():
                count = invalid_low.sum()
                result.warnings.append(f"最低价高于开盘收盘价: {count}条")
                result.metrics["invalid_low"] = int(count)

            # 检查负值
            negative_prices = (
                (df["open"] < 0) | (df["high"] < 0) | (df["low"] < 0) | (df["close"] < 0)
            )
            if negative_prices.any():
                count = negative_prices.sum()
                result.passed = False
                result.errors.append(f"发现负数价格: {count}条")
                result.metrics["negative_prices"] = int(count)

        # 检查成交量
        if "volume" in df.columns:
            negative_volume = df["volume"] < 0
            if negative_volume.any():
                count = negative_volume.sum()
                result.passed = False
                result.errors.append(f"发现负数成交量: {count}条")
                result.metrics["negative_volume"] = int(count)

        result.status = ValidationStatus.PASSED if result.passed else ValidationStatus.FAILED
        return result

    @staticmethod
    def validate_completeness(df: pd.DataFrame, expected_bars: int) -> ValidationResult:
        """验证数据完整性

        Args:
            df: 数据DataFrame
            expected_bars: 预期数据条数

        Returns:
            验证结果
        """
        result = ValidationResult(status=ValidationStatus.RUNNING, passed=True)

        if df is None or df.empty:
            result.status = ValidationStatus.FAILED
            result.passed = False
            result.errors.append("数据为空")
            return result

        actual_bars = len(df)
        completeness = (actual_bars / expected_bars * 100.0) if expected_bars > 0 else 100.0

        result.metrics["actual_bars"] = actual_bars
        result.metrics["expected_bars"] = expected_bars
        result.metrics["completeness"] = completeness

        if completeness < 80.0:
            result.passed = False
            result.errors.append(f"数据完整性低于80%: {completeness:.2f}%")
        elif completeness < 90.0:
            result.warnings.append(f"数据完整性较低: {completeness:.2f}%")

        result.status = ValidationStatus.PASSED if result.passed else ValidationStatus.FAILED
        return result

    @staticmethod
    def validate_freshness(df: pd.DataFrame, max_age_days: int = 7) -> ValidationResult:
        """验证数据新鲜度

        Args:
            df: 数据DataFrame
            max_age_days: 最大允许天数

        Returns:
            验证结果
        """
        result = ValidationResult(status=ValidationStatus.RUNNING, passed=True)

        if df is None or df.empty:
            result.status = ValidationStatus.SKIPPED
            result.passed = True
            return result

        # 获取最后一条数据的时间
        last_update = df.index[-1]

        # 获取当前时间（使用网络时间）
        try:
            current_time = NetworkTimeSync.get_time()
        except Exception as e:
            logger.debug(
                f"⚠️ [DataQuality] 获取网络时间失败，使用系统时间: {e}", extra={"log_type": "SYSTEM"}
            )
            current_time = datetime.now()

        # 计算时间差
        if isinstance(last_update, pd.Timestamp):
            last_update = last_update.to_pydatetime()

        age_days = (current_time - last_update).days

        result.metrics["last_update"] = last_update.isoformat()
        result.metrics["age_days"] = age_days
        result.metrics["max_age_days"] = max_age_days

        if age_days > max_age_days:
            result.passed = False
            result.errors.append(f"数据过旧: {age_days}天 > {max_age_days}天")
        elif age_days > max_age_days / 2:
            result.warnings.append(f"数据较旧: {age_days}天")

        result.status = ValidationStatus.PASSED if result.passed else ValidationStatus.FAILED
        return result

    @staticmethod
    def validate_all(
        df: pd.DataFrame,
        expected_bars: Optional[int] = None,
        max_age_days: int = 7,
    ) -> Dict[str, ValidationResult]:
        """执行所有验证

        Args:
            df: 数据DataFrame
            expected_bars: 预期数据条数
            max_age_days: 最大允许天数

        Returns:
            验证结果字典
        """
        results = {}

        # 格式验证
        results["format"] = StatelessValidator.validate_format(df)

        # 逻辑验证
        results["logic"] = StatelessValidator.validate_logic(df)

        # 完整性验证
        if expected_bars is not None:
            results["completeness"] = StatelessValidator.validate_completeness(df, expected_bars)

        # 新鲜度验证
        results["freshness"] = StatelessValidator.validate_freshness(df, max_age_days)

        return results


# ==============================================================================
# Part 3: 文件监控（DataFileWatcher）
# ==============================================================================


class DataFileWatcher:
    """数据文件监控器

    实时监控数据文件变化，支持：
    - 防抖机制
    - 事件发布
    - native_ipc集成：文件监控事件的跨进程推送
    """

    def __init__(self, watch_dir: Path, event_engine=None):
        """初始化文件监控器

        Args:
            watch_dir: 监控目录
            event_engine: VnPy EventEngine
        """
        self.watch_dir = Path(watch_dir)
        self.event_engine = event_engine

        # 监控状态
        self._watching = False
        self._watch_thread = None

        # 文件状态缓存
        self._file_states: Dict[Path, float] = {}  # {file_path: last_modified_time}

        # 防抖控制
        self._debounce_interval = 1.0  # 1秒
        self._pending_events: Dict[Path, float] = {}  # {file_path: event_time}

        logger.info(f"🔍 文件监控器初始化: {self.watch_dir}")

    def start(self):
        """启动监控"""
        if self._watching:
            logger.warning("⚠️ 文件监控已经启动", extra={"log_type": "SYSTEM"})
            return

        self._watching = True
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

        logger.info("✅ 文件监控已启动")

    def stop(self):
        """停止监控"""
        if not self._watching:
            return

        self._watching = False
        if self._watch_thread:
            self._watch_thread.join(timeout=2)

        logger.info("✅ 文件监控已停止")

    def _watch_loop(self):
        """监控循环"""
        logger.info("🔍 文件监控循环启动")

        while self._watching:
            try:
                self._scan_directory()
                self._process_pending_events()
                time.sleep(1.0)  # 每秒扫描一次
            except Exception as e:
                logger.error(
                    f"❌ 文件监控循环异常: {e}", exc_info=True, extra={"log_type": "SYSTEM"}
                )

    def _scan_directory(self):
        """扫描目录"""
        if not self.watch_dir.exists():
            return

        # 扫描所有Parquet文件（优先使用native_iocp高性能目录遍历）
        try:
            if NATIVE_IOCP_AVAILABLE and fast_dir_walk is not None:

                def _recursive_walk(directory: Path) -> List[Path]:
                    files: List[Path] = []
                    try:
                        # fast_dir_walk返回: [(root, dirs_list, files_list), ...]
                        result = fast_dir_walk(str(directory))  # type: ignore[call-arg]
                        if result and len(result) > 0:
                            _root, dirs_list, files_list = result[0]

                            # 当前目录文件
                            for file_name in files_list:
                                file_path = Path(file_name)
                                if file_path.suffix == ".parquet":
                                    files.append(file_path)

                            # 子目录递归
                            for dir_name in dirs_list:
                                files.extend(_recursive_walk(Path(dir_name)))
                    except Exception as e:
                        # 回退到标准rglob
                        logger.debug(f"fast_dir_walk失败，回退到rglob: {e}")
                        return list(directory.rglob("*.parquet"))
                    return files

                file_paths = _recursive_walk(self.watch_dir)
            else:
                # 降级：使用标准rglob
                file_paths = list(self.watch_dir.rglob("*.parquet"))
        except Exception as e:
            # 任意异常统一回退到rglob
            logger.debug(f"目录扫描异常，使用rglob回退: {e}")
            file_paths = list(self.watch_dir.rglob("*.parquet"))

        # 处理文件状态与事件
        for file_path in file_paths:
            try:
                mtime = file_path.stat().st_mtime

                # 检查是否有变化
                if file_path not in self._file_states:
                    # 新文件
                    self._file_states[file_path] = mtime
                    self._add_pending_event(file_path, "created")
                elif self._file_states[file_path] != mtime:
                    # 文件修改
                    self._file_states[file_path] = mtime
                    self._add_pending_event(file_path, "modified")
            except Exception as e:
                logger.debug(f"扫描文件失败: {file_path}, {e}")

    def _add_pending_event(self, file_path: Path, event_type: str):
        """添加待处理事件（防抖）

        Args:
            file_path: 文件路径
            event_type: 事件类型
        """
        self._pending_events[file_path] = time.time()

    def _process_pending_events(self):
        """处理待处理事件（防抖）"""
        current_time = time.time()
        processed_files = []

        for file_path, event_time in self._pending_events.items():
            # 检查是否超过防抖间隔
            if current_time - event_time >= self._debounce_interval:
                self._publish_event(file_path)
                processed_files.append(file_path)

        # 清理已处理事件
        for file_path in processed_files:
            self._pending_events.pop(file_path, None)

    def _publish_event(self, file_path: Path):
        """发布文件变化事件

        Args:
            file_path: 文件路径
        """
        logger.info(f"📢 文件变化: {file_path.name}")

        # 发送到EventEngine
        if self.event_engine:
            try:
                from vnpy.event import Event

                event = Event(
                    type="file_changed",
                    data={
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                self.event_engine.put(event)
            except Exception as e:
                logger.warning(f"⚠️ 发送文件变化事件失败: {e}", extra={"log_type": "SYSTEM"})


# ==============================================================================
# Part 4: 健康检查（HealthChecker）
# ==============================================================================


@dataclass
class HealthCheckResult:
    """健康检查结果"""

    healthy: bool
    score: float = 0.0  # 健康分数 0-100
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    check_time: datetime = field(default_factory=datetime.now)


class HealthChecker:
    """系统健康检查器

    多维度健康检查，包括：
    - 数据完整性检查
    - 存储空间检查
    - 缓存状态检查
    - 系统资源检查
    """

    def __init__(self, storage_manager: Optional[StorageManager] = None):
        """初始化健康检查器

        Args:
            storage_manager: 存储管理器
        """
        self.storage_manager = storage_manager or StorageManager()

    def check_health(self) -> HealthCheckResult:
        """执行完整健康检查

        Returns:
            健康检查结果
        """
        result = HealthCheckResult(healthy=True, score=100.0)

        # 检查存储空间
        storage_health = self._check_storage()
        if not storage_health["healthy"]:
            result.healthy = False
            result.issues.extend(storage_health["issues"])
        result.score -= storage_health.get("penalty", 0)
        result.metrics["storage"] = storage_health

        # 检查数据目录
        data_health = self._check_data_directory()
        if not data_health["healthy"]:
            result.warnings.extend(data_health["warnings"])
        result.score -= data_health.get("penalty", 0)
        result.metrics["data_directory"] = data_health

        # 添加建议
        if result.score < 80:
            result.suggestions.append("建议进行数据质量扫描")
        if result.score < 60:
            result.suggestions.append("建议清理无效数据")

        # 最终分数
        result.score = max(0, min(100, result.score))
        result.healthy = result.score >= 60

        return result

    def _check_storage(self) -> Dict[str, Any]:
        """检查存储空间

        Returns:
            检查结果
        """
        result = {"healthy": True, "issues": [], "warnings": [], "penalty": 0}

        try:
            import shutil

            # 获取磁盘空间
            data_dir = self.storage_manager.data_dir
            if data_dir.exists():
                disk_usage = shutil.disk_usage(data_dir)
                free_percent = (disk_usage.free / disk_usage.total) * 100

                result["free_percent"] = free_percent
                result["free_gb"] = disk_usage.free / (1024**3)
                result["total_gb"] = disk_usage.total / (1024**3)

                if free_percent < 5:
                    result["healthy"] = False
                    result["issues"].append(f"磁盘空间严重不足: {free_percent:.1f}%")
                    result["penalty"] = 30
                elif free_percent < 10:
                    result["warnings"].append(f"磁盘空间较低: {free_percent:.1f}%")
                    result["penalty"] = 15
                elif free_percent < 20:
                    result["warnings"].append(f"磁盘空间需要关注: {free_percent:.1f}%")
                    result["penalty"] = 5
        except Exception as e:
            logger.warning(f"⚠️ 检查存储空间失败: {e}", extra={"log_type": "SYSTEM"})
            result["warnings"].append("无法检查存储空间")

        return result

    def _check_data_directory(self) -> Dict[str, Any]:
        """检查数据目录

        Returns:
            检查结果
        """
        result = {"healthy": True, "warnings": [], "penalty": 0}

        try:
            data_dir = self.storage_manager.data_dir

            if not data_dir.exists():
                result["healthy"] = False
                result["warnings"].append("数据目录不存在")
                result["penalty"] = 20
            else:
                # 统计文件数量
                parquet_files = list(data_dir.rglob("*.parquet"))
                result["total_files"] = len(parquet_files)

                if len(parquet_files) == 0:
                    result["warnings"].append("没有找到Parquet数据文件")
                    result["penalty"] = 10
        except Exception as e:
            logger.warning(f"⚠️ 检查数据目录失败: {e}", extra={"log_type": "SYSTEM"})

        return result


# ==============================================================================
# Part 5: IPO日期缓存（IPODateCache）
# ==============================================================================


class IPODateCache:
    """IPO日期缓存管理器

    两级缓存（内存+文件），目标命中率95%+：
    - Level 1: 内存缓存（LRU）
    - Level 2: 文件缓存（native_iocp异步读写）

    文件I/O支持：
    - 同步方法：save() 和 _load_from_file() 用于初始化等同步场景
    - 异步方法：save_async() 和 _load_from_file_async() 使用 native_iocp 异步I/O
    """

    def __init__(self, cache_file: Optional[Path] = None, max_memory_size: int = 10000):
        """初始化IPO日期缓存

        Args:
            cache_file: 缓存文件路径
            max_memory_size: 最大内存缓存数量
        """
        # 🔧 修复：使用ConfigManager获取缓存目录，确保统一使用data/cache目录
        if cache_file is None:
            from backend.infrastructure.data_module_vnpy.core_engine import ConfigManager

            config_manager = ConfigManager.get_instance()
            cache_dir = config_manager.get_cache_dir()
            cache_file = cache_dir / "ipo_dates.json"
        self.cache_file = cache_file
        self.max_memory_size = max_memory_size

        # 尝试使用native_collections，否则回退到手动LRU实现
        self._use_native = NATIVE_COLLECTIONS_AVAILABLE and HighPerfLRUCache is not None

        # 统一类型声明
        self._all_data: Optional[Dict[str, Optional[date]]] = None
        self._cache: Any = None
        self._memory_cache: Dict[str, Optional[date]] = {}
        self._access_order: List[str] = []

        if self._use_native and HighPerfLRUCache is not None:
            # 使用native_collections.HighPerfLRUCache作为底层存储
            # HighPerfLRUCache构造函数接受一个可选参数maxsize
            self._cache = HighPerfLRUCache(max_memory_size)  # type: ignore
            # 额外维护一个字典用于遍历和保存（因为HighPerfLRUCache没有遍历方法）
            # 这个字典与缓存保持同步，但不参与LRU淘汰
            self._all_data = {}
            logger.debug("✅ [IPODateCache] 使用native_collections.HighPerfLRUCache")
        else:
            # 回退到手动LRU实现
            self._memory_cache = {}
            self._access_order = []
            logger.debug("⚠️ [IPODateCache] native_collections不可用，回退到手动LRU实现")

        self._lock = threading.Lock()

        # 统计信息
        self._stats = {
            "memory_hits": 0,
            "file_hits": 0,
            "misses": 0,
        }

        # 初始加载（同步，因为初始化需要等待数据）
        self._load_from_file()

    def get(self, symbol: str) -> Optional[date]:
        """获取IPO日期

        Args:
            symbol: 品种代码

        Returns:
            IPO日期，如果不存在则返回None
        """
        with self._lock:
            if self._use_native:
                # 使用native_collections实现
                try:
                    if self._cache is not None:
                        ipo_date = self._cache.get(symbol)
                        if ipo_date is not None:
                            self._stats["memory_hits"] += 1
                            # 更新_all_data（如果不存在）
                            if self._all_data is not None:
                                if symbol not in self._all_data:
                                    self._all_data[symbol] = ipo_date
                            return ipo_date
                except (KeyError, AttributeError):
                    # key不存在或缓存未初始化
                    pass
                self._stats["misses"] += 1
                return None
            else:
                # 使用手动LRU实现
                if symbol in self._memory_cache:
                    self._stats["memory_hits"] += 1
                    # 更新LRU
                    if symbol in self._access_order:
                        self._access_order.remove(symbol)
                    self._access_order.append(symbol)
                    return self._memory_cache[symbol]

                # Level 2: 文件缓存（已在初始化时加载）
                self._stats["misses"] += 1
                return None

    def set(self, symbol: str, ipo_date: Optional[date]):
        """设置IPO日期

        Args:
            symbol: 品种代码
            ipo_date: IPO日期
        """
        with self._lock:
            if self._use_native:
                # 使用native_collections实现
                # HighPerfLRUCache会自动处理LRU淘汰
                if self._cache is not None:
                    self._cache.set(symbol, ipo_date)
                # 更新_all_data用于遍历和保存
                if self._all_data is not None:
                    self._all_data[symbol] = ipo_date
            else:
                # 使用手动LRU实现
                if symbol not in self._memory_cache:
                    # 检查是否需要清理
                    if len(self._memory_cache) >= self.max_memory_size:
                        # LRU清理
                        oldest = self._access_order.pop(0)
                        self._memory_cache.pop(oldest, None)

                self._memory_cache[symbol] = ipo_date

                # 更新LRU
                if symbol in self._access_order:
                    self._access_order.remove(symbol)
                self._access_order.append(symbol)

    def batch_set(self, ipo_dates: Dict[str, Optional[date]]):
        """批量设置IPO日期

        Args:
            ipo_dates: IPO日期字典
        """
        for symbol, ipo_date in ipo_dates.items():
            self.set(symbol, ipo_date)

    def save(self):
        """保存缓存到文件（同步版本）"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            # 转换为JSON格式
            data = {}
            with self._lock:
                if self._use_native and self._all_data is not None:
                    # 使用_all_data来获取所有数据
                    for symbol, ipo_date in self._all_data.items():
                        if ipo_date:
                            data[symbol] = ipo_date.isoformat()
                        else:
                            data[symbol] = None
                else:
                    # 使用手动LRU实现
                    for symbol, ipo_date in self._memory_cache.items():
                        if ipo_date:
                            data[symbol] = ipo_date.isoformat()
                        else:
                            data[symbol] = None

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ IPO缓存已保存: {len(data)}条")
        except Exception as e:
            logger.error(f"❌ 保存IPO缓存失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)

    async def save_async(self):
        """保存缓存到文件（异步版本，使用 native_iocp）

        Returns:
            bool: 保存是否成功
        """
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            # 转换为JSON格式
            data = {}
            with self._lock:
                if self._use_native and self._all_data is not None:
                    # 使用_all_data来获取所有数据
                    for symbol, ipo_date in self._all_data.items():
                        if ipo_date:
                            data[symbol] = ipo_date.isoformat()
                        else:
                            data[symbol] = None
                else:
                    # 使用手动LRU实现
                    for symbol, ipo_date in self._memory_cache.items():
                        if ipo_date:
                            data[symbol] = ipo_date.isoformat()
                        else:
                            data[symbol] = None

            # 将数据序列化为JSON字符串
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            json_bytes = json_str.encode("utf-8")

            # 使用 native_iocp 异步写入
            async with await compat_aopen(self.cache_file, "wb") as f:
                await f.write(json_bytes)

            logger.info(f"✅ IPO缓存已保存（异步）: {len(data)}条")
            return True

        except Exception as e:
            logger.error(f"❌ 保存IPO缓存失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)
            return False

    def _load_from_file(self):
        """从文件加载缓存（同步版本）"""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 使用统一的提取函数处理缓存格式（兼容新旧两种格式）
            from backend.infrastructure.data_module_vnpy.core_engine import ChinaStockEngine

            ipo_dates = ChinaStockEngine._extract_ipo_data_from_cache(data)

            # 更新内存缓存
            with self._lock:
                if self._use_native:
                    # 使用native_collections实现
                    if self._cache is not None:
                        for symbol, ipo_date in ipo_dates.items():
                            self._cache.set(symbol, ipo_date)
                            if self._all_data is not None:
                                self._all_data[symbol] = ipo_date
                        cache_size = self._cache.size()
                    else:
                        cache_size = 0
                else:
                    # 使用手动LRU实现
                    self._memory_cache.update(ipo_dates)
                    cache_size = len(self._memory_cache)

            logger.info(f"✅ IPO缓存已加载: {cache_size}条")
        except Exception as e:
            logger.error(f"❌ 加载IPO缓存失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)

    async def _load_from_file_async(self):
        """从文件加载缓存（异步版本，使用 native_iocp）

        Returns:
            bool: 加载是否成功
        """
        if not self.cache_file.exists():
            return True

        try:
            # 使用 native_iocp 异步读取
            async with await compat_aopen(self.cache_file, "rb") as f:
                json_bytes = await f.read()

            # 解码并解析JSON
            json_str = json_bytes.decode("utf-8")
            data = json.loads(json_str)

            # 使用统一的提取函数处理缓存格式（兼容新旧两种格式）
            from backend.infrastructure.data_module_vnpy.core_engine import ChinaStockEngine

            ipo_dates = ChinaStockEngine._extract_ipo_data_from_cache(data)

            # 更新内存缓存
            with self._lock:
                if self._use_native:
                    # 使用native_collections实现
                    if self._cache is not None:
                        for symbol, ipo_date in ipo_dates.items():
                            self._cache.set(symbol, ipo_date)
                            if self._all_data is not None:
                                self._all_data[symbol] = ipo_date
                        cache_size = self._cache.size()
                    else:
                        cache_size = 0
                else:
                    # 使用手动LRU实现
                    self._memory_cache.update(ipo_dates)
                    cache_size = len(self._memory_cache)

            logger.info(f"✅ IPO缓存已加载（异步）: {cache_size}条")
            return True

        except Exception as e:
            logger.error(f"❌ 加载IPO缓存失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计

        Returns:
            统计信息
        """
        with self._lock:
            total_requests = sum(self._stats.values())
            hit_rate = 0.0
            if total_requests > 0:
                hit_rate = (
                    (self._stats["memory_hits"] + self._stats["file_hits"]) / total_requests * 100
                )

            # 获取缓存大小
            if self._use_native:
                cache_size = self._cache.size() if self._cache else 0
            else:
                cache_size = len(self._memory_cache)

            return {
                **self._stats,
                "total_requests": total_requests,
                "hit_rate": hit_rate,
                "cache_size": cache_size,
            }


# ==============================================================================
# 导出API（向后兼容）
# ==============================================================================

__all__ = [
    # 数据质量级别
    "DataQualityLevel",
    "ValidationStatus",
    # 数据结果
    "QualityScanResult",
    "ValidationResult",
    "HealthCheckResult",
    # 核心组件
    "DataSensor",
    "StatelessValidator",
    "DataFileWatcher",
    "HealthChecker",
    "IPODateCache",
]
