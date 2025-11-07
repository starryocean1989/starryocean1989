# -*- coding: utf-8 -*-
"""
native_netprobe C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_netprobe_module = Extension(
    'native_netprobe',
    sources=[
        'native_netprobe.c',
        'netprobe.c',
    ],
    libraries=['ws2_32', 'kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3', '/O2'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_netprobe',
    version='1.0.0',
    description='Native network probe for fast batch connectivity testing (Windows)',
    author='Terminal Project',
    ext_modules=[native_netprobe_module],
    platforms=['win32'],
    python_requires='>=3.8',
)
