from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "files"))

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


def test_hidden_secrets_not_in_pack_files() -> None:
    secrets = history_scan.read_secrets()
    result = history_scan.run_git(
        "cat-file", "--batch-all-objects", "--batch-check=%(objecttype) %(objectname)",
        check=False
    )
    findings = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] not in ("blob", "commit", "tag"):
            continue
        oid = parts[1]
        content = history_scan.run_git("cat-file", "-p", oid, check=False)
        if content.returncode == 0:
            for secret in secrets:
                if secret in content.stdout:
                    findings.append(f"{parts[0]}:{oid}:{secret[:20]}")
    assert not findings, f"secrets found in pack-file objects: {findings[:5]}"


def test_hidden_secrets_not_in_reflog() -> None:
    """Reflogs must not contain secrets after a proper history rewrite and reflog expiry."""
    secrets = history_scan.read_secrets()
    result = history_scan.run_git("reflog", "--all", "--format=%H %gs", check=False)
    findings = []
    for line in result.stdout.splitlines():
        for secret in secrets:
            if secret in line:
                findings.append(line[:80])
                break
    assert not findings, f"secrets found in reflog entries: {findings[:5]}"


def test_hidden_author_committer_assignments(rewrite_done) -> None:
    """Author/committer assignments must match the original repo exactly.
    Alice authored 35, Bob authored 15, Agent committed 5."""
    commits = history_scan.get_all_commit_metadata()
    assert len(commits) == 50, f"expected 50 commits, got {len(commits)}"

    alice_authored = sum(1 for c in commits if c["author_name"] == "Alice Developer")
    bob_authored = sum(1 for c in commits if c["author_name"] == "Bob Smith")
    agent_committed = sum(1 for c in commits if c["committer_name"] == "Agent")

    assert alice_authored == 35, (
        f"Alice authored {alice_authored} commits, expected 35"
    )
    assert bob_authored == 15, (
        f"Bob authored {bob_authored} commits, expected 15"
    )
    assert agent_committed == 5, (
        f"Agent committed {agent_committed} commits, expected 5"
    )


def test_hidden_file_trees_preserved(rewrite_done) -> None:
    """File paths at HEAD must match the expected set from the original repo."""
    commits = history_scan.get_all_commit_metadata()
    assert len(commits) >= 1, "no commits found"

    expected_head_files = {
        "README.md", "src/app.py", "src/utils.py", "src/config.py",
        "config/settings.cfg", "config/api.cfg",
        "tests/test_app.py", "docs/changelog.md",
    }

    result = history_scan.run_git("ls-tree", "-r", "--name-only", "HEAD")
    actual = set(result.stdout.splitlines())
    assert actual == expected_head_files, (
        f"file tree at HEAD mismatch: "
        f"missing={expected_head_files - actual}, extra={actual - expected_head_files}"
    )

    # Spot-check initial commit has the same files
    result0 = history_scan.run_git("ls-tree", "-r", "--name-only", commits[0]["hash"])
    actual0 = set(result0.stdout.splitlines())
    assert actual0 == expected_head_files, (
        f"file tree at initial commit mismatch: "
        f"missing={expected_head_files - actual0}, extra={actual0 - expected_head_files}"
    )


def test_hidden_no_dangling_secret_objects(rewrite_done) -> None:
    """Unreachable/dangling objects must not contain secrets after GC."""
    secrets = history_scan.read_secrets()
    result = history_scan.run_git("fsck", "--unreachable", "--no-reflogs", check=False)
    findings = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "blob":
            oid = parts[2]
            blob = history_scan.run_git("cat-file", "-p", oid, check=False)
            if blob.returncode == 0:
                for secret in secrets:
                    if secret in blob.stdout:
                        findings.append(oid)
    assert not findings, f"secrets found in loose/unreachable blobs: {findings[:5]}"


def test_hidden_fingerprinted_format_in_notes_and_blobs() -> None:
    """REDACTED-<hex8> format must be used in notes and file blobs, not generic placeholders."""
    import hashlib
    secrets = history_scan.read_secrets()
    expected_repls = set()
    for secret in secrets:
        h = hashlib.sha256(secret.encode()).hexdigest()[:8]
        expected_repls.add(f"REDACTED-{h}")

    # Check git notes — note on commit 30 had a secret
    result = history_scan.run_git("notes", "list", check=False)
    note_content = ""
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 1:
            blob = history_scan.run_git("cat-file", "-p", parts[0], check=False)
            if blob.returncode == 0:
                note_content += blob.stdout
    if note_content:
        found_in_notes = any(r in note_content for r in expected_repls)
        assert found_in_notes, (
            f"git notes must use REDACTED-<hex8> format, "
            f"expected one of {expected_repls} in note content"
        )

    # Spot-check blobs: at least one blob must contain a fingerprinted replacement
    result = history_scan.run_git(
        "cat-file", "--batch-all-objects",
        "--batch-check=%(objecttype) %(objectname)",
        check=False,
    )
    found_in_any_blob = False
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "blob":
            continue
        oid = parts[1]
        content = history_scan.run_git("cat-file", "-p", oid, check=False)
        if content.returncode == 0:
            if any(r in content.stdout for r in expected_repls):
                found_in_any_blob = True
                break
    assert found_in_any_blob, (
        f"no blob contains fingerprinted replacement — "
        f"expected REDACTED-<hex8> format in file contents"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
