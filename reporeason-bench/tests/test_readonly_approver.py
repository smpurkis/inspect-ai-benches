"""Tests for readonly approver helpers."""

from __future__ import annotations

import json

from src.readonly_approver import _extract_json_from_command


def test_extract_json_from_command_heredoc() -> None:
    cmd = """bash
cat << 'RESPONSEFINALOUTPUT422'
{
  \"reason\": \"ok\",
  \"answer\": \"&[13, 14]\"
}
RESPONSEFINALOUTPUT422
"""
    extracted = _extract_json_from_command(cmd)
    assert extracted is not None
    parsed = json.loads(extracted)
    assert parsed["answer"] == "&[13, 14]"
