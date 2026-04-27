"""Shared test utilities for git secret forensics benchmark."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO = Path("/app/repo")
SECRET_FILE = Path("/app/hidden/secret.txt")


def read_patterns() -> list[str]:
    """Read secret patterns from the hidden secret.txt file."""
    lines = SECRET_FILE.read_text().strip().splitlines()
    return [l.strip() for l in lines if l.strip()]


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def all_object_hashes() -> list[str]:
    """Return all object hashes in the repo (reachable and unreachable)."""
    # Use rev-list for reachable, fsck for unreachable
    hashes = set()

    # All reachable objects
    result = run_git(
        "rev-list", "--all", "--objects", check=False,
    )
    for line in result.stdout.strip().splitlines():
        h = line.split()[0] if line.strip() else ""
        if h:
            hashes.add(h)

    # Unreachable objects
    result = run_git("fsck", "--unreachable", "--no-reflogs", check=False)
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            hashes.add(parts[2])
    for line in result.stderr.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("unreachable", "dangling"):
            hashes.add(parts[2])

    return list(hashes)


def object_content(obj_hash: str) -> str:
    """Read the content of a git object, returning empty string on failure."""
    result = run_git("cat-file", "-p", obj_hash, check=False)
    return result.stdout if result.returncode == 0 else ""


def object_type(obj_hash: str) -> str:
    """Return the type of a git object."""
    result = run_git("cat-file", "-t", obj_hash, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""
