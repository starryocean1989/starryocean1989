# -*- coding: utf-8 -*-
"""
native_gil C扩展构建配置

底层GIL管理工具，提供多线程绕过GIL的能力。

编译说明：
1. 需要Windows平台
2. 需要Visual Studio Build Tools或完整Visual Studio
3. 需要Windows SDK
4. 需要Python开发头文件（通常包含在Python安装中）

编译命令：
    python setup.py build_ext --inplace

安装命令：
    python setup.py install
"""

import platform
import sys
from setuptools import setup, Extension

# 仅Windows平台支持
if platform.system() != "Windows":
    print("Warning: This extension only supports Windows platform")
    sys.exit(1)

# C扩展定义
native_gil_module = Extension(
    'native_gil',
    sources=[
        'native_gil.c',
        'gil_utils.c',
        'task_executor.c',
        'thread_safe.c',
        'lock_free.c',
        'high_perf_event.c'
    ],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],  # C11标准，警告级别3
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_gil',
    version='1.0.0',
    description='Native GIL management and thread-safe utilities for Windows',
    long_description="""
    Native GIL management and thread-safe utilities for Windows.

    This extension provides:
    - GIL release/restore functions
    - CPU-intensive task executor with multi-threading support
    - Thread-safe data structures (Queue, Counter)

    Requirements:
    - Windows platform only
    - Visual Studio Build Tools or Visual Studio
    - Windows SDK
    - Python 3.8+
    """,
    author='Terminal Project',
    author_email='',
    url='',
    ext_modules=[native_gil_module],
    py_modules=[],
    platforms=['win32'],
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: C',
        'Operating System :: Microsoft :: Windows',
        'Topic :: System :: Operating System',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='gil thread-safe windows async parallel cpu-intensive',
)

