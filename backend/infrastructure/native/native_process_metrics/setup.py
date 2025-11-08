from pathlib import Path
from setuptools import Extension, setup


ROOT = Path(__file__).resolve().parent

module = Extension(
    name="process_metrics",
    sources=[str(ROOT / "process_metrics.c")],
    libraries=["psapi", "iphlpapi"],
)

setup(
    name="native_process_metrics",
    version="0.1.0",
    description="Windows process metrics extension",
    ext_modules=[module],
)


