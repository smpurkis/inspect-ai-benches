"""Tests for shared JSON parsing utilities (src/parsing.py)."""

from __future__ import annotations

from src.parsing import (
    _iter_json_substrings,
    _recover_json_fields,
    _try_load_json,
    extract_final_json_object,
    looks_like_streaming_json,
    parse_json_output,
)


def test_parse_json_output_fenced_block() -> None:
    text = '```json\n{"reason": "ok", "answer": "42"}\n```'
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "42"


def test_parse_json_output_plain_json_prefix() -> None:
    text = 'json\n{\n    "reason": "DeepSeek explains", "answer": "1dec::1"\n}'
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "1dec::1"


def test_parse_json_output_raw_object() -> None:
    text = '{"reason": "simple", "answer": "pop"}'
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "pop"


def test_parse_json_output_embedded_in_text() -> None:
    text = 'Here is my answer:\n{"reason": "found it", "answer": "[]"}\nDone.'
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "[]"


def test_parse_json_output_numeric_string_answer() -> None:
    text = '{"reason": "found", "answer": "&[13, 14]"}'
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "&[13, 14]"


def test_parse_json_output_empty() -> None:
    assert parse_json_output("") is None
    assert parse_json_output(None) is None  # type: ignore[arg-type]


def test_parse_json_output_no_answer_key() -> None:
    text = '{"foo": "bar"}'
    assert parse_json_output(text) is None


def test_parse_json_output_recovers_broken_json() -> None:
    # Regex-based recovery can parse key-value pairs even without valid JSON
    text = 'some prefix "reason": "partial" and "answer": "value" tail'
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "value"


def test_try_load_json_valid() -> None:
    assert _try_load_json('{"reason": "a", "answer": "b"}') == {
        "reason": "a",
        "answer": "b",
    }


def test_try_load_json_invalid() -> None:
    assert _try_load_json("not json") is None
    assert _try_load_json("") is None
    assert _try_load_json('{"only": "one"}') is None


def test_iter_json_substrings() -> None:
    text = 'prefix {"reason":"a","answer":"b"} middle {"reason":"c","answer":"d"} end'
    results = list(_iter_json_substrings(text))
    assert len(results) == 2


def test_looks_like_streaming_json_incomplete() -> None:
    # Many open braces, few close braces, has reason/answer keys
    text = '{"reason": "thinking {"reason": "more {"answer": "still going'
    assert looks_like_streaming_json(text) is True


def test_looks_like_streaming_json_complete() -> None:
    text = '{"reason": "done", "answer": "42"}'
    assert looks_like_streaming_json(text) is False


def test_extract_final_json_object() -> None:
    text = 'Some preamble\n{"reason": "found", "answer": "result"}\nSome postamble'
    parsed = extract_final_json_object(text)
    assert parsed is not None
    assert parsed["answer"] == "result"


def test_recover_json_fields() -> None:
    # Broken JSON but with extractable fields
    text = '"reason": "discovered", "answer": "42"'
    parsed = _recover_json_fields(text)
    assert parsed is not None
    assert parsed["answer"] == "42"
    assert parsed["reason"] == "discovered"


def test_recover_json_fields_no_answer() -> None:
    assert _recover_json_fields('"reason": "only reason"') is None


def test_parse_json_output_tool_heredoc() -> None:
    text = """bash
cat << 'RESPONSEFINALOUTPUT422'
{
  \"reason\": \"ok\",
  \"answer\": \"&[13, 14]\"
}
RESPONSEFINALOUTPUT422
"""
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "&[13, 14]"


def test_parse_json_output_tool_limit_prompt_schema() -> None:
    text = """You have reached the final allowed turn. Output your final answer now as a single JSON object with string fields and no extra text:
{
  "reason": "ok",
  "answer": "value"
}
Schema:
{
  "type": "object",
  "required": ["reason", "answer"],
  "additionalProperties": false,
  "properties": {
    "reason": {"type": "string"},
    "answer": {"type": "string"}
  }
}
"""
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "value"


def test_parse_json_output_tool_echo_payload() -> None:
    text = """bash
echo '{"reason": "The test file has a placeholder <blank> that needs to be replaced with the expected value for cache.positions(8).", "answer": "[13, 14, 15, 16, 17, 18, 19, 20]"}'
"""
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "[13, 14, 15, 16, 17, 18, 19, 20]"


def test_parse_json_output_trailing_json_after_text() -> None:
    text = """Based on my analysis of the `positions` function in `/repo/candle-nn/src/kv_cache.rs`:

When calling `positions(seq_len)` with `seq_len > max_seq_len` (which is 6 for this cache), the function returns:
```rust
(self.current_seq_len..(self.current_seq_len + seq_len)).collect()
```

At line 92, before this assertion:
- `current_seq_len = 13`
- The argument to `positions` is `8`

So it should return the range `(13..21)` which equals `[13, 14, 15, 16, 17, 18, 19, 20]`.

The assertion pattern in the test uses `&[...]` format, so the answer is `&[13, 14, 15, 16, 17, 18, 19, 20]`.

{
    "reason": "Looking at the positions() function implementation in kv_cache.rs, when seq_len (the argument) > max_seq_len (which is 6), it returns (self.current_seq_len..(self.current_seq_len + seq_len)).collect(). At line 92, current_seq_len=13 and the argument is 8, so it returns (13..21) = [13, 14, 15, 16, 17, 18, 19, 20]. The test uses &[] format like other similar assertions in the file.",
    "answer": "&[13, 14, 15, 16, 17, 18, 19, 20]"
}
"""
    parsed = parse_json_output(text)
    assert parsed is not None
    assert parsed["answer"] == "&[13, 14, 15, 16, 17, 18, 19, 20]"
