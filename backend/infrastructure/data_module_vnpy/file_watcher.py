# -*- coding: utf-8 -*-
"""
文件监控模块

使用watchdog库监控数据文件变化，实时触发数据质量更新。
"""

import logging
import time
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None
    FileSystemEvent = None


class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器"""

    def __init__(self, callback: Callable[[Path], None]):
        """初始化事件处理器

        Args:
            callback: 文件变化回调函数
        """
        super().__init__()
        self.callback = callback
        self.logger = logging.getLogger(__name__)

        # 防抖动：记录最近处理的文件和时间
        self.recent_files = {}
        self.debounce_seconds = 2  # 2秒内的重复事件忽略

    def on_modified(self, event: FileSystemEvent) -> None:
        """文件修改事件

        Args:
            event: 文件系统事件
        """
        if not event.is_directory and self._is_data_file(event.src_path):
            self._handle_file_change(event.src_path, "modified")

    def on_created(self, event: FileSystemEvent) -> None:
        """文件创建事件

        Args:
            event: 文件系统事件
        """
        if not event.is_directory and self._is_data_file(event.src_path):
            self._handle_file_change(event.src_path, "created")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """文件删除事件

        Args:
            event: 文件系统事件
        """
        if not event.is_directory and self._is_data_file(event.src_path):
            self._handle_file_change(event.src_path, "deleted")

    def _is_data_file(self, file_path: str) -> bool:
        """判断是否是数据文件

        Args:
            file_path: 文件路径

        Returns:
            是否是数据文件
        """
        return file_path.endswith("data.parquet")

    def _handle_file_change(self, file_path: str, event_type: str) -> None:
        """处理文件变化

        Args:
            file_path: 文件路径
            event_type: 事件类型
        """
        try:
            # 防抖动检查
            current_time = time.time()
            if file_path in self.recent_files:
                last_time = self.recent_files[file_path]
                if current_time - last_time < self.debounce_seconds:
                    return  # 忽略短时间内的重复事件

            # 更新最近处理时间
            self.recent_files[file_path] = current_time

            # 调用回调
            path = Path(file_path)
            self.logger.info("文件变化: %s (%s)", path, event_type)
            self.callback(path)

        except Exception as e:
            self.logger.error("处理文件变化失败: %s", e)


class EventDrivenFileWatcher:
    """事件驱动文件监控器（兼容旧版本）

    这是一个简化的存根类，用于兼容旧代码。
    实际功能已由 DataFileWatcher 实现。
    """

    def __init__(self, event_engine):
        """初始化事件驱动文件监控器

        Args:
            event_engine: vnpy事件引擎（保留以兼容旧接口）
        """
        self.logger = logging.getLogger(__name__)
        self.event_engine = event_engine
        self._running = False

    def start(self) -> bool:
        """启动监控（存根方法）

        Returns:
            总是返回True
        """
        self._running = True
        self.logger.debug("EventDrivenFileWatcher.start() 被调用（存根实现）")
        return True

    def stop(self) -> bool:
        """停止监控（存根方法）

        Returns:
            总是返回True
        """
        self._running = False
        self.logger.debug("EventDrivenFileWatcher.stop() 被调用（存根实现）")
        return True

    def is_running(self) -> bool:
        """检查是否正在运行

        Returns:
            运行状态
        """
        return self._running


class DataFileWatcher:
    """数据文件监控器

    使用watchdog监控数据目录，文件变化时触发回调。
    """

    def __init__(
        self,
        data_dir: Path,
        callback: Callable[[Path], None],
    ):
        """初始化文件监控器

        Args:
            data_dir: 要监控的数据目录
            callback: 文件变化回调函数
        """
        self.logger = logging.getLogger(__name__)
        self.data_dir = data_dir
        self.callback = callback

        # watchdog组件
        self.observer: Optional[Observer] = None
        self.event_handler: Optional[DataFileEventHandler] = None

        # 运行状态
        self.is_running = False

        # 检查watchdog是否可用
        if not WATCHDOG_AVAILABLE:
            self.logger.warning(
                "watchdog库不可用，文件监控功能将被禁用。如需启用，请安装: pip install watchdog"
            )

    def start(self) -> bool:
        """启动文件监控

        Returns:
            是否启动成功
        """
        if not WATCHDOG_AVAILABLE:
            self.logger.warning("watchdog不可用，无法启动文件监控")
            return False

        if self.is_running:
            self.logger.warning("文件监控已在运行")
            return False

        try:
            self.logger.info("启动文件监控: %s", self.data_dir)

            # 确保目录存在
            if not self.data_dir.exists():
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info("创建数据目录: %s", self.data_dir)

            # 创建事件处理器
            self.event_handler = DataFileEventHandler(self.callback)

            # 创建观察者
            self.observer = Observer()
            self.observer.schedule(
                self.event_handler,
                str(self.data_dir),
                recursive=True,  # 递归监控子目录
            )

            # 启动观察者
            self.observer.start()
            self.is_running = True

            self.logger.info("✅ 文件监控已启动")
            return True

        except Exception as e:
            self.logger.error("启动文件监控失败: %s", e, exc_info=True)
            return False

    def stop(self) -> bool:
        """停止文件监控

        Returns:
            是否停止成功
        """
        if not self.is_running:
            self.logger.warning("文件监控未运行")
            return False

        try:
            self.logger.info("停止文件监控...")

            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)  # 等待最多5秒

            self.is_running = False
            self.observer = None
            self.event_handler = None

            self.logger.info("✅ 文件监控已停止")
            return True

        except Exception as e:
            self.logger.error("停止文件监控失败: %s", e, exc_info=True)
            return False

    def is_available(self) -> bool:
        """检查文件监控是否可用

        Returns:
            是否可用
        """
        return WATCHDOG_AVAILABLE
