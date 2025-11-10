# -*- coding: utf-8 -*-
"""模块热重载和动态替换机制

支持运行时模块热重载，无需重启应用。
提供安全的模块替换、状态迁移、依赖更新等功能。
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable, Type, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from watchdog.observers import Observer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 从framework导入基础抽象
import logging


class _LazyLoggerWrapper:
    """LazyLogger包装器，兼容旧代码"""

    def __init__(self, logger):
        self._logger = logger

    def get_logger(self):
        """获取实际的logger"""
        return self._logger

    def __getattr__(self, name):
        """代理其他方法到实际logger"""
        return getattr(self._logger, name)


def get_lazy_logger(name: str):
    """获取LazyLogger，兼容旧代码"""
    return _LazyLoggerWrapper(logging.getLogger(name))

# 从framework导入依赖解析器
try:
    from backend.framework.foundation import DependencyResolver
    _HAS_DEPENDENCY_RESOLVER = True
except ImportError:
    _HAS_DEPENDENCY_RESOLVER = False

def get_dependency_resolver():
    """获取依赖解析器"""
    if _HAS_DEPENDENCY_RESOLVER:
        from backend.framework.foundation import DependencyResolver
        return DependencyResolver()
    else:
        return None


class ReloadTrigger(Enum):
    """重载触发类型"""

    FILE_CHANGE = "file_change"  # 文件变化
    MANUAL_REQUEST = "manual_request"  # 手动请求
    DEPENDENCY_CHANGE = "dependency_change"  # 依赖变化
    ERROR_RECOVERY = "error_recovery"  # 错误恢复
    SCHEDULED = "scheduled"  # 定时重载


@dataclass
class ReloadEvent:
    """重载事件"""

    module_name: str
    trigger: ReloadTrigger
    timestamp: float = field(default_factory=time.time)
    file_path: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReloadResult:
    """重载结果"""

    success: bool
    module_name: str
    old_version: str
    new_version: str
    reload_time_ms: float
    error_message: Optional[str] = None
    affected_modules: List[str] = field(default_factory=list)
    migration_required: bool = False
    migration_result: Optional[bool] = None


class ModuleStateMigrator:
    """模块状态迁移器"""

    def __init__(self):
        self.logger = get_lazy_logger("module_state_migrator")
        self._migration_strategies: Dict[str, Callable] = {}

    def register_migration_strategy(self, module_name: str, strategy: Callable) -> None:
        """注册状态迁移策略"""
        self._migration_strategies[module_name] = strategy
        self.logger.get_logger().debug(f"Migration strategy registered for {module_name}")

    async def migrate_state(self, module_name: str, old_instance: Any, new_instance: Any) -> bool:
        """迁移模块状态"""
        try:
            # 使用注册的迁移策略
            if module_name in self._migration_strategies:
                strategy = self._migration_strategies[module_name]
                result = await strategy(old_instance, new_instance)
                self.logger.get_logger().info(f"State migrated for {module_name}: {result}")
                return result

            # 默认迁移策略：复制公共属性
            return await self._default_migration(old_instance, new_instance)

        except Exception as e:
            self.logger.get_logger().error(f"State migration failed for {module_name}: {e}")
            return False

    async def _default_migration(self, old_instance: Any, new_instance: Any) -> bool:
        """默认状态迁移"""
        try:
            # 获取旧实例的公共属性
            old_attrs = {
                name: value
                for name, value in inspect.getmembers(old_instance)
                if not name.startswith("_") and not inspect.ismethod(value)
            }

            # 设置到新实例
            for name, value in old_attrs.items():
                if hasattr(new_instance, name):
                    try:
                        setattr(new_instance, name, value)
                    except Exception:
                        # 忽略无法设置的属性
                        pass

            return True

        except Exception as e:
            self.logger.get_logger().error(f"Default migration failed: {e}")
            return False


class HotReloadHandler(FileSystemEventHandler):
    """文件变化处理器"""

    def __init__(self, hot_reload_manager):
        super().__init__()
        self.manager = hot_reload_manager
        self.logger = get_lazy_logger("hot_reload_handler")

    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            self._handle_file_change(str(event.src_path))

    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory and str(event.src_path).endswith(".py"):
            self._handle_file_change(str(event.src_path))

    def _handle_file_change(self, file_path: str):
        """处理文件变化"""
        try:
            # 从文件路径推导模块名
            module_name = self._path_to_module_name(file_path)
            if module_name:
                # 异步触发重载
                asyncio.create_task(
                    self.manager.reload_module(module_name, ReloadTrigger.FILE_CHANGE, file_path)
                )
        except Exception as e:
            self.logger.get_logger().error(f"File change handling failed: {e}")

    def _path_to_module_name(self, file_path: str) -> Optional[str]:
        """文件路径转模块名"""
        try:
            path = Path(file_path)

            # 查找对应的模块
            for name, module in sys.modules.items():
                if hasattr(module, "__file__") and module.__file__:
                    if Path(module.__file__).resolve() == path.resolve():
                        return name

            return None
        except Exception:
            return None


class ModuleHotReloadManager:
    """模块热重载管理器"""

    def __init__(self):
        self.dependency_resolver = get_dependency_resolver()
        self.state_migrator = ModuleStateMigrator()
        self.logger = get_lazy_logger("module_hot_reload_manager")
        self._modules: Dict[str, Any] = {}

        self._watched_paths: Dict[str, Any] = {}
        self._reload_history: List[ReloadResult] = []
        self._reload_locks: Dict[str, threading.Lock] = {}
        self._reload_listeners: List[Callable[[ReloadEvent], None]] = []
        self._enabled_modules: Set[str] = set()
        self._reload_stats = {
            "total_reloads": 0,
            "successful_reloads": 0,
            "failed_reloads": 0,
            "avg_reload_time_ms": 0.0,
        }

    def enable_hot_reload(self, module_name: str, watch_path: Optional[str] = None) -> None:
        """启用模块热重载"""
        self._enabled_modules.add(module_name)

        # 设置文件监控
        if watch_path:
            self._setup_file_watcher(module_name, watch_path)

        self.logger.get_logger().info(f"Hot reload enabled for module: {module_name}")

    def disable_hot_reload(self, module_name: str) -> None:
        """禁用模块热重载"""
        self._enabled_modules.discard(module_name)

        # 移除文件监控
        if module_name in self._watched_paths:
            observer = self._watched_paths[module_name]
            observer.stop()
            observer.join()
            del self._watched_paths[module_name]

        self.logger.get_logger().info(f"Hot reload disabled for module: {module_name}")

    def _setup_file_watcher(self, module_name: str, watch_path: str) -> None:
        """设置文件监控"""
        try:
            if module_name in self._watched_paths:
                # 已有监控，先停止
                self._watched_paths[module_name].stop()

            observer = Observer()
            handler = HotReloadHandler(self)
            observer.schedule(handler, watch_path, recursive=True)
            observer.start()

            self._watched_paths[module_name] = observer
            self.logger.get_logger().debug(f"File watcher setup for {module_name}: {watch_path}")

        except Exception as e:
            self.logger.get_logger().error(f"Failed to setup file watcher for {module_name}: {e}")

    async def reload_module(
        self,
        module_name: str,
        trigger: ReloadTrigger = ReloadTrigger.MANUAL_REQUEST,
        metadata: Optional[str] = None,
        reason: str = "",
    ) -> ReloadResult:
        """重载模块

        Args:
            module_name: 模块名称
            trigger: 重载触发类型
            metadata: 元数据（如文件路径）
            reason: 重载原因

        Returns:
            ReloadResult: 重载结果
        """
        if module_name not in self._enabled_modules:
            raise ValueError(f"Hot reload not enabled for module: {module_name}")

        start_time = time.time()

        # 避免重复重载
        if module_name in self._reload_locks:
            lock = self._reload_locks[module_name]
        else:
            lock = threading.Lock()
            self._reload_locks[module_name] = lock

        with lock:
            try:
                result = await self._perform_reload(
                    module_name, trigger, metadata, reason, start_time
                )
                self._record_reload_result(result)
                return result

            except Exception as e:
                error_result = ReloadResult(
                    success=False,
                    module_name=module_name,
                    old_version="unknown",
                    new_version="unknown",
                    reload_time_ms=(time.time() - start_time) * 1000,
                    error_message=str(e),
                )
                self._record_reload_result(error_result)
                return error_result

    async def _perform_reload(
        self,
        module_name: str,
        trigger: ReloadTrigger,
        metadata: Optional[str],
        reason: str,
        start_time: float,
    ) -> ReloadResult:
        """执行实际的重载操作"""
        # 1. 获取当前模块信息
        old_module = sys.modules.get(module_name)
        old_version = getattr(old_module, "__version__", "unknown") if old_module else "unknown"

        # 2. 通知监听器
        event = ReloadEvent(
            module_name=module_name, trigger=trigger, file_path=metadata, reason=reason
        )
        self._notify_reload_listeners(event)

        # 3. 获取依赖模块列表
        dependent_modules = self._get_dependent_modules(module_name)

        # 4. 保存旧实例状态（如果存在）
        old_instance = None
        if module_name in self._modules:
            old_instance = self._modules[module_name]

        # 5. 执行重载
        try:
            # 重新导入模块
            if module_name in sys.modules:
                del sys.modules[module_name]

            new_module = importlib.import_module(module_name)
            new_version = getattr(new_module, "__version__", "unknown")

            # 6. 状态迁移
            migration_required = old_instance is not None
            migration_result = True

            if migration_required and hasattr(new_module, "get_module_class"):
                # 获取新的模块类
                module_class = new_module.get_module_class()
                if module_class:
                    # 创建新实例
                    new_instance = module_class(getattr(new_module, "get_metadata", lambda: None)())

                    # 迁移状态
                    migration_result = await self.state_migrator.migrate_state(
                        module_name, old_instance, new_instance
                    )

                    # 更新模块实例
                    if module_name in self._modules:
                        self._modules[module_name] = new_instance

            # 7. 重新初始化模块（如果需要）
            reload_success = True

            reload_time = (time.time() - start_time) * 1000

            result = ReloadResult(
                success=reload_success and migration_result,
                module_name=module_name,
                old_version=old_version,
                new_version=new_version,
                reload_time_ms=reload_time,
                affected_modules=dependent_modules,
                migration_required=migration_required,
                migration_result=migration_result,
            )

            self.logger.get_logger().info(
                f"Module reloaded: {module_name} v{old_version} -> v{new_version} "
                f"({reload_time:.1f}ms, migration: {migration_result})"
            )

            return result

        except Exception as e:
            reload_time = (time.time() - start_time) * 1000
            self.logger.get_logger().error(f"Module reload failed: {module_name} - {e}")

            # 恢复旧模块
            if old_module:
                sys.modules[module_name] = old_module

            raise

    def _get_dependent_modules(self, module_name: str) -> List[str]:
        """获取依赖指定模块的模块列表"""
        dependents = []

        # 从依赖解析器获取
        if self.dependency_resolver is not None:
            direct_dependents = list(self.dependency_resolver.graph._reverse_nodes.get(module_name, set()))
            dependents.extend(direct_dependents)

        # 递归获取间接依赖
        for dependent in direct_dependents:
            indirect_dependents = self._get_dependent_modules(dependent)
            dependents.extend(indirect_dependents)

        return list(set(dependents))

    def add_reload_listener(self, listener: Callable[[ReloadEvent], None]) -> None:
        """添加重载监听器"""
        self._reload_listeners.append(listener)

    def remove_reload_listener(self, listener: Callable[[ReloadEvent], None]) -> None:
        """移除重载监听器"""
        if listener in self._reload_listeners:
            self._reload_listeners.remove(listener)

    def _notify_reload_listeners(self, event: ReloadEvent) -> None:
        """通知重载监听器"""
        for listener in self._reload_listeners:
            try:
                listener(event)
            except Exception as e:
                self.logger.get_logger().warning(f"Reload listener error: {e}")

    def _record_reload_result(self, result: ReloadResult) -> None:
        """记录重载结果"""
        self._reload_history.append(result)

        # 只保留最近100条记录
        if len(self._reload_history) > 100:
            self._reload_history = self._reload_history[-100:]

        # 更新统计
        self._reload_stats["total_reloads"] += 1
        if result.success:
            self._reload_stats["successful_reloads"] += 1
        else:
            self._reload_stats["failed_reloads"] += 1

        # 更新平均重载时间
        total_time = sum(r.reload_time_ms for r in self._reload_history)
        self._reload_stats["avg_reload_time_ms"] = total_time / len(self._reload_history)

    async def batch_reload(
        self, module_names: List[str], trigger: ReloadTrigger = ReloadTrigger.MANUAL_REQUEST
    ) -> Dict[str, ReloadResult]:
        """批量重载模块"""
        results = {}

        # 按依赖顺序重载
        if self.dependency_resolver is not None:
            try:
                reload_order = self.dependency_resolver.resolve_order(module_names)
            except Exception:
                # 如果解析失败，按原顺序重载
                reload_order = module_names
        else:
            # 如果没有依赖解析器，按原顺序重载
            reload_order = module_names

        for module_name in reload_order:
            if module_name in self._enabled_modules:
                try:
                    result = await self.reload_module(module_name, trigger)
                    results[module_name] = result
                except Exception as e:
                    results[module_name] = ReloadResult(
                        success=False,
                        module_name=module_name,
                        old_version="unknown",
                        new_version="unknown",
                        reload_time_ms=0,
                        error_message=str(e),
                    )

        return results

    def get_reload_history(self, limit: int = 50) -> List[ReloadResult]:
        """获取重载历史"""
        return self._reload_history[-limit:]

    def get_reload_statistics(self) -> Dict[str, Any]:
        """获取重载统计"""
        return self._reload_stats.copy()

    def get_enabled_modules(self) -> Set[str]:
        """获取启用热重载的模块"""
        return self._enabled_modules.copy()

    def shutdown(self) -> None:
        """关闭热重载管理器"""
        # 停止所有文件监控
        for observer in self._watched_paths.values():
            observer.stop()
            observer.join()
        self._watched_paths.clear()

        self.logger.get_logger().info("Hot reload manager shutdown")


# 全局热重载管理器
_global_hot_reload_manager = ModuleHotReloadManager()


def get_module_hot_reload_manager() -> ModuleHotReloadManager:
    """获取全局模块热重载管理器"""
    return _global_hot_reload_manager


# 便捷装饰器
def hot_reload_enabled(watch_path: Optional[str] = None):
    """装饰器：启用模块热重载

    Usage:
        @hot_reload_enabled("/path/to/module")
        class MyModule:
            pass
    """

    def decorator(module_class: Type) -> Type:
        module_name = module_class.__module__
        get_module_hot_reload_manager().enable_hot_reload(module_name, watch_path)
        return module_class

    return decorator


def state_migration_strategy(module_name: str):
    """装饰器：注册状态迁移策略

    Usage:
        @state_migration_strategy("my_module")
        async def migrate_my_module(old_instance, new_instance):
            # 迁移逻辑
            return True
    """

    def decorator(strategy: Callable) -> Callable:
        get_module_hot_reload_manager().state_migrator.register_migration_strategy(
            module_name, strategy
        )
        return strategy

    return decorator


# 便捷函数
async def reload_module(module_name: str, reason: str = "") -> ReloadResult:
    """重载指定模块"""
    return await get_module_hot_reload_manager().reload_module(
        module_name, ReloadTrigger.MANUAL_REQUEST, reason=reason
    )


async def reload_modules_batch(module_names: List[str]) -> Dict[str, ReloadResult]:
    """批量重载模块"""
    return await get_module_hot_reload_manager().batch_reload(module_names)
