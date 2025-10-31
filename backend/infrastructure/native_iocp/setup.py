# -*- coding: utf-8 -*-
"""
IOCP异步文件I/O C扩展构建配置

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
iocp_file_module = Extension(
    'iocp_file',
    sources=['iocp_file.c'],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],  # C11标准，警告级别3
    extra_link_args=[],
    include_dirs=[],
)

setup(
    name='native_iocp',
    version='1.0.0',
    description='Native IOCP async file I/O for Windows',
    long_description="""
    Native IOCP (I/O Completion Port) async file I/O implementation for Windows.

    This extension provides true asynchronous file I/O without using thread pools.
    It directly uses Windows IOCP API for maximum performance.

    Requirements:
    - Windows platform only
    - Visual Studio Build Tools or Visual Studio
    - Windows SDK
    - Python 3.8+
    """,
    author='Terminal Project',
    author_email='',
    url='',
    ext_modules=[iocp_file_module],
    py_modules=['async_iocp_file', 'iocp_loop', 'compat'],
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
    keywords='asyncio iocp windows async file i/o',
)

