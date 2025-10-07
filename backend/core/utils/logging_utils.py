# -*- coding: utf-8 -*-
"""
日志工具模块.

提供统一的日志配置和管理功能
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class LoggerMixin:
    """日志混合类."""

    @property
    def logger(self) -> logging.Logger:
        """获取日志器."""
        name = self.__class__.__name__
        return logging.getLogger(name)


def setup_logging(name: str = "terminal", level: str = "INFO",
                  log_file: Optional[str] = None) -> logging.Logger:
    """
    设置日志配置.

    Args:
        name: 日志器名称
        level: 日志级别
        log_file: 日志文件路径

    Returns:
        配置好的日志器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定）
    if log_file:
        try:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - '
                '%(filename)s:%(lineno)d - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning("无法创建日志文件处理器: %s", e)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取日志器."""
    return logging.getLogger(name)
