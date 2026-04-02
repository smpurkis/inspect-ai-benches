#!/usr/bin/env python3

from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Sequence


def init_details(step_names: Sequence[str]) -> dict:
    return {
        "steps": {name: {"gate_result": "not_run"} for name in step_names},
    }


def summarize_pytest_output(stdout_text: str) -> dict:
    lines = stdout_text.splitlines()
    summary_lines: list[str] = []
    failed_tests: list[str] = []

    capture = False
    for line in lines:
        lower = line.lower()
        if "short test summary info" in lower:
            capture = True
            continue
        if capture:
            if line.strip() == "":
                capture = False
                continue
            summary_lines.append(line)
            if line.strip().startswith("FAILED "):
                failed_tests.append(line.strip())

    result_line = ""
    for line in reversed(lines):
        s = line.strip()
        if " in " in s and (" passed" in s or " failed" in s or " error" in s):
            result_line = s
            break

    return {
        "result_line": result_line,
        "failed_tests": failed_tests,
        "summary_tail": "\n".join(summary_lines[-12:]),
        "output_head": "\n".join(lines[:20]),
        "output_tail": "\n".join(lines[-20:]),
    }


def run_pytest(
    *,
    step_name: str,
    test_files: list[pathlib.Path],
    ctrf_name: str,
    details: dict,
    log_dir: pathlib.Path,
) -> bool:
    cmd = [
        "python3",
        "-m",
        "pytest",
        "--ctrf",
        str(log_dir / ctrf_name),
        "-rA",
        *(str(p) for p in test_files),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    details["steps"][step_name]["command"] = " ".join(cmd)
    details["steps"][step_name]["returncode"] = proc.returncode
    details["steps"][step_name]["pytest"] = summarize_pytest_output(proc.stdout or "")
    details["steps"][step_name]["stderr"] = (proc.stderr or "")[:2000]
    details["steps"][step_name]["gate_result"] = (
        "pass" if proc.returncode == 0 else "fail"
    )
    return proc.returncode == 0


def run_pytest_capture(
    *,
    test_files: list[pathlib.Path],
    ctrf_name: str,
    log_dir: pathlib.Path,
) -> dict:
    cmd = [
        "python3",
        "-m",
        "pytest",
        "--ctrf",
        str(log_dir / ctrf_name),
        "-rA",
        *(str(p) for p in test_files),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "pytest": summarize_pytest_output(proc.stdout or ""),
        "stderr": (proc.stderr or "")[:2000],
        "gate_result": "pass" if proc.returncode == 0 else "fail",
    }


def run_step_with_visible_hidden(
    *,
    step_name: str,
    visible_file: pathlib.Path,
    hidden_file: pathlib.Path,
    details: dict,
    log_dir: pathlib.Path,
) -> bool:
    visible = run_pytest_capture(
        test_files=[visible_file],
        ctrf_name=f"ctrf_{step_name}_visible.json",
        log_dir=log_dir,
    )
    hidden = run_pytest_capture(
        test_files=[hidden_file],
        ctrf_name=f"ctrf_{step_name}_hidden.json",
        log_dir=log_dir,
    )
    details["steps"][step_name]["visible"] = visible
    details["steps"][step_name]["hidden"] = hidden
    step_ok = visible["returncode"] == 0 and hidden["returncode"] == 0
    details["steps"][step_name]["gate_result"] = "pass" if step_ok else "fail"
    return step_ok


def write_stage_status(
    status_path: pathlib.Path,
    step_names: Sequence[str],
    results: Sequence[bool],
) -> None:
    lines = [
        f"{name}={'pass' if ok else 'fail'}" for name, ok in zip(step_names, results)
    ]
    status_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reward(reward_path: pathlib.Path, score: float) -> None:
    reward_path.write_text(f"{score:.6f}", encoding="utf-8")


def write_details(details_path: pathlib.Path, details: dict) -> None:
    details_path.write_text(json.dumps(details, indent=2), encoding="utf-8")


def load_step_instructions(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data
