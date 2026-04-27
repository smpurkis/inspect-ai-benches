"""Build script for the cylinalg Cython extension.

Usage:
    cd /app/files && python3 setup_build.py build_ext --inplace
"""

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

extensions = [
    Extension(
        "cylinalg",
        sources=["cylinalg.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=["-O2"],
        libraries=["m"],
    )
]

setup(
    ext_modules=cythonize(extensions, language_level="3"),
)
