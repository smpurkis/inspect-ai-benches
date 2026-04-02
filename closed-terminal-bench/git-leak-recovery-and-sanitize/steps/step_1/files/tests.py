from __future__ import annotations

import pathlib
from collections.abc import Iterator

import hook_test_utils
import pytest


SECRET_FILE = pathlib.Path("/app/step_1/hidden/secret.txt")


@pytest.fixture(autouse=True)
def isolate_repo_state() -> Iterator[None]:
    start_head = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    hook_test_utils.reset_repo(start_head)
    yield
    hook_test_utils.reset_repo(start_head)


def test_precommit_rejects_original_secret_and_preserves_index() -> None:
    secret = SECRET_FILE.read_text(encoding="utf-8").strip()
    hook_test_utils.write_patterns([secret])
    hook_test_utils.stage_file(
        "src/hook_visible_block.txt", f"prefix {secret} suffix\n"
    )

    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    before = hook_test_utils.capture_index_and_status()

    result = hook_test_utils.commit("visible: should be rejected")
    assert result.returncode != 0, (
        "commit should be rejected when staged diff has secret"
    )
    output = f"{result.stdout}\n{result.stderr}".lower()
    assert "secret" in output or "pattern" in output, (
        "rejection should describe why commit was blocked"
    )

    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    after = hook_test_utils.capture_index_and_status()
    assert head_after == head_before, "HEAD must not move on hook rejection"
    assert after == before, "index and status changed after rejection"


def test_precommit_allows_clean_commit() -> None:
    secret = SECRET_FILE.read_text(encoding="utf-8").strip()
    hook_test_utils.write_patterns([secret])
    hook_test_utils.stage_file(
        "src/hook_visible_allow.txt", "no forbidden tokens here\n"
    )

    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    result = hook_test_utils.commit("visible: clean commit")
    assert result.returncode == 0, (
        f"clean commit should succeed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    assert head_after != head_before, (
        "HEAD should advance after successful clean commit"
    )


def test_precommit_rejects_patterns_in_commit_message() -> None:
    patterns = ["danger-message-token"]
    hook_test_utils.write_patterns(patterns)
    hook_test_utils.stage_file(
        "src/hook_visible_message_ok.txt", "safe staged payload\n"
    )

    before = hook_test_utils.capture_index_and_status()
    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    result = hook_test_utils.commit("visible message includes danger-message-token")
    assert result.returncode != 0, "message pattern should be blocked"

    output = f"{result.stdout}\n{result.stderr}".lower()
    assert "secret" in output or "pattern" in output, (
        "message rejection should explain blocked pattern"
    )

    after = hook_test_utils.capture_index_and_status()
    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    assert head_after == head_before, "HEAD moved after rejected message"
    assert after == before, "index or worktree changed after message rejection"


def test_precommit_scans_staged_index_not_working_tree() -> None:
    """The hook must scan the staged (index) version of the file, not the
    working-tree copy.  Stage a file with a secret, then overwrite the
    working-tree copy with clean content.  The commit must still be blocked."""
    pattern = "staged-only-secret-token"
    hook_test_utils.write_patterns([pattern])

    # Stage a file that contains the secret
    hook_test_utils.stage_file(
        "src/hook_visible_staged.txt", f"leaked: {pattern}\n"
    )

    # Overwrite the working-tree copy with clean content (index still dirty)
    (hook_test_utils.REPO / "src" / "hook_visible_staged.txt").write_text(
        "clean working tree, no secret here\n", encoding="utf-8"
    )

    head_before = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    before = hook_test_utils.capture_index_and_status()

    result = hook_test_utils.commit("visible: staged-only test")
    assert result.returncode != 0, (
        "commit must be rejected — the staged index still contains the secret "
        "even though the working tree copy is clean"
    )

    head_after = hook_test_utils.run_git("rev-parse", "HEAD").stdout.strip()
    after = hook_test_utils.capture_index_and_status()
    assert head_after == head_before, "HEAD must not move on hook rejection"
    assert after == before, "index and status changed after rejection"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
