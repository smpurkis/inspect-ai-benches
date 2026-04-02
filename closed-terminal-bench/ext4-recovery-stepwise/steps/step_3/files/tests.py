"""Step 3 visible tests — Merkle tree manifest tool."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

MANIFEST_TOOL = Path("/app/manifest_tool")
MANIFEST = Path("/app/manifest.txt")
WORKSPACE = Path("/app/workspace")
REFS = Path("/app/references/step3")

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
LINE_RE = re.compile(r"^[0-9a-f]{64}  .+$")


# ── Tests ────────────────────────────────────────────────────────────────

def test_toolchain_builds() -> None:
    """/app/manifest_tool binary exists and is non-empty."""
    assert MANIFEST_TOOL.exists(), f"{MANIFEST_TOOL} not found"
    assert MANIFEST_TOOL.stat().st_size > 0, "manifest_tool is empty"


def test_manifest_exists() -> None:
    """The manifest file was generated and is non-empty."""
    assert MANIFEST.exists(), f"{MANIFEST} not found"
    assert MANIFEST.stat().st_size > 0, "manifest.txt is empty"


def test_manifest_root_hash_on_first_line() -> None:
    """First line of manifest.txt is exactly 64 lowercase hex characters."""
    lines = MANIFEST.read_text().splitlines()
    assert len(lines) >= 1, "manifest.txt has no lines"
    first = lines[0].strip()
    assert HEX64_RE.match(first), (
        f"First line is not a 64-hex root hash: {first!r}"
    )


def test_manifest_has_dir_entries() -> None:
    """At least one manifest line (after the root) ends with '/' (directory entry)."""
    lines = MANIFEST.read_text().splitlines()
    assert len(lines) > 1, "manifest.txt has only the root hash line"
    dir_lines = [l for l in lines[1:] if l.endswith("/")]
    assert len(dir_lines) >= 1, (
        "No directory entries found in manifest. "
        "Bug B (skipping isDir entries) may not have been fixed."
    )


def test_manifest_deterministic() -> None:
    """Running manifest_tool again produces byte-identical output."""
    assert MANIFEST_TOOL.exists(), "manifest_tool not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        second = Path(tmpdir) / "manifest2.txt"
        result = subprocess.run(
            [str(MANIFEST_TOOL), str(WORKSPACE), str(second)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"manifest_tool failed: {result.stderr}"
        )
        assert MANIFEST.read_bytes() == second.read_bytes(), (
            "Manifest output is not deterministic"
        )


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
