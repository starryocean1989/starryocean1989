# -*- coding: utf-8 -*-

from typing import Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Category:
    """数据分类"""
    name: str
    code: str
    description: Optional[str] = None


@dataclass
class Quote:
    """行情数据"""
    symbol: str
    price: float
    volume: int
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass
class RoutingInfo:
    """路由信息"""
    source: str
    destination: str
    priority: int = 0


__all__ = ["Category", "Quote", "RoutingInfo"]
