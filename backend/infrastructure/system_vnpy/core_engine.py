# -*- coding: utf-8 -*-
"""
System Manager Core Engine - 系统管理核心引擎

核心职责：
- 整个监控模块的中枢，提供统一入口和基础设施服务
- 配置管理、缓存管理、事件系统、引擎注册表
- native_iocp深度集成（配置文件异步读写）
- native_ipc深度集成（与监控进程的所有通信）

文件组织（AI Debug友好）：
- Part 1: 配置管理（ConfigManager）
- Part 2: 缓存管理（CacheManager）
- Part 3: 事件系统（EventPublisher系列）
- Part 4: 引擎注册表（EngineRegistry）
- Part 5: 核心引擎（SystemManagerEngine）

Author: System Refactoring Team
Date: 2025-01-09
Version: v1.0 (Complete Refactor)
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

# VnPy导入
try:
    from vnpy.event import Event, EventEngine
except ImportError:
    EventEngine = None
    Event = None

# 日志配置
logger = logging.getLogger("core_engine")

# ==============================================================================
# Part 1: 配置管理（ConfigManager）
# ==============================================================================


class ConfigManager:
    """统一配置管理

    功能：
    - 单例模式，全局配置访问
    - 配置热更新支持
    - 路径自动标准化
    - 类型转换
    - native_iocp集成（配置文件异步读写）
    """

    _instance: Optional["ConfigManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        """初始化配置管理器"""
        if hasattr(self, "_initialized"):
            return

        self._config: Dict[str, Any] = {}
        self._threshold_config: Dict[str, Any] = {}

        # 配置文件路径
        base_dir = Path(__file__).parent
        self._config_file: Path = base_dir / "config" / "system_config.yaml"
        self._threshold_file: Path = base_dir / "config" / "threshold_config.yaml"

        # 加载配置
        self._load_config()
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_config(self) -> None:
        """加载配置文件（同步版本）"""
        try:
            # 加载系统配置
            if self._config_file.exists():
                with open(self._config_file, "r", encoding="utf-8") as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info(f"系统配置加载成功: {self._config_file}")
            else:
                logger.warning(f"系统配置文件不存在: {self._config_file}", extra={"log_type": "SYSTEM"})
                self._config = self._get_default_config()

            # 加载阈值配置
            if self._threshold_file.exists():
                with open(self._threshold_file, "r", encoding="utf-8") as f:
                    self._threshold_config = yaml.safe_load(f) or {}
                logger.info(f"阈值配置加载成功: {self._threshold_file}")
            else:
                logger.warning(f"阈值配置文件不存在: {self._threshold_file}", extra={"log_type": "SYSTEM"})
                self._threshold_config = self._get_default_threshold_config()

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            self._config = self._get_default_config()
            self._threshold_config = self._get_default_threshold_config()

    async def reload_config_async(self) -> bool:
        """异步重新加载配置（使用native_iocp）

        Returns:
            bool: 加载成功返回True
        """
        try:
            # 尝试使用native_iocp
            try:
                from backend.infrastructure.native_iocp import compat_aopen, IOCP_AVAILABLE

                if IOCP_AVAILABLE:
                    # 使用native_iocp加载系统配置
                    async with await compat_aopen(
                        self._config_file, "r", encoding="utf-8"
                    ) as f:
                        content = await f.read()
                        self._config = yaml.safe_load(content) or {}

                    # 使用native_iocp加载阈值配置
                    async with await compat_aopen(
                        self._threshold_file, "r", encoding="utf-8"
                    ) as f:
                        content = await f.read()
                        self._threshold_config = yaml.safe_load(content) or {}

                    logger.info("配置文件重新加载成功（使用native_iocp）")
                    return True

            except ImportError:
                logger.debug("native_iocp不可用，降级到aiofiles")

            # 降级到aiofiles
            import aiofiles

            async with aiofiles.open(self._config_file, "r", encoding="utf-8") as f:
                content = await f.read()
                self._config = yaml.safe_load(content) or {}

            async with aiofiles.open(
                self._threshold_file, "r", encoding="utf-8"
            ) as f:
                content = await f.read()
                self._threshold_config = yaml.safe_load(content) or {}

            logger.info("配置文件重新加载成功（使用aiofiles）")
            return True

        except Exception as e:
            logger.error(f"配置文件重新加载失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键（支持点分隔符，如"monitoring.intervals.system"）
            default: 默认值

        Returns:
            配置值或默认值
        """
        try:
            keys = key.split(".")
            value = self._config

            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default

                if value is None:
                    return default

            return value

        except Exception as e:
            logger.debug(f"获取配置项失败: {key}, {e}")
            return default

    def get_threshold_config(self) -> Dict[str, Any]:
        """获取阈值配置

        Returns:
            阈值配置字典
        """
        return self._threshold_config.copy()

    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取监控配置

        Returns:
            监控配置字典
        """
        return self._config.get("monitoring", {})

    def get_ipc_config(self) -> Dict[str, Any]:
        """获取IPC配置

        Returns:
            IPC配置字典
        """
        return self._config.get("ipc", {})

    def get_cache_config(self) -> Dict[str, Any]:
        """获取缓存配置

        Returns:
            缓存配置字典
        """
        return self._config.get("cache", {})

    @staticmethod
    def _get_default_config() -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "monitoring": {
                "intervals": {
                    "system": 1.0,
                    "hardware": 5.0,
                    "smart": 300.0,
                    "bandwidth": 3600.0,
                },
                "enabled": {
                    "system": True,
                    "hardware": True,
                    "smart": True,
                    "bandwidth": False,
                },
                "process": {
                    "parent_check_interval": 10.0,
                    "auto_restart": True,
                    "max_restart_count": 3,
                },
            },
            "ipc": {
                "pipe_names": {
                    "alert": "monitor_alerts",
                    "status": "monitor_status",
                    "query": "monitor_query",
                },
                "timeout": 5.0,
                "retry_count": 3,
            },
            "cache": {
                "enabled": True,
                "ttl": {
                    "system_metrics": 60,
                    "bandwidth_result": 3600,
                    "smart_data": 1800,
                },
            },
        }

    @staticmethod
    def _get_default_threshold_config() -> Dict[str, Any]:
        """获取默认阈值配置"""
        return {
            "system_resources": {
                "cpu": {"warning": 60, "error": 80, "critical": 95},
                "memory": {"warning": 60, "error": 80, "critical": 95},
                "disk": {"warning": 70, "error": 85, "critical": 95},
            },
            "hardware_sensors": {
                "cpu_temp": {"warning": 70, "error": 80, "critical": 90},
                "gpu_temp": {"warning": 75, "error": 85, "critical": 95},
            },
            "smart_attributes": {
                "reallocated_sectors": {"warning": 1, "error": 5, "critical": 10},
                "pending_sectors": {"warning": 1, "error": 5, "critical": 10},
                "uncorrectable_errors": {"warning": 1, "error": 5, "critical": 10},
            },
        }


# ==============================================================================
# Part 2: 缓存管理（CacheManager）
# ==============================================================================


@dataclass
class CachedData:
    """缓存数据结构"""

    data: Any
    timestamp: float
    ttl: int
    cache_key: str

    def is_valid(self) -> bool:
        """检查缓存是否有效

        Returns:
            bool: 缓存有效返回True
        """
        return time.time() - self.timestamp < self.ttl


class CacheManager:
    """监控数据缓存管理

    功能：
    - 系统指标缓存
    - 带宽测试结果缓存
    - SMART数据缓存
    - TTL自动过期
    - native_iocp集成（缓存文件异步读写）
    """

    # 缓存目录
    CACHE_DIR = Path("data")

    @staticmethod
    def _ensure_cache_dir() -> None:
        """确保缓存目录存在"""
        CacheManager.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save_monitor_data(data: Any, cache_key: str, ttl: int = 300) -> bool:
        """保存监控数据（同步版本）

        Args:
            data: 要缓存的数据
            cache_key: 缓存键
            ttl: 缓存有效期（秒）

        Returns:
            bool: 保存成功返回True
        """
        try:
            CacheManager._ensure_cache_dir()
            cache_file = CacheManager.CACHE_DIR / f"{cache_key}.json"

            cached_data = CachedData(
                data=data, timestamp=time.time(), ttl=ttl, cache_key=cache_key
            )

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(asdict(cached_data), f, ensure_ascii=False, indent=2)

            logger.debug(f"缓存数据保存成功: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"保存缓存失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    @staticmethod
    async def save_monitor_data_async(
        data: Any, cache_key: str, ttl: int = 300
    ) -> bool:
        """异步保存监控数据（使用native_iocp）

        Args:
            data: 要缓存的数据
            cache_key: 缓存键
            ttl: 缓存有效期（秒）

        Returns:
            bool: 保存成功返回True
        """
        try:
            CacheManager._ensure_cache_dir()
            cache_file = CacheManager.CACHE_DIR / f"{cache_key}.json"

            cached_data = CachedData(
                data=data, timestamp=time.time(), ttl=ttl, cache_key=cache_key
            )

            json_data = json.dumps(asdict(cached_data), ensure_ascii=False, indent=2)

            # 尝试使用native_iocp
            try:
                from backend.infrastructure.native_iocp import compat_aopen, IOCP_AVAILABLE

                if IOCP_AVAILABLE:
                    async with await compat_aopen(
                        cache_file, "w", encoding="utf-8"
                    ) as f:
                        await f.write(json_data)
                    logger.debug(f"缓存数据保存成功（native_iocp）: {cache_key}")
                    return True

            except ImportError:
                logger.debug("native_iocp不可用，降级到aiofiles")

            # 降级到aiofiles
            import aiofiles

            async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
                await f.write(json_data)

            logger.debug(f"缓存数据保存成功（aiofiles）: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"保存缓存失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    @staticmethod
    def load_monitor_data(cache_key: str) -> Tuple[Any, bool]:
        """加载监控数据（同步版本）

        Args:
            cache_key: 缓存键

        Returns:
            Tuple[Any, bool]: (数据, 是否有效)
        """
        try:
            cache_file = CacheManager.CACHE_DIR / f"{cache_key}.json"

            if not cache_file.exists():
                return None, False

            with open(cache_file, "r", encoding="utf-8") as f:
                cached_dict = json.load(f)

            cached_data = CachedData(**cached_dict)

            if cached_data.is_valid():
                logger.debug(f"缓存数据加载成功: {cache_key}")
                return cached_data.data, True
            else:
                logger.debug(f"缓存数据已过期: {cache_key}")
                return cached_data.data, False

        except Exception as e:
            logger.debug(f"加载缓存失败: {e}")
            return None, False

    @staticmethod
    async def load_monitor_data_async(cache_key: str) -> Tuple[Any, bool]:
        """异步加载监控数据（使用native_iocp）

        Args:
            cache_key: 缓存键

        Returns:
            Tuple[Any, bool]: (数据, 是否有效)
        """
        try:
            cache_file = CacheManager.CACHE_DIR / f"{cache_key}.json"

            if not cache_file.exists():
                return None, False

            # 尝试使用native_iocp
            try:
                from backend.infrastructure.native_iocp import compat_aopen, IOCP_AVAILABLE

                if IOCP_AVAILABLE:
                    async with await compat_aopen(
                        cache_file, "r", encoding="utf-8"
                    ) as f:
                        content = await f.read()
                        cached_dict = json.loads(content)

                    cached_data = CachedData(**cached_dict)

                    if cached_data.is_valid():
                        logger.debug(f"缓存数据加载成功（native_iocp）: {cache_key}")
                        return cached_data.data, True
                    else:
                        logger.debug(f"缓存数据已过期: {cache_key}")
                        return cached_data.data, False

            except ImportError:
                logger.debug("native_iocp不可用，降级到aiofiles")

            # 降级到aiofiles
            import aiofiles

            async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                content = await f.read()
                cached_dict = json.loads(content)

            cached_data = CachedData(**cached_dict)

            if cached_data.is_valid():
                logger.debug(f"缓存数据加载成功（aiofiles）: {cache_key}")
                return cached_data.data, True
            else:
                logger.debug(f"缓存数据已过期: {cache_key}")
                return cached_data.data, False

        except Exception as e:
            logger.debug(f"加载缓存失败: {e}")
            return None, False


# ==============================================================================
# Part 3: 事件系统（EventPublisher系列）
# ==============================================================================


class EventPublisher:
    """通用事件发布器

    功能：
    - 封装EventEngine事件发布
    - 提供类型安全的事件发布接口
    """

    def __init__(self, event_engine: "EventEngine"):
        """初始化事件发布器

        Args:
            event_engine: VnPy事件引擎
        """
        self.event_engine = event_engine

    def publish(self, event_type: str, data: Any) -> None:
        """发布事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self.event_engine is None:
            logger.warning("EventEngine未初始化，无法发布事件", extra={"log_type": "SYSTEM"})
            return

        try:
            event = Event(event_type, data)
            self.event_engine.put(event)
            logger.debug(f"事件已发布: {event_type}")
        except Exception as e:
            logger.error(f"发布事件失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})


class SystemEventPublisher(EventPublisher):
    """系统监控事件发布器"""

    # 事件类型定义
    EVENT_SYSTEM_METRICS = "eSystemMetrics"
    EVENT_RESOURCE_USAGE = "eResourceUsage"

    def publish_system_metrics(self, metrics: Dict) -> None:
        """发布系统指标

        Args:
            metrics: 系统指标数据
        """
        self.publish(self.EVENT_SYSTEM_METRICS, metrics)

    def publish_resource_usage(self, usage: Dict) -> None:
        """发布资源使用率

        Args:
            usage: 资源使用率数据
        """
        self.publish(self.EVENT_RESOURCE_USAGE, usage)


class HardwareEventPublisher(EventPublisher):
    """硬件监控事件发布器"""

    # 事件类型定义
    EVENT_HARDWARE_SENSORS = "eHardwareSensors"
    EVENT_SMART_DATA = "eSmartData"

    def publish_hardware_sensors(self, sensors: Dict) -> None:
        """发布硬件传感器数据

        Args:
            sensors: 硬件传感器数据
        """
        self.publish(self.EVENT_HARDWARE_SENSORS, sensors)

    def publish_smart_data(self, smart_data: Dict) -> None:
        """发布SMART数据

        Args:
            smart_data: SMART数据
        """
        self.publish(self.EVENT_SMART_DATA, smart_data)


class AlertEventPublisher(EventPublisher):
    """告警事件发布器"""

    # 事件类型定义
    EVENT_ALERT_CREATED = "eAlertCreated"
    EVENT_ALERT_UPDATED = "eAlertUpdated"

    def publish_alert_created(self, alert: Dict) -> None:
        """发布告警创建事件

        Args:
            alert: 告警数据
        """
        self.publish(self.EVENT_ALERT_CREATED, alert)

    def publish_alert_updated(self, alert: Dict) -> None:
        """发布告警更新事件

        Args:
            alert: 告警数据
        """
        self.publish(self.EVENT_ALERT_UPDATED, alert)


class BusinessEventPublisher(EventPublisher):
    """业务监控事件发布器"""

    # 事件类型定义
    EVENT_BUSINESS_METRICS = "eBusinessMetrics"
    EVENT_BOTTLENECK_DETECTED = "eBottleneckDetected"

    def publish_business_metrics(self, metrics: Dict) -> None:
        """发布业务指标

        Args:
            metrics: 业务指标数据
        """
        self.publish(self.EVENT_BUSINESS_METRICS, metrics)

    def publish_bottleneck_detected(self, bottleneck: Dict) -> None:
        """发布瓶颈检测结果

        Args:
            bottleneck: 瓶颈数据
        """
        self.publish(self.EVENT_BOTTLENECK_DETECTED, bottleneck)


# ==============================================================================
# Part 4: 引擎注册表（EngineRegistry）
# ==============================================================================


class EngineRegistry:
    """引擎注册表

    功能：
    - 管理所有子引擎实例
    - 统一生命周期管理
    - 单例模式
    - 延迟初始化
    """

    _instance: Optional["EngineRegistry"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        """初始化引擎注册表"""
        if hasattr(self, "_initialized"):
            return

        self._engines: Dict[str, Any] = {}
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "EngineRegistry":
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, name: str, engine: Any) -> None:
        """注册引擎

        Args:
            name: 引擎名称
            engine: 引擎实例
        """
        self._engines[name] = engine
        logger.info(f"引擎已注册: {name}")

    def get(self, name: str) -> Optional[Any]:
        """获取引擎

        Args:
            name: 引擎名称

        Returns:
            引擎实例或None
        """
        return self._engines.get(name)

    def get_all(self) -> Dict[str, Any]:
        """获取所有引擎

        Returns:
            引擎字典
        """
        return self._engines.copy()

    def unregister(self, name: str) -> bool:
        """注销引擎

        Args:
            name: 引擎名称

        Returns:
            bool: 注销成功返回True
        """
        if name in self._engines:
            del self._engines[name]
            logger.info(f"引擎已注销: {name}")
            return True
        return False


# ==============================================================================
# Part 5: 核心引擎（SystemManagerEngine）
# ==============================================================================


class SystemManagerEngine:
    """系统管理引擎（核心引擎）

    核心职责：
    - 整个模块的统一入口
    - 初始化所有子组件
    - 提供统一API接口
    - 协调组件间交互
    - 健康检查和状态管理
    - 启动/停止监控进程
    - native_ipc集成（与监控进程的所有通信）
    """

    def __init__(self, main_engine: Any, event_engine: "EventEngine"):
        """初始化系统管理引擎

        Args:
            main_engine: VnPy主引擎
            event_engine: VnPy事件引擎
        """
        self.main_engine = main_engine
        self.event_engine = event_engine

        # 初始化配置管理
        self.config_manager = ConfigManager.get_instance()

        # 初始化事件发布器
        self.system_publisher = SystemEventPublisher(event_engine)
        self.hardware_publisher = HardwareEventPublisher(event_engine)
        self.alert_publisher = AlertEventPublisher(event_engine)
        self.business_publisher = BusinessEventPublisher(event_engine)

        # 监控进程引用
        self.monitor_process: Optional[subprocess.Popen] = None
        self._ipc_pipes: Dict[str, Any] = {}

        # 状态管理
        self._is_ready: bool = False
        self._initialization_lock: threading.Lock = threading.Lock()

        # 注册到引擎注册表
        registry = EngineRegistry.get_instance()
        registry.register("system_manager", self)

        logger.info("SystemManagerEngine初始化完成")

    def initialize(self) -> bool:
        """初始化引擎

        Returns:
            bool: 初始化成功返回True
        """
        with self._initialization_lock:
            if self._is_ready:
                logger.info("SystemManagerEngine已经初始化")
                return True

            try:
                logger.info("正在初始化SystemManagerEngine...")

                # 初始化子组件
                self._initialize_components()

                self._is_ready = True
                logger.info("✅ SystemManagerEngine初始化成功")
                return True

            except Exception as e:
                logger.critical(f"🔥 SystemManagerEngine初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
                return False

    def _initialize_components(self) -> None:
        """初始化子组件"""
        logger.info("初始化子组件...")

        # 确保缓存目录存在
        CacheManager._ensure_cache_dir()

        # 加载配置
        monitoring_config = self.config_manager.get_monitoring_config()
        logger.info(f"监控配置: {monitoring_config}")

        # 初始化完成
        logger.info("子组件初始化完成")

    async def start_monitoring_process(self) -> bool:
        """启动监控进程

        Returns:
            bool: 启动成功返回True
        """
        try:
            logger.info("=" * 80)
            logger.info("正在启动监控进程...")
            logger.info("=" * 80)

            # 1. 检查native_ipc可用性
            try:
                from backend.infrastructure.native_ipc import AsyncIPCPipe, IPC_AVAILABLE

                if not IPC_AVAILABLE:
                    logger.warning("⚠️ native_ipc不可用，监控功能将在主进程运行（降级模式）", extra={"log_type": "SYSTEM"})
                    return True

                logger.info("✅ native_ipc可用")

            except ImportError:
                logger.warning("⚠️ native_ipc模块未安装，监控功能将在主进程运行（降级模式）", extra={"log_type": "SYSTEM"})
                return True

            # 2. 获取IPC配置
            ipc_config = self.config_manager.get_ipc_config()
            pipe_names = ipc_config.get("pipe_names", {})
            alert_pipe_name = pipe_names.get("alert", "monitor_alerts")

            # 3. 创建IPC管道（服务端模式 - 监听告警推送）
            logger.info(f"创建IPC管道: {alert_pipe_name}")
            self._ipc_pipes["alert"] = await AsyncIPCPipe.create_as_server(
                alert_pipe_name
            )
            logger.info("✅ 告警管道创建成功")

            # 4. 启动监控进程
            # 使用 monitor_system.py 作为入口（已包含 main() 函数）
            monitor_script = Path(__file__).parent / "monitor_system.py"

            if not monitor_script.exists():
                logger.error(
                    f"❌ 监控进程入口文件不存在: {monitor_script}。"
                    f" 解决方案: 1) 确保monitor_system.py文件存在于正确位置；2) 检查文件路径配置", 
                    extra={"log_type": "ALERT"}
                )
                return False

            logger.info(f"启动监控进程: {monitor_script}")

            # Windows环境使用CREATE_NEW_PROCESS_GROUP
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

            self.monitor_process = subprocess.Popen(
                [sys.executable, str(monitor_script)],
                creationflags=creation_flags,
            )

            logger.info(f"✅ 监控进程已启动，PID={self.monitor_process.pid}")

            # 5. 启动告警接收任务
            asyncio.create_task(self._receive_alerts())
            logger.info("✅ 告警接收任务已启动")

            logger.info("=" * 80)
            logger.info("✅ 监控进程启动完成")
            logger.info("=" * 80)
            return True

        except Exception as e:
            logger.critical(f"🔥 启动监控进程失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            return False

    async def stop_monitoring_process(self) -> bool:
        """停止监控进程

        Returns:
            bool: 停止成功返回True
        """
        try:
            logger.info("正在停止监控进程...")

            # 1. 关闭IPC管道
            for pipe_name, pipe in self._ipc_pipes.items():
                try:
                    if pipe:
                        await pipe.close()
                        logger.info(f"IPC管道已关闭: {pipe_name}")
                except Exception as e:
                    logger.error(f"关闭IPC管道失败: {pipe_name}, {e}", extra={"log_type": "SYSTEM"})

            self._ipc_pipes.clear()

            # 2. 终止监控进程
            if self.monitor_process:
                try:
                    self.monitor_process.terminate()
                    self.monitor_process.wait(timeout=10)
                    logger.info(f"监控进程已终止，PID={self.monitor_process.pid}")
                except Exception as e:
                    logger.error(f"终止监控进程失败: {e}", extra={"log_type": "SYSTEM"})
                    # 强制杀死
                    self.monitor_process.kill()
                    logger.warning("监控进程已被强制终止", extra={"log_type": "SYSTEM"})

                self.monitor_process = None

            logger.info("✅ 监控进程停止完成")
            return True

        except Exception as e:
            logger.error(f"停止监控进程失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return False

    async def _receive_alerts(self):
        """接收监控进程的告警推送"""
        alert_pipe = self._ipc_pipes.get("alert")
        if not alert_pipe:
            logger.warning("告警管道未初始化", extra={"log_type": "SYSTEM"})
            return

        logger.info("开始接收监控进程告警...")

        while True:
            try:
                # 读取告警数据
                alert_data = await alert_pipe.read_json()

                logger.info(f"收到告警: {alert_data.get('message', 'N/A')}")

                # 发布到事件引擎
                self.alert_publisher.publish_alert_created(alert_data)

            except Exception as e:
                logger.error(f"接收告警失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
                await asyncio.sleep(1)

    async def query_monitor_data(self, query_type: str) -> Optional[Dict]:
        """查询监控数据

        Args:
            query_type: 查询类型（get_system, get_hardware, test_bandwidth等）

        Returns:
            监控数据或None
        """
        try:
            from backend.infrastructure.native_ipc import AsyncIPCPipe

            ipc_config = self.config_manager.get_ipc_config()
            pipe_names = ipc_config.get("pipe_names", {})
            query_pipe_name = pipe_names.get("query", "monitor_query")
            timeout = ipc_config.get("timeout", 5.0)

            # 连接查询管道
            async with await AsyncIPCPipe.connect_as_client(
                query_pipe_name, timeout=timeout
            ) as pipe:
                # 发送查询请求
                await pipe.write_json({"action": query_type, "params": {}})

                # 接收响应
                response = await pipe.read_json()

                if response.get("success"):
                    return response.get("data")
                else:
                    logger.error(f"查询失败: {response.get('error')}", extra={"log_type": "SYSTEM"})
                    return None

        except Exception as e:
            logger.error(f"查询监控数据失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return None

    # ==========================================================================
    # API接口（保持100%向后兼容）
    # ==========================================================================

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息（同步接口，保持兼容）

        Returns:
            系统信息字典
        """
        try:
            # 尝试从缓存加载
            data, is_valid = CacheManager.load_monitor_data("system_info")
            if is_valid:
                return data

            # 缓存失效，查询监控进程（需要异步，这里返回空）
            logger.warning("get_system_info需要异步查询，请使用get_system_info_async", extra={"log_type": "SYSTEM"})
            return {}

        except Exception as e:
            logger.error(f"获取系统信息失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    async def get_system_info_async(self) -> Dict[str, Any]:
        """获取系统信息（异步接口）

        Returns:
            系统信息字典
        """
        try:
            # 尝试从缓存加载
            data, is_valid = await CacheManager.load_monitor_data_async("system_info")
            if is_valid:
                return data

            # 缓存失效，查询监控进程
            data = await self.query_monitor_data("get_system")
            if data:
                # 更新缓存
                await CacheManager.save_monitor_data_async(
                    data, "system_info", ttl=60
                )
                return data

            return {}

        except Exception as e:
            logger.error(f"获取系统信息失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def test_bandwidth(self) -> Dict[str, Any]:
        """测试网络带宽（同步接口，保持兼容）

        Returns:
            带宽测试结果
        """
        try:
            logger.warning("test_bandwidth需要异步查询，请使用test_bandwidth_async", extra={"log_type": "SYSTEM"})
            return {}

        except Exception as e:
            logger.error(f"测试网络带宽失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    async def test_bandwidth_async(self) -> Dict[str, Any]:
        """测试网络带宽（异步接口）

        Returns:
            带宽测试结果
        """
        try:
            # 查询监控进程
            data = await self.query_monitor_data("test_bandwidth")
            if data:
                # 更新缓存
                await CacheManager.save_monitor_data_async(
                    data, "bandwidth_result", ttl=3600
                )
                return data

            return {}

        except Exception as e:
            logger.error(f"测试网络带宽失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def healthcheck(self) -> Dict[str, Any]:
        """健康检查

        Returns:
            健康检查结果
        """
        try:
            status = {
                "status": "ok" if self._is_ready else "error",
                "timestamp": datetime.now().isoformat(),
                "monitoring_process_running": self.monitor_process is not None
                and self.monitor_process.poll() is None,
                "ipc_pipes_count": len(self._ipc_pipes),
            }

            return status

        except Exception as e:
            logger.error(f"健康检查失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            return {"status": "error", "error": str(e)}


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "ConfigManager",
    "CacheManager",
    "CachedData",
    "EventPublisher",
    "SystemEventPublisher",
    "HardwareEventPublisher",
    "AlertEventPublisher",
    "BusinessEventPublisher",
    "EngineRegistry",
    "SystemManagerEngine",
]
