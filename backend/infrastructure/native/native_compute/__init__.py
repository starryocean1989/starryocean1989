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
        from . import native_compute as _native
    except ImportError:
        COMPUTE_AVAILABLE = False
        PREFIX_SUM_AVAILABLE = False
        __all__ = ["COMPUTE_AVAILABLE", "PREFIX_SUM_AVAILABLE"]

        def _raise_error():
            raise ImportError("Compute C extension not compiled")

        batch_compute = batch_hash = batch_get_price = batch_validate_iso_dates = batch_compare_dates = prefix_sum_scale = _raise_error  # type: ignore
    else:
        batch_compute = getattr(_native, "batch_compute", None)
        batch_hash = getattr(_native, "batch_hash", None)
        batch_get_price = getattr(_native, "batch_get_price", None)
        batch_validate_iso_dates = getattr(_native, "batch_validate_iso_dates", None)
        batch_compare_dates = getattr(_native, "batch_compare_dates", None)
        prefix_sum_scale = getattr(_native, "prefix_sum_scale", None)

        essential_funcs = [batch_compute, batch_hash, batch_get_price]
        COMPUTE_AVAILABLE = all(callable(func) for func in essential_funcs)
        PREFIX_SUM_AVAILABLE = callable(prefix_sum_scale)

        if not COMPUTE_AVAILABLE:
            def _raise_error():
                raise ImportError("Compute C extension not compiled correctly")

            batch_compute = batch_hash = batch_get_price = batch_validate_iso_dates = batch_compare_dates = prefix_sum_scale = _raise_error  # type: ignore
            PREFIX_SUM_AVAILABLE = False

        if not PREFIX_SUM_AVAILABLE:
            def prefix_sum_scale(*_args, **_kwargs):  # type: ignore
                raise ImportError("prefix_sum_scale not available in native_compute")

        __all__ = [
            "batch_compute",
            "batch_hash",
            "batch_get_price",
            "batch_validate_iso_dates",
            "batch_compare_dates",
            "prefix_sum_scale",
            "COMPUTE_AVAILABLE",
            "PREFIX_SUM_AVAILABLE",
        ]
else:
    COMPUTE_AVAILABLE = False
    PREFIX_SUM_AVAILABLE = False
    __all__ = ["COMPUTE_AVAILABLE", "PREFIX_SUM_AVAILABLE"]

    def _raise_error():
        raise RuntimeError("Compute extension only supports Windows")

    batch_compute = batch_hash = batch_get_price = batch_validate_iso_dates = batch_compare_dates = prefix_sum_scale = _raise_error  # type: ignore

__version__ = "1.0.0"
