# -*- coding: utf-8 -*-
from pathlib import Path

from setuptools import Extension, setup


ROOT = Path(__file__).resolve().parent

module = Extension(
    name="conversion",
    sources=[str(ROOT / "conversion.c")],
)

setup(
    name="native_vnpy_conversion",
    version="1.0.0",
    description="High performance batch converter for VnPy style data objects",
    ext_modules=[module],
)


