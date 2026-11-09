# cython: language_level=3
"""Trusted real-Schur exchange scaffold."""

import numpy as np
cimport numpy as np
from libc.math cimport fabs, isfinite
from scipy.linalg.lapack import dtrexc

np.import_array()


cdef int _exchange_block(np.ndarray t, np.ndarray q, int source, int destination):
    """Move one Schur block using LAPACK's stable orthogonal exchange."""
    new_t, new_q, info = dtrexc(
        np.asfortranarray(t),
        np.asfortranarray(q),
        source + 1,
        destination + 1,
        wantq=1,
        overwrite_a=1,
        overwrite_q=1,
    )
    if info == 0:
        t[:, :] = new_t
        q[:, :] = new_q
    return info


include "reorder_kernel.pxi"
