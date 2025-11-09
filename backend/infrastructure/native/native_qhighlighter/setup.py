# -*- coding: utf-8 -*-
"""
native_qhighlighter 扩展编译脚本。

依赖 pybind11 与 Qt 头文件。若系统装有 PySide6，则默认从 PySide6 获取 include 路径。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from setuptools import Extension, setup


def _get_pybind_include(user: bool) -> str:
    import pybind11

    return pybind11.get_include(user)


def _qt_include_dirs() -> list[str]:
    include_dirs: list[str] = []

    try:
        import PySide6

        qt_root = Path(PySide6.__file__).resolve().parent
        include_dirs.append(str(qt_root / "include"))
    except Exception:
        pass

    return include_dirs


current_dir = Path(__file__).resolve().parent

ext_modules = [
    Extension(
        "native_qhighlighter_core",
        sources=[str(current_dir / "native_qhighlighter.cpp")],
        include_dirs=[
            _get_pybind_include(False),
            _get_pybind_include(True),
        ]
        + _qt_include_dirs(),
        language="c++",
        extra_compile_args=["/std:c++17"] if os.name == "nt" else ["-std=c++17"],
    )
]


setup(
    name="native_qhighlighter",
    version="0.1.0",
    author="terminal_v0.50",
    description="Qt/C++ 加速的代码高亮器",
    ext_modules=ext_modules,
    zip_safe=False,
)


