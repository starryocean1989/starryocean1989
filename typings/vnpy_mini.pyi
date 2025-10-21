# -*- coding: utf-8 -*-
"""Type stubs for vnpy_mini package."""

from typing import Any
from vnpy.trader.gateway import BaseGateway

class MiniGateway(BaseGateway):
    """Mini Gateway class stub."""
    def __init__(self, event_engine: Any, gateway_name: str = "MINI") -> None: ...

def __getattr__(name: str) -> Any: ...  # noqa: U100
