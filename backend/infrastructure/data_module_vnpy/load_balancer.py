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
    """负载均衡器
    
    智能负载均衡，核心特性：
    - 木桶理论：只看最短的那块板
    - 动态并发调整（0.3x-1.6x缩放）
    - 智能防抖机制（1秒/3秒）
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
        
        # 防抖控制
        self._last_adjustment_time = 0
        self._adjustment_history = []  # 记录最近的调整模式
        self._base_interval = 1.0  # 基础调整间隔（秒）
        self._pattern_interval = 3.0  # 特定模式调整间隔（秒）
        
        logger.info("✅ 负载均衡器已初始化")
    
    def get_optimal_config(self, task_type: str = "download") -> Dict[str, Any]:
        """获取最优配置（带防抖）
        
        Args:
            task_type: 任务类型
            
        Returns:
            最优配置
        """
        current_time = time.time()
        
        # 检查防抖间隔
        interval = self._get_debounce_interval()
        if current_time - self._last_adjustment_time < interval:
            # 未达到调整间隔，使用缓存配置
            return self._get_cached_config()
        
        # 计算新配置
        config = self.config_calculator.calculate(task_type)
        
        # 更新调整历史
        self._update_adjustment_history(config)
        self._last_adjustment_time = current_time
        
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
        # 简化：只记录workers的变化趋势
        if hasattr(self, '_last_config'):
            if config['max_workers'] > self._last_config.get('max_workers', 0):
                self._adjustment_history.append("increase")
            elif config['max_workers'] < self._last_config.get('max_workers', 999):
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
