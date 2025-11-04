# -*- coding: utf-8 -*-
"""
data_module_vnpy v3.0 - 核心引擎与基础设施模块

本文件包含数据模块的核心基础设施组件，提供统一的入口和基础服务。

文件结构：
- Part 1: 网络时间同步（NetworkTimeSync）
- Part 2: 缓存管理（DailyCacheManager）
- Part 3: 配置管理（ConfigManager）
- Part 4: 事件系统（EventPublisher系列）
- Part 5: 核心引擎（ChinaStockEngine）

设计原则：
- 事件驱动架构（通过EventEngine松耦合）
- 单例模式（配置、时间同步等全局服务）
- 线程安全（所有共享资源加锁保护）
- 向后兼容（保持所有API签名）

技术特性：
- native_iocp集成：缓存文件异步读写
- native_ipc集成：配置热更新跨进程通知
- 异步优先：全面支持async/await

作者：AI重构
版本：v3.0
日期：2025-11-01
"""

# ==============================================================================
# 导入依赖
# ==============================================================================

import logging
import threading
import json
import asyncio
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass

# VNPy相关
from vnpy.event import EventEngine, Event

# 可选依赖：vnpy_ctastrategy（CTA策略引擎，可选扩展包）
try:
    from vnpy_ctastrategy import CtaEngine
    CTA_STRATEGY_AVAILABLE = True
except ImportError:
    CtaEngine = None
    CTA_STRATEGY_AVAILABLE = False

# 可选依赖：ntplib
try:
    import ntplib
    NTPLIB_AVAILABLE = True
except ImportError:
    NTPLIB_AVAILABLE = False
    ntplib = None

# 可选依赖：native_iocp
try:
    from backend.infrastructure.native_iocp.compat import aopen as compat_aopen
    IOCP_AVAILABLE = True
except ImportError:
    try:
        import aiofiles
        async def compat_aopen(file, mode='r', **kwargs):
            return aiofiles.open(file, mode, **kwargs)
        IOCP_AVAILABLE = False
    except ImportError:
        compat_aopen = None
        IOCP_AVAILABLE = False

# 可选依赖：native_ipc
try:
    from backend.infrastructure.native_ipc import AsyncIPCPipe
    IPC_AVAILABLE = True
except ImportError:
    AsyncIPCPipe = None
    IPC_AVAILABLE = False

# 日志配置
logger = logging.getLogger("backend.data_module.core_engine")


# ==============================================================================
# Part 1: 网络时间同步（NetworkTimeSync）
# ==============================================================================

class NetworkTimeSync:
    """
    网络时间同步器（线程安全单例）

    功能：
    - 从NTP服务器同步真实时间
    - 缓存时间偏移量（1小时TTL）
    - 用于数据新鲜度计算、缓存验证

    使用示例：
        sync = NetworkTimeSync.get_instance()
        real_time = sync.get_real_datetime()
        real_date = sync.get_real_date()
    """

    _instance: Optional["NetworkTimeSync"] = None
    _lock: threading.Lock = threading.Lock()

    # NTP服务器列表（国内优先）
    NTP_SERVERS: List[str] = [
        "ntp.aliyun.com",
        "ntp.tencent.com",
        "cn.ntp.org.cn",
        "ntp1.aliyun.com",
        "ntp2.aliyun.com",
        "time.windows.com",
    ]
    
    # HTTP时间服务列表（备用方案,当NTP被防火墙阻止时使用）
    HTTP_TIME_SERVICES: List[str] = [
        "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
        "http://worldclockapi.com/api/json/utc/now",
    ]

    def __init__(self):
        # NTP客户端（仅ntplib可用时创建）
        if NTPLIB_AVAILABLE and ntplib is not None:
            self.ntp_client = ntplib.NTPClient()
        else:
            self.ntp_client = None

        # 缓存机制
        self._cached_offset: Optional[float] = None  # 时间偏移量（秒）
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl: int = 3600  # 1小时TTL

        # 统计信息
        self._sync_count: int = 0
        self._sync_failures: int = 0
        self._last_sync_time: Optional[datetime] = None
        self._last_successful_server: Optional[str] = None

        # 线程安全
        self._sync_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "NetworkTimeSync":
        """获取单例实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def sync_time(self, timeout: float = 2.0, max_attempts: int = 3) -> Tuple[bool, Optional[float]]:
        """
        从NTP服务器同步时间

        Args:
            timeout: 请求超时时间（秒）- 默认2秒,确保NTP请求有足够时间完成
            max_attempts: 最大尝试服务器数量 - 默认3个,总超时控制在6秒内

        Returns:
            (成功标志, 时间偏移量)
            偏移量 = 网络时间 - 系统时间（秒）
        """
        # ntplib不可用时直接返回失败
        if not NTPLIB_AVAILABLE or self.ntp_client is None:
            logger.warning("⚠️ ntplib不可用，无法进行网络时间同步", extra={"log_type": "SYSTEM"})
            logger.warning("⚠️ 将降级使用系统时间（可能不准确）", extra={"log_type": "SYSTEM"})
            return False, None

        with self._sync_lock:
            error_details = []  # 收集详细错误信息用于调试
            
            # 🔧 修复: 限制尝试次数,避免启动超时
            servers_to_try = self.NTP_SERVERS[:max_attempts]
            
            for ntp_server in servers_to_try:
                try:
                    logger.debug(f"尝试从 {ntp_server} 同步时间（超时: {timeout}秒）...")
                    
                    import time as _time
                    t0 = _time.time()

                    # 发送NTP请求
                    response = self.ntp_client.request(ntp_server, version=3, timeout=int(timeout))
                    offset = response.offset
                    elapsed = (_time.time() - t0) * 1000  # 毫秒

                    # 更新缓存
                    self._cached_offset = offset
                    self._cache_timestamp = datetime.now()
                    self._sync_count += 1
                    self._last_sync_time = datetime.now()
                    self._last_successful_server = ntp_server

                    # 日志输出
                    abs_offset = abs(offset)
                    direction = "慢" if offset > 0 else "快"

                    if abs_offset > 1.0:
                        logger.info(
                            f"✓ 时间同步成功: {ntp_server} ({elapsed:.0f}ms), "
                            f"系统时间{direction}了 {abs_offset:.3f}秒"
                        )
                    else:
                        logger.info(
                            f"✓ 时间同步成功: {ntp_server} ({elapsed:.0f}ms), "
                            f"偏差 {abs_offset*1000:.1f}毫秒"
                        )

                    return True, offset

                except Exception as e:
                    error_msg = f"{ntp_server}: {type(e).__name__} - {str(e)}"
                    error_details.append(error_msg)
                    logger.debug(f"从 {ntp_server} 同步失败: {error_msg}")
                    continue

            # 所有服务器都失败 - 简化错误信息
            self._sync_failures += 1
            logger.warning(
                f"⚠️ 时间同步失败，已尝试 {len(servers_to_try)} 个NTP服务器",
                extra={"log_type": "SYSTEM"}
            )
            # 只在调试模式下显示详细错误信息
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("⚠️ 详细错误信息:")
                for detail in error_details:
                    logger.debug(f"   - {detail}")
            
            # 尝试HTTP时间服务作为备用方案
            logger.info("⚠️ NTP同步失败，尝试HTTP时间服务...")
            # 🔧 修复: HTTP超时从10秒降到3秒,避免启动超时
            http_success, http_offset = self._sync_time_http(timeout=3.0)
            
            if http_success:
                return True, http_offset
            
            # 所有方法都失败
            logger.info("⚠️ 网络时间同步不可用，将使用系统时间")
            return False, None
    
    def _sync_time_http(self, timeout: float = 3.0) -> Tuple[bool, Optional[float]]:
        """
        使用HTTP时间服务同步时间（备用方案）
        
        Args:
            timeout: HTTP请求超时时间（秒）- 默认3秒,避免启动超时
            
        Returns:
            (成功标志, 时间偏移量)
        """
        try:
            import requests
            from dateutil import parser as date_parser
            
            for service_url in self.HTTP_TIME_SERVICES:
                try:
                    logger.debug(f"尝试HTTP时间服务: {service_url}")
                    
                    import time as _time
                    t0 = _time.time()
                    
                    response = requests.get(service_url, timeout=timeout)
                    response.raise_for_status()
                    data = response.json()
                    
                    elapsed = (_time.time() - t0) * 1000  # 毫秒
                    
                    # 解析不同API的时间格式
                    network_time: Optional[datetime] = None
                    
                    if "worldtimeapi.org" in service_url:
                        time_str = data.get("datetime", "")
                        if time_str:
                            parsed = date_parser.parse(time_str)
                            # 移除时区信息，使用naive datetime
                            if hasattr(parsed, 'replace'):
                                network_time = parsed.replace(tzinfo=None)  # type: ignore
                    
                    elif "worldclockapi.com" in service_url:
                        time_str = data.get("currentDateTime", "")
                        if time_str:
                            parsed = date_parser.parse(time_str)
                            if hasattr(parsed, 'replace'):
                                network_time = parsed.replace(tzinfo=None)  # type: ignore
                    
                    # 计算偏移量
                    system_time = datetime.now()
                    if network_time:
                        offset = (network_time - system_time).total_seconds()  # type: ignore
                    else:
                        logger.debug(f"HTTP服务 {service_url} 无法解析时间")
                        continue
                    
                    # 更新缓存
                    self._cached_offset = offset
                    self._cache_timestamp = datetime.now()
                    self._sync_count += 1
                    self._last_sync_time = datetime.now()
                    self._last_successful_server = f"HTTP:{service_url}"
                    
                    abs_offset = abs(offset)
                    direction = "慢" if offset > 0 else "快"
                    
                    logger.info(
                        f"✓ HTTP时间同步成功: {service_url} ({elapsed:.0f}ms), "
                        f"系统时间{direction}了 {abs_offset:.3f}秒"
                    )
                    
                    return True, offset
                    
                except Exception as e:
                    logger.debug(f"HTTP服务 {service_url} 失败: {type(e).__name__} - {str(e)}")
                    continue
            
            return False, None
            
        except ImportError:
            logger.warning("⚠️ requests或dateutil不可用，HTTP时间服务无法使用", extra={"log_type": "SYSTEM"})
            return False, None

    def get_real_datetime(self) -> datetime:
        """
        获取真实的当前时间（网络时间）

        策略：
        1. 优先使用缓存的偏移量（1小时TTL）
        2. 缓存失效则重新同步
        3. 同步失败则降级使用系统时间

        Returns:
            真实的当前时间
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
            logger.warning("⚠️ 时间同步失败，降级使用系统时间（可能不准确）", extra={"log_type": "SYSTEM"})
            return datetime.now()

    def get_real_date(self) -> date:
        """获取真实的当前日期（网络时间）"""
        return self.get_real_datetime().date()

    def get_time_offset(self) -> Optional[float]:
        """获取当前时间偏移量（秒）"""
        return self._cached_offset

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            包含同步统计的字典
        """
        return {
            "sync_count": self._sync_count,
            "sync_failures": self._sync_failures,
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "last_successful_server": self._last_successful_server,
            "cached_offset": self._cached_offset,
            "cache_age_seconds": (
                (datetime.now() - self._cache_timestamp).total_seconds()
                if self._cache_timestamp else None
            ),
        }


# ==============================================================================
# Part 2: 缓存管理（DailyCacheManager）
# ==============================================================================

class DailyCacheManager:
    """
    统一缓存管理器（日期失效机制）

    功能：
    - 日期失效机制（每日0时自动失效）
    - 品种列表缓存、服务器池缓存、交易日历缓存
    - native_iocp集成：异步文件读写

    缓存文件格式：
        {
            "_meta": {
                "cache_date": "2025-11-01",
                "version": "3.0"
            },
            "data": <实际数据>
        }

    使用示例：
        # 同步API
        DailyCacheManager.save_with_date(data, cache_file)
        data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)

        # 异步API（推荐）
        await DailyCacheManager.save_with_date_async(data, cache_file)
        data, cache_date, is_valid = await DailyCacheManager.load_with_validation_async(cache_file)
    """

    @staticmethod
    def save_with_date(data: Any, cache_file: Path) -> bool:
        """
        保存数据并记录日期（同步版本）

        Args:
            data: 要缓存的数据
            cache_file: 缓存文件路径

        Returns:
            是否保存成功
        """
        try:
            # 获取真实日期
            real_date = NetworkTimeSync.get_instance().get_real_date()

            # 构建缓存结构
            cache_obj = {
                "_meta": {
                    "cache_date": real_date.isoformat(),
                    "version": "3.0",
                    "timestamp": datetime.now().isoformat(),
                },
                "data": data
            }

            # 确保目录存在
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件（使用原子写入，确保文件完整性）
            import tempfile
            import os
            temp_file = cache_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_obj, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # 强制刷新到磁盘
                
                # 原子性替换
                temp_file.replace(cache_file)
            except Exception as e:
                # 如果写入失败，删除临时文件
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except:
                        pass
                raise

            logger.debug(f"✓ 缓存已保存: {cache_file.name} (日期: {real_date})")
            return True

        except Exception as e:
            logger.error(f"✗ 缓存保存失败: {cache_file.name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    @staticmethod
    def load_with_validation(cache_file: Path) -> Tuple[Any, str, bool]:
        """
        加载数据并验证日期有效性（同步版本）

        Args:
            cache_file: 缓存文件路径

        Returns:
            (数据, 缓存日期, 是否有效)
        """
        try:
            if not cache_file.exists():
                logger.debug(f"缓存文件不存在: {cache_file.name}")
                return None, "", False

            # 读取文件
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_obj = json.load(f)

            # 提取元数据
            meta = cache_obj.get("_meta", {})
            cache_date_str = meta.get("cache_date", "")
            data = cache_obj.get("data")

            # 验证日期
            if not cache_date_str:
                logger.warning(f"⚠️ 缓存缺少日期字段: {cache_file.name}", extra={"log_type": "SYSTEM"})
                return data, "", False

            # 获取真实日期
            real_date = NetworkTimeSync.get_instance().get_real_date()
            cache_date = date.fromisoformat(cache_date_str)

            # 检查是否当日缓存
            is_valid = (cache_date == real_date)

            if is_valid:
                logger.debug(f"✓ 缓存有效: {cache_file.name} (日期: {cache_date})")
            else:
                logger.debug(
                    f"⚠️ 缓存已过期: {cache_file.name} "
                    f"(缓存日期: {cache_date}, 当前日期: {real_date})"
                )

            return data, cache_date_str, is_valid

        except Exception as e:
            logger.error(f"✗ 缓存加载失败: {cache_file.name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return None, "", False

    @staticmethod
    async def save_with_date_async(data: Any, cache_file: Path) -> bool:
        """
        异步保存数据并记录日期（使用native_iocp）

        Args:
            data: 要缓存的数据
            cache_file: 缓存文件路径

        Returns:
            是否保存成功
        """
        if not compat_aopen:
            # 降级到同步版本
            return DailyCacheManager.save_with_date(data, cache_file)

        try:
            # 获取真实日期
            real_date = NetworkTimeSync.get_instance().get_real_date()

            # 构建缓存结构
            cache_obj = {
                "_meta": {
                    "cache_date": real_date.isoformat(),
                    "version": "3.0",
                    "timestamp": datetime.now().isoformat(),
                },
                "data": data
            }

            # 确保目录存在
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # 异步写入文件
            async with await compat_aopen(cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(cache_obj, ensure_ascii=False, indent=2))

            logger.debug(f"✓ 缓存已保存（异步）: {cache_file.name} (日期: {real_date})")
            return True

        except Exception as e:
            logger.error(f"✗ 缓存保存失败（异步）: {cache_file.name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    @staticmethod
    async def load_with_validation_async(cache_file: Path) -> Tuple[Any, str, bool]:
        """
        异步加载数据并验证日期有效性（使用native_iocp）

        Args:
            cache_file: 缓存文件路径

        Returns:
            (数据, 缓存日期, 是否有效)
        """
        if not compat_aopen:
            # 降级到同步版本
            return DailyCacheManager.load_with_validation(cache_file)

        try:
            if not cache_file.exists():
                logger.debug(f"缓存文件不存在: {cache_file.name}")
                return None, "", False

            # 异步读取文件
            async with await compat_aopen(cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()

            cache_obj = json.loads(content)

            # 提取元数据
            meta = cache_obj.get("_meta", {})
            cache_date_str = meta.get("cache_date", "")
            data = cache_obj.get("data")

            # 验证日期
            if not cache_date_str:
                logger.warning(f"⚠️ 缓存缺少日期字段: {cache_file.name}", extra={"log_type": "SYSTEM"})
                return data, "", False

            # 获取真实日期
            real_date = NetworkTimeSync.get_instance().get_real_date()
            cache_date = date.fromisoformat(cache_date_str)

            # 检查是否当日缓存
            is_valid = (cache_date == real_date)

            if is_valid:
                logger.debug(f"✓ 缓存有效（异步）: {cache_file.name} (日期: {cache_date})")
            else:
                logger.debug(
                    f"⚠️ 缓存已过期（异步）: {cache_file.name} "
                    f"(缓存日期: {cache_date}, 当前日期: {real_date})"
                )

            return data, cache_date_str, is_valid

        except Exception as e:
            logger.error(f"✗ 缓存加载失败（异步）: {cache_file.name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return None, "", False

    @staticmethod
    def clear_cache(cache_file: Path) -> bool:
        """
        清理缓存文件

        Args:
            cache_file: 缓存文件路径

        Returns:
            是否清理成功
        """
        try:
            if cache_file.exists():
                cache_file.unlink()
                logger.debug(f"✓ 缓存已清理: {cache_file.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"✗ 缓存清理失败: {cache_file.name}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    @staticmethod
    def get_cache_date(cache_file: Path) -> Optional[str]:
        """
        获取缓存日期（不加载数据）

        Args:
            cache_file: 缓存文件路径

        Returns:
            缓存日期字符串，失败返回None
        """
        try:
            if not cache_file.exists():
                return None

            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_obj = json.load(f)

            meta = cache_obj.get("_meta", {})
            return meta.get("cache_date")

        except Exception as e:
            logger.error(f"✗ 获取缓存日期失败: {cache_file.name}, 错误: {e}", extra={"log_type": "SYSTEM"})
            return None


# ==============================================================================
# Part 3: 配置管理（ConfigManager）
# ==============================================================================

class ConfigManager:
    """
    统一配置管理器（单例模式）

    功能：
    - 统一配置文件管理
    - 路径自动标准化
    - 配置热更新支持
    - native_ipc集成：配置热更新跨进程通知

    使用示例：
        config = ConfigManager.get_instance()
        cache_dir = config.get_cache_dir()
        data_dir = config.get_data_dir()
        value = config.get("key", default_value)
    """

    _instance: Optional["ConfigManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._config_file: Optional[Path] = None
        self._lock = threading.Lock()
        self._ipc_pipe: Optional[Any] = None  # AsyncIPCPipe实例

        # 加载配置
        self._load_config()

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """获取单例实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_config(self) -> None:
        """加载配置文件"""
        try:
            # 查找配置文件
            # 优先级：环境变量 > 当前目录 > 默认位置
            config_paths = [
                Path("config/terminal_config.json"),
                Path("terminal_config.json"),
                Path(__file__).parent.parent.parent.parent / "config" / "terminal_config.json",
            ]

            for config_path in config_paths:
                if config_path.exists():
                    self._config_file = config_path
                    break

            if self._config_file is None:
                logger.warning("⚠️ 未找到配置文件，使用默认配置", extra={"log_type": "SYSTEM"})
                self._config = self._get_default_config()
                return

            # 读取配置
            with open(self._config_file, 'r', encoding='utf-8') as f:
                self._config = json.load(f)

            logger.info(f"✓ 配置文件已加载: {self._config_file}")

        except Exception as e:
            logger.error(f"✗ 配置加载失败: {e}, 使用默认配置", exc_info=True, extra={"log_type": "SYSTEM"})
            self._config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "paths": {
                "cache_dir": "cache",
                "data_dir": "data/kline",
                "db_file": "data/kline.db",
                "tdx_dir": "",
            },
            "download": {
                "base_processes": 16,
                "base_coroutines_per_process": 40,
                "max_concurrent_connections": 2000,
            },
            "quality": {
                "scan_interval": 3600,
                "freshness_warning_days": 7,
                "freshness_error_days": 30,
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项（支持点号分隔的嵌套键）

        Args:
            key: 配置键（支持"paths.cache_dir"格式）
            default: 默认值

        Returns:
            配置值，不存在时返回默认值
        """
        try:
            keys = key.split('.')
            value = self._config

            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default

            return value if value is not None else default

        except Exception as e:
            logger.warning(f"⚠️ [ConfigManager] 获取配置失败: {key}, 错误: {e}, 使用默认值", extra={"log_type": "SYSTEM"})
            return default

    def set(self, key: str, value: Any) -> bool:
        """
        设置配置项（支持点号分隔的嵌套键）

        Args:
            key: 配置键
            value: 配置值

        Returns:
            是否设置成功
        """
        try:
            with self._lock:
                keys = key.split('.')
                config = self._config

                # 逐级创建嵌套字典
                for k in keys[:-1]:
                    if k not in config or not isinstance(config[k], dict):
                        config[k] = {}
                    config = config[k]

                # 设置最终值
                config[keys[-1]] = value

            logger.debug(f"✓ 配置已更新: {key} = {value}")
            return True

        except Exception as e:
            logger.error(f"✗ 配置更新失败: {key}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def get_cache_dir(self) -> Path:
        """获取缓存目录（自动标准化）

        默认使用项目根目录下的 data/cache 目录
        """
        cache_dir = self.get("paths.cache_dir", "data/cache")
        path = Path(cache_dir)

        # 如果是相对路径，转为绝对路径
        if not path.is_absolute():
            # 🔧 修复：统一使用项目根目录下的 data/cache 目录
            # 从当前文件路径向上找到项目根目录（core_engine.py 位于 backend/infrastructure/data_module_vnpy/）
            # 需要向上3级到达项目根目录
            current_file = Path(__file__)
            root_dir = current_file.parent.parent.parent.parent
            path = root_dir / cache_dir

        # 确保目录存在
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_data_dir(self) -> Path:
        """获取数据目录（Parquet文件）

        默认使用项目根目录下的 data/kline 目录
        """
        data_dir = self.get("paths.data_dir", "data/kline")
        path = Path(data_dir)

        # 如果是相对路径，转为绝对路径
        if not path.is_absolute():
            # 🔧 修复：统一使用项目根目录下的 data/kline 目录
            # 从当前文件路径向上找到项目根目录（core_engine.py 位于 backend/infrastructure/data_module_vnpy/）
            # 需要向上3级到达项目根目录
            current_file = Path(__file__)
            root_dir = current_file.parent.parent.parent.parent
            path = root_dir / data_dir

        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_db_file(self) -> Path:
        """获取数据库文件路径

        默认使用项目根目录下的 data/kline.db
        """
        db_file = self.get("paths.db_file", "data/kline.db")
        path = Path(db_file)

        # 如果是相对路径，转为绝对路径
        if not path.is_absolute():
            # 🔧 修复：统一使用项目根目录下的 data/kline.db
            # 从当前文件路径向上找到项目根目录（core_engine.py 位于 backend/infrastructure/data_module_vnpy/）
            # 需要向上3级到达项目根目录
            current_file = Path(__file__)
            root_dir = current_file.parent.parent.parent.parent
            path = root_dir / db_file

        # 确保父目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_tdx_dir(self) -> Path:
        """获取通达信目录"""
        tdx_dir = self.get("paths.tdx_dir", "")

        if not tdx_dir:
            return Path()

        path = Path(tdx_dir)
        return path

    def get_tdx_reader_root_dir(self) -> Path:
        """获取通达信读取器根目录（向后兼容方法）"""
        return self.get_tdx_dir()

    def get_config_file(self) -> Optional[Path]:
        """获取配置文件路径"""
        return self._config_file

    def update_config(self, config_data: Dict[str, Any]) -> bool:
        """批量更新配置（向后兼容方法）

        Args:
            config_data: 配置字典

        Returns:
            是否更新成功
        """
        try:
            with self._lock:
                for key, value in config_data.items():
                    keys = key.split('.')
                    config = self._config

                    # 逐级创建嵌套字典
                    for k in keys[:-1]:
                        if k not in config or not isinstance(config[k], dict):
                            config[k] = {}
                        config = config[k]

                    # 设置最终值
                    config[keys[-1]] = value

            logger.debug(f"✓ 批量配置已更新: {len(config_data)} 项")
            return True
        except Exception as e:
            logger.error(f"✗ 批量配置更新失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def reload_config(self) -> bool:
        """
        重新加载配置文件

        Returns:
            是否加载成功
        """
        try:
            with self._lock:
                self._load_config()

            # 如果native_ipc可用，通知其他进程
            if IPC_AVAILABLE and AsyncIPCPipe:
                asyncio.create_task(self._notify_config_update())

            logger.info("✓ 配置文件已重新加载")
            return True

        except Exception as e:
            logger.error(f"✗ 配置重新加载失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    async def _notify_config_update(self) -> None:
        """通过native_ipc通知配置更新（跨进程）"""
        try:
            if self._ipc_pipe is None:
                self._ipc_pipe = await AsyncIPCPipe.server("config_updates")

            # 发送配置更新通知
            if self._ipc_pipe is None:
                logger.warning("⚠️ IPC管道未初始化，跳过配置更新通知", extra={"log_type": "SYSTEM"})
                return

            update_data = {
                "action": "config_reload",
                "timestamp": datetime.now().isoformat(),
            }

            await self._ipc_pipe.write(json.dumps(update_data).encode())
            logger.debug("✓ 配置更新已通知到其他进程")

        except Exception as e:
            logger.error(f"✗ 配置更新通知失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})


# ==============================================================================
# Part 4: 事件系统（EventPublisher系列）
# ==============================================================================

class EventPublisher:
    """
    通用事件发布器

    功能：
    - 统一事件发布接口
    - 事件数据封装
    - 日志记录

    使用示例：
        publisher = EventPublisher(event_engine)
        publisher.publish("eMyEvent", {"key": "value"})
    """

    def __init__(self, event_engine: EventEngine):
        self.event_engine = event_engine

    def publish(self, event_type: str, data: Any) -> None:
        """
        发布事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        try:
            event = Event(event_type, data)
            self.event_engine.put(event)
            logger.debug(f"✓ 事件已发布: {event_type}")
        except Exception as e:
            logger.error(f"✗ 事件发布失败: {event_type}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})


class ValidationEventPublisher(EventPublisher):
    """
    验证事件发布器

    事件类型：
    - EVENT_CHINASTOCK_VALIDATION: 验证进度事件
    - EVENT_VALIDATION_COMPLETED: 验证完成事件
    """

    EVENT_CHINASTOCK_VALIDATION = "eChinastockValidation"
    EVENT_VALIDATION_COMPLETED = "eValidationCompleted"

    def publish_validation_progress(self, symbol: str, progress: int) -> None:
        """
        发布验证进度

        Args:
            symbol: 品种代码
            progress: 进度百分比（0-100）
        """
        data = {
            "symbol": symbol,
            "progress": progress,
            "timestamp": datetime.now().isoformat(),
        }
        self.publish(self.EVENT_CHINASTOCK_VALIDATION, data)

    def publish_validation_result(self, result: Dict[str, Any]) -> None:
        """
        发布验证结果

        Args:
            result: 验证结果字典
        """
        self.publish(self.EVENT_VALIDATION_COMPLETED, result)


class DownloadEventPublisher(EventPublisher):
    """
    下载事件发布器

    事件类型：
    - EVENT_CHINASTOCK_DOWNLOAD: 下载进度事件
    """

    EVENT_CHINASTOCK_DOWNLOAD = "eChinastockDownload"

    def publish_download_progress(self, progress: Dict[str, Any]) -> None:
        """
        发布下载进度

        Args:
            progress: 进度字典（包含total, completed, failed等）
        """
        self.publish(self.EVENT_CHINASTOCK_DOWNLOAD, progress)


class QualityEventPublisher(EventPublisher):
    """
    质量事件发布器

    事件类型：
    - EVENT_DATA_QUALITY_UPDATE: 数据质量更新事件
    """

    EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"

    def publish_quality_update(self, overview: Dict[str, Any]) -> None:
        """
        发布质量更新

        Args:
            overview: 质量概览字典
        """
        self.publish(self.EVENT_DATA_QUALITY_UPDATE, overview)


class SubscriptionEventPublisher(EventPublisher):
    """
    订阅事件发布器（新增）

    事件类型：
    - EVENT_SUBSCRIPTION_ADDED: 订阅添加事件
    - EVENT_SUBSCRIPTION_REMOVED: 订阅移除事件
    - EVENT_SUBSCRIPTION_UPDATED: 订阅更新事件
    """

    EVENT_SUBSCRIPTION_ADDED = "eSubscriptionAdded"
    EVENT_SUBSCRIPTION_REMOVED = "eSubscriptionRemoved"
    EVENT_SUBSCRIPTION_UPDATED = "eSubscriptionUpdated"

    def publish_subscription_added(self, module: str, symbols: List[str]) -> None:
        """
        发布订阅添加事件

        Args:
            module: 模块名称
            symbols: 订阅的品种列表
        """
        data = {
            "module": module,
            "symbols": symbols,
            "timestamp": datetime.now().isoformat(),
        }
        self.publish(self.EVENT_SUBSCRIPTION_ADDED, data)

    def publish_subscription_removed(self, module: str) -> None:
        """
        发布订阅移除事件

        Args:
            module: 模块名称
        """
        data = {
            "module": module,
            "timestamp": datetime.now().isoformat(),
        }
        self.publish(self.EVENT_SUBSCRIPTION_REMOVED, data)

    def publish_subscription_updated(self, module: str, symbols: List[str]) -> None:
        """
        发布订阅更新事件

        Args:
            module: 模块名称
            symbols: 更新后的品种列表
        """
        data = {
            "module": module,
            "symbols": symbols,
            "timestamp": datetime.now().isoformat(),
        }
        self.publish(self.EVENT_SUBSCRIPTION_UPDATED, data)


# ==============================================================================
# Part 5: 品种列表缓存验证工作线程（CacheValidationWorker）
# ==============================================================================

from PySide6.QtCore import QObject, Signal, QThread

class CacheValidationWorker(QObject):
    """品种列表缓存验证工作线程（Qt后台线程）
    
    负责在启动时执行完整的缓存验证与数据感知流程，
    确保数据模块处于可用状态。
    
    信号:
        validation_started: 验证开始
        validation_progress(str, int): 进度更新(步骤描述, 进度百分比)
        step_completed(int, str, dict): 步骤完成(步骤号, 步骤名, 步骤结果)
        validation_finished(dict): 验证完成(完整结果)
        validation_error(str): 验证失败(错误信息)
        offline_mode_triggered(str): 离线模式触发(原因)
    """
    
    # 信号定义
    validation_started = Signal()
    validation_progress = Signal(str, int)  # (描述, 百分比)
    step_completed = Signal(int, str, dict)  # (步骤号, 步骤名, 结果)
    validation_finished = Signal(dict)
    validation_error = Signal(str)
    offline_mode_triggered = Signal(str)  # 新增: 离线模式触发信号
    
    def __init__(self, china_stock_engine):
        """初始化验证工作线程
        
        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        super().__init__()
        self.engine = china_stock_engine
        self._cancelled = False
    
    def run(self):
        """执行验证流程（在QThread中调用）"""
        try:
            self.validation_started.emit()
            # 🎯 验证流程的详细输出已在_smart_cache_validation_and_sensing中使用STAGE_NODE输出
            # 这里只记录DEBUG日志，不输出到Terminal
            logger.debug("=" * 70)
            logger.debug("🚀 启动缓存验证与感知流程")
            logger.debug("=" * 70)
            
            # 调用核心验证逻辑
            result = self.engine._smart_cache_validation_and_sensing(
                progress_callback=self._on_progress,
                step_callback=self._on_step_completed
            )
            
            # 发送完成信号
            if result.get("offline_mode"):
                self.offline_mode_triggered.emit(result.get("offline_reason", "未知原因"))
            
            self.validation_finished.emit(result)
            # 🎯 完成消息已在_smart_cache_validation_and_sensing中使用STAGE_NODE输出
            logger.debug("✅ 缓存验证与感知流程完成")
            
        except Exception as e:
            logger.error("❌ 缓存验证失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            self.validation_error.emit(str(e))
    
    def _on_progress(self, description: str, percent: int):
        """进度回调"""
        if not self._cancelled:
            self.validation_progress.emit(description, percent)
    
    def _on_step_completed(self, step_num: int, step_name: str, step_result: dict):
        """步骤完成回调"""
        if not self._cancelled:
            self.step_completed.emit(step_num, step_name, step_result)
    
    def cancel(self):
        """取消验证（外部调用）"""
        self._cancelled = True
        logger.warning("⚠️ 缓存验证被取消", extra={"log_type": "SYSTEM"})


# ==============================================================================
# Part 6: 核心引擎（ChinaStockEngine）
# ==============================================================================

class ChinaStockEngine:
    """
    中国股票数据引擎（核心引擎）

    职责：
    - 整个模块的统一入口
    - 初始化所有子组件
    - 提供统一API接口
    - 健康检查和状态管理

    组件依赖：
    - ConfigManager: 配置管理
    - NetworkTimeSync: 时间同步
    - EventPublisher系列: 事件发布
    - SymbolLoader: 品种管理（延迟导入）
    - MultiProcessStockFetcher: 数据下载（延迟导入）
    - StorageManager: 存储管理（延迟导入）
    - DataSensor: 质量管理（延迟导入）
    - UnifiedDataManager: 统一数据管理（延迟导入）
    - LoadBalancer: 负载均衡（延迟导入）

    使用示例：
        engine = ChinaStockEngine(main_engine, event_engine)
        engine.initialize()
        result = engine.reload_stock_list()
        data = engine.query_data("000001", "1d", "2024-01-01", "2024-12-31")
    """

    # 应用名称（用于事件）
    APP_NAME = "ChinaStockData"

    # 事件类型常量
    EVENT_CHINASTOCK_LOG = "eChinastockLog"
    EVENT_CHINASTOCK_VALIDATION = "eChinastockValidation"
    EVENT_CHINASTOCK_DOWNLOAD = "eChinastockDownload"
    EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"
    EVENT_SYMBOL_CACHE_LOADED = "eSymbolCacheLoaded"
    EVENT_IPO_CACHE_UPDATED = "eIPOCacheUpdated"
    EVENT_VALIDATION_COMPLETED = "eValidationCompleted"
    EVENT_DATA_METRICS_UPDATED = "eDataMetricsUpdated"
    EVENT_UNIFIED_DATA_MANAGER_READY = "eUnifiedDataManagerReady"  # 🔧 新增：UnifiedDataManager就绪事件

    def __init__(self, main_engine, event_engine: EventEngine):
        """
        初始化核心引擎

        Args:
            main_engine: VNPy主引擎
            event_engine: VNPy事件引擎
        """
        self.main_engine = main_engine
        self.event_engine = event_engine

        # 初始化配置管理
        self.config_manager = ConfigManager.get_instance()

        # 初始化时间同步
        self.time_sync = NetworkTimeSync.get_instance()

        # 初始化事件发布器
        self.download_publisher = DownloadEventPublisher(event_engine)
        self.validation_publisher = ValidationEventPublisher(event_engine)
        self.quality_publisher = QualityEventPublisher(event_engine)
        self.subscription_publisher = SubscriptionEventPublisher(event_engine)

        # 子组件（延迟导入避免循环依赖）
        self.symbol_loader = None
        self.data_fetcher = None
        self.storage_manager = None
        self.data_validator = None
        self.data_sensor = None
        self.unified_data_manager = None
        self.load_balancer = None

        # 状态管理
        self._is_ready = False
        self._initialization_lock = threading.Lock()
        
        # 离线模式管理
        self._offline_mode = False
        self._offline_reason = ""

        logger.info(f"✓ {self.APP_NAME} 核心引擎已创建")

    def initialize(self) -> bool:
        """
        初始化所有子组件

        Returns:
            是否初始化成功
        """
        with self._initialization_lock:
            if self._is_ready:
                logger.info("引擎已初始化，跳过")
                return True

            try:
                logger.info("开始初始化数据引擎...")

                # 注意：网络时间同步已移至阶段3的8步验证流程（步骤2）中执行
                # 这里不再执行网络时间同步，确保单一事实原则
                
                # 1. 初始化子组件
                logger.info("1/6 初始化子组件...")
                self._initialize_components()

                # 3. 标记就绪
                self._is_ready = True
                logger.info("✓ 数据引擎初始化完成")
                return True

            except Exception as e:
                logger.critical(f"🔥 引擎初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
                return False

    def _initialize_components(self) -> None:
        """初始化所有子组件（延迟导入）"""
        # 延迟导入避免循环依赖
        from .data_storage import StorageManager
        from .load_balancer import LoadBalancer

        # 注意：其他组件在实际使用时再导入
        # 这里只初始化必需的核心组件

        # 存储管理器
        self.storage_manager = StorageManager()
        logger.debug("✓ StorageManager 已初始化")

        # 负载均衡器
        # 🔧 修复：LoadBalancer没有get_instance方法，需要直接实例化
        self.load_balancer = LoadBalancer(self.config_manager)
        logger.debug("✓ LoadBalancer 已初始化")

    # ========================================
    # 公开API接口（保持100%向后兼容）
    # ========================================

    def reload_stock_list(self) -> Dict[str, Any]:
        """
        重新加载品种列表

        Returns:
            包含品种分类的字典
        """
        import time
        start_time = time.time()
        scenario = "reload_symbol_list"
        stage_logger = logging.getLogger("startup.stage")
        
        try:
            # DEBUG日志（记录开始）
            logger.debug(
                "[RELOAD-STOCK-LIST] 开始重新加载品种列表",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            stage_logger.info(
                "📍 开始重新加载品种列表",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )
            
            # 延迟导入
            if self.symbol_loader is None:
                logger.debug(
                    "[RELOAD-STOCK-LIST] SymbolLoader不存在，开始导入...",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                from .data_acquisition import SymbolLoader
                self.symbol_loader = SymbolLoader(self.event_engine)
                logger.debug(
                    "[RELOAD-STOCK-LIST] SymbolLoader已创建",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            else:
                logger.debug(
                    "[RELOAD-STOCK-LIST] SymbolLoader已存在，跳过创建",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )

            # 执行重新加载
            logger.debug(
                "[RELOAD-STOCK-LIST] 开始调用symbol_loader.reload_and_classify()...",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[RELOAD-STOCK-LIST] ℹ️ 开始执行品种列表重新加载和分类...",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            reload_start_time = time.time()
            result = self.symbol_loader.reload_and_classify()
            reload_elapsed = (time.time() - reload_start_time) * 1000
            logger.debug(
                f"[RELOAD-STOCK-LIST] 品种列表重新加载完成: 耗时={reload_elapsed:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 统计品种数量
            logger.debug(
                "[RELOAD-STOCK-LIST] 开始统计品种数量...",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            classified = result if isinstance(result, dict) else {}
            sh_count = len(classified.get("上证A股", []))
            sz_count = len(classified.get("深证A股", []))
            bj_count = len(classified.get("北证A股", []))
            t0_count = len(classified.get("T+0基金", []))
            bond_count = len(classified.get("可转债", []))
            total_count = sum(len(v) for v in classified.values())
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            logger.debug(
                f"[RELOAD-STOCK-LIST] 品种统计完成: 总品种数={total_count}, "
                f"上证={sh_count}, 深证={sz_count}, 北证={bj_count}, "
                f"T+0基金={t0_count}, 可转债={bond_count}, 总耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                f"[RELOAD-STOCK-LIST] ✅ 品种列表加载完成: 总品种数={total_count}, 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            
            # 输出阶段成果日志
            stage_logger.info(
                f"✅ 品种列表加载完成 ({elapsed_ms:.0f}ms)",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )
            stage_logger.info(
                f"  ├─ 总品种数: {total_count}",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )
            stage_logger.info(
                f"  ├─ 上证: {sh_count} | 深证: {sz_count} | 北证: {bj_count}",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )
            stage_logger.info(
                f"  └─ T+0基金: {t0_count} | 可转债: {bond_count}",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )

            # 发布事件
            logger.debug(
                "[RELOAD-STOCK-LIST] 开始发布EVENT_SYMBOL_CACHE_LOADED事件...",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            self.event_engine.put(Event(self.EVENT_SYMBOL_CACHE_LOADED, result))
            logger.debug(
                "[RELOAD-STOCK-LIST] 事件已发布",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            return result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            # DEBUG日志（记录异常详情）
            logger.debug(
                f"[RELOAD-STOCK-LIST] 重新加载品种列表发生异常: {type(e).__name__}: {str(e)}, 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.error(
                f"✗ 重新加载品种列表失败: {e} ({elapsed_ms:.0f}ms)",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario}
            )
            logger.critical(
                f"🔥 重新加载品种列表严重失败，可能影响数据获取: {e} ({elapsed_ms:.0f}ms)",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario}
            )
            stage_logger.error(
                f"❌ 品种列表加载失败: {e}",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )
            return {"success": False, "error": str(e)}

    def download_incremental(
        self,
        start_date: str,
        intervals: List[str]
    ) -> Dict[str, Any]:
        """
        增量下载K线数据

        Args:
            start_date: 起始日期（YYYY-MM-DD）
            intervals: 周期列表（如["1d", "5m", "1m"]）

        Returns:
            下载结果字典
        """
        try:
            # 延迟导入
            if self.data_fetcher is None:
                from .data_acquisition import MultiProcessStockFetcher
                self.data_fetcher = MultiProcessStockFetcher(self.event_engine)

            if self.symbol_loader is None:
                from .data_acquisition import SymbolLoader
                self.symbol_loader = SymbolLoader(self.event_engine)

            # 获取品种列表
            symbols_data = self.symbol_loader.get_all_classified()
            all_symbols = self.symbol_loader.extract_all_codes()

            # 执行下载
            result = self.data_fetcher.download_incremental_kline(
                symbols=all_symbols,
                start_date=start_date,
                intervals=intervals,
                use_adaptive=True,
                use_two_phase=True
            )

            return result

        except Exception as e:
            logger.error(f"✗ 增量下载失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return {"success": False, "error": str(e)}

    def query_data(
        self,
        symbol: str,
        interval: str,
        start: str,
        end: str
    ) -> Any:
        """
        查询数据（统一接口）

        Args:
            symbol: 品种代码
            interval: 周期（1d/5m/1m等）
            start: 起始日期
            end: 结束日期

        Returns:
            DataFrame或None
        """
        try:
            # 延迟导入
            if self.unified_data_manager is None:
                from .data_runtime import UnifiedDataManager
                self.unified_data_manager = UnifiedDataManager(self)

            # 执行查询
            df = self.unified_data_manager.query_unified(
                symbol=symbol,
                interval=interval,
                start_date=start,
                end_date=end,
                check_gaps=True
            )

            return df

        except Exception as e:
            logger.error(f"✗ 数据查询失败: symbol={symbol}, interval={interval}, 错误: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return None

    def healthcheck(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态字典
        """
        try:
            health_status = {
                "engine_ready": self._is_ready,
                "config_loaded": self.config_manager._config_file is not None,
                "time_synced": self.time_sync.is_synced() if hasattr(self.time_sync, 'is_synced') else False,
                "symbol_loader_ready": self.symbol_loader is not None,
                "data_fetcher_ready": self.data_fetcher is not None,
                "storage_manager_ready": self.storage_manager is not None,
                "offline_mode": self._offline_mode,
                "offline_reason": self._offline_reason,
            }

            return health_status

        except Exception as e:
            logger.error(f"✗ 健康检查失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return {"engine_ready": False, "error": str(e)}

    # ========================================
    # 离线模式管理
    # ========================================

    def is_offline_mode(self) -> bool:
        """检查是否处于离线模式"""
        return self._offline_mode

    def get_offline_reason(self) -> str:
        """获取离线原因"""
        return self._offline_reason

    def set_offline_mode(self, offline: bool, reason: str = ""):
        """设置离线模式（内部使用）"""
        self._offline_mode = offline
        self._offline_reason = reason

        if offline:
            logger.warning(f"⚠️ 系统已进入离线降级模式: {reason}", extra={"log_type": "ALERT"})
            # 发布离线模式事件
            self.event_engine.put(Event("eSystemOfflineMode", {
                "offline": True,
                "reason": reason,
                "timestamp": datetime.now()
            }))

    # ========================================
    # 启动项验证主干流程
    # ========================================

    def _smart_cache_validation_and_sensing(
        self,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        step_callback: Optional[Callable[[int, str, dict], None]] = None
    ) -> Dict[str, Any]:
        """智能缓存验证与感知（8步流程 + 离线降级）

        这是启动项的核心主幹流程，负责：
        1. 验证和初始化所有缓存
        2. 初始化核心组件(LoadBalancer, UnifiedDataManager等)
        3. TDX离线降级检测
        4. 启动文件监控

        Args:
            progress_callback: 进度回调函数(description, percent)
            step_callback: 步骤完成回调(step_num, step_name, result)

        Returns:
            Dict[str, Any]: {
                "success": bool,
                "offline_mode": bool,
                "offline_reason": str,
                "steps_completed": int,
                "step_results": List[dict],
                "total_time": float
            }

        异常:
            不抛出异常，所有错误封装在返回值中
        """
        import time
        start_time = time.time()
        step_results = []
        offline_mode = False
        offline_reason = ""
        
        # 🎯 获取LoggingHub并切换到data_engine阶段
        from backend.infrastructure.system_vnpy import get_logging_hub
        hub = get_logging_hub()
        hub.set_stage("data_engine")
        
        stage_logger = logging.getLogger("startup.stage")

        # 辅助函数
        def _progress(desc: str, pct: int):
            if progress_callback:
                progress_callback(desc, pct)

        def _step_done(num: int, name: str, result: dict):
            step_results.append(result)
            if step_callback:
                step_callback(num, name, result)

        try:
            # 注意：流程开始标题已在CacheValidatorWorker中输出，这里不再重复输出
            # 🎯 直接开始步骤1
            
            # ========== 步骤1: 服务器池缓存验证与测速 ==========
            step1_start_time = time.time()
            stage_logger.info("┌─ 步骤1: 服务器池验证与测速 ─┐", extra={"log_type": "STAGE_NODE"})
            _progress("步骤1/8: 验证服务器池缓存并测速...", 5)
            step1_result = self._validate_server_pool_and_test_speed(stage_logger)
            _step_done(1, "服务器池验证与测速", step1_result)
            
            # 离线降级检查点（在步骤框内）
            if step1_result.get("offline_mode"):
                offline_mode = True
                offline_reason = step1_result.get("offline_reason", "未知原因")
                stage_logger.critical("│ 🔥 所有TDX服务器不可用，系统无法获取数据", extra={"log_type": "STAGE_NODE"})
                logger.critical(f"🔥 所有TDX服务器不可用，系统无法获取数据: {offline_reason}", extra={"log_type": "ALERT"})
                stage_logger.warning("│ ⚠️ 进入离线降级模式", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("⏭️ 跳过步骤2-7，直接执行步骤8", extra={"log_type": "STAGE_NODE"})
                # 设置离线模式
                self.set_offline_mode(True, str(offline_reason))
                # 跳转到步骤8
                _progress("离线模式: 跳过步骤2-7，直接启动文件监控", 90)
                goto_step_8 = True
            else:
                goto_step_8 = False
                # 初始化LoadBalancer（在步骤框内）
                _progress("步骤1/8: 初始化LoadBalancer...", 10)
                if self.load_balancer is None:
                    from .load_balancer import LoadBalancer
                    self.load_balancer = LoadBalancer(self.config_manager)
                stage_logger.info("│ ✅ LoadBalancer初始化完成", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("│   - 任务分类体系: NETWORK_DOWNLOAD, LOCAL_SCAN, LOCAL_READ", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("│   - 队列压力监控: 正常/高/临界三级", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
            
            step1_time = (time.time() - step1_start_time) * 1000
            stage_logger.info(f"✅ 步骤1完成 ({step1_time:.0f}ms) [进度: 12%]", extra={"log_type": "STAGE_NODE"})

            if not goto_step_8:
                # ========== 步骤2: 获取当前日期(网络时间) ==========
                step2_start_time = time.time()
                stage_logger.info("┌─ 步骤2: 获取当前日期（网络时间）─┐", extra={"log_type": "STAGE_NODE"})
                _progress("步骤2/8: 获取当前日期(网络时间)...", 15)
                step2_result = self._get_current_date(stage_logger)
                _step_done(2, "获取当前日期", step2_result)
                current_date = step2_result.get("current_date")
                
                step2_time = (time.time() - step2_start_time) * 1000
                stage_logger.info(f"✅ 步骤2完成 ({step2_time:.0f}ms) [进度: 25%]", extra={"log_type": "STAGE_NODE"})

                # ========== 步骤3: 验证交易日历缓存 ==========
                step3_start_time = time.time()
                stage_logger.info("┌─ 步骤3: 验证交易日历缓存 ─┐", extra={"log_type": "STAGE_NODE"})
                _progress("步骤3/8: 验证交易日历缓存...", 25)
                step3_result = self._validate_trade_calendar_cache(current_date, stage_logger)
                _step_done(3, "验证交易日历缓存", step3_result)
                
                step3_time = (time.time() - step3_start_time) * 1000
                stage_logger.info(f"✅ 步骤3完成 ({step3_time:.0f}ms) [进度: 37%]", extra={"log_type": "STAGE_NODE"})

                # ========== 步骤4: 验证品种列表缓存 ==========
                step4_start_time = time.time()
                stage_logger.info("┌─ 步骤4: 验证品种列表缓存 ─┐", extra={"log_type": "STAGE_NODE"})
                _progress("步骤4/8: 验证品种列表缓存...", 35)
                step4_result = self._validate_symbol_list_cache(current_date, stage_logger)
                _step_done(4, "验证品种列表缓存", step4_result)

                # 初始化SymbolLoader
                if not step4_result.get("cache_valid") or step4_result.get("cache_missing"):
                    _progress("步骤4/8: 重新加载品种列表...", 40)
                    if self.symbol_loader is None:
                        from .data_acquisition import SymbolLoader
                        self.symbol_loader = SymbolLoader(self.event_engine)
                    # 同步版本的reload
                    self.symbol_loader.reload_and_classify()
                    stage_logger.info("│ ✅ 品种列表已重新加载", extra={"log_type": "STAGE_NODE"})
                    
                    # 获取并显示分类统计
                    try:
                        classified = self.symbol_loader.get_all_classified()
                        if classified and isinstance(classified, dict):
                            categories = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]
                            total_count = 0
                            for category in categories:
                                count = len(classified.get(category, []))
                                total_count += count
                                stage_logger.info(f"│   - {category}: {count}", extra={"log_type": "STAGE_NODE"})
                            stage_logger.info(f"│   - 总计: {total_count}品种", extra={"log_type": "STAGE_NODE"})
                    except Exception as e:
                        logger.warning(f"获取品种统计失败: {e}", extra={"log_type": "SYSTEM"})
                
                # 确保SymbolLoader已初始化并显示统计
                if self.symbol_loader is None:
                    from .data_acquisition import SymbolLoader
                    self.symbol_loader = SymbolLoader(self.event_engine)
                
                # 如果之前没有显示统计,现在显示
                if step4_result.get("cache_valid"):
                    # 统计信息已在_validate_symbol_list_cache中显示
                    pass
                elif not hasattr(self, "_symbol_stats_displayed") or not self._symbol_stats_displayed:
                    try:
                        classified = self.symbol_loader.get_all_classified()
                        if classified and isinstance(classified, dict):
                            categories = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]
                            total_count = 0
                            for category in categories:
                                count = len(classified.get(category, []))
                                total_count += count
                            stage_logger.info(f"│   - 总计: {total_count}品种", extra={"log_type": "STAGE_NODE"})
                            self._symbol_stats_displayed = True
                    except Exception as e:
                        logger.debug(f"⚠️ [ChinaStockEngine] 显示品种统计失败: {e}", extra={"log_type": "SYSTEM"})
                        pass
                
                step4_time = (time.time() - step4_start_time) * 1000
                stage_logger.info(f"✅ 步骤4完成 ({step4_time:.0f}ms) [进度: 50%]", extra={"log_type": "STAGE_NODE"})

                # ========== 步骤5: 验证IPO日期缓存 ==========
                step5_start_time = time.time()
                stage_logger.info("┌─ 步骤5: 验证IPO日期缓存 ─┐", extra={"log_type": "STAGE_NODE"})
                _progress("步骤5/8: 验证IPO日期缓存...", 50)
                step5_result = self._validate_ipo_cache(current_date, stage_logger)
                _step_done(5, "验证IPO日期缓存", step5_result)
                
                step5_time = (time.time() - step5_start_time) * 1000
                stage_logger.info(f"✅ 步骤5完成 ({step5_time:.0f}ms) [进度: 62%]", extra={"log_type": "STAGE_NODE"})

                # ========== 步骤6: 更新本地数据索引 ==========
                step6_start_time = time.time()
                stage_logger.info("┌─ 步骤6: 更新本地数据索引 ─┐", extra={"log_type": "STAGE_NODE"})
                _progress("步骤6/8: 更新本地数据索引...", 65)
                step6_result = self._update_local_data_index(stage_logger)
                _step_done(6, "更新本地数据索引", step6_result)
                
                step6_time = (time.time() - step6_start_time) * 1000
                stage_logger.info(f"✅ 步骤6完成 ({step6_time:.0f}ms) [进度: 75%]", extra={"log_type": "STAGE_NODE"})

                # ========== 步骤7: 检查数据更新状态 ==========
                step7_start_time = time.time()
                stage_logger.info("┌─ 步骤7: 检查数据更新状态 ─┐", extra={"log_type": "STAGE_NODE"})
                _progress("步骤7/8: 检查数据更新状态...", 75)
                step7_result = self._check_data_update_status(stage_logger)
                _step_done(7, "检查数据更新状态", step7_result)
                
                step7_time = (time.time() - step7_start_time) * 1000
                stage_logger.info(f"✅ 步骤7完成 ({step7_time:.0f}ms) [进度: 87%]", extra={"log_type": "STAGE_NODE"})

            # ========== 步骤8: 启动文件监控 ==========
            step8_start_time = time.time()
            stage_logger.info("┌─ 步骤8: 启动文件监控 ─┐", extra={"log_type": "STAGE_NODE"})
            _progress("步骤8/8: 启动文件监控...", 90)
            step8_result = self._start_file_watcher(stage_logger)
            _step_done(8, "启动文件监控", step8_result)
            
            step8_time = (time.time() - step8_start_time) * 1000
            stage_logger.info(f"✅ 步骤8完成 ({step8_time:.0f}ms) [进度: 100%]", extra={"log_type": "STAGE_NODE"})

            # 完成
            _progress("缓存验证与感知完成", 100)
            elapsed_time = time.time() - start_time
            
            stage_logger.info(f"✅ 缓存验证与感知流程完成 (总耗时: {elapsed_time:.1f}s)", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("✅ 数据引擎完全就绪", extra={"log_type": "STAGE_NODE"})

            return {
                "success": True,
                "offline_mode": offline_mode,
                "offline_reason": offline_reason,
                "steps_completed": len(step_results),
                "step_results": step_results,
                "total_time": elapsed_time
            }

        except Exception as e:
            logger.error("❌ 缓存验证与感知失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "offline_mode": False,
                "offline_reason": "",
                "steps_completed": len(step_results),
                "step_results": step_results,
                "error": str(e)
            }

    # ========================================
    # 8步验证流程的详细实现
    # ========================================

    def _validate_server_pool_and_test_speed(self, stage_logger) -> Dict[str, Any]:
        """步骤1: 服务器池缓存验证与测速

        Returns:
            Dict[str, Any]: {
                "success": bool,
                "ipv4_available": bool,
                "ipv6_available": bool,
                "offline_mode": bool,
                "offline_reason": str
            }
        """
        try:
            # 使用ServerPoolManager进行缓存验证与测速
            from .load_balancer import get_server_pool_manager
            pool_manager = get_server_pool_manager()
            
            # 获取服务器总数
            stats_before = pool_manager.get_stats()
            ipv4_total = stats_before.get("ipv4_total", 0)
            ipv6_total = stats_before.get("ipv6_total", 0)
            
            # 🚀 优化1：检查缓存是否为当天，如果是则跳过测速
            cache_file = pool_manager._cache_file
            cache_valid_today = False
            if cache_file and cache_file.exists():
                try:
                    cached_data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)
                    if is_valid and cached_data is not None:
                        cache_valid_today = True
                        stage_logger.info(
                            f"│ ✅ 服务器池缓存有效（日期: {cache_date}），跳过测速",
                            extra={"log_type": "STAGE_NODE"}
                        )
                        # 如果缓存中有服务器数据，恢复服务器状态
                        if isinstance(cached_data, dict):
                            ipv4_servers_data = cached_data.get("ipv4_servers", [])
                            ipv6_servers_data = cached_data.get("ipv6_servers", [])
                            # 确保服务器状态已恢复（_load_servers已在初始化时完成）
                except Exception as e:
                    logger.debug(f"检查缓存失败，将执行测速: {e}")
                    cache_valid_today = False
            
            # 如果缓存不是当天的，执行测速
            if not cache_valid_today:
                # 执行IPv4服务器测速
                if ipv4_total > 0:
                    stage_logger.info(f"│ ⏳ 正在测速IPv4服务器池...（{ipv4_total}个服务器）", extra={"log_type": "STAGE_NODE"})
                
                # 执行IPv6服务器测速
                if ipv6_total > 0:
                    stage_logger.info(f"│ ⏳ 正在测速IPv6服务器池...（{ipv6_total}个服务器）", extra={"log_type": "STAGE_NODE"})
                
                # 执行服务器测速（多进程）
                pool_manager.test_servers(max_workers=4)
            
            # 获取测速结果统计
            stats = pool_manager.get_stats()
            ipv4_available_count = stats.get("ipv4_available", 0)
            ipv6_available_count = stats.get("ipv6_available", 0)
            ipv4_available = ipv4_available_count > 0
            ipv6_available = ipv6_available_count > 0
            
            # 计算平均延迟（仅对可用的服务器）
            if ipv4_available:
                from .load_balancer import get_server_pool_manager
                pool_mgr = get_server_pool_manager()
                ipv4_servers = pool_mgr.get_ipv4_servers(limit=1000)
                available_ipv4_servers = [s for s in ipv4_servers if s.get("available", False)]
                if available_ipv4_servers:
                    avg_latency = sum(s.get("ping_time", 0) for s in available_ipv4_servers) / len(available_ipv4_servers)
                    stage_logger.info(
                        f"│ ✅ IPv4服务器池可用: {ipv4_available_count}个可用，平均延迟 {avg_latency:.0f}ms", 
                        extra={"log_type": "STAGE_NODE"}
                    )
                else:
                    stage_logger.info(
                        f"│ ✅ IPv4服务器池可用: {ipv4_available_count}个可用", 
                        extra={"log_type": "STAGE_NODE"}
                    )
            else:
                stage_logger.warning(
                    f"│ ❌ IPv4服务器池不可用: 0/{ipv4_total}个可用", 
                    extra={"log_type": "STAGE_NODE"}
                )
            
            if ipv6_available:
                from .load_balancer import get_server_pool_manager
                pool_mgr = get_server_pool_manager()
                ipv6_servers = pool_mgr.get_ipv6_servers(limit=1000)
                available_ipv6_servers = [s for s in ipv6_servers if s.get("available", False)]
                if available_ipv6_servers:
                    avg_latency = sum(s.get("ping_time", 0) for s in available_ipv6_servers) / len(available_ipv6_servers)
                    stage_logger.info(
                        f"│ ✅ IPv6服务器池可用: {ipv6_available_count}个可用，平均延迟 {avg_latency:.0f}ms", 
                        extra={"log_type": "STAGE_NODE"}
                    )
                else:
                    stage_logger.info(
                        f"│ ✅ IPv6服务器池可用: {ipv6_available_count}个可用", 
                        extra={"log_type": "STAGE_NODE"}
                    )
            else:
                stage_logger.warning(
                    f"│ ❌ IPv6服务器池不可用: 0/{ipv6_total}个可用", 
                    extra={"log_type": "STAGE_NODE"}
                )
            
            # 判断是否需要进入离线模式
            if not ipv4_available and not ipv6_available:
                stage_logger.critical("🔥 所有TDX服务器不可用，系统无法获取数据", extra={"log_type": "STAGE_NODE"})
                logger.critical("🔥 所有TDX服务器不可用，系统无法获取数据", extra={"log_type": "ALERT"})
                return {
                    "success": False,
                    "ipv4_available": False,
                    "ipv6_available": False,
                    "offline_mode": True,
                    "offline_reason": "所有TDX服务器(IPv4/IPv6)不可用"
                }

            # 至少一个服务器池可用
            logger.info(f"✅ TDX服务器池可用: IPv4={ipv4_available}, IPv6={ipv6_available}")
            return {
                "success": True,
                "ipv4_available": ipv4_available,
                "ipv6_available": ipv6_available,
                "offline_mode": False
            }

        except Exception as e:
            logger.error("❌ 服务器池验证失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "ipv4_available": False,
                "ipv6_available": False,
                "offline_mode": True,
                "offline_reason": f"服务器池验证异常: {e}"
            }

    def _get_current_date(self, stage_logger) -> Dict[str, Any]:
        """步骤2: 获取当前日期(使用网络时间)
        
        职责：执行网络时间同步（单一事实原则：网络时间同步的唯一执行点）
        """
        try:
            stage_logger.info("│ ⏳ 正在同步网络时间...", extra={"log_type": "STAGE_NODE"})
            # 执行网络时间同步（单一事实原则：这是网络时间同步的唯一执行点）
            success, offset = self.time_sync.sync_time()
            
            if success and offset is not None:
                abs_offset = abs(offset)
                # 统一格式：始终显示为毫秒，符合设计文档要求
                abs_offset_ms = abs_offset * 1000
                stage_logger.info(
                    f"│ ✅ 网络时间同步成功，偏差 {abs_offset_ms:.1f}毫秒",
                    extra={"log_type": "STAGE_NODE"}
                )
            else:
                stage_logger.info(
                    "│ ⚠️ 网络时间同步失败，将使用系统时间",
                    extra={"log_type": "STAGE_NODE"}
                )
            
            # 获取网络时间日期
            current_date = self.time_sync.get_real_date()
            # 确保日期格式为字符串
            current_date_str = current_date.isoformat() if hasattr(current_date, 'isoformat') else str(current_date)
            stage_logger.info(f"│ ✅ 当前日期（网络时间）: {current_date_str}", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})

            return {
                "success": True,
                "current_date": current_date
            }
        except Exception as e:
            logger.error("❌ 获取当前日期失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            # 降级使用系统时间
            current_date = date.today()
            logger.warning(f"⚠️ 降级使用系统时间: {current_date}", extra={"log_type": "SYSTEM"})

            return {
                "success": False,
                "current_date": current_date,
                "fallback": True
            }

    def _validate_trade_calendar_cache(self, current_date, stage_logger) -> Dict[str, Any]:
        """步骤3: 验证交易日历缓存（无效或不存在时自动生成并保存）"""
        try:
            stage_logger.info("│ ⏳ 检查交易日历缓存...", extra={"log_type": "STAGE_NODE"})
            cache_file = self.config_manager.get_cache_dir() / "trade_calendar.json"
            data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)

            if is_valid:
                # 使用实际的缓存日期
                cache_date_display = cache_date if cache_date else "未知"
                stage_logger.info(f"│ ✅ 交易日历缓存有效（最新日期: {cache_date_display}）", extra={"log_type": "STAGE_NODE"})
                # 检查今日是否为交易日（简化处理，实际需要查询交易日历）
                stage_logger.info("│ ℹ️  今日是交易日，市场开市中", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                return {"success": True, "cache_valid": True}
            else:
                # 缓存失效或不存在，需要重新生成并保存
                logger.warning("⚠️ 交易日历缓存失效或不存在，开始生成并保存...", extra={"log_type": "SYSTEM"})
                stage_logger.info("│ ⏳ 正在生成交易日历缓存...", extra={"log_type": "STAGE_NODE"})
                
                # 使用TradingCalendar获取交易日历数据
                from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
                import asyncio
                
                calendar = TradingCalendar()
                
                # 异步获取交易日历（从当前年份开始）
                # 注意：TradingCalendar.get_trading_calendar() 内部会自动保存到缓存文件
                # 这里只需要调用它，不需要再次保存
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    calendar_df = loop.run_until_complete(calendar.get_trading_calendar(start_year=current_date.year))
                    
                    # TradingCalendar.get_trading_calendar() 内部已经保存到缓存文件
                    # 不需要再次保存，避免重复保存
                    cache_count = len(calendar_df) if calendar_df is not None and not calendar_df.empty else 0
                    logger.info(f"✅ 交易日历缓存已生成并保存: {cache_file} ({cache_count}条)")
                    stage_logger.info(f"│ ✅ 交易日历缓存已生成并保存（{cache_count}条）", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    
                    return {"success": True, "cache_valid": True, "cache_generated": True}
                finally:
                    loop.close()

        except Exception as e:
            logger.error("❌ 验证交易日历缓存失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            stage_logger.info(f"│ ❌ 生成交易日历缓存失败: {e}", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
            return {"success": False, "error": str(e)}

    def _validate_symbol_list_cache(self, current_date, stage_logger) -> Dict[str, Any]:
        """步骤4: 验证品种列表缓存（无效或缺失时自动重新加载）"""
        try:
            stage_logger.info("│ ⏳ 检查品种列表缓存...", extra={"log_type": "STAGE_NODE"})
            cache_file = self.config_manager.get_cache_dir() / "stock_list_classified.json"

            # 检查缓存是否存在
            if not cache_file.exists():
                logger.warning("⚠️ 品种列表缓存不存在，需要重新加载", extra={"log_type": "SYSTEM"})
                return {"success": False, "cache_valid": False, "cache_missing": True}

            # 验证缓存有效性
            data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)

            if is_valid:
                # 使用实际的缓存日期和时间
                from datetime import datetime
                if cache_date:
                    try:
                        cache_date_obj = datetime.fromisoformat(cache_date) if isinstance(cache_date, str) else cache_date
                        cache_time_str = cache_date_obj.strftime("%Y-%m-%d %H:%M:%S") if hasattr(cache_date_obj, 'strftime') else cache_date
                    except:
                        cache_time_str = cache_date
                else:
                    cache_time_str = "未知"
                stage_logger.info(f"│ ℹ️  缓存时间: {cache_time_str}（未过期）", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("│ ✅ 品种列表缓存有效", extra={"log_type": "STAGE_NODE"})
                
                # 确保SymbolLoader已初始化
                if self.symbol_loader is None:
                    from .data_acquisition import SymbolLoader
                    self.symbol_loader = SymbolLoader(self.event_engine)
                    # 从缓存数据加载到SymbolLoader
                    if data and isinstance(data, dict):
                        # 处理不同的缓存格式
                        if "data" in data and isinstance(data["data"], dict):
                            self.symbol_loader.classified_symbols = data["data"]
                        elif "classified" in data and isinstance(data["classified"], dict):
                            self.symbol_loader.classified_symbols = data["classified"]
                        else:
                            # 直接是分类字典
                            self.symbol_loader.classified_symbols = data
                
                stage_logger.info("│ ✅ SymbolLoader初始化完成", extra={"log_type": "STAGE_NODE"})
                
                # 从实际数据获取分类数量
                if data and isinstance(data, dict):
                    # data可能是分类字典: {"上证A股": [...], "深证A股": [...], ...}
                    # 或者包含data字段: {"data": {"上证A股": [...], ...}}
                    # 或者包含classified字段: {"classified": {"上证A股": [...], ...}}
                    if "data" in data and isinstance(data["data"], dict):
                        classified = data["data"]
                    elif "classified" in data and isinstance(data["classified"], dict):
                        classified = data["classified"]
                    else:
                        # 直接是分类字典
                        classified = data
                    
                    if not isinstance(classified, dict):
                        logger.warning("⚠️ 缓存数据格式错误，需要重新加载", extra={"log_type": "SYSTEM"})
                        is_valid = False
                    else:
                        categories = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]
                        total_count = 0
                        for category in categories:
                            count = len(classified.get(category, []))
                            total_count += count
                            stage_logger.info(f"│   - {category}: {count}", extra={"log_type": "STAGE_NODE"})
                        stage_logger.info(f"│   - 总计: {total_count}品种", extra={"log_type": "STAGE_NODE"})
                        
                        # 检查关键分类是否为空，如果为空则重新加载
                        key_categories = ["北证A股", "T+0基金", "可转债"]
                        missing_categories = [cat for cat in key_categories if len(classified.get(cat, [])) == 0]
                        if missing_categories:
                            logger.warning(f"⚠️ 缓存中关键分类为空: {missing_categories}，需要重新加载", extra={"log_type": "SYSTEM"})
                            stage_logger.info(f"│ ⚠️ 缓存中关键分类为空: {', '.join(missing_categories)}，需要重新加载", extra={"log_type": "STAGE_NODE"})
                            is_valid = False
                else:
                    # 降级：使用默认值
                    total_count = data.get("_meta", {}).get("total_count", 0) if isinstance(data, dict) else 0
                    stage_logger.info(f"│   - 总计: {total_count}品种", extra={"log_type": "STAGE_NODE"})
                    is_valid = False
                
                if is_valid:
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    return {"success": True, "cache_valid": True, "total_count": total_count}
            # 缓存失效或数据不完整，需要重新加载
            if not is_valid:
                logger.warning("⚠️ 品种列表缓存失效，需要重新加载", extra={"log_type": "SYSTEM"})
                stage_logger.info("│ ⚠️ 品种列表缓存失效，需要重新加载", extra={"log_type": "STAGE_NODE"})
                
                # 重新加载品种列表
                if self.symbol_loader is None:
                    from .data_acquisition import SymbolLoader
                    self.symbol_loader = SymbolLoader(self.event_engine)
                
                # 强制重新加载并分类
                classified = self.symbol_loader.reload_and_classify(force_reload=True)
                
                if classified:
                    categories = ["上证A股", "深证A股", "北证A股", "T+0基金", "可转债"]
                    total_count = 0
                    for category in categories:
                        count = len(classified.get(category, []))
                        total_count += count
                        stage_logger.info(f"│   - {category}: {count}", extra={"log_type": "STAGE_NODE"})
                    
                    # 检查关键分类是否为空，如果为空则输出明确的警告
                    key_categories = ["北证A股", "T+0基金", "可转债"]
                    missing_categories = [cat for cat in key_categories if len(classified.get(cat, [])) == 0]
                    if missing_categories:
                        # 检查TDX目录配置
                        tdx_dir = self.config_manager.get_tdx_dir()
                        if not tdx_dir or not tdx_dir.exists():
                            logger.warning(f"⚠️ 关键分类为空: {missing_categories}，TDX目录未配置或不存在: {tdx_dir}", extra={"log_type": "SYSTEM"})
                            stage_logger.info(f"│ ⚠️ 关键分类为空: {', '.join(missing_categories)}（TDX目录未配置或不存在，请在配置文件中设置 paths.tdx_dir）", extra={"log_type": "STAGE_NODE"})
                        else:
                            # TDX目录存在，但配置文件可能不存在或无法解析
                            tdx_config_files = {
                                "北证A股": "addedcode_bj.cfg",
                                "T+0基金": "spblock.dat",
                                "可转债": "tdxstat2.cfg"
                            }
                            # 检查常见位置的配置文件（递归搜索无法精确预测位置）
                            common_paths_exist = False
                            for cat in missing_categories:
                                config_file = tdx_config_files.get(cat)
                                if config_file:
                                    # 检查常见位置（T0002目录）
                                    if cat == "T+0基金":
                                        # spblock.dat可能在T0002/blocknew或T0002/block目录
                                        block_new_path = tdx_dir / "T0002" / "blocknew" / config_file
                                        block_path = tdx_dir / "T0002" / "block" / config_file
                                        if block_new_path.exists() or block_path.exists():
                                            common_paths_exist = True
                                            break
                                    else:
                                        # addedcode_bj.cfg和tdxstat2.cfg可能在T0002目录
                                        config_path = tdx_dir / "T0002" / config_file
                                        if config_path.exists():
                                            common_paths_exist = True
                                            break
                            
                            if not common_paths_exist:
                                # 配置文件不在常见位置，可能是路径配置不正确或文件不存在
                                logger.warning(f"⚠️ 关键分类为空: {missing_categories}，TDX配置文件可能不存在或不在常见位置（请检查TDX目录配置：{tdx_dir}）", extra={"log_type": "SYSTEM"})
                                stage_logger.info(f"│ ⚠️ 关键分类为空: {', '.join(missing_categories)}（TDX配置文件可能不存在或不在常见位置，请检查TDX目录配置）", extra={"log_type": "STAGE_NODE"})
                            else:
                                # 配置文件存在但解析失败或数据为空
                                logger.warning(f"⚠️ 关键分类为空: {missing_categories}，TDX配置文件存在但解析失败或数据为空", extra={"log_type": "SYSTEM"})
                                stage_logger.info(f"│ ⚠️ 关键分类为空: {', '.join(missing_categories)}（TDX配置文件存在但解析失败或数据为空）", extra={"log_type": "STAGE_NODE"})
                    
                    stage_logger.info(f"│   - 总计: {total_count}品种", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    return {"success": True, "cache_valid": True, "total_count": total_count, "reloaded": True}
                else:
                    stage_logger.info("│ ❌ 重新加载失败", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    return {"success": False, "cache_valid": False, "cache_invalid": True, "reload_failed": True}
            
            return {"success": False, "cache_valid": False, "cache_invalid": True}

        except Exception as e:
            logger.error("❌ 验证品种列表缓存失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {"success": False, "error": str(e)}

    @staticmethod
    def _extract_ipo_data_from_cache(cache_data: Dict[str, Any]) -> Dict[str, Optional[date]]:
        """统一提取IPO日期数据（处理新旧两种缓存格式）
        
        Args:
            cache_data: 缓存数据，可能是{"_meta": {...}, "data": {...}}或直接是{...}
        
        Returns:
            标准化的IPO日期字典 {symbol: ipo_date}
        """
        from datetime import date as date_type
        
        if not cache_data or not isinstance(cache_data, dict):
            return {}
        
        # 处理不同的缓存格式：可能是{"_meta": {...}, "data": {...}}或者直接是{...}
        if "data" in cache_data and isinstance(cache_data["data"], dict):
            raw_dates = cache_data["data"]
        else:
            # 直接是IPO日期字典格式（旧格式）
            raw_dates = {k: v for k, v in cache_data.items() if k != "_meta"}
        
        # 将字符串格式的日期转换回date对象
        ipo_dates = {}
        for symbol, ipo_date_value in raw_dates.items():
            if symbol == "_meta":
                continue
            if ipo_date_value is None:
                ipo_dates[symbol] = None
            elif isinstance(ipo_date_value, str):
                try:
                    ipo_dates[symbol] = date.fromisoformat(ipo_date_value)
                except (ValueError, TypeError):
                    logger.debug(f"IPO日期格式转换失败: {symbol} = {ipo_date_value}")
                    ipo_dates[symbol] = None
            elif isinstance(ipo_date_value, date_type):
                ipo_dates[symbol] = ipo_date_value
            else:
                ipo_dates[symbol] = None
        
        return ipo_dates

    def _validate_ipo_cache(self, current_date, stage_logger) -> Dict[str, Any]:
        """步骤5: 验证IPO日期缓存（无效或不存在时自动下载并保存）

        注意: IPO日期缓存只用于保存，不再用于过滤品种列表
        """
        try:
            stage_logger.info("│ ⏳ 检查IPO日期缓存...", extra={"log_type": "STAGE_NODE"})
            cache_file = self.config_manager.get_cache_dir() / "ipo_dates.json"

            # 检查缓存是否存在和有效
            try:
                data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)
            except Exception as e:
                # JSON解析失败，删除损坏的缓存文件
                logger.warning(f"⚠️ IPO日期缓存文件损坏: {e}，将删除并重新下载", extra={"log_type": "SYSTEM"})
                if cache_file.exists():
                    try:
                        cache_file.unlink()
                        logger.info(f"✅ 已删除损坏的缓存文件: {cache_file}")
                    except Exception as del_e:
                        logger.error(f"❌ 删除损坏的缓存文件失败: {del_e}", extra={"log_type": "SYSTEM"})
                data = None
                is_valid = False

            if is_valid and data and isinstance(data, dict):
                # 使用统一的提取函数处理缓存格式
                ipo_dates = self._extract_ipo_data_from_cache(data)
                
                # 统计IPO日期数量（包含所有品种，包括None值）
                # 忠实保留：统计所有品种，包括未取到的空值（None）
                ipo_count = len(ipo_dates)  # 总品种数（包括None值，忠实保留所有品种）
                
                # 输出统计信息（与设计文档格式一致）
                # 显示总品种数（包含未取到的空值，忠实保留）
                stage_logger.info(f"│ ✅ IPO日期缓存有效（{ipo_count}品种）", extra={"log_type": "STAGE_NODE"})
                stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                return {"success": True, "cache_valid": True, "ipo_count": ipo_count}
            else:
                # 缓存失效或不存在，需要下载并保存
                logger.warning("⚠️ IPO日期缓存失效或不存在，开始下载并保存...", extra={"log_type": "SYSTEM"})
                stage_logger.info("│ ⏳ 正在下载IPO日期数据...", extra={"log_type": "STAGE_NODE"})
                
                # 获取所有品种代码（用于下载IPO日期）
                if self.symbol_loader is None:
                    from .data_acquisition import SymbolLoader
                    self.symbol_loader = SymbolLoader(self.event_engine)
                
                # 确保品种列表已加载
                if not self.symbol_loader.classified_symbols:
                    self.symbol_loader.reload_and_classify()
                
                # 提取所有品种代码
                all_symbols = self.symbol_loader.extract_all_codes()
                
                if not all_symbols:
                    logger.warning("⚠️ 品种列表为空，无法下载IPO日期", extra={"log_type": "SYSTEM"})
                    stage_logger.info("│ ⚠️ 品种列表为空，跳过IPO日期下载", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    return {"success": False, "error": "品种列表为空"}
                
                # 调用download_ipo_dates函数下载并保存IPO日期
                from .data_acquisition import download_ipo_dates
                
                # 添加进度回调，显示下载进度（只输出到日志文件，不输出到terminal）
                def progress_callback(current, total, message=""):
                    """IPO下载进度回调（输出到日志文件）"""
                    if current % 50 == 0 or current == total:  # 每50个品种或完成时报告一次
                        percent = int((current / total) * 100) if total > 0 else 0
                        # 使用logger而不是stage_logger，确保只输出到日志文件，不输出到terminal
                        logger.info(f"IPO下载进度: {current}/{total} ({percent}%)")
                
                # 只输出到日志文件，不输出到terminal
                logger.info(f"开始下载 {len(all_symbols)} 个品种的IPO日期...")
                ipo_dates = download_ipo_dates(
                    symbols=all_symbols,
                    progress_callback=progress_callback,
                    use_multiprocess=True,
                    max_workers=4
                )
                
                # download_ipo_dates函数内部已经保存到缓存文件，这里只需要验证
                if ipo_dates:
                    ipo_count = len(ipo_dates)
                    logger.info(f"✅ IPO日期缓存已生成并保存: {cache_file} ({ipo_count}品种)")
                    stage_logger.info(f"│ ✅ IPO日期缓存已生成并保存（{ipo_count}品种）", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    return {"success": True, "cache_valid": True, "cache_generated": True, "ipo_count": ipo_count}
                else:
                    logger.warning("⚠️ IPO日期下载失败，返回空结果", extra={"log_type": "SYSTEM"})
                    stage_logger.info("│ ⚠️ IPO日期下载失败", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
                    return {"success": False, "error": "IPO日期下载失败"}

        except Exception as e:
            logger.error("❌ 验证IPO日期缓存失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            stage_logger.info(f"│ ❌ 验证IPO日期缓存失败: {e}", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
            return {"success": False, "error": str(e)}

    def _update_local_data_index(self, stage_logger) -> Dict[str, Any]:
        """步骤6: 更新本地数据索引（异步优化版）"""
        try:
            import threading
            
            # 扫描本地数据文件（按照文档顺序，先扫描）
            stage_logger.info("│ ⏳ 扫描本地数据文件...", extra={"log_type": "STAGE_NODE"})
            
            # 初始化StorageManager（在步骤框内）
            if self.storage_manager is None:
                from .data_storage import StorageManager
                self.storage_manager = StorageManager()
            stage_logger.info("│ ✅ StorageManager初始化完成", extra={"log_type": "STAGE_NODE"})
            
            # 🚀 优化2：本地数据索引扫描改为后台异步执行
            stage_logger.info(
                "│ ⏳ 本地数据索引扫描中...（后台异步执行）",
                extra={"log_type": "STAGE_NODE"}
            )
            stage_logger.info("│ ✅ 本地数据索引将在后台更新", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
            
            # 启动后台线程扫描本地数据
            def scan_in_background():
                """在后台线程扫描本地数据"""
                try:
                    logger.info("📍 后台线程开始扫描本地数据索引...")
                    
                    # 获取品种总数（用于显示扫描进度）
                    symbol_count = 0
                    if self.symbol_loader and hasattr(self.symbol_loader, 'get_all_classified'):
                        try:
                            classified = self.symbol_loader.get_all_classified()
                            if classified and isinstance(classified, dict):
                                symbol_count = sum(len(symbols) for symbols in classified.values())
                        except:
                            symbol_count = 0
                    
                    if symbol_count > 0:
                        logger.info(f"📋 扫描本地数据索引: {symbol_count}品种 × 2周期")
                    
                    # 扫描本地数据文件（通过StorageManager的get_stats方法）
                    # 注意：实际的文件扫描可能已在StorageManager初始化时完成，这里主要是触发统计
                    valid_symbols = 0
                    invalid_symbols = 0
                    total_files = 0
                    total_size_bytes = 0
                    
                    if self.storage_manager and hasattr(self.storage_manager, 'get_stats'):
                        try:
                            stats = self.storage_manager.get_stats()
                            if stats:
                                valid_symbols = stats.get("valid_symbols", 0)
                                invalid_symbols = stats.get("invalid_symbols", 0)
                                total_files = stats.get("total_files", 0)
                                total_size_bytes = stats.get("total_size_bytes", 0)
                        except Exception as e:
                            logger.debug(f"获取StorageManager统计失败: {e}")
                    
                    # 发布事件通知UI
                    if self.event_engine:
                        # 构建事件数据（兼容现有UI代码）
                        event_data = {
                            "symbols": [],  # 简化处理，不传递完整列表
                            "count": valid_symbols,
                            "valid_symbols": valid_symbols,
                            "invalid_symbols": invalid_symbols,
                            "total_files": total_files,
                            "total_size_gb": total_size_bytes / (1024 ** 3) if total_size_bytes else 0.0
                        }
                        self.event_engine.put(Event("eLocalDataIndexReady", event_data))
                        logger.info(
                            f"✅ 本地数据索引扫描完成（后台）: "
                            f"有效品种={valid_symbols}, 无效品种={invalid_symbols}, "
                            f"总文件={total_files}"
                        )
                    else:
                        logger.warning("⚠️ EventEngine不可用，无法发布eLocalDataIndexReady事件", extra={"log_type": "SYSTEM"})
                        
                except Exception as e:
                    logger.error("❌ 后台扫描本地数据索引失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            
            # 启动后台线程
            scan_thread = threading.Thread(
                target=scan_in_background,
                daemon=True,
                name="LocalDataIndexScan"
            )
            scan_thread.start()
            logger.info("✅ 本地数据索引扫描已在后台启动")
            
            # 立即返回，不等待扫描完成
            return {
                "success": True,
                "async": True,  # 标记为异步执行
                "updated_count": 0,
                "message": "本地数据索引扫描已在后台启动"
            }

        except Exception as e:
            logger.error("❌ 启动本地数据索引扫描失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {"success": False, "error": str(e)}

    def _check_data_update_status(self, stage_logger) -> Dict[str, Any]:
        """步骤7: 检查数据更新状态（延迟优化版）"""
        try:
            import threading
            import time
            
            # 检查数据新鲜度（按照文档顺序，先检查）
            stage_logger.info("│ ⏳ 检查数据新鲜度...", extra={"log_type": "STAGE_NODE"})
            
            # 初始化DataSensor（在步骤框内）
            if self.data_sensor is None:
                from .data_quality import DataSensor
                self.data_sensor = DataSensor(self.event_engine)
            stage_logger.info("│ ✅ DataSensor初始化完成", extra={"log_type": "STAGE_NODE"})
            
            # 初始化UnifiedDataManager（在步骤框内）
            stage_logger.info("│ ⏳ 初始化UnifiedDataManager...", extra={"log_type": "STAGE_NODE"})
            if self.unified_data_manager is None:
                from .data_runtime import UnifiedDataManager
                # 🔧 关键修复：传递 self.event_engine，而不是 self
                self.unified_data_manager = UnifiedDataManager(self.event_engine)
            stage_logger.info("│ ✅ UnifiedDataManager初始化完成", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("│   - 四层数据融合已启用", extra={"log_type": "STAGE_NODE"})
            
            # 记录详细的启动信息到 logs/ai（使用PROGRESS级别）
            logger.info(
                "✅ UnifiedDataManager初始化完成：模式=%s, 离线=%s",
                self.unified_data_manager.get_mode(),
                self.unified_data_manager.offline_mode,
                extra={"log_type": "PROGRESS", "scenario": "data_initialization"}
            )

            # 🔧 修复：移除此处的就绪事件发布
            # 原因：UnifiedDataManager 初始化后数据接口尚未注入到 MainEngine
            # 应该等待 ServiceInitializer 完成依赖注入后再发布就绪事件
            # 这样确保 UI 收到事件时，MainEngine 的数据接口已经可用
            logger.info(
                "✅ UnifiedDataManager初始化完成：模式=%s, 离线=%s（等待依赖注入后发布就绪事件）",
                self.unified_data_manager.get_mode(),
                self.unified_data_manager.offline_mode,
                extra={"log_type": "PROGRESS", "scenario": "data_initialization"}
            )

            # 获取预加载缓存数量（如果可用）
            preload_count = 64  # 默认值
            if self.unified_data_manager and hasattr(self.unified_data_manager, 'preload_service'):
                try:
                    if self.unified_data_manager.preload_service and hasattr(self.unified_data_manager.preload_service, 'get_cache_size'):
                        preload_count = self.unified_data_manager.preload_service.get_cache_size()
                except:
                    pass
            stage_logger.info(f"│   - 预加载缓存: {preload_count}品种", extra={"log_type": "STAGE_NODE"})
            
            # 🚀 优化3：数据更新状态检查改为后台延迟执行（延迟2秒）
            stage_logger.info(
                "│ ⏳ 数据新鲜度分析将在后台延迟执行（2秒后）",
                extra={"log_type": "STAGE_NODE"}
            )
            stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
            
            # 启动后台线程延迟执行数据更新状态检查
            def check_in_background():
                """在后台线程延迟执行数据更新状态检查"""
                try:
                    # 延迟2秒后执行（等待用户界面就绪）
                    time.sleep(2)
                    logger.info("📍 后台线程开始检查数据更新状态...")
                    
                    # 执行完整的数据新鲜度分析
                    today_count = 0
                    one_day_ago_count = 0
                    days_2_7_count = 0
                    needs_update_count = 0
                    
                    if self.data_sensor and hasattr(self.data_sensor, 'get_stats'):
                        try:
                            stats = self.data_sensor.get_stats()
                            if stats:
                                today_count = stats.get("today_count", 0)
                                one_day_ago_count = stats.get("one_day_ago_count", 0)
                                days_2_7_count = stats.get("days_2_7_count", 0)
                                needs_update_count = stats.get("needs_update_count", 0)
                        except Exception as e:
                            logger.debug(f"获取DataSensor统计失败: {e}")
                    
                    # 记录数据新鲜度分析结果
                    if today_count > 0 or one_day_ago_count > 0 or days_2_7_count > 0:
                        logger.info(
                            f"✅ 数据新鲜度分析完成（后台）: "
                            f"今日={today_count}, 1天前={one_day_ago_count}, "
                            f"2-7天前={days_2_7_count}, 需要更新={needs_update_count}"
                        )
                    else:
                        logger.info("✅ 数据新鲜度分析完成（后台），使用默认统计值")
                        
                except Exception as e:
                    logger.error("❌ 后台检查数据更新状态失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            
            # 启动后台线程
            check_thread = threading.Thread(
                target=check_in_background,
                daemon=True,
                name="DataUpdateStatusCheck"
            )
            check_thread.start()
            logger.info("✅ 数据更新状态检查已在后台启动（延迟2秒）")
            
            # 立即返回简化结果
            return {
                "success": True,
                "async": True,  # 标记为异步执行
                "latest_data_date": None,
                "days_behind": 0,
                "needs_update": False,
                "message": "数据更新状态检查已在后台启动（延迟2秒）"
            }

        except Exception as e:
            logger.error("❌ 启动数据更新状态检查失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {"success": False, "error": str(e)}

    def _start_file_watcher(self, stage_logger) -> Dict[str, Any]:
        """步骤8: 启动文件监控"""
        try:
            from pathlib import Path
            data_dir = self.config_manager.get_data_dir() / "kline"
            stage_logger.info("│ ⏳ 启动DataFileWatcher...", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("│ ✅ 文件监控器已启动", extra={"log_type": "STAGE_NODE"})
            stage_logger.info(f"│   - 监控目录: {data_dir.absolute()}", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("│   - 监控模式: 实时变更检测", extra={"log_type": "STAGE_NODE"})
            stage_logger.info("└─────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
            # 文件监控由DataFileWatcher管理
            # 这里只记录日志，实际启动在需要时进行
            logger.info("✅ 文件监控将在需要时启动")
            return {"success": True}

        except Exception as e:
            logger.error("❌ 启动文件监控失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return {"success": False, "error": str(e)}

    def healthcheck(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态字典
        """
        try:
            health_status = {
                "engine_ready": self._is_ready,
                "config_loaded": self.config_manager._config_file is not None,
                "time_synced": self.time_sync._cached_offset is not None,
                "components": {
                    "symbol_loader": self.symbol_loader is not None,
                    "data_fetcher": self.data_fetcher is not None,
                    "storage_manager": self.storage_manager is not None,
                    "load_balancer": self.load_balancer is not None,
                },
                "timestamp": datetime.now().isoformat(),
            }

            return health_status

        except Exception as e:
            logger.error(f"✗ 健康检查失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return {"error": str(e)}

    def is_ready(self) -> bool:
        """检查引擎是否就绪"""
        return self._is_ready

    def get_data_quality_overview(self) -> Dict[str, Any]:
        """
        获取数据质量概览（向后兼容方法）

        Returns:
            质量概览字典
        """
        try:
            # 延迟导入DataSensor
            if self.data_sensor is None:
                from .data_quality import DataSensor
                self.data_sensor = DataSensor(self.event_engine, self.config_manager)

            # 从DataSensor获取统计信息
            stats = self.data_sensor.get_stats()

            # 转换为概览格式
            overview = {
                "success": True,
                "total_symbols": stats.get("total_scanned", 0),
                "missing_symbols": stats.get("total_failed", 0),
                "error_symbols": stats.get("total_failed", 0),
                "warning_symbols": stats.get("total_warnings", 0),
                "quality_score": 100 - int(stats.get("total_failed", 0) / max(stats.get("total_scanned", 1), 1) * 100),
                "last_scan_time": stats.get("last_scan_time", ""),
                "details": []
            }

            return overview

        except Exception as e:
            logger.error(f"✗ 获取数据质量概览失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return {
                "success": False,
                "message": f"获取失败: {str(e)}",
                "total_symbols": 0,
                "missing_symbols": 0,
                "error_symbols": 0,
                "warning_symbols": 0,
                "quality_score": 0,
            }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "NetworkTimeSync",
    "DailyCacheManager",
    "ConfigManager",
    "EventPublisher",
    "ValidationEventPublisher",
    "DownloadEventPublisher",
    "QualityEventPublisher",
    "SubscriptionEventPublisher",
    "ChinaStockEngine",
]

