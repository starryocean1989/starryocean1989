# -*- coding: utf-8 -*-
"""Type stubs for vnpy_portfoliostrategy package."""

from typing import Any

def __getattr__(name: str) -> Any: ...  # noqa: U100

class PortfolioEngine:
    """Portfolio strategy engine."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...  # noqa: U100
    def __getattr__(self, name: str) -> Any: ...  # noqa: U100
