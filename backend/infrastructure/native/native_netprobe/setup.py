# -*- coding: utf-8 -*-
"""
native_netprobe C 扩展构建配置
"""

from pathlib import Path
import platform
import sys
from setuptools import Extension, setup

if platform.system() != "Windows":
    print("Warning: native_netprobe only supports Windows platform")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent

# netprobe C扩展模块（独立完整实现）
netprobe_module = Extension(
    "netprobe",
    sources=[str(ROOT / "netprobe.c")],
    libraries=["ws2_32", "kernel32", "Mswsock"],
    extra_compile_args=["/ std:c11", "/W3", "/O2"],
)

setup(
    name="native_netprobe",
    version="1.0.0",
    description="Native network probe for fast batch connectivity testing (Windows)",
    author="Terminal Project",
    ext_modules=[netprobe_module],
    platforms=["win32"],
    python_requires=">=3.8",
)
