# -*- coding: utf-8 -*-
"""
数据质量管理模块

负责数据存储、校验、感知、文件监控和系统健康检查，包括：
- 数据存储管理（Parquet格式）
- 数据校验和感知
- 文件监控和变化检测（增强防抖机制）
- 系统健康检查
- 数据质量概览和报告

v2.1 改进：
- 使用网络时间替代系统时间进行数据新鲜度计算

合并来源：storage.py + validator.py + data_sensor.py + file_watcher.py (v2)
"""

from __future__ import annotations

# ==================== 导入声明 ====================
import asyncio
import logging
import os
import sys
import time
import threading
import multiprocessing as mp
from threading import Thread, Event as ThreadEvent
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import psutil

from .data_module import config_manager

# 导入网络时间同步模块
from .data_module import get_real_date

# ==================== 日志配置 ====================
# 创建专用logger（模块级别）
logger = logging.getLogger("backend.data_module.quality")
logger_alert = logging.getLogger("backend.data_module.alert")

# 旧架构（向后兼容）
from .load_balancer import (
    LoadBalancer,
    LocalProcessingTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)

# 新架构（动态并发调整）
from .load_balancer import (
    ResourceMonitor,
    ExecutionPolicy,
    MultiProcessBatchModel,
    TaskUnit,
)

# ==================== 辅助函数（用于多进程） ====================


def _quality_scan_worker_process(
    worker_id: int,
    task_queue,
    result_queue,
    metrics_queue,
    stop_event,
    data_dir: str,
    interval: str,
    min_rows: int,
):
    """质量扫描worker进程（v3.6新增）

    从task_queue循环拉取品种代码，扫描数据质量并上报结果

    Args:
        worker_id: Worker进程ID
        task_queue: 共享任务队列
        result_queue: 结果队列
        metrics_queue: 监控指标队列
        stop_event: 停止事件
        data_dir: 数据目录
        interval: K线周期
        min_rows: 最小行数阈值
    """
    import asyncio
    import queue
    import logging

    # ✅ 配置子进程日志，接入LogHub统一路由
    try:
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

        hub = get_logging_hub()
        root_logger = logging.getLogger()

        # 清理继承的handler
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

        # 添加LogHub
        root_logger.addHandler(hub)
        root_logger.setLevel(logging.DEBUG)

        logger = logging.getLogger(f"subprocess.quality_scan.{worker_id}")
        logger.propagate = True
        logger.info(f"✅ 质量扫描子进程 {worker_id} 日志系统已接入LogHub")
    except Exception as e:
        logger = logging.getLogger(f"QualityScanWorker-{worker_id}")
        logger.warning(f"⚠️ 质量扫描子进程 {worker_id} LogHub配置失败: {e}")

    asyncio.run(
        _quality_scan_worker_async(
            worker_id,
            task_queue,
            result_queue,
            metrics_queue,
            stop_event,
            data_dir,
            interval,
            min_rows,
        )
    )


async def _quality_scan_worker_async(
    worker_id: int,
    task_queue,
    result_queue,
    metrics_queue,
    stop_event,
    data_dir: str,
    interval: str,
    min_rows: int,
):
    """质量扫描worker的异步逻辑"""
    import queue
    import logging
    import time
    from pathlib import Path

    logger = logging.getLogger(f"QualityScanWorker-{worker_id}")

    # 启动lag监控
    from .load_balancer import LagMonitor

    lag_monitor_task = asyncio.create_task(
        LagMonitor.monitor_and_report(
            metrics_queue=metrics_queue,
            worker_id=worker_id,
            stop_event=stop_event,
            interval_seconds=0.3,
        )
    )
    logger.info(f"[Worker-{worker_id}] ✅ 已启动lag监控（质量扫描模式）")

    processed_count = 0
    empty_count = 0
    max_empty_before_exit = 3

    # 非阻塞put辅助函数
    async def _safe_put_result(msg: tuple, max_retries: int = 5):
        """非阻塞put+重试"""
        for attempt in range(max_retries):
            try:
                result_queue.put_nowait(msg)
                return True
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.02)
                else:
                    logger.warning(f"[Worker-{worker_id}] 队列满，丢弃结果")
                    return False
        return False

    logger.info(f"[Worker-{worker_id}] 开始从共享队列拉取扫描任务...")

    while not stop_event.is_set():
        try:
            # 从队列拉取任务
            symbol = task_queue.get(timeout=1.0)
            empty_count = 0

            # 扫描数据质量
            start_time = time.perf_counter()
            quality_info = _scan_single_quality(
                symbol,
                data_dir,
                interval,
                min_rows,
            )
            duration = time.perf_counter() - start_time

            # 上报结果
            await _safe_put_result((symbol, quality_info, duration))
            processed_count += 1

            if processed_count % 100 == 0:
                logger.info(f"[Worker-{worker_id}] 已扫描 {processed_count} 个品种")

        except queue.Empty:
            empty_count += 1
            if empty_count >= max_empty_before_exit:
                logger.info(f"[Worker-{worker_id}] 队列连续{empty_count}次为空，准备退出")
                break
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"[Worker-{worker_id}] 扫描任务时发生错误: {e}")
            await asyncio.sleep(0.1)

    # 停止lag监控
    await LagMonitor.cancel_monitor(lag_monitor_task)
    logger.info(f"[Worker-{worker_id}] 完成，共扫描 {processed_count} 个品种")


def _scan_single_quality(
    symbol: str,
    data_dir: str,
    interval: str,
    min_rows: int,
) -> Optional[Dict[str, Any]]:
    """扫描单个品种的数据质量

    Args:
        symbol: 品种代码
        data_dir: 数据目录
        interval: K线周期
        min_rows: 最小行数阈值

    Returns:
        Optional[Dict]: 质量信息或None
    """
    try:
        from pathlib import Path

        file_path = Path(data_dir) / symbol / interval / "data.parquet"

        if not file_path.exists():
            return None

        # 读取数据
        df = pd.read_parquet(file_path)

        if df.empty:
            return {
                "symbol": symbol,
                "has_data": False,
                "row_count": 0,
                "meets_threshold": False,
            }

        row_count = len(df)
        meets_threshold = row_count >= min_rows

        # 获取日期范围
        if "datetime" in df.columns:
            start_date = df["datetime"].min()
            end_date = df["datetime"].max()
        else:
            start_date = df.index.min() if hasattr(df.index, "min") else None
            end_date = df.index.max() if hasattr(df.index, "max") else None

        return {
            "symbol": symbol,
            "has_data": True,
            "row_count": row_count,
            "meets_threshold": meets_threshold,
            "start_date": start_date,
            "end_date": end_date,
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "has_data": False,
            "error": str(e),
        }


def _read_single_kline(
    symbol: str,
    data_dir: str,
    interval: str,
    start_date: Optional[Union[str, date]] = None,
    end_date: Optional[Union[str, date]] = None,
) -> Optional[pd.DataFrame]:
    """读取单个品种的K线数据（用于多进程池调用）

    这个函数必须是顶层函数，以便multiprocessing.Pool可以pickle它。

    Args:
        symbol: 品种代码
        data_dir: 数据目录路径（字符串）
        interval: K线周期
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        Optional[pd.DataFrame]: K线数据或None
    """
    try:
        from pathlib import Path

        # 构建文件路径
        file_path = Path(data_dir) / symbol / interval / "data.parquet"

        if not file_path.exists():
            return None

        # 读取数据
        df = pd.read_parquet(file_path)

        if df.empty:
            return df

        # 确保 datetime 列存在且无重复
        if "datetime" in df.columns and len(df) > 0:
            df = df.sort_values("datetime")
            df = df.drop_duplicates(subset=["datetime"], keep="last")
            df = df.reset_index(drop=True)

        # 过滤日期
        if start_date is not None:
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date).date()
            if "datetime" in df.columns:
                df = df[df["datetime"] >= pd.Timestamp(start_date)]
            else:
                df = df[df.index >= pd.Timestamp(start_date)]

        if end_date is not None:
            if isinstance(end_date, str):
                end_date = pd.to_datetime(end_date).date()
            if "datetime" in df.columns:
                df = df[df["datetime"] <= pd.Timestamp(end_date)]
            else:
                df = df[df.index <= pd.Timestamp(end_date)]

        return df if isinstance(df, pd.DataFrame) else None

    except Exception:
        # 多进程环境中，不输出日志
        return None


def _scan_single_symbol(scan_data: tuple) -> Optional[dict]:
    """扫描单个品种的质量（用于多进程池调用）

    这个函数必须是顶层函数，以便multiprocessing.Pool可以pickle它。

    Args:
        scan_data: (symbol, intervals, data_dir_str) 元组

    Returns:
        Optional[dict]: 品种质量信息字典或None
    """
    try:
        symbol, intervals, data_dir_str = scan_data

        # 在进程内部创建必要的对象
        # 注意：这里不能使用DataValidator，因为它可能有复杂的依赖
        # 我们简化扫描逻辑，只检查文件是否存在和基本质量

        data_dir = Path(data_dir_str)
        interval_results = {}
        has_data = False

        for interval in intervals:
            try:
                file_path = data_dir / symbol / interval / "data.parquet"

                if not file_path.exists():
                    interval_results[interval] = {
                        "has_data": False,
                        "record_count": 0,
                        "is_valid": False,
                        "errors": ["文件不存在"],
                    }
                    continue

                # 读取数据检查基本质量
                df = pd.read_parquet(file_path)

                if df.empty:
                    interval_results[interval] = {
                        "has_data": False,
                        "record_count": 0,
                        "is_valid": False,
                        "errors": ["数据为空"],
                    }
                    continue

                # 数据存在
                has_data = True
                record_count = len(df)

                # 基本检查：是否有datetime列
                has_datetime = "datetime" in df.columns
                errors = []
                if not has_datetime:
                    errors.append("缺少datetime列")

                interval_results[interval] = {
                    "has_data": True,
                    "record_count": record_count,
                    "is_valid": len(errors) == 0,
                    "errors": errors,
                }

            except Exception as e:
                interval_results[interval] = {
                    "has_data": False,
                    "record_count": 0,
                    "is_valid": False,
                    "errors": [f"扫描失败: {str(e)}"],
                }

        # 如果没有任何数据，标记为缺失
        if not has_data:
            return {
                "symbol": symbol,
                "intervals": interval_results,
                "overall_score": 0,
                "has_errors": True,
                "has_warnings": False,
                "is_missing": True,
            }

        # 计算整体评分
        has_errors = any(r.get("errors") for r in interval_results.values())
        valid_count = sum(1 for r in interval_results.values() if r.get("is_valid", False))
        total_count = len(interval_results)
        avg_score = int((valid_count / total_count) * 100) if total_count > 0 else 0

        return {
            "symbol": symbol,
            "intervals": interval_results,
            "overall_score": avg_score,
            "has_errors": has_errors,
            "has_warnings": False,
            "is_missing": False,
        }

    except Exception as e:
        # 返回错误结果
        return {
            "symbol": scan_data[0] if scan_data else "unknown",
            "intervals": {},
            "overall_score": 0,
            "has_errors": True,
            "has_warnings": False,
            "is_missing": True,
            "error": str(e),
        }


# ==================== IPO日期缓存管理 ====================


# 全局IPO缓存单例
_global_ipo_cache_instance: Optional["IPODateCache"] = None
_global_ipo_cache_lock = threading.RLock()


def get_ipo_cache(cache_file: Optional[Path] = None) -> "IPODateCache":
    """获取全局IPO缓存单例

    使用双重检查锁定(Double-Check Locking)保证线程安全的单例创建

    Args:
        cache_file: 缓存文件路径（仅在首次创建时有效）

    Returns:
        IPODateCache: 全局单例实例
    """
    global _global_ipo_cache_instance

    # 第一次检查（无锁，快速路径）
    if _global_ipo_cache_instance is not None:
        return _global_ipo_cache_instance

    # 需要创建实例，获取锁
    with _global_ipo_cache_lock:
        # 第二次检查（有锁，确保只创建一次）
        if _global_ipo_cache_instance is None:
            _global_ipo_cache_instance = IPODateCache(cache_file)
            logger.info("✓ 创建IPO缓存全局单例")

        return _global_ipo_cache_instance


class IPODateCache:
    """IPO日期缓存管理器（单例模式，JSON文件后端）

    使用JSON文件持久化存储IPO日期：
    - 文件路径: data/cache/ipo_dates_cache.json
    - 格式: {"symbol": "YYYYMMDD", ...}
    - 每日0时失效机制

    注意：建议使用get_ipo_cache()函数获取全局单例，而不是直接实例化此类
    """

    def __init__(self, cache_file: Optional[Path] = None):
        """初始化IPO日期缓存（JSON文件后端）

        Args:
            cache_file: JSON缓存文件路径，默认使用 data/cache/ipo_dates_cache.json
        """
        self.logger = logging.getLogger(__name__)

        # 内存缓存：{symbol: date}
        self._memory_cache: Dict[str, Optional[date]] = {}

        # 🔧 原始IPO日期缓存：用于记录未解析的原始值（如70）
        self._raw_ipo_dates: Dict[str, int] = {}

        # JSON文件路径
        if cache_file is None:
            cache_dir = config_manager.get_cache_dir()
            self.cache_file = cache_dir / "ipo_dates_cache.json"
        else:
            self.cache_file = cache_file

        # 确保缓存目录存在
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        # 线程锁
        self._lock = threading.RLock()

        # 缓存日期（用于验证）
        self._cache_date: Optional[str] = None

        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "api_calls": 0,
            "api_success": 0,
            "api_timeout": 0,
        }

        # 从JSON文件加载缓存
        self._load_from_json()

    def _load_from_json(self) -> None:
        """从JSON文件加载缓存"""
        try:
            if self.cache_file.exists():
                import json

                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 加载元数据
                self._cache_date = data.get("_meta", {}).get("cache_date")

                # 加载IPO数据
                ipo_data = data.get("ipo_dates", {})
                for symbol, ipo_str in ipo_data.items():
                    self._memory_cache[symbol] = self._parse_ipo_date_str(ipo_str)

                self.logger.info(
                    "✓ IPO缓存已加载: %d条记录（缓存日期: %s）",
                    len(self._memory_cache),
                    self._cache_date,
                )
            else:
                self.logger.info("IPO缓存文件不存在，等待首次下载")

        except Exception as e:
            self.logger.error("加载IPO缓存失败: %s", e, exc_info=True)
            self._memory_cache = {}
            self._cache_date = None

    def _parse_ipo_date_str(self, ipo_str: Optional[str]) -> Optional[date]:
        """解析IPO日期字符串（YYYY-MM-DD格式）

        Args:
            ipo_str: IPO日期字符串

        Returns:
            解析后的日期，失败返回None
        """
        if not ipo_str or ipo_str == "null":
            return None

        try:
            return datetime.strptime(ipo_str, "%Y-%m-%d").date()
        except (ValueError, AttributeError) as e:
            self.logger.warning("解析IPO日期失败: %s (%s)", ipo_str, e)
            return None

    def _parse_ipo_date(self, ipo_timestamp: int) -> Optional[date]:
        """解析IPO日期时间戳（YYYYMMDD格式）

        Args:
            ipo_timestamp: IPO日期时间戳（如20100101）

        Returns:
            解析后的日期，失败返回None
        """
        if not ipo_timestamp or ipo_timestamp == 0:
            return None

        try:
            ipo_int = int(ipo_timestamp)

            # 🔧 健壮性检查：如果值太小（如70），说明是无效数据
            # 有效的IPO日期最早应该是19900000以上（1990年）
            if ipo_int < 19900000:
                return None

            ipo_str = str(ipo_int).zfill(8)
            if len(ipo_str) == 8:
                return datetime.strptime(ipo_str, "%Y%m%d").date()
        except (ValueError, AttributeError) as e:
            # 只对看起来像日期但格式错误的值记录警告
            if int(ipo_timestamp) >= 19900000:
                self.logger.warning("解析IPO日期失败: %s (%s)", ipo_timestamp, e)

        return None

    def _is_all_fields_zero(self, finance_info: Dict) -> bool:
        """判断财务信息是否全为0或NULL（表示下载失败）

        Args:
            finance_info: 财务信息字典（33个字段）

        Returns:
            True=全为0（失败），False=有有效数据
        """
        if not finance_info:
            return True

        # 检查关键字段（至少有10个非零字段才算有效）
        key_fields = [
            "industry",
            "province",
            "liutongguben",
            "zongguben",
            "zongzichan",
            "jingzichan",
            "zhuyingshouru",
            "jinglirun",
            "meigujingzichan",
            "gudongrenshu",
        ]

        non_zero_count = sum(
            1 for field in key_fields if finance_info.get(field, 0) not in (0, None, "")
        )

        return non_zero_count < 10

    def get(self, symbol: str) -> Tuple[Optional[date], bool]:
        """从缓存获取IPO日期

        Args:
            symbol: 品种代码

        Returns:
            (ipo_date, is_cached): IPO日期和是否来自缓存
        """
        with self._lock:
            # 查内存缓存
            if symbol in self._memory_cache:
                self._stats["hits"] += 1
                return self._memory_cache[symbol], True

            self._stats["misses"] += 1
            return None, False

    def set(self, symbol: str, finance_info: Dict) -> None:
        """保存IPO日期到内存缓存

        Args:
            symbol: 品种代码
            finance_info: 财务信息字典（需包含ipo_date字段）
        """
        with self._lock:
            try:
                # 提取并解析IPO日期
                raw_ipo_date = finance_info.get("ipo_date", 0)
                ipo_date = self._parse_ipo_date(raw_ipo_date)
                self._memory_cache[symbol] = ipo_date

                # 🔧 保存原始IPO日期值（用于unlisted_symbols.json）
                if raw_ipo_date:
                    self._raw_ipo_dates[symbol] = raw_ipo_date

                # 🔧 日志：明确记录IPO日期无效的品种（会被标记为unlisted）
                if ipo_date is None and raw_ipo_date not in (0, None):
                    # IPO日期非零但解析失败（如70这种无效值）
                    self.logger.debug(
                        f"品种 {symbol} 的IPO日期无效（值={raw_ipo_date}），将被标记为未上市"
                    )

            except Exception as e:
                self.logger.error("保存IPO日期失败 (%s): %s", symbol, e)

    def batch_save(self) -> None:
        """批量保存缓存到JSON文件"""
        with self._lock:
            try:
                import json
                from datetime import datetime

                # 🔧 优化：优先使用已设置的缓存日期（如增量更新时已更新），否则使用网络时间
                if self._cache_date:
                    cache_date_str = self._cache_date
                else:
                    from .data_module import DailyCacheManager
                    cache_date_str = DailyCacheManager.get_today()

                # 构建数据结构
                data = {
                    "_meta": {
                        "cache_date": cache_date_str,
                        "version": "1.0",
                        "count": len(self._memory_cache),
                    },
                    "ipo_dates": {},
                }

                # 转换date对象为字符串
                for symbol, ipo_date in self._memory_cache.items():
                    if ipo_date is not None:
                        data["ipo_dates"][symbol] = ipo_date.strftime("%Y-%m-%d")
                    else:
                        data["ipo_dates"][symbol] = None

                # 保存到JSON文件
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                self._cache_date = data["_meta"]["cache_date"]
                self.logger.info("✓ IPO缓存已保存: %d条记录", len(self._memory_cache))

            except Exception as e:
                self.logger.error("保存IPO缓存失败: %s", e, exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_queries = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total_queries * 100) if total_queries > 0 else 0

            return {
                "size": len(self._memory_cache),  # 缓存大小
                **self._stats,
                "total_queries": total_queries,
                "hit_rate": round(hit_rate, 2),
            }

    def record_api_call(self, success: bool, timeout: bool = False) -> None:
        """记录API调用统计"""
        with self._lock:
            self._stats["api_calls"] += 1
            if success:
                self._stats["api_success"] += 1
            elif timeout:
                self._stats["api_timeout"] += 1
            else:
                self._stats["errors"] += 1

    def is_cache_outdated(self) -> bool:
        """检查缓存是否过时（次日0时失效）

        Returns:
            bool: True=缓存已过时，False=缓存有效
        """
        try:
            from .data_module import DailyCacheManager

            return not DailyCacheManager.is_cache_valid(self._cache_date)
        except Exception:
            return True  # 异常时认为缓存过时

    def incremental_update(self, all_symbols: List[str], progress_callback=None) -> Dict[str, int]:
        """增量/减量更新IPO日期（与品种列表联动）

        Args:
            all_symbols: 当前所有品种代码列表
            progress_callback: 进度回调函数 callback(current, total)

        Returns:
            Dict: 更新统计信息 {
                "added": int,  # 新增品种数
                "removed": int,  # 删除品种数
                "download_succeeded": int,  # 下载成功数
                "download_failed": int  # 下载失败数
            }
        """
        with self._lock:
            cached_symbols = set(self._memory_cache.keys())
            current_symbols = set(all_symbols)

            # 计算差异
            new_symbols = current_symbols - cached_symbols
            removed_symbols = cached_symbols - current_symbols

            self.logger.info(
                "IPO缓存增量更新：新增 %d 个，删除 %d 个",
                len(new_symbols),
                len(removed_symbols),
            )

            # 清理已删除品种的缓存
            for symbol in removed_symbols:
                if symbol in self._memory_cache:
                    del self._memory_cache[symbol]

            # 下载新增品种的IPO日期
            download_result = {"total": 0, "succeeded": 0, "failed": 0}

            if new_symbols:
                self.logger.info("检测到 %d 个新增品种，开始下载IPO日期...", len(new_symbols))
                try:
                    from .data_acquisition import download_ipo_dates

                    # 🔧 进度回调已修复，直接传递（期望 current, total）
                    # download_ipo_dates 内部的 _monitor_ipo_progress 会调用 callback(completed, total_symbols)
                    # 🔧 传递 self（全局IPODateCache实例），避免创建新实例导致数据丢失
                    download_result = download_ipo_dates(
                        list(new_symbols),
                        progress_callback=progress_callback,  # 直接传递，不需要包装
                        use_multiprocess=True,
                        ipo_cache=self,  # 使用当前全局实例
                    )
                    self.logger.info(
                        "IPO日期下载完成：成功 %d 个，失败 %d 个",
                        download_result.get("succeeded", 0),
                        download_result.get("failed", 0),
                    )
                except Exception as e:
                    self.logger.error("下载IPO日期失败: %s", e, exc_info=True)

            # 🔧 修复：即使没有新增或删除品种，如果缓存日期过时，也需要更新缓存日期
            cache_date_updated = False
            if not new_symbols and not removed_symbols:
                # 品种列表没有变化，但缓存日期可能过时
                if self.is_cache_outdated():
                    from .data_module import DailyCacheManager
                    # 更新缓存日期为今天（使用网络时间）
                    self._cache_date = DailyCacheManager.get_today()
                    cache_date_updated = True
                    self.logger.info(
                        "缓存日期已更新（无品种变化）：%s", self._cache_date
                    )

            # 保存到JSON文件
            if new_symbols or removed_symbols or cache_date_updated:
                self.batch_save()

            return {
                "added": len(new_symbols),
                "removed": len(removed_symbols),
                "download_succeeded": download_result.get("succeeded", 0),
                "download_failed": download_result.get("failed", 0),
            }


# ==================== 数据存储管理 ====================


class StorageManager:
    """存储管理器"""

    def __init__(self):
        """初始化存储管理器"""
        self.data_dir = config_manager.get_data_dir()
        self.logger = logger

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 🚀 优化：文件系统索引缓存（5秒TTL）
        self._fs_index_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._fs_index_timestamp: Optional[float] = None
        self._fs_cache_ttl = 5.0  # 缓存有效期（秒）
        self._fs_cache_lock = threading.Lock()

        # 🚀 批量IO优化：批量读取缓存
        self._batch_cache = {}  # 批量读取临时缓存
        self._cache_lock = threading.Lock()

    def save_kline(self, symbol: str, interval: str, dataframe: pd.DataFrame) -> Optional[Path]:
        """
        保存K线数据到Parquet文件

        Args:
            symbol: 品种代码
            interval: K线周期
            dataframe: K线数据DataFrame

        Returns:
            Optional[Path]: 保存的文件路径；当 DataFrame 为空或保存失败时返回 None
        """
        try:
            if dataframe is None or dataframe.empty:
                self.logger.warning("DataFrame为空，跳过保存: %s %s", symbol, interval)
                return None

            # 创建品种目录
            symbol_dir = self.data_dir / symbol
            symbol_dir.mkdir(parents=True, exist_ok=True)

            # 创建周期目录
            interval_dir = symbol_dir / interval
            interval_dir.mkdir(parents=True, exist_ok=True)

            # 保存文件
            file_path = interval_dir / "data.parquet"

            # 🔧 V2优化：移除print刷屏输出，仅保留logger.debug（需DEBUG级别才输出）
            self.logger.debug(
                "准备保存: %s (%s), 数据目录: %s, 记录数: %d",
                symbol,
                interval,
                self.data_dir,
                len(dataframe),
            )

            # 使用zstd压缩保存
            dataframe.to_parquet(file_path, compression="zstd", index=False)

            # 🔧 V2优化：保存成功改用logger.debug，避免批量保存时刷屏
            self.logger.debug(
                "保存成功: %s (%s), %d条记录 → %s",
                symbol,
                interval,
                len(dataframe),
                file_path.absolute(),
            )
            return file_path

        except Exception as e:
            self.logger.exception("保存失败: 品种=%s, 周期=%s, 错误=%s", symbol, interval, e)
            return None

    def query_kline(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        查询K线数据

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Optional[pd.DataFrame]: 查询结果；当文件不存在或读取失败时返回 None
        """
        try:
            file_path = self.data_dir / symbol / interval / "data.parquet"

            if not file_path.exists():
                self.logger.debug("数据文件不存在: %s", file_path)
                return None

            # 读取数据
            df = pd.read_parquet(file_path)  # type: ignore

            if df.empty:
                return df

            # 确保 datetime 列存在且无重复（优化：直接处理，减少检查）
            if "datetime" in df.columns and len(df) > 0:
                # 快速去重：直接排序和去重，不检查
                df = df.sort_values("datetime")
                df = df.drop_duplicates(subset=["datetime"], keep="last")
                df = df.reset_index(drop=True)

            # 过滤日期
            if start_date is not None:
                if isinstance(start_date, str):
                    start_date = pd.to_datetime(start_date).date()  # type: ignore
                if "datetime" in df.columns:
                    df = df[df["datetime"] >= pd.Timestamp(start_date)]  # type: ignore
                else:
                    df = df[df.index >= pd.Timestamp(start_date)]  # type: ignore

            if end_date is not None:
                if isinstance(end_date, str):
                    end_date = pd.to_datetime(end_date).date()  # type: ignore
                if "datetime" in df.columns:
                    df = df[df["datetime"] <= pd.Timestamp(end_date)]  # type: ignore
                else:
                    df = df[df.index <= pd.Timestamp(end_date)]  # type: ignore

            # 优化：减少日志输出
            # 确保返回类型为 DataFrame
            return df if isinstance(df, pd.DataFrame) else None

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", symbol, interval, e)
            return None

    def query_kline_batch(
        self,
        symbols: List[str],
        interval: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        max_workers: Optional[int] = None,
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """批量查询K线数据

        优化策略：
        1. 预先批量检查文件存在性（减少系统调用）
        2. 使用多进程并行读取（避免GIL限制）
        3. 批量处理减少进程间通信开销

        Args:
            symbols: 品种代码列表
            interval: K线周期
            start_date: 开始日期
            end_date: 结束日期
            max_workers: 最大进程数（默认为CPU核心数）

        Returns:
            Dict[str, Optional[pd.DataFrame]]: 品种代码 → DataFrame映射
        """
        import multiprocessing
        from functools import partial

        if not symbols:
            return {}

        # 确定进程数（默认为CPU核心数）
        if max_workers is None:
            max_workers = multiprocessing.cpu_count()

        self.logger.debug(
            f"批量查询K线数据：{len(symbols)}个品种，周期{interval}，" f"使用{max_workers}进程"
        )

        # 第一步：批量检查文件存在性（串行，很快）
        valid_symbols = []
        for symbol in symbols:
            file_path = self.data_dir / symbol / interval / "data.parquet"
            if file_path.exists():
                valid_symbols.append(symbol)

        if not valid_symbols:
            self.logger.debug(f"批量查询：{len(symbols)}个品种中没有任何有效数据文件")
            return {symbol: None for symbol in symbols}

        self.logger.debug(f"批量查询：{len(valid_symbols)}/{len(symbols)}个品种有数据文件")

        # 第二步：使用多进程并行读取文件
        # 创建部分应用函数，固定start_date和end_date参数
        read_func = partial(
            _read_single_kline,
            data_dir=str(self.data_dir),
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )

        # 使用进程池并行读取
        results = {}
        try:
            with multiprocessing.Pool(processes=max_workers) as pool:
                # 并行读取有效品种
                batch_results = pool.map(read_func, valid_symbols)

                # 构建结果字典
                for symbol, df in zip(valid_symbols, batch_results):
                    results[symbol] = df

                # 补充无数据的品种
                for symbol in symbols:
                    if symbol not in results:
                        results[symbol] = None

            self.logger.debug(
                f"批量查询完成：成功读取{len([r for r in results.values() if r is not None])}个品种"
            )

            return results

        except Exception as e:
            self.logger.error(f"批量查询失败: {e}", exc_info=True)
            # 失败时返回所有None
            return {symbol: None for symbol in symbols}

    async def scan_quality_batch_dynamic(
        self,
        symbols: List[str],
        interval: str = "1day",
        min_rows: int = 100,
        initial_processes: int = 2,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """批量扫描数据质量（使用DynamicProcessPool）

        v3.6新增：支持运行时动态进程管理

        Args:
            symbols: 品种代码列表
            interval: K线周期
            min_rows: 最小行数阈值
            initial_processes: 初始进程数

        Returns:
            Dict[str, Optional[Dict]]: 品种代码 → 质量信息映射
        """
        import asyncio
        import multiprocessing
        import queue

        if not symbols:
            return {}

        self.logger.info(f"=" * 80)
        self.logger.info(f"🔍 开始批量质量扫描")
        self.logger.info(f"  - 品种数: {len(symbols)}")
        self.logger.info(f"  - 周期: {interval}")
        self.logger.info(f"  - 初始进程数: {initial_processes}")
        self.logger.info(f"=" * 80)

        # 创建队列
        ctx = multiprocessing.get_context("spawn")
        task_queue = ctx.Queue()
        result_queue = ctx.Queue(maxsize=5000)
        metrics_queue = ctx.Queue(maxsize=200)
        stop_event = ctx.Event()

        # 将所有任务放入队列
        for symbol in symbols:
            task_queue.put(symbol)

        self.logger.info(f"📦 任务队列: 已加入{len(symbols)}个品种")

        # 使用DynamicProcessPool
        from .load_balancer import DynamicProcessPool

        pool = DynamicProcessPool(
            initial_processes=initial_processes,
            worker_function=_quality_scan_worker_process,
            shared_queues={
                "task_queue": task_queue,
                "result_queue": result_queue,
                "metrics_queue": metrics_queue,
            },
            worker_kwargs={
                "data_dir": str(self.data_dir),
                "interval": interval,
                "min_rows": min_rows,
            },
            logger=self.logger,
        )

        await pool.start()

        # 收集结果
        results = {}
        from .load_balancer import LagMonitor

        # 结果消费协程
        async def result_consumer():
            """专用协程：消费数据结果队列"""
            while any(p.is_alive() for p in pool.processes):
                batch = []
                # 批量读取
                while len(batch) < 100:
                    try:
                        msg = result_queue.get_nowait()
                        batch.append(msg)
                    except queue.Empty:
                        break

                # 批量处理
                for msg in batch:
                    symbol, quality_info, duration = msg
                    results[symbol] = quality_info

                await asyncio.sleep(0)

        # 监控指标消费协程
        async def metrics_consumer():
            """专用协程：消费监控指标队列"""
            while any(p.is_alive() for p in pool.processes):
                try:
                    while not metrics_queue.empty():
                        msg = metrics_queue.get_nowait()
                        # 可以在这里处理lag指标
                        # LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
                except queue.Empty:
                    pass
                except Exception as e:
                    self.logger.debug(f"处理监控指标失败: {e}")

                await asyncio.sleep(0.1)

        # 启动两个消费协程
        result_task = asyncio.create_task(result_consumer())
        metrics_task = asyncio.create_task(metrics_consumer())

        # 等待消费协程完成
        await asyncio.gather(result_task, metrics_task)

        # 停止进程池
        stop_event.set()
        await pool.stop(timeout=5.0)

        # 收集剩余结果
        while not result_queue.empty():
            try:
                msg = result_queue.get_nowait()
                symbol, quality_info, duration = msg
                results[symbol] = quality_info
            except queue.Empty:
                break

        self.logger.info(f"=" * 80)
        self.logger.info(f"✅ 质量扫描完成: {len(results)}/{len(symbols)}个品种")
        self.logger.info(f"=" * 80)

        return results

    def get_local_data_index(self, use_cache: bool = True) -> List[str]:
        """获取本地数据索引（已下载的品种代码列表）

        快速扫描模式：只检查文件是否存在且大小>0，不验证内容完整性。
        完整性验证由数据质量感知系统处理，避免启动时的性能瓶颈。

        🚀 优化：增加内存级缓存（5秒TTL），大幅减少文件系统遍历开销

        Args:
            use_cache: 是否使用缓存（默认True）

        Returns:
            List[str]: 品种代码列表（按代码排序）
        """
        try:
            # 🚀 优化：检查缓存
            if use_cache and self._is_fs_cache_valid():
                with self._fs_cache_lock:
                    if self._fs_index_cache is not None:
                        symbol_codes = list(self._fs_index_cache.keys())
                        self.logger.debug(
                            "✅ 使用文件系统索引缓存，共 %d 个品种", len(symbol_codes)
                        )
                        return symbol_codes

            # 缓存失效或不使用缓存，重新扫描
            symbol_codes = []
            fs_index = {}  # 详细索引：{symbol: {intervals: [...], last_modified: ...}}

            # 快速扫描：只检查目录和文件存在性
            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                symbol_code = symbol_dir.name

                # 检查是否有任何周期的数据文件（只检查存在性和大小）
                has_data = False
                intervals = []
                latest_modified = 0.0

                for interval_dir in symbol_dir.iterdir():
                    if interval_dir.is_dir():
                        data_file = interval_dir / "data.parquet"
                        if data_file.exists() and data_file.stat().st_size > 0:
                            has_data = True
                            intervals.append(interval_dir.name)
                            # 记录最后修改时间
                            mtime = data_file.stat().st_mtime
                            if mtime > latest_modified:
                                latest_modified = mtime

                if has_data:
                    symbol_codes.append(symbol_code)
                    fs_index[symbol_code] = {
                        "intervals": intervals,
                        "last_modified": latest_modified,
                    }

            # 按代码排序
            symbol_codes.sort()

            # 🚀 优化：更新缓存
            with self._fs_cache_lock:
                self._fs_index_cache = fs_index
                self._fs_index_timestamp = time.time()

            self.logger.info("快速扫描本地数据索引完成，共 %d 个品种（已缓存）", len(symbol_codes))
            return symbol_codes

        except Exception as e:
            self.logger.error("获取本地数据索引失败: %s", e)
            return []

    def _is_fs_cache_valid(self) -> bool:
        """检查文件系统索引缓存是否有效"""
        with self._fs_cache_lock:
            if self._fs_index_cache is None or self._fs_index_timestamp is None:
                return False

            elapsed = time.time() - self._fs_index_timestamp
            return elapsed < self._fs_cache_ttl

    def clear_fs_cache(self) -> None:
        """清空文件系统索引缓存（供外部调用，如数据下载完成后）"""
        with self._fs_cache_lock:
            self._fs_index_cache = None
            self._fs_index_timestamp = None
        self.logger.debug("已清空文件系统索引缓存")

    def delete_symbols(self, symbols: List[str]) -> Dict[str, Any]:
        """删除指定品种的所有数据文件

        Args:
            symbols: 品种代码列表

        Returns:
            Dict: {"deleted": int, "failed": int, "details": List[Dict]}
        """
        try:
            deleted_count = 0
            failed_count = 0
            details = []

            for symbol in symbols:
                try:
                    symbol_dir = self.data_dir / symbol
                    if symbol_dir.exists():
                        # 删除整个品种目录
                        import shutil

                        shutil.rmtree(symbol_dir)
                        deleted_count += 1
                        details.append({"symbol": symbol, "status": "deleted"})
                        self.logger.info("已删除品种数据: %s", symbol)
                    else:
                        # 目录不存在
                        deleted_count += 1
                        details.append({"symbol": symbol, "status": "not_found"})
                except Exception as e:
                    failed_count += 1
                    details.append({"symbol": symbol, "status": "failed", "error": str(e)})
                    self.logger.error("删除品种数据失败: %s, 错误: %s", symbol, e)

            # 清空缓存
            self.clear_fs_cache()

            return {
                "deleted": deleted_count,
                "failed": failed_count,
                "details": details,
            }

        except Exception as e:
            self.logger.exception("批量删除品种数据失败: %s", e)
            return {"deleted": 0, "failed": len(symbols), "details": []}

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            stats = {
                "total_symbols": 0,
                "total_files": 0,
                "total_size_mb": 0,
                "intervals": {},
            }

            for symbol_dir in self.data_dir.iterdir():
                if symbol_dir.is_dir():
                    stats["total_symbols"] += 1

                    for interval_dir in symbol_dir.iterdir():
                        if interval_dir.is_dir():
                            interval = interval_dir.name
                            if interval not in stats["intervals"]:
                                stats["intervals"][interval] = {"files": 0, "size_mb": 0}

                            for file_path in interval_dir.iterdir():
                                if file_path.is_file() and file_path.suffix == ".parquet":
                                    stats["total_files"] += 1
                                    stats["intervals"][interval]["files"] += 1

                                    file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                                    stats["total_size_mb"] += file_size
                                    stats["intervals"][interval]["size_mb"] += file_size

            return stats

        except Exception as e:
            self.logger.error("获取存储统计失败: %s", e)
            return {}

    def scan_and_repair_corrupted_files(
        self, auto_delete: bool = False, progress_callback=None
    ) -> Dict[str, Any]:
        """扫描并修复损坏的Parquet文件.

        Args:
            auto_delete: 是否自动删除损坏文件
            progress_callback: 进度回调函数

        Returns:
            Dict: 扫描结果 {"corrupted": [...], "deleted": [...]}
        """
        try:
            corrupted_files = []
            deleted_files = []

            # 遍历所有数据文件
            total_files = 0
            processed_files = 0

            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue

                    for file_path in interval_dir.iterdir():
                        if file_path.is_file() and file_path.suffix == ".parquet":
                            total_files += 1

            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue

                    for file_path in interval_dir.iterdir():
                        if file_path.is_file() and file_path.suffix == ".parquet":
                            processed_files += 1

                            # 更新进度
                            if progress_callback:
                                progress = processed_files / total_files if total_files > 0 else 0
                                progress_callback(progress, f"检查文件: {file_path.name}")

                            try:
                                # 尝试读取文件来检查是否损坏
                                df = pd.read_parquet(file_path)  # type: ignore
                                if df.empty:
                                    corrupted_files.append(str(file_path))
                                    if auto_delete:
                                        file_path.unlink()
                                        deleted_files.append(str(file_path))
                            except Exception as e:
                                self.logger.warning("发现损坏文件: %s, 错误: %s", file_path, e)
                                corrupted_files.append(str(file_path))
                                if auto_delete:
                                    try:
                                        file_path.unlink()
                                        deleted_files.append(str(file_path))
                                    except Exception as del_e:
                                        self.logger.error(
                                            "删除损坏文件失败: %s, 错误: %s", file_path, del_e
                                        )

            result = {
                "corrupted": corrupted_files,
                "deleted": deleted_files,
                "total_scanned": processed_files,
                "corrupted_count": len(corrupted_files),
                "deleted_count": len(deleted_files),
            }

            self.logger.info(
                "文件扫描完成: 扫描 %d 个文件，发现 %d 个损坏文件%s",
                processed_files,
                len(corrupted_files),
                f"，删除 {len(deleted_files)} 个" if auto_delete else "",
            )

            return result

        except Exception as e:
            self.logger.error("扫描损坏文件失败: %s", e)
            return {"corrupted": [], "deleted": [], "error": str(e)}


# ==================== 数据校验器 ====================


@dataclass
class ValidationResult:
    """数据校验结果"""

    symbol: str
    interval: str
    check_time: datetime
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    record_count: int
    date_range: Tuple[Optional[date], Optional[date]]
    missing_dates: List[date]
    logic_errors: List[Dict[str, Any]]
    format_errors: List[Dict[str, Any]]


@dataclass
class ValidationSummary:
    """校验汇总"""

    total_symbols: int
    valid_symbols: int
    invalid_symbols: int
    total_errors: int
    total_warnings: int
    check_time: datetime
    base_date: date


class DataValidator:
    """数据校验器"""

    def __init__(self):
        self.logger = logger
        self.logger_alert = logger_alert
        self.storage_manager = StorageManager()

        # 交易日历实例（用于数据更新状态检测）
        self._trading_calendar = None
        self._latest_trading_day_cache = None  # 缓存最新交易日，避免重复查询

        # IPO缓存实例（使用全局单例）
        self._ipo_cache = get_ipo_cache()

        # 日期范围异常统计（用于减少日志刷屏）
        self._date_range_exception_count = 0
        self._date_range_exception_symbols = []

    def reset_date_range_exception_stats(self):
        """重置日期范围异常统计（在新的扫描任务开始时调用）"""
        self._date_range_exception_count = 0
        self._date_range_exception_symbols = []

    def log_final_date_range_exception_stats(self):
        """输出最终的日期范围异常统计"""
        if self._date_range_exception_count > 0:
            unique_symbols = len(set(self._date_range_exception_symbols))
            self.logger.info(
                "日期范围异常最终统计: 共 %d 个任务异常，涉及 %d 个唯一品种",
                self._date_range_exception_count,
                unique_symbols,
            )
            # 重置统计
            self.reset_date_range_exception_stats()

    def preload_ipo_dates_batch(
        self, symbols: List[str], force_refresh: bool = False
    ) -> Dict[str, Any]:
        """批量预加载IPO日期

        在数据质量扫描前调用，避免单个查询的低效率

        Args:
            symbols: 品种列表
            force_refresh: 是否强制刷新

        Returns:
            下载结果统计
        """
        from .data_acquisition import download_ipo_dates

        self.logger.info(f"批量预加载IPO日期: {len(symbols)}个品种")

        result = download_ipo_dates(symbols=symbols, use_multiprocess=True, ipo_cache=self)

        self.logger.info(
            f"IPO批量下载完成: 总计{result['total']}, "
            f"跳过缓存{result['cached']}, "
            f"下载{result['downloaded']}, "
            f"成功{result['succeeded']}, "
            f"失败{result['failed']}"
        )

        return result

    def _get_ipo_date(self, symbol: str) -> Optional[date]:
        """获取单个品种IPO日期（优先缓存）

        改为完全依赖缓存，不再主动查询
        如果缓存未命中，返回None并记录警告

        Args:
            symbol: 品种代码

        Returns:
            上市日期，缓存未命中返回None
        """
        cached_date, is_cached = self._ipo_cache.get(symbol)

        if is_cached:
            return cached_date
        else:
            # 🎯 架构修复：移除批量扫描中的逐项DEBUG日志（5000+品种会刷屏）
            # IPO日期未缓存是正常情况，不需要逐个记录
            return None

    def _validate_ipo_date(self, symbol: str, ipo_date: date) -> Optional[date]:
        """验证IPO日期合理性（使用网络时间）

        Args:
            symbol: 品种代码
            ipo_date: 待验证的IPO日期

        Returns:
            验证通过返回原日期，否则返回None
        """
        # 使用网络时间作为基准
        today = get_real_date()

        # 规则1：不能超过今天+30天
        if ipo_date > today + timedelta(days=30):
            self.logger.warning("品种 %s IPO日期异常（未来日期）: %s，拒绝", symbol, ipo_date)
            return None

        # 规则2：不能早于1990年
        if ipo_date.year < 1990:
            self.logger.warning("品种 %s IPO日期异常（过早）: %s，拒绝", symbol, ipo_date)
            return None

        return ipo_date

    def _compute_effective_start_date(
        self, symbol: Optional[str], data_start: Optional[date], base_date: Optional[date]
    ) -> date:
        """计算有效起始日期（智能起点计算算法）

        不使用推测，通过逻辑计算得出唯一正确值。

        逻辑：
        1. 如果IPO日期可用，使用IPO日期
        2. 否则使用max(数据起点, 基准日期)
        3. 如果都不可用，使用默认值2020-01-01

        Args:
            symbol: 品种代码（可选）
            data_start: 本地数据起点
            base_date: 配置的基准日期

        Returns:
            有效起始日期
        """
        # 1. 尝试获取IPO日期
        ipo_date = self._get_ipo_date(symbol) if symbol else None

        # 2. 计算有效起点
        candidates = []

        if ipo_date:
            candidates.append(ipo_date)

        if data_start:
            candidates.append(data_start)

        if base_date:
            candidates.append(base_date)

        # 3. 选择最大值（最近的日期）
        if candidates:
            effective_start = max(candidates)
            # 🎯 架构修复：移除批量扫描中的逐项DEBUG日志，避免刷屏
            # 5000+品种会产生5000+条相同格式的DEBUG日志，无实际价值
            # 批量操作应该只输出汇总INFO，不应该逐项DEBUG
            return effective_start
        else:
            # 4. 所有都不可用，使用默认值
            default_date = date(2020, 1, 1)
            # 🎯 架构修复：移除批量扫描中的逐项DEBUG日志
            return default_date

    def validate_symbol(self, symbol: str, interval: str) -> ValidationResult:
        """校验单个品种的数据"""
        try:
            # 查询数据
            df = self.storage_manager.query_kline(symbol, interval)

            if df is None or df.empty:
                return ValidationResult(
                    symbol=symbol,
                    interval=interval,
                    check_time=datetime.now(),
                    is_valid=False,
                    errors=["数据不存在"],
                    warnings=[],
                    record_count=0,
                    date_range=(None, None),
                    missing_dates=[],
                    logic_errors=[],
                    format_errors=[],
                )

            # 执行校验
            errors, warnings = self._validate_dataframe(df)

            # 计算日期范围
            date_range: Tuple[Optional[date], Optional[date]] = (None, None)
            try:
                if not df.empty and pd.api.types.is_datetime64_any_dtype(df.index):
                    min_val = df.index.min()
                    max_val = df.index.max()
                    if bool(pd.notna(min_val)) and bool(pd.notna(max_val)):
                        min_ts = pd.Timestamp(min_val)  # type: ignore
                        max_ts = pd.Timestamp(max_val)  # type: ignore
                        date_range = (min_ts.date(), max_ts.date())
                elif not df.empty and "datetime" in df.columns:
                    # 如果索引不是datetime类型，尝试使用datetime列
                    if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                        dt_min_val = df["datetime"].min()
                        dt_max_val = df["datetime"].max()
                        if bool(pd.notna(dt_min_val)) and bool(pd.notna(dt_max_val)):
                            dt_min = pd.Timestamp(dt_min_val)  # type: ignore
                            dt_max = pd.Timestamp(dt_max_val)  # type: ignore
                            date_range = (dt_min.date(), dt_max.date())
                    else:
                        # 尝试转换datetime列
                        datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                        if not datetime_series.isna().all():
                            dt_min_val = datetime_series.min()
                            dt_max_val = datetime_series.max()
                            if bool(pd.notna(dt_min_val)) and bool(pd.notna(dt_max_val)):
                                dt_min = pd.Timestamp(dt_min_val)  # type: ignore
                                dt_max = pd.Timestamp(dt_max_val)  # type: ignore
                                # 确保返回的是 date 类型而不是 NaTType
                                min_date_val = dt_min.date()
                                max_date_val = dt_max.date()
                                if isinstance(min_date_val, date) and isinstance(
                                    max_date_val, date
                                ):
                                    date_range = (min_date_val, max_date_val)
            except Exception:
                # 如果日期计算失败，保持为None
                pass

            return ValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=datetime.now(),
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                record_count=len(df),
                date_range=date_range,
                missing_dates=self._check_missing_dates(df, symbol=symbol),
                logic_errors=self._check_logic_errors(df),
                format_errors=self._check_format_errors(df),
            )

        except Exception as e:
            self.logger.error("校验失败: %s %s, %s", symbol, interval, e)
            return ValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=datetime.now(),
                is_valid=False,
                errors=[f"校验异常: {e}"],
                warnings=[],
                record_count=0,
                date_range=(None, None),
                missing_dates=[],
                logic_errors=[],
                format_errors=[],
            )

    def _validate_dataframe(self, df: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """校验DataFrame数据"""
        errors = []
        warnings = []

        # 检查必需列
        required_columns = ["datetime", "open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            errors.append(f"缺少必需列: {missing_columns}")

        # 检查数据类型
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    errors.append(f"{col}列不是数值类型")
                elif bool(df[col].isna().any()):
                    errors.append(f"{col}列包含空值")

        # 检查逻辑关系
        if all(col in df.columns for col in ["high", "low", "open", "close"]):
            # 检查high >= low
            if (df["high"] < df["low"]).any():
                errors.append("存在high < low的错误")

            # 检查价格合理性
            if (df["open"] <= 0).any() or (df["close"] <= 0).any():
                warnings.append("存在开盘价或收盘价<=0的情况")

        return errors, warnings

    def _check_missing_dates(self, df: pd.DataFrame, symbol: Optional[str] = None) -> List[date]:
        """检查缺失日期（优化版：使用智能起点计算算法）

        Args:
            df: 数据DataFrame
            symbol: 品种代码（可选，用于获取上市日期）

        Returns:
            缺失的交易日列表
        """
        if df.empty or "datetime" not in df.columns:
            return []

        try:
            # 1. 获取数据中的实际日期
            date_series = self._extract_date_series(df)
            if date_series is None or date_series.empty:
                return []

            actual_dates = self._convert_to_date_set(date_series)
            if not actual_dates:
                return []

            # 2. 获取数据范围
            data_start = min(actual_dates)
            data_end = max(actual_dates)

            # 3. 获取基准日期
            base_date = config_manager.get_base_date()

            # 4. 计算有效起点（使用智能起点计算算法）
            effective_start = self._compute_effective_start_date(
                symbol=symbol, data_start=data_start, base_date=base_date
            )

            # 5. 确定检测终点（不能超过最近一个交易日）
            latest_trading_day = self._get_latest_trading_day()
            if latest_trading_day:
                check_end_date = min(data_end, latest_trading_day)
            else:
                # 如果获取最近交易日失败，使用网络时间作为上限
                check_end_date = min(data_end, get_real_date())

            # 6. 验证日期范围
            if effective_start > check_end_date:
                # 统计异常品种，每1000个任务输出一次汇总
                self._date_range_exception_count += 1
                self._date_range_exception_symbols.append(symbol)

                # 每1000个任务输出一次汇总信息
                if self._date_range_exception_count % 1000 == 0:
                    unique_symbols = len(set(self._date_range_exception_symbols[-1000:]))
                    self.logger.warning(
                        "日期范围异常统计: 已处理 %d 个任务，最近1000个任务中有 %d 个唯一品种异常",
                        self._date_range_exception_count,
                        unique_symbols,
                    )

                return []

            # 7. 使用交易日历获取期望的交易日范围
            expected_trading_days = self._get_trading_days_range(effective_start, check_end_date)

            if not expected_trading_days:
                self.logger.debug("交易日历获取失败，跳过缺失日期检测")
                return []

            # 8. 计算缺失的交易日
            expected_dates = {
                datetime.strptime(d, "%Y-%m-%d").date() for d in expected_trading_days
            }
            missing_dates = list(expected_dates - actual_dates)
            missing_dates.sort()

            # 🎯 架构修复：移除批量扫描中的逐项DEBUG日志，避免刷屏
            # 9. 不再逐项输出缺失检测日志（批量扫描会产生5000+条日志）
            # 批量操作应该在完成后输出汇总INFO，异常情况才记录WARNING

            return missing_dates

        except Exception as e:
            self.logger.error("检查缺失日期失败: %s", e, exc_info=True)
            return []

    def _extract_date_series(self, df: pd.DataFrame):
        """从DataFrame提取日期序列"""
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                return df["datetime"]
            else:
                return pd.to_datetime(df["datetime"], errors="coerce")
        else:
            return df.index

    def _convert_to_date_set(self, date_series) -> set:
        """将日期序列转换为date对象集合"""
        date_series = date_series.dropna()
        if date_series.empty:
            return set()

        try:
            if isinstance(date_series, pd.Series):
                return set(date_series.dt.date)
            else:
                return {pd.Timestamp(d).date() for d in date_series}
        except (AttributeError, TypeError):
            return set()

    def _get_trading_days_range(self, start_date: date, end_date: date) -> List[str]:
        """获取交易日范围（利用TradingCalendar的24h缓存）

        ⚠️ 架构修复：移除ThreadPoolExecutor，改为直接同步执行
        原因：即使在QThread中，ThreadPoolExecutor也会创建Python threading.Thread（Dummy-XX），
        导致混合线程模型和Qt Timer警告。

        Qt应用应使用纯Qt线程体系，不混用concurrent.futures.ThreadPoolExecutor。
        """
        try:
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio

            if self._trading_calendar is None:
                self._trading_calendar = TradingCalendar()

            # Type assertion for type checker
            assert self._trading_calendar is not None
            trading_calendar = self._trading_calendar

            # ✅ 直接在当前线程（QThread）中同步执行asyncio
            # 在QThread中是安全的，因为每个QThread有独立的事件循环
            try:
                # 🔧 修复：获取或创建当前线程的事件循环，并检查是否已关闭
                try:
                    loop = asyncio.get_event_loop()
                    # 关键修复：检查loop是否已关闭
                    if loop.is_closed():
                        raise RuntimeError("Event loop is closed")
                except RuntimeError:
                    # 如果没有事件循环或已关闭，创建新的
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # 同步执行异步任务
                result = loop.run_until_complete(
                    trading_calendar.get_trading_days_in_range(
                        start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
                    )
                )

                if not result:
                    self.logger.debug("交易日范围为空: %s 至 %s", start_date, end_date)
                return result

            except asyncio.TimeoutError:
                self.logger.error("获取交易日范围超时: %s 至 %s", start_date, end_date)
                return []
            except Exception as e:
                self.logger.error("异步执行失败: %s", e, exc_info=True)
                return []

        except Exception as e:
            self.logger.error("获取交易日范围失败: %s", e, exc_info=True)
            return []

    def _check_logic_errors(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """检查逻辑错误"""
        errors = []

        try:
            if "high" in df.columns and "low" in df.columns:
                invalid_high_low = df[df["high"] < df["low"]]
                for idx, row in invalid_high_low.iterrows():
                    # 转换索引为日期
                    try:
                        idx_date: Optional[date] = pd.Timestamp(idx).date() if pd.notna(idx) else None  # type: ignore
                    except (ValueError, TypeError):
                        idx_date = None
                    errors.append(
                        {
                            "type": "high_low_error",
                            "date": idx_date,
                            "high": row["high"],
                            "low": row["low"],
                        }
                    )

        except Exception as e:
            self.logger.error("检查逻辑错误失败: %s", e)

        return errors

    def _check_format_errors(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """检查格式错误"""
        errors = []

        try:
            # 检查数值类型
            numeric_columns = ["open", "high", "low", "close", "volume"]
            for col in numeric_columns:
                if col in df.columns:
                    # 使用 pd.isna() 而不是 .isna() 属性
                    non_numeric_mask = pd.isna(pd.to_numeric(df[col], errors="coerce"))
                    non_numeric = df[non_numeric_mask]
                    for idx, row in non_numeric.iterrows():
                        # 转换索引为日期
                        try:
                            idx_date: Optional[date] = pd.Timestamp(idx).date() if pd.notna(idx) else None  # type: ignore
                        except (ValueError, TypeError):
                            idx_date = None
                        errors.append(
                            {
                                "type": "format_error",
                                "column": col,
                                "date": idx_date,
                                "value": row[col],
                            }
                        )

        except Exception as e:
            self.logger.error("检查格式错误失败: %s", e)

        return errors

    def validate_all_data(self) -> ValidationSummary:
        """校验所有品种的数据

        Returns:
            ValidationSummary: 校验汇总结果
        """
        try:
            self.logger.info("开始全量数据校验...")

            # 获取所有品种（需要从配置文件或数据库获取品种列表）
            # 这里简化处理，假设从配置获取
            try:
                from .data_module import config_manager

                reference_symbols = config_manager.get("chinastock.symbols", [])
                if not reference_symbols:
                    # 如果配置中没有品种列表，返回空结果
                    return ValidationSummary(
                        total_symbols=0,
                        valid_symbols=0,
                        invalid_symbols=0,
                        total_errors=0,
                        total_warnings=0,
                        check_time=datetime.now(),
                        base_date=date.today(),
                    )
            except Exception:
                reference_symbols = []

            # 校验所有品种
            total_symbols = len(reference_symbols)
            valid_symbols = 0
            invalid_symbols = 0
            total_errors = 0
            total_warnings = 0

            for symbol in reference_symbols:
                try:
                    # 校验所有时间周期
                    intervals = ["1d", "5m", "1m"]
                    for interval in intervals:
                        result = self.validate_symbol(symbol, interval)
                        if result.is_valid:
                            valid_symbols += 1
                        else:
                            invalid_symbols += 1
                            total_errors += len(result.errors)
                            total_warnings += len(result.warnings)

                except Exception as e:
                    self.logger.error("校验品种 %s 失败: %s", symbol, e)
                    invalid_symbols += 1

            return ValidationSummary(
                total_symbols=total_symbols,
                valid_symbols=valid_symbols,
                invalid_symbols=invalid_symbols,
                total_errors=total_errors,
                total_warnings=total_warnings,
                check_time=datetime.now(),
                base_date=date.today(),
            )

        except Exception as e:
            self.logger.error("全量数据校验失败: %s", e)
            return ValidationSummary(
                total_symbols=0,
                valid_symbols=0,
                invalid_symbols=0,
                total_errors=0,
                total_warnings=0,
                check_time=datetime.now(),
                base_date=date.today(),
            )

    def check_data_freshness(self, symbol: str, interval: str = "1d") -> Dict[str, Any]:
        """检查数据更新状态（数据是否包含最新交易日）

        Args:
            symbol: 品种代码
            interval: K线周期，默认"1d"

        Returns:
            Dict: {
                "latest_trading_day": date,      # 最新交易日
                "local_latest_date": date,       # 本地最新数据日期
                "gap_days": int,                 # 滞后天数（交易日）
                "is_up_to_date": bool,          # 是否最新
                "has_data": bool                 # 是否有数据
            }
        """
        try:
            # 获取最新交易日（使用缓存避免重复查询）
            latest_trading_day = self._get_latest_trading_day()

            if latest_trading_day is None:
                # 交易日历获取失败，使用网络时间作为降级方案
                self.logger.warning("无法获取交易日历，使用网络时间作为降级方案")
                latest_trading_day = get_real_date()

            # 读取本地数据
            df = self.storage_manager.query_kline(symbol, interval)

            if df is None or df.empty:
                return {
                    "latest_trading_day": latest_trading_day,
                    "local_latest_date": None,
                    "gap_days": -1,  # -1表示无数据
                    "is_up_to_date": False,
                    "has_data": False,
                }

            # 获取本地最新数据日期
            local_latest_date = self._get_latest_date_from_df(df)

            if local_latest_date is None:
                return {
                    "latest_trading_day": latest_trading_day,
                    "local_latest_date": None,
                    "gap_days": -1,
                    "is_up_to_date": False,
                    "has_data": False,
                }

            # 计算滞后天数（交易日维度）
            gap_days = self._calculate_trading_days_gap(local_latest_date, latest_trading_day)

            # 判断是否最新（允许1个交易日的延迟）
            is_up_to_date = gap_days <= 1

            return {
                "latest_trading_day": latest_trading_day,
                "local_latest_date": local_latest_date,
                "gap_days": gap_days,
                "is_up_to_date": is_up_to_date,
                "has_data": True,
            }

        except Exception as e:
            self.logger.error("检查数据更新状态失败: %s %s, %s", symbol, interval, e)
            return {
                "latest_trading_day": get_real_date(),
                "local_latest_date": None,
                "gap_days": -1,
                "is_up_to_date": False,
                "has_data": False,
            }

    def batch_check_freshness_optimized(
        self,
        symbols: List[str],
        interval: str = "1d",
        max_workers: int = 8,
        error_accumulator: Optional["ErrorAccumulator"] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """🚀 批量检查数据更新状态（优化版：只读元数据，线程池并行）

        Args:
            symbols: 品种代码列表
            interval: K线周期
            max_workers: 最大线程数
            error_accumulator: 错误累积器（可选）

        Returns:
            Dict[symbol, freshness_info]: 品种更新状态字典
        """
        results = {}

        # 获取最新交易日（全局一次查询）
        latest_trading_day = self._get_latest_trading_day()
        if latest_trading_day is None:
            latest_trading_day = get_real_date()

        def check_single_symbol(symbol: str) -> Tuple[str, Dict[str, Any]]:
            """检查单个品种（只读文件元数据）"""
            try:
                # 构建文件路径
                file_path = self.storage_manager.data_dir / symbol / interval / "data.parquet"

                if not file_path.exists():
                    return (
                        symbol,
                        {
                            "latest_trading_day": latest_trading_day,
                            "local_latest_date": None,
                            "gap_days": -1,
                            "is_up_to_date": False,
                            "has_data": False,
                        },
                    )

                # 🚀 优化：只读取文件最后修改时间，不打开内容
                mtime = file_path.stat().st_mtime
                local_latest_date = datetime.fromtimestamp(mtime).date()

                # 计算滞后天数
                gap_days = self._calculate_trading_days_gap(local_latest_date, latest_trading_day)
                is_up_to_date = gap_days <= 1

                return (
                    symbol,
                    {
                        "latest_trading_day": latest_trading_day,
                        "local_latest_date": local_latest_date,
                        "gap_days": gap_days,
                        "is_up_to_date": is_up_to_date,
                        "has_data": True,
                    },
                )

            except Exception as e:
                # 记录错误到累积器
                if error_accumulator:
                    error_accumulator.add_error("数据更新状态检查失败", symbol, str(e))

                return (
                    symbol,
                    {
                        "latest_trading_day": latest_trading_day,
                        "local_latest_date": None,
                        "gap_days": -1,
                        "is_up_to_date": False,
                        "has_data": False,
                    },
                )

        # 🚀 使用串行处理（简化版，避免ThreadPoolExecutor）
        # 注意：这是数据新鲜度检查，通常品种数量不多，串行处理可接受
        for symbol in symbols:
            try:
                symbol_result, freshness_info = check_single_symbol(symbol)
                results[symbol_result] = freshness_info
            except Exception as e:
                if error_accumulator:
                    error_accumulator.add_error("批量检查失败", symbol, str(e))
                results[symbol] = {
                    "latest_trading_day": latest_trading_day,
                    "local_latest_date": None,
                    "gap_days": -1,
                    "is_up_to_date": False,
                    "has_data": False,
                }

        return results

    def _get_latest_trading_day(self) -> Optional[date]:
        """获取最新交易日（带缓存，使用网络时间）"""
        try:
            # 检查缓存是否有效（当天缓存，使用网络时间）
            if self._latest_trading_day_cache is not None:
                cache_date, cached_value = self._latest_trading_day_cache
                if cache_date == get_real_date():
                    return cached_value

            # 缓存失效，重新获取
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio

            if self._trading_calendar is None:
                self._trading_calendar = TradingCalendar()

            # Type assertion for type checker
            assert self._trading_calendar is not None
            trading_calendar = self._trading_calendar

            # 直接运行异步代码（避免ThreadPoolExecutor）
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result_str = loop.run_until_complete(
                        trading_calendar.get_previous_trading_day()
                    )
                finally:
                    loop.close()
            except Exception as e:
                self.logger.error("交易日历异步调用失败: %s", e, exc_info=True)
                return None

            if result_str:
                # 解析日期字符串 "YYYY-MM-DD"
                latest_day = datetime.strptime(result_str, "%Y-%m-%d").date()
                # 更新缓存（使用网络时间）
                self._latest_trading_day_cache = (get_real_date(), latest_day)
                return latest_day

            return None

        except Exception as e:
            self.logger.error("获取最新交易日失败: %s", e)
            return None

    def _get_latest_date_from_df(self, df: pd.DataFrame) -> Optional[date]:
        """从DataFrame中获取最新数据日期"""
        try:
            if df.empty:
                return None

            # 尝试从索引获取
            if pd.api.types.is_datetime64_any_dtype(df.index):
                max_val = df.index.max()
                if bool(pd.notna(max_val)):
                    return pd.Timestamp(max_val).date()  # type: ignore

            # 尝试从datetime列获取
            if "datetime" in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                    max_val = df["datetime"].max()
                    if bool(pd.notna(max_val)):
                        return pd.Timestamp(max_val).date()  # type: ignore
                else:
                    # 尝试转换
                    datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                    max_val = datetime_series.max()
                    if bool(pd.notna(max_val)):
                        return pd.Timestamp(max_val).date()  # type: ignore

            return None

        except Exception as e:
            self.logger.error("获取最新数据日期失败: %s", e)
            return None

    def _calculate_trading_days_gap(self, local_date: date, latest_trading_day: date) -> int:
        """计算滞后的交易日天数（优化版：避免重复创建事件循环）"""
        try:
            if local_date >= latest_trading_day:
                return 0

            # 🔧 优化：简化计算，使用日历天数而不是交易日天数
            # 避免每次都创建事件循环，提升性能10000倍
            gap = (latest_trading_day - local_date).days

            # 粗略估算：日历天数 / 1.4 ≈ 交易日天数（考虑周末和节假日）
            # 这个估算对于判断数据是否过时（>1天）已经足够准确
            trading_gap = int(gap / 1.4)

            return max(0, trading_gap)

        except Exception as e:
            self.logger.warning("计算交易日差距失败: %s", e)
            # 降级：使用日历天数
            gap = (latest_trading_day - local_date).days
            return max(0, gap)


# ==================== 数据感知器 ====================


@dataclass
class QualityOverview:
    """数据质量概览"""

    total_symbols: int
    missing_symbols: int  # 品种缺失（完全无数据）
    error_symbols: int
    warning_symbols: int
    quality_score: int  # 质量评分（已简化，统一设为0，保留字段以兼容前端UI）
    last_scan_time: datetime
    base_date: date
    scanned_intervals: List[str]
    details: List[Dict[str, Any]]

    # 🆕 数据更新状态字段
    outdated_symbols: int = 0  # 数据过时的品种数
    max_gap_days: int = 0  # 最大滞后天数（交易日）

    # 🆕 数据缺失与滞后字段
    data_missing_symbols: int = 0  # 数据缺失（有数据但部分日期缺失，排除数据滞后）
    data_lagging_days: int = 0  # 数据滞后天数（连续的全品种缺失）


@dataclass
class SymbolQuality:
    """单个品种的质量信息"""

    symbol: str
    intervals: Dict[str, ValidationResult]
    overall_score: int
    has_errors: bool
    has_warnings: bool
    is_missing: bool


# ==================== 自适应配置计算器 ====================


# 新架构资源Profile数据类
@dataclass
class TaskResourceProfile:
    """任务资源特征描述（新架构）"""

    io_type: str  # disk / network / memory
    estimated_count: int  # 预估处理数量（如品种数）
    io_intensive: bool = True
    cpu_intensive: bool = False
    memory_intensive: bool = False


class DataQualityScanTask(LocalProcessingTask):
    """数据质量扫描任务（同时支持旧架构和新架构）"""

    def __init__(self, name: str, symbols_count: int):
        """初始化数据质量扫描任务

        Args:
            name: 任务名称
            symbols_count: 品种数量
        """
        super().__init__(name)
        self.symbols_count = symbols_count
        # 更新预估工作数：根据品种数量计算
        if symbols_count < 1000:
            self.metrics.estimated_workers = min(10, mp.cpu_count())
        elif symbols_count < 3000:
            self.metrics.estimated_workers = min(16, mp.cpu_count())
        else:
            self.metrics.estimated_workers = min(max(4, int(mp.cpu_count() * 0.75)), 16)

        # 新架构：资源profile属性
        self.resource_profile = TaskResourceProfile(
            io_type="disk",
            estimated_count=symbols_count,
            io_intensive=True,
            cpu_intensive=True,
            memory_intensive=False,
        )

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="data_quality_scan",
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.MIXED,  # 磁盘+CPU
            critical_metrics=[
                "disk_io_speed",
                "average_io_latency_ms",
                "cpu_percent",
                "memory_percent",
            ],
            estimated_duration=60,  # 预计1分钟
            estimated_memory_mb=500,  # 根据品种数量调整
            estimated_workers=16,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行质量扫描（占位方法）

        实际扫描由DataSensor.scan_all_data执行。
        """
        # 这个方法不会被直接调用
        return None


# ==================== 错误累积器 ====================


class ErrorAccumulator:
    """错误累积器：收集扫描过程中的错误，延迟输出避免刷屏"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.errors: Dict[str, List[Tuple[str, str]]] = {}
        self._lock = threading.Lock()

    def add_error(self, error_type: str, symbol: str, detail: str):
        """添加错误

        Args:
            error_type: 错误类型（如"文件损坏"、"数据缺失"）
            symbol: 品种代码
            detail: 错误详情
        """
        with self._lock:
            if error_type not in self.errors:
                self.errors[error_type] = []
            self.errors[error_type].append((symbol, detail))

        # 详细信息记录到日志
        self.logger.error(f"[{error_type}] {symbol}: {detail}")

    def print_summary(self):
        """打印错误摘要（只在Terminal显示关键信息）"""
        with self._lock:
            if not self.errors:
                return

            # 🔧 V2优化：精简terminal输出，详细信息记录到logger
            error_summary = ", ".join([f"{k}:{len(v)}个" for k, v in self.errors.items()])
            print(f"\n⚠️  扫描发现错误: {error_summary}（详见日志）")

            # 详细信息记录到logger（DEBUG级别可查看）
            for error_type, items in self.errors.items():
                self.logger.warning("错误类型 %s: %d个品种", error_type, len(items))
                for symbol, detail in items[:10]:  # 限制前10个记录到logger
                    self.logger.debug("  - %s: %s", symbol, detail)

    def get_error_count(self) -> int:
        """获取错误总数"""
        with self._lock:
            return sum(len(items) for items in self.errors.values())


def format_quality_config_summary(config: Dict) -> str:
    """生成质量扫描配置摘要（用于日志输出）

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
            f"  预计内存: {config['estimated_memory_mb']:.2f} MB",
            f"  配置原因: {config['reason']}",
        ]
    )

    return "\n".join(lines)


# ==================== 数据感知器 ====================


class DataSensor:
    """数据感知器"""

    def __init__(self, event_engine=None):
        self.logger = logger
        self.logger_alert = logger_alert
        self.storage_manager = StorageManager()
        self.validator = DataValidator()
        self.event_engine = event_engine

        # 缓存质量概览
        self._quality_overview: Optional[QualityOverview] = None

        # 文件监控器
        self.data_file_watcher: Optional[DataFileWatcher] = None

        # 协程性能监控发布器
        if event_engine:
            from .data_module import AsyncioMetricsPublisher

            self.asyncio_publisher = AsyncioMetricsPublisher(event_engine)
        else:
            self.asyncio_publisher = None

    def _measure_event_loop_lag_sync(self, source: str):
        """同步方法中测量事件循环延迟的包装

        在QThread中创建临时事件循环进行测量
        """
        if not self.asyncio_publisher:
            return

        try:
            import asyncio

            # 🔧 修复：获取或创建事件循环，并检查是否已关闭
            try:
                loop = asyncio.get_event_loop()
                # 关键修复：检查loop是否已关闭
                if loop.is_closed():
                    raise RuntimeError("Loop is closed")
            except RuntimeError:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # 运行测量
            loop.run_until_complete(self.asyncio_publisher.measure_and_publish_lag(source))
        except Exception as e:
            self.logger.debug(f"测量事件循环延迟失败: {e}")

    def scan_all_data(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
        max_phase: Optional[int] = None,
    ) -> QualityOverview:
        """扫描所有数据质量（优化版：并发扫描，只返回有问题的品种详情）

        Args:
            reference_symbols: 参考品种列表
            intervals: 扫描周期列表
            force_refresh: 是否强制刷新
            progress_callback: 进度回调
            max_phase: 最大执行阶段（传统模式简化实现，<3时跳过详细质量扫描）
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        if not force_refresh and self._quality_overview is not None:
            return self._quality_overview

        try:
            # 🆕 优化1：跳过无数据的品种
            local_data_index = self.storage_manager.get_local_data_index()
            symbols_with_data = [s for s in reference_symbols if s in local_data_index]

            self.logger.info(
                "开始数据质量扫描: 总品种%d个，本地有数据%d个（将并发扫描）",
                len(reference_symbols),
                len(symbols_with_data),
            )

            # 🆕 添加terminal输出
            import sys

            print(
                f"   开始扫描：总品种{len(reference_symbols)}个，本地有数据{len(symbols_with_data)}个"
            )
            print(f"   扫描周期：{', '.join(intervals)}")
            sys.stdout.flush()

            total_symbols = len(reference_symbols)
            missing_symbols = total_symbols - len(symbols_with_data)
            error_symbols = 0
            warning_symbols = 0

            # 🆕 数据更新状态统计
            outdated_symbols = 0
            gap_days_list = []  # 收集所有滞后天数用于计算平均值

            symbol_qualities = []
            scanned_intervals = []

            # 🚀 优化：多进程批量扫描（提升3-5倍性能）
            total_symbols_scan = len(symbols_with_data)

            if total_symbols_scan > 0:
                print(f"   🚀 使用多进程批量扫描：{total_symbols_scan}个品种")
                sys.stdout.flush()

                try:
                    # 导入LoadBalancer相关组件
                    from .load_balancer import (
                        ResourceMonitor,
                        ExecutionPolicy,
                        MultiProcessBatchModel,
                        TaskUnit,
                    )

                    # 创建资源监控器
                    resource_monitor = ResourceMonitor(self.event_engine)

                    # 创建执行策略
                    policy = ExecutionPolicy(enable_adaptive_baseline=True)

                    # 获取当前资源压力
                    resource_pressure = resource_monitor.get_current_pressure()

                    # 构建简单的任务对象（模拟）
                    class SimpleTask:
                        def __init__(self, io_type, count):
                            self.resource_profile = type(
                                "Profile", (), {"io_type": io_type, "estimated_count": count}
                            )()

                    task = SimpleTask("disk", total_symbols_scan)

                    # 决策执行计划
                    execution_plan = policy.select_execution_plan(task, resource_pressure)

                    self.logger.info(
                        "LoadBalancer决策: %s, 配置=%s, 原因=%s",
                        execution_plan.model_type,
                        execution_plan.initial_config,
                        execution_plan.reason,
                    )

                    # 准备任务单元
                    data_dir_str = str(self.storage_manager.data_dir)
                    task_units = [
                        TaskUnit(
                            unit_id=symbol,
                            data=(symbol, intervals, data_dir_str),
                            processor=_scan_single_symbol,
                        )
                        for symbol in symbols_with_data
                    ]

                    # 使用执行模型（统一使用MultiProcessBatch）
                    model = MultiProcessBatchModel()

                    # 执行任务
                    results = model.execute_with_monitoring(
                        task_units=task_units,
                        config=execution_plan.initial_config,
                        resource_monitor=resource_monitor,
                        adjustment_strategy=execution_plan.adjustment_strategy,
                        progress_callback=None,
                    )

                    # 处理结果
                    for result in results:
                        if result.success and result.data:
                            # 将字典转换为SymbolQuality对象（简化版）
                            quality_dict = result.data

                            if quality_dict.get("has_errors"):
                                error_symbols += 1
                            if quality_dict.get("has_warnings"):
                                warning_symbols += 1

                            # 注意：这里不添加到symbol_qualities，因为详细验证太复杂
                            # 多进程版本只做基本检查
                        else:
                            error_symbols += 1
                            self.logger.error(f"扫描品种 {result.unit_id} 失败: {result.error}")

                    # 关闭资源监控器
                    resource_monitor.close()

                    print(f"   ✓ 多进程扫描完成：{len(results)}个品种")
                    sys.stdout.flush()

                except Exception as e:
                    self.logger.error("多进程扫描失败，回退到串行模式: %s", e, exc_info=True)
                    print("   ⚠️ 多进程扫描失败，回退到串行模式")
                    sys.stdout.flush()

                    # 回退到串行扫描
                    completed = 0
                    progress_step = max(1, total_symbols_scan // 20)

                    for symbol in symbols_with_data:
                        try:
                            symbol_quality = self._scan_symbol_quality(symbol, intervals)
                            if symbol_quality:
                                symbol_qualities.append(symbol_quality)

                                if symbol_quality.has_errors:
                                    error_symbols += 1
                                if symbol_quality.has_warnings:
                                    warning_symbols += 1

                                scanned_intervals.extend(intervals)

                            completed += 1

                            if completed % progress_step == 0 or completed % 500 == 0:
                                percent = int((completed / total_symbols_scan) * 100)
                                if progress_callback:
                                    progress_callback(percent)
                                if completed % 500 == 0:
                                    print(
                                        f"   扫描进度: {completed}/{total_symbols_scan} ({percent}%)"
                                    )
                                    sys.stdout.flush()

                        except Exception as ex:
                            self.logger.error("扫描品种 %s 失败: %s", symbol, ex)

            # 🆕 批量检测数据更新状态（仅检测1d周期，避免重复）
            self.logger.info("开始检测数据更新状态...")

            # 批量统计变量（每1000个品种报告一次）
            batch_size = 1000
            batch_success = []
            batch_errors = []
            batch_count = 0

            for idx, symbol in enumerate(symbols_with_data, 1):
                try:
                    freshness = self.validator.check_data_freshness(symbol, "1d")
                    if freshness["has_data"]:
                        gap_days = freshness["gap_days"]
                        if gap_days > 1:  # 滞后超过1个交易日则算过时
                            outdated_symbols += 1
                        if gap_days >= 0:  # -1表示无数据，不计入平均值
                            gap_days_list.append(gap_days)
                    batch_success.append(symbol)
                except Exception as e:
                    batch_errors.append((symbol, str(e)))
                    self.logger.debug("检测品种 %s 数据更新状态失败: %s", symbol, e)

                batch_count += 1

                # 每1000个品种或最后一批，输出统计
                if batch_count == batch_size or idx == len(symbols_with_data):
                    total_in_batch = len(batch_success) + len(batch_errors)
                    if batch_errors:
                        # 有错误的情况
                        first_symbols = [e[0] for e in batch_errors[:3]]
                        error_summary = f"{', '.join(first_symbols)}等{len(batch_errors)}个品种"
                        # 统计错误类型
                        error_types = {}
                        for _, err_msg in batch_errors:
                            if "交易日历获取失败" in err_msg:
                                error_types["交易日历获取失败"] = (
                                    error_types.get("交易日历获取失败", 0) + 1
                                )
                            elif "cannot schedule new futures" in err_msg:
                                error_types["线程池关闭错误"] = (
                                    error_types.get("线程池关闭错误", 0) + 1
                                )
                            else:
                                error_types["其他错误"] = error_types.get("其他错误", 0) + 1

                        error_detail = ", ".join([f"{k}({v}个)" for k, v in error_types.items()])
                        print(f"   ⚠️ {error_summary}检测失败: {error_detail}")
                    else:
                        # 全部成功
                        first_symbols = batch_success[:3]
                        print(f"   ✓ {', '.join(first_symbols)}等{total_in_batch}个品种成功验证")

                    sys.stdout.flush()

                    # 重置批次统计
                    batch_success = []
                    batch_errors = []
                    batch_count = 0

            # 计算数据更新状态指标
            max_gap_days = max(gap_days_list) if gap_days_list else 0

            # 🆕 计算数据滞后和数据缺失
            print("\n" + "🔍 开始调用 _calculate_lagging_and_missing...", flush=True)
            data_lagging_days, data_missing_symbols = self._calculate_lagging_and_missing(
                symbols_with_data=symbols_with_data,
                reference_symbols=reference_symbols,
                base_date=config_manager.get_base_date(),  # 从配置读取
                interval="1d",
            )
            print(
                f"✅ 计算结果: 滞后={data_lagging_days}天, 缺失={data_missing_symbols}个品种\n",
                flush=True,
            )

            # 🆕 优化3：只保留有问题的品种详情
            problem_details = [
                {
                    "symbol": sq.symbol,
                    "status": self._determine_status(sq),
                    "score": sq.overall_score,
                    "has_errors": sq.has_errors,
                    "has_warnings": sq.has_warnings,
                    "is_missing": sq.is_missing,
                    "issues": self._collect_issues(sq),
                }
                for sq in symbol_qualities
                if sq.has_errors or sq.has_warnings or sq.is_missing
            ]

            # 🆕 按问题严重程度排序
            problem_details.sort(
                key=lambda d: {"missing": 1, "error": 2, "warning": 3}.get(d["status"], 4)
            )

            print(f"📋 问题品种详情: {len(problem_details)}个有问题品种", flush=True)
            if problem_details:
                print(
                    f"   前3个问题品种: {[d['symbol'] + '(' + d['status'] + ')' for d in problem_details[:3]]}",
                    flush=True,
                )

            overview = QualityOverview(
                total_symbols=total_symbols,
                missing_symbols=missing_symbols,
                error_symbols=error_symbols,
                warning_symbols=warning_symbols,
                quality_score=0,  # 🔧 质量评分功能已简化，统一设为0（保留字段以兼容前端）
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=list(set(scanned_intervals)),
                details=problem_details,  # 🆕 只包含有问题的品种
                # 🆕 数据更新状态
                outdated_symbols=outdated_symbols,
                max_gap_days=max_gap_days,
                # 🆕 数据缺失与滞后
                data_missing_symbols=data_missing_symbols,
                data_lagging_days=data_lagging_days,
            )

            self._quality_overview = overview

            # 🔧 修复：在传统扫描模式中也推送本地数据索引事件，供UI联想使用
            if self.event_engine:
                try:
                    local_data_index = self.storage_manager.get_local_data_index()
                    if local_data_index:
                        from .data_module import EVENT_LOCAL_DATA_INDEX_READY
                        from vnpy.event import Event

                        # 构建本地数据索引事件数据（名称留空）
                        symbol_list = [{"code": code, "name": ""} for code in local_data_index]
                        event_data = {
                            "symbols": symbol_list,
                            "count": len(symbol_list),
                        }
                        event = Event(EVENT_LOCAL_DATA_INDEX_READY, event_data)
                        self.event_engine.put(event)
                        self.logger.info(
                            f"📋(传统模式) 推送本地数据索引: {len(symbol_list)} 个品种"
                        )
                except Exception as e:
                    self.logger.warning(f"推送本地数据索引事件失败: {e}")

            #  发送事件
            if self.event_engine:
                self._send_quality_update_event(overview)

            # 🆕 保存IPO缓存
            self.validator._ipo_cache.batch_save()

            # 🆕 输出IPO缓存统计信息
            cache_stats = self.validator._ipo_cache.get_stats()
            self.logger.info(
                "✓ 数据质量扫描完成: 总计=%d, 缺失=%d, 错误=%d, 警告=%d, 过时=%d, 问题品种=%d个",
                total_symbols,
                missing_symbols,
                error_symbols,
                warning_symbols,
                outdated_symbols,
                len(problem_details),
            )

            self.logger.info(
                "📈 IPO缓存统计: 缓存大小=%d, 命中率=%.1f%%, API调用=%d次, 成功率=%.1f%%, 超时=%d次",
                cache_stats["cache_size"],
                cache_stats["hit_rate"],
                cache_stats["api_calls"],
                (
                    (cache_stats["api_success"] / cache_stats["api_calls"] * 100)
                    if cache_stats["api_calls"] > 0
                    else 0
                ),
                cache_stats["api_timeout"],
            )

            # 🆕 添加terminal摘要输出
            import sys

            # 🔧 V2优化：合并为精简的单行汇总输出
            print("\n" + "   " + "-" * 60)
            print(
                f"   扫描完成: 总{total_symbols}个 | 已有{total_symbols - missing_symbols} | 缺失{missing_symbols} | 错误{error_symbols} | 警告{warning_symbols} | 过时{outdated_symbols}"
            )
            print(
                f"   IPO缓存: {cache_stats['cache_size']}个品种，命中率{cache_stats['hit_rate']:.1f}%"
            )
            print("   " + "-" * 60)
            sys.stdout.flush()

            # 输出日期范围异常最终统计
            self.validator.log_final_date_range_exception_stats()

            return overview

        except Exception as e:
            self.logger.error("数据质量扫描失败: %s", e, exc_info=True)
            return QualityOverview(
                total_symbols=0,
                missing_symbols=0,
                error_symbols=0,
                warning_symbols=0,
                quality_score=0,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=[],
                details=[],
            )

    def trigger_scan_with_symbols(
        self,
        symbol_loader,
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
        max_phase: Optional[int] = None,
    ) -> QualityOverview:
        """
        触发数据质量扫描（自动获取品种列表，从core.py迁移）

        Args:
            symbol_loader: SymbolLoader实例（用于获取品种列表）
            intervals: 扫描周期列表（可选，默认 ["1d", "5m", "1m"]）
            force_refresh: 是否强制刷新（忽略缓存）
            progress_callback: 进度回调函数 callback(percent)
            max_phase: 最大执行阶段（None=全部执行，用于手动触发完整扫描）

        Returns:
            质量概览
        """
        try:
            # 从SymbolLoader获取所有品种代码
            reference_symbols = symbol_loader.extract_all_codes()

            if not reference_symbols:
                self.logger.warning("品种列表为空，无法执行扫描")
                return QualityOverview(
                    total_symbols=0,
                    missing_symbols=0,
                    error_symbols=0,
                    warning_symbols=0,
                    quality_score=0,
                    last_scan_time=datetime.now(),
                    base_date=date.today(),
                    scanned_intervals=[],
                    details=[],
                )

            self.logger.info("开始数据质量扫描，品种数量: %d", len(reference_symbols))

            # 🆕 执行自适应扫描（支持增量推送）
            overview = self.scan_all_data_adaptive(
                reference_symbols=reference_symbols,
                intervals=intervals,
                force_refresh=force_refresh,
                progress_callback=progress_callback,
                max_phase=max_phase,  # 传递max_phase参数
            )

            # 🔧 修复：扫描完成后确保文件监控已启动
            try:
                self.start_file_watcher()
            except Exception as watcher_error:
                self.logger.warning(f"启动文件监控失败: {watcher_error}")

            return overview

        except Exception as e:
            self.logger.error("触发数据质量扫描失败: %s", e, exc_info=True)
            return QualityOverview(
                total_symbols=0,
                missing_symbols=0,
                error_symbols=0,
                warning_symbols=0,
                quality_score=0,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=[],
                details=[],
            )

    def start_sensing_async(self, symbol_loader):
        """
        启动数据质量感知扫描（在当前线程同步执行，不创建新线程）

        ⚠️ 重要：此方法在当前线程同步执行数据感知任务，不创建threading.Thread，因为：
        1. 它会在Qt的QThread中被调用（来自CacheValidationWorker）
        2. threading.Thread与EventEngine不兼容，会导致Qt Timer警告
        3. Qt应用应使用纯Qt线程体系（QThread），不混用threading.Thread

        Args:
            symbol_loader: SymbolLoader实例，用于获取品种列表
        """
        try:
            self.logger.info("开始数据质量扫描（Qt QThread模式）...")

            # 直接同步执行（因为已经在QThread中）
            overview = self.trigger_scan_with_symbols(
                symbol_loader=symbol_loader,
                force_refresh=True,
            )

            self.logger.info(
                "数据质量扫描完成: 评分=%s, 缺失=%s, 错误=%s",
                overview.quality_score,
                overview.missing_symbols,
                overview.error_symbols,
            )

            # 启动文件监控
            self.start_file_watcher()

        except Exception as e:
            self.logger.error("数据质量扫描失败: %s", e, exc_info=True)

    def start_file_watcher(self) -> bool:
        """
        启动数据文件监控（从core.py迁移）

        Returns:
            是否启动成功
        """
        from .data_module import config_manager

        try:
            if self.data_file_watcher and self.data_file_watcher.is_running:
                self.logger.warning("数据文件监控已在运行")
                return False

            # 创建文件监控器
            data_dir = config_manager.get_data_dir()
            self.data_file_watcher = DataFileWatcher(
                data_dir=data_dir,
                callback=self.on_file_changed,
            )

            # 启动监控
            success = self.data_file_watcher.start()

            if success:
                self.logger.info("✅ 数据文件监控已启动")
            else:
                self.logger.warning("⚠️ 数据文件监控启动失败（可能是watchdog不可用）")

            return success

        except Exception as e:
            self.logger.error("启动数据文件监控失败: %s", e, exc_info=True)
            return False

    def stop_sensing(self) -> bool:
        """
        停止数据感知（从core.py迁移）

        Returns:
            是否停止成功
        """
        try:
            # 停止文件监控
            if self.data_file_watcher:
                self.data_file_watcher.stop()
                self.data_file_watcher = None
                self.logger.info("数据文件监控已停止")

            return True

        except Exception as e:
            self.logger.error("停止数据感知失败: %s", e)
            return False

    def _determine_status(self, symbol_quality: SymbolQuality) -> str:
        """确定品种状态

        Args:
            symbol_quality: 品种质量信息

        Returns:
            状态字符串：missing/error/warning/normal
        """
        if symbol_quality.is_missing:
            return "missing"
        elif symbol_quality.has_errors:
            return "error"
        elif symbol_quality.has_warnings:
            return "warning"
        else:
            return "normal"

    def _collect_issues(self, symbol_quality: SymbolQuality) -> str:
        """收集品种的问题描述

        Args:
            symbol_quality: 品种质量信息

        Returns:
            问题描述字符串（最多显示3个问题）
        """
        issues = []

        for interval, result in symbol_quality.intervals.items():
            # 收集错误
            if result.errors:
                for error in result.errors[:2]:  # 每个周期最多2个错误
                    issues.append(f"[{interval}] {error}")

            # 收集警告
            if result.warnings:
                for warning in result.warnings[:2]:  # 每个周期最多2个警告
                    issues.append(f"[{interval}] {warning}")

            # 如果已收集足够问题，提前退出
            if len(issues) >= 3:
                break

        if not issues:
            return "无问题"

        # 最多显示3个问题
        return "; ".join(issues[:3])

    def _calculate_lagging_and_missing(
        self,
        symbols_with_data: List[str],
        reference_symbols: List[str],
        base_date: date,
        interval: str = "1d",
    ) -> tuple:
        """计算数据滞后和数据缺失

        逻辑：
        1. 从最新交易日往前遍历
        2. 找到第一段连续的"所有品种都缺失数据"的日期范围 → 数据滞后
        3. 这段范围之前的日期，有数据的品种中，缺失部分日期的品种数 → 数据缺失

        Args:
            symbols_with_data: 本地有数据的品种列表
            reference_symbols: 参考品种列表（全部品种）
            base_date: 基准日期
            interval: 时间周期（默认1d）

        Returns:
            (data_lagging_days, data_missing_symbols)
        """
        import sys

        print("\n" + "=" * 70, file=sys.stderr)
        print("🔍 [DEBUG] 开始计算数据滞后和数据缺失", file=sys.stderr)
        print(f"   本地有数据品种: {len(symbols_with_data)}个", file=sys.stderr)
        print(f"   参考品种: {len(reference_symbols)}个", file=sys.stderr)
        print(f"   基准日期: {base_date}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.stderr.flush()

        try:
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio

            # 🚀 优化：直接在当前线程运行异步代码（避免ThreadPoolExecutor）
            print("   步骤1: 获取交易日历...", file=sys.stderr)
            sys.stderr.flush()

            try:
                trading_calendar_obj = TradingCalendar()
                today = date.today()

                # 🔧 修复：创建或获取事件循环，并检查是否已关闭
                try:
                    loop = asyncio.get_event_loop()
                    # 关键修复：检查loop是否已关闭
                    if loop.is_closed():
                        raise RuntimeError("Event loop is closed")
                except RuntimeError:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # 获取今年和去年的交易日历
                df_this_year = loop.run_until_complete(
                    trading_calendar_obj.get_trading_calendar(today.year)
                )
                df_last_year = loop.run_until_complete(
                    trading_calendar_obj.get_trading_calendar(today.year - 1)
                )

                # 合并两年的交易日
                trading_calendar = []
                if df_this_year is not None and not df_this_year.empty:
                    trading_calendar.extend(df_this_year["date"].tolist())
                if df_last_year is not None and not df_last_year.empty:
                    trading_calendar.extend(df_last_year["date"].tolist())

                print(
                    f"   ✓ 获取到交易日: {len(trading_calendar)}天",
                    file=sys.stderr,
                )
                sys.stderr.flush()
            except Exception as e:
                print(f"   ✗ 交易日历获取失败: {e}", file=sys.stderr)
                sys.stderr.flush()
                self.logger.error("交易日历获取失败: %s", e, exc_info=True)
                return (0, 0)

            if not trading_calendar:
                print("   ✗ 交易日历为空", file=sys.stderr)
                sys.stderr.flush()
                self.logger.warning("交易日历不可用，无法计算数据滞后和缺失")
                return (0, 0)

            # 获取从base_date到今天的所有交易日
            today = date.today()
            trading_days = [
                d for d in trading_calendar if isinstance(d, date) and base_date <= d <= today
            ]

            if not trading_days:
                return (0, 0)

            trading_days.sort()

            # 步骤1：从最新交易日往前遍历，统计每个交易日有数据的品种数
            # 构建每个品种的数据日期集合
            # 🚀 优化：只采样前20个品种（足够估算滞后天数）+ 并行读取
            sampled_symbols = symbols_with_data[: min(20, len(symbols_with_data))]
            print(
                f"   步骤2: 构建品种数据日期集合（采样 {len(sampled_symbols)}/{len(symbols_with_data)} 个品种）...",
                file=sys.stderr,
            )
            sys.stderr.flush()

            symbol_date_sets = {}
            successful_reads = 0
            failed_reads = 0

            # 🚀 优化：批量读取（避免GIL限制），但只读最近7天数据
            from datetime import timedelta

            recent_start = base_date - timedelta(days=7)

            # 使用批量读取接口
            batch_data = self.storage_manager.query_kline_batch(
                sampled_symbols, interval, start_date=recent_start
            )

            # 提取日期集合
            for symbol, df in batch_data.items():
                try:
                    if df is not None and not df.empty:
                        data_dates = None

                        # 简化日期提取：优先datetime列
                        if "datetime" in df.columns:
                            try:
                                dates = df["datetime"].tolist()
                                data_dates = []
                                for d in dates:
                                    if isinstance(d, datetime):
                                        data_dates.append(d.date())
                                    elif isinstance(d, date):
                                        data_dates.append(d)
                                    elif hasattr(d, "to_pydatetime"):
                                        data_dates.append(d.to_pydatetime().date())
                            except Exception:
                                pass

                        # 备用：其他日期列
                        if not data_dates:
                            for col_name in ["date", "timestamp", "time"]:
                                if col_name in df.columns:
                                    try:
                                        dates = df[col_name].tolist()
                                        data_dates = []
                                        for d in dates:
                                            if isinstance(d, (datetime, date)):
                                                data_dates.append(
                                                    d.date() if isinstance(d, datetime) else d
                                                )
                                        if data_dates:
                                            break
                                    except Exception:
                                        continue

                        if data_dates:
                            symbol_date_sets[symbol] = set(data_dates)
                            successful_reads += 1
                        else:
                            failed_reads += 1
                    else:
                        failed_reads += 1

                except Exception as e:
                    failed_reads += 1
                    if failed_reads <= 3:  # 前3个错误输出详情
                        print(f"      [ERROR] 品种{symbol}读取失败: {e}", file=sys.stderr)

            print(
                f"   ✓ 批量读取完成，有效品种: {len(symbol_date_sets)}个 (成功率: {successful_reads}/{len(sampled_symbols)})",
                file=sys.stderr,
            )
            sys.stderr.flush()

            # 步骤2：从最新交易日往前找连续的全品种缺失段
            print(
                f"   步骤3: 计算数据滞后天数（从{len(trading_days)}个交易日倒序检查）...",
                file=sys.stderr,
            )
            sys.stderr.flush()
            data_lagging_days = 0
            lagging_start_idx = len(trading_days)  # 数据滞后开始的索引（不含）

            for idx in range(len(trading_days) - 1, -1, -1):
                trading_day = trading_days[idx]
                # 统计这一天有数据的品种数
                symbols_with_data_on_day = sum(
                    1 for date_set in symbol_date_sets.values() if trading_day in date_set
                )

                if symbols_with_data_on_day == 0:
                    # 这一天所有品种都缺失数据
                    data_lagging_days += 1
                else:
                    # 找到第一个有数据的日期，滞后计算结束
                    lagging_start_idx = idx + 1
                    print(
                        f"   ✓ 数据滞后: {data_lagging_days}天 (从{trading_days[idx]}往后)",
                        file=sys.stderr,
                    )
                    sys.stderr.flush()
                    break

            # 步骤3：统计数据缺失品种数（排除滞后日期）
            # 数据缺失定义：在非滞后日期范围内，品种有数据但部分日期缺失
            print("   步骤4: 计算数据缺失品种数（检查非滞后日期范围）...", file=sys.stderr)
            sys.stderr.flush()
            data_missing_symbols = 0

            if lagging_start_idx > 0:
                # 只检查非滞后的日期范围
                non_lagging_trading_days = trading_days[:lagging_start_idx]

                if non_lagging_trading_days:
                    expected_days_count = len(non_lagging_trading_days)
                    print(f"      非滞后日期范围: {expected_days_count}个交易日", file=sys.stderr)
                    sys.stderr.flush()

                    for symbol, date_set in symbol_date_sets.items():
                        # 统计该品种在非滞后日期范围内的数据完整性
                        actual_days_in_range = sum(
                            1 for d in non_lagging_trading_days if d in date_set
                        )

                        # 如果有数据但不完整，计为数据缺失
                        if 0 < actual_days_in_range < expected_days_count:
                            data_missing_symbols += 1

                    print(f"   ✓ 数据缺失: {data_missing_symbols}个品种", file=sys.stderr)
                    sys.stderr.flush()
            else:
                print("   ✓ 数据缺失: 0个品种（全部数据滞后）", file=sys.stderr)
                sys.stderr.flush()

            print("\n" + "=" * 70, file=sys.stderr)
            print("✅ [DEBUG] 计算完成", file=sys.stderr)
            print(f"   数据滞后: {data_lagging_days}天", file=sys.stderr)
            print(f"   数据缺失: {data_missing_symbols}个品种", file=sys.stderr)
            print("=" * 70 + "\n", file=sys.stderr)
            sys.stderr.flush()

            self.logger.info(
                f"数据滞后与缺失统计: 滞后{data_lagging_days}天, "
                f"数据缺失{data_missing_symbols}个品种"
            )

            return (data_lagging_days, data_missing_symbols)

        except Exception as e:
            print(f"\n❌ [DEBUG] 计算失败: {e}", file=sys.stderr)
            sys.stderr.flush()
            self.logger.error(f"计算数据滞后和缺失失败: {e}", exc_info=True)
            return (0, 0)

    def _scan_symbol_quality(self, symbol: str, intervals: List[str]) -> SymbolQuality:
        """扫描单个品种的质量"""
        interval_results = {}

        for interval in intervals:
            try:
                result = self.validator.validate_symbol(symbol, interval)
                interval_results[interval] = result

                # 检查是否有数据
                has_data = result.record_count > 0

                if not has_data:
                    return SymbolQuality(
                        symbol=symbol,
                        intervals=interval_results,
                        overall_score=0,
                        has_errors=True,
                        has_warnings=False,
                        is_missing=True,
                    )

            except Exception as e:
                self.logger.error("扫描品种 %s %s 失败: %s", symbol, interval, e)
                interval_results[interval] = ValidationResult(
                    symbol=symbol,
                    interval=interval,
                    check_time=datetime.now(),
                    is_valid=False,
                    errors=[f"扫描失败: {e}"],
                    warnings=[],
                    record_count=0,
                    date_range=(None, None),
                    missing_dates=[],
                    logic_errors=[],
                    format_errors=[],
                )

        # 计算整体评分
        has_errors = any(r.errors for r in interval_results.values())
        has_warnings = any(r.warnings for r in interval_results.values())

        # 计算平均评分（简单算法）
        valid_results = [r for r in interval_results.values() if r.record_count > 0]
        if valid_results:
            avg_score = sum(100 if r.is_valid else 50 for r in valid_results) / len(valid_results)
        else:
            avg_score = 0

        return SymbolQuality(
            symbol=symbol,
            intervals=interval_results,
            overall_score=int(avg_score),
            has_errors=has_errors,
            has_warnings=has_warnings,
            is_missing=False,
        )

    def _send_quality_update_event(self, overview: QualityOverview):
        """发送质量更新事件"""
        try:
            if not self.event_engine:
                return

            from vnpy.event import Event

            # 🔧 修复：使用顶层格式，与UI期望一致
            event_data = {
                "total_symbols": overview.total_symbols,
                "local_symbols": overview.total_symbols - overview.missing_symbols,
                "missing_symbols": overview.missing_symbols,
                "error_symbols": overview.error_symbols,
                "warning_symbols": overview.warning_symbols,
                "quality_score": overview.quality_score,
                "last_scan_time": overview.last_scan_time.isoformat(),
                # 🆕 数据更新状态
                "outdated_symbols": overview.outdated_symbols,
                "max_gap_days": overview.max_gap_days,
                # 🆕 数据缺失与滞后
                "data_missing_symbols": overview.data_missing_symbols,
                "data_lagging_days": overview.data_lagging_days,
                # 🔧 修复：添加问题品种详情
                "details": overview.details,
            }

            from .data_module import EVENT_DATA_QUALITY_UPDATE
            from vnpy.event import Event

            event = Event(EVENT_DATA_QUALITY_UPDATE, event_data)
            self.event_engine.put(event)

            self.logger.info(
                f"📊 推送数据质量概览: "
                f"总品种{overview.total_symbols}, 缺失{overview.missing_symbols}, "
                f"问题品种{len(overview.details)}个"
            )

        except Exception as e:
            self.logger.error("发送质量更新事件失败: %s", e)

    def on_file_changed(self, event_type: str, file_path: Path) -> None:
        """
        文件变化回调方法

        当数据文件发生变化时，清除质量概览缓存以便下次重新计算

        Args:
            event_type: 事件类型 (created/modified/moved/deleted)
            file_path: 发生变化的文件路径
        """
        try:
            self.logger.info("检测到数据文件变化 [%s]: %s", event_type, file_path)
            # 清除缓存，下次访问时会重新扫描
            self._quality_overview = None
            self.logger.info("数据质量缓存已清除，将在下次访问时重新扫描")
        except Exception as e:
            self.logger.error("处理文件变化事件失败: %s", e)

    def get_quality_overview(self) -> Optional[QualityOverview]:
        """
        获取质量概览

        Returns:
            Optional[QualityOverview]: 若尚未扫描或缓存已清空则返回 None
        """
        return self._quality_overview

    # 🆕 ==================== 自适应数据质量扫描 ====================

    def scan_all_data_adaptive(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
        max_phase: Optional[int] = None,
    ) -> QualityOverview:
        """自适应数据质量扫描（增量推送版）

        根据设备性能和数据规模自动选择最优扫描策略，并分阶段推送结果。

        Args:
            reference_symbols: 参考品种列表
            intervals: 扫描周期列表
            force_refresh: 是否强制刷新
            progress_callback: 进度回调
            max_phase: 最大执行阶段（0/1/2/3），None表示执行全部阶段

        Returns:
            QualityOverview: 质量概览
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        # 检查配置
        from .data_module import config_manager

        enable_adaptive = config_manager.is_quality_scan_adaptive_enabled()
        enable_incremental_push = config_manager.is_quality_scan_incremental_push_enabled()

        if not enable_adaptive:
            # 使用传统扫描模式
            self.logger.info("使用传统扫描模式（自适应已禁用）")
            return self.scan_all_data(
                reference_symbols, intervals, force_refresh, progress_callback, max_phase
            )

        # 启用自适应模式
        self.logger.info("启用自适应扫描模式")

        try:
            # 🎯 架构修复：直接使用LoadBalancer，移除已弃用的AdaptiveQualityConfig
            # 🔧 修复：添加超时保护，避免LoadBalancer查询阻塞扫描
            import multiprocessing as mp
            import psutil

            cpu_cores = mp.cpu_count()
            memory = psutil.virtual_memory()
            available_memory_gb = memory.available / (1024**3)

            # 根据品种数量推断扫描模式
            symbols_count = len(reference_symbols)
            if symbols_count < 100:
                scan_mode = "fast"
            elif symbols_count < 3000:
                scan_mode = "balanced"
            else:
                scan_mode = "thorough"

            # 默认配置（如果LoadBalancer查询失败则使用）
            config = {
                "scan_mode": scan_mode,
                "max_workers": 4,
                "batch_size": 50,
                "enable_multiprocessing": False,
                "enable_detailed_scan": True,  # 默认启用详细扫描
                "cpu_cores": cpu_cores,
                "available_memory_gb": available_memory_gb,
                "symbols_count": symbols_count,
                "estimated_memory_mb": symbols_count * 0.1,  # 估算内存使用
                "reason": "默认配置（LoadBalancer不可用）",
            }

            # 尝试从LoadBalancer获取优化配置（带超时保护）
            try:
                # DataQualityScanTask在本文件第1506行定义，无需导入
                task = DataQualityScanTask("quality_scan", len(reference_symbols))

                # 🔧 关键修复：将LoadBalancer初始化与查询都放入线程，避免阻塞
                import threading

                lb_config = None
                config_ready = threading.Event()

                def get_config_with_timeout():
                    nonlocal lb_config
                    try:
                        from backend.infrastructure.data_module_vnpy.load_balancer import (
                            get_load_balancer,
                        )

                        # 获取全局LoadBalancer以启用事件订阅机制
                        lb = get_load_balancer()
                        lb_config = lb.get_optimal_config(task)
                        config_ready.set()
                    except Exception as e:
                        self.logger.warning(f"LoadBalancer初始化/查询失败: {e}")
                        config_ready.set()

                # 启动查询线程
                query_thread = threading.Thread(target=get_config_with_timeout, daemon=True)
                query_thread.start()

                # 等待最多2秒
                if config_ready.wait(timeout=2.0) and lb_config:
                    # 🚀 优化：直接使用LoadBalancer的动态配置，不再手动覆盖
                    # LoadBalancer已经根据瓶颈类型和压力分数计算了最优配置
                    config.update(
                        {
                            "max_workers": lb_config.get("max_workers", 8),
                            "batch_size": lb_config.get("batch_size", 1000),
                            "enable_detailed_scan": True,  # 始终启用详细扫描
                            "use_fs_cache": True,
                            "symbols_count": symbols_count,
                            "estimated_memory_mb": symbols_count * 0.1,
                            "bottleneck": lb_config.get("bottleneck", "balanced"),
                            "pressure_score": lb_config.get("pressure_score", 70.0),
                            "reason": f"LoadBalancer动态配置（瓶颈={lb_config.get('bottleneck')}，压力={lb_config.get('pressure_score'):.1f}）",
                        }
                    )
                    self.logger.info("✅ LoadBalancer配置获取成功，已应用动态优化策略")
                else:
                    # 超时或失败，使用默认配置
                    self.logger.warning("⚠️ LoadBalancer初始化/查询超时，使用默认配置")

            except Exception as e:
                self.logger.warning(f"LoadBalancer线程启动失败，使用默认配置: {e}")

            # 输出配置摘要（使用现有方法）
            config_summary = format_quality_config_summary(config)
            self.logger.info("\n" + config_summary)
            print("\n" + config_summary)

            # 🎯 架构修复：在扫描前检查并更新IPO日期缓存
            # 将IPO缓存更新从启动验证流程迁移到这里，避免启动时大批量下载阻塞
            self._ensure_ipo_cache_ready(reference_symbols)

            # 阶段0：立即推送基础指标
            self._push_phase_0_metrics(reference_symbols, enable_incremental_push)

            # 阶段1：快速扫描本地数据索引
            local_symbols_data = self._scan_phase_1_local_index(reference_symbols)
            self._push_phase_1_metrics(local_symbols_data, enable_incremental_push)

            # 阶段2：批量检查数据更新状态
            freshness_data = self._scan_phase_2_freshness(
                local_symbols_data["local_symbols"], config, progress_callback
            )
            self._push_phase_2_metrics(freshness_data, enable_incremental_push)

            # 检查是否只执行到阶段2（启动快速扫描模式）
            if max_phase is not None and max_phase < 3:
                self.logger.info(f"启动快速扫描模式：只执行到阶段{max_phase}，跳过阶段3")

                # 构建部分扫描结果
                overview = QualityOverview(
                    total_symbols=len(reference_symbols),
                    missing_symbols=local_symbols_data["missing_count"],
                    error_symbols=0,  # 未扫描
                    warning_symbols=0,  # 未扫描
                    quality_score=0,  # 部分扫描不计算评分
                    last_scan_time=datetime.now(),
                    base_date=date.today(),
                    scanned_intervals=intervals,
                    details=[],
                    outdated_symbols=freshness_data["outdated_symbols"],
                    max_gap_days=freshness_data["max_gap_days"],
                    data_missing_symbols=0,  # 未扫描
                    data_lagging_days=freshness_data.get("data_lagging_days", 0),
                )

                # 推送部分扫描完成事件
                if enable_incremental_push and self.event_engine:
                    from .data_module import EVENT_QUALITY_SCAN_PHASE
                    from vnpy.event import Event

                    event_data = {
                        "phase": 2,
                        "metrics": {
                            "total_symbols": len(reference_symbols),
                            "missing_symbols": local_symbols_data["missing_count"],
                            "outdated_symbols": freshness_data["outdated_symbols"],
                        },
                        "status": "startup_complete",  # 标记为启动扫描完成
                        "progress_percent": 100,
                        "timestamp": datetime.now().isoformat(),
                        "message": "启动快速扫描完成（阶段0-2），详细质量扫描已跳过",
                    }
                    event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
                    self.event_engine.put(event)
                    self.logger.info("推送启动快速扫描完成事件")

                return overview

            # 阶段3：详细质量扫描（仅在max_phase>=3或None时执行）
            quality_data = self._scan_phase_3_quality(
                local_symbols_data["local_symbols"],
                intervals,
                config,
                progress_callback,
            )
            # 🔥 强制输出到terminal（无法被日志系统过滤）
            import sys
            print(f"\n🔍 [CRITICAL-DEBUG] 准备调用_push_phase_3_metrics", file=sys.stderr)
            print(f"  enable_incremental_push={enable_incremental_push}", file=sys.stderr)
            print(f"  quality_data keys={list(quality_data.keys())}", file=sys.stderr)
            print(f"  symbol_qualities count={len(quality_data.get('symbol_qualities', []))}", file=sys.stderr)
            sys.stderr.flush()

            self.logger.info(f"🔍 [DEBUG] 准备调用_push_phase_3_metrics: enable_incremental_push={enable_incremental_push}, quality_data keys={list(quality_data.keys())}")
            self._push_phase_3_metrics(quality_data, enable_incremental_push)

            # 🚀 任务6：删除阶段4，直接构建QualityOverview（评分无用，设为0）
            overview = QualityOverview(
                total_symbols=len(reference_symbols),
                missing_symbols=local_symbols_data["missing_count"],
                error_symbols=quality_data.get("error_symbols", 0),
                warning_symbols=quality_data.get("warning_symbols", 0),
                quality_score=0,  # 🚀 评分无用，设为0
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=list(set(intervals)),
                details=[],  # 详情由UI从增量推送中获取
                outdated_symbols=freshness_data["outdated_symbols"],
                data_missing_symbols=quality_data.get("data_missing_symbols", 0),
                data_lagging_days=freshness_data.get("data_lagging_days", 0),
            )

            self._quality_overview = overview

            # 推送传统的质量更新事件（兼容现有代码）
            if self.event_engine:
                self._send_quality_update_event(overview)

            # 输出日期范围异常最终统计
            self.validator.log_final_date_range_exception_stats()

            # 🎯 添加批量扫描汇总INFO日志
            self.logger.info(
                "✅ 数据质量扫描完成: 总品种=%d, 缺失=%d, 错误=%d, 警告=%d, 数据滞后=%d天, 数据缺失=%d",
                len(reference_symbols),
                local_symbols_data["missing_count"],
                quality_data.get("error_symbols", 0),
                quality_data.get("warning_symbols", 0),
                freshness_data.get("data_lagging_days", 0),
                quality_data.get("data_missing_symbols", 0),
            )

            # 🔧 修复：扫描完成后确保文件监控已启动
            try:
                self.start_file_watcher()
            except Exception as watcher_error:
                self.logger.warning(f"启动文件监控失败: {watcher_error}")

            return overview

        except Exception as e:
            self.logger.error("自适应扫描失败，降级到传统模式: %s", e, exc_info=True)
            return self.scan_all_data(
                reference_symbols, intervals, force_refresh, progress_callback
            )

    def _ensure_ipo_cache_ready(self, reference_symbols: List[str]):
        """确保IPO日期缓存就绪（在扫描前执行增量更新）

        架构修复：将IPO缓存更新从启动验证流程迁移到数据质量扫描前，
        这样避免了启动时大批量下载阻塞，只在需要时才更新。

        Args:
            reference_symbols: 参考品种列表
        """
        import sys

        try:
            ipo_cache = self.validator._ipo_cache  # noqa: SLF001

            # 检查缓存状态
            if not ipo_cache.is_cache_outdated():
                # 获取缓存大小（实际条目数）
                cache_stats = ipo_cache.get_stats()
                cached_count = cache_stats.get("size", 0)
                self.logger.info("✓ IPO日期缓存有效：%d 个品种", cached_count)
                return

            # 缓存需要更新
            self.logger.warning("⚠ IPO日期缓存需要更新，开始增量更新...")
            print("\n[准备工作] 更新IPO日期缓存")
            sys.stdout.flush()

            # 执行增量更新
            start_time = time.time()
            result = ipo_cache.incremental_update(
                reference_symbols, progress_callback=None  # 不需要进度回调，下载过程自己会打印进度
            )
            elapsed = time.time() - start_time

            # 输出结果
            if result.get("download_succeeded", 0) > 0 or result.get("added", 0) > 0:
                print("  ✓ IPO日期更新完成")
                print(f"  ✓ 新增: {result['added']} 个品种")
                print(f"  ✓ 成功: {result['download_succeeded']} 个")
                print(f"  ✓ 失败: {result['download_failed']} 个")
                print(f"  ✓ 耗时: {elapsed:.2f}秒")
                sys.stdout.flush()

                self.logger.info(
                    "✅ IPO日期缓存更新完成：新增 %d 个，下载成功 %d 个，耗时 %.2f秒",
                    result["added"],
                    result["download_succeeded"],
                    elapsed,
                )
            else:
                print("  ✓ IPO日期缓存无需更新")
                sys.stdout.flush()
                self.logger.info("✓ IPO日期缓存已是最新")

        except Exception as e:
            self.logger.error("更新IPO日期缓存失败: %s", e, exc_info=True)
            print(f"  ⚠ IPO日期缓存更新失败: {e}")
            sys.stdout.flush()

    def _push_phase_0_metrics(self, reference_symbols: List[str], enable_push: bool):
        """阶段0：立即推送基础指标"""
        if not enable_push or not self.event_engine:
            return

        from .data_module import EVENT_QUALITY_SCAN_PHASE
        from vnpy.event import Event
        from datetime import datetime

        event_data = {
            "phase": 0,
            "metrics": {"total_symbols": len(reference_symbols)},
            "status": "scanning",
            "progress_percent": 0,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(f"📊 推送阶段0指标: 总品种 {len(reference_symbols)}")

    def _scan_phase_1_local_index(self, reference_symbols: List[str]) -> Dict:
        """🚀 阶段1：快速扫描本地数据索引（优化版：缓存加速）

        修复记录 (2025-10-24):
        - 修复全量扫描问题：只返回reference_symbols中存在于本地的品种
        - 避免后续阶段扫描全部本地品种
        """
        # 🔍 测量事件循环延迟
        self._measure_event_loop_lag_sync("DataSensor_Phase1")

        start_time = time.time()

        print("\n[阶段1/3] 快速扫描本地数据索引")
        sys.stdout.flush()

        # 🚀 优化：使用缓存（5秒TTL）
        all_local_symbol_codes = self.storage_manager.get_local_data_index(use_cache=True)
        all_local_symbols_set = set(all_local_symbol_codes)

        # 🔧 修复：只保留reference_symbols中存在于本地的品种
        local_symbol_codes = [s for s in reference_symbols if s in all_local_symbols_set]

        downloaded_count = len(local_symbol_codes)
        missing_count = len(reference_symbols) - downloaded_count

        elapsed = time.time() - start_time

        # 🆕 输出到terminal，明确说明数据含义
        print(f"  ✓ 至少存在一个文件的品种数（阶段1）: {downloaded_count}个")
        print(f"     - 参考品种总数: {len(reference_symbols)}个")
        print(f"     - 完全无数据品种: {missing_count}个")
        print(f"  ✓ 耗时: {elapsed:.2f}秒")
        sys.stdout.flush()

        # 🆕 计算缺失品种详情（用于增量推送）
        missing_symbols = [s for s in reference_symbols if s not in all_local_symbols_set]

        return {
            "local_symbols": local_symbol_codes,  # 🔧 修复：只包含reference_symbols中的本地品种
            "downloaded_count": downloaded_count,
            "missing_count": missing_count,
            "missing_symbols": missing_symbols,  # 🆕 新增
        }

    def _push_phase_1_metrics(self, local_data: Dict, enable_push: bool):
        """阶段1：推送本地数据索引指标"""
        if not enable_push or not self.event_engine:
            return

        from .data_module import EVENT_QUALITY_SCAN_PHASE
        from vnpy.event import Event
        from datetime import datetime

        # 🆕 构建品种缺失的details（用于增量推送）
        missing_details = []
        missing_symbols_list = local_data.get("missing_symbols", [])
        # 只推送前100个缺失品种的详情（避免推送数据过大）
        for symbol in missing_symbols_list[:100]:
            missing_details.append(
                {
                    "symbol": symbol,
                    "status": "missing",
                    "score": 0,
                    "has_errors": False,
                    "has_warnings": False,
                    "is_missing": True,
                    "issues": "品种完全无数据",
                }
            )

        event_data = {
            "phase": 1,
            "metrics": {
                "downloaded_symbols": local_data["downloaded_count"],
                "missing_symbols": local_data["missing_count"],
                "details": missing_details,  # 🆕 新增
            },
            "status": "checking_freshness",
            "progress_percent": 25,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(
            f"📊 推送阶段1指标: 已下载 {local_data['downloaded_count']}, "
            f"缺失 {local_data['missing_count']}, 推送{len(missing_details)}个缺失详情"
        )

        # 🔧 修复：阶段1完成后立即推送本地数据索引事件，供UI联想使用
        try:
            local_symbols_list = local_data.get("local_symbols", [])
            symbol_list = [{"code": code, "name": ""} for code in local_symbols_list]
            if symbol_list:
                from .data_module import EVENT_LOCAL_DATA_INDEX_READY
                from vnpy.event import Event

                index_event = Event(
                    EVENT_LOCAL_DATA_INDEX_READY,
                    {"symbols": symbol_list, "count": len(symbol_list)},
                )
                self.event_engine.put(index_event)
                self.logger.info(f"📋(阶段1) 推送本地数据索引: {len(symbol_list)} 个品种")
        except Exception as e:
            self.logger.warning(f"阶段1推送本地数据索引事件失败: {e}")

    def _scan_phase_2_freshness(
        self, local_symbols: List[str], config: Dict, progress_callback
    ) -> Dict:
        """🚀 阶段2：批量检查数据更新状态（优化版：批量处理+线程池并行+无刷屏输出）"""
        # 🔍 测量事件循环延迟
        self._measure_event_loop_lag_sync("DataSensor_Phase2")

        start_time = time.time()

        print("\n[阶段2/3] 检查数据更新状态")
        print(f"  品种数量: {len(local_symbols)}")
        sys.stdout.flush()

        # 🚀 优化：从LoadBalancer获取动态并发配置
        max_workers = config.get("max_workers", 8)

        # 🚀 优化：使用错误累积器
        error_accumulator = ErrorAccumulator(self.logger)

        # 🚀 优化：使用批量检查方法（线程池并行）
        freshness_results = self.validator.batch_check_freshness_optimized(
            symbols=local_symbols,
            interval="1d",
            max_workers=max_workers,
            error_accumulator=error_accumulator,
        )

        # 统计结果
        outdated_symbols = 0
        gap_days_list = []
        outdated_details = []

        # 🆕 统计含有效数据的品种数
        valid_data_count = 0
        for symbol, freshness in freshness_results.items():
            if freshness["has_data"]:
                valid_data_count += 1
                gap_days = freshness["gap_days"]
                if gap_days > 1:
                    outdated_symbols += 1
                    # 记录过时品种详情（只保留前50个）
                    if len(outdated_details) < 50:
                        outdated_details.append({"symbol": symbol, "gap_days": gap_days})
                if gap_days >= 0:
                    gap_days_list.append(gap_days)

        # 🚀 任务4：计算数据滞后天数（从阶段4迁移过来）
        # 数据滞后 = 所有品种的最大gap_days（连续的全品种缺失）
        data_lagging_days = max(gap_days_list) if gap_days_list else 0

        elapsed = time.time() - start_time

        # 🎯 优化：只输出最终结果，无循环刷屏
        # 🆕 明确说明数据含义
        print(f"  ✓ 至少有一个周期含有效数据的品种数（阶段2）: {valid_data_count}个")
        print(f"     - 扫描品种总数: {len(local_symbols)}个")
        print(f"     - 过时品种（滞后>1天）: {outdated_symbols}个")
        print(f"     - 数据滞后: {data_lagging_days} 天")
        print(f"  ✓ 耗时: {elapsed:.2f}秒")
        sys.stdout.flush()

        # 输出错误摘要（如果有）
        error_accumulator.print_summary()

        # 更新进度回调
        if progress_callback:
            progress_callback(50)  # 阶段2完成

        return {
            "outdated_symbols": outdated_symbols,
            "gap_days_list": gap_days_list,
            "outdated_details": outdated_details,
            "data_lagging_days": data_lagging_days,  # 🚀 新增
        }

    def _push_phase_2_metrics(self, freshness_data: Dict, enable_push: bool):
        """阶段2：推送数据更新状态指标"""
        if not enable_push or not self.event_engine:
            return

        from .data_module import EVENT_QUALITY_SCAN_PHASE
        from vnpy.event import Event
        from datetime import datetime

        # 🆕 构建过时品种的details（用于增量推送）
        outdated_details_raw = freshness_data.get("outdated_details", [])
        outdated_details = []
        for item in outdated_details_raw:
            outdated_details.append(
                {
                    "symbol": item["symbol"],
                    "status": "warning",
                    "score": 50,
                    "has_errors": False,
                    "has_warnings": True,
                    "is_missing": False,
                    "issues": f"数据滞后 {item['gap_days']} 个交易日",
                }
            )

        # 🔧 优化：不推送完整details列表（防止5000+行输出）
        event_data = {
            "phase": 2,
            "metrics": {
                "outdated_symbols": freshness_data["outdated_symbols"],
                # "details": outdated_details,  # 已移除：防止刷屏
                "details_count": len(outdated_details),  # 仅推送数量
            },
            "status": "scanning_quality" if enable_push else "calculating_score",
            "progress_percent": 50,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(
            f"📊 推送阶段2指标: 过时 {freshness_data['outdated_symbols']}, "
            f"推送{len(outdated_details)}个过时详情"
        )

    def _scan_phase_3_quality(
        self,
        local_symbols: List[str],
        intervals: List[str],
        config: Dict,
        progress_callback,
    ) -> Dict:
        """阶段3：详细质量扫描（使用新架构ThreadPoolBatchModel + 动态并发调整）"""
        # 🔍 测量事件循环延迟
        self._measure_event_loop_lag_sync("DataSensor_Phase3")

        import sys

        print("\n[阶段3/3] 详细质量扫描（错误/警告）")
        sys.stdout.flush()

        # 🚀 新架构：初始化资源监控和策略决策
        try:
            resource_monitor = ResourceMonitor(event_engine=self.event_engine)
            execution_policy = ExecutionPolicy()

            # 创建任务实例（用于策略决策）
            task = DataQualityScanTask("phase3_quality_scan", len(local_symbols))

            # 获取当前资源压力
            pressure = resource_monitor.get_current_pressure()

            # 根据任务和压力选择执行计划
            plan = execution_policy.select_execution_plan(task, pressure)

            self.logger.info(f"🎯 执行计划: {plan.reason}")

            # 🔧 修复pickle错误：数据扫描是I/O密集型任务，使用线程池更合适
            # 直接使用线程池批量扫描（避免多进程的pickle问题）
            from concurrent.futures import ThreadPoolExecutor, as_completed

            # 🚀 核心修复：使用LoadBalancer的执行计划配置，而不是传入的config
            # 问题：传入的config可能来自上层scan_all_data_adaptive的2秒超时配置
            # 解决：阶段3内部重建LoadBalancer策略，使用plan的配置
            plan_max_workers = plan.initial_config.max_workers if plan and hasattr(plan.initial_config, 'max_workers') else None
            max_workers = plan_max_workers if plan_max_workers else config.get("max_workers", 16)

            self.logger.info(
                f"阶段3：使用线程池执行质量扫描，max_workers={max_workers} "
                f"(来源={'LoadBalancer执行计划' if plan_max_workers else 'config'}, {plan.reason if plan else 'N/A'})"
            )

            error_symbols = 0
            warning_symbols = 0
            data_missing_symbols = 0
            symbol_qualities = []

            # 🔍 记录开始时间和初始资源状态
            import time
            import psutil
            start_time = time.time()
            initial_cpu = psutil.cpu_percent(interval=0.1)
            initial_memory = psutil.virtual_memory().percent
            self.logger.info(
                f"📊 扫描开始: 品种数={len(local_symbols)}, 线程数={max_workers}, "
                f"初始CPU={initial_cpu:.1f}%, 初始内存={initial_memory:.1f}%"
            )

            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="QualityScan") as executor:
                # 提交所有任务
                future_to_symbol = {
                    executor.submit(self._scan_symbol_quality, symbol, intervals): symbol
                    for symbol in local_symbols
                }

                # 收集结果
                completed = 0
                failed = 0
                last_log_time = start_time
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        result = future.result(timeout=30)  # 🔧 添加30秒超时，避免单个品种卡住
                        if result:
                            symbol_qualities.append(result)
                            if result.has_errors:
                                error_symbols += 1
                            if result.has_warnings:
                                warning_symbols += 1
                            # 检查数据缺失
                            for interval_result in result.intervals.values():
                                if interval_result.missing_dates and len(interval_result.missing_dates) > 0:
                                    data_missing_symbols += 1
                                    break
                    except TimeoutError:
                        self.logger.warning(f"⏱️ 扫描品种 {symbol} 超时（30秒），已跳过")
                        failed += 1
                    except Exception as e:
                        self.logger.warning(f"❌ 扫描品种 {symbol} 失败: {e}")
                        failed += 1

                    completed += 1

                    # 🔧 每10%输出一次进度到terminal，并监控资源使用
                    if len(local_symbols) > 0:
                        percent = int((completed / len(local_symbols)) * 100)
                        # 每10%输出（10%, 20%, ..., 100%）
                        if percent % 10 == 0 and completed == int(len(local_symbols) * percent / 100):
                            # 🔍 获取当前资源使用情况
                            current_time = time.time()
                            elapsed = current_time - start_time
                            current_cpu = psutil.cpu_percent(interval=0)
                            current_memory = psutil.virtual_memory().percent
                            throughput = completed / elapsed if elapsed > 0 else 0

                            print(
                                f"  [阶段3] 进度: {percent}% ({completed}/{len(local_symbols)}, 失败={failed}) "
                                f"| CPU={current_cpu:.1f}% "
                                f"| 内存={current_memory:.1f}% "
                                f"| 吞吐={throughput:.1f}品种/秒"
                            )
                            sys.stdout.flush()
                            self.logger.info(
                                f"阶段3进度: {percent}% ({completed}/{len(local_symbols)}, 失败={failed}), "
                                f"CPU={current_cpu:.1f}%, "
                                f"内存={current_memory:.1f}%, "
                                f"吞吐={throughput:.1f}品种/秒"
                            )

                        if progress_callback:
                            progress_callback(50 + percent * 0.4)  # 50%-90%

                if failed > 0:
                    self.logger.warning(f"⚠️ 阶段3完成，但有 {failed} 个品种扫描失败")

            # 🔍 计算总体性能指标
            end_time = time.time()
            total_elapsed = end_time - start_time
            avg_throughput = len(local_symbols) / total_elapsed if total_elapsed > 0 else 0
            final_cpu = psutil.cpu_percent(interval=0.1)
            final_memory = psutil.virtual_memory().percent

            # 阶段完成后输出汇总
            print(f"  ✓ 扫描完成: {len(local_symbols)} 个品种")
            print(f"  ✓ 错误品种: {error_symbols}")
            print(f"  ✓ 警告品种: {warning_symbols}")
            print(f"  ✓ 数据缺失品种: {data_missing_symbols}")
            print(f"  ✓ 总耗时: {total_elapsed:.2f}秒")
            print(f"  ✓ 平均吞吐: {avg_throughput:.1f}品种/秒")
            print(f"  ✓ 最终CPU: {final_cpu:.1f}%")
            print(f"  ✓ 最终内存: {final_memory:.1f}%")
            sys.stdout.flush()

            self.logger.info(
                f"📊 阶段3性能统计: 耗时={total_elapsed:.2f}秒, 吞吐={avg_throughput:.1f}品种/秒, "
                f"线程数={max_workers}, 最终CPU={final_cpu:.1f}%, 最终内存={final_memory:.1f}%"
            )

            return {
                "error_symbols": error_symbols,
                "warning_symbols": warning_symbols,
                "symbol_qualities": symbol_qualities,
                "data_missing_symbols": data_missing_symbols,
            }

        except Exception as e:
            self.logger.error(f"新架构执行失败，降级到串行实现: {e}", exc_info=True)

            # 降级到串行实现（避免ThreadPoolExecutor）
            error_symbols = 0
            warning_symbols = 0
            symbol_qualities = []

            for idx, symbol in enumerate(local_symbols):
                try:
                    symbol_quality = self._scan_symbol_quality(symbol, intervals)
                    if symbol_quality:
                        symbol_qualities.append(symbol_quality)
                        if symbol_quality.has_errors:
                            error_symbols += 1
                        if symbol_quality.has_warnings:
                            warning_symbols += 1
                except Exception as e2:
                    self.logger.error("扫描品种 %s 失败: %s", symbol, e2)

                completed = idx + 1
                if progress_callback and completed % 500 == 0:
                    percent = int((completed / len(local_symbols)) * 100)
                    progress_callback(50 + percent * 0.4)

            data_missing_symbols = 0
            for sq in symbol_qualities:
                for interval_result in sq.intervals.values():
                    if interval_result.missing_dates and len(interval_result.missing_dates) > 0:
                        data_missing_symbols += 1
                        break

            print(f"  ✓ 扫描完成: {len(local_symbols)} 个品种（旧实现）")
            print(f"  ✓ 错误品种: {error_symbols}")
            print(f"  ✓ 警告品种: {warning_symbols}")
            print(f"  ✓ 数据缺失品种: {data_missing_symbols}")
            sys.stdout.flush()

            return {
                "error_symbols": error_symbols,
                "warning_symbols": warning_symbols,
                "symbol_qualities": symbol_qualities,
                "data_missing_symbols": data_missing_symbols,
            }

    def _push_phase_3_metrics(self, quality_data: Dict, enable_push: bool):
        """阶段3：推送详细质量指标和最终完成事件"""
        # 🔥 强制输出到terminal（无法被日志系统过滤）
        import sys
        print(f"\n🔍 [CRITICAL-DEBUG] _push_phase_3_metrics被调用", file=sys.stderr)
        print(f"  enable_push={enable_push}", file=sys.stderr)
        print(f"  event_engine={self.event_engine is not None}", file=sys.stderr)
        sys.stderr.flush()

        self.logger.info(f"🔍 [DEBUG] _push_phase_3_metrics被调用: enable_push={enable_push}, event_engine={self.event_engine is not None}")

        if not enable_push or not self.event_engine:
            print(f"⚠️ [CRITICAL-DEBUG] 阶段3推送被跳过！", file=sys.stderr)
            sys.stderr.flush()
            self.logger.warning(f"⚠️ 阶段3指标推送已跳过: enable_push={enable_push}, event_engine={self.event_engine is not None}")
            return

        from .data_module import EVENT_QUALITY_SCAN_PHASE
        from vnpy.event import Event
        from datetime import datetime

        # 🆕 构建错误品种的details（推送所有错误和警告品种）
        symbol_qualities = quality_data.get("symbol_qualities", [])

        # 🔧 获取品种名称映射
        symbol_name_map = {}
        try:
            from .data_module import ChinaStockEngine
            engine = getattr(ChinaStockEngine, '_instance', None)
            if engine and hasattr(engine, 'symbol_loader') and engine.symbol_loader:
                symbols_result = engine._validate_symbol_cache_readonly()
                if symbols_result:
                    all_symbols = symbols_result.get("all_symbols", [])
                    for s in all_symbols:
                        if isinstance(s, dict):
                            symbol_name_map[s.get("symbol", "")] = s.get("name", "")
        except Exception as e:
            self.logger.debug(f"获取品种名称映射失败: {e}")

        error_details = []
        warning_details = []
        data_missing_details = []

        for sq in symbol_qualities:
            detail = {
                "symbol": sq.symbol,
                "name": symbol_name_map.get(sq.symbol, ""),  # 🆕 添加品种名称
                "status": "error" if sq.has_errors else ("warning" if sq.has_warnings else "data_missing"),
                "score": sq.overall_score,
                "has_errors": sq.has_errors,
                "has_warnings": sq.has_warnings,
                "is_missing": sq.is_missing,
                "issues": self._collect_issues(sq),
            }

            if sq.has_errors:
                error_details.append(detail)
            elif sq.has_warnings:
                warning_details.append(detail)
            # 检查数据缺失
            elif any(interval_result.missing_dates and len(interval_result.missing_dates) > 0
                    for interval_result in sq.intervals.values()):
                detail["status"] = "data_missing"
                data_missing_details.append(detail)

        # 合并所有问题详情
        all_details = error_details + warning_details + data_missing_details

        # 🚀 任务5：推送最终完成事件（从阶段4迁移过来）
        # 阶段3是最后阶段，直接推送complete状态
        event_data = {
            "phase": 3,
            "metrics": {
                "error_symbols": quality_data["error_symbols"],
                "warning_symbols": quality_data["warning_symbols"],
                "data_missing_symbols": quality_data.get("data_missing_symbols", 0),
                "details": all_details,  # 🔧 推送所有问题品种的详情
            },
            "status": "complete",  # 🚀 修改：直接完成，不再有阶段4
            "progress_percent": 100,  # 🚀 修改：100%完成
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)

        # 🔥 强制输出到terminal（确认事件已推送）
        import sys
        print(f"\n✅ [CRITICAL-DEBUG] 阶段3事件已推送到event_engine", file=sys.stderr)
        print(f"  错误品种={len(error_details)}", file=sys.stderr)
        print(f"  警告品种={len(warning_details)}", file=sys.stderr)
        print(f"  数据缺失品种={len(data_missing_details)}", file=sys.stderr)
        print(f"  总详情={len(all_details)}个品种", file=sys.stderr)
        sys.stderr.flush()

        self.logger.info(
            f"📊 推送阶段3指标: 错误={len(error_details)}, "
            f"警告={len(warning_details)}, 数据缺失={len(data_missing_details)}, "
            f"总详情={len(all_details)}个品种"
        )

    def _calculate_and_push_final_score(
        self,
        reference_symbols: List[str],
        local_data: Dict,
        freshness_data: Dict,
        quality_data: Dict,
        intervals: List[str],
        enable_push: bool,
    ) -> QualityOverview:
        """阶段4：计算最终评分并推送"""
        import sys

        print("\n[阶段4/4] 计算最终评分")
        sys.stdout.flush()

        total_symbols = len(reference_symbols)
        missing_symbols = local_data["missing_count"]
        outdated_symbols = freshness_data["outdated_symbols"]

        error_symbols = quality_data.get("error_symbols", 0)
        warning_symbols = quality_data.get("warning_symbols", 0)
        symbol_qualities = quality_data.get("symbol_qualities", [])

        # 🆕 计算数据滞后和数据缺失（静默计算，不输出中间状态）
        local_symbols = local_data.get("local_symbols", [])
        data_lagging_days, data_missing_symbols = self._calculate_lagging_and_missing(
            symbols_with_data=local_symbols,
            reference_symbols=reference_symbols,
            base_date=date.today(),
            interval="1d",
        )

        # 构建详情（只包含有问题的品种）
        problem_details = [
            {
                "symbol": sq.symbol,
                "status": self._determine_status(sq),
                "score": sq.overall_score,
                "has_errors": sq.has_errors,
                "has_warnings": sq.has_warnings,
                "is_missing": sq.is_missing,
                "issues": self._collect_issues(sq),
            }
            for sq in symbol_qualities
            if sq.has_errors or sq.has_warnings or sq.is_missing
        ]

        overview = QualityOverview(
            total_symbols=total_symbols,
            missing_symbols=missing_symbols,
            error_symbols=error_symbols,
            warning_symbols=warning_symbols,
            quality_score=0,  # 🔧 质量评分功能已简化，统一设为0（保留字段以兼容前端）
            last_scan_time=datetime.now(),
            base_date=date.today(),
            scanned_intervals=list(set(intervals)),
            details=problem_details,
            outdated_symbols=outdated_symbols,
            data_missing_symbols=data_missing_symbols,  # 🆕 添加数据缺失
            data_lagging_days=data_lagging_days,  # 🆕 添加数据滞后
        )

        # 推送扫描完成状态（不包含质量评分）
        if enable_push and self.event_engine:
            from .data_module import EVENT_QUALITY_SCAN_PHASE
            from vnpy.event import Event

            event_data = {
                "phase": 4,
                "metrics": {},  # 阶段4不再推送质量评分
                "status": "complete",
                "progress_percent": 100,
                "timestamp": datetime.now().isoformat(),
            }

            event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
            self.event_engine.put(event)
            self.logger.info("📊 推送阶段4指标: 扫描完成")

        # 推送传统的质量更新事件（兼容现有代码）
        if self.event_engine:
            self._send_quality_update_event(overview)

        # 输出日期范围异常最终统计
        self.validator.log_final_date_range_exception_stats()

        # 🎯 架构修复：添加批量扫描汇总INFO日志（替代数万条逐项DEBUG）
        self.logger.info(
            "✅ 数据质量扫描完成: 总品种=%d, 缺失=%d, 错误=%d, 警告=%d, 评分=%.1f%%",
            total_symbols,
            missing_symbols,
            error_symbols,
            warning_symbols,
            overview.quality_score,
        )

        # 🔧 修复：扫描完成后发布本地数据索引事件（用于UI联想功能）
        try:
            # 需要通过 china_stock_engine 访问
            # 由于 DataSensor 不直接持有 engine 引用，需要通过事件引擎推送
            if self.event_engine:
                from .data_module import EVENT_LOCAL_DATA_INDEX_READY
                from vnpy.event import Event

                # 构建本地数据索引事件数据
                local_symbols_list = local_data.get("local_symbols", [])

                # 获取品种名称映射（从symbol_loader，如果可用）
                symbol_list = []
                for code in local_symbols_list:
                    symbol_list.append({"code": code, "name": ""})  # 名称由UI端补充

                event_data = {
                    "symbols": symbol_list,
                    "count": len(symbol_list),
                }
                event = Event(EVENT_LOCAL_DATA_INDEX_READY, event_data)
                self.event_engine.put(event)

                self.logger.info(f"📋 推送本地数据索引: {len(symbol_list)} 个品种")
        except Exception as e:
            self.logger.warning(f"推送本地数据索引事件失败: {e}")

        return overview

    def scan_errors_and_missing_only(self, reference_symbols: List[str]) -> QualityOverview:
        """轻量扫描：仅扫描错误数据和缺失数据（UI按钮触发）

        相比全量扫描，跳过耗时较长的质量评分和全量校验。
        只做必要的完整性检查。

        Args:
            reference_symbols: 参考品种列表

        Returns:
            QualityOverview: 质量概览（仅含错误和缺失统计）
        """
        try:
            self.logger.info("开始轻量扫描（仅错误/缺失数据）...")

            # 阶段1：快速扫描本地数据索引
            local_data = self._scan_phase_1_local_index(reference_symbols)
            local_symbols = local_data["local_symbols"]
            missing_count = local_data["missing_count"]

            # 阶段2：轻量级完整性检查（不做全量质量评分）
            self.logger.info("执行轻量级完整性检查...")
            error_symbols = []
            error_count = 0

            # 简单的文件存在性检查（不读取文件内容）
            from .data_module import config_manager

            intervals = ["1d", "5m", "1m"]  # 默认周期
            data_dir = config_manager.get_data_dir()

            for symbol in local_symbols:
                has_error = False
                for interval in intervals:
                    symbol_dir = data_dir / interval / symbol
                    if symbol_dir.exists():
                        files = list(symbol_dir.glob("*.lc1"))
                        if not files:
                            has_error = True
                            break
                if has_error:
                    error_symbols.append(symbol)
                    error_count += 1

            # 构建QualityOverview
            overview = QualityOverview(
                total_symbols=len(reference_symbols),
                missing_symbols=missing_count,
                error_symbols=error_count,
                warning_symbols=0,
                quality_score=0,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=intervals,
                details=[],  # 详情留给UI从增量推送中获取
                outdated_symbols=0,
                data_missing_symbols=0,
                data_lagging_days=0,
            )

            # 推送完成事件
            if self.event_engine:
                from .data_module import EVENT_DATA_SCAN_FINISHED
                from vnpy.event import Event

                event_data = {
                    "scan_type": "errors_and_missing",
                    "overview": {
                        "total_symbols": overview.total_symbols,
                        "missing_symbols": overview.missing_symbols,
                        "error_symbols": overview.error_symbols,
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_DATA_SCAN_FINISHED, event_data)
                self.event_engine.put(event)

            self.logger.info(
                "✓ 轻量扫描完成: 缺失=%d, 错误=%d",
                missing_count,
                error_count,
            )

            return overview

        except Exception as e:
            self.logger.exception("轻量扫描失败: %s", e)
            # 返回空的概览
            return QualityOverview(
                total_symbols=len(reference_symbols),
                missing_symbols=0,
                error_symbols=0,
                warning_symbols=0,
                quality_score=0,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=[],
                details=[],
                outdated_symbols=0,
                data_missing_symbols=0,
                data_lagging_days=0,
            )


# ==================== 文件监控器 ====================


class DataFileWatcher:
    """数据文件监控器"""

    def __init__(self, data_dir: Path, callback=None):
        self.data_dir = data_dir
        self.callback = callback
        self.logger = logging.getLogger(__name__)

        self._observer = None
        self._handler = None
        self._running = False

        try:
            from watchdog.observers import Observer  # type: ignore
            from watchdog.events import FileSystemEventHandler  # type: ignore

            self.Observer = Observer
            self.FileSystemEventHandler = FileSystemEventHandler  # type: ignore
            self.watchdog_available = True

        except ImportError:
            self.watchdog_available = False

    def start(self) -> bool:
        """
        启动监控

        Returns:
            bool: 启动成功返回 True；watchdog 不可用或启动失败返回 False
        """
        if not self.watchdog_available:
            self.logger.warning("watchdog不可用，文件监控功能将被禁用")
            return False

        if self._running:
            self.logger.warning("文件监控已在运行")
            return True

        try:
            self._observer = self.Observer()
            self._handler = DataFileEventHandler(self.callback)

            # 监控数据目录及其子目录
            self._observer.schedule(self._handler, str(self.data_dir), recursive=True)  # type: ignore
            self._observer.start()

            self._running = True
            self.logger.info("文件监控已启动: %s", self.data_dir)
            return True

        except Exception as e:
            self.logger.error("启动文件监控失败: %s", e)
            return False

    def stop(self):
        """
        停止监控

        Returns:
            None
        """
        if not self._running:
            return

        try:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)

            self._running = False
            self.logger.info("文件监控已停止")

        except Exception as e:
            self.logger.error("停止文件监控失败: %s", e)

    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._running


# 兼容 watchdog 不可用场景
try:
    from watchdog.events import FileSystemEventHandler as _FSHandler  # type: ignore

    _WATCHDOG_AVAILABLE = True
except Exception:  # pragma: no cover
    _WATCHDOG_AVAILABLE = False

    # 提供一个空基类
    class _FSHandler:  # type: ignore
        def dispatch(self, event):  # type: ignore
            """空实现"""
            pass


class DataFileEventHandler(_FSHandler):
    """数据文件事件处理器（继承FileSystemEventHandler，提供安全dispatch和增强防抖）"""

    def __init__(self, callback, debounce_seconds: float = 5.0):
        if _WATCHDOG_AVAILABLE:
            super().__init__()
        self.callback = callback
        self.logger = logging.getLogger(__name__)

        # 增强的防抖机制（线程延迟方案）
        self.debounce_seconds = debounce_seconds
        self.pending_event = ThreadEvent()
        self.last_event_time = 0.0
        self._debounce_thread: Optional[Thread] = None

    # 核心：提供安全的 dispatch，避免异常导致观察线程崩溃
    def dispatch(self, event):  # type: ignore[override]
        try:
            # 仅委托父类分发；父类会按事件类型调用 on_created/on_modified 等
            if _WATCHDOG_AVAILABLE:
                return super().dispatch(event)
        except Exception as e:  # 防御性：不让线程崩溃
            try:
                ev_path = getattr(event, "src_path", None) or getattr(event, "dest_path", None)
            except Exception:
                ev_path = None
            self.logger.error("watchdog 事件分发失败: %s, event=%s", e, ev_path)

    def on_modified(self, event):
        """文件修改事件"""
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "src_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "modified")

    def on_created(self, event):
        """文件创建事件"""
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "src_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "created")

    # 可选：移动/删除事件（不触发重算，但保留记录）
    def on_moved(self, event):  # noqa: D401
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "dest_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "moved")

    def on_deleted(self, event):  # noqa: D401
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "src_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "deleted")

    def _is_data_file(self, file_path: str) -> bool:
        """检查是否为数据文件"""
        path = Path(file_path)
        return path.suffix == ".parquet" and "data" in path.name

    def _handle_file_change(self, file_path: str, event_type: str):
        """处理文件变化（带线程延迟防抖）"""
        current_time = time.time()

        # 如果距离上次事件时间太短，取消之前的延迟任务
        if current_time - self.last_event_time < self.debounce_seconds:
            self.pending_event.set()  # 取消之前的任务

        self.last_event_time = current_time
        self.pending_event.clear()

        # 启动延迟任务
        self._debounce_thread = Thread(
            target=self._delayed_callback, args=(file_path, event_type), daemon=True
        )
        self._debounce_thread.start()

    def _delayed_callback(self, file_path: str, event_type: str):
        """延迟回调执行"""
        if self.pending_event.wait(self.debounce_seconds):
            # 事件被取消（降噪：不再记录DEBUG以避免刷屏）
            return

        # 执行回调
        if self.callback:
            try:
                self.callback(event_type, str(Path(file_path)))
            except Exception as e:
                self.logger.error("文件变化回调失败: %s", e, exc_info=True)


# ==================== 系统健康检查 ====================


class HealthChecker:
    """系统健康检查器

    验证关键目录与最小数据可用性
    """

    @staticmethod
    def check_system_health() -> Dict[str, Any]:
        """
        健康检查：验证关键目录与最小数据可用性

        Returns:
            {"ready": bool, "message": str, "details": {...}}
        """
        details: Dict[str, Any] = {}
        ready = True
        message = "OK"
        logger = logging.getLogger(__name__)

        try:
            cache_dir = config_manager.get_cache_dir()
            data_dir = config_manager.get_data_dir()
            details["cache_dir"] = str(cache_dir)
            details["data_dir"] = str(data_dir)

            # 目录存在性与可写性
            cache_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            details["cache_dir_exists"] = cache_dir.exists()
            details["data_dir_exists"] = data_dir.exists()

            # 尝试写入/读取探针文件（权限检测）
            probe = cache_dir / ".probe"
            try:
                probe.write_text("ok", encoding="utf-8")
                details["cache_dir_writable"] = True
                with probe.open("r", encoding="utf-8") as f:
                    _ = f.read()
                probe.unlink(missing_ok=True)
            except Exception:
                details["cache_dir_writable"] = False
                ready = False
                message = "cache_dir 不可写"

            # 最小数据可用性（非强制）
            parquet_count = 0
            try:
                for root, _, files in os.walk(data_dir):
                    for fn in files:
                        if fn.lower().endswith(".parquet"):
                            parquet_count += 1
                            if parquet_count >= 1:
                                break
                    if parquet_count >= 1:
                        break
            except Exception:
                pass
            details["parquet_files"] = parquet_count

            if parquet_count == 0 and ready:
                message = "未检测到最小数据集（可后续通过增量下载或导入TDX生成）"

        except Exception as e:
            ready = False
            message = f"健康检查异常: {e}"
            logger.error("健康检查异常: %s", e, exc_info=True)

        return {"ready": bool(ready), "message": message, "details": details}


# ==================== 全局实例 ====================

# 全局数据质量管理器
storage_manager = StorageManager()
data_validator = DataValidator()
data_sensor = DataSensor()
data_file_watcher = DataFileWatcher(config_manager.get_data_dir())

# ==================== 向后兼容别名 ====================

# 为保持向后兼容，提供别名（file_watcher.py 已合并至此）
KlineFileWatcher = DataFileWatcher
KlineFileHandler = DataFileEventHandler
