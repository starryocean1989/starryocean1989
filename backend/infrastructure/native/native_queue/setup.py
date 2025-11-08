from setuptools import Extension, setup

extension = Extension("_native_queue", sources=["native_queue.c"], extra_compile_args=["/O2"])

setup(
    name="native_queue",
    version="0.1.0",
    description="Native queue component",
    ext_modules=[extension],
)

