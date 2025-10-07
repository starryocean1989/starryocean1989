# -*- coding: utf-8 -*-
"""
文件监控模块

基于watchdog库实现文件系统监控，实时感知数据变化：
- 监控数据目录变化（创建/修改/删除）
- 触发数据校验
- 通过事件引擎推送校验结果
- 支持多线程安全
"""

import time
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from datetime import datetime
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .config import config_manager
from .validator import DataValidator


class DataFileWatcher(FileSystemEventHandler):
    """数据文件监控处理器"""

    def __init__(self, callback: Optional[Callable] = None):
        """
        初始化文件监控处理器

        Args:
            callback: 文件变化回调函数
        """
        self.callback = callback
        self.logger = logging.getLogger(__name__)
        self.validator = DataValidator()

        # 监控的文件类型
        self.watched_extensions = {'.parquet'}

        # 防抖机制
        self._last_check_time = {}
        self._check_interval = 5  # 5秒内不重复检查同一文件

    def on_created(self, event: FileSystemEvent) -> None:
        """文件创建事件"""
        if not event.is_directory and self._should_watch(event.src_path):
            self._handle_file_change(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        """文件修改事件"""
        if not event.is_directory and self._should_watch(event.src_path):
            self._handle_file_change(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """文件删除事件"""
        if not event.is_directory and self._should_watch(event.src_path):
            self._handle_file_change(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        """文件移动事件"""
        if not event.is_directory and self._should_watch(event.src_path):
            self._handle_file_change(event.src_path, "moved")

    def _should_watch(self, file_path: str) -> bool:
        """
        判断是否应该监控该文件

        Args:
            file_path: 文件路径

        Returns:
            是否应该监控
        """
        path = Path(file_path)
        return path.suffix.lower() in self.watched_extensions

    def _handle_file_change(self, file_path: str, event_type: str) -> None:
        """
        处理文件变化

        Args:
            file_path: 文件路径
            event_type: 事件类型
        """
        try:
            # 防抖检查
            current_time = time.time()
            if file_path in self._last_check_time:
                if current_time - self._last_check_time[file_path] < self._check_interval:
                    return

            self._last_check_time[file_path] = current_time

            self.logger.info(f"检测到文件变化: {file_path} ({event_type})")

            # 解析文件路径获取品种和周期信息
            symbol, interval = self._parse_file_path(file_path)
            if symbol and interval:
                # 执行数据校验
                self._validate_changed_data(symbol, interval, event_type)

            # 调用回调函数
            if self.callback:
                self.callback(file_path, event_type, symbol, interval)

        except Exception as e:
            self.logger.error(f"处理文件变化失败: {file_path}, {e}")

    def _parse_file_path(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """
        解析文件路径获取品种和周期信息

        Args:
            file_path: 文件路径

        Returns:
            (品种代码, 周期)
        """
        try:
            path = Path(file_path)

            # 路径格式: data_dir/symbol/interval/data.parquet
            if path.name == "data.parquet":
                interval = path.parent.name
                symbol = path.parent.parent.name
                return symbol, interval

            return None, None

        except Exception as e:
            self.logger.error(f"解析文件路径失败: {file_path}, {e}")
            return None, None

    def _validate_changed_data(self, symbol: str, interval: str, event_type: str) -> None:
        """
        校验变化的数据

        Args:
            symbol: 品种代码
            interval: 周期
            event_type: 事件类型
        """
        try:
            if event_type == "deleted":
                self.logger.info(f"数据文件已删除: {symbol} {interval}")
                return

            # 执行数据校验
            result = self.validator.validate_symbol(symbol, interval)
            if result:
                if isinstance(result, list):
                    result = result[0]  # 取第一个结果

                if result.is_valid:
                    self.logger.info(f"数据校验通过: {symbol} {interval}")
                else:
                    self.logger.warning(f"数据校验失败: {symbol} {interval}, 错误: {result.errors}")
            else:
                self.logger.warning(f"数据校验失败: {symbol} {interval}")

        except Exception as e:
            self.logger.error(f"校验变化数据失败: {symbol} {interval}, {e}")


class FileWatcherManager:
    """文件监控管理器"""

    def __init__(self):
        """初始化文件监控管理器"""
        self.observer: Optional[Observer] = None
        self.handler: Optional[DataFileWatcher] = None
        self.logger = logging.getLogger(__name__)
        self._is_running = False
        self._lock = threading.Lock()

    def start_watching(self, watch_dir: Optional[Path] = None,
                      callback: Optional[Callable] = None) -> bool:
        """
        开始监控文件变化

        Args:
            watch_dir: 监控目录，如果为None则使用配置的数据目录
            callback: 文件变化回调函数

        Returns:
            是否启动成功
        """
        with self._lock:
            if self._is_running:
                self.logger.warning("文件监控已在运行")
                return True

            try:
                if watch_dir is None:
                    watch_dir = config_manager.get_data_dir()

                if not watch_dir.exists():
                    self.logger.error(f"监控目录不存在: {watch_dir}")
                    return False

                # 创建监控处理器
                self.handler = DataFileWatcher(callback)

                # 创建观察者
                self.observer = Observer()
                self.observer.schedule(self.handler, str(watch_dir), recursive=True)

                # 启动监控
                self.observer.start()
                self._is_running = True

                self.logger.info(f"开始监控目录: {watch_dir}")
                return True

            except Exception as e:
                self.logger.error(f"启动文件监控失败: {e}")
                return False

    def stop_watching(self) -> bool:
        """
        停止监控文件变化

        Returns:
            是否停止成功
        """
        with self._lock:
            if not self._is_running:
                self.logger.warning("文件监控未在运行")
                return True

            try:
                if self.observer:
                    self.observer.stop()
                    self.observer.join()
                    self.observer = None

                self.handler = None
                self._is_running = False

                self.logger.info("停止文件监控")
                return True

            except Exception as e:
                self.logger.error(f"停止文件监控失败: {e}")
                return False

    def is_running(self) -> bool:
        """
        检查是否正在监控

        Returns:
            是否正在监控
        """
        with self._lock:
            return self._is_running

    def get_watch_info(self) -> Dict[str, Any]:
        """
        获取监控信息

        Returns:
            监控信息字典
        """
        with self._lock:
            return {
                "is_running": self._is_running,
                "watch_dir": str(config_manager.get_data_dir()) if self._is_running else None,
                "handler": self.handler is not None,
                "observer": self.observer is not None
            }


class EventDrivenFileWatcher:
    """事件驱动的文件监控器"""

    def __init__(self, event_engine=None):
        """
        初始化事件驱动文件监控器

        Args:
            event_engine: vnpy事件引擎
        """
        self.event_engine = event_engine
        self.watcher_manager = FileWatcherManager()
        self.logger = logging.getLogger(__name__)

    def start(self, watch_dir: Optional[Path] = None) -> bool:
        """
        开始监控

        Args:
            watch_dir: 监控目录

        Returns:
            是否启动成功
        """
        callback = self._create_event_callback()
        return self.watcher_manager.start_watching(watch_dir, callback)

    def stop(self) -> bool:
        """
        停止监控

        Returns:
            是否停止成功
        """
        return self.watcher_manager.stop_watching()

    def is_running(self) -> bool:
        """
        检查是否正在监控

        Returns:
            是否正在监控
        """
        return self.watcher_manager.is_running()

    def _create_event_callback(self) -> Callable:
        """
        创建事件回调函数

        Returns:
            回调函数
        """
        def callback(file_path: str, event_type: str, symbol: str, interval: str):
            """文件变化回调函数"""
            try:
                if self.event_engine:
                    # 创建文件变化事件
                    event_data = {
                        "file_path": file_path,
                        "event_type": event_type,
                        "symbol": symbol,
                        "interval": interval,
                        "timestamp": datetime.now()
                    }

                    # 推送事件
                    from vnpy.event import Event
                    event = Event("EVENT_CHINASTOCK_FILE_CHANGE", event_data)
                    self.event_engine.put(event)

                    self.logger.info(f"推送文件变化事件: {symbol} {interval}")

            except Exception as e:
                self.logger.error(f"处理文件变化回调失败: {e}")

        return callback


# 全局文件监控管理器实例
file_watcher_manager = FileWatcherManager()
