"""Tests for jinja2 prompt templates (src/prompts/)."""

from __future__ import annotations

from src.prompts import render_judge_prompt, render_task_prompt


def test_render_task_prompt_basic() -> None:
    result = render_task_prompt(
        file_path="tests/test_example.py",
        masked_statement="assert foo == <blank>",
    )
    assert "<blank>" in result
    assert "tests/test_example.py" in result
    assert "FINAL answer" in result


def test_render_task_prompt_with_repo_dir() -> None:
    result = render_task_prompt(
        file_path="tests/test_example.py",
        masked_statement="assert foo == <blank>",
        repo_dir="/repo",
    )
    assert "/repo" in result
    assert "cloned into /repo" in result


def test_render_task_prompt_bash_tool() -> None:
    result = render_task_prompt(
        file_path="tests/test_example.py",
        masked_statement="assert foo == <blank>",
        repo_dir="/repo",
        use_bash_tool=True,
    )
    assert "bash tool" in result


def test_render_task_prompt_no_bash_tool() -> None:
    result = render_task_prompt(
        file_path="tests/test_example.py",
        masked_statement="assert foo == <blank>",
    )
    assert "bash tool" not in result


def test_render_judge_prompt() -> None:
    result = render_judge_prompt(
        assertion_line="assert foo == 1",
        masked_line="assert foo == <blank>",
        expected="1",
        candidate="one",
    )
    assert "assert foo == 1" in result
    assert "assert foo == <blank>" in result
    assert "Expected answer" in result
    assert "Provided answer" in result


def test_render_task_prompt_invalid_examples() -> None:
    result = render_task_prompt(
        file_path="tests/test_example.py",
        masked_statement="assert foo == <blank>",
    )
    assert "Invalid examples" in result
