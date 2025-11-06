# -*- coding: utf-8 -*-
"""
native_serialization C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_serialization_module = Extension(
    'native_serialization',
    sources=[
        'native_serialization.c',
        'batch_serialize.c',
        'zero_copy_serialize.c',
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_serialization',
    version='1.0.0',
    description='Native batch and zero-copy serialization for Windows',
    long_description="""Native serialization extension for Windows.""",
    author='Terminal Project',
    ext_modules=[native_serialization_module],
    py_modules=[],
    platforms=['win32'],
    python_requires='>=3.8',
)

