# -*- coding: utf-8 -*-
"""
原生数值计算模块

提供批量数值运算和批量哈希计算功能。
"""

import platform
import logging

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        from .native_compute import (
            batch_compute,
            batch_hash,
            batch_get_price,
            batch_validate_iso_dates,
            batch_compare_dates,
        )

        COMPUTE_AVAILABLE = True
        __all__ = [
            "batch_compute",
            "batch_hash",
            "batch_get_price",
            "batch_validate_iso_dates",
            "batch_compare_dates",
            "COMPUTE_AVAILABLE",
        ]
    except ImportError:
        COMPUTE_AVAILABLE = False
        __all__ = ["COMPUTE_AVAILABLE"]

        def _raise_error():
            raise ImportError("Compute C extension not compiled")

        batch_compute = batch_hash = batch_get_price = _raise_error
else:
    COMPUTE_AVAILABLE = False
    __all__ = ["COMPUTE_AVAILABLE"]

    def _raise_error():
        raise RuntimeError("Compute extension only supports Windows")

    batch_compute = batch_hash = batch_get_price = _raise_error

__version__ = "1.0.0"
