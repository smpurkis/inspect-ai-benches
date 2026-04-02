"""Tests for limit exceeded prompt handling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from inspect_ai.util import LimitExceededError

from src.reporeason_native import _final_answer_with_prompt, _force_final_answer, _has_limit_prompt


def _state_with_messages(count: int):
    return SimpleNamespace(messages=[SimpleNamespace(role="user", content="x") for _ in range(count)], metadata={}, model="test")


def test_final_answer_on_limit_exceeded() -> None:
    state = _state_with_messages(2)

    calls = {"count": 0}

    async def _fake_generate(state):
        calls["count"] += 1
        if calls["count"] == 1:
            raise LimitExceededError("message", value=5, limit=5)
        state.output = type("Output", (), {"completion": '{"reason":"ok","answer":"x"}'})()
        return state

    result = asyncio.run(
        _final_answer_with_prompt(state, _fake_generate, "input", "PROMPT")
    )
    assert _has_limit_prompt(result, "PROMPT") is True


def test_force_final_answer_appends_prompt() -> None:
    state = _state_with_messages(1)
    asyncio.run(_force_final_answer(state, "PROMPT"))
    assert _has_limit_prompt(state, "PROMPT") is True
