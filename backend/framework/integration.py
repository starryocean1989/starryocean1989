"""
Framework Integration - 框架集成API
提供统一的框架初始化和使用接口

职责：整合foundation、runtime、lifecycle，提供简洁的对外API
"""

import asyncio
import importlib
import logging
import os
import shutil
import sys
import time
import ctypes
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable, Type

from .foundation import (
    get_service_registry,
    get_main_engine,
    get_event_engine,
    ensure_vnpy_imported,
    ServiceBase,
    ServiceRegistry,
    ConfigManager,
)
from .runtime import (
    get_monitoring_manager,
    get_logging_manager,
)
from .lifecycle import (
    get_lifecycle_manager,
)

logger = logging.getLogger("framework.integration")


# ============================================================================
# Section 1: 服务注册扩展
# ============================================================================


class ServiceRegistryExtensions:
    """服务注册表扩展方法

    为现有的ServiceRegistry添加增强功能
    """

    @staticmethod
    def register_with_dependencies(
        registry: "ServiceRegistry",
        service: ServiceBase,
        dependencies: List[str],
    ):
        """带依赖注册服务"""
        registry.register(service)

        dependencies_map = getattr(registry, "_dependencies", None)
        if not isinstance(dependencies_map, dict):
            dependencies_map = {}
        dependencies_map[service.name] = dependencies
        setattr(registry, "_dependencies", dependencies_map)

    @staticmethod
    def resolve_dependencies(registry: "ServiceRegistry") -> List[str]:
        """解析服务启动顺序"""
        dependencies_map = getattr(registry, "_dependencies", None)
        if not isinstance(dependencies_map, dict):
            return list(registry._services.keys())

        visited = set()
        result: List[str] = []

        def visit(service_name: str):
            if service_name in visited:
                return
            visited.add(service_name)

            deps = getattr(registry, "_dependencies", {}).get(service_name, [])
            for dep in deps:
                if dep in registry._services:
                    visit(dep)

            result.append(service_name)

        for service_name in registry._services.keys():
            visit(service_name)

        return result

    @staticmethod
    def get_by_interface(registry: "ServiceRegistry", interface: Type) -> List[Any]:
        """根据接口查找服务"""
        result: List[Any] = []
        for service in registry._services.values():
            if isinstance(service, interface):
                result.append(service)
        return result

    @staticmethod
    def auto_wire(registry: "ServiceRegistry"):
        """根据类型注解自动装配依赖"""
        wiring_logger = logging.getLogger("integration.auto_wire")

        for service_name, service in registry._services.items():
            if hasattr(service, "__annotations__"):
                for attr_name, attr_type in service.__annotations__.items():
                    if not attr_name.startswith("_inject_"):
                        continue

                    for other_service in registry._services.values():
                        if isinstance(other_service, attr_type):
                            setattr(service, attr_name, other_service)
                            wiring_logger.debug(
                                "自动装配: %s.%s -> %s",
                                service_name,
                                attr_name,
                                other_service.name,
                            )
                            break


_service_registry_extended = False


def extend_service_registry():
    """扩展 ServiceRegistry 类"""
    global _service_registry_extended
    if _service_registry_extended:
        return

    setattr(
        ServiceRegistry,
        "register_with_dependencies",
        ServiceRegistryExtensions.register_with_dependencies,
    )
    setattr(
        ServiceRegistry,
        "resolve_dependencies",
        ServiceRegistryExtensions.resolve_dependencies,
    )
    setattr(
        ServiceRegistry,
        "get_by_interface",
        ServiceRegistryExtensions.get_by_interface,
    )
    setattr(
        ServiceRegistry,
        "auto_wire",
        ServiceRegistryExtensions.auto_wire,
    )

    logging.getLogger("integration").info("✅ ServiceRegistry扩展已加载")
    _service_registry_extended = True


# 触发扩展
extend_service_registry()


# ============================================================================
# Section 2: Native 支持增强
# ============================================================================


class NativeIntegrationError(RuntimeError):
    """Native 集成统一异常"""

    def __init__(self, message: str, *, module: Optional[str] = None):
        if module:
            message = f"[{module}] {message}"
        super().__init__(message)
        self.module = module


class NativePerformanceMonitor:
    """Native 调用性能监控"""

    def __init__(self):
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger("integration.native_perf")

    def record(self, key: str, duration: float, *, success: bool, error: Optional[Exception] = None):
        data = self._metrics.setdefault(
            key,
            {
                "count": 0,
                "errors": 0,
                "total_duration": 0.0,
                "last_duration": 0.0,
                "last_error": None,
            },
        )
        data["count"] += 1
        data["total_duration"] += duration
        data["last_duration"] = duration
        if not success:
            data["errors"] += 1
            data["last_error"] = repr(error) if error else None
            self.logger.debug("Native调用失败: %s (%.4f s) -> %s", key, duration, error)
        else:
            data["last_error"] = None

    def get_stats(self, key: str) -> Dict[str, Any]:
        data = self._metrics.get(key)
        if not data:
            return {}

        average = data["total_duration"] / data["count"] if data["count"] else 0.0
        return {
            "count": data["count"],
            "errors": data["errors"],
            "average_duration": average,
            "last_duration": data["last_duration"],
            "last_error": data["last_error"],
        }

    def summary(self, key: Optional[str] = None) -> Dict[str, Any]:
        if key:
            return {key: self.get_stats(key)}
        return {name: self.get_stats(name) for name in self._metrics.keys()}

    def reset(self, key: Optional[str] = None):
        if key:
            self._metrics.pop(key, None)
        else:
            self._metrics.clear()


class NativeFunctionWrapper:
    """Native 函数包装器，提供性能监控与异常转换"""

    def __init__(
        self,
        native_func: Callable,
        *,
        name: Optional[str] = None,
        module: Optional[str] = None,
        performance_monitor: Optional[NativePerformanceMonitor] = None,
        exception_translator: Optional[Callable[[Exception], Exception]] = None,
    ):
        self.native_func = native_func
        self.name = name or getattr(native_func, "__name__", "native_func")
        self.module = module
        self.performance_monitor = performance_monitor or NativePerformanceMonitor()
        self.exception_translator = exception_translator
        self._is_coroutine = asyncio.iscoroutinefunction(native_func)

    def __call__(self, *args, **kwargs):
        if self._is_coroutine:
            return self._async_call(*args, **kwargs)
        return self._sync_call(*args, **kwargs)

    def _sync_call(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = self.native_func(*args, **kwargs)
            self.performance_monitor.record(self.name, time.perf_counter() - start, success=True)
            return result
        except Exception as exc:
            duration = time.perf_counter() - start
            self.performance_monitor.record(self.name, duration, success=False, error=exc)
            raise self._translate_exception(exc) from exc

    async def _async_call(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = await self.native_func(*args, **kwargs)
            self.performance_monitor.record(self.name, time.perf_counter() - start, success=True)
            return result
        except Exception as exc:
            duration = time.perf_counter() - start
            self.performance_monitor.record(self.name, duration, success=False, error=exc)
            raise self._translate_exception(exc) from exc

    def _translate_exception(self, exc: Exception) -> Exception:
        if self.exception_translator:
            return self.exception_translator(exc)
        return NativeIntegrationError(f"Native函数调用失败: {exc}", module=self.module)


class NativeMemoryManager:
    """Native 内存管理器"""

    def __init__(self):
        self._allocations: Dict[int, ctypes.Array] = {}
        self.logger = logging.getLogger("integration.native_memory")

    def allocate(self, size: int) -> int:
        if size <= 0:
            raise ValueError("size 必须大于 0")

        buffer = ctypes.create_string_buffer(size)
        ptr = ctypes.addressof(buffer)
        self._allocations[ptr] = buffer
        self.logger.debug("Native内存分配: %s bytes @ 0x%x", size, ptr)
        return ptr

    def get_buffer(self, ptr: int) -> Optional[ctypes.Array]:
        return self._allocations.get(ptr)

    def deallocate(self, ptr: int):
        if ptr in self._allocations:
            self.logger.debug("Native内存释放: 0x%x", ptr)
            self._allocations.pop(ptr, None)
        else:
            self.logger.warning("尝试释放未知指针: 0x%x", ptr)

    def allocated_bytes(self) -> int:
        return sum(len(buffer) for buffer in self._allocations.values())

    def cleanup(self):
        count = len(self._allocations)
        self._allocations.clear()
        if count:
            self.logger.info("Native内存已清理，共释放 %s 个分配", count)


class NativeModuleLoader:
    """Native 模块加载器，支持热重载"""

    def __init__(self, performance_monitor: Optional[NativePerformanceMonitor] = None):
        self._loaded_modules: Dict[str, Any] = {}
        self._module_paths: Dict[str, Path] = {}
        self.performance_monitor = performance_monitor or NativePerformanceMonitor()
        self.logger = logging.getLogger("integration.native_loader")

    def _ensure_module_path(self, module_path: Optional[str]):
        if not module_path:
            return
        if module_path not in sys.path:
            sys.path.insert(0, module_path)

    def load_module(self, module_name: str, module_path: Optional[str] = None) -> Optional[Any]:
        if module_name in self._loaded_modules:
            return self._loaded_modules[module_name]

        start = time.perf_counter()
        try:
            self._ensure_module_path(module_path)
            module = importlib.import_module(module_name)
            self._loaded_modules[module_name] = module

            module_file = getattr(module, "__file__", None)
            if module_file:
                self._module_paths[module_name] = Path(module_file).resolve()

            self.logger.info("✅ 已加载Native模块: %s", module_name)
            return module
        except ImportError as exc:
            self.logger.error("❌ 加载Native模块失败 %s: %s", module_name, exc)
            return None
        finally:
            duration = time.perf_counter() - start
            self.performance_monitor.record(f"load:{module_name}", duration, success=module_name in self._loaded_modules)

    def reload_module(self, module_name: str) -> Optional[Any]:
        module = self._loaded_modules.get(module_name)
        if not module:
            self.logger.warning("模块尚未加载，无法重载: %s", module_name)
            return None

        start = time.perf_counter()
        try:
            reloaded = importlib.reload(module)
            self._loaded_modules[module_name] = reloaded
            module_file = getattr(reloaded, "__file__", None)
            if module_file:
                self._module_paths[module_name] = Path(module_file).resolve()

            self.logger.info("♻️ Native模块已热重载: %s", module_name)
            return reloaded
        except Exception as exc:
            self.logger.error("❌ Native模块重载失败 %s: %s", module_name, exc)
            return None
        finally:
            duration = time.perf_counter() - start
            self.performance_monitor.record(f"reload:{module_name}", duration, success=module_name in self._loaded_modules)

    def unload_module(self, module_name: str):
        if module_name in self._loaded_modules:
            self._loaded_modules.pop(module_name, None)
            self._module_paths.pop(module_name, None)
            self.logger.info("已卸载Native模块: %s", module_name)

    def get_module(self, module_name: str) -> Optional[Any]:
        return self._loaded_modules.get(module_name)

    def get_module_path(self, module_name: str) -> Optional[Path]:
        return self._module_paths.get(module_name)

    def list_loaded_modules(self) -> List[str]:
        return list(self._loaded_modules.keys())


class NativeHotReloader:
    """Native 模块热重载观察器"""

    def __init__(self, loader: NativeModuleLoader):
        self.loader = loader
        self._watched: Dict[str, float] = {}
        self.logger = logging.getLogger("integration.native_hot_reload")

    def watch(self, module_name: str) -> Optional[Path]:
        module_path = self.loader.get_module_path(module_name)
        if not module_path or not module_path.exists():
            self.logger.warning("无法监听模块（未找到文件）: %s", module_name)
            return None

        self._watched[module_name] = module_path.stat().st_mtime
        self.logger.debug("已监听Native模块变化: %s (%s)", module_name, module_path)
        return module_path

    def unwatch(self, module_name: str):
        self._watched.pop(module_name, None)

    def check_and_reload(self) -> List[str]:
        reloaded: List[str] = []
        for module_name in list(self._watched.keys()):
            module_path = self.loader.get_module_path(module_name)
            if not module_path or not module_path.exists():
                continue

            current_mtime = module_path.stat().st_mtime
            last_mtime = self._watched.get(module_name, current_mtime)
            if current_mtime > last_mtime:
                if self.loader.reload_module(module_name):
                    self._watched[module_name] = current_mtime
                    reloaded.append(module_name)
        return reloaded


class NativeCompatibilityChecker:
    """Native 兼容性检查器"""

    def __init__(self):
        self.logger = logging.getLogger("integration.native_compat")

    def check_compatibility(self) -> Dict[str, bool]:
        results = {
            "platform_supported": self._check_platform(),
            "compiler_available": self._check_compiler(),
            "dependencies_installed": self._check_dependencies(),
        }
        return results

    def _check_platform(self) -> bool:
        import platform

        system = platform.system()
        supported = system in ["Windows", "Linux", "Darwin"]
        if not supported:
            self.logger.warning("当前平台不支持Native扩展: %s", system)
        return supported

    def _check_compiler(self) -> bool:
        candidates = ["cl", "clang", "gcc"]
        for candidate in candidates:
            if shutil.which(candidate):
                return True
        self.logger.warning("未检测到可用的C/C++编译器")
        return False

    def _check_dependencies(self) -> bool:
        try:
            import ctypes.util

            if os.name == "nt":
                return bool(ctypes.util.find_library("msvcrt"))

            libc = ctypes.util.find_library("c")
            return bool(libc)
        except Exception as exc:
            self.logger.warning("Native依赖检查失败: %s", exc)
            return False

    def generate_report(self) -> Dict[str, Any]:
        results = self.check_compatibility()
        report_lines = ["Native兼容性报告:"]
        for check, passed in results.items():
            status = "✅ 通过" if passed else "❌ 失败"
            report_lines.append(f"  {check}: {status}")

        return {
            "results": results,
            "report": "\n".join(report_lines),
            "has_issue": not all(results.values()),
        }


class NativeIntegrationManager:
    """Native 集成统一管理器"""

    def __init__(self):
        self.performance_monitor = NativePerformanceMonitor()
        self.loader = NativeModuleLoader(self.performance_monitor)
        self.hot_reloader = NativeHotReloader(self.loader)
        self.compatibility_checker = NativeCompatibilityChecker()
        self.memory_manager = NativeMemoryManager()
        self.logger = logging.getLogger("integration.native_manager")

    def wrap_function(
        self,
        native_func: Callable,
        *,
        name: Optional[str] = None,
        module: Optional[str] = None,
        exception_translator: Optional[Callable[[Exception], Exception]] = None,
    ) -> NativeFunctionWrapper:
        return NativeFunctionWrapper(
            native_func,
            name=name,
            module=module,
            performance_monitor=self.performance_monitor,
            exception_translator=exception_translator,
        )

    def check_environment(self) -> Dict[str, Any]:
        report = self.compatibility_checker.generate_report()
        if report["has_issue"]:
            self.logger.warning(report["report"])
        else:
            self.logger.debug(report["report"])
        return report

    def watch_module(self, module_name: str) -> Optional[Path]:
        return self.hot_reloader.watch(module_name)

    def reload_module(self, module_name: str) -> Optional[Any]:
        return self.loader.reload_module(module_name)

    def reload_changed_modules(self) -> List[str]:
        return self.hot_reloader.check_and_reload()

    def get_performance_stats(self, name: Optional[str] = None) -> Dict[str, Any]:
        return self.performance_monitor.summary(name)

    def cleanup(self):
        self.memory_manager.cleanup()
        self.performance_monitor.reset()


# ============================================================================
# Section 3: 集成层工具函数
# ============================================================================


def cleanup_temp_files(directory: str = "temp", pattern: str = "*.tmp"):
    """清理临时文件"""
    cleanup_logger = logging.getLogger("integration.cleanup")

    temp_path = Path(directory)
    if not temp_path.exists():
        return

    count = 0
    for file_path in temp_path.glob(pattern):
        try:
            file_path.unlink()
            count += 1
        except Exception as exc:
            cleanup_logger.warning("删除临时文件失败 %s: %s", file_path, exc)

    cleanup_logger.info("已清理 %s 个临时文件", count)


def cleanup_old_logs(
    log_directory: str = "logs",
    days: int = 7,
    extensions: Optional[List[str]] = None,
):
    """清理旧日志文件"""
    cleanup_logger = logging.getLogger("integration.cleanup")

    if extensions is None:
        extensions = [".log", ".log.1", ".log.2"]

    log_path = Path(log_directory)
    if not log_path.exists():
        return

    cutoff_time = datetime.now() - timedelta(days=days)
    count = 0

    for ext in extensions:
        for file_path in log_path.glob(f"*{ext}*"):
            try:
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_time:
                    file_path.unlink()
                    count += 1
            except Exception as exc:
                cleanup_logger.warning("删除日志文件失败 %s: %s", file_path, exc)

    cleanup_logger.info("已清理 %s 个旧日志文件（%s天前）", count, days)


def cleanup_cache(cache_directory: str = "cache", max_size_mb: int = 100):
    """清理缓存目录"""
    cleanup_logger = logging.getLogger("integration.cleanup")

    cache_path = Path(cache_directory)
    if not cache_path.exists():
        return

    total_size = sum(
        file.stat().st_size for file in cache_path.rglob("*") if file.is_file()
    )
    total_size_mb = total_size / (1024 * 1024)

    if total_size_mb <= max_size_mb:
        cleanup_logger.info("缓存大小正常: %.2f MB", total_size_mb)
        return

    files = [
        (file, file.stat().st_mtime)
        for file in cache_path.rglob("*")
        if file.is_file()
    ]
    files.sort(key=lambda item: item[1])

    count = 0
    for file_path, _ in files:
        try:
            file_size = file_path.stat().st_size
            file_path.unlink()
            total_size -= file_size
            count += 1
            if total_size / (1024 * 1024) <= max_size_mb:
                break
        except Exception as exc:
            cleanup_logger.warning("删除缓存文件失败 %s: %s", file_path, exc)

    cleanup_logger.info("已清理 %s 个缓存文件", count)


def ensure_directory_structure(base_dir: str = "."):
    """确保基础目录结构存在"""
    required_dirs = [
        "config",
        "logs",
        "data",
        "cache",
        "temp",
        "strategies",
        "strategies/templates",
        "strategies/user_strategies",
    ]

    base_path = Path(base_dir)
    for dir_name in required_dirs:
        dir_path = base_path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)


def backup_configuration(
    config_dir: str = "config",
    backup_dir: str = "backups",
):
    """备份配置文件"""
    backup_logger = logging.getLogger("integration.backup")

    config_path = Path(config_dir)
    if not config_path.exists():
        backup_logger.warning("配置目录不存在: %s", config_dir)
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(backup_dir) / f"config_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for file_path in config_path.glob("*.json"):
        try:
            shutil.copy2(file_path, backup_path / file_path.name)
            count += 1
        except Exception as exc:
            backup_logger.error("备份配置文件失败 %s: %s", file_path, exc)

    backup_logger.info("✅ 已备份 %s 个配置文件到 %s", count, backup_path)


def restore_configuration(
    backup_path: str,
    config_dir: str = "config",
):
    """恢复配置文件"""
    restore_logger = logging.getLogger("integration.restore")

    backup = Path(backup_path)
    if not backup.exists():
        restore_logger.error("备份目录不存在: %s", backup_path)
        return

    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for file_path in backup.glob("*.json"):
        try:
            shutil.copy2(file_path, config_path / file_path.name)
            count += 1
        except Exception as exc:
            restore_logger.error("恢复配置文件失败 %s: %s", file_path, exc)

    restore_logger.info("✅ 已恢复 %s 个配置文件", count)


# ============================================================================
# Section 4: 框架主类
# ============================================================================


@dataclass
class FrameworkStatus:
    """框架状态"""

    initialized: bool = False
    vnpy_available: bool = False
    native_ready: bool = False
    config_loaded: bool = False
    services_running: bool = False
    monitoring_active: bool = False
    logging_active: bool = False


class Framework:
    """
    框架主类 - 统一入口
    整合所有框架功能，提供简洁的初始化和使用接口
    """

    _instance = None

    def __init__(self):
        if Framework._instance is not None:
            raise RuntimeError("请使用 Framework.get_instance()")

        self.status = FrameworkStatus()
        self.logger = logging.getLogger("framework")

        # 子系统引用
        self._settings = None
        self._service_registry: Optional[ServiceRegistry] = None
        self._monitoring_manager = None
        self._logging_manager = None
        self._lifecycle_manager = None
        self._native_manager = NativeIntegrationManager()

    @classmethod
    def get_instance(cls) -> "Framework":
        """获取框架单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, config_file: Optional[str] = None) -> bool:
        """
        初始化框架

        Args:
            config_file: 配置文件路径（可选）

        Returns:
            是否初始化成功
        """
        self.logger.info("=" * 70)
        self.logger.info("🚀 Terminal v0.50 Framework 正在初始化...")
        self.logger.info("=" * 70)

        try:
            # 1. 加载配置
            config_manager = ConfigManager.get_instance()
            self._settings = config_manager.get_settings()
            if config_file:
                config_manager.load(config_file)
                self._settings = config_manager.get_settings()
            self.status.config_loaded = True
            self.logger.info("✅ 配置加载完成")

            # 2. 初始化日志系统
            self._logging_manager = get_logging_manager()
            await self._logging_manager.initialize()
            self.status.logging_active = True
            self.logger.info("✅ 日志系统初始化完成")

            # 3. 检查VnPy可用性
            self.status.vnpy_available = ensure_vnpy_imported()
            if self.status.vnpy_available:
                self.logger.info("✅ VnPy可用")
            else:
                self.logger.warning("⚠️ VnPy不可用")

            # 4. 初始化监控系统
            self._monitoring_manager = get_monitoring_manager()
            self._monitoring_manager.initialize()
            self.status.monitoring_active = True
            self.logger.info("✅ 监控系统初始化完成")

            # 5. 获取服务注册表
            self._service_registry = get_service_registry()
            self.logger.info("✅ 服务注册表就绪")

            # 6. Native 环境检查
            native_report = self._native_manager.check_environment()
            self.status.native_ready = not native_report["has_issue"]
            if not self.status.native_ready:
                self.logger.warning("⚠️ Native环境检测存在问题，请查看日志详情")

            # 7. 执行启动流程
            self._lifecycle_manager = get_lifecycle_manager()
            success = await self._lifecycle_manager.startup()

            if success:
                self.status.initialized = True
                self.status.services_running = True
                self.logger.info("=" * 70)
                self.logger.info("✅ 框架初始化成功")
                self.logger.info("=" * 70)
                return True
            else:
                self.logger.error("❌ 启动流程失败")
                return False

        except Exception as exc:
            self.logger.error("❌ 框架初始化失败: %s", exc, exc_info=True)
            return False

    async def shutdown(self):
        """关闭框架"""
        self.logger.info("=" * 70)
        self.logger.info("🛑 正在关闭框架...")
        self.logger.info("=" * 70)

        try:
            if self._lifecycle_manager:
                await self._lifecycle_manager.shutdown()

            if self._monitoring_manager:
                self._monitoring_manager.shutdown()
                self.status.monitoring_active = False

            if self._logging_manager:
                self._logging_manager.shutdown()
                self.status.logging_active = False

            self._native_manager.cleanup()

            self.status.initialized = False
            self.status.services_running = False

            self.logger.info("=" * 70)
            self.logger.info("✅ 框架已关闭")
            self.logger.info("=" * 70)

        except Exception as exc:
            self.logger.error("❌ 框架关闭失败: %s", exc, exc_info=True)

    def register_service(self, service: ServiceBase, dependencies: Optional[List[str]] = None):
        """
        注册服务

        Args:
            service: 服务实例
            dependencies: 依赖的服务名称列表
        """
        if not self._service_registry:
            raise RuntimeError("框架未初始化")

        if dependencies:
            register_with_deps = getattr(self._service_registry, "register_with_dependencies", None)
            if callable(register_with_deps):
                register_with_deps(service, dependencies)
            else:
                self._service_registry.register(service)
        else:
            self._service_registry.register(service)

        auto_wire = getattr(self._service_registry, "auto_wire", None)
        if callable(auto_wire):
            auto_wire()

    def get_service(self, name: str) -> Optional[ServiceBase]:
        """获取服务"""
        if self._service_registry:
            return self._service_registry.get(name)
        return None

    async def health_check(self) -> Dict[str, Any]:
        """执行健康检查"""
        if not self._lifecycle_manager:
            return {"status": "not_initialized"}

        health_status = await self._lifecycle_manager.health_check()
        return {
            "healthy": health_status.healthy,
            "checks": health_status.checks,
            "message": health_status.message,
            "timestamp": health_status.timestamp.isoformat(),
        }

    def get_status(self) -> Dict[str, Any]:
        """获取框架状态"""
        return {
            "initialized": self.status.initialized,
            "vnpy_available": self.status.vnpy_available,
            "native_ready": self.status.native_ready,
            "config_loaded": self.status.config_loaded,
            "services_running": self.status.services_running,
            "monitoring_active": self.status.monitoring_active,
            "logging_active": self.status.logging_active,
        }

    def get_main_engine(self):
        """获取VnPy主引擎"""
        return get_main_engine()

    def get_event_engine(self):
        """获取VnPy事件引擎"""
        return get_event_engine()

    def get_native_manager(self) -> NativeIntegrationManager:
        """获取Native集成管理器"""
        return self._native_manager

    def get_native_loader(self) -> NativeModuleLoader:
        """获取Native模块加载器"""
        return self._native_manager.loader

    def get_native_memory_manager(self) -> NativeMemoryManager:
        """获取Native内存管理器"""
        return self._native_manager.memory_manager

    def wrap_native_function(
        self,
        native_func: Callable,
        *,
        name: Optional[str] = None,
        module: Optional[str] = None,
        exception_translator: Optional[Callable[[Exception], Exception]] = None,
    ) -> NativeFunctionWrapper:
        """为Native函数提供包装"""
        return self._native_manager.wrap_function(
            native_func,
            name=name,
            module=module,
            exception_translator=exception_translator,
        )

    def watch_native_module(self, module_name: str) -> Optional[Path]:
        """监听Native模块文件变化"""
        return self._native_manager.watch_module(module_name)

    def reload_native_module(self, module_name: str) -> Optional[Any]:
        """热重载指定Native模块"""
        return self._native_manager.reload_module(module_name)

    def reload_changed_native_modules(self) -> List[str]:
        """检查并热重载已监听模块"""
        return self._native_manager.reload_changed_modules()

    def get_native_performance_metrics(self, name: Optional[str] = None) -> Dict[str, Any]:
        """获取Native调用性能指标"""
        return self._native_manager.get_performance_stats(name)


# ============================================================================
# 便捷函数
# ============================================================================


def get_framework() -> Framework:
    """获取框架实例"""
    return Framework.get_instance()


async def init_framework(config_file: Optional[str] = None) -> Framework:
    """
    初始化框架（便捷函数）

    Args:
        config_file: 配置文件路径

    Returns:
        框架实例
    """
    framework = get_framework()
    await framework.initialize(config_file)
    return framework


async def shutdown_framework():
    """关闭框架（便捷函数）"""
    framework = get_framework()
    await framework.shutdown()


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # ServiceRegistry 扩展
    "ServiceRegistryExtensions",
    "extend_service_registry",
    # Native 集成
    "NativeIntegrationError",
    "NativePerformanceMonitor",
    "NativeFunctionWrapper",
    "NativeMemoryManager",
    "NativeModuleLoader",
    "NativeHotReloader",
    "NativeCompatibilityChecker",
    "NativeIntegrationManager",
    # 工具函数
    "cleanup_temp_files",
    "cleanup_old_logs",
    "cleanup_cache",
    "ensure_directory_structure",
    "backup_configuration",
    "restore_configuration",
    # 框架主类
    "Framework",
    "FrameworkStatus",
    "get_framework",
    "init_framework",
    "shutdown_framework",
]
