"""Step 3 hidden tests — full Merkle tree manifest validation.

Reference values are computed from the known workspace file contents
(see create_disk_image.py) using the correct Merkle algorithm:
  directory_hash = SHA-256(concat of "name\0hash\n" for children sorted by name)
  root_hash = directory_hash of the root directory's children
"""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

MANIFEST_TOOL = Path("/app/manifest_tool")
MANIFEST = Path("/app/manifest.txt")
WORKSPACE = Path("/app/workspace")
REFS = Path("/app/references/step3")


def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Hardcoded reference values (computed from workspace contents) ─────────
#
# These were derived by running the CORRECT Merkle algorithm on the workspace
# files embedded in create_disk_image.py.
#
# Directory hash algorithm:
#   children sorted by name ascending
#   buf = concat of (name + "\0" + child_hash + "\n") for each child
#   dir_hash = SHA-256(buf).hexdigest()

REFERENCE_ROOT_HASH = "2cb01a314de30c316fa6908bbf2d20f55a5d673e492db40cfb12d1e5bbda66dc"

REFERENCE_DIR_HASHES = {
    "config/":    "5eac8ae548f7eb7f738e74e14293211de70042d2933d0164480279aeb18167af",
    "data/":      "d4c0e1b977d48e93ca41b5d43ab1f19e5bc512dce6665f19e596c6956b369a5b",
}

# Total lines in manifest.txt: 1 (root hash) + 6 files + 2 dirs = 9
REFERENCE_TOTAL_LINES = 9

REFERENCE_MANIFEST_HASH = "ee2a6e8cfb0340b0ba16ceccc87f7bf062e0e9a266c95a2118014b177414b1fd"


# ── Tests ────────────────────────────────────────────────────────────────

def test_hidden_root_hash_exact() -> None:
    """First line of manifest.txt matches the correct Merkle root hash."""
    lines = MANIFEST.read_text().splitlines()
    assert len(lines) >= 1, "manifest.txt is empty"
    actual_root = lines[0].strip()
    assert actual_root == REFERENCE_ROOT_HASH, (
        f"Root hash mismatch.\n"
        f"  got:      {actual_root}\n"
        f"  expected: {REFERENCE_ROOT_HASH}\n"
        "Check that Bug A (sort by name not hash) is fixed."
    )


def test_hidden_dir_node_hashes() -> None:
    """At least 3 directory entries appear with correct hashes (spot-check)."""
    lines = MANIFEST.read_text().splitlines()[1:]  # skip root hash line
    actual = {}
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) == 2:
            h, path = parts
            if path.endswith("/"):
                actual[path] = h

    failures = []
    for dir_path, expected_hash in REFERENCE_DIR_HASHES.items():
        got = actual.get(dir_path)
        if got is None:
            failures.append(f"  {dir_path}: MISSING (Bug B may not be fixed)")
        elif got != expected_hash:
            failures.append(
                f"  {dir_path}: got {got}, expected {expected_hash} "
                "(Bug A may not be fixed)"
            )

    assert not failures, "Directory hash mismatches:\n" + "\n".join(failures)


def test_hidden_single_file_change_propagates() -> None:
    """Modifying one workspace file and re-running changes the root hash.

    This verifies that the Merkle tree is actually built bottom-up (not just
    a flat hash of file contents).
    """
    assert MANIFEST_TOOL.exists(), "manifest_tool not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # Copy workspace to a temp dir
        import shutil
        ws_copy = tmp / "workspace"
        shutil.copytree(str(WORKSPACE), str(ws_copy))

        # Generate baseline manifest for the copy
        baseline = tmp / "manifest_base.txt"
        r1 = subprocess.run(
            [str(MANIFEST_TOOL), str(ws_copy), str(baseline)],
            capture_output=True, text=True,
        )
        assert r1.returncode == 0, f"manifest_tool failed: {r1.stderr}"
        base_root = baseline.read_text().splitlines()[0]

        # Modify a file in the workspace copy
        sentinel = ws_copy / "data" / "sentinel_beta.txt"
        assert sentinel.exists(), "data/sentinel_beta.txt not found in workspace"
        sentinel.write_bytes(sentinel.read_bytes() + b"MODIFIED\n")

        # Re-run manifest
        modified = tmp / "manifest_modified.txt"
        r2 = subprocess.run(
            [str(MANIFEST_TOOL), str(ws_copy), str(modified)],
            capture_output=True, text=True,
        )
        assert r2.returncode == 0, f"manifest_tool failed on modified: {r2.stderr}"
        mod_root = modified.read_text().splitlines()[0]

        assert base_root != mod_root, (
            "Root hash did not change after modifying sentinel_beta.txt — "
            "the Merkle tree may not be propagating changes correctly."
        )


def test_hidden_entry_count() -> None:
    """Total lines in manifest.txt (root + files + dirs) matches reference."""
    lines = MANIFEST.read_text().splitlines()
    actual = len(lines)
    assert actual == REFERENCE_TOTAL_LINES, (
        f"Expected {REFERENCE_TOTAL_LINES} lines in manifest.txt, got {actual}.\n"
        "If fewer: Bug B (missing dir entries) may not be fixed.\n"
        "If more: unexpected extra entries present."
    )


def test_hidden_no_extra() -> None:
    """No extra lines in manifest.txt beyond the reference set (set comparison)."""
    ref_text = (REFS / "manifest_reference.txt").read_text()
    ref_lines = set(ref_text.strip().splitlines())
    actual_lines = set(MANIFEST.read_text().strip().splitlines())
    extra = actual_lines - ref_lines
    assert not extra, (
        f"Extra lines not in reference:\n" + "\n".join(sorted(extra))
    )


def test_hidden_e2e_determinism() -> None:
    """Second run of manifest_tool produces byte-identical manifest.txt."""
    assert MANIFEST_TOOL.exists(), "manifest_tool not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        check_manifest = Path(tmpdir) / "manifest_check.txt"
        result = subprocess.run(
            [str(MANIFEST_TOOL), str(WORKSPACE), str(check_manifest)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"manifest_tool re-run failed: {result.stderr}"
        )
        original = MANIFEST.read_bytes()
        rerun = check_manifest.read_bytes()
        assert original == rerun, (
            "End-to-end determinism failure: "
            "second manifest_tool run produced different output"
        )


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
