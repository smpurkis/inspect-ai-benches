import os
import shutil
import subprocess
from pathlib import Path

FILES = Path(os.environ.get("TASK_FILES", "/app/files"))
WORK = Path(os.environ.get("TASK_WORK", "/tmp/raft-public"))


def stage():
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.copytree(FILES, WORK, ignore=shutil.ignore_patterns("tests.py", "contract.toml", "TASK.md", "instructions.md"))


def test_public_contract():
    stage()
    result = subprocess.run(
        ["go", "test", "./..."], cwd=WORK, text=True, capture_output=True, timeout=180,
        env={**os.environ, "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off"},
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
