# Step 1: Reconstruct Canonical Log Stream

Merge corrupted distributed log shards into a single canonical JSONL stream.

## Context

Five log shards from distributed nodes are in `/app/step_1/files/shards/`. Each shard is a CSV file with corruptions described in `/app/step_1/files/merge_spec.md`.

## Requirements

- Write a Python script `/app/step_1/files/merge_shards.py` that:
  1. Reads all six shard CSV files from `/app/step_1/files/shards/`
  2. Parses the merge specification in `/app/step_1/files/merge_spec.md`
  3. Handles corrupted/malformed lines gracefully (skip them)
  4. Deduplicates by sequence number
  5. Corrects timestamp skew using the offset declared in each shard header
  6. Applies epoch normalisation: shards with `time_unit: seconds` must have timestamps multiplied by 1000 before applying the offset
  7. Applies field decoding: shards with `encoding_fields: event_type:base64` must have the event_type field base64-decoded
  8. Produces a canonical JSONL stream sorted by corrected timestamp (sequence number as tiebreaker)
  9. Writes output to `/app/step_1/files/merged_stream.jsonl`

## Epoch Normalisation

One shard (`shard_node_f.csv`) declares `time_unit: seconds` in its header. This means
its timestamps are Unix seconds, not milliseconds. Multiply these timestamps by 1000
before applying any `time_offset_ms` correction.

## Field Encoding

One shard (`shard_node_c.csv`) declares `encoding_fields: event_type:base64` in its
header. For approximately every 7th data line, the `event_type` field is base64-encoded.
Decode any base64 `event_type` values before including them in the merged output.

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

Compare your first 100 events against `/app/step_1/files/reference_stream_public.jsonl`.

Run visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` -- test files require pytest.

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files or reference files.
