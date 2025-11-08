# -*- coding: utf-8 -*-
"""
native_symbol_index 扩展构建脚本。
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
        "symbol_index",
        sources=[str(current_dir / "symbol_index.cpp")],
        include_dirs=[_get_pybind_include(False), _get_pybind_include(True)],
        language="c++",
        extra_compile_args=["/std:c++17"] if os.name == "nt" else ["-std=c++17"],
    )
]


setup(
    name="native_symbol_index",
    version="0.1.0",
    description="品种索引原生扩展",
    ext_modules=ext_modules,
    zip_safe=False,
)


