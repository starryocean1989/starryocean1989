# -*- coding: utf-8 -*-
"""基础控件基类 - 提供通用功能和接口."""

import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

# pylint: disable=no-name-in-module
from PySide6.QtCore import QTimer, Qt, Signal

# pylint: disable=no-name-in-module
from PySide6.QtWidgets import QMessageBox, QWidget


# 定义基础枚举类
class ErrorCategory(Enum):
    """错误分类枚举."""

    UI = "ui"
    SYSTEM = "system"
    NETWORK = "network"
    DATA = "data"
    VNPY = "vnpy"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """错误严重程度枚举."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


try:
    from ...utils.error_handler import error_handler
except ImportError:
    try:
        from utils.error_handler import error_handler
    except ImportError:

        class MockErrorHandler:
            """模拟错误处理器."""

            def handle_error(self, error_id, message, **kwargs):
                """处理错误信息."""
                # Suppress unused kwargs warning
                _ = kwargs
                print("错误 %s: %s", error_id, message)
                return False

        error_handler = MockErrorHandler()


class BaseWidget(QWidget):
    """基础控件基类."""

    # 信号定义
    error_occurred = Signal(str)  # 错误信号
    info_message = Signal(str)  # 信息信号
    data_updated = Signal(dict)  # 数据更新信号

    def __init__(self, parent=None, title: str = ""):
        """初始化基础控件.

        Args:
            parent: 父控件
            title: 窗口标题
        """
        super().__init__(parent)
        self.title = title
        # 使用私有属性避免与LoggerMixin的logger属性冲突
        self._logger = logging.getLogger(self.__class__.__name__)
        self._is_initialized = False
        self._update_timer: Optional[QTimer] = None

        # 设置窗口标志
        self.setWindowFlags(Qt.WindowType.Widget)

        # 初始化UI
        self.setup_ui()
        self.connect_signals()

        self._is_initialized = True
        self._logger.info("%s 初始化完成", self.__class__.__name__)

    @property
    def logger(self):
        """获取日志器."""
        return self._logger

    @logger.setter
    def logger(self, value):
        """设置日志器."""
        self._logger = value

    def setup_ui(self):
        """设置用户界面 - 子类必须实现."""
        raise NotImplementedError("子类必须实现 setup_ui 方法")

    def connect_signals(self):
        """连接信号槽 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def show_error(
        self,
        message: str,
        title: str = "错误",
        error_id: Optional[str] = None,
        category: Any = ErrorCategory.UI,
        severity: Any = ErrorSeverity.MEDIUM,
        max_retries: int = 1,
        retry_callback: Optional[Callable[..., Any]] = None,
    ):
        """显示错误信息 - 使用统一错误处理器."""
        error_id = error_id or f"{self.__class__.__name__}_{hash(message)}"

        # 使用统一错误处理器
        handled = error_handler.handle_error(
            error_id=error_id,
            message=f"{title}: {message}",
            category=category,
            severity=severity,
            max_retries=max_retries,
            callback=retry_callback,
            parent_widget=self,
        )

        # 记录到本地日志
        self._logger.error("%s: %s", title, message)
        self.error_occurred.emit(message)

        return handled

    def show_warning(self, message: str, title: str = "警告"):
        """显示警告信息."""
        self._logger.warning("%s: %s", title, message)

        QMessageBox.warning(self, title, message, QMessageBox.StandardButton.Ok)

    def show_info(self, message: str, title: str = "信息"):
        """显示信息."""
        self._logger.info("%s: %s", title, message)
        self.info_message.emit(message)

        QMessageBox.information(self, title, message, QMessageBox.StandardButton.Ok)

    def show_question(self, message: str, title: str = "确认") -> bool:
        """显示确认对话框."""
        self._logger.info("用户确认: %s", message)

        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        return reply == QMessageBox.StandardButton.Yes

    def set_loading_state(self, loading: bool, message: str = "加载中..."):
        """设置加载状态."""
        if loading:
            # 显示加载状态
            self.show_info(message)
        else:
            # 隐藏加载状态
            # pylint: disable=unnecessary-pass
            pass

    def start_update_timer(
        self, interval: int = 1000, callback: Optional[Callable[..., Any]] = None
    ):
        """启动更新定时器."""
        if self._update_timer:
            self._update_timer.stop()

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(callback or self._on_update_timer)
        self._update_timer.start(interval)

    def stop_update_timer(self):
        """停止更新定时器."""
        if self._update_timer and self._update_timer.isActive():
            self._update_timer.stop()

    def _on_update_timer(self):
        """定时器触发回调 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def update_data(self, data: Dict[str, Any]):
        """更新数据 - 子类可以重写."""
        self.data_updated.emit(data)

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """窗口大小改变事件."""
        super().resizeEvent(event)
        if self._is_initialized:
            self.on_resize(event.size())

    def on_resize(self, _size):  # noqa: U101
        """窗口大小改变回调 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """窗口关闭事件."""
        # 停止定时器
        self.stop_update_timer()

        # 调用子类清理方法
        self.on_close()

        super().closeEvent(event)

    def on_close(self):
        """关闭回调 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def set_title(self, title: str):
        """设置窗口标题."""
        self.title = title
        parent = self.parent()
        if isinstance(parent, QWidget) and hasattr(parent, "setWindowTitle"):
            parent.setWindowTitle(title)

    def get_title(self) -> str:
        """获取窗口标题."""
        return self.title

    def is_initialized(self) -> bool:
        """检查是否已初始化."""
        return self._is_initialized

    def retranslate_ui(self):
        """重新翻译界面 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def apply_theme(self, _theme_manager):  # noqa: U101
        """应用主题 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def save_settings(self) -> Dict[str, Any]:
        """保存设置 - 子类可以重写."""
        return {}

    def load_settings(self, _settings: Dict[str, Any]):  # noqa: U101
        """加载设置 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def reset_settings(self):
        """重置设置 - 子类可以重写."""
        # pylint: disable=unnecessary-pass
        pass

    def export_data(self, _format_type: str = "json") -> Optional[str]:  # noqa: U101
        """导出数据 - 子类可以重写."""
        return None

    def import_data(self, _data: str, _format_type: str = "json") -> bool:  # noqa: U101
        """导入数据 - 子类可以重写."""
        return False

    def get_status_info(self) -> Dict[str, Any]:
        """获取状态信息 - 子类可以重写."""
        return {
            "name": self.__class__.__name__,
            "initialized": self._is_initialized,
            "title": self.title,
        }
