"""sanity-bench: inspect-ai tasks (one per category).

15 categories, 20 tasks each — registered as separate @task functions so inspect
can address them individually:

    uv run inspect eval sanity-bench/run.py@math \\
        --model openai-api/local/Qwen3.6-27B-MTP-Q8_0-thinking \\
        --env LOCAL_BASE_URL=http://localhost:8234/v1 \\
        --env LOCAL_API_KEY=secret

Or run all of them by omitting the @suffix:

    uv run inspect eval sanity-bench/run.py --model ...

NOTE: inspect-ai's loader is AST-based — it only discovers `@task` decorators on
top-level `def`s. The per-category functions below are deliberately explicit
(not generated dynamically) so they remain discoverable.

Scoring delegates to `scoring.py` (deterministic — exact / regex / contains /
code_exec / json_schema / length / refusal / composite). See `schema.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from inspect_ai import Task, task  # noqa: E402
from inspect_ai.dataset import Sample  # noqa: E402
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig  # noqa: E402
from inspect_ai.scorer import (  # noqa: E402
    CORRECT,
    INCORRECT,
    PARTIAL,
    Score,
    Scorer,
    Target,
    accuracy,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState, generate  # noqa: E402

from scoring import score as score_response  # noqa: E402


TASKS_DIR = ROOT / "tasks"


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------


def _load_category(category: str) -> list[Sample]:
    yaml_path = TASKS_DIR / f"{category}.yaml"
    data = yaml.safe_load(yaml_path.read_text())
    samples: list[Sample] = []
    for t in data.get("tasks", []):
        if "system" in t:
            input_msgs = [
                ChatMessageSystem(content=t["system"]),
                ChatMessageUser(content=t["prompt"]),
            ]
        else:
            input_msgs = t["prompt"]
        samples.append(
            Sample(
                id=t["id"],
                input=input_msgs,
                target="",
                metadata={
                    "scoring": t["scoring"],
                    "max_tokens": t.get("max_tokens", 512),
                    "temperature": t.get("temperature", 0.0),
                },
            )
        )
    return samples


# ---------------------------------------------------------------------------
# Custom scorer — dispatches to scoring.py based on sample metadata
# ---------------------------------------------------------------------------


@scorer(metrics=[accuracy(), stderr()])
def sanity_scorer() -> Scorer:
    """Reads `metadata.scoring` per sample and dispatches to scoring.py.

    Captures `reasoning_content` (chain-of-thought from local thinking models)
    separately so it's recorded in the eval log but does not pollute the score.
    """

    async def score(state: TaskState, target: Target) -> Score:
        response = state.output.completion or ""

        # Surface reasoning_content if the provider exposed it via an extra
        # field on the assistant message (common with llama-swap thinking
        # variants exposed through openai-api).
        reasoning_text = ""
        try:
            last_assistant = next(
                m for m in reversed(state.messages) if getattr(m, "role", "") == "assistant"
            )
            reasoning_text = getattr(last_assistant, "reasoning", None) or ""
            if not reasoning_text:
                extra = getattr(last_assistant, "model_extra", None) or {}
                reasoning_text = extra.get("reasoning_content", "") or ""
        except StopIteration:
            pass

        scoring_cfg = (state.metadata or {}).get("scoring") or {}
        value, explanation = score_response(response, scoring_cfg)

        if not response and reasoning_text:
            explanation = (
                f"empty content (model used budget on thinking, "
                f"{len(reasoning_text)} chars). " + explanation
            )

        if value >= 0.999:
            label = CORRECT
        elif value <= 0.001:
            label = INCORRECT
        else:
            label = PARTIAL

        return Score(
            value=value,
            answer=response[:300],
            explanation=explanation,
            metadata={
                "label": label,
                "scoring_type": scoring_cfg.get("type"),
                "reasoning_chars": len(reasoning_text),
            },
        )

    return score


# ---------------------------------------------------------------------------
# Task builder
# ---------------------------------------------------------------------------


def _build_task(category: str) -> Task:
    samples = _load_category(category)
    if not samples:
        raise ValueError(f"No samples in tasks/{category}.yaml")
    max_tok = max(s.metadata.get("max_tokens", 512) for s in samples)
    temp = max(s.metadata.get("temperature", 0.0) for s in samples)
    return Task(
        dataset=samples,
        solver=generate(),
        scorer=sanity_scorer(),
        config=GenerateConfig(max_tokens=max_tok, temperature=temp),
    )


# ---------------------------------------------------------------------------
# 15 @task functions, one per category. These MUST be top-level for inspect-ai
# to discover them via AST parsing.
# ---------------------------------------------------------------------------


@task
def general_knowledge() -> Task:
    return _build_task("general_knowledge")


@task
def common_sense() -> Task:
    return _build_task("common_sense")


@task
def math() -> Task:
    return _build_task("math")


@task
def reasoning() -> Task:
    return _build_task("reasoning")


@task
def coding() -> Task:
    return _build_task("coding")


@task
def coding_debug() -> Task:
    return _build_task("coding_debug")


@task
def agentic_coding() -> Task:
    return _build_task("agentic_coding")


@task
def instruction_following() -> Task:
    return _build_task("instruction_following")


@task
def creative_writing() -> Task:
    return _build_task("creative_writing")


@task
def writing() -> Task:
    return _build_task("writing")


@task
def deep_research() -> Task:
    return _build_task("deep_research")


@task
def structured_output() -> Task:
    return _build_task("structured_output")


@task
def safety() -> Task:
    return _build_task("safety")


@task
def tool_use() -> Task:
    return _build_task("tool_use")


@task
def agentic_conversation() -> Task:
    return _build_task("agentic_conversation")
