# -*- coding: utf-8 -*-
"""
native_collections C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_collections_module = Extension(
    'native_collections',
    sources=[
        'native_collections.c',
        'lru_cache.c',
        'priority_queue.c',
        'match_cache.c',
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_collections',
    version='1.0.0',
    description='High-performance LRU cache and priority queue for Windows',
    author='Terminal Project',
    ext_modules=[native_collections_module],
    platforms=['win32'],
    python_requires='>=3.8',
)

