# -*- coding: utf-8 -*-

"""
数据引擎适配器模块

本模块提供各种数据源的适配器实现,
支持不同类型的数据源接入.
"""

__version__ = "1.0.0"

# 支持的数据源类型
SUPPORTED_SOURCES = ["sina", "tdx", "ths", "custom"]


def get_supported_sources() -> list[str]:
    """
    获取支持的数据源类型列表

    Returns:
        list[str]: 支持的数据源类型
    """
    return SUPPORTED_SOURCES.copy()


__all__ = ["get_supported_sources", "SUPPORTED_SOURCES"]
