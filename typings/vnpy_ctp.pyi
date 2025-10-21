# -*- coding: utf-8 -*-
"""Type stubs for vnpy_ctp package."""

from typing import Any
from vnpy.trader.gateway import BaseGateway

class CtpGateway(BaseGateway):
    """CTP Gateway class stub."""
    def __init__(self, event_engine: Any, gateway_name: str = "CTP") -> None: ...

def __getattr__(name: str) -> Any: ...  # noqa: U100
