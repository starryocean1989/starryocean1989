from setuptools import Extension, setup

extension = Extension(
    "_native_scheduler",
    sources=["native_scheduler.c"],
    extra_compile_args=["/O2"],
)

setup(
    name="native_scheduler",
    version="0.1.0",
    description="Native scheduler core",
    ext_modules=[extension],
)

