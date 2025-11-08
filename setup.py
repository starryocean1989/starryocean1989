from setuptools import setup, Extension
import pybind11
import os
from setuptools.command.build_ext import build_ext as _build_ext

class build_ext(_build_ext):
    def copy_extensions_to_source(self):
        print("--- Custom build_ext: copy_extensions_to_source ---")
        build_py = self.get_finalized_command('build_py')
        for ext in self.extensions:
            fullname = self.get_ext_fullname(ext.name)
            filename = self.get_ext_filename(fullname)
            modpath = fullname.split('.')
            package = '.'.join(modpath[:-1])
            package_dir = build_py.get_package_dir(package)
            dest_filename = os.path.join(package_dir, os.path.basename(filename))
            src_filename = os.path.join(self.build_lib, filename)

            print(f"Copying {src_filename} to {dest_filename}")
            if not os.path.exists(src_filename):
                print(f"ERROR: Source file not found: {src_filename}")
                continue
            if not os.path.exists(os.path.dirname(dest_filename)):
                print(f"Creating directory: {os.path.dirname(dest_filename)}")
                os.makedirs(os.path.dirname(dest_filename))

            self.copy_file(src_filename, dest_filename)
            print("--- Copy complete ---")

    def run(self):
        print("--- Custom build_ext: run ---")
        _build_ext.run(self)
        self.copy_extensions_to_source()

setup(
    name='native_calendar',
    version='0.1.0',
    packages=['native_calendar'],
    package_data={'native_calendar': ['sse_calendar.bin']},
    ext_modules=[
        Extension(
            'native_calendar._native_calendar',
            sources=['native_calendar/calendar.cpp'],
            include_dirs=[pybind11.get_include()],
            language='c++',
            extra_compile_args=['/std:c++17'],
        ),
    ],
    cmdclass={'build_ext': build_ext},
    zip_safe=False,
)