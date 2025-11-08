# -*- coding: utf-8 -*-
"""
native_async 扩展构建脚本。
"""

from __future__ import annotations

import os
from pathlib import Path

from setuptools import Extension, setup


def _get_pybind_include(user: bool) -> str:
    import pybind11

    return pybind11.get_include(user)


current_dir = Path(__file__).resolve().parent

ext_modules = [
    Extension(
        "async_reduce",
        sources=[str(current_dir / "async_reduce.cpp")],
        include_dirs=[_get_pybind_include(False), _get_pybind_include(True)],
        language="c++",
        extra_compile_args=["/std:c++17"] if os.name == "nt" else ["-std=c++17"],
    )
]


setup(
    name="native_async",
    version="0.1.0",
    description="异步任务结果归约扩展",
    ext_modules=ext_modules,
    zip_safe=False,
)


