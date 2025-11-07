# -*- coding: utf-8 -*-
"""
native_finance_ops C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_finance_ops_module = Extension(
    'native_finance_ops',
    sources=[
        'native_finance_ops.c',
        'finance_metrics.c',
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3', '/O2'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_finance_ops',
    version='1.0.0',
    description='Native financial operations for portfolio analysis (Windows)',
    author='Terminal Project',
    ext_modules=[native_finance_ops_module],
    platforms=['win32'],
    python_requires='>=3.8',
)
