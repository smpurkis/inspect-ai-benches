"""Step 2 hidden tests — thorough workspace and extractor validation."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

IMAGE = Path("/app/disk.img")
EXTRACTOR = Path("/app/extractor")
WORKSPACE = Path("/app/workspace")
REFS = Path("/app/references/step2")


def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def debugfs_dump(image: Path, fspath: str, local_path: Path) -> bool:
    proc = subprocess.run(
        ["debugfs", "-R", f"dump {fspath} {local_path}", str(image)],
        capture_output=True,
    )
    return proc.returncode == 0 and local_path.exists()


def hash_directory(root: Path) -> dict[str, str]:
    """Return {relative_path: sha256} for every regular file under root."""
    result = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(root))
            result[rel] = sha256hex(p.read_bytes())
    return result


# ── Tests ────────────────────────────────────────────────────────────────

def test_hidden_all_hashes() -> None:
    """Every workspace file matches its reference SHA-256."""
    ref = json.loads((REFS / "workspace_hashes.json").read_text())
    for relpath, expected in ref.items():
        p = WORKSPACE / relpath
        assert p.exists(), f"Missing: {relpath}"
        actual = sha256hex(p.read_bytes())
        assert actual == expected, f"Hash mismatch for {relpath}"


def test_hidden_file_count() -> None:
    """Workspace has the exact expected number of files."""
    ref = json.loads((REFS / "workspace_file_count.json").read_text())
    actual_files = [p for p in WORKSPACE.rglob("*") if p.is_file()]
    assert len(actual_files) == ref["count"], (
        f"Expected {ref['count']} files, found {len(actual_files)}"
    )


def test_hidden_binary_integrity() -> None:
    """Binary sentinel file (sentinel_gamma.bin) has correct hash."""
    ref = json.loads((REFS / "workspace_hashes.json").read_text())
    p = WORKSPACE / "data" / "sentinel_gamma.bin"
    assert p.exists(), "sentinel_gamma.bin not found"
    actual = sha256hex(p.read_bytes())
    assert actual == ref["data/sentinel_gamma.bin"], (
        "sentinel_gamma.bin hash mismatch"
    )


def test_hidden_large_file_integrity() -> None:
    """large_corpus.dat exists in workspace with correct size (>= 8 MB) and
    exact SHA-256 matching the hidden reference."""
    ref = json.loads((REFS / "workspace_hashes.json").read_text())
    p = WORKSPACE / "data" / "large_corpus.dat"
    assert p.exists(), "data/large_corpus.dat not found in workspace"
    size = p.stat().st_size
    assert size >= 8 * 1024 * 1024, (
        f"large_corpus.dat is too small: {size} bytes (expected >= 8 MB). "
        "The extractor's 4 MB LimitReader truncation bug may not have been fixed."
    )
    actual = sha256hex(p.read_bytes())
    expected = ref["data/large_corpus.dat"]
    assert actual == expected, (
        f"large_corpus.dat hash mismatch: got {actual}, expected {expected}. "
        "Check that the off-by-one LimitReader bug is fixed."
    )


def test_hidden_deterministic_two_runs() -> None:
    """Running the extractor twice produces identical output for ALL files.

    This catches the non-deterministic map-iteration bug: if files are
    accumulated in a map[string][]byte and written in arbitrary order,
    repeated runs may produce different results or corrupt content.
    Both runs are compared using sorted file listings and SHA-256 hashes.
    """
    assert EXTRACTOR.exists(), "extractor binary not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        payload = tmp / "payload.tar.gz"
        debugfs_dump(IMAGE, "project/data/payload.tar.gz", payload)
        assert payload.exists(), "Failed to extract payload"

        out1 = tmp / "workspace_run1"
        out2 = tmp / "workspace_run2"

        # First run
        r1 = subprocess.run(
            [str(EXTRACTOR), str(payload), str(out1)],
            capture_output=True,
        )
        assert r1.returncode == 0, (
            f"First extraction failed:\n{r1.stderr.decode()}"
        )
        first = hash_directory(out1)

        # Second run into a separate directory
        r2 = subprocess.run(
            [str(EXTRACTOR), str(payload), str(out2)],
            capture_output=True,
        )
        assert r2.returncode == 0, (
            f"Second extraction failed:\n{r2.stderr.decode()}"
        )
        second = hash_directory(out2)

        # Compare sorted file listings
        assert sorted(first.keys()) == sorted(second.keys()), (
            "File listings differ between runs — non-determinism in directory creation"
        )
        # Compare all hashes
        mismatches = [
            k for k in first if first[k] != second.get(k)
        ]
        assert not mismatches, (
            f"Hash mismatches between run 1 and run 2 for: {mismatches}. "
            "The map-iteration non-determinism bug may not have been fixed."
        )


def test_hidden_extractor_rejects_bad_payload() -> None:
    """Extractor returns non-zero exit code on invalid input."""
    assert EXTRACTOR.exists(), "extractor binary not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        bad = tmp / "bad.tar.gz"
        bad.write_bytes(b"this is definitely not a valid gzip file")
        out_dir = tmp / "out"

        result = subprocess.run(
            [str(EXTRACTOR), str(bad), str(out_dir)],
            capture_output=True,
        )
        assert result.returncode != 0, (
            "Extractor should fail on invalid payload"
        )


def test_hidden_extracted_tree_sorted_order() -> None:
    """Sorted file listing of workspace matches reference exactly."""
    ref = json.loads((REFS / "workspace_tree.json").read_text())
    actual = sorted(
        str(p.relative_to(WORKSPACE))
        for p in WORKSPACE.rglob("*") if p.is_file()
    )
    assert actual == ref["files"], (
        f"File listing mismatch:\n  expected: {ref['files']}\n  actual: {actual}"
    )


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
