"""Shared scoring and LLM-judge utilities for reporeason benchmark."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import Any

from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    scorer,
    stderr,
)

from .config import llm_judge_config
from .parsing import _iter_json_substrings, _try_load_json, parse_json_output

try:
    from .prompts import render_judge_prompt
except ImportError:
    from src.prompts import render_judge_prompt  # type: ignore


# ---------------------------------------------------------------------------
# Candidate normalisation
# ---------------------------------------------------------------------------


def normalize_candidate(value: Any) -> list[str]:
    if value is None:
        return []
    candidate = str(value)
    candidates = [candidate]
    if (
        len(candidate) >= 2
        and candidate[0] == candidate[-1]
        and candidate[0] in {"'", '"'}
    ):
        stripped = candidate[1:-1]
        if stripped:
            candidates.append(stripped)
    return candidates


def normalize_expected(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        expected = [str(item) for item in value]
        return expected
    expected = [str(value)]
    if expected[0].startswith("&[") and expected[0].endswith("]"):
        expected.append(expected[0][1:])
    return expected


# ---------------------------------------------------------------------------
# Equivalence-judge helpers
# ---------------------------------------------------------------------------


def _parse_equivalence_output(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    parsed = _try_load_equivalence_json(stripped)
    if parsed:
        return parsed
    for blob in _iter_json_substrings(text):
        parsed = _try_load_equivalence_json(blob)
        if parsed:
            return parsed
    return None


def _try_load_equivalence_json(blob: str) -> dict[str, Any] | None:
    if not blob or not blob.startswith("{") or not blob.rstrip().endswith("}"):
        return None
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and "equivalent" in parsed:
        return parsed
    return None


def llm_judge_equivalence(
    *,
    assertion_line: str | None,
    masked_line: str | None,
    expected: str,
    candidate: str,
) -> dict[str, Any] | None:
    """Ask an LLM judge whether *candidate* is equivalent to *expected*."""
    if not assertion_line or not masked_line:
        return {"used": False, "equivalent": None, "reason": None}

    config = llm_judge_config()
    api_key = os.getenv("OPENAI_API_KEY") or config.get("api_key")
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url")
    model = os.getenv("OPENAI_MODEL") or config.get("model")
    if not api_key or not base_url or not model:
        return {"used": False, "equivalent": None, "reason": None}

    try:
        from openai import OpenAI
    except Exception:
        return {"used": False, "equivalent": None, "reason": None}

    prompt = render_judge_prompt(
        assertion_line=assertion_line,
        masked_line=masked_line,
        expected=expected,
        candidate=candidate,
    )

    try:
        client = OpenAI(api_key=str(api_key), base_url=str(base_url))
        resp = client.chat.completions.create(
            model=str(model),
            messages=[
                {
                    "role": "system",
                    "content": "Return JSON only. No markdown, no extra text.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
    except Exception as exc:
        return {
            "used": True,
            "equivalent": None,
            "reason": None,
            "model": model,
            "base_url": base_url,
            "raw_output": None,
            "error": str(exc),
        }

    content = None
    try:
        content = resp.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        content = None
    if not content:
        return {
            "used": True,
            "equivalent": None,
            "reason": None,
            "model": model,
            "base_url": base_url,
            "raw_output": None,
        }

    parsed = _parse_equivalence_output(str(content))
    if not parsed:
        return {
            "used": True,
            "equivalent": None,
            "reason": None,
            "model": model,
            "base_url": base_url,
            "raw_output": str(content),
        }
    equivalent = parsed.get("equivalent")
    reason = parsed.get("reason")
    if isinstance(equivalent, bool):
        return {
            "used": True,
            "equivalent": equivalent,
            "reason": reason,
            "model": model,
            "base_url": base_url,
            "raw_output": str(content),
        }
    if isinstance(equivalent, str):
        lowered = equivalent.strip().lower()
        if lowered in {"true", "false"}:
            return {
                "used": True,
                "equivalent": lowered == "true",
                "reason": reason,
                "model": model,
                "base_url": base_url,
                "raw_output": str(content),
            }
    return {
        "used": True,
        "equivalent": None,
        "reason": reason,
        "model": model,
        "base_url": base_url,
        "raw_output": str(content),
    }


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


@scorer(metrics=[accuracy(), stderr()])
def repo_reason_scorer():
    """Inspect AI scorer for the reporeason benchmark."""

    def _stop_metadata(state) -> dict[str, Any] | None:
        metadata = state.metadata or {}
        if metadata.get("opencode"):
            return None
        stop_reason = getattr(state.output, "stop_reason", None)
        if not stop_reason:
            return None
        return {"stop_reason": stop_reason}

    async def score(state, target: Target) -> Score:
        completion = state.output.completion or ""
        parsed = parse_json_output(completion)
        stop_metadata = _stop_metadata(state)
        if not parsed:
            expected = normalize_expected(target)
            judge = None
            if completion.strip() and expected:
                expected_text = (
                    expected[0]
                    if len(expected) == 1
                    else json.dumps(expected, ensure_ascii=True)
                )
                mask = (state.metadata or {}).get("mask") or {}
                assertion = mask.get("assertion_statement")
                masked = mask.get("masked_statement")
                judge = llm_judge_equivalence(
                    assertion_line=assertion,
                    masked_line=masked,
                    expected=expected_text,
                    candidate=completion,
                )
                if judge and judge.get("used"):
                    parse_metadata = {"judge": judge, "parse_failed": True}
                    if stop_metadata:
                        parse_metadata.update(stop_metadata)
                    return Score(
                        value=CORRECT if judge.get("equivalent") else INCORRECT,
                        answer=None,
                        explanation=(
                            "Parsed JSON not found; judge used on raw output."
                        ),
                        metadata=parse_metadata,
                    )
            parse_metadata: dict[str, Any] = {"parse_failed": True}
            if judge and judge.get("used"):
                parse_metadata["judge"] = judge
            if stop_metadata:
                parse_metadata.update(stop_metadata)
            return Score(
                value=INCORRECT,
                answer=None,
                explanation="No JSON found",
                metadata=parse_metadata,
            )

        answer_value = parsed.get("answer")
        expected_source = target
        if hasattr(target, "__len__") and not isinstance(target, (str, bytes)):
            try:
                expected_source = list(target)
            except TypeError:
                expected_source = target
        elif hasattr(target, "text"):
            expected_source = target.text
        expected = normalize_expected(expected_source)
        candidates: list[str]
        candidates = normalize_candidate(answer_value)
        correct = any(candidate in expected for candidate in candidates)

        judge = None
        if not correct and candidates:
            mask = (state.metadata or {}).get("mask") or {}
            assertion = mask.get("assertion_statement")
            masked = mask.get("masked_statement")
            for candidate in candidates:
                for expected_item in expected:
                    judge = llm_judge_equivalence(
                        assertion_line=assertion,
                        masked_line=masked,
                        expected=expected_item,
                        candidate=candidate,
                    )
                    if not judge:
                        continue
                    if judge.get("used"):
                        correct = bool(judge.get("equivalent"))
                        break
                if correct or (judge and judge.get("used")):
                    break

        answer = candidates[0] if candidates else None
        explanation = parsed.get("reason") or completion
        metadata: dict[str, Any] | None = None
        if judge and judge.get("used"):
            metadata = {"judge": judge}
        if stop_metadata:
            metadata = metadata or {}
            metadata.update(stop_metadata)
        return Score(
            value=CORRECT if correct else INCORRECT,
            answer=answer,
            explanation=explanation,
            metadata=metadata,
        )

    return score
