from setuptools import Extension, setup

extension = Extension(
    "_native_scheduler",
    sources=["native_scheduler.c"],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    include_dirs=['..'],
    libraries=['kernel32'],
    extra_compile_args=["/std:c11", "/W3", "/O2"],
)

setup(
    name="native_scheduler",
    version="0.1.0",
    description="Native scheduler core",
    ext_modules=[extension],
)

