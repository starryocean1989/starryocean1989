# -*- coding: utf-8 -*-
"""
数据引擎模型定义模块.

提供数据引擎所需的基础数据模型，包括分类、行情数据和路由信息等。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Category:
    """数据分类."""

    name: str
    code: str
    description: Optional[str] = None


@dataclass
class Quote:
    """行情数据."""

    symbol: str
    price: float
    volume: int
    timestamp: Any
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass
class RoutingInfo:
    """路由信息."""

    source: str
    destination: str
    priority: int = 0


__all__ = ["Category", "Quote", "RoutingInfo"]
