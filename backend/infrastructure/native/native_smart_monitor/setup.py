# -*- coding: utf-8 -*-
"""native_smart_monitor C 扩展构建配置."""

from __future__ import annotations

import pathlib
from setuptools import Extension, setup

ROOT = pathlib.Path(__file__).resolve().parent

native_smart_monitor_module = Extension(
    "native_smart_monitor",
    sources=[str(ROOT / "native_smart_monitor.c")],
    include_dirs=[],
    libraries=["kernel32"],
    extra_compile_args=[
        "/std:c11",
        "/O2",
        "/Wall",
        "/DWIN32_LEAN_AND_MEAN",
        "/D_CRT_SECURE_NO_WARNINGS",
        "/DUNICODE",
        "/D_UNICODE",
        "/D_WIN32_WINNT=0x0A00",
    ],
)

setup(
    name="native_smart_monitor",
    version="1.0.0",
    description="Native SMART monitor helpers",
    ext_modules=[native_smart_monitor_module],
)


