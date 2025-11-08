# -*- coding: utf-8 -*-
"""native_indicator C 扩展构建脚本."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from setuptools import Extension, setup


def _extra_compile_args() -> list[str]:
    if sys.platform.startswith("win"):
        args = ["/O2", "/std:c11"]
        if os.getenv("ENABLE_NATIVE_INDATOR_AVX2", "0") not in {"0", "false", "False"}:
            args.append("/arch:AVX2")
        return args

    args = ["-O3", "-std=c11"]
    if os.getenv("ENABLE_NATIVE_INDATOR_AVX2", "0") not in {"0", "false", "False"}:
        args.extend(["-mavx2", "-mfma"])
    return args


HERE = Path(__file__).parent.resolve()

setup(
    name="native_indicator_core",
    version="1.0.0",
    description="High performance financial indicator calculations (SMA/EMA/MACD/RSI)",
    ext_modules=[
        Extension(
            "native_indicator_core",
            sources=[str(HERE / "indicator.c")],
            extra_compile_args=_extra_compile_args(),
        )
    ],
)


