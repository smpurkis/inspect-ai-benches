# Step 2: Build Rust Analytics CLI

Build a Rust command-line tool that reads the canonical JSONL log stream and computes analytics.

## Context

Your merged stream from Step 1 is at `/app/step_1/files/merged_stream.jsonl`. A stubbed Rust CLI project is provided at `/app/step_2/files/` with `Cargo.toml` and `src/main.rs`.

## Requirements

Complete the Rust CLI (`log_analytics`) that accepts input via file argument or stdin and supports these flags:

- `--sessions`: Output unique session count
- `--latency`: Compute and output p50/p95/p99 latency percentiles
- `--errors`: Classify and count errors by type
- `--rates`: Compute per-minute event rates
- `--all`: Output complete JSON analytics report (all of the above)
- `--input <path>`: Read JSONL from file (default: stdin)

## Percentile Method

Use nearest-rank percentile:
- Sort latency values ascending
- For percentile p (0-100): `index = ceil(p / 100 * n) - 1`
- Example: for 500 values, p50 index = ceil(250) - 1 = 249

## Per-Minute Rates

Group events by minute: `floor(timestamp_ms / 60000) * 60000`, then format the minute as `YYYY-MM-DDTHH:MM` in UTC.

## Output Format (--all)

The `--all` flag must produce a JSON object written to stdout with this exact structure:

```json
{
  "sessions": {"count": 20},
  "latency": {"p50": 2461, "p95": 4766, "p99": 4955},
  "errors": {"error_500": 44, "error_timeout": 61},
  "rates": [
    {"minute": "2024-01-15T10:00", "count": 13},
    {"minute": "2024-01-15T10:01", "count": 16}
  ]
}
```

Field names and types must match exactly. Error keys are sorted alphabetically. Rates are sorted by minute.

## --window <seconds> Flag

Compute sliding-window P99 latency. Window size is given in seconds, slide every 10 seconds.
Output: JSON array of `{window_start_ms, window_end_ms, p99_latency_ms}`.

Use nearest-rank percentile (same method as `--latency`) applied to latency values of events
whose timestamp falls within each window `[window_start_ms, window_end_ms)`.

## --sessions-detail Flag

Output per-session statistics.
Output: JSON object keyed by session_id: `{event_count, total_latency_ms, error_count, error_rate}`.

- `event_count`: total events for this session
- `total_latency_ms`: sum of all latency_ms values for this session
- `error_count`: number of events with event_type starting with "error_"
- `error_rate`: error_count / event_count (rounded to 2 decimal places)

## Building

```bash
cd /app/step_2/files
cargo build --release
```

The binary will be at `/app/step_2/files/target/release/log_analytics`.

Dependencies (serde, serde_json, clap, rmp-serde) are pre-vendored for offline builds.

## Verification

Compare your output against `/app/step_2/files/reference_analytics.json`.

```bash
cd /app/step_2/files
./target/release/log_analytics --all --input /app/step_1/files/merged_stream.jsonl
```

Run visible tests:

    python3 -m pytest /app/step_2/files/tests.py -v

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files or reference files.
