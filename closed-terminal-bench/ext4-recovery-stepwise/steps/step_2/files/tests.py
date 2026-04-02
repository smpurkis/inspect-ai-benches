"""Step 2 visible tests — recover Go extractor and produce workspace."""
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
    """Dump a file from the ext4 image to a local path."""
    proc = subprocess.run(
        ["debugfs", "-R", f"dump {fspath} {local_path}", str(image)],
        capture_output=True,
    )
    return proc.returncode == 0 and local_path.exists()


# ── Tests ────────────────────────────────────────────────────────────────

def test_go_source_found() -> None:
    """The Go extractor source exists in the repaired disk image."""
    proc = subprocess.run(
        ["debugfs", "-R", "stat project/src/extractor.go", str(IMAGE)],
        capture_output=True, text=True,
    )
    assert "Type:" in proc.stdout, "project/src/extractor.go not found in image"


def test_extractor_builds() -> None:
    """The extractor binary exists and is executable."""
    assert EXTRACTOR.exists(), f"{EXTRACTOR} not found"
    assert EXTRACTOR.stat().st_size > 0, "extractor binary is empty"


def test_extractor_runs() -> None:
    """Extractor processes the payload from the image without errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        payload = tmp / "payload.tar.gz"
        debugfs_dump(IMAGE, "project/data/payload.tar.gz", payload)
        assert payload.exists(), "Failed to extract payload from image"

        out_dir = tmp / "workspace"
        result = subprocess.run(
            [str(EXTRACTOR), str(payload), str(out_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"Extractor failed (rc={result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
        # Should have produced at least one file
        produced = list(out_dir.rglob("*"))
        assert len(produced) > 0, "Extractor produced no output files"


def test_workspace_tree() -> None:
    """Workspace has the expected directory structure."""
    ref = json.loads((REFS / "workspace_tree.json").read_text())
    missing = []
    for relpath in ref["files"]:
        if not (WORKSPACE / relpath).exists():
            missing.append(relpath)
    assert not missing, f"Missing workspace files: {missing}"


def test_sentinel_present() -> None:
    """The sentinel_alpha.txt file exists in the workspace."""
    p = WORKSPACE / "data" / "sentinel_alpha.txt"
    assert p.exists(), f"{p} not found"
    assert p.stat().st_size > 0, "sentinel_alpha.txt is empty"


def test_sentinel_content() -> None:
    """sentinel_alpha.txt content matches the reference hash."""
    ref = json.loads((REFS / "sentinel_hashes.json").read_text())
    p = WORKSPACE / "data" / "sentinel_alpha.txt"
    actual = sha256hex(p.read_bytes())
    assert actual == ref["data/sentinel_alpha.txt"], (
        "sentinel_alpha.txt hash mismatch"
    )


if __name__ == "__main__":
    import subprocess as _sp
    raise SystemExit(_sp.call(["python3", "-m", "pytest", __file__, "-v"]))
