from setuptools import setup, Extension

runtime_module = Extension(
    'bare_script.runtime_c',
    sources=['src/bare_script/runtime_c.c'],
)

setup(
    ext_modules=[runtime_module],
)
