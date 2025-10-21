# -*- coding: utf-8 -*-
"""Type stubs for vnpy_tts package."""

from typing import Any
from vnpy.trader.gateway import BaseGateway

class TtsGateway(BaseGateway):
    """TTS Gateway class stub."""
    def __init__(self, event_engine: Any, gateway_name: str = "TTS") -> None: ...

def __getattr__(name: str) -> Any: ...  # noqa: U100
