#!/usr/bin/env python3
# 23 hidden tests

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
FILES_BASE = HIDDEN_BASE.parent / "files"
MERGE_SCRIPT = FILES_BASE / "merge_shards.py"
OUTPUT_FILE = FILES_BASE / "merged_stream.jsonl"
REFERENCE_FULL = HIDDEN_BASE / "reference_stream_full.jsonl"

EXPECTED_EVENT_COUNT = 720
EXPECTED_FULL_SHA256 = "b1192a8523e0ffe627706e18c79a326cae80374c64a3d0df558784fe65e49680"
REQUIRED_FIELDS = {"seq", "timestamp", "session_id", "event_type", "latency_ms", "source_shard"}


def run_merge():
    subprocess.run(
        [sys.executable, str(MERGE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hidden_full_stream_matches():
    """Complete merged stream must match the hidden full reference exactly."""
    run_merge()
    output = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    assert len(output) == len(reference), (
        f"Event count mismatch: got {len(output)}, expected {len(reference)}"
    )
    for i in range(len(reference)):
        assert output[i] == reference[i], (
            f"Mismatch at event {i}:\n"
            f"  output:    {json.dumps(output[i], separators=(',', ':'))}\n"
            f"  reference: {json.dumps(reference[i], separators=(',', ':'))}"
        )


def test_hidden_event_count_exact():
    """Merged stream must have exactly 720 events after deduplication."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    assert len(records) == EXPECTED_EVENT_COUNT, (
        f"Expected {EXPECTED_EVENT_COUNT} events, got {len(records)}"
    )


def test_hidden_timestamp_correction():
    """Timestamps from skewed shards must be corrected properly.

    Verify that events from node_a (offset +300s) and node_d (offset -120s)
    have timestamps within the expected range of the overall stream.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)

    ref_by_seq = {r["seq"]: r for r in reference}
    for rec in records:
        ref = ref_by_seq.get(rec["seq"])
        assert ref is not None, f"Unexpected seq {rec['seq']}"
        assert rec["timestamp"] == ref["timestamp"], (
            f"Timestamp mismatch for seq {rec['seq']} (shard {rec['source_shard']}): "
            f"got {rec['timestamp']}, expected {ref['timestamp']}"
        )


def test_hidden_dropped_line_recovery():
    """Events from shards with truncated lines must still be recovered
    (from other shards that also contain those events)."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    seqs = {r["seq"] for r in records}
    # These are the truncated sequences in node_c that must be recovered from other shards
    truncated_seqs = {58, 88, 98, 138, 158, 173, 288, 383, 418, 448}
    for seq in truncated_seqs:
        assert seq in seqs, (
            f"Sequence {seq} (truncated in node_c) was not recovered from another shard"
        )


def test_hidden_deterministic_merge():
    """Two runs of the merge script must produce identical output."""
    run_merge()
    content_a = OUTPUT_FILE.read_bytes()

    run_merge()
    content_b = OUTPUT_FILE.read_bytes()

    assert content_a == content_b, "Merge output is not deterministic across runs"


def test_hidden_epoch_normalisation():
    """Events from node_f must have timestamps in milliseconds range (> 1e12), not seconds."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_f_events = [r for r in records if r["source_shard"] == "node_f"]
    assert len(node_f_events) > 0, "No events from node_f found in merged stream"
    for rec in node_f_events:
        assert rec["timestamp"] > 1_000_000_000_000, (
            f"node_f event seq={rec['seq']} has timestamp {rec['timestamp']} "
            f"which looks like seconds, not milliseconds (should be > 1e12)"
        )
        assert rec["timestamp"] < 2_000_000_000_000, (
            f"node_f event seq={rec['seq']} has timestamp {rec['timestamp']} "
            f"which is unexpectedly large"
        )


def test_hidden_base64_decoded_fields():
    """Events from node_c must have valid event_type strings, not raw base64 values."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_c_events = [r for r in records if r["source_shard"] == "node_c"]
    assert len(node_c_events) > 0, "No events from node_c found in merged stream"

    valid_event_types = {"request_start", "request_end", "error_500", "error_timeout", "heartbeat"}
    for rec in node_c_events:
        assert rec["event_type"] in valid_event_types, (
            f"node_c event seq={rec['seq']} has invalid event_type: {rec['event_type']!r} "
            f"(should be decoded from base64 if encoded)"
        )


def test_hidden_no_extra_fields():
    """Output records must contain exactly the required fields and no extras.

    Fields like 'payload' and 'status' from the CSVs must not leak into output.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    assert len(records) > 0, "No records in output"
    for i, rec in enumerate(records):
        extra = set(rec.keys()) - REQUIRED_FIELDS
        assert not extra, (
            f"Record {i} (seq={rec.get('seq', '?')}) has extra fields: {extra}"
        )


def test_hidden_compact_json_format():
    """Each line must use compact JSON serialization -- no spaces after colons or commas."""
    run_merge()
    with open(OUTPUT_FILE) as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            parsed = json.loads(line)
            canonical = json.dumps(parsed, separators=(",", ":"), sort_keys=False)
            # Re-encode with the same key order as the original line
            original_keys = list(json.loads(line).keys())
            reordered = json.dumps(
                {k: parsed[k] for k in original_keys},
                separators=(",", ":"),
            )
            assert line == reordered, (
                f"Line {lineno} is not compact JSON.\n"
                f"  got:      {line!r}\n"
                f"  expected: {reordered!r}"
            )


def test_hidden_no_blank_lines():
    """Output file must have no blank or whitespace-only lines."""
    run_merge()
    with open(OUTPUT_FILE) as f:
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                assert False, f"Blank line at line {lineno}"


def test_hidden_node_f_exact_count():
    """Node_f contributes exactly 80 events with sequence numbers 601-680."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_f_events = [r for r in records if r["source_shard"] == "node_f"]
    assert len(node_f_events) == 80, (
        f"Expected 80 events from node_f, got {len(node_f_events)}"
    )
    expected_seqs = set(range(601, 681))
    actual_seqs = {r["seq"] for r in node_f_events}
    assert actual_seqs == expected_seqs, (
        f"node_f sequence numbers mismatch.\n"
        f"  missing: {expected_seqs - actual_seqs}\n"
        f"  extra:   {actual_seqs - expected_seqs}"
    )


def test_hidden_node_f_timestamps_exact_ms_conversion():
    """Node_f timestamps stored in seconds must be converted to exact milliseconds.

    Each converted timestamp must be exactly original_seconds * 1000 (no drift).
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_f_events = [r for r in records if r["source_shard"] == "node_f"]
    assert len(node_f_events) > 0, "No node_f events found"
    for rec in node_f_events:
        assert rec["timestamp"] % 1000 == 0, (
            f"node_f seq={rec['seq']} timestamp {rec['timestamp']} is not an exact "
            f"multiple of 1000, suggesting incorrect seconds-to-milliseconds conversion"
        )


def test_hidden_dedup_source_attribution():
    """When the same sequence number appears in multiple shards, the output
    must attribute the event to the shard with the lowest latency_ms (ties
    broken by lexicographically-first shard name).

    Checks a sample of known cross-shard duplicates.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    output_by_seq = {r["seq"]: r for r in records}

    # Sequences that exist in multiple shards with known correct attribution
    # (equal latency across shards falls back to lex-first shard name)
    dedup_cases = {
        39: "node_a",   # node_a and node_d both have seq 39 (equal latency, a < d)
        66: "node_a",   # node_a and node_e (equal latency)
        79: "node_b",   # node_b and node_d (equal latency)
        98: "node_a",   # node_a and node_c (equal latency)
        109: "node_d",  # node_d and node_e (equal latency)
        165: "node_d",  # node_d and node_e (equal latency)
        192: "node_b",  # node_b and node_e (equal latency)
        319: "node_d",  # node_d and node_e (equal latency)
        353: "node_c",  # node_c and node_d (equal latency)
        378: "node_c",  # node_c and node_e (equal latency)
        448: "node_b",  # node_b and node_c (truncated in c, equal latency)
        # node_i overlaps where node_i has lower latency -> node_i wins
        489: "node_i",  # node_d(4280) vs node_i(3037) -> node_i wins
        496: "node_i",  # node_a(3191) vs node_i(1691) -> node_i wins
        560: "node_i",  # node_g(2331) vs node_i(1338) -> node_i wins
        # node_i overlaps where node_i has higher latency -> original wins
        497: "node_b",  # node_b(657) vs node_i(1647) -> node_b wins
        498: "node_c",  # node_c(1570) vs node_i(2188) -> node_c wins
    }
    for seq, expected_shard in dedup_cases.items():
        rec = output_by_seq.get(seq)
        assert rec is not None, f"Sequence {seq} missing from output"
        assert rec["source_shard"] == expected_shard, (
            f"Dedup attribution error for seq {seq}: "
            f"got source_shard={rec['source_shard']!r}, expected {expected_shard!r}"
        )


def test_hidden_reordered_columns_node_e():
    """Node_e has a different column order than other shards.

    Verify that events attributed to node_e have correct field values
    (not swapped due to column order assumptions).
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    node_e_events = [r for r in records if r["source_shard"] == "node_e"]
    assert len(node_e_events) > 0, "No events from node_e found"

    for rec in node_e_events:
        ref = ref_by_seq.get(rec["seq"])
        assert ref is not None, f"Unexpected seq {rec['seq']} from node_e"
        # Check all fields match -- wrong column parsing would swap values
        assert rec["session_id"] == ref["session_id"], (
            f"node_e seq={rec['seq']}: session_id {rec['session_id']!r} != {ref['session_id']!r}"
        )
        assert rec["latency_ms"] == ref["latency_ms"], (
            f"node_e seq={rec['seq']}: latency_ms {rec['latency_ms']} != {ref['latency_ms']}"
        )
        assert rec["event_type"] == ref["event_type"], (
            f"node_e seq={rec['seq']}: event_type {rec['event_type']!r} != {ref['event_type']!r}"
        )


def test_hidden_node_g_hex_session_ids():
    """Node_g stores session_id values as hex-encoded strings.

    Verify that events attributed to node_g have correctly decoded session_id
    values (e.g. "session_004", not "73657373696f6e5f303034").
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    node_g_events = [r for r in records if r["source_shard"] == "node_g"]
    assert len(node_g_events) > 0, "No events from node_g found"

    for rec in node_g_events:
        ref = ref_by_seq.get(rec["seq"])
        assert ref is not None, f"Unexpected seq {rec['seq']} from node_g"
        assert rec["session_id"] == ref["session_id"], (
            f"node_g seq={rec['seq']}: session_id {rec['session_id']!r} != {ref['session_id']!r} "
            f"(should be decoded from hex)"
        )
        # Also verify it looks like a proper session id, not raw hex
        assert rec["session_id"].startswith("session_"), (
            f"node_g seq={rec['seq']}: session_id {rec['session_id']!r} "
            f"does not start with 'session_' -- likely still hex-encoded"
        )


def test_hidden_node_g_clock_drift_seconds():
    """Node_g has a clock drift of -45 seconds (offset_ms = -45000).

    The drift must be inferred from the data. Verify timestamps are corrected
    by the full -45 second offset.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    # Check a sample of node_g-only events (seqs 516-550 only exist in node_g)
    sample_seqs = [516, 520, 530, 540, 550]
    for seq in sample_seqs:
        rec = next((r for r in records if r["seq"] == seq), None)
        assert rec is not None, f"Sequence {seq} (node_g unique) missing from output"
        ref = ref_by_seq[seq]
        assert rec["timestamp"] == ref["timestamp"], (
            f"node_g seq={seq}: timestamp {rec['timestamp']} != {ref['timestamp']} "
            f"(clock_drift_seconds: -45 means offset_ms = -45000)"
        )


def test_hidden_node_g_exact_count():
    """Node_g contributes exactly 58 events after dedup.

    Seqs 501-562 minus 555 and 559 (truncated in node_g, recovered from node_h),
    and minus 560 and 561 (node_i has lower latency for these).
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_g_events = [r for r in records if r["source_shard"] == "node_g"]
    assert len(node_g_events) == 58, (
        f"Expected 58 events from node_g, got {len(node_g_events)}"
    )
    expected_seqs = set(range(501, 563)) - {555, 559, 560, 561}
    actual_seqs = {r["seq"] for r in node_g_events}
    assert actual_seqs == expected_seqs, (
        f"node_g sequence numbers mismatch.\n"
        f"  missing: {expected_seqs - actual_seqs}\n"
        f"  extra:   {actual_seqs - expected_seqs}"
    )


def test_hidden_node_h_pipe_delimited_parsing():
    """Node_h uses pipe-delimited format instead of CSV.

    Verify that events from node_h are parsed correctly despite non-standard
    delimiter, URL-encoded event types, and float timestamps in seconds.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    node_h_events = [r for r in records if r["source_shard"] == "node_h"]
    assert len(node_h_events) > 0, "No events from node_h found"

    valid_event_types = {"request_start", "request_end", "error_500", "error_timeout", "heartbeat"}
    for rec in node_h_events:
        ref = ref_by_seq.get(rec["seq"])
        assert ref is not None, f"Unexpected seq {rec['seq']} from node_h"

        # Check event_type is properly URL-decoded (not "error%5F500")
        assert rec["event_type"] in valid_event_types, (
            f"node_h seq={rec['seq']}: event_type {rec['event_type']!r} invalid "
            f"(should be URL-decoded from e.g. 'error%5F500')"
        )
        assert "%5F" not in rec["event_type"] and "%5f" not in rec["event_type"], (
            f"node_h seq={rec['seq']}: event_type {rec['event_type']!r} "
            f"still contains URL-encoded underscores"
        )

        # Check session_id has no whitespace padding
        assert rec["session_id"] == rec["session_id"].strip(), (
            f"node_h seq={rec['seq']}: session_id {rec['session_id']!r} "
            f"has leading/trailing whitespace"
        )

        # Check all fields match reference
        assert rec == ref, (
            f"node_h seq={rec['seq']} mismatch:\n"
            f"  output:    {json.dumps(rec, separators=(',', ':'))}\n"
            f"  reference: {json.dumps(ref, separators=(',', ':'))}"
        )


def test_hidden_node_h_float_seconds_to_ms():
    """Node_h timestamps are decimal seconds with offset, needing exact ms conversion.

    Stored as float seconds (e.g. 1705314320.861) with a time offset in seconds.
    Must recover true_ms = round((stored_sec - offset) * 1000).
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    # Check node_h-range events (seqs 563-600), excluding 595 which is won by node_i
    node_h_only_seqs = set(range(563, 601)) - {595}
    for seq in sorted(node_h_only_seqs):
        rec = next((r for r in records if r["seq"] == seq), None)
        assert rec is not None, f"Sequence {seq} (node_h range) missing from output"
        ref = ref_by_seq[seq]
        assert rec["timestamp"] == ref["timestamp"], (
            f"node_h seq={seq}: timestamp {rec['timestamp']} != {ref['timestamp']} "
            f"(float seconds with offset must be converted to exact milliseconds)"
        )


def test_hidden_cross_shard_dedup_new_nodes():
    """Dedup attribution for events that overlap between nodes (g, h, i) and
    existing nodes must follow the lowest-latency-first rule (ties broken
    by lexicographic shard name).

    Checks overlaps across node_a/g, node_g/h, node_b/h, node_g/h/i.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    output_by_seq = {r["seq"]: r for r in records}

    cases = {
        # node_a vs node_g: equal latency, node_a wins (a < g)
        1: "node_a",
        6: "node_a",
        11: "node_a",
        # node_g vs node_h: equal latency, node_g wins (g < h) -- except truncated seqs
        551: "node_g",
        552: "node_g",
        553: "node_g",
        554: "node_g",
        555: "node_h",  # truncated in node_g, recovered from node_h
        559: "node_h",  # truncated in node_g, recovered from node_h
        # node_b vs node_h: equal latency, node_b wins (b < h)
        12: "node_b",
        17: "node_b",
        22: "node_b",
        # node_g vs node_h: equal latency, node_g wins (g < h)
        508: "node_g",
        510: "node_g",
        515: "node_g",
        # node_g vs node_i: node_i has lower latency -> node_i wins
        560: "node_i",
        561: "node_i",
        # node_h vs node_i: node_i has lower latency -> node_i wins
        595: "node_i",
    }
    for seq, expected_shard in cases.items():
        rec = output_by_seq.get(seq)
        assert rec is not None, f"Sequence {seq} missing from output"
        assert rec["source_shard"] == expected_shard, (
            f"Dedup attribution error for seq {seq}: "
            f"got source_shard={rec['source_shard']!r}, expected {expected_shard!r}"
        )


def test_hidden_node_i_jsonl_parsing():
    """Node_i uses JSON Lines format with cascading corruptions.

    Timestamps are base64-encoded epoch seconds strings and session_ids are
    ROT13-encoded. Verify that events from node_i are correctly decoded.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    node_i_events = [r for r in records if r["source_shard"] == "node_i"]
    assert len(node_i_events) > 0, "No events from node_i found"

    valid_event_types = {"request_start", "request_end", "error_500", "error_timeout", "heartbeat"}
    for rec in node_i_events:
        ref = ref_by_seq.get(rec["seq"])
        assert ref is not None, f"Unexpected seq {rec['seq']} from node_i"

        # session_id must be properly decoded (not ROT13-mangled)
        assert rec["session_id"].startswith("session_"), (
            f"node_i seq={rec['seq']}: session_id {rec['session_id']!r} "
            f"does not start with 'session_' -- likely still ROT13-encoded"
        )

        # event_type must be valid
        assert rec["event_type"] in valid_event_types, (
            f"node_i seq={rec['seq']}: event_type {rec['event_type']!r} invalid"
        )

        # timestamp must be in milliseconds range
        assert rec["timestamp"] > 1_000_000_000_000, (
            f"node_i seq={rec['seq']}: timestamp {rec['timestamp']} looks like seconds"
        )

        # All fields must match reference
        assert rec == ref, (
            f"node_i seq={rec['seq']} mismatch:\n"
            f"  output:    {json.dumps(rec, separators=(',', ':'))}\n"
            f"  reference: {json.dumps(ref, separators=(',', ':'))}"
        )


def test_hidden_node_i_exact_count():
    """Node_i contributes exactly 48 events after dedup.

    40 unique events (seqs 681-720) plus 8 overlap wins where node_i
    had lower latency than the competing shard.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_i_events = [r for r in records if r["source_shard"] == "node_i"]
    assert len(node_i_events) == 48, (
        f"Expected 48 events from node_i, got {len(node_i_events)}"
    )
    # All unique seqs 681-720 must be present
    expected_unique = set(range(681, 721))
    actual_seqs = {r["seq"] for r in node_i_events}
    missing_unique = expected_unique - actual_seqs
    assert not missing_unique, (
        f"node_i missing unique sequences: {missing_unique}"
    )


def test_hidden_node_i_timestamps_from_seconds():
    """Node_i unique events (681-720) have timestamps that are exact multiples
    of 1000 (since the shard stores epoch seconds, not milliseconds).
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    ref_by_seq = {r["seq"]: r for r in reference}

    for seq in range(681, 721):
        rec = next((r for r in records if r["seq"] == seq), None)
        assert rec is not None, f"Sequence {seq} (node_i unique) missing from output"
        assert rec["timestamp"] % 1000 == 0, (
            f"node_i seq={seq}: timestamp {rec['timestamp']} is not an exact "
            f"multiple of 1000 (shard stores seconds, convert to ms)"
        )
        ref = ref_by_seq[seq]
        assert rec["timestamp"] == ref["timestamp"], (
            f"node_i seq={seq}: timestamp {rec['timestamp']} != {ref['timestamp']}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
