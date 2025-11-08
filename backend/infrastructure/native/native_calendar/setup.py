# -*- coding: utf-8 -*-
from setuptools import setup, Extension
import pybind11

native_calendar_module = Extension(
    "native_calendar._native_calendar",
    sources=["calendar.cpp"],
    include_dirs=[pybind11.get_include()],
    language="c++",
    extra_compile_args=["/std:c++17"],
)

setup(
    name="native_calendar",
    version="0.1.0",
    packages=["native_calendar"],
    package_dir={"native_calendar": "."},
    package_data={"native_calendar": ["sse_calendar.bin"]},
    ext_modules=[native_calendar_module],
    zip_safe=False,
)
