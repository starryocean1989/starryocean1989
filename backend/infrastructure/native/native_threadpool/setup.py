from setuptools import Extension, setup

extension = Extension(
    "_native_threadpool",
    sources=["native_threadpool.c"],
    extra_compile_args=["/O2"],
)

setup(
    name="native_threadpool",
    version="0.1.0",
    description="Native thread pool component",
    ext_modules=[extension],
)

