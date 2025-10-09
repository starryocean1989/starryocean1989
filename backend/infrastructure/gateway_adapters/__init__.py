# -*- coding: utf-8 -*-
"""
网关适配器包.

提供各种网关的适配器实现，使其符合vnpy Gateway接口规范。
"""

from .paperaccount_gateway_adapter import PaperAccountGateway
from .tradex_gateway_adapter import TradeXGateway

__all__ = ["PaperAccountGateway", "TradeXGateway"]
