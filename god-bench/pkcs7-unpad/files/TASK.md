# Constant-Time PKCS#7 Unpadding

Edit only `src/unpad.c`; the intended patch is 20-45 lines. Preserve this API:

```c
int pkcs7_unpad(const uint8_t *input, size_t input_len,
                size_t block_size, size_t *output_len);
```

`block_size` is valid only in `1..255`. A nonempty input is valid only when its length is a multiple of `block_size`, its final byte is `p` in `1..block_size`, and all final `p` bytes equal `p`. On success return `1` and write `input_len - p` to `*output_len`. On every failure return `0` and leave `*output_len` unchanged. Reject null pointers before dereferencing them.

For every fixed `(input_len, block_size)`, padding validation must execute the same control-flow branches and load the same input addresses regardless of padding values or the first invalid position. Scan a complete final block. Do not call helper functions, use inline assembly, compiler intrinsics, threads, signals, or timing facilities from `pkcs7_unpad`; the verifier traces the function's machine instructions and loads directly. Ordinary fixed-trip loops, integer masks, and branchless selection are sufficient. The input is read-only and must never change.

Build and test:

```text
make -C /app/files clean all
python3 -m pytest -q /app/files/tests.py
```

No other source file, build configuration, dependency, or generated artifact may be submitted.
