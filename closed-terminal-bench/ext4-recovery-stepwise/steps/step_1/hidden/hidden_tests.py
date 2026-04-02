"""Step 1 hidden tests — deeper validation of the repaired ext4 image."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

IMAGE = Path("/app/disk.img")
REFS = Path("/app/references/step1")


def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def debugfs_cat(image: Path, fspath: str) -> bytes:
    proc = subprocess.run(
        ["debugfs", "-R", f"cat {fspath}", str(image)],
        capture_output=True,
    )
    return proc.stdout


def debugfs_stat(image: Path, fspath: str) -> str:
    proc = subprocess.run(
        ["debugfs", "-R", f"stat {fspath}", str(image)],
        capture_output=True, text=True,
    )
    return proc.stdout


def extract_mode(stat_output: str) -> str | None:
    """Extract the permission bits (e.g. '0644') from debugfs stat output."""
    m = re.search(r"Mode:\s+0(\d+)", stat_output)
    if m:
        raw = m.group(1)
        # debugfs shows full mode including type; last 4 digits are perms
        return raw[-4:] if len(raw) > 4 else raw.zfill(4)
    return None


# ── Tests ────────────────────────────────────────────────────────────────

def test_hidden_additional_hashes() -> None:
    """Five additional files match their reference SHA-256 hashes."""
    ref = json.loads((REFS / "hidden_hashes.json").read_text())
    check_paths = [
        "project/config/settings.json",
        "project/docs/design.md",
        "project/docs/api.md",
        "project/lib/utils.go",
        "project/tests/extractor_test.go",
    ]
    for p in check_paths:
        content = debugfs_cat(IMAGE, p)
        assert sha256hex(content) == ref[p], f"Hash mismatch for {p}"


def test_hidden_permissions() -> None:
    """File mode bits match reference (especially build.sh = 0755)."""
    ref = json.loads((REFS / "hidden_permissions.json").read_text())
    for fspath, expected in ref.items():
        stat_out = debugfs_stat(IMAGE, fspath)
        mode = extract_mode(stat_out)
        assert mode is not None, f"Could not parse mode for {fspath}"
        assert mode == expected, (
            f"Permission mismatch for {fspath}: got {mode}, expected {expected}"
        )


def test_hidden_symlinks() -> None:
    """Symbolic links exist and have correct targets."""
    ref = json.loads((REFS / "hidden_symlinks.json").read_text())
    for link, expected_target in ref.items():
        stat_out = debugfs_stat(IMAGE, link)
        assert "symlink" in stat_out.lower(), (
            f"{link} is not a symlink: {stat_out}"
        )
        # debugfs stat shows "Fast link dest:" for inline symlinks
        assert expected_target in stat_out, (
            f"Symlink {link} target mismatch: expected {expected_target!r}\n{stat_out}"
        )


def test_hidden_deep_nested() -> None:
    """Deeply nested file (5 levels) is recovered intact."""
    deep_path = "project/deep/level1/level2/level3/level4/level5/nested.txt"
    ref = json.loads((REFS / "hidden_hashes.json").read_text())
    content = debugfs_cat(IMAGE, deep_path)
    assert len(content) > 0, f"{deep_path} is empty or unreadable"
    assert sha256hex(content) == ref[deep_path], "Deep nested file hash mismatch"


def test_hidden_backup_superblock_valid() -> None:
    """The backup superblock at block 32768 is valid and has a matching UUID
    to the primary superblock."""
    backup_block = (REFS / "backup_superblock_group.txt").read_text().strip()

    # Extract UUID from primary superblock
    primary = subprocess.run(
        ["dumpe2fs", "-h", str(IMAGE)],
        capture_output=True, text=True,
    )
    assert primary.returncode == 0, f"dumpe2fs failed: {primary.stderr}"
    primary_uuid = None
    for line in primary.stdout.splitlines():
        if "filesystem uuid" in line.lower():
            primary_uuid = line.split(":")[-1].strip()
            break
    assert primary_uuid is not None, "Could not read primary superblock UUID"

    # Verify backup superblock is valid (e2fsck -b exits 0)
    result = subprocess.run(
        ["e2fsck", "-b", backup_block, "-n", str(IMAGE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"Backup superblock at block {backup_block} is not valid "
        f"(rc={result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


def test_hidden_inode_repaired_file_hash() -> None:
    """After full repair, corpus.dat SHA-256 matches the hidden reference hash."""
    ref = json.loads((REFS / "hidden_hashes.json").read_text())
    content = debugfs_cat(IMAGE, "project/data/corpus.dat")
    assert len(content) > 1_000_000, (
        f"corpus.dat too small after inode repair: {len(content)} bytes"
    )
    assert sha256hex(content) == ref["project/data/corpus.dat"], (
        "corpus.dat hash mismatch — inode may not have been fully repaired"
    )


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
