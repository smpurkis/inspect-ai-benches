from __future__ import annotations

import subprocess

import integrity_check
import pytest


@pytest.fixture(scope="session")
def rewrite_done():
    """Gate: secrets must be absent from blobs before structural tests run."""
    secrets = integrity_check.read_secrets()
    findings = integrity_check.find_secrets_in_blobs(secrets)
    if findings:
        pytest.fail(
            "secrets still present in blobs — history rewrite not done. "
            f"Found in: {findings[:3]}"
        )


def test_secrets_removed_from_blobs() -> None:
    """No blob object in repo_large should contain a secret."""
    secrets = integrity_check.read_secrets()
    findings = integrity_check.find_secrets_in_blobs(secrets)
    assert not findings, f"secrets found in blobs: {findings[:5]}"


def test_secrets_removed_from_commit_messages() -> None:
    """No commit message in repo_large history should contain a secret."""
    secrets = integrity_check.read_secrets()
    findings = integrity_check.find_secrets_in_commit_messages(secrets)
    assert not findings, f"secrets found in commit messages: {findings[:5]}"


def test_commit_structure_matches_reference(rewrite_done) -> None:
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()

    expected_commits = expected["commits"]
    actual_commits = actual["commits"]
    assert len(actual_commits) == len(expected_commits), "commit count mismatch"

    for i, (expected_commit, actual_commit) in enumerate(
        zip(expected_commits, actual_commits)
    ):
        assert actual_commit["parents"] == expected_commit["parents"], (
            f"parent topology mismatch at commit index {i}"
        )
        exp_paths = {f["path"] for f in expected_commit["files"]}
        act_paths = {f["path"] for f in actual_commit["files"]}
        assert act_paths == exp_paths, (
            f"file path set mismatch at commit index {i}"
        )


def test_commit_metadata_preserved(rewrite_done) -> None:
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()

    expected_commits = expected["commits"]
    actual_commits = actual["commits"]
    assert len(actual_commits) == len(expected_commits), "commit count mismatch"

    metadata_fields = [
        "author_name",
        "author_email",
        "author_date",
        "committer_name",
        "committer_email",
        "committer_date",
    ]
    for i, (expected_commit, actual_commit) in enumerate(
        zip(expected_commits, actual_commits)
    ):
        for field in metadata_fields:
            assert actual_commit[field] == expected_commit[field], (
                f"{field} mismatch at commit index {i}"
            )


def test_tag_layout_matches_reference(rewrite_done) -> None:
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()
    assert actual["expected_refs"]["tags"] == expected["expected_refs"]["tags"], (
        "tag layout mismatch"
    )


def test_git_notes_exist_and_secret_free() -> None:
    """Git notes must survive the rewrite and must not contain secrets."""
    secrets = integrity_check.read_secrets()
    result = integrity_check.run_git(
        "notes", "--ref", "refs/notes/commits", "list"
    )
    note_lines = [l for l in result.splitlines() if l.strip()]
    assert len(note_lines) > 0, (
        "all git notes were deleted during sanitization — "
        "notes must be preserved (with secrets redacted, not dropped)"
    )

    # Notes must not contain secrets
    findings = []
    for line in note_lines:
        parts = line.split()
        if len(parts) < 1:
            continue
        note_blob = parts[0]
        try:
            content = integrity_check.run_git("cat-file", "-p", note_blob)
        except subprocess.CalledProcessError:
            continue
        for secret in secrets:
            if secret in content:
                findings.append(note_blob[:12])
                break
    assert not findings, f"secrets still present in git notes: {findings[:5]}"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
