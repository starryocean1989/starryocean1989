# -*- coding: utf-8 -*-
"""native_statistics C extension build configuration."""

from __future__ import annotations

import platform
import sys
from setuptools import Extension, setup

if platform.system() != "Windows":
    print("Warning: native_statistics only supports the Windows platform")
    sys.exit(1)

native_statistics_module = Extension(
    "native_statistics",
    sources=[
        "native_statistics.c",
    ],
    define_macros=[("PY_SSIZE_T_CLEAN", None)],
    extra_compile_args=["/std:c11", "/O2", "/W3"],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name="native_statistics",
    version="1.0.0",
    description="Streaming statistics with native sliding window",
    author="Terminal Project",
    ext_modules=[native_statistics_module],
    platforms=["win32"],
    python_requires=">=3.8",
)
