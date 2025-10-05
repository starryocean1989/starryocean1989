# -*- coding: utf-8 -*-
"""
System VnPy包.

系统级功能包,提供VnPy生态系统无法覆盖的系统操作功能.
专门为系统管理服务提供底层支持.

核心功能模块:
- system_monitor: 系统资源监控
- file_operations: 文件系统操作
- process_manager: 进程生命周期管理
- network_utils: 网络工具集
- security_manager: 安全管理
- performance_optimizer: 性能优化
"""

from .file_operations import (
    DirectoryManager,
    FileManager,
    FilePermissionManager,
    batch_file_operations,
)
from .network_utils import (
    NetworkTester,
    PortScanner,
    SSLValidator,
    scan_ports,
    test_connectivity,
)
from .performance_optimizer import (
    CacheManager,
    ConcurrencyOptimizer,
    MemoryOptimizer,
    optimize_performance,
)
from .process_manager import (
    DaemonManager,
    ProcessManager,
    ServiceManager,
    get_process_info,
    manage_process_lifecycle,
)
from .security_manager import (
    AuditLogger,
    EncryptionManager,
    PermissionController,
    SecurityManager,
)
from .system_monitor import (
    HardwareMonitor,
    ResourceMonitor,
    SystemMonitor,
    get_resource_usage,
    get_system_info,
)

__all__ = [
    # 系统监控
    "SystemMonitor",
    "ResourceMonitor",
    "HardwareMonitor",
    "get_system_info",
    "get_resource_usage",

    # 文件操作
    "FileManager",
    "DirectoryManager",
    "FilePermissionManager",
    "batch_file_operations",

    # 进程管理
    "ProcessManager",
    "ServiceManager",
    "DaemonManager",
    "get_process_info",
    "manage_process_lifecycle",

    # 网络工具
    "NetworkTester",
    "PortScanner",
    "SSLValidator",
    "test_connectivity",
    "scan_ports",

    # 安全管理
    "SecurityManager",
    "PermissionController",
    "EncryptionManager",
    "AuditLogger",

    # 性能优化
    "CacheManager",
    "MemoryOptimizer",
    "ConcurrencyOptimizer",
    "optimize_performance",
]
