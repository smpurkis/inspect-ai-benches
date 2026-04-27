"""Tests for shared scoring utilities (src/scoring.py)."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from src.scoring import (
    _parse_equivalence_output,
    llm_judge_equivalence,
    normalize_candidate,
    normalize_expected,
)


@pytest.fixture(autouse=True)
def _clear_openai_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("OPENAI_JUDGE_ENABLED", raising=False)


def test_normalize_candidate_string() -> None:
    assert normalize_candidate("hello") == ["hello"]


def test_normalize_candidate_strips_wrapping_quotes() -> None:
    assert normalize_candidate("'foo'") == ["'foo'", "foo"]
    assert normalize_candidate('"bar"') == ['"bar"', "bar"]


def test_normalize_candidate_list() -> None:
    assert normalize_candidate(["a", "b"]) == ["['a', 'b']"]


def test_normalize_candidate_none() -> None:
    assert normalize_candidate(None) == []


def test_normalize_expected_from_json_list() -> None:
    assert normalize_expected('["a", "b"]') == ['["a", "b"]']


def test_candidate_exact_match_skips_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def _fake_judge(**_kwargs):
        calls["count"] += 1
        return {"used": True, "equivalent": False, "reason": "should not call"}

    monkeypatch.setattr("src.scoring.llm_judge_equivalence", _fake_judge)

    expected = normalize_expected("&[13, 14, 15, 16, 17, 18, 19, 20]")
    candidates = normalize_candidate("&[13, 14, 15, 16, 17, 18, 19, 20]")
    correct = any(candidate in expected for candidate in candidates)

    if not correct and candidates:
        _fake_judge(assertion_line=None, masked_line=None, expected="", candidate="")

    assert correct is True
    assert calls["count"] == 0


def test_normalize_expected_allows_bare_slice_literal() -> None:
    expected = normalize_expected("&[13, 14, 15]")
    assert expected == ["&[13, 14, 15]", "[13, 14, 15]"]


def test_normalize_expected_multiple_ground_truths() -> None:
    expected = normalize_expected(["&[13, 14]", "[13, 14]"])
    assert expected == ["&[13, 14]", "[13, 14]"]


def test_candidate_matches_second_ground_truth() -> None:
    expected = normalize_expected(
        [
            "&[13, 14, 15, 16, 17, 18, 19, 20]",
            "[13, 14, 15, 16, 17, 18, 19, 20]",
        ]
    )
    candidates = normalize_candidate("[13, 14, 15, 16, 17, 18, 19, 20]")
    assert any(candidate in expected for candidate in candidates) is True


def test_parse_equivalence_output_plain() -> None:
    text = '{"equivalent": true, "reason": "Matches"}'
    parsed = _parse_equivalence_output(text)
    assert parsed is not None
    assert parsed["equivalent"] is True


def test_parse_equivalence_output_embedded() -> None:
    text = 'Judge response: {"equivalent": false, "reason": "Nope"}'
    parsed = _parse_equivalence_output(text)
    assert parsed is not None
    assert parsed["equivalent"] is False


def test_parse_equivalence_output_empty() -> None:
    assert _parse_equivalence_output("") is None
    assert _parse_equivalence_output("not json") is None


def test_llm_judge_no_assertion_line() -> None:
    result = llm_judge_equivalence(
        assertion_line=None,
        masked_line=None,
        expected="x",
        candidate="y",
    )
    assert result is not None
    assert result["used"] is False


def test_llm_judge_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.config as _config_mod

    monkeypatch.setattr(_config_mod, "load_config", lambda *a, **kw: {})
    result = llm_judge_equivalence(
        assertion_line="assert foo == 1",
        masked_line="assert foo == <blank>",
        expected="1",
        candidate="1",
    )
    assert result is not None
    assert result["used"] is False


def test_llm_judge_with_fake_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __init__(self, content: str) -> None:
            self.choices = [
                type("Choice", (), {"message": type("Msg", (), {"content": content})()})
            ]

    class _FakeCompletions:
        def __init__(self, store: dict) -> None:
            self._store = store

        def create(self, **kwargs):
            self._store["kwargs"] = kwargs
            return _FakeResponse('{"equivalent": true, "reason": "ok"}')

    class _FakeChat:
        def __init__(self, store: dict) -> None:
            self.completions = _FakeCompletions(store)

    class _FakeOpenAI:
        def __init__(self, store: dict, **_kwargs) -> None:
            self._store = store
            self.chat = _FakeChat(self._store)

    store: dict = {}
    openai_module = ModuleType("openai")
    openai_module.OpenAI = lambda **kwargs: _FakeOpenAI(store, **kwargs)  # type: ignore[attr-defined]
    sys.modules["openai"] = openai_module

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test")
    monkeypatch.setenv("OPENAI_MODEL", "judge-model")
    monkeypatch.setenv("CONFIG_PATH", "")

    result = llm_judge_equivalence(
        assertion_line="assert g['escaped_bell'].literal == 'expected'",
        masked_line="assert g['escaped_bell'].literal == '<blank>'",
        expected="expected",
        candidate="candidate",
    )

    assert result is not None
    assert result["used"] is True
    assert result["equivalent"] is True
    assert result["model"] == "judge-model"
    assert result["base_url"] == "https://example.test"
    assert result["raw_output"] == '{"equivalent": true, "reason": "ok"}'
    prompt = store["kwargs"]["messages"][1]["content"]
    assert "expected" in prompt
    assert "candidate" in prompt
