# -*- coding: utf-8 -*-
"""Type stubs for vnpy_sopt package."""

from typing import Any
from vnpy.trader.gateway import BaseGateway

class SoptGateway(BaseGateway):
    """Sopt Gateway class stub."""
    def __init__(self, event_engine: Any, gateway_name: str = "SOPT") -> None: ...

def __getattr__(name: str) -> Any: ...  # noqa: U100
