# Reconstruct Canonical Log Stream

Merge corrupted distributed log shards into a single canonical JSONL stream.

## Context

Six log shards from distributed nodes are in `/app/files/shards/`. Each shard is a CSV file with corruptions described in `/app/files/merge_spec.md`.

## Requirements

- Write a Python script `/app/files/merge_shards.py` that:
  1. Reads all six shard CSV files from `/app/files/shards/`
  2. Parses the merge specification in `/app/files/merge_spec.md`
  3. Handles corrupted/malformed lines gracefully (skip them)
  4. Deduplicates by sequence number
  5. Applies all corrections described in the merge spec
  6. Produces a canonical JSONL stream sorted by corrected timestamp (sequence number as tiebreaker)
  7. Writes output to `/app/files/merged_stream.jsonl`

## Output Format

Each line of the output JSONL must be a JSON object with these exact fields:
```json
{"seq": 1, "timestamp": 1705312805738, "session_id": "session_004", "event_type": "request_start", "latency_ms": 2263, "source_shard": "node_a"}
```

- `seq`: integer sequence number
- `timestamp`: corrected timestamp in milliseconds (integer)
- `session_id`: string
- `event_type`: string
- `latency_ms`: integer
- `source_shard`: string (e.g. "node_a")

Use compact JSON (no extra spaces). One object per line, no trailing comma.

## Verification

Run visible tests:

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` -- test files require pytest.

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
