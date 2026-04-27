from __future__ import annotations

import base64
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "files"))

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


def test_hidden_secrets_removed_from_tags() -> None:
    """Tag annotation bodies in repo_large must not contain any secret."""
    secrets = integrity_check.read_secrets()
    result = subprocess.run(
        ["git", "-C", str(integrity_check.REPO),
         "for-each-ref", "--format=%(refname) %(objecttype) %(objectname)",
         "refs/tags"],
        capture_output=True, text=True, check=False,
    )
    findings = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        refname, objtype, objname = parts[0], parts[1], parts[2]
        if objtype == "tag":
            try:
                content = integrity_check.run_git("cat-file", "-p", objname)
            except subprocess.CalledProcessError:
                continue
            for secret in secrets:
                if secret in content:
                    findings.append(refname)
                    break
    assert not findings, f"secrets found in tag annotations: {findings[:5]}"


def test_hidden_secret_not_in_any_filename() -> None:
    """No tree object in repo_large history should have a secret in its file path."""
    secrets = integrity_check.read_secrets()
    result = subprocess.run(
        ["git", "-C", str(integrity_check.REPO),
         "rev-list", "--objects", "--all"],
        capture_output=True, text=True, check=False,
    )
    findings = []
    for line in result.stdout.splitlines():
        if " " not in line:
            continue
        _, path = line.split(" ", 1)
        for secret in secrets:
            if secret in path:
                findings.append(path)
                break
    assert not findings, f"secret found in filename(s) in repo_large: {findings[:5]}"


def test_hidden_commit_structure_matches_reference(rewrite_done) -> None:
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


def test_hidden_commit_metadata_preserved(rewrite_done) -> None:
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


def test_hidden_tag_layout_matches_reference(rewrite_done) -> None:
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()
    assert actual["expected_refs"]["tags"] == expected["expected_refs"]["tags"], (
        "tag layout mismatch"
    )


def test_hidden_merge_commit_topology_preserved(rewrite_done) -> None:
    """Merge commits must have exactly 2 parents and match the reference topology."""
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()
    expected_merges = [c for c in expected["commits"] if len(c["parents"]) == 2]
    actual_merges = [c for c in actual["commits"] if len(c["parents"]) == 2]
    assert len(actual_merges) == len(expected_merges), (
        f"merge commit count mismatch: expected {len(expected_merges)}, got {len(actual_merges)}"
    )
    for i, (exp, act) in enumerate(zip(expected_merges, actual_merges)):
        assert act["parents"] == exp["parents"], f"merge commit parent mismatch at merge index {i}"


def test_hidden_repo_large_status_clean(rewrite_done) -> None:
    """repo_large working tree must be clean after the sanitization rewrite."""
    result = subprocess.run(
        ["git", "-C", str(integrity_check.REPO), "status", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    assert not result.stdout.strip(), (
        f"repo_large working tree is not clean after rewrite:\n{result.stdout}"
    )


def test_hidden_repo_large_branch_heads_match_reference() -> None:
    """Branch head refs must match the reference manifest after the rewrite."""
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()
    exp_heads = expected["expected_refs"]["heads"]
    act_heads = actual["expected_refs"]["heads"]
    assert set(act_heads.keys()) == set(exp_heads.keys()), (
        f"branch name mismatch: expected {set(exp_heads.keys())}, got {set(act_heads.keys())}"
    )
    for branch, exp_idx in exp_heads.items():
        assert act_heads[branch] == exp_idx, (
            f"branch {branch!r} points to commit index {act_heads[branch]}, "
            f"expected {exp_idx}"
        )


def test_hidden_cross_line_secret_removed() -> None:
    """Secrets split across lines must also be sanitized (whitespace-collapsed check)."""
    secrets = integrity_check.read_secrets()
    proc = subprocess.run(
        ["git", "-C", str(integrity_check.REPO),
         "cat-file", "--batch-all-objects",
         "--batch-check=%(objecttype) %(objectname)"],
        capture_output=True, text=True, check=False,
    )
    findings = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "blob":
            continue
        oid = parts[1]
        try:
            content = integrity_check.run_git("cat-file", "-p", oid)
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            continue
        content_collapsed = re.sub(r"\s+", "", content)
        for secret in secrets:
            secret_collapsed = re.sub(r"\s+", "", secret)
            if secret_collapsed in content_collapsed:
                findings.append(oid[:12])
                break
    assert not findings, (
        f"secret found when whitespace collapsed (cross-line split not sanitized): "
        f"{findings[:5]}"
    )


def test_hidden_base64_secret_removed() -> None:
    """No blob should contain the base64 encoding of any secret."""
    secrets = integrity_check.read_secrets()
    encoded_variants = [
        base64.b64encode(s.encode()).decode()
        for s in secrets
    ]
    proc = subprocess.run(
        ["git", "-C", str(integrity_check.REPO),
         "cat-file", "--batch-all-objects",
         "--batch-check=%(objecttype) %(objectname)"],
        capture_output=True, text=True, check=False,
    )
    findings = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "blob":
            continue
        oid = parts[1]
        try:
            content = integrity_check.run_git("cat-file", "-p", oid)
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            continue
        for variant in encoded_variants:
            if variant in content:
                findings.append(oid[:12])
                break
    assert not findings, (
        f"base64-encoded secret found in blobs: {findings[:5]}"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
