# -*- coding: utf-8 -*-
"""
周期性错误计数器.

功能：
1. 识别相同错误（按异常类型+消息前50字符）
2. 首次出现：详细输出到Terminal和数据库
3. 后续出现：仅计数，Terminal输出简要信息
4. 里程碑记录：每10次记录一次数据库日志
"""
from datetime import datetime
from threading import Lock
from typing import Dict, Optional, Tuple


class ErrorCounter:
    """周期性错误计数器（单例模式）."""

    _instance: Optional["ErrorCounter"] = None
    _lock = Lock()

    def __new__(cls):
        """单例模式实现."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化错误计数器."""
        if hasattr(self, "_initialized"):
            return

        self._errors: Dict[str, int] = {}  # {error_key: count}
        self._first_seen: Dict[str, datetime] = {}  # {error_key: first_time}
        self._last_milestone: Dict[str, int] = {}  # {error_key: last_milestone_count}
        self._data_lock = Lock()
        self._initialized = True

    def _generate_error_key(self, exc_type: str, message: str) -> str:
        """
        生成错误唯一标识.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            错误唯一标识
        """
        # 取消息前50字符作为标识（避免参数变化导致误判为不同错误）
        message_prefix = message[:50] if message else ""
        return f"{exc_type}:{message_prefix}"

    def record_error(
        self, exc_type: str, message: str, traceback_str: Optional[str] = None  # noqa: ARG002
    ) -> Tuple[bool, int, bool]:
        """
        记录错误.

        Args:
            exc_type: 异常类型名称
            message: 错误消息
            traceback_str: 堆栈跟踪字符串（可选）

        Returns:
            (是否需要详细输出, 当前计数, 是否达到里程碑)
        """
        error_key = self._generate_error_key(exc_type, message)

        with self._data_lock:
            # 首次出现
            if error_key not in self._errors:
                self._errors[error_key] = 1
                self._first_seen[error_key] = datetime.now()
                self._last_milestone[error_key] = 0
                return (True, 1, True)  # 需要详细输出，计数为1，算作里程碑

            # 后续出现
            self._errors[error_key] += 1
            current_count = self._errors[error_key]

            # 检查是否达到里程碑（每10次）
            last_milestone = self._last_milestone.get(error_key, 0)
            is_milestone = (current_count % 10 == 0) and (current_count > last_milestone)

            if is_milestone:
                self._last_milestone[error_key] = current_count

            return (False, current_count, is_milestone)

    def get_count(self, exc_type: str, message: str) -> int:
        """
        获取错误计数.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            错误计数
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            return self._errors.get(error_key, 0)

    def get_first_seen(self, exc_type: str, message: str) -> Optional[datetime]:
        """
        获取错误首次出现时间.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            首次出现时间，如果不存在返回None
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            return self._first_seen.get(error_key)

    def should_output_detail(self, exc_type: str, message: str) -> bool:
        """
        判断是否需要详细输出.

        Args:
            exc_type: 异常类型名称
            message: 错误消息

        Returns:
            是否需要详细输出（首次或每10次）
        """
        error_key = self._generate_error_key(exc_type, message)
        with self._data_lock:
            count = self._errors.get(error_key, 0)
            if count == 0:
                return True  # 首次
            if count % 10 == 0:
                return True  # 里程碑
            return False

    def reset(self) -> None:
        """重置所有计数器（用于测试或手动重置）."""
        with self._data_lock:
            self._errors.clear()
            self._first_seen.clear()
            self._last_milestone.clear()

    def get_summary(self) -> Dict[str, int]:
        """
        获取所有错误的摘要.

        Returns:
            错误摘要字典 {error_key: count}
        """
        with self._data_lock:
            return self._errors.copy()


# 全局单例实例
_error_counter: Optional[ErrorCounter] = None


def get_error_counter() -> ErrorCounter:
    """
    获取全局错误计数器实例.

    Returns:
        ErrorCounter实例
    """
    global _error_counter  # noqa: PLW0603
    if _error_counter is None:
        _error_counter = ErrorCounter()
    return _error_counter
