# -*- coding: utf-8 -*-
"""Type stubs for vnpy_algotrading package."""

from typing import Any

def __getattr__(name: str) -> Any: ...  # noqa: U100

class AlgoEngine:
    """Algorithm trading engine."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...  # noqa: U100
    def __getattr__(self, name: str) -> Any: ...  # noqa: U100
