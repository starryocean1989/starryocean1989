# -*- coding: utf-8 -*-
"""
RPC方法定义
"""

from enum import IntEnum

class RPCMethod(IntEnum):
    """RPC方法ID枚举"""
    GET_KLINE_DATA = 1
    GET_STOCK_LIST = 2
    GET_CACHE_STATUS = 3
    CALCULATE_INDICATORS = 4
    SCAN_DATA_QUALITY = 5

# 方法名到ID的映射
METHOD_ID_MAP = {
    "get_kline_data": RPCMethod.GET_KLINE_DATA,
    "get_stock_list": RPCMethod.GET_STOCK_LIST,
    "get_cache_status": RPCMethod.GET_CACHE_STATUS,
    "calculate_indicators": RPCMethod.CALCULATE_INDICATORS,
    "scan_data_quality": RPCMethod.SCAN_DATA_QUALITY,
}

# ID到方法名的映射
ID_METHOD_MAP = {v: k for k, v in METHOD_ID_MAP.items()}

def get_method_id(method_name: str) -> int:
    """根据方法名获取方法ID"""
    return METHOD_ID_MAP.get(method_name, 0)

def get_method_name(method_id: int) -> str:
    """根据方法ID获取方法名"""
    return ID_METHOD_MAP.get(method_id)