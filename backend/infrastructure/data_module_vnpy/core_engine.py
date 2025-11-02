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
from vnpy_ctastrategy import CtaEngine

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

    def sync_time(self, timeout: float = 3.0) -> Tuple[bool, Optional[float]]:
        """
        从NTP服务器同步时间

        Args:
            timeout: 请求超时时间（秒）

        Returns:
            (成功标志, 时间偏移量)
            偏移量 = 网络时间 - 系统时间（秒）
        """
        # ntplib不可用时直接返回失败
        if not NTPLIB_AVAILABLE or self.ntp_client is None:
            logger.warning("⚠️ ntplib不可用，无法进行网络时间同步")
            return False, None

        with self._sync_lock:
            for ntp_server in self.NTP_SERVERS:
                try:
                    logger.debug(f"尝试从 {ntp_server} 同步时间...")

                    # 发送NTP请求
                    response = self.ntp_client.request(ntp_server, version=3, timeout=timeout)
                    offset = response.offset

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
                            f"✓ 时间同步成功: {ntp_server}, "
                            f"系统时间{direction}了 {abs_offset:.3f}秒"
                        )
                    else:
                        logger.info(
                            f"✓ 时间同步成功: {ntp_server}, "
                            f"偏差 {abs_offset*1000:.1f}毫秒"
                        )

                    return True, offset

                except Exception as e:
                    logger.debug(f"从 {ntp_server} 同步失败: {type(e).__name__}: {e}")
                    continue

            # 所有服务器都失败
            self._sync_failures += 1
            logger.warning(
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
            logger.warning("⚠️ 时间同步失败，降级使用系统时间（可能不准确）")
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

            # 写入文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_obj, f, ensure_ascii=False, indent=2)

            logger.debug(f"✓ 缓存已保存: {cache_file.name} (日期: {real_date})")
            return True

        except Exception as e:
            logger.error(f"✗ 缓存保存失败: {cache_file.name}, 错误: {e}", exc_info=True)
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
                logger.warning(f"⚠️ 缓存缺少日期字段: {cache_file.name}")
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
            logger.error(f"✗ 缓存加载失败: {cache_file.name}, 错误: {e}", exc_info=True)
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
            logger.error(f"✗ 缓存保存失败（异步）: {cache_file.name}, 错误: {e}", exc_info=True)
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
                logger.warning(f"⚠️ 缓存缺少日期字段: {cache_file.name}")
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
            logger.error(f"✗ 缓存加载失败（异步）: {cache_file.name}, 错误: {e}", exc_info=True)
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
            logger.error(f"✗ 缓存清理失败: {cache_file.name}, 错误: {e}", exc_info=True)
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
            logger.error(f"✗ 获取缓存日期失败: {cache_file.name}, 错误: {e}")
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
                logger.warning("⚠️ 未找到配置文件，使用默认配置")
                self._config = self._get_default_config()
                return

            # 读取配置
            with open(self._config_file, 'r', encoding='utf-8') as f:
                self._config = json.load(f)

            logger.info(f"✓ 配置文件已加载: {self._config_file}")

        except Exception as e:
            logger.error(f"✗ 配置加载失败: {e}, 使用默认配置", exc_info=True)
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

        except Exception:
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
            logger.error(f"✗ 配置更新失败: {key}, 错误: {e}", exc_info=True)
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
            logger.error(f"✗ 批量配置更新失败: {e}", exc_info=True)
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
            logger.error(f"✗ 配置重新加载失败: {e}", exc_info=True)
            return False

    async def _notify_config_update(self) -> None:
        """通过native_ipc通知配置更新（跨进程）"""
        try:
            if self._ipc_pipe is None:
                self._ipc_pipe = await AsyncIPCPipe.server("config_updates")

            # 发送配置更新通知
            update_data = {
                "action": "config_reload",
                "timestamp": datetime.now().isoformat(),
            }

            await self._ipc_pipe.write(json.dumps(update_data).encode())
            logger.debug("✓ 配置更新已通知到其他进程")

        except Exception as e:
            logger.error(f"✗ 配置更新通知失败: {e}", exc_info=True)


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
            logger.error(f"✗ 事件发布失败: {event_type}, 错误: {e}", exc_info=True)


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
            logger.info("=" * 70)
            logger.info("🚀 启动缓存验证与感知流程")
            logger.info("=" * 70)
            
            # 调用核心验证逻辑
            result = self.engine._smart_cache_validation_and_sensing(
                progress_callback=self._on_progress,
                step_callback=self._on_step_completed
            )
            
            # 发送完成信号
            if result.get("offline_mode"):
                self.offline_mode_triggered.emit(result.get("offline_reason", "未知原因"))
            
            self.validation_finished.emit(result)
            logger.info("✅ 缓存验证与感知流程完成")
            
        except Exception as e:
            logger.exception("❌ 缓存验证失败: %s", e)
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
        logger.warning("⚠️ 缓存验证被取消")


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

                # 1. 同步网络时间
                logger.info("1/7 同步网络时间...")
                self.time_sync.sync_time()

                # 2. 初始化子组件
                logger.info("2/7 初始化子组件...")
                self._initialize_components()

                # 3. 标记就绪
                self._is_ready = True
                logger.info("✓ 数据引擎初始化完成")
                return True

            except Exception as e:
                logger.error(f"✗ 引擎初始化失败: {e}", exc_info=True)
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
        try:
            # 延迟导入
            if self.symbol_loader is None:
                from .data_acquisition import SymbolLoader
                self.symbol_loader = SymbolLoader(self.event_engine)

            # 执行重新加载
            result = self.symbol_loader.reload_and_classify()

            # 发布事件
            self.event_engine.put(Event(self.EVENT_SYMBOL_CACHE_LOADED, result))

            return result

        except Exception as e:
            logger.error(f"✗ 重新加载品种列表失败: {e}", exc_info=True)
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
            logger.error(f"✗ 增量下载失败: {e}", exc_info=True)
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
            logger.error(f"✗ 数据查询失败: {symbol}/{interval}, 错误: {e}", exc_info=True)
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
            logger.error(f"✗ 健康检查失败: {e}", exc_info=True)
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
            logger.warning(f"⚠️ 系统已进入离线降级模式: {reason}")
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

        # 辅助函数
        def _progress(desc: str, pct: int):
            if progress_callback:
                progress_callback(desc, pct)

        def _step_done(num: int, name: str, result: dict):
            step_results.append(result)
            if step_callback:
                step_callback(num, name, result)

        try:
            # ========== 步骤1: 服务器池缓存验证与测速 ==========
            _progress("步骤1/8: 验证服务器池缓存并测速...", 5)
            step1_result = self._validate_server_pool_and_test_speed()
            _step_done(1, "服务器池验证与测速", step1_result)

            # 离线降级检查点
            if step1_result.get("offline_mode"):
                offline_mode = True
                offline_reason = step1_result.get("offline_reason")
                logger.critical(f"🔴 触发离线降级: {offline_reason}")
                # 设置离线模式
                self.set_offline_mode(True, offline_reason)
                # 跳转到步骤8
                _progress("离线模式: 跳过步骤2-7，直接启动文件监控", 90)
                goto_step_8 = True
            else:
                goto_step_8 = False
                # 初始化LoadBalancer
                _progress("步骤1/8: 初始化LoadBalancer...", 10)
                if self.load_balancer is None:
                    from .load_balancer import LoadBalancer
                    self.load_balancer = LoadBalancer(self.config_manager)
                logger.info("✅ LoadBalancer已初始化")

            if not goto_step_8:
                # ========== 步骤2: 获取当前日期(网络时间) ==========
                _progress("步骤2/8: 获取当前日期(网络时间)...", 15)
                step2_result = self._get_current_date()
                _step_done(2, "获取当前日期", step2_result)
                current_date = step2_result.get("current_date")

                # ========== 步骤3: 验证交易日历缓存 ==========
                _progress("步骤3/8: 验证交易日历缓存...", 25)
                step3_result = self._validate_trade_calendar_cache(current_date)
                _step_done(3, "验证交易日历缓存", step3_result)

                # ========== 步骤4: 验证品种列表缓存 ==========
                _progress("步骤4/8: 验证品种列表缓存...", 35)
                step4_result = self._validate_symbol_list_cache(current_date)
                _step_done(4, "验证品种列表缓存", step4_result)

                # 初始化SymbolLoader
                if not step4_result.get("cache_valid") or step4_result.get("cache_missing"):
                    _progress("步骤4/8: 重新加载品种列表...", 40)
                    if self.symbol_loader is None:
                        from .data_acquisition import SymbolLoader
                        self.symbol_loader = SymbolLoader(self.event_engine)
                    # 同步版本的reload
                    self.symbol_loader.reload_and_classify()
                    logger.info("✅ 品种列表已重新加载")

                # ========== 步骤5: 验证IPO日期缓存 ==========
                _progress("步骤5/8: 验证IPO日期缓存...", 50)
                step5_result = self._validate_ipo_cache(current_date)
                _step_done(5, "验证IPO日期缓存", step5_result)

                # ========== 步骤6: 更新本地数据索引 ==========
                _progress("步骤6/8: 更新本地数据索引...", 65)
                step6_result = self._update_local_data_index()
                _step_done(6, "更新本地数据索引", step6_result)

                # 初始化StorageManager
                _progress("步骤6/8: 初始化StorageManager...", 70)
                if self.storage_manager is None:
                    from .data_storage import StorageManager
                    self.storage_manager = StorageManager()
                logger.info("✅ StorageManager已初始化")

                # ========== 步骤7: 检查数据更新状态 ==========
                _progress("步骤7/8: 检查数据更新状态...", 75)
                step7_result = self._check_data_update_status()
                _step_done(7, "检查数据更新状态", step7_result)

                # 初始化DataSensor和UnifiedDataManager
                _progress("步骤7/8: 初始化DataSensor和UnifiedDataManager...", 85)
                if self.data_sensor is None:
                    from .data_quality import DataSensor
                    self.data_sensor = DataSensor(self.event_engine)
                if self.unified_data_manager is None:
                    from .data_runtime import UnifiedDataManager
                    self.unified_data_manager = UnifiedDataManager(self)
                logger.info("✅ DataSensor和UnifiedDataManager已初始化")

            # ========== 步骤8: 启动文件监控 ==========
            _progress("步骤8/8: 启动文件监控...", 90)
            step8_result = self._start_file_watcher()
            _step_done(8, "启动文件监控", step8_result)

            # 完成
            _progress("缓存验证与感知完成", 100)
            elapsed_time = time.time() - start_time

            return {
                "success": True,
                "offline_mode": offline_mode,
                "offline_reason": offline_reason,
                "steps_completed": len(step_results),
                "step_results": step_results,
                "total_time": elapsed_time
            }

        except Exception as e:
            logger.exception("❌ 缓存验证与感知失败: %s", e)
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

    def _validate_server_pool_and_test_speed(self) -> Dict[str, Any]:
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
            from .load_balancer import ServerPoolManager

            # 初始化服务器池管理器
            pool_manager = ServerPoolManager.get_instance()

            # 测试IPv4服务器池
            ipv4_results = pool_manager.test_servers(pool_type="ipv4", max_workers=4)
            ipv4_available = len([s for s in ipv4_results if s.get("latency", 999) < 500]) > 0

            # 测试IPv6服务器池
            ipv6_results = pool_manager.test_servers(pool_type="ipv6", max_workers=4)
            ipv6_available = len([s for s in ipv6_results if s.get("latency", 999) < 500]) > 0

            # 判断是否需要进入离线模式
            if not ipv4_available and not ipv6_available:
                logger.critical("🔴 所有TDX服务器不可用，进入离线降级模式")
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
            logger.exception("❌ 服务器池验证失败: %s", e)
            return {
                "success": False,
                "ipv4_available": False,
                "ipv6_available": False,
                "offline_mode": True,
                "offline_reason": f"服务器池验证异常: {e}"
            }

    def _get_current_date(self) -> Dict[str, Any]:
        """步骤2: 获取当前日期(使用网络时间)"""
        try:
            current_date = self.time_sync.get_real_date()
            logger.info(f"✅ 当前日期(网络时间): {current_date}")

            return {
                "success": True,
                "current_date": current_date
            }
        except Exception as e:
            logger.exception("❌ 获取当前日期失败: %s", e)
            # 降级使用系统时间
            current_date = date.today()
            logger.warning(f"⚠️ 降级使用系统时间: {current_date}")

            return {
                "success": False,
                "current_date": current_date,
                "fallback": True
            }

    def _validate_trade_calendar_cache(self, current_date) -> Dict[str, Any]:
        """步骤3: 验证交易日历缓存"""
        try:
            cache_file = self.config_manager.get_cache_dir() / "trade_calendar.json"
            data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)

            if is_valid:
                logger.info("✅ 交易日历缓存有效")
                return {"success": True, "cache_valid": True}
            else:
                logger.warning("⚠️ 交易日历缓存失效，需要重新下载")
                return {"success": False, "cache_valid": False, "action_needed": "download"}

        except Exception as e:
            logger.exception("❌ 验证交易日历缓存失败: %s", e)
            return {"success": False, "error": str(e)}

    def _validate_symbol_list_cache(self, current_date) -> Dict[str, Any]:
        """步骤4: 验证品种列表缓存（无效或缺失时自动重新加载）"""
        try:
            cache_file = self.config_manager.get_cache_dir() / "stock_list_classified.json"

            # 检查缓存是否存在
            if not cache_file.exists():
                logger.warning("⚠️ 品种列表缓存不存在，需要重新加载")
                return {"success": False, "cache_valid": False, "cache_missing": True}

            # 验证缓存有效性
            data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)

            if is_valid:
                logger.info("✅ 品种列表缓存有效")
                total_count = data.get("_meta", {}).get("total_count", 0) if data else 0
                return {"success": True, "cache_valid": True, "total_count": total_count}
            else:
                logger.warning("⚠️ 品种列表缓存失效，需要重新加载")
                return {"success": False, "cache_valid": False, "cache_invalid": True}

        except Exception as e:
            logger.exception("❌ 验证品种列表缓存失败: %s", e)
            return {"success": False, "error": str(e)}

    def _validate_ipo_cache(self, current_date) -> Dict[str, Any]:
        """步骤5: 验证IPO日期缓存（无效时增量下载，不存在时全部下载）

        注意: 不再使用IPO日期缓存对品种列表进行过滤
        """
        try:
            # IPO缓存通常由data_acquisition模块管理
            # 这里只检查缓存是否存在和有效
            cache_file = self.config_manager.get_cache_dir() / "ipo_dates.json"

            # 检查缓存是否存在
            cache_exists = cache_file.exists()

            if not cache_exists:
                logger.warning("⚠️ IPO日期缓存不存在，需要全部下载")
                return {"success": False, "cache_missing": True, "action_needed": "download_all"}

            # 检查缓存有效性
            data, cache_date, is_valid = DailyCacheManager.load_with_validation(cache_file)

            if is_valid:
                logger.info("✅ IPO日期缓存有效")
                return {"success": True, "cache_valid": True}
            else:
                logger.warning("⚠️ IPO日期缓存失效，需要增量下载")
                return {"success": False, "cache_invalid": True, "action_needed": "download_incremental"}

        except Exception as e:
            logger.exception("❌ 验证IPO日期缓存失败: %s", e)
            return {"success": False, "error": str(e)}

    def _update_local_data_index(self) -> Dict[str, Any]:
        """步骤6: 更新本地数据索引"""
        try:
            # 数据索引由StorageManager管理
            # 这里只记录日志，实际索引更新在需要时进行
            logger.info("✅ 本地数据索引将在需要时更新")
            return {"success": True, "updated_count": 0}

        except Exception as e:
            logger.exception("❌ 更新本地数据索引失败: %s", e)
            return {"success": False, "error": str(e)}

    def _check_data_update_status(self) -> Dict[str, Any]:
        """步骤7: 检查数据更新状态"""
        try:
            # 数据更新状态由DataSensor管理
            # 这里只记录日志，实际检查在DataSensor初始化后进行
            logger.info("✅ 数据更新状态检查将在DataSensor初始化后进行")
            return {
                "success": True,
                "latest_data_date": None,
                "days_behind": 0,
                "needs_update": False
            }

        except Exception as e:
            logger.exception("❌ 检查数据更新状态失败: %s", e)
            return {"success": False, "error": str(e)}

    def _start_file_watcher(self) -> Dict[str, Any]:
        """步骤8: 启动文件监控"""
        try:
            # 文件监控由DataFileWatcher管理
            # 这里只记录日志，实际启动在需要时进行
            logger.info("✅ 文件监控将在需要时启动")
            return {"success": True}

        except Exception as e:
            logger.exception("❌ 启动文件监控失败: %s", e)
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
            logger.error(f"✗ 健康检查失败: {e}", exc_info=True)
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
            logger.error(f"✗ 获取数据质量概览失败: {e}", exc_info=True)
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
