from __future__ import annotations

import history_scan
import pytest


@pytest.fixture(scope="session")
def rewrite_done():
    """Gate: secrets must be absent from tracked blobs before structural tests run."""
    secrets = history_scan.read_secrets()
    findings = list(history_scan.find_secret_in_tracked_blobs_multi(secrets))
    if findings:
        pytest.fail(
            "secrets still present in tracked blobs — history rewrite not done. "
            f"Found in: {[f['path'] for f in findings[:3]]}"
        )


def test_all_secrets_removed() -> None:
    """Comprehensive check: no secret in blobs, commit messages, tags, notes, or filenames."""
    secrets = history_scan.read_secrets()
    findings: list[str] = []

    for f in history_scan.find_secret_in_tracked_blobs_multi(secrets):
        findings.append(f"blob {f['object'][:12]} ({f['path']})")
    for f in history_scan.find_secret_in_commit_messages_multi(secrets):
        findings.append(f"commit-msg {f['commit'][:12]}")
    for f in history_scan.find_secret_in_tags_multi(secrets):
        findings.append(f"tag {f['ref']} ({f['field']})")
    for f in history_scan.find_secret_in_notes(secrets):
        findings.append(f"note on {f['note_target'][:12]}")

    result = history_scan.run_git("rev-list", "--objects", "--all")
    for line in result.stdout.splitlines():
        if " " not in line:
            continue
        _, path = line.split(" ", 1)
        for secret in secrets:
            if secret in path:
                findings.append(f"filename {path}")
                break

    assert not findings, f"secrets still present in repository: {findings[:10]}"


def test_commit_count_preserved(rewrite_done) -> None:
    """History rewrite must keep all 50 original commits — no squashing or drops."""
    result = history_scan.run_git(
        "rev-list", "--exclude=refs/notes/*", "--count", "--all",
    )
    actual = int(result.stdout.strip())
    assert actual == 50, f"commit count changed: expected 50, got {actual}"


def test_commit_metadata_preserved(rewrite_done) -> None:
    """Author/committer names, emails, and dates must be unchanged after rewrite."""
    commits = history_scan.get_all_commit_metadata()
    assert len(commits) == 50, f"expected 50 commits, got {len(commits)}"

    valid_authors = {"Alice Developer", "Bob Smith"}
    valid_committers = {"Alice Developer", "Bob Smith", "Agent"}
    valid_author_emails = {"alice@dev.example.com", "bob@dev.example.com"}
    valid_committer_emails = {"alice@dev.example.com", "bob@dev.example.com", "agent@example.com"}

    for i, c in enumerate(commits):
        assert c["author_name"] in valid_authors, (
            f"commit {i}: unexpected author {c['author_name']!r}"
        )
        assert c["committer_name"] in valid_committers, (
            f"commit {i}: unexpected committer {c['committer_name']!r}"
        )
        assert c["author_email"] in valid_author_emails, (
            f"commit {i}: unexpected author email {c['author_email']!r}"
        )
        assert c["committer_email"] in valid_committer_emails, (
            f"commit {i}: unexpected committer email {c['committer_email']!r}"
        )


def test_commit_messages_preserved() -> None:
    """All commit messages must be unchanged except secret portions replaced."""
    commits = history_scan.get_all_commit_metadata()
    assert len(commits) == 50, f"expected 50 commits, got {len(commits)}"
    secrets = history_scan.read_secrets()

    # Index 0: initial commit
    assert commits[0]["message"].startswith("Initial project setup"), (
        f"commit 0 message changed: {commits[0]['message'][:80]!r}"
    )

    # Index 15: had secret in message — must be replaced, not empty
    msg_15 = commits[15]["message"]
    for secret in secrets:
        assert secret not in msg_15, (
            f"commit 15 still contains secret in message"
        )
    assert len(msg_15.strip()) > 0, "commit 15 message is empty after rewrite"
    assert "API" in msg_15 or "api" in msg_15 or "config" in msg_15.lower() or "staging" in msg_15.lower(), (
        f"commit 15 message lost its non-secret content: {msg_15[:80]!r}"
    )

    # Index 20: should be unchanged
    assert commits[20]["message"].startswith("Remove hardcoded API key"), (
        f"commit 20 message changed: {commits[20]['message'][:80]!r}"
    )

    # All other routine commits should match "Commit N: routine update"
    routine_indices = set(range(50)) - {0, 15, 20}
    mismatches = []
    for i in routine_indices:
        expected = f"Commit {i}: routine update"
        if not commits[i]["message"].startswith(expected):
            mismatches.append(i)
    assert not mismatches, (
        f"routine commit messages changed at indices: {mismatches[:10]}"
    )


def test_tag_structure_preserved(rewrite_done) -> None:
    """Tag v1.0 must exist and be annotated (not lightweight) after rewrite."""
    result = history_scan.run_git(
        "for-each-ref", "--format=%(refname) %(objecttype)",
        "refs/tags/v1.0", check=False,
    )
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert lines, "tag v1.0 does not exist after rewrite"
    parts = lines[0].split()
    assert len(parts) >= 2, f"unexpected tag format: {lines[0]}"
    assert parts[1] == "tag", (
        f"v1.0 must be an annotated tag, got type {parts[1]!r}"
    )

    # Tag message should be non-empty (secret replaced, not deleted)
    tag_content = history_scan.run_git("cat-file", "-p", "v1.0").stdout
    # Annotated tags have a blank line separating header from message
    if "\n\n" in tag_content:
        message = tag_content.split("\n\n", 1)[1].strip()
        assert len(message) > 0, "tag v1.0 annotation message is empty after rewrite"


def test_git_notes_preserved() -> None:
    """Git notes must survive the rewrite — content changed, not deleted."""
    secrets = history_scan.read_secrets()
    result = history_scan.run_git("notes", "list", check=False)
    note_lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(note_lines) > 0, (
        "all git notes were deleted — notes must be preserved "
        "(with secrets redacted, not dropped)"
    )

    # Notes must not contain secrets
    findings = history_scan.find_secret_in_notes(secrets)
    assert not findings, f"secrets found in git notes: {findings[:5]}"


def test_replacement_uses_fingerprinted_format() -> None:
    """Secrets must be replaced with REDACTED-<hex8> where hex8 = first 8 chars of SHA-256."""
    import hashlib
    secrets = history_scan.read_secrets()
    expected_repls = {}
    for secret in secrets:
        h = hashlib.sha256(secret.encode()).hexdigest()[:8]
        expected_repls[secret] = f"REDACTED-{h}"

    # Commit 15 message had a secret — replacement must use fingerprinted format
    commits = history_scan.get_all_commit_metadata()
    msg_15 = commits[15]["message"]
    found_in_msg = any(r in msg_15 for r in expected_repls.values())
    assert found_in_msg, (
        f"commit 15 message must use REDACTED-<hex8> format, "
        f"expected one of {list(expected_repls.values())}, got: {msg_15[:100]!r}"
    )

    # Tag v1.0 annotation had a secret — must also use fingerprinted format
    tag_content = history_scan.run_git("cat-file", "-p", "v1.0").stdout
    if "\n\n" in tag_content:
        tag_msg = tag_content.split("\n\n", 1)[1]
        found_in_tag = any(r in tag_msg for r in expected_repls.values())
        assert found_in_tag, (
            f"tag v1.0 annotation must use REDACTED-<hex8> format, "
            f"expected one of {list(expected_repls.values())}, got: {tag_msg[:100]!r}"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
