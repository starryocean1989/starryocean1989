# -*- coding: utf-8 -*-
"""
Setup configuration for the data_module_vnpy package.

This module provides the setup configuration for the VnPy data module,
which handles data operations and integration with VnPy trading platform.
"""

from setuptools import find_packages, setup

setup(
    name="data_module_vnpy",
    version="1.0.0",
    description="Data Module for VnPy",
    author="StarryFinance",
    packages=find_packages(),
    install_requires=[
        "vnpy",
        "pandas",
        "numpy",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
