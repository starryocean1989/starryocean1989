# -*- coding: utf-8 -*-
"""
native_compute C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_compute_module = Extension(
    'native_compute',
    sources=[
        'native_compute.c',
        'batch_compute.c',
        'batch_hash.c',
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_compute',
    version='1.0.0',
    description='Batch numerical operations and hash computation for Windows',
    author='Terminal Project',
    ext_modules=[native_compute_module],
    platforms=['win32'],
    python_requires='>=3.8',
)

