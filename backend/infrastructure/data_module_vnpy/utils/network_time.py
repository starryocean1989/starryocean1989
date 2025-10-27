# -*- coding: utf-8 -*-
"""
网络时间同步模块

提供从NTP服务器获取真实时间的功能，避免依赖不准确的系统时间。
用于数据新鲜度计算、缓存验证等场景。

核心功能：
1. 从NTP服务器同步时间（国内优先：阿里云、腾讯）
2. 缓存时间偏移量（1小时TTL）
3. 提供真实日期/时间查询接口
4. 失败降级策略（使用系统时间）

使用示例：
    from backend.infrastructure.data_module_vnpy.utils import get_real_date

    # 获取真实的当前日期（网络时间）
    today = get_real_date()

    # 获取真实的当前时间
    now = get_real_datetime()

    # 手动触发时间同步
    success = sync_network_time()
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

logger = logging.getLogger("backend.data_module.network_time")


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
            logger.warning("⚠️ ntplib不可用，无法进行网络时间同步")
            return False, None

        with self._sync_lock:
            for ntp_server in self.NTP_SERVERS:
                try:
                    logger.debug(f"尝试从 {ntp_server} 同步时间...")

                    # 发送NTP请求
                    response = self.ntp_client.request(ntp_server, version=3, timeout=timeout)

                    # 计算偏移量
                    # offset: NTP服务器时间 - 本地系统时间（秒）
                    # 正值表示系统时间慢了，负值表示系统时间快了
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
                        logger.info(
                            f"✓ 时间同步成功: {ntp_server}, "
                            f"系统时间{direction}了 {abs_offset:.3f}秒"
                        )
                    else:
                        logger.info(
                            f"✓ 时间同步成功: {ntp_server}, " f"偏差 {abs_offset*1000:.1f}毫秒"
                        )

                    return True, offset

                except Exception as e:
                    # 统一处理所有异常（包括 ntplib.NTPException 如果可用）
                    logger.debug(f"从 {ntp_server} 同步失败: {type(e).__name__}: {e}")
                    continue

            # 所有服务器都失败
            self._sync_failures += 1
            logger.warning(f"⚠️ 时间同步失败，已尝试 {len(self.NTP_SERVERS)} 个NTP服务器")
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
                logger.debug(
                    f"使用缓存的时间偏移: {self._cached_offset:.3f}秒 "
                    f"(缓存年龄: {cache_age:.1f}秒)"
                )
                return real_time

        # 缓存失效，重新同步
        logger.debug("时间偏移缓存失效，重新同步...")
        success, offset = self.sync_time()

        if success and offset is not None:
            # 同步成功，使用新的偏移量
            return datetime.now() + timedelta(seconds=offset)
        else:
            # 同步失败，降级使用系统时间
            logger.warning("⚠️ 时间同步失败，降级使用系统时间（可能不准确）")
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
        success, _ = sync.sync_time()
        return success


def get_time_stats() -> dict:
    """
    获取时间同步统计信息

    Returns:
        dict: 统计信息
    """
    sync = NetworkTimeSync.get_instance()
    return sync.get_stats()
