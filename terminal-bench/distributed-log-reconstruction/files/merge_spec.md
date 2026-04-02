# Shard Merge Specification

## Shard Format

Each shard CSV file has:
- One or more header comment lines (starting with `#`) declaring metadata such as timestamp offset
- A CSV header row — column names may vary between shards
- Data lines with the fields declared in the header

## Corruptions

Different shards have different corruptions:
- **Timestamp skew**: Some shards have timestamps shifted by a fixed offset (declared in the header comment). The `offset_ms` value was *added* to the true timestamp to produce the stored value.
- **Duplicate entries**: Some shards contain duplicate sequence numbers (the same event repeated).
- **Truncated lines**: Some shards have lines cut off mid-field (incomplete CSV rows).
- **Missing events**: Some shards are missing events entirely (gaps in sequence numbers).
- **Inconsistent units**: Not all shards use the same timestamp unit.

## Merge Rules

1. **Parse**: Read all shard files. Skip any line that is malformed (wrong number of fields, non-numeric values where numbers expected, etc.).
2. **Deduplicate**: Remove duplicate events by sequence number. When the same sequence number appears in multiple shards, keep the first occurrence encountered when processing shards in alphabetical filename order.
3. **Correct timestamps**: Subtract the shard's `offset_ms` from each stored timestamp to recover the true timestamp. That is: `true_timestamp = stored_timestamp - offset_ms`.
4. **Sort**: Order events by corrected timestamp (ascending). Use `sequence_number` as a tiebreaker (ascending) when timestamps are equal.
5. **Output**: Write one JSON object per line (JSONL format) with fields: `seq`, `timestamp`, `session_id`, `event_type`, `latency_ms`, `source_shard`.

## Notes

- The `source_shard` field records which shard file the event was taken from (e.g., `"node_a"`).
- The `payload` field from the CSV is NOT included in the output.
- Use compact JSON serialization (no extra whitespace between keys/values).

## Output Timestamps

All output timestamps must be in milliseconds.
