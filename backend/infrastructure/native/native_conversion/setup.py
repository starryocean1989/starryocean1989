# -*- coding: utf-8 -*-
"""
native_conversion C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_conversion_module = Extension(
    'native_conversion',
    sources=[
        'native_conversion.c',
        'batch_convert.c',
        'batch_string.c',
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_conversion',
    version='1.0.0',
    description='Native batch type conversion and string operations for Windows',
    author='Terminal Project',
    ext_modules=[native_conversion_module],
    platforms=['win32'],
    python_requires='>=3.8',
)

