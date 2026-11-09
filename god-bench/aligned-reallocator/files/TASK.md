# Aligned Reallocator

Edit exactly `/app/files/src/aligned_pool.zig` and implement `resize`.

`Pool.resize(old, new_len, new_alignment)` must first validate the complete allocation handle. Valid alignments are powers of two from 1 through 4096. `new_len == 0` frees the allocation and returns `null`. Shrinking may stay in place. Growth may stay in place only when the existing offset satisfies the new alignment and the enlarged range is free. Otherwise allocate a correctly aligned replacement, copy exactly `min(old.len, new_len)` prefix bytes, then free the old allocation and return the replacement.

Errors must leave the original allocation and bytes unchanged. Reject stale, forged, or already-freed handles. Detect size/address overflow and report an allocation error rather than trapping or corrupting memory. A successful move invalidates the old handle. The trusted pool exposes its block metadata and provides `validate`, `allocate`, `free`, `bytes`, and `bytesConst`; allocation bookkeeping and the operation harness are not editable.

Do not edit or add other source files, use the network, or introduce dependencies. Run `python3 -m pytest -q /app/files/tests.py`.
