import copy
import hashlib
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FILES = Path("/app/files")
BUILD = Path("/tmp/json-patch-verifier")
ALLOWED = {
    "Makefile", "TASK.md", "contract.toml", "instructions.md", "package.json",
    "tests.py", "tsconfig.json", "src/applyOperation.ts", "src/cli.ts",
    "src/pointer.ts", "src/types.ts",
}
TRUSTED_HASHES = {
    "Makefile": "4f949d3b6657adb666d042fe0ca20898edc29de1277fbc7d2dd194a242713308",
    "TASK.md": "8e46e540a4611c6837925131e948908808df0303a93f5ee23827a52cea7939f9",
    "contract.toml": "3d7ec96e6cf820e2da88e99406ee4a180337366cf2347f0dc7e37e5ed3c83599",
    "instructions.md": "655928a1994dd8733f5e5720b9e033f16b80487eeddc28194a98bee04e31f513",
    "package.json": "42380383cb681cac698051c349edf4c76680bd1a1efcdf5b3fd7b129aeb24902",
    "tests.py": "69173fe0b9a2e1b0d9b8804bdf8460c9ba7ea5ceb85402acac727e47dfd7b9ce",
    "tsconfig.json": "6dc28129e24cbf0a34a2963d9706be977490469b271e65c48107ea5ae60d0812",
    "src/cli.ts": "a7fbc213fca69d292ba75412b774e24abab83426cdaba23c4efd0e8b937c3bcf",
    "src/pointer.ts": "074d5a7fb3a63355e6c82caf0a1caccda991c58412ba15bad5cca044f779f75e",
    "src/types.ts": "787ca5ae007bb1beb68b9b74955e9e7d74e79d894a1a52ed5bf1ce09b8449128",
}


class OracleError(Exception):
    pass


def _stage():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "src").mkdir(parents=True)
    for relative in ALLOWED:
        source = FILES / relative
        assert source.is_file() and not source.is_symlink(), f"missing/symlink: {relative}"
        target = BUILD / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    actual = {
        str(path.relative_to(FILES)) for path in FILES.rglob("*")
        if path.is_file() and "build" not in path.parts and "__pycache__" not in path.parts
    }
    assert actual == ALLOWED, f"undeclared files: {sorted(actual ^ ALLOWED)}"
    result = subprocess.run(
        ["make", "-C", str(BUILD), "clean", "all"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr[-3000:]


def _run(cases):
    _stage()
    payload = "".join(json.dumps(case, separators=(",", ":")) + "\n" for case in cases)
    result = subprocess.run(
        ["node", str(BUILD / "build/cli.js")], input=payload,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == len(cases)
    return rows


def _tokens(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise OracleError()
    result = []
    for raw in pointer[1:].split("/"):
        decoded = ""
        index = 0
        while index < len(raw):
            if raw[index] != "~":
                decoded += raw[index]
            elif index + 1 < len(raw) and raw[index + 1] in "01":
                decoded += "~" if raw[index + 1] == "0" else "/"
                index += 1
            else:
                raise OracleError()
            index += 1
        result.append(decoded)
    return result


def _index(token, length, end=False):
    if not re.fullmatch(r"0|[1-9][0-9]*", token):
        raise OracleError()
    value = int(token)
    if value >= length + int(end):
        raise OracleError()
    return value


def _read(root, tokens):
    value = root
    for token in tokens:
        if isinstance(value, list):
            value = value[_index(token, len(value))]
        elif isinstance(value, dict) and token in value:
            value = value[token]
        else:
            raise OracleError()
    return value


def _parent(root, tokens):
    if not tokens:
        raise OracleError()
    return _read(root, tokens[:-1]), tokens[-1]


def _remove(root, tokens):
    if not tokens:
        return None, root
    parent, token = _parent(root, tokens)
    if isinstance(parent, list):
        return root, parent.pop(_index(token, len(parent)))
    if isinstance(parent, dict) and token in parent:
        return root, parent.pop(token)
    raise OracleError()


def _add(root, tokens, value):
    if not tokens:
        return value
    if root is None:
        raise OracleError()
    parent, token = _parent(root, tokens)
    if isinstance(parent, list):
        index = len(parent) if token == "-" else _index(token, len(parent), True)
        parent.insert(index, value)
    elif isinstance(parent, dict):
        parent[token] = value
    else:
        raise OracleError()
    return root


def _oracle(document, operation):
    original = copy.deepcopy(document)
    work = copy.deepcopy(document)
    try:
        source = _tokens(operation["from"])
        path = _tokens(operation["path"])
        if operation["op"] == "copy":
            return True, _add(work, path, copy.deepcopy(_read(work, source)))
        if source == path:
            _read(work, source)
            return True, work
        if len(path) > len(source) and path[:len(source)] == source:
            raise OracleError()
        root, value = _remove(work, source)
        return True, _add(root, path, value)
    except (OracleError, KeyError, IndexError, TypeError):
        return False, original


def _escape(token):
    return token.replace("~", "~0").replace("/", "~1")


def _paths(value, prefix=()):
    yield prefix
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _paths(child, prefix + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _paths(child, prefix + (str(index),))


def _pointer(tokens):
    return "" if not tokens else "/" + "/".join(_escape(token) for token in tokens)


def _tree(rng, depth=0):
    if depth >= 3 or rng.random() < 0.35:
        return rng.choice([None, True, False, rng.randint(-20, 20), "x/y", "til~de"])
    if rng.random() < 0.5:
        return [_tree(rng, depth + 1) for _ in range(rng.randint(1, 4))]
    keys = rng.sample(["a", "b/c", "m~n", "0", "", "__proto__"], rng.randint(1, 4))
    return {key: _tree(rng, depth + 1) for key in keys}


def test_protected_scaffold_import_policy_and_direct_call_site():
    _stage()
    source = (BUILD / "src/applyOperation.ts").read_text()
    imports = re.findall(r"from\s+[\"']([^\"']+)", source)
    assert set(imports) <= {"./pointer", "./types"}
    assert not re.search(r"\b(require|eval|Function|process|fetch|XMLHttpRequest)\b", source)
    assert re.search(r"export\s+function\s+applyOperation\s*\(", source)
    assert "applyOperation(request.document, request.operation)" in (BUILD / "src/cli.ts").read_text()
    for relative, expected in TRUSTED_HASHES.items():
        assert hashlib.sha256((FILES / relative).read_bytes()).hexdigest() == expected
        assert hashlib.sha256((BUILD / relative).read_bytes()).hexdigest() == expected


def test_generated_operations_against_independent_oracle():
    rng = random.Random(0x69026902)
    cases = []
    for _ in range(220):
        document = _tree(rng)
        paths = list(_paths(document))
        source = rng.choice(paths)
        operation = rng.choice(["copy", "move"])
        if isinstance(document, dict):
            destination = (rng.choice(["new", "a", "slash/key", "til~key"]),)
        elif isinstance(document, list):
            destination = (rng.choice(["0", str(len(document)), "-"]),)
        else:
            destination = ()
        if rng.random() < 0.35:
            destination = rng.choice(paths)
        op = {"op": operation, "from": _pointer(source), "path": _pointer(destination)}
        cases.append({"document": document, "operation": op})
    rows = _run(cases)
    for case, row in zip(cases, rows):
        ok, value = _oracle(case["document"], case["operation"])
        assert row["ok"] is ok
        if ok:
            assert row["result"] == value
        else:
            assert row["document"] == value


def test_escaped_pointers_array_shifts_and_shared_ancestors():
    cases = [
        {"document": {"a/b": {"m~n": [0, 1]}}, "operation": {"op": "move", "from": "/a~1b/m~0n/0", "path": "/a~1b/m~0n/1"}},
        {"document": {"a": {"left": {"v": 1}, "right": []}}, "operation": {"op": "move", "from": "/a/left", "path": "/a/right/0"}},
        {"document": ["a", "b", "c", "d"], "operation": {"op": "move", "from": "/1", "path": "/3"}},
        {"document": ["a", "b", "c", "d"], "operation": {"op": "move", "from": "/3", "path": "/1"}},
        {"document": {"~1": 4}, "operation": {"op": "copy", "from": "/~01", "path": "/x"}},
    ]
    for case, row in zip(cases, _run(cases)):
        ok, expected = _oracle(case["document"], case["operation"])
        assert ok and row == {"ok": True, "result": expected}


def test_rollback_invalid_destinations_and_self_descendants():
    cases = [
        {"document": {"source": [1], "keep": 2}, "operation": {"op": "move", "from": "/source", "path": "/missing/child"}},
        {"document": {"a": {"b": 1}}, "operation": {"op": "move", "from": "/a", "path": "/a/new"}},
        {"document": [0, 1], "operation": {"op": "move", "from": "/0", "path": "/9"}},
        {"document": {"a/b": {"x": 1}}, "operation": {"op": "move", "from": "/a~1b", "path": "/a~1b/x/y"}},
        {"document": {"a": 1}, "operation": {"op": "copy", "from": "/a", "path": "/bad~2escape"}},
    ]
    rows = _run(cases)
    for case, row in zip(cases, rows):
        assert row["ok"] is False
        assert row["document"] == case["document"]


def test_deep_copy_aliasing_rollback_and_same_path_directly():
    _stage()
    shutil.copyfile("/app/hidden/direct_tests.ts", BUILD / "src/direct_tests.ts")
    result = subprocess.run(
        ["tsc", "-p", str(BUILD / "tsconfig.json")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        ["node", str(BUILD / "build/direct_tests.js")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "direct checks passed\n"


def test_invalid_pointer_and_index_boundaries_are_atomic():
    operations = [
        {"op": "move", "from": "a", "path": "/x"},
        {"op": "copy", "from": "/0", "path": "/01"},
        {"op": "move", "from": "/0", "path": "/-1"},
        {"op": "move", "from": "/0", "path": "/9007199254740992"},
        {"op": "copy", "from": "/-", "path": "/0"},
        {"op": "move", "from": "/0", "path": "/-/x"},
    ]
    cases = [{"document": ["stable", "tail"], "operation": op} for op in operations]
    for case, row in zip(cases, _run(cases)):
        assert row["ok"] is False and row["document"] == case["document"]


def test_repeatability_and_source_is_not_cached():
    first = {"document": {"x": {"v": 1}}, "operation": {"op": "copy", "from": "/x", "path": "/y"}}
    second = {"document": {"x": {"v": 9}}, "operation": first["operation"]}
    rows = _run([first, first, second])
    assert rows[0] == rows[1]
    assert rows[2]["result"]["y"]["v"] == 9
