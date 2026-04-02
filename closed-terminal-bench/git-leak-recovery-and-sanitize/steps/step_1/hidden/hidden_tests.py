from __future__ import annotations

import pathlib
import sys
from collections.abc import Iterator

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "files"))

import hook_test_utils


@pytest.fixture(autouse=True)
def isolate_repo_state() -> Iterator[None]:
    start_head = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    hook_test_utils.reset_repo(start_head)
    yield
    hook_test_utils.reset_repo(start_head)


def test_hidden_shell_special_chars_in_pattern() -> None:
    """Patterns containing shell metacharacters must still be blocked.
    Catches: unquoted variable interpolation ($), glob expansion (*),
    and bracket expressions ([) being mishandled by the hook."""
    patterns = ["PRICE=$100-fixed", "glob*.log", "env[PROD]key"]
    hook_test_utils.write_patterns(patterns)

    for i, pattern in enumerate(patterns):
        hook_test_utils.stage_file(
            f"src/hook_hidden_special_{i}.txt",
            f"config contains: {pattern}\n",
        )

        head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
        result = hook_test_utils.commit(f"hidden: special chars {i}")
        assert result.returncode != 0, (
            f"pattern with shell-special chars {pattern!r} was not blocked; "
            "hook likely unquotes patterns or uses regex matching"
        )

        hook_test_utils.reset_repo(head_before)


def test_hidden_pattern_treated_as_fixed_string() -> None:
    """Patterns must be matched as fixed strings, not regular expressions.
    'api.key' should NOT match 'apixkey' (dot is literal, not regex wildcard).
    """
    pattern = "api.key"
    hook_test_utils.write_patterns([pattern])

    # Stage a file containing 'apixkey' — dot-as-wildcard would match, fixed-string won't
    hook_test_utils.stage_file(
        "src/hook_hidden_fixed_str_ok.txt", "apixkey is not the pattern\n"
    )
    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    result = hook_test_utils.commit("hidden: fixed-string safe commit")
    assert result.returncode == 0, (
        "commit with 'apixkey' should succeed when pattern is 'api.key' (fixed-string, dot is literal)"
    )
    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    assert head_after != head_before, "HEAD should advance on clean commit"

    hook_test_utils.reset_repo(head_before)

    # Now stage a file with the literal pattern — must be blocked
    hook_test_utils.stage_file(
        "src/hook_hidden_fixed_str_bad.txt", "config: api.key=secret\n"
    )
    result2 = hook_test_utils.commit("hidden: fixed-string blocked commit")
    assert result2.returncode != 0, (
        "commit with literal 'api.key' should be blocked"
    )


def test_hidden_amend_commit_blocked() -> None:
    """git commit --amend must also be guarded by the hooks.
    First make a clean commit, then try to amend it with a secret in the
    message and with a secret staged into the index."""
    pattern = "amend-escape-secret"
    hook_test_utils.write_patterns([pattern])

    # Make a clean initial commit
    hook_test_utils.stage_file(
        "src/hook_hidden_amend_clean.txt", "clean content\n"
    )
    result = hook_test_utils.commit("hidden: clean base for amend test")
    assert result.returncode == 0, (
        f"clean base commit should succeed:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    head_after_clean = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()

    # Attempt 1: amend with secret in commit message
    before = hook_test_utils.capture_index_and_status()
    result_msg = hook_test_utils.commit_amend(
        f"amended message with {pattern} leaked"
    )
    assert result_msg.returncode != 0, (
        "git commit --amend must be rejected when new message contains secret"
    )
    head_after_msg = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    assert head_after_msg == head_after_clean, "HEAD changed after rejected amend"

    # Attempt 2: amend with secret staged into the index
    hook_test_utils.stage_file(
        "src/hook_hidden_amend_dirty.txt", f"leaked: {pattern}\n"
    )
    result_idx = hook_test_utils.commit_amend("hidden: amend with dirty index")
    assert result_idx.returncode != 0, (
        "git commit --amend must be rejected when staged index contains secret"
    )


def test_hidden_secret_spanning_lines_in_diff() -> None:
    """A secret pattern that is split across two adjacent lines in the staged
    file must still be detected.  Line-by-line grep will miss this."""
    pattern = "SPLIT_SECRET_ACROSS_LINES"
    hook_test_utils.write_patterns([pattern])

    # Split the pattern across two lines inside the file content
    mid = len(pattern) // 2
    first_half = pattern[:mid]
    second_half = pattern[mid:]
    hook_test_utils.stage_file(
        "src/hook_hidden_spanning.txt",
        f"begin {first_half}\n{second_half} end\n",
    )

    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    before = hook_test_utils.capture_index_and_status()
    result = hook_test_utils.commit("hidden: spanning-lines test")
    assert result.returncode != 0, (
        "commit should be rejected when secret pattern spans two adjacent lines "
        "in the staged file — the hook must not scan line-by-line only"
    )

    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    after = hook_test_utils.capture_index_and_status()
    assert head_after == head_before, "HEAD moved after rejected spanning-lines commit"
    assert after == before, "index or worktree changed after spanning-lines rejection"


def test_hidden_rejects_secret_in_binary_staged_file() -> None:
    """A secret embedded in a file with binary content (null bytes) must be caught.
    Git treats files with null bytes as binary and shows 'Binary files differ'
    in diff output — a hook that only greps the diff text will miss the secret.
    The hook must read the actual staged blob content per file."""
    pattern = "binary-embedded-secret-key"
    hook_test_utils.write_patterns([pattern])

    path = hook_test_utils.REPO / "src" / "hook_hidden_binary.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x01HEADER\x00" + pattern.encode() + b"\x00TAIL\x02")
    hook_test_utils.run_git("add", "src/hook_hidden_binary.bin")

    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    result = hook_test_utils.commit("hidden: binary file with secret")
    assert result.returncode != 0, (
        "commit should be rejected — secret in binary file was missed; "
        "hook likely greps 'git diff --cached' output which suppresses binary content"
    )
    hook_test_utils.reset_repo(head_before)


def test_hidden_empty_patterns_does_not_block_clean_commit() -> None:
    """When secret-patterns contains blank/whitespace lines plus one real
    pattern that is NOT in the staged content, a clean commit must succeed.
    Catches hooks that pass empty patterns to grep (empty string matches all)."""
    _, patterns_file = hook_test_utils.hook_paths()
    patterns_file.write_text(
        "\n  \n\t\nthis-pattern-is-not-in-staged-content\n\n",
        encoding="utf-8",
    )

    hook_test_utils.stage_file(
        "src/hook_hidden_empty_patterns.txt",
        "content with no forbidden pattern\n",
    )
    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    result = hook_test_utils.commit("hidden: empty-line patterns test")
    assert result.returncode == 0, (
        f"clean commit was blocked — hook likely treats empty/whitespace lines "
        f"as match-everything patterns:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    assert head_after != head_before, "HEAD did not advance on a clean commit"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
