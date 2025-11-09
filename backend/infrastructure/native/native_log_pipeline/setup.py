from pathlib import Path
from setuptools import Extension, setup


ROOT = Path(__file__).resolve().parent

module = Extension(
    name="pipeline",
    sources=[str(ROOT / "pipeline.c")],
    define_macros=[('PY_SSIZE_T_CLEAN', None)],
    include_dirs=['..'],
)

setup(
    name="native_log_pipeline",
    version="0.1.0",
    description="Native log pipeline buffer",
    ext_modules=[module],
)


