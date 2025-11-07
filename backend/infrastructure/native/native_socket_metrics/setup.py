# -*- coding: utf-8 -*-
"""native_socket_metrics C 扩展构建脚本."""

import platform
import sys
from setuptools import Extension, setup


if platform.system() != "Windows":
    print("Warning: native_socket_metrics only supports Windows platform")
    sys.exit(1)


socket_metrics_module = Extension(
    "socket_metrics",
    sources=[
        "socket_metrics.c",
    ],
    libraries=["iphlpapi", "ws2_32"],
    define_macros=[("PY_SSIZE_T_CLEAN", None)],
    extra_compile_args=["/std:c11", "/W3"],
)


setup(
    name="native_socket_metrics",
    version="1.0.0",
    description="Native socket metrics collector for Windows",
    author="Terminal Project",
    ext_modules=[socket_metrics_module],
    platforms=["win32"],
    python_requires=">=3.8",
)


