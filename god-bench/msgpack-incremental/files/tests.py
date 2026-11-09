import os
import shutil
import subprocess
from pathlib import Path

FILES = Path(os.environ.get("TASK_FILES", "/app/files"))
WORK = Path(os.environ.get("TASK_WORK", "/tmp/msgpack-public"))


def stage():
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "src").mkdir(parents=True)
    (WORK / "tests").mkdir()
    for name in ("Cargo.toml",):
        shutil.copy2(FILES / name, WORK / name)
    for name in ("lib.rs", "main.rs", "decode.rs"):
        shutil.copy2(FILES / "src" / name, WORK / "src" / name)
    shutil.copy2(FILES / "rust_tests" / "public.rs", WORK / "tests" / "public.rs")


def test_public_contract():
    stage()
    result = subprocess.run(
        ["cargo", "test", "--offline", "--test", "public"], cwd=WORK,
        text=True, capture_output=True, timeout=180,
        env={**os.environ, "CARGO_NET_OFFLINE": "true"},
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
