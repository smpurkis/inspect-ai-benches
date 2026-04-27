"""Hidden tests — comprehensive validation across all three phases.

Phase 1: ext4 disk image repair
Phase 2: Go extractor bug fixes and workspace extraction
Phase 3: Merkle tree manifest correctness

Reference values are computed from the known workspace file contents
(see create_disk_image.py) using the correct Merkle algorithm:
  directory_hash = SHA-256(concat of "name\0hash\n" for children sorted by name)
  root_hash = directory_hash of the root directory's children
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

MANIFEST_TOOL = Path("/app/manifest_tool")
MANIFEST = Path("/app/manifest.txt")
WORKSPACE = Path("/app/workspace")
EXTRACTOR = Path("/app/extractor")
DISK_IMG = Path("/app/disk.img")
REFS = Path("/app/references")


def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Hardcoded reference values (computed from workspace contents) ─────────

REFERENCE_ROOT_HASH = "485e593a44aa288cdd1f1b03ed9d4b8c57b9141c0302ef286e57a896e9dc5578"

REFERENCE_DIR_HASHES = {
    "config/":    "5eac8ae548f7eb7f738e74e14293211de70042d2933d0164480279aeb18167af",
    "data/":      "480b7693e8f91636e5e1b909c42786b399d27089fc1339f3f0da7cf346605b98",
}

# Total lines in manifest.txt: 1 (root hash) + 7 files + 2 dirs = 10
REFERENCE_TOTAL_LINES = 10

REFERENCE_MANIFEST_HASH = "8de991365ade2b186e426d35c1ce0d1a82d19941127efb7ce61e90ebd21c4a51"


# ══════════════════════════════════════════════════════════════════════════
# Phase 1 hidden tests — disk image repair
# ══════════════════════════════════════════════════════════════════════════

def test_hidden_disk_image_clean_fsck() -> None:
    """Repaired disk image passes e2fsck with a clean exit code."""
    result = subprocess.run(
        ["e2fsck", "-n", "-f", str(DISK_IMG)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"e2fsck -n -f reports errors on repaired image.\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )


def test_hidden_all_disk_files_recoverable() -> None:
    """Every file originally written to the image is extractable with correct content."""
    ref_path = REFS / "step1" / "hidden_hashes.json"
    assert ref_path.exists(), f"{ref_path} not found"
    expected_hashes = json.loads(ref_path.read_text())

    with tempfile.TemporaryDirectory() as tmpdir:
        failures = []
        for fspath, expected_hash in expected_hashes.items():
            out_path = Path(tmpdir) / fspath.replace("/", "__")
            result = subprocess.run(
                ["debugfs", "-R", f"dump {fspath} {out_path}", str(DISK_IMG)],
                capture_output=True, text=True,
            )
            if not out_path.exists():
                failures.append(f"  {fspath}: could not extract (debugfs dump failed)")
                continue
            actual_hash = sha256hex(out_path.read_bytes())
            if actual_hash != expected_hash:
                failures.append(
                    f"  {fspath}: hash mismatch (got {actual_hash[:16]}..., "
                    f"expected {expected_hash[:16]}...)"
                )

        assert not failures, (
            f"Disk file recovery failures ({len(failures)}):\n" + "\n".join(failures)
        )


def test_hidden_disk_symlinks_intact() -> None:
    """Symlinks inside the disk image resolve correctly after repair."""
    ref_path = REFS / "step1" / "hidden_symlinks.json"
    assert ref_path.exists(), f"{ref_path} not found"
    expected_symlinks = json.loads(ref_path.read_text())

    failures = []
    for link_path, expected_target in expected_symlinks.items():
        result = subprocess.run(
            ["debugfs", "-R", f"stat {link_path}", str(DISK_IMG)],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        # Fast symlinks store target in inode; debugfs stat shows it
        if expected_target not in combined and "symlink" not in combined.lower():
            # Try reading the symlink target directly
            result2 = subprocess.run(
                ["debugfs", "-R", f"cat {link_path}", str(DISK_IMG)],
                capture_output=True, text=True,
            )
            if expected_target not in result2.stdout:
                failures.append(f"  {link_path} -> {expected_target}: not found or broken")

    assert not failures, (
        "Symlink verification failures:\n" + "\n".join(failures)
    )


def test_hidden_corpus_file_recovered() -> None:
    """The corpus.dat file (whose inode was corrupted) is fully recoverable."""
    ref_path = REFS / "step1" / "hidden_hashes.json"
    expected_hashes = json.loads(ref_path.read_text())
    corpus_key = "project/data/corpus.dat"
    assert corpus_key in expected_hashes, "corpus.dat not in reference hashes"

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "corpus.dat"
        result = subprocess.run(
            ["debugfs", "-R", f"dump {corpus_key} {out_path}", str(DISK_IMG)],
            capture_output=True, text=True,
        )
        assert out_path.exists() and out_path.stat().st_size > 0, (
            "corpus.dat could not be extracted -- inode repair may have failed"
        )
        actual_hash = sha256hex(out_path.read_bytes())
        assert actual_hash == expected_hashes[corpus_key], (
            f"corpus.dat content hash mismatch after repair.\n"
            f"  got:      {actual_hash}\n"
            f"  expected: {expected_hashes[corpus_key]}"
        )


# ══════════════════════════════════════════════════════════════════════════
# Phase 2 hidden tests — extractor and workspace
# ══════════════════════════════════════════════════════════════════════════

def test_hidden_extractor_binary_exists() -> None:
    """The extractor binary was built at /app/extractor."""
    assert EXTRACTOR.exists(), "/app/extractor binary not found"
    assert EXTRACTOR.stat().st_size > 0, "/app/extractor is empty"


def test_hidden_workspace_file_count() -> None:
    """Workspace contains exactly the expected number of files."""
    ref_path = REFS / "step2" / "workspace_file_count.json"
    expected = json.loads(ref_path.read_text())["count"]
    actual_files = [f for f in WORKSPACE.rglob("*") if f.is_file()]
    assert len(actual_files) == expected, (
        f"Expected {expected} files in workspace, found {len(actual_files)}.\n"
        f"Files found: {sorted(str(f.relative_to(WORKSPACE)) for f in actual_files)}"
    )


def test_hidden_workspace_all_hashes() -> None:
    """Every workspace file has the correct SHA-256 hash (catches truncation, append bugs)."""
    ref_path = REFS / "step2" / "workspace_hashes.json"
    expected_hashes = json.loads(ref_path.read_text())

    failures = []
    for rel_path, expected_hash in expected_hashes.items():
        full_path = WORKSPACE / rel_path
        if not full_path.exists():
            failures.append(f"  {rel_path}: MISSING")
            continue
        actual_hash = sha256hex(full_path.read_bytes())
        if actual_hash != expected_hash:
            actual_size = full_path.stat().st_size
            failures.append(
                f"  {rel_path}: hash mismatch (size={actual_size}, "
                f"got {actual_hash[:16]}..., expected {expected_hash[:16]}...)"
            )

    assert not failures, (
        f"Workspace file hash failures ({len(failures)}):\n" + "\n".join(failures)
    )


def test_hidden_large_corpus_not_truncated() -> None:
    """large_corpus.dat is exactly 8MB -- tests that the LimitReader is correct."""
    large_corpus = WORKSPACE / "data" / "large_corpus.dat"
    assert large_corpus.exists(), "data/large_corpus.dat not found in workspace"
    actual_size = large_corpus.stat().st_size
    expected_size = 8 * 1024 * 1024  # 8 MB exactly
    assert actual_size == expected_size, (
        f"data/large_corpus.dat is {actual_size} bytes, expected {expected_size}.\n"
        f"The LimitReader may be truncating files "
        f"(diff = {expected_size - actual_size} bytes)."
    )


def test_hidden_extractor_deterministic_rerun() -> None:
    """Running the extractor a second time produces byte-identical workspace files."""
    assert EXTRACTOR.exists(), "/app/extractor not found"

    # Find the payload in the disk image
    ref_path = REFS / "step2" / "workspace_hashes.json"
    expected_hashes = json.loads(ref_path.read_text())

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract payload from disk image
        payload_tmp = Path(tmpdir) / "payload.tar.gz"
        subprocess.run(
            ["debugfs", "-R",
             f"dump project/data/payload.tar.gz {payload_tmp}",
             str(DISK_IMG)],
            capture_output=True, text=True,
        )
        if not payload_tmp.exists():
            # Payload might already be extracted elsewhere; skip gracefully
            return

        ws2 = Path(tmpdir) / "workspace2"
        result = subprocess.run(
            [str(EXTRACTOR), str(payload_tmp), str(ws2)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"Extractor re-run failed: {result.stderr[:500]}"
        )

        # Compare file-by-file
        failures = []
        for rel_path, expected_hash in expected_hashes.items():
            f2 = ws2 / rel_path
            if not f2.exists():
                failures.append(f"  {rel_path}: missing in second run")
                continue
            h2 = sha256hex(f2.read_bytes())
            if h2 != expected_hash:
                failures.append(f"  {rel_path}: hash differs on second run")

        assert not failures, (
            "Extractor output not deterministic across runs:\n"
            + "\n".join(failures)
        )


def test_hidden_workspace_symlink_is_symlink() -> None:
    """data/latest_sentinel.txt must be a real symlink, not a regular file.

    The tar payload contains a symlink entry for data/latest_sentinel.txt
    pointing to sentinel_alpha.txt.  The buggy extractor writes the link
    target string as file content instead of creating an actual symlink.
    """
    link_path = WORKSPACE / "data" / "latest_sentinel.txt"
    assert link_path.exists(), (
        "data/latest_sentinel.txt not found in workspace"
    )
    assert link_path.is_symlink(), (
        "data/latest_sentinel.txt should be a symlink but is a regular file. "
        "The extractor may not be handling tar symlink entries correctly."
    )
    actual_target = str(link_path.readlink())
    assert actual_target == "sentinel_alpha.txt", (
        f"data/latest_sentinel.txt symlink target is {actual_target!r}, "
        f"expected 'sentinel_alpha.txt'"
    )


def test_hidden_workspace_symlink_content() -> None:
    """data/latest_sentinel.txt resolves to the correct content.

    Verifies that the symlink target (sentinel_alpha.txt) exists and
    that reading through the symlink returns the expected content.
    """
    link_path = WORKSPACE / "data" / "latest_sentinel.txt"
    target_path = WORKSPACE / "data" / "sentinel_alpha.txt"
    assert link_path.exists(), "data/latest_sentinel.txt not found"
    assert target_path.exists(), "data/sentinel_alpha.txt not found"

    ref_path = REFS / "step2" / "workspace_hashes.json"
    expected_hashes = json.loads(ref_path.read_text())
    expected_hash = expected_hashes.get("data/latest_sentinel.txt")
    assert expected_hash is not None, "latest_sentinel.txt not in reference hashes"

    actual_hash = sha256hex(link_path.read_bytes())
    assert actual_hash == expected_hash, (
        f"data/latest_sentinel.txt content hash mismatch.\n"
        f"  got:      {actual_hash}\n"
        f"  expected: {expected_hash}\n"
        "The symlink may not resolve to the correct target."
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 3 hidden tests — Merkle tree manifest
# ══════════════════════════════════════════════════════════════════════════

def test_hidden_root_hash_exact() -> None:
    """First line of manifest.txt matches the correct Merkle root hash."""
    lines = MANIFEST.read_text().splitlines()
    assert len(lines) >= 1, "manifest.txt is empty"
    actual_root = lines[0].strip()
    assert actual_root == REFERENCE_ROOT_HASH, (
        f"Root hash mismatch.\n"
        f"  got:      {actual_root}\n"
        f"  expected: {REFERENCE_ROOT_HASH}"
    )


def test_hidden_dir_node_hashes() -> None:
    """Directory entries appear with correct hashes."""
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
            failures.append(f"  {dir_path}: MISSING")
        elif got != expected_hash:
            failures.append(
                f"  {dir_path}: got {got}, expected {expected_hash}"
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
            "Root hash did not change after modifying sentinel_beta.txt -- "
            "the Merkle tree may not be propagating changes correctly."
        )


def test_hidden_entry_count() -> None:
    """Total lines in manifest.txt (root + files + dirs) matches reference."""
    lines = MANIFEST.read_text().splitlines()
    actual = len(lines)
    assert actual == REFERENCE_TOTAL_LINES, (
        f"Expected {REFERENCE_TOTAL_LINES} lines in manifest.txt, got {actual}."
    )


def test_hidden_no_extra() -> None:
    """No extra lines in manifest.txt beyond the reference set (set comparison)."""
    ref_text = (REFS / "step3" / "manifest_reference.txt").read_text()
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


def test_hidden_manifest_full_hash() -> None:
    """SHA-256 of the entire manifest.txt matches the precomputed reference."""
    actual_hash = sha256hex(MANIFEST.read_bytes())
    assert actual_hash == REFERENCE_MANIFEST_HASH, (
        f"Full manifest hash mismatch.\n"
        f"  got:      {actual_hash}\n"
        f"  expected: {REFERENCE_MANIFEST_HASH}\n"
        "This catches any formatting, ordering, or content error."
    )


def test_hidden_manifest_tool_on_empty_dir() -> None:
    """manifest_tool handles an empty directory without crashing."""
    assert MANIFEST_TOOL.exists(), "manifest_tool not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        empty_dir = Path(tmpdir) / "empty"
        empty_dir.mkdir()
        out = Path(tmpdir) / "empty_manifest.txt"
        result = subprocess.run(
            [str(MANIFEST_TOOL), str(empty_dir), str(out)],
            capture_output=True, text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"manifest_tool crashed on empty directory: {result.stderr[:300]}"
        )
        lines = out.read_text().splitlines()
        # An empty directory should produce at least a root hash line
        assert len(lines) >= 1, "manifest_tool produced no output for empty directory"


# ══════════════════════════════════════════════════════════════════════════
# Additional hardened hidden tests
# ══════════════════════════════════════════════════════════════════════════

def test_hidden_disk_file_permissions() -> None:
    """File permission bits are preserved after repair (especially the executable script).

    The setup script sets project/scripts/build.sh to mode 0100755 (executable).
    After repair, debugfs should report the correct mode.  Most agents focus on
    content recovery and forget to verify or restore permission metadata.
    """
    ref_path = REFS / "step1" / "hidden_permissions.json"
    assert ref_path.exists(), f"{ref_path} not found"
    expected_perms = json.loads(ref_path.read_text())

    failures = []
    for fspath, expected_mode_str in expected_perms.items():
        result = subprocess.run(
            ["debugfs", "-R", f"stat {fspath}", str(DISK_IMG)],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        # debugfs stat output contains "Mode:  0644" or "Mode:  0755" etc.
        import re
        mode_match = re.search(r"Mode:\s+(0\d+)", combined)
        if mode_match is None:
            failures.append(f"  {fspath}: could not read mode from debugfs stat")
            continue
        actual_mode = mode_match.group(1)
        # Compare the lower 12 bits (permission portion).  debugfs may report
        # the full mode (e.g. "0100644") or just the permission bits ("0644").
        # Normalise both to the last 4 characters for comparison.
        actual_perm = actual_mode[-4:] if len(actual_mode) > 4 else actual_mode
        expected_perm = expected_mode_str[-4:] if len(expected_mode_str) > 4 else expected_mode_str
        if actual_perm != expected_perm:
            failures.append(
                f"  {fspath}: mode {actual_perm}, expected {expected_perm}"
            )

    assert not failures, (
        f"Permission verification failures ({len(failures)}):\n"
        + "\n".join(failures)
    )


def test_hidden_disk_directory_structure_intact() -> None:
    """All original directories in the disk image survive repair.

    The image contains 14 directories including a deeply nested path
    (project/deep/level1/.../level5).  Agents that only do a shallow
    repair often lose the deep directory metadata.
    """
    ref_path = REFS / "step1" / "hidden_dir_info.json"
    assert ref_path.exists(), f"{ref_path} not found"
    dir_info = json.loads(ref_path.read_text())
    expected_dirs = dir_info["dirs"]

    failures = []
    for d in expected_dirs:
        result = subprocess.run(
            ["debugfs", "-R", f"stat {d}", str(DISK_IMG)],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        # debugfs stat for a directory will contain "directory" in the type/mode
        if "directory" not in combined.lower():
            failures.append(f"  {d}: not a directory or missing after repair")

    assert not failures, (
        f"Directory structure failures ({len(failures)}):\n"
        + "\n".join(failures)
    )


def test_hidden_deeply_nested_file_content() -> None:
    """The deeply nested file (5 levels deep) has correct content after repair.

    This specifically targets the file at
    project/deep/level1/level2/level3/level4/level5/nested.txt which is
    the hardest file to recover because its directory chain is long and
    any single lost directory inode in the chain makes it inaccessible.
    """
    ref_path = REFS / "step1" / "hidden_hashes.json"
    expected_hashes = json.loads(ref_path.read_text())
    nested_key = "project/deep/level1/level2/level3/level4/level5/nested.txt"
    assert nested_key in expected_hashes, f"{nested_key} not in reference hashes"

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "nested.txt"
        result = subprocess.run(
            ["debugfs", "-R", f"dump {nested_key} {out_path}", str(DISK_IMG)],
            capture_output=True, text=True,
        )
        assert out_path.exists() and out_path.stat().st_size > 0, (
            f"Could not extract deeply nested file {nested_key} -- "
            "deep directory chain may not have been recovered"
        )
        actual_hash = sha256hex(out_path.read_bytes())
        assert actual_hash == expected_hashes[nested_key], (
            f"Deeply nested file content mismatch.\n"
            f"  got:      {actual_hash}\n"
            f"  expected: {expected_hashes[nested_key]}"
        )


def test_hidden_workspace_directory_entries() -> None:
    """Workspace subdirectories (config/, data/) exist as real directories.

    Some extractor bug fixes only create files via MkdirAll on parent
    paths without honouring the explicit TypeDir tar entries.  This test
    checks that config/ and data/ are proper directories with correct
    properties -- not merely side-effects of file extraction.
    """
    for dirname in ("config", "data"):
        dirpath = WORKSPACE / dirname
        assert dirpath.exists(), (
            f"{dirname}/ missing from workspace -- "
            "extractor may not process tar TypeDir entries"
        )
        assert dirpath.is_dir(), (
            f"{dirname} exists but is not a directory"
        )
        # Verify the directory is not empty (contains expected files)
        children = list(dirpath.iterdir())
        assert len(children) > 0, (
            f"{dirname}/ directory is empty -- extraction likely failed"
        )


def test_hidden_manifest_line_format_strict() -> None:
    """Every non-root manifest line uses exactly the format '<64hex>  <path>'.

    The separator is exactly two spaces.  Common mistakes include using a
    single space, a tab, or trailing whitespace.  This catches subtle
    formatting bugs in the manifest tool output.
    """
    import re as _re
    STRICT_LINE_RE = _re.compile(r"^[0-9a-f]{64}  \S.*$")

    lines = MANIFEST.read_text().splitlines()
    assert len(lines) > 1, "manifest.txt has only the root hash or is empty"

    failures = []
    for i, line in enumerate(lines[1:], start=2):
        if not STRICT_LINE_RE.match(line):
            failures.append(f"  line {i}: {line!r}")

    assert not failures, (
        f"Manifest format violations ({len(failures)}):\n"
        + "\n".join(failures[:10])
        + ("\n  ..." if len(failures) > 10 else "")
    )


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
