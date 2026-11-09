# Constant-Time PKCS#7 Unpadding

Edit only `src/unpad.c`. Implement `pkcs7_unpad` using the API and complete contract in `TASK.md` and `contract.toml`. The validation work must not branch on padding bytes or vary which input bytes are loaded for equal `input_len` and `block_size`.

Build with `make -C /app/files clean all` and run `python3 -m pytest -q /app/files/tests.py`. Network access and new dependencies are forbidden.
