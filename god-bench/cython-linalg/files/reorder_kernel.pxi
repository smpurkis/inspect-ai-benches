def ordschur(np.ndarray t, np.ndarray q, select):
    """Return fresh arrays containing an ordered real Schur decomposition."""
    cdef Py_ssize_t n, i, j
    cdef double value, scale = 1.0

    if t.ndim != 2 or t.shape[0] != t.shape[1]:
        raise ValueError("T must be square")
    if q.ndim != 2 or q.shape[0] != q.shape[1] or q.shape[0] != t.shape[0]:
        raise ValueError("Q must be square and match T")
    if t.dtype != np.float64 or q.dtype != np.float64:
        raise ValueError("T and Q must have dtype float64")
    n = t.shape[0]
    if len(select) != n:
        raise ValueError("select must have length n")

    for i in range(n):
        for j in range(n):
            value = t[i, j]
            if not isfinite(value) or not isfinite(q[i, j]):
                raise ValueError("T and Q must be finite")
            if fabs(value) > scale:
                scale = fabs(value)

    # Incomplete baseline: validation is useful, but selected blocks are not moved.
    return np.array(t, dtype=np.float64, order="C", copy=True), np.array(q, dtype=np.float64, order="C", copy=True)
