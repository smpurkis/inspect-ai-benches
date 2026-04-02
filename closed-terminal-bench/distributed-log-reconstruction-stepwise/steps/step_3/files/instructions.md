# Step 3: Streaming Binary Export

Add a `--export <path>` flag to the analytics CLI that produces a compressed binary artifact
using a custom format. The export must process the stream in a single pass (no loading all
events into memory).

## Binary Format

Bytes 0-3: Magic bytes `LCMP` (0x4C 0x43 0x4D 0x50)
Byte 4: Version = 1
Bytes 5-N: LZ4-compressed analytics JSON (use lz4_flex frame format)
Bytes N+1 to N+8: xxHash64 checksum of bytes 5..N (8 bytes, little-endian u64)

## Requirements

1. `--export <path>`: Write binary artifact to path; also print JSON analytics to stdout
2. Single-pass: max heap RSS must stay under 10MB for any stream size
3. Deterministic: identical input → identical output bytes
4. The full pipeline (merge + analytics + export) must be reproducible

## Building

```bash
cd /app/step_2/files && cargo build --release
```

## Usage

```bash
# Run full pipeline
python3 /app/step_1/files/merge_shards.py
cd /app/step_2/files
./target/release/log_analytics --all --export /app/step_3/files/export.bin \
    --input /app/step_1/files/merged_stream.jsonl
```

## Verification

    python3 -m pytest /app/step_3/files/tests.py -v

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files or reference files.
