# -*- coding: utf-8 -*-
"""
native_rpc_bridge C扩展构建配置
"""

import platform
import sys
from setuptools import setup, Extension

if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

native_rpc_bridge_module = Extension(
    'native_rpc_bridge',
    sources=[
        'native_rpc_bridge.c',
        'rpc_bridge.c',
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3', '/O2'],
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_rpc_bridge',
    version='1.1.0',
    description='Native RPC bridge for zero-copy IPC communication (Windows)',
    author='Terminal Project',
    ext_modules=[native_rpc_bridge_module],
    platforms=['win32'],
    python_requires='>=3.8',
)
