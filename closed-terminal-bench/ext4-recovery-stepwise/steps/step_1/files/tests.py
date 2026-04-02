"""Step 1 visible tests — repair and recover ext4 disk image."""
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
    """Read file content from an ext4 image via debugfs."""
    proc = subprocess.run(
        ["debugfs", "-R", f"cat {fspath}", str(image)],
        capture_output=True,
    )
    return proc.stdout


def debugfs_stat(image: Path, fspath: str) -> str:
    """Run debugfs stat on a path and return stdout."""
    proc = subprocess.run(
        ["debugfs", "-R", f"stat {fspath}", str(image)],
        capture_output=True, text=True,
    )
    return proc.stdout


# ── Tests ────────────────────────────────────────────────────────────────

def test_image_exists() -> None:
    assert IMAGE.exists(), f"{IMAGE} not found"
    assert IMAGE.stat().st_size > 0, "disk.img is empty"


def test_image_repaired() -> None:
    """e2fsck in check-only mode should report a clean filesystem."""
    result = subprocess.run(
        ["e2fsck", "-f", "-n", str(IMAGE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"e2fsck reports errors (rc={result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_files_accessible() -> None:
    """A known file can be read from the repaired image."""
    content = debugfs_cat(IMAGE, "project/README.md")
    assert len(content) > 0, "project/README.md is empty or unreadable"
    assert b"Recovery Project" in content


def test_directory_tree_structure() -> None:
    """All expected files exist in the repaired image."""
    ref = json.loads((REFS / "reference_tree.json").read_text())
    missing = []
    for fspath in ref["files"]:
        stat_out = debugfs_stat(IMAGE, fspath)
        if "Type:" not in stat_out:
            missing.append(fspath)
    assert not missing, f"Missing files in image: {missing}"


def test_backup_superblock_usable() -> None:
    """The backup superblock at block 32768 is valid and usable by e2fsck."""
    backup_block = (REFS / "backup_superblock_group.txt").read_text().strip()
    result = subprocess.run(
        ["e2fsck", "-b", backup_block, "-n", str(IMAGE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"e2fsck -b {backup_block} -n failed (rc={result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_inode_file_accessible() -> None:
    """After repair, corpus.dat inode shows Type: Regular and non-zero size."""
    stat_out = debugfs_stat(IMAGE, "project/data/corpus.dat")
    assert "type: regular" in stat_out.lower(), (
        f"corpus.dat is not a regular file after repair:\n{stat_out}"
    )
    m = re.search(r"Size:\s+(\d+)", stat_out)
    assert m is not None, f"Could not parse size from stat output:\n{stat_out}"
    size = int(m.group(1))
    assert size > 0, f"corpus.dat has zero size after repair: {stat_out}"


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
