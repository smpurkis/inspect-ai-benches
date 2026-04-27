"""Visible tests for git secret forensics benchmark (4 tests)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import forensics_utils as utils


REPO = utils.REPO

# Expected repo structure (from create_repo.py)
EXPECTED_BRANCHES = {"main"}
EXPECTED_TAGS = {"v1.0"}
EXPECTED_COMMIT_COUNT = 62  # 60 linear + 1 merge + 1 feature branch commit


def test_secret_not_in_current_files() -> None:
    """No secret pattern appears anywhere in the current working tree."""
    patterns = utils.read_patterns()
    for pattern in patterns:
        result = subprocess.run(
            ["grep", "-rF", "--exclude-dir=.git", pattern, str(REPO)],
            capture_output=True, text=True,
        )
        # Exclude secret-patterns.txt itself (that's the manifest)
        matching_lines = [
            line for line in result.stdout.strip().splitlines()
            if "secret-patterns.txt" not in line
        ]
        assert not matching_lines, (
            f"Secret pattern {pattern!r} found in working tree:\n"
            + "\n".join(matching_lines[:5])
        )


def test_secret_not_in_commit_history() -> None:
    """No secret pattern appears in any reachable commit diff."""
    patterns = utils.read_patterns()
    for pattern in patterns:
        result = utils.run_git(
            "log", "-p", "--all", "--notes", "-S", pattern,
            check=False,
        )
        assert pattern not in result.stdout, (
            f"Secret pattern {pattern!r} still found in commit history "
            f"(git log -p --all -S)"
        )


def test_secret_not_in_tag_messages() -> None:
    """No secret pattern appears in any annotated tag message."""
    patterns = utils.read_patterns()
    tags = utils.run_git("tag", "-l").stdout.strip().splitlines()
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        content = utils.run_git("cat-file", "-p", tag, check=False).stdout
        for pattern in patterns:
            assert pattern not in content, (
                f"Secret pattern {pattern!r} found in tag {tag!r} message"
            )


def test_repo_structure_preserved() -> None:
    """Branch names, tag names, and commit count must be preserved."""
    # Branches
    result = utils.run_git("branch", "--format=%(refname:short)")
    branches = {b.strip() for b in result.stdout.strip().splitlines() if b.strip()}
    assert branches == EXPECTED_BRANCHES, (
        f"Expected branches {EXPECTED_BRANCHES}, got {branches}"
    )

    # Tags
    result = utils.run_git("tag", "-l")
    tags = {t.strip() for t in result.stdout.strip().splitlines() if t.strip()}
    assert tags == EXPECTED_TAGS, (
        f"Expected tags {EXPECTED_TAGS}, got {tags}"
    )

    # Commit count on main
    result = utils.run_git("rev-list", "--count", "main")
    count = int(result.stdout.strip())
    assert count == EXPECTED_COMMIT_COUNT, (
        f"Expected {EXPECTED_COMMIT_COUNT} commits on main, got {count}"
    )
