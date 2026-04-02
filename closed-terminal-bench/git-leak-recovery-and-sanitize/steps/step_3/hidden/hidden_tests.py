from __future__ import annotations

import pathlib
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


def test_hidden_file_paths_match_reference(rewrite_done) -> None:
    """All file path sets must match the reference at every commit."""
    expected = integrity_check.load_reference()
    actual = integrity_check.build_actual_manifest()
    for i, (exp, act) in enumerate(zip(expected["commits"], actual["commits"])):
        exp_paths = {f["path"] for f in exp["files"]}
        act_paths = {f["path"] for f in act["files"]}
        assert act_paths == exp_paths, f"file path set mismatch at commit index {i}"


def test_hidden_git_notes_content_clean() -> None:
    """Git notes must survive the rewrite and their content must not contain secrets."""
    secrets = integrity_check.read_secrets()
    result = integrity_check.run_git("notes", "--ref", "refs/notes/commits", "list")
    note_lines = [l for l in result.splitlines() if l.strip()]
    assert len(note_lines) > 0, "all git notes were deleted — notes must be preserved"
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
    assert not findings, f"secrets still present in git notes blobs: {findings[:5]}"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
