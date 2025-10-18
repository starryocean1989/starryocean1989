# -*- coding: utf-8 -*-
"""
文件监听器 - 监控data/kline目录变化，触发数据质量增量扫描
"""
import time
import logging
from pathlib import Path
from typing import Optional, Callable
from threading import Thread, Event as ThreadEvent

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # 创建占位类

    class FileSystemEventHandler:
        pass

    class FileSystemEvent:
        pass


logger = logging.getLogger(__name__)


class KlineFileHandler(FileSystemEventHandler):
    """K线数据文件事件处理器"""

    def __init__(self, callback: Callable[[str, str], None], debounce_seconds: float = 5.0):
        """
        Args:
            callback: 回调函数(event_type, file_path)
            debounce_seconds: 防抖时间（秒）
        """
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.pending_event = ThreadEvent()
        self.last_event_time = 0
        self._debounce_thread: Optional[Thread] = None

    def on_created(self, event: FileSystemEvent):
        """文件创建"""
        if not event.is_directory and event.src_path.endswith(".parquet"):
            self._trigger_callback("created", event.src_path)

    def on_modified(self, event: FileSystemEvent):
        """文件修改"""
        if not event.is_directory and event.src_path.endswith(".parquet"):
            self._trigger_callback("modified", event.src_path)

    def _trigger_callback(self, event_type: str, file_path: str):
        """触发回调（带防抖）"""
        current_time = time.time()

        # 防抖：如果距离上次事件时间太短，延迟触发
        if current_time - self.last_event_time < self.debounce_seconds:
            # 取消之前的延迟任务
            self.pending_event.set()

        self.last_event_time = current_time
        self.pending_event.clear()

        # 启动延迟任务
        self._debounce_thread = Thread(
            target=self._delayed_callback, args=(event_type, file_path), daemon=True
        )
        self._debounce_thread.start()

    def _delayed_callback(self, event_type: str, file_path: str):
        """延迟回调"""
        if self.pending_event.wait(self.debounce_seconds):
            # 事件被取消
            return

        # 执行回调
        try:
            self.callback(event_type, file_path)
        except Exception as e:
            logger.error(f"文件监听回调失败: {e}", exc_info=True)


class KlineFileWatcher:
    """K线文件监听器"""

    def __init__(self, data_dir: str, callback: Callable[[str, str], None]):
        """
        Args:
            data_dir: 监听的数据目录
            callback: 文件变化回调
        """
        self.data_dir = Path(data_dir)
        self.callback = callback
        self.observer: Optional[Observer] = None
        self.running = False

    def start(self):
        """启动监听"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog库未安装，文件监听功能不可用")
            return

        if self.running:
            logger.warning("文件监听器已经在运行")
            return

        if not self.data_dir.exists():
            logger.warning(f"数据目录不存在: {self.data_dir}")
            return

        try:
            self.observer = Observer()
            handler = KlineFileHandler(self.callback, debounce_seconds=5.0)
            self.observer.schedule(handler, str(self.data_dir), recursive=True)
            self.observer.start()
            self.running = True

            logger.info(f"✓ K线文件监听器已启动，监控目录: {self.data_dir}")
        except Exception as e:
            logger.error(f"启动文件监听器失败: {e}", exc_info=True)

    def stop(self):
        """停止监听"""
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=2.0)
                self.running = False
                logger.info("✓ K线文件监听器已停止")
            except Exception as e:
                logger.error(f"停止文件监听器失败: {e}", exc_info=True)
