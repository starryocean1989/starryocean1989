"""
Framework Lifecycle - 生命周期管理
提供启动编排、进程管理、健康检查

原子来源（完全重构startup模块）:
- startup/orchestrator.py (完整重构)
- startup/context.py (完整重构)
- startup/stages/* (完整重构)
- startup/workers/* (完整重构)
- startup/processes/* (完整重构)
- startup/health/* (完整重构)

职责：应用生命周期管理，完全重构以消除循环依赖
"""

import asyncio
import contextlib
import logging
import multiprocessing
import os
import sys
import time
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import psutil
import socket

from backend.framework.foundation import (
    ConfigManager,
    EngineManager,
    ServiceStatus,
    get_service_registry,
    get_settings,
)
from backend.framework.runtime import get_logging_manager
from backend.infrastructure.system_vnpy.core_engine import CacheManager

logger = logging.getLogger("framework.lifecycle")


# ============================================================================
# Section 1: 启动编排 (行 1-200)
# ============================================================================

class StartupPhase(str, Enum):
    """启动阶段"""
    INIT = "init"
    CONFIG = "config"
    DATABASE = "database"
    ENGINE = "engine"
    SERVICES = "services"
    PROCESSES = "processes"
    READY = "ready"


@dataclass
class StartupContext:
    """启动上下文"""
    phase: StartupPhase = StartupPhase.INIT
    config_loaded: bool = False
    database_connected: bool = False
    engine_initialized: bool = False
    services_started: bool = False
    processes_started: bool = False
    errors: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    process_manager: Optional["ProcessManager"] = None
    context_manager: Optional["StartupContextManager"] = None
    event_bus: Optional["StartupEventBus"] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    required_ports: List[int] = field(default_factory=list)
    dns_test_hosts: List[str] = field(default_factory=list)
    cache_directory: Path = field(default_factory=lambda: Path("cache"))
    cache_ttl_hours: int = 24
    worker_results: Dict[str, Any] = field(default_factory=dict)

    # 兼容性属性
    project_root: Optional[Path] = None
    config_file: Optional[str] = None
    app: Optional[Any] = None

    def add_error(self, error: str):
        """添加错误"""
        self.errors.append(error)

    def get_elapsed_time(self) -> float:
        """获取启动耗时（秒）"""
        return (datetime.now() - self.start_time).total_seconds()


class StartupContextManager:
    """启动上下文管理器

    管理启动过程中产生的共享数据与异步锁
    """

    def __init__(self):
        self._context: Dict[str, Any] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self.logger = logging.getLogger("lifecycle.context_manager")

    def set(self, key: str, value: Any):
        """设置上下文值"""
        self._context[key] = value
        self.logger.debug("StartupContextManager set %s=%s", key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文值"""
        return self._context.get(key, default)

    def has(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._context

    async def acquire_lock(self, key: str) -> asyncio.Lock:
        """获取指定键的锁"""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def clear(self):
        """清空上下文数据"""
        self._context.clear()
        self._locks.clear()


class StartupEventBus:
    """启动事件总线"""

    def __init__(self):
        self._subscribers: Dict[str, List] = {}
        self.logger = logging.getLogger("lifecycle.event_bus")

    def subscribe(self, event_type: str, callback: Callable[[Any], Any]):
        """订阅事件"""
        self._subscribers.setdefault(event_type, []).append(callback)
        self.logger.debug("Subscribe event %s -> %s", event_type, callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Any], Any]):
        """取消订阅"""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
            except ValueError:
                pass

    async def publish(self, event_type: str, data: Any = None):
        """发布事件"""
        callbacks = self._subscribers.get(event_type)
        if not callbacks:
            return

        for callback in list(callbacks):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as exc:  # pragma: no cover - 防御性日志
                self.logger.error("事件处理失败 %s: %s", event_type, exc, exc_info=True)


class StartupStage(ABC):
    """启动阶段基类"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"lifecycle.stage.{name}")
        self.description = f"{name} 阶段"

    @abstractmethod
    async def execute(self, context: StartupContext) -> bool:
        """执行阶段，返回是否成功"""
        pass

    @abstractmethod
    async def rollback(self, context: StartupContext):
        """回滚阶段"""
        pass


class ValidationStage(StartupStage):
    """环境验证阶段"""

    def __init__(self):
        super().__init__("validation")
        self.min_python_version = (3, 8)
        self.required_packages: List[str] = [
            "psutil",
            "PySide6",
        ]
        self.required_directories = ["config", "logs", "data"]

    async def execute(self, context: StartupContext) -> bool:
        try:
            if not self._check_python_version():
                context.add_error(
                    f"Python版本不符合要求，需要>={self.min_python_version}"
                )
                return False

            missing_packages = self._check_required_packages()
            if missing_packages:
                context.add_error(
                    f"缺少必要的依赖包: {', '.join(missing_packages)}"
                )
                return False

            if not self._ensure_directories():
                context.add_error("配置目录结构不完整")
                return False

            self.logger.info("✅ 环境验证通过")
            return True
        except Exception as exc:
            context.add_error(f"环境验证失败: {exc}")
            self.logger.exception("环境验证失败: %s", exc)
            return False

    def _check_python_version(self) -> bool:
        return sys.version_info[:2] >= self.min_python_version

    def _check_required_packages(self) -> List[str]:
        missing: List[str] = []
        for package in self.required_packages:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)
        return missing

    def _ensure_directories(self) -> bool:
        try:
            for directory in self.required_directories:
                Path(directory).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as exc:
            self.logger.error("创建目录失败: %s", exc)
            return False

    async def rollback(self, context: StartupContext):
        # 验证阶段无需特殊回滚
        return


class CleanupStage(StartupStage):
    """清理准备阶段"""

    def __init__(self):
        super().__init__("cleanup")

    async def execute(self, context: StartupContext) -> bool:
        try:
            self._cleanup_temp_files()
            self._cleanup_old_logs(days=30)
            self._cleanup_pid_files()
            self.logger.info("✅ 清理完成")
            return True
        except Exception as exc:
            self.logger.warning("清理失败但不阻塞启动: %s", exc)
            return True

    def _cleanup_temp_files(self):
        temp_dir = Path("temp")
        if not temp_dir.exists():
            return

        for file in temp_dir.glob("*.tmp"):
            try:
                file.unlink()
            except Exception:
                # 临时文件清理失败不阻塞
                pass

    def _cleanup_old_logs(self, days: int = 30):
        logs_dir = Path("logs")
        if not logs_dir.exists():
            return

        cutoff_time = datetime.now() - timedelta(days=days)
        for log_file in logs_dir.glob("*.log*"):
            try:
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_time:
                    log_file.unlink()
            except Exception:
                pass

    def _cleanup_pid_files(self):
        for pid_file in Path(".").glob("*.pid"):
            try:
                pid_file.unlink()
            except Exception:
                pass

    async def rollback(self, context: StartupContext):
        return


class ResourceCheckStage(StartupStage):
    """资源检查阶段"""

    def __init__(self):
        super().__init__("resource_check")
        self.min_free_memory_mb = 512
        self.min_free_disk_gb = 1
        self.port_env_var = "TERMINAL_REQUIRED_PORTS"

    async def execute(self, context: StartupContext) -> bool:
        try:
            if not self._check_memory():
                context.add_error(
                    f"可用内存不足，至少需要{self.min_free_memory_mb}MB"
                )
                return False

            if not self._check_disk_space(context):
                context.add_error(
                    f"磁盘空间不足，至少需要{self.min_free_disk_gb}GB"
                )
                return False

            blocked_ports = self._check_required_ports(context)
            if blocked_ports:
                context.add_error(
                    f"以下端口已被占用: {', '.join(str(port) for port in blocked_ports)}"
                )
                return False

            self.logger.info("✅ 资源检查通过")
            return True
        except Exception as exc:
            context.add_error(f"资源检查失败: {exc}")
            self.logger.exception("资源检查失败: %s", exc)
            return False

    def _check_memory(self) -> bool:
        memory = psutil.virtual_memory()
        free_mb = memory.available / (1024 * 1024)
        self.logger.debug("可用内存 %.2f MB", free_mb)
        return free_mb >= self.min_free_memory_mb

    def _check_disk_space(self, context: StartupContext) -> bool:
        root_path = context.metadata.get("disk_root") or Path.cwd().anchor or str(Path.cwd())
        try:
            disk = psutil.disk_usage(root_path)
        except FileNotFoundError:
            disk = psutil.disk_usage(str(Path.cwd()))
        free_gb = disk.free / (1024 * 1024 * 1024)
        self.logger.debug("磁盘剩余空间 %.2f GB (%s)", free_gb, root_path)
        return free_gb >= self.min_free_disk_gb

    def _collect_required_ports(self, context: StartupContext) -> List[int]:
        ports: List[int] = []
        ports.extend(context.required_ports)

        env_ports = os.getenv(self.port_env_var)
        if env_ports:
            for port_str in env_ports.split(","):
                port_str = port_str.strip()
                if not port_str:
                    continue
                try:
                    ports.append(int(port_str))
                except ValueError:
                    self.logger.warning("忽略非法端口号: %s", port_str)

        # 去重并排序
        unique_ports = sorted({port for port in ports if port > 0})
        return unique_ports

    def _check_required_ports(self, context: StartupContext) -> List[int]:
        blocked: List[int] = []
        for port in self._collect_required_ports(context):
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("", port))
                except OSError:
                    blocked.append(port)
        if blocked:
            self.logger.error("端口被占用: %s", blocked)
        return blocked

    async def rollback(self, context: StartupContext):
        return


class NetworkCheckStage(StartupStage):
    """网络检查阶段"""

    def __init__(self):
        super().__init__("network_check")
        self.dns_env_var = "TERMINAL_DNS_CHECK_HOSTS"

    async def execute(self, context: StartupContext) -> bool:
        try:
            if not self._check_network_interfaces():
                self.logger.warning("未检测到活动网络接口，可能处于离线模式")
                return True

            if not self._check_dns_resolution(context):
                self.logger.warning("DNS解析失败，将继续以离线模式运行")
                return True

            self.logger.info("✅ 网络检查完成")
            return True
        except Exception as exc:
            self.logger.warning("网络检查失败（忽略）: %s", exc)
            return True

    def _check_network_interfaces(self) -> bool:
        net_if_addrs = psutil.net_if_addrs()
        for interface, addrs in net_if_addrs.items():
            if interface.lower() in {"lo", "loopback"}:
                continue
            if addrs:
                stats = psutil.net_if_stats().get(interface)
                if stats and stats.isup:
                    self.logger.debug("检测到活动网络接口: %s", interface)
                    return True
        return False

    def _build_dns_hosts(self, context: StartupContext) -> List[str]:
        hosts: List[str] = []
        hosts.extend(context.dns_test_hosts)

        env_hosts = os.getenv(self.dns_env_var)
        if env_hosts:
            hosts.extend([host.strip() for host in env_hosts.split(",") if host.strip()])

        if not hosts:
            hosts = ["localhost", "127.0.0.1"]

        return sorted({host for host in hosts})

    def _check_dns_resolution(self, context: StartupContext) -> bool:
        hosts = self._build_dns_hosts(context)
        for host in hosts:
            try:
                socket.getaddrinfo(host, None)
                self.logger.debug("DNS解析成功: %s", host)
            except socket.gaierror as exc:
                self.logger.warning("DNS解析失败 %s: %s", host, exc)
                return False
        return True

    async def rollback(self, context: StartupContext):
        return


class CacheInitStage(StartupStage):
    """缓存初始化阶段"""

    def __init__(self):
        super().__init__("cache_init")

    async def execute(self, context: StartupContext) -> bool:
        try:
            cache_dir = context.cache_directory
            cache_dir.mkdir(parents=True, exist_ok=True)

            removed_files = self._cleanup_expired_cache(cache_dir, context.cache_ttl_hours)
            cache_manager = self._initialize_cache_manager(cache_dir)
            context.metadata["cache_manager"] = cache_manager
            context.metadata["cache_cleanup_count"] = removed_files

            self.logger.info(
                "✅ 缓存初始化完成，清理过期文件 %d 个，目录: %s",
                removed_files,
                cache_dir,
            )
            return True
        except Exception as exc:
            context.add_error(f"缓存初始化失败: {exc}")
            self.logger.exception("缓存初始化失败: %s", exc)
            return False

    def _cleanup_expired_cache(self, cache_dir: Path, ttl_hours: int) -> int:
        if ttl_hours <= 0:
            return 0

        removed = 0
        expire_before = datetime.now() - timedelta(hours=ttl_hours)
        for cache_file in cache_dir.glob("**/*"):
            if not cache_file.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                if mtime < expire_before:
                    cache_file.unlink()
                    removed += 1
            except Exception as exc:
                self.logger.debug("清理缓存文件失败（忽略）: %s => %s", cache_file, exc)
        return removed

    def _initialize_cache_manager(self, cache_dir: Path) -> Type[CacheManager]:
        CacheManager._ensure_cache_dir()
        # 将框架缓存目录指向新的 cache 目录，默认CacheManager使用 data 目录
        if cache_dir != CacheManager.CACHE_DIR:
            CacheManager.CACHE_DIR = cache_dir  # type: ignore[assignment]
            CacheManager._ensure_cache_dir()
        return CacheManager

    async def rollback(self, context: StartupContext):
        return


class ConfigStage(StartupStage):
    """配置加载阶段"""

    def __init__(self):
        super().__init__("config")

    async def execute(self, context: StartupContext) -> bool:
        """执行配置加载"""
        try:
            get_settings()
            context.config_loaded = True
            context.phase = StartupPhase.CONFIG
            self.logger.info("✅ 配置加载完成")
            return True
        except Exception as e:
            context.add_error(f"配置加载失败: {e}")
            return False

    async def rollback(self, context: StartupContext):
        """回滚配置"""
        context.config_loaded = False


class DatabaseStage(StartupStage):
    """数据库初始化阶段"""

    def __init__(self):
        super().__init__("database")

    async def execute(self, context: StartupContext) -> bool:
        """执行数据库初始化"""
        try:
            initializer = DatabaseInitializer()
            success = await initializer.initialize()
            if not success:
                context.add_error("数据库初始化器执行失败")
                return False

            context.database_connected = True
            context.phase = StartupPhase.DATABASE
            context.metadata["database_initializer"] = initializer
            self.logger.info("✅ 数据库连接完成")
            return True
        except Exception as e:
            context.add_error(f"数据库连接失败: {e}")
            return False

    async def rollback(self, context: StartupContext):
        """回滚数据库"""
        initializer = context.metadata.pop("database_initializer", None)
        if isinstance(initializer, DatabaseInitializer):
            await initializer.cleanup()
        context.database_connected = False


class EngineStage(StartupStage):
    """引擎初始化阶段"""

    def __init__(self):
        super().__init__("engine")

    async def execute(self, context: StartupContext) -> bool:
        """执行引擎初始化"""
        try:
            engine_manager = EngineManager.get_instance()
            success = engine_manager.initialize()
            context.engine_initialized = success
            if success:
                context.phase = StartupPhase.ENGINE
                self.logger.info("✅ 引擎初始化完成")
            return success
        except Exception as e:
            context.add_error(f"引擎初始化失败: {e}")
            return False

    async def rollback(self, context: StartupContext):
        """回滚引擎"""
        EngineManager.get_instance().shutdown()
        context.engine_initialized = False


class ServiceStage(StartupStage):
    """服务启动阶段"""

    def __init__(self):
        super().__init__("services")

    async def execute(self, context: StartupContext) -> bool:
        """执行服务启动"""
        try:
            registry = get_service_registry()
            registry.initialize_all()
            context.services_started = True
            context.phase = StartupPhase.SERVICES
            self.logger.info("✅ 服务启动完成")
            return True
        except Exception as e:
            context.add_error(f"服务启动失败: {e}")
            return False

    async def rollback(self, context: StartupContext):
        """回滚服务"""
        get_service_registry().shutdown_all()
        context.services_started = False


@dataclass
class StartupResult:
    """启动结果"""
    success: bool
    message: str = ""
    error: Exception | None = None
    elapsed_ms: float = 0.0


class StartupOrchestrator:
    """启动编排器"""

    def __init__(self):
        self.context = StartupContext()
        self.context.context_manager = StartupContextManager()
        self.context.event_bus = StartupEventBus()
        self.stages: List[StartupStage] = []
        self.logger = logging.getLogger("lifecycle.orchestrator")
        self._setup_stages()

        # 兼容性属性
        self.startup = self.start

    def _setup_stages(self):
        """设置启动阶段"""
        self.stages = [
            ValidationStage(),
            CleanupStage(),
            ResourceCheckStage(),
            NetworkCheckStage(),
            CacheInitStage(),
            ConfigStage(),
            DatabaseStage(),
            EngineStage(),
            ServiceStage(),
            UIActivationStage(),  # 添加UI激活阶段
        ]

    def add_stage(self, stage: StartupStage):
        """添加启动阶段（兼容性方法）"""
        self.stages.append(stage)
        self.logger.debug(f"添加启动阶段: {stage.name}")

    async def start(self) -> StartupResult:
        """执行启动流程"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 开始启动流程")
        self.logger.info("=" * 60)

        start_time = time.time()

        for stage in self.stages:
            self.logger.info(f"执行阶段: {stage.name}")
            try:
                success = await stage.execute(self.context)

                if not success:
                    elapsed_ms = (time.time() - start_time) * 1000
                    self.logger.error(f"❌ 阶段 {stage.name} 执行失败")
                    await self._rollback(stage)
                    return StartupResult(success=False, message=f"阶段 {stage.name} 执行失败", elapsed_ms=elapsed_ms)
            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                self.logger.exception(f"❌ 阶段 {stage.name} 异常: {e}")
                await self._rollback(stage)
                return StartupResult(success=False, message=f"阶段 {stage.name} 异常: {str(e)}", error=e, elapsed_ms=elapsed_ms)

        self.context.phase = StartupPhase.READY
        elapsed = self.context.get_elapsed_time()
        elapsed_ms = elapsed * 1000  # Convert to milliseconds
        self.logger.info("=" * 60)
        self.logger.info(f"✅ 启动完成 (耗时: {elapsed:.2f}秒)")
        self.logger.info("=" * 60)
        return StartupResult(success=True, elapsed_ms=elapsed_ms)

    async def _rollback(self, failed_stage: StartupStage):
        """回滚到失败阶段之前"""
        self.logger.warning("开始回滚...")
        idx = self.stages.index(failed_stage)

        for stage in reversed(self.stages[:idx]):
            try:
                await stage.rollback(self.context)
                self.logger.info(f"回滚阶段: {stage.name}")
            except Exception as e:
                self.logger.error(f"回滚失败 {stage.name}: {e}")

    def get_context(self) -> StartupContext:
        """获取启动上下文"""
        return self.context


# ============================================================================
# Section 2: 进程管理 (行 200-400)
# ============================================================================

class ProcessStatus(str, Enum):
    """进程状态"""
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ProcessSpec:
    """进程规格"""
    name: str
    target: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    auto_restart: bool = True
    max_restarts: int = 3


class ProcessManager:
    """进程管理器"""

    def __init__(self):
        self._processes: Dict[str, multiprocessing.Process] = {}
        self._specs: Dict[str, ProcessSpec] = {}
        self._status: Dict[str, ProcessStatus] = {}
        self._restart_counts: Dict[str, int] = {}
        self.logger = logging.getLogger("lifecycle.process_manager")

    def register(self, spec: ProcessSpec):
        """注册进程"""
        self._specs[spec.name] = spec
        self._status[spec.name] = ProcessStatus.CREATED
        self.logger.info(f"进程已注册: {spec.name}")

    async def start_process(self, name: str) -> bool:
        """启动进程"""
        if name not in self._specs:
            self.logger.error(f"进程未注册: {name}")
            return False

        spec = self._specs[name]
        self._status[name] = ProcessStatus.STARTING

        try:
            # 创建进程
            process = multiprocessing.Process(
                target=spec.target,
                args=spec.args,
                kwargs=spec.kwargs,
                name=name
            )

            # 启动进程
            process.start()

            # 等待片刻以确认进程启动
            await asyncio.sleep(0.1)

            # 检查进程是否运行
            if process.is_alive():
                self._processes[name] = process
                self._status[name] = ProcessStatus.RUNNING
                self._restart_counts[name] = 0
                self.logger.info(f"✅ 进程已启动: {name} (PID={process.pid})")
                return True
            else:
                self._status[name] = ProcessStatus.ERROR
                self.logger.error(f"❌ 进程启动后立即退出: {name}")
                return False

        except Exception as e:
            self._status[name] = ProcessStatus.ERROR
            self.logger.error(f"❌ 进程启动失败 {name}: {e}")
            return False

    async def stop_process(self, name: str, timeout: float = 5.0):
        """停止进程

        Args:
            name: 进程名称
            timeout: 超时时间（秒）
        """
        if name not in self._processes:
            self.logger.warning(f"进程不存在: {name}")
            return

        process = self._processes[name]
        self._status[name] = ProcessStatus.STOPPING

        try:
            if process.is_alive():
                # 先尝试优雅关闭
                self.logger.info(f"正在停止进程: {name}...")
                process.terminate()

                # 等待进程结束
                process.join(timeout=timeout)

                # 如果进程仍然存活，强制杀死
                if process.is_alive():
                    self.logger.warning(f"进程 {name} 未响应terminate，强制kill")
                    process.kill()
                    process.join(timeout=1)

                self.logger.info(f"✅ 进程已停止: {name}")

            # 清理
            del self._processes[name]
            self._status[name] = ProcessStatus.STOPPED

        except Exception as e:
            self.logger.error(f"停止进程失败 {name}: {e}")
            self._status[name] = ProcessStatus.ERROR

    async def start_all(self):
        """启动所有进程"""
        for name in self._specs.keys():
            await self.start_process(name)

    async def stop_all(self, timeout: float = 5.0):
        """停止所有进程

        Args:
            timeout: 每个进程的超时时间（秒）
        """
        for name in list(self._processes.keys()):
            await self.stop_process(name, timeout)

    def get_status(self, name: str) -> Optional[ProcessStatus]:
        """获取进程状态"""
        return self._status.get(name)

    def get_process_info(self, name: str) -> Optional[Dict]:
        """获取进程详细信息"""
        if name not in self._processes:
            return None

        process = self._processes[name]
        return {
            "name": name,
            "pid": process.pid,
            "alive": process.is_alive(),
            "exitcode": process.exitcode,
            "status": self._status.get(name, ProcessStatus.STOPPED).value,
        }

    async def restart_process(self, name: str) -> bool:
        """重启进程

        Args:
            name: 进程名称

        Returns:
            是否重启成功
        """
        if name not in self._specs:
            self.logger.error(f"进程未注册: {name}")
            return False

        spec = self._specs[name]

        # 检查重启次数
        restart_count = self._restart_counts.get(name, 0)
        if restart_count >= spec.max_restarts:
            self.logger.error(f"进程 {name} 已达最大重启次数: {spec.max_restarts}")
            return False

        # 停止现有进程
        if name in self._processes:
            await self.stop_process(name)

        # 启动新进程
        self._restart_counts[name] = restart_count + 1
        self.logger.info(f"重启进程: {name} (第{restart_count + 1}次)")
        return await self.start_process(name)


class WorkerExecutionError(RuntimeError):
    """Worker执行异常"""


class WorkerBase(ABC):
    """Worker基类"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"lifecycle.worker.{name}")

    async def execute(self, context: StartupContext) -> bool:
        start_time = time.perf_counter()
        try:
            self.logger.info("执行Worker: %s", self.name)
            result = await self.run(context)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            context.worker_results[self.name] = {
                "success": result,
                "elapsed_ms": elapsed_ms,
            }
            if result:
                self.logger.info("✅ Worker %s 执行成功 (%.0fms)", self.name, elapsed_ms)
            else:
                self.logger.error("❌ Worker %s 执行失败", self.name)
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            context.worker_results[self.name] = {
                "success": False,
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
            }
            context.add_error(f"Worker {self.name} 执行失败: {exc}")
            self.logger.exception("Worker %s 执行异常: %s", self.name, exc)
            return False

    @abstractmethod
    async def run(self, context: StartupContext) -> bool:
        """执行Worker逻辑"""
        raise NotImplementedError

    async def rollback(self, context: StartupContext):
        """回滚"""
        return


class UIActivationStage(StartupStage):
    """UI激活阶段"""

    def __init__(self):
        super().__init__("ui_activation")

    async def execute(self, context: StartupContext) -> bool:
        """执行UI激活"""
        try:
            # 延迟导入Qt避免在非GUI环境下导入失败
            from PySide6.QtWidgets import QApplication

            # 创建主窗口
            from ui.main_window import MainWindow

            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)

            # 创建主窗口
            main_window = MainWindow(backend_ready=True)
            main_window.show()

            # 保存到上下文
            context.app = app
            context.metadata["main_window"] = main_window

            self.logger.info("✅ UI激活完成")
            return True
        except Exception as exc:
            context.add_error(f"UI激活失败: {exc}")
            self.logger.exception("UI激活失败: %s", exc)
            return False

    async def rollback(self, context: StartupContext):
        """回滚UI"""
        try:
            if "main_window" in context.metadata:
                main_window = context.metadata["main_window"]
                if hasattr(main_window, "close"):
                    main_window.close()
        except Exception as exc:
            self.logger.warning("UI回滚失败: %s", exc)
    logger.info("监控进程已启动 (PID=%s)", os.getpid())
    try:
        while True:
            logger.debug("监控进程心跳")
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("监控进程接收到终止信号并退出")


def _data_process_entry():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("lifecycle.process.data")
    logger.info("数据进程已启动 (PID=%s)", os.getpid())
    try:
        while True:
            logger.debug("数据进程心跳")
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("数据进程接收到终止信号并退出")


class BackendInitializer(WorkerBase):
    """后端初始化Worker"""

    def __init__(self):
        super().__init__("backend_initializer", "绑定主引擎与服务注册表")

    async def run(self, context: StartupContext) -> bool:
        engine_manager = EngineManager.get_instance()
        main_engine = engine_manager.get_main_engine()
        event_engine = engine_manager.get_event_engine()

        if not main_engine or not event_engine:
            raise WorkerExecutionError("主引擎或事件引擎未初始化")

        registry = get_service_registry()
        registry.set_engines(main_engine, event_engine)
        self.logger.debug("已为服务注册表绑定VnPy引擎")
        return True


class MonitorLauncher(WorkerBase):
    """监控进程启动Worker"""

    def __init__(self):
        super().__init__("monitor_launcher", "启动监控进程")

    async def run(self, context: StartupContext) -> bool:
        manager = self._resolve_process_manager(context)
        self._ensure_monitor_spec(manager)
        success = await manager.start_process("monitor")
        if not success:
            raise WorkerExecutionError("监控进程启动失败")

        info = manager.get_process_info("monitor")
        if not info or not info.get("alive"):
            raise WorkerExecutionError("监控进程未处于运行状态")

        context.metadata["monitor_process"] = info
        context.processes_started = True
        return True

    def _resolve_process_manager(self, context: StartupContext) -> ProcessManager:
        if context.process_manager:
            return context.process_manager
        lifecycle_manager = LifecycleManager.get_instance()
        context.process_manager = lifecycle_manager.process_manager
        return lifecycle_manager.process_manager

    def _ensure_monitor_spec(self, manager: ProcessManager):
        # Monitor process spec - disabled for now
        pass


class DataLauncher(WorkerBase):
    """数据进程启动Worker"""

    def __init__(self):
        super().__init__("data_launcher", "启动数据进程")

    async def run(self, context: StartupContext) -> bool:
        manager = self._resolve_process_manager(context)
        self._ensure_data_spec(manager)

        monitor_status = manager.get_status("monitor")
        if monitor_status != ProcessStatus.RUNNING:
            self.logger.info("监控进程未运行，先行启动监控进程")
            await MonitorLauncher().run(context)

        success = await manager.start_process("data")
        if not success:
            raise WorkerExecutionError("数据进程启动失败")

        info = manager.get_process_info("data")
        if not info or not info.get("alive"):
            raise WorkerExecutionError("数据进程未处于运行状态")

        context.metadata["data_process"] = info
        return True

    def _resolve_process_manager(self, context: StartupContext) -> ProcessManager:
        if context.process_manager:
            return context.process_manager
        lifecycle_manager = LifecycleManager.get_instance()
        context.process_manager = lifecycle_manager.process_manager
        return lifecycle_manager.process_manager

    def _ensure_data_spec(self, manager: ProcessManager):
        # Data process spec - disabled for now
        pass


class InitializerBase(ABC):
    """初始化器基类"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"lifecycle.initializer.{name}")
        self._initialized = False

    async def initialize(self) -> bool:
        if self._initialized:
            self.logger.debug("初始化器 %s 已执行，跳过", self.name)
            return True

        try:
            await self._do_initialize()
            self._initialized = True
            self.logger.info("✅ 初始化器 %s 完成", self.name)
            return True
        except Exception as exc:
            self.logger.error("初始化器 %s 失败: %s", self.name, exc)
            with contextlib.suppress(Exception):
                await self.cleanup()
            return False

    @abstractmethod
    async def _do_initialize(self):
        """执行初始化逻辑"""
        raise NotImplementedError

    async def cleanup(self):
        """清理资源"""
        self._initialized = False


class LoggingInitializer(InitializerBase):
    """日志系统初始化器"""

    def __init__(self):
        super().__init__("logging")

    async def _do_initialize(self):
        logging_manager = get_logging_manager()
        await logging_manager.initialize()

    async def cleanup(self):
        get_logging_manager().shutdown()
        await super().cleanup()


class DatabaseInitializer(InitializerBase):
    """数据库初始化器"""

    def __init__(self):
        super().__init__("database")
        self.timeout = 5.0

    async def _do_initialize(self):
        settings = get_settings()
        db_config = settings.database
        host = getattr(db_config, "host", "localhost")
        port = int(getattr(db_config, "port", 3306))

        self.logger.info("验证数据库连通性: %s:%s", host, port)
        try:
            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout,
            )
        finally:
            if writer:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
            if reader:
                reader.feed_eof()

    async def cleanup(self):
        await super().cleanup()


class CacheInitializer(InitializerBase):
    """缓存初始化器"""

    def __init__(self):
        super().__init__("cache")

    async def _do_initialize(self):
        cache_dir = Path("cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        if CacheManager.CACHE_DIR != cache_dir:
            CacheManager.CACHE_DIR = cache_dir  # type: ignore[assignment]
        CacheManager._ensure_cache_dir()
        self.logger.debug("缓存目录已就绪: %s", CacheManager.CACHE_DIR)

    async def cleanup(self):
        await super().cleanup()


class ConfigInitializer(InitializerBase):
    """配置初始化器"""

    def __init__(self):
        super().__init__("config")

    async def _do_initialize(self):
        config_path = os.getenv("TERMINAL_CONFIG_FILE")
        if config_path:
            ConfigManager.get_instance().load(config_path)
            self.logger.info("已加载配置文件: %s", config_path)
        else:
            self.logger.debug("未提供配置文件路径，使用默认配置")

    async def cleanup(self):
        await super().cleanup()


# ============================================================================
# Section 3: 健康检查 (行 400-500)
# ============================================================================

@dataclass
class HealthStatus:
    """健康状态"""
    healthy: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class HealthCheckManager:
    """健康检查管理器"""

    def __init__(self):
        self._checks: Dict[str, Callable] = {}
        self.logger = logging.getLogger("lifecycle.health")

    def register_check(self, name: str, check_func: Callable):
        """注册健康检查"""
        self._checks[name] = check_func
        self.logger.info(f"已注册健康检查: {name}")

    async def check_all(self) -> HealthStatus:
        """执行所有健康检查"""
        results = {}

        for name, check_func in self._checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    results[name] = await check_func()
                else:
                    results[name] = check_func()
            except Exception as e:
                self.logger.error(f"健康检查失败 {name}: {e}")
                results[name] = False

        healthy = all(results.values())
        return HealthStatus(
            healthy=healthy,
            checks=results,
            message="All checks passed" if healthy else "Some checks failed"
        )


class DatabaseHealthCheck:
    """数据库健康检查"""

    def __init__(self, timeout: float = 3.0):
        self.logger = logging.getLogger("lifecycle.health.database")
        self.timeout = timeout

    async def check(self) -> bool:
        try:
            settings = get_settings()
            db_config = settings.database
            host = getattr(db_config, "host", "localhost")
            port = int(getattr(db_config, "port", 3306))

            self.logger.debug(
                "开始数据库健康检查 host=%s port=%s timeout=%.1fs",
                host,
                port,
                self.timeout,
            )

            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.timeout,
                )
                self.logger.info("✅ 数据库端口可访问 (%s:%s)", host, port)
                return True
            finally:
                if writer:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()
                if reader:
                    reader.feed_eof()
        except Exception as exc:
            self.logger.error("数据库健康检查失败: %s", exc)
            return False


class EngineHealthCheck:
    """引擎健康检查"""

    def __init__(self):
        self.logger = logging.getLogger("lifecycle.health.engine")

    async def check(self) -> bool:
        try:
            engine_manager = EngineManager.get_instance()
            main_engine = engine_manager.get_main_engine()
            event_engine = engine_manager.get_event_engine()

            if not main_engine or not event_engine:
                self.logger.error("引擎未初始化或缺少关键组件")
                return False

            if hasattr(event_engine, "is_active"):
                is_active = event_engine.is_active()  # type: ignore[attr-defined]
                if not is_active:
                    self.logger.error("事件引擎未处于活动状态")
                    return False

            self.logger.debug("引擎健康检查通过")
            return True
        except Exception as exc:
            self.logger.error("引擎健康检查失败: %s", exc)
            return False


class ServiceHealthCheck:
    """服务健康检查"""

    def __init__(self):
        self.logger = logging.getLogger("lifecycle.health.service")

    async def check(self) -> bool:
        try:
            registry = get_service_registry()
            services = registry.get_all()
            if not services:
                self.logger.info("未注册服务，跳过服务健康检查")
                return True

            unhealthy: List[str] = []
            for name, service in services.items():
                status = getattr(service, "status", None)
                if status and isinstance(status, ServiceStatus):
                    if status not in {ServiceStatus.RUNNING, ServiceStatus.CREATED}:
                        unhealthy.append(f"{name}:{status.value}")
                elif hasattr(service, "get_status"):
                    try:
                        status_info = service.get_status()
                        if isinstance(status_info, dict) and not status_info.get("healthy", True):
                            unhealthy.append(f"{name}:unhealthy")
                    except Exception as exc:
                        self.logger.warning("获取服务状态失败 %s: %s", name, exc)
                        unhealthy.append(f"{name}:status_error")

            if unhealthy:
                self.logger.error("服务健康检查失败: %s", ", ".join(unhealthy))
                return False

            self.logger.debug("服务健康检查通过")
            return True
        except Exception as exc:
            self.logger.error("服务健康检查异常: %s", exc)
            return False


class ResourceHealthCheck:
    """资源健康检查"""

    def __init__(self):
        self.logger = logging.getLogger("lifecycle.health.resource")
        self.cpu_threshold = 90.0
        self.memory_threshold = 90.0

    async def check(self) -> bool:
        try:
            cpu_percent_raw = psutil.cpu_percent(interval=1)
            if isinstance(cpu_percent_raw, (int, float)):
                cpu_percent = float(cpu_percent_raw)
            else:
                cpu_percent = 0.0
            if cpu_percent > self.cpu_threshold:
                self.logger.warning("CPU使用率过高: %.1f%%", cpu_percent)
                return False

            memory_info = psutil.virtual_memory()
            total_memory = float(getattr(memory_info, "total", 0.0) or 0.0)
            available_memory = float(getattr(memory_info, "available", 0.0) or 0.0)
            memory_percent = (
                ((total_memory - available_memory) / total_memory) * 100.0
                if total_memory > 0.0
                else 0.0
            )
            if memory_percent > self.memory_threshold:
                self.logger.warning("内存使用率过高: %.1f%%", memory_percent)
                return False

            return True
        except Exception as exc:
            self.logger.error("资源健康检查失败: %s", exc)
            return False


class NetworkHealthCheck:
    """网络健康检查"""

    def __init__(self, timeout: float = 3.0):
        self.logger = logging.getLogger("lifecycle.health.network")
        self.timeout = timeout

    async def check(self) -> bool:
        try:
            interfaces = psutil.net_if_stats()
            active_interfaces = [
                name for name, stats in interfaces.items()
                if stats.isup and name.lower() not in {"lo", "loopback"}
            ]

            if not active_interfaces:
                self.logger.warning("未找到活动网络接口")
                return False

            targets_env = os.getenv("TERMINAL_NETWORK_HEALTH_TARGETS")
            targets: List[str]
            if targets_env:
                targets = [item.strip() for item in targets_env.split(",") if item.strip()]
            else:
                targets = ["8.8.8.8:53", "1.1.1.1:53"]

            for target in targets:
                host, _, port_str = target.partition(":")
                port = int(port_str or "53")
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(self._probe_endpoint, host, port),
                        timeout=self.timeout,
                    )
                    self.logger.debug("网络连通性检测成功: %s", target)
                    return True
                except Exception as exc:
                    self.logger.warning("网络连通性检测失败 %s: %s", target, exc)

            self.logger.error("所有网络连通性检测均失败")
            return False
        except Exception as exc:
            self.logger.error("网络健康检查失败: %s", exc)
            return False

    def _probe_endpoint(self, host: str, port: int):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(self.timeout)
            sock.connect((host, port))
            sock.shutdown(socket.SHUT_RDWR)


class LifecycleManager:
    """生命周期管理器 - 单例"""
    _instance = None

    def __init__(self):
        self.orchestrator = StartupOrchestrator()
        self.process_manager = ProcessManager()
        self.health_checker = HealthCheckManager()
        self.logger = logging.getLogger("lifecycle.manager")
        self.initializers: List[InitializerBase] = [
            ConfigInitializer(),
            LoggingInitializer(),
            CacheInitializer(),
            DatabaseInitializer(),
        ]
        self.workers: List[WorkerBase] = [
            BackendInitializer(),
            MonitorLauncher(),
            DataLauncher(),
        ]

        # 共享上下文引用
        self.orchestrator.context.process_manager = self.process_manager
        self.orchestrator.context.metadata["lifecycle_manager"] = self

        self._register_health_checks()

    @classmethod
    def get_instance(cls) -> "LifecycleManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def startup(self) -> bool:
        """执行完整启动流程"""
        if not await self._run_initializers():
            self.logger.error("初始化器执行失败，启动流程终止")
            return False

        result = await self.orchestrator.start()
        if result.success:
            if not await self._run_workers():
                self.logger.error("Worker 执行失败，启动流程终止")
                return False
        return result.success

    async def shutdown(self):
        """执行关闭流程"""
        self.logger.info("开始关闭流程...")
        await self.process_manager.stop_all()

        get_service_registry().shutdown_all()

        EngineManager.get_instance().shutdown()

        for worker in reversed(self.workers):
            with contextlib.suppress(Exception):
                await worker.rollback(self.orchestrator.context)

        for initializer in reversed(self.initializers):
            with contextlib.suppress(Exception):
                await initializer.cleanup()

        self.logger.info("✅ 关闭完成")

    async def health_check(self) -> HealthStatus:
        """执行健康检查"""
        return await self.health_checker.check_all()

    def _register_health_checks(self):
        self.health_checker.register_check("database", DatabaseHealthCheck().check)
        self.health_checker.register_check("engine", EngineHealthCheck().check)
        self.health_checker.register_check("services", ServiceHealthCheck().check)
        self.health_checker.register_check("resource", ResourceHealthCheck().check)
        self.health_checker.register_check("network", NetworkHealthCheck().check)

    async def _run_initializers(self) -> bool:
        for initializer in self.initializers:
            success = await initializer.initialize()
            if not success:
                self.logger.error("初始化器失败: %s", initializer.name)
                return False
        return True

    async def _run_workers(self) -> bool:
        context = self.orchestrator.get_context()
        for worker in self.workers:
            success = await worker.execute(context)
            if not success:
                self.logger.error("Worker 执行失败: %s", worker.name)
                return False
        return True


def get_lifecycle_manager() -> LifecycleManager:
    return LifecycleManager.get_instance()


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 启动
    "StartupPhase",
    "StartupContext",
    "StartupStage",
    "StartupOrchestrator",
    "StartupContextManager",
    "StartupEventBus",
    "ValidationStage",
    "CleanupStage",
    "ResourceCheckStage",
    "NetworkCheckStage",
    "CacheInitStage",
    "ConfigStage",
    "DatabaseStage",
    "EngineStage",
    "ServiceStage",

    # 进程
    "ProcessStatus",
    "ProcessSpec",
    "ProcessManager",
    "WorkerBase",
    "WorkerExecutionError",
    "BackendInitializer",
    "MonitorLauncher",
    "DataLauncher",

    # 健康检查
    "HealthStatus",
    "HealthCheckManager",
    "DatabaseHealthCheck",
    "EngineHealthCheck",
    "ServiceHealthCheck",
    "ResourceHealthCheck",
    "NetworkHealthCheck",

    # 生命周期
    "LifecycleManager",
    "get_lifecycle_manager",

    # 初始化器
    "InitializerBase",
    "LoggingInitializer",
    "DatabaseInitializer",
    "CacheInitializer",
    "ConfigInitializer",
]
