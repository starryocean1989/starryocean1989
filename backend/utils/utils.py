# -*- coding: utf-8 -*-
"""
通用工具函数.

提供响应格式、数据验证、缓存等功能。
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ==================== 响应格式化 ====================


def success_response(data: Any = None, message: str = "success") -> Dict[str, Any]:
    """
    成功响应格式.

    Args:
        data: 返回数据
        message: 消息

    Returns:
        响应字典
    """
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }


def error_response(
    message: str, error_code: Optional[str] = None, data: Any = None
) -> Dict[str, Any]:
    """
    错误响应格式.

    Args:
        message: 错误消息
        error_code: 错误代码
        data: 附加数据

    Returns:
        响应字典
    """
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }


# ==================== 数据验证 ====================


def validate_required_fields(data: Dict[str, Any], required_fields: list) -> tuple:
    """
    验证必填字段.

    Args:
        data: 数据字典
        required_fields: 必填字段列表

    Returns:
        (是否有效, 错误消息)
    """
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        return False, f"缺少必填字段: {', '.join(missing_fields)}"

    return True, ""


def validate_symbol(symbol: str) -> bool:
    """验证品种代码格式."""
    if not symbol or len(symbol) < 2 or len(symbol) > 20:
        return False
    return True


def validate_date_range(start_date: Optional[datetime], end_date: Optional[datetime]) -> tuple:
    """验证日期范围."""
    if start_date and end_date and start_date > end_date:
        return False, "开始日期不能晚于结束日期"
    return True, ""


# ==================== 简单缓存 ====================


class SimpleCache:
    """简单的内存缓存."""

    def __init__(self, ttl_seconds: int = 300):
        """
        初始化缓存.

        Args:
            ttl_seconds: 缓存过期时间（秒）
        """
        self._cache: Dict[str, tuple] = {}  # key -> (value, expire_time)
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值."""
        if key not in self._cache:
            return None

        value, expire_time = self._cache[key]

        # 检查是否过期
        if datetime.now() > expire_time:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """设置缓存值."""
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expire_time = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (value, expire_time)

    def delete(self, key: str) -> bool:
        """删除缓存."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """清空缓存."""
        self._cache.clear()

    def size(self) -> int:
        """获取缓存大小."""
        return len(self._cache)


# ==================== 其他工具 ====================


def format_number(value: float, precision: int = 2) -> str:
    """格式化数字."""
    return f"{value:.{precision}f}"


def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


__all__ = [
    "success_response",
    "error_response",
    "validate_required_fields",
    "validate_symbol",
    "validate_date_range",
    "SimpleCache",
    "format_number",
    "truncate_string",
]
