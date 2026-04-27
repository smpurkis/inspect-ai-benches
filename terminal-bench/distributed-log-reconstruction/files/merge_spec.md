# Shard Merge Specification

## Shard Format

Shard files in the `shards/` directory contain distributed log events. Each file may use a different serialization format (CSV, delimited text, JSON Lines, or other structured formats). Your parser must auto-detect the format and schema from each file's contents -- do not assume a uniform schema across shards.

Some shards include metadata as comment lines. Where present, this metadata may describe calibration or timing information. Not all shards contain metadata, and metadata key names and value units vary between shards.

## Corruptions

The shards contain various data-quality issues that differ between files. You must detect and handle each issue from the data itself. Issues may include (but are not limited to):
- Timestamp skew or drift
- Duplicate or repeated event entries
- Truncated or malformed lines
- Missing events (gaps in sequence numbers)
- Non-standard field encodings. Detect the encoding from the data itself.
- Inconsistencies in units or formats across shards
- Varying delimiters or column naming conventions
- Whitespace anomalies in field values

## Merge Rules

1. **Parse**: Read all shard files from the `shards/` directory. Auto-detect each file's format, delimiter, column mapping, and any metadata. Skip any line that is malformed or unparseable.
2. **Deduplicate**: Each event (identified by its sequence number) should appear exactly once. When a sequence number appears in multiple shards, keep the record with the **lowest `latency_ms` value**. If two records for the same sequence number have equal `latency_ms`, break the tie by keeping the one from the shard whose filename comes first in lexicographic order.
3. **Correct timestamps**: Apply any offset or calibration metadata from each shard to recover the true timestamp for each event. All output timestamps must be integers in milliseconds.
4. **Sort**: Order events by corrected timestamp ascending, with sequence number as tiebreaker.
5. **Output**: Write one compact JSON object per line (JSONL) with fields: `seq`, `timestamp`, `session_id`, `event_type`, `latency_ms`, `source_shard`. The `source_shard` value is the node name extracted from the filename (e.g., `"node_a"` from `shard_node_a.csv`). Do not include any extra columns from the source data in the output.
