import json
import subprocess
from pathlib import Path

FILES = Path("/app/files")


def _build():
    result = subprocess.run(
        ["make", "-C", str(FILES), "all"], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def _run(document, operation):
    _build()
    request = json.dumps({"document": document, "operation": operation}) + "\n"
    result = subprocess.run(
        ["node", str(FILES / "build/cli.js")], input=request,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_normal_copy_primitive():
    result = _run({"source": 7}, {"op": "copy", "from": "/source", "path": "/copy"})
    assert result == {"ok": True, "result": {"source": 7, "copy": 7}}


def test_edge_move_array_index_uses_post_removal_array():
    result = _run(["a", "b", "c", "d"], {"op": "move", "from": "/1", "path": "/3"})
    assert result == {"ok": True, "result": ["a", "c", "d", "b"]}


def test_invariant_missing_source_does_not_mutate_document():
    original = {"stable": [1, 2]}
    result = _run(original, {"op": "move", "from": "/missing", "path": "/x"})
    assert result["ok"] is False and result["document"] == original


def test_determinism_repeated_operation():
    document = {"a/b": {"value": True}}
    operation = {"op": "copy", "from": "/a~1b/value", "path": "/again"}
    assert _run(document, operation) == _run(document, operation)
