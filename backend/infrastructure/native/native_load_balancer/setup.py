# -*- coding: utf-8 -*-
from __future__ import annotations

from setuptools import Extension, setup

module = Extension(
    "backend.infrastructure.native.native_load_balancer.load_balancer",
    sources=["load_balancer.c"],
    extra_compile_args=["/O2", "/std:c17", "/utf-8"],
)


setup(
    name="native_load_balancer",
    version="0.1.0",
    description="High performance load balancer optimizer",
    ext_modules=[module],
)


