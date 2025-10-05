# -*- coding: utf-8 -*-
"""
数据引擎工具模块.

提供数据引擎相关的通用工具函数,包括日志配置,数据验证和格式化等功能.
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """
    设置日志配置.

    Args:
        level: 日志级别,默认INFO
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def validate_symbol(symbol: str) -> bool:
    """
    验证证券代码格式.

    Args:
        symbol: 证券代码

    Returns:
        bool: 是否有效
    """
    if not symbol or not isinstance(symbol, str):
        return False

    # 简单的验证规则,可以根据需要扩展
    return len(symbol.strip()) > 0


def format_datetime(dt: str) -> str:
    """
    格式化日期时间字符串.

    Args:
        dt: 日期时间字符串

    Returns:
        str: 格式化后的字符串
    """
    # 这里可以添加更复杂的格式化逻辑
    return dt.strip()
