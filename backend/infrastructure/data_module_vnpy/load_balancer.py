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
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# 导入TDX异步API
from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

# 导入核心模块
from .core_engine import ConfigManager, DailyCacheManager

# ==================== 日志配置 ====================
logger = logging.getLogger("backend.data_module.loadbalancer")


# ==============================================================================
# Part 0: 任务类型系统（v3.1新增）
# ==============================================================================


class TaskCategory(str, Enum):
    """任务类别（轻量级枚举）"""
    NETWORK_DOWNLOAD = "network_download"    # K线下载（网络I/O密集）
    LOCAL_SCAN = "local_scan"                # 本地数据扫描（磁盘I/O密集）
    LOCAL_READ = "local_read"                # TDX数据读取（磁盘I/O密集）


@dataclass
class TaskConfig:
    """任务配置（简化版TaskMetrics）"""
    name: str                    # 任务名称
    category: TaskCategory       # 任务类别
    total_count: int             # 任务总数
    
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
    current_size: int          # 当前队列大小
    max_size: int              # 最大队列容量
    fill_rate: float           # 填充率（0-1）
    
    # 背压相关指标
    enqueue_lag_ms: float = 0.0      # 入队延迟（毫秒）
    dequeue_lag_ms: float = 0.0      # 出队延迟（毫秒）
    avg_task_time_ms: float = 0.0    # 平均任务耗时（毫秒）
    
    # 告警阈值
    HIGH_FILL_RATE = 0.8       # 80%填充率告警
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
        return cls._strategies.get(
            category, 
            cls._strategies[TaskCategory.NETWORK_DOWNLOAD]
        )


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
            "coroutines_per_worker": max(10, int(self.BASE_CONFIG["coroutines_per_worker"] * scale)),
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


class ServerPoolManager:
    """服务器池管理器
    
    TDX服务器测速、排序、热备管理：
    - 多进程测速
    - IPv4/IPv6分离
    - 两段式下载支持
    - 缓存机制（native_iocp集成）
    """
    
    # 默认服务器列表
    DEFAULT_IPV4_SERVERS = [
        {"ip": "119.147.212.81", "port": 7709, "name": "广东电信1"},
        {"ip": "113.105.73.88", "port": 7709, "name": "广东电信2"},
        {"ip": "113.105.73.86", "port": 7709, "name": "广东电信3"},
        {"ip": "120.79.60.82", "port": 7709, "name": "广东移动"},
        {"ip": "113.105.142.136", "port": 443, "name": "广东联通"},
    ]
    
    DEFAULT_IPV6_SERVERS = [
        {"ip": "2408:8256:3be:3880::1", "port": 7709, "name": "广东电信IPv6"},
    ]
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """初始化服务器池管理器
        
        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager or ConfigManager()
        
        # 服务器池
        self._ipv4_servers: List[ServerInfo] = []
        self._ipv6_servers: List[ServerInfo] = []
        
        # 缓存文件
        self._cache_file = Path("cache/server_pool.json")
        
        # 加载服务器
        self._load_servers()
        
        logger.info(
            f"✅ 服务器池管理器已初始化: "
            f"IPv4={len(self._ipv4_servers)}, IPv6={len(self._ipv6_servers)}"
        )
    
    def _load_servers(self):
        """加载服务器列表"""
        # 从配置加载
        try:
            ipv4_config = self.config_manager.get_config("tdx.servers.ipv4", [])
            ipv6_config = self.config_manager.get_config("tdx.servers.ipv6", [])
        except Exception:
            ipv4_config = []
            ipv6_config = []
        
        # 转换为ServerInfo
        if ipv4_config:
            self._ipv4_servers = [
                ServerInfo(**server) for server in ipv4_config
            ]
        else:
            self._ipv4_servers = [
                ServerInfo(**server) for server in self.DEFAULT_IPV4_SERVERS
            ]
        
        if ipv6_config:
            self._ipv6_servers = [
                ServerInfo(**server) for server in ipv6_config
            ]
        else:
            self._ipv6_servers = [
                ServerInfo(**server) for server in self.DEFAULT_IPV6_SERVERS
            ]
    
    def get_ipv4_servers(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取IPv4服务器列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            服务器列表
        """
        # 按延迟排序
        sorted_servers = sorted(
            [s for s in self._ipv4_servers if s.available],
            key=lambda s: s.ping_time
        )
        
        # 转换为字典
        return [
            {"ip": s.ip, "port": s.port, "name": s.name}
            for s in sorted_servers[:limit]
        ]
    
    def get_ipv6_servers(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取IPv6服务器列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            服务器列表
        """
        # 按延迟排序
        sorted_servers = sorted(
            [s for s in self._ipv6_servers if s.available],
            key=lambda s: s.ping_time
        )
        
        # 转换为字典
        return [
            {"ip": s.ip, "port": s.port, "name": s.name}
            for s in sorted_servers[:limit]
        ]
    
    def test_servers(self, max_workers: int = 4):
        """测试所有服务器（多进程）
        
        Args:
            max_workers: 最大进程数
        """
        logger.info("🔍 开始测试服务器...")
        
        all_servers = self._ipv4_servers + self._ipv6_servers
        
        # 使用进程池测试
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_test_single_server, server.ip, server.port): server
                for server in all_servers
            }
            
            for future in as_completed(futures):
                server = futures[future]
                try:
                    ping_time, available = future.result()
                    server.ping_time = ping_time
                    server.available = available
                    server.last_test = datetime.now()
                    
                    if available:
                        logger.info(f"✅ {server.name} ({server.ip}): {ping_time:.0f}ms")
                    else:
                        logger.warning(f"❌ {server.name} ({server.ip}): 不可用")
                except Exception as e:
                    logger.warning(f"⚠️ 测试失败 {server.name}: {e}")
                    server.available = False
        
        logger.info("✅ 服务器测试完成")


def _test_single_server(ip: str, port: int) -> Tuple[float, bool]:
    """测试单个服务器（Worker函数）
    
    Args:
        ip: 服务器IP
        port: 服务器端口
        
    Returns:
        (延迟, 是否可用)
    """
    try:
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 测试连接
            api = AsyncTdxHq_API()
            start_time = time.time()
            
            connected = loop.run_until_complete(
                asyncio.wait_for(api.connect(ip, port), timeout=5.0)
            )
            
            if connected:
                ping_time = (time.time() - start_time) * 1000  # 转换为毫秒
                loop.run_until_complete(api.disconnect())
                return ping_time, True
            else:
                return 9999.0, False
        finally:
            loop.close()
    except Exception as e:
        logger.debug(f"测试服务器失败 {ip}:{port}, {e}")
        return 9999.0, False


# ==============================================================================
# Part 4: 负载均衡器（LoadBalancer）
# ==============================================================================


class LoadBalancer:
    """负载均衡器 v3.1
    
    智能负载均衡，核心特性：
    - 木桶理论：只看最短的那块板
    - 动态并发调整（0.3x-1.6x缩放）
    - 智能防抖机制（1秒/3秒）
    - 任务类型区分（v3.1新增）
    - 队列压力监控（v3.1新增）
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
        
        logger.info("✅ 负载均衡器已初始化 (v3.1 - 支持任务类型和队列压力)")
    
    def get_optimal_config(
        self, 
        task: Optional[TaskConfig] = None,
        task_type: str = "download",
        queue_metrics: Optional[QueueMetrics] = None
    ) -> Dict[str, Any]:
        """获取最优配置（带防抖）
        
        Args:
            task: 任务配置（v3.1新增，为空时兼容旧API）
            task_type: 任务类型字符串（向后兼容）
            queue_metrics: 队列指标（v3.1新增）
            
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
            config = self._calculate_with_task_config(task, queue_metrics)
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
        queue_metrics: Optional[QueueMetrics] = None
    ) -> Dict[str, Any]:
        """基于任务配置计算最优配置（v3.1新增）
        
        Args:
            task: 任务配置
            queue_metrics: 队列指标
            
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
            resource_metrics, 
            f"{resource_metrics.bottleneck.lower()}_percent", 
            50.0
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
        processes = max(
            1, 
            int(strategy["base_processes"] * resource_scale)
        )
        coroutines_per_process = max(
            10, 
            int(strategy["base_coroutines_per_process"] * resource_scale)
        )
        
        # 6. 应用队列压力调整
        processes = max(1, int(processes * queue_pressure_factor))
        coroutines_per_process = max(
            10, 
            int(coroutines_per_process * queue_pressure_factor)
        )
        
        # 7. 构建配置
        config = {
            "processes": min(processes, strategy["max_processes"]),
            "coroutines_per_process": min(
                coroutines_per_process, 
                strategy["max_coroutines_per_process"]
            ),
            "max_workers": min(processes, strategy["max_processes"]),  # 兼容旧API
            "coroutines_per_worker": min(
                coroutines_per_process, 
                strategy["max_coroutines_per_process"]
            ),  # 兼容旧API
            
            # 诊断信息
            "task_category": task.category.value,
            "resource_bottleneck": resource_metrics.bottleneck,
            "resource_scale": resource_scale,
            "queue_pressure_level": pressure_level,
            "queue_pressure_factor": queue_pressure_factor,
            "pressure_score": int(
                (1 - queue_pressure_factor) * 100
            ),  # 0-100压力评分
        }
        
        logger.debug(
            f"动态配置 [{task.name}]: 进程={config['processes']}, "
            f"协程={config['coroutines_per_process']}, "
            f"瓶颈={resource_metrics.bottleneck}({bottleneck_value:.1f}%), "
            f"队列压力={pressure_level}, "
            f"压力评分={config['pressure_score']}/100"
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
        if hasattr(self, '_last_config') and self._last_config:
            # 兼容新旧API
            current_workers = config.get('processes', config.get('max_workers', 0))
            last_workers = self._last_config.get('processes', self._last_config.get('max_workers', 0))
            
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
        if hasattr(self, '_last_config'):
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
        servers = {
            "ipv4": self.server_pool.get_ipv4_servers(),
            "ipv6": []
        }
        
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
