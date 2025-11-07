# -*- coding: utf-8 -*-
"""native_dataframe_ops C 扩展构建脚本."""

import platform
import sys
from setuptools import Extension, setup


if platform.system() != "Windows":
    print("Warning: native_dataframe_ops only supports Windows platform")
    sys.exit(1)


dataframe_ops_module = Extension(
    "dataframe_ops",
    sources=[
        "dataframe_ops.c",
    ],
    define_macros=[("PY_SSIZE_T_CLEAN", None)],
    extra_compile_args=["/std:c11", "/W3"],
)


setup(
    name="native_dataframe_ops",
    version="1.0.0",
    description="Native dataframe helper functions",
    author="Terminal Project",
    ext_modules=[dataframe_ops_module],
    platforms=["win32"],
    python_requires=">=3.8",
)


