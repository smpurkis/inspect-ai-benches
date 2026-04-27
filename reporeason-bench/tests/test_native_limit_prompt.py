"""Tests for native limit prompt behavior."""

from __future__ import annotations

from types import SimpleNamespace

import asyncio

from src.reporeason_native import _apply_limit_prompt, _final_answer_with_prompt, _has_limit_prompt


def _state_with_messages(count: int):
    return SimpleNamespace(messages=[SimpleNamespace(role="user", content="x") for _ in range(count)])


def test_apply_limit_prompt_before_limit() -> None:
    state = _state_with_messages(4)
    applied = _apply_limit_prompt(state, 5, "prompt")
    assert applied is True
    assert len(state.messages) == 5
    assert state.messages[-1].role == "user"
    assert state.messages[-1].content == "prompt"


def test_apply_limit_prompt_not_yet() -> None:
    state = _state_with_messages(3)
    applied = _apply_limit_prompt(state, 5, "prompt")
    assert applied is False
    assert len(state.messages) == 3


def test_has_limit_prompt() -> None:
    state = _state_with_messages(1)
    assert _has_limit_prompt(state, "prompt") is False
    _apply_limit_prompt(state, 1, "prompt")
    assert _has_limit_prompt(state, "prompt") is True


def test_final_answer_with_prompt_adds_user_message() -> None:
    state = _state_with_messages(2)
    state.message_limit = 0
    state.metadata = {}

    async def _fake_generate(state):
        state.output = type("Output", (), {"completion": '{"reason":"ok","answer":"x"}'})()
        return state

    result = asyncio.run(
        _final_answer_with_prompt(state, _fake_generate, "input", "PROMPT")
    )
    assert _has_limit_prompt(result, "PROMPT") is True
