# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script setup
"""

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext


class OptionalBuildExt(build_ext):
    """
    Build C extensions optionally - if compilation fails, the package still installs
    and falls back to the pure-Python implementation.
    """

    def run(self):
        try:
            super().run()
        except Exception: # pylint: disable=broad-except
            self._unavailable()

    def build_extension(self, ext):
        try:
            super().build_extension(ext)
        except Exception: # pylint: disable=broad-except
            self._unavailable()

    @staticmethod
    def _unavailable():
        print('*' * 70)
        print('WARNING: C extension could not be compiled.')
        print('         Falling back to pure-Python implementation.')
        print('*' * 70)


setup(
    ext_modules=[
        Extension(
            'bare_script.runtime_c',
            sources=['src/bare_script/runtime_c.c']
        )
    ],
    cmdclass={'build_ext': OptionalBuildExt}
)
