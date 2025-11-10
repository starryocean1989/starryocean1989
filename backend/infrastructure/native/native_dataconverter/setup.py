from setuptools import setup
from setuptools import Extension
from setuptools.command.build_ext import build_ext

try:
    from pybind11.setup_helpers import Pybind11Extension
    HAVE_PYBIND11_HELPERS = True
except Exception:
    HAVE_PYBIND11_HELPERS = False


class BuildExt(build_ext):
    c_opts = {
        'msvc': ['/EHsc'],
        'unix': ['-O3'],
    }

    def build_extensions(self):
        ct = self.compiler.compiler_type
        opts = self.c_opts.get(ct, [])
        for ext in self.extensions:
            ext.extra_compile_args = opts
        super().build_extensions()


ext_cls = Pybind11Extension if HAVE_PYBIND11_HELPERS else Extension

ext_modules = [
    ext_cls(
        "native_dataconverter",
        ["dataconverter.cpp"],
        include_dirs=['..'],
        language="c++",
    )
]

setup(
    name="native_dataconverter",
    version="0.1.0",
    description="Native DataConverter for vnpy BarData field conversion",
    ext_modules=ext_modules,
    cmdclass={"build_ext": BuildExt},
    zip_safe=False,
)

