# -*- coding: utf-8 -*-
"""
data_module核心模块 - AI Debug友好的激进合并版

本文件合并了data_module_vnpy的核心基础设施组件：
- 第1部分：网络时间同步（原utils/network_time.py，240行）
- 第2部分：缓存管理（原cache_manager.py，302行）
- 第3部分：事件系统（原events.py，377行）
- 第4部分：配置管理（原config.py，774行）
- 第5部分：Qt工作线程（原validation_worker.py，114行）
- 第6部分：主引擎（原core.py，1613行）

合并优势：
- AI可一次性读取完整的核心模块逻辑
- 减少跨文件跳转，提升Debug效率
- 清晰的分区标记，易于定位
- 100% API兼容，所有导入路径保持有效

总行数：约3,420行
合并日期：2025-10-29
"""

# ==============================================================================
# 第1部分：网络时间同步模块（原 utils/network_time.py）
# ==============================================================================

"""
网络时间同步模块

提供从NTP服务器获取真实时间的功能，避免依赖不准确的系统时间。
用于数据新鲜度计算、缓存验证等场景。

核心功能：
1. 从NTP服务器同步时间（国内优先：阿里云、腾讯）
2. 缓存时间偏移量（1小时TTL）
3. 提供真实日期/时间查询接口
4. 失败降级策略（使用系统时间）
"""

# 可选依赖：如果ntplib不可用，降级到系统时间
try:
    import ntplib

    NTPLIB_AVAILABLE = True
except ImportError:
    NTPLIB_AVAILABLE = False
    ntplib = None  # type: ignore

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple
import threading

logger_network_time = logging.getLogger("backend.data_module.network_time")


class NetworkTimeSync:
    """网络时间同步器（线程安全单例）"""

    _instance = None
    _lock = threading.Lock()

    # 国内可靠的NTP服务器（按优先级排序）
    NTP_SERVERS = [
        "ntp.aliyun.com",  # 阿里云NTP（首选）
        "ntp.tencent.com",  # 腾讯NTP
        "cn.ntp.org.cn",  # 中国NTP服务器池
        "ntp1.aliyun.com",  # 阿里云备用1
        "ntp2.aliyun.com",  # 阿里云备用2
        "time.windows.com",  # Windows时间服务器（国际备用）
    ]

    def __init__(self):
        # 只有ntplib可用时才创建客户端
        if NTPLIB_AVAILABLE and ntplib is not None:
            self.ntp_client = ntplib.NTPClient()
        else:
            self.ntp_client = None

        # 缓存机制（避免频繁请求）
        self._cached_offset: Optional[float] = None  # 系统时间偏移量（秒）
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 3600  # 缓存1小时（3600秒）

        # 统计信息
        self._sync_count = 0
        self._sync_failures = 0
        self._last_sync_time: Optional[datetime] = None
        self._last_successful_server: Optional[str] = None

        # 线程安全锁
        self._sync_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """获取单例实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def sync_time(self, timeout: float = 3.0) -> Tuple[bool, Optional[float]]:
        """
        从NTP服务器同步时间

        Args:
            timeout: 请求超时时间（秒）

        Returns:
            (成功标志, 时间偏移量)
            偏移量: 网络时间 - 系统时间（秒）
        """
        # 如果ntplib不可用，直接返回失败
        if not NTPLIB_AVAILABLE or self.ntp_client is None:
            logger_network_time.warning("⚠️ ntplib不可用，无法进行网络时间同步")
            return False, None

        with self._sync_lock:
            for ntp_server in self.NTP_SERVERS:
                try:
                    logger_network_time.debug(f"尝试从 {ntp_server} 同步时间...")

                    # 发送NTP请求
                    response = self.ntp_client.request(ntp_server, version=3, timeout=timeout)

                    # 计算偏移量
                    offset = response.offset

                    # 更新缓存
                    self._cached_offset = offset
                    self._cache_timestamp = datetime.now()
                    self._sync_count += 1
                    self._last_sync_time = datetime.now()
                    self._last_successful_server = ntp_server

                    # 格式化偏移量信息
                    abs_offset = abs(offset)
                    direction = "慢" if offset > 0 else "快"

                    if abs_offset > 1.0:
                        logger_network_time.info(
                            f"✓ 时间同步成功: {ntp_server}, "
                            f"系统时间{direction}了 {abs_offset:.3f}秒"
                        )
                    else:
                        logger_network_time.info(
                            f"✓ 时间同步成功: {ntp_server}, " f"偏差 {abs_offset*1000:.1f}毫秒"
                        )

                    return True, offset

                except Exception as e:
                    logger_network_time.debug(f"从 {ntp_server} 同步失败: {type(e).__name__}: {e}")
                    continue

            # 所有服务器都失败
            self._sync_failures += 1
            logger_network_time.warning(
                f"⚠️ 时间同步失败，已尝试 {len(self.NTP_SERVERS)} 个NTP服务器"
            )
            return False, None

    def get_real_datetime(self) -> datetime:
        """
        获取真实的当前时间（网络时间）

        策略：
        1. 优先使用缓存的偏移量（1小时TTL）
        2. 缓存失效则重新同步
        3. 同步失败则降级使用系统时间

        Returns:
            datetime: 真实的当前时间
        """
        # 检查缓存是否有效
        if self._cached_offset is not None and self._cache_timestamp is not None:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()

            if cache_age < self._cache_ttl:
                # 使用缓存的偏移量修正系统时间
                real_time = datetime.now() + timedelta(seconds=self._cached_offset)
                logger_network_time.debug(
                    f"使用缓存的时间偏移: {self._cached_offset:.3f}秒 "
                    f"(缓存年龄: {cache_age:.1f}秒)"
                )
                return real_time

        # 缓存失效，重新同步
        logger_network_time.debug("时间偏移缓存失效，重新同步...")
        success, offset = self.sync_time()

        if success and offset is not None:
            # 同步成功，使用新的偏移量
            return datetime.now() + timedelta(seconds=offset)
        else:
            # 同步失败，降级使用系统时间
            logger_network_time.warning("⚠️ 时间同步失败，降级使用系统时间（可能不准确）")
            return datetime.now()

    def get_real_date(self) -> date:
        """
        获取真实的当前日期（网络时间）

        Returns:
            date: 真实的当前日期
        """
        real_datetime = self.get_real_datetime()
        return real_datetime.date()

    def get_offset(self) -> Optional[float]:
        """
        获取当前缓存的时间偏移量（秒）

        Returns:
            float: 时间偏移量（秒），未同步返回None
        """
        return self._cached_offset

    def is_synced(self) -> bool:
        """
        检查时间是否已同步

        Returns:
            bool: 已同步返回True
        """
        return self._cached_offset is not None

    def get_stats(self) -> dict:
        """
        获取同步统计信息

        Returns:
            dict: 统计信息字典
        """
        cache_age = None
        if self._cache_timestamp is not None:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()

        return {
            "sync_count": self._sync_count,
            "sync_failures": self._sync_failures,
            "last_sync_time": self._last_sync_time,
            "last_successful_server": self._last_successful_server,
            "cached_offset": self._cached_offset,
            "cache_age": cache_age,
            "cache_ttl": self._cache_ttl,
            "is_synced": self.is_synced(),
        }

    def force_sync(self) -> bool:
        """
        强制重新同步时间（忽略缓存）

        Returns:
            bool: 同步成功返回True
        """
        success, _ = self.sync_time()
        return success


# ==================== 全局便捷接口 ====================


def get_real_date() -> date:
    """
    获取真实的当前日期（网络时间）

    这是最常用的接口，用于替代 date.today()

    Returns:
        date: 真实的当前日期
    """
    sync = NetworkTimeSync.get_instance()
    return sync.get_real_date()


def get_real_datetime() -> datetime:
    """
    获取真实的当前时间（网络时间）

    用于替代 datetime.now()

    Returns:
        datetime: 真实的当前时间
    """
    sync = NetworkTimeSync.get_instance()
    return sync.get_real_datetime()


def sync_network_time(force: bool = False) -> bool:
    """
    手动触发时间同步

    Args:
        force: 是否强制同步（忽略缓存）

    Returns:
        bool: 同步成功返回True
    """
    sync = NetworkTimeSync.get_instance()

    if force:
        return sync.force_sync()
    else:
        success, _ = sync.time()
        return success


def get_time_stats() -> dict:
    """
    获取时间同步统计信息

    Returns:
        dict: 统计信息
    """
    sync = NetworkTimeSync.get_instance()
    return sync.get_stats()


# ==============================================================================
# 第2部分：缓存管理模块（原 cache_manager.py）
# ==============================================================================

"""
统一缓存管理器

实现次日0时失效策略的缓存管理机制。
所有缓存文件格式统一为：
{
    "cache_date": "YYYY-MM-DD",
    "data": { ... }
}

v1.1 改进：
- 使用网络时间替代系统时间，避免系统时间不准确导致的缓存验证错误
"""

import json
from pathlib import Path
from typing import Any, Dict

logger_cache = logging.getLogger("backend.data_module.cache")


class DailyCacheManager:
    """
    统一缓存管理器（静态工具类）

    提供基于日期的缓存失效机制：
    - 次日0时自动失效
    - 统一的缓存文件格式
    - 线程安全的读写操作
    """

    @classmethod
    def _get_cache_dir(cls) -> Path:
        """动态获取缓存目录（绝对路径）

        优先从 config_manager 获取，确保使用用户配置的绝对路径
        """
        try:
            # 延迟导入避免循环依赖
            from backend.infrastructure.data_module_vnpy.data_module import config_manager

            return config_manager.get_cache_dir()
        except Exception:
            # 降级方案：使用 get_project_root()
            from backend.infrastructure.data_module_vnpy.data_module import get_project_root

            cache_dir = get_project_root() / "data" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir

    @staticmethod
    def get_today() -> str:
        """获取今天的日期字符串（使用网络时间）

        使用网络时间同步，避免系统时间不准确导致的缓存验证错误

        Returns:
            str: YYYY-MM-DD格式的日期字符串
        """
        return get_real_date().isoformat()

    @staticmethod
    def is_cache_valid(cache_date: Optional[str]) -> bool:
        """判断缓存是否有效（次日0时失效，使用网络时间）

        使用网络时间同步，避免系统时间不准确导致的误判

        Args:
            cache_date: 缓存日期（YYYY-MM-DD格式）

        Returns:
            bool: True=有效，False=失效
        """
        if not cache_date:
            return False

        try:
            cached = datetime.strptime(cache_date, "%Y-%m-%d").date()
            # 使用网络时间替代系统时间
            today = get_real_date()

            # 只有当天的缓存才有效
            return cached >= today

        except (ValueError, TypeError):
            return False

    @classmethod
    def save_with_date(cls, data: Any, cache_file: str, cache_date: Optional[str] = None) -> bool:
        """保存数据到缓存文件（带日期）

        Args:
            data: 要缓存的数据
            cache_file: 缓存文件名（相对于cache_dir）
            cache_date: 缓存日期（默认今天）

        Returns:
            bool: 是否保存成功
        """
        try:
            # 获取缓存目录（绝对路径）
            cache_dir = cls._get_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)

            # 构建缓存对象
            cache_obj = {"cache_date": cache_date or cls.get_today(), "data": data}

            # 写入文件
            cache_path = cache_dir / cache_file
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_obj, f, ensure_ascii=False, indent=2, default=str)

            logger_cache.debug("缓存已保存: %s (日期: %s)", cache_file, cache_obj["cache_date"])
            return True

        except Exception as e:
            logger_cache.error("保存缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return False

    @classmethod
    def load_with_validation(
        cls, cache_file: str, validate_date: bool = True
    ) -> Tuple[Optional[Any], Optional[str], bool]:
        """加载缓存并验证日期

        Args:
            cache_file: 缓存文件名（相对于cache_dir）
            validate_date: 是否验证日期（默认True）

        Returns:
            Tuple[data, cache_date, is_valid]:
            - data: 缓存的数据（None表示不存在）
            - cache_date: 缓存日期
            - is_valid: 是否有效（True=有效，False=失效）
        """
        try:
            # 获取缓存目录（绝对路径）
            cache_dir = cls._get_cache_dir()
            cache_path = cache_dir / cache_file

            # 检查文件是否存在
            if not cache_path.exists():
                logger_cache.debug("缓存文件不存在: %s", cache_file)
                return None, None, False

            # 读取文件
            with open(cache_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

                # 处理空文件
                if not content:
                    logger_cache.warning("缓存文件为空: %s", cache_file)
                    return None, None, False

                try:
                    cache_obj = json.loads(content)
                except json.JSONDecodeError as e:
                    logger_cache.warning("缓存文件JSON格式错误: %s (%s)", cache_file, e)
                    return None, None, False

            # 提取数据和日期
            data = cache_obj.get("data")
            cache_date = cache_obj.get("cache_date")

            # 验证日期
            if validate_date:
                is_valid = cls.is_cache_valid(cache_date)
                # 架构修复：移除高频DEBUG日志，避免刷屏
                if not is_valid:
                    logger_cache.warning("缓存已失效: %s (日期: %s)", cache_file, cache_date)
            else:
                is_valid = True  # 不验证则认为有效

            return data, cache_date, is_valid

        except Exception as e:
            logger_cache.error("加载缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return None, None, False

    @classmethod
    def delete_cache(cls, cache_file: str) -> bool:
        """删除缓存文件

        Args:
            cache_file: 缓存文件名

        Returns:
            bool: 是否删除成功
        """
        try:
            cache_dir = cls._get_cache_dir()
            cache_path = cache_dir / cache_file
            if cache_path.exists():
                cache_path.unlink()
                logger_cache.info("缓存已删除: %s", cache_file)
                return True
            return False

        except Exception as e:
            logger_cache.error("删除缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return False

    @classmethod
    def get_cache_info(cls, cache_file: str) -> Dict[str, Any]:
        """获取缓存文件信息

        Args:
            cache_file: 缓存文件名

        Returns:
            Dict: 缓存信息 {
                "exists": bool,
                "cache_date": str,
                "is_valid": bool,
                "file_size": int (bytes),
                "modified_time": str
            }
        """
        cache_dir = cls._get_cache_dir()
        cache_path = cache_dir / cache_file

        if not cache_path.exists():
            return {
                "exists": False,
                "cache_date": None,
                "is_valid": False,
                "file_size": 0,
                "modified_time": None,
            }

        try:
            # 读取缓存日期
            _, cache_date, is_valid = cls.load_with_validation(cache_file)

            # 文件统计信息
            stat = cache_path.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime).isoformat()

            return {
                "exists": True,
                "cache_date": cache_date,
                "is_valid": is_valid,
                "file_size": stat.st_size,
                "modified_time": modified_time,
            }

        except Exception:
            return {
                "exists": True,
                "cache_date": None,
                "is_valid": False,
                "file_size": 0,
                "modified_time": None,
            }


# 便捷函数（供快速调用）


def is_cache_valid(cache_date: Optional[str]) -> bool:
    """判断缓存日期是否有效（便捷函数）"""
    return DailyCacheManager.is_cache_valid(cache_date)


def get_today() -> str:
    """获取今天的日期字符串（便捷函数）"""
    return DailyCacheManager.get_today()


def save_cache(data: Any, cache_file: str) -> bool:
    """保存缓存（便捷函数）"""
    return DailyCacheManager.save_with_date(data, cache_file)


def load_cache(cache_file: str) -> Tuple[Optional[Any], Optional[str], bool]:
    """加载缓存（便捷函数）"""
    return DailyCacheManager.load_with_validation(cache_file)


# ==============================================================================
# 第3部分：事件系统模块（原 events.py）
# ==============================================================================

"""
事件工具模块

提供vnpy事件推送的通用工具类和方法
"""

from vnpy.event import Event, EventEngine

logger_events = logging.getLogger("backend.data_module.events")


# ==================== 事件类型常量 ====================

EVENT_CHINASTOCK_LOG = "eChinaStockLog"
EVENT_CHINASTOCK_VALIDATION = "eChinaStockValidation"
EVENT_CHINASTOCK_FILE_CHANGE = "eChinaStockFileChange"
EVENT_CHINASTOCK_DOWNLOAD = "eChinaStockDownload"
EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"
EVENT_DATA_SCAN_COMPLETE = "eDataScanComplete"
EVENT_LOCAL_DATA_INDEX_READY = "eLocalDataIndexReady"

# 数据质量感知阶段性推送事件
EVENT_QUALITY_SCAN_PHASE = "eQualityScanPhase"
EVENT_QUALITY_METRIC_UPDATE = "eQualityMetricUpdate"

# 协程性能监控事件
EVENT_ASYNCIO_METRICS = "eAsyncioMetrics"

# 新增事件类型（8步流程改造）
EVENT_DATA_METRICS_UPDATED = "eDataMetricsUpdated"
EVENT_INVALID_SYMBOLS_UPDATED = "eInvalidSymbolsUpdated"
EVENT_FILE_WATCHER_STARTED = "eFileWatcherStarted"
EVENT_DATA_SCAN_FINISHED = "eDataScanFinished"

# 8步验证流程事件
EVENT_SYMBOL_CACHE_LOADED = "eSymbolCacheLoaded"
EVENT_IPO_CACHE_UPDATED = "eIPOCacheUpdated"
EVENT_VALIDATION_COMPLETED = "eValidationCompleted"

# 应用名称
APP_NAME = "ChinaStock"


# ==================== 事件发布器基类 ====================


class EventPublisher:
    """通用事件发布器基类"""

    def __init__(self, event_engine: Optional[EventEngine] = None, app_name: str = APP_NAME):
        """
        初始化事件发布器

        Args:
            event_engine: vnpy事件引擎
            app_name: 应用名称
        """
        self.event_engine = event_engine
        self.app_name = app_name
        self.logger = logger_events

    def push_log_event(self, message: str, level: str = "INFO") -> None:
        """
        推送日志事件

        Args:
            message: 日志消息
            level: 日志级别
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "message": message,
                "level": level,
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_LOG, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送日志事件失败: %s", e)


# ==================== 校验事件发布器 ====================


class ValidationEventPublisher(EventPublisher):
    """校验事件发布器"""

    def push_validation_event(self, summary) -> None:
        """
        推送校验事件

        Args:
            summary: 校验汇总对象（ValidationSummary）
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "summary": {
                    "total_symbols": summary.total_symbols,
                    "valid_symbols": summary.valid_symbols,
                    "invalid_symbols": summary.invalid_symbols,
                    "total_errors": summary.total_errors,
                    "total_warnings": summary.total_warnings,
                    "check_time": summary.check_time.isoformat(),
                    "base_date": summary.base_date.isoformat(),
                },
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_VALIDATION, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送校验事件失败: %s", e)


# ==================== 下载事件发布器 ====================


class DownloadEventPublisher(EventPublisher):
    """下载事件发布器"""

    def push_download_event(
        self, download_type: str, status: str, count: int, error: Optional[str] = None
    ) -> None:
        """
        推送下载事件

        Args:
            download_type: 下载类型
            status: 状态
            count: 数量
            error: 错误信息
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "download_type": download_type,
                "status": status,
                "count": count,
                "error": error,
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_DOWNLOAD, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送下载事件失败: %s", e)

    def push_download_progress_event(
        self, download_type: str, progress_pct: float, completed: int, total: int, current_item: str
    ) -> None:
        """
        推送下载进度事件

        Args:
            download_type: 下载类型
            progress_pct: 进度百分比
            completed: 已完成数量
            total: 总数量
            current_item: 当前项目
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "download_type": download_type,
                "status": "progress",
                "progress": progress_pct,
                "completed": completed,
                "total": total,
                "current_item": current_item,
                "timestamp": datetime.now(),
                "engine": self.app_name,
            }

            event = Event(EVENT_CHINASTOCK_DOWNLOAD, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送下载进度事件失败: %s", e)


# ==================== 数据质量事件发布器 ====================


class QualityEventPublisher(EventPublisher):
    """数据质量事件发布器"""

    def push_quality_update_event(self, overview) -> None:
        """
        推送数据质量更新事件

        Args:
            overview: 质量概览对象（QualityOverview）
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "quality_score": overview.quality_score,
                "total_symbols": overview.total_symbols,
                "local_symbols": overview.total_symbols - overview.missing_symbols,
                "missing_symbols": overview.missing_symbols,
                "error_symbols": overview.error_symbols,
                "warning_symbols": overview.warning_symbols,
                "last_scan_time": overview.last_scan_time.isoformat(),
                "timestamp": datetime.now(),
                "engine": self.app_name,
                # 添加所有必要字段
                "outdated_symbols": getattr(overview, "outdated_symbols", 0),
                "avg_gap_days": getattr(overview, "avg_gap_days", 0),
                "data_missing_symbols": getattr(overview, "data_missing_symbols", 0),
                "data_lagging_days": getattr(overview, "data_lagging_days", 0),
                "details": getattr(overview, "details", []),
            }

            event = Event(EVENT_DATA_QUALITY_UPDATE, event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("推送数据质量事件失败: %s", e)


# ==================== 协程性能监控发布器 ====================


class AsyncioMetricsPublisher(EventPublisher):
    """协程性能指标发布器

    用于测量和上报 asyncio 事件循环延迟，帮助判断协程是否排队。
    """

    async def measure_and_publish_lag(self, source: str, threshold_ms: float = 5.0) -> float:
        """测量事件循环延迟并在超过阈值时上报

        v3.4 改进：综合测量协程排队情况
        1. 测量调度延迟（schedule lag）
        2. 统计pending tasks数量（真正的排队指标）
        3. 测量事件循环响应时间

        Args:
            source: 指标来源（模块名）
            threshold_ms: 上报阈值（毫秒），只在延迟超过此值时上报

        Returns:
            测量的延迟值（毫秒）
        """
        import time
        import asyncio

        # 1. 测量调度延迟
        start = time.perf_counter()
        await asyncio.sleep(0)
        schedule_lag_ms = (time.perf_counter() - start) * 1000

        # 2. 统计pending tasks数量
        try:
            loop = asyncio.get_running_loop()
            all_tasks = asyncio.all_tasks(loop)

            # 统计各状态的task
            pending_count = 0
            done_count = 0

            for task in all_tasks:
                if task.done():
                    done_count += 1
                elif not task.cancelled():
                    pending_count += 1

            # 3. 测量事件循环响应时间
            callback_start = time.perf_counter()
            callback_done = asyncio.Future()

            def callback_measure():
                if not callback_done.done():
                    callback_done.set_result(time.perf_counter() - callback_start)

            loop.call_soon(callback_measure)

            try:
                callback_lag_s = await asyncio.wait_for(callback_done, timeout=1.0)
                callback_lag_ms = callback_lag_s * 1000
            except asyncio.TimeoutError:
                callback_lag_ms = 1000.0

            # 计算综合延迟指标
            queue_pressure_ms = (pending_count / 100) * 10
            lag_ms = max(schedule_lag_ms, callback_lag_ms) + queue_pressure_ms

            # 只在延迟超过阈值时上报
            if lag_ms > threshold_ms and self.event_engine:
                try:
                    event_data = {
                        "event_loop_lag_ms": round(lag_ms, 3),
                        "schedule_lag_ms": round(schedule_lag_ms, 3),
                        "callback_lag_ms": round(callback_lag_ms, 3),
                        "pending_tasks": pending_count,
                        "done_tasks": done_count,
                        "total_tasks": len(all_tasks),
                        "queue_pressure_ms": round(queue_pressure_ms, 3),
                        "source": source,
                        "timestamp": datetime.now().isoformat(),
                        "engine": self.app_name,
                    }
                    event = Event(EVENT_ASYNCIO_METRICS, event_data)
                    self.event_engine.put(event)
                except Exception as e:
                    self.logger.error("推送协程性能指标失败: %s", e)

            return lag_ms

        except Exception as e:
            self.logger.error("测量事件循环延迟失败: %s", e)
            return schedule_lag_ms


# ==============================================================================
# 第4部分：配置管理模块（原 config.py）
# ==============================================================================

"""
配置管理模块

负责管理data_module_vnpy的所有配置项，包括：
- 品种列表缓存路径
- K线数据存储路径
- 通达信软件根目录和配置文件
- 数据感知基日
- 其他运行时配置

合并来源：config.py + config_file_parser.py
"""

from contextlib import suppress
from typing import List
import re

from vnpy.trader.setting import SETTINGS, SETTING_FILENAME
from vnpy.trader.utility import load_json, save_json

logger_config = logging.getLogger("backend.data_module.config")


def get_project_root() -> Path:
    """获取项目根目录

    从当前文件向上查找，直到找到真正的项目根目录标记文件
    优先查找 pyproject.toml 和 venv310 目录（项目特有），避免被子模块的 requirements.txt 误导
    """
    current = Path(__file__).resolve().parent

    # 向上查找，最多10层
    for _ in range(10):
        # 优先级1：pyproject.toml 或 venv310 目录（最可靠）
        if (current / "pyproject.toml").exists() or (current / "venv310").exists():
            return current

        # 优先级2：检查是否同时有 requirements.txt 和 ui 目录（避免子模块干扰）
        if (current / "requirements.txt").exists() and (current / "ui").exists():
            return current

        parent = current.parent
        if parent == current:  # 到达根目录
            break
        current = parent

    # 如果没找到，返回当前工作目录
    return Path.cwd()


class TdxConfigFileParser:
    """通达信配置文件解析器

    合并自 config_file_parser.py
    """

    # 类级别缓存：避免重复搜索配置文件（启动优化）
    _config_path_cache: Dict[str, Optional[Path]] = {}

    def __init__(self, tdx_dir: Optional[Path] = None):
        """
        初始化配置文件解析器

        Args:
            tdx_dir: 通达信软件根目录，如果为None则自动查找
        """
        self.tdx_dir = tdx_dir
        self.tdxstat2_path: Optional[Path] = None
        self.addedcode_bj_path: Optional[Path] = None
        self._find_config_files()

    def _find_config_files(self) -> None:
        """查找配置文件（递归搜索，带缓存优化）"""
        # 优化：先检查缓存，避免重复搜索
        tdx_dir_key = str(self.tdx_dir) if self.tdx_dir else "default"
        cache_key_tdxstat2 = f"{tdx_dir_key}:tdxstat2.cfg"
        cache_key_addedcode = f"{tdx_dir_key}:addedcode_bj.cfg"

        if cache_key_tdxstat2 in self._config_path_cache:
            self.tdxstat2_path = self._config_path_cache[cache_key_tdxstat2]
            logger_config.debug("✓ 使用缓存的tdxstat2.cfg路径")

        if cache_key_addedcode in self._config_path_cache:
            self.addedcode_bj_path = self._config_path_cache[cache_key_addedcode]
            logger_config.debug("✓ 使用缓存的addedcode_bj.cfg路径")

        # 如果缓存中都有且有效，直接返回
        if (
            self.tdxstat2_path
            and self.tdxstat2_path.exists()
            and self.addedcode_bj_path
            and self.addedcode_bj_path.exists()
        ):
            return

        # 缓存未命中或文件不存在，执行搜索
        if self.tdx_dir and self.tdx_dir.exists():
            # 在指定目录下递归搜索
            self._search_config_files_in_dir(self.tdx_dir)
            if self.tdxstat2_path and self.addedcode_bj_path:
                # 更新缓存
                self._config_path_cache[cache_key_tdxstat2] = self.tdxstat2_path
                self._config_path_cache[cache_key_addedcode] = self.addedcode_bj_path
                return

        # 如果未指定路径或搜索失败，尝试常见根目录并递归搜索
        common_root_dirs = [
            Path("C:/new_tdx"),
            Path("C:/通达信金融终端V7"),
            Path("C:/Program Files/通达信金融终端V7"),
            Path("D:/通达信金融终端V7"),
            Path("C:/tdx"),
            Path("D:/tdx"),
        ]

        for root_dir in common_root_dirs:
            if root_dir.exists() and self._search_config_files_in_dir(root_dir):
                # 更新缓存
                if self.tdxstat2_path:
                    self._config_path_cache[cache_key_tdxstat2] = self.tdxstat2_path
                if self.addedcode_bj_path:
                    self._config_path_cache[cache_key_addedcode] = self.addedcode_bj_path
                break

    def _search_config_files_in_dir(self, directory: Path) -> bool:
        """
        在指定目录下递归搜索配置文件

        Args:
            directory: 要搜索的目录

        Returns:
            是否找到所有配置文件
        """
        try:
            logger_config.info("正在递归搜索 %s 目录下的配置文件...", directory)

            # 搜索 tdxstat2.cfg
            if not self.tdxstat2_path:
                for file in directory.rglob("tdxstat2.cfg"):
                    if file.is_file():
                        self.tdxstat2_path = file
                        logger_config.info("✓ 找到 tdxstat2.cfg: %s", file)
                        break

            # 搜索 addedcode_bj.cfg
            if not self.addedcode_bj_path:
                for file in directory.rglob("addedcode_bj.cfg"):
                    if file.is_file():
                        self.addedcode_bj_path = file
                        logger_config.info("✓ 找到 addedcode_bj.cfg: %s", file)
                        break

            # 如果都找到了，返回True
            if self.tdxstat2_path and self.addedcode_bj_path:
                return True

            if not self.tdxstat2_path:
                logger_config.warning("在 %s 目录下未找到 tdxstat2.cfg 文件", directory)
            if not self.addedcode_bj_path:
                logger_config.warning("在 %s 目录下未找到 addedcode_bj.cfg 文件", directory)

            return False

        except OSError as e:
            logger_config.warning("搜索 %s 时发生错误: %s", directory, e)
            return False

    def parse_tdxstat2(self) -> Dict[int, List[str]]:
        """
        解析tdxstat2.cfg文件，获取可转债代码

        实际文件为管道分隔：如 market|code|date|...
        - 取第二列为6位代码
        - 代码以11开头 -> 市场1；以12开头 -> 市场0
        """
        if not self.tdxstat2_path or not self.tdxstat2_path.exists():
            logger_config.warning("tdxstat2.cfg 文件不存在，返回空字典")
            return {0: [], 1: []}

        result: Dict[int, List[str]] = {0: [], 1: []}
        total_lines = 0
        parsed = 0

        try:
            # 使用GBK读取
            with open(self.tdxstat2_path, "r", encoding="gbk", errors="ignore") as f:
                for raw in f:
                    total_lines += 1
                    line = raw.strip()
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        code = parts[1].strip()
                        if code.isdigit() and len(code) == 6:
                            if code.startswith("11"):
                                result[1].append(code)
                                parsed += 1
                            elif code.startswith("12"):
                                result[0].append(code)
                                parsed += 1

            logger_config.info(
                "成功解析 tdxstat2.cfg: market0=%d, market1=%d, 总行=%d, 命中=%d",
                len(result[0]),
                len(result[1]),
                total_lines,
                parsed,
            )
            return result

        except Exception as e:
            logger_config.error("解析 tdxstat2.cfg 失败: %s", e, exc_info=True)
            return {0: [], 1: []}

    def parse_addedcode_bj(self) -> List[Dict[str, str]]:
        """
        解析addedcode_bj.cfg（GBK）：实际格式多为
        44|原代码|北证代码|名称|日期
        - 取第3列为 920xxx（6位），第4列为名称（去除尾部括号注）
        - 若该格式不匹配，再回退到简单 "code|name" 或空白分隔的两列格式（9/8/4开头）
        """
        if not self.addedcode_bj_path or not self.addedcode_bj_path.exists():
            logger_config.warning("addedcode_bj.cfg 文件不存在，返回空列表")
            return []

        result = []
        used_new_format = 0

        try:
            with open(self.addedcode_bj_path, "r", encoding="gbk", errors="ignore") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split("|")]

                    # 优先解析 5 段及以上：44|orig|bj(920xxx)|name|date
                    if len(parts) >= 4 and parts[2].isdigit() and len(parts[2]) == 6:
                        bj_code = parts[2]
                        name = parts[3]
                        # 仅收集 920xxx（北证股票）
                        if bj_code.startswith("920"):
                            # 去除名称中的尾部括号注释
                            name_clean = re.sub(r"\(.*?\)$", "", name).strip()
                            result.append({"code": bj_code, "name": name_clean})
                            used_new_format += 1
                        continue

                    # 回退：两段或空白分隔（兼容旧历史数据）
                    if "|" not in line:
                        parts = [p.strip() for p in re.split(r"\s+", line) if p.strip()]
                    if len(parts) >= 2:
                        code = parts[0]
                        name = parts[1]
                        if code.isdigit() and len(code) == 6 and code.startswith(("9", "8", "4")):
                            name_clean = re.sub(r"\(.*?\)$", "", name).strip()
                            result.append({"code": code, "name": name_clean})

            logger_config.info(
                "成功解析 addedcode_bj.cfg: %d 个北交所股票（新格式匹配 %d 条）",
                len(result),
                used_new_format,
            )
            return result

        except Exception as e:
            logger_config.error("解析 addedcode_bj.cfg 失败: %s", e, exc_info=True)
            return []

    def is_available(self) -> bool:
        """
        检查配置文件是否可用

        Returns:
            是否可用
        """
        return (self.tdxstat2_path is not None and self.tdxstat2_path.exists()) or (
            self.addedcode_bj_path is not None and self.addedcode_bj_path.exists()
        )

    def get_file_info(self) -> Dict[str, Dict[str, str]]:
        """
        获取配置文件信息

        Returns:
            文件信息字典
        """
        info = {}

        if self.tdxstat2_path and self.tdxstat2_path.exists():
            info["tdxstat2.cfg"] = {
                "status": "可用",
                "path": str(self.tdxstat2_path),
                "size": f"{self.tdxstat2_path.stat().st_size / 1024:.2f} KB",
            }
        else:
            info["tdxstat2.cfg"] = {"status": "不可用", "path": ""}

        if self.addedcode_bj_path and self.addedcode_bj_path.exists():
            info["addedcode_bj.cfg"] = {
                "status": "可用",
                "path": str(self.addedcode_bj_path),
                "size": f"{self.addedcode_bj_path.stat().st_size / 1024:.2f} KB",
            }
        else:
            info["addedcode_bj.cfg"] = {"status": "不可用", "path": ""}

        return info


class ConfigManager:
    """配置管理器

    合并自 config.py
    """

    # 默认配置项
    DEFAULT_CONFIG = {
        "chinastock.cache_dir": "./data/cache",
        "chinastock.data_dir": "./data/kline",
        "chinastock.tdx_dir": "",
        "chinastock.base_date": "2020-01-01",
        "chinastock.max_workers": 10,
        "chinastock.timeout": 30,
        "chinastock.retry_times": 3,
        "chinastock.enable_watcher": True,
        "chinastock.watcher_interval": 5,
        # 多服务器并行下载配置
        "chinastock.server_pool_size": 5,
        # 服务器池管理器配置
        "chinastock.server_pool.server_count": None,
        "chinastock.server_pool.use_multiprocess": True,
        "chinastock.server_pool.max_coroutines_per_process": None,
        "chinastock.server_pool.update_interval": 600.0,
        # 热备服务器配置
        "chinastock.standby_servers.count": 30,
        "chinastock.standby_servers.warmup_timeout": 1.5,
        # 两段式下载配置
        "chinastock.two_phase_download.enabled": True,
        "chinastock.two_phase_download.threshold_ratio": 0.05,
        "chinastock.two_phase_download.min_threshold": 100,
        # 轮询数据源转换器配置
        "chinastock.polling_gateway.enabled": False,
        "chinastock.polling_gateway.interval": 60,
        # 虚拟推送数据网关配置
        "chinastock.virtual_gateway.enabled": False,
        "chinastock.virtual_gateway.start_datetime": "",
        "chinastock.virtual_gateway.speed": 1.0,
        # 数据标准化读取工具配置
        "chinastock.data_readers.tdx_root_dir": "C:/new_tdx",
        # 统一数据管理器与预加载配置
        "chinastock.unified_manager.enabled": True,
        "chinastock.unified_manager.auto_download": False,
        "chinastock.preload.enabled": True,
        "chinastock.preload.auto_start": False,
        "chinastock.preload.max_cache_symbols": 64,
        "chinastock.preload.intervals": ["1d", "5m"],
        "chinastock.preload.frequently_used_symbols": [
            "000001",
            "000002",
            "600000",
            "600036",
            "600519",
        ],
        # 数据质量感知配置
        "chinastock.quality_scan.enable_adaptive": True,
        "chinastock.quality_scan.enable_detailed_scan": True,
        "chinastock.quality_scan.enable_incremental_push": True,
        "chinastock.quality_scan.min_push_interval_ms": 500,
        # 混合异步架构配置
        "chinastock.quality_scan.enable_hybrid_async": True,
        "chinastock.quality_scan.max_async_workers": 2000,
        "chinastock.quality_scan.max_thread_workers": 50,
        "chinastock.quality_scan.max_process_workers": 16,
        "chinastock.quality_scan.enable_dynamic_tuning": True,
        "chinastock.quality_scan.file_size_threshold_small_kb": 1024,
        "chinastock.quality_scan.file_size_threshold_large_kb": 10240,
    }

    def __init__(self):
        """初始化配置管理器"""
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """加载配置"""
        # 从默认配置开始
        self._config.update(self.DEFAULT_CONFIG)

        # 从vnpy全局设置加载
        for key, value in SETTINGS.items():
            if key.startswith("chinastock."):
                self._config[key] = value

        # 从vt_setting.json加载
        try:
            setting_data = load_json(SETTING_FILENAME)
            for key, value in setting_data.items():
                if key.startswith("chinastock."):
                    self._config[key] = value
        except Exception:
            pass

        # 新增：初始化时主动转换相对路径为绝对路径
        self._normalize_paths_on_init()

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        self._config[key] = value
        self._save_to_file()

    def _normalize_paths_on_init(self) -> None:
        """初始化时主动转换相对路径为绝对路径

        检查 cache_dir 和 data_dir 配置，如果是相对路径则转换为绝对路径并持久化
        """
        try:
            project_root = get_project_root()
            path_updated = False

            # 1. 检查并转换 cache_dir
            cache_dir_str = self._config.get("chinastock.cache_dir", "./data/cache")
            if cache_dir_str:
                cache_path = Path(cache_dir_str)
                if not cache_path.is_absolute():
                    abs_cache_path = project_root / cache_path
                    abs_cache_str = str(abs_cache_path.resolve())
                    self._config["chinastock.cache_dir"] = abs_cache_str
                    path_updated = True
                    print("\n🔧 初始化配置转换: 品种缓存目录")
                    print(f"   原配置: {cache_dir_str} (相对路径)")
                    print(f"   新配置: {abs_cache_str} (绝对路径)")

            # 2. 检查并转换 data_dir
            data_dir_str = self._config.get("chinastock.data_dir", "./data/kline")
            if data_dir_str:
                data_path = Path(data_dir_str)
                if not data_path.is_absolute():
                    abs_data_path = project_root / data_path
                    abs_data_str = str(abs_data_path.resolve())
                    self._config["chinastock.data_dir"] = abs_data_str
                    path_updated = True
                    print("🔧 初始化配置转换: K线数据目录")
                    print(f"   原配置: {data_dir_str} (相对路径)")
                    print(f"   新配置: {abs_data_str} (绝对路径)")

            # 3. 检查并转换 db_file
            db_file_str = self._config.get("chinastock.db_file", "./data/terminal.db")
            if db_file_str:
                db_path = Path(db_file_str)
                if not db_path.is_absolute():
                    abs_db_path = project_root / db_path
                    abs_db_str = str(abs_db_path.resolve())
                    self._config["chinastock.db_file"] = abs_db_str
                    path_updated = True
                    print("🔧 初始化配置转换: 数据库文件")
                    print(f"   原配置: {db_file_str} (相对路径)")
                    print(f"   新配置: {abs_db_str} (绝对路径)")

            # 4. 检查并转换 config_file
            config_file_str = self._config.get(
                "chinastock.config_file", "./config/terminal_config.json"
            )
            if config_file_str:
                config_path = Path(config_file_str)
                if not config_path.is_absolute():
                    abs_config_path = project_root / config_path
                    abs_config_str = str(abs_config_path.resolve())
                    self._config["chinastock.config_file"] = abs_config_str
                    path_updated = True
                    print("🔧 初始化配置转换: 终端配置文件")
                    print(f"   原配置: {config_file_str} (相对路径)")
                    print(f"   新配置: {abs_config_str} (绝对路径)")

            # 5. 检查并转换 logs_dir
            logs_dir_str = self._config.get("chinastock.logs_dir", "./logs")
            if logs_dir_str:
                logs_path = Path(logs_dir_str)
                if not logs_path.is_absolute():
                    abs_logs_path = project_root / logs_path
                    abs_logs_str = str(abs_logs_path.resolve())
                    self._config["chinastock.logs_dir"] = abs_logs_str
                    path_updated = True
                    print("🔧 初始化配置转换: 日志目录")
                    print(f"   原配置: {logs_dir_str} (相对路径)")
                    print(f"   新配置: {abs_logs_str} (绝对路径)")

            # 6. 如果有路径更新，保存到配置文件
            if path_updated:
                print(f"   项目根目录: {project_root}")
                print("✅ 配置已自动转换并持久化\n")
                self._save_to_file()
                logger_config.info("路径配置已在初始化时转换为绝对路径并持久化")

        except Exception as e:
            logger_config.warning("初始化路径转换失败: %s", e)

    def get_cache_dir(self) -> Path:
        """获取品种列表缓存目录

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        cache_dir_str = self.get("chinastock.cache_dir", "./data/cache")
        cache_dir = Path(cache_dir_str)

        # 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not cache_dir.is_absolute():
            project_root = get_project_root()
            cache_dir = project_root / cache_dir
            abs_path_str = str(cache_dir.resolve())
            self._config["chinastock.cache_dir"] = abs_path_str
            self._save_to_file()
            logger_config.warning(
                "检测到相对路径配置，已转换: %s -> %s", cache_dir_str, abs_path_str
            )

        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_data_dir(self) -> Path:
        """获取K线数据存储目录

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        data_dir_str = self.get("chinastock.data_dir", "./data/kline")
        data_dir = Path(data_dir_str)

        # 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not data_dir.is_absolute():
            project_root = get_project_root()
            data_dir = project_root / data_dir
            abs_path_str = str(data_dir.resolve())
            self._config["chinastock.data_dir"] = abs_path_str
            self._save_to_file()
            logger_config.warning(
                "检测到相对路径配置，已转换: %s -> %s", data_dir_str, abs_path_str
            )

        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_db_file(self) -> Path:
        """获取数据库文件路径

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        db_file_str = self.get("chinastock.db_file", "./data/terminal.db")
        db_file = Path(db_file_str)

        # 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not db_file.is_absolute():
            project_root = get_project_root()
            db_file = project_root / db_file
            abs_path_str = str(db_file.resolve())
            self._config["chinastock.db_file"] = abs_path_str
            self._save_to_file()
            logger_config.warning("检测到相对路径配置，已转换: %s -> %s", db_file_str, abs_path_str)

        db_file.parent.mkdir(parents=True, exist_ok=True)
        return db_file

    def get_config_file(self) -> Path:
        """获取终端配置文件路径

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        config_file_str = self.get("chinastock.config_file", "./config/terminal_config.json")
        config_file = Path(config_file_str)

        # 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not config_file.is_absolute():
            project_root = get_project_root()
            config_file = project_root / config_file
            abs_path_str = str(config_file.resolve())
            self._config["chinastock.config_file"] = abs_path_str
            self._save_to_file()
            logger_config.warning(
                "检测到相对路径配置，已转换: %s -> %s", config_file_str, abs_path_str
            )

        config_file.parent.mkdir(parents=True, exist_ok=True)
        return config_file

    def get_logs_dir(self) -> Path:
        """获取日志目录

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        logs_dir_str = self.get("chinastock.logs_dir", "./logs")
        logs_dir = Path(logs_dir_str)

        # 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not logs_dir.is_absolute():
            project_root = get_project_root()
            logs_dir = project_root / logs_dir
            abs_path_str = str(logs_dir.resolve())
            self._config["chinastock.logs_dir"] = abs_path_str
            self._save_to_file()
            logger_config.warning(
                "检测到相对路径配置，已转换: %s -> %s", logs_dir_str, abs_path_str
            )

        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def get_tdx_dir(self) -> Optional[Path]:
        """获取通达信软件根目录"""
        tdx_dir = self.get("chinastock.tdx_dir", "")
        if tdx_dir and Path(tdx_dir).exists():
            return Path(tdx_dir)
        return None

    def get_base_date(self) -> date:
        """获取数据感知基日"""
        base_date_str = self.get("chinastock.base_date", "2020-01-01")
        try:
            return datetime.strptime(base_date_str, "%Y-%m-%d").date()
        except ValueError:
            return date(2020, 1, 1)

    def get_max_workers(self) -> int:
        """获取最大工作线程数"""
        return int(self.get("chinastock.max_workers", 10))

    def get_timeout(self) -> int:
        """获取请求超时时间（秒）"""
        return int(self.get("chinastock.timeout", 30))

    def get_retry_times(self) -> int:
        """获取重试次数"""
        return int(self.get("chinastock.retry_times", 3))

    def is_watcher_enabled(self) -> bool:
        """是否启用文件监控"""
        return bool(self.get("chinastock.enable_watcher", True))

    def get_watcher_interval(self) -> int:
        """获取文件监控间隔（秒）"""
        return int(self.get("chinastock.watcher_interval", 5))

    def is_polling_gateway_enabled(self) -> bool:
        """是否启用轮询数据源转换器"""
        return bool(self.get("chinastock.polling_gateway.enabled", False))

    def get_polling_interval(self) -> int:
        """获取轮询间隔（秒）"""
        return int(self.get("chinastock.polling_gateway.interval", 60))

    def is_virtual_gateway_enabled(self) -> bool:
        """是否启用虚拟推送数据网关"""
        return bool(self.get("chinastock.virtual_gateway.enabled", False))

    def get_virtual_gateway_start_datetime(self) -> str:
        """获取虚拟网关起始时间"""
        return str(self.get("chinastock.virtual_gateway.start_datetime", ""))

    def get_virtual_gateway_speed(self) -> float:
        """获取虚拟网关推送速度倍数"""
        return float(self.get("chinastock.virtual_gateway.speed", 1.0))

    def get_tdx_reader_root_dir(self) -> Optional[Path]:
        """获取通达信数据读取器根目录"""
        tdx_root = self.get("chinastock.data_readers.tdx_root_dir", "C:/new_tdx")
        if tdx_root and Path(tdx_root).exists():
            return Path(tdx_root)
        return None

    def is_unified_manager_enabled(self) -> bool:
        """是否启用统一数据管理器"""
        return bool(self.get("chinastock.unified_manager.enabled", True))

    def is_unified_manager_auto_download_enabled(self) -> bool:
        """统一数据管理器是否允许自动补全下载"""
        return bool(self.get("chinastock.unified_manager.auto_download", False))

    def is_preload_enabled(self) -> bool:
        """是否启用预加载服务"""
        return bool(self.get("chinastock.preload.enabled", True))

    def is_preload_auto_start(self) -> bool:
        """预加载服务是否自动启动"""
        return bool(self.get("chinastock.preload.auto_start", True))

    def get_preload_max_cache_symbols(self) -> int:
        """获取预加载缓存的最大品种数量"""
        return int(self.get("chinastock.preload.max_cache_symbols", 64))

    def get_preload_intervals(self) -> List[str]:
        """获取预加载的默认周期列表"""
        intervals = self.get("chinastock.preload.intervals", ["1d", "5m"])
        if isinstance(intervals, str):
            return [item.strip() for item in intervals.split(",") if item.strip()]
        if isinstance(intervals, list):
            return [str(item).strip() for item in intervals if str(item).strip()]
        return ["1d", "5m"]

    def get_preload_frequently_used_symbols(self) -> List[str]:
        """获取常用品种列表"""
        symbols = self.get("chinastock.preload.frequently_used_symbols", [])
        if isinstance(symbols, str):
            return [item.strip() for item in symbols.split(",") if item.strip()]
        if isinstance(symbols, list):
            return [str(item).strip() for item in symbols if str(item).strip()]
        return []

    # 数据质量感知配置访问方法

    def is_quality_scan_adaptive_enabled(self) -> bool:
        """是否启用自适应质量扫描"""
        return bool(self.get("chinastock.quality_scan.enable_adaptive", True))

    def is_quality_scan_detailed_enabled(self) -> bool:
        """是否启用详细质量扫描（错误/警告检查）"""
        return bool(self.get("chinastock.quality_scan.enable_detailed_scan", True))

    def is_quality_scan_incremental_push_enabled(self) -> bool:
        """是否启用增量推送"""
        return bool(self.get("chinastock.quality_scan.enable_incremental_push", True))

    def get_quality_scan_min_push_interval(self) -> int:
        """获取最小推送间隔（毫秒）"""
        return int(self.get("chinastock.quality_scan.min_push_interval_ms", 500))

    def _save_to_file(self) -> None:
        """保存配置到文件"""
        try:
            # 读取现有配置
            setting_data = {}
            with suppress(Exception):
                setting_data = load_json(SETTING_FILENAME)

            # 更新chinastock相关配置
            for key, value in self._config.items():
                if key.startswith("chinastock."):
                    setting_data[key] = value

            # 保存到文件
            save_json(SETTING_FILENAME, setting_data)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def update_config(self, config_dict: Dict[str, Any]) -> None:
        """批量更新配置"""
        for key, value in config_dict.items():
            if key.startswith("chinastock."):
                self._config[key] = value
        self._save_to_file()

    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

    # 新增：便捷访问配置文件解析器
    def get_config_parser(self) -> Optional[TdxConfigFileParser]:
        """
        获取通达信配置文件解析器实例

        Returns:
            TdxConfigFileParser实例，如果通达信目录存在
        """
        tdx_dir = self.get_tdx_dir()
        if tdx_dir:
            return TdxConfigFileParser(tdx_dir)
        return None


# 全局配置管理器实例
config_manager = ConfigManager()


# ==============================================================================
# 第5部分：Qt工作线程模块（原 validation_worker.py）
# ==============================================================================

"""
缓存验证工作对象（Qt原生，线程安全）

此模块实现Qt原生的后台验证工作对象，用于在QThread中执行完整的缓存验证和数据感知流程。

架构说明：
- 使用QObject和QThread，完全兼容Qt的EventEngine
- 通过信号槽与UI线程通信，线程安全
- 在UI就绪后启动，不阻塞应用启动
- 直接调用 ChinaStockEngine._smart_cache_validation_and_sensing() 执行完整逻辑
"""

from PySide6.QtCore import QObject, Signal

logger_validation_worker = logging.getLogger("backend.data_module.validation_worker")


class CacheValidationWorker(QObject):
    """缓存验证工作对象（Qt原生）

    在QThread中执行缓存验证和数据质量感知，完全兼容EventEngine。

    信号：
        progress(str, int): 进度更新 (消息, 百分比)
        finished(bool): 验证完成 (成功)
        error(str): 错误发生 (错误消息)
    """

    # Qt信号定义
    progress = Signal(str, int)  # (消息, 进度百分比)
    finished = Signal(bool)  # (成功)
    error = Signal(str)  # (错误消息)

    def __init__(self, china_stock_engine):
        """初始化验证工作对象

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        super().__init__()
        self.engine = china_stock_engine
        self.logger = logger_validation_worker
        self.progress_emitter = china_stock_engine.progress_emitter

    def run(self):
        """执行完整的缓存验证和数据感知流程

        此方法在QThread中执行，可以安全使用EventEngine。
        """
        try:
            self.logger.info("=" * 70)
            self.logger.info("【后台进程】智能缓存验证与数据感知流程启动")
            self.logger.info("=" * 70)

            # 连接进度发射器到信号
            self.progress_emitter.progress_updated_connect(
                lambda msg, pct: self.progress.emit(msg, pct)
            )

            # 执行智能缓存验证逻辑
            self.engine._smart_cache_validation_and_sensing()

            self.progress.emit("缓存验证完成", 100)
            self.logger.info("✅ 智能缓存验证流程完成")
            self.finished.emit(True)

        except Exception as e:
            error_msg = f"缓存验证失败: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            self.finished.emit(False)


def create_validation_worker_and_thread(china_stock_engine):
    """工厂函数：创建验证工作对象和线程

    便捷函数，用于快速创建和配置验证工作流程。

    Args:
        china_stock_engine: ChinaStockEngine实例

    Returns:
        (worker, thread): 工作对象和线程对象的元组

    使用示例:
        worker, thread = create_validation_worker_and_thread(engine)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.progress.connect(on_progress_callback)
        thread.start()
    """
    from PySide6.QtCore import QThread

    worker = CacheValidationWorker(china_stock_engine)
    thread = QThread()
    worker.moveToThread(thread)

    return worker, thread


# ==============================================================================
# 第6部分：主引擎模块（原 core.py）
# ==============================================================================

"""
主引擎模块

ChinaStockEngine继承vnpy的BaseEngine，集成所有功能模块：
- 品种列表获取和缓存
- K线数据下载（增量下载）
- 数据存储和查询
- 数据感知和校验
- 文件监控
- 事件推送

合并来源：engine.py -> core.py
"""

import time
from typing import Union
from vnpy.trader.engine import BaseEngine, MainEngine

logger_engine = logging.getLogger("backend.data_module.engine")
logger_engine_download = logging.getLogger("backend.data_module.download")
logger_engine_alert = logging.getLogger("backend.data_module.alert")


class CacheValidationProgressEmitter:
    """缓存验证进度信号发射器（线程安全，避免Qt Timer问题）

    修复说明：
    - 原实现继承QObject，在后台线程中创建会触发Qt Timer警告
    - 新实现使用回调函数机制，线程安全且无Qt依赖
    """

    def __init__(self):
        """初始化进度发射器"""
        self._callbacks = []
        self._lock = threading.Lock()

    def progress_updated_connect(self, callback):
        """连接回调函数（替代Qt的connect）

        Args:
            callback: 回调函数 callback(message: str, progress: int)
        """
        with self._lock:
            self._callbacks.append(callback)

    @property
    def progress_updated(self):
        """提供兼容的API（模拟Qt Signal）"""
        return self

    def emit(self, message: str, progress: int):
        """发射进度更新信号（线程安全）

        Args:
            message: 进度消息
            progress: 进度百分比
        """
        with self._lock:
            callbacks = self._callbacks.copy()

        # 执行所有回调（在锁外执行，避免死锁）
        for callback in callbacks:
            try:
                callback(message, progress)
            except Exception:
                pass  # 静默处理回调异常，不影响主流程

    def connect(self, callback):
        """Qt兼容的connect方法"""
        self.progress_updated_connect(callback)


class ChinaStockEngine(BaseEngine):
    """中国A股数据管理引擎"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """
        初始化引擎

        Args:
            main_engine: vnpy主引擎
            event_engine: vnpy事件引擎
        """
        super().__init__(main_engine, event_engine, APP_NAME)

        # 延迟导入避免循环依赖
        from .data_acquisition import SymbolLoader, MultiProcessStockFetcher, TdxBinaryReader
        from .data_quality import (
            StorageManager,
            DataValidator,
            ValidationSummary,
            DataFileWatcher,
            DataSensor,
            QualityOverview,
        )
        from .data_management import (
            PreloadService,
            UnifiedDataManager,
            TdxDataSource,
            VirtualDataSource,
        )

        # 初始化组件（传入event_engine让各模块自己管理事件）
        self.symbol_loader = SymbolLoader(event_engine)
        self.stock_fetcher = MultiProcessStockFetcher(event_engine=event_engine)
        self.storage_manager = StorageManager()
        self.validator = DataValidator()
        # 文件监控器（已合并到data_quality.py中，由data_sensor处理）
        self.file_watcher = None

        # 新增：数据感知器
        self.data_sensor = DataSensor(event_engine)
        self.data_file_watcher: Optional[DataFileWatcher] = None

        # 新增：轮询网关和虚拟网关（向后兼容别名）
        self.polling_gateway: Optional[TdxDataSource] = None
        self.virtual_gateway: Optional[VirtualDataSource] = None

        # 新增：数据读取器
        self.tdx_reader: Optional[TdxBinaryReader] = None

        # 新增：统一数据管理组件
        self.preload_service: Optional[PreloadService] = None
        self.unified_data_manager: Optional[UnifiedDataManager] = None

        # 日志记录器（使用专用logger）
        self.logger = logger_engine
        self.logger_download = logger_engine_download
        self.logger_alert = logger_engine_alert

        # 通用事件发布器（用于日志等通用事件）
        self.event_publisher = EventPublisher(event_engine)

        # 进度信号发射器（组合模式）
        self.progress_emitter = CacheValidationProgressEmitter()

        # ⚡ 延迟初始化标志
        self._lazy_init_done = False
        self._lazy_init_lock = threading.Lock()

        # 自动启动轮询网关（如果配置启用）
        if config_manager.is_polling_gateway_enabled():
            self._init_polling_gateway()

        # 自动启动虚拟网关（如果配置启用）
        if config_manager.is_virtual_gateway_enabled():
            self._init_virtual_gateway()

        # ⚡ 优化：初始化预加载服务但不自动启动，避免阻塞初始化
        if config_manager.is_preload_enabled():
            try:
                self.preload_service = PreloadService(self)
                self.logger.info("预加载服务已创建（延迟启动）")
            except Exception as exc:
                self.logger.exception("预加载服务初始化失败: %s", exc)
                self.preload_service = None

        # ⚡ 优化：统一数据管理器立即初始化（不涉及耗时操作）
        if config_manager.is_unified_manager_enabled():
            try:
                self.unified_data_manager = UnifiedDataManager(
                    self,
                    preload_service=self.preload_service,
                )
            except Exception as exc:
                self.logger.exception("统一数据管理器初始化失败: %s", exc)
                self.unified_data_manager = None

        # 阶段感知的初始化日志
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

            ctx = get_logging_hub()
            if ctx.get_current_stage() == "startup":
                self.logger.info(
                    "中国A股数据引擎初始化完成: 模式=快速启动, "
                    "组件=[品种加载器,数据下载器,数据验证器,数据感知器,统一数据管理器]"
                )
            else:
                self.logger.debug("数据引擎重新初始化")
        except Exception:
            # 如果logging_context未就绪，使用简单日志
            self.logger.info("中国A股数据管理引擎初始化完成（快速启动模式）")

        # 🔧 架构修复：移除SmartCacheValidator线程（混合线程模型导致Qt Timer警告）
        self.logger.info("✓ 智能缓存验证将在UI就绪后启动（避免启动阻塞）")

    # ==================== 健康检查与就绪 ====================

    def _ensure_lazy_init(self) -> None:
        """确保延迟初始化已完成

        首次调用时初始化：
        1. 文件监控器
        2. 数据感知器
        3. 预加载服务
        """
        if self._lazy_init_done:
            return

        with self._lazy_init_lock:
            if not self._lazy_init_done:
                self.logger.info("[LAZY-INIT] 开始延迟初始化...")

                try:
                    # 1. 启动文件监控（如果配置启用）
                    if config_manager.is_watcher_enabled():
                        self.logger.info("[LAZY-INIT] 启动文件监控...")
                        try:
                            # 文件监控现在由data_sensor处理，无需单独启动
                            self.logger.info("[LAZY-INIT] ✅ 文件监控由data_sensor管理")
                        except Exception as e:
                            self.logger.warning("[LAZY-INIT] ⚠️ 文件监控启动失败: %s", e)
                    else:
                        self.logger.info("[LAZY-INIT] 文件监控未启用，跳过")

                    # 2. 启动数据感知器（异步扫描）
                    self.logger.info("[LAZY-INIT] 启动数据感知器...")
                    try:
                        # 数据感知器的启动逻辑已经移到DataSensor中
                        self.logger.info("[LAZY-INIT] ✅ 数据感知器准备就绪（按需启动）")
                    except Exception as e:
                        self.logger.warning("[LAZY-INIT] ⚠️ 数据感知器启动失败: %s", e)

                    # 3. 启动预加载服务（如果配置启用且自动启动）
                    if self.preload_service and config_manager.is_preload_auto_start():
                        self.logger.info("[LAZY-INIT] 启动预加载服务...")
                        try:
                            self.preload_service.start(prime=True)
                            self.logger.info("[LAZY-INIT] ✅ 预加载服务启动成功")
                        except Exception as e:
                            self.logger.warning("[LAZY-INIT] ⚠️ 预加载服务启动失败: %s", e)
                    else:
                        self.logger.info("[LAZY-INIT] 预加载服务未启用或不自动启动，跳过")

                    self.logger.info("[LAZY-INIT] ✅ 延迟初始化完成")

                except Exception as e:
                    self.logger.exception("[LAZY-INIT] ❌ 延迟初始化发生异常: %s", e)

                self._lazy_init_done = True

    def healthcheck(self) -> Dict[str, Any]:
        """健康检查（代理调用）"""
        from .data_quality import HealthChecker

        result = HealthChecker.check_system_health()
        setattr(self, "_ready", result["ready"])
        return result

    def is_ready(self) -> bool:
        """是否已通过健康检查（基本就绪）"""
        # ⚡ 快速启动模式：默认返回True，实际健康检查延迟到首次使用
        return True

    def _smart_cache_validation_and_sensing(self):
        """智能缓存验证与数据感知（8步流程）

        执行顺序（优化后，网络依赖前置）：
        1. 验证服务器池缓存 - 确保网络连接就绪（所有后续步骤的前提）
        2. 获取当前日期
        3. 验证交易日历缓存（依赖网络）
        4. 验证品种列表缓存并增量更新（依赖网络和服务器池）
        5. 验证IPO日期缓存并增量更新（依赖网络和服务器池）
        6. 更新本地数据索引（含失效品种池维护）
        7. 检查数据更新状态
        8. 启动文件监控
        """
        try:
            # 使用self.logger，通过extra={"log_type": "stage_node"}标记为阶段节点日志
            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info(
                "【后台进程】智能缓存验证与数据感知流程启动", extra={"log_type": "stage_node"}
            )
            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info("开始智能缓存验证流程", extra={"log_type": "stage_node"})

            # 步骤1：验证服务器池缓存 (10%) - 前置网络依赖
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤1/8】验证服务器池缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[1/8] 验证服务器池缓存...", extra={"log_type": "stage_node"})
            self._validate_server_pool_cache()
            self.progress_emitter.progress_updated.emit("验证服务器池缓存", 10)

            # 步骤2：获取当前日期 (15%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤2/8】获取当前日期", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            today = date.today()
            self.logger.info(
                "[2/8] 当前日期: %s", today.strftime("%Y-%m-%d"), extra={"log_type": "stage_node"}
            )
            self.progress_emitter.progress_updated.emit("获取当前日期", 15)

            # 步骤3：验证交易日历缓存 (25%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤3/8】验证交易日历缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[3/8] 验证交易日历缓存...", extra={"log_type": "stage_node"})
            self._validate_trading_calendar_cache()
            self.progress_emitter.progress_updated.emit("验证交易日历缓存", 25)

            # 步骤4：验证品种列表缓存（只读） (35%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤4/8】验证品种列表缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[4/8] 验证品种列表缓存...", extra={"log_type": "stage_node"})
            symbols_result = self._validate_symbol_cache_readonly()
            self.progress_emitter.progress_updated.emit("验证品种列表缓存", 35)

            # 推送品种列表加载完成事件
            if symbols_result:
                event_data = {
                    "symbol_count": len(symbols_result.get("all_symbols", [])),
                    "is_new": symbols_result.get("is_new", False),
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_SYMBOL_CACHE_LOADED, event_data)
                self.event_engine.put(event)

            # 步骤5：验证IPO日期缓存并增量更新 (45%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤5/8】验证IPO日期缓存", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[5/8] 验证IPO日期缓存...", extra={"log_type": "stage_node"})
            listed_symbols = []
            if symbols_result and symbols_result.get("all_symbols"):
                self._validate_and_update_ipo_cache(symbols_result["all_symbols"])
                # 获取IPO过滤后的已上市品种列表
                listed_symbols = self.symbol_loader.extract_all_codes()
            self.progress_emitter.progress_updated.emit("验证IPO日期缓存", 45)

            # 推送IPO缓存更新完成事件
            event_data = {
                "listed_count": len(listed_symbols) if listed_symbols else 0,
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_IPO_CACHE_UPDATED, event_data)
            self.event_engine.put(event)

            # 步骤6：更新本地数据索引（含失效品种池维护）(55%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤6/8】更新本地数据索引", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[6/8] 更新本地数据索引...", extra={"log_type": "stage_node"})
            self._update_local_data_index(listed_symbols)
            self.progress_emitter.progress_updated.emit("更新本地数据索引", 55)

            # 步骤7：检查数据更新状态 (60%-75%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤7/8】检查数据更新状态", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[7/8] 检查数据更新状态...", extra={"log_type": "stage_node"})
            self._check_data_update_status(listed_symbols)
            self.progress_emitter.progress_updated.emit("检查数据更新状态", 75)

            # 步骤8：启动文件监控 (100%)
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【步骤8/8】启动文件监控", extra={"log_type": "stage_node"})
            self.logger.info("-" * 70, extra={"log_type": "stage_node"})
            self.logger.info("[8/8] 启动文件监控...", extra={"log_type": "stage_node"})
            self.data_sensor.start_file_watcher()

            # 推送文件监控启动事件
            event_data = {"status": "started", "timestamp": datetime.now().isoformat()}
            event = Event(EVENT_FILE_WATCHER_STARTED, event_data)
            self.event_engine.put(event)

            self.logger.info("✓ 文件监控已启动", extra={"log_type": "stage_node"})

            self.progress_emitter.progress_updated.emit("系统就绪", 100)

            # 推送validation流程完成事件
            event_data = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_VALIDATION_COMPLETED, event_data)
            self.event_engine.put(event)

            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info("【后台线程】智能缓存验证流程完成", extra={"log_type": "stage_node"})
            self.logger.info("=" * 70, extra={"log_type": "stage_node"})
            self.logger.info("智能缓存验证流程完成", extra={"log_type": "stage_node"})

        except Exception as e:
            self.logger.exception("智能缓存验证失败: %s", e)

            # 推送失败事件
            try:
                event_data = {
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_VALIDATION_COMPLETED, event_data)
                self.event_engine.put(event)
            except Exception:
                pass  # 静默处理事件推送失败，避免掩盖原始异常

    def _validate_trading_calendar_cache(self):
        """验证交易日历缓存"""
        # 交易日历已在TradingCalendar中自动验证和更新
        try:
            # 直接检查缓存文件
            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "trading_calendar.json"
            )

            if cache_data and is_valid:
                # 尝试从缓存数据中提取交易日数量
                trading_days_count = len(cache_data) if isinstance(cache_data, list) else 0
                self.logger.info(
                    "✓ 交易日历缓存有效：%s 约%d个交易日",
                    cache_date,
                    trading_days_count,
                    extra={"log_type": "stage_node"},
                )
            elif cache_data and not is_valid:
                self.logger.info("   缓存状态: 已过时（日期: %s）", cache_date)
                self.logger.info("   操作: 自动重新获取...")
                self.logger.warning("交易日历缓存已过时（%s），尝试自动修复", cache_date)
                try:
                    self._regenerate_trading_calendar_cache()
                    self.logger.info("   ✓ 已自动重新生成")
                    self.logger.info("✓ 交易日历缓存已自动重新生成")
                except Exception as fix_error:
                    self.logger.error("   ❌ 自动修复失败: %s", fix_error)
                    self.logger.error("交易日历缓存自动修复失败: %s", fix_error)
                    raise RuntimeError(f"交易日历缓存修复失败: {fix_error}")
            else:
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次生成...")
                self.logger.warning("交易日历缓存不存在，尝试首次生成")
                try:
                    trading_days_count = self._regenerate_trading_calendar_cache()
                    self.logger.info("   ✓ 已生成")
                    self.logger.info(
                        "✓ 交易日历缓存已首次生成：%d个交易日",
                        trading_days_count,
                        extra={"log_type": "stage_node"},
                    )
                except Exception as gen_error:
                    self.logger.error("   ❌ 生成失败: %s", gen_error)
                    self.logger.error("交易日历缓存生成失败: %s", gen_error)
                    raise RuntimeError(f"交易日历缓存生成失败: {gen_error}")

        except Exception as e:
            self.logger.error("   验证异常: %s", e)
            self.logger.error("交易日历缓存验证失败: %s", e)
            raise  # 重新抛出异常

    def _regenerate_trading_calendar_cache(self) -> int:
        """重新生成交易日历缓存（同步调用异步方法）

        Returns:
            int: 交易日数量
        """
        import asyncio
        from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar

        calendar = TradingCalendar()
        today = date.today()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 调用get_trading_calendar会自动保存到文件缓存
            trading_days_df = loop.run_until_complete(calendar.get_trading_calendar(today.year))
            if trading_days_df is None or len(trading_days_df) == 0:
                raise RuntimeError("获取到的交易日历为空")
            count = len(trading_days_df)
            self.logger.info("交易日历缓存已生成：%d个交易日", count)
            return count
        finally:
            loop.close()

    def _validate_server_pool_cache(self):
        """验证服务器池缓存

        增强健壮性：
        1. 检查服务器池状态
        2. 如果未就绪，调用start()初始化
        3. 验证初始化后的状态
        4. 如果失败，记录详细日志并抛出异常
        """
        try:
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                server_pool_manager,
            )

            # 如果未初始化，直接调用start()加载缓存（不会重新测速）
            if not server_pool_manager._running:
                self.logger.info("服务器池未初始化，正在从缓存加载...")
                self.logger.info("   缓存状态: 正在加载...")

                success = server_pool_manager.start()

                if not success:
                    self.logger.error("   ❌ 启动失败")
                    self.logger.error("❌ 服务器池启动失败！")
                    raise RuntimeError("服务器池启动失败")

                # 验证启动后的状态
                if not server_pool_manager._running:
                    self.logger.error("   ❌ 启动后状态仍未就绪")
                    self.logger.error("❌ 服务器池启动后状态仍未就绪！_running=False")
                    raise RuntimeError("服务器池状态异常：启动成功但_running=False")

                if not server_pool_manager._sorted_servers_ipv4:
                    self.logger.error("   ❌ 启动后无可用IPv4服务器")
                    self.logger.error("❌ 服务器池启动后IPv4池为空！")
                    raise RuntimeError("服务器池状态异常：启动成功但无可用IPv4服务器")

                # 加载成功，显示状态
                stats = server_pool_manager.get_stats()
                cache_date = getattr(server_pool_manager, "_cache_date", None)

                if stats["available"] > 0:
                    self.logger.info("   缓存状态: 有效")
                    self.logger.info("   缓存日期: %s", cache_date)
                    # 计算总测试服务器数（IPv4 + IPv6）
                    total_tested = getattr(server_pool_manager, "_total_servers", stats["total"])
                    self.logger.info(
                        "   测速结果: %d/%d 个服务器可用", stats["available"], total_tested
                    )
                    ipv4_count = (
                        len(server_pool_manager._sorted_servers_ipv4)
                        if hasattr(server_pool_manager, "_sorted_servers_ipv4")
                        else 0
                    )
                    ipv6_count = (
                        len(server_pool_manager._sorted_servers_ipv6)
                        if hasattr(server_pool_manager, "_sorted_servers_ipv6")
                        else 0
                    )
                    self.logger.info(
                        "✓ 服务器池缓存有效：从缓存加载%d个（IPv4=%d, IPv6=%d）",
                        total_tested,
                        ipv4_count,
                        ipv6_count,
                        extra={"log_type": "stage_node"},
                    )
                else:
                    # 如果加载后还是0个，说明测速失败或缓存为空
                    self.logger.warning(
                        "   ⚠️ 加载后无可用服务器: %d/%d", stats["available"], stats["total"]
                    )
                    self.logger.warning("⚠️ 服务器池加载后无可用服务器，但不阻塞启动")
            else:
                # 已经运行，直接显示状态
                stats = server_pool_manager.get_stats()
                cache_date = getattr(server_pool_manager, "_cache_date", None)

                self.logger.info("   缓存状态: 有效（已运行）")
                self.logger.info("   缓存日期: %s", cache_date)
                # 计算总测试服务器数（IPv4 + IPv6）
                total_tested = getattr(server_pool_manager, "_total_servers", stats["total"])
                self.logger.info(
                    "   测速结果: %d/%d 个服务器可用", stats["available"], total_tested
                )
                ipv4_count = (
                    len(server_pool_manager._sorted_servers_ipv4)
                    if hasattr(server_pool_manager, "_sorted_servers_ipv4")
                    else 0
                )
                ipv6_count = (
                    len(server_pool_manager._sorted_servers_ipv6)
                    if hasattr(server_pool_manager, "_sorted_servers_ipv6")
                    else 0
                )
                self.logger.info(
                    "✓ 服务器池已运行：缓存中%d个服务器（IPv4=%d, IPv6=%d）",
                    total_tested,
                    ipv4_count,
                    ipv6_count,
                    extra={"log_type": "stage_node"},
                )

                # 额外验证：即使_running=True，也要确认IPv4池不为空
                if not server_pool_manager._sorted_servers_ipv4:
                    self.logger.warning("⚠️ 服务器池已运行但IPv4池为空，尝试重新加载")
                    self.logger.warning("   ⚠️ 检测到IPv4服务器列表为空，尝试重新加载...")
                    # 强制重新加载
                    server_pool_manager._running = False
                    success = server_pool_manager.start()
                    if not success or not server_pool_manager._sorted_servers_ipv4:
                        raise RuntimeError("服务器池重新加载失败")

        except RuntimeError:
            raise  # 重新抛出RuntimeError
        except Exception as e:
            self.logger.error("   验证异常: %s", e)
            self.logger.error("验证服务器池缓存失败: %s", e, exc_info=True)
            raise RuntimeError(f"服务器池缓存验证异常: {e}")

    def _validate_symbol_cache_readonly(self):
        """只读验证品种列表缓存（步骤4专用：缓存为空时立即重载）"""
        try:
            # 添加互斥锁机制，避免与其他流程冲突
            loading_flag = Path(config_manager.get_cache_dir()) / ".symbol_loading.lock"

            if loading_flag.exists():
                file_age = time.time() - loading_flag.stat().st_mtime
                if file_age < 300:  # 5分钟内
                    self.logger.info("检测到其他流程正在加载品种列表，等待完成...")
                    for _ in range(30):
                        time.sleep(1)
                        if not loading_flag.exists():
                            break
                        classified = self.symbol_loader.get_all_classified()
                        if classified:
                            break

            # 直接从SymbolLoader读取缓存（不验证过期）
            classified = self.symbol_loader.get_all_classified()

            if not classified or len(classified) == 0:
                self.logger.warning("品种列表缓存不存在，开始首次加载...")
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次加载（耗时约30秒）...")
                self.progress_emitter.progress_updated.emit("加载品种列表（首次，耗时约30秒）", 36)

                # 创建锁文件
                try:
                    loading_flag.touch()
                    self.logger.debug("已创建加载锁文件")
                except Exception:
                    pass

                try:
                    result = self.symbol_loader.load_from_api()

                    if not result or "classified" not in result:
                        raise RuntimeError("品种列表加载失败：返回结果为空")

                    all_codes = self.symbol_loader.extract_all_codes()

                    if len(all_codes) == 0:
                        raise RuntimeError("品种列表加载失败：品种数量为0")

                    self.logger.info("   ✓ 加载结果: 共%d个品种", len(all_codes))
                    self.logger.info(
                        "✓ 品种列表首次加载成功：%d个品种（含未上市）",
                        len(all_codes),
                        extra={"log_type": "stage_node"},
                    )
                    return {"all_symbols": all_codes, "is_new": True}

                except Exception as e:
                    self.logger.error("   ✗ 加载失败: %s", e)
                    self.logger.error("品种列表首次加载失败: %s", e, exc_info=True)
                    raise
                finally:
                    # 删除锁文件
                    try:
                        if loading_flag.exists():
                            loading_flag.unlink()
                            self.logger.debug("已删除加载锁文件")
                    except Exception:
                        pass

            # 提取所有品种代码
            all_codes = self.symbol_loader.extract_all_codes()

            self.logger.info(
                "✓ 品种列表缓存有效：%d个品种（含未上市）",
                len(all_codes),
                extra={"log_type": "stage_node"},
            )
            return {"all_symbols": all_codes, "is_valid": True}

        except Exception as e:
            self.logger.exception("验证品种列表缓存失败: %s", e)
            raise  # 重新抛出，让上层处理

    def _validate_and_update_ipo_cache(self, all_symbols):
        """验证并增量更新IPO日期缓存（与品种列表联动）"""
        try:
            ipo_cache = self.validator._ipo_cache
            cache_date = getattr(ipo_cache, "_cache_date", None)

            # SQLite后端：从数据库查询记录数
            cached_count = 0
            try:
                with ipo_cache.db.get_connection() as conn:
                    result = conn.execute("SELECT COUNT(*) FROM finance_info").fetchone()
                    cached_count = result[0] if result else 0
            except Exception as e:
                self.logger.warning("查询SQLite缓存记录数失败: %s", e)

            # 检查缓存是否存在（基于SQLite记录数）
            cache_exists = cached_count > 0

            if not cache_exists:
                self.logger.info("   缓存状态: 不存在")
                self.logger.info("   操作: 首次加载（耗时约1-2分钟）...")
                self.logger.warning("IPO日期缓存不存在，开始首次下载...")

                # 输出IPO下载前总品种数
                import sys

                print(f"\n[IPO下载] IPO下载前总品种数: {len(all_symbols)}个")
                sys.stdout.flush()

                self.progress_emitter.progress_updated.emit("下载IPO日期（首次）", 46)

                try:
                    # 首次下载所有品种的IPO日期
                    from .data_acquisition import download_ipo_dates

                    # 定义进度回调函数（46%-48%范围）
                    last_update_time = [time.time()]

                    def ipo_progress_callback(current, total):
                        """IPO下载进度回调 - 限制更新频率避免UI卡顿"""
                        if total > 0:
                            now = time.time()
                            # 每0.5秒或每100个品种更新一次
                            if (
                                (now - last_update_time[0] >= 0.5)
                                or (current % 100 == 0)
                                or (current == total)
                            ):
                                # 计算进度（46%-48%）
                                percent = int(46 + (current / total) * 2)
                                last_update_time[0] = now

                                self.progress_emitter.progress_updated.emit(
                                    f"下载IPO日期 ({current}/{total})", percent
                                )
                                self.logger.debug("IPO下载进度: %d/%d", current, total)

                    result = download_ipo_dates(
                        symbols=all_symbols,
                        progress_callback=ipo_progress_callback,
                        use_multiprocess=True,
                        ipo_cache=ipo_cache,  # 传递全局IPODateCache实例
                    )

                    # 输出IPO过滤详细统计
                    unlisted_symbols = result.get("unlisted", [])
                    listed_count = len(all_symbols) - len(unlisted_symbols)

                    # 初始化统计
                    unlisted_stats = {"股票": 0, "可转债": 0, "基金": 0, "其他": 0}

                    if unlisted_symbols:
                        # 分类统计未上市品种（复用已初始化的symbol_loader实例）
                        classified = self.symbol_loader.get_all_classified()

                        for symbol in unlisted_symbols:
                            # 检查属于哪个分类
                            found = False
                            for category in ["上证A股", "深证A股", "北证A股"]:
                                if symbol in [s.get("code") for s in classified.get(category, [])]:
                                    unlisted_stats["股票"] += 1
                                    found = True
                                    break
                            if not found:
                                for category in ["可转债"]:
                                    if symbol in [
                                        s.get("code") for s in classified.get(category, [])
                                    ]:
                                        unlisted_stats["可转债"] += 1
                                        found = True
                                        break
                            if not found:
                                for category in ["T+0基金"]:
                                    if symbol in [
                                        s.get("code") for s in classified.get(category, [])
                                    ]:
                                        unlisted_stats["基金"] += 1
                                        found = True
                                        break
                            if not found:
                                unlisted_stats["其他"] += 1

                        # 输出到日志
                        self.logger.info("✓ 发现未上市品种: %d个", len(unlisted_symbols))
                        self.logger.info(
                            "   其中：股票%d个, 可转债%d个, 基金%d个, 其他%d个",
                            unlisted_stats["股票"],
                            unlisted_stats["可转债"],
                            unlisted_stats["基金"],
                            unlisted_stats["其他"],
                        )
                        listed_count = len(all_symbols) - len(unlisted_symbols)
                        self.logger.info(
                            "✓ 过滤后品种数量: %d个（已上市）",
                            listed_count,
                        )

                    # 输出到terminal摘要（无论是否有未上市品种都输出）
                    import sys

                    if unlisted_symbols:
                        print("\n" + "   " + "-" * 60)
                        print(
                            f"   📊 IPO过滤结果: "
                            f"发现{len(unlisted_symbols)}个未上市品种（股票{unlisted_stats['股票']}个, "
                            f"可转债{unlisted_stats['可转债']}个, 基金{unlisted_stats['基金']}个）"
                        )
                        print(f"   ✓ 去除后，品种数量: {listed_count}个（已上市）")
                        print("   " + "-" * 60)
                    else:
                        print(f"\n   ✓ IPO过滤完成: 全部{len(all_symbols)}个品种均已上市")
                    sys.stdout.flush()

                    self.logger.info(
                        "✓ 下载结果: 成功%d个, 失败%d个", result["succeeded"], result["failed"]
                    )
                    self.logger.info("✓ IPO日期首次下载完成：成功 %d 个", result["succeeded"])

                except Exception as e:
                    self.logger.error("   ⚠️ 下载异常: %s", e)
                    self.logger.error("IPO日期首次下载失败: %s", e, exc_info=True)
                    # 不阻塞后续流程（用户需求2c）
                    self.progress_emitter.progress_updated.emit("IPO缓存下载失败（已跳过）", 48)

            elif ipo_cache.is_cache_outdated():
                self.logger.info("   缓存状态: 已过时（日期: %s）", cache_date)
                self.logger.info("   已缓存: %d个品种的IPO日期", cached_count)
                self.logger.info("   操作: 增量更新...")
                self.logger.warning("IPO日期缓存已过时，开始增量更新...")

                # 定义进度回调函数（46%-48%范围）
                last_update_time = [time.time()]
                last_percent = [46]

                def ipo_progress_callback(current, total):
                    """IPO下载进度回调 - 限制更新频率避免UI卡顿"""
                    if total > 0:
                        now = time.time()
                        # 每0.5秒或每100个品种更新一次
                        if (
                            (now - last_update_time[0] >= 0.5)
                            or (current % 100 == 0)
                            or (current == total)
                        ):
                            # 计算进度（46%-48%）
                            percent = int(46 + (current / total) * 2)
                            last_percent[0] = percent
                            last_update_time[0] = now

                            self.progress_emitter.progress_updated.emit(
                                f"更新IPO日期 ({current}/{total})", percent
                            )
                            self.logger.debug("IPO下载进度: %d/%d", current, total)

                # 初始提示
                self.progress_emitter.progress_updated.emit("更新IPO日期缓存（准备中）", 46)
                result = ipo_cache.incremental_update(
                    all_symbols, progress_callback=ipo_progress_callback
                )

                self.logger.info(
                    "   更新结果: 新增%d个, 删除%d个, 下载成功%d个",
                    result["added"],
                    result["removed"],
                    result["download_succeeded"],
                )
                self.logger.info(
                    "✓ IPO日期更新完成：新增 %d 个，删除 %d 个，下载成功 %d 个",
                    result["added"],
                    result["removed"],
                    result["download_succeeded"],
                )
            else:
                self.logger.info("   缓存状态: 有效")
                if cache_date:
                    self.logger.info("   缓存日期: %s", cache_date)
                self.logger.info("   已缓存: %d个品种的IPO日期", cached_count)
                # 获取过滤后的已上市品种数（才是真实可用的）
                listed_count = len(self.symbol_loader.extract_all_codes())
                self.logger.info(
                    "✓ IPO过滤完成：%d个品种已上市（缓存总数%d）",
                    listed_count,
                    cached_count,
                    extra={"log_type": "stage_node"},
                )

        except Exception as e:
            self.logger.error("   验证异常: %s", e)
            self.logger.exception("验证IPO日期缓存失败: %s", e)
            # IPO缓存验证失败，显示错误状态但不阻塞后续流程
            self.progress_emitter.progress_updated.emit("IPO缓存验证失败（已跳过）", 48)

    def _update_local_data_index(self, reference_symbols: List[str]):
        """更新本地数据索引（步骤6）

        1. 快速获取本地数据索引
        2. 计算差异：新增=参考集-本地，失效=本地-参考集
        3. 更新数据库中的本地数据索引和失效品种池
        4. 推送指标更新事件

        Args:
            reference_symbols: 参考品种列表（IPO过滤后的已上市品种）
        """
        try:
            from backend.services.database_adapter import get_db_manager

            # 1. 快速获取本地数据索引
            local_symbols = self.storage_manager.get_local_data_index(use_cache=True)
            local_set = set(local_symbols)
            reference_set = set(reference_symbols)

            # 2. 计算差异
            new_symbols = list(reference_set - local_set)  # 新增
            invalid_symbols = list(local_set - reference_set)  # 失效

            # 日志输出（符合v5.0规范：简洁的terminal输出）
            self.logger.info(
                "✓ 索引更新完成：参考=%d, 本地=%d, 新增=%d, 失效=%d",
                len(reference_symbols),
                len(local_symbols),
                len(new_symbols),
                len(invalid_symbols),
                extra={"log_type": "stage_node"},
            )

            # 3. 更新数据库
            db_manager = get_db_manager()
            db_manager.upsert_local_data_index(local_symbols)
            db_manager.upsert_invalid_symbols(invalid_symbols, reason="not_in_reference")

            # 4. 推送指标更新事件
            # 计算统计指标
            total_with_invalid = len(reference_symbols) + len(invalid_symbols)
            downloaded = len(reference_set & local_set)
            missing = len(reference_set - local_set)

            metrics_data = {
                "total_symbols": total_with_invalid,
                "reference_symbols": len(reference_symbols),
                "downloaded": downloaded,
                "missing": missing,
                "invalid_count": len(invalid_symbols),
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_DATA_METRICS_UPDATED, metrics_data)
            self.event_engine.put(event)

            if invalid_symbols:
                invalid_data = {
                    "symbols": invalid_symbols,
                    "count": len(invalid_symbols),
                    "timestamp": datetime.now().isoformat(),
                }
                event = Event(EVENT_INVALID_SYMBOLS_UPDATED, invalid_data)
                self.event_engine.put(event)

        except Exception as e:
            self.logger.exception("更新本地数据索引失败: %s", e)

    def _check_data_update_status(self, reference_symbols: List[str]):
        """检查数据更新状态（步骤7）

        仅做更新状态/新鲜度检查，不做耗时质量深扫。
        移植自原阶段2逻辑：批量检查数据新鲜度。

        Args:
            reference_symbols: 参考品种列表
        """
        try:
            start_time = time.time()

            # 获取有本地数据的品种列表
            local_symbols = self.storage_manager.get_local_data_index(use_cache=True)
            # 只检查参考品种中有数据的品种
            symbols_to_check = [s for s in reference_symbols if s in local_symbols]

            if not symbols_to_check:
                self.logger.info(
                    "✓ 跳过数据新鲜度检查：无本地数据", extra={"log_type": "stage_node"}
                )
                return

            # 使用较少线程避免启动阶段资源竞争
            max_workers = 4

            # 批量检查数据新鲜度（使用DataValidator）
            freshness_results = self.data_sensor.validator.batch_check_freshness_optimized(
                symbols=symbols_to_check,
                interval="1d",
                max_workers=max_workers,
                error_accumulator=None,  # 启动阶段不记录详细错误
            )

            # 统计结果
            outdated_count = 0
            gap_days_list = []

            for symbol, freshness in freshness_results.items():
                if freshness["has_data"]:
                    gap_days = freshness["gap_days"]
                    if gap_days > 1:  # 滞后超过1天算过时
                        outdated_count += 1
                    if gap_days >= 0:
                        gap_days_list.append(gap_days)

            avg_gap = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0
            elapsed = time.time() - start_time

            # 简洁输出（符合v5.0规范）
            self.logger.info(
                "✓ 数据新鲜度检查完成：已检查%d个品种，过时%d个，平均滞后%d天（耗时%.1fs）",
                len(symbols_to_check),
                outdated_count,
                avg_gap,
                elapsed,
                extra={"log_type": "stage_node"},
            )

        except Exception as e:
            self.logger.exception("检查数据更新状态失败: %s", e)
            # 不阻塞后续流程
            self.logger.warning("数据新鲜度检查失败，已跳过")

    def close(self) -> None:
        """关闭引擎"""
        try:
            # 停止文件监听器
            if self.data_sensor and hasattr(self.data_sensor, "data_file_watcher"):
                if self.data_sensor.data_file_watcher:
                    try:
                        self.data_sensor.data_file_watcher.stop()
                        self.logger.info("数据文件监控已停止")
                    except Exception as e:
                        self.logger.warning("停止数据文件监控失败: %s", e)

            # 停止数据感知
            if self.data_sensor and hasattr(self.data_sensor, "stop_sensing"):
                try:
                    self.data_sensor.stop_sensing()
                except Exception as e:
                    self.logger.error("停止数据感知失败: %s", e)

            # 停止预加载服务
            if self.preload_service and hasattr(self.preload_service, "stop"):
                try:
                    self.preload_service.stop()
                except Exception as e:
                    self.logger.error("停止预加载服务失败: %s", e)

            # 关闭轮询网关
            if self.polling_gateway and hasattr(self.polling_gateway, "close"):
                try:
                    self.polling_gateway.close()
                except Exception as e:
                    self.logger.error("关闭轮询网关失败: %s", e)

            # 关闭虚拟网关
            if self.virtual_gateway and hasattr(self.virtual_gateway, "close"):
                try:
                    self.virtual_gateway.close()
                except Exception as e:
                    self.logger.error("关闭虚拟网关失败: %s", e)

            self.logger.info("中国A股数据管理引擎已关闭")

        except Exception as e:
            self.logger.error("关闭引擎失败: %s", e)

    # ==================== 代理方法：品种管理 ====================

    def refresh_stock_list(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """读取本地品种缓存（代理调用）"""
        self._ensure_lazy_init()
        return self.symbol_loader.load_from_cache() or {}

    def reload_stock_list(self) -> Dict[str, Any]:
        """调用API更新品种缓存（代理调用，事件由SymbolLoader推送）"""
        return self.symbol_loader.reload_and_classify()

    def get_market_stocks(self, market_type: str) -> List[Dict[str, Any]]:
        """获取指定市场的品种列表（代理调用）"""
        self._ensure_lazy_init()
        return self.symbol_loader.get_market_stocks(market_type)

    def get_all_market_stocks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有市场的品种分类（代理调用）

        Returns:
            所有市场的品种分类字典，每个品种包含 code, name, market
        """
        return self.symbol_loader.get_all_classified()

    def clear_symbol_cache(self) -> bool:
        """删除品种列表缓存（代理调用）"""
        return self.symbol_loader.clear_cache()

    # ==================== 代理方法：数据下载 ====================

    def download_incremental(
        self,
        start_date: Union[str, date],
        market_types: Optional[List[str]] = None,
        use_adaptive: bool = True,
    ) -> bool:
        """
        增量下载K线数据（代理调用）

        Args:
            start_date: 起始日期
            market_types: 市场类型列表
            use_adaptive: 是否使用自适应配置（默认True，企业级推荐）

        Returns:
            是否成功启动下载任务
        """
        self._ensure_lazy_init()

        # 使用场景上下文和阶段切换
        try:
            from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

            ctx = get_logging_hub()

            # 切换到下载阶段
            ctx.set_stage("downloading")

            # 开始增量下载
            self.logger_download.info(
                "开始增量下载: 起始日期=%s, 市场=%s, 自适应=%s",
                start_date,
                market_types or "全部",
                use_adaptive,
            )

            result = self.stock_fetcher.start_incremental_download_async(
                start_date, self.symbol_loader, self.storage_manager, market_types, use_adaptive
            )

            if result:
                self.logger_download.info("增量下载任务已启动")
            else:
                self.logger_alert.warning("增量下载任务启动失败")

            # v5.0不需要恢复阶段，下载完成后会自动切换到idle阶段
            return result
        except Exception as e:
            # 如果上下文管理失败，回退到简单调用
            self.logger.warning("场景上下文初始化失败，使用默认日志: %s", e)
            return self.stock_fetcher.start_incremental_download_async(
                start_date, self.symbol_loader, self.storage_manager, market_types, use_adaptive
            )

    def stop_download(self):
        """停止当前下载任务（代理调用）"""
        self.stock_fetcher.stop_download()

    def pause_download(self):
        """暂停当前下载任务（代理调用）"""
        self.stock_fetcher.pause_download()

    def resume_download(self):
        """恢复暂停的下载任务（代理调用）"""
        self.stock_fetcher.resume_download()

    def get_download_progress(self) -> Dict[str, Any]:
        """获取当前下载进度（代理调用）"""
        return self.stock_fetcher.get_download_progress()

    # ==================== 代理方法：数据查询 ====================

    def query_data(
        self,
        symbol: Optional[str] = None,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        **kwargs,
    ) -> Optional[Any]:
        """统一查询接口（代理调用）"""

        # ⚡ 首次查询时执行延迟初始化
        self._ensure_lazy_init()

        # 代理调用unified_data_manager
        if self.unified_data_manager:
            return self.unified_data_manager.query_unified(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                **kwargs,
            )
        else:
            # Fallback到基础存储管理器（单品种查询）
            target_symbol: Optional[str] = None
            symbol_candidate = symbol or kwargs.get("symbols")

            if isinstance(symbol_candidate, (list, tuple)):
                # 从列表或元组中取第一个元素
                if len(symbol_candidate) > 0:
                    first_item = symbol_candidate[0]
                    if isinstance(first_item, str):
                        target_symbol = first_item
            elif isinstance(symbol_candidate, str):
                target_symbol = symbol_candidate

            if target_symbol is None:
                return None

            return self.storage_manager.query_kline(target_symbol, interval, start_date, end_date)

    def get_local_data_index(self) -> List[str]:
        """获取本地数据索引（已下载的品种代码列表，代理调用）"""
        try:
            return self.storage_manager.get_local_data_index()
        except Exception as e:
            self.logger.error("获取本地数据索引失败: %s", e)
            return []

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息（代理调用）"""
        try:
            return self.storage_manager.get_storage_stats()
        except Exception as e:
            self.logger.error("获取存储统计失败: %s", e)
            return {}

    # ==================== 代理方法：数据验证与质量 ====================

    def get_validation_result(self, force_refresh: bool = False) -> Optional[Any]:
        """获取数据感知结果（代理调用）"""
        return self.validator.validate_all_data()

    def get_data_quality_overview(self) -> Optional[Any]:
        """获取数据质量概览（代理调用）"""
        return self.data_sensor.get_quality_overview()

    def trigger_data_quality_scan(self, force_refresh: bool = False) -> Optional[Any]:
        """手动触发数据质量扫描（代理调用）"""
        return self.data_sensor.trigger_scan_with_symbols(
            self.symbol_loader, force_refresh=force_refresh
        )

    def scan_corrupted_files(self, auto_delete: bool = False) -> Dict[str, List[str]]:
        """扫描并修复损坏的Parquet文件（代理调用）"""
        return self.storage_manager.scan_and_repair_corrupted_files(auto_delete)

    def _start_data_sensing_async(self) -> None:
        """启动数据感知（代理调用）"""
        self.data_sensor.start_sensing_async(self.symbol_loader)

    def stop_data_sensing(self) -> bool:
        """停止数据感知（代理调用）"""
        return self.data_sensor.stop_sensing()

    # ==================== 代理方法：配置管理 ====================

    def get_config(self) -> Dict[str, Any]:
        """获取配置信息（代理调用）"""
        return config_manager.get_all_config()

    def update_config(self, config_dict: Dict[str, Any]) -> bool:
        """更新配置（代理调用）"""
        config_manager.update_config(config_dict)
        return True

    # ==================== 代理方法：轮询网关管理 ====================

    def _init_polling_gateway(self) -> None:
        """初始化轮询网关（已迁移到UnifiedDataManager）"""
        # 轮询网关已迁移到 UnifiedDataManager.tdx_source
        # 保留此方法以保持向后兼容性
        return

    def start_polling_gateway(self, setting: Optional[Dict] = None) -> bool:
        """启动轮询网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 启动 TdxDataSource
        if self.unified_data_manager:
            return self.unified_data_manager.start_tdx_source(setting or {})
        return False

    def stop_polling_gateway(self) -> bool:
        """停止轮询网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 停止 TdxDataSource
        if self.unified_data_manager:
            return self.unified_data_manager.stop_tdx_source()
        return False

    # ==================== 代理方法：虚拟网关管理 ====================

    def _init_virtual_gateway(self) -> None:
        """初始化虚拟网关（已迁移到UnifiedDataManager）"""
        # 虚拟网关已迁移到 UnifiedDataManager.virtual_source
        # 保留此方法以保持向后兼容性
        return

    def start_virtual_gateway(
        self, start_datetime: str, speed: float = 1.0, symbols: Optional[List[str]] = None
    ) -> bool:
        """启动虚拟网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 启动 VirtualDataSource
        if self.unified_data_manager:
            config = {
                "start_datetime": start_datetime,
                "speed": speed,
                "symbols": symbols,
            }
            return self.unified_data_manager.start_virtual_source(config)
        return False

    def stop_virtual_gateway(self) -> bool:
        """停止虚拟网关（通过UnifiedDataManager）"""
        # 通过 UnifiedDataManager 停止 VirtualDataSource
        if self.unified_data_manager:
            return self.unified_data_manager.stop_virtual_source()
        return False

    # ==================== 代理方法：数据读取器 ====================

    def read_tdx_data(
        self, symbols: List[str], data_type: str = "day", market: str = "sh"
    ) -> Dict[str, bool]:
        """读取通达信本地数据并保存（使用TdxDynamicExecutor）"""
        import asyncio

        from .data_acquisition import TdxDynamicExecutor

        # 获取TDX目录
        tdx_dir = config_manager.get_tdx_reader_root_dir()
        if tdx_dir is None:
            self.logger.error("TDX根目录未配置")
            return {symbol: False for symbol in symbols}

        # 创建执行器
        executor = TdxDynamicExecutor(tdx_dir=Path(tdx_dir))

        # 同步调用异步方法
        results = asyncio.run(
            executor.execute_batch(
                symbols=symbols,
                data_type=data_type,
                market=market,
                initial_processes=4,
                initial_coroutines=20,
                enable_throttling=False,
            )
        )

        # 转换结果格式：ExecutionResult -> bool
        return {symbol: result.success for symbol, result in results.items()}

    def get_unified_data_manager(self) -> Optional[Any]:
        """获取统一数据管理器实例（代理调用）"""
        return self.unified_data_manager

    # ==================== 代理方法：事件推送 ====================

    def _start_file_watcher(self) -> None:
        """启动文件监控（已合并到data_sensor）"""
        # 文件监控现在由data_sensor处理，无需单独启动
        return

    def _push_log_event(self, message: str, level: str = "INFO") -> None:
        """推送日志事件（代理到EventPublisher）"""
        self.event_publisher.push_log_event(message, level)

    def _push_validation_event(self, summary: Any) -> None:
        """推送校验事件（代理到EventPublisher）"""
        publisher = ValidationEventPublisher(self.event_engine)
        publisher.push_validation_event(summary)

    def _push_download_event(
        self, download_type: str, status: str, count: int, error: Optional[str] = None
    ) -> None:
        """推送下载事件（代理到EventPublisher）"""
        publisher = DownloadEventPublisher(self.event_engine)
        publisher.push_download_event(download_type, status, count, error)

    def _push_download_progress_event(
        self, download_type: str, progress_pct: float, completed: int, total: int, current_item: str
    ) -> None:
        """推送下载进度事件（代理到EventPublisher）"""
        publisher = DownloadEventPublisher(self.event_engine)
        publisher.push_download_progress_event(
            download_type, progress_pct, completed, total, current_item
        )


# ==============================================================================
# 导出列表（向后兼容）
# ==============================================================================

__all__ = [
    # 网络时间同步
    "NetworkTimeSync",
    "get_real_date",
    "get_real_datetime",
    "sync_network_time",
    "get_time_stats",
    # 缓存管理
    "DailyCacheManager",
    "is_cache_valid",
    "get_today",
    "save_cache",
    "load_cache",
    # 事件系统
    "EventPublisher",
    "ValidationEventPublisher",
    "DownloadEventPublisher",
    "QualityEventPublisher",
    "AsyncioMetricsPublisher",
    "EVENT_CHINASTOCK_LOG",
    "EVENT_CHINASTOCK_VALIDATION",
    "EVENT_CHINASTOCK_FILE_CHANGE",
    "EVENT_CHINASTOCK_DOWNLOAD",
    "EVENT_DATA_QUALITY_UPDATE",
    "EVENT_DATA_SCAN_COMPLETE",
    "EVENT_LOCAL_DATA_INDEX_READY",
    "EVENT_QUALITY_SCAN_PHASE",
    "EVENT_QUALITY_METRIC_UPDATE",
    "EVENT_ASYNCIO_METRICS",
    "EVENT_DATA_METRICS_UPDATED",
    "EVENT_INVALID_SYMBOLS_UPDATED",
    "EVENT_FILE_WATCHER_STARTED",
    "EVENT_DATA_SCAN_FINISHED",
    "EVENT_SYMBOL_CACHE_LOADED",
    "EVENT_IPO_CACHE_UPDATED",
    "EVENT_VALIDATION_COMPLETED",
    "APP_NAME",
    # 配置管理
    "ConfigManager",
    "TdxConfigFileParser",
    "config_manager",
    "get_project_root",
    # Qt工作线程
    "CacheValidationWorker",
    "create_validation_worker_and_thread",
    # 主引擎
    "ChinaStockEngine",
    "CacheValidationProgressEmitter",
]
