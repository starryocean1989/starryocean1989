"""
负载均衡模块 - 架构v3.0重构版

本模块负责智能负载均衡，包括：
- 负载均衡器（LoadBalancer）
- 服务器池管理（ServerPoolManager）
- 资源监控（ResourceMonitor）
- 动态配置计算（DynamicConfigCalculator）

架构特性：
- 木桶理论：系统性能 = min(CPU, 内存, 磁盘IO)
- 动态并发调整（0.3x-1.6x缩放）
- 智能防抖机制（基础1秒，特定模式3秒）
- 两段式下载支持（IPv4→IPv6）
- native_iocp集成：服务器池缓存异步读写
- 100% API向后兼容

重构日期：2025年
作者：AI Assistant (基于v2.1重构)
"""

import asyncio
import logging
import psutil
import threading
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.infrastructure.tdx_asyncio.retry_connection_pool import RetryConnectionPool

# 导入TDX异步API
from backend.infrastructure.tdx_asyncio import ServerTester

# 导入核心模块
from .core_engine import ConfigManager

# ==================== 日志配置 ====================
logger = logging.getLogger("backend.data_module.loadbalancer")


# ==============================================================================
# Part 0: 任务类型系统（v3.1新增）
# ==============================================================================


class TaskCategory(str, Enum):
    """任务类别（轻量级枚举）"""

    NETWORK_DOWNLOAD = "network_download"  # K线下载（网络I/O密集）
    LOCAL_SCAN = "local_scan"  # 本地数据扫描（磁盘I/O密集）
    LOCAL_READ = "local_read"  # TDX数据读取（磁盘I/O密集）


@dataclass
class TaskConfig:
    """任务配置（简化版TaskMetrics）"""

    name: str  # 任务名称
    category: TaskCategory  # 任务类别
    total_count: int  # 任务总数

    # 资源特征
    is_io_intensive: bool = True
    is_cpu_intensive: bool = False
    is_memory_intensive: bool = False

    # 预估资源
    estimated_memory_mb: float = 100.0
    estimated_duration_sec: float = 60.0


@dataclass
class QueueMetrics:
    """队列指标（观察磁盘I/O的关键指标）"""

    queue_name: str
    current_size: int  # 当前队列大小
    max_size: int  # 最大队列容量
    fill_rate: float  # 填充率（0-1）

    # 背压相关指标
    enqueue_lag_ms: float = 0.0  # 入队延迟（毫秒）
    dequeue_lag_ms: float = 0.0  # 出队延迟（毫秒）
    avg_task_time_ms: float = 0.0  # 平均任务耗时（毫秒）

    # 告警阈值
    HIGH_FILL_RATE = 0.8  # 80%填充率告警
    CRITICAL_FILL_RATE = 0.95  # 95%填充率严重告警


class QueuePressureMonitor:
    """队列压力监控器（轻量级）

    专注于磁盘I/O观察，作为木桶理论第四板：
    - 通过队列积压反映磁盘I/O瓶颈
    - 提供调整系数用于动态并发控制
    """

    def __init__(self):
        """初始化队列压力监控器"""
        self._metrics_history = deque(maxlen=60)  # 保留60秒历史

    def record_metrics(self, metrics: QueueMetrics) -> None:
        """记录队列指标

        Args:
            metrics: 队列指标
        """
        self._metrics_history.append(metrics)

    def get_pressure_level(self) -> str:
        """获取压力等级

        Returns:
            压力等级：normal/medium/high/critical
        """
        if not self._metrics_history:
            return "normal"

        latest = self._metrics_history[-1]

        if latest.fill_rate >= QueueMetrics.CRITICAL_FILL_RATE:
            return "critical"
        elif latest.fill_rate >= QueueMetrics.HIGH_FILL_RATE:
            return "high"
        elif latest.fill_rate >= 0.6:
            return "medium"
        else:
            return "normal"

    def get_adjustment_factor(self) -> float:
        """获取调整系数（用于动态调整并发）

        Returns:
            调整系数（0.5-1.0）
        """
        pressure = self.get_pressure_level()

        # 根据压力等级返回调整系数
        if pressure == "critical":
            return 0.5  # 严重积压，减半
        elif pressure == "high":
            return 0.7  # 高压，减少30%
        elif pressure == "medium":
            return 0.9  # 中压，减少10%
        else:
            return 1.0  # 正常，不调整


class TaskStrategyRegistry:
    """任务策略注册表

    为不同任务类型提供基准配置和资源权重：
    - 网络下载：网络I/O密集
    - 本地扫描：磁盘I/O密集，大量小文件
    - 本地读取：磁盘I/O密集，需要CPU解码
    """

    _strategies: Dict[TaskCategory, Dict[str, Any]] = {
        # K线下载：网络I/O密集
        TaskCategory.NETWORK_DOWNLOAD: {
            "base_processes": 4,
            "base_coroutines_per_process": 40,
            "max_processes": 8,
            "max_coroutines_per_process": 50,
            "resource_weights": {
                "cpu": 0.2,
                "memory": 0.3,
                "disk_io": 0.1,
                "network_io": 0.4,  # 网络I/O权重最高
            },
            "description": "网络下载任务（K线、IPO日期）",
        },
        # 本地数据扫描：磁盘I/O密集
        TaskCategory.LOCAL_SCAN: {
            "base_processes": 8,
            "base_coroutines_per_process": 2000,  # 协程数高（大量小文件）
            "max_processes": 16,
            "max_coroutines_per_process": 3000,
            "resource_weights": {
                "cpu": 0.2,
                "memory": 0.2,
                "disk_io": 0.5,  # 磁盘I/O权重最高
                "network_io": 0.1,
            },
            "description": "本地数据扫描（质量检查）",
        },
        # TDX数据读取：磁盘I/O密集
        TaskCategory.LOCAL_READ: {
            "base_processes": 4,
            "base_coroutines_per_process": 1000,
            "max_processes": 8,
            "max_coroutines_per_process": 1500,
            "resource_weights": {
                "cpu": 0.3,  # TDX解码需要CPU
                "memory": 0.2,
                "disk_io": 0.4,  # 磁盘I/O权重高
                "network_io": 0.1,
            },
            "description": "TDX本地文件读取",
        },
    }

    @classmethod
    def get_strategy(cls, category: TaskCategory) -> Dict[str, Any]:
        """获取任务策略

        Args:
            category: 任务类别

        Returns:
            策略配置字典
        """
        return cls._strategies.get(category, cls._strategies[TaskCategory.NETWORK_DOWNLOAD])


# ==============================================================================
# Part 1: 资源监控（ResourceMonitor）
# ==============================================================================


@dataclass
class ResourceMetrics:
    """资源指标"""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_io_percent: float = 0.0
    network_io_percent: float = 0.0
    bottleneck: str = "unknown"  # 瓶颈资源
    timestamp: datetime = field(default_factory=datetime.now)


class ResourceMonitor:
    """系统资源监控器

    实时监控系统资源，计算木桶理论指标：
    - CPU使用率
    - 内存使用率
    - 磁盘I/O使用率
    - 网络I/O使用率
    """

    def __init__(self):
        """初始化资源监控器"""
        self._last_disk_io = None
        self._last_network_io = None
        self._last_check_time = None

    def get_metrics(self) -> ResourceMetrics:
        """获取当前资源指标

        Returns:
            资源指标
        """
        metrics = ResourceMetrics()

        # CPU使用率
        try:
            cpu_usage = psutil.cpu_percent(interval=0.1)
            if isinstance(cpu_usage, (int, float)):
                metrics.cpu_percent = float(cpu_usage)
        except Exception as e:
            logger.debug(f"获取CPU使用率失败: {e}")
            metrics.cpu_percent = 0.0

        # 内存使用率
        try:
            memory = psutil.virtual_memory()
            metrics.memory_percent = memory.percent
        except Exception as e:
            logger.debug(f"获取内存使用率失败: {e}")
            metrics.memory_percent = 0.0

        # 磁盘I/O使用率（简化估算）
        try:
            disk_io = psutil.disk_io_counters()
            current_time = time.time()

            if disk_io and self._last_disk_io and self._last_check_time:
                time_delta = current_time - self._last_check_time
                read_bytes_delta = disk_io.read_bytes - self._last_disk_io.read_bytes  # type: ignore
                write_bytes_delta = disk_io.write_bytes - self._last_disk_io.write_bytes  # type: ignore

                # 计算I/O速率（MB/s）
                io_rate = (read_bytes_delta + write_bytes_delta) / time_delta / (1024 * 1024)
                # 假设最大I/O速率为100 MB/s（HDD），计算百分比
                metrics.disk_io_percent = min(100.0, io_rate / 100.0 * 100.0)

            self._last_disk_io = disk_io
            self._last_check_time = current_time
        except Exception as e:
            logger.debug(f"获取磁盘I/O使用率失败: {e}")
            metrics.disk_io_percent = 0.0

        # 确定瓶颈（木桶理论）
        resources = {
            "CPU": metrics.cpu_percent,
            "Memory": metrics.memory_percent,
            "DiskIO": metrics.disk_io_percent,
        }
        metrics.bottleneck = max(resources, key=lambda k: resources[k])  # type: ignore

        return metrics


# ==============================================================================
# Part 2: 动态配置计算（DynamicConfigCalculator）
# ==============================================================================


class DynamicConfigCalculator:
    """动态配置计算器

    根据资源指标计算最优并发配置：
    - 基于木桶理论
    - 考虑任务类型
    - 动态缩放（0.3x-1.6x）
    """

    # 基准配置
    BASE_CONFIG = {
        "max_workers": 4,
        "coroutines_per_worker": 50,
    }

    # 缩放范围
    SCALE_MIN = 0.3
    SCALE_MAX = 1.6

    def __init__(self, resource_monitor: Optional[ResourceMonitor] = None):
        """初始化配置计算器

        Args:
            resource_monitor: 资源监控器
        """
        self.resource_monitor = resource_monitor or ResourceMonitor()

    def calculate(self, task_type: str = "download") -> Dict[str, int]:
        """计算最优配置

        Args:
            task_type: 任务类型（download/scan/validate）

        Returns:
            配置字典
        """
        # 获取资源指标
        metrics = self.resource_monitor.get_metrics()

        # 计算缩放因子（基于瓶颈资源的反向缩放）
        bottleneck_value = getattr(metrics, f"{metrics.bottleneck.lower()}_percent", 50.0)

        # 瓶颈资源使用率越高，缩放因子越小
        if bottleneck_value > 80:
            scale = self.SCALE_MIN
        elif bottleneck_value > 60:
            scale = 0.6
        elif bottleneck_value > 40:
            scale = 1.0
        else:
            scale = self.SCALE_MAX

        # 应用缩放
        config = {
            "max_workers": max(1, int(self.BASE_CONFIG["max_workers"] * scale)),
            "coroutines_per_worker": max(
                10, int(self.BASE_CONFIG["coroutines_per_worker"] * scale)
            ),
        }

        logger.debug(
            f"动态配置: workers={config['max_workers']}, "
            f"coroutines={config['coroutines_per_worker']}, "
            f"瓶颈={metrics.bottleneck}({bottleneck_value:.1f}%), 缩放={scale:.1f}x"
        )

        return config


# ==============================================================================
# Part 3: 服务器池管理（ServerPoolManager）
# ==============================================================================


@dataclass
class ServerInfo:
    """服务器信息"""

    ip: str
    port: int
    name: str = ""
    ping_time: float = 0.0  # 延迟（毫秒）
    available: bool = True
    last_test: Optional[datetime] = None
    max_connections: int = 20  # 最大并发连接数（默认20）


class ServerPoolManager:
    """服务器池管理器

    TDX服务器测速、排序、热备管理：
    - 多进程测速
    - IPv4/IPv6分离
    - 两段式下载支持
    - 缓存机制（native_iocp集成）
    """

    # 默认服务器列表
    # 🎯 使用constants.py中所有的7709端口IPv4服务器
    DEFAULT_IPV4_SERVERS = []
    DEFAULT_IPV6_SERVERS = []

    @classmethod
    def _init_default_servers(cls):
        """初始化默认服务器列表（从constants.py加载）"""
        if cls.DEFAULT_IPV4_SERVERS:  # 已初始化
            return

        try:
            from backend.infrastructure.tdx_asyncio.constants import BROKER_SERVERS_7709

            # ✅ 直接使用BROKER_SERVERS_7709（已包含所有服务器，格式：(名称, IP, 端口, 最大连接数)）
            all_7709_servers = list(BROKER_SERVERS_7709)

            # 使用集合去重（基于(ip, port)）
            seen = set()
            unique_servers = []
            for name, ip, port, max_conn in all_7709_servers:
                if port == 7709:
                    key = (ip, port)
                    if key not in seen:
                        seen.add(key)
                        # 保存完整的4字段信息，用于后续处理
                        unique_servers.append((name, ip, port, max_conn))

            # 提取所有7709端口的IPv4和IPv6服务器（包含最大连接数信息）
            for name, ip, port, max_conn in unique_servers:
                server_info = {"ip": ip, "port": port, "name": name, "max_connections": max_conn}

                # 判断IPv4还是IPv6
                if ":" in ip and ip.strip("[]").count(":") > 1:
                    # IPv6（需要去掉中括号）
                    clean_ip = ip.strip("[]")
                    server_info["ip"] = clean_ip
                    cls.DEFAULT_IPV6_SERVERS.append(server_info)
                else:
                    # IPv4
                    cls.DEFAULT_IPV4_SERVERS.append(server_info)

            logger.info(
                f"✅ 从constants.py加载默认服务器: IPv4={len(cls.DEFAULT_IPV4_SERVERS)}, IPv6={len(cls.DEFAULT_IPV6_SERVERS)}"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ 从constants.py加载服务器失败: {e}, 使用备用服务器", extra={"log_type": "SYSTEM"}
            )
            # 备用服务器列表
            cls.DEFAULT_IPV4_SERVERS = [
                {"ip": "119.147.212.81", "port": 7709, "name": "广东电信1"},
                {"ip": "113.105.73.88", "port": 7709, "name": "广东电信2"},
                {"ip": "113.105.73.86", "port": 7709, "name": "广东电信3"},
                {"ip": "120.79.60.82", "port": 7709, "name": "广东移动"},
                {"ip": "113.105.142.136", "port": 443, "name": "广东联通"},
            ]
            cls.DEFAULT_IPV6_SERVERS = [
                {"ip": "2408:8256:3be:3880::1", "port": 7709, "name": "广东电信IPv6"},
            ]

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """初始化服务器池管理器

        Args:
            config_manager: 配置管理器
        """
        # 🎯 首先初始化默认服务器列表
        self._init_default_servers()

        self.config_manager = config_manager or ConfigManager()

        # 服务器池
        self._ipv4_servers: List[ServerInfo] = []
        self._ipv6_servers: List[ServerInfo] = []

        # 🔧 修复：使用 ConfigManager 获取缓存目录，确保使用 data/cache 目录
        cache_dir = self.config_manager.get_cache_dir()
        self._cache_file = cache_dir / "server_pool.json"

        # 🎯 连接池复用机制
        self._connection_pool: Optional[ProcessPoolExecutor] = (
            None  # ProcessPoolExecutor连接池（用于启动时复用）
        )
        self._retry_connection_pool: Optional["RetryConnectionPool"] = (
            None  # RetryConnectionPool连接池（用于启动时复用）
        )
        self._pool_mode = "auto"  # auto: 自动管理, manual: 手动管理

        # 加载服务器
        self._load_servers()

        # 🔧 修复：检查缓存状态，但不阻塞初始化（延迟测速）
        self._cache_needs_update = False
        self._check_cache_status()

        logger.debug(
            f"✅ 服务器池管理器已初始化: "
            f"IPv4={len(self._ipv4_servers)}, IPv6={len(self._ipv6_servers)}"
        )

    def _check_cache_status(self):
        """检查缓存状态（不阻塞）"""
        try:
            from .core_engine import DailyCacheManager

            # 检查缓存是否存在且有效
            cached_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                self._cache_file
            )

            if cached_data is not None and is_valid:
                # 缓存有效，无需更新
                self._cache_needs_update = False
                return

            # 缓存不存在或已过时，标记需要更新（在实际使用时再触发测速）
            self._cache_needs_update = True
            if cached_data is None:
                logger.debug("🔧 服务器池缓存不存在，将在首次使用时自动测速生成...")
            else:
                logger.info(
                    f"🔧 服务器池缓存已过时（日期: {cache_date}），将在首次使用时自动更新..."
                )
        except Exception as e:
            logger.debug(f"检查服务器池缓存状态失败: {e}")
            self._cache_needs_update = True

    def _load_servers(self):
        """加载服务器列表

        优先级：
        1. 从缓存文件加载（如果有效且不为空）
        2. 从配置加载
        3. 使用默认服务器列表
        """
        # 🔧 修复：首先尝试从缓存加载
        try:
            from .core_engine import DailyCacheManager

            cached_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                self._cache_file
            )

            if cached_data is not None and is_valid and isinstance(cached_data, dict):
                # 从缓存恢复服务器列表
                ipv4_servers_data = cached_data.get("ipv4_servers", [])
                ipv6_servers_data = cached_data.get("ipv6_servers", [])

                # 只有当缓存中有实际数据时才使用缓存
                if ipv4_servers_data or ipv6_servers_data:
                    # 转换为ServerInfo
                    # 🔧 修复：从缓存加载时，保留缓存中的 available 状态，优先使用本地缓存
                    self._ipv4_servers = [
                        ServerInfo(
                            ip=s.get("ip", ""),
                            port=s.get("port", 7709),
                            name=s.get("name", ""),
                            max_connections=s.get("max_connections", 20),
                            ping_time=s.get("ping_time", 9999.0),
                            available=s.get("available", True),  # 🔧 从缓存加载，保留缓存中的状态
                            last_test=(
                                datetime.fromisoformat(s["last_test"])
                                if s.get("last_test")
                                else None
                            ),
                        )
                        for s in ipv4_servers_data
                    ]

                    self._ipv6_servers = [
                        ServerInfo(
                            ip=s.get("ip", ""),
                            port=s.get("port", 7709),
                            name=s.get("name", ""),
                            max_connections=s.get("max_connections", 20),
                            ping_time=s.get("ping_time", 9999.0),
                            available=s.get("available", True),  # 🔧 从缓存加载，保留缓存中的状态
                            last_test=(
                                datetime.fromisoformat(s["last_test"])
                                if s.get("last_test")
                                else None
                            ),
                        )
                        for s in ipv6_servers_data
                    ]

                    # 统计可用服务器数量
                    ipv4_available = sum(1 for s in self._ipv4_servers if s.available)
                    ipv6_available = sum(1 for s in self._ipv6_servers if s.available)

                    logger.info(
                        f"✅ 从缓存加载服务器池: "
                        f"IPv4={len(self._ipv4_servers)} (可用: {ipv4_available}), "
                        f"IPv6={len(self._ipv6_servers)} (可用: {ipv6_available})"
                    )
                    return
                else:
                    logger.debug("缓存文件存在但为空，将使用默认服务器列表")
        except Exception as e:
            logger.debug(f"从缓存加载服务器失败: {e}")

        # 🔧 降级：从配置加载
        try:
            ipv4_config = self.config_manager.get("tdx.servers.ipv4", [])
            ipv6_config = self.config_manager.get("tdx.servers.ipv6", [])
        except Exception as e:
            logger.warning(
                f"⚠️ [LoadBalancer] 从配置加载服务器列表失败: {e}, 使用空列表",
                extra={"log_type": "SYSTEM"},
            )
            ipv4_config = []
            ipv6_config = []

        # 转换为ServerInfo
        if ipv4_config:
            self._ipv4_servers = [ServerInfo(**server) for server in ipv4_config]
            logger.info(f"✅ 从配置加载IPv4服务器: {len(self._ipv4_servers)} 个")
        else:
            self._ipv4_servers = [ServerInfo(**server) for server in self.DEFAULT_IPV4_SERVERS]
            logger.info(f"✅ 使用默认IPv4服务器列表: {len(self._ipv4_servers)} 个")

        if ipv6_config:
            self._ipv6_servers = [ServerInfo(**server) for server in ipv6_config]
            logger.info(f"✅ 从配置加载IPv6服务器: {len(self._ipv6_servers)} 个")
        else:
            self._ipv6_servers = [ServerInfo(**server) for server in self.DEFAULT_IPV6_SERVERS]
            logger.info(f"✅ 使用默认IPv6服务器列表: {len(self._ipv6_servers)} 个")

    def get_ipv4_servers(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取IPv4服务器列表

        Args:
            limit: 返回数量限制

        Returns:
            服务器列表
        """
        # 🔧 修复：如果缓存需要更新，在首次使用时触发测速（非阻塞，使用后台线程）
        if getattr(self, "_cache_needs_update", False):
            self._ensure_server_cache_async()

        # 按延迟排序
        sorted_servers = sorted(
            [s for s in self._ipv4_servers if s.available], key=lambda s: s.ping_time
        )

        # 转换为字典（包含max_connections信息）
        return [
            {"ip": s.ip, "port": s.port, "name": s.name, "max_connections": s.max_connections}
            for s in sorted_servers[:limit]
        ]

    def get_ipv6_servers(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取IPv6服务器列表

        Args:
            limit: 返回数量限制

        Returns:
            服务器列表
        """
        # 🔧 修复：如果缓存需要更新，在首次使用时触发测速（非阻塞，使用后台线程）
        if getattr(self, "_cache_needs_update", False):
            self._ensure_server_cache_async()

        # 按延迟排序
        sorted_servers = sorted(
            [s for s in self._ipv6_servers if s.available], key=lambda s: s.ping_time
        )

        # 转换为字典（包含max_connections信息）
        return [
            {"ip": s.ip, "port": s.port, "name": s.name, "max_connections": s.max_connections}
            for s in sorted_servers[:limit]
        ]

    def _ensure_server_cache_async(self):
        """异步确保服务器池缓存存在且有效（使用后台线程，不阻塞）"""
        if not getattr(self, "_cache_needs_update", False):
            return

        # 标记正在更新，避免重复触发
        self._cache_needs_update = False

        def update_cache():
            """在后台线程中更新缓存"""
            try:
                logger.debug("🔧 服务器池缓存不存在或已过时，开始后台自动测速生成...")
                self.test_servers()  # 这会在test_servers()方法结束时自动保存缓存
                logger.info("✅ 服务器池缓存已自动生成")
            except Exception as e:
                logger.warning(f"⚠️ 自动生成服务器池缓存失败: {e}", extra={"log_type": "SYSTEM"})
                # 失败后重新标记需要更新
                self._cache_needs_update = True

        # 使用后台线程执行，不阻塞调用
        thread = threading.Thread(target=update_cache, daemon=True, name="ServerCacheUpdate")
        thread.start()

    def test_servers(self, max_workers: Optional[int] = None, keep_pool: bool = False):
        """测试所有服务器

        完全委托给 tdx_asyncio.ServerTester 进行服务器测速。

        Args:
            max_workers: 最大并发协程数，如果为None则根据服务器数量自动设置（默认最多100）
            keep_pool: 是否保持连接池（已废弃，保留用于向后兼容）

        Note:
            keep_pool 参数已废弃，因为 ServerTester 内部管理连接池，无需外部管理。
        """
        scenario = "manual_speedtest" if not keep_pool else "startup_speedtest"
        logger.debug(
            f"🔍 开始测试服务器（委托ServerTester）... keep_pool={keep_pool}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        # 委托至tdx_asyncio.ServerTester（统一实现，简化逻辑）
        try:
            all_servers = self._ipv4_servers + self._ipv6_servers
            ipv4_count = len(self._ipv4_servers)
            ipv6_count = len(self._ipv6_servers)
            logger.debug(
                f"🔍 服务器统计: IPv4={ipv4_count}, IPv6={ipv6_count}, 总计={len(all_servers)}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 动态并发数（旧参数max_workers复用为协程并发数）
            if max_workers is None:
                max_workers = min(len(all_servers), 100)
            logger.debug(
                f"🎯 并发协程数设置: {max_workers}",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            servers = [(s.ip, s.port) for s in all_servers]

            async def _run_speedtest():
                tester = ServerTester(timeout=3.0, max_concurrent=max_workers)
                return await tester.batch_test_servers(
                    servers, max_concurrent=max_workers, timeout=3.0
                )

            test_start_time = time.time()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(_run_speedtest())
            finally:
                loop.close()

            # 更新结果
            for s in all_servers:
                key = (s.ip, s.port)
                if key in results:
                    s.ping_time = results[key] * 1000.0  # 秒→毫秒
                    s.available = True
                else:
                    s.ping_time = 9999.0
                    s.available = False
                s.last_test = datetime.now()

            # 汇总统计
            test_elapsed = time.time() - test_start_time
            available_count = sum(1 for s in all_servers if s.available)
            ipv4_available = sum(1 for s in self._ipv4_servers if s.available)
            ipv6_available = sum(1 for s in self._ipv6_servers if s.available)

            logger.info(
                f"✅ 服务器测速完成: 可用={available_count}/{len(all_servers)}, "
                f"IPv4可用={ipv4_available}/{ipv4_count}, IPv6可用={ipv6_available}/{ipv6_count}, "
                f"耗时={test_elapsed:.2f}s",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            if available_count == 0:
                logger.warning(
                    "⚠️ 所有服务器测速失败，没有可用服务器！",
                    extra={"log_type": "ALERT", "scenario": scenario},
                )

            # 保存缓存（沿用原逻辑）
            logger.debug(
                "[SPEEDTEST-LOADBALANCER] 开始保存测速结果到缓存",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            cache_save_start = time.time()
            try:
                ipv4_data = [
                    {
                        "ip": s.ip,
                        "port": s.port,
                        "name": s.name,
                        "max_connections": s.max_connections,
                        "ping_time": s.ping_time,
                        "available": s.available,
                        "last_test": s.last_test.isoformat() if s.last_test else None,
                    }
                    for s in self._ipv4_servers
                ]
                ipv6_data = [
                    {
                        "ip": s.ip,
                        "port": s.port,
                        "name": s.name,
                        "max_connections": s.max_connections,
                        "ping_time": s.ping_time,
                        "available": s.available,
                        "last_test": s.last_test.isoformat() if s.last_test else None,
                    }
                    for s in self._ipv6_servers
                ]

                cache_data = {"ipv4_servers": ipv4_data, "ipv6_servers": ipv6_data}
                from .core_engine import DailyCacheManager

                success = DailyCacheManager.save_with_date(cache_data, self._cache_file)
                cache_save_elapsed = time.time() - cache_save_start
                if success:
                    logger.info(
                        f"✅ 服务器池缓存已保存: IPv4={len(ipv4_data)}, IPv6={len(ipv6_data)}, 用时={cache_save_elapsed:.2f}s",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                else:
                    logger.warning(
                        "⚠️ 保存服务器池缓存失败", extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
            except Exception as e:
                logger.error(
                    f"❌ 保存服务器池缓存异常: {e}",
                    exc_info=True,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )

            # 委托模式完成，直接返回
            return
        except Exception as e:
            logger.error(
                f"❌ 服务器测速异常（委托ServerTester）: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            # 异常时不再回退到旧逻辑，直接抛出异常
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取服务器池统计信息

        Returns:
            统计信息字典
        """
        available_ipv4 = sum(1 for s in self._ipv4_servers if s.available)
        available_ipv6 = sum(1 for s in self._ipv6_servers if s.available)
        total_ipv4 = len(self._ipv4_servers)
        total_ipv6 = len(self._ipv6_servers)

        return {
            "available": available_ipv4 + available_ipv6,
            "total": total_ipv4 + total_ipv6,
            "ipv4_available": available_ipv4,
            "ipv4_total": total_ipv4,
            "ipv6_available": available_ipv6,
            "ipv6_total": total_ipv6,
            "running": True,  # 服务器池管理器始终运行
        }

    def is_running(self) -> bool:
        """检查服务器池管理器是否运行中

        Returns:
            始终返回True（服务器池管理器始终运行）
        """
        return True

    def stop(self) -> None:
        """停止服务器池管理器（向后兼容方法，实际无操作）"""
        logger.debug("服务器池管理器stop()被调用（无实际操作）")

    def close_connection_pool(self) -> None:
        """关闭连接池（在步骤8完成后调用）

        用于启动时的连接池复用机制：
        - 步骤1测速时保持连接池（keep_pool=True）
        - 步骤2-7复用连接池
        - 步骤8完成后关闭连接池
        """
        if self._connection_pool:
            try:
                logger.info("🔧 正在关闭服务器池连接池...", extra={"log_type": "SYSTEM"})
                self._connection_pool.shutdown(wait=True)
                self._connection_pool = None
                self._pool_mode = "auto"
                logger.info("✅ 服务器池连接池已关闭", extra={"log_type": "SYSTEM"})
            except Exception as e:
                logger.warning(
                    f"⚠️ 关闭连接池时发生异常: {e}", exc_info=True, extra={"log_type": "ALERT"}
                )
                self._connection_pool = None
                self._pool_mode = "auto"
        else:
            logger.debug("连接池已经关闭或未创建，无需操作", extra={"log_type": "SYSTEM"})

    def get_or_create_retry_pool(
        self, keep_pool: bool = False, max_connections: Optional[int] = None
    ) -> "RetryConnectionPool":
        """获取或创建RetryConnectionPool（封装连接池复用机制）

        参考ProcessPoolExecutor的keep_pool机制：
        - keep_pool=True: 创建并保持连接池，供后续步骤复用
        - keep_pool=False: 创建临时连接池，使用后自动关闭

        Args:
            keep_pool: 是否保持连接池（True=不关闭，False=立即关闭）
            max_connections: 最大连接数（None=自动计算，每个服务器一个连接；指定值=限制总连接数）

        Returns:
            RetryConnectionPool实例
        """
        scenario = "manual_task" if not keep_pool else "startup_task"

        # 如果已存在且需要保持，直接返回
        if keep_pool and self._retry_connection_pool is not None:
            logger.debug(
                "[RETRY-POOL] 复用已存在的RetryConnectionPool（启动模式）",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return self._retry_connection_pool

        # 创建新的连接池
        from backend.infrastructure.tdx_asyncio.retry_connection_pool import RetryConnectionPool

        logger.debug(
            f"[RETRY-POOL] 开始创建RetryConnectionPool: keep_pool={keep_pool}, max_connections={max_connections}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )

        retry_pool = RetryConnectionPool(
            server_pool_manager=self,
            phase1_max_attempts=10,
            phase2_max_attempts=5,
            connection_timeout=5.0,
            enable_connection_pool=True,
            max_connections=max_connections,
        )

        if keep_pool:
            # 保持连接池供后续步骤复用
            self._retry_connection_pool = retry_pool
            max_conn_str = str(max_connections) if max_connections else "自动（每个服务器一个连接）"
            logger.info(
                f"✅ RetryConnectionPool已创建并保留（启动模式，max_connections={max_conn_str}），供后续步骤复用",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
        else:
            logger.debug(
                "[RETRY-POOL] RetryConnectionPool已创建（临时模式）",
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        return retry_pool

    def close_retry_connection_pool(self) -> None:
        """关闭RetryConnectionPool连接池（在步骤8完成后调用）

        用于启动时的连接池复用机制：
        - 步骤1测速时保持连接池（keep_pool=True）
        - 步骤2-7复用连接池
        - 步骤8完成后关闭连接池
        """
        if self._retry_connection_pool:
            try:
                import asyncio

                logger.info("🔧 正在关闭RetryConnectionPool连接池...", extra={"log_type": "SYSTEM"})

                # RetryConnectionPool的关闭需要异步执行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._retry_connection_pool.close_all())
                    self._retry_connection_pool = None
                    logger.info("✅ RetryConnectionPool连接池已关闭", extra={"log_type": "SYSTEM"})
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(
                    f"⚠️ 关闭RetryConnectionPool时发生异常: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT"},
                )
                self._retry_connection_pool = None
        else:
            logger.debug(
                "RetryConnectionPool已经关闭或未创建，无需操作", extra={"log_type": "SYSTEM"}
            )

    def _start_multiprocess(self) -> bool:
        """启动多进程测速（向后兼容方法）

        Returns:
            是否启动成功
        """
        try:
            self.test_servers()
            return True
        except Exception as e:
            logger.error(f"多进程测速失败: {e}", extra={"log_type": "SYSTEM"}, exc_info=True)
            return False

    def save_server_cache(self, ipv4_servers: List, ipv6_servers: List) -> None:
        """保存服务器缓存（向后兼容方法）

        Args:
            ipv4_servers: IPv4服务器列表（可以是ServerInfo对象或字典）
            ipv6_servers: IPv6服务器列表（可以是ServerInfo对象或字典）
        """
        try:
            from .core_engine import DailyCacheManager

            # 🔧 修复：将服务器列表转换为可序列化格式
            def server_to_dict(server) -> dict:
                """将ServerInfo对象或字典转换为可序列化格式"""
                if isinstance(server, ServerInfo):
                    return {
                        "ip": server.ip,
                        "port": server.port,
                        "name": server.name,
                        "max_connections": server.max_connections,
                        "ping_time": server.ping_time,
                        "available": server.available,
                        "last_test": server.last_test.isoformat() if server.last_test else None,
                    }
                elif isinstance(server, dict):
                    # 已经是字典，确保last_test是字符串格式，包含max_connections
                    result = dict(server)
                    if (
                        "last_test" in result
                        and result["last_test"]
                        and not isinstance(result["last_test"], str)
                    ):
                        result["last_test"] = (
                            result["last_test"].isoformat()
                            if hasattr(result["last_test"], "isoformat")
                            else None
                        )
                    # 确保包含max_connections字段
                    if "max_connections" not in result:
                        result["max_connections"] = 20  # 默认值
                    return result
                else:
                    # 未知格式，尝试转换
                    return {
                        "ip": getattr(server, "ip", ""),
                        "port": getattr(server, "port", 7709),
                        "name": getattr(server, "name", ""),
                        "max_connections": getattr(server, "max_connections", 20),
                        "ping_time": getattr(server, "ping_time", 9999.0),
                        "available": getattr(server, "available", False),
                        "last_test": getattr(server, "last_test", None),
                    }

            ipv4_data = [server_to_dict(s) for s in ipv4_servers]
            ipv6_data = [server_to_dict(s) for s in ipv6_servers]

            cache_data = {"ipv4_servers": ipv4_data, "ipv6_servers": ipv6_data}

            # 🔧 使用 DailyCacheManager 保存缓存（带日期验证）
            success = DailyCacheManager.save_with_date(cache_data, self._cache_file)
            if success:
                logger.info(f"✅ 服务器池缓存已保存: IPv4={len(ipv4_data)}, IPv6={len(ipv6_data)}")
            else:
                logger.warning("⚠️ 保存服务器池缓存失败", extra={"log_type": "SYSTEM"})
        except Exception as e:
            logger.error(
                f"❌ 保存服务器池缓存异常: {e}", exc_info=True, extra={"log_type": "SYSTEM"}
            )

    def _push_server_status_event(self) -> None:
        """推送服务器状态事件（向后兼容方法）"""
        logger.debug("_push_server_status_event()被调用（当前实现暂无事件推送）")

    def get_top_30_percent_ipv4_servers(
        self, shuffle: bool = True, exclude: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """获取IPv4最快前30%服务器（按ping_time排序）

        Args:
            shuffle: 是否打乱顺序
            exclude: 排除的服务器列表（格式：["ip:port", ...]）

        Returns:
            服务器列表，格式：[{"ip": ..., "port": ..., "name": ..., "ping_time": ...}]
        """
        import random

        # 过滤可用服务器
        available_servers = [
            s
            for s in self._ipv4_servers
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude)
        ]

        if not available_servers:
            logger.warning("⚠️ 无可用IPv4服务器", extra={"log_type": "SYSTEM"})
            return []

        # 按ping_time排序
        sorted_servers = sorted(available_servers, key=lambda s: s.ping_time)

        # 取前30%
        top_count = max(1, int(len(sorted_servers) * 0.3))
        top_servers = sorted_servers[:top_count]

        # 转换为字典格式（包含max_connections信息）
        result = [
            {
                "ip": s.ip,
                "port": s.port,
                "name": s.name,
                "ping_time": s.ping_time,
                "max_connections": s.max_connections,
            }
            for s in top_servers
        ]

        # 打乱顺序（如果启用）
        if shuffle:
            random.shuffle(result)

        logger.debug(
            f"[SERVER-POOL] 获取IPv4最快30%服务器: 总数={len(available_servers)}, "
            f"前30%={top_count}, 返回={len(result)}",
            extra={"log_type": "SYSTEM"},
        )

        return result

    def get_mixed_servers(
        self, shuffle: bool = True, exclude: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """获取IPv4+IPv6混合服务器池（乱序）

        Args:
            shuffle: 是否打乱顺序
            exclude: 排除的服务器列表（格式：["ip:port", ...]）

        Returns:
            服务器列表，格式：[{"ip": ..., "port": ..., "name": ..., "ping_time": ...}]
        """
        import random

        # 合并IPv4和IPv6服务器
        all_servers = []

        # 添加IPv4服务器（包含max_connections信息）
        for s in self._ipv4_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                all_servers.append(
                    {
                        "ip": s.ip,
                        "port": s.port,
                        "name": s.name,
                        "ping_time": s.ping_time,
                        "max_connections": s.max_connections,
                    }
                )

        # 添加IPv6服务器（包含max_connections信息）
        for s in self._ipv6_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                all_servers.append(
                    {
                        "ip": s.ip,
                        "port": s.port,
                        "name": s.name,
                        "ping_time": s.ping_time,
                        "max_connections": s.max_connections,
                    }
                )

        if not all_servers:
            logger.warning("⚠️ 无可用混合服务器（IPv4+IPv6）", extra={"log_type": "SYSTEM"})
            return []

        # 打乱顺序（如果启用）
        if shuffle:
            random.shuffle(all_servers)

        logger.debug(
            f"[SERVER-POOL] 获取混合服务器池: IPv4={len([s for s in self._ipv4_servers if s.available])}, "
            f"IPv6={len([s for s in self._ipv6_servers if s.available])}, "
            f"返回={len(all_servers)}",
            extra={"log_type": "SYSTEM"},
        )

        return all_servers

    def calculate_weighted_avg_max_connections(
        self, exclude: Optional[List[str]] = None
    ) -> Tuple[float, int]:
        """计算可用服务器的max_connections加权平均

        Args:
            exclude: 排除的服务器列表（格式：["ip:port", ...]）

        Returns:
            (加权平均值, 可用服务器数量)
        """
        # 获取所有可用服务器
        available_servers = []

        # 添加IPv4服务器
        for s in self._ipv4_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                available_servers.append(s)

        # 添加IPv6服务器
        for s in self._ipv6_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                available_servers.append(s)

        if not available_servers:
            logger.warning(
                "⚠️ 无可用服务器，使用默认max_connections=20", extra={"log_type": "SYSTEM"}
            )
            return 20.0, 0

        # 计算加权平均（所有服务器等权重，即简单平均）
        total_max_conn = sum(s.max_connections for s in available_servers)
        avg_max_conn = total_max_conn / len(available_servers)

        logger.debug(
            f"[SERVER-POOL] 计算加权平均max_connections: "
            f"可用服务器={len(available_servers)}, 平均={avg_max_conn:.2f}",
            extra={"log_type": "SYSTEM"},
        )

        return avg_max_conn, len(available_servers)

    def calculate_total_max_connections(self, exclude: Optional[List[str]] = None) -> int:
        """计算所有活跃服务器的max_connections总和（准确的最大并发数限制）

        Args:
            exclude: 排除的服务器列表（格式：["ip:port", ...]）

        Returns:
            所有活跃服务器的max_connections累加值
        """
        # 获取所有可用服务器
        available_servers = []

        # 添加IPv4服务器
        for s in self._ipv4_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                available_servers.append(s)

        # 添加IPv6服务器
        for s in self._ipv6_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                available_servers.append(s)

        if not available_servers:
            logger.warning(
                "⚠️ 无可用服务器，使用默认max_connections=20", extra={"log_type": "SYSTEM"}
            )
            return 20

        # 直接累加所有服务器的max_connections
        total_max_connections = sum(s.max_connections for s in available_servers)

        logger.debug(
            f"[SERVER-POOL] 计算总最大连接数: "
            f"可用服务器={len(available_servers)}, 总max_connections={total_max_connections}",
            extra={"log_type": "SYSTEM"},
        )

        return total_max_connections

    def allocate_connections_intelligently(
        self, total_connections: int, exclude: Optional[List[str]] = None
    ) -> List[Tuple[str, int, int]]:
        """
        智能连接分配策略

        分配优先级：
        1. 第一阶段：每个服务器至少1个连接（负载均衡）
        2. 第二阶段：优先使用max_connections为19和20的服务器，平均分配负载
        3. 第三阶段：当19和20的服务器达到上限后，再给其他服务器加负载

        Args:
            total_connections: 总连接数需求
            exclude: 排除的服务器列表（格式：["ip:port", ...]）

        Returns:
            连接分配列表，格式：[(ip, port, connections_count), ...]
        """
        # 获取所有可用服务器
        available_servers = []

        # 添加IPv4服务器
        for s in self._ipv4_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                available_servers.append(s)

        # 添加IPv6服务器
        for s in self._ipv6_servers:
            if s.available and (exclude is None or f"{s.ip}:{s.port}" not in exclude):
                available_servers.append(s)

        if not available_servers:
            logger.warning("⚠️ 无可用服务器，无法分配连接", extra={"log_type": "SYSTEM"})
            return []

        # 按max_connections分组
        servers_high_capacity = []  # max_connections为19或20的服务器
        servers_other = []  # 其他服务器

        for s in available_servers:
            if s.max_connections in [19, 20]:
                servers_high_capacity.append(s)
            else:
                servers_other.append(s)

        # 初始化每个服务器的连接数为0
        connection_map: Dict[str, Tuple[str, int, int]] = {}
        for s in available_servers:
            key = f"{s.ip}:{s.port}"
            connection_map[key] = (s.ip, s.port, 0)

        remaining_connections = total_connections

        # 第一阶段：每个服务器至少1个连接（负载均衡）
        for s in available_servers:
            if remaining_connections <= 0:
                break
            key = f"{s.ip}:{s.port}"
            ip, port, current = connection_map[key]
            connection_map[key] = (ip, port, current + 1)
            remaining_connections -= 1

        if remaining_connections <= 0:
            # 只够第一阶段，返回结果
            return [conn for conn in connection_map.values() if conn[2] > 0]

        # 第二阶段：优先分配给max_connections为19和20的服务器
        # 使用轮询方式平均分配
        high_capacity_servers = servers_high_capacity.copy()

        while remaining_connections > 0 and high_capacity_servers:
            # 找出还没有达到max_connections的服务器
            available_high = [
                s
                for s in high_capacity_servers
                if connection_map[f"{s.ip}:{s.port}"][2] < s.max_connections
            ]

            if not available_high:
                # 所有19和20的服务器都达到上限了
                break

            # 轮询分配：每次给每个可用服务器分配1个连接
            for s in available_high:
                if remaining_connections <= 0:
                    break
                key = f"{s.ip}:{s.port}"
                ip, port, current = connection_map[key]
                connection_map[key] = (ip, port, current + 1)
                remaining_connections -= 1

        if remaining_connections <= 0:
            # 只够前两个阶段，返回结果
            return [conn for conn in connection_map.values() if conn[2] > 0]

        # 第三阶段：分配给其他服务器
        other_servers = servers_other.copy()

        while remaining_connections > 0 and other_servers:
            # 找出还没有达到max_connections的服务器
            available_other = [
                s
                for s in other_servers
                if connection_map[f"{s.ip}:{s.port}"][2] < s.max_connections
            ]

            if not available_other:
                # 所有服务器都达到上限了
                break

            # 轮询分配：每次给每个可用服务器分配1个连接
            for s in available_other:
                if remaining_connections <= 0:
                    break
                key = f"{s.ip}:{s.port}"
                ip, port, current = connection_map[key]
                connection_map[key] = (ip, port, current + 1)
                remaining_connections -= 1

        # 统计分配结果
        result = [conn for conn in connection_map.values() if conn[2] > 0]
        total_allocated = sum(conn[2] for conn in result)
        high_cap_allocated = sum(
            conn[2]
            for conn in result
            if any(
                s.ip == conn[0] and s.port == conn[1] and s.max_connections in [19, 20]
                for s in servers_high_capacity
            )
        )

        logger.debug(
            f"[SERVER-POOL] 智能连接分配完成: "
            f"总需求={total_connections}, 已分配={total_allocated}, "
            f"高容量服务器(19/20)分配={high_cap_allocated}, "
            f"剩余需求={remaining_connections}, 涉及服务器={len(result)}",
            extra={"log_type": "SYSTEM"},
        )

        if remaining_connections > 0:
            logger.warning(
                f"⚠️ 连接分配未完全满足: 剩余需求={remaining_connections}个连接",
                extra={"log_type": "SYSTEM"},
            )

        return result


# ==============================================================================
# Part 4: 负载均衡器（LoadBalancer）
# ==============================================================================


class LoadBalancer:
    """负载均衡器 v3.2

    智能负载均衡，核心特性：
    - 木桶理论：只看最短的那块板
    - 动态并发调整（0.3x-1.6x缩放）
    - 智能防抖机制（1秒/3秒）
    - 任务类型区分（v3.1新增）
    - 队列压力监控（v3.1新增）
    - 智能连接分配策略（v3.2新增）：
      * 每个服务器可创建多个连接（受限于max_connections字段）
      * 基于加权平均max_connections计算总协程限制
      * 突破单服务器单连接限制，性能提升约20倍
    """

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """初始化负载均衡器

        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager or ConfigManager()
        self.resource_monitor = ResourceMonitor()
        self.config_calculator = DynamicConfigCalculator(self.resource_monitor)
        self.server_pool = ServerPoolManager(config_manager)

        # v3.1新增：队列压力监控器
        self.queue_monitor = QueuePressureMonitor()

        # v3.1新增：任务策略注册表
        self.task_strategies = TaskStrategyRegistry()

        # 防抖控制
        self._last_adjustment_time = 0
        self._adjustment_history = []  # 记录最近的调整模式
        self._base_interval = 1.0  # 基础调整间隔（秒）
        self._pattern_interval = 3.0  # 特定模式调整间隔（秒）

        # 缓存配置
        self._last_config = {}

        logger.info("✅ 负载均衡器已初始化 (v3.2 - 支持智能连接分配策略)")

    def get_optimal_config(
        self,
        task: Optional[TaskConfig] = None,
        task_type: str = "download",
        queue_metrics: Optional[QueueMetrics] = None,
        available_servers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取最优配置（带防抖）

        Args:
            task: 任务配置（v3.1新增，为空时兼容旧API）
            task_type: 任务类型字符串（向后兼容）
            queue_metrics: 队列指标（v3.1新增）
            available_servers: 可用服务器数量（已废弃，不再使用，改为直接累加所有服务器max_connections）

        Returns:
            最优配置
        """
        current_time = time.time()

        # 检查防抖间隔
        interval = self._get_debounce_interval()
        if current_time - self._last_adjustment_time < interval:
            # 未达到调整间隔，使用缓存配置
            return self._get_cached_config()

        # v3.1: 支持任务类型和队列压力
        if task is not None:
            # 新API：使用TaskConfig
            config = self._calculate_with_task_config(task, queue_metrics, available_servers)
        else:
            # 旧API：兼容性支持
            config = self.config_calculator.calculate(task_type)

        # 更新调整历史
        self._update_adjustment_history(config)
        self._last_adjustment_time = current_time

        return config

    def _calculate_with_task_config(
        self,
        task: TaskConfig,
        queue_metrics: Optional[QueueMetrics] = None,
        available_servers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """基于任务配置计算最优配置（v3.1新增）

        Args:
            task: 任务配置
            queue_metrics: 队列指标
            available_servers: 可用服务器数量（已废弃，不再使用，改为直接累加所有服务器max_connections）

        Returns:
            最优配置
        """
        # 1. 资源监控（木桶理论）
        resource_metrics = self.resource_monitor.get_metrics()

        # 2. 队列压力监控
        if queue_metrics:
            self.queue_monitor.record_metrics(queue_metrics)
            queue_pressure_factor = self.queue_monitor.get_adjustment_factor()
            pressure_level = self.queue_monitor.get_pressure_level()
        else:
            queue_pressure_factor = 1.0
            pressure_level = "normal"

        # 3. 获取任务策略
        strategy = self.task_strategies.get_strategy(task.category)

        # 4. 计算基准配置（基于资源指标调整）
        bottleneck_value = getattr(
            resource_metrics, f"{resource_metrics.bottleneck.lower()}_percent", 50.0
        )

        # 瓶颈资源使用率越高，缩放因子越小
        if bottleneck_value > 80:
            resource_scale = 0.3
        elif bottleneck_value > 60:
            resource_scale = 0.6
        elif bottleneck_value > 40:
            resource_scale = 1.0
        else:
            resource_scale = 1.6

        # 5. 应用资源缩放
        processes = max(1, int(strategy["base_processes"] * resource_scale))
        coroutines_per_process = max(
            10, int(strategy["base_coroutines_per_process"] * resource_scale)
        )

        # 6. 应用队列压力调整
        processes = max(1, int(processes * queue_pressure_factor))
        coroutines_per_process = max(10, int(coroutines_per_process * queue_pressure_factor))

        # 7. 🎯 应用服务器连接数约束（直接累加所有活跃服务器的max_connections）
        server_constrained = False
        original_coroutines = coroutines_per_process

        # 直接累加所有活跃服务器的max_connections
        max_total_coroutines = self.server_pool.calculate_total_max_connections()

        # 获取服务器数量用于日志
        stats = self.server_pool.get_stats()
        num_available_servers = stats.get("available", 0)

        if num_available_servers > 0 and max_total_coroutines > 0:
            # 总并发数 = 进程数 × 每进程协程数
            total_concurrency = processes * coroutines_per_process

            # 如果总并发数超过最大协程限制，进行约束
            if total_concurrency > max_total_coroutines:
                server_constrained = True
                # 优先调整协程数，保持进程数不变（避免进程创建开销）
                coroutines_per_process = max(1, max_total_coroutines // processes)

                # 如果调整后的协程数太小（<3），则减少进程数
                if coroutines_per_process < 3 and processes > 1:
                    processes = max(1, max_total_coroutines // 3)
                    coroutines_per_process = max(1, max_total_coroutines // processes)

                logger.debug(
                    f"[LOADBALANCER] 服务器连接数约束生效: "
                    f"可用服务器={num_available_servers}, "
                    f"最大总协程数={max_total_coroutines}（所有服务器max_connections累加）, "
                    f"原始并发={processes}×{original_coroutines}={processes*original_coroutines}, "
                    f"约束后并发={processes}×{coroutines_per_process}={processes*coroutines_per_process}"
                )
            else:
                logger.debug(
                    f"[LOADBALANCER] 服务器连接数约束未生效: "
                    f"可用服务器={num_available_servers}, "
                    f"最大总协程数={max_total_coroutines}（所有服务器max_connections累加）, "
                    f"当前总并发={total_concurrency}（未超过限制）"
                )

        # 8. 🎯 应用任务数量约束（总协程数 ≤ 任务数）
        task_constrained = False
        original_total_coroutines = processes * coroutines_per_process
        if task.total_count > 0:
            total_coroutines = processes * coroutines_per_process

            # 如果总协程数超过任务数，进行约束
            if total_coroutines > task.total_count:
                task_constrained = True
                # 优先调整协程数，保持进程数不变（避免进程创建开销）
                coroutines_per_process = max(1, task.total_count // processes)

                # 如果调整后的协程数太小（<3），则减少进程数
                if coroutines_per_process < 3 and processes > 1:
                    processes = max(1, task.total_count // 3)
                    coroutines_per_process = max(1, task.total_count // processes)

                logger.debug(
                    f"[LOADBALANCER] 任务数量约束生效: 任务数={task.total_count}, "
                    f"原始总协程数={original_total_coroutines}, "
                    f"约束后总协程数={processes * coroutines_per_process}, "
                    f"进程={processes}, 每进程协程={coroutines_per_process}"
                )

        # 9. 构建配置
        config = {
            "processes": min(processes, strategy["max_processes"]),
            "coroutines_per_process": min(
                coroutines_per_process, strategy["max_coroutines_per_process"]
            ),
            "max_workers": min(processes, strategy["max_processes"]),  # 兼容旧API
            "coroutines_per_worker": min(
                coroutines_per_process, strategy["max_coroutines_per_process"]
            ),  # 兼容旧API
            # 诊断信息
            "task_category": task.category.value,
            "resource_bottleneck": resource_metrics.bottleneck,
            "resource_scale": resource_scale,
            "queue_pressure_level": pressure_level,
            "queue_pressure_factor": queue_pressure_factor,
            "pressure_score": int((1 - queue_pressure_factor) * 100),  # 0-100压力评分
            "available_servers": num_available_servers,
            "max_total_coroutines": max_total_coroutines,
            "server_constrained": server_constrained,
            "task_constrained": task_constrained,
            "task_count": task.total_count,
        }

        logger.debug(
            f"[LOADBALANCER] 动态配置 [{task.name}]: 进程={config['processes']}, "
            f"协程={config['coroutines_per_process']}, 总并发={config['processes']*config['coroutines_per_process']}, "
            f"任务数={task.total_count}, "
            f"可用服务器={num_available_servers}, "
            f"最大总协程数={max_total_coroutines}, "
            f"服务器约束={'生效' if server_constrained else '未生效'}, "
            f"任务约束={'生效' if task_constrained else '未生效'}, "
            f"瓶颈={resource_metrics.bottleneck}({bottleneck_value:.1f}%), "
            f"队列压力={pressure_level}",
            extra={"log_type": "SYSTEM", "scenario": "refresh_symbol_list"},
        )

        return config

    def _get_debounce_interval(self) -> float:
        """获取防抖间隔

        Returns:
            防抖间隔（秒）
        """
        # 检查是否存在特定模式（increase→decrease→increase 或相反）
        if len(self._adjustment_history) >= 3:
            last_three = self._adjustment_history[-3:]
            if self._is_oscillating_pattern(last_three):
                return self._pattern_interval

        return self._base_interval

    def _is_oscillating_pattern(self, history: List[str]) -> bool:
        """检查是否为振荡模式

        Args:
            history: 调整历史（最近3次）

        Returns:
            是否为振荡模式
        """
        if len(history) != 3:
            return False

        # 检查 increase→decrease→increase
        if history[0] == "increase" and history[1] == "decrease" and history[2] == "increase":
            return True

        # 检查 decrease→increase→decrease
        if history[0] == "decrease" and history[1] == "increase" and history[2] == "decrease":
            return True

        return False

    def _update_adjustment_history(self, config: Dict[str, Any]):
        """更新调整历史

        Args:
            config: 新配置
        """
        # 简化：只记录workers/processes的变化趋势
        if hasattr(self, "_last_config") and self._last_config:
            # 兼容新旧API
            current_workers = config.get("processes", config.get("max_workers", 0))
            last_workers = self._last_config.get(
                "processes", self._last_config.get("max_workers", 0)
            )

            if current_workers > last_workers:
                self._adjustment_history.append("increase")
            elif current_workers < last_workers:
                self._adjustment_history.append("decrease")
            else:
                self._adjustment_history.append("stable")

            # 只保留最近10次记录
            if len(self._adjustment_history) > 10:
                self._adjustment_history.pop(0)

        self._last_config = config

    def _get_cached_config(self) -> Dict[str, Any]:
        """获取缓存配置

        Returns:
            缓存配置
        """
        if hasattr(self, "_last_config"):
            return self._last_config
        else:
            return DynamicConfigCalculator.BASE_CONFIG.copy()

    def get_servers(self, use_two_phase: bool = True) -> Dict[str, List[Dict]]:
        """获取服务器列表

        Args:
            use_two_phase: 是否启用两段式下载

        Returns:
            服务器字典 {"ipv4": [...], "ipv6": [...]}
        """
        servers = {"ipv4": self.server_pool.get_ipv4_servers(), "ipv6": []}

        if use_two_phase:
            servers["ipv6"] = self.server_pool.get_ipv6_servers()

        return servers


# ==============================================================================
# 导出API（向后兼容）
# ==============================================================================

__all__ = [
    # 任务类型系统 (v3.1)
    "TaskCategory",
    "TaskConfig",
    "QueueMetrics",
    "QueuePressureMonitor",
    "TaskStrategyRegistry",
    # 资源监控
    "ResourceMetrics",
    "ResourceMonitor",
    # 配置计算
    "DynamicConfigCalculator",
    # 服务器池
    "ServerInfo",
    "ServerPoolManager",
    # 负载均衡
    "LoadBalancer",
]

# ==============================================================================
# 全局实例（向后兼容）
# ==============================================================================

# 创建全局服务器池管理器实例（向后兼容旧代码）
_server_pool_manager_instance: Optional[ServerPoolManager] = None


def get_server_pool_manager() -> ServerPoolManager:
    """获取全局服务器池管理器实例（单例模式）

    Returns:
        ServerPoolManager实例
    """
    global _server_pool_manager_instance
    if _server_pool_manager_instance is None:
        _server_pool_manager_instance = ServerPoolManager()
    return _server_pool_manager_instance


# 🔧 修复：删除模块级别的自动初始化，避免在阶段0触发测速
# 改为延迟初始化，只在需要时创建实例
# server_pool_manager = get_server_pool_manager()  # ❌ 已删除：违反单一事实原则
