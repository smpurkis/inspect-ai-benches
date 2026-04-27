"""Jinja2 template loading for benchmark prompts."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).resolve().parent
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)


def render_task_prompt(
    *,
    file_path: str,
    masked_statement: str,
    repo_dir: str | None = None,
    use_bash_tool: bool = False,
) -> str:
    template = _env.get_template("task_instructions.j2")
    return template.render(
        file_path=file_path,
        masked_statement=masked_statement,
        repo_dir=repo_dir,
        use_bash_tool=use_bash_tool,
    ).strip()


def render_judge_prompt(
    *,
    assertion_line: str,
    masked_line: str,
    expected: str,
    candidate: str,
) -> str:
    template = _env.get_template("judge_equivalence.j2")
    return template.render(
        assertion_line=assertion_line,
        masked_line=masked_line,
        expected=expected,
        candidate=candidate,
    ).strip()
