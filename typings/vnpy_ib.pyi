# -*- coding: utf-8 -*-
"""Type stubs for vnpy_ib package."""

from typing import Any
from vnpy.trader.gateway import BaseGateway

class IbGateway(BaseGateway):
    """Interactive Brokers Gateway class stub."""
    def __init__(self, event_engine: Any, gateway_name: str = "IB") -> None: ...

def __getattr__(name: str) -> Any: ...  # noqa: U100
