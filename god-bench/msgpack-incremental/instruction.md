# Incremental MessagePack Decoder

Edit only `src/decode.rs`. Repair `Decoder` so it accepts any sequence of input chunks and emits each complete top-level value exactly once. Preserve the API in `src/lib.rs`.

The supported, canonical MessagePack subset is nil, booleans, signed and unsigned integers represented as `i64`, arrays, and maps. Accept positive/negative fixints and markers `cc`-`cf`, `d0`-`d3`, `dc`/`dd`, and `de`/`df`. Reject reserved or unsupported markers. Fixed-width integers must use the shortest encoding (including a fixint when possible). Container lengths are unsigned big-endian and may be split at any byte. A map length counts key/value pairs.

`feed` may receive empty chunks and multiple values. Incomplete input is not an error until `finish`; malformed/non-canonical input fails immediately and poisons the decoder. Enforce the configured maximum container depth, where a scalar has depth zero and the outermost container has depth one. Enforce `MAX_CONTAINER_ITEMS` before allocating or traversing children. After any error, `feed` and `finish` must return `DecodeError::Poisoned`. Output and errors must be deterministic.

Build with `cp /app/files/Cargo.toml /app/Cargo.toml && mkdir -p /app/src && cp /app/files/src/*.rs /app/src/ && cd /app && cargo build --offline`. Run `python3 -m pytest -q /app/files/tests.py`.
