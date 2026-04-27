# Reconstruct Canonical Log Stream

Merge corrupted distributed log shards into a single, deduplicated, time-ordered JSONL stream.

## Context

Several log shards from distributed nodes are in `/app/files/shards/`. A merge specification is in `/app/files/merge_spec.md`. The shards contain various corruptions and inconsistencies that must be handled to produce correct output.

## Requirements

Write a Python script `/app/files/merge_shards.py` that reads all shard files, applies the merge specification, and writes the canonical output to `/app/files/merged_stream.jsonl`.

Study the merge specification and the shard files carefully. Each shard may have its own quirks -- header formats, column orderings, data encodings, and corruptions vary between shards. Your script must handle all of these correctly.

## Verification

Run visible tests:

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` -- test files require pytest.

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
