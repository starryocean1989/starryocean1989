# -*- coding: utf-8 -*-
"""
IPC异步通信 C扩展构建配置

基于 Windows Named Pipe + IOCP 实现真正的异步跨进程通信，不使用线程池。

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
ipc_async_module = Extension(
    'ipc_async',
    sources=['ipc_async.c'],
    libraries=['kernel32'],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    extra_compile_args=['/std:c11', '/W3'],  # C11标准，警告级别3
    extra_link_args=[],
    include_dirs=['..'],
)

setup(
    name='native_ipc',
    version='1.0.0',
    description='Native IOCP async IPC for Windows',
    long_description="""
    Native IOCP (I/O Completion Port) async IPC implementation for Windows.

    This extension provides true asynchronous inter-process communication 
    without using thread pools. It directly uses Windows Named Pipe + IOCP API 
    for maximum performance.

    Requirements:
    - Windows platform only
    - Visual Studio Build Tools or Visual Studio
    - Windows SDK
    - Python 3.8+
    """,
    author='Terminal Project',
    author_email='',
    url='',
    ext_modules=[ipc_async_module],
    py_modules=['async_ipc', 'ipc_loop'],
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
    keywords='asyncio iocp windows async ipc named-pipe inter-process-communication',
)
