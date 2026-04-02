from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess


REPO = pathlib.Path("/app/repo")


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def hook_paths() -> tuple[pathlib.Path, pathlib.Path]:
    hooks_dir = REPO / ".git" / "hooks"
    return hooks_dir / "pre-commit", hooks_dir / "secret-patterns"


def write_patterns(patterns: list[str]) -> pathlib.Path:
    _, patterns_file = hook_paths()
    patterns_file.write_text("\n".join(patterns) + "\n", encoding="utf-8")
    return patterns_file


def stage_file(relpath: str, content: str) -> None:
    path = REPO / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run_git("add", relpath)


def capture_index_and_status() -> dict[str, str]:
    tree = run_git("write-tree").stdout.strip()
    cached_diff = run_git("diff", "--cached", "--binary").stdout
    cached_hash = hashlib.sha256(cached_diff.encode("utf-8")).hexdigest()
    status = run_git("status", "--porcelain=v1").stdout
    return {"tree": tree, "cached_hash": cached_hash, "status": status}


def commit(message: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Agent")
    env.setdefault("GIT_AUTHOR_EMAIL", "agent@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Agent")
    env.setdefault("GIT_COMMITTER_EMAIL", "agent@example.com")
    return subprocess.run(
        ["git", "-C", str(REPO), "commit", "-m", message],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def commit_amend(message: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Agent")
    env.setdefault("GIT_AUTHOR_EMAIL", "agent@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Agent")
    env.setdefault("GIT_COMMITTER_EMAIL", "agent@example.com")
    return subprocess.run(
        ["git", "-C", str(REPO), "commit", "--amend", "-m", message],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def reset_repo(head_oid: str) -> None:
    run_git("reset", "--hard", head_oid)
    run_git("clean", "-fd")
