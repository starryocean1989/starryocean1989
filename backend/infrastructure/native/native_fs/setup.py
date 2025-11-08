# -*- coding: utf-8 -*-
from __future__ import annotations

from setuptools import Extension, setup

module = Extension(
    "backend.infrastructure.native.native_fs.fs_watcher",
    sources=["fs_watcher.c"],
    libraries=["kernel32"],
    extra_compile_args=["/O2", "/std:c17", "/utf-8"],
)


setup(
    name="native_fs",
    version="0.1.0",
    description="High performance directory watcher for terminal_v0.50",
    ext_modules=[module],
)


